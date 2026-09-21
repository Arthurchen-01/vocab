# -*- coding: utf-8 -*-
"""Deploy the app itself (not just the data), with a backup and a verification.

`deliver.py`'s S7 can restart the service, and `deliver_client.py` pulls data
back, but nothing in the toolkit ever pushed application code to the host: the
live server.py was three commits behind the repository, which is exactly how the
"export collection is nothing" fix stayed un-deployed while the source looked
correct.

    python tools/quality_pipeline/deploy_app.py --dry-run
    python tools/quality_pipeline/deploy_app.py
    python tools/quality_pipeline/deploy_app.py --files server.py --no-restart

Every upload is preceded by a timestamped backup on the host and followed by a
sha256 comparison plus live probes, so a bad push is both visible and reversible.
"""
import argparse
import hashlib
import os
import posixpath
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = "/var/www/harvard_justice_app"
BACKUP_ROOT = "/root/deploy_backup"

# Never let console encoding decide whether a deploy succeeds.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
DEFAULT_FILES = ["server.py", "docx_generator.py", "public/index.html"]
PROBES = ["/api/health", "/api/preset/ep01", "/api/preset/ep02", "/api/preset/ep03",
          "/api/vocab-bank", "/api/collections", "/api/collection/harvard_justice"]


def credentials():
    import json
    host = os.environ.get("VOCAB_SSH_HOST", "")
    user = os.environ.get("VOCAB_SSH_USER", "root")
    pwd = os.environ.get("VOCAB_SSH_PASSWORD", "")
    path = os.path.join(os.path.expanduser("~"), ".vocab_deploy.json")
    if not (host and pwd) and os.path.isfile(path):
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        host = host or cfg.get("host", "")
        user = cfg.get("user", user)
        pwd = pwd or cfg.get("password", "")
    if not host or not pwd:
        sys.exit("missing SSH credentials: set VOCAB_SSH_HOST/USER/PASSWORD or create "
                 "~/.vocab_deploy.json")
    return host, user, pwd


