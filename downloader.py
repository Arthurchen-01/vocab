# -*- coding: utf-8 -*-
"""
Video, Audio & Subtitle Downloader Engine for VerbaLex Studio (Enterprise Grade)
Supports:
1. Scientific American (科学美国人 - Science Quickly / Podcasts / Articles)
   - Tier 1: Megaphone / Omny 官方原装播客 CDN MP3 直链提取（秒级直达、0风控）
2. YouTube (Video / Audio / Shorts / Public Seminars)
   - Tier 2: yt-dlp 多端协议伪装 (Android/iOS 模拟绕过人机验证)
   - Tier 3: Invidious / Piped 备用无头解析容灾网关
3. Bilibili (BV ID / 视频链接 / 课程)
   - Wbi 签名与游客 buvid3 会话算法，支持原声音频流与字幕
4. Direct Audio/Video/Subtitle URLs (.mp3, .mp4, .m4a, .srt, .vtt, .txt, .json)
5. 批量解析调度器 (batch_resolve_media) 与流式中继传输 (stream-download)
"""
import os
import re
import json
import shutil
import tempfile
import urllib.request
import urllib.parse
import subprocess
import time

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

# ---------------------------------------------------------------------------
# Transcript honesty
# ---------------------------------------------------------------------------
# This module used to answer every request with a canned "transcript" whenever
# the real subtitles could not be fetched - invented sentences such as
# "[01:15] Suppose you're the driver of a trolley car hurtling down the track...",
# always with has_subtitles=True. Those strings are indistinguishable from real
# lecture text once they reach the UI or the AI word extractor, which is how a
# deck of words that were never spoken can be produced (the Ep03 deck had 24 of
# 44 words that never occur in the lecture).
#
# Rule enforced from here on: `transcript` is only ever text actually fetched
# from the source. When nothing real is available the field is empty,
# has_subtitles is False, and transcript_source says why. Curated catalogs keep
# their real metadata (title/author/duration/url) but their sample text is named
# `demo_transcript` and is never surfaced as a transcript.
NO_SUBTITLE_NOTICE = (
    "未获取到该来源的真实字幕/逐字稿，因此系统不提供任何“课堂原文”，也不会用编造文本冒充。"
    "请改用带字幕的来源（B站 CC 字幕 / YouTube 字幕），或粘贴 SRT、VTT、DownSub 文稿后再做 AI 词汇提炼。"
)


def _transcript_fields(text, source):
    """The single place that decides whether text may be called a transcript."""
    text = (text or "").strip()
    if not text:
        return {"transcript": "", "has_subtitles": False,
                "transcript_source": "unavailable",
                "subtitle_notice": NO_SUBTITLE_NOTICE}
    return {"transcript": text, "has_subtitles": True, "transcript_source": source}


def _ytdlp_bin():
    return shutil.which("yt-dlp") or ("/usr/local/bin/yt-dlp"
                                      if os.path.exists("/usr/local/bin/yt-dlp") else "")


def fetch_youtube_transcript(vid, timeout=120):
    """Real subtitles only, via yt-dlp. Returns (text, source)."""
    return ytdlp_transcript("https://www.youtube.com/watch?v=%s" % vid, timeout=timeout)


def ytdlp_run(url, extra=None, timeout=150):
    """Run yt-dlp and return its stdout lines. Empty list on any failure."""
    binary = _ytdlp_bin()
    if not binary:
        return []
    cmd = [binary, "--no-warnings", "--skip-download"] + (extra or []) + [url]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        print("[WARN] yt-dlp failed for %s: %s" % (url[:60], exc))
        return []
    out = proc.stdout.decode("utf-8", "replace")
    return [ln for ln in out.splitlines() if ln.strip()]


def ytdlp_metadata(url, extra=None, timeout=150):
    """First JSON object yt-dlp prints, or {}.

    yt-dlp is the reliable path for Bilibili from this host: the official
    api.bilibili.com/x/web-interface/view endpoint answers HTTP 412 (risk
    control), which is what made the app fall back to invented titles.
    """
    for line in ytdlp_run(url, (extra or []) + ["--dump-json"], timeout=timeout):
        if line.lstrip().startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


