# Ep0x 质量流水线（Quality Pipeline）

面向「公开课词汇卡片」的**字幕重建 → 音频重切 → 语境翻译 → 端到端验证**流水线。
每一段都有 **AI 把关 + 自动化断言**，任一门禁失败即中止，坏数据不会流到站点。

## 为什么需要它

上线版本的问题（已实测确认）：

| 问题 | 根因 |
| :-- | :-- |
| 原声片段截头去尾、听不到完整例句 | 切片边界取自 ASR **任意分段组**（1–8 段，均长 13.7 s），不是句子边界 |
| 英文例句断句错误、含识别讹误 | 直接把逐字稿拼接当句子用（1092 段里只有 13.9% 带句末标点） |
| 中文翻译机械、缺上下文 | 按「词」分配译文，同一句英文在不同卡片上有最多 3 种不同中文 |

## 流水线

```
s1_build_sentences.py   ASR 逐段 → 完整英文句子（标点/大小写/讹误修正）   ← 2 次 AI 复核
s2_map_words.py         目标词 → 真正包含它的句子（时间戳定位 + AI 裁定）
s3_cut_media.py         按句子边界重切原声 + 重取课堂截帧（ffmpeg）
s4_translate.py         带上下文的整句中文翻译 + AI 审校 + 单句重译
s5_apply_and_verify.py  写回数据文件 + 端到端验证（可选线上比对）
run_all.py              编排：按序执行、遇错即停、汇总门禁报告
```

### 各阶段门禁（Gate）摘要

**S1**
- 分句结果必须是全体 ASR 段的**严格连续划分**（首尾相接、全覆盖、不重叠）——时间戳始终锚定原始分段，AI 不产生时间。
- 润色：逐条校验「首尾词保留 + 与 ASR 文本 token LCS ≥ 0.70」，**拒绝原样回抄**；失败的条目以 ≤6 条为一批重试（绝不让模型「整批重做」——那正是内容串位的成因）。
- 批量复核（带上下文）只能报 `merge_prev / merge_next / asr_error / not_english`。
- 碎片判定：单条 AI 复核，必须**回填签名 sig**，防止结论落到相邻句。
- 词数/时长上限、时间轴单调不重叠、每条都有 ≥0.8 s 可切音区间。

**S2**：每个词必须真的出现在它被绑定到的那一句里（词边界匹配 + 简单词形变化）；匹配不到的逐词交给 AI 裁定（只能选候选 id 或判 `absent`，不得造句）。

**S3**：每条片段 `ffprobe` 时长与声明窗口一致（±0.30 s）、文件非空、帧文件齐全；并输出**修复前后对比指标**（旧窗口与真实句子边界不符的比例）。

**S4**：整句翻译必须使用给定权威释义用词；AI 审校只**打标**（不改写），被标记的句子逐条重译，避免串位；门禁检查中文里不得残留大段英文、不得出现占位式短译。

**S5**：句子必须包含目标词；片段头尾完整覆盖句子；**同一句只能有一个中文译文**（旧数据最多 3 个）；两份 Ep02 数据副本内容一致；可选与线上接口逐行比对。

## 运行

```bash
# 依赖：python3、ffmpeg/ffprobe（S3 需要原始音视频）
export VOCAB_APP_DIR=/var/www/harvard_justice_app     # 或本地仓库路径
export VOCAB_WORK_DIR=/root/quality_pipeline          # 中间产物/缓存/报告目录
export VOCAB_EP=ep02
export DEEPSEEK_API_KEY=...                           # 或 data/secret_config.json

python tools/quality_pipeline/run_all.py                 # 全流程（S5 干跑，不改数据）
python tools/quality_pipeline/run_all.py --write         # 同时写回数据文件
python tools/quality_pipeline/run_all.py --from s3       # 从某阶段续跑
python tools/quality_pipeline/run_all.py --deploy-check https://vocab.samuraiguan.cloud
```

- 所有 AI 调用按 `(model, system, user)` 哈希**落盘缓存**（`<work>/cache`），重跑几乎不花钱且结果可复现。
- 门禁报告：`<work>/reports/<stage>.{json,md}`；汇总：`<work>/out/<ep>_pipeline_summary.json`。
- 中间产物：`<work>/out/<ep>_{sentences,word_map,translations,media_report,verification}.json`。
- 环境变量可调：`VOCAB_PAD_HEAD/TAIL`（切片前后留白 0.12/0.18 s）、`VOCAB_MAX_SENT_SEC/WORDS`、`VOCAB_SIM_GATE` 等。

## 产物落到哪里

| 阶段 | 产物 |
| :-- | :-- |
| S1 | `out/<ep>_sentences.json`：`{sent_id,a,b,start,end,text,src_text,lcs}` |
| S2 | `out/<ep>_word_map.json`：每个词 → `sent_id` + 匹配方式 |
| S3 | `public/assets/audio/clips/<ep>_*_native.mp3`、`public/assets/scenes/<ep>/frame_*.jpg` |
| S4 | `out/<ep>_translations.json`：每句一个中文译文（该句所有词共用） |
| S5 | `data/<ep>_curriculum_final_audited.json` 与 `data/curriculum_tiered.json[ep]`（两份保持一致） |

## 设计上的两条硬规矩

1. **时间戳只能来自原始 ASR 分段。** AI 只被允许输出「段序号区间」，永远不产生秒数，因此不可能凭空造时间。
2. **AI 产出必须可校验。** 每个 AI 输出都有对应的确定性断言（划分完整性、token 重叠下限、词包含关系、签名回填、时长一致性）；断言不过就重试，重试不过就回退到原始文本并记入门禁报告——绝不静默接受。
