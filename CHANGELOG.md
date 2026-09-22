# CHANGELOG

本项目此前**没有任何 tag**，本文件从首次正式发布开始记录。
版本口径：**MAJOR** 数据契约 / 交付格式不兼容变更；**MINOR** 新增采集能力或工具链；
**PATCH** 缺陷修复。

---

## [1.2.0] - 2026-09-22

> 版本跨度：`v1.1.1` → `v1.2.0`（1 个提交）
> 基线提交：`7062340`（v1.1.1）→ 本次发布提交
> 代码量：**5 个文件，+133 / −40 行**（含 1 个新增 provider）

### 上一版（v1.1.1）的状态 —— 改之前是什么样

| 文件 / 目录 | v1.1.1 时的状态 |
| :--- | :--- |
| `providers/bilibili_cc.py` | 调用 `api.bilibili.com/x/web-interface/view` —— 该接口对本机返回 **HTTP 412**，所以它**每次都失败**（健康度 0/3）。更糟的是失败时**整条结果作废**：连已经拿到的元数据也不返回 |
| BBDown | 未接入（用户要求加的"B 站专用下载备份"） |
| 对 412 的理解 | 只知道"官方 API 被风控"，**没有分清是哪个接口** —— 因此误以为"整个 B 站 API 都不通" |

### ★ 本轮查明的根因：412 是「按接口」封的

**同一台机器**上逐接口实测：

| 接口 | 结果 |
| :--- | :--- |
| `x/web-interface/view` | **HTTP 412** ← BBDown 1.6.3 只用这个 |
| `x/web-interface/wbi/view` | **HTTP 200**，完整 JSON ← yt-dlp 用这个 |
| `x/web-interface/view/detail` | HTTP 412 |
| `x/player/pagelist` | HTTP 200 |
| `x/player/wbi/v2` | HTTP 200（需有效 cid） |

裸 curl、带 UA+Referer、带 `buvid3` cookie —— 对前者**全都是 412**；WBI 版本**什么都不用带**就 200。
这同时解释了三件事：yt-dlp 同机为什么能下载、BBDown 为什么四种 API 模式全 412
（它报错写着"请尝试升级到最新版本"，而 **1.6.3 已是上游最新版 2024-08**）、
以及我自己的 `bilibili_cc` 为什么一直 0/3。

### 本次改动的文件 —— 改了什么

| 文件 | 类型 | 改动行数 | 改了什么 |
| :--- | :--- | ---: | :--- |
| `providers/bilibili_cc.py` | 改 | +68 / −33 | **改用 WBI 端点**（WBI 优先 + 老接口回退，并记录每个接口的失败原因）；声明 `CAP_METADATA`，可作为元数据备份；没有字幕时返回**真实元数据**（部分成功）而不是整条失败 |
| `providers/bbdown.py` | **新** | +15（净） | BBDown provider（B 站专用下载备份），带 **24h 缓存的自我探针**：探不通就把自己排除出链，零成本零噪音；接口放开/上游更新/配上 cookie 时自动加入，不需改代码 |
| `providers/base.py` | 改 | +7 / −3 | 注册 `bbdown`；跳过原因表述改为"依赖缺失**或自探针失败**" |
| `tools/quality_pipeline/provider_matrix_gate.py` | 改 | +15 | 新增 **WBI 端点回归检查**（防止有人改回被封的那个接口）；记录 bbdown 被自探针排除的原因 |
| `docs/SOURCE_PROVIDERS.md` | 改 | +43 / −4 | 接口级 412 实测表、BBDown 现状与自探针设计、待办更新 |

### Added

- `providers/bbdown.py`：BBDown（nilaoda/BBDown 1.6.3，自包含二进制，无需 .NET 运行时）作为 B 站专用下载备份，带自探针

### Fixed

- `bilibili_cc` 改用 WBI 端点后**从 0/3 变为可用**（实测 `ok(0.13s)`，此前 `no(0.57s)` 撞 412）
- `bilibili_cc` 不再因为"没有字幕"而丢弃已经拿到的元数据

### Verified（生产机实测）

