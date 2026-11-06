"""diff.js under node (skipped without node)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "src" / "trust_ledger_ui" / "static"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="needs node")


def run(expr):
    js = f"const d = require({str(STATIC / 'diff.js')!r}); console.log(JSON.stringify({expr}));"
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def test_word_diff_marks_only_the_change():
    ops = run("d.diff('For every $k$, t = 1.', 'For every $k$, t = 2.')")
    assert ops == [["=", "For every $k$, t = "], ["-", "1"], ["+", "2"], ["=", "."]]


def test_insertions_and_deletions_and_equal_texts():
    assert run("d.diff('a b c', 'a c')") == [["=", "a "], ["-", "b "], ["=", "c"]]
    assert run("d.diff('same', 'same')") == [["=", "same"]]
    assert run("d.diff('', 'new')") == [["+", "new"]]


def test_html_is_escaped_and_marked():
    html = run("d.toHtml(d.diff('<b>x</b>', '<b>y</b>'))")
    assert "<del>x</del>" in html and "<ins>y</ins>" in html and "&lt;b&gt;" in html and "<b>" not in html


def test_fields_lists_only_changed_keys_and_shows_non_strings_as_json():
    f = run("d.fields({type: 'Nat', value: 'fun n => n', k: 1}, {type: 'Nat', value: 'fun n => n + 2', k: 2})")
    assert [x["key"] for x in f] == ["k", "value"] and "<ins>" in f[1]["html"]


def test_large_inputs_do_not_blow_up():
    big = "word " * 3000
    ops = run(f"d.diff({big!r}, {big!r} + 'x')")
    assert ops[0][0] == "=" and ops[-1] == ["+", "x"]
