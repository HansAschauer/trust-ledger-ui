"""Attesting claims and hypotheses (SPEC.md section 6): preview, signing job, undo.

One signature per attestation, made by `ssh-keygen -Y sign` through ssh-agent (ledger.py's `sign_attestation`); this
module never sees a private key. A batch is a list of targets with one level, one reason, one checklist and one key.
The browser cannot change what is signed after the preview: it sends only the preview's id."""
from __future__ import annotations

import json
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import agent
from .ledgerio import Project, ToolError

PREVIEW_TTL = 20 * 60          # seconds a preview can still be executed


class AttestError(Exception):
    """A problem the person can fix; the message is shown to them."""


@dataclass
class Preview:
    id: str
    paper: str | None
    kind: str                  # "claim" | "hypothesis"
    level: str
    reason: str
    checklist: list[str]
    key: str
    person: str
    items: list[dict]          # {target, ok, problem, bound, current}
    created: float = field(default_factory=time.monotonic)


class Attestor:
    def __init__(self, project: Project, log_path: Path | None = None):
        self.project = project
        self.log_path = log_path
        self._previews: dict[str, Preview] = {}
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._running: str | None = None
        self.last_batch: dict | None = None        # for undo: {"path", "text" (bytes), "targets"}

    # ---- what the dialog offers
    def options(self, paper: str | None) -> dict:
        e = self.project.load(paper)
        L = e["L"]
        ag = agent.agent_state()
        keys = []
        for kid, k in sorted(L.keys.items()):
            pub = k.get("public", "")
            fp = self.project.tool.fingerprint(pub) if pub else ""
            keys.append(dict(id=kid, person=k.get("person", ""), fingerprint=fp, in_agent=fp in ag["fingerprints"]))
        default = self.project.cfg.key if any(k["id"] == self.project.cfg.key for k in keys) else (keys[0]["id"] if keys else "")
        recent, seen = [], set()
        for a in reversed(L.attestations):
            r = (a.get("reason") or "").strip()
            if r and r not in seen:
                seen.add(r)
                recent.append(r)
        return dict(keys=keys, default_key=default, levels=list(self.project.tool.LEVELS),
                    checklist={k: dict(text=v.get("text", ""), applies=v.get("applies", "claim")) for k, v in L.checklist.items()},
                    reasons=list(self.project.cfg.reasons), recent_reasons=recent[:8], agent=ag)

    # ---- preview
    def preview(self, paper: str | None, kind: str, targets: list[str], level: str, reason: str,
                checklist: list[str], key: str) -> dict:
        if kind not in ("claim", "hypothesis"):
            raise AttestError("kind must be claim or hypothesis")
        targets = list(dict.fromkeys(targets))
        if not targets:
            raise AttestError("nothing selected")
        L = self.project.load(paper)["L"]
        try:
            pub = L.key_public(key)
        except self.project.tool.LedgerError as e:
            raise AttestError(str(e)) from e
        person = (L.keys.get(key) or {}).get("person") or self.project.cfg.person
        if not person:
            raise AttestError(f"key {key!r} has no person in ledger/keys.toml")
        items = []
        for t in targets:
            try:
                rec = L.make_attestation(person, level, **{kind: t}, reason=reason, checklist=checklist)
                cur = L.attestation_state(t) if kind == "claim" else L.hypothesis_state(t)
                items.append(dict(target=t, ok=True, problem="", bound=rec["bound"],
                                  current=[dict(person=p, level=lv, date=d, current=c) for p, lv, d, c in cur]))
            except self.project.tool.LedgerError as e:
                items.append(dict(target=t, ok=False, problem=str(e), bound="", current=[]))
        ag = agent.agent_state(max_age=0)
        fp = self.project.tool.fingerprint(pub)
        pv = Preview(secrets.token_urlsafe(16), paper, kind, level, reason, list(checklist), key, person, items)
        with self._lock:
            self._previews = {i: p for i, p in self._previews.items() if time.monotonic() - p.created < PREVIEW_TTL}
            self._previews[pv.id] = pv
        return dict(id=pv.id, kind=kind, level=level, reason=reason, checklist=list(checklist), key=key, person=person,
                    items=items, agent=ag, key_in_agent=fp in ag["fingerprints"], fingerprint=fp,
                    signatures=sum(i["ok"] for i in items))

    # ---- execution
    def start(self, preview_id: str) -> str:
        with self._lock:
            pv = self._previews.pop(preview_id, None)
            if pv is None or time.monotonic() - pv.created > PREVIEW_TTL:
                raise AttestError("this preview is unknown or expired; review the batch again")
            if self._running:
                self._previews[preview_id] = pv
                raise AttestError("another batch is still being signed")
            if not any(i["ok"] for i in pv.items):
                raise AttestError("nothing to sign: every target has a problem")
            job = dict(id=secrets.token_urlsafe(8), state="running", message="", kind=pv.kind, level=pv.level,
                       key=pv.key, person=pv.person,
                       results=[dict(target=i["target"], status="pending" if i["ok"] else "failed", message=i["problem"])
                                for i in pv.items])
            self._jobs[job["id"]] = job
            self._running = job["id"]
        threading.Thread(target=self._run, args=(job, pv), daemon=True).start()
        return job["id"]

    def job(self, job_id: str) -> dict | None:
        with self._lock:
            j = self._jobs.get(job_id)
            return json.loads(json.dumps(j)) if j else None

    def _set(self, job, **kw):
        with self._lock:
            job.update(kw)

    def _result(self, job, i, status, message=""):
        with self._lock:
            job["results"][i].update(status=status, message=message)

    def _run(self, job: dict, pv: Preview) -> None:
        tool = self.project.tool
        try:
            L = self.project.load(pv.paper)["L"]          # reloads if a file changed since the preview
            pub = L.key_public(pv.key)
            fp = tool.fingerprint(pub)
            ag = agent.agent_state(max_age=0)
            if not ag["available"]:
                raise AttestError(ag["message"])
            if fp not in ag["fingerprints"]:
                raise AttestError(f"the key {pv.key!r} ({fp}) is not loaded in your ssh-agent: run `ssh-add` for it, then try again")
            appended = []
            with tempfile.TemporaryDirectory() as d:
                keyfile = Path(d) / "key.pub"
                keyfile.write_text(pub + "\n")
                for i, item in enumerate(pv.items):
                    if not item["ok"]:
                        continue
                    t = item["target"]
                    spec = L.cspec.get(t) if pv.kind == "claim" else L.hspec.get(t)
                    if spec != item["bound"]:
                        self._result(job, i, "skipped", "its statement or evidence changed since the preview")
                        self._log(job, pv, t, "skipped", item["bound"])
                        continue
                    self._result(job, i, "signing", "waiting for the ssh-agent")
                    try:
                        rec = L.make_attestation(pv.person, pv.level, **{pv.kind: t}, reason=pv.reason, checklist=pv.checklist)
                        L.sign_attestation(rec, pv.key, keyfile)
                        text = (tool.toml_record("[[attestation]]", rec)).encode("utf-8")
                        path = L.append_attestation(rec)
                        appended.append((path, text))
                        self._result(job, i, "attested", f"{pv.level}, bound to {rec['bound'][:12]}")
                        self._log(job, pv, t, "attested", rec["bound"])
                    except tool.LedgerError as e:
                        self._result(job, i, "failed", str(e))
                        self._log(job, pv, t, "failed", item["bound"], str(e))
            if appended:
                self.last_batch = dict(path=appended[-1][0], text=b"".join(t for _, t in appended),
                                       targets=[r["target"] for r in job["results"] if r["status"] == "attested"])
            self._set(job, state="done")
        except (AttestError, ToolError, tool.LedgerError) as e:
            self._set(job, state="failed", message=str(e))
        except Exception as e:                            # a bug must not leave the dialog waiting forever
            self._set(job, state="failed", message=f"{type(e).__name__}: {e}")
        finally:
            with self._lock:
                self._running = None

    # ---- undo
    def undo(self) -> dict:
        lb = self.last_batch
        if not lb:
            raise AttestError("nothing to undo")
        import fcntl
        with open(lb["path"], "r+b") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            data = f.read()
            if not data.endswith(lb["text"]):
                raise AttestError("attestations.toml has changed since that batch; remove its records by hand")
            f.truncate(len(data) - len(lb["text"]))
        self.last_batch = None
        self._log_line(dict(event="undo", targets=lb["targets"]))
        return dict(removed=lb["targets"])

    # ---- the session log (next to the config file)
    def _log(self, job, pv, target, status, bound, message=""):
        self._log_line(dict(event=status, kind=pv.kind, target=target, level=pv.level, key=pv.key, person=pv.person,
                            bound=bound, message=message, job=job["id"]))

    def _log_line(self, rec: dict) -> None:
        if not self.log_path:
            return
        rec = dict(time=time.strftime("%Y-%m-%dT%H:%M:%S%z"), **rec)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
