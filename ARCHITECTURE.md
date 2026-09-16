# 🏛️ VerbaLex Studio · 核心系统架构与设计理念 (Architecture)

## 1. 整体技术分层架构图

```
+-------------------------------------------------------------------------------+
|                       Client Layer (浏览器 / 移动端 / 平板)                      |
|                                                                               |
|   +-------------------+  +--------------------+  +------------------------+   |
|   |  Landing Page     |  | Collections Grid   |  | Focused Flashcards     |   |
|   |  / (首页展示)      |  | /collections       |  | /study/ep01 (全键盘自测)|  |
|   +-------------------+  +--------------------+  +------------------------+   |
|   +-------------------+  +--------------------+  +------------------------+   |
|   | Vocab Bank        |  | Swagger UI Docs    |  | Feedback Modal         |   |
|   | /vocab-bank       |  | /docs (OpenAPI 3)  |  | 现场截屏粘贴工单        |   |
|   +-------------------+  +--------------------+  +------------------------+   |
|                                                                               |
|             [HTML5 History API Router: pushState + popstate 状态同步]          |
+-------------------------------------------------------------------------------+
                                      |
                                  HTTP/HTTPS
                                      |
+-------------------------------------------------------------------------------+
|                         Nginx 反向代理 / 边缘网关 (Port 80/443)                  |
|          SSL 终结 / Gzip 压缩 / 静态切片字节流范围请求 (Range: bytes 206)       |
+-------------------------------------------------------------------------------+
                                      |
                                 127.0.0.1:8765
                                      |
+-------------------------------------------------------------------------------+
|                     VerbaLex Enterprise Server (server.py)                    |
|                                                                               |
|  [SPA Fallback Engine]              [RESTful API Router]                      |
|  - 拦截 /study/*, /collections 等   - /api/collections, /api/preset/*         |
|  - 拦截 /docs 返回 Swagger 页面     - /api/vocab-bank, /api/user/*            |
|  - 返回 HTTP 200 index.html         - /api/export, /api/feedback              |
|                                                                               |
|  [Core Modules]                                                               |
|  - SRS Repetition Controller (Anki SM-2 艾宾浩斯四级评分状态机)               |
|  - Strict Telemetry Watchdog (严格双条件学时累加与防偷跑哨兵)                 |
|  - Docx / Markdown / Anki Exporter (多格式手册生成引擎)                       |
|  - DeepSeek / Claude AI Proxy (学术词汇提炼微调模型管道)                     |
+-------------------------------------------------------------------------------+
                                      |
+-------------------------------------------------------------------------------+
|                     Storage & Media Assets (物理磁盘资产层)                   |
|                                                                               |
|  data/curriculum_tiered.json    : 161 词四维对标真本 (TOEFL, GRE, 哲学, 短语) |
|  public/assets/scenes/ep01/     : 161 张哈佛现场视频毫秒级截帧 (frame_*.jpg)  |
|  public/assets/audio/clips/     : 161 个现场原声 Sandel 授课切片 (*_native.mp3)|
|  public/assets/audio/           : 329 个独立单词高清朗读真人音频              |
|  public/openapi.json            : OpenAPI 3.0.3 标准接口规范契约              |
+-------------------------------------------------------------------------------+
```

---

## 2. 核心设计模式与技术亮点

### 2.1 SPA 客户端路由与服务端 Fallback 闭环
以往前端虽然是单页，但点击所有页面 URL 均保持为 `https://vocab.samuraiguan.cloud`，导致无法分享深链、无法刷新页面，甚至返回时状态丢失。
本系统重构为：
1. **客户端 History 引擎**：
   - 视图切换自动派发 `history.pushState({ route, param }, '', targetPath)`；
   - 监听 `window.onpopstate`，浏览器返回/前进时直接还原视图与数据上下文；
2. **服务端 Fallback 分发**：
   - `server.py` 在 `do_GET` 中识别客户端路由白名单（`/collections`, `/collection/*`, `/study/*`, `/vocab-bank`, `/docs`）；
   - 若匹配前端路由，直接将 `index.html` 以 HTTP 200 交付，客户端接管后解析 `window.location.pathname` 实现毫秒级深链直达！

### 2.2 严格双条件学时真核守护 (Anti-Idle Timer Invariant)
学时是衡量真实投入的核心指标，严禁挂机刷时长：
$$	ext{Timer Active} \iff (	ext{Is Logged In} = 	ext{True}) \land (	ext{Card View Open} = 	ext{True})$$
- 退出专注卡片界面或处于合集列表时，心跳定时器立即切断，状态徽章显示 `待机暂停`；
- 只有学员在词卡界面进行专注翻转与评级切词时，心跳定时器才通过 `POST /api/user/heartbeat-time` 向后端累加今日与历史研学秒数。

### 2.3 现场视频帧与原声音频毫秒级时间戳映射 (1:1:1 守恒)
- 全课 161 个词汇条目均拥有严格的时间戳 `[mm:ss]`；
- 映射公式：
  $$	ext{Word}_i \mapsto (	ext{Frame}_i \in 	ext{/scenes/ep01/}, \ 	ext{AudioClip}_i \in 	ext{/clips/}, \ 	ext{SpokenSentence}_i)$$
- 达成严格的 **1 词 : 1 现场截图 : 1 现场原声**，字字有据、句句有声。