def ytdlp_playlist(url, timeout=200):
    """Every entry of a playlist/season/multi-part video, with real titles."""
    entries = []
    for line in ytdlp_run(url, ["--flat-playlist", "--dump-json"], timeout=timeout):
        if line.lstrip().startswith("{"):
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    return entries


def ytdlp_transcript(url, timeout=150):
    """Download a real subtitle track with yt-dlp. Returns (text, source)."""
    binary = _ytdlp_bin()
    if not binary:
        return "", ""
    workdir = tempfile.mkdtemp(prefix="verbaLEX_subs_")
    try:
        subprocess.run(
            [binary, "--no-warnings", "--skip-download", "--write-subs",
             "--write-auto-subs", "--sub-langs", "en.*,en,zh.*,zh", "--sub-format",
             "srt", "--convert-subs", "srt", "-o",
             os.path.join(workdir, "%(id)s.%(ext)s"), url],
            capture_output=True, timeout=timeout)
        for name in sorted(os.listdir(workdir)):
            if name.endswith((".srt", ".vtt")):
                with open(os.path.join(workdir, name), encoding="utf-8",
                          errors="replace") as f:
                    text = parse_srt_to_transcript(f.read())
                if text:
                    return text, "yt-dlp:%s" % name.rsplit(".", 1)[-1]
        return "", ""
    except Exception as exc:  # noqa: BLE001 - network, timeout, missing ffmpeg
        print("[WARN] subtitle fetch failed for %s: %s" % (url[:60], exc))
        return "", ""
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# Curated Scientific American Science Quickly fallback catalog for guaranteed offline resilience.
# NOTE: `demo_transcript` is illustrative sample text, NOT the episode's real
# transcript. It exists only so the cards have something to show offline; it must
# never be returned as `transcript` (see _transcript_fields).
SCIAM_FALLBACK_CATALOG = [
    {
        "url_match": "friendship",
        "title": "The science of friendship and loneliness",
        "author": "Scientific American · Science Quickly",
        "cover": "https://static.scientificamerican.com/dam/asset/d666c57a-f730-4e99-a70d-3552a4db8a75/2609_SQ_WED_FRIENDSHIP-1.png?w=1200",
        "duration": "14 分钟",
        "direct_mp3": "https://traffic.megaphone.fm/SAM7091445305.mp3",
        "demo_transcript": "[00:15] Welcome to Science Quickly, I'm Jessica Ayers. Today we examine the evolutionary psychology of human friendship.\n[02:10] Why do humans feel acute loneliness when social bonds deteriorate?\n[05:30] Neurological imaging shows that emotional isolation triggers similar pain pathways as physical trauma.\n[09:45] Cultivating meaningful reciprocal relationships remains essential for cognitive resilience."
    },
    {
        "url_match": "music",
        "title": "Why the Human Brain Craves Music and Rhythm",
        "author": "Scientific American · Science Quickly",
        "cover": "https://static.scientificamerican.com/dam/asset/d666c57a-f730-4e99-a70d-3552a4db8a75/2609_SQ_WED_FRIENDSHIP-1.png?w=1200",
        "duration": "12 分钟",
        "direct_mp3": "https://traffic.megaphone.fm/SAM4307756875.mp3",
        "demo_transcript": "[00:20] Music is a universal feature of human culture spanning millennia.\n[03:15] When we listen to harmonious melodies, dopamine pathways in the striatum light up with predictive anticipation.\n[07:40] Auditory cortex synchronization allows ensembles of musicians to coordinate in milliseconds."
    },
    {
        "url_match": "data-center",
        "title": "AI Sparks Math Debate as Data Center Energy Concerns Grow",
        "author": "Scientific American · Tech & Physics",
        "cover": "https://static.scientificamerican.com/dam/asset/d666c57a-f730-4e99-a70d-3552a4db8a75/2609_SQ_WED_FRIENDSHIP-1.png?w=1200",
        "duration": "15 分钟",
        "direct_mp3": "https://traffic.megaphone.fm/SAM8705727348.mp3",
        "demo_transcript": "[00:30] Artificial intelligence clusters demand gigawatts of electrical infrastructure.\n[04:00] Mathematical optimizations in matrix multiplication can drastically reduce computational latency.\n[08:20] Renewable power integration and water-cooling mechanics represent key engineering hurdles."
    }
]

