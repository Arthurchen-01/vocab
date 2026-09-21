# -*- coding: utf-8 -*-
"""sciam - Scientific American podcast episodes (Megaphone/Omny CDN + article text).

The article text is real fetched prose but it is NOT audio-aligned dialogue, so it
is labelled `transcript_source=article_text` and carries no timestamps. The
provider used to stamp invented "[00:00]" times on those paragraphs, which made a
written article look like a transcript.
"""
from providers.base import CAP_MEDIA, CAP_METADATA, CAP_SUBTITLES, Provider


class SciAmProvider(Provider):
    name = "sciam"
    capabilities = (CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES)
    priority = 15

    def can_handle(self, url):
        return bool(url) and ("scientificamerican.com" in url
                              or "traffic.megaphone.fm" in url)

    def fetch(self, url, need, policy):
        import downloader
        info = downloader.fetch_scientific_american_info(url)
        if not info:
            return {"success": False, "error": "科学美国人解析失败"}
        return info
