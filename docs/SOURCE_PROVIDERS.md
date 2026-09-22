# 来源解析架构：可插拔 provider 链 + 本地 ASR 兜底

> 对应问题：「能不能对接其他 B 站/YouTube 工具？多个 backup，按用户和我们的需求调整？还是现在已经完全打通了？」

## 一、先回答：当时**没有**完全打通，缺口是同一个东西

2026-09-21 在生产机上实测（不是推测）：

| 环节 | YouTube | Bilibili | 科学美国人 | 直链媒体 | 字幕文件 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 真实元数据 | ✅ yt-dlp | ✅ yt-dlp（官方 API 被 **412** 挡） | ✅ | ✅ | — |
| 音视频下载 | ✅ | ✅ | ✅ Megaphone CDN | ✅ | — |
| **真实字幕** | ✅ 人工 + 自动（`en`/`zh-Hans`） | ❌ **完全没有**（`subs=NA`、无自动字幕） | ⚠️ 文章正文（非音频同步） | ❌ | ✅ SRT/VTT |
| **能否产出词表** | ✅ | ❌ 卡在字幕 | ⚠️ 可用正文 | ❌ | ✅ |

即：**YouTube 一直通**（12 集就是这么产出的）；**Bilibili 只通了"下载 + 真实标题"，没通字幕**，
而没字幕就不能做词表（本项目明确拒绝编造）。

## 二、现在：本地 ASR 把这个死胡同拆掉了

`providers/whisper_asr.py` 用本机 `faster-whisper` 转写已下载的音频：

| 指标 | 实测值 |
| :--- | :--- |
| 机器 | 16 vCPU（AMD EPYC 7K62）/ 15 GB 内存 / **无 GPU** |
| 模型 | `small` int8（467 MB，已缓存） |
| 速度 | 10.6 分钟音频 → 转写 58.8s（**10.9x 实时**，空载）；有并发时实测 1.7x |
| 质量 | 180 段 / 1800 词；121 段以标点结尾、122 段首字母大写；人名与专有名词正确 |

推算：**55 分钟讲座约 5-30 分钟**（取决于机器负载）。

**诚实标注**：ASR 产物一律 `transcript_source=whisper_asr:<model>` +
`is_machine_transcript=True`，卡片与导出都能区分"机器转写"和"人工/平台字幕"。

**模型下载的坑（已解）**：本机 `huggingface.co` 与 `hf-mirror.com` 通，但
`cdn-lfs.huggingface.co` 与 Xet CAS 端点（`cas-server.xethub.hf.co`）**不通**，默认客户端路径
报 `File reconstruction error`。解法是 `HF_ENDPOINT=https://hf-mirror.com` +
`HF_HUB_DISABLE_XET=1`（已写进 `whisper_asr._asr_env()` 与 S0 的 `asr_env()`）。

## 三、架构：能力声明，而不是写死的顺序

改动前：`downloader.py` 里 "Tier 1..4" **只是文案**，实际是一条 `if/elif` 链 ——
加工具要改核心文件、不能按需求切换、降级顺序是拍脑袋写的。

```
providers/
  base.py       Provider 协议 + 能力常量（metadata / media / subtitles / asr）+ 注册表
  policy.py     按请求/按用户的开关（数据，不是代码分支）
  health.py     每个 (provider, host) 的实测成功率与耗时 → 决定链的顺序
  resolver.py   选链 → 合并各 provider 的部分结果 → 记录健康度 → 标注机器转写
  ytdlp_provider.py   YouTube / Bilibili / 任意 yt-dlp 支持的站点
  bbdown.py           B 站专用下载器（**自探针**：被风控时自动不参与，见下）
  youget.py           备用下载器（中文视频站）
  bilibili_cc.py      B 站官方接口：元数据 + CC/AI 字幕（走 WBI 端点，见下）
  direct_media.py     直链音视频
  direct_subtitle.py  SRT/VTT/DownSub 文本
  sciam.py            科学美国人播客 CDN + 文章正文
  whisper_asr.py      本地转写兜底（唯一能处理"完全没字幕"的来源）
```

`downloader.py` 保留原有公开函数并改为**委托**，所以 `server.py` 一行没改。

### ★ B 站的 412 是「按接口」封的（2026-09-22 实测）

这条是理解整件事的关键。**同一台机器**上：

| 接口 | 结果 |
| :--- | :--- |
| `x/web-interface/view` | **HTTP 412**（风控）← BBDown 1.6.3 只用这个 |
| `x/web-interface/wbi/view` | **HTTP 200**，完整 JSON ← yt-dlp 用这个 |
| `x/web-interface/view/detail` | HTTP 412 |
| `x/player/pagelist` | HTTP 200 |
| `x/player/wbi/v2` | HTTP 200（需有效 cid） |

裸 curl、带 UA+Referer、带 `buvid3` cookie —— 对 `x/web-interface/view` **全都是 412**；
而 WBI 版本**什么都不用带**就返回 200。所以：

- **yt-dlp 能用**是因为它走 WBI 路线（同机 B 站元数据 8/8 成功、下载到 10.7 MB 真实音频）；
- **BBDown 不能用**是因为它只调被封的那个老接口，报错甚至写着"请尝试升级到最新版本"，
  而 **1.6.3 已经是上游最新版（2024-08）**；
- 我自己的 `bilibili_cc` 原先也用被封的那个接口（健康度一直 0/3），
  **已改为 WBI 优先 + 老接口回退**。

### BBDown：装了，但**自探针**让它自动不参与

