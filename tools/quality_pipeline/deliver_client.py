# -*- coding: utf-8 -*-
"""Windows-side client: paste a link, get a verified episode.

    python tools/quality_pipeline/deliver_client.py --url "https://youtu.be/Qw4l1w0rkjs"
    python tools/quality_pipeline/deliver_client.py --episode ep05 --url "..." --commit

What it does, with no manual steps in between:
  1. uploads the pipeline scripts so the server always runs the current version;
  2. launches `deliver.py` on the server as a detached job and follows its log;
  3. pulls the produced data files, gate reports and the acceptance report back;
  4. optionally commits and pushes them (`--commit`).

Credentials are NEVER stored in the repository. Provide them via environment
variables or an untracked file:

    $env:VOCAB_SSH_HOST / VOCAB_SSH_USER / VOCAB_SSH_PASSWORD
    or  %USERPROFILE%\\.vocab_deploy.json  -> {"host":..., "user":..., "password":...}
"""
import argparse
import getpass
import json
import os
import posixpath
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
APP = "/var/www/harvard_justice_app"
PIPE = "/root/quality_pipeline"

# Upload every stage module in this directory rather than a hand-kept list: the
# list used to omit s0b_build_deck.py, so a fresh episode silently ran whatever
# copy happened to be on the host (or failed outright).
CLIENT_ONLY = {"deliver_client.py", "stage_client.py", "run_all.py"}
SCRIPTS = sorted(f for f in os.listdir(HERE)
                 if f.endswith(".py") and f not in CLIENT_ONLY
                 and os.path.isfile(os.path.join(HERE, f)))
REPORT_NAME = {"s0": "acquire", "s1": "sentences", "s0b": "deck", "s2": "word_map",
               "s3": "media", "s4": "translation", "s4b": "deck_translations",
               "s4c": "english_definitions", "s5": "apply_verify",
               "s6": "bank_sync", "s6b": "bank_def_en", "s7": "deploy",
               "s7b": "export"}