# The curated Bilibili "knowledge graph" catalog that used to live here was
# FABRICATED and has been deleted. Verified with yt-dlp on 2026-09-21:
#
#   catalog said: BV1jt411m7rn = "哈佛大学公开课：公正 Justice（全12集官方精校完整版）"
#   reality:      BV1jt411m7rn = "【fl原创音乐】 Unreal Rainbow 不知道做的是什么鬼.."
#                                by 冰之龙晶, 3:12, 271 views  (a music video)
#
# It also presented 12 invented "episodes" pointing at ?p=1..12 of that video, and
# the UI told users to paste that BV id as the example. Any real metadata now
# comes from yt-dlp (see ytdlp_metadata / ytdlp_playlist); when nothing can be
# fetched the caller reports the BV id and says so, instead of inventing a title.


def parse_srt_to_transcript(srt_text):
    """Parses SRT format into timestamped text [MM:SS] Dialogue."""
    lines = srt_text.replace('\r\n', '\n').split('\n')
    cues = []
    i = 0
    time_pat = re.compile(r"(\d{2}):(\d{2}):(\d{2})[,\.]\d{3}\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,\.]\d{3}")
    
    while i < len(lines):
        line = lines[i].strip()
        m = time_pat.search(line)
        if m:
            h, m_val, s = m.group(1), m.group(2), m.group(3)
            ts = f"[{m_val}:{s}]"
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip() and not time_pat.search(lines[i]):
                clean_text = re.sub(r'<[^>]+>', '', lines[i].strip())
                if clean_text:
                    text_lines.append(clean_text)
                i += 1
            if text_lines:
                cues.append(f"{ts} {' '.join(text_lines)}")
        else:
            i += 1
    return '\n'.join(cues)

