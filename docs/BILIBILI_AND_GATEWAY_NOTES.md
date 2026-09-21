# B 站取错视频 · 编造目录 · AI 网关切换（2026-09-21 处理记录）

## 一、用户报告

> 复制了 `https://www.bilibili.com/video/BV1NdwWe6Epf?vd_source=...`（The Indicator from
> Planet Money），但提取出来的还是**哈佛公正课**；删掉原有链接后「一个也是一样的」；
> 「不过貌似提取出来的也是"错误"」。

## 二、复现与根因：三个彼此独立的缺陷

### 缺陷 1（前端）批量弹窗自动预填示例链接 → 识别的是别人那条

```js
function openBatchMediaModal() {
  ...
  if (input && !input.value.trim()) insertBatchPresetUrls('sciam');   // 打开就填 3 条示例
}
```

用户随后粘贴自己的链接，输入框里就有多条；而「智能嗅探」只读 **第一行**
（`text.split('\n')[0]`），也就是示例链接 → 返回示例那条课。批量提取则会把**所有**行都处理，
实测 `[哈佛BV, 用户BV]` → 13 条结果（12 条哈佛 + 1 条用户的）。这正好印证了用户当时的猜测
（"你原来有链接在上面，没删掉的话相当于好几个链接"）。

**修复**：弹窗不再预填（示例仍保留为**按钮**，需主动点击）；智能嗅探改为只保留**最后粘贴的那一条**
并弹窗告知；示例按钮里的 B 站 id 全部移除。

### 缺陷 2（后端）B 站官方接口 412 → 落到**硬编码的假标题**

实测 `api.bilibili.com/x/web-interface/view?bvid=...` 从本机对**两个视频都返回 HTTP 412**
（风控，响应体是 HTML 报错页，不是 JSON）。两个 B 站解析函数在 API 失败后都回落到写死的占位标题：

| | 修复前（占位/编造） | 修复后（真实） |
|---|---|---|
| 用户的视频 | `Bilibili 经典公开课深度精讲 (BV1NdwWe6Epf)` | `【0120The Indicator from Planet Money】谁在为加州无法投保的房屋负责？…` |
| 作者 | `Bilibili 主讲人` | `Gabriel的英语杂货铺` |
| 时长 | `45 分钟`（写死） | `10 分钟`（真实 638s） |

**修复**：元数据与字幕改以 **yt-dlp 为主**（本机实测可用），官方 API 仅作回退；两者都失败时
**只显示 BV 号并明确说明未取到真实信息**，不再编造描述性标题。

### 缺陷 3（数据）「经典名校公开课知识图谱合集库」是**编造目录**

`BILIBILI_COLLECTIONS_CATALOG` 声称 `BV1jt411m7rn` 是「哈佛大学公开课：公正 Justice（全12集官方精校完整版）」，
并附 12 个虚构分集（`?p=1..12`）。yt-dlp 实测该 id 是：

```
【fl原创音乐】 Unreal Rainbow  不知道做的是什么鬼..   by 冰之龙晶   3:12   271 次播放
```

一个 3 分钟音乐视频。**该目录、它虚构的 12 个分集、以及前端教用户粘贴这个 id 的示例，全部删除**；
合集改为用 yt-dlp 的 flat playlist / 官方 API 的真实分 P 数据识别。

> 这也修正了 `docs/ep01_REBUILD_NOTES.md` 里「B站合集 BV1jt411m7rn 实测可展开 12 集」的说法。

## 三、线上验收（公网实测，21 项全过）

```
detect-collection(用户链接)   → 真实标题 + 真实 UP 主，total_episodes=1
detect-collection(哈佛BV)     → 【fl原创音乐】Unreal Rainbow（不再声称哈佛 12 集）
batch-extract([哈佛BV,用户BV]) → 2 条（修复前 13 条），各自真实标题
batch-extract(用户链接)        → has_subtitles=false, transcript_source=unavailable, 正文为空
                                 （不再用编造文本冒充"课堂原文"；下载链接仍然给出）
/api/import/link(无字幕链接)   → 422，并说明"请改用带字幕来源或粘贴 SRT/VTT 文稿"
前端                          → 不再预填示例；页面已无 BV1jt411m7rn；只保留最后粘贴的链接
```

