# -*- coding: utf-8 -*-
"""S13 - SAT deck from the most widely used public wordbook.

Provenance, stated plainly because it matters:

* Source: `Kaiyiwing/qwerty-learner`, `public/dicts/SAT_3_T.json` (4,464 entries,
  fields `name` / `trans` / `usphone` / `ukphone`).
* That repository is **GPL-3.0**, and several of its dictionaries are believed to
  derive from commercial publishers (新东方 SAT and similar). ECDICT could not
  supply SAT because it carries no `sat` tag, and re-labelling TOEFL/GRE words as
  SAT would be fabrication. The repository owner therefore chose to take the
  popular market list and accept the provenance caveat, on the record.
* Consequences, handled here rather than hidden:
  - the deck is isolated in its own file (`data/sat_deck.json`) so it can be
    dropped by deleting one file;
  - `docs/THIRD_PARTY_DATA.md` records the licence honestly;
  - nothing from this source is presented as verified-original content.

The source has no English definitions and no part of speech, so `def_en` is left
empty on purpose and S4c authors it under the usual gates.

Usage: python s13_import_sat_deck.py [--dry-run]
"""
import argparse
import csv
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import APP_DIR, DATA_DIR, Report, load_json, log, save_json  # noqa: E402

SOURCE_URL = ("https://raw.githubusercontent.com/Kaiyiwing/qwerty-learner/"
              "master/public/dicts/SAT_3_T.json")
OUT = os.path.join(DATA_DIR, "sat_deck.json")
DECK_ID = "exam_sat"
ATTRIBUTION = os.path.join(APP_DIR, "docs", "THIRD_PARTY_DATA.md")