| 验收项 | 结果 |
| :--- | :--- |
| `provider_matrix_gate` | **26 passed / 0 failed**（含新的 WBI 回归检查） |
| `download_gate` | **18 passed / 0 failed**（B 站 10.7 MB / YouTube 166 MB / 直链 16.7 MB 真实媒体） |
| BBDown 四种模式（WEB/TV/APP/INTL） | 均 HTTP 412 → 自探针正确地将其排除出链 |
| `bilibili_cc` 走 WBI 后 | `bilibili_cc:ok(0.13s)`（此前 `no(0.57s)`） |

---

## [1.1.1] - 2026-09-22

> 版本跨度：`v1.1.0` → `v1.1.1`（1 个提交）
> 基线提交：`006edc7`（v1.1.0）→ 本次发布提交
> 代码量：**5 个文件，+169 / −22 行**

### 上一版（v1.1.0）的状态 —— 改之前是什么样

| 文件 / 目录 | v1.1.0 时的状态 |
| :--- | :--- |
| 下载 URL 构造 | `download_url` 里的 `filename=` 是**未编码的中文**（如 `filename=谁在为加州…mp3`）。浏览器会静默百分号编码，所以看着正常；但任何严格客户端在发请求前就 `UnicodeEncodeError` |
| `server.py` 媒体代理 | yt-dlp 的真实媒体流解析**只对 YouTube 生效**（`if is_youtube:`）→ 粘贴 B 站链接"下载"到的是**它的 HTML 网页**，不是音频 |
| `server.py` 媒体代理 | `Content-Disposition` 直接塞原始中文文件名 → 在 http.server 内部 latin-1 抛异常。**这正是工单里「导出合集是 nothing」的同一个缺陷**，当时的修复只落在导出端点，这个端点漏了 |
| 下载链路验证 | **完全没有**。没有任何门禁验证过"用户点下载能不能真的拿到媒体" |

### 本次改动的文件 —— 改了什么

| 文件 | 类型 | 改动行数 | 改了什么 |
| :--- | :--- | ---: | :--- |
| `downloader.py` | 改 | +20 / −12 | 新增 `media_proxy_url()` 统一构造函数（每个组成部分都百分号编码）；7 处手拼 URL 全部改走它 |
| `server.py` | 改 | +24 / −16 | 媒体代理的 yt-dlp 解析从"仅 YouTube"改为**除 direct 外全平台**（超时 15s→60s）；`Content-Disposition` 改用 `build_content_disposition()`（ASCII 回退 + RFC 5987 `filename*`） |
| `providers/ytdlp_provider.py` | 改 | +6 / −4 | 走统一的 URL 构造函数 |
| `providers/youget.py` | 改 | +2 / −4 | 同上 |
| `tools/quality_pipeline/download_gate.py` | **新** | 138 | 下载链路门禁：跟随 `download_url` 发 Range 请求，校验状态、字节数、容器魔数，以及 URL 是否 ASCII 安全 |

### Fixed

- **B 站下载此前根本不通**（代理到的是网页 HTML，不是音频）
- 下载 URL 里的中文未编码（严格客户端直接崩）
- 媒体代理的 `Content-Disposition` 中文导致 latin-1 崩溃（工单同类缺陷的遗漏端点）

### Verified（生产机实测，`download_gate.py` 18/18）

| 来源 | 状态 | 实测 | 总大小 | 容器 |
| :--- | :--- | :--- | ---: | :--- |
| Bilibili | HTTP 206 | 1 MB / 3.8s | 10,720,262 B | m4a ✓ |
| YouTube | HTTP 206 | 1 MB / 6.7s | 166,424,048 B | m4a ✓ |
| 直链 mp3 | HTTP 206 | 1 MB / 5.0s | 16,694,855 B | ID3 ✓ |

三者的 `download_url` 均通过"ASCII 安全"校验。

---

## [1.1.0] - 2026-09-21

> 版本跨度：`v1.0.0` → `v1.1.0`（2 个提交）
> 基线提交：`448ea08`（v1.0.0）→ 本次发布提交
> 代码量：**19 个文件，+1,497 / −56 行**（其中 12 个是新增的 provider 模块）

### 上一版（v1.0.0）的状态 —— 改之前是什么样

