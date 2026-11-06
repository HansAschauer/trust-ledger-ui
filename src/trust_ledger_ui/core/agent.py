"""State of the user's ssh-agent. The UI signs only through the agent (SPEC.md section 6.3): it never reads a private key."""
from __future__ import annotations

import re
import shutil
import subprocess
import time

_cache: tuple[float, dict] | None = None


def agent_state(max_age: float = 2.0) -> dict:
    """{"available": bool, "fingerprints": ["SHA256:..."], "message": str}. `available` is False without a socket, without
    ssh-add, or when the agent cannot be reached; an agent without keys is available with no fingerprints."""
    global _cache
    if _cache and time.monotonic() - _cache[0] < max_age:
        return _cache[1]
    if not shutil.which("ssh-add"):
        st = dict(available=False, fingerprints=[], message="ssh-add is not installed")
    else:
        try:
            r = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True, timeout=5)
        except (subprocess.TimeoutExpired, OSError) as e:
            st = dict(available=False, fingerprints=[], message=f"ssh-add failed: {e}")
        else:
            if r.returncode == 0:
                st = dict(available=True, fingerprints=re.findall(r"SHA256:\S+", r.stdout), message="")
            elif r.returncode == 1:                       # "The agent has no identities."
                st = dict(available=True, fingerprints=[], message="the ssh-agent holds no keys")
            else:
                st = dict(available=False, fingerprints=[],
                          message="no ssh-agent reachable (SSH_AUTH_SOCK): start one and `ssh-add` your key")
    _cache = (time.monotonic(), st)
    return st


def forget() -> None:
    global _cache
    _cache = None