def local_sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def connect_with_retry(host, user, pwd, attempts=5):
    """The host drops connections fairly often (timeouts, EOFError, WinError
    10054), so every client retries instead of failing the whole delivery."""
    import paramiko
    last = None
    for attempt in range(attempts):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, 22, user, pwd, timeout=30, banner_timeout=30,
                      auth_timeout=30)
            return c
        except Exception as exc:  # noqa: BLE001
            last = exc
            print("   [ssh] attempt %d/%d failed: %s"
                  % (attempt + 1, attempts, type(exc).__name__))
            time.sleep(8)
    sys.exit("cannot reach %s: %s" % (host, last))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--files", default=",".join(DEFAULT_FILES))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--origin", default="http://127.0.0.1:8765")
    args = ap.parse_args()

    try:
        import paramiko
    except ImportError:
        sys.exit("pip install paramiko")

    files = [f.strip() for f in args.files.split(",") if f.strip()]
    expanded = []
    for f in files:
        local = os.path.join(REPO, f.replace("/", os.sep))
        if os.path.isdir(local):
            # A directory argument means "deploy this package": list its files so
            # `--files providers` works instead of naming every module.
            for root, _dirs, names in os.walk(local):
                for name in sorted(names):
                    if name.endswith((".pyc",)):
                        continue
                    rel = os.path.relpath(os.path.join(root, name), REPO)
                    expanded.append(rel.replace(os.sep, "/"))
        else:
            expanded.append(f)
    files = expanded
    for f in files:
        if not os.path.isfile(os.path.join(REPO, f.replace("/", os.sep))):
            sys.exit("not in the repo: %s" % f)

    host, user, pwd = credentials()
    state = {"client": connect_with_retry(host, user, pwd)}

    def run(cmd, timeout=300, quiet=False, attempts=4):
        """Run a remote command, reconnecting when the channel drops.

        This host resets SSH sessions mid-deploy (EOFError / WinError 10054), so
        a single connection cannot be trusted for a whole deployment.
        """
        last = None
        for attempt in range(attempts):
            try:
                _i, o, e = state["client"].exec_command(cmd, timeout=timeout)
                out = (o.read() + e.read()).decode("utf-8", "replace")
                if not quiet:
                    sys.stdout.write(out)
                    sys.stdout.flush()
                return out
            except Exception as exc:  # noqa: BLE001
                last = exc
                print("   [ssh] command failed (%s), reconnecting"
                      % type(exc).__name__)
                time.sleep(6)
                try:
                    state["client"].close()
                except Exception:  # noqa: BLE001
                    pass
                state["client"] = connect_with_retry(host, user, pwd)
        print("   [ssh] giving up on: %s" % cmd[:60])
        return "(failed: %s)" % type(last).__name__

    def sftp_put(local, remote, attempts=4):
        last = None
        for attempt in range(attempts):
            try:
                sftp = state["client"].open_sftp()
                try:
                    sftp.put(local, remote)
                finally:
                    sftp.close()
                return True
            except Exception as exc:  # noqa: BLE001
                last = exc
                print("   [sftp] %s failed (%s), reconnecting"
                      % (os.path.basename(local), type(exc).__name__))
                time.sleep(6)
                try:
                    state["client"].close()
                except Exception:  # noqa: BLE001
                    pass
                state["client"] = connect_with_retry(host, user, pwd)
        print("   [sftp] giving up on %s: %s" % (local, last))
        return False

    print("[compare] local vs deployed")
    changed = []
    for f in files:
        lp = os.path.join(REPO, f.replace("/", os.sep))
        lh = local_sha(lp)
        rh = run("sha256sum %s 2>/dev/null | cut -d' ' -f1" % posixpath.join(APP, f),
                 quiet=True).strip()
        same = lh == rh
        if not same:
            changed.append(f)
        print("   %-24s %s" % (f, "identical" if same else "CHANGED (%s -> %s)"
                               % (rh[:10] or "absent", lh[:10])))
    if not changed:
        print("\nnothing to deploy.")
        state["client"].close()
        return 0
    if args.dry_run:
        print("\n[dry run] would upload %d file(s) and restart" % len(changed))
        state["client"].close()
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run("mkdir -p %s/%s" % (BACKUP_ROOT, stamp), quiet=True)
    for f in changed:
        run("cd %s && cp --parents %s %s/%s/ 2>/dev/null || true"
            % (APP, f, BACKUP_ROOT, stamp), quiet=True)
    print("\n[backup] %s/%s" % (BACKUP_ROOT, stamp))

    print("[upload]")
    upload_failed = []
    for f in changed:
        remote = posixpath.join(APP, f)
        run("mkdir -p %s" % posixpath.dirname(remote), quiet=True)
        if sftp_put(os.path.join(REPO, f.replace("/", os.sep)), remote):
            print("    %s" % f)
        else:
            upload_failed.append(f)
    if upload_failed:
        sys.exit("upload failed for: %s" % upload_failed)

    print("\n[verify upload]")
    ok = True
    for f in changed:
        lh = local_sha(os.path.join(REPO, f.replace("/", os.sep)))
        rh = run("sha256sum %s | cut -d' ' -f1" % posixpath.join(APP, f), quiet=True).strip()
        good = lh == rh
        ok = ok and good
        print("    %-24s %s" % (f, "ok" if good else "MISMATCH"))
    if not ok:
        sys.exit("upload verification failed; nothing was restarted")

    if args.no_restart:
        print("\n[restart] skipped (--no-restart); the service still runs the old code")
        state["client"].close()
        return 0

    print("\n[restart]")
    run("systemctl restart vocab_app && sleep 3 && systemctl is-active vocab_app")
    print(run("systemctl show vocab_app -p NRestarts -p ExecMainStartTimestamp"))
    print(run("journalctl -u vocab_app -n 12 --no-pager | tail -12"))

    print("\n[live probes]")
    for path in PROBES:
        code = run("curl -s -o /dev/null -w '%%{http_code}' %s%s" % (args.origin, path),
                   quiet=True).strip()
        print("    %-34s %s" % (path, code))
    state["client"].close()
    print("\ndone. Roll back with: cp -r %s/%s/* %s/" % (BACKUP_ROOT, stamp, APP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
