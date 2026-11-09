"""A static, read-only page of a paper's ledger for referees and readers (SPEC.md section 16).

`export_site` writes one self-contained HTML file per paper (data, scripts, styles and fonts inlined; it works from
disk, from a web server or from GitHub Pages) and an `index.html` that links them. The page shows what the ledger
records; it recomputes no hash and checks no signature, and says so. The data block also carries the hashes that
`ledger.py lock` would write, so that a later version of the page can recompute the root in the browser."""
from __future__ import annotations

import base64
import datetime as _dt
import html
import json
import re
import subprocess
from pathlib import Path

from .. import __version__
from . import papermeta
from .ledgerio import Project
from .render import paper_macros

STATIC = Path(__file__).resolve().parent.parent / "static"
EXPORT_FORMAT = "0.1"            # the layout of the data block (BUNDLE below); bump on incompatible changes


class ExportError(Exception):
    pass


def git_state(root: Path) -> dict | None:
    """{commit, dirty} of the project's git checkout, None outside git. `dirty` lists changed tracked files (at most 20)."""
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
        if head.returncode != 0:
            return None
        st = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    changed = [ln[3:] for ln in st.stdout.splitlines() if ln.strip()]
    return dict(commit=head.stdout.strip(), dirty=changed[:20], dirty_count=len(changed))


def _stale(x: dict) -> bool:
    return any(not a["current"] for a in x["attestations"])


def bundle(project: Project, paper: str, *, repo: str | None = None, now: _dt.datetime | None = None) -> dict:
    """Everything the page shows for one paper, as JSON-able data. Texts are as the ledger has them (LaTeX source);
    the page renders them. Paths are relative to the project root."""
    if paper not in {p.name for p in project.papers()}:
        raise ExportError(f"unknown paper {paper!r}; configured: {', '.join(p.name for p in project.papers())}")
    status = project.status(paper)
    claims = {c["name"]: project.detail(paper, c["name"]) for c in status["claims"]}
    hyps = {h["name"]: project.hypothesis_detail(paper, h["name"]) for h in status["hypotheses"]}
    diffs = {}
    for c in status["claims"]:
        if _stale(c):
            try:
                diffs["claim:" + c["name"]] = project.diff(paper, "claim", c["name"])
            except KeyError:
                pass
    for h in status["hypotheses"]:
        if _stale(h):
            try:
                diffs["hypothesis:" + h["name"]] = project.diff(paper, "hypothesis", h["name"])
            except KeyError:
                pass
    meta = papermeta.load(project.cfg.paper_toml, project.root, paper, project.paper(paper).main)
    settings = project.paper_settings(paper)
    tex = project.main_tex(paper)
    st = {k: v for k, v in status.items() if k not in ("notes", "unsnapshotted", "stale_unsnapshotted")}
    when = (now or _dt.datetime.now(_dt.timezone.utc)).replace(microsecond=0)
    return dict(
        export_format=EXPORT_FORMAT, generated=when.isoformat(), ui_version=__version__,
        project=project.root.name, paper=paper, title=meta.title, repo=repo,
        supplement=settings.get("supplement"), verify=settings.get("verify") or f"python3 ledger.py -P {paper} verify",
        printed_root=project.printed_root(paper), git=git_state(project.root),
        status=st, claims=claims, hypotheses=hyps, diffs=diffs, attestations=project.attestation_records(paper),
        vocabulary=project.vocabulary(paper),
        macros=paper_macros(tex) if tex else paper_macros(Path("/nonexistent")),
        lock=project.lock_data(paper))


# ---- inlining
def _script_safe(js: str) -> str:
    """Text that can sit inside <script>...</script>: `</script` (any case) would end the element early."""
    return re.sub(r"</(script)", r"<\\/\1", js, flags=re.I)


