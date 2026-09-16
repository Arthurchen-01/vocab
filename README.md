# 🏛️ VerbaLex Studio (知源思辨)
### 哈佛大学公开课沉浸式学术英语听说与词汇预习研学系统

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-emerald.svg)](https://opensource.org/licenses/MIT)
[![OpenAPI 3.0](https://img.shields.io/badge/OpenAPI-3.0.3-brightgreen.svg)](https://vocab.samuraiguan.cloud/docs)
[![Production Live](https://img.shields.io/badge/Production-Live-rose.svg)](https://vocab.samuraiguan.cloud)
[![AI Engine](https://img.shields.io/badge/AI%20Engine-DeepSeek%20V3-blueviolet.svg)](https://deepseek.com)

> **VerbaLex Studio** 是专为全球名校公开课研学者（以哈佛大学迈克尔·桑德尔教授《公正：该如何做是好？》为标杆课程）打造的企业级听说精读与词汇深度预习系统。  
> 告别脱离语境的孤立背词表，通过**原汁原味课堂现场视频帧抓取**、**毫秒级现场原声音频切片**、**四维学术词表标准对标**与 **Anki 级全键盘盲刷自测**，帮助学员在课前扫清听力障碍，在课后实现抗遗忘长效内化。

---

## 🌟 核心工程特性与创新架构 (Key Features)

### 1. 🎞️ 现场授课真实视频逐帧截图 (Authentic Video Frames)
- 彻底摒弃网图与合成占位图，云端对标哈佛公开课官方 480p 视频源（`ep01_video.mp4`）；
- 使用 `ffmpeg` 依据全量 161 词在真实演讲逐字稿中的毫秒级时间戳，精准抽取 **161 张** 桑德尔教授课堂现场授课截图（保存在 `/assets/scenes/ep01/frame_{word}.jpg`）；
- 还原真实的 Sanders Theatre 现场大厅、黑板板书、手势互动与听众席提问氛围。

### 2. 🎙️ 课堂原汁原味现场原声切片 (Native Lecture Audio Clips)
- 全本 54 分钟授课高清录音物理切割，产出 **161 个** 专属原生切片（保存在 `/assets/audio/clips/`）；
- 双轨音频矩阵：支持【🎙️ 课堂原声 (Sandel现场原音)】与【🔊 词典标准真人发音 (329个独立音频)】一键对比切换。

### 3. 🎯 四维词库权威深度对标与扩充 (Four-Tiered Academic Curriculum)
全量提取哈佛 Ep01 真实 1,142 句逐字稿（7,242 词），依托官方标准与 DeepSeek 大模型独立审计会话沉淀 **161 个核心词条与动词短语**：
- 📘 **托福 / 雅思核心高频词 (TOEFL/IELTS)**：94 词
- ⚡ **GRE / SAT 拔高与思辨难词 (GRE/SAT)**：21 词
- 🏛️ **道德哲学与法理学术专精术语 (Philosophy & Law)**：24 词
- 🔥 **核心动词短语与固定搭配 (Phrasal Verbs)**：22 组

### 4. ⌨️ Anki 经典全键盘沉浸式盲刷 (Anki-Style Keyboard Flow)
自测过程双手无需离开键盘：
- `Space` (空格键)：卡片双向顺畅 3D 翻转（正面 &harr; 背面）；
- `1` / `2` / `3` / `4`：艾宾浩斯自评评分（`1: 忘记`、`2: 模糊`、`3: 掌握`、`4: 熟练`），一键评分并自动秒切下一词；
- `&larr;` / `&rarr;` 或 `P` / `N`：快速上一个 / 下一个词卡；
- `R`：重听桑德尔现场原声。

### 5. 🌐 全链路 HTML5 History 路由与 API 深度配对 (SPA Deep Linking)
彻底解决“所有页面全都是主网址”的单页弊端：
- `/`：研学大厅与名校课程展区
- `/collections`：学术合集矩阵库
- `/collection/:id`：单合集详情页（如 `/collection/harvard_justice`）
- `/study/:id`：专注词卡自测沉浸流（如 `/study/ep01`）
- `/vocab-bank`：跨剧集全景大词库
- `/docs` 或 `/api-docs`：交互式 OpenAPI 3.0 Swagger 开发者接口中心
- 刷新（F5）、浏览器前进后退（Back/Forward）与直接分享深链 100% 状态保留。

### 6. ⏱️ 严格双条件研学计时与快速闪刷学时预估 (Strict Timer Telemetry)
- **真核计时铁律**：仅在【学员已登录】且【处于打开词卡专注学习】时累加学时；退出专注模式或关闭卡片即刻进入 `待机暂停`；
- **科学闪刷模型**：按 6-8 秒/词校准预估，161 词全量闪刷仅需 16-23 分钟，22 组动词短语仅需 2-3 分钟。

### 7. 📤 五合一多格式文献与题库导出 (Universal Exporter)
一键导出精美研学手册：
- **Word (.docx)**：排版考究、含封面与版权声明的正式双语听力讲义；
- **Markdown (.md)**：适合知识库与 GitHub 阅读的排版手册；
- **Anki (.csv)**：内置 HTML 挖空样式、正反面释义的卡组；
- **欧路 / Quizlet (.txt)**：制表符分隔的一键导入文本；
- **纯词表 (.txt)**：极简单词清单。

### 8. 💬 现场带图反馈工单与开发者邮件直通 (Feedback System)
- 在任何学习页面支持 `Ctrl+V` 粘贴截图并填写反馈；
- 图片自动物理落盘，元数据同步至后台工单队列并直通开发者邮箱 `billychen0726@gmail.com`。

---

## 🛠️ 技术栈与架构 (Tech Stack)

```
├── 前端表现层 (Frontend)
│   ├── 原生 HTML5 / ES6+ (零臃肿 Node 构建依赖，毫秒级轻量响应)
│   ├── Tailwind CSS (现代响应式排版) + FontAwesome 6
│   ├── HTML5 History API (客户端无刷新路由与浏览器前进后退状态机)
│   └── Swagger UI 5.x (标准化 OpenAPI 交互式测试中心)
│
├── 后端核心服务 (Backend)
│   ├── Python 3.10+ 标准库 (http.server, socketserver, urllib, json)
│   ├── Edge-TTS (微软神经网络高质量流式语音合成)
│   ├── python-docx (定制化 Word 讲义排版生成器)
│   └── yt-dlp & ffmpeg (音视频提取与毫秒级时间戳切帧引擎)
│
├── 智能体与模型中枢 (AI Proxy)
│   ├── DeepSeek-V3 / DeepSeek-Chat (官方直连或代理)
│   └── Anthropic Claude 3.5 Sonnet (学术语义与法理术语萃取)
│
└── 生产基础设施 (Production & Infra)
    ├── Ubuntu 22.04 LTS (公网 IP: 38.76.174.32)
    ├── Systemd (守护服务: vocab_app.service, PPid=1)
    ├── Nginx (反向代理与静态资源字节流加速)
    └── Cloudflare CDN (全球 Anycast 边缘路由与 SSL/TLS 终结)
```

---

## 🚀 快速开始 (Quick Start)

### 1. 克隆仓库与安装依赖
```bash
git clone https://github.com/Arthurchen-01/vocab.git
cd vocab

# 创建并激活虚拟环境 (可选)
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装必要依赖
pip install edge-tts python-docx
```

### 2. 启动本地开发服务
```bash
python server.py 8765
```
启动后访问：
- 研学中心: [http://localhost:8765/](http://localhost:8765/)
- 课程合集: [http://localhost:8765/collections](http://localhost:8765/collections)
- 哈佛 Ep01 词卡: [http://localhost:8765/study/ep01](http://localhost:8765/study/ep01)
- 接口文档: [http://localhost:8765/docs](http://localhost:8765/docs)

---

## 📖 开放 API 接口文档 (OpenAPI 3.0)

本项目提供完整的 OpenAPI 3.0.3 规范。您可以在启动服务后访问 `/docs` 查阅或在线调试：

| 请求方法 | 接口路径 | 描述 |
| :---: | :--- | :--- |
| `GET` | `/api/openapi.json` | 获取全量 OpenAPI 3.0.3 规范 JSON |
| `GET` | `/api/collections` | 获取所有名校公开课合集及统计 |
| `GET` | `/api/collection/{cid}` | 获取特定合集详情与剧集清单 |
| `POST` | `/api/collection/add` | 自定义创建/导入新课程合集 |
| `GET` | `/api/episodes` | 获取所有剧集概览与词汇量 |
| `GET` | `/api/preset/{ep_id}` | 获取剧集四维 161 分级词表及切片元数据 |
| `GET` | `/api/vocab-bank` | 获取跨剧集全景大词库及多出处语境 |
| `POST` | `/api/vocab-bank/record` | 提交全景词库艾宾浩斯复习评分 |
| `GET` | `/api/user/stats` | 获取学员活跃学时看板与词汇记忆状态 |
| `POST` | `/api/user/record` | 提交剧集内单词自评评分与用时 |
| `POST` | `/api/user/heartbeat-time` | 严格双条件活跃研学计时心跳累加 |
| `POST` | `/api/auth/register` | 学员注册 |
| `POST` | `/api/auth/login` | 学员登录 |
| `POST` | `/api/export` | 导出 Word/Markdown/Anki/Quizlet/TXT 手册 |
| `GET` | `/api/audio/tts` | 神经 TTS 动态流式发音接口 |
| `POST` | `/api/import/link` | 粘贴视频链接自动化提取字幕并 AI 生成词库 |
| `POST` | `/api/ai-extract` | 调用大模型提取学术专业词表 |
| `POST` | `/api/test-connection` | 测试大模型 API 连通性 |
| `POST` | `/api/feedback` | 提交问题反馈与现场截屏工单 |

完整接口参数与 cURL 示例请详见：[`API_DOCUMENTATION.md`](./API_DOCUMENTATION.md)。

---

## 📂 目录结构说明 (Directory Structure)

```
├── server.py                   # 企业级后端服务主程序 (REST API, SPA 路由分发)
├── docx_generator.py           # Word (.docx) 精编手册排版与样式引擎
├── downloader.py               # 视频字幕与元数据下载提取器
├── API_DOCUMENTATION.md        # 官方 RESTful API 完整规范手册
├── ARCHITECTURE.md             # 系统内核设计与多模态切片架构设计
├── README.md                   # 项目工程主文档
├── .gitignore                  # Git 安全脱敏与大文件排除规则
├── data/
│   ├── curriculum_tiered.json  # 核心数据：哈佛 Justice Ep01 四维 161 词库与元数据
│   ├── openapi.json            # OpenAPI 3.0.3 标准契约源文件
│   └── transcripts/            # 哈佛公开课 Ep01-Ep04 完整时间戳逐字稿
└── public/
    ├── index.html              # 前端核心 SPA 应用 (HTML5 History 路由, 3D 词卡)
    ├── docs.html               # Swagger UI 交互式 API 开发者中心
    ├── openapi.json            # 静态 OpenAPI 契约镜像
    └── assets/
        ├── scenes/             # 真实视频截图 (ep01/ 下含 161 帧真机截屏)
        └── audio/              # 单字高清真人发音 (clips/ 下含 161 个现场原声)
```

---

## 🔒 安全合规与数据主权 (Security & Sovereignty)
1. **脱敏承诺**：代码库与所有公开文档严格杜绝明文凭证，密码哈希基于 SHA-256；
2. **数据主权**：所有多媒体切片、音视频帧与学员学习轨迹均物理存储于自主受控服务器，杜绝第三方依赖断供；
3. **性能守护**：内存占用稳定于 25-38MB，轻量高并发，支持秒级冷启动。

---

## 📄 许可证 (License)
本项目基于 [MIT 许可证](LICENSE) 开源发布。哈佛大学公开课原文版权归哈佛大学及 Michael J. Sandel 教授所有，本项目仅供学术研读与非商业教育研究之用。
