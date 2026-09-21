# -*- coding: utf-8 -*-
"""Resolve a source link into real metadata / media / transcript.

Chain selection is by capability, then by *measured* health for that host, then
by the provider's static priority. `quality=fast` stops at the first provider
that satisfies the request; `quality=best` consults every capable provider and
keeps the richest real transcript.

Hard rules (enforced by `tools/quality_pipeline/no_fabrication_gate.py`):
  * a provider that fails is skipped, never asked to improvise;
  * `transcript` is only ever text a provider actually obtained;
  * a machine transcript (ASR) is labelled `transcript_source=whisper_asr:<model>`
    and flagged `is_machine_transcript=True`, so the UI can say so.
"""
import time
import urllib.parse

from providers import health
from providers import policy as policy_mod
from providers.base import (CAP_ASR, CAP_MEDIA, CAP_METADATA, CAP_SUBTITLES,
                            load_registry)

DEFAULT_NEED = (CAP_METADATA, CAP_MEDIA, CAP_SUBTITLES)
_TEXT_KEYS = ("transcript", "has_subtitles", "transcript_source",
              "subtitle_notice", "is_machine_transcript", "asr_stats")


def _log(msg, *args):
    if args:
        msg = msg % args
    print(msg, flush=True)


def _transcript_score(result):
    """Human/platform subtitles beat a machine transcript; longer beats shorter."""
    text = (result.get("transcript") or "").strip()
    if not text:
        return (0, 0)
    machine = 1 if result.get("is_machine_transcript") else 0
    return (1 - machine, len(text))


def _host(url):
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _satisfied(result, need):
    for cap in need:
        if cap == CAP_METADATA and not (result.get("title") or "").strip():
            return False
        if cap == CAP_MEDIA and not (result.get("direct_media_url")
                                     or result.get("download_url")):
            return False
        if cap == CAP_SUBTITLES and not (result.get("transcript") or "").strip():
            return False
    return True


def resolve(url, need=None, overrides=None, registry=None, verbose=False):
    """Returns (result_dict, trail_list)."""
    url = (url or "").strip()
    pol = policy_mod.resolve(overrides)
    need = tuple(need or DEFAULT_NEED)
    host = _host(url)
    if not url:
        return ({"success": False, "error": "URL 不能为空", "transcript": "",
                 "has_subtitles": False, "provider_trail": []}, [])

    providers = registry if registry is not None else load_registry(verbose=verbose)
    # ASR is deliberately NOT part of the candidate chain. It declares
    # CAP_SUBTITLES (so the chain knows it can satisfy a transcript request) and
    # can_handle() accepts any URL, so leaving it in the loop made it run as an
    # ordinary provider - which bypassed `allow_asr` entirely and transcribed a
    # video even when the policy forbade it. It is now reached only through the
    # explicit fallback below, which honours the policy.
    candidates = [p for p in providers
                  if p.can_handle(url) and CAP_ASR not in p.capabilities]
    if not candidates:
        return ({"success": False, "provider_trail": [],
                 "error": "未识别的音视频或字幕网址（当前没有 provider 能处理该域名）",
                 "transcript": "", "has_subtitles": False,
                 "subtitle_notice": "没有可用的解析工具能处理这个链接。"}, [])

    def rank(p):
        rate, mean_ms = health.score(p.name, host)
        return (-rate, p.priority, mean_ms)

    candidates.sort(key=rank)

    merged = {"success": False, "transcript": "", "has_subtitles": False,
              "transcript_source": "unavailable"}
    trail = []
    for provider in candidates:
        if _satisfied(merged, need):
            break
        t0 = time.time()
        try:
            part = provider.fetch(url, need, pol) or {}
        except Exception as exc:  # noqa: BLE001 - one broken provider is not fatal
            took = time.time() - t0
            health.record(provider.name, host, False, took,
                          "%s: %s" % (type(exc).__name__, exc))
            trail.append({"provider": provider.name, "ok": False,
                          "seconds": round(took, 2),
                          "error": "%s: %s" % (type(exc).__name__, str(exc)[:120])})
            if verbose:
                _log("    [resolve] %s failed: %s", provider.name, str(exc)[:120])
            continue
        took = time.time() - t0
        ok = bool(part.get("success", True)) and any(
            (part.get(k) or "") for k in ("title", "direct_media_url",
                                          "download_url", "transcript"))
        health.record(provider.name, host, ok, took, part.get("error", ""))
        trail.append({"provider": provider.name, "ok": ok, "seconds": round(took, 2),
                      "capabilities": list(provider.capabilities),
                      "transcript_source": part.get("transcript_source", ""),
                      "error": part.get("error", "")})
        if verbose:
            _log("    [resolve] %s -> %s (%.1fs)", provider.name,
                 "ok" if ok else "no", took)

        if _transcript_score(part) > _transcript_score(merged):
            for key in _TEXT_KEYS:
                if key in part:
                    merged[key] = part[key]
        for key, value in part.items():
            if key in _TEXT_KEYS or key in ("success", "error"):
                continue
            if value not in (None, "", [], {}) and merged.get(key) in (None, "", [], {}):
                merged[key] = value
        if ok:
            # A provider need not carry an explicit `success` flag: producing any
            # usable field is what counts. (sciam returns metadata without one,
            # which used to leave the merged result looking failed.)
            merged["success"] = True
        if pol["quality"] == policy_mod.QUALITY_FAST and _satisfied(merged, need):
            break

    # ASR fallback: only when nothing real was found and the policy allows it.
    if CAP_SUBTITLES in need and not (merged.get("transcript") or "").strip():
        if pol["allow_asr"]:
            asr = next((p for p in providers if CAP_ASR in p.capabilities
                        and p.can_handle(url)), None)
            if asr is None:
                asr = next((p for p in providers if CAP_ASR in p.capabilities), None)
            if asr is not None:
                t0 = time.time()
                try:
                    part = asr.fetch(url, need, pol) or {}
                except Exception as exc:  # noqa: BLE001
                    part = {"success": False,
                            "error": "%s: %s" % (type(exc).__name__, exc)}
                took = time.time() - t0
                ok = bool((part.get("transcript") or "").strip())
                health.record(asr.name, host, ok, took, part.get("error", ""))
                trail.append({"provider": asr.name, "ok": ok, "seconds": round(took, 2),
                              "capabilities": list(asr.capabilities),
                              "transcript_source": part.get("transcript_source", ""),
                              "error": part.get("error", "")})
                if ok:
                    for key in _TEXT_KEYS:
                        if key in part:
                            merged[key] = part[key]
        else:
            trail.append({"provider": "whisper_asr", "ok": False, "seconds": 0,
                          "error": "ASR disabled by policy (allow_asr=false)"})

    merged["provider_trail"] = trail
    merged.setdefault("provider", trail[-1]["provider"] if trail else "")
    if not merged.get("success"):
        merged["error"] = (trail[-1].get("error") if trail else "") or "所有 provider 均失败"
    return merged, trail


def resolve_batch(urls, need=None, overrides=None, verbose=False, mode="media"):
    registry = load_registry(verbose=verbose)
    out = []
    for i, url in enumerate(urls, 1):
        result, _trail = resolve(url, need=need, overrides=overrides,
                                 registry=registry, verbose=verbose)
        result["index"] = i
        result["req_mode"] = mode
        out.append(result)
    return out
