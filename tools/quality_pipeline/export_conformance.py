# -*- coding: utf-8 -*-
"""S7B - export conformance gate (the regression net for `导出合集是 nothing`).

The ticket's export failure was invisible to every existing check:

  * the handler answered **HTTP 200**;
  * the body was an 84-byte latin-1 error string, not a .docx;
  * it only happened when the download title contained non-ASCII characters,
    which is *every* title the UI passes ("哈佛大学《公正》第01集精读手册").

So this gate walks the whole matrix the browser can reach - every format x every
word source - over real HTTP, and validates the bytes that come back:

  1. status 200, correct Content-Type;
  2. every response header is ASCII, with an ASCII filename fallback *and* an
     RFC 5987 ``filename*=UTF-8''`` value (a raw CJK filename crashes
     http.server, which is the original bug);
  3. the body is non-empty and, for .docx, a real zip that passes the full
     docx_conformance package check against the same word list;
  4. every word from the request appears in the rendered text.

Usage
-----
    python export_conformance.py --base https://vocab.samuraiguan.cloud
    python export_conformance.py --base http://127.0.0.1:8765 --episodes ep02
"""
import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Report, log  # noqa: E402
from docx_conformance import check_package  # noqa: E402

FORMATS = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "study_guide_md": ("text/markdown", ".md"),
    "anki_csv": ("text/csv", ".csv"),
    "eudic_quizlet": ("text/plain", ".txt"),
    "words_only": ("text/plain", ".txt"),
}
CJK_TITLE = "哈佛大学《公正：该如何做是好？》(Justice) 第02集精读手册"


class Headers(dict):
    """Case-insensitive header view.

    Cloudflare answers with lowercase header names (HTTP/2 semantics), the origin
    Python server answers with Capitalized ones. A plain `dict(response.headers)`
    lookup is case-sensitive, so `headers["Content-Disposition"]` silently came
    back empty through Cloudflare and made a working deployment look broken.
    """

    def __init__(self, message):
        super().__init__((str(k).lower(), v) for k, v in message.items())

    def get(self, key, default=None):
        return super().get(str(key).lower(), default)


def http(method, url, payload=None, timeout=300, attempts=3):
    """One HTTP call, retried; a network failure becomes a readable failed check
    instead of a traceback that hides the rest of the result."""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": "export-conformance"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, Headers(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, Headers(e.headers), e.read()
        except Exception as exc:  # noqa: BLE001 - timeouts, resets, DNS
            last = exc
            if attempt + 1 < attempts:
                time.sleep(5 * (attempt + 1))
    return (0, Headers({}),
            ("network error after %d attempts: %s" % (attempts, last)).encode("utf-8"))


def word_sources(base, episodes):
    """The exact word lists the UI would send, per episode and per collection."""
    sources = []
    for ep in episodes:
        st, _h, body = http("GET", "%s/api/preset/%s" % (base, ep))
        if st == 200:
            words = json.loads(body.decode("utf-8")).get("words", [])
            if words:
                sources.append(("episode:%s" % ep, "%s_精读手册" % ep, words))
    st, _h, body = http("GET", "%s/api/collections" % base)
    if st == 200:
        for col in json.loads(body.decode("utf-8")):
            cid = col.get("id")
            st2, _h2, body2 = http("GET", "%s/api/collection/%s" % (base, cid))
            if st2 != 200:
                continue
            details = json.loads(body2.decode("utf-8")).get("episode_details") or []
            merged, seen = [], set()
            for ep in details:
                for w in (ep.get("words") or []):
                    k = (w.get("word") or "").lower()
                    if k and k not in seen:
                        seen.add(k)
                        merged.append(w)
            if merged:
                sources.append(("collection:%s" % cid,
                                "%s_合集精读手册" % col.get("title", cid), merged))
    st, _h, body = http("GET", "%s/api/vocab-bank" % base)
    if st == 200:
        words = json.loads(body.decode("utf-8")).get("words", [])
        if words:
            sources.append(("vocab-bank", "Harvard_Justice_Universal_Vocab_Bank", words))
    return sources


