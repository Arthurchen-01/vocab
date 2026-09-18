# -*- coding: utf-8 -*-
"""Verify the app locally, before anything is deployed.

    python tools/quality_pipeline/local_smoke.py
    python tools/quality_pipeline/local_smoke.py --port 8811 --keep

Starts the real `server.py` on a local port and runs the export conformance gate
against it, so a change to the export path, the .docx writer or the API can be
proven here instead of on production.

Why the strict port binding matters: `server.ThreadingHTTPServer` sets
`allow_reuse_address = True`, and on Windows that lets a *second* process bind an
already-listening port. A stale server from an earlier session then answers the
probes and you end up "verifying" code you did not change - which is exactly how
a broken export can look fixed locally. This script therefore binds with
`allow_reuse_address = False` and refuses to start when the port is busy.
"""
import argparse
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))


class StrictServer:
    """ThreadingHTTPServer that fails loudly instead of double-binding."""

    @staticmethod
    def make():
        sys.path.insert(0, REPO)
        # server.py reads sys.argv[1] as its port; this script's own flags must
        # not be mistaken for one.
        sys.argv = [sys.argv[0]]
        import server
        import http.server

        class _Strict(server.ThreadingHTTPServer):
            allow_reuse_address = False

        return server, _Strict


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8811)
    ap.add_argument("--keep", action="store_true", help="leave the server running")
    ap.add_argument("--skip-gate", action="store_true")
    args = ap.parse_args()

    if not port_is_free(args.port):
        sys.exit("port %d is already in use - a stale local server would answer the "
                 "probes instead of your current code. Pick another --port or kill it."
                 % args.port)

    os.chdir(REPO)
    # edge_tts is only needed for audio synthesis; stub it when absent so the API
    # can be exercised on a machine without it.
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        import types
        mod = types.ModuleType("edge_tts")

        class _Communicate:
            def __init__(self, *a, **k):
                pass

            async def save(self, path):
                open(path, "wb").close()

        mod.Communicate = _Communicate
        sys.modules["edge_tts"] = mod
        print("[deps] edge_tts stubbed (not installed)")

    server, strict = StrictServer.make()
    httpd = strict(("127.0.0.1", args.port), server.RequestHandler)
    print("[ready] http://127.0.0.1:%d  (strict bind, no double-bind)" % args.port)
    if args.keep:
        httpd.serve_forever()
        return 0

    import threading
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.5)

    rc = 0
    if not args.skip_gate:
        rc = subprocess.call([sys.executable,
                              os.path.join(HERE, "export_conformance.py"),
                              "--base", "http://127.0.0.1:%d" % args.port,
                              "--stage", "s7b_local"], cwd=REPO)
    httpd.shutdown()
    print("\n[local smoke] %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
