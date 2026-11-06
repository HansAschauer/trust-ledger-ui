"""ledger-ui.toml (SPEC.md section 3). Unknown keys are an error: a typo must not be silent."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "ledger-ui.toml"

KNOWN = {
    "ledger": {"file", "tool"},
    "signing": {"person", "key", "reasons"},
    "metadata": {"paper_toml"},
    "viewer": {"pdf"},
    "server": {"port", "open_browser"},
}


class ConfigError(Exception):
    pass


@dataclass
class Config:
    path: Path                                   # the config file (paths in it are relative to its directory)
    ledger_file: Path                            # .../ledger/ledger.toml
    tool: Path                                   # ledger.py, imported as a module
    person: str = ""
    key: str = ""
    reasons: list[str] = field(default_factory=list)
    paper_toml: str | None = None                # pattern with {name}, relative to the project root
    pdf_viewer: str = "embed"
    port: int = 0
    open_browser: bool = True

    @property
    def root(self) -> Path:
        """The project root: the directory that contains ledger/ (ledger.py's `-C`)."""
        return self.ledger_file.parent.parent


def find_config(explicit: str | None = None, cwd: Path | None = None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigError(f"{p}: no such file")
        return p
    for p in (Path(cwd or ".") / CONFIG_NAME,
              Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "trust-ledger-ui" / "config.toml"):
        if p.is_file():
            return p
    raise ConfigError(f"no {CONFIG_NAME} here and no ~/.config/trust-ledger-ui/config.toml; use --config FILE")


def load_config(path: Path) -> Config:
    path = Path(path).resolve()
    try:
        raw = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e
    for table, body in raw.items():
        if table not in KNOWN:
            raise ConfigError(f"{path}: unknown table [{table}]; known: {', '.join(KNOWN)}")
        if not isinstance(body, dict):
            raise ConfigError(f"{path}: {table} must be a table")
        bad = set(body) - KNOWN[table]
        if bad:
            raise ConfigError(f"{path}: unknown key(s) in [{table}]: {', '.join(sorted(bad))}; "
                              f"known: {', '.join(sorted(KNOWN[table]))}")
    led = raw.get("ledger", {})
    for k in ("file", "tool"):
        if k not in led:
            raise ConfigError(f"{path}: [ledger] needs `{k}`")
    here = path.parent
    sig, meta, view, srv = (raw.get(t, {}) for t in ("signing", "metadata", "viewer", "server"))
    reasons = sig.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        raise ConfigError(f"{path}: [signing] reasons must be a list of strings")
    cfg = Config(path=path, ledger_file=(here / led["file"]).resolve(), tool=(here / led["tool"]).resolve(),
                 person=sig.get("person", ""), key=sig.get("key", ""), reasons=reasons,
                 paper_toml=meta.get("paper_toml"), pdf_viewer=view.get("pdf", "embed"),
                 port=int(srv.get("port", 0)), open_browser=bool(srv.get("open_browser", True)))
    for what, p in (("ledger file", cfg.ledger_file), ("tool", cfg.tool)):
        if not p.is_file():
            raise ConfigError(f"{path}: {what} {p} does not exist")
    return cfg


def guess_tool(ledger_file: Path) -> Path | None:
    """A ledger.py for this project: the project's vendored copy, else a trust-ledger checkout next to the project."""
    root = ledger_file.parent.parent
    for c in (root / "ledger" / "vendor" / "ledger.py", root.parent / "trust-ledger" / "ledger.py"):
        if c.is_file():
            return c
    return None


def known_keys(ledger_file: Path) -> list[tuple[str, str]]:
    """(key id, person) of ledger/keys.toml, for the default signing key."""
    f = ledger_file.parent / "keys.toml"
    try:
        raw = tomllib.loads(f.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return []
    return [(k, v.get("person", "")) for k, v in raw.get("key", {}).items()]


def write_config(path: Path, ledger_file: Path, tool: Path, key: str = "", person: str = "") -> Path:
    """Write a minimal ledger-ui.toml (paths relative to its directory where possible). Never overwrites."""
    path = Path(path)
    if path.exists():
        raise ConfigError(f"{path} exists; edit it instead")
    rel = lambda p: os.path.relpath(Path(p).resolve(), path.parent.resolve())
    lines = ["# trust-ledger-ui: where the ledger is and who signs (docs: README.md of trust-ledger-ui)", "[ledger]",
             f'file = "{rel(ledger_file)}"', f'tool = "{rel(tool)}"   # a trust-ledger ledger.py with the library API', ""]
    if key or person:
        lines += ["[signing]"] + ([f'person = "{person}"'] if person else []) + ([f'key = "{key}"   # id in ledger/keys.toml; signs through ssh-agent'] if key else []) + [""]
    lines += ["[metadata]", '# paper_toml = "paper/{name}/paper.toml"   # titles and edition PDFs, if you have such files', ""]
    path.write_text("\n".join(lines))
    return path
