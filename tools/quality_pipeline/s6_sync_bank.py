# -*- coding: utf-8 -*-
"""S6 - rebuild the master vocabulary bank FROM the episode decks (single source of truth).

Why this stage exists
---------------------
`vocab_bank.json` used to be a hand-maintained parallel copy of the per-episode
cards. It drifted in two ways:

  * coverage : only 23/163 Ep01 words, 7/44 Ep03 words, 1/32 Yale words were
               present (the bank was still the old 56-word Ep01 subset);
  * content  : the bank stored its OWN copy of each example sentence, so
               224/245 comparable entries showed a different sentence than the
               card the student actually studied - Ep02 still showed the old
               fragmented ASR splice, Ep01 showed synthesised example sentences
               that were never said in the lecture.

Making the bank *derived* means one command re-syncs it after any episode rebuild,
and the gates below make drift impossible to ship.

Invariants enforced
-------------------
  1. every word of every deck (episodes + custom imports) exists in the bank;
  2. for every (word, episode) pair the bank context carries EXACTLY the deck's
     `sentence` and `sentence_cn`;
  3. SRS progress is never lost: review_count / total_seconds / status may only
     keep or increase;
  4. every entry has a non-empty `def_cn` and `word`;
  5. entries keep a stable order (existing order first, new words appended in
     deck order) so the vocabulary view does not jump around.

Output: data/vocab_bank.json (backed up first) + out/<ep>_bank_sync.json report
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (BACKUP_DIR, CURRICULUM_KEYS_ORDER, DATA_DIR, EPISODE, OUT_DIR,  # noqa: E402
                    Report, load_json, log, save_json)

TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
CUSTOM = os.path.join(DATA_DIR, "custom_episodes.json")
EXAM = os.path.join(DATA_DIR, "exam_decks.json")
LONGSENT = os.path.join(DATA_DIR, "longsent_decks.json")
BANK = os.path.join(DATA_DIR, "vocab_bank.json")
STUDY = os.path.join(DATA_DIR, "study_records.json")
REPORT = os.path.join(OUT_DIR, f"{EPISODE}_bank_sync.json")

DEFAULT_STATS = {"review_count": 0, "today_seconds": 0, "total_seconds": 0,
                 "status": "learning", "last_rating": "new", "last_reviewed_at": None}


def deck_sources():
    """Ordered {source_id: payload} for every deck that can contribute words."""
    out = {}
    tiered = load_json(TIERED) or {}
    for ep_id in CURRICULUM_KEYS_ORDER:
        if ep_id in tiered:
            out[ep_id] = tiered[ep_id]
    for ep_id, payload in (load_json(CUSTOM) or {}).items():
        out[ep_id] = payload
    # Exam decks imported from open lexical data (S9) and the long-sentence deck
    # (S10) both belong in the master bank.
    for ep_id, payload in (load_json(EXAM) or {}).items():
        out[ep_id] = payload
    for ep_id, payload in (load_json(LONGSENT) or {}).items():
        out[ep_id] = payload
    return out


def source_title(payload, ep_id):
    return payload.get("cn_title") or payload.get("title") or ep_id


def main():
    rep = Report(f"{EPISODE}_s6_bank_sync")
    decks = deck_sources()
    old_bank = load_json(BANK) or {}
    study = load_json(STUDY) or {}
    if not decks:
        rep.check("episode decks available", False, TIERED)
        rep.write()
        return 1
    rep.check("episode decks available", True,
              ", ".join(f"{k}={len(v.get('words', []))}" for k, v in decks.items()))
    rep.check("existing bank loaded", True, f"{len(old_bank)} entries")

    # ---------------- build ----------------
    entries = {}          # key -> entry
    order = [k for k in old_bank]          # keep the bank's current order
    per_source = {}
    missing_prob = []

    for ep_id, payload in decks.items():
        title = source_title(payload, ep_id)
        hits = 0
        for w in payload.get("words", []):
            name = (w.get("word") or "").strip()
            if not name:
                continue
            key = name.lower()
            ctx = {
                "source_id": ep_id,
                "source_title": title,
                "sentence": (w.get("sentence") or "").strip(),
                "trans": (w.get("sentence_cn") or "").strip(),
                "audio_url": (w.get("native_clip_url") or w.get("audio_url") or "").strip(),
            }
            if not ctx["sentence"] or not ctx["trans"]:
                missing_prob.append((key, ep_id))
            e = entries.get(key)
            if e is None:
                e = entries[key] = {
                    "word": name,
                    "phonetic": (w.get("phonetic") or "").strip(),
                    "pos": (w.get("pos") or "").strip(),
                    "def_cn": (w.get("def_cn") or "").strip(),
                    # The English definition is part of the card now (S4c); a
                    # rebuild that dropped it would silently undo that stage.
                    "def_en": (w.get("def_en") or "").strip(),
                    "def_en_source": (w.get("def_en_source") or "").strip(),
                    "contexts": [],
                    "stats": None,
                }
                if key not in order:
                    order.append(key)
            else:
                # keep the richest metadata
                for f in ("phonetic", "pos", "def_cn", "def_en", "def_en_source"):
                    if not e.get(f) and (w.get(f) or "").strip():
                        e[f] = w[f].strip()
            if not any(c["source_id"] == ep_id for c in e["contexts"]):
                e["contexts"].append(ctx)
                hits += 1
        per_source[ep_id] = hits

    # ---------------- carry over bank-only entries ----------------
    # Some entries exist in the bank but in no current deck (the original curated
    # Ep01/E02 bank). Deleting them would throw away a learner's SRS progress, so
    # they are carried over verbatim and flagged for review.
    carried = []
    for key in order:
        if key in entries:
            continue
        old = old_bank.get(key)
        if not old:
            continue
        entries[key] = {
            "word": old.get("word", key),
            "phonetic": old.get("phonetic", ""),
            "pos": old.get("pos", ""),
            "def_cn": old.get("def_cn", ""),
            "def_en": old.get("def_en", ""),
            "def_en_source": old.get("def_en_source", ""),
            "contexts": old.get("contexts", []),
            "bank_only": True,
        }
        carried.append(key)

    # ---------------- stats: never lose progress ----------------
    def study_stats(key):
        for _user, rec in study.items():
            ws = (rec or {}).get("words", {})
            if key in ws:
                s = ws[key]
                return {"review_count": s.get("review_count", 0),
                        "today_seconds": s.get("today_seconds", 0),
                        "total_seconds": s.get("total_seconds", 0),
                        "status": s.get("status", "learning"),
                        "last_rating": s.get("last_rating", "new"),
                        "last_reviewed_at": s.get("last_reviewed_at")}
        return None

    kept = 0
    for key in order:
        e = entries.get(key)
        if not e:
            continue
        old = old_bank.get(key) or {}
        old_stats = old.get("stats") or {}
        st = dict(DEFAULT_STATS)
        for src in (old_stats, study_stats(key) or {}):
            for f, v in (src or {}).items():
                if v not in (None, "", 0) or f in ("review_count", "total_seconds"):
                    st[f] = v
        # monotonic guard: review_count / total_seconds may not decrease
        st["review_count"] = max(int(old_stats.get("review_count") or 0), int(st.get("review_count") or 0))
        st["total_seconds"] = max(int(old_stats.get("total_seconds") or 0), int(st.get("total_seconds") or 0))
        if old_stats.get("last_reviewed_at") and not st.get("last_reviewed_at"):
            st["last_reviewed_at"] = old_stats["last_reviewed_at"]
        e["stats"] = st
        if old_stats:
            kept += 1

    new_bank = {k: entries[k] for k in order if k in entries}

    # ---------------- gates ----------------
    rep.check("every deck word exists in the bank",
              all(k in new_bank for k in entries), f"{len(new_bank)} entries")
    rep.check("no dictionary entry lost", set(old_bank) <= set(new_bank),
              f"removed: {sorted(set(old_bank) - set(new_bank))[:6]}")

    mism = []
    for ep_id, payload in decks.items():
        for w in payload.get("words", []):
            key = (w.get("word") or "").strip().lower()
            e = new_bank.get(key)
            if not e:
                continue
            ctx = next((c for c in e["contexts"] if c["source_id"] == ep_id), None)
            if ctx is None:
                mism.append((key, ep_id, "missing-context"))
            elif (ctx["sentence"] != (w.get("sentence") or "").strip()
                  or ctx["trans"] != (w.get("sentence_cn") or "").strip()):
                mism.append((key, ep_id, "text-drift"))
    rep.check("bank context text == deck card text for every (word, episode)",
              not mism, f"{len(mism)} mismatches: {mism[:6]}")

    empty_def = [k for k, e in new_bank.items() if not e["def_cn"]]
    rep.check("every entry has def_cn", not empty_def, f"{len(empty_def)}: {empty_def[:6]}")
    empty_ctx = [k for k, e in new_bank.items() if not e["contexts"]]
    rep.check("every entry has at least one context", not empty_ctx, str(empty_ctx[:6]))

    lost = []
    for key, old in old_bank.items():
        o = old.get("stats") or {}
        n = (new_bank.get(key) or {}).get("stats") or {}
        if int(n.get("review_count") or 0) < int(o.get("review_count") or 0) or \
           int(n.get("total_seconds") or 0) < int(o.get("total_seconds") or 0):
            lost.append(key)
    rep.check("no SRS progress lost", not lost, f"{len(lost)} entries regressed: {lost[:6]}")

    multi = {k: len(e["contexts"]) for k, e in new_bank.items() if len(e["contexts"]) > 1}
    rep.note(f"coverage: " + ", ".join(f"{k} {v}/{len(decks[k].get('words', []))}"
                                       for k, v in per_source.items()))
    rep.note(f"bank size {len(old_bank)} -> {len(new_bank)}; multi-context words: {len(multi)} "
             f"({sorted(multi.items(), key=lambda x: -x[1])[:6]})")
    rep.note(f"entries keeping existing SRS stats: {kept}")
    if carried:
        rep.note(f"{len(carried)} bank-only entries carried over (in the bank but in no deck, "
                 f"kept so learner progress survives): {carried[:10]}")
    if missing_prob:
        rep.note(f"{len(missing_prob)} (word, episode) pairs have an empty sentence/translation: "
                 f"{missing_prob[:6]}")

    # ---------------- write ----------------
    if not rep.ok:
        rep.note("gates failed -> bank NOT written")
        payload = rep.write()
        return 1
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, "vocab_bank.pre_sync.json")
    if os.path.isfile(BANK) and not os.path.exists(bak):
        shutil.copy2(BANK, bak)
        rep.note(f"backup: {bak}")
    save_json(BANK, new_bank)
    rep.note(f"wrote {BANK} ({os.path.getsize(BANK)} B)")
    save_json(REPORT, {"bank_size": len(new_bank), "per_source": per_source,
                       "multi_context": len(multi), "study_stats_kept": kept})
    payload = rep.write()
    log("\nS6 %s - bank %d entries, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(new_bank), payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
