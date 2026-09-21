# -*- coding: utf-8 -*-
"""Measured provider health, so the fallback order is data rather than opinion.

Every resolution records (provider, host) -> attempts / successes / total ms.
The resolver then tries the provider that has actually been working for that host
first, instead of the order someone typed into an if/elif chain.

Self-contained on purpose: this package ships inside the app, so it must not
import the quality pipeline's config. State goes to VOCAB_WORK_DIR when set
(pipeline runs), otherwise next to the app's data directory.
"""
import json
import os
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)


def _store_path():
    work = os.environ.get("VOCAB_WORK_DIR", "").strip()
    if work:
        out = os.path.join(work, "out")
        if os.path.isdir(out) or os.path.isdir(work):
            return os.path.join(out, "provider_health.json")
    return os.path.join(_APP, "data", "provider_health.json")


STORE = _store_path()


def _load():
    try:
        with open(STORE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:  # noqa: BLE001
        return {}


def _save(data):
    try:
        os.makedirs(os.path.dirname(STORE), exist_ok=True)
        tmp = STORE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE)
    except Exception:  # noqa: BLE001 - health is advisory, never fatal
        pass


def _key(provider, host):
    return "%s@%s" % (provider, host or "-")


def record(provider, host, ok, seconds=0.0, note=""):
    data = _load()
    row = data.setdefault(_key(provider, host),
                          {"attempts": 0, "successes": 0, "total_ms": 0,
                           "last_note": "", "updated": ""})
    row["attempts"] += 1
    row["successes"] += 1 if ok else 0
    row["total_ms"] += int(seconds * 1000)
    if note:
        row["last_note"] = str(note)[:160]
    row["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save(data)
    return row


def score(provider, host):
    """(success_rate, mean_ms) - unknown providers sit in the middle."""
    row = _load().get(_key(provider, host))
    if not row or not row.get("attempts"):
        return (0.5, 0)
    return (row["successes"] / float(row["attempts"]),
            row["total_ms"] / float(row["attempts"]))


def snapshot():
    return _load()
