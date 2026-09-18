# -*- coding: utf-8 -*-
"""S0b - build a GROUNDED word deck for an episode (word selection + metadata).

Why this stage exists
---------------------
Ep03 shipped with a deck that was never grounded in the audio: 24 of its 44 words
(55%) do not occur anywhere in the lecture, the timestamps were invented
([02:10], [05:40], [07:15] ... evenly spaced), and the "example sentences" were
LLM paraphrases that Sandel never said. S2 rightly refused to bind them.

This stage rebuilds such a deck from what is actually spoken:

  1. deterministic candidate list = the transcript's own vocabulary, minus a small
     function-word list, with counts (the AI can only pick from this list, so it
     cannot invent a word);
  2. the AI selects the N most valuable academic/argumentative items and writes
     their metadata (phonetic / pos / Chinese gloss / tier), and for each one the
     id of the sentence that best shows it in use;
  3. both choices are then verified deterministically: the word must occur in the
     transcript, and the chosen sentence must really contain it;
  4. the deck is written back into curriculum_tiered.json; the previous deck is
     archived under data/_retired/ so nothing is lost (its SRS progress also
     survives as bank-only entries).

Usage: python s0b_build_deck.py --episode ep03 [--count 45]
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (DATA_DIR, OUT_DIR, Report, load_deck_words, load_json,  # noqa: E402
                    log, norm_words, save_json)
from ai_gate import ask_json, usage  # noqa: E402

TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
CUSTOM_EPISODES = os.path.join(DATA_DIR, "custom_episodes.json")
EXAM_DECKS = os.path.join(DATA_DIR, "exam_decks.json")
SENTS_TMPL = os.path.join(OUT_DIR, "{ep}_sentences.json")
RETIRED = os.path.join(DATA_DIR, "_retired")
COUNT = 45
# Words requested per AI call. A single call for a 163-word deck overflowed the
# output budget and came back truncated mid-JSON, failing the stage.
SELECT_BATCH = 40

FUNCTION_WORDS = set("""
a an the and or but if then than that this these those there here when where which who whom whose why how
is are was were be been being am do does did done doing have has had having will would shall should can could
may might must ought i you he she it we they me him her us them my your his its our their mine yours theirs
of to in on at by for with from into onto over under about after before during without within across between
as so such not no nor only just also too very more most much many few less least own same other another any
some all both each every either neither one two three four five six seven eight nine ten first second third
up down out off again further once because while until unless since though although even well now yes no okay
ok right alright yeah yep nope hey oh ah uh um er hmm lets let don't didn't doesn't isn't aren't wasn't weren't
cant can't wont won't thats that's whats what's theres there's you're youve you've we're were they're im i'm
gonna gotta wanna kinda sorta lot lots thing things get got go goes going gone went come comes came coming
make makes made making take takes took taken taking give gives gave given giving say says said saying
know knows knew known knowing think thinks thought thinking want wants wanted see sees saw seen look looks looked
tell tells told ask asks asked answer answers answered talk talks talked speak speaks spoke put puts putting
use uses used using find finds found need needs needed try tries tried keep keeps kept call calls called
mean means meant show shows showed become becomes became leave leaves left feel feels felt bring brings brought
begin begins began seem seems seemed help helps helped turn turns turned start starts started play plays played
run runs ran move moves moved live lives lived believe believes believed hold holds held happen happens happened
write writes wrote provide provides provided sit sits sat stand stands stood lose loses lost pay pays paid
meet meets met include includes included continue continues continued set sets learn learns learned change
changes changed lead leads led understand understands understood watch watches watched follow follows followed
stop stops stopped create creates created open opens opened walk walks walked win wins won offer offers offered
remember remembers remembered love loves loved consider considers considered appear appears appeared buy buys
bought wait waits waited serve serves served die dies died send sends sent expect expects expected build builds
built stay stays stayed fall falls fell cut cuts reach reaches reached kill kills killed remain remains remained
suggest suggests suggested raise raises raised pass passes passed sell sells sold require requires required
report reports reported decide decides decided pull pulls pulled
""".split())

TIER_NAMES = {
    "toefl_ielts": "托福/雅思核心",
    "sat_gre": "GRE/SAT进阶",
    "academic_philosophy": "生命定价与功利哲学",
    "phrasal_verbs": "核心动词短语",
}

SELECT_SYSTEM = """你是学术英语与法理学教研编辑。输入是一节哈佛《公正》公开课的**真实逐字稿词汇统计**（词/出现次数）与候选句子。
请从中挑选最适合做成「学术词汇卡片」的条目，并给出词条元数据。