BBDown 在 WEB / TV / APP / INTL **四种模式下全部 412**，带 cookie 也一样。
与其上线一个"永远失败"的 provider（会给每次 B 站解析加一次超时 + 一条失败健康记录），
`bbdown.py` 会**自检**：

```python
def available(self):
    # 24h 缓存一次探针：让 BBDown 解析一个固定视频
    # 412 -> False -> 整个 provider 被排除出链，零成本零噪音
```

现状是「已安装、已接线、被排除」；**哪天 B 站放开那个接口、或上游出了新版、
或配上登录 cookie，它会自动加入链，不需要改代码**。探针结果缓存在
`out/bbdown_probe.json`（默认 24h TTL），不是每次请求都跑。

### 三个关键设计

1. **按能力组链**：`need = (metadata, media, subtitles)`，resolver 自动挑能满足的 provider；
   ASR **不在候选链里**，只走显式的最后兜底（否则它会绕过策略开关 —— 这是门禁抓到的真 bug）。
2. **按实测健康度排序**：每次解析记录 `(provider, host) → 成功/失败/耗时`，
   下次优先用"这个站上确实好用的那个"。例如现在：
   ```
   yt-dlp@www.bilibili.com       8/8 ok  mean 7.4s
   whisper_asr@www.bilibili.com  7/7 ok  mean 400s
   bilibili_cc@www.bilibili.com  0/3 ok  mean 0.1s   ← 官方 API 被 412
   you-get@www.bilibili.com      0/3 ok  mean 11s
   ```
3. **按需求调策略**（`providers/policy.py`）：

   | 开关 | 默认 | 作用 |
   | :--- | :--- | :--- |
   | `quality` | `best` | `fast` = 第一个满足就停；`best` = 问遍所有能做的，取最好的真实逐字稿 |
   | `allow_asr` | `true` | 关掉后，没字幕的来源**明确报错**，绝不用别的东西凑 |
   | `asr_model` | `small` | `tiny`/`base`/`small`/`medium` |
   | `asr_max_minutes` | 90 | 超过就跳过 ASR（控成本） |
   | `max_minutes` | 0 | 来源时长上限 |
   | `cookies_file` | 空 | 登录态 cookie（解锁 B 站 AI 字幕） |

   调用方可以按用途覆盖：**媒体下载中心只要 `(metadata, media)`，永远不花时间转写**；
   导入路径才要逐字稿、才可能触发 ASR。

## 四、怎么加一个新工具（配方）

```python
# providers/my_tool.py
from providers.base import CAP_MEDIA, CAP_METADATA, Provider

class MyToolProvider(Provider):
    name = "my-tool"
    capabilities = (CAP_METADATA, CAP_MEDIA)   # 只声明它真能给的东西
    priority = 45                              # 只在健康度相同时用来打破平局

    def available(self):                       # 依赖缺失 → 只摘掉自己，不炸整条链
        import shutil; return bool(shutil.which("my-tool"))

    def can_handle(self, url):
        return "example.com" in url

    def fetch(self, url, need, policy):
        ...                                    # 拿不到就返回 {"success": False, "error": ...}
        return {"success": True, "title": real_title, "direct_media_url": stream,
                "transcript": "", "has_subtitles": False}   # 不许编造
```

然后在 `providers/base.py` 的 `load_registry()` 里加一行。**不需要改 resolver、不需要改 app。**

## 五、验证（`tools/quality_pipeline/provider_matrix_gate.py`）

在生产机上跑，**26 项全过**，其中包括：

```
[x] YouTube: real transcript obtained — source=yt-dlp:srt
[x] YouTube: ASR was not invoked (no wasted minutes) — yt-dlp:ok(9.39s)
[x] Bilibili: a transcript is produced where none exists — whisper_asr:small
[x] Bilibili: the transcript is labelled machine-generated — is_machine_transcript=True
[x] policy allow_asr=off: no transcript is claimed — source=unavailable
[x] policy allow_asr=off: the refusal is explicit — ... | whisper_asr:no(0s)
[x] quality=fast consults fewer providers than quality=best — 1 providers
[x] has_subtitles always agrees with whether text was obtained — []
```

这个门禁在开发过程中**抓到了本次改动自己的一个真 bug**：`whisper_asr` 声明了
`CAP_SUBTITLES` 且 `can_handle()` 接受任意 URL，于是它混进了候选链，
在 `allow_asr=off` 时仍然跑了 302 秒并产出逐字稿。修法是把它排除出候选链，只保留显式兜底。

## 六、仍然不通 / 待办

| 项 | 状态 | 说明 |
| :--- | :--- | :--- |
| **下载（B 站 / YouTube）** | ✅ **已实测打通** | `download_gate.py` 18/18：B 站 10.7 MB、YouTube 166 MB、直链 16.7 MB，全是真实媒体字节 |
| B 站 **AI 字幕**（`--cookies`） | **未实测** | 需要登录 cookie。若可用，可省掉 ASR 开销（预期可行，未验证） |
| `BBDown` | ⚠️ 已装、已接线、**被自探针排除** | 见上文：它只调被封的 `x/web-interface/view`；四种 API 模式全 412 |
| `bilibili_cc` | ✅ **已修好** | 改用 WBI 端点后能返回平台元数据；有 CC 的视频还能直接拿平台字幕 |
| `you-get` 在 B 站 | ❌ 0/3 | 本机实测失败（失败原因与 yt-dlp 不同，保留作备份仍有价值） |
| ASR 语言 | 仅 `en` | 讲座是英文；中文/多语需扩参数 |
| ASR 质量门禁 | 已兼容 | S1 断句重建本来就是为 ASR 噪声设计的，ASR 产物走同一套门禁 |
