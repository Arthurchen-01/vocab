# -*- coding: utf-8 -*-
"""yt-dlp provider - the general workhorse (metadata + media + real subtitles).

Measured on the production host: YouTube links expose both human subtitles and
auto-captions (`en`, `zh-Hans`); Bilibili links expose neither. The official
Bilibili view API answers HTTP 412 (risk control) from this host, so yt-dlp is
also the primary *metadata* source there - which is why the app no longer shows a
hardcoded placeholder title.

For sites with no dedicated provider, yt-dlp still supplies real metadata and any
subtitle track, so an arbitrary lecture link is usable rather than rejected.
"""
import os
import re
import shutil
import urllib.parse

from providers.base import CAP_MEDIA, CAP_METADATA, CAP_SUBTITLES, Provider


def _stream_proxy(url, title, media_type="audio", platform="generic"):
    safe = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fa5-]", "_", title or "media").strip("_")[:40]
    ext = "mp4" if media_type == "video" else "mp3"
    return ("/api/media/stream-download?url=%s&filename=%s.%s&media_type=%s&platform=%s"
            % (urllib.parse.quote(url), safe, ext, media_type, platform))


class YtDlpProvider(Provider):
    name = "yt-dlp"
    capabilities = (CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES)
    priority = 60          # general fallback behind the shape-specific providers

    def available(self):
        return bool(shutil.which("yt-dlp")
                    or os.path.exists("/usr/local/bin/yt-dlp"))

    def can_handle(self, url):
        return bool(url) and (url.startswith("http://") or url.startswith("https://"))

    def fetch(self, url, need, policy):
        import downloader  # lazy: downloader delegates back into this package
        if "youtube.com" in url or "youtu.be" in url:
            return downloader.fetch_youtube_video_info(url) or {
                "success": False, "error": "yt-dlp 未能解析该 YouTube 链接"}
        if "bilibili.com" in url or re.search(r"BV[0-9A-Za-z]{10}", url):
            return downloader.fetch_bilibili_video_info(url) or {
                "success": False, "error": "yt-dlp 未能解析该 Bilibili 链接"}
        return self._generic(url, policy, downloader)

    def _generic(self, url, policy, downloader):
        """Any other yt-dlp-supported site: real metadata + whatever subs exist."""
        meta = downloader.ytdlp_metadata(url)
        if not meta:
            return {"success": False, "error": "yt-dlp 无法解析该链接（站点不支持或需要登录）"}
        transcript, source = downloader.ytdlp_transcript(url)
        seconds = meta.get("duration") or 0
        title = (meta.get("title") or "").strip()
        return {
            "success": True,
            "platform": "generic",
            "platform_name": "通用站点 (yt-dlp)",
            "platform_icon": "fa-solid fa-globe",
            "video_id": meta.get("id") or "",
            "title": title or url,
            "author": (meta.get("uploader") or "").strip(),
            "cover": (meta.get("thumbnail") or "").strip(),
            "duration": ("%d 分钟" % (seconds // 60)) if seconds else "",
            "media_type": "audio",
            "direct_media_url": url,
            "download_url": _stream_proxy(url, title),
            "metadata_source": "yt-dlp",
            "tier_used": "yt-dlp 通用解析",
            **downloader._transcript_fields(transcript, source),
        }
