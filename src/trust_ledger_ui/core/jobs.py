"""Background jobs: ledger.py commands that take a while (SPEC.md section 8).

Only a fixed list of commands can be started, with arguments built here from validated names; the browser never sends a
command line or a path. One job per kind at a time, and only one Lean job at all (`extract` starts Docker Lean).
Review packs are written to `<state dir>/packs/<job id>/`, never into the project's own review directory."""
from __future__ import annotations

import os
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .ledgerio import Project

KINDS = {
    "review": "Build a review pack (PDF)",
    "lock": "Write the lock file",
    "verify": "Verify the lock file",
    "check": "Run the [check.*] commands",
    "extract": "Extract the Lean evidence (Docker, minutes)",
}
LEAN_KINDS = {"extract"}           # at most one of these runs at any time
NEEDS_CONFIRM = {"extract"}
NEEDS_PAPER = {"review"}
MAX_LINES = 20000


class JobError(Exception):
    """A problem the person can fix; the message is shown to them."""


class JobManager:
    def __init__(self, project: Project, state_dir: Path, tool: Path | None = None):
        self.project = project
        self.state_dir = Path(state_dir)
        self.tool = Path(tool or project.cfg.tool)
        self._jobs: dict[str, dict] = {}
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    # ---- starting
    def start(self, kind: str, paper: str | None = None, targets: list[str] | None = None, confirm: bool = False) -> str:
        if kind not in KINDS:
            raise JobError(f"unknown job kind {kind!r}")
        if kind in NEEDS_PAPER and not paper:
            raise JobError(f"{kind} needs one paper selected (not 'all papers')")
        if kind in NEEDS_CONFIRM and not confirm:
            raise JobError(f"{kind} must be confirmed")
        targets = list(dict.fromkeys(targets or []))
        bounds: dict[str, str] = {}
        if targets:
            claims = {c["name"]: c for c in self.project.status(paper)["claims"]}
            by_label = {lab: c["name"] for c in claims.values() for lab in c["labels"]}
            bad = [t for t in targets if t not in claims and t not in by_label]
            if bad:
                raise JobError(f"not a claim or label of this ledger: {', '.join(bad)}")
            bounds = {claims[t if t in claims else by_label[t]]["name"]: claims[t if t in claims else by_label[t]]["bound"]
                      for t in targets}
        jid = secrets.token_urlsafe(8)
        argv = [sys.executable, str(self.tool), "-C", str(self.project.root)]
        if paper and kind != "extract":
            argv += ["-P", paper]
        argv.append(kind)
        out_dir = None
        if kind == "review":
            out_dir = self.state_dir / "packs" / jid
            out_dir.mkdir(parents=True, exist_ok=True)
            argv += ["--out", str(out_dir)]
            if targets:
                argv += ["--for", ",".join(targets)]
        job = dict(id=jid, kind=kind, title=KINDS[kind], paper=paper, targets=targets, state="running", returncode=None,
                   started=time.time(), finished=None, lines=[], dropped=0, pack=None)
        with self._lock:
            for j in self._jobs.values():
                if j["state"] == "running" and (j["kind"] == kind or (kind in LEAN_KINDS and j["kind"] in LEAN_KINDS)):
                    raise JobError(f"a {j['kind']} job is already running" if j["kind"] == kind
                                   else "a Lean job is already running; Lean jobs run one at a time")
            self._jobs[jid] = job
        if kind == "review":
            job["pack"] = dict(pdf=str(out_dir / f"{paper}-review.pdf"), bounds=bounds, paper=paper, ready=False)
        try:
            proc = subprocess.Popen(argv, cwd=str(self.project.root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace", bufsize=1, start_new_session=True,
                                    env=dict(os.environ, PYTHONUNBUFFERED="1"))
        except OSError as e:
            with self._lock:
                job.update(state="failed", finished=time.time())
                job["lines"].append(f"could not start: {e}")
            return jid
        self._procs[jid] = proc
        threading.Thread(target=self._watch, args=(job, proc), daemon=True).start()
        return jid

    def _watch(self, job: dict, proc: subprocess.Popen) -> None:
        for line in proc.stdout:
            with self._lock:
                job["lines"].append(line.rstrip("\n"))
                if len(job["lines"]) > MAX_LINES:
                    cut = len(job["lines"]) - MAX_LINES
                    del job["lines"][:cut]
                    job["dropped"] += cut
        rc = proc.wait()
        with self._lock:
            cancelled = job["state"] == "cancelling"
            job.update(returncode=rc, finished=time.time(),
                       state="cancelled" if cancelled else ("done" if rc == 0 else "failed"))
            pack = job.get("pack")
            if pack and rc == 0 and Path(pack["pdf"]).is_file():
                pack["ready"] = True
        self._procs.pop(job["id"], None)

    # ---- reading
    def get(self, jid: str, since: int = 0) -> dict | None:
        with self._lock:
            j = self._jobs.get(jid)
            if not j:
                return None
            start = max(0, since - j["dropped"])
            out = {k: v for k, v in j.items() if k not in ("lines", "dropped")}
            out["pack"] = dict(j["pack"]) if j["pack"] else None
            out["log"] = j["lines"][start:]
            out["next"] = j["dropped"] + len(j["lines"])
            out["elapsed"] = (j["finished"] or time.time()) - j["started"]
            return out

    def list(self) -> list[dict]:
        with self._lock:
            rows = []
            for j in sorted(self._jobs.values(), key=lambda x: -x["started"]):
                rows.append(dict(id=j["id"], kind=j["kind"], title=j["title"], paper=j["paper"], targets=j["targets"],
                                 state=j["state"], returncode=j["returncode"], started=j["started"],
                                 elapsed=(j["finished"] or time.time()) - j["started"],
                                 pack=bool(j["pack"] and j["pack"]["ready"])))
            return rows

    def cancel(self, jid: str) -> None:
        with self._lock:
            j = self._jobs.get(jid)
            if not j:
                raise JobError("unknown job")
            if j["state"] != "running":
                raise JobError("this job is not running")
            j["state"] = "cancelling"
        proc = self._procs.get(jid)
        if proc:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    def pack_pdf(self, jid: str) -> Path | None:
        with self._lock:
            j = self._jobs.get(jid)
            p = j and j["pack"]
            return Path(p["pdf"]) if p and p["ready"] else None

    def running(self) -> int:
        with self._lock:
            return sum(j["state"] in ("running", "cancelling") for j in self._jobs.values())
