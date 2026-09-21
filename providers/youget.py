# -*- coding: utf-8 -*-
"""youget - a second, independent downloader as a media backup for Bilibili.

yt-dlp and you-get fail for different reasons (protocol changes, risk control,
API signing), so keeping both means a Bilibili link that one cannot fetch is
often still fetchable by the other. Measured priority: yt-dlp is tried first
(richer metadata), you-get is the backup.

you-get provides media + a title; it does NOT provide subtitles, so it never
claims a transcript.
"""
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse

from providers.base import CAP_MEDIA, CAP_METADATA, Provider


class YouGetProvider(Provider):
    name = "you-get"
    capabilities = (CAP_METADATA, CAP_MEDIA)
    priority = 55          # after yt-dlp, before ASR

    def available(self):
        return bool(shutil.which("you-get"))

    def can_handle(self, url):
        if not url or not url.startswith("http"):
            return False
        # you-get covers the Chinese video sites yt-dlp sometimes struggles with.
        return any(host in url for host in (
            "bilibili.com", "youku.com", "iqiyi.com", "v.qq.com", "douyin.com",
            "weibo.com", "acfun.cn", "youtube.com"))

    def fetch(self, url, need, policy):
        binary = shutil.which("you-get")
        if not binary:
            return {"success": False, "error": "you-get 未安装"}
        # --json prints the resolved media info without downloading.
        try:
            proc = subprocess.run([binary, "--json", url], capture_output=True,
                                  timeout=int(policy.get("timeout") or 180))
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": "you-get 调用失败: %s" % type(exc).__name__}
        raw = proc.stdout.decode("utf-8", "replace").strip()
        if not raw:
            err = proc.stderr.decode("utf-8", "replace").strip()[-200:]
            return {"success": False, "error": "you-get 未返回信息: %s" % err}
        import json
        try:
            data = json.loads(raw)
        except ValueError:
            return {"success": False, "error": "you-get 返回的不是 JSON"}
        if isinstance(data, list):
            data = data[0] if data else {}
        title = (data.get("title") or "").strip()

        def first_url(src):
            if isinstance(src, list) and src:
                item = src[0]
                return item if isinstance(item, str) else (item or {}).get("url", "")
            if isinstance(src, str):
                return src
            return ""

        best = ""
        for _key, entry in (data.get("streams") or {}).items():
            best = first_url((entry or {}).get("src"))
            if best:
                break
        if not best:
            best = first_url(data.get("src"))
        safe = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fa5-]", "_", title or "media")[:40]
        download_url = ("/api/media/stream-download?url=%s&filename=%s.mp4"
                        "&media_type=video&platform=youget"
                        % (urllib.parse.quote(url), safe))
        return {
            "success": bool(title),
            "platform": "youget",
            "platform_name": "you-get (备用下载器)",
            "platform_icon": "fa-solid fa-download",
            "title": title or url,
            "author": (data.get("site") or ""),
            "cover": "",
            "duration": "",
            "media_type": "video",
            "direct_media_url": best or url,
            "download_url": download_url,
            "metadata_source": "you-get",
            "tier_used": "you-get 备用解析",
            **self.no_text(),
        }
