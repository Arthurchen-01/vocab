# CHANGELOG

本项目此前**没有任何 tag**，本文件从首次正式发布开始记录。
版本口径：**MAJOR** 数据契约 / 交付格式不兼容变更；**MINOR** 新增采集能力或工具链；
**PATCH** 缺陷修复。

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
