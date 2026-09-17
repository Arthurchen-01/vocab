# -*- coding: utf-8 -*-
"""S1 - rebuild real English sentences from raw ASR segments (final).

Why: the shipped Ep02 clips were cut on arbitrary ASR *segment groups* (1-8
segments, ~14s), so both ends of a clip landed mid-sentence. This stage rebuilds
true sentences and keeps every timestamp anchored to the raw ASR segments.

Stages (each with an automated gate + an AI review where judgement is needed):
  1. boundaries : ONE AI pass over the whole numbered transcript -> sentence
                  ranges (inclusive segment indices). GATE: strict contiguous
                  partition of all segments.
  2. polish     : batched AI pass adding punctuation/case and repairing obvious
                  ASR errors. GATE per item: edge words preserved + token LCS vs
                  the ASR text >= 0.70; echo of raw unpunctuated text rejected;
                  failures are retried in chunks of <=6 (never "redo the batch",
                  which is what made the model shift content between ids).
  3. review     : batched AI pass with neighbour context -> merge_prev /
                  merge_next / asr_error / not_english.
  4. asr fixes  : flagged sentences are re-requested ONE at a time and validated.
  5. merge      : union-find over ADJACENT pairs only (no runaway chains), with
                  absurd-merge caps.
  6. split      : AI pass splitting still-overlong sentences at clause
                  boundaries, again as segment sub-ranges; iterated up to 3x,
                  newly created parts re-polished.
  7. fragments  : deterministic candidate detection (missing final punctuation /
                  starts with a continuation word / ends on a function word) and
                  a single-sentence AI verdict per candidate -> merge_prev,
                  merge_next, punctuate, or keep.
  8. gates      : partition, monotonic timeline, duration/word caps, LCS floor,
                  punctuation coverage, no mid-thought starts.

Output: out/<ep>_sentences.json -> [{sent_id,a,b,start,end,text,src_text,lcs}]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (EPISODE, MAX_SENTENCE_SECONDS, MAX_SENTENCE_WORDS,  # noqa: E402
                    MIN_SENTENCE_WORDS, OUT_DIR, TRANS_DIR, Report, lcs_ratio,
                    load_json, log, norm_words, save_json, tidy_english)
from ai_gate import _extract_json, ask_json, chat, usage  # noqa: E402

SEG_FILE = os.path.join(TRANS_DIR, f"{EPISODE}_transcript.json")
OUT_FILE = os.path.join(OUT_DIR, f"{EPISODE}_sentences.json")
POLISH_BATCH = 30
REVIEW_BATCH = 36
SPLIT_BATCH = 12
FRAGMENT_BATCH = 6
MAX_SPLIT_ROUNDS = 3

CONT_START = {"and", "but", "so", "because", "which", "that", "or", "nor", "yet", "if", "when",
              "while", "although", "though", "since", "as", "then", "also", "plus", "whereas"}
CONT_END = {"and", "but", "or", "the", "a", "an", "of", "to", "for", "with", "because", "that",
            "which", "if", "when", "my", "your", "his", "her", "their", "our", "in", "on", "at",
            "by", "from", "is", "are", "was", "were", "as", "than", "into", "about", "over"}
QUESTION_START = {"who", "what", "when", "where", "why", "how", "does", "did", "do", "is", "are",
                  "can", "could", "would", "should", "will", "has", "have", "was", "were"}

BOUNDARY_SYSTEM = """你是哈佛大学《公正》(Justice with Michael Sandel) 公开课的资深英文字幕编辑。
输入是自动语音识别(ASR)产出的**逐段**转写，每段形如 `序号|起始秒|文本`，段与段首尾相接。
你的唯一任务：把这 N 段划分成**语义完整的句子**，只输出每句占用的段序号区间。

