# -*- coding: utf-8 -*-
"""direct_media - a bare audio/video URL. Metadata is derived from the URL itself
and, crucially, NO transcript is claimed: a media file carries no text, and
inventing one is exactly the defect this project had to remove twice.
"""
import os
import urllib.parse

from providers.base import CAP_MEDIA, CAP_METADATA, Provider

AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac")
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".mov", ".flv")


class DirectMediaProvider(Provider):
    name = "direct_media"
    capabilities = (CAP_METADATA, CAP_MEDIA)
    priority = 20

    def can_handle(self, url):
        path = urllib.parse.urlparse(url or "").path.lower()
        return path.endswith(AUDIO_EXT + VIDEO_EXT)

    def fetch(self, url, need, policy):
        import downloader
        return downloader.fetch_direct_media_info(url)