回归门禁：**导出 389/389 通过**、**反造假 S8 15/15 通过**。

## 四、AI 网关切换（原 DeepSeek 账户余额耗尽）

原账户所有 AI 阶段报 `HTTP 402 Insufficient Balance`，导致 ep09/10/11 的词表无法生成
（`s0b` 选词 3 次重试全失败）。改用新的 OpenAI 兼容网关：

- base：`http://<gateway>/v1`，模型：`deepseek-v4.1-flash`（该网关允许清单仅 `hy3` 与它）
- 凭据格式 `token;model` → **只有分号前那段是 key**（整串会 401）
- 凭据写入服务器 `data/secret_config.json`（0600，`/data/*` 线上 404 已验证），仓库内零残留

**代码改动（可配置化，不再写死厂商）**：`api_base`/`model`/`review_model` 按
「环境变量 → `secret_config.json` → 默认值」解析（`server.py` 与流水线 `config.py` 同一规则）；
操作者自己配置的网关主机自动进入 `ALLOWED_AI_HOSTS`，且**只对该主机允许 http**，
调用方自带 `api_base` 的 SSRF 防护不受影响。

**推理模型加固（`ai_gate.py`）**：推理模型的思考 token 也计入 `max_tokens`，
`max_tokens=64` 时实测 `finish_reason=length` 且正文被截断成 `{"items`。现在：
`finish_reason=length` 或正文为空 → **预算翻倍重试**（上限 32768），
且**截断的响应绝不写入缓存**（否则会污染之后所有同 key 的运行）。
线上实测生效：

```
ai[ep09_s4_rev_00] 0 chars finish=length budget=3000
  → attempt 1/4 truncated; retrying with max_tokens=6000
  → 94 chars finish=stop budget=6000        ✓
```

## 五、Harvard《公正》全系列现状

| 集 | 词表 | 线上 | 备注 |
|---|---|---|---|
| ep01 | 117 | 200 | 已按标准流程重建（163→117，全部可溯源） |
| ep02 | 215 | 200 | |
| ep03 | 44 | 200 | |
| ep04–ep08 | 51–105 | 200 | 已上线；**本轮修好了标题**（原先显示 `ep04`…） |
| ep09–ep11 | 补建中 | — | 有音频/转写/断句，缺词表；AI 恢复后正在跑 |
| ep12 | 92 | 200 | |
| yale_ep01 | 32 | 200 | |
| 考试词表 | 600×5 + SAT | 200 | 另一工作流用 ECDICT(MIT)+Tatoeba 导入 |
| hj_longsent | 97 | 200 | 长难句精读（真实讲座句 + 已审校译文） |

**标题修复**：新增 `s5c_apply_catalog_meta.py`，把 `source_catalog.json` 里**已验证的真实元数据**
（英文标题 / 中文标题 / 时长 / 来源 URL）盖到词表上；此前 ep04–ep12 线上标题是裸 id。
门禁：词数不变、只允许改元数据字段、写入后不得再出现裸 id 标题。已重启生效。

## 六、遗留

1. **ep09–ep11 词表补建**正在后台运行（`logs/series_ep09_11.log`），完成后需跑 S6/S7/S7B 并复核。
2. 旧 DeepSeek 账户若继续使用需充值；当前配置已指向新网关。
3. 新网关是 **http**（非 https），因此 `/api/ai-extract`、`/api/test-connection`
   这两个「调用方自带 key」的端点仍只接受 https（除操作者配置的主机外）。
4. `data/secret_config.json` 含明文 key（0600，未入版本库）；如需更强隔离可改为 systemd
   `EnvironmentFile`。
