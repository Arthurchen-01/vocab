# -*- coding: utf-8 -*-
"""bbdown - a second, independent Bilibili downloader (nilaoda/BBDown).

Status on this host: **installed but blocked**. BBDown 1.6.3 (the latest upstream
release, 2024-08) reads a video through `api.bilibili.com/x/web-interface/view`,
and that exact endpoint answers HTTP 412 (risk control) here - in every API mode it
offers (WEB / TV / APP / INTL), with and without a cookie:

    x/web-interface/view         -> 412     <- what BBDown calls
    x/web-interface/wbi/view     -> 200     <- what yt-dlp calls
    x/web-interface/view/detail  -> 412
    x/player/pagelist            -> 200

So the block is per endpoint, not per IP: yt-dlp downloads this same video fine.
BBDown's own error even says "请尝试升级到最新版本后重试", but 1.6.3 is the newest.

Rather than ship a provider that always fails (which would add a failing health row
and a timeout to every Bilibili resolution), this provider **probes itself** and
reports unavailable while the probe fails. That way:
  * today it is silently skipped - no cost, no noise;
  * the day Bilibili unblocks that endpoint, or a newer BBDown ships, or a login
    cookie changes the outcome, it joins the chain with no code change.

Probe results are cached on disk (default 24h) so the check is paid once per day,
not per request.
"""
import json
import os
import re
import shutil
import subprocess
import time

from providers.base import CAP_MEDIA, CAP_METADATA, Provider

# A long-lived public video, used only to ask "can BBDown talk to Bilibili at all?"
PROBE_URL = os.environ.get("VOCAB_BBDOWN_PROBE_URL",
                           "https://www.bilibili.com/video/BV1xx411c7mD")
PROBE_TTL = int(os.environ.get("VOCAB_BBDOWN_PROBE_TTL", str(24 * 3600)))
PROBE_TIMEOUT = int(os.environ.get("VOCAB_BBDOWN_PROBE_TIMEOUT", "90"))


def _state_path():
    work = os.environ.get("VOCAB_WORK_DIR", "").strip()
    if work:
        return os.path.join(work, "out", "bbdown_probe.json")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "bbdown_probe.json")


def _read_state():
    try:
        with open(_state_path(), encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _write_state(state):
    try:
        path = _state_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001
        pass


class BBDownProvider(Provider):
    name = "bbdown"
    capabilities = (CAP_METADATA, CAP_MEDIA)
    priority = 45          # behind yt-dlp (which is measured working), ahead of ASR

    def available(self):
        if not shutil.which("bbdown"):
            return False
        state = _read_state()
        now = time.time()
        if state.get("checked_at") and (now - state["checked_at"]) < PROBE_TTL:
            return bool(state.get("ok"))
        ok, note = self._probe()
        _write_state({"checked_at": now, "ok": ok, "note": note,
                      "checked": time.strftime("%Y-%m-%d %H:%M:%S")})
        return ok

    def can_handle(self, url):
        return bool(url) and ("bilibili.com" in url
                              or bool(re.search(r"BV[0-9A-Za-z]{10}", url)))

    def fetch(self, url, need, policy):
        """Real metadata from BBDown's own resolver, plus a media proxy URL."""
        import downloader
        binary = shutil.which("bbdown")
        if not binary:
            return {"success": False, "error": "BBDown 未安装"}
        cmd = [binary, "--only-show-info"]
        cookies = policy.get("cookies_file")
        if cookies and os.path.isfile(cookies):
            cmd += ["--cookie", _cookie_string(cookies)]
        cmd.append(url)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=int(policy.get("timeout") or 180))
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": "BBDown 调用失败: %s" % type(exc).__name__}
        out = (proc.stdout or "") + (proc.stderr or "")
        if "412" in out:
            return {"success": False, "error": "BBDown 被 B 站风控拦截 (HTTP 412)"}
        title = _field(out, r"标题:\s*(.+)") or _field(out, r"title:\s*(.+)")
        if not title:
            return {"success": False, "error": "BBDown 未返回可解析的标题"}
        return {
            "success": True,
            "platform": "bilibili",
            "platform_name": "Bilibili (BBDown)",
            "title": title.strip(),
            "author": (_field(out, r"UP主:\s*(.+)") or "").strip(),
            "duration": (_field(out, r"时长:\s*(.+)") or "").strip(),
            "media_type": "audio",
            "direct_media_url": url,
            "download_url": downloader.media_proxy_url(
                url, re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fa5-]", "_", title)[:40] + ".mp3",
                "audio", "bilibili"),
            "metadata_source": "bbdown",
            **self.no_text(),
        }

    # ---- internals -------------------------------------------------------
    @staticmethod
    def _probe():
        """Ask BBDown to resolve one known video. Cheap and decisive."""
        binary = shutil.which("bbdown")
        if not binary:
            return False, "binary missing"
        try:
            proc = subprocess.run([binary, "--only-show-info", PROBE_URL],
                                  capture_output=True, text=True, timeout=PROBE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return False, "%s: %s" % (type(exc).__name__, exc)
        out = (proc.stdout or "") + (proc.stderr or "")
        if "412" in out:
            return False, "blocked by Bilibili risk control (HTTP 412)"
        if proc.returncode == 0 and ("标题" in out or "title" in out.lower()):
            return True, "resolves normally"
        return False, (out.strip().splitlines() or ["no output"])[-1][:160]


def _field(text, pattern):
    m = re.search(pattern, text or "")
    return m.group(1) if m else ""


def _cookie_string(path):
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
