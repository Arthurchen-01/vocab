# -*- coding: utf-8 -*-
"""bilibili_cc - the platform's own metadata + subtitle track, via the official API.

Endpoint choice is not cosmetic here. Measured from the production host:

    x/web-interface/view         -> HTTP 412 (risk control)   <- the classic one
    x/web-interface/wbi/view     -> HTTP 200, full JSON
    x/web-interface/view/detail  -> HTTP 412
    x/player/pagelist            -> HTTP 200

The block is **per endpoint**, not per IP and not per header: the WBI variant of the
same call answers normally with nothing but a UA and a Referer. This provider
originally used the blocked endpoint, so it failed every time (0/3 in the health
store) while yt-dlp succeeded on the same host - yt-dlp simply uses the WBI route.
It now tries WBI first and falls back to the classic path, and it declares
CAP_METADATA so it can serve as a real metadata backup too.

It stays in the chain because
  * it is the only route to Bilibili's **AI subtitles**, which need a logged-in
    cookie (`policy.cookies_file`), and
  * when the video has CC, platform subtitles beat a machine transcript.
"""
import json
import os
import re
import urllib.request

from providers.base import CAP_METADATA, CAP_SUBTITLES, Provider

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# WBI first: the classic endpoint is the one this host is blocked on.
API_ENDPOINTS = (
    "https://api.bilibili.com/x/web-interface/wbi/view?bvid=%s",
    "https://api.bilibili.com/x/web-interface/view?bvid=%s",
)


class BilibiliCCProvider(Provider):
    name = "bilibili_cc"
    capabilities = (CAP_METADATA, CAP_SUBTITLES)
    priority = 40

    def can_handle(self, url):
        return bool(url) and ("bilibili.com" in url
                              or re.search(r"BV[0-9A-Za-z]{10}", url))

    def fetch(self, url, need, policy):
        import downloader
        m = re.search(r"(BV[0-9A-Za-z]{10})", url)
        if not m:
            return {"success": False, "error": "未找到 BV 号"}
        bvid = m.group(1)
        headers = {"User-Agent": USER_AGENT, "Referer": "https://www.bilibili.com"}
        cookies = policy.get("cookies_file")
        if cookies and os.path.isfile(cookies):
            headers["Cookie"] = _cookie_header(cookies)
        else:
            headers["Cookie"] = "buvid3=F8B7B618-6A47-19B4-0994-39908FEE998188198infoc;"
        info, errors = None, []
        for template in API_ENDPOINTS:
            endpoint = template.split("?")[0].rsplit("/", 1)[-1]
            try:
                req = urllib.request.Request(template % bvid, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    status = getattr(resp, "status", 200)
                    body = resp.read()
            except Exception as exc:  # noqa: BLE001
                errors.append("%s -> %s" % (endpoint, type(exc).__name__))
                continue
            if status != 200 or not body.lstrip().startswith(b"{"):
                errors.append("%s -> HTTP %s (risk control)" % (endpoint, status))
                continue
            try:
                data = json.loads(body.decode("utf-8"))
            except ValueError:
                errors.append("%s -> not JSON" % endpoint)
                continue
            if data.get("code") != 0:
                errors.append("%s -> code=%s %s" % (endpoint, data.get("code"),
                                                    data.get("message")))
                continue
            info = data.get("data", {})
            break
        if not info:
            return {"success": False, "error": "B 站接口均不可用: %s" % "; ".join(errors)}

        seconds = info.get("duration") or 0
        result = {
            "success": True,
            "title": (info.get("title") or "").strip(),
            "author": (info.get("owner") or {}).get("name", ""),
            "cover": info.get("pic", ""),
            "duration": ("%d 分钟" % (seconds // 60)) if seconds else "",
            "metadata_source": "bilibili_cc",
            **self.no_text(),
        }
        subs = (info.get("subtitle") or {}).get("subtitles") or []
        if not subs:
            return result
        chosen = None
        for s in subs:
            if "en" in s.get("lan", "") or "英" in s.get("lan_doc", ""):
                chosen = s
                break
        chosen = chosen or subs[0]
        text = downloader.parse_bilibili_subtitles(chosen.get("subtitle_url", ""))
        if not text:
            return result
        result.update({
            "transcript": text,
            "has_subtitles": True,
            "transcript_source": "bilibili_cc",
            "is_machine_transcript": False,
        })
        return result


def _cookie_header(path):
    """Netscape cookie file -> a Cookie header value."""
    pairs = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                bits = line.split("\t")
                if len(bits) >= 7:
                    pairs.append("%s=%s" % (bits[5], bits[6]))
    except Exception:  # noqa: BLE001
        return ""
    return "; ".join(pairs)
