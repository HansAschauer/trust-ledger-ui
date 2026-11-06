"""The only module that touches ledger.py: loads it as a module and turns its `status_data()` into view models.

If ledger.py's API changes, this is the place to adapt. The tool version is checked here (SPEC.md section 2)."""
from __future__ import annotations

import importlib.util
import threading
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .config import Config

SUPPORTED_FORMATS = ("0.3.0",)          # ledger formats this UI has been tested against
REQUIRED_API = ("Ledger", "LedgerError", "LEVELS", "FORMAT_VERSION", "__version__")


class ToolError(Exception):
    pass


def load_tool(path: Path):
    """Import ledger.py from `path` (not as `ledger`, so a project's own module of that name is not shadowed)."""
    spec = importlib.util.spec_from_file_location("trust_ledger_tool", path)
    if spec is None or spec.loader is None:
        raise ToolError(f"{path}: cannot be loaded as a Python module")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # a broken or incompatible ledger.py
        raise ToolError(f"{path}: {type(e).__name__}: {e}") from e
    missing = [n for n in REQUIRED_API if not hasattr(mod, n)]
    if missing or not hasattr(mod.Ledger, "status_data"):
        raise ToolError(f"{path} (trust-ledger {getattr(mod, '__version__', '?')}) lacks the library API this UI "
                        f"needs ({', '.join(missing + ([] if hasattr(mod.Ledger, 'status_data') else ['Ledger.status_data']))}); "
                        "use a ledger.py with `status --json` / status_data (trust-ledger after 2026-11-06)")
    if mod.FORMAT_VERSION not in SUPPORTED_FORMATS:
        raise ToolError(f"{path}: ledger format {mod.FORMAT_VERSION}; this UI supports {', '.join(SUPPORTED_FORMATS)}")
    return mod


def attention(claim: dict) -> str:
    """`none` (no attestation), `stale` (attested, but no attestation is current) or `ok`."""
    att = claim["attestations"]
    if not att:
        return "none"
    return "ok" if any(a["current"] for a in att) else "stale"


@dataclass
class PaperInfo:
    name: str
    main: str | None
    texinputs: list[str]


