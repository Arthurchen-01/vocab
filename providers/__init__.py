# -*- coding: utf-8 -*-
"""Pluggable source providers (see `base.py` for the contract).

Layering
--------
    providers/base.py       capability contract + registry loader
    providers/policy.py     per-request / per-user knobs (data, not code paths)
    providers/health.py     measured success per (provider, host) -> chain order
    providers/resolver.py   picks the chain, merges partial results, records health
    providers/<tool>.py     one file per tool

`downloader.py` keeps its public functions and delegates here, so the app and
server code did not have to change when the chain became pluggable.
"""

__all__ = ["base", "policy", "health", "resolver"]
