# -*- coding: utf-8 -*-
"""S9 - build exam word decks (TOEFL / IELTS / GRE / 考研) from real, licensed data.

Why this stage exists
---------------------
The app taught vocabulary only through Harvard Justice lectures. The user asked
for exam-oriented vocabulary - rarer words, and crucially noun/verb PHRASES, not
just single words. Inventing such a list is not acceptable (this project already
shipped one fabricated deck), and neither is copying a list we may not use.

What the research (verified by fetching every URL) found:

* **ECDICT** (github.com/skywind3000/ECDICT, **MIT**) - 13-column CSV with
  `word, phonetic, definition(EN), translation(CN), pos, collins, oxford, tag,
  bnc, frq, exchange, detail, audio`. `tag` carries real exam markers
  (`toefl`, `ielts`, `gre`, `cet4`, `cet6`, `ky`, `gk`, `zk`) and the list
  genuinely contains multi-word units ("community service", "no gains without
  pains"). No example sentences.
* **Tatoeba** (**CC-BY 2.0 FR**, attribution required) - 77,985 resolvable
  cmn-eng sentence pairs. Usable for short example sentences; its English side
  has a median length of 6 words, so it cannot supply 长难句.
* `qwerty-learner` bundles 380 dictionaries but is **GPL-3.0** (copyleft) and some
  of its files derive from proprietary books - deliberately NOT used.
* There is **no `sat` tag in ECDICT**, so no SAT deck is produced here. Faking one
  by re-labelling TOEFL/GRE words would be exactly the dishonesty this project
  keeps having to remove.
* WikiMatrix (CC-BY-SA, viral) is the only permissive long en-zh pair source; it
  is left for a later stage rather than pulled in under a copyleft obligation now.

Output
------
* `data/exam_decks.json`  - decks in the same shape as the lecture decks, so the
  existing S4c (author missing def_en) and S6b (bank sync) stages absorb them
  with no new AI code.
* `docs/THIRD_PARTY_DATA.md` - source, licence and exact retrieval URL.

Usage
-----
    python s9_import_exam_decks.py --dry-run
    python s9_import_exam_decks.py --exams toefl,ielts,gre,ky --size 400 --with-tatoeba
"""
import argparse
import bz2
import csv
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import APP_DIR, DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log, save_json  # noqa: E402

ECDICT_URL = "https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv"
RAW_DIR = os.path.join(DATA_DIR, "raw")
ECDICT_CACHE = os.path.join(RAW_DIR, "ecdict.csv")
TATOEBA = {
    "cmn_links": "https://downloads.tatoeba.org/exports/per_language/cmn/cmn-eng_links.tsv.bz2",
    "cmn_sentences": "https://downloads.tatoeba.org/exports/per_language/cmn/cmn_sentences.tsv.bz2",
    "eng_sentences": "https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2",
}
EXAM_DECKS = {
    "toefl": {"id": "exam_toefl", "tag": "toefl",
              "title": "TOEFL Academic Vocabulary", "cn_title": "托福学术核心词汇"},
    "ielts": {"id": "exam_ielts", "tag": "ielts",
              "title": "IELTS Academic Vocabulary", "cn_title": "雅思学术核心词汇"},
    "gre": {"id": "exam_gre", "tag": "gre",
            "title": "GRE Verbal Vocabulary", "cn_title": "GRE 高阶词汇"},
    "ky": {"id": "exam_ky", "tag": "ky",
           "title": "Postgraduate Entrance Exam Vocabulary", "cn_title": "考研英语核心词汇"},
    # ECDICT's exam tags sit almost exclusively on single words: measured phrase
    # candidates are toefl 4 / ielts 2 / gre 0 / ky 0. Phrases DO exist in the
    # data ("community service", "no gains without pains") but carry no exam tag,
    # so this deck selects them with the source's own quality markers instead of
    # re-labelling single-word exams as phrases.
    "phrases": {"id": "exam_phrases", "tag": None,
                "title": "Academic Phrases & Collocations", "cn_title": "学术词组与固定搭配"},
}
# Frequency ranks at or below this are everyday words; the user asked for the
# ones that do NOT show up in daily reading.
COMMON_RANK_CUTOFF = 2500
# The user explicitly asked for noun/verb PHRASES, not just single words. A pure
# frequency ranking fills every slot with rare single words first, so each deck
# reserves this share for multi-word units.
PHRASE_TARGET = 0.35
MAX_PHRASE_SHARE = 0.5
OUT = os.path.join(DATA_DIR, "exam_decks.json")
ATTRIBUTION = os.path.join(APP_DIR, "docs", "THIRD_PARTY_DATA.md")


