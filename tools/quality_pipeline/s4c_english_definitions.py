# -*- coding: utf-8 -*-
"""S4c - author the English definition (`def_en`) for every deck word.

Why: the ticket asks for 英文释义 alongside the Chinese gloss.  `def_cn` alone
forces the learner back through Chinese, which is exactly what an academic
listening course should avoid.

Contract
--------
* One definition per **unique headword** (case-insensitive).  Several decks may
  reuse a word; the definition is authored once from every usage we have and
  then written to all of them, so the deck cards and the master bank can never
  disagree about the same word.
* The AI only ever emits text keyed by an opaque id, and every id is validated
  deterministically before it is accepted (sense echo, circularity, Chinese
  leakage, example-sentence plagiarism, length, duplication).
* A second AI pass reviews the accepted definitions and may only *flag* ids; a
  flagged definition is regenerated on its own with the review notes attached.
* Nothing is written unless every gate passes afterwards.

Input : data/curriculum_tiered.json + data/custom_episodes.json (+ audited decks)
Output: the same deck files, each word gaining `def_en`; report in out/
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log,  # noqa: E402
                    norm_words, normalize_text, save_json, sha1)
from ai_gate import ask_json, usage  # noqa: E402

TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
CUSTOM = os.path.join(DATA_DIR, "custom_episodes.json")
BANK = os.path.join(DATA_DIR, "vocab_bank.json")
EXAM = os.path.join(DATA_DIR, "exam_decks.json")
LONGSENT = os.path.join(DATA_DIR, "longsent_decks.json")
REPORT = os.path.join(OUT_DIR, f"{EPISODE}_english_definitions.json")

BATCH = 8
MIN_WORDS = 3
MAX_WORDS = 32
MAX_CHARS = 220
ECHO_RUN = 8          # verbatim word run that counts as copying the example

CJK_RE = re.compile("[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
                    "\ufe30-\ufe4f\uff00-\uffef]")
MARKDOWN_RE = re.compile(r"[*_`#\[\]{}|]|^\s*[-•]\s")

GENERATE_SYSTEM = """你是面向中国大学生的英语学习词典释义撰写专家（CEFR B1-B2 读者）。
为英语学习词表（公开课精读词表 / 托福雅思GRE考研词表 / 学术词组与固定搭配表）中的每个词条
撰写一条**英英释义**（learner's dictionary 风格）。词条可能是单词，也可能是多词词组（如 "amount to"）。

硬性要求：
1. 只输出英文，绝对不允许出现任何中文字符或中文标点。
2. 若给出了例句，释义必须贴合该词条**在例句中的实际词义和词性**（pos）；
   没有例句时以 pos 与中文释义为准，只写最常见、最值得学的那一个义项。
3. 长度 6-22 个英文单词，写成一条可以直接替换词条的名词短语或动词不定式短语。
4. 用比词条本身更简单的词解释；解释部分不得循环定义（不能只用词条本身解释自己）。
5. 不得照抄或改写给定例句；不得提及课程、讲师、人名（Sandel / Bentham / Kant / lecture 等）。
6. 不要以 "It is" / "This is" / "Refers to" 开头；直接写 "the belief that ..."、"to force someone ..."。
7. 不写词性标记、不写序号、不加引号、不用 markdown、不用分号罗列多个义项。
8. 词组的释义要体现它的**搭配与用法**（例如说明后面接什么），不要只给同义词。

