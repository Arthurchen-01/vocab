# Ep0x 质量流水线（Quality Pipeline）

**一句话**：给一个视频链接，产出一集「例句完整、原声对齐、译文自然、词库一致」并已上线验收的课程。
AI 只作为流水线**内部的门禁**（断句复核 / 翻译审校 / evidence 裁定），不需要人在中间操作。

---

## 1. 怎么用

### 1.1 最省事：双击粘贴链接

```
tools\quality_pipeline\交付-粘贴链接.cmd
```

按提示粘贴链接（已知课程会自动识别是哪一集），回车即可。跑完会把数据与验收报告拉回仓库，
并在 `--commit` 模式下自动提交推送。

### 1.2 命令行（等价）

```powershell
# 已知课程：只给链接
python tools\quality_pipeline\deliver_client.py --url "https://youtu.be/Qw4l1w0rkjs"

# 指定卡组 id
python tools\quality_pipeline\deliver_client.py --episode ep03 --url "https://youtu.be/Qw4l1w0rkjs" --commit

# 只在服务器上跑（不发车客户端）
python deliver.py --url "https://..." --write --deploy-check https://vocab.samuraiguan.cloud
```

**凭据**（绝不入库）：环境变量 `VOCAB_SSH_HOST / VOCAB_SSH_USER / VOCAB_SSH_PASSWORD`，
或 `%USERPROFILE%\.vocab_deploy.json` = `{"host":"...","user":"root","password":"..."}`。

### 1.3 已知课程来源

`data/source_catalog.json` 存了已验证的视频 id 与时长（用视频时长和逐字稿跨度交叉核对过）：

| 分集 | 来源 | 时长 |
| :-- | :-- | --: |
| ep01 | https://www.youtube.com/watch?v=kBdfcR-8hEY | 3296s |
| ep02 | https://www.youtube.com/watch?v=0O2Rq4HJBxw | 3310s |
| ep03 | https://www.youtube.com/watch?v=Qw4l1w0rkjs | 3308s |
| ep04 | https://www.youtube.com/watch?v=MGyygiXMzRk | 3299s |

> Bilibili 镜像（`BV1jt411m7rn?p=N`）在 `downloader.py` 里有目录，但生产机访问会被风控（HTTP 412），
> 因此 YouTube 是主源；`s0` 对任何 yt-dlp 支持的站点都能用。

---

## 2. 九个阶段，各自的门禁

```
S0 采集  链接 ──► 原始音频 + 视频 + 带时间戳逐字稿
S1 断句  逐字稿 ──► 完整英文句子（补标点/大小写、修 ASR 讹误）
S2 绑定  卡组 + 句子 ──► 每个词真正属于哪一句
S3 切媒体 句子 + 原始音频 ──► 按句子边界切片 + 取课堂截帧
S4 翻译  句子 ──► 带上下文的整句中文（AI 审校）
S4b 补译 其它卡组 ──► 补齐任何缺失译文（空译文会显示「暂无官方中文翻译」）
S5 落盘  产物 ──► 写回数据文件 + 断言校验
S6 词库  卡组 ──► 从卡组重建全景大词库（派生，不再手工维护）
S7 部署  线上 ──► 重启服务 + 端到端验收报告
```

| 阶段 | AI 把关 | 自动化断言（不过就停） |
| :-- | :-- | :-- |
| S0 | — | 元数据可取、时长与目录一致、音视频时长相符、逐字稿段数/跨度/单调性 |
| S1 | 分句 + 批量复核 + 碎片复核（须回填签名） | 严格连续划分、token 重叠下限、词数/时长上限、标点覆盖、时间轴单调 |
| S2 | 疑难词逐条裁定并要求**原样摘录 evidence** | 词必须出现在绑定句中（词形变化 + evidence 子串校验） |
| S3 | — | `ffprobe` 时长一致（±0.30s）、文件齐备、帧有效 |
| S4 | 翻译 + 审校（只打标）+ 单句重译 | 一句一译、无英文残留、无占位短译 |
| S4b | 同上 | 无空译文 |
| S5 | — | 句子包含目标词、切片头尾覆盖整句、时长一致、词数/分级守恒、两份副本一致 |
| S6 | — | 覆盖 0 缺失、**词库文本必须与卡片逐字相同**、SRS 进度只增不减、词典条目不丢失 |
| S7 | — | 服务存活、线上卡片完整、资产可达（源站+公网）、词库↔卡片一致 |

---

## 3. 为什么需要这些门禁（都踩过）

| 坑 | 现象 | 现在的防线 |
| :-- | :-- | :-- |
| 切片按 ASR 分段组切 | 88% 的切片两头都在句子中间 | S1 重建真句子 → S3 按句子边界切 → S5 断言头尾覆盖 |
| 让模型「整批重做」 | 内容在 id 之间串位 | 失败只以 ≤6 条小批重试 |
| 单句裁决不回填签名 | 结论落到相邻句 | 要求回显 `sig`，校验后采用 |
| 词库是手工副本 | 与卡片 224/245 条文本不一致、Ep01 只覆盖 23/163 | S6 改为从卡组派生 + 逐字一致断言 |
| 空译文 | 卡片显示「暂无官方中文翻译」 | S4b 补齐 + 门禁禁止空译文 |
| 采集失效 | Bilibili 风控 412 | S0 元数据/时长双重校验，YouTube 主源 |

---

## 4. 运行环境

- 服务器需 `ffmpeg/ffprobe`、`yt-dlp`、`python3`；原始媒体放 `data/raw_audio/`、`data/raw_video/`。
- 环境变量：`VOCAB_APP_DIR`（应用目录）、`VOCAB_WORK_DIR`（中间产物/缓存/报告）、`VOCAB_EP`（卡组 id）。
- AI Key：`data/secret_config.json`（不入库）或 `DEEPSEEK_API_KEY`。
- 所有 AI 调用按内容哈希落盘缓存，重跑几乎不花钱且结果可复现。
- 产物：`<work>/out/`（句子/映射/译文/验收报告）、`<work>/reports/`（各阶段门禁 JSON+MD）。

## 5. 新增一集（任意链接）

1. `s0` 会自动抓媒体与字幕（`data/source_catalog.json` 有目录的走目录，否则用你给的 `--url`）；
2. 若该集还没有卡组（词表），流水线会在 S2 停下并提示——目前词表仍需先由选词环节生成
   （应用内的「链接导入」走的是 `/api/import/link` 的 AI 抽词）；
3. 生成卡组后重跑：`python deliver.py --episode <新id> --from s1 --write`。
