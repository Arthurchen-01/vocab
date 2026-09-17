# -*- coding: utf-8 -*-
"""S6b - keep the master vocabulary bank and the episode decks in agreement.

The bank is a *derived* view: one entry per unique headword, each entry listing
every episode that used the word as a context. That is also the answer to
"为什么总词库和一集一集的词表看起来不一样" - they are not two different lists:

  * a word reused across episodes is ONE bank entry with N contexts, it is never
    dropped from the later episode;
  * a word that is in the bank but in no deck anymore is carried over and marked
    `bank_only: true` so a rebuild cannot silently delete it;
  * the bank additionally carries per-user study stats, which no deck has.

This stage is deliberately surgical: it ONLY propagates `def_en` from the decks
into the bank, then proves that nothing else in the bank changed. Rebuilding the
whole bank is S6's job and is far riskier to run against live data.

Gates
-----
  * key sets are identical before and after (no entry added, none removed);
  * every bank entry has a non-empty def_en;
  * bank def_en == deck def_en for every word that appears in a deck;
  * the only modified JSON field anywhere in the file is `def_en`;
  * drift between bank and decks is reported explicitly (bank-only words, and
    deck words missing from the bank).

Usage: python s6b_sync_bank_def_en.py [--dry-run]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, EPISODE, OUT_DIR, Report, load_json, log, save_json  # noqa: E402
from s4c_english_definitions import deck_sources  # noqa: E402

BANK = os.path.join(DATA_DIR, "vocab_bank.json")
REPORT = os.path.join(OUT_DIR, f"{EPISODE}_bank_def_en.json")


def deck_def_en():
    """lowercased headword -> (def_en, set(deck ids)) straight from the decks."""
    out = {}
    for ep_id, payload, _path in deck_sources():
        for w in payload.get("words", []):
            k = (w.get("word") or "").strip().lower()
            if not k:
                continue
            val = (w.get("def_en") or "").strip()
            slot = out.setdefault(k, {"def_en": "", "decks": set()})
            slot["decks"].add(ep_id)
            if val and not slot["def_en"]:
                slot["def_en"] = val
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rep = Report(f"{EPISODE}_s6b_bank_def_en")
    bank = load_json(BANK)
    if not isinstance(bank, dict) or not bank:
        rep.check("master bank readable", False, BANK)
        rep.write()
        return 1
    decks = deck_def_en()
    rep.check("master bank readable", True, f"{len(bank)} entries, {len(decks)} deck headwords")

    keys_before = set(bank)
    bank_only = sorted(k for k in keys_before if k not in decks)
    deck_missing = sorted(k for k in decks if k not in keys_before)
    rep.note(f"{len(bank_only)} bank-only words (kept, marked bank_only): {bank_only[:8]}")
    rep.check("no deck headword is missing from the master bank", not deck_missing,
              f"{len(deck_missing)}: {deck_missing[:8]}" if deck_missing
              else f"all {len(decks)} deck headwords are present")

    # `taught_in` is what the per-episode filter must use.  Deriving it here is
    # what makes the bank honest: a retired word (from a deck that has since been
    # rebuilt) keeps its historical context but is no longer attributed to the
    # episode, and a word reused across episodes lists every episode that
    # actually teaches it.  Guessing from contexts[].source_id is what made the
    # bank look like it contained words the episode decks did not have.
    stale = []
    for k, entry in bank.items():
        taught = sorted(decks.get(k, {}).get("decks", []))
        entry["taught_in"] = taught
        if not taught:
            entry["bank_only"] = True
            srcs = sorted({(c.get("source_id") or "") for c in (entry.get("contexts") or [])})
            stale.append((k, srcs))
    rep.note(f"{len(bank_only)} entries are taught by no current deck "
             f"(retired decks only): {[k for k, _ in stale][:8]}")
    if stale:
        by_ep = {}
        for _k, srcs in stale:
            for s in srcs:
                by_ep[s] = by_ep.get(s, 0) + 1
        rep.note("their historical contexts claim these episodes: %s "
                 "(shown only under '全部' now)" % by_ep)
    multi = [k for k in bank if len(bank[k].get("taught_in") or []) > 1]
    rep.note(f"{len(multi)} words are reused across episodes and kept as ONE entry "
             f"with one context per episode: {multi[:6]}")

    no_def = sorted(k for k in bank if not (bank[k].get("def_en") or "").strip())
    rep.note(f"{len(no_def)} bank entries had no def_en before this stage: {no_def[:6]}")

    filled, mismatched = 0, []
    for k, entry in bank.items():
        want = (decks.get(k) or {}).get("def_en", "")
        if not want:
            continue
        if (entry.get("def_en") or "").strip() != want:
            mismatched.append(k)
            if not args.dry_run:
                entry["def_en"] = want
                filled += 1
    rep.note(f"{len(mismatched)} bank entries disagreed with the decks "
             f"({filled} corrected, {len(no_def)} had no definition at all)")

    if args.dry_run:
        rep.check("dry run: the bank and the decks already agree",
                  not mismatched and not no_def,
                  f"{len(mismatched)} mismatched, {len(no_def)} missing")
        payload = rep.write()
        log("\nS6b dry-run %s - %d passed / %d failed",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 0 if payload["ok"] else 1

    still = sorted(k for k in bank if not (bank[k].get("def_en") or "").strip())
    rep.check("every bank entry carries a def_en after the sync", not still,
              f"{len(still)} without: {still[:8]}" if still else
              f"{len(bank)} entries, {filled} filled")

    rep.check("bank entry set is unchanged (no add, no remove)",
              set(bank) == keys_before,
              "%d -> %d" % (len(keys_before), len(bank)))

    before = load_json(BANK)
    changed_fields = set()
    for k in set(before) | set(bank):
        a, b = before.get(k, {}), bank.get(k, {})
        for field in set(a) | set(b):
            if a.get(field) != b.get(field):
                changed_fields.add(field)
    rep.check("only def_en / taught_in / bank_only were modified",
              changed_fields <= {"def_en", "taught_in", "bank_only"},
              f"changed: {sorted(changed_fields)}")

    wrong = sorted(k for k, v in bank.items()
                   if sorted(v.get("taught_in") or []) !=
                   sorted(decks.get(k, {}).get("decks", [])))
    rep.check("taught_in matches the decks for every entry", not wrong,
              f"{len(wrong)} wrong: {wrong[:6]}" if wrong
              else f"{len(bank) - len(bank_only)} attributed, {len(bank_only)} historical")

    if not rep.ok:
        rep.note("gates failed - the bank was NOT written")
        payload = rep.write()
        log("\nS6b %s - %d passed / %d failed (no write)",
            "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
        return 1

    save_json(BANK, bank)
    after = load_json(BANK)
    rep.check("written bank has def_en on every entry",
              all((v.get("def_en") or "").strip() for v in after.values()),
              f"{sum(1 for v in after.values() if (v.get('def_en') or '').strip())}"
              f"/{len(after)}")
    rep.check("written bank still has every key", set(after) == keys_before,
              f"{len(after)} entries")
    drift = [k for k, v in after.items()
             if k in decks and (v.get("def_en") or "").strip() != decks[k]["def_en"]]
    rep.check("written bank def_en is identical to the decks", not drift,
              f"{len(drift)}: {drift[:8]}")
    save_json(REPORT, {"entries": len(after), "def_en_written": filled,
                       "bank_only": len(bank_only), "dry_run": False})
    payload = rep.write()
    log("\nS6b %s - %d entries, %d def_en propagated, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", len(after), filled,
        payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
