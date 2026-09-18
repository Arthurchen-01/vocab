# 第一集（ep01）重建说明与前后对照

- 结论：**已按标准流程重建并全绿通过**（S1→S7B 全阶段 PASS，S7 验收 13/13，导出验收 389/389）
- 提交：`f9c89b2`（已推送 GitHub）· 生产已部署 · 线上实测通过
- 机读验收报告：`docs/ep01_DELIVERY_REPORT.md`

---

## 一、诊断：问题比"切片不准"严重

开工前先把缺陷量化（而不是凭印象）：

| 检查项 | 改造前 |
|---|---|
| 例句以终止标点结尾 | **122/163**（41 条没有）|
| 例句小写开头（从句中间切） | **36/163** |
| `sentence_start` 句边界锚定 | **0/163**（字段根本不存在）|
| 切片时长 | **固定 6.0 秒**（min 6.0 / avg 6.0 / max 7.0）|
| 词表词能在讲座文稿中找到 | **108/163 = 66%** |
| 例句能在文稿中溯源 | **68 通过 / 95 不通过** |

缺失词里有 `self-knowledge`、`trolley problem`、`moral agency`、`common law`、
`custom of the sea`、`defense of necessity` —— 这些像"学术主题标签"而不是讲座里说过的话，
和 ep03 那份**伪造词表**是同一个签名。95 条例句来自**另一次 ASR 转写**，与现文稿逐字不符。

> 诚实修正一处：我先前报的"53 个词讲座里完全没有"**略微高估**。复核发现连字符词是假阴性
> （`self-knowledge` 的例句 "as an exercise in self-knowledge" 确实出自讲座，是我的匹配把连字符
> 当成了分隔符），另有一些是**多词短语**（`trolley problem`、`common law`），讲座里两个词都出现
> 但未必连在一起。真实的"幽灵词"少于 53，但确实存在。

## 二、重建结果

| 指标 | 改造前 | 改造后 |
|---|---|---|
| 词条数 | 163（其中约 1/3 未落地）| **117（100% 可溯源）** |
| 句子 | 1142 个 ASR 片段直接切片 | **326 个完整句**（全部有终止标点）|
| `sentence_start` 锚定 | 0/163 | **117/117** |
| 切片时长 | 固定 6.0s | **3.2 / 11.7 / 21.6 s**（min/avg/max）|
| `def_cn` / `def_en` / `sentence_cn` / 切片窗口 | 部分缺失 | **117/117 齐全** |
| S7 线上验收 | — | **13/13 PASS**（含"每个切片完整覆盖其句子"、"线上卡片与交付词表 0 漂移"）|

例句样例（线上实际内容）：

```
trolley    [00:33] This is a course about Justice and we begin with a story. Suppose you're the driver of a trolley car…
murder     [07:48] Whereas pushing the fat man over is an actual act of murder on your part. You have control over that.
onlooker   This time you're not the driver of the trolley car, you're an onlooker standing on a bridge overlooking…
```

词数从 163 降到 117 是**必然结果**：只有真出现在讲座里、且没被其它讲座剧集教过的词才会保留
（63 个因已被 ep02/ep03 教过而按设计去重，例如 `principle`、`minority`、`justice`）。
旧词表已归档在 `data/_retired/ep01_previous_deck.json`，随时可回滚或对照。

## 三、这次暴露并修掉的流水线缺陷（5 个）

1. **S0b 一次要 AI 选整份词表** → 输出超 token 上限，JSON 被截断（`"level_na`）导致阶段失败。
   改为**按讲座时间窗分批选词**，顺带让词覆盖整堂课而不是挤在前十分钟。
2. **考试词表把讲座词"占"掉了**：排除逻辑把 3000 条词典型词表也算作占用者，
   结果 **290 个真实出现在讲座里的词被排除**，包括《公正》第一集里的 `justice`。
   现在只排除**其它讲座剧集**（考试词表共存，词库里本就是一条 entry 多个 context）。
3. **候选清单被当成白名单**：模型提出的词只要不在清单里就丢弃，白白扔掉 100 个好词
   （`principle`、`totalitarianism`…）。现在规则改为**"真的出现在讲座里 且 没被别的讲座剧集占用"**
   就收下（救回 37 个）。
4. **S4c 把全部 3480 条释义标成"自己写的"**（因为它的定义集合里混进了"已有释义"），
   于是导入的词典释义被严格文体门禁误杀 207 条。现在只标记**本轮真正生成的**，
   其余按宽松规则校验并如实记数。
5. **导出门禁拿 Anki 的 CSV 原始字节做子串匹配**：释义里的引号被转义成 `""`，
   导致 10 个词被误报缺失（数据其实完好）。现在**解析 CSV 取真实字段**再比对。

## 四、下一步

哈佛《公正》全系列 ep04…ep12：`data/source_catalog.json` 目前只登记 ep01–ep04 的
YouTube 视频 ID，**需要先核实补齐 ep05–ep12**（B站合集 `BV1jt411m7rn` 实测可展开 12 集，
可作分集标题与顺序的对照）。每集将按同一套流程产出 `docs/epNN_DELIVERY_REPORT.md` 与门禁 JSON。
