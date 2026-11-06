import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
TOOL = Path(os.environ.get("TRUST_LEDGER", HERE.parent.parent / "trust-ledger"))   # checkout of trust-ledger


@pytest.fixture
def tool() -> Path:
    p = TOOL / "ledger.py"
    if not p.is_file():
        pytest.skip(f"no trust-ledger checkout at {TOOL} (set TRUST_LEDGER)")
    return p


@pytest.fixture
def egg(tmp_path, tool) -> Path:
    """A scratch copy of trust-ledger's egg example (it ships attestations and keys)."""
    dst = tmp_path / "egg"
    shutil.copytree(TOOL / "examples" / "egg", dst, ignore=shutil.ignore_patterns("__pycache__"))
    return dst


@pytest.fixture
def config_file(tmp_path, egg, tool) -> Path:
    p = tmp_path / "ledger-ui.toml"
    p.write_text(f'[ledger]\nfile = "{egg}/ledger/ledger.toml"\ntool = "{tool}"\n'
                 '[signing]\nperson = "Test"\nkey = "test"\n')
    return p


def ledger_cli(tool: Path, root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(tool), "-C", str(root), *args], capture_output=True, text=True)


@pytest.fixture
def signing(tmp_path, egg, tool, monkeypatch):
    """A key registered in the egg ledger as `tester`, and a private ssh-agent (not yet holding it)."""
    if not (shutil.which("ssh-keygen") and shutil.which("ssh-agent") and shutil.which("ssh-add")):
        pytest.skip("needs ssh-keygen, ssh-agent, ssh-add")
    key = tmp_path / "tester"
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", "tester", "-f", str(key), "-q"], check=True)
    r = ledger_cli(tool, egg, "addkey", "tester", "--person", "T. Ester", "--pub", str(key) + ".pub", "--source", "paper")
    assert r.returncode == 0, r.stderr
    sock = tmp_path / "agent.sock"
    proc = subprocess.Popen(["ssh-agent", "-D", "-a", str(sock)], stdout=subprocess.DEVNULL)
    import time
    for _ in range(50):
        if sock.exists():
            break
        time.sleep(0.1)
    monkeypatch.setenv("SSH_AUTH_SOCK", str(sock))
    from trust_ledger_ui.core import agent
    agent.forget()

    class S:
        pass
    s = S()
    s.key, s.id, s.sock = key, "tester", sock
    s.load = lambda: (subprocess.run(["ssh-add", str(key)], check=True, capture_output=True), agent.forget())
    yield s
    proc.terminate()
    proc.wait()
    agent.forget()
