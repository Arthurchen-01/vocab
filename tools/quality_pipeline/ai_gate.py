# -*- coding: utf-8 -*-
"""Thin, cached LLM gateway used by every pipeline stage (the "AI gate").

Design rules:
  * every call is cached on disk keyed by (model, system, user) so a re-run is
    cheap and reproducible;
  * every call asks for strict JSON and is validated by the caller;
  * failures raise, they never silently degrade into "no AI review happened".
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import AI_BASE, AI_MODEL, CACHE_DIR, api_key, load_json, log, save_json, sha1  # noqa: E402

USAGE_FILE = os.path.join(CACHE_DIR, "_usage.json")
_usage = load_json(USAGE_FILE, {"calls": 0, "cached": 0, "prompt_tokens": 0, "completion_tokens": 0})


def _cache_path(tag, key):
    return os.path.join(CACHE_DIR, f"{tag}__{key}.json")


def usage():
    return dict(_usage)


def _flush_usage():
    save_json(USAGE_FILE, _usage)


def chat(system, user, tag, model=None, max_tokens=8000, temperature=0.2,
         json_mode=True, use_cache=True, retries=3, timeout=180):
    """Single LLM round-trip. Returns the raw assistant text (JSON string if json_mode)."""
    model = model or AI_MODEL
    key = sha1("\u0000".join([model, system or "", user or "", str(temperature), str(json_mode)]))
    cp = _cache_path(tag, key)
    if use_cache and os.path.exists(cp):
        cached = load_json(cp)
        if cached is not None:
            _usage["cached"] += 1
            _flush_usage()
            return cached["content"]

    k = api_key()
    if not k:
        raise RuntimeError("no API key available (DEEPSEEK_API_KEY or data/secret_config.json)")

    payload = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else [])
                    + [{"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(1, retries + 1):
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{AI_BASE}/chat/completions", data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {k}"})
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            u = data.get("usage") or {}
            _usage["calls"] += 1
            _usage["prompt_tokens"] += int(u.get("prompt_tokens") or 0)
            _usage["completion_tokens"] += int(u.get("completion_tokens") or 0)
            _flush_usage()
            log("    ai[%s] %d chars in %.1fs (prompt=%s completion=%s)",
                tag, len(content), time.time() - t0,
                u.get("prompt_tokens"), u.get("completion_tokens"))
            if use_cache:
                save_json(cp, {"content": content, "model": model, "tag": tag})
            return content
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode("utf-8", "replace")
            last_err = f"HTTP {e.code}: {detail}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        log("    ai[%s] attempt %d/%d failed: %s", tag, attempt, retries, last_err)
        time.sleep(2 * attempt)
    raise RuntimeError(f"AI call '{tag}' failed after {retries} attempts: {last_err}")


def _extract_json(text):
    """Tolerate ```json fences and leading prose."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t[:-3]
        t = t.strip()
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # last resort: first {...} or [...] block
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except Exception:
                continue
    raise ValueError("response is not valid JSON: " + t[:200])


def ask_json(system, user, tag, validate=None, repair_rounds=2, **kw):
    """JSON-mode call with a validation/repair loop.

    `validate(obj)` must return None when acceptable, or a string describing the
    problem; that string is fed back to the model for a repair attempt.
    """
    convo = user
    last_problem = None
    for attempt in range(repair_rounds + 1):
        raw = chat(system, convo, tag if attempt == 0 else f"{tag}_repair{attempt}", **kw)
        try:
            obj = _extract_json(raw)
        except ValueError as e:
            last_problem = str(e)
        else:
            if validate is None:
                return obj
            problem = validate(obj)
            if not problem:
                return obj
            last_problem = problem
        log("    ai[%s] validation failed: %s", tag, str(last_problem)[:300])
        convo = (user + "\n\n---\nYour previous answer was REJECTED by the automated validator.\n"
                        f"Problem: {last_problem}\n"
                        "Return the COMPLETE corrected JSON again, same schema, no commentary.")
    raise RuntimeError(f"AI gate '{tag}' produced invalid output after repair: {last_problem}")
