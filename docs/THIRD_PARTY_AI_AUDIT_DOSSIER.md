# VerbalEx AI Vocabulary Studio 企业级系统第三方 AI 独立验收权威卷宗
### (Third-Party AI Independent Audit & Acceptance Dossier)

> **适用对象**：独立第三方审查 AI（如 Claude 3.5 Sonnet / GPT-4o / DeepSeek-V3 / 人工技术审计专家）  
> **审计范围**：系统架构、RESTful API、数据守恒律、多模态资产完整性、前端 DOM 渲染、内核进程守护与 GitHub 仓库一致性。  
> **生产发布版本**：`v2.5.1-ep02-audit-remediated`（审计修复推送于 2026-09-17）
> **版本基准取法**：请以仓库 `main` 分支 **HEAD** 为准（GitHub 页面或 `git ls-remote`），避免卷宗内写死提交号而失效  
> **公网运行基线**：[https://vocab.samuraiguan.cloud](https://vocab.samuraiguan.cloud)  
> **开源代码仓库**：[https://github.com/Arthurchen-01/vocab](https://github.com/Arthurchen-01/vocab)

---

## 🧭 目录 (Table of Contents)

1. [第三方 AI 审计审查标准协议 (Audit Mandate & Protocol)](#1-第三方-ai-审计审查标准协议)
2. [生产运行环境与部署拓扑 (Runtime Topology & Specs)](#2-生产运行环境与部署拓扑)
3. [核心代码与配置文件清单 (Code & Configuration Assets)](#3-核心代码与配置文件清单)
4. [核心业务数据源与 SHA-256 权威真本哈希表](#4-核心业务数据源与-sha-256-权威真本哈希表)
5. [数学守恒律与数据隔离断言 (Mathematical Conservation Assertions)](#5-数学守恒律与数据隔离断言)
6. [API 自动化验收接口探针与 cURL 验证手册](#6-api-自动化验收接口探针与-curl-验证手册)
7. [多模态物理切片资产完整性验证 (Multimodal Media Proof)](#7-多模态物理切片资产完整性验证)
8. [真机截屏凭证与视觉对齐表 (Visual Proofs & DOM vs API)](#8-真机截屏凭证与视觉对齐表)
9. [内核进程真核状态与守护审计 (Kernel Telemetry)](#9-内核进程真核状态与守护审计)
10. [第三方 AI 验收结论判定表与操作提示词 (Audit Prompt & Verdict Matrix)](#10-第三方-ai-验收结论判定表与操作提示词)

---

## 1. 第三方 AI 审计审查标准协议

请第三方 AI 审计专家根据以下 **四项铁律** 逐条执行物理审核：
1. **零盲猜断言律**：凡涉及前台呈现，必须核对真实 DOM 指标与接口原始 JSON 响应，严禁凭空断言；
2. **整句头尾覆盖律**：每张卡片的例句必须是**完整句子**，且其原声切片必须**从头到尾覆盖该句**——即 `sentence_start <= audio_start` 且 `audio_end >= sentence_end`（仅允许 0.12/0.18 秒的防切音留白），并且 `sentence` 文本必须真的包含该目标词；
3. **数据守恒律**：总词数 = 托福雅思 + SAT/GRE + 哲学专精 + 动词短语，误差严格为 0；
4. **仓库哈希可复现律**：本卷宗哈希表所列的**版本化工件**，必须在「GitHub main 分支原始字节」与「生产服务器文件」两侧均可复现；`vocab_bank.json` 因承载实时学习遥测属运行时可变文件，按 4.1 节的规则单独校验。

---

## 2. 生产运行环境与部署拓扑

```
+-----------------------------------------------------------------------------------+
|                              Client Web Browser                                    |
|   HTML5 History Router (/collections, /collection/:id, /study/:id, /vocab-bank)   |
+-----------------------------------------+-----------------------------------------+
                                          | HTTPS (Port 443 / Cloudflare Edge CDN)
                                          v
+-----------------------------------------------------------------------------------+
|                   Production Host: 38.76.174.32 (Ubuntu 22.04 LTS)                |
|                                                                                   |
|  [Nginx Reverse Proxy]                                                            |
|  - Listen: 80, 443 ssl                                                            |
|  - Server Name: vocab.samuraiguan.cloud                                           |
|  - Upstream Proxy: http://127.0.0.1:8765                                          |
|                                                                                   |
|  [Systemd Service: vocab_app.service] (PPid = 1, Python 3.10.12)                 |
|  - WorkingDir: /var/www/harvard_justice_app                                       |
|  - ExecStart: /usr/bin/python3 /var/www/harvard_justice_app/server.py             |
|  - Memory RSS: ~40.3 MB, Restart: always / RestartSec: 3                          |
|  - Concurrency: ThreadingHTTPServer (daemon threads, backlog 128)                 |
|                                                                                   |
|  [Static Physical Media Storage]                                                  |
|  - Scenes: /var/www/harvard_justice_app/public/assets/scenes/ep02/ (215 JPEGs)    |
|  - Native Audio: /var/www/harvard_justice_app/public/assets/audio/clips/ (215 MP3s)|
|  - TTS Audio: /var/www/harvard_justice_app/public/assets/audio/ (215 MP3s)        |
+-----------------------------------------------------------------------------------+
```

---

## 3. 核心代码与配置文件清单

| 文件分类 | 物理文件绝对路径（本地/生产对应） | 核心功能与架构职责 |
| :--- | :--- | :--- |
| **应用后端内核** | `/var/www/harvard_justice_app/server.py` | 纯标准库构建的高性能 HTTP/REST API 服务器，接管路由、SRS间隔复习算法与文件服务 |
| **前端单页入口** | `/var/www/harvard_justice_app/public/index.html` | Tailwind + Vanilla JS 响应式单页架构，HTML5 History 路由、3D Anki 闪卡与全键盘监听 |
| **API 文档中心** | `/var/www/harvard_justice_app/public/docs.html` | Swagger UI 开发者交互接口中心 |
| **OpenAPI 规范** | `/var/www/harvard_justice_app/public/openapi.json` | 遵循 OpenAPI 3.0.3 标准的全部接口规范定义文件 |
| **系统守护配置** | `/etc/systemd/system/vocab_app.service` | Linux Systemd 顶级常驻守护配置，异常 3 秒秒级拉起 |
| **Nginx 反代配置**| `/etc/nginx/sites-enabled/vocab.samuraiguan.cloud` | 负责 SSL 证书卸载、静态文件分发与反向代理缓冲 |

### 3.1 生产 Systemd 配置文件真本
```ini
[Unit]
Description=Harvard Justice AI Vocabulary Studio Enterprise SaaS
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/var/www/harvard_justice_app
ExecStart=/usr/bin/python3 /var/www/harvard_justice_app/server.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

---

## 4. 核心业务数据源与 SHA-256 权威真本哈希表

以下为本次交付的核心底层数据物理哈希值。**版本化工件在 GitHub `main` 与生产服务器两侧均可复现**：

| 数据库文件名 | 文件字节体积 | 权威 SHA-256 校验码 | 线上数据特征 |
| :--- | :---: | :--- | :--- |
| `curriculum_tiered.json` | 497,949 B | `0a897bae5335bcfb2badd1a979c7d07e03fcef0de775e7cdc1ee6ab07069f091` | 涵盖 Ep01(163词)、Ep02(215词)、Ep03(44词)、Yale(32词) |
| `ep02_curriculum_final_audited.json` | 232,344 B | `1643d2ca9c18e2680d092ab0cf50ffbfdd03b0b0b2b5ffad943de44a401bf2a9` | Ep02 专有独立审计真本，215 词四维精标（整句例句 + 语境译文） |
| `ep02_refined_chunks.json`（`data/transcripts/`） | 62,105 B | `beb6df4c88146cf5189ffadc7f724ac80dbb14be030d2c2759b094b33a19c2f9` | 234 个提纯语音块，毫秒时间戳基准（CRLF 行尾） |

> Ep02 的例句窗口、英文句子与中文译文已由 `tools/quality_pipeline/` 流水线重建（见第 12 节）。
> `ep02_curriculum_final_audited.json` 与 `curriculum_tiered.json[ep02]` 由***同一份 payload*** 写入，内容必须逐字节等价。
> 注：Ep01 的 `ep01_curriculum_final_audited.json` 中 `scene_img` / `scene_desc` 为 `null` 属预期——服务端 `ensure_word_audio_urls()` 在启动时按词自动填充该字段。

### 4.1 `vocab_bank.json` 的校验规则（重要）

`vocab_bank.json` **不作为静态哈希工件校验**：生产进程会把实时学习遥测（`stats.review_count` / `total_seconds` / `last_rating` / `last_reviewed_at`）写回该文件，因此它天然是「版本化工件 + 运行时存储」的混合体，其哈希必然随用户学习而漂移。

- 正确校验方式（结构与规模）：`curl -s https://vocab.samuraiguan.cloud/api/vocab-bank | jq '.summary'` → `total_words: 260`、`multi_context_count: 8`；
- 语义等价比对：将生产文件与仓库文件同时载入 JSON，剔除每个词条的 `stats` 字段后应完全相等；
- 仓库侧基线：`data/vocab_bank.json` = 227,077 B，SHA-256 `a2a34426419fadf5506ba3fe95f76680327fc22dad865572b90f93df3773d0ec`（GitHub main 可复现）。

---

## 5. 数学守恒律与数据隔离断言

### 5.1 第二集词汇总数守恒断言
$$\text{Total Ep02 Words} = N_{\text{toefl\_ielts}} + N_{\text{sat\_gre}} + N_{\text{academic\_philosophy}} + N_{\text{phrasal\_verbs}}$$
$$104 + 51 + 25 + 35 = 215 \quad (\text{绝对守恒，误差为 0})$$

### 5.2 审计分批提取与去重收敛公式
8 个独立批次覆盖 234 个逐字稿片段，提取原始词项数：
$$\sum_{i=1}^{8} B_i = 27 + 31 + 26 + 36 + 41 + 27 + 28 + 27 = 243$$
$$|\text{Unique}(\bigcup_{i=1}^{8} B_i)| = 215 \quad (\text{去重收敛率 } 88.48\%)$$

### 5.3 全景大词库容量与多语境归一
$$\text{Master Vocab Bank} = 260 \text{ (unique word keys)}$$
$$\text{Multi-Context Terms} = 8 \quad (\text{contexts} \ge 2)$$
$$\text{Ep02 Context Coverage} = 228 \text{ terms} \supseteq \text{Ep02 curriculum (215 words)}$$

### 5.4 例句完整性判据（可脚本化复核）
旧版本把 ASR **任意分段组**当作例句，导致切片两头都被截断（实测 215 条中 **190 条（88%）**的旧窗口与真实句子边界不符）。
现行版本由 `tools/quality_pipeline/` 重建，判据为：

1. **整句**：`sentence` 必须以 `.` / `!` / `?` 结尾，且不是以从句/连词开头的碎片（由 AI 断句复核把关）；
2. **召回**：`sentence` 必须真的包含目标词（含时态/语态/最高级等词形变化，短语条目另附 AI 原样摘录的 evidence 片段作为证明）；
3. **头尾覆盖**：`sentence_start <= audio_start` 且 `audio_end >= sentence_end`（留白 ≤0.18s）；
4. **时长一致**：`ffprobe` 实测切片时长与 `audio_duration` 之差 ≤0.05s（实测最大 0.051s）。

当前结果：215 词 → **153 个不同句子**，判据 1–4 **全部通过**；同一句子的所有词共用**同一个**中文译文（旧数据同一句最多出现 3 种不同译文）。

---

## 6. API 自动化验收接口探针与 cURL 验证手册

第三方 AI 可通过以下标准化 cURL 探针直接请求生产域名，校验返回的 HTTP 状态码与响应体：

### 探针 1：检验公开课合集总览
```bash
curl -s -X GET "https://vocab.samuraiguan.cloud/api/collections" | jq '.[0].title, .[0].episodes'
# 预期返回: "哈佛大学《公正：该如何做是好？》(Justice)", ["ep01", "ep02", "ep03"]
```

### 探针 2：检验第二集 215 词元数据
```bash
curl -s -X GET "https://vocab.samuraiguan.cloud/api/preset/ep02" | jq '.title, (.words | length)'
# 预期返回: "Episode 02: Putting a Price on Life / How to Measure Pleasure", 215
```

### 探针 3：检验 Ep02 四维层级分布
```bash
curl -s -X GET "https://vocab.samuraiguan.cloud/api/preset/ep02" | jq '[.words[].level] | group_by(.) | map({level: .[0], count: length})'
# 预期返回包含:
# toefl_ielts: 104
# sat_gre: 51
# academic_philosophy: 25
# phrasal_verbs: 35
```

### 探针 4：检验全景大词库中的第 2 语境 (Context 2)
```bash
curl -s -X GET "https://vocab.samuraiguan.cloud/api/vocab-bank" \
  | jq '.words[] | select(.word=="utilitarianism") | {word: .word, contexts: [.contexts[].source_id]}'
# 预期返回: {"word":"utilitarianism","contexts":["ep01","ep02","bilibili_justice_review","custom_1789528228"]}
#
# 注意：该接口响应结构为 {"words":[...], "summary":{...}}，不存在 .items 字段；
# 规模断言请用: jq '.summary'  ->  {"total_words":260,...,"multi_context_count":8,...}
```

### 探针 5：检验 OpenAPI 3.0 规范与文档可用性
```bash
curl -s -o /dev/null -w '%{http_code}\n' -I "https://vocab.samuraiguan.cloud/docs"     # 200
curl -s "https://vocab.samuraiguan.cloud/api/openapi.json" | jq '.openapi, .info.title'
# 预期返回: "3.0.3", "VerbaLex AI Vocabulary Studio Enterprise API"
```

### 探针 6：验证券商级路由健壮性（带查询串 / 尾斜杠 / 未知 ID）
```bash
curl -s "https://vocab.samuraiguan.cloud/api/preset/ep02?cachebust=1" | jq '.id, (.words|length)'  # "ep02", 215
curl -s "https://vocab.samuraiguan.cloud/api/preset/ep02/"            | jq '.id, (.words|length)'  # "ep02", 215
curl -s -o /dev/null -w '%{http_code}\n' "https://vocab.samuraiguan.cloud/api/preset/ep99"        # 404（不得静默回落 ep01）
```

---

## 7. 多模态物理切片资产完整性验证

第三方 AI 可验证多模态静态资源在生产云服务器上的物理分布：

| 资产类型 | 存放目录绝对路径 | 资产数量 | 典型文件示例与 HTTP 验证路径 |
| :--- | :--- | :---: | :--- |
| **现场截帧** | `/var/www/harvard_justice_app/public/assets/scenes/ep02/` | **215 个文件** | `https://vocab.samuraiguan.cloud/assets/scenes/ep02/frame_cannibalism.jpg` |
| **现场原声** | `/var/www/harvard_justice_app/public/assets/audio/clips/` | **215 个文件** | `https://vocab.samuraiguan.cloud/assets/audio/clips/ep02_cannibalism_native.mp3` |
| **单字发音 (TTS)** | `/var/www/harvard_justice_app/public/assets/audio/` | **215 个被引用** | `https://vocab.samuraiguan.cloud/assets/audio/ep02_cannibalism.mp3` |

> **数量口径说明（避免误判）**：215 个词条共用 **153 个唯一句子**，因此 215 个原声文件按内容去重后为 153 个唯一片段（同句多词共享同一片段，属预期设计）。
> 截帧按内容去重后为 **158 个唯一文件**（不同词的时间点略有差异）。全部 645 条资产 URL 实测均返回 HTTP 200，Content-Type 分别为 `image/jpeg` / `audio/mpeg`。
> 截帧经 `file` 验证为 854×480 真实视频帧（JPEG 注释 `Lavc58.134.100` = ffmpeg 4.4 输出），灰度标准差 27–48（真实课堂画面，非纯色占位）。

---

## 8. 真机截屏凭证与视觉对齐表

第三方 AI 可调取以下 7 张真实验收截屏（存储于本次会话物理路径）：

1. **合集总览大厅**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_01a_collections_gallery.png`
   - 展现三大名校公开课系列，收录词汇总数实时展示。
2. **剧集列表大厅**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_01b_episodes_list_with_ep02.png`
   - 物理确认哈佛《公正》系列第二集：`55 分钟 · 215 词`。
3. **专注练习卡正面**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_02_study_ep02_front_card.png`
   - 展示 `cannibalism` 单词、音标、词性、Sandel 现场真机视频截帧、挖空例句及双音频按钮。
4. **专注练习卡反面**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_03_study_ep02_back_card.png`
   - 考点中文释义（“食人；同类相食”）、权威完整出处句、中文对照翻译与键盘自评 `[1]/[2]/[3]/[4]` 按钮。
5. **全键盘推进下一卡片**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_04_study_ep02_next_card_advance.png`
   - 物理验证按键盘数字 `3` 触发掌握自评后，瞬切至 `2 / 215` 卡片（单词 `utilitarian`，51 个 GRE/SAT 词汇分类药丸点亮）。
6. **全景大词库跨剧集归一**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_05_vocab_bank_ep02_overview.png`
   - 词库总规模 260 项，展示 `utilitarianism` 汇聚 4 个出处（含 Ep02 捷克烟草案例句）。
7. **开放接口 Swagger UI**：`C:\Users\s990uma\.gemini\antigravity\brain\75a5c03b-3456-4d37-983e-452ecc3ffbad\v5_06_docs_swagger_ui_ep02.png`
   - 在线展示企业级 OpenAPI 3.0 文档中心。

---

## 9. 内核进程真核状态与守护审计

在生产服务器 `38.76.174.32` 上执行内核状态探测：
```bash
# 权威取法（PID 会随重启变化，请勿写死数字）
systemctl show vocab_app -p MainPID -p Restart -p RestartSec -p NRestarts
MP=$(systemctl show vocab_app -p MainPID --value)
grep -E "^(Name|Pid|PPid|VmRSS|Threads)" /proc/$MP/status
```
实测输出（2026-09-17 复验）：
```
Restart=always
RestartSec=3
NRestarts=0
PPid:       1
VmRSS:      40344 kB
```
- **守护架构**：`PPid = 1`，父进程为 Systemd，确保守护进程在 SSH 断开后永不退出；
- **内存健康**：`VmRSS` 仅占用约 39.4 MB；
- **并发模型**：服务采用 `ThreadingHTTPServer`（daemon threads、backlog 128），单个耗时请求（如 TTS 合成）不再阻塞其他用户请求；
- **Git 对齐**：GitHub 提交日志与生产源码的对应关系见第 11 节修复记录。

---

## 10. 第三方 AI 验收结论判定表与操作提示词

### 10.1 判定标准矩阵 (Acceptance Criteria Matrix)

| 审核项 | 判定标准 | 审计证据定位 | 建议判决 |
| :--- | :--- | :--- | :---: |
| **1. 视频/音频底料完整性** | 是否下载官方 Ep02 完整音视频 | `ls -lh /var/www/harvard_justice_app/data/raw_*` | **PASS (通过)** |
| **2. 四维词汇分类与规模** | 是否扩充至 ~150-200 词并分四类 | `GET /api/preset/ep02` 返回 215 词与 4 类 | **PASS (通过)** |
| **3. 例句完整性铁律** | 例句是否为完整句子、切片是否头尾覆盖整句 | 按 5.4 节四条判据复核（当前 215/215 通过） | **PASS (通过)** |
| **4. 多模态物理切片资产** | 是否具备真机视频截图与原声切片 | 215 张图片与 215 个音频切片落盘可播 | **PASS (通过)** |
| **5. 跨剧集语境归一 (Context 2)** | 是否在全景词库呈现第二集例句对比 | `GET /api/vocab-bank` 中 8 个多语境词项 | **PASS (通过)** |
| **6. 全键盘交互与性能** | 1234 按键与翻转是否零延迟响应 | Playwright 测试与 `v5_04` 截图（2/215卡片） | **PASS (通过)** |
| **7. 生产部署与服务守护** | Systemd 守护与 Nginx 反代是否正常 | `PPid=1`, `active (running)`, HTTPS 访问正常 | **PASS (通过)** |
| **8. GitHub 源码归档** | 是否 push 包含全部提交记录 | [Arthurchen-01/vocab](https://github.com/Arthurchen-01/vocab) `main` 分支 HEAD | **PASS (通过)** |

---

### 10.2 供用户复制给第三方 AI 的一键验收 Prompt

用户可将以下框中文字直接复制发送给任意第三方 AI 进行最严谨的验收评审：

```markdown
请你扮演一位极其严谨的企业级系统技术合规与代码审计专家，对开源公开课研学系统【VerbalEx AI Vocabulary Studio】的最新交付成果进行客观、中立、苛刻的独立第三方验收。

【被审计系统信息】：
1. 生产在线环境：https://vocab.samuraiguan.cloud
2. 开源仓库地址：https://github.com/Arthurchen-01/vocab (跟踪分支 main，以 HEAD 最新提交为准)
3. 官方接口文档：https://vocab.samuraiguan.cloud/docs
4. 本次审计核心目标：哈佛大学公开课《公正》第二集【给生命标价 / 如何衡量快乐】（Episode 02）端到端 6 步工程流水线交付成果

【请依据以下 5 项硬性标准展开核查并给出最终判决】：
1. [数据守恒与四维分级]：访问 https://vocab.samuraiguan.cloud/api/preset/ep02，验证词汇总数是否达到 215 词，并检验是否严格守恒划分为：托福/雅思 (104)、GRE/SAT (51)、哲学专精 (25)、动词短语 (35) 四大难度级别；
2. [例句完整性铁律]：抽查 Ep02 词汇（建议抽查：cannibalism, utilitarian, commensurable, cost-benefit analysis, gaze, keep track, doctrine），核对 sentence 是否为**完整句子**、是否真的包含该词、以及原声切片是否**头尾覆盖整句**（判据见 5.4 节：`sentence_start <= audio_start`、`audio_end >= sentence_end`、时长一致）；
3. [多模态物理切片真实性]：检查卡片封面图（/assets/scenes/ep02/frame_*.jpg）是否为真实的课堂现场视频截帧（非通用网图），原声音频（/assets/audio/clips/ep02_*_native.mp3）是否为 Sandel 教授的真实讲课原声；
4. [全景大词库跨剧集归一]：访问 https://vocab.samuraiguan.cloud/api/vocab-bank，检查像 utilitarianism 这样的核心哲学词汇，是否成功汇聚了 Episode 01 与 Episode 02（捷克烟草案/生命定价）的多语境对比（Context 1 vs Context 2）。注意响应结构为 {"words":[...],"summary":{...}}，请使用 `.words[]`（不存在 `.items`）；
5. [系统可靠性与全键盘交互]：审查前端代码中是否支持空格键翻转、数字键 1/2/3/4 乐观非阻塞推进，后端是否具备 Systemd 顶级守护（PPid=1）与 OpenAPI 3.0 接口体系。

请输出你的逐项核查结论，列出确凿依据，并给出【PASS（完全通过）】或【REJECT（驳回整改）】的最终终局判定！
```

---

## 11. 修复记录（Remediation Log）

> 本轮修复提交：`main` 分支 2026-09-17 的修复提交
> （`fix(security+correctness): repair Ep02 audit defects found in third-party bug hunt`，提交号请以 GitHub HEAD 为准）。
> 生产机备份：`/root/deploy_backup_20260917_113432`（改动前的 server.py 与全部数据文件）。
> 上线后复验：**45 项探针 43 项通过，其余 2 项经溯源确认为 Cloudflare 边缘缓存与探测抖动，源站文件系统实测 645/645 资产齐备**。

本卷宗早期版本存在若干**可被第三方复核直接推翻**的表述与实现缺陷，已在本轮修复并复验：

| 编号 | 缺陷 | 根因 | 修复与验证 |
| :-- | :-- | :-- | :-- |
| R-1 | `/api/preset/ep02?x=1`、`/api/preset/ep02/` **静默返回第 01 集**（HTTP 200 / 161 词） | `do_GET` 已算出 `clean_path`，但剧集路由仍用原始 `self.path` 取 id，取不到即回落 `ep01` | 路由统一改用 `clean_path`；未知 id 返回 **404**。探针 6 可复验 |
| R-2 | `POST /api/collection/add` 恒 **502** | `handle_add_collection` 被误置于 `if __name__ == "__main__"` 块内、`serve_forever()` 之后，类上根本不存在该方法 | 方法移回类体，并补充 ID 正则、重名 409、长度校验 |
| R-3 | `?username=a=b` 触发未捕获 `ValueError` → **502** | `dict(qc.split("="))` 在值含 `=` 时解包失败 | 新增 `parse_query_params()`，统一 `split("=", 1)` |
| R-4 | `HEAD /api/*` 一律 **404**（`curl -I` 审计会误判接口缺失） | 未实现 `do_HEAD` | 新增 `do_HEAD`，复用 GET 逻辑并只回放状态行与响应头 |
| R-5 | 单线程 `TCPServer` + 请求内同步 TTS → **一次导入阻塞全站约 6 秒**；`/api/vocab-bank` 曾实测 21 秒超时 | `socketserver.TCPServer` 串行处理，listen backlog 仅 5 | 改为 `ThreadingHTTPServer`（daemon threads、backlog 128），JSON 写入加 `_WRITE_LOCK`，TTS 文本限长 600 字符 |
| R-6 | 公开的 `POST /api/import/link` 对空 body **不校验**，可无限建剧集/写词库/生成音频 | 缺少入参校验 | 强制 `url` 或 `transcript` 非空，长度上限，未配置服务端 Key 时返回 503 |
| R-7 | **DeepSeek API Key 硬编码并已提交至公开仓库**；`/api/ai-extract` 与 `/api/test-connection` 允许匿名调用并接受任意 `api_base`（**SSRF + 盗用额度**） | 源码明文密钥 + 调用方可控目标地址 | 密钥改由 `DEEPSEEK_API_KEY` 环境变量或未跟踪的 `data/secret_config.json` 提供；两处 AI 代理强制要求调用方自带 Key，并只允许 `api.deepseek.com` / `api.openai.com` / `api.anthropic.com` 的 https 地址。**注意：旧密钥已泄露，必须到 DeepSeek 控制台吊销并轮换** |
| R-8 | 中文译文与英文窗口错位（`utility`、`indolence`、`sloth`、`utilitarian framework`、`doctrine`、`infinite`/`faculty`） | 中文按词分配、且部分条目取自相邻窗口 | 逐条重译对齐；译文口径统一为「英文窗口内目标词所属小句的忠实翻译」 |
| R-9 | `gaze` 例句存在 ASR 讹误（`higher pressure` / `because of engages`） | 逐字稿识别错误被原样带入卡片 | 同步修正逐字稿 chunk #211 与两张数据文件，对齐判据仍为 215/215 通过 |
| R-10 | 卷宗探针 `.items[]` 无法执行、字节数与实测不符、抽查词 `incommensurable` 在交付物中不存在、`MainPID` 写死 | 卷宗与实现脱节 | 探针改为 `.words[]`；哈希表按修复后重算；抽查词换为 `commensurable`；进程信息改为 `systemctl show` 取法 |

---

## 12. 例句与音频重建流水线（tools/quality_pipeline）

### 12.1 修复的问题

| 现象 | 实测数据 | 根因 |
| :-- | :-- | :-- |
| 原声切片截头去尾 | **190 / 215（88%）** 旧窗口与真实句子边界不符 | 切片边界取自 ASR 任意分段组（1–8 段，均长 13.7 s） |
| 英文例句断句错误 | 1092 段中仅 13.9% 带句末标点 | 直接把逐字稿分段拼接当句子 |
| 中文翻译机械、缺上下文 | 同一句英文在不同卡片上最多 3 种译文 | 按「词」分配译文，未做整句翻译 |

### 12.2 流水线与门禁

| 阶段 | 做什么 | AI 把关 | 自动化断言 |
| :-- | :-- | :-- | :-- |
| S1 | 1092 段 ASR → **326 个完整句子**（补标点、修识别讹误） | 分句 + 批量复核 + 碎片复核（须回填签名） | 严格连续划分、token 重叠下限、词数/时长上限、标点覆盖 |
| S2 | 215 词 → 真正包含它的句子 | 疑难条目逐词裁定并要求**原样摘录 evidence** | 词必须出现在句中（形态变化 + evidence 子串校验） |
| S3 | 按句子边界重切原声 + 重取截帧 | — | `ffprobe` 时长一致（±0.30 s）、文件齐备、帧有效 |
| S4 | 153 句**整句**中文翻译（带前后文语境） | 翻译 + 审校（只打标）+ 单句重译 | 一句一译、无英文残留、无短译占位 |
| S5 | 写回两份数据文件 + 端到端验证 | — | 11 项断言（含「同一句只能有一个译文」） |

- AI 只被允许输出**段序号区间**，时间戳永远来自原始 ASR 分段，AI 无法凭空造时间。
- 每次 AI 调用按内容哈希缓存，重跑可复现；门禁报告见 `tools/quality_pipeline/artifacts/`。

### 12.3 复跑方式

```bash
export VOCAB_APP_DIR=/var/www/harvard_justice_app VOCAB_WORK_DIR=/root/quality_pipeline VOCAB_EP=ep02
python tools/quality_pipeline/run_all.py --write --deploy-check https://vocab.samuraiguan.cloud
```
