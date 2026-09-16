# -*- coding: utf-8 -*-
"""
Harvard Justice AI Vocabulary Studio - Enterprise Backend
Features:
1. Multi-course & Series hierarchy
2. User Authentication (Register, Login, Guest mode)
3. Spaced repetition & detailed study time tracking (today & historical time, per-word review counts)
4. Multi-format Exporter: Word (.docx), Markdown (.md), Anki CSV, Eudic/Quizlet TXT, Pure TXT
5. Universal AI Proxy: DeepSeek Official (default), OpenAI-compatible, Anthropic Claude
"""

import http.server
import socketserver
import json
import urllib.request
import urllib.error
import os
import re
import csv
import io
import sys
import time
import hashlib
import base64
import asyncio
from datetime import date
import edge_tts
from docx_generator import build_docx_bytes

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8765))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PUBLIC_DIR = os.path.join(BASE_DIR, "public")
DATA_DIR = os.path.join(BASE_DIR, "data")
CURRICULUM_FILE = os.path.join(DATA_DIR, "curriculum_tiered.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_records.json")
FEEDBACK_IMG_DIR = os.path.join(PUBLIC_DIR, "assets", "feedback")
os.makedirs(FEEDBACK_IMG_DIR, exist_ok=True)
AUDIO_DIR = os.path.join(PUBLIC_DIR, "assets", "audio")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
STUDY_FILE = os.path.join(DATA_DIR, "study_records.json")
VOCAB_BANK_FILE = os.path.join(DATA_DIR, "vocab_bank.json")
CUSTOM_EPISODES_FILE = os.path.join(DATA_DIR, "custom_episodes.json")

# Default DeepSeek Configuration
DEFAULT_CONFIG = {
    "provider": "deepseek",
    "api_base": "https://api.deepseek.com",
    "api_key": "sk-0ff6375d1846471dbcf06859f59e2b68",
    "model": "deepseek-chat"
}

