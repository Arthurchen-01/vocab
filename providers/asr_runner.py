# -*- coding: utf-8 -*-
"""Runs INSIDE the ASR venv (which has faster-whisper); the app never imports it.

Usage: /opt/asr-venv/bin/python asr_runner.py <audio> <model> <compute> [lang]
Prints one JSON object on stdout: segments with real start/end times.
Keeping the heavy dependency in its own interpreter is deliberate - the app is
stdlib-only and shells out to yt-dlp/ffmpeg already, so ASR is just one more tool
behind a subprocess boundary.
"""
import json
import sys
import time


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: asr_runner.py <audio> [model] [compute] [lang]"}))
        return 2
    audio = sys.argv[1]
    model_size = sys.argv[2] if len(sys.argv) > 2 else "small"
    compute = sys.argv[3] if len(sys.argv) > 3 else "int8"
    lang = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": "faster_whisper import failed: %s" % exc}))
        return 3

    t0 = time.time()
    model = WhisperModel(model_size, device="cpu", compute_type=compute, cpu_threads=8)
    load_s = time.time() - t0

    t0 = time.time()
    segments, info = model.transcribe(
        audio, language=lang, vad_filter=True, beam_size=1,
        condition_on_previous_text=False)
    segs = [{"start": round(s.start, 2), "end": round(s.end, 2),
             "text": (s.text or "").strip()}
            for s in segments]
    elapsed = time.time() - t0
    duration = getattr(info, "duration", 0) or 0
    print(json.dumps({
        "model": model_size,
        "compute": compute,
        "language": getattr(info, "language", lang),
        "load_seconds": round(load_s, 1),
        "audio_seconds": round(duration, 1),
        "transcribe_seconds": round(elapsed, 1),
        "realtime_factor": round(duration / elapsed, 2) if elapsed else None,
        "segments": [s for s in segs if s["text"]],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