def credentials():
    host = os.environ.get("VOCAB_SSH_HOST", "")
    user = os.environ.get("VOCAB_SSH_USER", "root")
    pwd = os.environ.get("VOCAB_SSH_PASSWORD", "")
    if not (host and pwd):
        path = os.path.join(os.path.expanduser("~"), ".vocab_deploy.json")
        if os.path.isfile(path):
            # utf-8-sig: PowerShell's `Set-Content -Encoding UTF8` and Notepad
            # both write a BOM, which plain utf-8 decoding rejects.
            with open(path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
            host = host or cfg.get("host", "")
            user = cfg.get("user", user)
            pwd = pwd or cfg.get("password", "")
    if not host or not pwd:
        sys.exit("missing SSH credentials: set VOCAB_SSH_HOST/USER/PASSWORD or create "
                 "~/.vocab_deploy.json ({\"host\":..,\"user\":..,\"password\":..})")
    return host, user, pwd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--episode", default="")
    ap.add_argument("--from", dest="from_stage", default="s0")
    ap.add_argument("--commit", action="store_true", help="git add/commit/push the pulled data")
    ap.add_argument("--no-pull", action="store_true")
    ap.add_argument("--poll", type=int, default=30, help="log poll interval (s)")
    args = ap.parse_args()
    if not args.url and not args.episode:
        sys.exit("need --url and/or --episode")

    try:
        import paramiko
    except ImportError:
        sys.exit("pip install paramiko")

    host, user, pwd = credentials()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, 22, user, pwd, timeout=30)
    sftp = c.open_sftp()

    def run(cmd, timeout=600, quiet=False):
        _i, o, e = c.exec_command(cmd, timeout=timeout)
        try:
            out = (o.read() + e.read()).decode("utf-8", "replace")
        except Exception as ex:  # channel timeout on detached jobs
            out = f"(channel closed: {type(ex).__name__})"
        if not quiet:
            print(out.rstrip())
        return out

    print("=" * 78)
    print(f"VERBALEX DELIVERY  url={args.url or '-'}  episode={args.episode or '(from url)'}")
    print("=" * 78)

    print("\n[1/4] uploading pipeline scripts ...")
    for f in SCRIPTS:
        sftp.put(os.path.join(HERE, f), posixpath.join(PIPE, f))
    run(f"mkdir -p {PIPE}/logs {PIPE}/out {PIPE}/reports", quiet=True)
    print(f"      {len(SCRIPTS)} scripts -> {PIPE}")

    ep_guess = args.episode or "auto"
    log = f"{PIPE}/logs/deliver_{ep_guess}.log"
    cmd = (f"cd {PIPE} && VOCAB_APP_DIR={APP} VOCAB_WORK_DIR={PIPE} "
           f"setsid nohup python3 -u deliver.py "
           f"{'--episode ' + args.episode if args.episode else ''} "
           f"{'--url ' + json.dumps(args.url) if args.url else ''} "
           f"--from {args.from_stage} --write "
           f"{'--commit ' if False else ''} "
           f"> {log} 2>&1 < /dev/null & echo LAUNCHED")
    print("\n[2/4] launching on the server ...")
    run(cmd)
    time.sleep(5)

    print("\n[3/4] following the log (Ctrl-C is safe: the server job keeps running)\n")
    seen = 0
    last = time.time()
    try:
        while True:
            out = run(f"tail -c +{seen + 1} {log}", quiet=True)
            if out.strip():
                sys.stdout.write(out)
                sys.stdout.flush()
                seen += len(out.encode("utf-8", "replace"))
            if "RESULT:" in out or "INCOMPLETE" in out:
                break
            if time.time() - last > 7200:
                print("\n[client] giving up after 2h of following; the server job continues.")
                break
            if not out.strip():
                alive = run("pgrep -f 'deliver.py' >/dev/null && echo RUNNING || echo DONE", quiet=True).strip()
                if "DONE" in alive:
                    out = run(f"tail -c +{seen + 1} {log}", quiet=True)
                    sys.stdout.write(out)
                    break
            time.sleep(args.poll)
    except KeyboardInterrupt:
        print("\n[client] detached. The server keeps working; check " + log)

    if args.no_pull:
        return 0

    print("\n[4/4] pulling data + reports back into the repo ...")
    pulls = ["data/curriculum_tiered.json", "data/vocab_bank.json", "data/source_catalog.json"]
    if args.episode:
        pulls.append(f"data/{args.episode}_curriculum_final_audited.json")
    for rel in pulls:
        remote = posixpath.join(APP, rel)
        local = os.path.join(REPO, rel.replace("/", os.sep))
        try:
            sftp.get(remote, local)
            print(f"      {rel}")
        except IOError:
            print(f"      (skip, not on server) {rel}")

    os.makedirs(os.path.join(REPO, "tools", "quality_pipeline", "artifacts"), exist_ok=True)
    for key, name in REPORT_NAME.items():
        for folder in ("out", "reports"):
            remote = posixpath.join(PIPE, folder, f"{args.episode or 'ep03'}_{key}_{name}.json"
                                    if folder == "reports" else f"{args.episode or 'ep03'}_{name}.json")
            tag = f"report_{args.episode or ''}_{key}_{name}.json" if folder == "reports" else \
                  f"{args.episode or ''}_{name}.json"
            try:
                sftp.get(remote, os.path.join(REPO, "tools", "quality_pipeline", "artifacts", tag))
            except IOError:
                continue
    report = posixpath.join(PIPE, "out", f"{args.episode or 'ep03'}_delivery.md")
    try:
        sftp.get(report, os.path.join(REPO, "docs", f"{args.episode or 'ep03'}_DELIVERY_REPORT.md"))
        print(f"      docs/{args.episode or 'ep03'}_DELIVERY_REPORT.md")
    except IOError:
        pass

    if args.commit:
        print("\n[git] committing the delivered data ...")
        subprocess.run(["git", "-C", REPO, "add", "-A",
                        "data", "docs", "tools/quality_pipeline"], check=False)
        msg = f"feat({args.episode or 'episode'}): deliver rebuilt episode via quality pipeline"
        subprocess.run(["git", "-C", REPO, "-c", "core.safecrlf=false", "commit", "-q", "-m", msg], check=False)
        subprocess.run(["git", "-C", REPO, "push", "origin", "main"], check=False)
    sftp.close()
    c.close()
    print("\ndone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
