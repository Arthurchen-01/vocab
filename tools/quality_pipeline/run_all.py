# -*- coding: utf-8 -*-
"""Orchestrator: run the whole Ep0x quality pipeline with gates, in order.

    python run_all.py                 # S1..S5 (S5 dry-run, no data written)
    python run_all.py --write         # also overwrite the shipped data files
    python run_all.py --from s3       # resume from a stage
    python run_all.py --deploy-check https://vocab.samuraiguan.cloud

Every stage writes a gate report to <work>/reports/<stage>.{json,md} and exits
non-zero when a gate fails; the orchestrator stops at the first failing stage so a
broken artefact can never reach the site.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import EPISODE, OUT_DIR, REPORT_DIR, log, save_json, WORK_DIR  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = [
    ("s1", "s1_build_sentences.py", "rebuild complete English sentences from ASR"),
    ("s2", "s2_map_words.py", "bind every target word to its sentence"),
    ("s3", "s3_cut_media.py", "re-cut clips + frames on sentence boundaries"),
    ("s4", "s4_translate.py", "context-aware translation + AI review"),
    ("s4b", "s4b_fill_deck_translations.py", "fill missing translations in the other decks"),
    ("s5", "s5_apply_and_verify.py", "apply to data files + end-to-end verification"),
    ("s6", "s6_sync_bank.py", "rebuild the master vocab bank from the episode decks"),
]


def run_stage(script, extra):
    cmd = [sys.executable, "-u", os.path.join(HERE, script)] + extra
    log("\n" + "=" * 78)
    log("RUN %s", " ".join(cmd[1:]))
    log("=" * 78)
    t0 = time.time()
    p = subprocess.run(cmd)
    log("-> exit %d in %.1fs", p.returncode, time.time() - t0)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_stage", default="s1", choices=[s[0] for s in STAGES])
    ap.add_argument("--only", default="", choices=[""] + [s[0] for s in STAGES])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--deploy-check", default="")
    args = ap.parse_args()

    started = args.from_stage
    todo = [s for s in STAGES if s[0] == args.only] if args.only else \
           STAGES[[s[0] for s in STAGES].index(started):]

    results = []
    for key, script, desc in todo:
        extra = []
        if key == "s5":
            if args.write:
                extra.append("--write")
            if args.deploy_check:
                extra += ["--deploy-check", args.deploy_check]
        rc = run_stage(script, extra)
        results.append({"stage": key, "script": script, "desc": desc, "exit": rc})
        if rc != 0:
            log("\n[STOP] stage %s failed its gates - later stages not run", key)
            break

    summary = {"episode": EPISODE, "work_dir": WORK_DIR, "results": results}
    for key, _script, _d in STAGES:
        base = os.path.join(REPORT_DIR, f"{EPISODE}_{key}_" + {"s1": "sentences", "s2": "word_map",
                                                              "s3": "media", "s4": "translation",
                                                              "s4b": "deck_translations",
                                                              "s5": "apply_verify",
                                                              "s6": "bank_sync"}[key] + ".json")
        summary.setdefault("reports", {})[key] = json.load(open(base, encoding="utf-8")) if os.path.exists(base) else None
    save_json(os.path.join(OUT_DIR, f"{EPISODE}_pipeline_summary.json"), summary)

    log("\n" + "=" * 78)
    log("PIPELINE SUMMARY (%s)", EPISODE)
    log("=" * 78)
    for r in results:
        log("  %-3s %-38s %s", r["stage"], r["desc"], "PASS" if r["exit"] == 0 else "FAIL")
    log("  reports: %s", REPORT_DIR)
    return 0 if all(r["exit"] == 0 for r in results) and len(results) == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
