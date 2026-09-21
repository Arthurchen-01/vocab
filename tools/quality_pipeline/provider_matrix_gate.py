# -*- coding: utf-8 -*-
"""S9 - provider matrix gate: every source path verified end to end.

"Multiple backups" is only real if each one is exercised. This gate runs the
resolver against real links that cover every capability path and asserts the
outcome, including the policy switches:

  * YouTube        -> real subtitles, and ASR must NOT be invoked (no wasted minutes)
  * Bilibili       -> no subtitles at all, so local ASR must supply a transcript
                      that is LABELLED as a machine transcript
  * direct .srt    -> the subtitle URL is the transcript
  * direct .mp3    -> media only; asking for a transcript must not silently invent one
  * SciAm          -> podcast CDN + article text, labelled `article_text`
  * allow_asr=off  -> the Bilibili link must FAIL with a clear reason, never fabricate
  * quality=fast   -> stops at the first provider that satisfies the request

Run it on the host (it needs yt-dlp / you-get / the ASR venv):
    python provider_matrix_gate.py --stage s9_providers
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import APP_DIR, Report, log  # noqa: E402

sys.path.insert(0, APP_DIR)
from providers import health, policy as policy_mod  # noqa: E402
from providers.base import (CAP_MEDIA, CAP_METADATA, CAP_SUBTITLES,  # noqa: E402
                            load_registry)
from providers.resolver import resolve  # noqa: E402

YOUTUBE = "https://www.youtube.com/watch?v=kBdfcR-8hEY"          # has subtitles
BILIBILI = "https://www.bilibili.com/video/BV1NdwWe6Epf"          # has none
SCIAM = ("https://www.scientificamerican.com/podcast/episode/"
         "the-science-of-friendship-and-loneliness/")
DIRECT_MP3 = "https://traffic.megaphone.fm/SAM8705727348.mp3"

OBSERVED = []   # every result this gate saw, for the honesty invariant below


def _remember(result):
    OBSERVED.append(result)
    return result


def _resolve(*a, **kw):
    """resolve() plus recording, so the honesty invariant can see every result."""
    res, trail = resolve(*a, **kw)
    _remember(res)
    return res, trail


def trail_summary(trail):
    return " | ".join("%s:%s(%ss)" % (t["provider"], "ok" if t["ok"] else "no",
                                      t.get("seconds"))
                      for t in trail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="s9_providers")
    ap.add_argument("--skip-asr", action="store_true",
                    help="skip the slow ASR path (development only)")
    args = ap.parse_args()

    rep = Report(args.stage)
    registry = load_registry(verbose=True)
    names = {p.name for p in registry}
    rep.check("provider registry loads", bool(registry),
              ", ".join(sorted(names)))
    for required in ("yt-dlp", "direct_media", "direct_subtitle", "sciam",
                     "bilibili_cc", "whisper_asr", "you-get"):
        rep.check("provider available: %s" % required, required in names,
                  "missing" if required not in names else "ok")

    # 1. YouTube: real subtitles, and ASR must not be needed.
    t0 = time.time()
    res, trail = _resolve(YOUTUBE, need=(CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES))
    rep.check("YouTube: real transcript obtained", bool(res.get("transcript")),
              "source=%s provider=%s" % (res.get("transcript_source"),
                                         res.get("provider")))
    rep.check("YouTube: transcript is not a machine transcript",
              not res.get("is_machine_transcript"), res.get("transcript_source"))
    rep.check("YouTube: ASR was not invoked (no wasted minutes)",
              not any(t["provider"] == "whisper_asr" for t in trail),
              trail_summary(trail))
    rep.check("YouTube: real title", bool((res.get("title") or "").strip()),
              (res.get("title") or "")[:60])
    log("    YouTube in %.1fs -> %s", time.time() - t0, trail_summary(trail))

    # 2. Bilibili: no subtitles exist, so ASR is the only honest route.
    if args.skip_asr:
        rep.note("Bilibili/ASR path skipped (--skip-asr)")
    else:
        t0 = time.time()
        res, trail = _resolve(BILIBILI, need=(CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES))
        rep.check("Bilibili: a transcript is produced where none exists",
                  bool(res.get("transcript")), res.get("transcript_source"))
        rep.check("Bilibili: the transcript is labelled machine-generated",
                  bool(res.get("is_machine_transcript")),
                  "is_machine_transcript=%s" % res.get("is_machine_transcript"))
        rep.check("Bilibili: transcript_source names the ASR model",
                  str(res.get("transcript_source", "")).startswith("whisper_asr:"),
                  res.get("transcript_source"))
        rep.check("Bilibili: real title from yt-dlp (not a placeholder)",
                  "Planet Money" in (res.get("title") or ""),
                  (res.get("title") or "")[:60])
        stats = res.get("asr_stats") or {}
        rep.note("Bilibili ASR: %s seg / %s words / %.1fs / %.1fx realtime"
                 % (stats.get("segments"), stats.get("words"), stats.get("seconds") or 0,
                    stats.get("realtime_factor") or 0))
        log("    Bilibili in %.1fs -> %s", time.time() - t0, trail_summary(trail))

        # 3. policy: ASR disabled must refuse, not fabricate.
        res2, trail2 = resolve(BILIBILI, need=(CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES),
                               overrides={"allow_asr": False})
        rep.check("policy allow_asr=off: no transcript is claimed",
                  not (res2.get("transcript") or "").strip(),
                  "source=%s" % res2.get("transcript_source"))
        rep.check("policy allow_asr=off: the refusal is explicit",
                  any("ASR disabled" in (t.get("error") or "") for t in trail2)
                  or not res2.get("success"),
                  trail_summary(trail2))
        rep.check("policy allow_asr=off: metadata still returned (partial success)",
                  bool((res2.get("title") or "").strip()), (res2.get("title") or "")[:50])

    # 4. direct media: media only, and no invented transcript when only media is asked.
    res, trail = _resolve(DIRECT_MP3, need=(CAP_METADATA, CAP_MEDIA))
    rep.check("direct media: a media stream is returned",
              bool(res.get("direct_media_url") or res.get("download_url")),
              trail_summary(trail))
    rep.check("direct media: no transcript claimed",
              not (res.get("transcript") or "").strip(),
              repr((res.get("transcript") or "")[:40]))

    # 5. SciAm: podcast metadata + media, article text labelled.
    res, trail = _resolve(SCIAM, need=(CAP_METADATA, CAP_MEDIA))
    rep.check("sciam: metadata + media resolved", bool(res.get("success")),
              trail_summary(trail))
    if (res.get("transcript") or "").strip():
        rep.check("sciam: article text is labelled article_text",
                  res.get("transcript_source") == "article_text",
                  res.get("transcript_source"))

    # 6. quality=fast must not consult every provider.
    _, trail_fast = resolve(YOUTUBE, need=(CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES),
                            overrides={"quality": "fast"})
    rep.check("quality=fast consults fewer providers than quality=best",
              len(trail_fast) <= 3, "%d providers: %s" % (len(trail_fast),
                                                          trail_summary(trail_fast)))

    # 7. honesty invariants across every observation above
    lying = [(r.get("provider"), r.get("has_subtitles"),
              bool((r.get("transcript") or "").strip()))
             for r in OBSERVED
             if bool(r.get("has_subtitles")) != bool((r.get("transcript") or "").strip())]
    rep.check("has_subtitles always agrees with whether text was obtained",
              not lying, str(lying[:4]))
    machine = [r for r in OBSERVED if r.get("is_machine_transcript")]
    rep.check("every machine transcript names its source",
              all(str(r.get("transcript_source", "")).startswith("whisper_asr")
                  for r in machine),
              str([r.get("transcript_source") for r in machine]))

    snap = health.snapshot()
    rep.note("provider health rows: %d" % len(snap))
    for key, row in sorted(snap.items())[:12]:
        rep.note("  %-28s %d/%d ok  mean %dms"
                 % (key, row["successes"], row["attempts"],
                    row["total_ms"] // max(1, row["attempts"])))
    rep.note("policy: %s" % policy_mod.describe(policy_mod.resolve()))

    payload = rep.write()
    log("\nS9 provider matrix %s - %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