硬性规则：
1. 每一段必须且只能属于一个句子；区间必须首尾相接、覆盖全部段（a0=0，最后一句的 b=N-1，且 b_i+1 = a_{i+1}）。
2. 句子必须是**完整的思想单位**：不能在半句处开始或结束。ASR 分段点经常落在句子中间，必须跨段合并。
3. 长句（超过约 30 个英文词）应在自然的小句边界（逗号、and/but/so/which/because 等）处切分，切分后每一部分仍要能独立成句。
4. 太短的碎片（少于 4 个英文词，且不是 "Thank you." "Right." 这类完整短句）应并入相邻句子。
5. 开场白、赞助商口播、观众笑声/掌声等明显非讲课内容的短段，也要按语义独立成句，不要硬塞进正文。
6. 不要改写、不要翻译、不要增删任何词；本步只决定“在哪里断句”。

只输出 JSON：{"sentences":[{"a":起段,"b":止段}, ...]}"""

POLISH_SYSTEM = """你是英文听写校对员。输入是若干条按 ASR 逐段拼接出来的英文句子（未加标点、可能有识别错误）。
请为每条输出**同一条句子**的规范英文文本，要求：
1. 补全标点（句末 . ! ?，句内逗号、撇号、引号）与首字母大写；专有名词首字母大写。
   若该句是疑问句，句末必须是 "?"。
2. 修正**明显的同音/近音识别错误**（例如 "Queen verses" -> "Queen versus"、"higher pressure" -> "higher pleasure"、"because of engages" -> "because it engages"、"Mills" 指人时 -> "Mill's"），以及明显的重复词、口吃。
3. 严禁改写、润色、简化、概括、翻译，严禁增删实词，严禁改变语序（除非 ASR 明显错序）。
4. 保留口语原貌（如 "alright"、"gonna" 之类如原样出现则保留），不要改成书面语。
5. 每条输出必须与输入**逐一对应**，不得合并或拆分句子，数量必须完全一致。
6. 即使原文已经通顺，也必须补上句末标点，并把首字母大写——不允许原样返回未加标点的文本。

只输出 JSON：{"items":[{"id":原样返回, "text":"校对后的句子"}]}"""

REVIEW_SYSTEM = """你是字幕质量审核员。输入是《公正》公开课已断句并校对过的连续句子（带 id 与相邻上下文）。
请**只报告确实存在的问题**，不要为了凑数而报问题；没有问题的句子不要出现在结果里。

问题类型与必填字段：
- {"id":N,"type":"merge_next","reason":"..."}  句子在语义中途被切断，后半部分在**下一句**里。
- {"id":N,"type":"merge_prev","reason":"..."}  该句是**上一句**的延续（碎片），应并入上一句。
- {"id":N,"type":"asr_error","corrected":"...","reason":"..."}  仍存在明显识别错误；corrected 必须保持原词序，只修正错误。
- {"id":N,"type":"not_english","reason":"..."}  非英文讲稿内容（音乐标记、噪声等）。

不要因为句子长、口语化、含专业术语、或含 "um/uh" 而报问题。同一处断句问题只报一次（在**前一句**上报 merge_next 即可，不要同时对后一句报 merge_prev）。

只输出 JSON：{"issues":[...]}"""

SPLIT_SYSTEM = """你是字幕编辑。输入是若干条**过长的英文句子**，每条给出其 ASR 段序号区间与逐段文本。
请把这些句子在自然的小句边界处切分成较短的句子，要求：

1. 只用给出的段序号切分：每条输出若干个子区间 {a,b}，必须**恰好覆盖**该句原本的 [a,b]（首尾相接、不重叠、不遗漏）。
2. 切分点必须落在小句边界（逗号、and/but/so/because/which/when 等从句起点）；不要把一个从句劈成两半。
3. 目标：每个子句 8-25 个英文词；如果一条长句包含多个完整句（有句号），就按句号切分。
4. 每个子句都要能独立读懂；不要产生少于 5 个英文词的碎片。
5. 如果该句其实已经足够自然、无法在不破坏语义的前提下切分，就原样返回单个区间。

只输出 JSON：{"splits":[{"id":句id,"parts":[{"a":起段,"b":止段}, ...]}, ...]}"""

FRAGMENT_SYSTEM = """你是字幕断句审核员。输入是若干条句子（每条带 id、签名 sig、上一句、当前句、下一句）。
请逐条判断该句是否**被从中间截断**，或只是缺少标点。

