# 工单修复与端到端验收报告

- 工单：`D:\vocab\工单修复.docx`（WPS 里词汇表显示异常 / 导出合集是 nothing / 分集词数疑问）
- 目标：修好工单里的 bug + 新增英文释义（`def_en`）+ 端到端验收
- 结论：**全部修复并上线，公网端到端门禁 346/346 通过**
- 验收时间：2026-09-17 13:08（UTC）
- 站点：https://vocab.samuraiguan.cloud （origin `127.0.0.1:8765`，nginx + Cloudflare）

---

## 一、工单问题逐条对照

### 1. 「导出合集是 nothing」——根因是"假成功"，不是没数据

复现（线上）：

```
POST /api/export {"format":"docx","words":[414 个词],"title":"哈佛大学《公正…》_合集精读手册"}
HTTP/1.0 200 OK
Content-Type: application/vnd…wordprocessingml.document
HTTP/1.0 500 Internal Server Error      <-- 同一份响应里又追加了一行状态
（响应体 84 字节）
'latin-1' codec can't encode characters in position 43-58: ordinal not in range(256)
```

三层原因叠在一起：

1. **线上 `server.py` 落后于仓库 3 个提交**（线上文件 mtime 09-17 03:36，仓库里早已有 `build_content_disposition()`）。线上代码是这一行：
   `self.send_header("Content-Disposition", f'attachment; filename="{filename}"')`
   而 HTTP 响应头只能用 latin-1 编码，标题里的 16 个中文字符正好落在偏移 43–58
   （`Content-Disposition: attachment; filename="` 是 43 个 ASCII 字符）→ `UnicodeEncodeError`。
2. **异常处理在写完 200 状态行之后才补 500**：`http.server` 把状态行缓存在同一个 buffer 里，
   客户端只读第一行，于是**拿到的是 200**，把 84 字节错误文本当成文件下载。
3. 因为标题是中文，**每一个真实导出都会中招**（分集、合集、总词库全都是中文标题）。

修复：

- 部署新 `server.py`（含 `build_content_disposition`：ASCII 回退名 + RFC 5987 `filename*=UTF-8''…`）。
- 新增 `send_bytes()`：**所有响应头先构造并校验完，再写任何字节**，失败时能诚实地回 500。
- 导出逻辑抽成纯函数 `build_export_payload()`（可离线门禁，不需要点按钮）。
- 前端 `downloadExport()` 增加双重校验：拒绝 `application/json` 响应、校验 `.docx` 的 zip 魔术字节
  `PK\x03\x04`（这类"200 + 错误体"从此在浏览器侧也能被挡住）。

证据：`S7B export gate PASS - 346 passed / 0 failed`（公网 URL 实测）。

### 2. WPS 打开词汇表乱码 / 「缺失字体兼容模式」

线上 docx 是手搓 OOXML，只有 **5 个部件**，`styles.xml` 只有 418 字节。经静态解包确认 6 个缺陷：

| # | 缺陷 | 后果 |
|---|---|---|
| 1 | 缺 `word/fontTable.xml`、`settings.xml`、`theme/theme1.xml`、`docProps/*` | WPS 判定包不完整 → 「缺失字体兼容模式」 |
| 2 | **全文没有任何 `w:lang`** | WPS 无法判断哪些字符该用拉丁字体槽，于是**用中文字体去画英文** → 英文变乱码 |
| 3 | 字体是 `Segoe UI` + `Microsoft YaHei`，且未在 fontTable 声明 | 不在 WPS 保证字体集内，由阅读器自行替换 |
| 4 | `w:pPr` 里 `jc` 排在 `spacing` 之前；`w:tblPr` 里 `tblLayout` 排在 `tblBorders` 之前；`w:tcMar` 写成 top/bottom/left/right | OOXML 这些是 **sequence 不是 choice**，严格阅读器按"文件损坏"处理 |
| 5 | `w:sz` 没有配套 `w:szCs` | 中文按阅读器默认的复杂脚本字号排版 |
| 6 | 没有控制字符消毒 | ASR 句子里一个 `\x0b` 就能让整个文档打不开 |

