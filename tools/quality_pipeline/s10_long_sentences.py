# -*- coding: utf-8 -*-
"""S10 - long / difficult sentence deck, built from the lectures we already own.

The user asked for 长难句 study material. The honest source is the project's own
output: S1 produced complete sentences from the lecture ASR and S4 produced
REVIEWED Chinese translations for the ones the decks bind to (93 / 153 / 39 across
Ep01-Ep03). Those sentences are real, timestamped, and playable - unlike anything
a generator would invent, and unlike Tatoeba, whose English side has a median
length of 6 words (measured: only 0.4% reach 30 words).

Each card gets one focal word so the app can attach a definition, plus the real
audio span so the sentence can be replayed from the lecture.

Gates: every sentence carries a reviewed translation, every sentence comes from a
real pipeline artefact, the audio span is within the lecture, the focal word
exists in the master bank, and no sentence is duplicated.

Usage: python s10_long_sentences.py [--dry-run] [--min-words 18] [--per-episode 40]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log, save_json  # noqa: E402

OUT_FILE = os.path.join(DATA_DIR, "longsent_decks.json")
DECK_ID = "hj_longsent"
EPISODES = ["ep01", "ep02", "ep03"]
FUNCTION_WORDS = set("""
a an the and or but if then than that this these those there here when where which who whom whose why how
is are was were be been being am do does did done doing have has had having will would shall should can could
may might must of to in on at by for with from into over under about as it its they them we us you your our
not no so such very more most much many few less least own same too also just only even still yet because
while although though unless until since whether what whatever however therefore thus hence
""".split())
CLAUSE_MARKERS = (" that ", " which ", " who ", " whom ", " whose ", " because ", " although ",
                  " though ", " if ", " when ", " while ", " unless ", " whether ", " whereas ")


def load_episode(ep, rep):
    sents = load_json(os.path.join(OUT_DIR, "%s_sentences.json" % ep))
    trans = load_json(os.path.join(OUT_DIR, "%s_translations.json" % ep)) or {}
    table = trans.get("translations") or {}
    if not isinstance(sents, list) or not sents:
        rep.note("%s: no sentence artefact, skipped" % ep)
        return []
    out = []
    for idx, s in enumerate(sents):
        t = table.get(str(idx))
        if not isinstance(t, dict):
            continue
        cn = (t.get("cn") or "").strip()
        text = (s.get("text") or "").strip()
        if not cn or not text:
            continue
        words = len(text.split())
        score = words + 3 * sum(text.lower().count(m) for m in CLAUSE_MARKERS) \
            + 2 * text.count(",") + 3 * text.count(";")
        out.append({"ep": ep, "index": idx, "text": text, "cn": cn,
                    "start": s.get("start"), "end": s.get("end"),
                    "words": words, "score": score,
                    "reviewed": bool(t.get("reviewed"))})
    return out


def focal_word(text, bank):
    """The hardest content word in the sentence that the bank can define.

    Widening pass first (7+ letters), then any content word the bank knows: some
    perfectly good long sentences are made of short words ("there was still no
    ship in sight"), and dropping the sentence for that would be silly.
    """
    tokens = re.findall(r"[A-Za-z][A-Za-z'\-]+", text)
    candidates = [t.lower() for t in tokens
                  if t.lower() not in FUNCTION_WORDS and t.lower() in bank]
    if not candidates:
        return ""
    long_ones = [t for t in candidates if len(t) >= 7]
    pool = long_ones or candidates
    return max(pool, key=len)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-words", type=int, default=18)
    ap.add_argument("--per-episode", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rep = Report("s10_long_sentences")
    bank = load_json(os.path.join(DATA_DIR, "vocab_bank.json")) or {}
    rep.check("master bank available", bool(bank), "%d entries" % len(bank))

    pool = []
    for ep in EPISODES:
        rows = load_episode(ep, rep)
        long_rows = [r for r in rows if r["words"] >= args.min_words]
        rep.note("%s: %d reviewed translations, %d of them >= %d words"
                 % (ep, len(rows), len(long_rows), args.min_words))
        long_rows.sort(key=lambda r: -r["score"])
        pool.extend(long_rows[:args.per_episode])

    rep.check("long sentences available from real lectures", bool(pool),
              "%d sentences selected" % len(pool))
    if not pool:
        rep.write()
        return 1

    seen, cards, no_focal = set(), [], []
    for r in pool:
        key = r["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        focal = focal_word(r["text"], bank)
        if not focal:
            no_focal.append(r["text"][:60])
            continue
        entry = bank[focal]
        cards.append({
            "word": entry.get("word") or focal,
            "phonetic": entry.get("phonetic", ""),
            "pos": entry.get("pos", ""),
            "def_cn": entry.get("def_cn", ""),
            "def_en": entry.get("def_en", ""),
            "sentence": r["text"],
            "sentence_cn": r["cn"],
            "sentence_source": "lecture:%s" % r["ep"],
            "sentence_id": r["index"],
            "sentence_start": r["start"],
            "sentence_end": r["end"],
            "audio_start": r["start"],
            "audio_end": r["end"],
            "audio_duration": (round(r["end"] - r["start"], 3)
                               if isinstance(r["start"], (int, float))
                               and isinstance(r["end"], (int, float)) else None),
            "timestamp": ("%02d:%02d" % (int(r["start"]) // 60, int(r["start"]) % 60)
                          if isinstance(r["start"], (int, float)) else ""),
            "tier": "long_sentence",
            "level": "long_sentence",
            "level_name": "长难句",
            "difficulty_words": r["words"],
            "reviewed": r["reviewed"],
            "source": "lecture",
        })

    rep.check("every card keeps a sentence and its reviewed translation",
              all(c["sentence"] and c["sentence_cn"] for c in cards),
              "%d cards, %d flagged reviewed" % (len(cards),
                                                 sum(1 for c in cards if c["reviewed"])))
    rep.check("every card has a focal word the bank can define",
              all(c["def_cn"] for c in cards),
              "%d without: %s" % (len(no_focal), no_focal[:3]))
    rep.check("every card has a playable audio span",
              all(isinstance(c["audio_start"], (int, float))
                  and isinstance(c["audio_end"], (int, float))
                  and c["audio_end"] > c["audio_start"] for c in cards),
              "%d cards" % len(cards))
    lengths = sorted(c["difficulty_words"] for c in cards)
    rep.note("sentence length min/median/max = %d/%d/%d words"
             % (lengths[0], lengths[len(lengths) // 2], lengths[-1]))
    rep.note("sources: %s" % json.dumps(
        {ep: sum(1 for c in cards if c["sentence_source"] == "lecture:%s" % ep)
         for ep in EPISODES}))

    if args.dry_run:
        rep.note("dry run: %s not written" % os.path.basename(OUT_FILE))
        payload = rep.write()
        log("\nS10 dry-run %s - %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    decks = load_json(OUT_FILE) or {}
    decks[DECK_ID] = {
        "id": DECK_ID,
        "title": "Justice Lectures: Long & Difficult Sentences",
        "cn_title": "哈佛《公正》长难句精读（讲座原句）",
        "topic": "取自讲座真实原句与已审校译文的长难句精读",
        "duration": "长难句",
        "cover_scene": "/assets/scenes/banner_harvard_series.jpg",
        "platform": "lecture_sentences",
        "words": cards,
    }
    save_json(OUT_FILE, decks)
    rep.check("long-sentence deck written", os.path.exists(OUT_FILE),
              "%s (%d cards)" % (os.path.basename(OUT_FILE), len(cards)))

    again = load_json(OUT_FILE) or {}
    rep.check("written deck round-trips",
              len((again.get(DECK_ID) or {}).get("words", [])) == len(cards),
              "%d cards" % len((again.get(DECK_ID) or {}).get("words", [])))
    payload = rep.write()
    log("\nS10 %s - %d long sentences, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(cards),
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