- "merge_prev"：该句是上一句的延续（它以从句/连词开头且缺少自己的主语、或上一句明显没说完）-> 应并入上一句。
- "merge_next"：该句本身没说完，后半部分在下一句里 -> 应与下一句合并。
- "punctuate"：该句语法完整、只是缺句末标点 -> 只需补标点。
- "keep"：完全正常，无需处理。

注意：口语讲课中大量句子以 And / So / But / Now 开头，这**属于正常完整句**，应判 "keep"；
只有当该句明显缺少主语或谓语、必须依赖相邻句子才能成立时才判合并。
必须为每一条输入都给出结论，并原样回填该条的 sig。

只输出 JSON：{"verdicts":[{"id":N,"sig":"原样回填","action":"merge_prev"|"merge_next"|"punctuate"|"keep","reason":"简短理由"}]}"""


# ------------------------------------------------------------------ helpers
def build_listing(segs, a=0, b=None):
    b = len(segs) - 1 if b is None else b
    return "\n".join(f"{i}|{segs[i]['start']:.2f}|{' '.join(str(segs[i].get('text', '')).split())}"
                     for i in range(a, b + 1))


def validate_partition(obj, n, lo, hi):
    """Ranges must exactly tile [lo, hi]."""
    if not isinstance(obj, dict) or not isinstance(obj.get("sentences"), list):
        return 'expected {"sentences":[{"a":int,"b":int}, ...]}'
    sents = obj["sentences"]
    if not sents:
        return "sentences is empty"
    expect = lo
    for k, s in enumerate(sents):
        if not isinstance(s, dict) or not isinstance(s.get("a"), int) or not isinstance(s.get("b"), int):
            return f"sentence #{k} needs integer a and b"
        if s["a"] != expect:
            return (f"sentence #{k} starts at a={s['a']} but the previous one ended at {expect - 1}; "
                    f"ranges must be contiguous and cover every segment exactly once")
        if s["b"] < s["a"]:
            return f"sentence #{k} has b<a"
        expect = s["b"] + 1
    if expect != hi + 1:
        return f"coverage ends at segment {expect - 1} but it must reach {hi}"
    return None


def sentence_from_range(segs, a, b):
    src = " ".join(" ".join(str(segs[i].get("text", "")).split()) for i in range(a, b + 1)).strip()
    return {"a": a, "b": b,
            "start": round(float(segs[a]["start"]), 3),
            "end": round(float(segs[b]["start"]) + float(segs[b]["duration"]), 3),
            "src_text": src, "text": src}


def renumber(sents):
    for k, s in enumerate(sents):
        s["sent_id"] = k
    return sents


def has_terminal_punct(t):
    return (t or "").rstrip().endswith((".", "!", "?"))


def punctuate(text):
    """Deterministic: capitalise + add a terminal mark (no AI involved)."""
    t = (text or "").strip()
    if not t:
        return t
    t = t[0].upper() + t[1:]
    if has_terminal_punct(t):
        return t
    w = norm_words(t)
    return t + ("?" if w and w[0] in QUESTION_START else ".")


def _edge_ok(src, out):
    a, b = norm_words(src), norm_words(out)
    if not a or not b:
        return False

    def close(x, y):
        return x == y or bool(set(x) & set(y))

    return close(a[:2], b[:2]) and close(a[-2:], b[-2:])


def item_ok(src, out, min_lcs=0.70, require_polish=False):
    out = (out or "").strip()
    if not out:
        return False
    if require_polish and out == src.strip() and not has_terminal_punct(src):
        return False
    return _edge_ok(src, out) and lcs_ratio(out, src) >= min_lcs


# ------------------------------------------------------------------ stage 1
def stage_boundaries(segs):
    user = (f"本集共 {len(segs)} 段 ASR 转写，格式为 `序号|起始秒|文本`。\n"
            f"请切分为语义完整的句子，并只返回段序号区间。\n\n{build_listing(segs)}\n\n"
            f"再次强调：a0=0，最后一句 b={len(segs) - 1}，区间首尾相接、全覆盖、不重复。")
    obj = ask_json(BOUNDARY_SYSTEM, user, tag=f"{EPISODE}_s1_boundaries",
                   validate=lambda o: validate_partition(o, len(segs), 0, len(segs) - 1),
                   max_tokens=8000, temperature=0.1)
    return obj["sentences"]


# ------------------------------------------------------------------ stage 2
def _polish_call(items, tag):
    payload = [{"id": i, "text": t} for i, t in items]
    user = ("请按**输入顺序**逐条校对下列句子，每条必须返回它自己的文本，"
            "不要在不同 id 之间错位，也不要合并或拆分条目：\n"
            + json.dumps(payload, ensure_ascii=False))
    obj = _extract_json(chat(POLISH_SYSTEM, user, tag=tag, max_tokens=6000, temperature=0.1))
    out = {}
    for it in (obj.get("items") or []):
        if isinstance(it, dict) and it.get("id") is not None and isinstance(it.get("text"), str):
            out[it["id"]] = it["text"].strip()
    return out


def polish_group(items, tag):
    good, bad = {}, []
    try:
        got = _polish_call(items, tag)
    except Exception as e:  # noqa: BLE001
        log("    polish %s call failed: %s", tag, str(e)[:140])
        got = {}
    for i, src in items:
        out = got.get(i)
        if out is not None and item_ok(src, out, require_polish=True):
            good[i] = out
        else:
            bad.append((i, src))
    for k in range(0, len(bad), 6):
        chunk = bad[k:k + 6]
        try:
            got2 = _polish_call(chunk, f"{tag}_retry{k // 6}")
        except Exception as e:  # noqa: BLE001
            log("    polish %s retry failed: %s", tag, str(e)[:140])
            continue
        for i, src in chunk:
            out = got2.get(i)
            if out is not None and item_ok(src, out, require_polish=True):
                good[i] = out
    return good


def stage_polish(sents, tag_prefix):
    changed = 0
    fallbacks = []
    for base in range(0, len(sents), POLISH_BATCH):
        batch = sents[base:base + POLISH_BATCH]
        good = polish_group([(s["sent_id"], s["src_text"]) for s in batch],
                            f"{EPISODE}_{tag_prefix}_polish_{base // POLISH_BATCH:02d}")
        for s in batch:
            new = good.get(s["sent_id"])
            if new is None:
                new = s["src_text"]
                fallbacks.append(s["sent_id"])
            s["lcs"] = round(lcs_ratio(new, s["src_text"]), 3)
            if new != s["text"]:
                changed += 1
            s["text"] = new
    return changed, fallbacks


# ------------------------------------------------------------------ stage 3/4
def stage_review(sents):
    issues = []
    ids_all = {s["sent_id"] for s in sents}
    for base in range(0, len(sents), REVIEW_BATCH):
        batch = sents[base:base + REVIEW_BATCH]
        ctx = []
        for s in batch:
            prev = sents[s["sent_id"] - 1]["text"] if s["sent_id"] > 0 else ""
            nxt = sents[s["sent_id"] + 1]["text"] if s["sent_id"] + 1 < len(sents) else ""
            ctx.append({"id": s["sent_id"], "prev": prev[-150:], "text": s["text"], "next": nxt[:150]})
        obj = ask_json(REVIEW_SYSTEM, "请审核下列句子：\n" + json.dumps(ctx, ensure_ascii=False),
                       tag=f"{EPISODE}_s1_review_{base // REVIEW_BATCH:02d}",
                       validate=lambda o: None if isinstance(o, dict) and isinstance(o.get("issues", []), list)
                       else 'expected {"issues":[...]}',
                       max_tokens=4000, temperature=0.0)
        for it in obj.get("issues", []):
            if isinstance(it, dict) and it.get("id") in ids_all:
                issues.append(it)
    return issues


def stage_asr_fixes(sents, issues, rep):
    flagged = []
    for it in issues:
        if (it.get("type") or "").lower() == "asr_error" and isinstance(it.get("id"), int):
            s = next((x for x in sents if x["sent_id"] == it["id"]), None)
            if s:
                flagged.append((s["sent_id"], s["src_text"]))
    if not flagged:
        rep.note("review flagged no ASR repairs")
        return 0
    good = polish_group(flagged, f"{EPISODE}_s1_asrfix")
    applied = 0
    for s in sents:
        if s["sent_id"] in good and good[s["sent_id"]] != s["text"]:
            s["text"] = good[s["sent_id"]]
            s["lcs"] = round(lcs_ratio(s["text"], s["src_text"]), 3)
            s["ai_corrected"] = True
            applied += 1
    rep.note(f"ASR repairs: {len(flagged)} flagged -> {applied} applied and validated")
    return applied


# ------------------------------------------------------------------ stage 5
def collect_merge_plan(issues, n):
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    merges = 0
    for it in issues:
        t = (it.get("type") or it.get("action") or "").lower()
        i = it.get("id")
        if not isinstance(i, int) or not (0 <= i < n):
            continue
        if t == "merge_next" and i + 1 < n:
            union(i, i + 1)
            merges += 1
        elif t == "merge_prev" and i - 1 >= 0:
            union(i - 1, i)
            merges += 1
    return parent, find, merges


def build_merged(sents, find, rep):
    n = len(sents)
    groups, cur = [], [0]
    for i in range(1, n):
        if find(i) == find(i - 1):
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)

    out, refused = [], []
    for g in groups:
        s = dict(sents[g[0]])
        if len(g) > 1:
            s["b"] = sents[g[-1]]["b"]
            s["end"] = sents[g[-1]]["end"]
            s["src_text"] = " ".join(sents[i]["src_text"] for i in g)
            s["text"] = " ".join(sents[i]["text"] for i in g).strip()
            s["lcs"] = round(min((sents[i].get("lcs") or 1.0) for i in g), 3)
            if (s["end"] - s["start"]) > MAX_SENTENCE_SECONDS * 3 or len(norm_words(s["text"])) > MAX_SENTENCE_WORDS * 3:
                refused.append((s["sent_id"], round(s["end"] - s["start"], 1), len(norm_words(s["text"]))))
                for i in g[1:]:
                    out.append(dict(sents[i]))
                s = dict(sents[g[0]])
        out.append(s)
    out.sort(key=lambda x: x["a"])
    renumber(out)
    if refused:
        rep.note(f"refused {len(refused)} absurd merges: {refused[:4]}")
    return out


# ------------------------------------------------------------------ stage 6
def merge_short_spans(sents, rep, min_span=0.8):
    """Glue sub-second 'sentences' onto a neighbour.

    A sentence whose audio span is shorter than the minimum clip length cannot
    produce a usable example clip (a word bound to it would get a <0.8s clip), so
    it is merged into the previous sentence - these are always ASR crumbs like a
    lone "Right." that the boundary pass left standing alone.
    """
    merged = 0
    while len(sents) > 1:
        idx = next((i for i, s in enumerate(sents) if (s["end"] - s["start"]) < min_span), None)
        if idx is None:
            break
        kind = "merge_prev" if idx > 0 else "merge_next"
        sents = build_merged(sents, collect_merge_plan([{"id": idx, "type": kind}], len(sents))[1], rep)
        merged += 1
    if merged:
        rep.note(f"merged {merged} sub-{min_span}s sentence crumbs into their neighbours")
    return sents


def stage_split(segs, sents, rep):
    """Iteratively split overlong sentences (segment-aligned, AI gated)."""
    new_parts_all = []
    for round_no in range(1, MAX_SPLIT_ROUNDS + 1):
        longs = [s for s in sents
                 if len(norm_words(s["text"])) > MAX_SENTENCE_WORDS
                 or (s["end"] - s["start"]) > MAX_SENTENCE_SECONDS]
        if not longs:
            rep.note(f"split pass: nothing over the caps after {round_no - 1} round(s)")
            break
        split_map = {}
        for base in range(0, len(longs), SPLIT_BATCH):
            batch = longs[base:base + SPLIT_BATCH]
            ids = [s["sent_id"] for s in batch]
            payload = [{"id": s["sent_id"], "a": s["a"], "b": s["b"],
                        "text": build_listing(segs, s["a"], s["b"])} for s in batch]

            def validate(o, ids=ids, batch=batch):
                if not isinstance(o, dict) or not isinstance(o.get("splits"), list):
                    return 'expected {"splits":[{"id":..,"parts":[{"a":..,"b":..}]}]}'
                got = {x.get("id"): x.get("parts") for x in o["splits"] if isinstance(x, dict)}
                if set(got) != set(ids):
                    return f"ids must match exactly; missing={sorted(set(ids) - set(got))[:5]}"
                for s in batch:
                    parts = got[s["sent_id"]]
                    if not isinstance(parts, list) or not parts:
                        return f"id {s['sent_id']}: parts must be a non-empty list"
                    expect = s["a"]
                    for p in parts:
                        if not isinstance(p, dict) or not isinstance(p.get("a"), int) or not isinstance(p.get("b"), int):
                            return f"id {s['sent_id']}: each part needs integer a and b"
                        if p["a"] != expect:
                            return (f"id {s['sent_id']}: parts must tile from segment {s['a']} "
                                    f"(got a={p['a']}, expected {expect})")
                        if p["b"] < p["a"]:
                            return f"id {s['sent_id']}: part with b<a"
                        expect = p["b"] + 1
                    if expect != s["b"] + 1:
                        return f"id {s['sent_id']}: parts must cover up to segment {s['b']}"
                return None

            try:
                obj = ask_json(SPLIT_SYSTEM, "请切分下列过长句子：\n" + json.dumps(payload, ensure_ascii=False),
                               tag=f"{EPISODE}_s1_split_r{round_no}_{base // SPLIT_BATCH:02d}",
                               validate=validate, max_tokens=4000, temperature=0.1)
            except RuntimeError as e:
                log("    split round %d batch %d failed: %s", round_no, base, str(e)[:140])
                continue
            for x in obj["splits"]:
                split_map[x["id"]] = x["parts"]

        out, news = [], []
        for s in sents:
            parts = split_map.get(s["sent_id"])
            if not parts or len(parts) == 1:
                out.append(s)
                continue
            for idx, p in enumerate(parts):
                ns = sentence_from_range(segs, p["a"], p["b"])
                if idx > 0:
                    ns["is_split_part"] = True
                news.append(ns)
                out.append(ns)
        out.sort(key=lambda x: x["a"])
        renumber(out)
        sents = out
        new_parts_all.extend(news)
        rep.note(f"split round {round_no}: {len(longs)} overlong -> {len(news)} parts")
    return sents, new_parts_all


# ------------------------------------------------------------------ stage 7
def fragment_candidates(sents):
    """Sentences that might be cut mid-thought.

    Deliberately over-inclusive: the AI verdict is the decision maker. Split
    parts (produced by the splitter at a clause boundary) are exempt from the
    "starts with a conjunction" rule - that start is intentional, otherwise the
    splitter and the fragment checker would fight each other.
    """
    cands = []
    for s in sents:
        w = norm_words(s["text"])
        if len(w) < 3:
            continue
        t = s["text"].strip()
        if not has_terminal_punct(t):
            cands.append(s)
        elif s.get("is_split_part"):
            continue
        elif s["sent_id"] > 0 and w[0] in CONT_START:
            cands.append(s)
        elif len(w) >= 4 and w[-2] in CONT_END:
            cands.append(s)
    return cands


def signature(text, n=5):
    return " ".join(norm_words(text)[:n])


def stage_fragments(sents, rep, round_no=1):
    """Verdicts on fragment candidates. Batched, with a signature echo so the
    model cannot slide answers onto neighbouring ids."""
    cands = fragment_candidates(sents)
    if not cands:
        rep.note(f"fragment pass {round_no}: no candidates")
        return sents
    issues, punctuated, kept = [], 0, 0
    for base in range(0, len(cands), FRAGMENT_BATCH):
        batch = cands[base:base + FRAGMENT_BATCH]
        payload = []
        for s in batch:
            i = s["sent_id"]
            payload.append({
                "id": i,
                "sig": signature(s["text"]),
                "prev": (sents[i - 1]["text"][-200:] if i > 0 else ""),
                "current": s["text"],
                "next": (sents[i + 1]["text"][:200] if i + 1 < len(sents) else ""),
            })
        ids = {p["id"]: p["sig"] for p in payload}

        def validate(o, ids=ids):
            if not isinstance(o, dict) or not isinstance(o.get("verdicts"), list):
                return 'expected {"verdicts":[{"id":..,"sig":"..","action":".."}]}'
            got = {v.get("id"): v for v in o["verdicts"] if isinstance(v, dict)}
            if set(got) != set(ids):
                return f"ids must match exactly; missing={sorted(set(ids) - set(got))[:5]}"
            for i, sig in ids.items():
                v = got[i]
                if v.get("sig") != sig:
                    return (f"id {i}: sig must be echoed exactly as given ({sig!r}); "
                            f"you returned {v.get('sig')!r}")
                if v.get("action") not in ("merge_prev", "merge_next", "punctuate", "keep"):
                    return f"id {i}: action must be merge_prev/merge_next/punctuate/keep"
            return None

        try:
            obj = ask_json(FRAGMENT_SYSTEM,
                           "请逐条判断下列句子：\n" + json.dumps(payload, ensure_ascii=False),
                           tag=f"{EPISODE}_s1_frag{round_no}_{base // FRAGMENT_BATCH:02d}",
                           validate=validate, max_tokens=2500, temperature=0.0)
        except RuntimeError as e:
            log("    fragment batch %d round %d failed: %s", base, round_no, str(e)[:140])
            continue
        for v in obj["verdicts"]:
            s = next((x for x in batch if x["sent_id"] == v["id"]), None)
            if not s:
                continue
            if v["action"] in ("merge_prev", "merge_next"):
                issues.append({"id": v["id"], "type": v["action"], "reason": v.get("reason", "")[:100]})
            elif v["action"] == "punctuate":
                s["text"] = punctuate(s["text"])
                punctuated += 1
            else:
                kept += 1
    rep.note(f"fragment pass {round_no}: {len(cands)} candidates -> {len(issues)} merges, "
             f"{punctuated} punctuated, {kept} kept")
    if issues:
        sents = build_merged(sents, collect_merge_plan(issues, len(sents))[1], rep)
    for s in sents:
        if not has_terminal_punct(s["text"]) and len(norm_words(s["text"])) >= 2:
            s["text"] = punctuate(s["text"])
    return sents


# ------------------------------------------------------------------ main
def main():
    rep = Report(f"{EPISODE}_s1_sentences")
    segs = load_json(SEG_FILE)
    if not segs:
        rep.check("raw transcript present", False, SEG_FILE)
        rep.write()
        return 1
    rep.check("raw transcript present", True, f"{len(segs)} segments")

    ranges = stage_boundaries(segs)
    rep.check("AI boundary pass returned a valid partition", True, f"{len(ranges)} sentences")
    sents = renumber([dict(sentence_from_range(segs, r["a"], r["b"]), sent_id=k)
                      for k, r in enumerate(ranges)])

    changed, fb1 = stage_polish(sents, "s1")
    rep.note(f"polish: {changed}/{len(sents)} rewritten, {len(fb1)} raw fallbacks")

    issues = stage_review(sents)
    rep.check("AI review pass executed", True, f"{len(issues)} issues reported")
    stage_asr_fixes(sents, issues, rep)

    plan = [i for i in issues if (i.get("type") or "").lower() in ("merge_prev", "merge_next")]
    parent, find, merges = collect_merge_plan(plan, len(sents))
    before = len(sents)
    if merges:
        sents = build_merged(sents, find, rep)
    rep.note(f"review merges: {merges} -> {before} to {len(sents)} sentences")

    # order matters: merging fragments can re-create overlong sentences and
    # splitting can expose new fragments, so iterate to a fixpoint (bounded).
    prev_state = None
    for cycle in range(1, 4):
        sents = stage_fragments(sents, rep, round_no=cycle)
        sents, parts = stage_split(segs, sents, rep)
        if parts:
            ch, fb = stage_polish(parts, f"s1_p{cycle}")
            rep.note(f"cycle {cycle}: split produced {len(parts)} parts, re-polished {ch}, {len(fb)} fallbacks")
        sents = merge_short_spans(sents, rep)
        state = (len(sents), sum(len(norm_words(s["text"])) for s in sents))
        if state == prev_state:
            rep.note(f"segmentation reached a fixpoint after {cycle} cycle(s)")
            break
        prev_state = state
    else:
        rep.note("segmentation hit the cycle cap (3) without a fixpoint")
    sents = merge_short_spans(sents, rep)

    # deterministic last sweep: no sentence may be left without a terminal mark
    swept = 0
    for s in sents:
        before = s["text"]
        s["text"] = tidy_english(s["text"])
        if len(norm_words(s["text"])) >= 2 and not has_terminal_punct(s["text"]):
            s["text"] = punctuate(s["text"])
        if s["text"] != before:
            swept += 1
    if swept:
        rep.note(f"cosmetic/punctuation sweep applied to {swept} sentences")

    # ------------------------------------------------------------ gates
    rep.check("partition complete after all AI passes",
              sents[0]["a"] == 0 and sents[-1]["b"] == len(segs) - 1
              and all(sents[i]["b"] + 1 == sents[i + 1]["a"] for i in range(len(sents) - 1)),
              f"{len(sents)} sentences covering segments 0..{len(segs) - 1}")

    low = []
    for s in sents:
        w = len(norm_words(s["text"]))
        if (s.get("lcs") or 0) < (0.75 if w >= 12 else 0.68):
            low.append((s["sent_id"], s.get("lcs"), w))
    low.sort(key=lambda x: x[1] or 0)
    rep.check("no AI rewriting of the lecture text (token overlap floor)", not low,
              str(low[:5]) if low else "all within tolerance")

    unpunctuated = [s["sent_id"] for s in sents if not has_terminal_punct(s["text"])]
    rep.check("every sentence ends with terminal punctuation", not unpunctuated,
              f"{len(unpunctuated)} left: {unpunctuated[:10]}")

    # NOTE: starting with And/So/But is normal in spoken lectures and the AI
    # fragment pass explicitly allows it - this is reported, not gated.
    conj_start = [s["sent_id"] for s in sents if len(norm_words(s["text"])) >= 3
                  and norm_words(s["text"])[0] in CONT_START and s["sent_id"] > 0]
    rep.note(f"{len(conj_start)} sentences start with a conjunction (normal for spoken lecture; "
             f"AI fragment pass reviewed them)")

    over_w = [(s["sent_id"], len(norm_words(s["text"]))) for s in sents if len(norm_words(s["text"])) > MAX_SENTENCE_WORDS + 8]
    over_s = [(s["sent_id"], round(s["end"] - s["start"], 1)) for s in sents if (s["end"] - s["start"]) > MAX_SENTENCE_SECONDS + 6]
    rep.check("sentence word cap respected", not over_w, str(over_w[:6]))
    rep.check("sentence duration cap respected", not over_s, str(over_s[:6]))

    durs = [s["end"] - s["start"] for s in sents]
    rep.check("timeline monotonic and non-overlapping",
              all(sents[i]["end"] <= sents[i + 1]["start"] + 0.001 for i in range(len(sents) - 1)),
              f"n={len(sents)} median={sorted(durs)[len(durs) // 2]:.1f}s "
              f"p90={sorted(durs)[int(len(durs) * 0.9)]:.1f}s max={max(durs):.1f}s")
    rep.check("every sentence has a usable audio span (>=0.8s)",
              all(d >= 0.8 for d in durs), str([s["sent_id"] for s, d in zip(sents, durs) if d < 0.8][:6]))
    tiny = [s["sent_id"] for s in sents if len(norm_words(s["text"])) < MIN_SENTENCE_WORDS]
    rep.note(f"{len(tiny)} sentences under {MIN_SENTENCE_WORDS} words (kept as real interjections): {tiny[:8]}")

    save_json(OUT_FILE, sents)
    rep.note(f"wrote {OUT_FILE} ({len(sents)} sentences)")
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS1 %s - %d sentences, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(sents), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