重写 `docx_generator.py`：**12 个部件**、字体只用 `Times New Roman`（拉丁）+ `宋体/SimSun`（中文）
且都在 fontTable 声明、**每个 run 都带完整 `rFonts` + `w:lang`**、按脚本把文本切成"中文 run / 拉丁 run"
（中文 run 打 `w:hint="eastAsia"`），元素顺序全部按 ECMA-376 校正，并加了控制字符消毒。

同时新增 `w:szCs`/`w:bCs`/`w:iCs`，页脚 `PAGE/NUMPAGES` 改成最兼容的 `fldChar` begin/instr/separate/result/end 写法，
表宽严格自洽（`tblW = Σ gridCol = 9746 dxa`）。

新增 **`docx_conformance.py` 门禁（30 项）**：包完整性、content-types、关系目标、XML 合法性、
**元素顺序合规**、字体白名单 + fontTable 声明、每个 run 的 `rFonts/lang/szCs`、`hint` 与 CJK 一致、
表宽自洽、`sectPr` 位置、以及**内容往返**（每个 word / def_cn / def_en 必须出现在文档里、行数 = 词数 + 1）。

> 需要你确认的部分：我无法看到 WPS 的渲染结果。请用 WPS 打开
> `docs/samples/ep02_study_guide.docx` 与 `docs/samples/collection_harvard_justice.docx`
> （这两个文件是**从线上接口直接下载的**，不是我本地生成的）。静态可证的部分已经全绿；
> 若你的机器上仍提示缺字体，只可能是 `宋体` 本身缺失（中文 Windows/WPS 均自带），到时告诉我。

### 3. 分集导出按钮

前端已有「导出本集手册 (.docx)」（学习页顶部 + 合集详情里每一集），它们的失败原因与合集完全相同（中文标题 → latin-1 崩溃），
现已随根因一并修好；分集导出走 `/api/preset/<ep>` 的完整词表，**包含 `def_en`**。

---

## 二、新增功能：英文释义 `def_en`

工单里问「能不能加上英文释义」——已作为数据 + 接口 + 界面 + 导出四层贯通。

**数据生成（`s4c_english_definitions.py`，AI 生成 + AI 复审 + 确定性门禁）**

- 以**唯一词头**为单位：跨集复用的词只生成一条，再写回所有出现它的分集与总词库，保证"同一词在任何页面释义一致"。
- 生成后逐条确定性校验：含中文/标点、markdown、引号包裹、长度、词数、循环定义（去掉词头后剩余实词 < 2）、
  以 "It is/This is" 等填充语开头、**照抄例句**（与例句连续 8 词完全重合即拒）、提及课程本身（Sandel/Harvard/this lecture…）。
- 再跑一轮 **AI 复审**（只允许报 id + 问题类型），被标记的**单独重写**。
- **撞车处理**：`irrespective of` 与 `regardless of` 生成了同一句释义。第一版脚本只是"丢弃后来者"，
  结果缺 1 条 → 门禁**拒绝写入**（0 字节落盘，这是设计如此）。改为：成对要求区分措辞，两次仍相同则作为
  "真同义词对"显式记录（同义是语言事实，不是缺陷）。
- 覆盖范围：**502 个词头 = 449 个分集词 + 53 个词库历史词**（后者见下一节）。

**界面**

- 学习卡背面新增独立的「English Definition」区块（`focus-back-def-en-wrap`），无释义时自动隐藏，不影响老数据。
- 总词库列表每条在中文释义下方增加 `EN` 行，并**参与搜索**（中英都能搜到）。

**导出（5 种格式全覆盖）**

| 格式 | 英文释义落点 |
|---|---|
| `.docx` | 「词性与中英释义」列：中文一行 + `EN …` 一行（列宽重算：560/1900/3100/4186） |
| `.md` | 新增「英英释义」列 |
| Anki `.csv` | 新增 `EnglishDefinition` 字段，并写进卡片背面 HTML |
| 欧路/Quizlet `.txt` | 释义字段内换行附上英文释义 |
| 纯词表 `.txt` | 不含释义（本就是词表） |

