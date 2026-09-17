# -*- coding: utf-8 -*-
"""S2 - map every Ep02 target word to the sentence that actually contains it.

The shipped data picked each word's example by timestamp and then quoted whatever
ASR chunk happened to cover that timestamp - which is why examples started and
ended mid-sentence. Here each word is bound to a *rebuilt sentence*:

  * locate the sentence covering the word's original timestamp;
  * verify the word really occurs in that sentence (boundary-aware, tolerant of
    hyphenation/spacing and simple morphology);
  * otherwise search the neighbouring sentences;
  * words that still cannot be matched are adjudicated one-by-one by the AI,
    which must pick a candidate id or answer "absent" (never invent text).

Output: out/<ep>_word_map.json
        {episode, generated, sentences_file, words:[{word, sent_id, match, ...}]}
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log,  # noqa: E402
                    norm_words, normalize_text, save_json)
from ai_gate import ask_json, usage  # noqa: E402

SENTS_FILE = os.path.join(OUT_DIR, f"{EPISODE}_sentences.json")
CURRICULUM = os.path.join(DATA_DIR, f"{EPISODE}_curriculum_final_audited.json")
OUT_FILE = os.path.join(OUT_DIR, f"{EPISODE}_word_map.json")

ADJUDICATE_SYSTEM = """你是英语教学语料编辑。给定一个**目标词/短语**和若干候选句子（来自哈佛《公正》公开课逐字稿，按时间排序）。
请选出**最适合作为该词例句**的候选句子：优先选择该词真实出现、且句子语义完整、能体现该词学术含义的那一句。

判定"出现"时请考虑真实语料中的形态变化：
- 时态/语态变化：kept track（keep track）、translated into（translate into）、placing a value on（place a value on）
- 代词/插入成分：take it under advisement（take under advisement）、concerning itself with（concern oneself with）、have a say in
- 比较级/最高级：noblest（noble）

必须同时给出 **evidence**：从你选中的那句里**原样复制**的一小段连续文本（必须能在该句中一字不差地找到），用以证明目标词确实出现。
- 只能从候选 id 中选择，绝不能造句子或改写候选句子。
- 如果所有候选里都没有该词（含上述形态变化），返回 {"pick": null, "reason":"absent"}。