| 文件 / 目录 | v1.0.0 时的状态 |
| :--- | :--- |
| `downloader.py` | 解析是一条写死的 `if/elif` 链；"Tier 1..4" **只是文案**。加一个新工具必须改这个核心文件；无法按需求在"快/准"之间切换；降级顺序是人工写死的，不是实测出来的 |
| 字幕来源 | **只有 yt-dlp 一条路**。实测：YouTube 有人工+自动字幕，**Bilibili 完全没有字幕**（`subs=NA`、无自动字幕），官方 API 又被 **HTTP 412** 风控挡住 → 粘贴 B 站链接**必然**走到"没有真实字幕"的报错，等于 B 站这条线根本不通 |
| `tools/quality_pipeline/s0_acquire_media.py` | 只从 yt-dlp 抓字幕；没有字幕就**整集交付不了**，没有任何兜底 |
| 转写能力 | 无。服务器上也没有任何 ASR 依赖 |
| 可观测性 | 无。不知道"哪个站用哪个工具最灵"，也无从按实测数据排序 |
| 备份 | 名义上有"多级容灾"，实际只有 yt-dlp 一个真实可用的下载器 |

### 本次改动的文件 —— 改了什么

| 文件 | 类型 | 改动行数 | 改了什么 |
| :--- | :--- | ---: | :--- |
| `providers/base.py` | **新** | 96 | Provider 协议 + 能力常量（metadata/media/subtitles/asr）+ 注册表；依赖缺失只摘掉该 provider，不炸整条链 |
| `providers/resolver.py` | **新** | 187 | 按能力组链 → 按**实测健康度**排序 → 合并各 provider 的部分结果 → 记录健康度；ASR 只走显式兜底（不进候选链） |
| `providers/policy.py` | **新** | 50 | 按请求/按用户的开关（数据不是分支）：`quality=fast\|best`、`allow_asr`、`asr_model`、`asr_max_minutes`、`max_minutes`、`cookies_file` |
| `providers/health.py` | **新** | 80 | 每个 (provider, host) 的成功率与平均耗时，决定链顺序 |
| `providers/whisper_asr.py` | **新** | 180 | **本地 faster-whisper 兜底**：下载音频→转写→标注 `whisper_asr:<model>` + `is_machine_transcript`；含 HF 镜像/Xet 规避环境 |
| `providers/asr_runner.py` | **新** | 56 | 在 ASR venv 里跑的转写器（重依赖隔离在独立解释器） |
| `providers/ytdlp_provider.py` | **新** | 74 | yt-dlp：YouTube/Bilibili/任意支持站点；通用站点也返回真实元数据 |
| `providers/bilibili_cc.py` | **新** | 99 | B 站官方 CC/AI 字幕（被 412 挡时如实失败）；支持 cookie 文件 |
| `providers/youget.py` | **新** | 95 | you-get 作为第二个下载器（中文视频站备份） |
| `providers/direct_media.py` | **新** | 26 | 直链音视频；**不声称任何逐字稿** |
| `providers/direct_subtitle.py` | **新** | 43 | SRT/VTT/DownSub 文本 |
| `providers/sciam.py` | **新** | 26 | 科学美国人播客 CDN + 文章正文（标注 `article_text`） |
| `downloader.py` | 改 | +33 / −51 | 公开函数保留、内部改为**委托**给 provider 链（`server.py` 一行未改）；媒体下载路径只要 `(metadata, media)`，不触发转写 |
| `tools/quality_pipeline/s0_acquire_media.py` | 改 | +89 / −4 | 采集阶段增加同一个 ASR 兜底（`--no-asr` / `--asr-model`）；无字幕的来源从"交付不了"变成"可交付" |
| `tools/quality_pipeline/provider_matrix_gate.py` | **新** | 183 | 来源链路门禁：逐条实测每个 provider 与每个策略开关（26 项） |
| `tools/quality_pipeline/deploy_app.py` | 改 | 15 | `--files providers` 支持整目录部署 |
| `docs/SOURCE_PROVIDERS.md` | **新** | 141 | 架构、能力矩阵、加新工具的配方、策略说明、实测结果、待办 |
| `README.md` | 改 | +8 / −1 | 架构树补上 `providers/` 与四类门禁 |

