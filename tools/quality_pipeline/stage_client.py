# -*- coding: utf-8 -*-
"""Run one pipeline stage on the production host, from here.

`deliver_client.py` drives the whole link -> episode flow. This is the smaller
tool for everything else: re-running a single stage, checking a gate, syncing
data, or pulling artefacts back - without hand-written SSH one-liners.

    python tools/quality_pipeline/stage_client.py --stage s6b
    python tools/quality_pipeline/stage_client.py --stage s6b --dry-run
    python tools/quality_pipeline/stage_client.py --stage s7b \
        --script export_conformance.py --args "--base http://127.0.0.1:8765"
    python tools/quality_pipeline/stage_client.py --stage s4c --pull data/curriculum_tiered.json

Credentials come from the environment or ~/.vocab_deploy.json (never the repo):
    VOCAB_SSH_HOST / VOCAB_SSH_USER / VOCAB_SSH_PASSWORD
"""
import argparse
import json
import os
import posixpath
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = "/var/www/harvard_justice_app"
PIPE = "/root/quality_pipeline"

# Stage output can contain anything the product renders (the Markdown export
# starts with an emoji). A Windows console defaults to a legacy code page and
# would raise UnicodeEncodeError while simply printing a log line.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

# Everything a stage might import, so the server always runs the current code.
# Discovered rather than listed: a hand-kept list once omitted s0b_build_deck.py.
CLIENT_ONLY = {"deliver_client.py", "stage_client.py", "run_all.py"}
UPLOAD_ALL = sorted(f for f in os.listdir(HERE)
                    if f.endswith(".py") and f not in CLIENT_ONLY
                    and os.path.isfile(os.path.join(HERE, f)))