只输出 JSON：{"pick": 选中候选的 id 或 null, "evidence": "原样摘录的连续片段或空串", "reason": "简短理由"}"""


def token_forms(tok):
    """Common inflections of ONE token (used inside multi-word phrases too)."""
    forms = {tok}
    if len(tok) >= 4:
        if tok.endswith("e"):
            forms |= {tok + "s", tok + "d", tok[:-1] + "ing", tok + "ing"}
        elif tok.endswith("y") and tok[-2] not in "aeiou":
            forms |= {tok[:-1] + "ies", tok[:-1] + "ied", tok + "s"}
        else:
            forms |= {tok + "s", tok + "es", tok + "ed", tok + "ing"}
        forms |= {tok + "er", tok + "est", tok + "st"}   # nobler / noblest
    if tok.endswith("s") and len(tok) > 4:
        forms.add(tok[:-1])
    return {f for f in forms if len(f) >= 2}


def word_pattern(word):
    """Boundary-aware regex where every token may appear in an inflected form."""
    toks = norm_words(word)
    if not toks:
        return None
    parts = []
    for t in toks:
        forms = sorted(token_forms(t), key=len, reverse=True)
        parts.append("(?:" + "|".join(re.escape(f) for f in forms) + ")")
    return re.compile(r"\b" + r"\W+".join(parts) + r"\b")


def variants(word):
    w = normalize_text(word).lower()
    return token_forms(w) | {w}


def contains(sentence_text, word, fuzzy=True):
    s = normalize_text(sentence_text).lower()
    pat = word_pattern(word)
    if pat and pat.search(s):
        m = pat.search(s)
        return m.group(0)
    if not fuzzy:
        return None
    # fall back to a stem match for single words (e.g. 'maximize' vs 'maximizing')
    if " " not in normalize_text(word).strip():
        for cand in variants(word):
            p = word_pattern(cand)
            if p and p.search(s):
                return cand
    return None


def sentence_at(sents, t):
    """Index of the sentence whose span covers t (else the closest before)."""
    for i, s in enumerate(sents):
        if s["start"] <= t <= s["end"]:
            return i
    prev = 0
    for i, s in enumerate(sents):
        if s["start"] <= t:
            prev = i
        else:
            break
    return prev


def main():
    rep = Report(f"{EPISODE}_s2_word_map")
    sents = load_json(SENTS_FILE)
    words = load_json(CURRICULUM)
    if not sents or not words:
        rep.check("inputs present", False, f"sentences={bool(sents)} curriculum={bool(words)}")
        rep.write()
        return 1
    rep.check("inputs present", True, f"{len(sents)} sentences, {len(words)} target words")

    mapped, need_ai, absent = [], [], []
    for w in words:
        t = float(w.get("audio_start") or 0)
        idx = sentence_at(sents, t)
        window = [idx] + [j for d in (1, -1, 2, -2, 3, -3) for j in [idx + d] if 0 <= idx + d < len(sents)]
        hit = None
        for rank, j in enumerate(window):
            form = contains(sents[j]["text"], w["word"])
            if form:
                hit = {"sent_id": j, "match": "exact" if rank == 0 else f"neighbour+{rank}", "form": form}
                break
        if hit is None:
            form = contains(sents[idx]["text"], w["word"], fuzzy=False)
            if form:
                hit = {"sent_id": idx, "match": "exact", "form": form}
        if hit:
            mapped.append(dict(w, **hit))
        else:
            need_ai.append((w, idx, window))

    rep.check("words matched to a sentence by direct search", True,
              f"{len(mapped)} direct, {len(need_ai)} need AI adjudication")

    # ---- AI adjudication, one word per call -------------------------
    for w, idx, window in need_ai:
        cands = [{"id": j, "text": sents[j]["text"]} for j in window[:6]]
        user = (f"目标词：{w['word']}\n该词在音视频中的时间戳：{w.get('audio_start')}s\n"
                f"候选句子（按时间顺序）：\n{json.dumps(cands, ensure_ascii=False, indent=1)}")
        text_of = {c["id"]: c["text"] for c in cands}

        def validate(o, window=window, text_of=text_of):
            if not isinstance(o, dict):
                return 'expected {"pick": id|null, "evidence": "..", "reason": ".."}'
            pick = o.get("pick")
            if pick is None:
                return None
            if pick not in window:
                return f'"pick" must be one of {window} or null'
            ev = normalize_text(o.get("evidence") or "").lower()
            if len(ev) < 3:
                return ('"evidence" must be a verbatim quote copied from the chosen sentence '
                        'that proves the target word occurs there')
            if ev not in normalize_text(text_of[pick]).lower():
                return (f'"evidence" must appear verbatim inside sentence {pick}. '
                        f'You gave {ev!r} which is not a substring of it.')
            return None

        try:
            obj = ask_json(ADJUDICATE_SYSTEM, user,
                           tag=f"{EPISODE}_s2_adj2_{w['word'].replace(' ', '_')}",
                           validate=validate, max_tokens=400, temperature=0.0)
        except RuntimeError as e:
            log("    adjudication failed for %r: %s", w["word"], str(e)[:120])
            absent.append(w["word"])
            continue
        pick = obj.get("pick")
        if pick is None:
            absent.append(w["word"])
        else:
            mapped.append(dict(w, sent_id=pick, match="ai_adjudicated",
                               form=(obj.get("evidence") or "").strip(),
                               evidence=(obj.get("evidence") or "").strip()))

    # ---- gates ------------------------------------------------------
    rep.check("every target word resolved to a sentence", len(mapped) == len(words),
              f"{len(mapped)}/{len(words)} mapped; unresolved: {absent[:10]}")

    bad_form = []
    for m in mapped:
        txt = sents[m["sent_id"]]["text"]
        if contains(txt, m["word"]):
            continue
        ev = normalize_text(m.get("evidence") or "").lower()   # AI-quoted proof
        if ev and len(ev) >= 3 and ev in normalize_text(txt).lower():
            continue
        bad_form.append(m["word"])
    rep.check("every mapped sentence really contains its target word (matcher or AI quote)", not bad_form,
              f"{len(bad_form)} mismatches: {bad_form[:10]}")

    durs = [sents[m["sent_id"]]["end"] - sents[m["sent_id"]]["start"] for m in mapped]
    rep.check("all clip windows are usable (0.8s..40s)",
              all(0.8 <= d <= 40 for d in durs),
              f"min={min(durs):.1f}s max={max(durs):.1f}s")

    ids = {s["sent_id"] for s in sents}
    rep.check("all referenced sentence ids exist", all(m["sent_id"] in ids for m in mapped))

    uniq = len({m["sent_id"] for m in mapped})
    rep.note(f"{len(mapped)} words -> {uniq} distinct sentences (shared examples are expected)")
    rep.note(f"match breakdown: exact={sum(1 for m in mapped if m['match']=='exact')}, "
             f"neighbour={sum(1 for m in mapped if m['match'].startswith('neighbour'))}, "
             f"ai={sum(1 for m in mapped if m['match']=='ai_adjudicated')}")

    save_json(OUT_FILE, {"episode": EPISODE, "sentences_file": os.path.basename(SENTS_FILE),
                         "words": [{k: v for k, v in m.items() if k not in ("sentence",)} for m in mapped]})
    rep.note(f"wrote {OUT_FILE}")
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS2 %s - %d words mapped, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(mapped), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
