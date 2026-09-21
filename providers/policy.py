# -*- coding: utf-8 -*-
"""Per-request / per-user resolution policy.

"Multiple backups, tuned to what the user and we need" is exactly this file: the
knobs are data, not code paths. Defaults come from the environment (so the
operator sets the house policy once) and any caller may override them per
request - the app can offer a "fast" and a "best" mode without a code change.

Nothing here may ever enable fabrication. `require_real_subtitles` defaults to
True, and turning on `allow_asr` only permits a *machine transcript* that is
labelled as such.
"""
import os

QUALITY_FAST = "fast"     # stop at the first provider that satisfies the need
QUALITY_BEST = "best"     # consult every capable provider, keep the best transcript

DEFAULTS = {
    "quality": os.environ.get("VOCAB_RESOLVE_QUALITY", QUALITY_BEST),
    "allow_asr": (os.environ.get("VOCAB_ALLOW_ASR", "1") not in ("0", "false", "no")),
    "asr_model": os.environ.get("VOCAB_ASR_MODEL", "small"),
    "asr_compute": os.environ.get("VOCAB_ASR_COMPUTE", "int8"),
    "asr_python": os.environ.get("VOCAB_ASR_PYTHON", "/opt/asr-venv/bin/python"),
    "asr_max_minutes": int(os.environ.get("VOCAB_ASR_MAX_MINUTES", "90") or 0),
    # refuse to produce vocabulary from anything but real source text
    "require_real_subtitles": True,
    # 0 = no limit; otherwise refuse sources longer than this
    "max_minutes": int(os.environ.get("VOCAB_MAX_MINUTES", "0") or 0),
    # login-gated sources (e.g. Bilibili AI subtitles) need a cookie file
    "cookies_file": os.environ.get("VOCAB_COOKIES_FILE", ""),
    "timeout": int(os.environ.get("VOCAB_PROVIDER_TIMEOUT", "180")),
}


def resolve(overrides=None):
    """House defaults + environment + this request's overrides."""
    policy = dict(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key in policy and value is not None:
            policy[key] = value
    policy["quality"] = str(policy["quality"]).lower()
    if policy["quality"] not in (QUALITY_FAST, QUALITY_BEST):
        policy["quality"] = QUALITY_BEST
    return policy


def describe(policy):
    keys = ("quality", "allow_asr", "asr_model", "require_real_subtitles",
            "max_minutes", "cookies_file")
    return ", ".join("%s=%s" % (k, policy.get(k)) for k in keys)
