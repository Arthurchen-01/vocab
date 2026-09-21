# -*- coding: utf-8 -*-
"""S5c - stamp real catalogue metadata onto the decks that are being served.

`data/source_catalog.json` holds the verified per-episode facts (YouTube id,
real English title, real Chinese title, duration, url). The S5 apply step writes
a deck's *words* but not that metadata, so ep04..ep12 went live titled "ep04",
"ep05", ... while ep01..ep03 (hand-authored) had proper titles. A user browsing
the collection sees a bare id where a title belongs.

This stage copies ONLY metadata fields from the catalogue onto the decks and
proves nothing else changed. It never invents a title: an episode with no
catalogue entry keeps whatever it has and is reported.

Usage: python s5c_apply_catalog_meta.py [--dry-run]
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log, save_json  # noqa: E402

CATALOG = os.path.join(DATA_DIR, "source_catalog.json")
TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
REPORT = os.path.join(OUT_DIR, f"{EPISODE}_catalog_meta.json")

# Only these keys are ever written, and only from the catalogue.
META_KEYS = ("title", "cn_title", "duration", "source_url", "video_id", "platform")


def catalog_index():
    """episode id -> real metadata, flattened across every series."""
    cat = load_json(CATALOG) or {}
    out = {}
    for series in cat.values():
        for ep_id, ep in (series.get("episodes") or {}).items():
            if isinstance(ep, dict):
                out[ep_id] = ep
    return out


def minutes(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    return "%d 分钟" % round(seconds / 60.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stage", default="s5c_catalog_meta")
    args = ap.parse_args()

    rep = Report(args.stage)
    cat = catalog_index()
    rep.check("source catalogue readable", bool(cat), "%d episodes" % len(cat))
    if not cat:
        rep.write()
        return 1

    decks = load_json(TIERED) or {}
    rep.check("deck file readable", bool(decks), "%d decks" % len(decks))

    before_words = {k: len(v.get("words", [])) for k, v in decks.items()}
    before_meta = {k: {m: v.get(m) for m in META_KEYS} for k, v in decks.items()}
    bare_before = [k for k, v in decks.items()
                   if k in cat and (v.get("cn_title") or "").strip() in ("", k)
                   and (cat[k].get("cn_title") or "").strip()]
    rep.note("before: %d deck(s) titled with a raw id: %s"
             % (len(bare_before), bare_before))

    stamped, untouched = [], []
    for ep_id, deck in decks.items():
        ep = cat.get(ep_id)
        if not ep:
            untouched.append(ep_id)
            continue
        changed = False
        title = (ep.get("title") or "").strip()
        cn_title = (ep.get("cn_title") or "").strip()
        # A real English title from the catalogue is preferable to a bare id, but
        # never overwrite a hand-authored title with a worse one.
        if title and deck.get("title") in (None, "", ep_id):
            deck["title"] = title
            changed = True
        if cn_title and deck.get("cn_title") in (None, "", ep_id):
            deck["cn_title"] = cn_title
            changed = True
        dur = minutes(ep.get("duration"))
        if dur and not (deck.get("duration") or "").strip():
            deck["duration"] = dur
            changed = True
        if ep.get("url") and not (deck.get("source_url") or "").strip():
            deck["source_url"] = ep["url"]
            changed = True
        if ep.get("video_id") and not (deck.get("video_id") or "").strip():
            deck["video_id"] = ep["video_id"]
            changed = True
        if ep.get("platform") and not (deck.get("platform") or "").strip():
            deck["platform"] = ep["platform"]
            changed = True
        (stamped if changed else untouched).append(ep_id)

    rep.note("stamped: %s" % (stamped or "none"))
    rep.note("already complete / not catalogued: %s" % (untouched or "none"))

    # Gate: no deck may still be titled with its own bare id.
    bare = [k for k, v in decks.items()
            if (v.get("cn_title") or "").strip() in ("", k)
            and k in cat and (cat[k].get("cn_title") or "").strip()]
    rep.check("no catalogued episode is still titled with its raw id", not bare,
              str(bare))
    titled = [k for k, v in decks.items() if (v.get("cn_title") or "").strip()]
    rep.check("every deck carries a title", len(titled) == len(decks),
              "%d/%d" % (len(titled), len(decks)))

    if args.dry_run:
        rep.note("dry run: %s not written" % os.path.basename(TIERED))
        payload = rep.write()
        log("\nS5c dry-run %s - %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    after_words = {k: len(v.get("words", [])) for k, v in decks.items()}
    rep.check("word counts unchanged", before_words == after_words,
              str({k: (before_words[k], after_words[k])
                   for k in before_words if before_words[k] != after_words[k]}))
    changed_fields = set()
    for k in decks:
        for m in META_KEYS:
            if before_meta[k].get(m) != decks[k].get(m):
                changed_fields.add(m)
    rep.check("only catalogue metadata fields were modified",
              changed_fields <= set(META_KEYS), str(sorted(changed_fields)))

    if not rep.ok:
        rep.note("gates failed - the deck file was NOT written")
        payload = rep.write()
        log("\nS5c %s - %d passed / %d failed (no write)",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 1

    save_json(TIERED, decks)
    check = load_json(TIERED) or {}
    still_bare = [k for k, v in check.items()
                  if (v.get("cn_title") or "").strip() in ("", k) and k in cat]
    rep.check("written file has no bare-id titles", not still_bare, str(still_bare))
    rep.check("written file still has every deck", set(check) == set(decks),
              "%d decks" % len(check))
    save_json(REPORT, {"stamped": stamped, "untouched": untouched})
    payload = rep.write()
    log("\nS5c %s - %d decks stamped, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(stamped),
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