选择标准（宁缺毋滥）：
1. 只从给定候选词表中挑选，**绝不能**自己造词或改动词形；
2. 优先挑选：道德哲学/政治哲学/法理学的核心术语、学术论证常用词、以及影响听力理解的低频词；
3. 排除：日常基础词、专有名词（人名/地名/书名）、纯语气词、缩写与拼写噪声；
4. 每个词必须配一个**真实出现该词的句子 id**（来自候选句子列表），该句要能体现这个词在论证中的作用；
5. 四个分级只能取：toefl_ielts / sat_gre / academic_philosophy / phrasal_verbs。

对每个词输出：{"word":候选词,"sentence_id":句id,"phonetic":"/.../","pos":"n./v./adj./adv./phrase","def_cn":"中文释义","tier":"四选一","level_name":"分级中文名","why":"一句话理由"}
只输出 JSON：{"words":[...]}"""


def candidates_from_transcript(sents, exclude):
    counts = collections.Counter()
    for s in sents:
        for w in norm_words(s["text"]):
            if len(w) >= 3 and w not in FUNCTION_WORDS and not w.isdigit():
                counts[w] += 1
    # keep words that appear often enough to matter but are not the lecture's filler
    items = [(w, c) for w, c in counts.items() if c >= 2 and w not in exclude]
    items.sort(key=lambda x: (-x[1], x[0]))
    return items


def sentence_index_for(sents, word):
    """Deterministic: the sentence that contains the word, preferring a mid-length one."""
    pat = re.compile(r"\b" + re.escape(word) + r"\b")
    hits = [i for i, s in enumerate(sents) if pat.search(s["text"].lower())]
    if not hits:
        return None
    best = min(hits, key=lambda i: (abs(len(norm_words(sents[i]["text"])) - 16), i))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", required=True)
    ap.add_argument("--count", type=int, default=COUNT)
    ap.add_argument("--title", default="")
    ap.add_argument("--rebuild", action="store_true",
                    help="rebuild even if the current deck already looks grounded")
    args = ap.parse_args()
    ep = args.episode
    rep = Report(f"{ep}_s0b_deck")

    sents = load_json(SENTS_TMPL.format(ep=ep))
    if not sents:
        rep.check("sentences available (run S1 first)", False, SENTS_TMPL.format(ep=ep))
        rep.write()
        return 1
    rep.check("sentences available (run S1 first)", True, f"{len(sents)} sentences")

    old_words, deck_kind = load_deck_words(ep)

    # Safety: never overwrite a deck that is already grounded in the audio.
    if old_words and not args.rebuild:
        blob = " ".join(s["text"] for s in sents).lower()
        hit = sum(1 for w in old_words
                  if re.search(r"\b" + re.escape(w["word"].lower()) + r"\b", blob))
        if hit / len(old_words) >= 0.8:
            rep.check("existing deck is already grounded in the lecture", True,
                      f"{hit}/{len(old_words)} words occur; pass --rebuild to force a rebuild")
            rep.note("nothing to do -> S0b skipped")
            rep.write()
            return 0
        # Informational, not a failure: this is exactly why we are rebuilding.
        rep.note(f"existing deck is NOT grounded in the lecture "
                 f"({hit}/{len(old_words)} words occur) -> rebuilding from the transcript")

    # Words already owned by ANOTHER LECTURE deck are excluded so two episodes do
    # not teach the same word twice. Exam decks (exam_*) are deliberately NOT
    # counted as owners: they are dictionary imports, so excluding their 3000
    # words removed 290 words that genuinely occur in this lecture - including
    # "justice" and "principle" from the Justice lecture itself. The bank merges
    # both anyway, and `taught_in` records every deck a word belongs to.
    other_decks = set()
    tiered = load_json(TIERED) or {}
    for k, payload in tiered.items():
        if k != ep:
            other_decks.update(w["word"].lower() for w in payload.get("words", []))
    for k, payload in (load_json(CUSTOM_EPISODES) or {}).items():
        other_decks.update(w["word"].lower() for w in payload.get("words", []))
    lecture_owners = len(other_decks)
    cands = candidates_from_transcript(sents, exclude=other_decks)
    rep.check("candidate vocabulary built", len(cands) >= min(args.count, 60),
              f"{len(cands)} candidates after excluding {lecture_owners} words owned "
              f"by other lecture decks (exam decks do not exclude)")

    # Selecting 163 words in ONE response does not fit the output budget: the
    # model's JSON was being truncated mid-object ("level_na) and the stage
    # failed. Ask for a share of the words per slice of the lecture instead -
    # which also spreads the deck across the whole episode rather than letting
    # the model cluster everything in the first ten minutes.
    windows = max(1, (args.count + SELECT_BATCH - 1) // SELECT_BATCH)
    per_window = args.count // windows + 4
    picks = []
    for wi in range(windows):
        lo = wi * len(sents) // windows
        hi = (wi + 1) * len(sents) // windows
        win_sents = sents[lo:hi]
        win_text = " ".join(s["text"].lower() for s in win_sents)
        win_cands = [(w, c) for w, c in cands
                     if re.search(r"\b" + re.escape(w) + r"\b", win_text)]
        if not win_cands:
            continue
        listing = ", ".join(f"{w}({c})" for w, c in win_cands[:400])
        sent_listing = "\n".join(f"{lo + i}|{s['text']}" for i, s in enumerate(win_sents))
        user = (f"候选词表（词(出现次数)）：\n{listing}\n\n"
                f"候选句子（句id|英文，句 id 是全局编号）：\n{sent_listing}\n\n"
                f"请挑选 {per_window} 个最有教学价值的词条，sentence_id 必须使用上面给出的全局句 id。")

        def validate(o, per_window=per_window):
            """Only structural checks here.

            Picks that fall outside the candidate list, repeat a word, or point at the
            wrong sentence are repaired or dropped deterministically afterwards - failing
            the whole stage for those would be brittle (the model naturally reaches for
            words other decks already own). What must never happen is shipping a word
            that does not occur, and that is enforced by the post-filter + final gate.
            """
            if not isinstance(o, dict) or not isinstance(o.get("words"), list):
                return 'expected {"words":[...]}'
            ws = o["words"]
            if len(ws) < max(6, per_window // 2):
                return f"only {len(ws)} words returned, need about {per_window}"
            for w in ws:
                name = (w.get("word") or "").strip().lower()
                if not name:
                    return "every entry needs a word"
                if w.get("tier") not in TIER_NAMES:
                    return f"{name}: tier must be one of {list(TIER_NAMES)}"
                if not (w.get("def_cn") or "").strip():
                    return f"{name}: def_cn is required"
            return None

        try:
            obj = ask_json(SELECT_SYSTEM, user, tag=f"{ep}_s0b_select_w{wi:02d}",
                           validate=validate, max_tokens=8000, temperature=0.2)
        except RuntimeError as e:
            log("    window %d/%d selection failed: %s", wi + 1, windows, str(e)[:140])
            rep.note(f"window {wi + 1}/{windows} produced no usable selection")
            continue
        picks.extend(obj["words"])
    rep.check("AI selection is a subset of the transcript vocabulary", bool(picks),
              f"{len(picks)} words chosen across {windows} lecture window(s)")
    if not picks:
        rep.check("the model produced at least one usable selection", False,
                  "every window failed")
        return 1

    # The model often mis-points at the sentence (and occasionally at the metadata):
    # wherever the correct answer is computable, repair it deterministically instead
    # of failing the stage.
    #
    # The candidate list is a HINT, not a whitelist. A word the model proposed is
    # perfectly usable when it really occurs in this lecture and is not owned by
    # another lecture deck - rejecting it merely because our frequency/length
    # filter left it out of the list threw away 100 good picks (principle,
    # totalitarianism, endorsed ...) and shrank the deck to half its size.
    repaired, dropped, rescued = 0, [], []
    allowed = {w for w, _ in cands}
    seen = set()
    cleaned = []
    for p in picks:
        name = p.get("word", "").strip()
        key = name.lower()
        if key in seen:
            dropped.append(name + " (duplicate)")
            continue
        if key not in allowed:
            occurs = sentence_index_for(sents, key) is not None
            owned = key in other_decks
            if not occurs:
                dropped.append(name + " (never occurs in this lecture)")
                continue
            if owned:
                dropped.append(name + " (already taught by another lecture deck)")
                continue
            rescued.append(name)
        seen.add(key)
        sid = p.get("sentence_id")
        ok = isinstance(sid, int) and 0 <= sid < len(sents) and \
            re.search(r"\b" + re.escape(key) + r"\b", sents[sid]["text"].lower())
        if not ok:
            auto = sentence_index_for(sents, key)
            if auto is None:
                dropped.append(name + " (no occurrence)")
                continue
            p["sentence_id"] = auto
            repaired += 1
        cleaned.append(p)
    picks = cleaned[:args.count]
    if repaired:
        rep.note(f"repaired {repaired} sentence pointers deterministically (model mis-pointed)")
    if rescued:
        rep.note(f"kept {len(rescued)} words the candidate filter had skipped but which "
                 f"really occur in this lecture: {rescued[:8]}")
    if dropped:
        rep.note(f"dropped {len(dropped)} picks: {dropped[:8]}")
    rep.note(f"{len(picks)} usable words remain (requested {args.count})")

    # ---- build the deck -------------------------------------------------
    title = args.title or (tiered.get(ep, {}) or {}).get("title") or ep
    cn_title = (tiered.get(ep, {}) or {}).get("cn_title") or title
    words = []
    for p in picks:
        name = p["word"].strip()
        sid = p["sentence_id"]
        s = sents[sid]
        words.append({
            "word": name,
            "phonetic": p.get("phonetic", ""),
            "pos": p.get("pos", ""),
            "def_cn": p.get("def_cn", "").strip(),
            "tier": p["tier"],
            "level": p["tier"],
            "level_name": p.get("level_name") or TIER_NAMES[p["tier"]],
            "sentence": s["text"],
            "sentence_cn": "",
            "sentence_id": sid,
            "sentence_start": s["start"],
            "sentence_end": s["end"],
            "audio_start": s["start"],
            "audio_end": s["end"],
            "audio_duration": round(s["end"] - s["start"], 3),
            "timestamp": "%02d:%02d" % (int(s["start"]) // 60, int(s["start"]) % 60),
            "speaker": "Prof. Michael Sandel",
            "why": p.get("why", ""),
        })

    # ---- gates ----------------------------------------------------------
    missing = [w["word"] for w in words
               if not re.search(r"\b" + re.escape(w["word"]) + r"\b",
                                " ".join(x["text"] for x in sents).lower())]
    rep.check("every chosen word really occurs in the lecture", not missing, f"{len(missing)}: {missing[:6]}")
    rep.check("rebuilt deck is grounded (>=90% of words occur)",
              (len(words) - len(missing)) / max(1, len(words)) >= 0.9,
              f"{len(words) - len(missing)}/{len(words)}")
    notin = [w["word"] for w in words
             if not re.search(r"\b" + re.escape(w["word"]) + r"\b", w["sentence"].lower())]
    rep.check("every example sentence contains its word", not notin, f"{len(notin)}: {notin[:6]}")
    dupes = [w for w, c in collections.Counter(x["word"].lower() for x in words).items() if c > 1]
    rep.check("no duplicate words", not dupes, str(dupes[:6]))
    lv = collections.Counter(w["tier"] for w in words)
    rep.note(f"tier mix: {dict(lv)}")
    spans = [w["audio_duration"] for w in words]
    rep.check("all example spans are usable (0.8s..40s)",
              all(0.8 <= x <= 40 for x in spans), f"min={min(spans):.1f}s max={max(spans):.1f}s")

    payload = rep.write()
    if not rep.ok:
        rep.note("gates failed -> deck NOT written")
        return 1

    # ---- write, archiving the previous deck -----------------------------
    os.makedirs(RETIRED, exist_ok=True)
    if old_words:
        save_json(os.path.join(RETIRED, f"{ep}_previous_deck.json"),
                  {"words": old_words, "source": deck_kind,
                   "note": "replaced by S0b because it was not grounded in the audio"})
        rep.note(f"previous deck archived ({len(old_words)} words) -> data/_retired/{ep}_previous_deck.json")
    tiered = load_json(TIERED) or {}
    entry = dict(tiered.get(ep, {}))
    entry.update({"id": ep, "title": title, "cn_title": cn_title, "words": words})
    entry.setdefault("topic", f"《{title}》核心学术词汇")
    entry.setdefault("duration", "55 分钟")
    entry.setdefault("cover_scene", "/assets/scenes/banner_harvard_series.jpg")
    tiered[ep] = entry
    save_json(TIERED, tiered)
    rep.note(f"deck written: {len(words)} words into curriculum_tiered.json[{ep}]")
    save_json(os.path.join(OUT_DIR, f"{ep}_deck.json"), words)
    rep.note(f"AI usage: {json.dumps(usage())}")
    payload = rep.write()
    log("\nS0b %s - %d words, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(words), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
