# -*- coding: utf-8 -*-
"""S4 - rewrite the Chinese translations with real context (AI), then review them.

The shipped translations were mechanical, clause-fragment glosses: the same
English sentence carried three different Chinese renderings depending on which
word pointed at it, and none of them read like a lecture. This stage translates
each *sentence* once, with its neighbouring sentences as context and the target
words' authoritative glosses pinned, then runs an AI review pass that may only
FLAG problems (rewrites are produced afterwards, one sentence per call, so the
reviewer can never shift content between ids).

Output: out/<ep>_translations.json -> {sent_id: {cn, reviewed, issues}}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log,  # noqa: E402
                    norm_words, save_json, tidy_english)
from ai_gate import ask_json, usage  # noqa: E402

SENTS_FILE = os.path.join(OUT_DIR, f"{EPISODE}_sentences.json")
MAP_FILE = os.path.join(OUT_DIR, f"{EPISODE}_word_map.json")
CURRICULUM = os.path.join(DATA_DIR, f"{EPISODE}_curriculum_final_audited.json")
OUT_FILE = os.path.join(OUT_DIR, f"{EPISODE}_translations.json")

TRANSLATE_BATCH = 6
CONTEXT_SPAN = 2

TRANSLATE_SYSTEM = """你是哈佛大学《公正》(Justice with Michael Sandel) 公开课中文字幕的资深译者。
输入是若干条**连续**的英文字幕句子（句首带 id，并给出前后文作为语境），以及这些句子里出现的**目标词及其权威中文释义**。

请为**每一条**英文句子给出自然、准确的中文翻译，要求：
1. **按整句翻译**，读起来像中文课堂字幕：符合中文表达习惯，不要逐词硬译，不要保留英文语序。
2. **语境连贯**：这是连续讲课内容，术语必须前后一致；代词指代要按上下文补明（如 he 指 Mill 时译为"密尔"），必要时补出隐含主语。
3. **术语准确**：目标词必须使用给定的权威释义用词；哲学/法学专有名词用学界通行译法（utilitarianism 功利主义、higher pleasure 高级快乐、categorical 绝对的/定言的、cost-benefit analysis 成本效益分析 等）。
4. **口语保留口语感**：Sandel 与学生的对话要译得像对话（"好吧"、"那么"、"你们觉得呢"），不要翻译成书面报告腔。
5. 人名、书名、专有名词用通行中文译名；确实无通行译名的专有名词（如 Pinto 车型、Rembrandt 画作）可保留原文或音译，但最多保留少量必要原词。
6. 严禁增删英文原句的信息，严禁加解释性注释，严禁合并或拆分条目。
7. 只输出 JSON：{"items":[{"id":原样返回,"cn":"中文译文"}]}，数量与输入完全一致。"""

REVIEW_SYSTEM = """你是中文字幕审校。输入是若干条连续英文句子及其现有中文译文（带 id）。
请**只标记确实有问题的条目**，不要重写译文，也不要为了凑数而报问题。

问题类型：
- "unfaithful"：译文与英文含义不符、漏译或多译。
- "mechanical"：逐词硬译、语序生硬、不像中文口语字幕。
- "context": 指代不清或与相邻句子不一致（人称、时态、术语）。
- "term"：术语译法与给定权威释义不符。
- "english": 中文里残留了不必要的英文词。

