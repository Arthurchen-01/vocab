# 第二轮：考试词表导入 + 字幕诚实性修复（验收报告）

- 目标来源：用户要求"扩充托福雅思/SAT/GRE/学术词汇，包括名词词组动词词组，不要自己造"
- 结论：**已用真实开源数据导入 3000 词（含 600 条真实词组），并顺带修掉一处系统性造假缺陷**
- 验收时间：2026-09-18 02:00（UTC）
- 站点：https://vocab.samuraiguan.cloud · GitHub `Arthurchen-01/vocab` @ `caff184`

---

## 一、先说结论：你的判断是对的，但许可证决定了能用哪一个

我把每条线索都实际抓取验证过（不是听说）：

| 数据 | 许可证 | 能不能用 | 关键事实 |
|---|---|---|---|
| **ECDICT** `skywind3000/ECDICT` | **MIT** ✅ | **已采用** | 770,611 行；含**英英释义 + 中文翻译 + 音标 + 词性 + 考试标签**；`tag` 实测含 `toefl/ielts/gre/cet4/cet6/ky/gk/zk`；**有真实词组**（`community service`、`no gains without pains`） |
| qwerty-learner | **GPL-3.0** ❌ | 不可用 | 打包了 380 本词书（TOEFL 4264 / IELTS 3575 / GRE 6515 / SAT 4464），**但许可证有传染性**，且部分词书源自专有出版物，不能并入本公开仓库 |
| 1eez/103976（10 万词） | **无许可证** ❌ | 不可用 | 只有 word/translation 两列 |
| mahavivo/english-wordlists | **无许可证** ❌ | 不可用 | 内容据称源自 2003 年金山词霸（专有） |
| Coxhead AWL 官方表 | 未声明 ❌ | 不可用 | 再分发法律状态不明 |
| Oxford 3000/5000、Longman、COCA | 商业专有 ❌ | 不可用 | — |
| Tatoeba | CC-BY 2.0 FR ✅ | 已采用 | 78,188 组 cmn-eng 句对（**需要署名**） |
| WikiMatrix | CC-BY-SA ⚠️ | 暂缓 | 786,512 组 en-zh 长句对，但 ShareAlike 有传染性 |

**所以"有人做出来了"是事实，但"能合法直接拿来用"的基本只有 ECDICT。** 这也是为什么我没有采纳任何一个中文考试词表——不是没找到，是许可证不允许。

### 关于 SAT

**ECDICT 没有 `sat` 标签**，所以本仓库**不提供 SAT 词表**。用托福/GRE 的词重新贴一个 "SAT" 标签属于伪造数据——正是这个项目已经修过两次的那类问题。要做 SAT 只能另找有明确许可的来源。

---

## 二、导入结果（线上实测）

```
GET /api/collections -> 5 个合集
   exam_vocabulary   5 集  3000 词  考试与学术词汇（托福 / 雅思 / GRE / 考研 / 学术词组）
GET /api/collection/exam_vocabulary  total_words=3000
   exam_toefl     600 词 | 英释 600 | 词组   4 | 真实例句  47
   exam_ielts     600 词 | 英释 600 | 词组   1 | 真实例句 145
   exam_gre       600 词 | 英释 600 | 词组   0 | 真实例句  12
   exam_ky        600 词 | 英释 600 | 词组   0 | 真实例句 283
   exam_phrases   600 词 | 英释 600 | 词组 600 | 真实例句   0   ← 全是多词单位
GET /api/vocab-bank -> 3480 条（原 502），1.97 MB，2.26s
   taught_in: ep01 163 / ep02 215 / ep03 44 / yale 32 / custom 12
              exam_toefl 600 / exam_ielts 600 / exam_gre 600 / exam_ky 600 / exam_phrases 600
```

选词策略（可复核）：按来源的 `tag` 过滤 → 剔除专有名词、过短词、**日常高频词**（bnc/frq 排名 ≤ 2500）
→ 按稀有度排序 → **为词组预留 35% 名额**（否则稀有单词会占满全部名额，实测第一版词组数为 0）。

词组样本（总词库实际内容）：

```
cost-benefit analysis   a way of deciding by comparing the costs and benefits of an action
principle of utility    the fundamental utilitarian doctrine that actions are right insofar as they prom…
deontological ethics    ethical theory that judges actions by inherent rightness rather than by their res…
general welfare         the collective good and prosperity of a community as a whole
```

流水线：**S9 导入 → S4c 补英英释义（605 条，含 AI 复审）→ S6 重建词库 → S6b 一致性门禁**，
四个阶段全部 PASS，学习进度（502 条 SRS 记录）无损。

### 一个必须说清的缺口

**考试词表基本没有例句**：ECDICT 本身不含例句字段（`detail` 官方标注"待添加"，实测全空）；
Tatoeba 只覆盖到 487/3000。剩下 2513 个词条**没有例句**，卡片会显示
"该词条来自词典词表，暂无例句（不显示编造的句子）"，而不是填一句假的。
长难句（`长难句精读`）需要 WikiMatrix（CC-BY-SA）或自建语料，**尚未做**。

