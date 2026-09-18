# -*- coding: utf-8 -*-
"""S8 - anti-fabrication gate.

The project has twice shipped invented study material:

  * the original Ep03 deck (24 of 44 words never occur in the lecture, with
    evenly-spaced invented timestamps);
  * every link import, because `downloader.py` answered with canned "transcripts"
    such as "[01:15] Suppose you're the driver of a trolley car hurtling down the
    track..." and always reported has_subtitles=True. `/api/import/link` never
    fetched anything at all, so a link-only import *always* produced a deck
    extracted from text nobody ever said.

Both were invisible to every other gate: the JSON was well-formed, the fields
were populated, and the output looked exactly like the real thing. So this stage
checks the *behaviour*, not the shape:

A. static scan - no code path may hand a string literal to a `transcript` field,
   and the phrases that were removed must not come back.
B. live probe (optional, needs --base) - link imports and batch resolution must
   never return a transcript that is not accompanied by has_subtitles=True and a
   transcript_source, and an import that cannot obtain real subtitles must fail
   loudly instead of silently producing an episode.

Usage:
    python no_fabrication_gate.py --app /var/www/harvard_justice_app
    python no_fabrication_gate.py --base http://127.0.0.1:8765
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import APP_DIR, Report, log  # noqa: E402

# Sentences that were deleted from the codebase. Their return means the
# fabrication came back.
BANNED_PHRASES = [
    "Suppose you're the driver of a trolley car hurtling down the track",
    "Welcome to this special seminar on moral theory and utilitarianism",
    "In our seminar today, we address the fundamental conflict",
    "Direct audio stream imported from web resource",
    "课堂原声英文字幕逐字稿同步挂载就绪",
    "Ready for high-definition playback and AI vocabulary analysis",
    "Welcome to Science Quickly from Scientific American",
]

# A transcript field assigned a literal (optionally f-string) is fabrication:
# real transcripts always come from a variable holding fetched text.
LITERAL_TRANSCRIPT = re.compile(
    r'["\']transcript["\']\s*:\s*f?["\'][^"\']{12,}', re.S)


def scan_file(path, rep, allowed_demo=False):
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
    except OSError as exc:
        rep.check("read %s" % name, False, str(exc))
        return
    hits = [p for p in BANNED_PHRASES if p in src]
    # Comments explaining the history are fine; live code is not.
    code_lines = [ln for ln in src.splitlines()
                  if not ln.lstrip().startswith("#")]
    code = "\n".join(code_lines)
    live_hits = [p for p in hits if p in code]
    rep.check("%s: no fabricated transcript sentence in live code" % name,
              not live_hits, str(live_hits))
    lit = LITERAL_TRANSCRIPT.findall(code)
    if allowed_demo:
        code = re.sub(r'["\']demo_transcript["\']\s*:\s*f?["\'][^"\']*', "", code, flags=re.S)
        lit = LITERAL_TRANSCRIPT.findall(code)
    rep.check("%s: no string literal assigned to a transcript field" % name,
              not lit, str(lit[:3]))


def http(method, base, path, payload=None, timeout=180, attempts=3):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = None
    for i in range(attempts):
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "anti-fabrication"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5)
    return 0, ("network error: %s" % last).encode("utf-8")


def probe(base, rep):
    # Deliberately a tiny, unrecognised URL: it exercises the "no real text can
    # be obtained" path without triggering a multi-megabyte media download.
    opaque = "https://example.com/not-a-media-page.html"

    # 1. Resolution of a source with no text at all must not claim subtitles.
    st, body = http("POST", base, "/api/media/batch-extract", {
        "urls": [opaque],
        "mode": "media", "media_type": "audio", "auto_expand": False}, timeout=60)
    items = []
    try:
        items = json.loads(body.decode("utf-8")).get("items", [])
    except Exception:  # noqa: BLE001
        pass
    invented = [it for it in items
                if any(p in (it.get("transcript") or "") for p in BANNED_PHRASES)]
    lying = [it for it in items
             if (it.get("transcript") or "").strip() and not it.get("has_subtitles")]
    rep.check("live: an unresolvable source returns no invented text", not invented,
              str([it.get("title") for it in items])[:120])
    rep.check("live: has_subtitles never disagrees with the transcript",
              not lying, "%d items" % len(lying))

    # 2. A link import with no obtainable subtitles must fail, not fabricate.
    st, body = http("POST", base, "/api/import/link",
                    {"url": opaque, "title": "anti-fabrication probe"}, timeout=120)
    text = body.decode("utf-8", "replace")
    fabricated = any(p in text for p in BANNED_PHRASES)
    rep.check("live: link import refuses to invent a transcript",
              st >= 400 and not fabricated,
              "status=%s body=%s" % (st, text[:200]))
    rep.check("live: the import failure explains what to do instead",
              st != 422 or ("字幕" in text or "transcript" in text),
              text[:200] if st == 422 else "not a 422")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", default=APP_DIR)
    ap.add_argument("--base", default="", help="probe a running instance")
    ap.add_argument("--stage", default="s8_no_fabrication")
    args = ap.parse_args()

    rep = Report(args.stage)
    targets = ["downloader.py", "server.py", "docx_generator.py"]
    targets = [os.path.join(args.app, t) for t in targets]
    targets += [os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
                for f in ("s4c_english_definitions.py", "export_conformance.py")]
    for path in targets:
        if os.path.exists(path):
            scan_file(path, rep, allowed_demo=path.endswith("downloader.py"))
    rep.check("at least the app modules were scanned",
              any(os.path.exists(p) for p in targets), str(targets))

    if args.base:
        probe(args.base.rstrip("/"), rep)
    else:
        rep.note("no --base given: live probes skipped")

    payload = rep.write()
    log("\nS8 anti-fabrication %s - %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