def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers={"User-Agent": "VerbaLex-import"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def clean_gloss(text):
    return re.sub(r"\s+", " ", (text or "").replace("\u3000", " ")).strip(" ；;")


def enrich_from_ecdict(words, rep):
    """Fill def_en / pos / phonetic from the MIT-licensed ECDICT cache.

    The SAT wordbook has no English definitions and no part of speech. ECDICT is
    already on disk for S9 and covers most of these words with real dictionary
    text, so use that instead of asking a model to invent definitions - and only
    leave the remainder for S4c.
    """
    cache = os.path.join(DATA_DIR, "raw", "ecdict.csv")
    if not os.path.exists(cache):
        rep.note("ECDICT cache absent (%s): def_en/pos left for S4c" % cache)
        return 0
    wanted = {w["word"].lower(): w for w in words}
    filled_en = filled_pos = filled_phon = 0
    try:
        with open(cache, encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = (row.get("word") or "").strip().lower()
                w = wanted.get(key)
                if not w:
                    continue
                if not w["def_en"]:
                    en = re.sub(r"\s+", " ", (row.get("definition") or "").replace("\\n", " ")).strip()
                    if en:
                        w["def_en"] = en
                        w["def_en_source"] = "ecdict"
                        filled_en += 1
                if not w["pos"]:
                    pos = parse_pos(row.get("pos"))
                    if pos:
                        w["pos"] = pos
                        filled_pos += 1
                if not w["phonetic"]:
                    ph = (row.get("phonetic") or "").strip()
                    if ph:
                        w["phonetic"] = "/%s/" % ph
                        filled_phon += 1
    except Exception as exc:  # noqa: BLE001
        rep.note("ECDICT enrichment failed (%s); S4c will author the rest" % exc)
        return 0
    rep.note("ECDICT enrichment: +%d English definitions, +%d part-of-speech, "
             "+%d phonetics" % (filled_en, filled_pos, filled_phon))
    return filled_en


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rep = Report("s13_sat_deck")
    try:
        raw = fetch(SOURCE_URL)
    except Exception as exc:  # noqa: BLE001
        rep.check("SAT wordbook reachable", False, "%s (%s)" % (SOURCE_URL, exc))
        rep.write()
        return 1
    rep.check("SAT wordbook reachable", True,
              "%d entries from %s" % (len(raw), SOURCE_URL.rsplit("/", 1)[-1]))

    words, seen, no_gloss, no_phon = [], set(), 0, 0
    for item in raw:
        name = (item.get("name") or "").strip()
        glosses = [clean_gloss(g) for g in (item.get("trans") or []) if clean_gloss(g)]
        if not name:
            continue
        if not glosses:
            no_gloss += 1
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        us = (item.get("usphone") or "").strip().strip("/")
        uk = (item.get("ukphone") or "").strip().strip("/")
        phonetic = "/%s/" % (us or uk) if (us or uk) else ""
        if not phonetic:
            no_phon += 1
        words.append({
            "word": name,
            # The source gives no part of speech; leaving it empty is honest and
            # the card/export renderers now omit the bracket instead of printing [].
            "pos": "",
            "phonetic": phonetic,
            "def_cn": "；".join(glosses),
            "def_en": "",
            "source": "qwerty-learner",
            "source_url": SOURCE_URL,
            "license": "GPL-3.0 (upstream repository)",
            "exam": "sat",
        })

    rep.check("every entry carries a word and a Chinese gloss",
              all(w["word"] and w["def_cn"] for w in words), "%d entries" % len(words))
    rep.check("no duplicate headwords", len(words) == len({w["word"].lower() for w in words}),
              "%d unique" % len({w["word"].lower() for w in words}))
    rep.note("%d entries dropped for having no gloss; %d have no phonetic"
             % (no_gloss, no_phon))
    phrases = [w for w in words if " " in w["word"]]
    rep.note("%d of %d entries are multi-word units" % (len(phrases), len(words)))

    enrich_from_ecdict(words, rep)
    still = [w for w in words if not w["def_en"]]
    rep.note("%d entries still need an English definition (S4c authors those)"
             % len(still))
    no_pos = [w for w in words if not w["pos"]]
    rep.note("%d entries still have no part of speech (the source carries none)" % len(no_pos))

    deck = {
        "id": DECK_ID,
        "title": "SAT Vocabulary (popular public wordbook)",
        "cn_title": "SAT 核心词汇",
        "topic": "SAT 词表（取自公开词书 SAT_3_T，共 %d 条；来源与许可见 docs/THIRD_PARTY_DATA.md）"
                 % len(words),
        "duration": "词汇表",
        "cover_scene": "/assets/scenes/scene_theatre.jpg",
        "platform": "exam_list",
        "source_url": SOURCE_URL,
        "license_note": "GPL-3.0 upstream (Kaiyiwing/qwerty-learner); isolated deck",
        "words": words,
    }

    if args.dry_run:
        rep.note("dry run: %s not written" % os.path.basename(OUT))
        payload = rep.write()
        log("\nS13 dry-run %s - %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    save_json(OUT, {DECK_ID: deck})
    rep.check("SAT deck written", os.path.exists(OUT),
              "%s (%.1f KB, %d words)" % (os.path.basename(OUT),
                                          os.path.getsize(OUT) / 1024, len(words)))

    # Keep the attribution file honest about this one.
    if os.path.exists(ATTRIBUTION):
        with open(ATTRIBUTION, encoding="utf-8") as f:
            doc = f.read()
        marker = "## SAT 词表（qwerty-learner）"
        if marker not in doc:
            doc += """
## SAT 词表（qwerty-learner）

- 项目：https://github.com/Kaiyiwing/qwerty-learner
- 取用文件：`public/dicts/SAT_3_T.json`（%d 条）
- 许可：**GPL-3.0**（该仓库根许可），且其部分词书据信源自商业出版物（如新东方 SAT）。
- 说明：ECDICT 没有 `sat` 标签，用托福/GRE 词重贴 SAT 标签属于伪造数据，因此经仓库所有者决定，
  改用市面流行词书并**如实记录本条 provenance**。该词表隔离在 `data/sat_deck.json`，
  删除该文件即可整体移除；其内容不作为本项目原创或已核验内容呈现。
""" % len(words)
            with open(ATTRIBUTION, "w", encoding="utf-8") as f:
                f.write(doc)
            log("  attribution updated: %s", ATTRIBUTION)

    payload = rep.write()
    log("\nS13 %s - %d SAT words, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(words),
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