### Added

- `providers/` 可插拔来源链（12 个模块）：能力声明、实测健康度排序、按需策略
- **本地 ASR 兜底**（faster-whisper `small` int8），以及它的独立 venv 与转写器
- `provider_matrix_gate.py`（26 项来源链路门禁）
- `docs/SOURCE_PROVIDERS.md`（架构与配方）

### Changed

- `downloader.py` 从"写死的链"变成"委托给链"；`server.py` 无需改动
- S0 采集阶段具备 ASR 兜底，`--no-asr` 可关闭

### Fixed

- **B 站链接此前完全无法产出词表**（无字幕 → 直接失败）；现在由本地 ASR 补齐并如实标注为机器转写
- 门禁抓到本次改动自身的一个真 bug：`whisper_asr` 声明 `CAP_SUBTITLES` 且接受任意 URL，
  于是混进候选链，在 `allow_asr=off` 时仍跑了 302 秒并产出逐字稿；已改为只走显式兜底

### Verified（生产机实测）

| 验收项 | 结果 |
| :--- | :--- |
| `provider_matrix_gate` | **26 passed / 0 failed** |
| YouTube 导入路径 | 10.0s，真实字幕 `yt-dlp:srt`，1142 行，**未触发 ASR** |
| Bilibili 导入路径（用户报告的链接） | 419.7s：`bilibili_cc:no(0.57s)` → `you-get:no(6.38s)` → `yt-dlp:ok(8.5s)` 真实标题 → `whisper_asr:ok(403s)` 逐字稿；180 段 / 1800 词 / 1.74x 实时 |
| 媒体下载路径（只要元数据+媒体） | **9.8s，不转写**（速度保证成立） |
| 策略 `allow_asr=off` | 不产出任何逐字稿（`source=unavailable`），且明确说明原因 |
| ASR 空载速度 | 10.6 分钟音频 → 转写 58.8s（**10.9x 实时**）；有并发时 1.7x |

---

## [1.0.0] - 2026-09-21

> 版本跨度：首次打版本（此前无 tag）
> 基线提交：`9ef68a8`（origin/main，即上一版线上代码）→ 本次发布提交
> 代码量：**16 个文件，+32,819 / −7,361 行**（其中 4 个数据文件占 +46,992 / −6,796 行）
> 新增文件：9 个 `data/epNN_curriculum_final_audited.json`（ep04–ep12 的审计副本）

### 上一版（`9ef68a8`，即改之前）的状态 —— 改之前是什么样

| 文件 / 目录 | `9ef68a8` 时的状态 |
| :--- | :--- |
| `downloader.py` | 内含 `BILIBILI_COLLECTIONS_CATALOG`「经典名校公开课知识图谱合集库」：**编造目录**，声称 `BV1jt411m7rn` 是「哈佛公正全 12 集」并附 12 个虚构分集（实测该 id 是 3 分钟音乐视频）；B 站官方接口被 412 风控时回落到**硬编码假标题**（`Bilibili 经典公开课深度精讲 (BVxxx)`）；另有多处**编造字幕**（`has_subtitles` 恒为 True） |
| `public/index.html` | 批量弹窗**一打开就自动预填** 3 条示例链接；「智能嗅探」只读输入框**第一行**；合集卡片在 `bvid` 缺失时**显示 `BV1jt411m7rn`**；导出按钮无法识别「200 + 错误 JSON」的假成功 |
| `server.py` | `api_base`/`model` 硬编码 `api.deepseek.com` + `deepseek-chat`；`/api/import/link` 在拿不到字幕时**用编造文本冒充原文**并据此提炼词汇；`harvard_justice` 合集成员写死 `["ep01","ep02","ep03","hj_longsent"]`；`sys.argv[1]` 直接 `int()`（任何带参数的启动器都会崩） |
| `tools/quality_pipeline/ai_gate.py` | 单次请求；`max_tokens` 用满即返回**被截断的半个 JSON**，而且**照写缓存**（污染后续所有同 key 运行）；不识别 `finish_reason=length` |
| `tools/quality_pipeline/config.py` | AI base/model 只认环境变量，无 `secret_config.json` 回退；`token;model` 形式的网关凭据会被整串当 key（401） |
| `tools/quality_pipeline/s6_sync_bank.py` | 分集清单被 `CURRICULUM_KEYS_ORDER` **当成筛选条件**（该列表只该决定顺序）→ 系列长到 12 集后 **ep04–ep12 被静默排除在总词库外（598 个词头缺失）**；门禁要求词库 context 等于该分集的**每一张**卡（长难句表一个词多张卡 → 12 处误报 `text-drift`） |
| `tools/quality_pipeline/s4_translate.py` | 「中文里残留长英文」门禁把**单个英文单词**也计入，且额度只有 2 条 → ep09 因 `David`/`Anisha`/`telos` 被误判失败 |
| `tools/quality_pipeline/s5_apply_and_verify.py` | 无条件要求每个词都有课堂抽帧文件 → **音频-only 采集的集数必然失败**（ep09–ep11） |
| `tools/quality_pipeline/deploy_app.py` | 只在首次连接重试，命令中途断线（EOFError / 10054）即整体失败 |
| `data/curriculum_tiered.json` | 只有 ep01–ep03 + yale；ep04–ep12 虽已产出但**未落盘**，且 ep04–ep12 线上标题是裸 id（`ep04`…） |
| `data/vocab_bank.json` | 3568 条，**缺 ep04–ep12 的 598 个词** |
| `data/exam_decks.json` | 3000 个考试词条**缺 `def_en`** |
| `VERSION` / `CHANGELOG.md` | **不存在**（仓库从未打过版本） |

