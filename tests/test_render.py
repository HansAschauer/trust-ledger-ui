from trust_ledger_ui.core.render import SHIMS, macros_from_preamble, paper_macros


def test_newcommand_with_arguments_and_nesting():
    m = macros_from_preamble(r"""
\newcommand{\R}{\mathbb{R}}
\newcommand{\norm}[1]{\left\lVert #1 \right\rVert}   % a comment
\newcommand{\nuc}[1]{\norm{#1}_{*}}
\renewcommand\eps{\varepsilon}
\DeclareMathOperator{\tr}{tr}
\DeclareMathOperator*{\argmax}{arg\,max}
\newcommand{\opt}[2][x]{#1 #2}
\begin{document} \newcommand{\late}{no} \end{document}""")
    assert m["\\R"] == "\\mathbb{R}"
    assert m["\\norm"] == "\\left\\lVert #1 \\right\\rVert"
    assert m["\\nuc"] == "\\norm{#1}_{*}"
    assert m["\\eps"] == "\\varepsilon"
    assert m["\\tr"] == "\\operatorname{tr}"
    assert m["\\argmax"] == "\\operatorname*{arg\\,max}"
    assert "\\opt" not in m and "\\late" not in m      # default arguments and the body of the document are not macros


def test_paper_macros_adds_shims_and_survives_a_missing_file(tmp_path):
    f = tmp_path / "p.tex"
    f.write_text("\\newcommand{\\mathds}[1]{\\mathbf{#1}}\n\\begin{document}\\end{document}")
    assert paper_macros(f)["\\mathds"] == "\\mathbf{#1}"      # the paper's own definition wins
    assert paper_macros(tmp_path / "missing.tex") == SHIMS
