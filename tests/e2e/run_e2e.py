"""End-to-end test of the attest dialog in a real browser, on a scratch copy of trust-ledger's egg example with a
private ssh-agent. Not part of `pytest` (it needs node, playwright-core and Google Chrome):

    uv run python tests/e2e/run_e2e.py [--trust-ledger ../trust-ledger] [--playwright DIR_WITH_node_modules]

The agent socket lives in a short temporary path (a Unix socket path is limited to about 100 characters)."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trust-ledger", default=str(HERE.parent.parent.parent / "trust-ledger"))
    ap.add_argument("--playwright", default=str(HERE), help="directory whose node_modules has playwright-core")
    ap.add_argument("--keep", action="store_true", help="keep the scratch directory and print the screenshots' place")
    args = ap.parse_args()
    tl = Path(args.trust_ledger).resolve()
    work = Path(tempfile.mkdtemp(prefix="tlui-"))
    procs = []
    try:
        shutil.copytree(tl / "examples" / "egg", work / "egg", ignore=shutil.ignore_patterns("__pycache__"))
        key = work / "tester"
        subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "tester", "-f", str(key), "-q"], check=True)
        subprocess.run([sys.executable, str(tl / "ledger.py"), "-C", str(work / "egg"), "addkey", "tester", "--person",
                        "T. Ester", "--pub", str(key) + ".pub", "--source", "paper"], check=True, capture_output=True)
        sock = work / "a.sock"
        procs.append(subprocess.Popen(["ssh-agent", "-D", "-a", str(sock)], stdout=subprocess.DEVNULL))
        for _ in range(50):
            if sock.exists():
                break
            time.sleep(0.1)
        env = dict(os.environ, SSH_AUTH_SOCK=str(sock))
        subprocess.run(["ssh-add", str(key)], check=True, capture_output=True, env=env)
        (work / "ledger-ui.toml").write_text(
            f'[ledger]\nfile = "{work}/egg/ledger/ledger.toml"\ntool = "{tl}/ledger.py"\n'
            '[signing]\nperson = "T. Ester"\nkey = "tester"\nreasons = ["Checked against blind backtranslation"]\n')
        from trust_ledger_ui.core.config import load_config
        from trust_ledger_ui.core.ledgerio import Project
        from trust_ledger_ui.server import App
        os.environ["SSH_AUTH_SOCK"] = str(sock)
        import threading
        app = App(Project(load_config(work / "ledger-ui.toml")), port=0, token="e2etoken")
        threading.Thread(target=app.warm.run, daemon=True).start()
        threading.Thread(target=app.httpd.serve_forever, daemon=True).start()
        node_env = dict(os.environ, NODE_PATH=str(Path(args.playwright).resolve() / "node_modules"))
        r = subprocess.run(["node", str(HERE / "attest_flow.js"), str(work), str(app.port), "e2etoken"], env=node_env)
        app.shutdown()
        if args.keep:
            print("scratch directory (screenshots e2e_*.png):", work)
        return r.returncode
    finally:
        for p in procs:
            p.terminate()
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
