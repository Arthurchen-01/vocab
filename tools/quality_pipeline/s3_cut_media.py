# -*- coding: utf-8 -*-
"""S3 - re-cut every Ep02 native clip on its sentence's true boundaries, and
re-extract the card frames.

Old behaviour: the clip was the ASR chunk covering the word's timestamp, so the
audio started and stopped in the middle of the spoken sentence. New behaviour:
the clip is exactly [sentence.start - pad, sentence.end + pad], i.e. the sentence
is covered head to tail (plus a small pad so no phoneme is clipped).

Requires ffmpeg/ffprobe and the raw episode media. On the production host the raw
media lives in data/raw_audio/ and data/raw_video/.

Output: out/<ep>_media_report.json  (+ rewritten clip/frame files in public/)
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (AUDIO_CLIP_DIR, AUDIO_DIR, CLIP_PAD_HEAD, CLIP_PAD_TAIL, DATA_DIR,  # noqa: E402
                    EPISODE, OUT_DIR, PUBLIC_DIR, RAW_AUDIO_DIR, RAW_VIDEO_DIR,
                    Report, SCENE_DIR, WORK_DIR, fmt_ts, load_deck_words, load_json,
                    log, safe_name, save_json)

WORK_ORPHANS = os.path.join(WORK_DIR, "orphans")

SENTS_FILE = os.path.join(OUT_DIR, f"{EPISODE}_sentences.json")
MAP_FILE = os.path.join(OUT_DIR, f"{EPISODE}_word_map.json")
CURRICULUM = os.path.join(DATA_DIR, f"{EPISODE}_curriculum_final_audited.json")
REPORT_FILE = os.path.join(OUT_DIR, f"{EPISODE}_media_report.json")

RAW_AUDIO = os.path.join(RAW_AUDIO_DIR, f"{EPISODE}_full.mp3")
RAW_VIDEO = os.path.join(RAW_VIDEO_DIR, f"{EPISODE}_video.mp4")
TMP_DIR = os.path.join(OUT_DIR, "_clips_tmp")


def run(cmd, timeout=300):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:3])}... failed: {p.stderr.strip()[:300]}")
    return p.stdout


def probe_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path], timeout=60)
    try:
        return float(out.strip().splitlines()[0])
    except Exception:
        return None


def cut_audio(src, start, end, dst):
    dur = max(0.2, end - start)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
         "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "1",
         "-map_metadata", "-1", dst], timeout=180)


def cut_frame(src, t, dst):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1", "-q:v", "3",
         "-vf", "scale=854:-2", dst], timeout=180)


def ensure_word_tts(words, rep):
    """Every card needs its own pronunciation file (<ep>_<word>.mp3).

    When a deck is rebuilt the word list changes, so the per-word TTS of the new
    words does not exist yet - the card would offer a play button that 404s.
    """
    import asyncio

    try:
        import edge_tts
    except Exception as e:  # noqa: BLE001
        rep.check("edge-tts available for word pronunciation", False, str(e)[:120])
        return

    os.makedirs(AUDIO_DIR, exist_ok=True)
    missing, made, failed = [], 0, []
    for w in words:
        path = os.path.join(AUDIO_DIR, f"{EPISODE}_{safe_name(w['word'])}.mp3")
        if os.path.isfile(path) and os.path.getsize(path) > 2000:
            continue
        missing.append(w["word"])
        try:
            asyncio.run(edge_tts.Communicate(w["word"], "en-US-ChristopherNeural").save(path))
            if os.path.isfile(path) and os.path.getsize(path) > 2000:
                made += 1
            else:
                failed.append(w["word"])
        except Exception as e:  # noqa: BLE001
            failed.append(f"{w['word']}:{type(e).__name__}")
    rep.check("every card has its own pronunciation clip", not failed,
              f"{made} generated, {len(failed)} failed {failed[:5]}")
    if made:
        rep.note(f"generated {made} word-pronunciation files (were missing: {len(missing)})")

    # retire pronunciation files whose word left the episode
    keep = {f"{EPISODE}_{safe_name(w['word'])}.mp3" for w in words}
    orphans = []
    if os.path.isdir(AUDIO_DIR):
        for f in os.listdir(AUDIO_DIR):
            if f.startswith(f"{EPISODE}_") and f.endswith(".mp3") and f not in keep:
                orphans.append(f)
    if orphans:
        odir = os.path.join(WORK_ORPHANS, EPISODE)
        os.makedirs(odir, exist_ok=True)
        for f in orphans:
            os.replace(os.path.join(AUDIO_DIR, f), os.path.join(odir, f))
        rep.note(f"retired {len(orphans)} orphan pronunciation files -> {odir}")


def main():
    rep = Report(f"{EPISODE}_s3_media")
    sents = load_json(SENTS_FILE)
    wmap = load_json(MAP_FILE)
    words, deck_kind = load_deck_words(EPISODE)
    if not (sents and wmap and words):
        rep.check("inputs present", False,
                  f"sentences={bool(sents)} map={bool(wmap)} deck_words={len(words)} ({deck_kind})")
        rep.write()
        return 1
    rep.check("inputs present", True,
              f"{len(sents)} sentences, {len(wmap['words'])} mapped words (deck: {deck_kind})")

    rep.check("raw episode audio present", os.path.isfile(RAW_AUDIO), RAW_AUDIO)
    if not os.path.isfile(RAW_AUDIO):
        rep.write()
        return 1
    audio_dur = probe_duration(RAW_AUDIO) or 0
    rep.check("raw audio is long enough for every window",
              all(s["end"] + CLIP_PAD_TAIL <= audio_dur + 0.5 for s in sents),
              f"audio={audio_dur:.1f}s, last sentence ends at {sents[-1]['end']:.1f}s")
    has_video = os.path.isfile(RAW_VIDEO)
    rep.note(f"raw video present: {has_video} ({RAW_VIDEO})")

    os.makedirs(TMP_DIR, exist_ok=True)
    os.makedirs(AUDIO_CLIP_DIR, exist_ok=True)
    scene_dir = os.path.join(SCENE_DIR, EPISODE)
    os.makedirs(scene_dir, exist_ok=True)

    sent_by_id = {s["sent_id"]: s for s in sents}
    by_word = {w["word"]: next((m for m in wmap["words"] if m["word"] == w["word"]), None) for w in words}

    # ---- 1. one clip per distinct sentence --------------------------
    used_ids = sorted({m["sent_id"] for m in wmap["words"] if m})
    clip_of = {}
    cut_fail = []
    for sid in used_ids:
        s = sent_by_id[sid]
        start = max(0.0, s["start"] - CLIP_PAD_HEAD)
        end = min(audio_dur, s["end"] + CLIP_PAD_TAIL)
        dst = os.path.join(TMP_DIR, f"{EPISODE}_sent{sid:04d}_native.mp3")
        try:
            cut_audio(RAW_AUDIO, start, end, dst)
            d = probe_duration(dst) or 0
            if abs(d - (end - start)) > 0.30:
                cut_fail.append((sid, round(end - start, 2), round(d, 2)))
            clip_of[sid] = (dst, start, end)
        except Exception as e:  # noqa: BLE001
            cut_fail.append((sid, "cut-error", str(e)[:120]))
    rep.check("every used sentence produced a clip", not cut_fail,
              f"{len(clip_of)}/{len(used_ids)} clips; problems: {cut_fail[:5]}")

    # ---- 2. fan the sentence clip out to each word's filename -------
    frame_fail = []
    audio_fail = []
    for w in words:
        m = by_word.get(w["word"])
        if not m:
            audio_fail.append((w["word"], "unmapped"))
            continue
        sid = m["sent_id"]
        s = sent_by_id[sid]
        safe = safe_name(w["word"])
        dst = os.path.join(AUDIO_CLIP_DIR, f"{EPISODE}_{safe}_native.mp3")
        try:
            shutil.copyfile(clip_of[sid][0], dst)
        except Exception as e:  # noqa: BLE001
            audio_fail.append((w["word"], str(e)[:80]))
            continue
        # frame at the moment the word is actually spoken
        if has_video:
            try:
                cut_frame(RAW_VIDEO, float(m.get("audio_start") or s["start"]) + 0.2,
                          os.path.join(scene_dir, f"frame_{safe}.jpg"))
            except Exception as e:  # noqa: BLE001
                frame_fail.append((w["word"], str(e)[:80]))
    rep.check("all 215 clips written", not audio_fail, f"{len(words) - len(audio_fail)}/{len(words)}; {audio_fail[:5]}")
    if has_video:
        rep.check("all 215 frames re-extracted", not frame_fail,
                  f"{len(words) - len(frame_fail)}/{len(words)}; {frame_fail[:5]}")

    # ---- 3. verify on disk -----------------------------------------
    bad_dur, tiny, missing = [], [], []
    for w in words:
        m = by_word.get(w["word"])
        if not m:
            continue
        s = sent_by_id[m["sent_id"]]
        p = os.path.join(AUDIO_CLIP_DIR, f"{EPISODE}_{safe_name(w['word'])}_native.mp3")
        if not os.path.isfile(p):
            missing.append(w["word"])
            continue
        if os.path.getsize(p) < 4096:
            tiny.append((w["word"], os.path.getsize(p)))
        d = probe_duration(p) or 0
        want = min(audio_dur, s["end"] + CLIP_PAD_TAIL) - max(0.0, s["start"] - CLIP_PAD_HEAD)
        if abs(d - want) > 0.30:
            bad_dur.append((w["word"], round(want, 2), round(d, 2)))
    rep.check("no clip file missing", not missing, str(missing[:6]))
    rep.check("no suspiciously small clip", not tiny, str(tiny[:6]))
    rep.check("clip duration matches the sentence window", not bad_dur,
              f"{len(words) - len(bad_dur)}/{len(words)} within 0.30s; {bad_dur[:5]}")

    frame_missing = [w["word"] for w in words
                     if not os.path.isfile(os.path.join(scene_dir, f"frame_{safe_name(w['word'])}.jpg"))]
    if has_video:
        rep.check("no frame file missing", not frame_missing, str(frame_missing[:6]))

    # ---- 3b. per-word pronunciation (TTS) ----
    ensure_word_tts(words, rep)

    # ---- 4. before/after alignment metric --------------------------
    old_mid = []
    for w in words:
        m = by_word.get(w["word"])
        if not m:
            continue
        s = sent_by_id[m["sent_id"]]
        old_s, old_e = float(w.get("audio_start") or 0), float(w.get("audio_end") or 0)
        head_gap = s["start"] - old_s        # >0 => old clip started inside the sentence
        tail_gap = s["end"] - old_e          # >0 => old clip ended inside the sentence
        if head_gap > 0.75 or tail_gap > 0.75 or head_gap < -0.75 or tail_gap < -0.75:
            old_mid.append({"word": w["word"], "old": [round(old_s, 2), round(old_e, 2)],
                            "new": [round(s["start"], 2), round(s["end"], 2)],
                            "head_gap_s": round(head_gap, 2), "tail_gap_s": round(tail_gap, 2)})
    rep.note(f"clips whose old window did NOT match the spoken sentence: "
             f"{len(old_mid)}/{len(words)} ({100 * len(old_mid) / len(words):.0f}%)")

    save_json(REPORT_FILE, {
        "episode": EPISODE, "clips_cut": len(clip_of), "words": len(words),
        "raw_audio": RAW_AUDIO, "pad_head": CLIP_PAD_HEAD, "pad_tail": CLIP_PAD_TAIL,
        "old_window_mismatch_count": len(old_mid),
        "old_window_mismatch_examples": old_mid[:25],
    })
    rep.note(f"wrote {REPORT_FILE}")
    payload = rep.write()
    log("\nS3 %s - %d clips, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(clip_of), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