def credentials():
    host = os.environ.get("VOCAB_SSH_HOST", "")
    user = os.environ.get("VOCAB_SSH_USER", "root")
    pwd = os.environ.get("VOCAB_SSH_PASSWORD", "")
    path = os.path.join(os.path.expanduser("~"), ".vocab_deploy.json")
    if not (host and pwd) and os.path.isfile(path):
        # utf-8-sig: PowerShell's `Set-Content -Encoding UTF8` and Notepad both
        # write a BOM, which plain utf-8 decoding rejects.
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        host = host or cfg.get("host", "")
        user = cfg.get("user", user)
        pwd = pwd or cfg.get("password", "")
    if not host or not pwd:
        sys.exit("missing SSH credentials: set VOCAB_SSH_HOST/USER/PASSWORD or create "
                 "~/.vocab_deploy.json")
    return host, user, pwd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True, help="file name inside tools/quality_pipeline")
    ap.add_argument("--stage", default="", help="label used for the log/report name")
    ap.add_argument("--args", default="", help="extra CLI arguments for the stage")
    ap.add_argument("--dry-run", action="store_true",
                    help="append --dry-run and stream the output in the foreground")
    ap.add_argument("--upload", default="", help="comma list; default: every pipeline script")
    ap.add_argument("--pull", default="", help="comma list of paths relative to the app dir")
    ap.add_argument("--reports", action="store_true",
                    help="pull out/<stage>_*.json, reports/<stage>_*.json and out/*delivery.md")
    ap.add_argument("--timeout", type=int, default=5400)
    args = ap.parse_args()

    try:
        import paramiko
    except ImportError:
        sys.exit("pip install paramiko")

    host, user, pwd = credentials()

    def connect_with_retry(host, user, pwd, attempts=6):
        last = None
        for attempt in range(attempts):
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(host, 22, user, pwd, timeout=30,
                              banner_timeout=30, auth_timeout=30)
                return client
            except Exception as exc:  # noqa: BLE001
                last = exc
                print("   [ssh] connect attempt %d failed: %s"
                      % (attempt + 1, type(exc).__name__))
                time.sleep(8)
        sys.exit("cannot reach %s: %s" % (host, last))

    c = connect_with_retry(host, user, pwd)

    def run(cmd, timeout=600, quiet=False):
        _i, o, e = c.exec_command(cmd, timeout=timeout)
        try:
            out = (o.read() + e.read()).decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            out = "(channel closed: %s)" % type(exc).__name__
        if not quiet:
            sys.stdout.write(out)
            sys.stdout.flush()
        return out

    label = args.stage or os.path.splitext(args.script)[0]
    log_path = "%s/logs/%s.log" % (PIPE, label)

    uploads = [f.strip() for f in args.upload.split(",") if f.strip()] or UPLOAD_ALL
    print("[upload] %d files -> %s" % (len(uploads), PIPE))
    pending, missing = list(uploads), []
    # The host drops SFTP sessions mid-transfer often enough that one connection
    # cannot be trusted for the whole batch: verify per file and reconnect.
    for _attempt in range(4):
        if not pending:
            break
        sftp = c.open_sftp()
        still = []
        for name in pending:
            local = os.path.join(HERE, name)
            if not os.path.isfile(local):
                missing.append(name)
                continue
            try:
                sftp.put(local, posixpath.join(PIPE, name))
            except Exception as exc:  # noqa: BLE001
                print("   [sftp] %s failed (%s), retrying"
                      % (name, type(exc).__name__))
                still.append(name)
                try:
                    sftp.close()
                except Exception:  # noqa: BLE001
                    pass
                c = connect_with_retry(host, user, pwd)
                sftp = c.open_sftp()
        try:
            sftp.close()
        except Exception:  # noqa: BLE001
            pass
        pending = still
    if pending:
        sys.exit("upload failed for: %s" % pending)
    if missing:
        print("   (missing locally: %s)" % missing)

    env = "VOCAB_APP_DIR=%s VOCAB_WORK_DIR=%s" % (APP, PIPE)
    if args.dry_run:
        print("\n[dry-run]")
        run("cd %s && %s python3 %s %s --dry-run 2>&1 | tail -40"
            % (PIPE, env, args.script, args.args), timeout=1800)
        sftp.close()
        c.close()
        return 0

    run("mkdir -p %s/logs && rm -f %s" % (PIPE, log_path), quiet=True)
    run("cd %s && setsid nohup env %s python3 -u %s %s > %s 2>&1 < /dev/null & echo LAUNCHED"
        % (PIPE, env, args.script, args.args, log_path))
    print("\n[log] %s\n" % log_path)

    seen, started = 0, time.time()
    while True:
        chunk = run("tail -c +%d %s 2>/dev/null" % (seen + 1, log_path), quiet=True)
        if chunk:
            for line in chunk.splitlines():
                if not line.startswith("    ai["):
                    print(line, flush=True)
            seen += len(chunk.encode("utf-8", "replace"))
        if "RESULT:" in chunk or "S4c " in chunk or "S6b " in chunk or "S7B " in chunk:
            break
        alive = run("pgrep -f %s >/dev/null && echo RUNNING || echo DONE" % args.script,
                    quiet=True).strip()
        if "DONE" in alive and not chunk:
            print(run("grep -vE '^ +ai\\[' %s | tail -25" % log_path, quiet=True))
            break
        if time.time() - started > args.timeout:
            print("[client] timeout; the server job keeps running")
            break
        time.sleep(20)

    pulls = [p.strip() for p in args.pull.split(",") if p.strip()]
    if args.reports or pulls:
        print("\n[pull]")
    for rel in pulls:
        local = os.path.join(REPO, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        try:
            sftp.get(posixpath.join(APP, rel), local)
            print("   ", rel)
        except IOError:
            print("    (skip, missing on server)", rel)
    if args.reports:
        arts = os.path.join(HERE, "artifacts")
        os.makedirs(arts, exist_ok=True)
        for folder, pattern in (("out", "%s_*.json" % label), ("reports", "%s_*.json" % label)):
            listing = run("ls %s/%s/%s 2>/dev/null" % (PIPE, folder, pattern), quiet=True)
            for remote in [x.strip() for x in listing.splitlines() if x.strip()]:
                tag = os.path.basename(remote)
                try:
                    sftp.get(remote, os.path.join(arts, "%s__%s" % (folder, tag)))
                    print("    %s/%s" % (folder, tag))
                except IOError:
                    pass
    sftp.close()
    c.close()
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