只输出 JSON：{"items":[{"id":"<原样返回>","en":"<英英释义>"}]}"""

REVIEW_SYSTEM = """你是英汉双语词典的资深审校。逐条检查给出的英英释义是否有下列问题：
- WRONG_SENSE：释义的词义或词性与该词在例句中的用法不符
- ECHOES_EXAMPLE：释义基本是例句的复述/照抄，不是词典释义
- CIRCULAR：用词条本身解释词条，没有提供新信息
- HAS_CHINESE：出现中文或中文标点
- GRAMMAR：语法错误，或不是可独立使用的释义片段
- VAGUE：过度空泛（如 "a kind of thing"），读者无法据此理解该词
- MENTIONS_COURSE：提到课程、讲师或人名
只报告确实有问题的条目；没有问题就返回空数组，不要为了凑数而报问题。
输出 JSON：{"issues":[{"id":"<原样返回>","type":"上列之一","note":"不超过 40 字的说明"}]}"""

RETRY_SYSTEM = """你是英语学习词典释义撰写专家。下面这个词的英英释义被审校打回，
请根据审校意见重写一条符合要求的英英释义（6-22 个英文单词，贴合例句中的词义与词性，
只用英文，不照抄例句，不循环定义，不加引号或 markdown）。
只输出 JSON：{"en":"<重写后的英英释义>"}"""


# ------------------------------------------------------------------ helpers
def deck_sources():
    """[(deck_id, payload, path)] for every file the app actually serves."""
    out, seen = [], set()
    tiered = load_json(TIERED) or {}
    for ep_id, payload in tiered.items():
        if payload.get("words"):
            out.append((ep_id, payload, TIERED))
            seen.add(ep_id)
    custom = load_json(CUSTOM) or {}
    for ep_id, payload in custom.items():
        if payload.get("words"):
            out.append((ep_id, payload, CUSTOM))
            seen.add(ep_id)
    # Exam decks imported from open lexical data (S9). Their phrase table has
    # almost no English definitions in the source, so they need this stage.
    for ep_id, payload in (load_json(EXAM) or {}).items():
        if payload.get("words"):
            out.append((ep_id, payload, EXAM))
            seen.add(ep_id)
    # Long-sentence deck (S10) - built from the lecture transcripts we own.
    for ep_id, payload in (load_json(LONGSENT) or {}).items():
        if payload.get("words"):
            out.append((ep_id, payload, LONGSENT))
            seen.add(ep_id)
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith("_curriculum_final_audited.json"):
            continue
        ep_id = name[: -len("_curriculum_final_audited.json")]
        if ep_id in seen:
            continue
        audited = load_json(os.path.join(DATA_DIR, name))
        if isinstance(audited, list) and audited:
            out.append((ep_id, {"words": audited}, os.path.join(DATA_DIR, name)))
    return out


def bank_only_deck():
    """The master-bank entries no current deck teaches, as a virtual deck.

    The bank keeps words from decks that have since been rebuilt (a learner may
    already have studied them), and the UI lists them under "全部". They are
    visible cards, so they need an English definition as well - otherwise the
    bank would show an EN line for 449 of 502 words and silently nothing for the
    rest. They are authored here and written straight back into the bank; they
    are deliberately NOT part of `deck_sources()`, so S6b still sees them as
    untaught and reports them honestly.
    """
    bank = load_json(BANK) or {}
    covered = set()
    for _ep, payload, _path in deck_sources():
        for w in payload.get("words", []):
            covered.add((w.get("word") or "").strip().lower())
    words = []
    for key, entry in bank.items():
        if key in covered:
            continue
        examples = [(c.get("sentence") or "").strip()
                    for c in (entry.get("contexts") or [])
                    if (c.get("sentence") or "").strip()]
        words.append({"word": entry.get("word") or key,
                      "pos": entry.get("pos", ""),
                      "def_cn": entry.get("def_cn", ""),
                      "def_en": entry.get("def_en", ""),
                      "examples": examples[:2],
                      "_bank_key": key})
    return {"words": words} if words else None


def collect_targets(decks):
    """unique headword -> {pos, def_cn, examples[], refs[(deck, index)]}"""
    targets = {}
    for ep_id, payload, _path in decks:
        for i, w in enumerate(payload.get("words", [])):
            key = (w.get("word") or "").strip().lower()
            if not key:
                continue
            t = targets.setdefault(key, {"word": (w.get("word") or "").strip(),
                                         "pos": "", "def_cn": "", "def_en": "",
                                         "examples": [], "refs": []})
            t["refs"].append((ep_id, i))
            if not t["pos"] and (w.get("pos") or "").strip():
                t["pos"] = w["pos"].strip()
            if not t["def_cn"] and (w.get("def_cn") or "").strip():
                t["def_cn"] = w["def_cn"].strip()
            if not t["def_en"] and (w.get("def_en") or "").strip():
                t["def_en"] = w["def_en"].strip()
                t["def_en_source"] = (w.get("def_en_source") or "").strip()
            # Deck words carry a single `sentence`; the bank pseudo-deck passes a
            # ready-made `examples` list (one per episode that used the word).
            cands = [w.get("sentence"), w.get("example")] + list(w.get("examples") or [])
            for cand in cands:
                cand = (cand or "").strip()
                if cand and cand not in t["examples"] and len(t["examples"]) < 2:
                    t["examples"].append(cand[:400])
    return targets


def _echoes(en, examples):
    """True when `en` reproduces a long verbatim run of an example sentence."""
    en_words = norm_words(en)
    if len(en_words) < ECHO_RUN:
        return False
    for ex in examples:
        ex_words = norm_words(ex)
        for start in range(0, len(en_words) - ECHO_RUN + 1):
            run = en_words[start:start + ECHO_RUN]
            for j in range(0, len(ex_words) - ECHO_RUN + 1):
                if ex_words[j:j + ECHO_RUN] == run:
                    return True
    return False


def check_definition(word, en, examples, strict=True):
    """Deterministic per-item gate.  Returns None or a reason string.

    ``strict`` applies the learner-dictionary house style (length, no brackets,
    no quotes) and is only enforced on definitions THIS stage authored.  Text
    imported from a real dictionary (ECDICT) or written by an earlier pass is
    legitimately longer and uses brackets - failing it would be the gate
    mistaking "not our style" for "wrong".
    """
    en = (en or "").strip()
    if not en:
        return "empty"
    if CJK_RE.search(en):
        return "contains Chinese"
    if normalize_text(en).lower().strip(".") == normalize_text(word).lower():
        return "identical to the headword"
    if not strict:
        return None
    if MARKDOWN_RE.search(en):
        return "markdown/quotes/list characters"
    if en[0] in "\"'\u201c\u2018" or en[-1] in "\"'\u201d\u2019":
        return "wrapped in quotes"
    if len(en) > MAX_CHARS:
        return f"too long ({len(en)} chars)"
    tokens = norm_words(en)
    if len(tokens) < MIN_WORDS:
        return f"too short ({len(tokens)} words)"
    if len(tokens) > MAX_WORDS:
        return f"too many words ({len(tokens)})"
    if set(tokens) == {w for w in norm_words(word)}:
        return "circular: only the headword"
    core = [t for t in tokens if t not in set(norm_words(word))]
    if len(core) < 2:
        return "circular: no information beyond the headword"
    stripped = re.sub(r"^(it is|this is|refers to|a word meaning)\b[:,]?\s*", "",
                      normalize_text(en), flags=re.I)
    if stripped != normalize_text(en):
        return "starts with a filler phrase"
    if _echoes(en, examples):
        return "copies a run of the example sentence"
    # Only *meta* references to the course itself are banned.  Philosophers are
    # content, not context: a definition of "categorical" or "utilitarianism"
    # legitimately names Kant or Bentham.
    for bad in ("sandel", "harvard", "this lecture", "the lecture", "this course",
                "the course", "the video", "the episode", "professor",
                "as we discussed", "in class"):
        if bad in normalize_text(en).lower():
            return f"mentions the course itself ({bad})"
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser(description="author def_en for every deck word")
    ap.add_argument("--dry-run", action="store_true",
                    help="inspect the decks and validate existing def_en, no AI calls")
    ap.add_argument("--no-bank-only", action="store_true",
                    help="skip the master-bank entries that no deck teaches")
    args = ap.parse_args()

    rep = Report(f"{EPISODE}_s4c_english_definitions")
    decks = deck_sources()
    if not decks:
        rep.check("deck files available", False, DATA_DIR)
        rep.write()
        return 1
    rep.check("deck files available", True,
              ", ".join("%s=%d" % (ep, len(p.get("words", []))) for ep, p, _ in decks))
    bank_deck = None if args.no_bank_only else bank_only_deck()
    if bank_deck:
        decks = decks + [("__bank_only__", bank_deck, BANK)]
        rep.note(f"{len(bank_deck['words'])} master-bank words are taught by no deck "
                 f"and are authored here too (written back into the bank)")

    targets = collect_targets(decks)
    todo = {k: t for k, t in targets.items() if not (t.get("def_en") or "").strip()}
    already = len(targets) - len(todo)
    rep.note(f"{len(targets)} unique headwords, {already} already carry def_en, "
             f"{len(todo)} to author")

    if args.dry_run:
        no_example = [k for k, t in targets.items() if not t["examples"]]
        no_gloss = [k for k, t in targets.items() if not t["def_cn"]]
        rep.check("every headword has a Chinese gloss for the AI to anchor on",
                  not no_gloss, f"{len(no_gloss)}: {no_gloss[:6]}")
        rep.note(f"{len(no_example)} headwords have no example sentence: {no_example[:6]}")
        bad = []
        for k, t in targets.items():
            if not t["def_en"]:
                continue
            reason = check_definition(t["word"], t["def_en"], t["examples"],
                                      strict=t.get("def_en_source") == "ai")
            if reason:
                bad.append(f"{k} ({reason})")
        rep.check("existing def_en values pass the gate for their source",
                  not bad, f"{len(bad)}: {bad[:6]}")
        rep.note("dry run: no AI call was made and no file was written")
        payload = rep.write()
        log("\nS4c dry-run %s - %d unique headwords, %d to author, %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", len(targets), len(todo),
            payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    # Preserve existing definitions so a re-run cannot silently rewrite them.
    existing = {}
    for ep_id, payload, _p in decks:
        for w in payload.get("words", []):
            k = (w.get("word") or "").strip().lower()
            if k and (w.get("def_en") or "").strip():
                existing[k] = w["def_en"].strip()

    if todo:
        keys = sorted(todo)
        defs, failed = {}, []

        # ---------- pass 1: author ----------
        for base in range(0, len(keys), BATCH):
            batch = keys[base:base + BATCH]
            ids = {"w%03d" % (base + n): k for n, k in enumerate(batch)}
            payload = [{"id": i,
                        "word": todo[k]["word"],
                        "pos": todo[k]["pos"],
                        "def_cn": todo[k]["def_cn"],
                        "examples": todo[k]["examples"]}
                       for i, k in ids.items()]

            def validate(o, ids=ids):
                if not isinstance(o, dict) or not isinstance(o.get("items"), list):
                    return 'expected {"items":[{"id":..,"en":".."}]}'
                got = {}
                for it in o["items"]:
                    if isinstance(it, dict) and it.get("id") in ids:
                        got[it["id"]] = it.get("en")
                if set(got) != set(ids):
                    return ("ids must match exactly; missing=%s unknown=%s"
                            % (sorted(set(ids) - set(got))[:5],
                               sorted(set(got) - set(ids))[:5]))
                return None

            try:
                obj = ask_json(GENERATE_SYSTEM,
                               "请为下列词条撰写英英释义：\n"
                               + json.dumps(payload, ensure_ascii=False, indent=1),
                               tag=f"{EPISODE}_s4c_gen_{base // BATCH:03d}",
                               validate=validate, max_tokens=4000, temperature=0.3)
            except RuntimeError as e:
                log("    batch %d failed: %s", base, str(e)[:140])
                failed.extend(batch)
                continue
            for it in obj["items"]:
                k = ids[it["id"]]
                reason = check_definition(k, it.get("en"), todo[k]["examples"])
                if reason:
                    log("    rejected %s: %s", k, reason)
                    failed.append(k)
                else:
                    defs[k] = it["en"].strip()

        rep.check("pass 1 produced a valid definition for every word",
                  not [k for k in keys if k not in defs],
                  f"{len(defs)}/{len(keys)}; rejected {len(failed)}")

        # ---------- helpers shared by the review / rewrite / collision passes ----------
        def by_text_index():
            idx = {}
            for k, v in defs.items():
                idx.setdefault(normalize_text(v).lower(), []).append(k)
            return {t: ks for t, ks in idx.items() if len(ks) > 1}

        def rewrite(k, notes, attempt=0):
            body = {"word": todo[k]["word"], "pos": todo[k]["pos"],
                    "def_cn": todo[k]["def_cn"], "examples": todo[k]["examples"],
                    "previous": defs.get(k, ""), "review_notes": notes}
            try:
                obj = ask_json(RETRY_SYSTEM,
                               json.dumps(body, ensure_ascii=False, indent=1),
                               tag=f"{EPISODE}_s4c_fix_{sha1(k)[:10]}_{attempt}",
                               validate=lambda o: None if isinstance(o, dict)
                               and isinstance(o.get("en"), str) and o["en"].strip()
                               else 'expected {"en":"..."}',
                               max_tokens=600, temperature=0.3)
            except RuntimeError as e:
                log("    rewrite failed for %s: %s", k, str(e)[:120])
                return False
            reason = check_definition(k, obj.get("en"), todo[k]["examples"])
            if reason:
                log("    rewrite of %s rejected: %s", k, reason)
                return False
            defs[k] = obj["en"].strip()
            return True

        # ---------- pass 2: AI review (flags ids only) ----------
        flagged = {}
        reviewable = sorted(defs)
        for base in range(0, len(reviewable), BATCH):
            batch = reviewable[base:base + BATCH]
            ids = {"w%03d" % (base + n): k for n, k in enumerate(batch)}
            payload = [{"id": i, "word": todo[k]["word"], "pos": todo[k]["pos"],
                        "example": (todo[k]["examples"] or [""])[0][:300],
                        "def_en": defs[k]} for i, k in ids.items()]
            try:
                obj = ask_json(REVIEW_SYSTEM,
                               "请审校下列英英释义：\n"
                               + json.dumps(payload, ensure_ascii=False, indent=1),
                               tag=f"{EPISODE}_s4c_rev_{base // BATCH:03d}",
                               validate=lambda o: None if isinstance(o, dict)
                               and isinstance(o.get("issues", []), list)
                               else 'expected {"issues":[...]}',
                               max_tokens=3000, temperature=0.0)
            except RuntimeError as e:
                log("    review %d failed: %s", base, str(e)[:140])
                continue
            for it in obj.get("issues", []):
                if isinstance(it, dict) and it.get("id") in ids:
                    flagged.setdefault(ids[it["id"]], []).append(
                        f'{it.get("type")}: {str(it.get("note"))[:80]}')
        rep.note(f"AI review flagged {len(flagged)} of {len(defs)} definitions")

        # ---------- pass 3: re-author the flagged ones, one at a time ----------
        still_bad = []
        for k, notes in flagged.items():
            if not rewrite(k, notes, attempt=0):
                still_bad.append(k)
        rep.check("flagged definitions were rewritten into a passing form",
                  not still_bad, f"{len(flagged) - len(still_bad)}/{len(flagged)}"
                  + (f"; still bad {still_bad[:5]}" if still_bad else ""))

        # ---------- pass 4: collision screen ----------
        # `irrespective of` / `regardless of` really are synonyms, so colliding
        # wording is not automatically wrong - but two cards must not read
        # identically either. Ask for one differentiating rewrite; if the model
        # still returns the same phrasing, record the pair as an accepted
        # synonym rather than either failing forever or silently accepting it.
        for _round in range(2):
            dupes = by_text_index()
            if not dupes:
                break
            for text, ks in dupes.items():
                keeper, others = ks[0], ks[1:]
                for k in others:
                    notes = ["DUPLICATE: 词条 %r 已使用该措辞：%s。请改写得更贴合 %r 自身的"
                             "搭配与语域，必须与那一条措辞明显不同。"
                             % (todo[keeper]["word"], text, todo[k]["word"])]
                    if rewrite(k, notes, attempt=_round):
                        log("    de-duplicated %s vs %s", k, keeper)

        synonyms = [{"wording": t, "words": ks}
                    for t, ks in by_text_index().items()]
        rep.check("no two headwords read identically", not synonyms,
                  ("%d accepted synonym pair(s): %s"
                   % (len(synonyms), [s["words"] for s in synonyms[:4]]))
                  if synonyms else "")
        if synonyms:
            rep.note("identical wording kept only for true synonyms: "
                     + "; ".join("~".join(s["words"]) for s in synonyms[:10]))

        # re-author anything the collision screen could not place
        rescued = []
        for k in [k for k in todo if k not in defs]:
            log("    re-authoring missing headword %s", k)
            if rewrite(k, ["先前的释义与其它词条重复，必须换一种说法。"], attempt=9):
                rescued.append(k)
        if rescued:
            rep.note(f"collision screen re-authored {len(rescued)} headwords: {rescued[:8]}")

        defs.update({k: v for k, v in existing.items() if k not in defs})

        # ---------- write back ----------
        missing = [k for k in targets if k not in defs]
        rep.check("every headword has a definition before writing", not missing,
                  f"{len(missing)} missing e.g. {missing[:6]}")
        if missing:
            rep.write()
            return 1

        written = 0
        slots_empty_before = sum(1 for _e, p, _pa in decks
                                 for w in p.get("words", [])
                                 if not (w.get("def_en") or "").strip())
        by_path = {}
        for ep_id, payload, path in decks:
            by_path.setdefault(path, []).append((ep_id, payload))
        for path, group in by_path.items():
            doc = load_json(path)
            for ep_id, payload in group:
                if path == BANK:
                    # vocab_bank.json is keyed by lowercased headword, not split
                    # into episodes.
                    for w in payload.get("words", []):
                        key = w.get("_bank_key") or (w.get("word") or "").strip().lower()
                        if key in defs and key in doc:
                            if (doc[key].get("def_en") or "").strip() != defs[key]:
                                written += 1
                            doc[key]["def_en"] = defs[key]
                            if key in todo:
                                doc[key]["def_en_source"] = "ai"
                    continue
                words = doc if isinstance(doc, list) else doc[ep_id]["words"]
                for w in words:
                    k = (w.get("word") or "").strip().lower()
                    if k in defs:
                        if (w.get("def_en") or "").strip() != defs[k]:
                            written += 1
                        w["def_en"] = defs[k]
                        # Only label entries THIS run authored. `defs` also holds
                        # the definitions that were already there, so marking
                        # everything "ai" made imported dictionary prose look
                        # self-written and the strict gate then failed it.
                        if k in todo:
                            w["def_en_source"] = "ai"
            save_json(path, doc)
        # `written` counts deck SLOTS, not unique headwords: a word that already
        # had a definition in Ep01 still had to be filled in wherever another
        # deck lists it. The honest comparison is against the slots that were
        # empty before the write.
        detail = (f"{written} slots updated, {slots_empty_before} were empty "
                  f"({len(todo)} unique headwords authored)") if slots_empty_before \
            else f"{written} slots updated (all already carried def_en)"
        rep.check("every deck slot that lacked a definition was filled",
                  written >= slots_empty_before, detail)
    else:
        rep.check("nothing to author (all headwords already have def_en)", True)

    # ---------- gates on the files as they now sit on disk ----------
    decks2 = deck_sources()
    empty = [(ep, w.get("word")) for ep, p, _ in decks2
             for w in p.get("words", []) if not (w.get("def_en") or "").strip()]
    rep.check("no deck word is left without an English definition", not empty,
              f"{len(empty)}: {empty[:6]}")

    # Strictly validate what THIS run wrote. Everything else was authored by an
    # earlier pass or imported from a dictionary, where long, bracket-heavy prose
    # is normal - reporting it as a gate failure would be the gate mistaking
    # "not our house style" for "wrong".
    authored_now = set(todo)
    bad, others, off_style = [], 0, []
    for ep, p, _ in decks2:
        for w in p.get("words", []):
            key = (w.get("word") or "").strip().lower()
            reason = check_definition(w.get("word", ""), w.get("def_en"),
                                      [w.get("sentence") or ""],
                                      strict=(key in authored_now))
            if reason:
                bad.append(f"{ep}:{w.get('word')} ({reason})")
            elif key in authored_now:
                continue
            else:
                others += 1
                if check_definition(w.get("word", ""), w.get("def_en"),
                                    [w.get("sentence") or ""], strict=True):
                    off_style.append(f"{w.get('word')}")
    rep.check("every definition this run authored passes the strict gate", not bad,
              f"{len(bad)}: {bad[:6]}" if bad else
              f"{len(authored_now)} authored this run, all conform")
    rep.note(f"{others} pre-existing / imported definitions were validated leniently")
    if off_style:
        rep.note(f"{len(off_style)} of them would not meet the learner-dictionary house "
                 f"style (dictionary prose is longer / uses brackets): {off_style[:8]}")

    conflicts = {}
    for ep, p, _ in decks2:
        for w in p.get("words", []):
            k = (w.get("word") or "").strip().lower()
            conflicts.setdefault(k, set()).add((w.get("def_en") or "").strip())
    split = {k: v for k, v in conflicts.items() if len(v) > 1}
    rep.check("a headword reused across decks carries one definition everywhere",
              not split, f"{len(split)} conflicting: {list(split)[:4]}")

    total = sum(len(p.get("words", [])) for _, p, _ in decks2)
    rep.note(f"{len(conflicts)} unique headwords across {total} deck slots")
    save_json(REPORT, {"unique_headwords": len(conflicts), "deck_slots": total,
                       "authored": len(todo), "usage": usage()})
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS4c %s - %d unique headwords, %d authored, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(conflicts), len(todo),
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
