import time

import pytest

from trust_ledger_ui.core.attest import AttestError, Attestor
from trust_ledger_ui.core.config import load_config
from trust_ledger_ui.core.ledgerio import Project

pytestmark = pytest.mark.usefixtures("signing")


def make(config_file, tmp_path):
    project = Project(load_config(config_file))
    return project, Attestor(project, tmp_path / "ledger-ui.log")


def wait(att, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        j = att.job(job_id)
        if j["state"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def sign(att, targets, signing, **kw):
    args = dict(paper="egg", kind="claim", targets=targets, level="green", reason="", checklist=[], key=signing.id)
    args.update(kw)
    pv = att.preview(**args)
    return pv, wait(att, att.start(pv["id"]))


def test_options_show_the_key_and_whether_the_agent_holds_it(config_file, tmp_path, signing):
    project, att = make(config_file, tmp_path)
    o = att.options("egg")
    k = {x["id"]: x for x in o["keys"]}["tester"]
    assert k["person"] == "T. Ester" and k["fingerprint"].startswith("SHA256:") and not k["in_agent"]
    assert o["agent"]["available"] and "green" in o["levels"] and "C1" in o["checklist"]
    signing.load()
    assert {x["id"]: x for x in att.options("egg")["keys"]}["tester"]["in_agent"]


def test_batch_is_signed_through_the_agent_and_verifies(config_file, tmp_path, signing):
    signing.load()
    project, att = make(config_file, tmp_path)
    pv, job = sign(att, ["scaling", "colder"], signing, level="yellow", reason="read both, same reason", checklist=["C1"])
    assert pv["signatures"] == 2 and pv["key_in_agent"] and pv["person"] == "T. Ester"
    assert job["state"] == "done" and [r["status"] for r in job["results"]] == ["attested", "attested"]
    L = project.tool.Ledger(project.root, "egg")
    for c in ("scaling", "colder"):
        assert L.signature_of(c, "T. Ester") == "signed"
        assert L.attestation_state(c)[-1][1:] == ("yellow", L.attestation_state(c)[-1][2], True)
    assert L.warnings == [] and L.errors == []
    log = (tmp_path / "ledger-ui.log").read_text().splitlines()
    assert len(log) == 2 and '"event": "attested"' in log[0]


def test_unloaded_key_stops_before_the_first_claim(config_file, tmp_path, signing):
    project, att = make(config_file, tmp_path)
    f = project.root / "ledger" / "attestations.toml"
    before = f.read_bytes()
    pv, job = sign(att, ["scaling", "colder"], signing)                      # the agent holds no key
    assert not pv["key_in_agent"]
    assert job["state"] == "failed" and "not loaded" in job["message"] and "ssh-add" in job["message"]
    assert f.read_bytes() == before


def test_a_claim_that_changed_since_the_preview_is_skipped(config_file, tmp_path, signing):
    signing.load()
    project, att = make(config_file, tmp_path)
    pv = att.preview("egg", "claim", ["scaling", "colder"], "green", "", [], signing.id)
    tex = project.root / "paper" / "main.tex"
    tex.write_text(tex.read_text().replace("\\label{lem:scaling}", "\\label{lem:scaling} Additionally, trivially so.", 1))
    job = wait(att, att.start(pv["id"]))
    st = {r["target"]: r for r in job["results"]}
    assert st["scaling"]["status"] == "skipped" and "changed since the preview" in st["scaling"]["message"]
    assert st["colder"]["status"] == "attested"


def test_problems_are_reported_per_target_and_bad_input_is_refused(config_file, tmp_path, signing):
    project, att = make(config_file, tmp_path)
    pv = att.preview("egg", "claim", ["scaling", "no-such-claim"], "green", "", ["C9"], signing.id)
    assert [i["ok"] for i in pv["items"]] == [False, False]                   # C9 is not a checklist item; unknown claim
    with pytest.raises(AttestError, match="nothing to sign"):
        att.start(pv["id"])
    pv = att.preview("egg", "claim", ["scaling"], "yellow", "", [], signing.id)
    assert "yellow needs" in pv["items"][0]["problem"]
    with pytest.raises(AttestError):
        att.preview("egg", "claim", [], "green", "", [], signing.id)
    with pytest.raises(AttestError, match="not in ledger/keys.toml"):
        att.preview("egg", "claim", ["scaling"], "green", "", [], "nokey")
    with pytest.raises(AttestError, match="unknown or expired"):
        att.start("nope")


def test_a_preview_can_be_executed_once(config_file, tmp_path, signing):
    signing.load()
    project, att = make(config_file, tmp_path)
    pv = att.preview("egg", "claim", ["scaling"], "green", "", [], signing.id)
    wait(att, att.start(pv["id"]))
    with pytest.raises(AttestError, match="unknown or expired"):
        att.start(pv["id"])


def test_undo_removes_exactly_the_last_batch_and_refuses_after_other_changes(config_file, tmp_path, signing):
    signing.load()
    project, att = make(config_file, tmp_path)
    f = project.root / "ledger" / "attestations.toml"
    before = f.read_bytes()
    sign(att, ["scaling", "colder"], signing)
    assert f.read_bytes() != before
    assert att.undo()["removed"] == ["scaling", "colder"]
    assert f.read_bytes() == before
    with pytest.raises(AttestError, match="nothing to undo"):
        att.undo()
    sign(att, ["scaling"], signing)
    f.write_bytes(f.read_bytes() + b"\n# someone edited this\n")
    with pytest.raises(AttestError, match="changed since that batch"):
        att.undo()


def test_hypothesis_targets_use_the_hypothesis_checklist_and_state(config_file, tmp_path, signing):
    project, att = make(config_file, tmp_path)
    hyps = project.status("egg")["hypotheses"]
    if not hyps:
        pytest.skip("the egg example has no hypothesis")
    pv = att.preview("egg", "hypothesis", [hyps[0]["name"]], "green", "", [], signing.id)
    assert pv["items"][0]["ok"]


def git_repo(path):
    import os
    import shutil
    import subprocess
    if not shutil.which("git"):
        pytest.skip("needs git")
    env = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.org", GIT_COMMITTER_NAME="T",
               GIT_COMMITTER_EMAIL="t@example.org", GIT_CONFIG_GLOBAL="/dev/null")
    g = lambda *a: subprocess.run(["git", "-C", str(path), *a], check=True, capture_output=True, text=True, env=env).stdout.strip()
    g("init", "-q", "-b", "main")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    return g


def test_in_a_git_project_the_record_names_the_commit_and_undo_still_works(config_file, tmp_path, signing, egg):
    g = git_repo(egg)
    signing.load()
    project, att = make(config_file, tmp_path)
    f = egg / "ledger" / "attestations.toml"
    before = f.read_bytes()
    pv, job = sign(att, ["scaling"], signing)
    assert job["state"] == "done"
    text = f.read_text()
    assert f'git_head = "{g("rev-parse", "HEAD")}"' in text and "git_dirty = " in text
    assert att.undo()["removed"] == ["scaling"]                       # the text it removes is what was really appended
    assert f.read_bytes() == before
    L = project.tool.Ledger(project.root, "egg")
    assert L.errors == []
