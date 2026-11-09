"""Entry point: `ledger-ui` reads its config file and serves the UI on 127.0.0.1 ."""
from __future__ import annotations

import argparse
import sys

from pathlib import Path

from .core.config import CONFIG_NAME, ConfigError, find_config, guess_tool, known_keys, load_config, write_config
from .core.ledgerio import Project, ToolError


def init(ledger_file: Path) -> int:
    ledger_file = ledger_file.resolve()
    if not ledger_file.is_file():
        print(f"ledger-ui: {ledger_file}: no such file (give the project's ledger/ledger.toml)", file=sys.stderr)
        return 2
    tool = guess_tool(ledger_file)
    keys = known_keys(ledger_file)
    if tool is None:
        print("ledger-ui: no ledger.py found (looked for ledger/vendor/ledger.py and ../trust-ledger/ledger.py); "
              "write the [ledger] tool path into the config yourself", file=sys.stderr)
        tool = Path("ledger.py")
    key, person = keys[0] if keys else ("", "")
    try:
        path = write_config(Path.cwd() / CONFIG_NAME, ledger_file, tool, key, person)
    except ConfigError as e:
        print(f"ledger-ui: {e}", file=sys.stderr)
        return 2
    print(f"wrote {path}" + (f"; signing as {person} with key {key!r} (change it in the file if that is not you)" if keys else
                             "; no keys in the ledger yet: register one with `ledger.py addkey`, then set [signing] key"))
    return 0


def export(project: Project, out: Path, papers: list[str], repo: str | None) -> int:
    from .core.export import ExportError, export_site
    if repo and not repo.startswith("https://"):
        print("ledger-ui: --repo must be an https:// URL (it is shown to readers as a link)", file=sys.stderr)
        return 2
    try:
        entries = export_site(project, out, papers, repo=repo)
    except ExportError as e:
        print(f"ledger-ui: {e}", file=sys.stderr)
        return 2
    for e in entries:
        print(f"{out / e['file']}  root {e['root']}")
        for w in e["warnings"]:
            print(f"  warning: {w}", file=sys.stderr)
    print(f"{out / 'index.html'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ledger-ui", description=__doc__)
    ap.add_argument("--config", help="ledger-ui.toml (default: ./ledger-ui.toml, then ~/.config/trust-ledger-ui/config.toml)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser (overrides [server] open_browser)")
    ap.add_argument("--init", metavar="LEDGER_TOML", help=f"write a {CONFIG_NAME} for this ledger/ledger.toml into the current directory and exit")
    ap.add_argument("--summary", action="store_true", help="print the papers with their counts and exit (no server)")
    ap.add_argument("--export", metavar="DIR", help="write a static read-only page per paper (DIR/<paper>.html, self-contained) "
                    "and DIR/index.html, for referees and readers, and exit (no server)")
    ap.add_argument("--paper", action="append", default=[], help="with --export: only this paper (repeatable; default: all)")
    ap.add_argument("--repo", metavar="URL", help="with --export: the public https URL of the project's repository, shown on the page")
    args = ap.parse_args(argv)
    if (args.paper or args.repo) and not args.export:
        ap.error("--paper and --repo go with --export")
    if args.init:
        return init(Path(args.init))
    try:
        cfg = load_config(find_config(args.config))
        project = Project(cfg)
        if args.summary:
            for p in project.papers():
                c = project.status(p.name)["counts"]
                print(f"{p.name:12} claims {c['claims']:3}  none {c['none']:3}  stale {c['stale']:3}  "
                      f"green {c['green']:3}  yellow {c['yellow']:3}  hypotheses open {c['hypotheses_open']}/{c['hypotheses']}")
            return 0
        if args.export:
            return export(project, Path(args.export), args.paper, args.repo)
    except (ConfigError, ToolError) as e:
        print(f"ledger-ui: {e}", file=sys.stderr)
        return 2
    from .server import App
    app = App(project, port=cfg.port)
    print(f"ledger-ui: {app.url}", flush=True)
    if cfg.open_browser and not args.no_browser:
        import webbrowser
        webbrowser.open(app.url)
    try:
        app.serve()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
