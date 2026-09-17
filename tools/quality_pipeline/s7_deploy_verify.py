# -*- coding: utf-8 -*-
"""S7 - deploy (restart the service) and verify the episode end to end on the live site.

This is the stage that used to be done by hand: restart the daemon, then check that
the public API and the static assets really serve the freshly rebuilt episode.

What it verifies
----------------
  1. the service is active and answers;
  2. /api/preset/<ep> returns the deck's word count and every card has a complete
     sentence, a translation, and a usable audio window;
  3. every clip/frame URL of the episode is reachable (sampled, with retries) both
     from the origin and through the public hostname;
  4. /api/vocab-bank contains the episode's words and its bank context matches the
     card text (this is the bank<->deck invariant, re-checked after deployment);
  5. writes a human-readable acceptance report (markdown) for the episode.

Never mutates content: it only restarts the daemon and reads.
"""
import argparse
import concurrent.futures as cf
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, EPISODE, OUT_DIR, PUBLIC_DIR, Report, load_json, log, save_json  # noqa: E402

ORIGIN = "http://127.0.0.1:8765"
PUBLIC = os.environ.get("VOCAB_PUBLIC_BASE", "https://vocab.samuraiguan.cloud")
SAMPLE = 24


def http_json(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "s7"}), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_status(url, method="HEAD", tries=3, timeout=40):
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "s7"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            continue
    return "ERR"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", default=EPISODE)
    ap.add_argument("--no-restart", action="store_true")
    args = ap.parse_args()
    ep = args.episode
    rep = Report(f"{ep}_s7_deploy")

    deck = (load_json(os.path.join(DATA_DIR, "curriculum_tiered.json")) or {}).get(ep, {})
    words = deck.get("words", [])
    rep.check("deck present", bool(words), f"{len(words)} words")

    if not args.no_restart:
        p = subprocess.run(["systemctl", "restart", "vocab_app"], capture_output=True, text=True)
        rep.check("service restarted", p.returncode == 0, (p.stderr or "ok").strip()[:120])
        for _ in range(15):
            time.sleep(1)
            q = subprocess.run(["systemctl", "is-active", "vocab_app"], capture_output=True, text=True)
            if q.stdout.strip() == "active":
                break
        rep.check("service is active",
                  subprocess.run(["systemctl", "is-active", "vocab_app"],
                                 capture_output=True, text=True).stdout.strip() == "active")

    # ---- live API ----
    try:
        live = http_json(f"{ORIGIN}/api/preset/{ep}")
        lw = live["words"] if isinstance(live, dict) else live
        rep.check("live API returns the episode", len(lw) == len(words),
                  f"live={len(lw)} deck={len(words)}")
    except Exception as e:  # noqa: BLE001
        rep.check("live API returns the episode", False, f"{type(e).__name__}: {e}")
        rep.write()
        return 1

    incomplete = [w["word"] for w in lw if not (w.get("sentence") or "").rstrip().endswith((".", "!", "?"))]
    rep.check("every live card sentence is complete", not incomplete, f"{len(incomplete)}: {incomplete[:5]}")
    notrans = [w["word"] for w in lw if not (w.get("sentence_cn") or "").strip()]
    rep.check("every live card has a translation", not notrans, f"{len(notrans)}: {notrans[:5]}")
    nowin = [w["word"] for w in lw if w.get("audio_start") is None or w.get("audio_end") is None]
    rep.check("every live card has an audio window", not nowin, f"{len(nowin)}: {nowin[:5]}")
    covered = [w["word"] for w in lw
               if w.get("sentence_start") is not None and (
                   w["audio_start"] > w["sentence_start"] + 0.001 or w["audio_end"] < w["sentence_end"] - 0.001)]
    rep.check("every clip covers its sentence head to tail", not covered, f"{len(covered)}: {covered[:5]}")

    # ---- compare every live card against the deck on disk ----
    deck_by_word = {w["word"]: w for w in words}
    drift = [w["word"] for w in lw
             if w["word"] in deck_by_word and (
                 w.get("sentence") != deck_by_word[w["word"]].get("sentence")
                 or w.get("sentence_cn") != deck_by_word[w["word"]].get("sentence_cn")
                 or w.get("audio_start") != deck_by_word[w["word"]].get("audio_start"))]
    rep.check("live cards match the delivered deck", not drift, f"{len(drift)} drifted: {drift[:5]}")

    # ---- assets: origin + public ----
    urls = []
    for w in lw:
        for f in ("native_clip_url", "scene_img", "audio_url"):
            if w.get(f):
                urls.append(w[f])
    sample = random.Random(7).sample(urls, min(SAMPLE, len(urls)))
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        origin_res = list(ex.map(lambda u: http_status(ORIGIN + u), sample))
    rep.check(f"sampled {len(sample)} asset URLs on the origin", all(r == 200 for r in origin_res),
              f"ok={sum(1 for r in origin_res if r == 200)} bad={[u for u, r in zip(sample, origin_res) if r != 200][:3]}")
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        public_res = list(ex.map(lambda u: http_status(PUBLIC + u), sample[:12]))
    rep.check("sampled 12 asset URLs through the public host", all(r == 200 for r in public_res),
              f"ok={sum(1 for r in public_res if r == 200)}")

    # ---- bank <-> deck invariant ----
    try:
        vb = http_json(f"{ORIGIN}/api/vocab-bank")
        bank = {w["word"].lower(): w for w in vb["words"]}
        missing = [w["word"] for w in lw if w["word"].lower() not in bank]
        rep.check("every episode word is in the master bank", not missing, f"{len(missing)}: {missing[:6]}")
        drift = []
        for w in lw:
            b = bank.get(w["word"].lower())
            if not b:
                continue
            ctx = next((c for c in b["contexts"] if c.get("source_id") == ep), None)
            if ctx and (ctx.get("sentence") != w.get("sentence") or ctx.get("trans") != w.get("sentence_cn")):
                drift.append(w["word"])
        rep.check("bank context matches the card text", not drift, f"{len(drift)} drifted: {drift[:6]}")
    except Exception as e:  # noqa: BLE001
        rep.check("master bank reachable", False, f"{type(e).__name__}: {e}")

    # ---- acceptance report ----
    md = [f"# 交付验收报告 · {ep}", "",
          f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
          f"- 词条数：**{len(lw)}**",
          f"- 句子数（去重）：**{len({w['sentence'] for w in lw})}**",
          f"- 译文数（去重）：**{len({w['sentence_cn'] for w in lw})}**",
          f"- 切片总时长：{sum(float(w.get('audio_duration') or 0) for w in lw):.0f}s",
          f"- 门禁结果：**{'PASS' if rep.ok else 'FAIL'}** "
          f"（{sum(1 for c in rep.checks if c['ok'])}/{len(rep.checks)} 通过）", ""]
    for c in rep.checks:
        md.append(f"- [{'x' if c['ok'] else ' '}] {c['check']}"
                  + (f" — {c['detail']}" if c["detail"] else ""))
    if rep.notes:
        md += ["", "## 备注"] + [f"- {n}" for n in rep.notes]
    save_json(os.path.join(OUT_DIR, f"{ep}_delivery.json"),
              {"episode": ep, "words": len(lw), "ok": rep.ok, "checks": rep.checks})
    path = os.path.join(OUT_DIR, f"{ep}_delivery.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    rep.note(f"acceptance report: {path}")
    payload = rep.write()
    log("\nS7 %s - %s, %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", ep, payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
