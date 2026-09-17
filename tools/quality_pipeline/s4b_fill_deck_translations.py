# -*- coding: utf-8 -*-
"""S4b - fill missing deck translations for decks the sentence pipeline never touched.

Ep03 / Yale / custom-import decks carry English example sentences but an EMPTY
`sentence_cn`, which is what makes cards show "暂无官方中文翻译" and what would
otherwise be copied into the master bank by S6.

This stage translates those sentences with the same context-aware prompt used by
S4 (whole sentence + neighbouring sentences as context + pinned target-word
glosses), reviews them with the AI, re-translates flagged ones individually, and
writes the result back into the deck files.

Output: data/curriculum_tiered.json + data/custom_episodes.json (in place)
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CURRICULUM_KEYS_ORDER, DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log, save_json  # noqa: E402
from ai_gate import ask_json, usage  # noqa: E402
from s4_translate import RETRY_SYSTEM, REVIEW_SYSTEM, TRANSLATE_SYSTEM  # noqa: E402

TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
CUSTOM = os.path.join(DATA_DIR, "custom_episodes.json")
REPORT = os.path.join(OUT_DIR, f"{EPISODE}_deck_translations.json")
BATCH = 6
CONTEXT_SPAN = 3


def deck_list():
    out = []
    tiered = load_json(TIERED) or {}
    for ep in CURRICULUM_KEYS_ORDER:
        if ep in tiered:
            out.append((ep, tiered[ep], "tiered"))
    for ep, payload in (load_json(CUSTOM) or {}).items():
        out.append((ep, payload, "custom"))
    return out


def main():
    rep = Report(f"{EPISODE}_s4b_deck_translations")
    decks = deck_list()
    if not decks:
        rep.check("decks available", False, TIERED)
        rep.write()
        return 1

    todo = []          # (deck_id, index, sentence, glosses, context)
    for ep_id, payload, _kind in decks:
        ws = payload.get("words", [])
        for i, w in enumerate(ws):
            if (w.get("sentence_cn") or "").strip() or not (w.get("sentence") or "").strip():
                continue
            ctx = []
            for j in range(max(0, i - CONTEXT_SPAN), min(len(ws), i + CONTEXT_SPAN + 1)):
                if j != i and (ws[j].get("sentence") or "").strip():
                    ctx.append({"text": ws[j]["sentence"]})
            todo.append((ep_id, i, w["sentence"].strip(),
                         [{"word": w["word"], "def_cn": w.get("def_cn", ""), "pos": w.get("pos", "")}], ctx))

    rep.check("decks available", True,
              ", ".join(f"{ep}={len(p.get('words', []))}" for ep, p, _ in decks))
    rep.note(f"{len(todo)} deck words missing sentence_cn")
    if not todo:
        rep.check("nothing to translate", True)
        rep.write()
        return 0

    # one translation per distinct sentence
    uniq = {}
    for ep_id, i, sent, glosses, ctx in todo:
        uniq.setdefault(sent, {"glosses": glosses, "ctx": ctx, "refs": []})["refs"].append((ep_id, i))
    keys = sorted(uniq)
    rep.note(f"{len(keys)} distinct sentences to translate")

    translations = {}
    failed = []
    for base in range(0, len(keys), BATCH):
        batch = keys[base:base + BATCH]
        payload = [{"id": k, "text": k,
                    "context": [c["text"] for c in uniq[k]["ctx"]][:4],
                    "target_words": uniq[k]["glosses"]} for k in batch]
        ids = set(batch)

        def validate(o, ids=ids):
            if not isinstance(o, dict) or not isinstance(o.get("items"), list):
                return 'expected {"items":[{"id":..,"cn":".."}]}'
            got = {it.get("id"): (it.get("cn") or "").strip() for it in o["items"] if isinstance(it, dict)}
            if set(got) != ids:
                return f"ids must match exactly; missing={sorted(ids - set(got))[:4]}"
            for i in ids:
                if len(got[i]) < 2:
                    return f"id {i}: translation too short"
            return None

        try:
            obj = ask_json(TRANSLATE_SYSTEM,
                           "请翻译下列句子（context 仅供理解语境，不要翻译 context 本身）：\n"
                           + json.dumps(payload, ensure_ascii=False),
                           tag=f"{EPISODE}_s4b_tr_{base // BATCH:02d}",
                           validate=validate, max_tokens=6000, temperature=0.3)
        except RuntimeError as e:
            log("    batch %d failed: %s", base, str(e)[:140])
            failed.extend(batch)
            continue
        for it in obj["items"]:
            translations[it["id"]] = it["cn"].strip()

    rep.check("first pass produced a translation for every sentence", not failed,
              f"{len(translations)}/{len(keys)}; failed {failed[:4]}")

    # ---- AI review (flags only) ----
    flagged = {}
    for base in range(0, len(keys), BATCH):
        batch = [k for k in keys[base:base + BATCH] if k in translations]
        if not batch:
            continue
        payload = [{"id": k, "en": k, "cn": translations[k]} for k in batch]
        ids = {p["id"] for p in payload}
        try:
            obj = ask_json(REVIEW_SYSTEM, "请审校下列译文：\n" + json.dumps(payload, ensure_ascii=False),
                           tag=f"{EPISODE}_s4b_rev_{base // BATCH:02d}",
                           validate=lambda o: None if isinstance(o, dict) and isinstance(o.get("issues", []), list)
                           else 'expected {"issues":[...]}',
                           max_tokens=3000, temperature=0.0)
        except RuntimeError as e:
            log("    review %d failed: %s", base, str(e)[:140])
            continue
        for it in obj.get("issues", []):
            if isinstance(it, dict) and it.get("id") in ids:
                flagged.setdefault(it["id"], []).append(f'{it.get("type")}: {str(it.get("note"))[:100]}')
    rep.note(f"review flagged {len(flagged)} of {len(translations)}")

    fixed = 0
    for k, notes in flagged.items():
        payload = {"text": k, "context": [c["text"] for c in uniq[k]["ctx"]][:4],
                   "target_words": uniq[k]["glosses"], "review_notes": notes,
                   "previous_translation": translations[k]}
        try:
            obj = ask_json(RETRY_SYSTEM, json.dumps(payload, ensure_ascii=False, indent=1),
                           tag=f"{EPISODE}_s4b_fix_{abs(hash(k)) % (10 ** 12)}",
                           validate=lambda o: None if isinstance(o, dict) and len((o.get("cn") or "").strip()) >= 2
                           else 'expected {"cn":"..."}',
                           max_tokens=800, temperature=0.3)
        except RuntimeError as e:
            log("    re-translation failed: %s", str(e)[:120])
            continue
        translations[k] = obj["cn"].strip()
        fixed += 1
    rep.note(f"re-translated {fixed} flagged sentences")

    # ---- write back into the deck files ----
    tiered = load_json(TIERED) or {}
    custom = load_json(CUSTOM) or {}
    applied = 0
    for sent, info in uniq.items():
        cn = translations.get(sent)
        if not cn:
            continue
        for ep_id, i in info["refs"]:
            target = tiered if ep_id in tiered else custom
            target[ep_id]["words"][i]["sentence_cn"] = cn
            applied += 1
    save_json(TIERED, tiered)
    save_json(CUSTOM, custom)
    rep.check("every previously-missing translation was filled", applied == len(todo),
              f"{applied}/{len(todo)}")

    # ---- gates on the written decks ----
    empty = []
    for ep_id, payload, _k in deck_list():
        for w in payload.get("words", []):
            if not (w.get("sentence_cn") or "").strip() and (w.get("sentence") or "").strip():
                empty.append((ep_id, w.get("word")))
    rep.check("no deck word is left without a translation", not empty, f"{len(empty)}: {empty[:6]}")

    latin = [(ep, w.get("word")) for ep, payload, _k in deck_list() for w in payload.get("words", [])
             if len(re.findall(r"[A-Za-z][A-Za-z'\- ]{3,}", w.get("sentence_cn") or "")) > 0]
    rep.note(f"{len(latin)} deck words keep some Latin in the Chinese (proper nouns allowed): {latin[:5]}")

    save_json(REPORT, {"translated_sentences": len(translations), "words_filled": applied,
                       "review_flagged": len(flagged)})
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS4b %s - %d sentences, %d words filled, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(translations), applied,
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