def fetch(url, dest, rep, timeout=600):
    """Download once, keep it cached. The CSV is 66 MB, so never re-fetch blindly."""
    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        log("  cached %s (%.1f MB)", os.path.basename(dest), os.path.getsize(dest) / 1e6)
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    log("  downloading %s", url)
    tmp = dest + ".part"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VerbaLex-import"})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
            total = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
                if total % (20 << 20) < (1 << 20):
                    log("    ... %.0f MB", total / 1e6)
        os.replace(tmp, dest)
        log("  saved %s (%.1f MB)", os.path.basename(dest), os.path.getsize(dest) / 1e6)
        return True
    except Exception as exc:  # noqa: BLE001
        log("  DOWNLOAD FAILED: %s", exc)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def parse_pos(raw):
    """ECDICT encodes pos as frequency pairs: 'n:46/v:54' -> 'n., v.'"""
    if not raw:
        return ""
    parts = []
    for chunk in re.split(r"[/,]", raw):
        name = chunk.split(":")[0].strip().lower().rstrip(".")
        if name and name not in parts:
            parts.append(name)
    return ", ".join(p + "." for p in parts[:3])


def norm_def_cn(text):
    return re.sub(r"\s+", " ", (text or "").replace("\\n", "；").replace("\n", "；")).strip("； ")


def is_multiword(word):
    return " " in word.strip()