### 本次改动的文件 —— 改了什么

| 文件 | 类型 | 改动行数 | 改了什么 |
| :--- | :--- | ---: | :--- |
| `data/curriculum_tiered.json` | 改 | +15548 / −3 | 落盘 ep04–ep12（含 ep09–ep11 新建词表），并用 `source_catalog.json` 的**真实中英文标题/时长/来源**替换裸 id 标题 |
| `data/vocab_bank.json` | 改 | +25250 / −3696 | 词库 3568 → **4166 条**：补入 ep04–ep12 的 598 个词头、为全部词条补齐 `def_en` 与 `taught_in` |
| `data/exam_decks.json` | 改 | +6000 / −3000 | 3000 个考试词条补齐 `def_en` |
| `data/longsent_decks.json` | 改 | +194 / −97 | 长难句词表同步（97 条） |
| `data/ep04…ep12_curriculum_final_audited.json` | **新** | 9 个文件 | 各集审计副本（S5 产出，词表与线上一致） |
| `downloader.py` | 改 | +258 / −234 | **删除编造目录**；B 站元数据/字幕改为 **yt-dlp 为主、官方 API 为备**；取不到就只显示 BV 号并说明；`transcript` 只允许是真实抓取文本（`_transcript_fields`），并新增通用 `ytdlp_run/metadata/playlist/transcript` |
| `public/index.html` | 改 | +28 / −26 | 弹窗不再预填示例；智能嗅探只保留**最后粘贴**的链接；移除编造 BV 示例与 `c.bvid \|\|` 兜底；导出处拒绝 `application/json` 响应并校验 `.docx` 的 zip 魔术字节；新增 `def_en` 卡片块与总词库 EN 行；分集筛选改用 `taught_in` |
| `server.py` | 改 | +86 / −21 | AI `api_base`/`model` **可配置化**（env → `secret_config.json` → 默认）；`ai_base_allowed()`（http 仅对操作者配置的主机放行）；`/api/import/link` **先真实抓取字幕**，取不到返回 422 而非编造；`harvard_series_episodes()` 从实际词表推导合集成员；`_resolve_port()` 容忍启动参数；导出渲染抽成纯函数 `build_export_payload()` + `send_bytes()`（头全部校验后才写字节） |
| `tools/quality_pipeline/s5c_apply_catalog_meta.py` | **新** | +162 | 把已验证的分集元数据盖到词表；门禁：词数不变、只允许改元数据、写入后不得出现裸 id 标题 |
| `tools/quality_pipeline/ai_gate.py` | 改 | +48 / −19 | 推理模型加固：`finish_reason=length` / 空正文 → **预算翻倍重试**（上限 32768）；**截断结果不写缓存**；可配置 token 下限 |
| `tools/quality_pipeline/config.py` | 改 | +34 / −9 | AI 设置三级解析（env → secret_config → 默认）；`token;model` 只取分号前段；`AI_MIN_TOKENS` |
| `tools/quality_pipeline/s6_sync_bank.py` | 改 | +21 / −4 | 分集清单不再被顺序表过滤（**修复 598 词缺失**）；`text-drift` 门禁改为「词库文本必须**来自**该分集」（允许一词多卡） |
| `tools/quality_pipeline/s4_translate.py` | 改 | +20 / −6 | 「英文残留」只判 **3 词以上**未翻译短语，2 词仅记 note（不再把 `David`/`telos` 当残留） |
| `tools/quality_pipeline/s5_apply_and_verify.py` | 改 | +19 / −1 | 抽帧要求**按是否有视频**条件化；无视频时改为「不得指向不存在的帧文件」 |
| `tools/quality_pipeline/deploy_app.py` | 改 | +65 / −21 | 逐文件 SFTP 重试 + 命令级断线重连；上传失败即中止且不重启 |
| `docs/BILIBILI_AND_GATEWAY_NOTES.md` | **新** | +121 | 三个 B 站缺陷的复现与修复、编造目录的证据、AI 网关切换与推理模型加固、系列现状 |
| `docs/ep01_REBUILD_NOTES.md` | 改 | +10 / −3 | 更正「B站合集 `BV1jt411m7rn` 可展开 12 集」这一**已被证伪**的说法 |