没有问题的条目不要出现在结果里。只输出 JSON：{"issues":[{"id":N,"type":"...","note":"简短说明"}]}"""

RETRY_SYSTEM = """你是哈佛《公正》公开课中文字幕译者。下面给出**一条**英文句子、它的上下文、以及审校意见。
请给出最终中文译文：自然、准确、符合课堂口语，术语按给定释义，不增删信息。
只输出 JSON：{"cn":"最终中文译文"}"""


def main():
    rep = Report(f"{EPISODE}_s4_translation")
    sents = load_json(SENTS_FILE)
    wmap = load_json(MAP_FILE)
    words = load_json(CURRICULUM)
    if not (sents and wmap and words):
        rep.check("inputs present", False, "missing sentences/word_map/curriculum")
        rep.write()
        return 1

    sent_by_id = {s["sent_id"]: s for s in sents}
    used = sorted({m["sent_id"] for m in wmap["words"] if m})
    rep.check("inputs present", True, f"{len(sents)} sentences, {len(used)} need translation")

    # target words (with authoritative glosses) per sentence
    gloss_by_sent = {}
    for m in wmap["words"]:
        w = next((x for x in words if x["word"] == m["word"]), None)
        if w:
            gloss_by_sent.setdefault(m["sent_id"], []).append(
                {"word": w["word"], "def_cn": w.get("def_cn", ""), "pos": w.get("pos", "")})

    def ctx_for(sid):
        lo, hi = max(0, sid - CONTEXT_SPAN), min(len(sents) - 1, sid + CONTEXT_SPAN)
        return [{"id": j, "text": tidy_english(sent_by_id[j]["text"])} for j in range(lo, hi + 1)]

    def en_of(sid):
        return tidy_english(sent_by_id[sid]["text"])

    translations = {}
    failed = []
    for base in range(0, len(used), TRANSLATE_BATCH):
        batch = used[base:base + TRANSLATE_BATCH]
        payload = []
        for sid in batch:
            payload.append({
                "id": sid,
                "context": [c for c in ctx_for(sid) if c["id"] != sid],
                "text": en_of(sid),
                "target_words": gloss_by_sent.get(sid, []),
            })
        ids = set(batch)

        def validate(o, ids=ids):
            if not isinstance(o, dict) or not isinstance(o.get("items"), list):
                return 'expected {"items":[{"id":..,"cn":".."}]}'
            got = {it.get("id"): (it.get("cn") or "").strip() for it in o["items"] if isinstance(it, dict)}
            if set(got) != ids:
                return (f"ids must match exactly; missing={sorted(ids - set(got))[:5]} "
                        f"extra={sorted(set(got) - ids)[:5]}")
            for i in ids:
                if len(got[i]) < 2:
                    return f"id {i}: translation too short"
            return None

        try:
            obj = ask_json(TRANSLATE_SYSTEM,
                           "请翻译下列句子（context 仅供理解语境，不要翻译 context 本身）：\n"
                           + json.dumps(payload, ensure_ascii=False),
                           tag=f"{EPISODE}_s4_tr_{base // TRANSLATE_BATCH:02d}",
                           validate=validate, max_tokens=6000, temperature=0.3)
        except RuntimeError as e:
            log("    translation batch %d failed: %s", base, str(e)[:140])
            failed.extend(batch)
            continue
        for it in obj["items"]:
            translations[it["id"]] = {"cn": it["cn"].strip(), "issues": []}
    rep.check("first-pass translations produced for every sentence", not failed,
              f"{len(translations)}/{len(used)}; failed: {failed[:8]}")

    # ---- AI review pass (flags only) --------------------------------
    flagged = {}
    for base in range(0, len(used), TRANSLATE_BATCH):
        batch = [s for s in used[base:base + TRANSLATE_BATCH] if s in translations]
        if not batch:
            continue
        payload = [{"id": sid, "en": en_of(sid), "cn": translations[sid]["cn"]} for sid in batch]
        ids = {p["id"] for p in payload}
        try:
            obj = ask_json(REVIEW_SYSTEM, "请审校下列译文：\n" + json.dumps(payload, ensure_ascii=False),
                           tag=f"{EPISODE}_s4_rev_{base // TRANSLATE_BATCH:02d}",
                           validate=lambda o: None if isinstance(o, dict) and isinstance(o.get("issues", []), list)
                           else 'expected {"issues":[...]}',
                           max_tokens=3000, temperature=0.0)
        except RuntimeError as e:
            log("    review batch %d failed: %s", base, str(e)[:140])
            continue
        for it in obj.get("issues", []):
            if isinstance(it, dict) and it.get("id") in ids and it.get("type") in (
                    "unfaithful", "mechanical", "context", "term", "english"):
                flagged.setdefault(it["id"], []).append(f'{it["type"]}: {it.get("note", "")[:120]}')
    rep.note(f"AI review flagged {len(flagged)} of {len(translations)} translations")

    # ---- re-translate the flagged ones, one sentence per call --------
    fixed = 0
    for sid, notes in flagged.items():
        payload = {"text": en_of(sid), "context": ctx_for(sid),
                   "target_words": gloss_by_sent.get(sid, []), "review_notes": notes,
                   "previous_translation": translations[sid]["cn"]}
        try:
            obj = ask_json(RETRY_SYSTEM, json.dumps(payload, ensure_ascii=False, indent=1),
                           tag=f"{EPISODE}_s4_fix_{sid}",
                           validate=lambda o: None if isinstance(o, dict) and len((o.get("cn") or "").strip()) >= 2
                           else 'expected {"cn":"..."}',
                           max_tokens=800, temperature=0.3)
        except RuntimeError as e:
            log("    re-translation %d failed: %s", sid, str(e)[:120])
            continue
        translations[sid] = {"cn": obj["cn"].strip(), "reviewed": True, "review_notes": notes}
        fixed += 1
    rep.note(f"re-translated {fixed} flagged sentences individually")

    # ---- gates ------------------------------------------------------
    rep.check("all used sentences have a translation", len(translations) == len(used),
              f"{len(translations)}/{len(used)}")

    latin = []
    for sid, t in translations.items():
        runs = re.findall(r"[A-Za-z][A-Za-z'\- ]{3,}", t["cn"])
        if runs:
            latin.append((sid, runs[:3]))
    rep.check("no long English residue inside Chinese", len(latin) <= max(2, len(translations) // 40),
              f"{len(latin)} sentences contain Latin runs (proper nouns allowed): {latin[:5]}")

    short = [(sid, len(t["cn"])) for sid, t in translations.items()
             if len(t["cn"]) > 2 and len(t["cn"]) < 0.10 * len(sent_by_id[sid]["text"])]
    rep.check("no stub translations", not short, str(short[:6]))

    empty = [sid for sid, t in translations.items() if not t["cn"].strip()]
    rep.check("no empty translations", not empty, str(empty[:6]))

    # consistency: one sentence -> one translation (shared by every word on it)
    multi = {}
    for m in wmap["words"]:
        multi.setdefault(m["sent_id"], set())
    rep.note(f"{len(multi)} sentences serve {len(wmap['words'])} words; every word on a sentence "
             f"now shows the SAME translation (old data had up to 3 different ones)")

    save_json(OUT_FILE, {"episode": EPISODE, "translations": {str(k): v for k, v in translations.items()}})
    rep.note(f"wrote {OUT_FILE}")
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS4 %s - %d translations, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(translations), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