def parse_bilibili_subtitles(subtitle_url):
    """Downloads Bilibili JSON format subtitles and converts to timestamped transcript."""
    if not subtitle_url:
        return ""
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url
    
    req = urllib.request.Request(subtitle_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            body = data.get("body", [])
            cues = []
            for item in body:
                sec = int(item.get("from", 0))
                m_val = f"{sec // 60:02d}"
                s_val = f"{sec % 60:02d}"
                text = item.get("content", "").strip()
                if text:
                    cues.append(f"[{m_val}:{s_val}] {text}")
            return '\n'.join(cues)
    except Exception as e:
        print(f"[WARN] Error fetching Bilibili subtitle json: {e}")
        return ""

def fetch_scientific_american_info(url):
    """
    Tier 1 Resolver: Scientific American (科学美国人)
    Extracts official Megaphone / Omny CDN MP3 podcast streams and article transcripts.
    """
    clean_url = url.strip()
    title = "Scientific American · Science Quickly"
    author = "Scientific American"
    cover = "https://static.scientificamerican.com/dam/asset/d666c57a-f730-4e99-a70d-3552a4db8a75/2609_SQ_WED_FRIENDSHIP-1.png?w=1200"
    duration = "14 分钟"
    direct_mp3 = ""
    transcript = ""
    transcript_source = ""
    
    if clean_url.lower().endswith(".mp3") or ("traffic.megaphone.fm" in clean_url and ".mp3" in clean_url):
        direct_mp3 = clean_url
        title = "Scientific American · Science Quickly Podcast"
    else:
        try:
            req = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                
                # Title
                t_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                if t_match:
                    title = t_match.group(1).split("|")[0].replace("Scientific American", "").strip() or title
                
                # Direct Megaphone MP3 CDN link
                mp3_matches = re.findall(r'https?://traffic\.megaphone\.fm/[^\s"\'<>]+\.mp3', html)
                if not mp3_matches:
                    mp3_matches = re.findall(r'https?://[^\s"\'<>]+\.mp3[^\s"\'<>]*', html)
                if mp3_matches:
                    direct_mp3 = mp3_matches[0]
                    
                # Cover image
                img_match = re.search(r'<meta property="og:image" content="([^"]+)"', html)
                if img_match:
                    cover = img_match.group(1)
                    
                # Article paragraphs are real fetched text, but they are NOT
                # audio-aligned dialogue: the old code stamped invented
                # "[00:00]-style" timestamps on them, which made a written
                # article look like a transcript. Keep the text, drop the fake
                # timings, and label the source honestly.
                paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
                clean_paras = []
                for p in paragraphs[:15]:
                    cp = re.sub(r'<[^>]+>', '', p).strip()
                    if len(cp) > 50 and not cp.startswith("©") and "Scientific American" not in cp:
                        clean_paras.append(cp)
                if clean_paras:
                    transcript = '\n'.join(clean_paras[:8])
                    transcript_source = "article_text"
        except Exception as e:
            print(f"[WARN] SciAm live parse warning: {e}")

    # If live extraction didn't find mp3, engage curated fallback
    if not direct_mp3:
        matched_fb = SCIAM_FALLBACK_CATALOG[0]
        for fb in SCIAM_FALLBACK_CATALOG:
            if fb["url_match"] in clean_url.lower():
                matched_fb = fb
                break
        title = matched_fb["title"] if title == "Scientific American · Science Quickly" else title
        direct_mp3 = matched_fb["direct_mp3"]
        cover = matched_fb["cover"]
        duration = matched_fb["duration"]
        # `demo_transcript` is sample text and is deliberately NOT used here.

    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', title).strip('_')[:40]
    stream_download_url = f"/api/media/stream-download?url={urllib.parse.quote(direct_mp3)}&filename={safe_name}.mp3&media_type=audio&platform=sciam"

    return {
        "platform": "scientific_american",
        "platform_name": "Scientific American (科学美国人)",
        "platform_icon": "fa-solid fa-atom",
        "title": title,
        "author": author,
        "cover": cover,
        "duration": duration,
        "media_type": "audio",
        "direct_media_url": direct_mp3,
        "download_url": stream_download_url,
        "tier_used": "Tier 1: 官方原装播客 CDN 直链 (Megaphone 无损秒发)",
        "status": "ready",
        **_transcript_fields(transcript, transcript_source or "fetched"),
    }

def _bili_target(url_or_bvid):
    """(bvid, canonical_url, page_number) for a Bilibili link or a bare BV id."""
    m = re.search(r"(BV[0-9A-Za-z]{10})", str(url_or_bvid))
    if not m:
        return "", "", 1
    bvid = m.group(1)
    page = 1
    pm = re.search(r"[?&]p=(\d+)", str(url_or_bvid))
    if pm:
        page = max(1, int(pm.group(1)))
    url = "https://www.bilibili.com/video/%s" % bvid
    if page > 1:
        url += "?p=%d" % page
    return bvid, url, page


def _bili_api_view(bvid):
    """Official view API. Returns {} when Bilibili risk-controls us (HTTP 412)."""
    api_url = "https://api.bilibili.com/x/web-interface/view?bvid=%s" % bvid
    req = urllib.request.Request(api_url, headers={
        "User-Agent": USER_AGENT,
        "Referer": "https://www.bilibili.com",
        "Cookie": "buvid3=F8B7B618-6A47-19B4-0994-39908FEE998188198infoc;",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status != 200:
                return {}
            body = resp.read()
            if not body.lstrip().startswith(b"{"):
                return {}
            res = json.loads(body.decode("utf-8"))
            return res.get("data", {}) if res.get("code") == 0 else {}
    except Exception as exc:  # noqa: BLE001 - a 412 risk-control block lands here
        print("[WARN] Bilibili view API unavailable (%s); relying on yt-dlp"
              % type(exc).__name__)
        return {}


def fetch_bilibili_video_info(url_or_bvid):
    """Real Bilibili metadata and real subtitles. Neither is ever invented.

    api.bilibili.com/x/web-interface/view answers HTTP 412 (risk control) from
    this host, which is why the previous implementation fell through to a
    hardcoded title - "Bilibili 经典公开课深度精讲 (BVxxx)" - a fabricated
    description of whatever the video actually was (the reported bug: a Planet
    Money podcast episode came back looking like a Harvard lecture). yt-dlp reads
    Bilibili fine from here, so it is the primary source and the API is a
    fallback. When both fail, the caller gets the BV id and an explicit notice.
    """
    bvid, target, page = _bili_target(url_or_bvid)
    if not bvid:
        return None

    meta = ytdlp_metadata(target)
    source = "yt-dlp" if meta else ""
    api = {} if meta else _bili_api_view(bvid)
    if api:
        source = "bilibili_api"

    title = (meta.get("title") or api.get("title") or "").strip()
    author = (meta.get("uploader") or api.get("owner", {}).get("name") or "").strip()
    cover = (meta.get("thumbnail") or api.get("pic") or "").strip()
    seconds = meta.get("duration") or api.get("duration") or 0
    duration_str = ("%d 分钟" % (seconds // 60)) if seconds else ""

    transcript, tsrc = ytdlp_transcript(target)
    if not transcript:
        subs = (api.get("subtitle") or {}).get("subtitles") or []
        chosen = None
        for s in subs:
            if "en" in s.get("lan", "") or "英" in s.get("lan_doc", ""):
                chosen = s
                break
        chosen = chosen or (subs[0] if subs else None)
        if chosen:
            transcript = parse_bilibili_subtitles(chosen.get("subtitle_url", ""))
            tsrc = "bilibili_cc" if transcript else ""

    safe_title = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fa5-]", "_",
                        title or bvid).strip("_")[:40]
    stream_download_url = (
        "/api/media/stream-download?url=%s&filename=%s.mp3"
        "&media_type=audio&platform=bilibili"
        % (urllib.parse.quote(target), safe_title))

    return {
        "platform": "bilibili",
        "platform_name": "Bilibili (哔哩哔哩)",
        "platform_icon": "fa-brands fa-bilibili",
        "video_id": bvid,
        # Either the real title or the id itself - never a descriptive guess.
        "title": title or bvid,
        "author": author or "未知 UP 主",
        "cover": cover or "/assets/scenes/banner_harvard_series.jpg",
        "duration": duration_str or "时长未知",
        "media_type": "audio",
        "direct_media_url": target,
        "download_url": stream_download_url,
        "page": page,
        "metadata_source": source or "unavailable",
        "metadata_notice": "" if source else
        "未能获取该视频的真实标题与作者（B 站接口风控、yt-dlp 亦失败），"
        "因此只显示 BV 号，不猜测视频内容。",
        "tier_used": "Tier 2: yt-dlp 元数据/字幕解析（官方 API 风控时回退）",
        "status": "ready",
        **_transcript_fields(transcript, tsrc),
    }


def detect_bilibili_collection(url_or_bvid):
    """Is this link a multi-part video or a season? Answered with real data only.

    yt-dlp's flat playlist gives the real entry titles and urls; the official API
    (ugc_season / pages) is the fallback. There is deliberately NO curated
    fallback catalog: the one that used to exist here was fabricated, and the UI
    advertised its BV id as the paste-me example.
    """
    bvid, target, page = _bili_target(url_or_bvid)
    if not bvid:
        return {"success": False, "is_collection": False,
                "error": "未能在链接中找到有效的 Bilibili BV号"}

    entries = ytdlp_playlist(target)
    if len(entries) > 1:
        eps = []
        for i, e in enumerate(entries, 1):
            ep_url = e.get("url") or ""
            if ep_url and not ep_url.startswith("http"):
                ep_url = "https://www.bilibili.com/video/%s" % ep_url
            if not ep_url:
                ep_url = target if i == 1 else "%s?p=%d" % (target, i)
            dur = e.get("duration") or 0
            eps.append({
                "page": i,
                "title": (e.get("title") or "第%d集" % i).strip(),
                "bvid": e.get("id") or bvid,
                "duration": ("%d 分钟" % (dur // 60)) if dur else "",
                "url": ep_url,
                "platform": "bilibili",
            })
        return {
            "success": True,
            "is_collection": True,
            "collection_type": "multi_part",
            "collection_title": (entries[0].get("playlist_title")
                                 or entries[0].get("title") or bvid),
            "total_episodes": len(eps),
            "author": entries[0].get("uploader") or "",
            "bvid": bvid,
            "episodes": eps,
            "tier_used": "Tier 2: yt-dlp 分P/合集真实展开",
        }

    # Fallback: the official API can still describe seasons/multi-page videos.
    api = _bili_api_view(bvid)
    pages = api.get("pages") or []
    if len(pages) > 1:
        eps = []
        for p in pages:
            p_num = p.get("page", 1)
            part = (p.get("part") or "").strip() or "第%d部分" % p_num
            dur = p.get("duration", 0)
            eps.append({
                "page": p_num,
                "title": "第%d集 %s" % (p_num, part),
                "bvid": bvid,
                "duration": ("%d 分钟" % (dur // 60)) if dur else "",
                "url": "https://www.bilibili.com/video/%s?p=%d" % (bvid, p_num),
                "platform": "bilibili",
            })
        return {
            "success": True, "is_collection": True, "collection_type": "multi_page",
            "collection_title": api.get("title") or bvid,
            "total_episodes": len(eps),
            "author": api.get("owner", {}).get("name") or "",
            "cover": api.get("pic") or "",
            "bvid": bvid, "episodes": eps,
            "tier_used": "Tier 2: 哔哩哔哩官方 Multi-page 分P解析",
        }
    ugc = api.get("ugc_season") or {}
    if ugc.get("sections"):
        eps, idx = [], 1
        for sec in ugc.get("sections", []):
            for ep in sec.get("episodes", []):
                ep_bvid = ep.get("bvid", bvid)
                dur = ep.get("arc", {}).get("duration", 0)
                eps.append({
                    "page": idx,
                    "title": (ep.get("title") or "第%d集" % idx).strip(),
                    "bvid": ep_bvid,
                    "duration": ("%d 分钟" % (dur // 60)) if dur else "",
                    "url": "https://www.bilibili.com/video/%s" % ep_bvid,
                    "platform": "bilibili",
                })
                idx += 1
        if len(eps) > 1:
            return {
                "success": True, "is_collection": True,
                "collection_type": "ugc_season",
                "collection_title": ugc.get("title") or api.get("title") or bvid,
                "total_episodes": len(eps),
                "author": api.get("owner", {}).get("name") or "",
                "cover": api.get("pic") or "",
                "bvid": bvid, "episodes": eps,
                "tier_used": "Tier 2: 哔哩哔哩官方 UGC Season 合集解析",
            }

    info = fetch_bilibili_video_info(target) or {}
    return {
        "success": True, "is_collection": False, "collection_type": "single",
        "collection_title": info.get("title") or bvid,
        "total_episodes": 1,
        "author": info.get("author") or "",
        "cover": info.get("cover") or "",
        "bvid": bvid,
        "duration": info.get("duration") or "",
        "has_subtitles": bool(info.get("has_subtitles")),
        "transcript_source": info.get("transcript_source", "unavailable"),
        "subtitle_notice": info.get("subtitle_notice", ""),
        "metadata_source": info.get("metadata_source", "unavailable"),
        "episodes": [{
            "page": page,
            "title": info.get("title") or bvid,
            "bvid": bvid,
            "duration": info.get("duration") or "",
            "url": target,
        }],
        "tier_used": "Tier 2: 单视频（yt-dlp 已校验，无分P/合集）",
    }

def fetch_youtube_video_info(url):
    """
    Tier 2 & 3 Resolver: YouTube
    Metadata via oEmbed & direct audio stream pipeline via multi-client spoofing.
    """
    m = re.search(r"(?:v=|\/|be\/)([0-9A-Za-z_-]{11})", url)
    if not m:
        return None
    vid = m.group(1)
    yt_full_url = f"https://www.youtube.com/watch?v={vid}"
    oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(yt_full_url)}&format=json"
    req = urllib.request.Request(oembed_url, headers={"User-Agent": USER_AGENT})
    
    title = f"YouTube 公开课精读 ({vid})"
    author = "YouTube Academic"
    cover = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
    
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            title = data.get("title", title)
            author = data.get("author_name", author)
    except Exception as e:
        print(f"[WARN] YouTube oEmbed fetch error: {e}")

    # Fetch the real subtitle track instead of shipping a canned paragraph.
    transcript, transcript_source = fetch_youtube_transcript(vid)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', title).strip('_')[:40]
    stream_download_url = f"/api/media/stream-download?url={urllib.parse.quote(yt_full_url)}&filename={safe_title}.mp3&media_type=audio&platform=youtube"

    return {
        "platform": "youtube",
        "platform_name": "YouTube (全球公开课与讲座)",
        "platform_icon": "fa-brands fa-youtube",
        "video_id": vid,
        "title": title,
        "author": author,
        "cover": cover,
        "duration": "52 分钟",
        "media_type": "audio",
        "direct_media_url": yt_full_url,
        "download_url": stream_download_url,
        "tier_used": "Tier 2: yt-dlp Android/iOS 移动协议伪装 (免登录人机拦截)",
        "status": "ready",
        **_transcript_fields(transcript, transcript_source),
    }

def fetch_direct_media_info(url):
    """
    Handles direct media files (.mp3, .mp4, .m4a, megaphone.fm, etc.)
    """
    clean_url = url.strip()
    filename = os.path.basename(urllib.parse.urlparse(clean_url).path) or "extracted_media"
    title = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title() or "Direct Audio Stream"
    is_video = any(clean_url.lower().endswith(ext) for ext in [".mp4", ".mkv", ".webm", ".mov"])
    media_type = "video" if is_video else "audio"

    stream_download_url = f"/api/media/stream-download?url={urllib.parse.quote(clean_url)}&filename={filename}&media_type={media_type}&platform=direct"

    # A bare media URL carries no text at all; say so rather than inventing one.
    return {
        "platform": "direct_media",
        "platform_name": "Direct Media Stream (直链音频/视频)",
        "platform_icon": "fa-solid fa-file-audio" if not is_video else "fa-solid fa-file-video",
        "title": title,
        "author": "Direct Web Stream",
        "cover": "/assets/scenes/banner_harvard_series.jpg",
        "duration": "音频原声",
        "media_type": media_type,
        "direct_media_url": clean_url,
        "download_url": stream_download_url,
        "tier_used": "Tier 1: 原始 HTTP/HTTPS 流媒体直达通道",
        "status": "ready",
        **_transcript_fields("", ""),
    }

def fetch_direct_subtitles(url):
    """Downloads subtitles from direct URL or DownSub link."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            if url.endswith(".json") or raw.strip().startswith("{") or raw.strip().startswith("["):
                try:
                    data = json.loads(raw)
                    if isinstance(data, dict) and "body" in data:
                        cues = [f"[{int(c.get('from', 0))//60:02d}:{int(c.get('from', 0))%60:02d}] {c.get('content', '')}" for c in data["body"]]
                        return '\n'.join(cues)
                except:
                    pass
            return parse_srt_to_transcript(raw) or raw
    except Exception as e:
        print(f"[WARN] Direct subtitle fetch error: {e}")
        return ""

def auto_fetch_subtitles_and_meta(url):
    """Unified single-URL dispatcher."""
    url = url.strip()
    if not url:
        return {"success": False, "error": "URL 不能为空"}
    
    # 1. Scientific American
    if "scientificamerican.com" in url or "traffic.megaphone.fm" in url:
        info = fetch_scientific_american_info(url)
        if info:
            return {"success": True, **info}

    # 2. Bilibili
    if "bilibili.com" in url or re.search(r"BV[0-9A-Za-z]{10}", url):
        info = fetch_bilibili_video_info(url)
        if info:
            return {"success": True, **info}
    
    # 3. YouTube
    if "youtube.com" in url or "youtu.be" in url:
        info = fetch_youtube_video_info(url)
        if info:
            return {"success": True, **info}
            
    # 4. Direct Media (.mp3, .mp4, .m4a)
    if any(url.lower().endswith(ext) for ext in [".mp3", ".mp4", ".m4a", ".wav", ".aac"]):
        info = fetch_direct_media_info(url)
        if info:
            return {"success": True, **info}

    # 5. Direct Subtitle URL
    if any(url.lower().endswith(ext) for ext in [".srt", ".vtt", ".txt", ".json"]) or "downsub.com" in url:
        txt = fetch_direct_subtitles(url)
        if txt:
            return {
                "success": True,
                "platform": "direct_subtitle",
                "title": "已提取的字幕逐字稿",
                "author": "公开课原声字幕",
                "cover": "/assets/scenes/banner_harvard_series.jpg",
                "duration": "45 分钟",
                "transcript": txt,
                "has_subtitles": True,
                "transcript_source": "direct_subtitle",
                "tier_used": "Tier 1: 字幕文件直连解析"
            }
            
    return {
        "success": False,
        "error": "未识别的音视频或字幕网址，系统支持科学美国人播客、YouTube、Bilibili 及 Direct MP3 链接"
    }

def batch_resolve_media(raw_urls_input, mode="media", media_type="audio", auto_expand_collections=True):
    """
    Batch Dispatcher & Multi-Tier Fallback Resolver
    Accepts raw string with multiple URLs (one per line) or list of URLs.
    If auto_expand_collections is True, any single Bilibili URL belonging to a
    collection/series is automatically unpacked into its full episode list!
    """
    if isinstance(raw_urls_input, str):
        lines = [line.strip() for line in raw_urls_input.replace('\r\n', '\n').split('\n')]
    else:
        lines = [str(u).strip() for u in raw_urls_input]

    valid_urls = [u for u in lines if u.startswith("http://") or u.startswith("https://") or re.search(r"BV[0-9A-Za-z]{10}", u)]
    
    results = []
    collections_detected = []
    item_counter = 1

    for u in valid_urls:
        # Check if single Bilibili URL belongs to a multi-part collection
        is_bili = ("bilibili.com" in u or bool(re.search(r"BV[0-9A-Za-z]{10}", u)))
        if auto_expand_collections and is_bili:
            try:
                col = detect_bilibili_collection(u)
                if col.get("is_collection") and len(col.get("episodes", [])) > 1:
                    collections_detected.append({
                        "bvid": col.get("bvid", ""),
                        "title": col.get("collection_title", "合集"),
                        "total_episodes": col.get("total_episodes", len(col.get("episodes", []))),
                        "collection_type": col.get("collection_type", "multi_page")
                    })
                    
                    for ep in col["episodes"]:
                        ep_title = ep.get("title", "公开课分集")
                        safe_title = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5-]', '_', ep_title).strip('_')[:40]
                        stream_download_url = f"/api/media/stream-download?url={urllib.parse.quote(ep['url'])}&filename={safe_title}.mp3&media_type={media_type}&platform=bilibili"
                        
                        results.append({
                            "index": item_counter,
                            "req_mode": mode,
                            "platform": "bilibili",
                            "platform_name": "Bilibili (全集合集自动展开)",
                            "platform_icon": "fa-brands fa-bilibili",
                            "video_id": ep.get("bvid", col.get("bvid", "")),
                            "title": ep_title,
                            "author": col.get("author", "Bilibili 主讲教授"),
                            "cover": ep.get("cover") or col.get("cover", "/assets/scenes/banner_harvard_series.jpg"),
                            "duration": ep.get("duration", "55 分钟"),
                            "media_type": media_type,
                            "direct_media_url": ep["url"],
                            "download_url": stream_download_url,
                            "is_collection_item": True,
                            "collection_title": col.get("collection_title"),
                            "collection_total": col.get("total_episodes"),
                            "episode_page": ep.get("page", 1),
                            "tier_used": col.get("tier_used", "Tier 3: B站单链接自动识别全集合集展开"),
                            "status": "ready",
                            "success": True,
                            # Expanding a collection yields URLs, not text. Each
                            # episode's subtitles must be fetched individually;
                            # until then its transcript is honestly empty.
                            **_transcript_fields(ep.get("transcript", ""),
                                                 ep.get("transcript_source", "")),
                        })
                        item_counter += 1
                    continue
            except Exception as ce:
                print(f"[WARN] Error expanding collection for {u}: {ce}")

        # Standard single URL resolution
        try:
            item = auto_fetch_subtitles_and_meta(u)
            if item.get("success"):
                item["index"] = item_counter
                item["req_mode"] = mode
                results.append(item)
                item_counter += 1
            else:
                results.append({
                    "index": item_counter,
                    "url": u,
                    "success": False,
                    "title": f"解析失败 ({u[:30]}...)",
                    "error": item.get("error", "未知解析异常")
                })
                item_counter += 1
        except Exception as e:
            results.append({
                "index": item_counter,
                "url": u,
                "success": False,
                "title": f"解析异常 ({u[:30]}...)",
                "error": str(e)
            })
            item_counter += 1

    return {
        "success": True,
        "total_requested": len(valid_urls),
        "resolved_count": len([r for r in results if r.get("success")]),
        "items": results,
        "collections_detected": collections_detected
    }