---

## 三、顺带修掉的系统性造假缺陷

回答工单 image1（"B站合集要不要逐条粘贴链接"）时，我实测了批量提取接口，发现返回的
`transcript` 是**编造的占位文本**：

```
"transcript": "[01:00] Welcome to this special seminar on moral theory and utilitarianism…"
"has_subtitles": true
```

排查 `downloader.py` 后确认有 **7 处**同类伪造（YouTube 通用路径、B站无字幕回退、直链、批量B站分集、
科学美国人预设、以及把文章段落**盖上编造的时间戳**冒充逐字稿）。

**更严重的是**：`/api/import/link` **从来不抓取任何字幕**。它只在请求体里找 `transcript`，
找不到就填一段编造的哲学散文，然后"从中提炼核心词汇"。也就是说——
**仅粘贴链接的导入，100% 会生成一个例句从未在任何地方被说过的假词汇集**。这与 ep03 那个
已修的伪造词表是同一类问题，只是活在另一条代码路径上。

修复：

1. **先真的去抓**：YouTube 走 yt-dlp 字幕轨（新增）、B站走官方 CC 接口、直链走 SRT/VTT 解析。
2. **抓不到就说没有**：`transcript` 为空、`has_subtitles=false`、带 `transcript_source` 与提示文案；
   导入接口返回 **422** 并告诉用户改用带字幕来源或粘贴 SRT/DownSub 文稿。
3. `demo_transcript` 改名，目录里保留真实元数据但示例文本永不冒充逐字稿。
4. 新增 **S8 反造假门禁**（`no_fabrication_gate.py`）：静态扫描"字面量赋给 transcript 字段"+
   已删除句子黑名单 + **线上行为探针**（不可解析来源不得返回文本；无字幕导入必须失败且给出指引）。
   本地 14/14 PASS，线上 15/15 PASS。

顺带修掉：`server.py` 用 `int(sys.argv[1])` 解析端口，**任何带参数的启动器都会让它崩在导入期**
（`ValueError: invalid literal for int(): '--port'`）——本地冒烟测试就是这么把它逼出来的。

---

## 四、验收记录（可复现命令）

```powershell
# 导入考试词表（真实数据，缓存 66MB CSV；--dry-run 不落盘）
python tools/quality_pipeline/stage_client.py --script s9_import_exam_decks.py --stage s9 `
    --args "--size 600 --with-tatoeba"

# 补英英释义（AI 生成 + AI 复审 + 撞车门禁）
python tools/quality_pipeline/stage_client.py --script s4c_english_definitions.py --stage s4c_exam

# 重建总词库 + 一致性门禁
python tools/quality_pipeline/stage_client.py --script s6_sync_bank.py   --stage s6_exam
python tools/quality_pipeline/stage_client.py --script s6b_sync_bank_def_en.py --stage s6b_exam2

# 反造假门禁（含线上行为探针）
python tools/quality_pipeline/stage_client.py --script no_fabrication_gate.py --stage s8_live `
    --args "--base http://127.0.0.1:8765"
```

| 阶段 | 结果 |
|---|---|
| S9 导入 | PASS 12/12 — 770,611 行解析，5 个词表 3000 词，署名文件已生成 |
| S4c 英英释义 | PASS 5/5 — 3480 词头全部有释义（本轮新生成 605 条） |
| S6 词库重建 | PASS 8/8 — 502 → 3480 条，SRS 进度无损，51 条历史词保留 |
| S6b 一致性 | PASS 9/9 — `taught_in` 与分集完全一致，只改动允许的字段 |
| S8 反造假 | PASS 15/15（线上） |
| 线上验收 | PASS — 合集/词表/词库全部可达，3000 词 100% 有英英释义 |

---

## 五、下一步（你已指定）

1. **修第一集**：ep01 的切片边界与部分 ASR 例句仍是旧数据（ep02/ep03 已按句边界重切）。
2. **哈佛《公正》全系列**：按同一套流程跑 ep04…ep12 并验收。
   - `data/source_catalog.json` 目前只登记了 ep01–ep04 的 YouTube 视频 ID，**需要先核实并补齐 ep05–ep12**；
   - B站合集 `BV1jt411m7rn` 实测可自动展开 12 集（`detect-collection` 返回 12 集、批量解析 `resolved_count=12`），
     可作为分集标题与顺序的对照；
   - 每集跑完都会产出 `docs/epNN_DELIVERY_REPORT.md` 与门禁 JSON。

## 六、已知待办

- `/api/vocab-bank` 响应已达 1.97 MB / 2.26s，词库继续增长需要分页或按需加载。
- 长难句词表（WikiMatrix CC-BY-SA 或自建语料）未做。
- SAT 词表无合规来源。
- DeepSeek API Key 仍需轮换（历史提交里可读）。
