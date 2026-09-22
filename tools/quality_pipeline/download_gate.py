# -*- coding: utf-8 -*-
"""S10 - download gate: can a user actually DOWNLOAD from each source?

Nothing verified this before, and the user's question was exactly "can we download
now?". A resolver returning a `download_url` proves only that the link was
resolved - the media proxy behind that URL has its own failure modes, and two of
them were live until this gate was written:

  * the download URL carried a raw Chinese filename, so any client that does not
    silently percent-encode it died with `UnicodeEncodeError` (browsers hide it);
  * the proxy resolved a real media stream with yt-dlp only for YouTube, so a
    Bilibili link was proxied as its HTML watch page;
  * the proxy set a raw non-ASCII `Content-Disposition`, which raises inside
    http.server - the same latin-1 defect the export path had.

So this gate follows the URL and checks bytes: status, length, and the container
magic, using a Range request so a 166 MB episode is not pulled in full.

    python download_gate.py --base https://vocab.samuraiguan.cloud
    python download_gate.py --base http://127.0.0.1:8765
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Report, log  # noqa: E402

LINKS = [
    ("bilibili", "https://www.bilibili.com/video/BV1NdwWe6Epf"),
    ("youtube", "https://www.youtube.com/watch?v=kBdfcR-8hEY"),
    ("direct-mp3", "https://traffic.megaphone.fm/SAM8705727348.mp3"),
]
CHUNK = 1 << 20          # 1 MB is enough to identify the container


def _post(base, path, payload, timeout=300):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "download-gate"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "replace")[:200]}


def sniff(head):
    if head[:3] == b"ID3":
        return "mp3 (ID3)"
    if len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3 (MPEG frame sync)"
    if head[4:8] == b"ftyp":
        return "mp4/m4a (ftyp)"
    if head[:4] == b"\x1aE\xdf\xa3":
        return "webm/mkv (EBML)"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"RIFF":
        return "wav"
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    ap.add_argument("--stage", default="s10_download")
    ap.add_argument("--links", default="", help="comma list of name=url overrides")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    links = list(LINKS)
    for item in [x.strip() for x in args.links.split(",") if x.strip()]:
        name, _, url = item.partition("=")
        if url:
            links.append((name, url))

    rep = Report(args.stage)
    for name, url in links:
        st, data = _post(base, "/api/media/batch-extract",
                         {"urls": [url], "mode": "media", "media_type": "audio",
                          "auto_expand": False})
        items = data.get("items") or []
        rep.check("%s: resolved to a media item" % name, bool(items),
                  "HTTP %s, %d item(s)" % (st, len(items)))
        if not items:
            continue
        item = items[0]
        rep.check("%s: real title (not a placeholder)" % name,
                  bool((item.get("title") or "").strip()),
                  (item.get("title") or "")[:60])
        dl = item.get("download_url") or ""
        rep.check("%s: a download url is offered" % name, bool(dl), dl[:90])
        if not dl:
            continue
        # The URL itself must be ASCII-safe, or strict clients cannot use it.
        try:
            (base + dl).encode("ascii")
            ascii_ok, why = True, ""
        except UnicodeEncodeError as exc:
            ascii_ok, why = False, str(exc)
        rep.check("%s: download url is ASCII-safe" % name, ascii_ok, why)

        target = base + dl if dl.startswith("/") else dl
        req = urllib.request.Request(target, headers={
            "Range": "bytes=0-%d" % (CHUNK - 1), "User-Agent": "download-gate"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                status = r.status
                ctype = r.headers.get("Content-Type", "")
                crange = r.headers.get("Content-Range", "")
                body = r.read(CHUNK)
        except Exception as exc:  # noqa: BLE001
            rep.check("%s: bytes actually arrive" % name, False,
                      "%s: %s" % (type(exc).__name__, exc))
            continue
        took = time.time() - t0
        kind = sniff(body)
        rep.check("%s: bytes actually arrive" % name, len(body) > 100000,
                  "%d bytes in %.1fs (%s)" % (len(body), took, ctype[:40]))
        rep.check("%s: the payload is real media, not an error page" % name,
                  bool(kind), kind or "unrecognised magic: %r" % body[:12])
        if crange:
            rep.note("%s: total size %s" % (name, crange.split("/")[-1]))

    payload = rep.write()
    log("\nS10 download gate %s - %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