验收：`ep01 163/163、ep02 215/215、ep03 44/44` 全部带释义；总词库 `502/502`。

---

## 三、你问过的：「总词库为什么和一集一集的词表不一样？」

**结论：不是两套数据，是"并集 + 学习统计 + 历史保留"。** 现在这三个关系都被显式建模并可机器校验。

线上实测：

| 指标 | 数值 |
|---|---|
| 总词库条目 | 502 |
| 分集词头并集 | 449（ep01 163 + ep02 215 + ep03 44 + yale 32 + custom 12 = 466 个槽位，去重后 449） |
| 分集有、词库没有 | **0**（不存在"分集里有而词库漏掉"的词） |
| 词库有、分集没有 | **53** |
| 跨集复用（一条 entry 多个 context） | **16**，如 `utilitarianism` → `[ep01, ep02, custom]` |

两件容易误解的事：

1. **重复出现的词不会被后一集排除**。它在词库里就是**一条** entry，`contexts` 里每个分集一条例句
   （这正是"🌟 多语境汇聚"标签的含义）。分集词表只列"本集新教/本集选入"的词，所以看起来"少"。
2. **那 53 个多出来的词是历史遗留**：它们来自**已被替换的旧词表**——其中 33 个来自最初那份**伪造的 ep03 词表**
   （24/44 个词在讲座里根本没出现，已重建），12 个来自 audited 之前的 ep02，8 个来自旧 ep01
   （如 `cabin boy`、`castaway`、`actuary`）。它们的旧 context 仍写着 `source_id: ep03` 之类，
   **于是前端按分集筛选时会把它们显示在"已经不教这个词"的分集下面** —— 这就是你看到"词库和分集不一样"的直接机制。

修复方式（不删你的数据）：

- 新增由分集推导的 **`taught_in`** 字段（`s6b_sync_bank_def_en.py`），前端筛选**以它为准**，
  不再靠 `source_id`/标题关键字猜；`custom` 有专门分支（匹配 `custom*`）。
- 历史词打上 `bank_only: true`，界面显示 **「📜 历史词（未编入现有分集）」**，只在"全部"里出现。
- 53 个历史词**也被补上了英文释义**（否则会出现"502 条里 53 条没有 EN"的新不一致）。
- 门禁：`taught_in` 必须与分集完全一致；词库条目集合不得增删；**本次只允许改动 `def_en/taught_in/bank_only` 三个字段**
  （`S6b PASS - 502 entries, 449 def_en propagated, 9 passed / 0 failed`）。

---

## 四、流程脚本化（你要的"我只负责分发任务"）

新增/改造的脚本都在 `tools/quality_pipeline/`：

| 脚本 | 作用 |
|---|---|
| `s4c_english_definitions.py` | 生成 `def_en`（AI 生成 + AI 复审 + 重写 + 撞车门禁，支持 `--dry-run`） |
| `s6b_sync_bank_def_en.py` | 词库 ↔ 分集一致性：同步 `def_en`、推导 `taught_in`、只允许改这三个字段 |
| `docx_conformance.py` | 任意 .docx 的 30 项包门禁（结构/顺序/字体/内容往返） |
| `export_conformance.py` | 导出全矩阵验收：**词表源 × 5 种格式**，实测 HTTP：状态、Content-Type、头 ASCII 安全性、`filename*`、zip 魔术字节、内嵌 docx 过包门禁、每个词/释义都在正文里 |
| `local_smoke.py` | **部署前**本地起服 + 跑导出门禁 |
| `deploy_app.py` | 应用代码部署：比对 sha256 → 备份 → 上传 → 校验 → 重启 → 探针 |
| `stage_client.py` | 在服务器上跑任意单个阶段并取回产物（不用手写 SSH） |
| `deliver.py` | 全流程编排新增 `s4c` 与 `s7b` 两级 |

复现命令：

