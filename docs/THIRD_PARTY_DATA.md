# 第三方数据来源与许可（Third-party data attribution）

本仓库的课程词表（哈佛《公正》各集、耶鲁、用户导入）来自本项目的语音转写与翻译流水线。
**考试词表（托福 / 雅思 / GRE / 考研）不是本项目生成的**，而是从下列开源数据导入，
在此按许可要求署名。

## ECDICT

- 项目：https://github.com/skywind3000/ECDICT
- 许可：**MIT License**（Copyright (c) 2025 Linwei）
- 取用地址：`https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv`
- 解析行数：770611
- 取用字段：`word`、`phonetic`、`definition`（英英释义）、`translation`（中文释义）、
  `pos`、`tag`（考试标签）、`collins`、`oxford`、`bnc`/`frq`（词频）、`exchange`（词形变化）
- 说明：本项目**未修改**词条文本，仅做字段映射、按 `tag` 过滤与排序筛选。
  未收录 ECDICT 的 `detail` 字段（其官方标注为"待添加"，实际为空）。

| 词表 | deck id | 词条数 |
| --- | --- | --- |
| 托福学术核心词汇 | exam_toefl | 600 |
| 雅思学术核心词汇 | exam_ielts | 600 |
| GRE 高阶词汇 | exam_gre | 600 |
| 考研英语核心词汇 | exam_ky | 600 |
| 学术词组与固定搭配 | exam_phrases | 600 |

## Tatoeba

- 项目：https://tatoeba.org
- 许可：**CC-BY 2.0 FR**（要求署名）
- 取用地址：`https://downloads.tatoeba.org/exports/per_language/...`
- 说明：Tatoeba (CC-BY 2.0 FR) example sentences were attached to 487 words.

## 未采用的数据（许可或质量原因）

| 数据 | 原因 |
| --- | --- |
| Kaiyiwing/qwerty-learner 词书 | **GPL-3.0** 传染性许可，且部分词书源自专有出版物，不适合并入本仓库 |
| 1eez/103976 | 无许可证 |
| mahavivo/english-wordlists | 无许可证，内容据称源自 2003 年金山词霸（专有） |
| Coxhead AWL 官方表 | 未声明开源许可，再分发法律状态不明 |
| Oxford 3000/5000、Longman 3000、COCA 20000 | 商业专有词表 |
| TED2020 / News-Commentary / OpenSubtitles | CC-BY-NC-ND / NC-SA，禁止商用或改作 |
| **SAT 词表** | **ECDICT 没有 `sat` 标签**，因此本仓库不提供 SAT 词表——
  用托福/GRE 词重新贴标签属于伪造数据，本项目明确拒绝这样做。 |

## SAT 词表（qwerty-learner）

- 项目：https://github.com/Kaiyiwing/qwerty-learner
- 取用文件：`public/dicts/SAT_3_T.json`（4463 条）
- 许可：**GPL-3.0**（该仓库根许可），且其部分词书据信源自商业出版物（如新东方 SAT）。
- 说明：ECDICT 没有 `sat` 标签，用托福/GRE 词重贴 SAT 标签属于伪造数据，因此经仓库所有者决定，
  改用市面流行词书并**如实记录本条 provenance**。该词表隔离在 `data/sat_deck.json`，
  删除该文件即可整体移除；其内容不作为本项目原创或已核验内容呈现。
