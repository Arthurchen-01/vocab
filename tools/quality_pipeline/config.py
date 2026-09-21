# -*- coding: utf-8 -*-
"""Shared configuration and small helpers for the Ep0x media/translation quality pipeline.

Everything is env-overridable so the SAME scripts run locally (Windows dev box)
and on the production host (where the raw media lives).
"""
import hashlib
import json
import os
import random
import re
import sys
import time

# ---------------------------------------------------------------- paths
# Windows consoles default to a legacy code page (GBK on a Chinese install) and
# raise UnicodeEncodeError on anything outside it - the exported Markdown alone
# contains an emoji, which used to crash a gate while printing a *detail* string.
# Never let logging be the thing that fails.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - not a tty, or an exotic runtime
        pass

APP_DIR = os.environ.get("VOCAB_APP_DIR") or os.environ.get("VOCAB_REPO_DIR") or "."
if os.path.basename(APP_DIR) != "harvard_justice_app" and os.path.isdir("harvard_justice_app"):
    APP_DIR = os.path.join(os.getcwd(), "harvard_justice_app")

DATA_DIR = os.path.join(APP_DIR, "data")
TRANS_DIR = os.path.join(DATA_DIR, "transcripts")
RAW_AUDIO_DIR = os.path.join(DATA_DIR, "raw_audio")
RAW_VIDEO_DIR = os.path.join(DATA_DIR, "raw_video")
PUBLIC_DIR = os.path.join(APP_DIR, "public")
AUDIO_CLIP_DIR = os.path.join(PUBLIC_DIR, "assets", "audio", "clips")
AUDIO_DIR = os.path.join(PUBLIC_DIR, "assets", "audio")
SCENE_DIR = os.path.join(PUBLIC_DIR, "assets", "scenes")

WORK_DIR = os.environ.get("VOCAB_WORK_DIR") or os.path.join(APP_DIR, "data", "quality")
OUT_DIR = os.path.join(WORK_DIR, "out")
CACHE_DIR = os.path.join(WORK_DIR, "cache")
REPORT_DIR = os.path.join(WORK_DIR, "reports")
BACKUP_DIR = os.path.join(WORK_DIR, "backup")
for _d in (WORK_DIR, OUT_DIR, CACHE_DIR, REPORT_DIR, BACKUP_DIR):
    os.makedirs(_d, exist_ok=True)

EPISODE = os.environ.get("VOCAB_EP", "ep02")

# Stable deck order used when rebuilding the master vocabulary bank (S6).
CURRICULUM_KEYS_ORDER = [k for k in (os.environ.get("VOCAB_DECK_ORDER") or
                                     "ep01,ep02,ep03,yale_ep01").split(",") if k]

# ---------------------------------------------------------------- AI gateway
# Resolution order for every AI setting: environment, then data/secret_config.json,
# then the built-in default. Hard-coding one vendor's base URL and model id meant a
# switch to a self-hosted gateway required editing code in two places.
SECRET_FILE = os.path.join(DATA_DIR, "secret_config.json")


def _secret():
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _setting(env_key, secret_key, default=""):
    value = (os.environ.get(env_key) or "").strip()
    if value:
        return value
    return (str(_secret().get(secret_key) or "")).strip() or default


AI_BASE = _setting("VOCAB_AI_BASE", "api_base", "https://api.deepseek.com")
AI_MODEL = _setting("VOCAB_AI_MODEL", "model", "deepseek-chat")
AI_REVIEW_MODEL = _setting("VOCAB_AI_REVIEW_MODEL", "review_model", AI_MODEL)
# A reasoning model spends part of max_tokens on hidden thinking, so the small
# budgets some stages use (400-3000) always truncate once before succeeding.
# Raising the floor centrally avoids a wasted round-trip per call; it is an
# operator setting because it only applies to reasoning-style models.
try:
    AI_MIN_TOKENS = int(_setting("VOCAB_AI_MIN_TOKENS", "min_tokens", "0") or 0)
except ValueError:
    AI_MIN_TOKENS = 0


def api_key():
    k = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if k:
        return k
    # A gateway may hand out "token;model" credentials; only the token is the key.
    raw = (str(_secret().get("deepseek_api_key") or "")).strip()
    return raw.split(";", 1)[0].strip() if ";" in raw else raw


# ---------------------------------------------------------------- tunables
CLIP_PAD_HEAD = float(os.environ.get("VOCAB_PAD_HEAD", "0.12"))   # seconds before sentence start
CLIP_PAD_TAIL = float(os.environ.get("VOCAB_PAD_TAIL", "0.18"))   # seconds after sentence end
MAX_SENTENCE_SECONDS = float(os.environ.get("VOCAB_MAX_SENT_SEC", "26"))
MAX_SENTENCE_WORDS = int(os.environ.get("VOCAB_MAX_SENT_WORDS", "45"))
MIN_SENTENCE_WORDS = int(os.environ.get("VOCAB_MIN_SENT_WORDS", "4"))
SIM_GATE = float(os.environ.get("VOCAB_SIM_GATE", "0.86"))        # AI text vs ASR text similarity floor

