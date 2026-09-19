# -*- coding: utf-8 -*-
"""VerbalEx delivery pipeline - one entry point, from a link to a verified episode.

    python deliver.py --episode ep03                 # known episode (catalog)
    python deliver.py --url "https://youtu.be/..."   # resolves the episode from the URL
    python deliver.py --episode ep05 --url "..."     # explicit deck + explicit source

Stages (each one is a separate script with its own AI gate + assertions; the
orchestrator stops at the first failure so a broken artefact can never ship):

    S0 acquire   link            -> raw audio + video + timestamped transcript
    S1 sentences transcript      -> complete, punctuated English sentences (AI)
    S2 mapping   deck + sentences-> which sentence really contains each word (AI)
    S3 media     sentences+audio -> clips cut on sentence boundaries + frames
    S4 translate sentences       -> context-aware Chinese, AI reviewed
    S4b decks    other decks     -> fill missing translations anywhere
    S5 apply     artefacts       -> write the data files + verify invariants
    S6 bank      decks           -> rebuild the master vocabulary bank (derived)
    S7 deploy    live site       -> restart + end-to-end acceptance report

Nothing here needs a human in the middle: the AI calls inside S1/S2/S4/S4b are
validated by deterministic assertions, and every stage fails loudly instead of
shipping doubtful data.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, EPISODE, OUT_DIR, REPORT_DIR, WORK_DIR, load_json, log, save_json  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(DATA_DIR, "source_catalog.json")

STAGES = [
    ("s0", "s0_acquire_media.py", "acquire media + transcript from the source link"),
    ("s1", "s1_build_sentences.py", "rebuild complete English sentences from ASR"),
    ("s0b", "s0b_build_deck.py", "build a grounded word deck (only for new/ungrounded episodes)"),
    ("s2", "s2_map_words.py", "bind every target word to its sentence"),
    ("s3", "s3_cut_media.py", "re-cut clips + frames on sentence boundaries"),
    ("s4", "s4_translate.py", "context-aware translation + AI review"),
    ("s4b", "s4b_fill_deck_translations.py", "fill missing translations in the other decks"),
    ("s4c", "s4c_english_definitions.py", "author the English definition (def_en) for every deck word"),
    ("s5", "s5_apply_and_verify.py", "apply to data files + end-to-end verification"),
    ("s6", "s6_sync_bank.py", "rebuild the master vocab bank from the episode decks"),
    ("s6b", "s6b_sync_bank_def_en.py",
     "write def_en/taught_in into the bank and prove it matches the decks"),
    ("s7", "s7_deploy_verify.py", "restart the service + live acceptance report"),
    ("s7b", "export_conformance.py", "verify every export format over live HTTP"),
]
REPORT_NAME = {"s0": "acquire", "s1": "sentences", "s0b": "deck", "s2": "word_map", "s3": "media",
               "s4": "translation", "s4b": "deck_translations", "s4c": "english_definitions",
               "s5": "apply_verify", "s6": "bank_sync", "s6b": "bank_def_en", "s7": "deploy",
               "s7b": "export"}


def episode_from_url(url):
    """Match a source link against the catalog so a bare URL is enough."""
    cat = load_json(CATALOG) or {}
    for series in cat.values():
        for ep_id, ep in (series.get("episodes") or {}).items():
            vid = ep.get("video_id") or ""
            if vid and vid in url:
                return ep_id, ep
            if ep.get("url") and ep["url"] in url:
                return ep_id, ep
    return "", {}


def deck_exists(ep):
    tiered = load_json(os.path.join(DATA_DIR, "curriculum_tiered.json")) or {}
    custom = load_json(os.path.join(DATA_DIR, "custom_episodes.json")) or {}
    return ep in tiered or ep in custom


def stage_args(key, args, ep):
    if key == "s0":
        out = ["--ep-id", ep]
        out += ["--url", args.url] if args.url else ["--episode", ep]
        if args.force:
            out.append("--force")
        if args.no_video:
            out.append("--no-video")
        return out
    if key == "s0b":
        return ["--episode", ep, "--count", str(args.deck_size)] + (["--rebuild"] if args.rebuild_deck else [])
    if key == "s5":
        out = ["--episode", ep]
        if args.write:
            out.append("--write")
        # The post-write check must hit the ORIGIN: a server-side request to the
        # public hostname can be answered with 403 by Cloudflare's bot rules.
        out += ["--deploy-check", args.deploy_check or "http://127.0.0.1:8765"]
        return out
    if key in ("s7",):
        return ["--episode", ep] + (["--no-restart"] if args.no_restart else [])
    if key == "s7b":
        # Always probe the origin: a server-side request to the public hostname
        # can be answered with 403 by Cloudflare's bot rules.
        return ["--base", args.deploy_check or "http://127.0.0.1:8765"]
    return []


def deck_is_grounded(ep):
    """Is the existing deck actually grounded in this episode's transcript?

    A deck is considered ungrounded when a large share of its words never occur in
    the lecture text (that is how Ep03 arrived: 24/44 words were never said).
    """
    from config import norm_words  # local import keeps the module import-light
    sents = load_json(os.path.join(OUT_DIR, f"{ep}_sentences.json"))
    words, kind = load_deck_words(ep)
    if not sents or not words:
        return False, "no deck or no sentences yet"
    text = " ".join(s["text"] for s in sents).lower()
    hit = sum(1 for w in words if re.search(r"\b" + re.escape(w["word"].lower()) + r"\b", text))
    return (hit / len(words)) >= 0.8, f"{hit}/{len(words)} words occur in the lecture"


def main():
    ap = argparse.ArgumentParser(description="link -> verified episode delivery")
    ap.add_argument("--url", default="", help="source link (YouTube/Bilibili/...); enough by itself if the episode is catalogued")
    ap.add_argument("--episode", default=EPISODE, help="deck id, e.g. ep03")
    ap.add_argument("--from", dest="from_stage", default="s0", choices=[s[0] for s in STAGES])
    ap.add_argument("--only", default="", choices=[""] + [s[0] for s in STAGES])
    ap.add_argument("--write", action="store_true", help="write the data files in S5 (default: dry run)")
    ap.add_argument("--deploy-check", default="", help="base URL to cross-check in S5")
    ap.add_argument("--no-restart", action="store_true", help="S7 without restarting the service")
    ap.add_argument("--force", action="store_true", help="re-acquire media even if present")
    ap.add_argument("--no-video", action="store_true",
                    help="acquire audio only (no card frames; saves ~130 MB per episode)")
    ap.add_argument("--deck-size", type=int, default=45, help="words to pick when building a new deck")
    ap.add_argument("--rebuild-deck", action="store_true", help="rebuild the deck even if it looks grounded")
    ap.add_argument("--stage-timeout", type=int, default=7200)
    args = ap.parse_args()

    ep = args.episode
    catalog_hit = {}
    if args.url:
        found, entry = episode_from_url(args.url)
        catalog_hit = entry
        if found and (not args.episode or args.episode == EPISODE):
            ep = found
            log("[orchestrator] URL matched the catalog -> episode %s", ep)

    log("=" * 78)
    log("VERBALEX DELIVERY  episode=%s  url=%s", ep, args.url or "(from catalog)")
    log("work dir: %s", WORK_DIR)
    log("=" * 78)

    if not deck_exists(ep) and args.from_stage in ("s0", "s1", "s2"):
        log("[orchestrator] WARNING: deck %r does not exist yet.", ep)
        log("               S0 will still acquire the media and transcript; S2 will stop")
        log("               until the word list for this episode is created.")

    todo = [s for s in STAGES if s[0] == args.only] if args.only else \
           STAGES[[s[0] for s in STAGES].index(args.from_stage):]

    results = []
    for key, script, desc in todo:
        cmd = [sys.executable, "-u", os.path.join(HERE, script)] + stage_args(key, args, ep)
        log("\n" + "=" * 78)
        log("STAGE %s - %s", key.upper(), desc)
        log("  $ %s", " ".join(cmd[1:]))
        log("=" * 78)
        t0 = time.time()
        env = dict(os.environ, VOCAB_EP=ep)
        rc = subprocess.run(cmd, env=env, timeout=args.stage_timeout).returncode
        results.append({"stage": key, "desc": desc, "exit": rc, "seconds": round(time.time() - t0, 1)})
        log("-> %s in %.0fs", "PASS" if rc == 0 else "FAIL", time.time() - t0)
        if rc != 0:
            log("\n[STOP] stage %s failed its gates; later stages were not run.", key)
            break

    summary = {"episode": ep, "url": args.url, "catalog": catalog_hit, "results": results,
               "reports": {}}
    for key, _s, _d in STAGES:
        p = os.path.join(REPORT_DIR, f"{ep}_{key}_{REPORT_NAME[key]}.json")
        summary["reports"][key] = load_json(p) if os.path.exists(p) else None
    save_json(os.path.join(OUT_DIR, f"{ep}_delivery_summary.json"), summary)

    log("\n" + "=" * 78)
    log("DELIVERY SUMMARY - %s", ep)
    log("=" * 78)
    for r in results:
        log("  %-4s %-52s %-5s %6.0fs", r["stage"], r["desc"][:52],
            "PASS" if r["exit"] == 0 else "FAIL", r["seconds"])
    report = os.path.join(OUT_DIR, f"{ep}_delivery.md")
    if os.path.exists(report):
        log("\nacceptance report: %s", report)
    log("gate reports      : %s", REPORT_DIR)
    ok = bool(results) and all(r["exit"] == 0 for r in results) and len(results) == len(todo)
    log("\nRESULT: %s", "ALL STAGES PASSED" if ok else "INCOMPLETE / FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