def json_block(obj) -> str:
    """JSON for a <script type="application/json"> element: `<` is escaped, so no `</script>` or `<!--` can occur."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def katex_css() -> str:
    """KaTeX's stylesheet with the shipped .woff2 fonts as data: URIs (the .woff/.ttf fallbacks are not shipped and are
    dropped, so the browser does not try to load them)."""
    css = (STATIC / "vendor/katex/katex.min.css").read_text()
    fonts = STATIC / "vendor/katex/fonts"

    def src(m):
        urls = re.findall(r"url\(([^)]+)\)\s*format\([^)]*\)", m.group(1))
        out = []
        for u in urls:
            f = fonts / Path(u.strip("'\"")).name
            if f.suffix == ".woff2" and f.is_file():
                out.append(f"url(data:font/woff2;base64,{base64.b64encode(f.read_bytes()).decode()}) format(\"woff2\")")
        return "src:" + ",".join(out) if out else m.group(0)
    return re.sub(r"src:([^;}]+)", src, css)


def render_page(data: dict) -> str:
    page = (STATIC / "reader.html").read_text()
    parts = {
        "katex_css": katex_css(),
        "style_css": (STATIC / "style.css").read_text() + "\n" + (STATIC / "reader.css").read_text(),
        "scripts": "\n".join(f"<script>{_script_safe((STATIC / f).read_text())}</script>"
                             for f in ("vendor/katex/katex.min.js", "texlite.js", "diff.js", "reader.js")),
        "alpine": f"<script defer>{_script_safe((STATIC / 'vendor/alpine/alpine.min.js').read_text())}</script>",
        "data": json_block(data),
        "title": html.escape(f"{data['title'] or data['paper']}: ledger"),
    }
    # The page in static/ links its files (so that it opens from the source tree while editing); the export replaces
    # each link by the inlined file. Every marker must be found exactly once.
    def sub(pattern, repl, flags=0):
        nonlocal page
        page, n = re.subn(pattern, lambda m: repl, page, flags=flags)
        if n != 1:
            raise ExportError(f"reader.html: marker {pattern!r} found {n} times, expected once")
    sub(r'<link rel="stylesheet" href="vendor/katex/katex.min.css">', f"<style>{parts['katex_css']}</style>")
    sub(r'<link rel="stylesheet" href="style.css">\s*<link rel="stylesheet" href="reader.css">',
        f"<style>{parts['style_css']}</style>")
    sub(r'<!-- scripts -->.*?<!-- /scripts -->', parts["scripts"], re.S)
    sub(r'<script defer src="vendor/alpine/alpine.min.js"></script>', parts["alpine"])
    sub(r'<script type="application/json" id="ledger-data">null</script>',
        f'<script type="application/json" id="ledger-data">{parts["data"]}</script>')
    sub(r'<title>ledger</title>', f"<title>{parts['title']}</title>")
    return page


def index_page(entries: list[dict], project: str) -> str:
    rows = "\n".join(
        f'<li><a href="{html.escape(e["file"])}"><b>{html.escape(e["title"] or e["paper"])}</b></a>'
        f'{" <span class=muted>(" + html.escape(e["paper"]) + ")</span>" if e["title"] else ""}<br>'
        f'<span class="muted">{e["claims"]} results · root</span> <code>{e["root"]}</code></li>' for e in entries)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(project)}: ledgers</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1d1d1b;background:#fafaf8}}
code{{font-size:.8em;word-break:break-all}} .muted{{color:#6b6b66}} li{{margin:1rem 0}}
@media (prefers-color-scheme: dark){{body{{color:#e8e8e2;background:#161614}} a{{color:#9ab8ff}} .muted{{color:#9a9a92}}}}</style>
</head><body>
<h1>{html.escape(project)}</h1>
<p>What the trust ledger of each paper records: for every result, what it rests on, what was checked by a tool,
and who has attested it. Each page is a preview: it shows the ledger, it does not check it.</p>
<ul>
{rows}
</ul>
<p class="muted">Generated by trust-ledger-ui {__version__}.</p>
</body></html>
"""


def export_site(project: Project, out: Path, papers: list[str] | None = None, *, repo: str | None = None,
                now: _dt.datetime | None = None) -> list[dict]:
    """Write <out>/<paper>.html for each paper (all configured ones if `papers` is empty) and <out>/index.html. Returns
    one entry per paper: {paper, file, title, root, claims, printed_root, warnings}."""
    names = papers or [p.name for p in project.papers()]
    if not names:
        raise ExportError("the ledger configures no [paper.*]; nothing to export")
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for name in names:
        data = bundle(project, name, repo=repo, now=now)
        f = out / f"{name}.html"
        f.write_text(render_page(data))
        warnings = []
        if data["printed_root"] and data["printed_root"] != data["status"]["root"]:
            warnings.append(f"the generated ledger-{name}-root.tex shows {data['printed_root'][:12]}..., the ledger is at "
                            f"{data['status']['root'][:12]}...: run `ledger.py -P {name} tex` and rebuild the PDF, or the "
                            "page and the paper show different roots")
        if not data["printed_root"]:
            warnings.append(f"no generated ledger-{name}-root.tex: the page cannot be compared with a root in the paper")
        if data["git"] and data["git"]["dirty_count"]:
            warnings.append(f"{data['git']['dirty_count']} tracked file(s) have uncommitted changes; the page says so")
        if not data["status"]["ok"]:
            warnings.append("the ledger reports errors; the page lists them")
        entries.append(dict(paper=name, file=f.name, title=data["title"], root=data["status"]["root"],
                            claims=len(data["claims"]), printed_root=data["printed_root"], warnings=warnings))
    (out / "index.html").write_text(index_page(entries, project.root.name))
    return entries