TOL_CLIP_SECONDS = 0.25     # |probe duration - planned window|
TOL_AUDIO_EDGE = 0.35       # clip must not exceed raw audio duration


# ---------------------------------------------------------------- helpers
def log(msg, *args):
    if args:
        msg = msg % args
    print(msg, flush=True)


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, obj, indent=2):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent)
    os.replace(tmp, path)
    return path


def sha1(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def normalize_text(text):
    """Fold curly quotes/dashes and stray whitespace so comparisons are stable."""
    t = text or ""
    for a, b in (("\u2019", "'"), ("\u2018", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"), ("\u00a0", " "), ("\u2026", "...")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def norm_words(text):
    """Lowercase word tokens, no punctuation - used for fidelity comparisons."""
    return re.findall(r"[a-z0-9']+", normalize_text(text).lower())


def tidy_english(text):
    """Deterministic cosmetics for subtitle text (never changes wording)."""
    t = normalize_text(text)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)      # no space before punctuation
    t = re.sub(r",\s*\.", ".", t)               # ",." -> "."
    t = re.sub(r"\.\s*,", ".", t)               # ".," -> "."
    t = re.sub(r",\s*,+", ",", t)               # duplicate commas
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"^[\s,;:]+", "", t)
    return t.strip()


def word_set(text):
    return set(norm_words(text))


def similarity(a, b):
    """Token-level Jaccard-ish similarity in [0,1] (order-insensitive)."""
    sa, sb = word_set(a), word_set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def lcs_ratio(a, b):
    """Longest-common-subsequence ratio over token lists (order sensitive)."""
    ta, tb = norm_words(a), norm_words(b)
    if not ta or not tb:
        return 0.0
    prev = [0] * (len(tb) + 1)
    for x in ta:
        cur = [0]
        for j, y in enumerate(tb):
            cur.append(prev[j] + 1 if x == y else max(cur[j], prev[j + 1]))
        prev = cur
    return prev[-1] / max(len(ta), len(tb))


def safe_name(word):
    return re.sub(r"[^a-zA-Z0-9_]", "_", (word or "").lower()).strip("_")


def load_deck_words(ep):
    """The word list for an episode, wherever it actually lives.

    Decks are authored in different generations: Ep01/Ep02 have their own
    `<ep>_curriculum_final_audited.json`, Ep03 and Yale only exist inside
    curriculum_tiered.json, and imported episodes live in custom_episodes.json.
    Returns (words, source_kind).
    """
    tiered = load_json(os.path.join(DATA_DIR, "curriculum_tiered.json")) or {}
    if ep in tiered and tiered[ep].get("words"):
        return tiered[ep]["words"], "curriculum_tiered"
    custom = load_json(os.path.join(DATA_DIR, "custom_episodes.json")) or {}
    if ep in custom and custom[ep].get("words"):
        return custom[ep]["words"], "custom_episodes"
    audited = load_json(os.path.join(DATA_DIR, f"{ep}_curriculum_final_audited.json"))
    if isinstance(audited, list) and audited:
        return audited, "audited"
    return [], "missing"


def fmt_ts(seconds):
    seconds = max(0, int(seconds or 0))
    return "%02d:%02d" % (seconds // 60, seconds % 60)


def now_stamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class Report:
    """Accumulates gate results for one stage; writes JSON + human-readable MD."""

    def __init__(self, stage):
        self.stage = stage
        self.checks = []
        self.notes = []
        self.started = now_stamp()

    def check(self, name, ok, detail="", **extra):
        row = {"check": name, "ok": bool(ok), "detail": str(detail)}
        row.update(extra)
        self.checks.append(row)
        log("  [%s] %s %s", "PASS" if ok else "FAIL", name, ("-> " + str(detail)) if detail else "")
        return bool(ok)

    def note(self, text):
        self.notes.append(text)
        log("  [note] %s", text)

    @property
    def ok(self):
        return all(c["ok"] for c in self.checks) and bool(self.checks)

    def write(self):
        payload = {
            "stage": self.stage,
            "started": self.started,
            "finished": now_stamp(),
            "ok": self.ok,
            "passed": sum(1 for c in self.checks if c["ok"]),
            "failed": sum(1 for c in self.checks if not c["ok"]),
            "checks": self.checks,
            "notes": self.notes,
        }
        save_json(os.path.join(REPORT_DIR, f"{self.stage}.json"), payload)
        lines = [f"# Gate report - {self.stage}", "",
                 f"- finished: {payload['finished']}",
                 f"- result: **{'PASS' if self.ok else 'FAIL'}** "
                 f"({payload['passed']} passed / {payload['failed']} failed)", ""]
        for c in self.checks:
            lines.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}"
                         + (f" — {c['detail']}" if c["detail"] else ""))
        if self.notes:
            lines += ["", "## notes"] + [f"- {n}" for n in self.notes]
        with open(os.path.join(REPORT_DIR, f"{self.stage}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return payload
