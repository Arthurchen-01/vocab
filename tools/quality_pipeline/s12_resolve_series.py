# -*- coding: utf-8 -*-
"""S12 - resolve and verify the remaining Harvard Justice episodes (05..12).

The catalog only carried ep01-ep04, which is why the series could not simply be
run. Rather than guessing ids, ask yt-dlp and then VERIFY the match:

  * the result must come from the official `Harvard University` channel
  * the title must name the same episode number
  * the duration must be a full lecture (50-58 min), like ep01-ep04

Anything that fails verification is reported, not silently written.

Usage: python s12_resolve_series.py [--episodes 05,06,...] [--dry-run] [--write]
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, Report, load_json, log, save_json  # noqa: E402

CATALOG = os.path.join(DATA_DIR, "source_catalog.json")
SERIES = "harvard_justice"
OFFICIAL_CHANNEL = "harvard university"
MIN_DURATION, MAX_DURATION = 3000, 3480      # ep01..ep04 measured 3296..3310
SEARCH = ("ytsearch8:Justice What's The Right Thing To Do Episode %s "
          "Harvard University Sandel")
CN_TITLES = {
    "05": "第 05 集：雇凶杀人 / 出售母职",
    "06": "第 06 集：注意你的动机 / 康德的绝对命令",
    "07": "第 07 集：谎言的教训 / 约定就是约定",
    "08": "第 08 集：什么是公平的起点 / 罗尔斯的无知之幕",
    "09": "第 09 集：平权行动的辩论 / 目的何在",
    "10": "第 10 集：好公民 / 亚里士多德的目的论",
    "11": "第 11 集：忠诚的边界 / 我们的忠诚何在",
    "12": "第 12 集：同性婚姻的辩论 / 美好生活",
}


def ytdlp(args, timeout=300):
    try:
        out = subprocess.run(["yt-dlp", "--no-warnings"] + args,
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip().splitlines()
    except Exception as exc:  # noqa: BLE001
        log("  yt-dlp failed: %s", exc)
        return []


def resolve(number):
    """Verified (video_id, title, duration) for one episode, or None."""
    lines = ytdlp(["--flat-playlist",
                   "--print", "%(id)s|%(duration)s|%(channel)s|%(title)s",
                   SEARCH % number], timeout=420)
    for line in lines:
        parts = line.split("|")
        if len(parts) < 4:
            continue
        vid, dur, channel, title = parts[0], parts[1], parts[2], "|".join(parts[3:])
        try:
            duration = int(float(dur))
        except ValueError:
            continue
        if OFFICIAL_CHANNEL not in channel.lower():
            continue
        if not re.search(r"episode\s*0?%d\b" % int(number), title, re.I):
            continue
        if not (MIN_DURATION <= duration <= MAX_DURATION):
            continue
        return vid, title, duration
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", default="05,06,07,08,09,10,11,12")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rep = Report("s12_resolve_series")
    cat = load_json(CATALOG) or {}
    series = cat.get(SERIES) or {}
    eps = series.get("episodes") or {}
    rep.check("catalog readable", bool(eps), "%d episodes already catalogued" % len(eps))

    wanted = [n.strip() for n in args.episodes.split(",") if n.strip()]
    found, missing = {}, []
    for number in wanted:
        hit = resolve(number)
        if not hit:
            missing.append(number)
            log("  ep%s: no verified official match" % number)
            continue
        vid, title, duration = hit
        # Never overwrite a catalogued episode with a different video.
        key = "ep%s" % number
        if key in eps and eps[key].get("video_id") != vid:
            log("  ep%s: catalog already points at %s (search said %s) - keeping catalog"
                % (number, eps[key].get("video_id"), vid))
            found[key] = dict(eps[key])
            continue
        found[key] = {
            "url": "https://www.youtube.com/watch?v=%s" % vid,
            "video_id": vid,
            "duration": duration,
            "title": title,
            "cn_title": CN_TITLES.get(number, "第 %s 集" % number),
        }
        log("  ep%s -> %s  %ds  %s", number, vid, duration, title[:66])

    rep.check("every requested episode resolved from the official channel",
              not missing, "unresolved: %s" % missing if missing else
              "%d episodes" % len(found))
    ids = [v["video_id"] for v in found.values()]
    rep.check("no duplicate video ids", len(ids) == len(set(ids)), "%d ids" % len(ids))
    bad = [k for k, v in found.items() if not (MIN_DURATION <= v.get("duration", 0) <= MAX_DURATION)]
    rep.check("every duration is a full-length lecture", not bad,
              str(bad) if bad else "%d..%d s" % (min(v["duration"] for v in found.values()),
                                                 max(v["duration"] for v in found.values())))

    if args.dry_run or not args.write:
        rep.note("not written (pass --write)")
        payload = rep.write()
        log("\nS12 %s - %d resolved, %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", len(found),
            payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    merged = dict(eps)
    merged.update(found)
    series["episodes"] = dict(sorted(merged.items()))
    cat[SERIES] = series
    save_json(CATALOG, cat)
    rep.check("catalog written", os.path.exists(CATALOG),
              "%d episodes total" % len(series["episodes"]))
    payload = rep.write()
    log("\nS12 %s - catalog now holds %d episodes",
        "PASS" if payload["ok"] else "FAIL", len(series["episodes"]))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
