# -*- coding: utf-8 -*-
"""bilibili_cc - the platform's own subtitle track, via the official API.

Kept as a separate provider (rather than folded into the yt-dlp one) because it
fails independently: measured from the production host, `x/web-interface/view`
answers **HTTP 412 (risk control)** for every request, so this provider usually
loses to yt-dlp. It stays in the chain because
  * it is the only route to Bilibili's **AI subtitles**, which need a logged-in
    cookie (`policy.cookies_file`), and
  * when the risk control lifts, it is cheaper than transcribing audio.
"""
import json
import os
import re
import urllib.request

from providers.base import CAP_SUBTITLES, Provider

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


class BilibiliCCProvider(Provider):
    name = "bilibili_cc"
    capabilities = (CAP_SUBTITLES,)
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
        api = "https://api.bilibili.com/x/web-interface/view?bvid=%s" % bvid
        try:
            req = urllib.request.Request(api, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read()
            if not body.lstrip().startswith(b"{"):
                return {"success": False,
                        "error": "B 站接口返回非 JSON（HTTP %s，通常是 412 风控）"
                                 % getattr(resp, "status", "?")}
            data = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": "B 站接口不可用: %s" % type(exc).__name__}
        if data.get("code") != 0:
            return {"success": False,
                    "error": "B 站接口返回 code=%s %s"
                             % (data.get("code"), data.get("message"))}
        info = data.get("data", {})
        subs = (info.get("subtitle") or {}).get("subtitles") or []
        if not subs:
            return {"success": False, "error": "该视频没有平台字幕（CC/AI 字幕均无）"}
        chosen = None
        for s in subs:
            if "en" in s.get("lan", "") or "英" in s.get("lan_doc", ""):
                chosen = s
                break
        chosen = chosen or subs[0]
        text = downloader.parse_bilibili_subtitles(chosen.get("subtitle_url", ""))
        if not text:
            return {"success": False, "error": "字幕地址为空或解析失败"}
        return {
            "success": True,
            "title": (info.get("title") or "").strip(),
            "author": (info.get("owner") or {}).get("name", ""),
            "cover": info.get("pic", ""),
            "transcript": text,
            "has_subtitles": True,
            "transcript_source": "bilibili_cc",
            "is_machine_transcript": False,
        }


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
