import sys
import time

import pytest

from trust_ledger_ui.core.config import load_config
from trust_ledger_ui.core.jobs import JobError, JobManager
from trust_ledger_ui.core.ledgerio import Project

STUB = r'''
import sys, time, pathlib
a = sys.argv[1:]
print("args:", " ".join(a), flush=True)
if "review" in a:
    out = pathlib.Path(a[a.index("--out") + 1]); P = a[a.index("-P") + 1]
    (out / f"{P}-review.pdf").write_bytes(b"%PDF-1.4 stub")
if "extract" in a or "check" in a:
    for i in range(200):
        print("tick", i, flush=True); time.sleep(0.1)
if "lock" in a:
    print("boom", file=sys.stderr); sys.exit(3)
'''


@pytest.fixture
def jm(config_file, tmp_path):
    stub = tmp_path / "stub.py"
    stub.write_text(STUB)
    return JobManager(Project(load_config(config_file)), tmp_path / "state", tool=stub)


def wait(jm, jid, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = jm.get(jid)
        if j["state"] not in ("running", "cancelling"):
            return j
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_review_job_builds_the_command_and_records_the_pack(jm):
    jid = jm.start("review", "egg", ["scaling", "lem:colder"])           # a claim name and a label
    j = wait(jm, jid)
    assert j["state"] == "done" and j["returncode"] == 0
    cmd = j["log"][0]
    assert "-P egg review" in cmd and "--for scaling,lem:colder" in cmd and f"packs/{jid}" in cmd
    assert j["pack"]["ready"] and set(j["pack"]["bounds"]) == {"scaling", "colder"}     # label resolved to the claim name
    assert all(len(b) == 64 for b in j["pack"]["bounds"].values())
    assert jm.pack_pdf(jid).read_bytes().startswith(b"%PDF")
    assert jm.list()[0]["pack"] is True


def test_a_failing_job_is_reported_with_its_output(jm):
    j = wait(jm, jm.start("lock", "egg"))
    assert j["state"] == "failed" and j["returncode"] == 3 and "boom" in j["log"]


def test_refusals(jm):
    with pytest.raises(JobError, match="unknown job kind"):
        jm.start("rm -rf", "egg")
    with pytest.raises(JobError, match="needs one paper"):
        jm.start("review", None)
    with pytest.raises(JobError, match="must be confirmed"):
        jm.start("extract", None)
    with pytest.raises(JobError, match="not a claim or label"):
        jm.start("review", "egg", ["scaling; echo hacked"])
    assert jm.pack_pdf("nope") is None and jm.get("nope") is None


def test_one_job_per_kind_and_one_lean_job_and_cancel(jm):
    a = jm.start("extract", None, confirm=True)
    with pytest.raises(JobError, match="already running"):
        jm.start("extract", None, confirm=True)
    time.sleep(0.5)
    first = jm.get(a)
    assert first["state"] == "running" and any(l.startswith("tick") for l in first["log"])
    more = jm.get(a, since=first["next"])                                    # incremental reading of the log
    assert all(l not in first["log"] for l in more["log"][:1]) or not more["log"]
    jm.cancel(a)
    assert wait(jm, a)["state"] == "cancelled"
    jm.start("check", "egg")                                                 # other kinds are not blocked by it
    for j in jm.list():
        if j["state"] == "running":
            jm.cancel(j["id"])


def test_real_lock_and_verify_through_the_manager(config_file, tmp_path):
    project = Project(load_config(config_file))
    jm = JobManager(project, tmp_path / "state")                               # the real ledger.py
    assert wait(jm, jm.start("lock", "egg"))["state"] == "done"
    j = wait(jm, jm.start("verify", "egg"))
    assert j["state"] == "done" and any("OK" in l for l in j["log"])
