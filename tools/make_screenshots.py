"""Regenerate the screenshots of the user manual (docs/images/*.png) from trust-ledger's public `egg` example.

    uv run python tools/make_screenshots.py --trust-ledger ../trust-ledger --playwright DIR [--out docs/images]

Needs node with `playwright-core` (npm i playwright-core in DIR), Google Chrome, ssh-keygen/ssh-agent/ssh-add and, for the
review-pack picture, latexmk + pdflatex. Nothing here touches a real project: everything runs on a scratch copy.
The agent socket lives in a short temporary path (a Unix socket path is limited to about 100 characters)."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(*cmd, **kw):
    return subprocess.run(list(map(str, cmd)), check=True, capture_output=True, text=True, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trust-ledger", default=str(HERE.parent.parent / "trust-ledger"))
    ap.add_argument("--playwright", required=True, help="directory whose node_modules has playwright-core")
    ap.add_argument("--out", default=str(HERE.parent / "docs" / "images"))
    args = ap.parse_args()
    tl, out = Path(args.trust_ledger).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tlui-doc-"))
    procs = []
    try:
        # the egg example refers to ../../tex (texinputs): keep that layout
        proj = work / "examples" / "egg"
        shutil.copytree(tl / "examples" / "egg", proj, ignore=shutil.ignore_patterns("__pycache__", "snapshots"))
        shutil.copytree(tl / "tex", work / "tex")
        # two claims without any attestation, to have "none" rows
        att = proj / "ledger" / "attestations.toml"
        blocks = re.split(r"(?m)^(?=\[\[attestation\]\])", att.read_text())
        att.write_text("".join(b for b in blocks if not re.search(r'(?m)^claim = "(kitchen|taste)"', b)))
        # a paper.toml: title in the paper menu
        (proj / "paper" / "egg").mkdir(exist_ok=True)
        (proj / "paper" / "egg" / "paper.toml").write_text(
            '[paper]\nname = "egg"\nmain = "../main.tex"\ntitle = "How long to boil an egg"\n')
        # two people: jdoe (key loaded in the agent) and ksmith (key not loaded)
        sock = work / "a.sock"
        procs.append(subprocess.Popen(["ssh-agent", "-D", "-a", str(sock)], stdout=subprocess.DEVNULL))
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.1)
        env = dict(os.environ, SSH_AUTH_SOCK=str(sock))
        for kid, person, load in (("jdoe", "J. Doe", True), ("ksmith", "K. Smith", False)):
            run("ssh-keygen", "-t", "ed25519", "-N", "", "-C", kid, "-f", work / kid, "-q")
            run(sys.executable, tl / "ledger.py", "-C", proj, "addkey", kid, "--person", person, "--pub", f"{work / kid}.pub",
                "--source", "paper")
            if load:
                run("ssh-add", work / kid, env=env)
        (work / "ledger-ui.toml").write_text(
            f'[ledger]\nfile = "{proj}/ledger/ledger.toml"\ntool = "{tl}/ledger.py"\n'
            '[signing]\nperson = "J. Doe"\nkey = "jdoe"\nreasons = ["Checked against the paper and the Lean statement"]\n'
            '[metadata]\npaper_toml = "paper/{name}/paper.toml"\n')
        from trust_ledger_ui.core.config import load_config
        from trust_ledger_ui.core.ledgerio import Project
        from trust_ledger_ui.server import App
        os.environ["SSH_AUTH_SOCK"] = str(sock)
        app = App(Project(load_config(work / "ledger-ui.toml")), port=0, token="doctoken")
        threading.Thread(target=app.warm.run, daemon=True).start()
        threading.Thread(target=app.httpd.serve_forever, daemon=True).start()
        node_env = dict(os.environ, NODE_PATH=str(Path(args.playwright).resolve() / "node_modules"))
        r = subprocess.run(["node", str(HERE / "shots.js"), str(out), str(app.port), "doctoken", str(proj)], env=node_env)
        app.shutdown()
        return r.returncode
    finally:
        for p in procs:
            p.terminate()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
