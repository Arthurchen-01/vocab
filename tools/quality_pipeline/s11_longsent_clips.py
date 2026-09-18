# -*- coding: utf-8 -*-
"""S11 - cut real lecture audio for the long-sentence deck.

The long-sentence cards point at their own lecture span (`audio_start`/`audio_end`
from S1), so the app can replay the sentence in Sandel's actual voice instead of
a synthetic one. Without this the cards advertise `/assets/audio/clips/...` files
that do not exist and the play button fails silently.

Gates: one clip per card, real duration within tolerance of the planned span,
no clip running past the end of the source audio.

Usage: python s11_cut_longsent_clips.py [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (AUDIO_CLIP_DIR, DATA_DIR, RAW_AUDIO_DIR, Report,  # noqa: E402
                    load_json, log, save_json)

DECKS = os.path.join(DATA_DIR, "longsent_decks.json")
DECK_ID = "hj_longsent"
PAD_HEAD = 0.15
PAD_TAIL = 0.25
TOLERANCE = 0.35


def safe_name(word):
    return re.sub(r"[^a-z0-9_]", "_", (word or "").lower()).strip("_")


def probe(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rep = Report("s11_longsent_clips")
    decks = load_json(DECKS) or {}
    deck = decks.get(DECK_ID)
    if not deck:
        rep.check("long-sentence deck present", False, DECKS)
        rep.write()
        return 1
    cards = deck.get("words", [])
    rep.check("long-sentence deck present", True, "%d cards" % len(cards))
    os.makedirs(AUDIO_CLIP_DIR, exist_ok=True)

    sources = {}
    for ep in sorted({c.get("sentence_source", "") for c in cards}):
        ep_id = (ep or "").split(":")[-1]
        path = os.path.join(RAW_AUDIO_DIR, "%s_full.mp3" % ep_id)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            sources[ep_id] = path
    rep.check("source lecture audio available", bool(sources),
              ", ".join("%s=%.1f MB" % (k, os.path.getsize(v) / 1e6)
                        for k, v in sorted(sources.items())))

    cut, skipped, bad = 0, [], []
    for c in cards:
        ep_id = (c.get("sentence_source") or "").split(":")[-1]
        src = sources.get(ep_id)
        start, end = c.get("audio_start"), c.get("audio_end")
        if not src or not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            skipped.append((c.get("word"), "no source" if not src else "no span"))
            continue
        name = "%s_%s_native.mp3" % (DECK_ID, safe_name(c.get("word")))
        dest = os.path.join(AUDIO_CLIP_DIR, name)
        if args.dry_run:
            cut += 1
            continue
        ss = max(0.0, start - PAD_HEAD)
        duration = (end - start) + PAD_HEAD + PAD_TAIL
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", "%.3f" % ss, "-t", "%.3f" % duration,
             "-i", src, "-acodec", "libmp3lame", "-q:a", "5", dest],
            capture_output=True, text=True, timeout=180)
        if proc.returncode != 0 or not os.path.exists(dest):
            bad.append((c.get("word"), proc.stderr.strip()[:80]))
            continue
        got = probe(dest)
        if got and abs(got - duration) > TOLERANCE:
            bad.append((c.get("word"), "duration %.2fs vs planned %.2fs" % (got, duration)))
            os.remove(dest)
            continue
        c["native_clip_url"] = "/assets/audio/clips/%s" % name
        cut += 1

    rep.check("a clip was produced for every card with a lecture span",
              not bad, "%d cut, %d skipped, %d failed %s"
              % (cut, len(skipped), len(bad), bad[:4]))
    rep.check("every clip duration matches its planned span", not bad,
              "%d mismatches" % len(bad))
    if skipped:
        rep.note("%d cards had no usable span: %s" % (len(skipped), skipped[:4]))

    if not args.dry_run and cut:
        save_json(DECKS, decks)
        again = (load_json(DECKS) or {}).get(DECK_ID, {}).get("words", [])
        with_clip = sum(1 for w in again if w.get("native_clip_url"))
        rep.check("written deck references one clip per card",
                  with_clip == len(cards),
                  "%d/%d cards carry native_clip_url" % (with_clip, len(cards)))
    if args.dry_run:
        rep.note("dry run: no clip written")

    payload = rep.write()
    log("\nS11 %s - %d clips, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", cut, payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
