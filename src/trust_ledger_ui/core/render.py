"""Macros for KaTeX, collected from a paper's preamble (SPEC.md section 9).

Result: a dict {"\\\\name": "expansion with #1"} for KaTeX's `macros` option. Supported: \\newcommand,
\\renewcommand, \\providecommand (with a number of arguments, no optional default argument) and
\\DeclareMathOperator[*]. Anything else in a preamble is ignored; a macro KaTeX cannot expand shows up in the page as a
formula that is displayed as source."""
from __future__ import annotations

import re
from pathlib import Path

# \mathds{1} has no KaTeX font; \mathbb is the closest. \cite/\ref/\eqref are handled in the page (texlite.js).
SHIMS = {
    "\\mathds": "\\mathbb{#1}",
    "\\eqref": "(#1)",
    "\\ref": "#1",
    "\\cite": "[#1]",
}

_DEF = re.compile(r"\\(newcommand|renewcommand|providecommand|DeclareMathOperator)(\*?)")


def _strip_comments(s: str) -> str:
    return re.sub(r"(?<!\\)%.*", "", s)


def _group(s: str, i: int, open_: str, close: str) -> tuple[str, int] | None:
    """The balanced group starting at the first `open_` at or after i (only whitespace may precede it)."""
    n = len(s)
    while i < n and s[i].isspace():
        i += 1
    if i >= n or s[i] != open_:
        return None
    depth, j = 0, i
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None


def _name(s: str, i: int) -> tuple[str, int] | None:
    """The macro name: {\\name} or \\name."""
    while i < len(s) and s[i].isspace():
        i += 1
    g = _group(s, i, "{", "}")
    if g:
        return g[0].strip(), g[1]
    m = re.compile(r"\\[A-Za-z]+|\\.").match(s, i)
    return (m.group(0), m.end()) if m else None


def macros_from_preamble(tex: str) -> dict[str, str]:
    pre = tex.split("\\begin{document}")[0] if "\\begin{document}" in tex else tex
    pre = _strip_comments(pre)
    out: dict[str, str] = {}
    for m in _DEF.finditer(pre):
        kind, star = m.group(1), m.group(2)
        nm = _name(pre, m.end())
        if not nm or not nm[0].startswith("\\"):
            continue
        name, i = nm
        if kind == "DeclareMathOperator":
            body = _group(pre, i, "{", "}")
            if body:
                out[name] = f"\\operatorname{star}{{{body[0]}}}"
            continue
        nargs = 0
        a = _group(pre, i, "[", "]")
        if a and a[0].strip().isdigit():
            nargs, i = int(a[0]), a[1]
            if _group(pre, i, "[", "]"):          # optional default argument: not expressible as a KaTeX macro
                continue
        body = _group(pre, i, "{", "}")
        if body:
            out[name] = body[0] if nargs or body[0] else body[0]
    return out


def paper_macros(main_tex: Path) -> dict[str, str]:
    """Shims first, then the paper's own definitions (which win)."""
    try:
        text = main_tex.read_text()
    except OSError:
        return dict(SHIMS)
    return {**SHIMS, **macros_from_preamble(text)}
