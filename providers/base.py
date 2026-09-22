# -*- coding: utf-8 -*-
"""Source providers: one module per tool, declared by CAPABILITY not by order.

The old resolver was a hard-coded if/elif chain in `downloader.py` ("Tier 1..4"
was only a label): adding a tool meant editing the core file, there was no way to
prefer speed over accuracy, and the fallback order was whatever someone typed.

Here each provider declares
  * which URL shapes it can handle,
  * which capabilities it can supply (metadata / media / subtitles / asr),
  * a static priority used only to break ties,
and the resolver picks a chain per request, ordered by **measured success rate**
for that host (see `health.py`). A provider that fails is skipped, not fatal.

Contract: `fetch()` returns a partial result dict; the resolver merges the
results of several providers, so one can supply metadata while another supplies
the transcript. Anything a provider cannot obtain must be left EMPTY - no
provider may invent a title or a transcript (see
`tools/quality_pipeline/no_fabrication_gate.py`).
"""
import os

CAP_METADATA = "metadata"      # real title / author / duration / cover
CAP_MEDIA = "media"            # a downloadable audio/video stream
CAP_SUBTITLES = "subtitles"    # a real subtitle track (human or platform CC)
CAP_ASR = "asr"                # machine transcription of the audio


class Provider:
    """Base class. Subclasses set `name`, `capabilities`, `priority`."""

    name = "provider"
    capabilities = ()
    priority = 50          # lower is tried first when health is equal

    def can_handle(self, url):
        return False

    def available(self):
        """False when the tool this provider wraps is not installed/configured.

        A missing optional tool must only remove that provider from the chain,
        never break resolution: that is what makes the chain a real set of
        backups rather than a single point of failure.
        """
        return True

    def fetch(self, url, need, policy):
        """Return a partial result dict for the requested capabilities."""
        raise NotImplementedError

    # ---- helpers shared by providers -------------------------------------
    @staticmethod
    def no_text():
        return {"transcript": "", "has_subtitles": False,
                "transcript_source": "unavailable"}

    def describe(self):
        return "%s(%s)" % (self.name, ",".join(self.capabilities))


def load_registry(verbose=False):
    """Instantiate every provider whose dependency is present.

    Import order does not matter: the resolver sorts by capability, measured
    health and priority. An import error or a missing dependency drops just that
    provider.
    """
    from providers import (bbdown, bilibili_cc, direct_media, direct_subtitle,
                           sciam, whisper_asr, ytdlp_provider, youget)
    classes = [
        sciam.SciAmProvider,
        direct_subtitle.DirectSubtitleProvider,
        direct_media.DirectMediaProvider,
        ytdlp_provider.YtDlpProvider,
        bbdown.BBDownProvider,
        youget.YouGetProvider,
        bilibili_cc.BilibiliCCProvider,
        whisper_asr.WhisperASRProvider,
    ]
    out = []
    for cls in classes:
        try:
            p = cls()
        except Exception as exc:  # noqa: BLE001
            if verbose:
                print("[providers] %s unavailable: %s" % (cls.__name__, exc))
            continue
        try:
            ready = p.available()
        except Exception:  # noqa: BLE001
            ready = False
        if ready:
            out.append(p)
        elif verbose:
            # `available()` is also how a provider declares "the tool is installed
            # but cannot currently work" - BBDown probes itself for exactly that.
            print("[providers] %s skipped (dependency missing or self-probe failed)"
                  % p.name)
    return out
