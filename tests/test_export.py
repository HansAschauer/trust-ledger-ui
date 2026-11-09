"""The static read-only page (`ledger-ui --export`), on a scratch copy of the egg example."""
import json
import re
import shutil
import subprocess

import pytest
from conftest import ledger_cli

from trust_ledger_ui import cli
from trust_ledger_ui.core.config import load_config
from trust_ledger_ui.core.export import ExportError, export_site, json_block, render_page
from trust_ledger_ui.core.ledgerio import Project


def data_of(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="ledger-data">(.*?)</script>', page, re.S)
    return json.loads(m.group(1))


@pytest.fixture
def project(config_file):
    return Project(load_config(config_file))


def test_one_self_contained_page_per_paper_and_an_index(project, tmp_path, tool, egg):
    out = tmp_path / "site"
    [e] = export_site(project, out)
    assert sorted(p.name for p in out.iterdir()) == ["egg.html", "index.html"]
    page = (out / "egg.html").read_text()
    # nothing is loaded from elsewhere: no linked script, stylesheet or font, no http(s) resource
    assert not re.search(r'<script[^>]+src=|<link[^>]+stylesheet|url\(fonts/', page)
    assert "data:font/woff2;base64," in page
    d = data_of(page)
    st = json.loads(ledger_cli(tool, egg, "-P", "egg", "status", "--json").stdout)
    assert d["status"]["root"] == st["root"] == e["root"]
    assert sorted(d["claims"]) == sorted(c["name"] for c in st["claims"])
    assert d["lock"]["root"] == st["root"] and d["lock"]["nodes"]
    assert d["export_format"] and d["paper"] == "egg" and d["verify"]
    # the written records carry what status leaves out: reason, signature, the public keys to check it later
    assert any(a.get("reason") for a in d["attestations"]) and d["vocabulary"]["keys"]
    assert "egg.html" in (out / "index.html").read_text()


def test_no_local_paths_in_the_data(project, tmp_path, egg):
    export_site(project, tmp_path / "site")
    page = (tmp_path / "site" / "egg.html").read_text()
    assert str(egg) not in page and str(tmp_path) not in page


def test_root_shown_in_the_paper_is_compared(project, tmp_path, tool, egg):
    assert ledger_cli(tool, egg, "-P", "egg", "tex").returncode == 0
    [e] = export_site(project, tmp_path / "a")
    assert e["printed_root"] == e["root"] and not [w for w in e["warnings"] if "root" in w]
    f = egg / "paper" / "ledger" / "ledger-egg-root.tex"
    f.write_text(re.sub(r"\\def\\LedgerRoot\{[0-9a-f]+\}", r"\\def\\LedgerRoot{" + "0" * 64 + "}", f.read_text()))
    [e] = export_site(project, tmp_path / "b")
    assert any("different roots" in w for w in e["warnings"])
    assert data_of((tmp_path / "b" / "egg.html").read_text())["printed_root"] == "0" * 64


def test_git_state_is_recorded(project, tmp_path, egg):
    if not shutil.which("git"):
        pytest.skip("needs git")
    run = lambda *a: subprocess.run(["git", "-C", str(egg), *a], check=True, capture_output=True)
    run("init", "-q"); run("add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qm", "x")
    d = data_of((export_site(project, tmp_path / "s") and (tmp_path / "s" / "egg.html")).read_text())
    assert len(d["git"]["commit"]) == 40 and d["git"]["dirty_count"] == 0
    (egg / "README.md").write_text("changed\n")
    [e] = export_site(project, tmp_path / "t")
    assert data_of((tmp_path / "t" / "egg.html").read_text())["git"]["dirty_count"] == 1
    assert any("uncommitted" in w for w in e["warnings"])


def test_data_cannot_end_the_script_element():
    s = json_block({"x": "</script><script>alert(1)</script> <!-- "})
    assert "</" not in s and "<!--" not in s and json.loads(s)["x"].startswith("</script>")


def test_text_in_the_data_cannot_break_out(project, tmp_path):
    from trust_ledger_ui.core.export import bundle
    d = bundle(project, "egg")
    d["title"] = "</title><script>x</script>"
    d["status"]["messages"] = ["</script><b>"]
    page = render_page(d)
    from html.parser import HTMLParser

    class Scripts(HTMLParser):                    # what a browser sees as elements (script content is raw text)
        def __init__(self):
            super().__init__(); self.tags = []
        def handle_starttag(self, tag, attrs):
            self.tags.append((tag, dict(attrs).get("type")))
    p = Scripts(); p.feed(page)
    scripts = [t for t in p.tags if t[0] == "script"]
    assert scripts == [("script", "application/json")] + [("script", None)] * 5
    assert ("title", None) in p.tags and "&lt;script&gt;" in page.split("</title>")[0]
    assert data_of(page)["status"]["messages"] == ["</script><b>"]


def test_unknown_paper(project, tmp_path):
    with pytest.raises(ExportError, match="unknown paper"):
        export_site(project, tmp_path / "s", ["nope"])


def test_cli(config_file, tmp_path, capsys):
    out = tmp_path / "site"
    assert cli.main(["--config", str(config_file), "--export", str(out), "--paper", "egg",
                     "--repo", "https://example.org/egg"]) == 0
    assert data_of((out / "egg.html").read_text())["repo"] == "https://example.org/egg"
    assert cli.main(["--config", str(config_file), "--export", str(out), "--repo", "git@example.org:egg"]) == 2
    assert cli.main(["--config", str(config_file), "--export", str(out), "--paper", "nope"]) == 2
    with pytest.raises(SystemExit):
        cli.main(["--config", str(config_file), "--paper", "egg"])
