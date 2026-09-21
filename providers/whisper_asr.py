# -*- coding: utf-8 -*-
"""whisper_asr - machine transcription, the fallback that makes ANY source usable.

Why this provider exists: measured on the production host, YouTube links have real
subtitles but Bilibili links have none at all (`subs=NA`, no auto-captions), so
"paste a Bilibili link and study its vocabulary" was impossible - the honest
answer was an error. Local ASR removes that dead end: 16 vCPU / 15 GB RAM / no
GPU, faster-whisper `small` int8.

This is a *machine* transcript and is labelled as such:
  transcript_source = "whisper_asr:small"
  is_machine_transcript = True
so the card and the export can distinguish it from human/platform subtitles.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from providers.base import CAP_ASR, CAP_SUBTITLES, Provider

_HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(_HERE, "asr_runner.py")


def _fmt_ts(seconds):
    seconds = max(0, int(seconds or 0))
    return "[%02d:%02d]" % (seconds // 60, seconds % 60)


class WhisperASRProvider(Provider):
    name = "whisper_asr"
    capabilities = (CAP_SUBTITLES, CAP_ASR)
    priority = 90          # last resort: slow, so anything real wins first

    def available(self):
        py = os.environ.get("VOCAB_ASR_PYTHON", "/opt/asr-venv/bin/python")
        if not os.path.isfile(py):
            return False
        try:
            rc = subprocess.run([py, "-c", "import faster_whisper"],
                                capture_output=True, timeout=120).returncode
        except Exception:  # noqa: BLE001
            return False
        return rc == 0

    def can_handle(self, url):
        # Any link yt-dlp can download audio from; the resolver only reaches this
        # provider when no real subtitle track was found.
        return bool(url) and (url.startswith("http://") or url.startswith("https://"))

    def fetch(self, url, need, policy):
        py = policy.get("asr_python") or "/opt/asr-venv/bin/python"
        model = policy.get("asr_model") or "small"
        compute = policy.get("asr_compute") or "int8"
        limit = int(policy.get("asr_max_minutes") or 0)
        workdir = tempfile.mkdtemp(prefix="verbalex_asr_")
        try:
            meta = self._probe(url, policy)
            minutes = (meta.get("duration") or 0) / 60.0
            if limit and minutes > limit:
                return {"success": False,
                        "error": "音频 %.0f 分钟超过 ASR 上限 %d 分钟（policy.asr_max_minutes）"
                                 % (minutes, limit)}
            audio = self._download_audio(url, workdir, policy)
            if not audio:
                return {"success": False, "error": "无法下载该链接的音频，ASR 无法进行"}
            t0 = time.time()
            proc = subprocess.run([py, RUNNER, audio, model, compute, "en"],
                                  capture_output=True, timeout=7200,
                                  env=self._asr_env())
            out = proc.stdout.decode("utf-8", "replace")
            payload = None
            for line in out.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        continue
            if not payload or payload.get("error"):
                err = (payload or {}).get("error") or proc.stderr.decode(
                    "utf-8", "replace")[-200:]
                return {"success": False, "error": "ASR 失败: %s" % err}
            segs = [s for s in payload.get("segments", []) if s.get("text")]
            if not segs:
                return {"success": False, "error": "ASR 没有产出任何文本"}
            transcript = "\n".join("%s %s" % (_fmt_ts(s["start"]), s["text"])
                                   for s in segs)
            return {
                "success": True,
                "title": meta.get("title") or "",
                "author": meta.get("uploader") or "",
                "cover": meta.get("thumbnail") or "",
                "duration": meta.get("duration_string") or "",
                "transcript": transcript,
                "has_subtitles": True,
                "transcript_source": "whisper_asr:%s" % model,
                "is_machine_transcript": True,
                "subtitle_notice": (
                    "该来源没有人工/平台字幕，本逐字稿由本地 faster-whisper(%s) 机器转写，"
                    "可能存在识别误差，卡片会标注“机器转写”。" % model),
                "asr_stats": {"model": model, "compute": compute,
                              "segments": len(segs),
                              "words": sum(len(s["text"].split()) for s in segs),
                              "realtime_factor": payload.get("realtime_factor"),
                              "seconds": round(time.time() - t0, 1)},
            }
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ---- internals -------------------------------------------------------
    @staticmethod
    def _asr_env():
        """Environment for the model download.

        Measured on the production host: huggingface.co and hf-mirror.com answer
        200, but cdn-lfs.huggingface.co and the new Xet CAS endpoint
        (cas-server.xethub.hf.co) are unreachable, so the default client path
        fails with "File reconstruction error". Pointing HF at the mirror while
        disabling Xet is what actually downloads the model - verified by loading
        faster-whisper `small` (467 MB) successfully.
        """
        env = dict(os.environ)
        env.setdefault("HF_HUB_DISABLE_XET", "1")
        env.setdefault("HF_ENDPOINT", os.environ.get("VOCAB_HF_ENDPOINT",
                                                     "https://hf-mirror.com"))
        env.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
        return env

    @staticmethod
    def _ytdlp():
        return shutil.which("yt-dlp") or ("/usr/local/bin/yt-dlp"
                                          if os.path.exists("/usr/local/bin/yt-dlp") else "")

    def _probe(self, url, policy):
        binary = self._ytdlp()
        if not binary:
            return {}
        args = [binary, "--no-warnings", "--skip-download",
                "--print", "%(title)s\t%(uploader)s\t%(duration)s\t%(thumbnail)s"]
        cookies = policy.get("cookies_file")
        if cookies and os.path.isfile(cookies):
            args += ["--cookies", cookies]
        try:
            proc = subprocess.run(args + [url], capture_output=True,
                                  timeout=int(policy.get("timeout") or 180))
            line = proc.stdout.decode("utf-8", "replace").strip().splitlines()
            if line:
                parts = line[0].split("\t")
                while len(parts) < 4:
                    parts.append("")
                return {"title": parts[0], "uploader": parts[1],
                        "duration": float(parts[2] or 0),
                        "thumbnail": parts[3]}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _download_audio(self, url, workdir, policy):
        binary = self._ytdlp()
        if not binary:
            return ""
        args = [binary, "--no-warnings", "-x", "--audio-format", "mp3",
                "-o", os.path.join(workdir, "audio.%(ext)s")]
        cookies = policy.get("cookies_file")
        if cookies and os.path.isfile(cookies):
            args += ["--cookies", cookies]
        try:
            subprocess.run(args + [url], capture_output=True, timeout=1800)
        except Exception as exc:  # noqa: BLE001
            print("[whisper_asr] download failed: %s" % exc, file=sys.stderr)
            return ""
        for name in os.listdir(workdir):
            if name.startswith("audio."):
                return os.path.join(workdir, name)
        return ""
