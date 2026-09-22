# -*- coding: utf-8 -*-
"""
Harvard Justice AI Vocabulary Studio - Enterprise Backend
Features:
1. Multi-course & Series hierarchy
2. User Authentication (Register, Login, Guest mode)
3. Spaced repetition & detailed study time tracking (today & historical time, per-word review counts)
4. Multi-format Exporter: Word (.docx), Markdown (.md), Anki CSV, Eudic/Quizlet TXT, Pure TXT
5. Universal AI Proxy: DeepSeek Official (default), OpenAI-compatible, Anthropic Claude
"""

import http.server
import socketserver
import threading
import json
import urllib.parse
import urllib.request
import urllib.error
import os
import re
import csv
import io
import sys
import time
import hashlib
import base64
import asyncio
from datetime import date
try:
    import edge_tts
except ImportError:
    edge_tts = None
from docx_generator import build_docx_bytes

def _resolve_port():
    """argv[1] wins only when it is a bare port number.

    This used to be `int(sys.argv[1])`, so launching the app through any wrapper
    that passes its own flags (a smoke-test harness, a process manager) crashed
    at import time with `ValueError: invalid literal for int(): '--port'`.
    """
    candidates = [sys.argv[1] if len(sys.argv) > 1 else "",
                  os.environ.get("PORT", "")]
    for candidate in candidates:
        candidate = (candidate or "").strip()
        if candidate.isdigit():
            return int(candidate)
    return 8765


PORT = _resolve_port()


