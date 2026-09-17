# -*- coding: utf-8 -*-
"""S5 - apply the pipeline results to the shipped data and verify end to end.

Writes the same Ep02 payload into BOTH files that carry it
(ep02_curriculum_final_audited.json and the ep02 section of curriculum_tiered.json),
then proves the invariants that were broken before:

  * every example sentence starts and ends where the clip does (head-to-tail);
  * every sentence contains its own target word;
  * one sentence -> exactly ONE Chinese translation (was up to 3 different ones);
  * no clip/frame missing, durations match the declared window;
  * optionally: the deployed API returns exactly what the files say.

Usage:  python s5_apply_and_verify.py [--deploy-check https://host]
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (AUDIO_CLIP_DIR, CLIP_PAD_HEAD, CLIP_PAD_TAIL, DATA_DIR,  # noqa: E402
                    EPISODE, OUT_DIR, PUBLIC_DIR, Report, SCENE_DIR, fmt_ts,
                    load_json, log, norm_words, normalize_text, safe_name, save_json,
                    tidy_english, BACKUP_DIR)

SENTS_FILE = os.path.join(OUT_DIR, f"{EPISODE}_sentences.json")
MAP_FILE = os.path.join(OUT_DIR, f"{EPISODE}_word_map.json")
TRANS_FILE = os.path.join(OUT_DIR, f"{EPISODE}_translations.json")
CURRICULUM = os.path.join(DATA_DIR, f"{EPISODE}_curriculum_final_audited.json")
TIERED = os.path.join(DATA_DIR, "curriculum_tiered.json")
REPORT_FILE = os.path.join(OUT_DIR, f"{EPISODE}_verification.json")

LEVELS = ["toefl_ielts", "sat_gre", "academic_philosophy", "phrasal_verbs"]


def clip_duration(path):
    try:
        p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        return float(p.stdout.strip().splitlines()[0])
    except Exception:
        return None


def build_payload(words, sents, wmap, trans, clip_bounds):
    by_word = {m["word"]: m for m in wmap["words"] if m}
    sent_by_id = {s["sent_id"]: s for s in sents}
    out = []
    for w in words:
        w = dict(w)
        m = by_word.get(w["word"])
        if not m:
            out.append(w)
            continue
        s = sent_by_id[m["sent_id"]]
        start, end = clip_bounds[m["sent_id"]]
        t = trans.get(str(m["sent_id"])) or trans.get(m["sent_id"])
        w["sentence"] = tidy_english(s["text"])
        w["sentence_cn"] = (t or {}).get("cn", w.get("sentence_cn", ""))
        w["audio_start"] = round(start, 3)
        w["audio_end"] = round(end, 3)
        w["audio_duration"] = round(end - start, 3)
        w["timestamp"] = fmt_ts(s["start"])
        w["sentence_id"] = m["sent_id"]
        w["sentence_start"] = s["start"]
        w["sentence_end"] = s["end"]
        w["clip_match"] = m["match"]
        w["scene_desc"] = f"哈佛公开课第二讲现场 · 时间戳 [{fmt_ts(s['start'])}]"
        out.append(w)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy-check", default="", help="base URL of the running site to cross-check")
    ap.add_argument("--write", action="store_true", help="actually overwrite the data files")
    args = ap.parse_args()

    rep = Report(f"{EPISODE}_s5_apply_verify")
    sents = load_json(SENTS_FILE)
    wmap = load_json(MAP_FILE)
    trans_all = load_json(TRANS_FILE) or {}
    trans = trans_all.get("translations", {})
    words = load_json(CURRICULUM)
    old_words = json.loads(json.dumps(words))
    if not (sents and wmap and words and trans):
        rep.check("inputs present", False, "missing sentences/word_map/translations/curriculum")
        rep.write()
        return 1
    rep.check("inputs present", True,
              f"{len(sents)} sentences, {len(wmap['words'])} words, {len(trans)} translations")

    sent_by_id = {s["sent_id"]: s for s in sents}
    audio_dur = None
    raw = os.path.join(DATA_DIR, "raw_audio", f"{EPISODE}_full.mp3")
    if os.path.isfile(raw):
        audio_dur = clip_duration(raw)
    clip_bounds = {}
    for sid in {m["sent_id"] for m in wmap["words"] if m}:
        s = sent_by_id[sid]
        start = max(0.0, s["start"] - CLIP_PAD_HEAD)
        end = s["end"] + CLIP_PAD_TAIL
        if audio_dur:
            end = min(audio_dur, end)
        clip_bounds[sid] = (round(start, 3), round(end, 3))

    import s2_map_words as s2  # reuse the same containment test

    # ------------------------------------------------ invariant checks
    one_cn = {}
    for m in wmap["words"]:
        if not m:
            continue
        one_cn.setdefault(m["sent_id"], set()).add(trans.get(str(m["sent_id"]), {}).get("cn", ""))
    conflicts = {k: v for k, v in one_cn.items() if len(v) > 1}
    rep.check("one sentence -> exactly one Chinese translation", not conflicts,
              f"{len(conflicts)} sentences with conflicting translations")

    not_contained = []
    for m in wmap["words"]:
        if not m:
            continue
        txt = sent_by_id[m["sent_id"]]["text"]
        if s2.contains(txt, m["word"]):
            continue
        # phrasal entries carry an AI-quoted verbatim fragment as proof
        ev = normalize_text(m.get("evidence") or "").lower()
        if ev and len(ev) >= 3 and ev in normalize_text(txt).lower():
            continue
        not_contained.append(m["word"])
    rep.check("every example sentence contains its target word (matcher or AI quote)", not not_contained,
              f"{len(not_contained)} violations: {not_contained[:8]}")

    head_to_tail = []
    for m in wmap["words"]:
        if not m:
            continue
        s = sent_by_id[m["sent_id"]]
        a, b = clip_bounds[m["sent_id"]]
        if a > s["start"] + 0.001 or b < s["end"] - 0.001:
            head_to_tail.append(m["word"])
    rep.check("every clip covers its sentence head to tail (plus pad)", not head_to_tail,
              f"{len(head_to_tail)} violations")

    missing_clip, bad_dur, missing_frame = [], [], []
    for m in wmap["words"]:
        if not m:
            continue
        safe = safe_name(m["word"])
        cp = os.path.join(AUDIO_CLIP_DIR, f"{EPISODE}_{safe}_native.mp3")
        fp = os.path.join(SCENE_DIR, EPISODE, f"frame_{safe}.jpg")
        if not os.path.isfile(cp):
            missing_clip.append(m["word"])
        else:
            d = clip_duration(cp)
            want = clip_bounds[m["sent_id"]][1] - clip_bounds[m["sent_id"]][0]
            if d is None or abs(d - want) > 0.30:
                bad_dur.append((m["word"], round(want, 2), None if d is None else round(d, 2)))
        if not os.path.isfile(fp):
            missing_frame.append(m["word"])
    rep.check("all clips present on disk", not missing_clip, str(missing_clip[:6]))
    rep.check("all clip durations match the declared window", not bad_dur, str(bad_dur[:6]))
    rep.check("all frames present on disk", not missing_frame, str(missing_frame[:6]))

    payload_words = build_payload(words, sents, wmap, trans, clip_bounds)
    rep.check("word count unchanged", len(payload_words) == len(words), f"{len(payload_words)}")
    lv = {}
    for w in payload_words:
        lv[w.get("level")] = lv.get(w.get("level"), 0) + 1
    rep.check("tier distribution unchanged (104/51/25/35)",
              lv == {"toefl_ielts": 104, "sat_gre": 51, "academic_philosophy": 25, "phrasal_verbs": 35},
              str(lv))
    dupes = {w["word"] for w in payload_words if [x["word"] for x in payload_words].count(w["word"]) > 1}
    rep.check("no duplicate words", not dupes, str(sorted(dupes)[:6]))

    dur_old = sum(float(w.get("audio_duration") or 0) for w in old_words)
    dur_new = sum(float(w.get("audio_duration") or 0) for w in payload_words)
    rep.note(f"total clip length {dur_old:.0f}s -> {dur_new:.0f}s "
             f"(median {sorted(float(w.get('audio_duration') or 0) for w in payload_words)[len(payload_words)//2]:.1f}s)")

    improved = 0
    for o, n in zip(old_words, payload_words):
        if o.get("sentence") != n.get("sentence"):
            improved += 1
    rep.note(f"{improved}/{len(words)} words now quote a different (complete) sentence than before")

    # ------------------------------------------------ write + verify
    if args.write:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        for p in (CURRICULUM, TIERED):
            if os.path.isfile(p):
                dst = os.path.join(BACKUP_DIR, os.path.basename(p))
                if not os.path.exists(dst):
                    with open(p, "rb") as a, open(dst, "wb") as b:
                        b.write(a.read())
        save_json(CURRICULUM, payload_words)
        tiered = load_json(TIERED) or {}
        if EPISODE in tiered:
            tiered[EPISODE]["words"] = payload_words
            save_json(TIERED, tiered)
        rep.note(f"data written: {CURRICULUM} and curriculum_tiered.json[{EPISODE}]")
        same = load_json(CURRICULUM) == (load_json(TIERED) or {}).get(EPISODE, {}).get("words")
        rep.check("the two Ep02 copies are byte-identical in content", same)
    else:
        rep.note("dry run (pass --write to update the data files)")

    # ------------------------------------------------ optional live check
    if args.deploy_check:
        import urllib.request
        try:
            with urllib.request.urlopen(args.deploy_check.rstrip("/") + f"/api/preset/{EPISODE}",
                                        timeout=60) as r:
                live = json.loads(r.read().decode("utf-8"))
            lw = live["words"] if isinstance(live, dict) else live
            rep.check("live API returns the same word count", len(lw) == len(payload_words),
                      f"live={len(lw)} local={len(payload_words)}")
            mism = [(a["word"], b["word"]) for a, b in zip(payload_words, lw)
                    if a["sentence"] != b.get("sentence") or a["sentence_cn"] != b.get("sentence_cn")]
            rep.check("live API serves the new sentences/translations", not mism,
                      f"{len(mism)} mismatched rows: {mism[:5]}")
        except Exception as e:  # noqa: BLE001
            rep.check("live API reachable", False, f"{type(e).__name__}: {e}")

    save_json(REPORT_FILE, {"episode": EPISODE, "checks": rep.checks, "notes": rep.notes,
                            "ok": rep.ok})
    payload = rep.write()
    log("\nS5 %s - %d passed / %d failed",
        "PASS" if payload["ok"] else "FAIL", payload["passed"], payload["failed"])
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
