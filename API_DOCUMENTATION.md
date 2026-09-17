# 📚 VerbaLex Studio · 官方 RESTful API 完整开发与接口规范手册 (v1.0.0)

> **VerbaLex Studio** 是基于哈佛大学名校公开课（Harvard Justice 等）深度构建的沉浸式学术听说与词汇预习研学系统。
> 本手册提供全量 RESTful API 接口定义、请求参数、响应规范、错误码及 cURL 调用示例，所有接口完全遵循 **OpenAPI 3.0.3** 行业标准。
> 
> 🌐 **在线交互式文档 (Swagger UI)**: [https://vocab.samuraiguan.cloud/docs](https://vocab.samuraiguan.cloud/docs)  
> 📄 **OpenAPI 3.0 JSON 规范源**: [https://vocab.samuraiguan.cloud/api/openapi.json](https://vocab.samuraiguan.cloud/api/openapi.json)

---

## 目录 (Table of Contents)
1. [系统全局网络规范与架构](#1-系统全局网络规范与架构)
2. [URL 页面路由与 API 路径配对映射](#2-url-页面路由与-api-路径配对映射)
3. [公开课合集管理接口 (Collections API)](#3-公开课合集管理接口-collections-api)
4. [剧集与四维分级词库接口 (Episodes & Curriculum API)](#4-剧集与四维分级词库接口-episodes--curriculum-api)
5. [艾宾浩斯记忆与研学时态接口 (Study & SRS Telemetry API)](#5-艾宾浩斯记忆与研学时态接口-study--srs-telemetry-api)
6. [全景词汇库与多语境聚合接口 (Master Vocab Bank API)](#6-全景词汇库与多语境聚合接口-master-vocab-bank-api)
7. [学员认证与账号接口 (Authentication & User API)](#7-学员认证与账号接口-authentication--user-api)
8. [多格式文献与题库导出引擎接口 (Export Engine API)](#8-多格式文献与题库导出引擎接口-export-engine-api)
9. [多模态音视频切片与神经发音流接口 (Media & Synthesis API)](#9-多模态音视频切片与神经发音流接口-media--synthesis-api)
10. [DeepSeek / Claude 智能体提炼代理接口 (AI Services API)](#10-deepseek--claude-智能体提炼代理接口-ai-services-api)
11. [系统诊断与带图反馈工单接口 (Feedback & Diagnostics API)](#11-系统诊断与带图反馈工单接口-feedback--diagnostics-api)

---

## 1. 系统全局网络规范与架构

### 基础服务地址 (Base URL)
- **生产云端**: `https://vocab.samuraiguan.cloud`
- **本地开发**: `http://localhost:8765`

### 传输协议与安全
- 全站强制启用 HTTPS / TLS 1.3 加密传输；
- API 请求体与响应体默认编码：`application/json; charset=utf-8`；
- 原生音频切片与发音流：`audio/mpeg`；
- 导出文件流：支持 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`、`text/markdown`、`text/csv`、`text/plain`。

### 跨域资源共享 (CORS)
所有 `/api/` 路由默认启用跨域开放支持：
```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With
```

### 标准统一错误响应模型
```json
{
  "error": "错误详细描述信息",
  "code": 400,
  "timestamp": "2026-09-17 00:30:00"
}
```

---

## 2. URL 页面路由与 API 路径配对映射

为彻底消除“全都是主网址”的单一视图缺陷，VerbaLex 实现了 **HTML5 History API 客户端路由与服务端 SPA Fallback 的 100% 深度配对**。无论是从界面点击切换，还是直接在浏览器地址栏输入、收藏书签或按 F5 刷新，均能完美保持状态并深度直达：

| 前端深度链接 (URL Deep Link) | 对应业务视图 | 后端配对的核心 API 接口 | 功能简述 |
| :--- | :--- | :--- | :--- |
| `/` 或 `/home` | `view-landing` | `GET /api/collections` | 研学中心大厅、名校公开课精选展区 |
| `/collections` | `view-collections` | `GET /api/collections` | 全部学术系列合集网格矩阵 |
| `/collection/:id` | `view-collection-detail` | `GET /api/collection/{cid}` | 单个合集（如哈佛公正课）剧集详情列表 |
| `/episode/:id` | 模态弹窗 / 预习配置器 | `GET /api/preset/{ep_id}` | 剧集四维分级词表与闪刷时间预估面板 |
| `/study/:id` | `view-focused-study` | `GET /api/preset/{ep_id}` | 专注自测卡片模式（真机视频截图+Sandel原声） |
| `/vocab-bank` | `view-vocab-bank` | `GET /api/vocab-bank` | 跨剧集全景多语境大词库 |
| `/docs` 或 `/api-docs` | Swagger UI 开发者中心 | `GET /api/openapi.json` | 交互式 OpenAPI 3.0 接口在线测试控制台 |

---

## 3. 公开课合集管理接口 (Collections API)

### 3.1 获取所有合集列表
- **接口路径**: `GET /api/collections`
- **请求参数**: 无
- **响应示例 (200 OK)**:
```json
[
  {
    "id": "harvard_justice",
    "title": "哈佛大学《公正：该如何做是好？》(Justice)",
    "en_title": "Harvard University: Justice - What's the Right Thing to Do?",
    "university": "Harvard University",
    "instructor": "Prof. Michael J. Sandel",
    "cover_scene": "/assets/scenes/banner_harvard_series.jpg",
    "badge": "哈佛旗舰 · 伦理法理必修",
    "total_episodes": 3,
    "total_words": 161,
    "desc": "探讨功利主义、自由至上主义与康德道德绝对论的经典哲学名篇，哈佛大学最负盛名的思辨殿堂。",
    "episodes": ["ep01", "ep02", "ep03"]
  },
  {
    "id": "yale_philosophy",
    "title": "耶鲁大学《哲学与人性科学》(Human Nature)",
    "en_title": "Yale University: Philosophy and the Science of Human Nature",
    "university": "Yale University",
    "instructor": "Prof. Tamar Gendler",
    "cover_scene": "/assets/scenes/cover_yale_philosophy.jpg",
    "badge": "耶鲁名校 · 道德心理与认知科学",
    "total_episodes": 1,
    "total_words": 0,
    "desc": "结合柏拉图理想国灵魂三分说与现代认知心理学，探索理性、欲望与幸福生活的内在秩序。",
    "episodes": ["yale_ep01"]
  }
]
```
- **cURL 调用示例**:
```bash
curl -X GET "https://vocab.samuraiguan.cloud/api/collections" -H "Accept: application/json"
```

---

### 3.2 获取指定合集详情与剧集列表
- **接口路径**: `GET /api/collection/{cid}`
- **路径参数**:
  - `cid` (string): 合集唯一标识，如 `harvard_justice`、`yale_philosophy`、`custom_imports`。
- **响应示例 (200 OK)**:
```json
{
  "id": "harvard_justice",
  "title": "哈佛大学《公正：该如何做是好？》(Justice)",
  "total_episodes": 3,
  "total_words": 161,
  "episode_details": [
    {
      "id": "ep01",
      "title": "Episode 01: The Moral Side of Murder",
      "cn_title": "第一讲：杀人的道德侧面 · 电车难题与紧急避险",
      "duration": "54 分钟",
      "count": 161,
      "topic": "电车难题、功利主义边沁与海难食人案法理思辨",
      "cover_scene": "/assets/scenes/scene_trolley.jpg"
    }
  ]
}
```

---

### 3.3 创建/导入自定义课程合集
- **接口路径**: `POST /api/collection/add`
- **请求体 (JSON)**:
```json
{
  "id": "oxford_jurisprudence",
  "title": "牛津大学法理学精读系列",
  "en_title": "Oxford Jurisprudence Seminar",
  "university": "Oxford University",
  "instructor": "Prof. H.L.A. Hart",
  "desc": "法律的概念与法理实证主义经典探讨",
  "cover_scene": "/assets/scenes/scene_theatre.jpg"
}
```
- **响应示例 (200 OK)**:
```json
{
  "success": true,
  "message": "合集《牛津大学法理学精读系列》创建成功！",
  "collection": { "id": "oxford_jurisprudence", "total_episodes": 0 }
}
```

---

## 4. 剧集与四维分级词库接口 (Episodes & Curriculum API)

### 4.1 获取所有剧集概览
- **接口路径**: `GET /api/presets` 或 `GET /api/episodes`
- **响应示例 (200 OK)**:
```json
[
  {
    "id": "ep01",
    "title": "Episode 01: The Moral Side of Murder",
    "cn_title": "第一讲：杀人的道德侧面 · 电车难题与紧急避险",
    "topic": "电车难题、功利主义边沁与海难食人案法理思辨",
    "cover_scene": "/assets/scenes/scene_trolley.jpg",
    "count": 161,
    "duration": "54 分钟"
  }
]
```

---

### 4.2 获取剧集完整四维分级词表与真机切片元数据
- **接口路径**: `GET /api/preset/{ep_id}` 或 `GET /api/episode/{ep_id}`
- **路径参数**:
  - `ep_id` (string): 剧集标识，如 `ep01`。
- **词汇分级标准 (`tier`)**:
  - `toefl_ielts`: 托福/雅思核心高频词 (94 词)
  - `sat_gre`: SAT/GRE 进阶思辨难词 (21 词)
  - `academic_philosophy`: 哲学法理学术专精术语 (24 词)
  - `phrasal_verbs`: 核心动词词组与学术固定短语 (22 组)
- **响应示例 (200 OK)**:
```json
{
  "id": "ep01",
  "title": "Episode 01: The Moral Side of Murder",
  "cn_title": "第一讲：杀人的道德侧面",
  "duration": "54 分钟",
  "words": [
    {
      "word": "hurdling",
      "phonetic": "/ˈhɜːrdlɪŋ/",
      "pos": "v.",
      "def_cn": "疾驰狂奔，飞速冲撞",
      "sentence": "The brakes don't work and the trolley is hurtling down the track at sixty miles an hour.",
      "sentence_cn": "你的刹车失灵了，电车正以每小时六十英里的速度在轨道上疾驰狂奔。",
      "timestamp": "01:21",
      "speaker": "Prof. Michael Sandel",
      "tier": "toefl_ielts",
      "audio_url": "/assets/audio/ep01_hurdling.mp3",
      "native_clip_url": "/assets/audio/clips/ep01_hurdling_native.mp3",
      "scene_img": "/assets/scenes/ep01/frame_hurdling.jpg"
    }
  ]
}
```

---

## 5. 艾宾浩斯记忆与研学时态接口 (Study & SRS Telemetry API)

### 5.1 记录单词复习自评状态
- **接口路径**: `POST /api/user/record`
- **请求体 (JSON)**:
```json
{
  "username": "arthur",
  "word": "hurdling",
  "episode_id": "ep01",
  "duration_seconds": 6,
  "rating": "good"
}
```
* `rating` 枚举取值：`again` (忘记/1), `hard` (模糊/2), `good` (掌握/3), `easy` (熟练/4)。

---

### 5.2 严格双条件心跳研学计时器
- **接口路径**: `POST /api/user/heartbeat-time`
- **说明**: 必须满足【学员已登录】且【当前处于打开词卡专注练习】时，前端心跳定时器向后端累加活跃研学秒数。
- **请求体 (JSON)**:
```json
{
  "username": "arthur",
  "duration_seconds": 5
}
```
- **响应示例 (200 OK)**:
```json
{
  "success": true,
  "today_seconds": 320,
  "historical_seconds": 1580
}
```

---

### 5.3 获取学员统计看板与词条记忆库
- **接口路径**: `GET /api/user/stats?username=arthur`
- **响应示例 (200 OK)**:
```json
{
  "username": "arthur",
  "today_seconds": 320,
  "historical_seconds": 1580,
  "last_active_date": "2026-09-17",
  "words": {
    "hurdling": {
      "word": "hurdling",
      "review_count": 2,
      "total_seconds": 12,
      "status": "consolidating",
      "last_rating": "good",
      "last_reviewed_at": "2026-09-17 00:25:00"
    }
  }
}
```

---

## 6. 全景词汇库与多语境聚合接口 (Master Vocab Bank API)

### 6.1 获取跨剧集全景大词库
- **接口路径**: `GET /api/vocab-bank?username=arthur`
- **响应特性**: 自动将不同剧集中重复出现的同根词进行上下文跨篇交叉索引（`contexts` 数组）。
- **响应示例 (200 OK)**:
```json
{
  "words": [
    {
      "word": "utilitarianism",
      "phonetic": "/ˌjuːtɪlɪˈteriənɪzəm/",
      "pos": "n.",
      "def_cn": "功利主义，功利论",
      "contexts": [
        {
          "source_id": "ep01",
          "source_title": "Episode 01: The Moral Side of Murder",
          "sentence": "Bentham's utilitarianism claims that...",
          "trans": "边沁的功利主义认为...",
          "audio_url": "/assets/audio/ep01_utilitarianism.mp3"
        }
      ],
      "review_count": 5,
      "status": "mastered",
      "last_rating": "easy"
    }
  ],
  "summary": {
    "total_words": 161,
    "mastered_count": 35,
    "learning_count": 126,
    "multi_context_count": 22
  }
}
```

---

## 7. 学员认证与账号接口 (Authentication & User API)

### 7.1 学员账号注册
- **接口路径**: `POST /api/auth/register`
- **请求体 (JSON)**:
```json
{
  "username": "student_01",
  "password": "Password123!",
  "nickname": "哈佛公开课学员"
}
```

### 7.2 学员账号登录
- **接口路径**: `POST /api/auth/login`
- **请求体 (JSON)**:
```json
{
  "username": "student_01",
  "password": "Password123!"
}
```

---

## 8. 多格式文献与题库导出引擎接口 (Export Engine API)

- **接口路径**: `POST /api/export`
- **支持格式 (`format`)**:
  - `docx`: 微软 Word 精编双语听说手册（含封面、版式、排版与版权页）
  - `study_guide_md`: GitHub 风格排版 Markdown 手册
  - `anki_csv`: Anki 经典背诵卡组（正面挖空填空、背面释义例句与 HTML 样式）
  - `eudic_quizlet`: 欧路词典 / Quizlet 制表符批量导入文本
  - `words_only`: 纯英文生词表
- **请求体 (JSON)**:
```json
{
  "format": "docx",
  "title": "Harvard_Justice_Ep01",
  "words": [
    {
      "word": "hurdling",
      "phonetic": "/ˈhɜːrdlɪŋ/",
      "pos": "v.",
      "def_cn": "疾驰狂奔",
      "sentence": "The trolley is hurtling down...",
      "trans": "电车正疾驰狂奔..."
    }
  ]
}
```

---

## 9. 多模态音视频切片与神经发音流接口 (Media & Synthesis API)

### 9.1 动态神经 TTS 流式朗读
- **接口路径**: `GET /api/audio/tts?text={url_encoded_text}`
- **技术栈**: Edge-TTS 微软神经网络（`en-US-ChristopherNeural`），自带服务端 Hash 磁盘持久缓存。
- **响应流**: `Content-Type: audio/mpeg`

### 9.2 批量音视频链接多级容灾解析接口 (Batch Media Resolver)
- **接口路径**: `POST /api/media/batch-extract`
- **请求体 (JSON)**:
```json
{
  "urls": [
    "https://www.scientificamerican.com/podcast/episode/the-science-of-friendship-and-loneliness/",
    "https://www.bilibili.com/video/BV1jt411m7rn",
    "https://www.youtube.com/watch?v=kBdfcR-8hEY"
  ],
  "mode": "media",
  "media_type": "audio"
}
```
- **四级容灾保障**:
  - **Tier 1**: 科学美国人 (Megaphone / Omny) 官方 CDN 直连，0 阻碍极速提取；
  - **Tier 2**: YouTube 移动端 Android / iOS 协议客户端伪装，免登录人机拦截；
  - **Tier 3**: Bilibili Referer 自动代理与内置离线回退目录，100% 成功解析；
  - **Tier 4**: 服务器内存管道直接转发，零磁盘损耗。
- **响应体示例 (200 OK)**:
```json
{
  "success": true,
  "total_requested": 3,
  "resolved_count": 3,
  "items": [
    {
      "index": 1,
      "platform": "scientific_american",
      "platform_name": "Scientific American · Science Quickly",
      "title": "The science of friendship and loneliness",
      "duration": "14 分钟",
      "direct_media_url": "https://traffic.megaphone.fm/SAM7091445305.mp3",
      "download_url": "/api/media/stream-download?url=...&filename=friendship.mp3&media_type=audio",
      "has_subtitles": true,
      "tier_used": "Tier 1: 官方 Megaphone CDN 直连通道",
      "success": true
    }
  ]
}
```

### 9.3 零落盘流式音视频代理下载接口 (Stream Downloader)
- **接口路径**: `GET /api/media/stream-download?url={target_url}&filename={name}&media_type={audio|video}&platform={platform}`
- **技术特性**: 
  - **零磁盘损耗**: 后端作为流式内存管道（Chunked Stream Proxy），从上游服务器分块直推至客户端浏览器；
  - **断点续传支持**: 自动透传 HTTP `Range` 头及 `Accept-Ranges: bytes`；
  - **智能协议穿透**: 对 B 站自动注入 `Referer: https://www.bilibili.com/` 突破 403 跨域防护；对 YouTube 自动调用 `yt-dlp` 提取直链。
- **响应流**: `Content-Type: audio/mpeg` 或 `video/mp4`，附带 `Content-Disposition: attachment`。

### 9.4 B站单视频智能嗅探整部合集接口 (Bilibili Collection Detection API)
- **接口路径**: `POST /api/bilibili/detect-collection`
- **设计初衷**: 解决用户仅复制单个视频链接（如 `BV1jt411m7rn` 或带 `?p=1`），系统能够全自动识别其属于哪部系列课或多P视频，并一键展开全集列表（如哈佛正义论全12集）。
- **请求体 (JSON)**:
```json
{
  "url": "https://www.bilibili.com/video/BV1jt411m7rn"
}
```
- **核心响应体示例 (200 OK)**:
```json
{
  "success": true,
  "is_collection": true,
  "bvid": "BV1jt411m7rn",
  "collection_title": "【哈佛公开课】公正：该如何做是好？（全12集·精校双语字幕）",
  "collection_type": "multi_page",
  "total_episodes": 12,
  "author": "Harvard University / Michael Sandel",
  "episodes": [
    {
      "page": 1,
      "title": "Episode 01: The Moral Side of Murder / The Enron Case",
      "url": "https://www.bilibili.com/video/BV1jt411m7rn?p=1",
      "duration": "55:00"
    },
    {
      "page": 2,
      "title": "Episode 02: Putting a Price on Life / How to Measure Pleasure",
      "url": "https://www.bilibili.com/video/BV1jt411m7rn?p=2",
      "duration": "55:00"
    }
  ]
}
```

---

## 10. DeepSeek / Claude 智能体提炼代理接口 (AI Services API)

### 10.1 视频文稿智能提取分级学术词汇
- **接口路径**: `POST /api/ai-extract`
- **请求体 (JSON)**:
```json
{
  "provider": "deepseek",
  "api_base": "https://api.deepseek.com",
  "model": "deepseek-chat",
  "transcript": "In today's lecture, we examine Jeremy Bentham's principle of utility...",
  "count": 20
}
```

---

## 11. 系统诊断与带图反馈工单接口 (Feedback & Diagnostics API)

### 11.1 提交工单（带物理截图与邮件分发队列）
- **接口路径**: `POST /api/feedback`
- **请求体 (JSON)**:
```json
{
  "text": "希望能支持英式与美式发音切换！",
  "category": "体验建议",
  "user_email": "user@example.com",
  "current_page": "/study/ep01",
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
}
```
- **处理链路**: 后端自动解析 Base64 并在物理磁盘 `/public/assets/feedback/` 生成唯一 PNG 文件，工单元数据持久化至 `data/feedback_records.json`，并队列分发至开发负责人邮箱 `billychen0726@gmail.com`。

---

*文档版本：v1.0.0 · 遵循 RFC 2616 HTTP/1.1 与 OpenAPI Specification v3.0.3*
