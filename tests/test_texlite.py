"""texlite.js under node, with the vendored KaTeX (skipped without node)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "src" / "trust_ledger_ui" / "static"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")

SCRIPT = """
const katex = require(%r), texlite = require(%r);
const cases = JSON.parse(process.argv[1]);
console.log(JSON.stringify(cases.map(c => texlite.toHtml(c.src, {katex, macros: c.macros || {}}))));
"""


def run(*cases):
    cases = [c if isinstance(c, dict) else {"src": c} for c in cases]
    out = subprocess.run(["node", "-e", SCRIPT % (str(STATIC / "vendor/katex/katex.min.js"), str(STATIC / "texlite.js")),
                          json.dumps(cases)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_inline_display_and_text_commands():
    [r] = run(r"Let \textbf{$k\ge 1$} and \emph{\ensuremath{\eta}} with $x$~and \(y\). \[ a=b \]")
    assert r["failures"] == [] and r["unknown"] == []
    assert r["html"].count("katex-display") == 1 and r["html"].count('class="katex"') >= 4
    assert "<b>" in r["html"] and "<i>" in r["html"]


def test_statement_blocks_and_bare_equation():
    [r] = run({"src": "[eq:a] equation: x^2+\\tr A\n[thm:a] theorem: [Title] Then $x$ holds, see \\eqref{eq:a}.",
               "macros": {"\\tr": "\\operatorname{tr}"}})
    assert r["failures"] == []
    assert r["html"].count("stmt-block") == 2 and "eq:a" in r["html"] and "Title" in r["html"]


def test_lists_and_pandoc_artifacts():
    [r] = run("\\begin{enumerate}\n\\def\\labelenumi{\\arabic{enumi}.}\n\\tightlist\n\\item one $a$\n\\item two\n\\end{enumerate}")
    assert r["unknown"] == []
    assert r["html"].count("<li>") == 2 and r["html"].count("</li>") == 2 and "<ol>" in r["html"]


def test_unrenderable_math_and_unknown_commands_are_visible_not_silent():
    [r] = run(r"Here \weirdcmd{x} and $\undefinedmacro{y}$ and $\frac{1}{$")
    assert "\\weirdcmd" in r["unknown"]
    assert len(r["failures"]) == 2 and r["html"].count('class="norender"') == 2


def test_katex_gaps_are_shimmed():
    [r] = run(r"\[\begin{multline} a \\ b \end{multline}\] $\begin{psmallmatrix}1&2\end{psmallmatrix}$")
    assert r["failures"] == []


def test_html_is_escaped():
    [r] = run("<script>alert(1)</script> & \\textless{}")
    assert "<script>" not in r["html"] and "&lt;script&gt;" in r["html"]


def test_empty_group_after_control_symbol():
    """Pandoc writes `exactalt\\_{}converse`; the empty group only ends the symbol and must not show."""
    [r] = run(r"\texttt{exactalt\_{}converse} and 5\%{} of a\_b")
    assert "exactalt_converse" in r["html"] and "{}" not in r["html"] and "a_b" in r["html"]


def test_list_spacing_settings_are_dropped():
    [r] = run(r"\begin{itemize}\itemsep0pt \item one \item two\end{itemize} and \parskip=2pt plus 1pt after")
    assert r["unknown"] == [] and "itemsep" not in r["html"] and "0pt" not in r["html"] and "2pt" not in r["html"]
    assert r["html"].count("<li>") == 2 and "after" in r["html"]


def test_bare_groups_are_invisible():
    """Pandoc writes `depolN\\_\\allowbreak{}tprod`; a bare {...} group shows no braces, an escaped \\{ does."""
    [r] = run(r"\texttt{depolN\_\allowbreak{}tprod} and {grouped} text, a set \{x\}")
    assert "depolN_tprod" in r["html"] and "grouped text" in r["html"] and "{x}" in r["html"]
    assert "{}" not in r["html"] and "{grouped}" not in r["html"]
