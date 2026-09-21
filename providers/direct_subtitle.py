# -*- coding: utf-8 -*-
"""direct_subtitle - an SRT/VTT/TXT/JSON subtitle URL (including DownSub links).

This is the one path where the "transcript" is the whole point and is definitely
real text fetched from the URL.
"""
import urllib.parse

from providers.base import CAP_SUBTITLES, Provider

EXTS = (".srt", ".vtt", ".txt", ".json")


class DirectSubtitleProvider(Provider):
    name = "direct_subtitle"
    capabilities = (CAP_SUBTITLES,)
    priority = 10

    def can_handle(self, url):
        parsed = urllib.parse.urlparse(url or "")
        return (parsed.path.lower().endswith(EXTS)
                or "downsub" in (parsed.netloc or "").lower()
                or "downsub" in (url or "").lower())

    def fetch(self, url, need, policy):
        import downloader
        text = downloader.fetch_direct_subtitles(url)
        if not text:
            return {"success": False, "error": "字幕地址无法解析出文本"}
        return {
            "success": True,
            "title": "已提取的字幕逐字稿",
            "author": "公开课原声字幕",
            "cover": "/assets/scenes/banner_harvard_series.jpg",
            "duration": "45 分钟",
            "media_type": "audio",
            "direct_media_url": url,
            "transcript": text,
            "has_subtitles": True,
            "transcript_source": "direct_subtitle",
            "is_machine_transcript": False,
            "tier_used": "字幕文件直连解析",
        }