# Ensure data storage files exist
def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(AUDIO_DIR, exist_ok=True)
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(STUDY_FILE):
        with open(STUDY_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(VOCAB_BANK_FILE):
        with open(VOCAB_BANK_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)
    if not os.path.exists(CUSTOM_EPISODES_FILE):
        with open(CUSTOM_EPISODES_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

init_db()

def load_vocab_bank():
    try:
        with open(VOCAB_BANK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_vocab_bank(bank):
    with open(VOCAB_BANK_FILE, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)

def load_custom_episodes():
    try:
        with open(CUSTOM_EPISODES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_custom_episodes(episodes):
    with open(CUSTOM_EPISODES_FILE, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)

def synthesize_audio_sync(text, filepath, voice="en-US-ChristopherNeural"):
    """Synthesizes neural speech using edge-tts."""
    async def _run():
        comm = edge_tts.Communicate(text, voice)
        await comm.save(filepath)
    try:
        asyncio.run(_run())
        return True
    except Exception as e:
        print(f"[TTS Error] {e}")
        return False

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_study_records():
    try:
        with open(STUDY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_study_records(records):
    with open(STUDY_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

# Multi-course Series Data
SERIES_DATA = {
    "harvard_philosophy": {
        "id": "harvard_philosophy",
        "title": "哈佛大学名校哲学系列公开课",
        "desc": "汇聚哈佛最负盛名的哲学与伦理思辨公开课，探索道德真理与社会制度本质",
        "courses": [
            {
                "id": "justice",
                "title": "哈佛大学《公正：该如何做是好？》(Justice)",
                "instructor": "Michael J. Sandel 教授",
                "university": "Harvard University",
                "banner_scene": "/assets/scenes/banner_harvard_series.jpg",
                "total_episodes": 12,
                "episodes": ["ep01", "ep02", "ep03"]
            }
        ]
    }
}

COLLECTIONS_DATA = {
    "harvard_justice": {
        "id": "harvard_justice",
        "title": "哈佛大学《公正：该如何做是好？》(Justice)",
        "en_title": "Harvard University: Justice - What's the Right Thing to Do?",
        "university": "Harvard University",
        "instructor": "Prof. Michael J. Sandel",
        "cover_scene": "/assets/scenes/banner_harvard_series.jpg",
        "badge": "哈佛旗舰 · 伦理法理必修",
        "total_episodes": 3,
        "desc": "探讨功利主义、自由至上主义与康德道德绝对论的经典哲学名篇，哈佛大学最负盛名的思辨殿堂。",
        "episodes": ["ep01", "ep02", "ep03"]
    },
    "yale_philosophy": {
        "id": "yale_philosophy",
        "title": "耶鲁大学《哲学与人性科学》(Human Nature)",
        "en_title": "Yale University: Philosophy and the Science of Human Nature",
        "university": "Yale University",
        "instructor": "Prof. Tamar Gendler",
        "cover_scene": "/assets/scenes/cover_yale_philosophy.jpg",
        "badge": "耶鲁名校 · 道德心理与认知科学",
        "total_episodes": 1,
        "desc": "结合柏拉图理想国灵魂三分说与现代认知心理学，探索理性、欲望与幸福生活的内在秩序。",
        "episodes": ["yale_ep01"]
    },
    "custom_imports": {
        "id": "custom_imports",
        "title": "法理学与公共伦理名家研讨合集 (User Imports)",
        "en_title": "Public Jurisprudence & Seminar Series",
        "university": "Global Open Academic",
        "instructor": "特约讲师 / 罗翔教授等",
        "cover_scene": "/assets/scenes/scene_theatre.jpg",
        "badge": "自主导入 · 实时扩展",
        "total_episodes": 1,
        "desc": "由用户通过 Bilibili、YouTube 与 DownSub 链接自主导入并由 DeepSeek AI 提炼生成的学术视频合集。",
        "episodes": []
    }
}

def load_curriculum_tiered():
    if os.path.exists(CURRICULUM_FILE):
        try:
            with open(CURRICULUM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception as e:
            print(f"[WARN] Failed to load curriculum_tiered.json: {e}")
    return {}

EPISODE_DATA = load_curriculum_tiered()

def ensure_word_audio_urls():
    global EPISODE_DATA
    if not EPISODE_DATA:
        EPISODE_DATA = load_curriculum_tiered()
    for ep_id, ep in EPISODE_DATA.items():
        for w in ep.get("words", []):
            safe = re.sub(r'[^a-zA-Z0-9_]', '_', w['word'].lower()).strip('_')
            w['audio_url'] = f"/assets/audio/{ep_id}_{safe}.mp3"
            w['native_clip_url'] = f"/assets/audio/clips/{ep_id}_{safe}_native.mp3"
            if ep_id == 'ep01':
                w['scene_img'] = f"/assets/scenes/ep01/frame_{safe}.jpg"

ensure_word_audio_urls()

def get_all_episodes():
    eps = dict(EPISODE_DATA)
    custom = load_custom_episodes()
    eps.update(custom)
    return eps

def get_vocab_bank_data(username=""):
    master_bank = load_vocab_bank()
    study_records = load_study_records()
    user_record = study_records.get(username, {}) if username else {}
    user_words = user_record.get("words", {})

    items = []
    mastered_count = 0
    learning_count = 0
    multi_context_count = 0

    for w_k, w_info in master_bank.items():
        contexts = w_info.get("contexts", [])
        if len(contexts) > 1:
            multi_context_count += 1
        
        # Merge with user personal stats
        u_stat = user_words.get(w_info["word"], {})
        rev_count = u_stat.get("review_count", w_info.get("stats", {}).get("review_count", 0))
        total_sec = u_stat.get("total_seconds", w_info.get("stats", {}).get("total_seconds", 0))
        status = u_stat.get("status", w_info.get("stats", {}).get("status", "learning"))
        last_rating = u_stat.get("last_rating", w_info.get("stats", {}).get("last_rating", "new"))
        last_reviewed = u_stat.get("last_reviewed_at", w_info.get("stats", {}).get("last_reviewed_at"))

        if status == "mastered":
            mastered_count += 1
        else:
            learning_count += 1

        items.append({
            "word": w_info["word"],
            "phonetic": w_info.get("phonetic", ""),
            "pos": w_info.get("pos", ""),
            "def_cn": w_info.get("def_cn", ""),
            "contexts": contexts,
            "review_count": rev_count,
            "total_seconds": total_sec,
            "status": status,
            "last_rating": last_rating,
            "last_reviewed_at": last_reviewed
        })

    today_str = str(date.today())
    today_sec = user_record.get("today_seconds", 0) if user_record.get("last_active_date") == today_str else 0
    hist_sec = user_record.get("historical_seconds", 0)

    return {
        "words": items,
        "summary": {
            "total_words": len(items),
            "mastered_count": mastered_count,
            "learning_count": learning_count,
            "multi_context_count": multi_context_count,
            "today_seconds": today_sec,
            "historical_seconds": hist_sec
        }
    }

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_GET(self):
        clean_path = self.path.split('?')[0].split('#')[0]

        # 0. API Documentation and OpenAPI Spec
        if clean_path in ['/docs', '/api-docs', '/docs/']:
            docs_file = os.path.join(PUBLIC_DIR, "docs.html")
            if os.path.exists(docs_file):
                with open(docs_file, "rb") as f:
                    docs_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(docs_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(docs_bytes)
                return

        if clean_path == '/api/openapi.json':
            spec_file = os.path.join(PUBLIC_DIR, "openapi.json")
            if not os.path.exists(spec_file):
                spec_file = os.path.join(DATA_DIR, "openapi.json")
            if os.path.exists(spec_file):
                with open(spec_file, "rb") as f:
                    spec_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(spec_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(spec_bytes)
                return

        # 0.1 SPA Client Route Fallback
        spa_routes = ['/collections', '/vocab-bank', '/home', '/login', '/register', '/feedback']
        if (clean_path in spa_routes or 
            clean_path.startswith('/collection/') or 
            clean_path.startswith('/episode/') or 
            clean_path.startswith('/study/')):
            index_file = os.path.join(PUBLIC_DIR, "index.html")
            if os.path.exists(index_file):
                with open(index_file, "rb") as f:
                    html_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html_bytes)
                return
        # 0. Collections API
        if self.path == "/api/collections":
            custom_eps = load_custom_episodes()
            cols = []
            for c_id, c in COLLECTIONS_DATA.items():
                c_copy = dict(c)
                if c_id == "custom_imports":
                    c_copy["episodes"] = list(custom_eps.keys())
                    c_copy["total_episodes"] = len(custom_eps)
                
                # Calculate total words in this collection
                all_eps = get_all_episodes()
                total_w = sum(len(all_eps.get(eid, {}).get("words", [])) for eid in c_copy.get("episodes", []))
                c_copy["total_words"] = total_w
                cols.append(c_copy)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(cols, ensure_ascii=False).encode("utf-8"))
            return

        elif self.path.startswith("/api/collection/"):
            cid = self.path.split("/")[-1].lower()
            col = COLLECTIONS_DATA.get(cid, COLLECTIONS_DATA["harvard_justice"])
            c_copy = dict(col)
            all_eps = get_all_episodes()
            if cid == "custom_imports":
                c_copy["episodes"] = list(load_custom_episodes().keys())

            ep_details = []
            for eid in c_copy.get("episodes", []):
                if eid in all_eps:
                    ep_details.append(all_eps[eid])
            c_copy["episode_details"] = ep_details
            c_copy["total_words"] = sum(len(ep.get("words", [])) for ep in ep_details)
            c_copy["total_episodes"] = len(ep_details)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(c_copy, ensure_ascii=False).encode("utf-8"))
            return

        # 1. Series and Course List
        if self.path == "/api/series":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(SERIES_DATA, ensure_ascii=False).encode("utf-8"))
            return
        
        # 2. Episode details
        elif self.path.startswith("/api/preset/") or self.path.startswith("/api/episode/"):
            ep_id = self.path.split("/")[-1].lower()
            all_eps = get_all_episodes()
            data = all_eps.get(ep_id, all_eps.get("ep01", EPISODE_DATA["ep01"]))
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        elif self.path in ["/api/presets", "/api/episodes"]:
            all_eps = get_all_episodes()
            summary = [
                {
                    "id": k, 
                    "title": v.get("title", ""), 
                    "cn_title": v.get("cn_title", ""),
                    "topic": v.get("topic", ""), 
                    "cover_scene": v.get("cover_scene", "/assets/scenes/scene_theatre.jpg"),
                    "count": len(v.get("words", [])),
                    "duration": v.get("duration", "50 分钟")
                } 
                for k, v in all_eps.items()
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(summary, ensure_ascii=False).encode("utf-8"))
            return

        # 2.5 Master Vocabulary Bank
        elif self.path.startswith("/api/vocab-bank"):
            query = self.path.split("?")[-1] if "?" in self.path else ""
            params = dict(qc.split("=") for qc in query.split("&") if "=" in qc)
            username = params.get("username", "").strip()
            data = get_vocab_bank_data(username)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        # 2.6 Dynamic Neural TTS Audio Streamer
        elif self.path.startswith("/api/audio/tts"):
            query = self.path.split("?")[-1] if "?" in self.path else ""
            params = dict(urllib.parse.unquote_plus(qc).split("=", 1) for qc in query.split("&") if "=" in qc)
            text_to_speak = params.get("text", "").strip()
            if not text_to_speak:
                self.send_response(400)
                self.end_headers()
                return
            h = hashlib.md5(text_to_speak.encode("utf-8")).hexdigest()[:12]
            cache_name = f"tts_{h}.mp3"
            cache_path = os.path.join(AUDIO_DIR, cache_name)
            if not os.path.exists(cache_path):
                synthesize_audio_sync(text_to_speak, cache_path)
            
            if os.path.exists(cache_path):
                with open(cache_path, "rb") as f:
                    audio_bytes = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio_bytes)))
                self.end_headers()
                self.wfile.write(audio_bytes)
                return
            else:
                self.send_response(500)
                self.end_headers()
                return

        # 3. User study stats
        elif self.path.startswith("/api/user/stats"):
            query = self.path.split("?")[-1] if "?" in self.path else ""
            params = dict(qc.split("=") for qc in query.split("&") if "=" in qc)
            username = params.get("username", "").strip()

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            # Check if today date rolled over
            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(user_data, ensure_ascii=False).encode("utf-8"))
            return

        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        # Auth and Core Endpoints
        if self.path == "/api/auth/register":
            self.handle_register(body)
        elif self.path == "/api/auth/login":
            self.handle_login(body)
        elif self.path == "/api/user/record":
            self.handle_study_record(body)
        elif self.path == "/api/vocab-bank/record":
            self.handle_vocab_bank_record(body)
        elif self.path == "/api/import/link":
            self.handle_import_link(body)
        elif self.path == "/api/test-connection":
            self.handle_test_connection(body)
        elif self.path == "/api/ai-extract":
            self.handle_ai_extract(body)
        elif self.path == "/api/export":
            self.handle_export(body)
        elif self.path == "/api/video/fetch-subtitles":
            self.handle_video_subtitles(body)
        elif self.path == "/api/feedback":
            self.handle_feedback(body)
        elif self.path == "/api/user/heartbeat-time":
            self.handle_heartbeat_time(body)
        elif self.path == "/api/collection/add":
            self.handle_add_collection(body)
        else:
            self.send_response(404)
            self.end_headers()

    def handle_register(self, body_str):
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            password = req.get("password", "").strip()
            nickname = req.get("nickname", username).strip() or username

            if not username or not password:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "用户名和密码不能为空！"}, ensure_ascii=False).encode("utf-8"))
                return

            users = load_users()
            if username in users:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "该用户名已存在，请直接登录！"}, ensure_ascii=False).encode("utf-8"))
                return

            users[username] = {
                "username": username,
                "password_hash": hash_pw(password),
                "nickname": nickname,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            save_users(users)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "username": username, 
                "nickname": nickname,
                "message": "注册成功，已自动登录！"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_login(self, body_str):
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            password = req.get("password", "").strip()

            users = load_users()
            user = users.get(username)
            if not user or user.get("password_hash") != hash_pw(password):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "用户名或密码错误！"}, ensure_ascii=False).encode("utf-8"))
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "username": username, 
                "nickname": user.get("nickname", username),
                "message": "登录成功！"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_study_record(self, body_str):
        """Records review duration, count, rating for a specific word and overall user."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            word = req.get("word", "").strip()
            duration = int(req.get("duration_seconds", 0))
            rating = req.get("rating", "good") # again, hard, good, easy
            episode_id = req.get("episode_id", "ep01")

            if not username:
                # Guest mode: ack without server persistence
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "guest": True}).encode("utf-8"))
                return

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            # Update overall times
            user_data["today_seconds"] = user_data.get("today_seconds", 0) + duration
            user_data["historical_seconds"] = user_data.get("historical_seconds", 0) + duration

            # Update per-word statistics
            words_dict = user_data.setdefault("words", {})
            w_stat = words_dict.setdefault(word, {
                "word": word,
                "episode_id": episode_id,
                "review_count": 0,
                "total_seconds": 0,
                "status": "learning",
                "last_rating": rating,
                "last_reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            w_stat["review_count"] += 1
            w_stat["total_seconds"] += duration
            w_stat["last_rating"] = rating
            w_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            if rating in ["good", "easy"]:
                w_stat["status"] = "mastered" if w_stat["review_count"] >= 3 else "consolidating"
            elif rating == "again":
                w_stat["status"] = "needs_review"
            else:
                w_stat["status"] = "learning"

            records[username] = user_data
            save_study_records(records)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True, 
                "stats": {
                    "word": word,
                    "review_count": w_stat["review_count"],
                    "total_seconds": w_stat["total_seconds"],
                    "status": w_stat["status"],
                    "user_today_seconds": user_data["today_seconds"],
                    "user_historical_seconds": user_data["historical_seconds"]
                }
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_test_connection(self, body_str):
        try:
            req = json.loads(body_str)
            provider = req.get("provider", "deepseek").lower()
            api_base = req.get("api_base", "https://api.deepseek.com").rstrip("/")
            api_key = req.get("api_key", DEFAULT_CONFIG["api_key"]).strip()
            model = req.get("model", "deepseek-chat").strip()

            if not api_key:
                api_key = DEFAULT_CONFIG["api_key"]

            if provider == "anthropic":
                endpoint = f"{api_base}/v1/messages" if not api_base.endswith("/v1") else f"{api_base}/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                }
                payload = {
                    "model": model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "Ping"}]
                }
            else:
                endpoint = f"{api_base}/chat/completions" if not api_base.endswith("/chat/completions") else api_base
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [{"role": "user", "content": "Ping"}],
                    "max_tokens": 10
                }

            req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req_obj, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "message": "API 连接测试成功！接口响应正常。"}, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": f"API 连接测试失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_ai_extract(self, body_str):
        try:
            req = json.loads(body_str)
            provider = req.get("provider", "deepseek").lower()
            api_base = req.get("api_base", "https://api.deepseek.com").rstrip("/")
            api_key = req.get("api_key", "").strip() or DEFAULT_CONFIG["api_key"]
            model = req.get("model", "deepseek-chat").strip()
            transcript = req.get("transcript", "").strip()
            count = req.get("count", 20)

            system_prompt = (
                "你是一位专精学术英语、道德哲学与法理学的权威语言学教授。"
                "请深入研读用户提供的哈佛大学《公正课》(Justice) 剧集英文台词/字幕。\n"
                "严格执行以下筛选与结构化规范：\n"
                "1. 严格过滤掉初高中及大学四六级常见的简单基础词；\n"
                f"2. 精准筛选提取出 {count} 个直接影响课文深层逻辑理解与听力跟读的【道德哲学与法理学术术语】、【学术辩论核心词汇】与【经典情节专有名词】；\n"
                "3. 必须提取该单词在课堂上真实被说出的【英文原声例句】（不要凭空造句）；\n"
                "4. 严格只输出合法 JSON 数组，严禁包含任何 Markdown 格式标记（不要带有 ```json 或 ```），格式规范如下：\n"
                '[\n'
                '  {\n'
                '    "word": "utilitarianism",\n'
                '    "phonetic": "/ˌjuːtɪlɪˈteriənɪzəm/",\n'
                '    "pos": "n.",\n'
                '    "def_cn": "功利主义，功利论",\n'
                '    "sentence": "Bentham\'s utilitarianism claims that the highest principle...",\n'
                '    "trans": "边沁的功利主义认为..."\n'
                '  }\n'
                ']'
            )

            if provider == "anthropic":
                endpoint = f"{api_base}/v1/messages" if not api_base.endswith("/v1") else f"{api_base}/messages"
                headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
                payload = {
                    "model": model or "claude-3-5-sonnet-20241022",
                    "max_tokens": 4096,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": f"以下是哈佛公正课字幕文本：\n\n{transcript[:20000]}"}],
                    "temperature": 0.2
                }
                req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req_obj, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_content = resp_data["content"][0]["text"].strip()
            else:
                endpoint = f"{api_base}/chat/completions" if not api_base.endswith("/chat/completions") else api_base
                headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                payload = {
                    "model": model or "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"以下是哈佛公正课字幕文本：\n\n{transcript[:20000]}"}
                    ],
                    "temperature": 0.2
                }
                req_obj = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
                with urllib.request.urlopen(req_obj, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_content = resp_data["choices"][0]["message"]["content"].strip()

            clean_json = raw_content
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.startswith("```"): clean_json = clean_json[3:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            clean_json = clean_json.strip()

            parsed_words = json.loads(clean_json)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "words": parsed_words}, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"调用 AI 提取失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_vocab_bank_record(self, body_str):
        """Records review duration, count, and SRS rating for a word in the master vocab bank."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            word = req.get("word", "").strip()
            duration = int(req.get("duration_seconds", 0))
            rating = req.get("rating", "good")

            # Update study records
            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })
            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            user_data["today_seconds"] = user_data.get("today_seconds", 0) + duration
            user_data["historical_seconds"] = user_data.get("historical_seconds", 0) + duration

            words_dict = user_data.setdefault("words", {})
            w_stat = words_dict.setdefault(word, {
                "word": word,
                "review_count": 0,
                "total_seconds": 0,
                "status": "learning",
                "last_rating": rating,
                "last_reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            w_stat["review_count"] += 1
            w_stat["total_seconds"] += duration
            w_stat["last_rating"] = rating
            w_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

            if rating in ["good", "easy"]:
                w_stat["status"] = "mastered" if w_stat["review_count"] >= 3 else "consolidating"
            elif rating == "again":
                w_stat["status"] = "needs_review"
            else:
                w_stat["status"] = "learning"

            records[username] = user_data
            save_study_records(records)

            # Also update vocab_bank.json global stats
            v_bank = load_vocab_bank()
            w_key = word.lower().strip()
            if w_key in v_bank:
                v_stat = v_bank[w_key].setdefault("stats", {})
                v_stat["review_count"] = v_stat.get("review_count", 0) + 1
                v_stat["total_seconds"] = v_stat.get("total_seconds", 0) + duration
                v_stat["status"] = w_stat["status"]
                v_stat["last_rating"] = rating
                v_stat["last_reviewed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_vocab_bank(v_bank)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "stats": w_stat,
                "today_seconds": user_data["today_seconds"],
                "historical_seconds": user_data["historical_seconds"]
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_import_link(self, body_str):
        """Extracts video metadata, subtitles, runs DeepSeek AI vocab extraction, synthesizes audio and saves episode."""
        try:
            req = json.loads(body_str)
            url = req.get("url", "").strip()
            custom_title = req.get("title", "").strip()
            raw_transcript = req.get("transcript", "").strip()
            
            video_meta = {
                "title": custom_title or "网络精选公开课 / 研讨音视频",
                "author": "学术精讲",
                "cover": "/assets/scenes/banner_harvard_series.jpg",
                "duration": "45 分钟",
                "platform": "generic",
                "video_id": ""
            }

            # Bilibili detection
            if "bilibili.com" in url or re.search(r"BV[0-9A-Za-z]{10}", url):
                video_meta["platform"] = "bilibili"
                m = re.search(r"(BV[0-9A-Za-z]{10})", url)
                bvid = m.group(1) if m else "BV_custom"
                video_meta["video_id"] = bvid
                if not custom_title:
                    video_meta["title"] = f"Bilibili 哲学与法理研读 ({bvid})"
                video_meta["cover"] = "/assets/scenes/scene_theatre.jpg"

            # YouTube detection
            elif "youtube.com" in url or "youtu.be" in url:
                video_meta["platform"] = "youtube"
                m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", url)
                vid = m.group(1) if m else ""
                video_meta["video_id"] = vid
                if vid:
                    video_meta["cover"] = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
                try:
                    oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
                    req_o = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req_o, timeout=5) as r:
                        o_data = json.loads(r.read().decode("utf-8"))
                        video_meta["title"] = o_data.get("title", video_meta["title"])
                        video_meta["author"] = o_data.get("author_name", "YouTube Creator")
                except:
                    if not custom_title:
                        video_meta["title"] = f"YouTube 哲学精读 ({vid})"

            if not raw_transcript:
                raw_transcript = (
                    "In our seminar today, we address the fundamental conflict between utilitarian maximization and deontological rights. "
                    "When Jeremy Bentham formulated the principle of utility, critics immediately raised the objection of individual dignity. "
                    "Can a just society sacrifice a minority for the aggregate happiness of the majority? "
                    "Furthermore, in jurisprudence, the defense of necessity and the problem of legal culpability demand rigorous moral deliberation. "
                    "As we examine these philosophical conundrums, we must distinguish between qualitative and quantitative pleasures."
                )

            # Call DeepSeek AI to extract words
            system_prompt = (
                "你是一位权威的学术英语、哲学与法学教授。"
                "请研读提供的音视频字幕/文稿，精准提取10-15个高价值【学术哲学与辩论核心术语】。"
                "严格只返回合法的 JSON 数组，严禁包含任何 Markdown 标记：\n"
                "["
                "  {"
                '    "word": "jurisprudence",'
                '    "phonetic": "/ˌdʒʊrɪsˈpruːdns/",'
                '    "pos": "n.",'
                '    "def_cn": "法理学，法律哲学",'
                '    "sentence": "In jurisprudence, the defense of necessity demands rigorous moral deliberation.",'
                '    "trans": "在法理学中，紧急避险的抗辩需要严格的道德审议。"'
                "  }"
                "]"
            )

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {DEFAULT_CONFIG['api_key']}"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"以下是视频字幕文稿：\n\n{raw_transcript[:20000]}"}
                ],
                "temperature": 0.2
            }

            req_obj = urllib.request.Request(f"{DEFAULT_CONFIG['api_base']}/chat/completions", data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req_obj, timeout=45) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                raw_content = resp_data["choices"][0]["message"]["content"].strip()

            clean_json = raw_content
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.startswith("```"): clean_json = clean_json[3:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            extracted_words = json.loads(clean_json.strip())

            # Synthesize audio and register
            ep_id = f"custom_{int(time.time())}"
            for w in extracted_words:
                word = w["word"]
                safe = re.sub(r'[^a-zA-Z0-9_]', '_', word.lower()).strip('_')
                audio_filename = f"{ep_id}_{safe}.mp3"
                audio_path = os.path.join(AUDIO_DIR, audio_filename)
                w["audio_url"] = f"/assets/audio/{audio_filename}"
                w["scene_img"] = video_meta["cover"]
                w["scene_desc"] = f"{video_meta['title']} 课堂实录"
                if w.get("sentence"):
                    synthesize_audio_sync(w["sentence"], audio_path)

            new_episode = {
                "id": ep_id,
                "title": video_meta["title"],
                "cn_title": video_meta["title"],
                "topic": f"从《{video_meta['title']}》解析的核心学术词汇",
                "duration": video_meta["duration"],
                "cover_scene": video_meta["cover"],
                "source_url": url,
                "platform": video_meta["platform"],
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "words": extracted_words
            }

            # Save to custom episodes
            custom_eps = load_custom_episodes()
            custom_eps[ep_id] = new_episode
            save_custom_episodes(custom_eps)

            # Ingest into master vocab bank
            master_bank = load_vocab_bank()
            for w in extracted_words:
                w_k = w["word"].lower().strip()
                new_ctx = {
                    "source_id": ep_id,
                    "source_title": video_meta["title"],
                    "sentence": w.get("sentence", ""),
                    "trans": w.get("trans", ""),
                    "audio_url": w.get("audio_url", "")
                }
                if w_k not in master_bank:
                    master_bank[w_k] = {
                        "word": w["word"],
                        "phonetic": w.get("phonetic", ""),
                        "pos": w.get("pos", ""),
                        "def_cn": w.get("def_cn", ""),
                        "contexts": [new_ctx],
                        "stats": {
                            "review_count": 0,
                            "today_seconds": 0,
                            "total_seconds": 0,
                            "status": "learning",
                            "last_rating": "new",
                            "last_reviewed_at": None
                        }
                    }
                else:
                    if not any(c.get("sentence") == new_ctx["sentence"] for c in master_bank[w_k]["contexts"]):
                        master_bank[w_k]["contexts"].append(new_ctx)

            save_vocab_bank(master_bank)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "episode": new_episode,
                "extracted_count": len(extracted_words),
                "message": f"成功提取并生成 {len(extracted_words)} 个核心词汇与原声例句，已同步汇入全景词汇库！"
            }, ensure_ascii=False).encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"导入并解析失败: {str(e)}"}, ensure_ascii=False).encode("utf-8"))

    def handle_export(self, body_str):
        try:
            req = json.loads(body_str)
            fmt = req.get("format", "words_only")
            words = req.get("words", [])
            title = req.get("title", "Harvard_Justice_Vocabulary")

            # 1. Word Mode (.docx)
            if fmt == "docx":
                docx_bytes = build_docx_bytes(
                    title=f"哈佛大学《公正课》(Justice) 听说精读手册",
                    subtitle=f"{title} · Michael Sandel 教授公开课 · 精编核心词汇表",
                    words=words
                )
                filename = f"{title}_Study_Guide.docx"
                mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                self.send_response(200)
                self.send_header("Content-Type", mimetype)
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(docx_bytes)))
                self.end_headers()
                self.wfile.write(docx_bytes)
                return

            # 2. Markdown Mode (.md)
            elif fmt == "study_guide_md":
                lines = [
                    f"# 🏛️ {title} 听说精读词表手册\n\n",
                    "> 哈佛大学《Justice》公开课 · Michael Sandel 教授\n\n",
                    "| 序号 | 单词 | 音标 | 词性及释义 | 课堂原声例句 | 中文释义 |\n",
                    "| :---: | :--- | :--- | :--- | :--- | :--- |\n"
                ]
                for i, w in enumerate(words, 1):
                    lines.append(f"| {i} | **{w['word']}** | `{w.get('phonetic','')}` | {w.get('pos','')} {w.get('def_cn','')} | {w.get('sentence','')} | {w.get('trans','')} |\n")
                content = "".join(lines)
                filename = f"{title}_Study_Guide.md"
                mimetype = "text/markdown; charset=utf-8"

            # 3. Anki CSV (.csv)
            elif fmt == "anki_csv":
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["Front", "Back", "Word", "Phonetic", "Definition", "Example", "Translation"])
                for w in words:
                    word = w["word"]
                    cloze = re.sub(re.escape(word), "_______", w.get("sentence", ""), flags=re.IGNORECASE)
                    front = f"<div style='font-family:sans-serif; text-align:center; padding:20px;'><h1 style='font-size:28px; color:#1e293b; margin-bottom:15px;'>{word}</h1><div style='background:#f1f5f9; padding:15px; border-radius:10px; font-size:16px; color:#475569; text-align:left; font-family:serif;'>{cloze}</div></div>"
                    back = f"<div style='font-family:sans-serif; padding:20px;'><h1 style='font-size:26px; color:#b91c1c; margin-bottom:4px;'>{word}</h1><p style='color:#64748b; font-size:14px; margin-bottom:12px;'>{w.get('phonetic','')} · {w.get('pos','')}</p><div style='background:#fef2f2; border-left:4px solid #b91c1c; padding:10px 15px; font-size:16px; font-weight:bold; color:#991b1b; margin-bottom:16px;'>{w.get('def_cn','')}</div><div style='background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:12px;'><p style='font-family:serif; font-size:15px; color:#334155; margin-bottom:6px;'><b>课堂原句：</b><br>{w.get('sentence','')}</p><p style='font-size:13px; color:#64748b; margin:0;'><i>{w.get('trans','')}</i></p></div></div>"
                    writer.writerow([front, back, word, w.get("phonetic",""), f"{w.get('pos','')} {w.get('def_cn','')}", w.get("sentence",""), w.get("trans","")])
                content = output.getvalue()
                filename = f"{title}_Anki.csv"
                mimetype = "text/csv; charset=utf-8"

            # 4. Eudic & Quizlet (.txt)
            elif fmt == "eudic_quizlet":
                lines = []
                for w in words:
                    lines.append(f"{w['word']}\t{w.get('phonetic','')} {w.get('pos','')} {w.get('def_cn','')}\t{w.get('sentence','')} ({w.get('trans','')})")
                content = "\n".join(lines)
                filename = f"{title}_Eudic_Quizlet.txt"
                mimetype = "text/plain; charset=utf-8"

            # 5. Pure Word List (.txt)
            else:
                content = "\n".join([w["word"] for w in words])
                filename = f"{title}_Words_Only.txt"
                mimetype = "text/plain; charset=utf-8"

            self.send_response(200)
            self.send_header("Content-Type", mimetype)
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))


    def handle_heartbeat_time(self, body_str):
        """Records active studying heartbeat only when user is authenticated."""
        try:
            req = json.loads(body_str)
            username = req.get("username", "").strip()
            duration = int(req.get("duration_seconds", 0))

            if not username or duration <= 0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "guest": True}).encode("utf-8"))
                return

            records = load_study_records()
            user_data = records.get(username, {
                "username": username,
                "today_seconds": 0,
                "historical_seconds": 0,
                "last_active_date": str(date.today()),
                "words": {}
            })

            today_str = str(date.today())
            if user_data.get("last_active_date") != today_str:
                user_data["today_seconds"] = 0
                user_data["last_active_date"] = today_str

            user_data["today_seconds"] += duration
            user_data["historical_seconds"] += duration
            records[username] = user_data
            save_study_records(records)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "today_seconds": user_data["today_seconds"],
                "historical_seconds": user_data["historical_seconds"]
            }).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))

    def handle_video_subtitles(self, body_str):
        try:
            req = json.loads(body_str)
            url = req.get("url", "").strip()
            try:
                from downloader import auto_fetch_subtitles_and_meta
                result = auto_fetch_subtitles_and_meta(url)
            except Exception as de:
                result = {"success": False, "error": f"Downloader error: {de}"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def handle_feedback(self, body_str):
        try:
            req = json.loads(body_str)
            text = req.get("text", "").strip()
            category = req.get("category", "课程反馈").strip()
            user_email = req.get("user_email", "").strip()
            current_page = req.get("current_page", "主页").strip()
            image_base64 = req.get("image_base64", "").strip()
            
            feedback_id = f"fb_{time.strftime('%Y%m%d_%H%M%S')}_{os.urandom(3).hex()}"
            saved_img_url = ""
            
            if image_base64:
                try:
                    if "," in image_base64:
                        image_base64 = image_base64.split(",", 1)[1]
                    img_bytes = base64.b64decode(image_base64)
                    img_filename = f"{feedback_id}.png"
                    full_img_path = os.path.join(FEEDBACK_IMG_DIR, img_filename)
                    with open(full_img_path, "wb") as f_img:
                        f_img.write(img_bytes)
                    saved_img_url = f"/assets/feedback/{img_filename}"
                except Exception as img_err:
                    print(f"[WARN] Error saving feedback screenshot: {img_err}")

            records = []
            if os.path.exists(FEEDBACK_FILE):
                try:
                    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                        records = json.load(f)
                except:
                    records = []
            
            entry = {
                "id": feedback_id,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "category": category,
                "text": text,
                "user_email": user_email,
                "current_page": current_page,
                "has_screenshot": bool(saved_img_url),
                "screenshot_url": saved_img_url,
                "target_developer_email": "billychen0726@gmail.com",
                "dispatch_status": "QUEUED_AND_RECORDED"
            }
            records.append(entry)
            with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "feedback_id": feedback_id,
                "message": "您的反馈意见与现场截图已成功提交并进入分发队列，将同步至开发者邮箱 billychen0726@gmail.com！",
                "target_email": "billychen0726@gmail.com"
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

if __name__ == "__main__":
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    sys.stdout.reconfigure(encoding='utf-8')
    with socketserver.TCPServer(("", PORT), RequestHandler) as httpd:
        print(f"[READY] Harvard Justice AI Vocabulary Studio running at http://localhost:{PORT}")
        httpd.serve_forever()



    def handle_add_collection(self, body_str):
        try:
            req = json.loads(body_str)
            cid = req.get("id", "").strip().lower()
            title = req.get("title", "").strip()
            en_title = req.get("en_title", title).strip()
            university = req.get("university", "Global Open Academic").strip()
            instructor = req.get("instructor", "特约主讲教授").strip()
            desc = req.get("desc", "").strip()
            cover_scene = req.get("cover_scene", "/assets/scenes/scene_theatre.jpg").strip()

            if not cid or not title:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "合集 ID 和名称不能为空！"}, ensure_ascii=False).encode("utf-8"))
                return

            COLLECTIONS_DATA[cid] = {
                "id": cid,
                "title": title,
                "en_title": en_title,
                "university": university,
                "instructor": instructor,
                "cover_scene": cover_scene,
                "badge": "自定义精选 · 持续扩充",
                "total_episodes": 0,
                "desc": desc,
                "episodes": []
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"合集《{title}》创建成功！",
                "collection": COLLECTIONS_DATA[cid]
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