def _app_version():
    """The single source of truth is the VERSION file at the repo root.

    Resolved from this file's own location rather than BASE_DIR, so the constant
    can be defined before BASE_DIR without an import-time NameError.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or "0.0.0"
    except Exception:
        return "0.0.0"


APP_VERSION = _app_version()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DATA_DIR = os.path.join(BASE_DIR, "data")
CURRICULUM_FILE = os.path.join(DATA_DIR, "curriculum_tiered.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_records.json")
FEEDBACK_IMG_DIR = os.path.join(PUBLIC_DIR, "assets", "feedback")
os.makedirs(FEEDBACK_IMG_DIR, exist_ok=True)
AUDIO_DIR = os.path.join(PUBLIC_DIR, "assets", "audio")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STUDY_FILE = os.path.join(DATA_DIR, "study_records.json")
VOCAB_BANK_FILE = os.path.join(DATA_DIR, "vocab_bank.json")
CUSTOM_EPISODES_FILE = os.path.join(DATA_DIR, "custom_episodes.json")

def build_content_disposition(filename):
    """
    Builds an RFC 5987 / RFC 6266 compliant Content-Disposition header value.
    Provides strict ASCII-safe filename fallback and UTF-8 encoded filename* to avoid
    Latin-1 encoding crashes in Python http.server.
    """
    ascii_safe = re.sub(r'[^a-zA-Z0-9\.\-_]', '_', filename)
    ascii_safe = re.sub(r'_+', '_', ascii_safe).strip('_')
    if not ascii_safe or ascii_safe in ('.docx', '.md', '.csv', '.txt'):
        ascii_safe = "study_guide.docx"
    utf8_quoted = urllib.parse.quote(filename, encoding='utf-8')
    return f'attachment; filename="{ascii_safe}"; filename*=UTF-8\'\'{utf8_quoted}'

# ---------------------------------------------------------------------------
# Secrets. NEVER hard-code credentials here: this repository is public.
# Resolution order:
#   1) environment variable DEEPSEEK_API_KEY  (preferred, set in the systemd unit)
#   2) data/secret_config.json -> {"deepseek_api_key": "sk-..."}  (untracked)
# The data/ directory is not served over HTTP (verified: /data/* -> 404).
# ---------------------------------------------------------------------------
SECRET_FILE = os.path.join(DATA_DIR, "secret_config.json")

def load_server_api_key():
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if key:
        return key.split(";", 1)[0].strip() if ";" in key else key
    try:
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            raw = (json.load(f).get("deepseek_api_key") or "").strip()
        # A gateway may hand out "token;model" credentials; only the token is the key.
        return raw.split(";", 1)[0].strip() if ";" in raw else raw
    except Exception:
        return ""


def _ai_setting(env_key, secret_key, default=""):
    """Resolve an AI endpoint setting: environment first, then secret_config.json.

    Hard-coding a single vendor's base URL and model id meant switching to a
    self-hosted gateway (or any OpenAI-compatible endpoint) required editing this
    file. Both are operator settings, so both are configurable now.
    """
    value = (os.environ.get(env_key) or "").strip()
    if value:
        return value
    try:
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            return (json.load(f).get(secret_key) or "").strip() or default
    except Exception:
        return default


# Default AI Configuration (overridable per deployment)
DEFAULT_CONFIG = {
    "provider": _ai_setting("VOCAB_AI_PROVIDER", "provider", "deepseek"),
    "api_base": _ai_setting("VOCAB_AI_BASE", "api_base", "https://api.deepseek.com"),
    "api_key": load_server_api_key(),
    "model": _ai_setting("VOCAB_AI_MODEL", "model", "deepseek-chat"),
}

# Hosts that may ever be contacted with a server API key or as an AI proxy.
ALLOWED_AI_HOSTS = {"api.deepseek.com", "api.openai.com", "api.anthropic.com"}
_CONFIGURED_AI_HOST = urllib.parse.urlparse(DEFAULT_CONFIG["api_base"]).hostname or ""
if _CONFIGURED_AI_HOST:
    ALLOWED_AI_HOSTS.add(_CONFIGURED_AI_HOST)


def ai_base_allowed(api_base):
    """https anywhere in the allowlist; http only for the operator's own gateway.

    A caller-supplied api_base used to be an SSRF hole, so the allowlist stays.
    But an operator-run gateway is typically plain http on a private address, and
    refusing it would make the app unable to use its own configured endpoint.
    """
    parsed = urllib.parse.urlparse(api_base or "")
    if not parsed.hostname or parsed.hostname not in ALLOWED_AI_HOSTS:
        return False
    return parsed.scheme == "https" or parsed.hostname == _CONFIGURED_AI_HOST

# Serialises JSON read-modify-write cycles now that the server is threaded.
_WRITE_LOCK = threading.RLock()

# Ensure data storage files exist
def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(STUDY_FILE):
        with open(STUDY_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(VOCAB_BANK_FILE):
        with open(VOCAB_BANK_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(CUSTOM_EPISODES_FILE):
        with open(CUSTOM_EPISODES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

init_db()

def load_vocab_bank():
    try:
        with open(VOCAB_BANK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_vocab_bank(bank):
    with _WRITE_LOCK:
        with open(VOCAB_BANK_FILE, "w", encoding="utf-8") as f:
            json.dump(bank, f, ensure_ascii=False, indent=2)

def load_custom_episodes():
    try:
        with open(CUSTOM_EPISODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_custom_episodes(episodes):
    with _WRITE_LOCK:
        with open(CUSTOM_EPISODES_FILE, "w", encoding="utf-8") as f:
            json.dump(episodes, f, ensure_ascii=False, indent=2)

def synthesize_audio_sync(text, filepath, voice="en-US-ChristopherNeural"):
    """Synthesizes neural speech using edge-tts."""
    async def _run():
        comm = edge_tts.Communicate(text, voice)
        await comm.save(filepath)
    try:
        asyncio.run(_run())
        return True
    except Exception as e:
        print(f"[TTS Error] {e}")
        return False

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with _WRITE_LOCK:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

def load_study_records():
    try:
        with open(STUDY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_study_records(records):
    with _WRITE_LOCK:
        with open(STUDY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

def parse_query_params(path):
    """Safe query-string parser. Tolerates '=' inside values (e.g. ?username=a=b)."""
    query = path.split("?", 1)[1] if "?" in path else ""
    params = {}
    for pair in query.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[urllib.parse.unquote_plus(k)] = urllib.parse.unquote_plus(v)
    return params

def hash_pw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

# Multi-course Series Data
SERIES_DATA = {
    "harvard_philosophy": {
        "id": "harvard_philosophy",
        "title": "哈佛大学名校哲学系列公开课",
        "desc": "汇聚哈佛最负盛名的哲学与伦理思辨公开课，探索道德真理与社会制度本质",
        "courses": [
            {
                "id": "justice",
                "title": "哈佛大学《公正：该如何做是好？》(Justice)",
                "instructor": "Michael J. Sandel 教授",
                "university": "Harvard University",
                "banner_scene": "/assets/scenes/banner_harvard_series.jpg",
                "total_episodes": 12,
                "episodes": ["ep01", "ep02", "ep03"]
            }
        ]
    }
}

COLLECTIONS_DATA = {
    "harvard_justice": {
        "id": "harvard_justice",
        "title": "哈佛大学《公正：该如何做是好？》(Justice)",
        "en_title": "Harvard University: Justice - What's the Right Thing to Do?",
        "university": "Harvard University",
        "instructor": "Prof. Michael J. Sandel",
        "cover_scene": "/assets/scenes/banner_harvard_series.jpg",
        "badge": "哈佛旗舰 · 伦理法理必修",
        "total_episodes": 4,
        "desc": "探讨功利主义、自由至上主义与康德道德绝对论的经典哲学名篇，哈佛大学最负盛名的思辨殿堂。"
                "含一册长难句精读：取自讲座真实原句与已审校译文。",
        "episodes": ["ep01", "ep02", "ep03", "hj_longsent"]
    },
    "exam_vocabulary": {
        "id": "exam_vocabulary",
        "title": "考试与学术词汇（托福 / 雅思 / GRE / 考研 / 学术词组）",
        "en_title": "Exam & Academic Vocabulary (TOEFL / IELTS / GRE / Postgraduate / Phrases)",
        "university": "Open Lexical Data",
        "instructor": "ECDICT (MIT) · Tatoeba (CC-BY 2.0 FR)",
        "cover_scene": "/assets/scenes/scene_theatre.jpg",
        "badge": "真实词表导入 · 含词组与固定搭配",
        "total_episodes": 6,
        "desc": "由开源词典数据 ECDICT（MIT 许可）按考试标签筛选导入：托福、雅思、GRE、考研核心词汇，"
                "以及单独整理的真实学术词组与固定搭配表（600 条，全部为多词单位）；"
                "SAT 词表取自市面流行的公开词书（GPL-3.0，见 docs/THIRD_PARTY_DATA.md）。"
                "词条不是 AI 生成的，来源与许可均已记录。",
        "episodes": ["exam_toefl", "exam_ielts", "exam_gre", "exam_ky",
                     "exam_phrases", "exam_sat"]
    },
    "yale_philosophy": {
        "id": "yale_philosophy",
        "title": "耶鲁大学《哲学与人性科学》(Human Nature)",
        "en_title": "Yale University: Philosophy and the Science of Human Nature",
        "university": "Yale University",
        "instructor": "Prof. Tamar Gendler",
        "cover_scene": "/assets/scenes/cover_yale_philosophy.jpg",
        "badge": "耶鲁名校 · 道德心理与认知科学",
        "total_episodes": 1,
        "desc": "结合柏拉图理想国灵魂三分说与现代认知心理学，探索理性、欲望与幸福生活的内在秩序。",
        "episodes": ["yale_ep01"]
    },
    "custom_imports": {
        "id": "custom_imports",
        "title": "法理学与公共伦理名家研讨合集 (User Imports)",
        "en_title": "Public Jurisprudence & Seminar Series",
        "university": "Global Open Academic",
        "instructor": "特约讲师 / 罗翔教授等",
        "cover_scene": "/assets/scenes/scene_theatre.jpg",
        "badge": "自主导入 · 实时扩展",
        "total_episodes": 1,
        "desc": "由用户通过 Bilibili、YouTube 与 DownSub 链接自主导入并由 DeepSeek AI 提炼生成的学术视频合集。",
        "episodes": []
    }
}

def load_curriculum_tiered():
    if os.path.exists(CURRICULUM_FILE):
        try:
            with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception as e:
            print(f"[WARN] Failed to load curriculum_tiered.json: {e}")
    return {}

EPISODE_DATA = load_curriculum_tiered()

EXAM_DECKS_FILE = os.path.join(DATA_DIR, "exam_decks.json")
LONGSENT_DECKS_FILE = os.path.join(DATA_DIR, "longsent_decks.json")
SAT_DECK_FILE = os.path.join(DATA_DIR, "sat_deck.json")

_EXTRA_DECKS_CACHE = None

def load_exam_decks():
    """Extra study decks that are not lecture transcriptions.

    * `exam_decks.json`  - exam vocabulary imported from open lexical data
      (ECDICT/MIT, Tatoeba/CC-BY; see docs/THIRD_PARTY_DATA.md).
    * `longsent_decks.json` - long/difficult sentences taken from the lecture
      transcripts this project already processed, each with its reviewed
      translation and its real audio span.

    Kept out of curriculum_tiered.json so the lecture decks stay untouched.

    Cached on purpose: `ensure_word_audio_urls()` enriches these entries in
    place, and re-reading the file on every call threw that enrichment away, so
    every imported card came back without an `audio_url` at all.
    """
    global _EXTRA_DECKS_CACHE
    if _EXTRA_DECKS_CACHE is not None:
        return _EXTRA_DECKS_CACHE
    out = {}
    for path in (EXAM_DECKS_FILE, LONGSENT_DECKS_FILE, SAT_DECK_FILE):
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                out.update(json.load(f) or {})
        except Exception as e:
            print(f"[WARN] Failed to load {os.path.basename(path)}: {e}")
    _EXTRA_DECKS_CACHE = out
    return out

def ensure_word_audio_urls():
    """Attach audio URLs that actually resolve.

    These used to be built unconditionally, so every card in an imported deck
    (exam vocabulary, long sentences) advertised an .mp3 that was never
    generated and the play button failed silently. The server knows which files
    exist, so it decides here: a real file when there is one, otherwise the
    on-demand TTS endpoint, otherwise no clip at all.
    """
    global EPISODE_DATA
    if not EPISODE_DATA:
        EPISODE_DATA = load_curriculum_tiered()
    tts = lambda text: "/api/audio/tts?text=" + urllib.parse.quote(text or "")
    for ep_id, ep in list(EPISODE_DATA.items()) + list(load_exam_decks().items()):
        for w in ep.get("words", []):
            safe = re.sub(r'[^a-zA-Z0-9_]', '_', w['word'].lower()).strip('_')
            word_rel = f"/assets/audio/{ep_id}_{safe}.mp3"
            clip_rel = f"/assets/audio/clips/{ep_id}_{safe}_native.mp3"
            w['audio_url'] = (word_rel if os.path.exists(os.path.join(PUBLIC_DIR, word_rel.lstrip('/')))
                              else tts(w['word']))
            w['native_clip_url'] = (clip_rel
                                    if os.path.exists(os.path.join(PUBLIC_DIR, clip_rel.lstrip('/')))
                                    else "")
            if ep_id == 'ep01':
                w['scene_img'] = f"/assets/scenes/ep01/frame_{safe}.jpg"

ensure_word_audio_urls()

def harvard_series_episodes():
    """The Harvard Justice series membership, derived from what is actually served.

    COLLECTIONS_DATA used to hard-code ["ep01","ep02","ep03","hj_longsent"]. Once
    the series grew to twelve episodes that list was never extended, so the
    collection page offered only the first three even though ep04..ep12 were
    served and present in the master bank. Deriving it means the collection can
    no longer drift away from the decks.
    """
    eps = get_all_episodes()
    justice = sorted((k for k in eps if re.fullmatch(r"ep\d+", k)),
                     key=lambda k: int(k[2:]))
    if "hj_longsent" in eps:
        justice.append("hj_longsent")
    return justice


def get_all_episodes():
    eps = dict(EPISODE_DATA)
    eps.update(load_custom_episodes())
    eps.update(load_exam_decks())
    return eps

def get_vocab_bank_data(username=""):
    master_bank = load_vocab_bank()
    study_records = load_study_records()
    user_record = study_records.get(username, {}) if username else {}
    user_words = user_record.get("words", {})

    items = []
    mastered_count = 0
    learning_count = 0
    multi_context_count = 0

    for w_k, w_info in master_bank.items():
        contexts = w_info.get("contexts", [])
        if len(contexts) > 1:
            multi_context_count += 1
        
        # Merge with user personal stats
        u_stat = user_words.get(w_info["word"], {})
        rev_count = u_stat.get("review_count", w_info.get("stats", {}).get("review_count", 0))
        total_sec = u_stat.get("total_seconds", w_info.get("stats", {}).get("total_seconds", 0))
        status = u_stat.get("status", w_info.get("stats", {}).get("status", "learning"))
        last_rating = u_stat.get("last_rating", w_info.get("stats", {}).get("last_rating", "new"))
        last_reviewed = u_stat.get("last_reviewed_at", w_info.get("stats", {}).get("last_reviewed_at"))

        if status == "mastered":
            mastered_count += 1
        else:
            learning_count += 1

        items.append({
            "word": w_info["word"],
            "phonetic": w_info.get("phonetic", ""),
            "pos": w_info.get("pos", ""),
            "def_cn": w_info.get("def_cn", ""),
            "def_en": w_info.get("def_en", ""),
            # Which episodes actually teach this word, derived from the decks.
            # The UI must filter on this rather than guessing from
            # contexts[].source_id: a word kept from a since-rebuilt deck still
            # carries its historical context, which made the bank look like it
            # held words the episode decks did not.
            "taught_in": w_info.get("taught_in", []),
            "bank_only": bool(w_info.get("bank_only")),
            "contexts": contexts,
            "review_count": rev_count,
            "total_seconds": total_sec,
            "status": status,
            "last_rating": last_rating,
            "last_reviewed_at": last_reviewed
        })

    today_str = str(date.today())
    today_sec = user_record.get("today_seconds", 0) if user_record.get("last_active_date") == today_str else 0
    hist_sec = user_record.get("historical_seconds", 0)

    return {
        "words": items,
        "summary": {
            "total_words": len(items),
            "mastered_count": mastered_count,
            "learning_count": learning_count,
            "multi_context_count": multi_context_count,
            "today_seconds": today_sec,
            "historical_seconds": hist_sec
        }
    }


# ---------------------------------------------------------------------------
# Export rendering. Pure functions: no socket, no handler state, so the whole
# matrix of formats can be verified offline (tools/quality_pipeline/
# export_conformance.py) instead of by clicking buttons in a browser.
# ---------------------------------------------------------------------------
def _export_words(words):
    """Normalise the incoming JS objects into the shape the renderers expect."""
    out = []
    for w in words or []:
        if not isinstance(w, dict):
            continue
        item = dict(w)
        item.setdefault("word", "")
        item.setdefault("phonetic", "")
        item.setdefault("pos", "")
        item.setdefault("def_cn", "")
        item.setdefault("def_en", "")
        if not item.get("sentence") and item.get("contexts"):
            first = item["contexts"][0] or {}
            item["sentence"] = first.get("sentence", "")
            item["trans"] = first.get("trans", "")
        item.setdefault("sentence", "")
        item.setdefault("trans", "")
        out.append(item)
    return out


def build_export_payload(fmt, words, title):
    """Render one export. Returns (bytes, download_filename, mimetype)."""
    words = _export_words(words)
    if not words:
        raise ValueError("待导出的词汇列表为空")

    if fmt == "docx":
        content = build_docx_bytes(
            title="哈佛大学《公正课》(Justice) 听说精读手册",
            subtitle=f"{title} · Michael Sandel 教授公开课 · 精编核心词汇表",
            words=words,
        )
        return (content, f"{title}_Study_Guide.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    if fmt == "study_guide_md":
        lines = [
            f"# 🏛️ {title} 听说精读词表手册\n\n",
            "> 哈佛大学《Justice》公开课 · Michael Sandel 教授\n\n",
            "| 序号 | 单词 | 音标 | 词性与中文释义 | 英英释义 | 课堂原声例句 | 中文翻译 |\n",
            "| :---: | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        ]
        for i, w in enumerate(words, 1):
            en = (w.get("def_en") or "").replace("|", "\\|")
            lines.append(
                f"| {i} | **{w['word']}** | `{w.get('phonetic','')}` | "
                f"{w.get('pos','')} {w.get('def_cn','')} | {en} | "
                f"{w.get('sentence','')} | {w.get('trans','')} |\n")
        return ("".join(lines).encode("utf-8"), f"{title}_Study_Guide.md",
                "text/markdown; charset=utf-8")

    if fmt == "anki_csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Front", "Back", "Word", "Phonetic", "Definition",
                         "EnglishDefinition", "Example", "Translation"])
        for w in words:
            word = w["word"]
            cloze = re.sub(re.escape(word), "_______", w.get("sentence", ""),
                           flags=re.IGNORECASE)
            front = (f"<div style='font-family:sans-serif; text-align:center; padding:20px;'>"
                     f"<h1 style='font-size:28px; color:#1e293b; margin-bottom:15px;'>{word}</h1>"
                     f"<div style='background:#f1f5f9; padding:15px; border-radius:10px; "
                     f"font-size:16px; color:#475569; text-align:left; font-family:serif;'>"
                     f"{cloze}</div></div>")
            en_block = (f"<div style='font-size:14px; color:#334155; margin-bottom:12px;'>"
                        f"{w.get('def_en','')}</div>" if w.get("def_en") else "")
            back = (f"<div style='font-family:sans-serif; padding:20px;'>"
                    f"<h1 style='font-size:26px; color:#b91c1c; margin-bottom:4px;'>{word}</h1>"
                    f"<p style='color:#64748b; font-size:14px; margin-bottom:12px;'>"
                    f"{w.get('phonetic','')} · {w.get('pos','')}</p>"
                    f"<div style='background:#fef2f2; border-left:4px solid #b91c1c; "
                    f"padding:10px 15px; font-size:16px; font-weight:bold; color:#991b1b; "
                    f"margin-bottom:8px;'>{w.get('def_cn','')}</div>{en_block}"
                    f"<div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; "
                    f"padding:12px;'><p style='font-family:serif; font-size:15px; color:#334155; "
                    f"margin-bottom:6px;'><b>课堂原句：</b><br>{w.get('sentence','')}</p>"
                    f"<p style='font-size:13px; color:#64748b; margin:0;'>"
                    f"<i>{w.get('trans','')}</i></p></div></div>")
            writer.writerow([front, back, word, w.get("phonetic", ""),
                             f"{w.get('pos','')} {w.get('def_cn','')}",
                             w.get("def_en", ""), w.get("sentence", ""),
                             w.get("trans", "")])
        return (output.getvalue().encode("utf-8"), f"{title}_Anki.csv",
                "text/csv; charset=utf-8")

    if fmt == "eudic_quizlet":
        lines = []
        for w in words:
            gloss = f"{w.get('pos','')} {w.get('def_cn','')}".strip()
            if w.get("def_en"):
                gloss = f"{gloss}\\n{w['def_en']}"
            lines.append(f"{w['word']}\t{w.get('phonetic','')} {gloss}\t"
                         f"{w.get('sentence','')} ({w.get('trans','')})")
        return ("\n".join(lines).encode("utf-8"), f"{title}_Eudic_Quizlet.txt",
                "text/plain; charset=utf-8")

    if fmt == "words_only":
        return ("\n".join(w["word"] for w in words).encode("utf-8"),
                f"{title}_Words_Only.txt", "text/plain; charset=utf-8")

    raise ValueError(f"未知的导出格式: {fmt}")


class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self._response_started = False
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def send_error_json(self, code, message):
        body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
        self._response_started = True

    def send_bytes(self, code, body, content_type, download_name=None,
                   cache_control="no-store"):
        """Send a complete, fully-validated response.

        `http.server` encodes header lines as latin-1. A non-ASCII header value
        therefore raises UnicodeEncodeError *after* send_response() has already
        buffered the status line; the old export handler caught that and appended
        a 500 to the same buffer, so the client read "HTTP/1.0 200 OK" and saved
        an 84-byte error message as a .docx/.csv (ticket: 导出合集是 nothing).

        Every header is validated before anything is written, so a failure can
        still be reported honestly.
        """
        headers = [("Content-Type", content_type),
                   ("Content-Length", str(len(body))),
                   ("Cache-Control", cache_control),
                   ("Access-Control-Allow-Origin", "*")]
        if download_name:
            headers.append(("Content-Disposition",
                            build_content_disposition(download_name)))
        for key, value in headers:
            try:
                ("%s: %s" % (key, value)).encode("latin-1")
            except UnicodeEncodeError:
                raise ValueError("header %s is not ASCII-safe: %r" % (key, value))
        self.send_response(code)
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        self._response_started = True
        if body:
            self.wfile.write(body)

    def do_HEAD(self):
        """HEAD support for API + docs routes.

        SimpleHTTPRequestHandler only knows how to HEAD static files, so
        `curl -I` against any /api/* route used to answer 404 and made the
        whole API look missing. We run the GET logic against a recording sink
        and then replay only the status line + headers, discarding the body.
        (Swapping self.wfile for a discarding sink is NOT enough: end_headers()
        writes the header block through self.wfile as well.)
        """
        clean_path = self.path.split('?')[0].split('#')[0]
        if not (clean_path.startswith("/api/") or clean_path in ('/docs', '/docs/', '/api-docs')):
            return super().do_HEAD()

        class _HeadRecorder:
            def __init__(self):
                self.buf = bytearray()
                self.headers_done = False

            def write(self, data):
                if not self.headers_done:
                    self.buf += data
                    if b"\r\n\r\n" in self.buf:
                        self.headers_done = True
                return len(data)

            def flush(self):
                return None

        recorder = _HeadRecorder()
        real_wfile = self.wfile
        try:
            self.wfile = recorder
            self.do_GET()
        finally:
            self.wfile = real_wfile

        head, sep, _body = bytes(recorder.buf).partition(b"\r\n\r\n")
        if sep:
            self.wfile.write(head + sep)
        else:
            self.send_error(500, "HEAD probe produced no response headers")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split('?')[0].split('#')[0]

        if clean_path in ['/api/health', '/health']:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "service": "Harvard Justice AI Studio",
                # Lets anyone (and the release checklist) confirm which version the
                # running deployment is actually serving.
                "version": APP_VERSION,
            }, ensure_ascii=False).encode("utf-8"))
            return

        # 0. API Documentation and OpenAPI Spec
        if clean_path in ['/docs', '/api-docs', '/docs/']:
            docs_file = os.path.join(PUBLIC_DIR, "docs.html")
            if os.path.exists(docs_file):
                with open(docs_file, "rb") as f:
                    docs_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(docs_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(docs_bytes)
                return

        if clean_path == '/api/openapi.json':
            spec_file = os.path.join(PUBLIC_DIR, "openapi.json")
            if not os.path.exists(spec_file):
                spec_file = os.path.join(DATA_DIR, "openapi.json")
            if os.path.exists(spec_file):
                with open(spec_file, "rb") as f:
                    spec_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(spec_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(spec_bytes)
                return

        # 0.1 SPA Client Route Fallback
        spa_routes = ['/collections', '/vocab-bank', '/home', '/login', '/register', '/feedback']
        if (clean_path in spa_routes or 
            clean_path.startswith('/collection/') or 
            clean_path.startswith('/episode/') or 
            clean_path.startswith('/study/')):
            index_file = os.path.join(PUBLIC_DIR, "index.html")
            if os.path.exists(index_file):
                with open(index_file, "rb") as f:
                    html_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html_bytes)
                return
        # 0. Collections API
        if clean_path == "/api/collections":
            custom_eps = load_custom_episodes()
            cols = []
            for c_id, c in COLLECTIONS_DATA.items():
                c_copy = dict(c)
                if c_id == "custom_imports":
                    c_copy["episodes"] = list(custom_eps.keys())
                    c_copy["total_episodes"] = len(custom_eps)
                elif c_id == "harvard_justice":
                    c_copy["episodes"] = harvard_series_episodes()
                    c_copy["total_episodes"] = len(c_copy["episodes"])
                
                # Calculate total words in this collection
                all_eps = get_all_episodes()
                total_w = sum(len(all_eps.get(eid, {}).get("words", [])) for eid in c_copy.get("episodes", []))
                c_copy["total_words"] = total_w
                cols.append(c_copy)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cols, ensure_ascii=False).encode("utf-8"))
            return

        elif clean_path.startswith("/api/collection/"):
            cid = clean_path.rstrip("/").split("/")[-1].lower()
            if cid not in COLLECTIONS_DATA:
                self.send_error_json(404, f"合集不存在: {cid}")
                return
            col = COLLECTIONS_DATA[cid]
            c_copy = dict(col)
            all_eps = get_all_episodes()
            if cid == "custom_imports":
                c_copy["episodes"] = list(load_custom_episodes().keys())
            elif cid == "harvard_justice":
                c_copy["episodes"] = harvard_series_episodes()

            ep_details = []
            for eid in c_copy.get("episodes", []):
                if eid in all_eps:
                    ep_details.append(all_eps[eid])
            c_copy["episode_details"] = ep_details
            c_copy["total_words"] = sum(len(ep.get("words", [])) for ep in ep_details)
            c_copy["total_episodes"] = len(ep_details)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(c_copy, ensure_ascii=False).encode("utf-8"))
            return

        # 1. Series and Course List
        if clean_path == "/api/series":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(SERIES_DATA, ensure_ascii=False).encode("utf-8"))
            return
        
        # 2. Episode details
        elif clean_path.startswith("/api/preset/") or clean_path.startswith("/api/episode/"):
            # NOTE: must use clean_path -- self.path still carries "?query" and a
            # trailing "/", which previously produced a bogus id and silently
            # served Episode 01 for ANY querystring/trailing-slash request.
            ep_id = clean_path.rstrip("/").split("/")[-1].lower()
            all_eps = get_all_episodes()
            if ep_id not in all_eps:
                self.send_error_json(404, f"剧集不存在: {ep_id}")
                return
            data = all_eps[ep_id]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        elif clean_path == "/api/transcript/search":
            self.handle_transcript_search()
            return

        elif clean_path in ["/api/presets", "/api/episodes"]:
            all_eps = get_all_episodes()
            summary = [
                {
                    "id": k, 
                    "title": v.get("title", ""), 
                    "cn_title": v.get("cn_title", ""),
                    "topic": v.get("topic", ""), 
                    "cover_scene": v.get("cover_scene", "/assets/scenes/scene_theatre.jpg"),
                    "count": len(v.get("words", [])),
                    "duration": v.get("duration", "50 分钟")
                } 
                for k, v in all_eps.items()
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(summary, ensure_ascii=False).encode("utf-8"))
            return

        # 2.5 Master Vocabulary Bank
        elif clean_path.startswith("/api/vocab-bank"):
            params = parse_query_params(self.path)
            username = params.get("username", "").strip()
            data = get_vocab_bank_data(username)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        # 2.6 Dynamic Neural TTS Audio Streamer
        elif clean_path.startswith("/api/audio/tts"):
            params = parse_query_params(self.path)
            text_to_speak = params.get("text", "").strip()
            if not text_to_speak:
                self.send_error_json(400, "缺少 text 参数")
                return
            if len(text_to_speak) > 600:
                self.send_error_json(400, "text 过长（最多 600 字符）")
                return
            h = hashlib.md5(text_to_speak.encode("utf-8")).hexdigest()[:12]
            cache_name = f"tts_{h}.mp3"
            cache_path = os.path.join(AUDIO_DIR, cache_name)
            if not os.path.exists(cache_path):
                synthesize_audio_sync(text_to_speak, cache_path)
            
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as f:
                    audio_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            else:
                self.send_response(500)
                self.end_headers()
                return

        # 3. User study stats
        elif clean_path.startswith("/api/user/stats"):
            params = parse_query_params(self.path)
            username = params.get("username", "").strip()

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            # Check if today date rolled over
            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(user_data, ensure_ascii=False).encode("utf-8"))
            return

        # 4. Stream Download Endpoint (zero-disk streaming proxy)
        elif clean_path == "/api/media/stream-download":
            self.handle_media_stream_download()
            return

        return super().do_GET()

    def do_POST(self):
        # Reject absurd bodies outright instead of buffering them.
        # 24 MB covers a full-size screenshot data URL (the client does not
        # downscale before upload) while still bounding abuse.
        MAX_BODY_BYTES = 24 * 1024 * 1024
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            content_length = 0
        if content_length < 0 or content_length > MAX_BODY_BYTES:
            self.send_error_json(413, "请求体过大或长度非法")
            return
        body = self.rfile.read(content_length).decode("utf-8", "replace")

        clean_path = self.path.split('?')[0].split('#')[0]

        # Auth and Core Endpoints
        if clean_path == "/api/auth/register":
            self.handle_register(body)
        elif clean_path == "/api/auth/login":
            self.handle_login(body)
        elif clean_path == "/api/user/record":
            self.handle_study_record(body)
        elif clean_path == "/api/vocab-bank/record":
            self.handle_vocab_bank_record(body)
        elif clean_path == "/api/import/link":
            self.handle_import_link(body)
        elif clean_path == "/api/media/batch-extract":
            self.handle_batch_media_extract(body)
        elif clean_path == "/api/bilibili/detect-collection":
            self.handle_detect_bilibili_collection(body)
        elif clean_path == "/api/custom-word/add":
            self.handle_add_custom_word(body)
        elif clean_path == "/api/test-connection":
            self.handle_test_connection(body)
        elif clean_path == "/api/ai-extract":
            self.handle_ai_extract(body)
        elif clean_path == "/api/export":
            self.handle_export(body)
        elif clean_path == "/api/video/fetch-subtitles":
            self.handle_video_subtitles(body)
        elif clean_path == "/api/feedback":
            self.handle_feedback(body)
        elif clean_path == "/api/user/heartbeat-time":
            self.handle_heartbeat_time(body)
        elif clean_path == "/api/collection/add":
            self.handle_add_collection(body)
        else:
            self.send_error_json(404, f"未知接口: {clean_path}")

    def handle_register(self, body_str):
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            password = req.get("password", "").strip()
            nickname = req.get("nickname", username).strip() or username

            if not username or not password:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "用户名和密码不能为空！"}, ensure_ascii=False).encode("utf-8"))
                return

            users = load_users()
            if username in users:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "该用户名已存在，请直接登录！"}, ensure_ascii=False).encode("utf-8"))
                return

            users[username] = {
                "username": username,
                "password_hash": hash_pw(password),
                "nickname": nickname,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_users(users)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "username": username, 
                "nickname": nickname,
                "message": "注册成功，已自动登录！"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_login(self, body_str):
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            password = req.get("password", "").strip()

            users = load_users()
            user = users.get(username)
            if not user or user.get("password_hash") != hash_pw(password):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "用户名或密码错误！"}, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "username": username, 
                "nickname": user.get("nickname", username),
                "message": "登录成功！"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_study_record(self, body_str):
        """Records review duration, count, rating for a specific word and overall user."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            word = req.get("word", "").strip()
            duration = int(req.get("duration_seconds", 0))
            rating = req.get("rating", "good") # again, hard, good, easy
            episode_id = req.get("episode_id", "ep01")

            if not username:
                # Guest mode: ack without server persistence
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "guest": True}).encode("utf-8"))
                return

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            # Update overall times
            user_data["today_seconds"] = user_data.get("today_seconds", 0) + duration
            user_data["historical_seconds"] = user_data.get("historical_seconds", 0) + duration

            # Update per-word statistics
            words_dict = user_data.setdefault("words", {})
            w_stat = words_dict.setdefault(word, {
                "word": word,
                "episode_id": episode_id,
                "review_count": 0,
                "total_seconds": 0,
                "status": "learning",
                "last_rating": rating,
                "last_reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            w_stat["review_count"] += 1
            w_stat["total_seconds"] += duration
            w_stat["last_rating"] = rating
            w_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            if rating in ["good", "easy"]:
                w_stat["status"] = "mastered" if w_stat["review_count"] >= 3 else "consolidating"
            elif rating == "again":
                w_stat["status"] = "needs_review"
            else:
                w_stat["status"] = "learning"

            records[username] = user_data
            save_study_records(records)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "stats": {
                    "word": word,
                    "review_count": w_stat["review_count"],
                    "total_seconds": w_stat["total_seconds"],
                    "status": w_stat["status"],
                    "user_today_seconds": user_data["today_seconds"],
                    "user_historical_seconds": user_data["historical_seconds"]
                }
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_test_connection(self, body_str):
        try:
            req = json.loads(body_str)
            provider = req.get("provider", "deepseek").lower()
            api_base = (req.get("api_base") or DEFAULT_CONFIG["api_base"]).rstrip("/")
            # Same rule as /api/ai-extract: never lend the server key to an
            # anonymous caller, and never POST to a caller-chosen host (SSRF).
            api_key = req.get("api_key", "").strip()
            model = (req.get("model") or DEFAULT_CONFIG["model"]).strip()

            if not ai_base_allowed(api_base):
                self.send_error_json(400, f"api_base 不被允许: {api_base}（仅支持 {sorted(ALLOWED_AI_HOSTS)}）")
                return
            if not api_key:
                self.send_error_json(400, "请提供您自己的 API Key")
                return

            if provider == "anthropic":
                endpoint = f"{api_base}/v1/messages" if not api_base.endswith("/v1") else f"{api_base}/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Ping"}]
                }
            else:
                endpoint = f"{api_base}/chat/completions" if not api_base.endswith("/chat/completions") else api_base
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [{"role": "user", "content": "Ping"}],
                    "max_tokens": 10
                }

            req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req_obj, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "message": "API 连接测试成功！接口响应正常。"}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"API 连接测试失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_ai_extract(self, body_str):
        try:
            req = json.loads(body_str)
            provider = req.get("provider", "deepseek").lower()
            api_base = (req.get("api_base") or DEFAULT_CONFIG["api_base"]).rstrip("/")
            # The caller must bring their own key. Falling back to the server key
            # turned this endpoint into an unauthenticated proxy that let anyone
            # spend the project's DeepSeek credits.
            api_key = req.get("api_key", "").strip()
            model = (req.get("model") or DEFAULT_CONFIG["model"]).strip()
            transcript = req.get("transcript", "").strip()
            count = req.get("count", 20)

            # Caller-controlled api_base was an SSRF hole (the server would POST
            # to any URL supplied, including internal/metadata addresses).
            if not ai_base_allowed(api_base):
                self.send_error_json(400, f"api_base 不被允许: {api_base}（仅支持 {sorted(ALLOWED_AI_HOSTS)}）")
                return
            if not api_key:
                self.send_error_json(400, "请提供您自己的 API Key（服务端不再代为支付调用额度）")
                return
            if not transcript:
                self.send_error_json(400, "transcript 不能为空")
                return
            try:
                count = max(1, min(int(count), 60))
            except (TypeError, ValueError):
                count = 20

            system_prompt = (
                "你是一位专精学术英语、道德哲学与法理学的权威语言学教授。"
                "请深入研读用户提供的哈佛大学《公正课》(Justice) 剧集英文台词/字幕。\n"
                "严格执行以下筛选与结构化规范：\n"
                "1. 严格过滤掉初高中及大学四六级常见的简单基础词；\n"
                f"2. 精准筛选提取出 {count} 个直接影响课文深层逻辑理解与听力跟读的【道德哲学与法理学术术语】、【学术辩论核心词汇】与【经典情节专有名词】；\n"
                "3. 必须提取该单词在课堂上真实被说出的【英文原声例句】（不要凭空造句）；\n"
                "4. 严格只输出合法 JSON 数组，严禁包含任何 Markdown 格式标记（不要带有 ```json 或 ```），格式规范如下：\n"
                '[\n'
                '  {\n'
                '    "word": "utilitarianism",\n'
                '    "phonetic": "/ˌjuːtɪlɪˈteriənɪzəm/",\n'
                '    "pos": "n.",\n'
                '    "def_cn": "功利主义，功利论",\n'
                '    "sentence": "Bentham\'s utilitarianism claims that the highest principle...",\n'
                '    "trans": "边沁的功利主义认为..."\n'
                '  }\n'
                ']'
            )

            if provider == "anthropic":
                endpoint = f"{api_base}/v1/messages" if not api_base.endswith("/v1") else f"{api_base}/messages"
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                payload = {
                    "model": model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": f"以下是哈佛公正课字幕文本：\n\n{transcript[:20000]}"}],
                    "temperature": 0.2
                }
                req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req_obj, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_content = resp_data["content"][0]["text"].strip()
            else:
                endpoint = f"{api_base}/chat/completions" if not api_base.endswith("/chat/completions") else api_base
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"以下是哈佛公正课字幕文本：\n\n{transcript[:20000]}"}
                    ],
                    "temperature": 0.2
                }
                req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req_obj, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_content = resp_data["choices"][0]["message"]["content"].strip()

            clean_json = raw_content
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.startswith("```"): clean_json = clean_json[3:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            clean_json = clean_json.strip()

            parsed_words = json.loads(clean_json)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "words": parsed_words}, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"调用 AI 提取失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_vocab_bank_record(self, body_str):
        """Records review duration, count, and SRS rating for a word in the master vocab bank."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            word = req.get("word", "").strip()
            duration = int(req.get("duration_seconds", 0))
            rating = req.get("rating", "good")

            # Update study records
            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })
            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            user_data["today_seconds"] = user_data.get("today_seconds", 0) + duration
            user_data["historical_seconds"] = user_data.get("historical_seconds", 0) + duration

            words_dict = user_data.setdefault("words", {})
            w_stat = words_dict.setdefault(word, {
                "word": word,
                "review_count": 0,
                "total_seconds": 0,
                "status": "learning",
                "last_rating": rating,
                "last_reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            w_stat["review_count"] += 1
            w_stat["total_seconds"] += duration
            w_stat["last_rating"] = rating
            w_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            if rating in ["good", "easy"]:
                w_stat["status"] = "mastered" if w_stat["review_count"] >= 3 else "consolidating"
            elif rating == "again":
                w_stat["status"] = "needs_review"
            else:
                w_stat["status"] = "learning"

            records[username] = user_data
            save_study_records(records)

            # Also update vocab_bank.json global stats
            v_bank = load_vocab_bank()
            w_key = word.lower().strip()
            if w_key in v_bank:
                v_stat = v_bank[w_key].setdefault("stats", {})
                v_stat["review_count"] = v_stat.get("review_count", 0) + 1
                v_stat["total_seconds"] = v_stat.get("total_seconds", 0) + duration
                v_stat["status"] = w_stat["status"]
                v_stat["last_rating"] = rating
                v_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_vocab_bank(v_bank)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "stats": w_stat,
                "today_seconds": user_data["today_seconds"],
                "historical_seconds": user_data["historical_seconds"]
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_import_link(self, body_str):
        """Extracts video metadata, subtitles, runs DeepSeek AI vocab extraction, synthesizes audio and saves episode."""
        try:
            req = json.loads(body_str)
            url = req.get("url", "").strip()
            custom_title = req.get("title", "").strip()
            raw_transcript = req.get("transcript", "").strip()

            # An empty body used to be accepted and silently produced a real
            # episode from a built-in sample transcript (13 TTS files + 13 new
            # vocab-bank entries per call, unauthenticated -> unbounded growth).
            if not url and not raw_transcript:
                self.send_error_json(400, "请至少提供 url 或 transcript，不能创建空导入。")
                return
            if len(raw_transcript) > 200000:
                self.send_error_json(413, "transcript 过长（最多 200000 字符）。")
                return
            if custom_title and len(custom_title) > 200:
                self.send_error_json(400, "标题过长（最多 200 字符）。")
                return
            if not DEFAULT_CONFIG["api_key"]:
                self.send_error_json(503, "服务端未配置 DeepSeek API Key，无法执行 AI 词汇抽取。")
                return
            
            video_meta = {
                "title": custom_title or "网络精选公开课 / 研讨音视频",
                "author": "学术精讲",
                "cover": "/assets/scenes/banner_harvard_series.jpg",
                "duration": "45 分钟",
                "platform": "generic",
                "video_id": ""
            }

            # Bilibili detection
            if "bilibili.com" in url or re.search(r"BV[0-9A-Za-z]{10}", url):
                video_meta["platform"] = "bilibili"
                m = re.search(r"(BV[0-9A-Za-z]{10})", url)
                bvid = m.group(1) if m else "BV_custom"
                video_meta["video_id"] = bvid
                if not custom_title:
                    video_meta["title"] = f"Bilibili 哲学与法理研读 ({bvid})"
                video_meta["cover"] = "/assets/scenes/scene_theatre.jpg"

            # YouTube detection
            elif "youtube.com" in url or "youtu.be" in url:
                video_meta["platform"] = "youtube"
                m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
                vid = m.group(1) if m else ""
                video_meta["video_id"] = vid
                if vid:
                    video_meta["cover"] = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
                try:
                    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
                    req_o = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req_o, timeout=5) as r:
                        o_data = json.loads(r.read().decode("utf-8"))
                        video_meta["title"] = o_data.get("title", video_meta["title"])
                        video_meta["author"] = o_data.get("author_name", "YouTube Creator")
                except:
                    if not custom_title:
                        video_meta["title"] = f"YouTube 哲学精读 ({vid})"

            # Fetch the link's REAL transcript before doing anything else. This
            # route never used to fetch anything: it fell back to a paragraph of
            # invented philosophy prose and extracted "core vocabulary" from it,
            # so every link-only import produced an episode whose example
            # sentences were never spoken in the video.
            if not raw_transcript and url:
                try:
                    from downloader import auto_fetch_subtitles_and_meta
                    fetched = auto_fetch_subtitles_and_meta(url) or {}
                except Exception as fetch_err:
                    print(f"[WARN] transcript fetch failed: {fetch_err}")
                    fetched = {}
                if fetched.get("has_subtitles") and (fetched.get("transcript") or "").strip():
                    raw_transcript = fetched["transcript"].strip()
                    if not custom_title and fetched.get("title"):
                        video_meta["title"] = fetched["title"]
                    if fetched.get("author"):
                        video_meta["author"] = fetched["author"]
                    if fetched.get("cover"):
                        video_meta["cover"] = fetched["cover"]
                    if fetched.get("duration"):
                        video_meta["duration"] = fetched["duration"]
                    if fetched.get("platform"):
                        video_meta["platform"] = fetched["platform"]
                    if fetched.get("video_id"):
                        video_meta["video_id"] = fetched["video_id"]

            if not raw_transcript:
                # No real subtitles is a dead end, not an invitation to invent
                # them. Say so and tell the user how to proceed.
                self.send_error_json(
                    422,
                    "未能从该链接获取到真实字幕/逐字稿，因此没有可用于提炼词汇的原文。"
                    "请：① 改用带字幕的来源（B 站 CC 字幕 / YouTube 字幕）；"
                    "② 或把 SRT/VTT/DownSub 文稿粘贴到下方文本框后重新导入。")
                return

            # Call DeepSeek AI to extract words
            system_prompt = (
                "你是一位权威的学术英语、哲学与法学教授。"
                "请研读提供的音视频字幕/文稿，精准提取10-15个高价值【学术哲学与辩论核心术语】。"
                "严格只返回合法的 JSON 数组，严禁包含任何 Markdown 标记：\n"
                "["
                "  {"
                '    "word": "jurisprudence",'
                '    "phonetic": "/ˌdʒʊrɪsˈpruːdns/",'
                '    "pos": "n.",'
                '    "def_cn": "法理学，法律哲学",'
                '    "def_en": "the branch of law concerned with the principles behind legal rules",'
                '    "sentence": "In jurisprudence, the defense of necessity demands rigorous moral deliberation.",'
                '    "trans": "在法理学中，紧急避险的抗辩需要严格的道德审议。"'
                "  }"
                "]"
                "注意：def_en 是面向中国大学生的英英释义，只写英文，6-22 个单词，"
                "贴合该词在例句中的词义，不要照抄例句。"
            )

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEFAULT_CONFIG['api_key']}"
            }
            payload = {
                # The model is an operator setting (a reasoning model needs far
                # more headroom, since its thinking tokens count against the cap).
                "model": DEFAULT_CONFIG["model"],
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"以下是视频字幕文稿：\n\n{raw_transcript[:20000]}"}
                ],
                "temperature": 0.2,
                "max_tokens": 8192
            }

            req_obj = urllib.request.Request(f"{DEFAULT_CONFIG['api_base']}/chat/completions", data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req_obj, timeout=120) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                choice = (resp_data.get("choices") or [{}])[0]
                raw_content = (choice.get("message") or {}).get("content", "").strip()
                if choice.get("finish_reason") == "length" and not raw_content:
                    self.send_error_json(
                        502, "AI 返回被截断（推理模型把 token 用在了思考上）。请重试，"
                             "或把 max_tokens 调大。")
                    return

            clean_json = raw_content
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.startswith("```"): clean_json = clean_json[3:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            extracted_words = json.loads(clean_json.strip())

            # Synthesize audio and register
            ep_id = f"custom_{int(time.time())}"
            for w in extracted_words:
                word = w["word"]
                safe = re.sub(r'[^a-zA-Z0-9_]', '_', word.lower()).strip('_')
                audio_filename = f"{ep_id}_{safe}.mp3"
                audio_path = os.path.join(AUDIO_DIR, audio_filename)
                w["audio_url"] = f"/assets/audio/{audio_filename}"
                w["scene_img"] = video_meta["cover"]
                w["scene_desc"] = f"{video_meta['title']} 课堂实录"
                if w.get("sentence"):
                    synthesize_audio_sync(w["sentence"], audio_path)

            new_episode = {
                "id": ep_id,
                "title": video_meta["title"],
                "cn_title": video_meta["title"],
                "topic": f"从《{video_meta['title']}》解析的核心学术词汇",
                "duration": video_meta["duration"],
                "cover_scene": video_meta["cover"],
                "source_url": url,
                "platform": video_meta["platform"],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "words": extracted_words
            }

            # Save to custom episodes
            custom_eps = load_custom_episodes()
            custom_eps[ep_id] = new_episode
            save_custom_episodes(custom_eps)

            # Ingest into master vocab bank
            master_bank = load_vocab_bank()
            for w in extracted_words:
                w_k = w["word"].lower().strip()
                new_ctx = {
                    "source_id": ep_id,
                    "source_title": video_meta["title"],
                    "sentence": w.get("sentence", ""),
                    "trans": w.get("trans", ""),
                    "audio_url": w.get("audio_url", "")
                }
                if w_k not in master_bank:
                    master_bank[w_k] = {
                        "word": w["word"],
                        "phonetic": w.get("phonetic", ""),
                        "pos": w.get("pos", ""),
                        "def_cn": w.get("def_cn", ""),
                        "def_en": w.get("def_en", ""),
                        "contexts": [new_ctx],
                        "stats": {
                            "review_count": 0,
                            "today_seconds": 0,
                            "total_seconds": 0,
                            "status": "learning",
                            "last_rating": "new",
                            "last_reviewed_at": None
                        }
                    }
                else:
                    if not any(c.get("sentence") == new_ctx["sentence"] for c in master_bank[w_k]["contexts"]):
                        master_bank[w_k]["contexts"].append(new_ctx)

            save_vocab_bank(master_bank)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "episode": new_episode,
                "extracted_count": len(extracted_words),
                "message": f"成功提取并生成 {len(extracted_words)} 个核心词汇与原声例句，已同步汇入全景词汇库！"
            }, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"导入并解析失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_export(self, body_str):
        try:
            req = json.loads(body_str)
            fmt = req.get("format", "words_only")
            words = req.get("words", [])
            title = req.get("title", "Harvard_Justice_Vocabulary")
            if not isinstance(words, list):
                raise ValueError("words 必须是数组")
            if not isinstance(title, str) or not title.strip():
                title = "Harvard_Justice_Vocabulary"
            # A long/odd title must never be able to break the response headers.
            title = re.sub(r"[\r\n]+", " ", title).strip()[:120]

            content, filename, mimetype = build_export_payload(fmt, words, title)
        except Exception as e:
            self.send_error_json(400, f"导出处理失败: {str(e)}")
            return
        self.send_bytes(200, content, mimetype, download_name=filename)


    def handle_heartbeat_time(self, body_str):
        """Records active studying heartbeat only when user is authenticated."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            duration = int(req.get("duration_seconds", 0))

            if not username or duration <= 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "guest": True}).encode("utf-8"))
                return

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            user_data["today_seconds"] += duration
            user_data["historical_seconds"] += duration
            records[username] = user_data
            save_study_records(records)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "today_seconds": user_data["today_seconds"],
                "historical_seconds": user_data["historical_seconds"]
            }).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_video_subtitles(self, body_str):
        try:
            req = json.loads(body_str)
            url = req.get("url", "").strip()
            try:
                from downloader import auto_fetch_subtitles_and_meta
                result = auto_fetch_subtitles_and_meta(url)
            except Exception as de:
                result = {"success": False, "error": f"Downloader error: {de}"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_batch_media_extract(self, body_str):
        try:
            req = json.loads(body_str) if body_str else {}
            raw_urls = req.get("urls", [])
            mode = req.get("mode", "media")
            media_type = req.get("media_type", "audio")
            auto_expand = req.get("auto_expand_collections", True)

            from downloader import batch_resolve_media
            result = batch_resolve_media(raw_urls, mode=mode, media_type=media_type, auto_expand_collections=auto_expand)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"批量解析异常: {str(e)}"}).encode("utf-8"))

    def handle_detect_bilibili_collection(self, body_str):
        try:
            req = json.loads(body_str) if body_str else {}
            url = req.get("url", "").strip()
            if not url:
                self.send_error_json(400, "缺少 url 参数")
                return

            from downloader import detect_bilibili_collection
            result = detect_bilibili_collection(url)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"探测合集异常: {str(e)}"}).encode("utf-8"))

    def handle_media_stream_download(self):
        try:
            params = parse_query_params(self.path)
            raw_url = params.get("url", "").strip()
            filename = params.get("filename", "").strip()
            media_type = params.get("media_type", "audio").strip().lower()
            platform = params.get("platform", "").strip().lower()

            if not raw_url:
                self.send_error_json(400, "缺少 url 参数")
                return

            # Sanitize filename
            if not filename:
                ext = ".mp3" if media_type == "audio" else ".mp4"
                filename = f"extracted_media_{int(time.time())}{ext}"
            safe_filename = re.sub(r'[^a-zA-Z0-9_.\-\u4e00-\u9fa5]', '_', filename)
            if not (safe_filename.endswith('.mp3') or safe_filename.endswith('.mp4') or safe_filename.endswith('.m4a')):
                safe_filename += (".mp3" if media_type == "audio" else ".mp4")

            # Determine Content-Type
            content_type = "audio/mpeg" if (safe_filename.endswith(".mp3") or media_type == "audio") else "video/mp4"

            # Resolve a page URL into a real media stream before proxying it.
            #
            # This used to run only for YouTube, so a Bilibili link was proxied as
            # its HTML watch page instead of audio - the download produced a web
            # page. yt-dlp resolves both (and any other supported site), so it is
            # attempted for every platform except `direct`, where the URL already
            # points at a media file.
            if platform != "direct":
                import shutil
                import subprocess
                ytdlp_bin = shutil.which("yt-dlp") or ("/usr/local/bin/yt-dlp" if os.path.exists("/usr/local/bin/yt-dlp") else None)
                if ytdlp_bin:
                    try:
                        fmt = ("bestaudio[ext=m4a]/bestaudio/best" if media_type == "audio"
                               else "best[ext=mp4]/best")
                        cmd = [ytdlp_bin, "-g", "-f", fmt]
                        if "youtube.com" in raw_url or "youtu.be" in raw_url:
                            cmd += ["--extractor-args", "youtube:player_client=android,ios,web"]
                        cmd.append(raw_url)
                        # 15s was too tight for Bilibili (measured ~7s, with spikes).
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                        if proc.returncode == 0 and proc.stdout.strip():
                            raw_url = proc.stdout.strip().split("\n")[0]
                        else:
                            print(f"[WARN] yt-dlp -g gave no stream for {raw_url[:60]}: "
                                  f"{(proc.stderr or '').strip()[-160:]}")
                    except Exception as yt_err:
                        print(f"[WARN] yt-dlp -g resolution: {yt_err}")

            # Stream direct URL to client
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            if "bilibili.com" in raw_url or platform == "bilibili":
                headers["Referer"] = "https://www.bilibili.com/"

            # Forward client Range header if requested
            client_range = self.headers.get("Range")
            if client_range:
                headers["Range"] = client_range

            req = urllib.request.Request(raw_url, headers=headers)
            try:
                resp = urllib.request.urlopen(req, timeout=30)
                status_code = resp.status if hasattr(resp, 'status') else 200
                self.send_response(status_code)
                self.send_header("Content-Type", content_type)
                # Must be ASCII-safe: a Chinese filename in this header raises
                # UnicodeEncodeError inside http.server, which is exactly the bug
                # the export path had ("导出合集是 nothing"). build_content_disposition
                # emits an ASCII fallback plus an RFC 5987 filename*.
                self.send_header("Content-Disposition", build_content_disposition(safe_filename))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Access-Control-Allow-Origin", "*")
                
                content_len = resp.headers.get("Content-Length")
                if content_len:
                    self.send_header("Content-Length", content_len)
                content_range = resp.headers.get("Content-Range")
                if content_range:
                    self.send_header("Content-Range", content_range)

                self.end_headers()

                # Stream chunks directly (zero disk footprint)
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                return
            except urllib.error.HTTPError as he:
                print(f"[ERROR] Upstream stream HTTPError: {he.code} {he.reason}")
                self.send_error_json(he.code, f"上游媒体流传输受限 ({he.code}): {he.reason}")
                return
            except Exception as ue:
                print(f"[ERROR] Upstream stream error: {ue}")
                self.send_error_json(502, f"媒体流代理传输异常: {str(ue)}")
                return
        except Exception as e:
            self.send_error_json(500, f"下载服务内部异常: {str(e)}")

    def handle_transcript_search(self):
        try:
            params = parse_query_params(self.path)
            query = params.get("query", "").strip()
            ep_id = params.get("episode_id", "ep01").strip().lower()

            if not query:
                self.send_error_json(400, "缺少 query 参数")
                return

            transcript_file = os.path.join(DATA_DIR, "transcripts", f"{ep_id}_transcript.json")
            if not os.path.exists(transcript_file):
                transcript_file = os.path.join(DATA_DIR, "transcripts", "ep01_transcript.json")

            hits = []
            if os.path.exists(transcript_file):
                with open(transcript_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                pattern = re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)
                for item in data:
                    text = item.get("text", "") or item.get("sentence", "")
                    if pattern.search(text):
                        start_sec = float(item.get("start", 0))
                        mins = int(start_sec // 60)
                        secs = int(start_sec % 60)
                        ts = f"[{mins:02d}:{secs:02d}]"
                        hits.append({
                            "sentence": text.replace("\n", " ").strip(),
                            "start": start_sec,
                            "timestamp": ts,
                            "speaker": item.get("speaker", "Prof. Michael Sandel")
                        })
                        if len(hits) >= 10:
                            break

            all_eps = get_all_episodes()
            dict_match = None
            for eid, ep_content in all_eps.items():
                for w in ep_content.get("words", []):
                    if w.get("word", "").lower() == query.lower():
                        dict_match = w
                        break
                if dict_match:
                    break

            res = {
                "success": True,
                "query": query,
                "episode_id": ep_id,
                "total_hits": len(hits),
                "hits": hits,
                "dict_match": dict_match
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_add_custom_word(self, body_str):
        try:
            req = json.loads(body_str) if body_str else {}
            ep_id = req.get("episode_id", "ep01").strip().lower()
            word = req.get("word", "").strip()
            if not word:
                self.send_error_json(400, "缺少 word 参数")
                return

            def_cn = req.get("def_cn", "").strip() or "暂无释义"
            phonetic = req.get("phonetic", "").strip() or "/--/"
            pos = req.get("pos", "n.").strip()
            level = req.get("level", "toefl_ielts").strip()
            sentence = req.get("sentence", "").strip() or f"In this lecture, the concept of {word} plays an important philosophical role."
            sentence_cn = req.get("sentence_cn", "").strip() or f"在本堂课中，{word} 的概念扮演了重要的哲学角色。"
            speaker = req.get("speaker", "Prof. Michael Sandel").strip()
            timestamp = req.get("timestamp", "[10:00]").strip()
            audio_start = float(req.get("audio_start", 600.0))

            new_entry = {
                "word": word,
                "phonetic": phonetic,
                "pos": pos,
                "level": level,
                "def_cn": def_cn,
                "def_en": req.get("def_en", ""),
                "sentence": sentence,
                "sentence_cn": sentence_cn,
                "cloze_sentence": sentence.replace(word, "___").replace(word.capitalize(), "___"),
                "speaker": speaker,
                "timestamp": timestamp,
                "audio_start": audio_start,
                "audio_duration": 6.0,
                "audio_url": f"/assets/audio/custom_{word.lower()}.mp3",
                "native_clip_url": f"/assets/audio/clips/custom_{word.lower()}_native.mp3",
                "scene_img": "/assets/scenes/scene_theatre.jpg",
                "scene_desc": f"哈佛 Sanders 剧院授课实景 · 时间戳 {timestamp}",
                "is_custom_added": True
            }

            global EPISODE_DATA
            if ep_id in EPISODE_DATA:
                existing_idx = None
                for idx, ew in enumerate(EPISODE_DATA[ep_id].get("words", [])):
                    if ew.get("word", "").lower() == word.lower():
                        existing_idx = idx
                        break
                if existing_idx is None:
                    EPISODE_DATA[ep_id]["words"].append(new_entry)
                    try:
                        with open(CURRICULUM_FILE, "w", encoding="utf-8") as f:
                            json.dump(EPISODE_DATA, f, ensure_ascii=False, indent=2)
                    except Exception as pe:
                        print(f"[WARN] Failed to persist new word: {pe}")
                else:
                    new_entry = EPISODE_DATA[ep_id]["words"][existing_idx]

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "word_data": new_entry}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_feedback(self, body_str):
        try:
            req = json.loads(body_str)
            text = req.get("text", "").strip()
            category = req.get("category", "课程反馈").strip()
            user_email = req.get("user_email", "").strip()
            current_page = req.get("current_page", "主页").strip()
            image_base64 = req.get("image_base64", "").strip()

            # The UI allows a screenshot-only report, so require text OR screenshot.
            if not text and not image_base64:
                self.send_error_json(400, "反馈内容与截图至少提供一项。")
                return
            if len(text) > 5000 or len(category) > 60 or len(user_email) > 200 or len(current_page) > 300:
                self.send_error_json(400, "反馈内容过长。")
                return
            # Unauthenticated screenshot upload: cap it, otherwise the endpoint is
            # a trivial disk-exhaustion vector. 16 MB of base64 ~= a 12 MB image,
            # comfortably above any realistic screenshot.
            if len(image_base64) > 16 * 1024 * 1024:
                self.send_error_json(413, "截图过大（上限约 12MB）。")
                return

            feedback_id = f"fb_{time.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
            saved_img_url = ""
            
            if image_base64:
                try:
                    if "," in image_base64:
                        image_base64 = image_base64.split(",", 1)[1]
                    img_bytes = base64.b64decode(image_base64)
                    if len(img_bytes) > 12 * 1024 * 1024:
                        self.send_error_json(413, "截图过大（上限 12MB）。")
                        return
                    img_filename = f"{feedback_id}.png"
                    full_img_path = os.path.join(FEEDBACK_IMG_DIR, img_filename)
                    with open(full_img_path, "wb") as f_img:
                        f_img.write(img_bytes)
                    saved_img_url = f"/assets/feedback/{img_filename}"
                except Exception as img_err:
                    print(f"[WARN] Error saving feedback screenshot: {img_err}")

            with _WRITE_LOCK:
                records = []
                if os.path.exists(FEEDBACK_FILE):
                    try:
                        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                            records = json.load(f)
                    except:
                        records = []

                entry = {
                    "id": feedback_id,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "category": category,
                    "text": text,
                    "user_email": user_email,
                    "current_page": current_page,
                    "has_screenshot": bool(saved_img_url),
                    "screenshot_url": saved_img_url,
                    "target_developer_email": "billychen0726@gmail.com",
                    "dispatch_status": "RECORDED_LOCALLY_NOT_EMAILED"
                }
                records.append(entry)
                with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "feedback_id": feedback_id,
                "message": "您的反馈意见与现场截图已成功记录，开发者将在后台查看。",
                "target_email": "billychen0726@gmail.com"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def handle_add_collection(self, body_str):
        """Creates a user-defined collection.

        NOTE: this method previously lived *inside* the `if __name__ == "__main__"`
        block, after httpd.serve_forever() -- i.e. it was unreachable and
        RequestHandler had no such attribute, so POST /api/collection/add always
        raised AttributeError and nginx answered 502.
        """
        try:
            req = json.loads(body_str)
            cid = req.get("id", "").strip().lower()
            title = req.get("title", "").strip()
            en_title = req.get("en_title", title).strip()
            university = req.get("university", "Global Open Academic").strip()
            instructor = req.get("instructor", "特约主讲教授").strip()
            desc = req.get("desc", "").strip()
            cover_scene = req.get("cover_scene", "/assets/scenes/scene_theatre.jpg").strip()

            if not cid or not title:
                self.send_error_json(400, "合集 ID 和名称不能为空！")
                return
            if not re.fullmatch(r"[a-z0-9_\-]{2,64}", cid):
                self.send_error_json(400, "合集 ID 仅允许 2-64 位小写字母、数字、下划线或连字符！")
                return
            if cid in COLLECTIONS_DATA:
                self.send_error_json(409, f"合集 ID 已存在: {cid}")
                return
            if len(title) > 120 or len(desc) > 1000:
                self.send_error_json(400, "名称或描述过长！")
                return

            with _WRITE_LOCK:
                COLLECTIONS_DATA[cid] = {
                    "id": cid,
                    "title": title,
                    "en_title": en_title[:200],
                    "university": university[:120],
                    "instructor": instructor[:120],
                    "cover_scene": cover_scene,
                    "badge": "自定义精选 · 持续扩充",
                    "total_episodes": 0,
                    "desc": desc,
                    "episodes": []
                }
                created = dict(COLLECTIONS_DATA[cid])

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"合集《{title}》创建成功！",
                "collection": created
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_error_json(500, str(e))


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Concurrent HTTP server.

    The service used to run on a single-threaded socketserver.TCPServer with a
    listen backlog of 5, so one synchronous edge-tts synthesis blocked every
    other request (measured: a single /api/import/link call stalled the whole
    API for ~6s, and /api/vocab-bank timed out at 21s).
    """
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128


if __name__ == "__main__":
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    sys.stdout.reconfigure(encoding='utf-8')
    if not DEFAULT_CONFIG["api_key"]:
        print("[WARN] No DEEPSEEK_API_KEY configured; server-side AI import will fail "
              "(set it in the systemd unit or data/secret_config.json).")
    with ThreadingHTTPServer(("", PORT), RequestHandler) as httpd:
        print(f"[READY] Harvard Justice AI Vocabulary Studio running at http://localhost:{PORT}")
        httpd.serve_forever()
