import pytest
from conftest import ledger_cli

from trust_ledger_ui.core.config import load_config
from trust_ledger_ui.core.ledgerio import Project, ToolError, attention, load_tool


def text_rows(tool, root, paper):
    """The claim rows of `ledger.py status` (before the blank line): (name, attestation column)."""
    r = ledger_cli(tool, root, "-P", paper, "status")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.split("\n\n")[0].splitlines()
    head = lines[0]
    start = head.index("attestation")
    return {ln.split()[0]: ln[start:].rsplit("  ", 1)[0].strip() for ln in lines[1:]}


def test_claims_and_attestation_state_match_ledger_status(config_file, tool, egg):
    project = Project(load_config(config_file))
    papers = [p.name for p in project.papers()]
    assert papers, "the egg example defines a paper"
    for paper in papers:
        d = project.status(paper)
        rows = text_rows(tool, egg, paper)
        assert {c["name"] for c in d["claims"]} == set(rows)
        for c in d["claims"]:
            cell = rows[c["name"]]
            assert ("STALE" in cell) == any(not a["current"] for a in c["attestations"]), c["name"]
            assert (cell == "none") == (not c["attestations"]), c["name"]


def test_counts_add_up(config_file):
    d = Project(load_config(config_file)).status("egg")
    c = d["counts"]
    assert c["claims"] == len(d["claims"])
    assert c["none"] + c["stale"] + sum(x["attention"] == "ok" for x in d["claims"]) == c["claims"]


def test_attention():
    cur, old = dict(current=True), dict(current=False)
    assert attention(dict(attestations=[])) == "none"
    assert attention(dict(attestations=[old])) == "stale"
    assert attention(dict(attestations=[old, cur])) == "ok"


def test_tool_without_the_api_is_refused(tmp_path):
    old = tmp_path / "ledger.py"
    old.write_text('__version__ = "0.2.0"\nFORMAT_VERSION = "0.3.0"\nclass Ledger: pass\n')
    with pytest.raises(ToolError, match="lacks the library API"):
        load_tool(old)


def test_unsupported_format_is_refused(tmp_path, tool):
    src = tool.read_text().replace('FORMAT_VERSION = "0.3.0"', 'FORMAT_VERSION = "9.9.9"', 1)
    p = tmp_path / "ledger.py"
    p.write_text(src)
    with pytest.raises(ToolError, match="supports"):
        load_tool(p)
