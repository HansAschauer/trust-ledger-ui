from trust_ledger_ui.core import papermeta


def make(tmp_path, body, pdfs=("p.pdf", "p_reviewed.pdf")):
    d = tmp_path / "paper" / "demo"
    d.mkdir(parents=True)
    (d / "paper.toml").write_text(body)
    for f in pdfs:
        (d / f).write_bytes(b"%PDF")
    return d


GOOD = '[paper]\nname = "demo"\nmain = "p.tex"\ntitle = "A title"\n[editions]\nreviewed = "p_reviewed.tex"\nexplained = "p_explained.tex"\n'


def test_title_and_existing_editions(tmp_path):
    d = make(tmp_path, GOOD)
    m = papermeta.load("paper/{name}/paper.toml", tmp_path, "demo", "paper/demo/p.tex")
    assert m.title == "A title" and m.warnings == []
    assert set(m.pdfs) == {"paper", "reviewed"}               # the explained PDF does not exist: no link
    assert m.pdfs["reviewed"] == d / "p_reviewed.pdf"


def test_missing_file_or_no_pattern_is_not_an_error(tmp_path):
    assert papermeta.load(None, tmp_path, "demo", None).title is None
    m = papermeta.load("paper/{name}/paper.toml", tmp_path, "demo", None)
    assert m.title is None and m.pdfs == {} and m.warnings == []


def test_cross_check_warns_and_bad_toml_is_reported(tmp_path):
    make(tmp_path, GOOD)
    m = papermeta.load("paper/{name}/paper.toml", tmp_path, "demo", "paper/demo/other.tex")
    assert any("main is p.tex" in w for w in m.warnings)
    (tmp_path / "paper" / "demo" / "paper.toml").write_text("[paper\n")
    m = papermeta.load("paper/{name}/paper.toml", tmp_path, "demo", None)
    assert m.title is None and m.warnings
