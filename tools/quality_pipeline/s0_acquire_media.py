# -*- coding: utf-8 -*-
"""S0 - acquire the source media and transcript for one episode.

This is the stage that turns "a link" into everything the rest of the pipeline
needs:

    <ep>_full.mp3        full episode audio   (clips are cut from this)
    <ep>_video.mp4       video for card frames
    <ep>_transcript.json [{start, duration, text}, ...]  (ASR/subtitle segments)

Sources
-------
  * a direct URL (YouTube / Bilibili / any yt-dlp supported site), or
  * `--episode ep03` resolved through data/source_catalog.json (verified ids and
    expected durations for the known Harvard Justice episodes).

Design notes
------------
  * idempotent: existing artefacts that pass the gates are reused unless --force;
  * the transcript is either fetched from the platform's subtitles or kept if a
    usable one already exists;
  * every artefact is validated (duration, segment count, monotonic timeline) so
    a half-downloaded file can never reach the cutting stage.

Usage
-----
  python s0_acquire_media.py --episode ep03
  python s0_acquire_media.py --url "https://www.youtube.com/watch?v=..." --ep-id ep05
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (DATA_DIR, OUT_DIR, RAW_AUDIO_DIR, RAW_VIDEO_DIR, Report,  # noqa: E402
                    TRANS_DIR, load_json, log, save_json)

CATALOG = os.path.join(DATA_DIR, "source_catalog.json")
WORK = os.path.join(DATA_DIR, "_acquire")

# 480p h264 is plenty for 854x480 card frames and decodes everywhere; audio is
# re-encoded to a uniform 128k mp3 so ffmpeg cuts behave consistently.
VIDEO_FMT = "bv*[height<=480][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=480]+ba/b[height<=480]/best"
AUDIO_FMT = "bestaudio/best"


def sh(cmd, timeout=3600, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def ffprobe_duration(path):
    rc, out, _ = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "csv=p=0", path], timeout=120)
    try:
        return float(out.strip().splitlines()[0])
    except Exception:
        return None


def srt_time(t):
    t = t.replace(",", ".")
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def parse_subtitles(path):
    """SRT/VTT -> [{start, duration, text}], merging overlapping cues."""
    raw = open(path, encoding="utf-8", errors="replace").read().replace("\ufeff", "")
    raw = re.sub(r"^WEBVTT.*?$", "", raw, flags=re.M)
    cues = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [l for l in block.strip().splitlines() if l.strip()]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, _, b = lines[ti].partition("-->")
        try:
            start = srt_time(a.strip().split()[0])
            end = srt_time(b.strip().split()[0])
        except Exception:
            continue
        text = " ".join(lines[ti + 1:]).strip()
        text = re.sub(r"<[^>]+>", "", text)                    # strip karaoke tags
        text = re.sub(r"\s+", " ", text).strip()
        if text and end > start:
            cues.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    cues.sort(key=lambda c: c["start"])
    # merge duplicate/overlapping auto-subtitle lines
    merged = []
    for c in cues:
        if merged and abs(c["start"] - merged[-1]["start"]) < 0.6 and c["text"] == merged[-1]["text"]:
            merged[-1]["end"] = max(merged[-1]["end"], c["end"])
            continue
        merged.append(dict(c))
    return [{"start": c["start"], "duration": round(c["end"] - c["start"], 3), "text": c["text"]}
            for c in merged]


def transcript_ok(path, expected_span=None, min_segments=200):
    d = load_json(path)
    if not isinstance(d, list) or len(d) < min_segments:
        return False, f"only {len(d) if isinstance(d, list) else 'invalid'} segments"
    bad = [s for s in d if not isinstance(s.get("start"), (int, float))
           or not isinstance(s.get("duration"), (int, float)) or s["duration"] <= 0
           or not (s.get("text") or "").strip()]
    if bad:
        return False, f"{len(bad)} malformed segments"
    if any(d[i]["start"] > d[i + 1]["start"] for i in range(len(d) - 1)):
        return False, "timeline is not monotonic"
    span = d[-1]["start"] + d[-1]["duration"]
    if expected_span and abs(span - expected_span) > 180:
        return False, f"span {span:.0f}s vs media {expected_span:.0f}s"
    return True, f"{len(d)} segments, span {span:.0f}s"


def resolve_source(args):
    if args.url:
        return {"platform": "url", "url": args.url, "duration": None, "title": ""}
    cat = load_json(CATALOG) or {}
    for series in cat.values():
        ep = (series.get("episodes") or {}).get(args.episode)
        if ep:
            return ep
    raise SystemExit(f"episode {args.episode!r} not found in {CATALOG}; pass --url instead")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", default="", help="episode id, resolved via source_catalog.json")
    ap.add_argument("--ep-id", default="", help="output key (defaults to --episode)")
    ap.add_argument("--url", default="", help="source URL (overrides the catalog)")
    ap.add_argument("--force", action="store_true", help="re-download even if artefacts exist")
    ap.add_argument("--keep-subtitles", action="store_true")
    args = ap.parse_args()

    ep = args.ep_id or args.episode
    if not ep:
        raise SystemExit("need --episode or --ep-id")
    rep = Report(f"{ep}_s0_acquire")

    audio = os.path.join(RAW_AUDIO_DIR, f"{ep}_full.mp3")
    video = os.path.join(RAW_VIDEO_DIR, f"{ep}_video.mp4")
    transcript = os.path.join(TRANS_DIR, f"{ep}_transcript.json")
    os.makedirs(RAW_AUDIO_DIR, exist_ok=True)
    os.makedirs(RAW_VIDEO_DIR, exist_ok=True)
    os.makedirs(TRANS_DIR, exist_ok=True)
    os.makedirs(WORK, exist_ok=True)

    src = resolve_source(args)
    expected = src.get("duration") or None
    rep.check("source resolved", bool(src.get("url")), f"{src.get('url','')[:90]}")
    rep.note(f"expected duration: {expected}s" if expected else "expected duration: unknown")

    # ---------- metadata (also verifies the link is reachable) ----------
    meta = {}
    rc, out, err = sh(["yt-dlp", "--no-warnings", "--skip-download",
                       "--print", "%(id)s\u0001%(duration)s\u0001%(title)s\u0001%(extractor)s",
                       src["url"]], timeout=300)
    if rc == 0 and out.strip():
        parts = out.strip().splitlines()[0].split("\u0001")
        meta = {"id": parts[0], "duration": float(parts[1] or 0) if len(parts) > 1 else None,
                "title": parts[2] if len(parts) > 2 else "", "extractor": parts[3] if len(parts) > 3 else ""}
        rep.check("metadata fetched from the source", True,
                  f"{meta.get('extractor')} · {meta.get('title','')[:60]} · {meta.get('duration')}s")
        if expected and meta.get("duration"):
            rep.check("source duration matches the catalog",
                      abs(meta["duration"] - expected) < 60,
                      f"source={meta['duration']:.0f}s catalog={expected}s")
    else:
        rep.check("metadata fetched from the source", False, err.strip().splitlines()[-1][:160] if err else "yt-dlp failed")
    media_dur = meta.get("duration") or expected

    # ---------- audio ----------
    need_audio = args.force or not os.path.isfile(audio)
    if not need_audio:
        d = ffprobe_duration(audio)
        need_audio = d is None or (media_dur and abs(d - media_dur) > 60)
        rep.note(f"existing audio kept ({d:.0f}s)" if not need_audio else f"existing audio unusable ({d})")
    if need_audio:
        rc, out, err = sh(["yt-dlp", "--no-warnings", "-f", AUDIO_FMT, "-x", "--audio-format", "mp3",
                           "--audio-quality", "128K", "--postprocessor-args", "-ac 1",
                           "-o", os.path.join(WORK, f"{ep}_audio.%(ext)s"), src["url"]], timeout=3600)
        produced = os.path.join(WORK, f"{ep}_audio.mp3")
        if rc == 0 and os.path.isfile(produced):
            os.replace(produced, audio)
        else:
            rep.check("audio downloaded", False, (err or out).strip().splitlines()[-1][:200] if (err or out) else "no output")
    adur = ffprobe_duration(audio) if os.path.isfile(audio) else None
    rep.check("audio present and probeable", bool(adur), f"{audio} ({adur:.0f}s)" if adur else audio)

    # ---------- video (for frames) ----------
    need_video = args.force or not os.path.isfile(video)
    if not need_video:
        d = ffprobe_duration(video)
        need_video = d is None or (media_dur and abs(d - media_dur) > 60)
    if need_video:
        rc, out, err = sh(["yt-dlp", "--no-warnings", "-f", VIDEO_FMT, "--merge-output-format", "mp4",
                           "-o", os.path.join(WORK, f"{ep}_video.%(ext)s"), src["url"]], timeout=5400)
        produced = os.path.join(WORK, f"{ep}_video.mp4")
        if rc == 0 and os.path.isfile(produced):
            os.replace(produced, video)
        else:
            rep.check("video downloaded", False, (err or out).strip().splitlines()[-1][:200] if (err or out) else "no output")
    vdur = ffprobe_duration(video) if os.path.isfile(video) else None
    rep.check("video present and probeable", bool(vdur), f"{video} ({vdur:.0f}s)" if vdur else video)
    if adur and vdur:
        rep.check("audio and video durations agree", abs(adur - vdur) < 5, f"{adur:.1f}s vs {vdur:.1f}s")

    # ---------- transcript ----------
    ok, why = (False, "missing")
    if os.path.isfile(transcript) and not args.force:
        ok, why = transcript_ok(transcript, vdur or adur)
    if ok:
        rep.check("transcript acquired", True, f"reused existing: {why}")
    else:
        rep.note(f"existing transcript unusable ({why}) -> fetching subtitles")
        subdir = os.path.join(WORK, "subs")
        os.makedirs(subdir, exist_ok=True)
        rc, out, err = sh(["yt-dlp", "--no-warnings", "--skip-download", "--write-auto-subs",
                           "--write-subs", "--sub-langs", "en.*,en", "--sub-format", "srt",
                           "--convert-subs", "srt", "-o", os.path.join(subdir, f"{ep}.%(ext)s"),
                           src["url"]], timeout=900)
        cand = [os.path.join(subdir, f) for f in os.listdir(subdir) if f.endswith(".srt")]
        if cand:
            best = max(cand, key=os.path.getsize)
            segs = parse_subtitles(best)
            if len(segs) >= 200:
                save_json(transcript, segs)
            else:
                rep.check("subtitles parsed into segments", False, f"only {len(segs)} cues from {os.path.basename(best)}")
            if not args.keep_subtitles:
                for f in cand:
                    os.remove(f)
        else:
            rep.check("subtitles fetched", False, (err or out).strip().splitlines()[-1][:200] if (err or out) else "no subtitle files")
        if os.path.isfile(transcript):
            ok, why = transcript_ok(transcript, vdur or adur)
            rep.check("transcript acquired", ok, why)

    # ---------- final gates ----------
    if adur and os.path.isfile(transcript):
        ok, why = transcript_ok(transcript, adur)
        rep.check("transcript covers the media", ok, why)

    save_json(os.path.join(OUT_DIR, f"{ep}_source.json"),
              {"episode": ep, "source": src, "meta": meta,
               "audio": audio, "video": video, "transcript": transcript,
               "audio_duration": adur, "video_duration": vdur})
    rep.note(f"artifacts: {audio} | {video} | {transcript}")
    payload = rep.write()
    log("\nS0 %s - %s, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", ep, payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