class Project:
    """One ledger project: the configured ledger.toml, read through ledger.py.

    Loading a ledger takes seconds (it parses the papers), so each scope (one paper, or everything) is loaded once
    and kept; `stamp()` changes when a file the ledger reads has changed, and the next request reloads."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.tool = load_tool(cfg.tool)
        self._cache: dict[str, dict] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def root(self) -> Path:
        return self.cfg.root

    def _raw(self) -> dict:
        return tomllib.loads(self.cfg.ledger_file.read_text())

    def papers(self) -> list[PaperInfo]:
        return [PaperInfo(n, (p or {}).get("main"), list((p or {}).get("texinputs", [])))
                for n, p in self._raw().get("paper", {}).items()]

    def paper(self, name: str) -> PaperInfo:
        for p in self.papers():
            if p.name == name:
                return p
        raise KeyError(name)

    def paper_dir(self, name: str) -> Path | None:
        p = self.paper(name)
        return (self.root / p.main).parent if p.main else None

    def main_tex(self, name: str) -> Path | None:
        p = self.paper(name)
        return self.root / p.main if p.main else None

    def stamp(self, paper: str | None = None) -> tuple:
        """Modification times of the files a ledger of this scope reads: everything in ledger/, the .tex files of the
        papers' directories and texinputs, and the review templates' directories."""
        raw = self._raw()
        dirs = [self.root / "ledger"]
        for n, p in raw.get("paper", {}).items():
            if paper and n != paper:
                continue
            if p and p.get("main"):
                dirs.append((self.root / p["main"]).parent)
            dirs += [self.root / t for t in (p or {}).get("texinputs", [])]
        for t in raw.get("review", {}).values():
            if isinstance(t, str) and "{claim}" in t:
                dirs.append((self.root / t).parent)
        seen, out = set(), []
        for d in dirs:
            if not d.is_dir() or d in seen:
                continue
            seen.add(d)
            pats = ("*.toml", "*.json") if d.name == "ledger" else ("*.tex", "*.lean")
            for pat in pats:
                for f in (d.rglob(pat) if d.name != "ledger" and pat == "*.tex" and d != self.root else d.glob(pat)):
                    if "build" in f.parts or "_attic" in f.parts:
                        continue
                    try:
                        out.append((str(f), f.stat().st_mtime_ns))
                    except OSError:
                        pass
        return tuple(sorted(out))

    def _lock(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def load(self, paper: str | None = None, *, force: bool = False) -> dict:
        """The cache entry of a scope: {"L": Ledger, "data": status data, "stamp": ...}; reloaded when stale."""
        key = paper or ""
        with self._lock(key):
            e = self._cache.get(key)
            stamp = self.stamp(paper)
            if e is None or force or e["stamp"] != stamp:
                try:
                    L = self.tool.Ledger(self.root, paper)
                except self.tool.LedgerError as ex:
                    raise ToolError(str(ex)) from ex
                d = L.status_data()
                for c in d["claims"]:
                    c["attention"] = attention(c)
                d["counts"] = counts(d)
                d["unsnapshotted"] = unsnapshotted(L, d)
                d["stale_unsnapshotted"] = unsnapshotted(L, d, stale=True)
                e = self._cache[key] = dict(L=L, data=d, stamp=stamp)
            return e

    def status(self, paper: str | None = None) -> dict:
        """`status_data()` of the ledger (of one paper's scope, or of everything), with `attention` added to each
        claim and the counts the paper overview needs."""
        return self.load(paper)["data"]

    def changed(self, paper: str | None = None) -> bool:
        """True if files changed on disk since the scope was loaded (False if it was never loaded)."""
        e = self._cache.get(paper or "")
        return bool(e) and e["stamp"] != self.stamp(paper)

    def diff(self, paper: str | None, kind: str, name: str) -> dict:
        """What changed since the latest attestation that has a snapshot (ledger.py `diff_since`)."""
        L = self.load(paper)["L"]
        try:
            return L.diff_since(**{kind: name})
        except self.tool.LedgerError as ex:
            raise KeyError(name) from ex

    def record_snapshots(self, paper: str | None) -> list[str]:
        L = self.load(paper)["L"]
        done = L.record_snapshots()
        self._cache.pop(paper or "", None)                    # the data says which targets lack a snapshot
        return done

    def audit_assessments(self, paper: str | None) -> list[dict]:
        """`ledger.py assess --audit`: for unbound assessments, what changed since they were written (from git). Takes seconds,
        so it is kept until a file the ledger reads changes."""
        e = self.load(paper)
        if e.get("audit_stamp") != e["stamp"]:
            try:
                e["audit"] = e["L"].audit_assessments()
            except self.tool.LedgerError as ex:
                e["audit"] = [dict(claim="", state="no git", note=str(ex))]
            e["audit_stamp"] = e["stamp"]
        return e["audit"]

    def recover_snapshots(self, paper: str | None, partial: bool = False, dry_run: bool = False) -> list[dict]:
        """Rebuild the snapshots of stale attestations from the project's git history (ledger.py `snapshot --from-git`)."""
        L = self.load(paper)["L"]
        try:
            res = L.recover_snapshots(partial=partial, dry_run=dry_run)
        except self.tool.LedgerError as ex:
            raise ToolError(str(ex)) from ex
        if not dry_run:
            self._cache.pop(paper or "", None)
        return res

    def hypothesis_detail(self, paper: str | None, name: str) -> dict:
        e = self.load(paper)
        try:
            return e["L"].hypothesis_detail(name)
        except self.tool.LedgerError as ex:
            raise KeyError(name) from ex

    def detail(self, paper: str | None, claim: str) -> dict:
        e = self.load(paper)
        try:
            return e["L"].claim_detail(claim)
        except self.tool.LedgerError as ex:
            raise KeyError(claim) from ex


def unsnapshotted(L, d: dict, stale: bool = False) -> list[str]:
    """Targets with an attestation but no snapshot of what it bound to. Current ones can still be recorded (a later change could
    then be shown as a diff); stale ones (stale=True) only by rebuilding from git history."""
    def lacks(x):
        atts = x["attestations"]
        hit = any(a["current"] for a in atts) if not stale else (bool(atts) and not any(a["current"] for a in atts))
        return bool(x["bound"]) and hit and (not L.snapshot_path(x["bound"]).exists() if not stale else
                                              not any(L.snapshot_path(b).exists() for b in {a.get("bound") for a in L.attestations
                                                                                           if a.get("claim") == x["name"] or a.get("hypothesis") == x["name"]}))
    return [c["name"] for c in d["claims"] if lacks(c)] + ["hypothesis " + h["name"] for h in d["hypotheses"] if lacks(h)]


def counts(d: dict) -> dict:
    """Per scope: how many claims need attention, by kind (the paper overview)."""
    cl = d["claims"]
    levels = {"green": 0, "yellow": 0, "conjecture": 0}
    for c in cl:
        cur = [a["level"] for a in c["attestations"] if a["current"]]
        if cur:
            levels[cur[0]] += 1                  # attestations are per person; one person today
    return dict(claims=len(cl), none=sum(c["attention"] == "none" for c in cl),
                stale=sum(c["attention"] == "stale" for c in cl), **levels,
                hypotheses=len(d["hypotheses"]),
                hypotheses_open=sum(not h["known_theorem"] for h in d["hypotheses"]),
                uncovered=len(d["uncovered"]))