```powershell
# 部署前本地验证（严格绑定端口，端口被占会直接报错而不是静默共存）
python tools/quality_pipeline/local_smoke.py

# 部署
python tools/quality_pipeline/deploy_app.py

# 公网端到端验收
python tools/quality_pipeline/export_conformance.py --base https://vocab.samuraiguan.cloud

# 单阶段（含 dry-run）
python tools/quality_pipeline/stage_client.py --script s6b_sync_bank_def_en.py --stage s6b --dry-run
```

---

## 五、验收结果

```
S4c（英文释义生成）      PASS  9 passed / 0 failed   502 词头（449 分集 + 53 历史），AI 复审标记 58 条→全部重写通过
S6b（词库一致性）        PASS  9 passed / 0 failed   502 条全部有 def_en，449 attributed + 53 historical，只改了 3 个字段
S7B（导出，公网实测）    PASS  346 passed / 0 failed 8 个词表源 × 5 种格式 + 工单致命用例
  └ docx 包门禁          PASS  30/30 × 8 个词表源
UI/API 验收              PASS  见下
```

界面/接口实测：

```
GET /                                      200  前端含 def_en 卡片块、taught_in 筛选、历史词标记、zip 校验
GET /api/preset/ep02                       215 words, 215 with def_en
GET /api/vocab-bank                        502 entries, 0 missing def_en, 449 attributed + 53 historical
GET /api/collection/harvard_justice        422 words, ep01/ep02/ep03 全部带 def_en
POST /api/export (中文标题, 工单致命用例)   200 且 body 是真正的 zip (PK\x03\x04)
```

---

## 六、遗留事项（需要你决定）

1. **DeepSeek API Key 需要轮换**。`sk-0ff6375d…` 自提交 `bb47147` 起就在公开仓库历史里，代码里已移除，
   但**历史提交仍可读到**，必须去 DeepSeek 控制台吊销并换新。
2. **git 未推送**：我这边最后一个提交（导出门禁的健壮性修复）**故意没有 push**，遵守你"等另一台机器跑完再上传"的要求。
   注意另一台机器已经把 `0da0c48` 推到了 origin（含本次全部数据与脚本）。
3. **ep01 回填**：ep01 的切片边界与部分 ASR 例句仍是旧数据（ep02/ep03 已按句边界重切）。
4. **无音档的词表**：yale / custom 目前没有音频文件。
5. **WPS 实机确认**：请打开 `docs/samples/` 里两个 docx 反馈是否还有字体提示。
6. **`data/quality/`** 是本机跑门禁产生的缓存与报告（0.3 MB），未纳入版本控制。

---

## 七、本次顺带修掉的工具链缺陷（诚实记录）

| 缺陷 | 影响 |
|---|---|
| `deliver_client.py` 上传清单**漏了 `s0b_build_deck.py`** | 新集交付会跑到服务器上的旧版本或直接失败；已改为自动扫描目录，不可能再漏 |
| `local_smoke`/`serve_local` 因 `allow_reuse_address=True` 在 Windows 上**可与旧进程重复绑定同一端口** | 我因此一度"验证"的是上一次会话遗留进程的旧代码；现已严格绑定，端口被占直接报错 |
| 导出门禁用 `dict(r.headers)` 做**大小写敏感**查找 | Cloudflare 返回小写头名，导致误报 40 项"Content-Disposition 丢失"（其实头是好的）|
| 导出门禁没有重试、缺 `import time` | 网络抖动会直接崩掉整轮验收 |
| `docx_conformance` 遇到缺 `tblGrid` 的旧包会抛异常 | 门禁自己崩掉，而不是给出失败结论 |
| `config.log` 在 GBK 控制台打印 emoji 会抛 `UnicodeEncodeError` | 会在打印某一项**明细**时崩掉整个阶段 |
| `~/.vocab_deploy.json` 用 PowerShell 写入带 BOM | 客户端 `json.load` 直接失败；已改用 `utf-8-sig` 读取 |
| `s4c` 首版把"deck 槽位数"和"唯一词头数"混为一谈 | 报了一处假的 FAIL（数据其实完好） |