def load_tatoeba(rep, limit_words):
    """word -> (sentence, sentence_cn) from real CC-BY pairs. Empty if unavailable.

    Streamed with bz2.open and reduced to the ids the links file mentions, so the
    2-million-sentence English export never has to fit in memory at once.
    """
    paths = {}
    for key, url in TATOEBA.items():
        dest = os.path.join(RAW_DIR, os.path.basename(url))
        if not fetch(url, dest, rep):
            return {}
        paths[key] = dest

    cmn_ids, eng_ids, pairs = set(), set(), []
    with bz2.open(paths["cmn_links"], "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            bits = line.rstrip("\n").split("\t")
            if len(bits) == 2 and bits[0] and bits[1]:
                cmn_ids.add(bits[0])
                eng_ids.add(bits[1])
                pairs.append((bits[0], bits[1]))

    def read_subset(path, wanted):
        table = {}
        with bz2.open(path, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                bits = line.rstrip("\n").split("\t")
                if len(bits) >= 3 and bits[0] in wanted:
                    table[bits[0]] = bits[2]
        return table

    cmn = read_subset(paths["cmn_sentences"], cmn_ids)
    eng = read_subset(paths["eng_sentences"], eng_ids)
    best = {}
    for cid, eid in pairs:
        ctext, etext = cmn.get(cid), eng.get(eid)
        if not ctext or not etext:
            continue
        for w in set(re.findall(r"[a-zA-Z][a-zA-Z'-]+", etext.lower())):
            if w not in limit_words:
                continue
            # Short, clean sentences make better cards than long rambling ones.
            score = (abs(len(etext.split()) - 12), len(etext))
            if w not in best or score < best[w][0]:
                best[w] = (score, etext.strip(), ctext.strip())
    rep.note("Tatoeba: %d linked pairs, %d Chinese / %d English sentences resolved"
             % (len(pairs), len(cmn), len(eng)))
    return {w: (v[1], v[2]) for w, v in best.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exams", default="toefl,ielts,gre,ky,phrases")
    ap.add_argument("--size", type=int, default=400, help="words per exam deck")
    ap.add_argument("--with-tatoeba", action="store_true",
                    help="attach real CC-BY example sentences (attribution written)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stage", default="s9_exam_decks")
    args = ap.parse_args()

    rep = Report(args.stage)
    exams = [e.strip() for e in args.exams.split(",") if e.strip()]
    unknown = [e for e in exams if e not in EXAM_DECKS]
    rep.check("requested exams are supported by the source", not unknown,
              "unsupported: %s" % unknown if unknown else ", ".join(exams))
    if unknown:
        rep.write()
        return 1

    if not fetch(ECDICT_URL, ECDICT_CACHE, rep):
        rep.check("ECDICT source reachable", False, ECDICT_URL)
        rep.write()
        return 1
    rep.check("ECDICT source reachable", True,
              "%.1f MB cached" % (os.path.getsize(ECDICT_CACHE) / 1e6))
    rep.note("ECDICT is MIT licensed (github.com/skywind3000/ECDICT); "
             "attribution is written to docs/THIRD_PARTY_DATA.md")

    csv.field_size_limit(10 ** 7)
    buckets = {e: [] for e in exams}
    stats = defaultdict(int)
    with open(ECDICT_CACHE, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats["rows"] += 1
            word = (row.get("word") or "").strip()
            tags = (row.get("tag") or "").strip()
            if not word:
                continue
            if word[0].isupper():            # proper nouns are not study words
                stats["proper_noun"] += 1
                continue
            cn = norm_def_cn(row.get("translation"))
            if not cn:
                stats["no_chinese"] += 1
                continue
            phrase = is_multiword(word)
            if not phrase and len(word) < 4:
                stats["too_short"] += 1
                continue
            # A phrase must look like a lexical unit, not a stray fragment.
            if phrase:
                tokens = word.split()
                if not (2 <= len(tokens) <= 4) or any(
                        not re.fullmatch(r"[a-z][a-z'\-]*", t) for t in tokens):
                    stats["phrase_shape"] += 1
                    continue
            if not tags and not phrase:
                continue
            ranks = []
            for col in ("bnc", "frq"):
                try:
                    value = int((row.get(col) or "0").strip() or 0)
                except ValueError:
                    value = 0
                if value:
                    ranks.append(value)
            if not phrase and ranks and min(ranks) <= COMMON_RANK_CUTOFF:
                stats["too_common"] += 1
                continue
            entry = {
                "word": word,
                "phonetic": ("/" + row["phonetic"].strip() + "/")
                if (row.get("phonetic") or "").strip() else "",
                "pos": parse_pos(row.get("pos")),
                "def_cn": cn,
                "def_en": re.sub(r"\s+", " ", (row.get("definition") or "")
                                 .replace("\\n", " ")).strip(),
                "exchange": (row.get("exchange") or "").strip(),
                "collins": (row.get("collins") or "").strip(),
                "oxford": (row.get("oxford") or "").strip(),
                "rank": min(ranks) if ranks else 0,
                "_phrase": phrase,
            }
            if entry["def_en"]:
                # Dictionary prose, not our learner-dictionary house style: the
                # S4c gate applies its strict length/format rules only to text it
                # authored itself.
                entry["def_en_source"] = "ecdict"
            for exam in exams:
                tag = EXAM_DECKS[exam]["tag"]
                if tag is None:
                    # Phrase deck: keep only units the source itself marks as
                    # established vocabulary (Collins star or Oxford 3000/5000).
                    if not phrase:
                        continue
                    try:
                        collins = int(entry["collins"] or 0)
                    except ValueError:
                        collins = 0
                    if collins < 1 and entry["oxford"] not in ("1", "2"):
                        stats["phrase_unmarked"] += 1
                        continue
                elif tag not in tags.split():
                    continue
                buckets[exam].append(entry)

    rep.check("ECDICT parsed", stats["rows"] > 100000,
              "%d rows; %s" % (stats["rows"], dict(stats)))
    for exam in exams:
        rep.note("%s: %d candidate words" % (exam, len(buckets[exam])))

    # Assign each word to exactly one deck so the decks do not overlap: a word
    # tagged toefl+gre is placed where that deck is currently thinnest. Each
    # deck's preference order is: its reserved phrases (rarest first), then rare
    # single words, then any leftover phrases.
    chosen = {e: [] for e in exams}
    seen = set()
    preferences = {}
    for exam in exams:
        ranked = sorted(buckets[exam], key=lambda w: (-w["rank"], w["word"]))
        phrases = [c for c in ranked if c["_phrase"]]
        singles = [c for c in ranked if not c["_phrase"]]
        reserve = min(len(phrases), int(args.size * PHRASE_TARGET))
        preferences[exam] = phrases[:reserve] + singles + phrases[reserve:]
        rep.note("%s: %d phrase candidates available, %d reserved for this deck"
                 % (exam, len(phrases), reserve))
    order = sorted(exams, key=lambda e: -len(preferences[e]))
    while any(len(chosen[e]) < args.size and preferences[e] for e in exams):
        for exam in order:
            pool = preferences[exam]
            # The phrase share caps MIXED decks only; the dedicated phrase deck
            # is legitimately 100% phrases.
            cap = (int(args.size * MAX_PHRASE_SHARE)
                   if EXAM_DECKS[exam]["tag"] else args.size)
            while pool and len(chosen[exam]) < args.size:
                cand = pool.pop(0)
                key = cand["word"].lower()
                if key in seen:
                    continue
                if cand["_phrase"] and sum(1 for c in chosen[exam]
                                           if c["_phrase"]) >= cap:
                    continue
                seen.add(key)
                chosen[exam].append(cand)
                break
        if all(len(chosen[e]) >= args.size or not preferences[e] for e in exams):
            break

    for exam in exams:
        rep.check("%s deck reached the requested size" % exam,
                  len(chosen[exam]) >= min(args.size, len(buckets[exam])),
                  "%d/%d" % (len(chosen[exam]), args.size))
        phrases = sum(1 for c in chosen[exam] if c["_phrase"])
        rep.note("%s: %d words, %d of them phrases (%.0f%%), "
                 "%d without phonetic, %d without an English definition"
                 % (exam, len(chosen[exam]), phrases,
                    100.0 * phrases / max(1, len(chosen[exam])),
                    sum(1 for c in chosen[exam] if not c["phonetic"]),
                    sum(1 for c in chosen[exam] if not c["def_en"])))

    sentences = {}
    if args.with_tatoeba:
        wanted = {(c["word"].lower() if not c["_phrase"] else c["word"].lower())
                  for exam in exams for c in chosen[exam]}
        sentences = load_tatoeba(rep, wanted)
        rep.check("Tatoeba sentences attached", bool(sentences),
                  "%d of %d target words have a real CC-BY sentence"
                  % (len(sentences), len(wanted)))
    else:
        rep.note("no example sentences attached (--with-tatoeba not given); cards "
                 "will show no example rather than an invented one")

    crossed = set()
    for exam in exams:
        for c in chosen[exam]:
            k = c["word"].lower()
            if k in crossed:
                rep.check("no word is present in two exam decks", False, k)
            crossed.add(k)
    rep.check("no word is present in two exam decks", True, "%d unique words" % len(crossed))

    if args.dry_run:
        rep.note("dry run: data/exam_decks.json not written")
        payload = rep.write()
        log("\nS9 dry-run %s - %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    decks = {}
    for exam in exams:
        meta = EXAM_DECKS[exam]
        words = []
        for c in chosen[exam]:
            entry = {k: v for k, v in c.items() if not k.startswith("_")}
            sent = sentences.get(c["word"].lower())
            if sent:
                entry["sentence"], entry["sentence_cn"] = sent
                entry["sentence_source"] = "tatoeba"      # CC-BY 2.0 FR
            entry["exam"] = meta["tag"]
            entry["source"] = "ecdict"                    # MIT
            words.append(entry)
        decks[meta["id"]] = {
            "id": meta["id"],
            "title": meta["title"],
            "cn_title": meta["cn_title"],
            "topic": "%s 考试词汇（真实词表导入，含词组）" % meta["cn_title"],
            "duration": "词汇表",
            "cover_scene": "/assets/scenes/scene_library.jpg",
            "platform": "exam_list",
            "source_url": ECDICT_URL,
            "words": words,
        }
    save_json(OUT, decks)
    rep.check("exam decks written", os.path.exists(OUT),
              "%s (%.1f KB, %d decks, %d words)"
              % (os.path.basename(OUT), os.path.getsize(OUT) / 1024, len(decks),
                 sum(len(d["words"]) for d in decks.values())))

    with open(ATTRIBUTION, "w", encoding="utf-8") as f:
        f.write(ATTRIBUTION_TEXT.format(
            ecdict_url=ECDICT_URL, rows=stats["rows"],
            decks="\n".join("| %s | %s | %d |" % (EXAM_DECKS[e]["cn_title"],
                                                  EXAM_DECKS[e]["id"],
                                                  len(chosen[e])) for e in exams),
            tatoeba=("Tatoeba (CC-BY 2.0 FR) example sentences were attached to "
                     "%d words." % len(sentences)) if sentences else
                    "No Tatoeba sentences were attached in this build."))
    rep.check("attribution recorded", os.path.exists(ATTRIBUTION), ATTRIBUTION)

    payload = rep.write()
    log("\nS9 %s - %d decks, %d words, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(decks),
        sum(len(d["words"]) for d in decks.values()),
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


ATTRIBUTION_TEXT = """# 第三方数据来源与许可（Third-party data attribution）

本仓库的课程词表（哈佛《公正》各集、耶鲁、用户导入）来自本项目的语音转写与翻译流水线。
**考试词表（托福 / 雅思 / GRE / 考研）不是本项目生成的**，而是从下列开源数据导入，
在此按许可要求署名。

## ECDICT

- 项目：https://github.com/skywind3000/ECDICT
- 许可：**MIT License**（Copyright (c) 2025 Linwei）
- 取用地址：`{ecdict_url}`
- 解析行数：{rows}
- 取用字段：`word`、`phonetic`、`definition`（英英释义）、`translation`（中文释义）、
  `pos`、`tag`（考试标签）、`collins`、`oxford`、`bnc`/`frq`（词频）、`exchange`（词形变化）
- 说明：本项目**未修改**词条文本，仅做字段映射、按 `tag` 过滤与排序筛选。
  未收录 ECDICT 的 `detail` 字段（其官方标注为"待添加"，实际为空）。

| 词表 | deck id | 词条数 |
| --- | --- | --- |
{decks}

## Tatoeba

- 项目：https://tatoeba.org
- 许可：**CC-BY 2.0 FR**（要求署名）
- 取用地址：`https://downloads.tatoeba.org/exports/per_language/...`
- 说明：{tatoeba}

## 未采用的数据（许可或质量原因）

| 数据 | 原因 |
| --- | --- |
| Kaiyiwing/qwerty-learner 词书 | **GPL-3.0** 传染性许可，且部分词书源自专有出版物，不适合并入本仓库 |
| 1eez/103976 | 无许可证 |
| mahavivo/english-wordlists | 无许可证，内容据称源自 2003 年金山词霸（专有） |
| Coxhead AWL 官方表 | 未声明开源许可，再分发法律状态不明 |
| Oxford 3000/5000、Longman 3000、COCA 20000 | 商业专有词表 |
| TED2020 / News-Commentary / OpenSubtitles | CC-BY-NC-ND / NC-SA，禁止商用或改作 |
| **SAT 词表** | **ECDICT 没有 `sat` 标签**，因此本仓库不提供 SAT 词表——
  用托福/GRE 词重新贴标签属于伪造数据，本项目明确拒绝这样做。 |
"""


if __name__ == "__main__":
    sys.exit(main())