### Added

- `tools/quality_pipeline/s5c_apply_catalog_meta.py`（真实分集元数据落盘）
- `docs/BILIBILI_AND_GATEWAY_NOTES.md`（本轮修复与网关切换记录）
- `VERSION`、`CHANGELOG.md`（首次版本化）
- 9 个 `data/epNN_curriculum_final_audited.json`（ep04–ep12）

### Fixed

- **B 站链接取回别人课程**：前端自动预填 + 只读第一行（根因）、官方接口 412 后落到假标题、编造合集目录
- **导出「合集是 nothing」**：中文标题触发 latin-1 崩溃且异常在写完 200 状态行后才补 500
- **编造数据**：B 站多处假字幕（`has_subtitles` 恒 True）、`/api/import/link` 用编造文稿提炼词汇
- **总词库缺 598 个词**（ep04–ep12 从未进入词库）
- **ep04–ep12 线上标题是裸 id**；合集页只列 3 集，ep04–ep12 无法进入
- 三个误报门禁（英文残留、抽帧、`text-drift`）
- `sys.argv[1]` 直接 `int()` 导致带参数启动即崩

### Changed

- AI 供应商**可配置**（不再写死 `api.deepseek.com` / `deepseek-chat`），兼容 `token;model` 凭据
- 推理模型下的小预算调用由 token 下限兜底，避免每次先截断一次

### Verified（全部为线上实测数字）

| 验收项 | 结果 |
| :--- | :--- |
| Harvard《公正》全 12 集上线 | ep01 117 / ep02 215 / ep03 44 / ep04 98 / ep05 105 / ep06 91 / ep07 84 / ep08 51 / ep09 39 / ep10 43 / ep11 41 / ep12 92 = **1020 词**，每词均有 `def_en` + 中文翻译 + 原声切片 |
| 总词库 | **4166 条**，0 条缺 `def_en`，覆盖全部 12 集 + 5 套考试词表 + 长难句；历史词 140 条标 `bank_only` |
| 合集页 | 列出 ep01–ep12 + 长难句，共 **13 项 / 1117 词** |
| 导出验收（公网） | **389 passed / 0 failed**（8 个词表源 × 5 种格式 + 中文标题致命用例） |
| 反造假门禁（公网） | **15 passed / 0 failed** |
| B 站修复验收（公网） | **21 passed / 0 failed**；用户链接返回真实标题与 UP 主，`BV1jt411m7rn` 返回其真实身份（音乐视频） |
| ep09–ep11 流水线 | `S0b → S7B` 全阶段 PASS，`RESULT: ALL STAGES PASSED` |