def check_text_payload(rep, tag, fmt, text, words):
    low = text.lower()
    if fmt == "anki_csv":
        # Compare against the PARSED field values. A definition containing a quote
        # is CSV-escaped to "" in the file, so a raw substring search reports those
        # words as missing even though Anki imports the file perfectly.
        import csv as _csv
        import io as _io
        try:
            rows = list(_csv.reader(_io.StringIO(text)))
        except Exception:  # noqa: BLE001
            rows = []
        if rows:
            header = rows[0]
            fields = []
            for col in ("EnglishDefinition", "Definition", "Back", "Word"):
                if col in header:
                    i = header.index(col)
                    fields += [r[i] for r in rows[1:] if len(r) > i]
            if fields:
                low = "\n".join(fields).lower()
    missing = [w["word"] for w in words if (w.get("word") or "").lower() not in low]
    rep.check("%s: every word present in the %s payload" % (tag, fmt),
              not missing, "%d missing e.g. %s" % (len(missing), missing[:4]))
    if fmt == "words_only":
        # A bare word list carries no definitions by design.
        return
    with_en = [w for w in words if (w.get("def_en") or "").strip()]
    if with_en:
        miss_en = [w["word"] for w in with_en
                   if w["def_en"].strip().lower() not in low]
        rep.check("%s: English definitions (%d) present in %s"
                  % (tag, len(with_en), fmt), not miss_en,
                  "%d missing e.g. %s" % (len(miss_en), miss_en[:4]))
    else:
        rep.note("%s: no word in this source carries def_en yet" % tag)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://vocab.samuraiguan.cloud")
    ap.add_argument("--episodes", default="ep01,ep02,ep03,yale_ep01")
    ap.add_argument("--formats", default=",".join(FORMATS))
    ap.add_argument("--stage", default="s7b_export")
    args = ap.parse_args()

    base = args.base.rstrip("/")
    rep = Report(args.stage)
    episodes = [e.strip() for e in args.episodes.split(",") if e.strip()]
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    sources = word_sources(base, episodes)
    rep.check("word sources reachable over HTTP", bool(sources),
              ", ".join("%s=%d" % (n, len(w)) for n, _t, w in sources))
    if not sources:
        rep.write()
        return 1

    for name, title, words in sources:
        for fmt in formats:
            expected_type, ext = FORMATS[fmt]
            st, headers, body = http("POST", "%s/api/export" % base,
                                     {"format": fmt, "title": title, "words": words})
            tag = "%s/%s" % (name, fmt)
            rep.check("%s: HTTP 200" % tag, st == 200, "status=%s" % st)
            ctype = (headers.get("content-type") or "").lower()
            rep.check("%s: Content-Type is %s" % (tag, expected_type),
                      expected_type in ctype, ctype)
            disp = headers.get("content-disposition") or ""
            rep.check("%s: Content-Disposition has an ASCII filename and filename*"
                      % tag, 'filename="' in disp and "filename*=UTF-8''" in disp,
                      disp[:110])
            try:
                disp.encode("latin-1")
                ascii_ok = True
                why = ""
            except UnicodeEncodeError as exc:
                ascii_ok, why = False, str(exc)
            rep.check("%s: response headers are latin-1 safe" % tag, ascii_ok, why)
            rep.check("%s: body is not empty" % tag, len(body) > 16,
                      "%d bytes" % len(body))

            if fmt == "docx":
                is_zip = body[:4] == b"PK\x03\x04"
                rep.check("%s: body is really a zip package" % tag, is_zip,
                          "magic=%r" % body[:8])
                if is_zip:
                    rep.check("%s: Content-Length matches the body" % tag,
                              int(headers.get("content-length") or 0) == len(body),
                              "%s vs %d" % (headers.get("content-length"), len(body)))
                    sub, _ = check_package(io.BytesIO(body), expected_words=words,
                                           stage="%s_docx" % args.stage)
                    rep.check("%s: embedded .docx passes the package gate" % tag,
                              sub.ok, "%d/%d checks failed"
                              % (sum(1 for c in sub.checks if not c["ok"]),
                                 len(sub.checks)))
                    for c in sub.checks:
                        if not c["ok"]:
                            log("      docx gate: %s -> %s", c["check"], c["detail"])
            else:
                text = body.decode("utf-8", "replace")
                rep.check("%s: body is valid UTF-8 text" % tag,
                          "\ufffd" not in text,
                          "replacement characters found" if "\ufffd" in text
                          else "%d chars" % len(text))
                rep.check("%s: body is not an error message" % tag,
                          '"error"' not in text[:200] and "codec can't encode" not in text,
                          text[:120])
                check_text_payload(rep, tag, fmt, text, words)

    # The exact failing case from the ticket, with the CJK title the UI uses.
    st, headers, body = http("POST", "%s/api/export" % base,
                             {"format": "docx", "title": CJK_TITLE,
                              "words": sources[0][2]})
    rep.check("CJK download title (the ticket's trigger) returns a real .docx",
              st == 200 and body[:4] == b"PK\x03\x04",
              "status=%s magic=%r" % (st, body[:8]))

    payload = rep.write()
    log("\nS7B export gate %s - %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
