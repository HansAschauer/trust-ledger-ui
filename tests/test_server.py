import json
import threading
import urllib.error
import urllib.request

import pytest

from trust_ledger_ui.core.config import load_config
from trust_ledger_ui.core.ledgerio import Project
from trust_ledger_ui.server import App

TOKEN = "test-token"


@pytest.fixture
def app(config_file):
    a = App(Project(load_config(config_file)), port=0, token=TOKEN)
    threading.Thread(target=a.httpd.serve_forever, daemon=True).start()
    yield a
    a.shutdown()


def get(app, path, *, token=TOKEN, host=None, origin=None, method="GET"):
    req = urllib.request.Request(f"http://127.0.0.1:{app.port}{path}", method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if host:
        req.add_header("Host", host)
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_api_needs_the_token(app):
    assert get(app, "/api/papers", token=None)[0] == 401
    assert get(app, "/api/papers", token="wrong")[0] == 401
    assert get(app, "/api/papers")[0] == 200


def test_host_and_origin_are_checked(app):
    assert get(app, "/api/papers", host="evil.example")[0] == 403
    assert get(app, "/api/papers", host=f"evil.example:{app.port}")[0] == 403
    assert get(app, "/api/papers", origin="http://evil.example")[0] == 403
    assert get(app, "/", host="evil.example")[0] == 403                     # also for the page (DNS rebinding)
    assert get(app, "/api/papers", origin=f"http://127.0.0.1:{app.port}")[0] == 200
    assert get(app, "/api/papers", host=f"localhost:{app.port}")[0] == 200


def test_static_files_and_no_traversal(app):
    st, body, h = get(app, "/", token=None)
    assert st == 200 and b"trust-ledger-ui" in body
    assert "default-src 'none'" in h["Content-Security-Policy"] and h["X-Content-Type-Options"] == "nosniff"
    assert get(app, "/vendor/katex/katex.min.js", token=None)[0] == 200
    assert get(app, "/%2e%2e/server.py", token=None)[0] == 404
    assert get(app, "/vendor/%2e%2e/%2e%2e/server.py", token=None)[0] == 404
    assert get(app, "/VENDOR.md", token=None)[0] == 404
    assert get(app, "/", token=None, method="POST")[0] == 405


def test_claims_detail_macros_and_state(app):
    st, body, _ = get(app, "/api/claims?paper=egg")
    d = json.loads(body)
    assert st == 200 and d["claims"] and d["counts"]["claims"] == len(d["claims"])
    name = d["claims"][0]["name"]
    st, body, _ = get(app, f"/api/claims/{name}?paper=egg")
    assert st == 200 and json.loads(body)["name"] == name
    assert get(app, "/api/claims/nope?paper=egg")[0] == 404
    assert get(app, "/api/claims?paper=nopaper")[0] == 404
    st, body, _ = get(app, "/api/macros?paper=egg")
    assert st == 200 and "\\mathds" in json.loads(body)
    st, body, _ = get(app, "/api/state?paper=egg")
    assert json.loads(body)["changed"] is False
    assert get(app, "/api/reload?paper=egg", method="POST")[0] == 200
    assert get(app, "/api/reload?paper=egg")[0] == 404                       # GET is not an endpoint for it
    assert get(app, "/api/nothing")[0] == 404


def post(app, path, body=None, *, token=TOKEN, origin=None, ctype="application/json"):
    data = json.dumps(body if body is not None else {}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{app.port}{path}", data=data, method="POST")
    if ctype:
        req.add_header("Content-Type", ctype)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_attest_over_http(app, signing):
    import time
    signing.load()
    st, raw, _ = get(app, "/api/attest/options?paper=egg")
    o = json.loads(raw)
    assert st == 200 and o["default_key"] and o["agent"]["available"]
    body = {"paper": "egg", "kind": "claim", "targets": ["scaling", "colder"], "level": "yellow",
            "reason": "r", "checklist": ["C1"], "key": "tester"}
    # writes need the token, a JSON body and a same-origin request
    assert post(app, "/api/attest/preview", body, token=None)[0] == 401
    assert post(app, "/api/attest/preview", body, origin="http://evil.example")[0] == 403
    assert post(app, "/api/attest/preview", body, ctype="text/plain")[0] == 400
    assert post(app, "/api/attest/preview", {**body, "targets": "scaling"})[0] == 400
    st, pv = post(app, "/api/attest/preview", body)
    assert st == 200 and pv["signatures"] == 2 and pv["key_in_agent"]
    assert post(app, "/api/attest", {"preview": "forged"})[0] == 400
    st, j = post(app, "/api/attest", {"preview": pv["id"]})
    assert st == 200
    for _ in range(300):
        job = json.loads(get(app, f"/api/attest/jobs/{j['job']}")[1])
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done" and [r["status"] for r in job["results"]] == ["attested"] * 2
    assert get(app, "/api/attest/jobs/unknown")[0] == 404
    st, u = post(app, "/api/attest/undo")
    assert st == 200 and u["removed"] == ["scaling", "colder"]
    assert post(app, "/api/attest/undo")[0] == 400


def test_jobs_and_packs_over_http(app):
    import time
    st, body, _ = get(app, "/api/jobs")
    assert st == 200 and "review" in json.loads(body)["kinds"]
    assert post(app, "/api/jobs", {"kind": "extract"}, token=None)[0] == 401
    assert post(app, "/api/jobs", {"kind": "extract"})[0] == 400                          # needs confirm
    assert post(app, "/api/jobs", {"kind": "evil"})[0] == 400
    assert post(app, "/api/jobs", {"kind": "lock", "paper": "nope"})[0] == 404
    st, j = post(app, "/api/jobs", {"kind": "lock", "paper": "egg"})
    assert st == 200
    for _ in range(200):
        job = json.loads(get(app, f"/api/jobs/{j['job']}")[1])
        if job["state"] != "running":
            break
        time.sleep(0.1)
    assert job["state"] == "done" and job["returncode"] == 0
    assert get(app, "/api/jobs/unknown")[0] == 404
    assert get(app, "/api/packs/unknown.pdf")[0] == 404
    assert post(app, f"/api/jobs/{j['job']}/cancel")[0] == 400                            # not running any more


def test_hypothesis_detail_and_edition_pdfs(app):
    d = json.loads(get(app, "/api/claims?paper=egg")[1])
    hyps = d["hypotheses"]
    assert hyps and "known_theorem" in hyps[0]
    st, body, _ = get(app, f"/api/hypotheses/{hyps[0]['name']}?paper=egg")
    j = json.loads(body)
    assert st == 200 and j["name"] == hyps[0]["name"] and "checklist" in j and isinstance(j["cites"], list)
    assert get(app, "/api/hypotheses/No.Such?paper=egg")[0] == 404
    assert get(app, "/api/editions/egg/reviewed.pdf")[0] == 404                       # no paper.toml configured
    assert get(app, "/api/editions/nope/paper.pdf")[0] == 404
    ov = json.loads(get(app, "/api/papers")[1])["papers"][0]
    assert ov["title"] is None and ov["editions"] == []


def test_titles_and_edition_pdfs_from_paper_toml(egg, tool, tmp_path):
    (egg / "meta").mkdir()
    (egg / "meta" / "egg.toml").write_text('[paper]\nname = "egg"\nmain = "../paper/main.tex"\ntitle = "Eggs and fridges"\n'
                                           '[editions]\nreviewed = "r.tex"\n')
    (egg / "meta" / "r.pdf").write_bytes(b"%PDF-1.4 reviewed")
    (egg / "paper" / "main.pdf").write_bytes(b"%PDF-1.4 plain")
    cfg = tmp_path / "ledger-ui.toml"
    cfg.write_text(f'[ledger]\nfile = "{egg}/ledger/ledger.toml"\ntool = "{tool}"\n[metadata]\npaper_toml = "meta/{{name}}.toml"\n')
    a = App(Project(load_config(cfg)), port=0, token=TOKEN)
    threading.Thread(target=a.httpd.serve_forever, daemon=True).start()
    try:
        ov = json.loads(get(a, "/api/papers")[1])["papers"][0]
        assert ov["title"] == "Eggs and fridges" and ov["editions"] == ["paper", "reviewed"] and ov["meta_warnings"] == []
        st, body, h = get(a, "/api/editions/egg/reviewed.pdf")
        assert st == 200 and body.startswith(b"%PDF") and h["Content-Type"] == "application/pdf"
        assert get(a, "/api/editions/egg/explained.pdf")[0] == 404
        assert get(a, "/api/editions/egg/reviewed.pdf", token=None)[0] == 401
    finally:
        a.shutdown()


def test_snapshots_and_diff(app):
    d = json.loads(get(app, "/api/claims?paper=egg")[1])
    assert "scaling" in d["unsnapshotted"]                                         # attested before snapshots existed
    st, body, _ = get(app, "/api/claims/scaling/diff?paper=egg")
    assert st == 200 and json.loads(body)["available"] is False
    st, r = post(app, "/api/snapshots?paper=egg")
    assert st == 200 and "scaling" in r["recorded"]
    assert json.loads(get(app, "/api/claims?paper=egg")[1])["unsnapshotted"] == []
    j = json.loads(get(app, "/api/claims/scaling/diff?paper=egg")[1])
    assert j["available"] and j["current"]
    assert get(app, "/api/claims/nope/diff?paper=egg")[0] == 404
    assert get(app, "/api/hypotheses/No.Such/diff?paper=egg")[0] == 404
    assert post(app, "/api/snapshots?paper=egg", token=None)[0] == 401


def test_unread_post_bodies_do_not_corrupt_a_keep_alive_connection(app):
    import http.client
    c = http.client.HTTPConnection("127.0.0.1", app.port)
    h = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    for _ in range(3):
        c.request("POST", "/api/reload?paper=egg", body=b"{}", headers=h)           # this endpoint never reads its body
        r = c.getresponse()
        r.read()
        assert r.status == 200
        c.request("GET", "/api/papers", headers={"Authorization": f"Bearer {TOKEN}"})
        r = c.getresponse()
        assert r.status == 200 and b"papers" in r.read()
    c.request("POST", "/api/reload?paper=egg", body=b"x" * 1_000_001, headers=h)
    assert c.getresponse().status == 413


def test_assessment_in_the_detail_and_recovery_from_git(app, egg):
    d = json.loads(get(app, "/api/claims?paper=egg")[1])
    assert "stale_unsnapshotted" in d and all("assessment" in c for c in d["claims"])
    det = json.loads(get(app, "/api/claims/scaling?paper=egg")[1])
    assert "assessment" in det
    # not a git repository: the message says so, the server stays up
    st, r = post(app, "/api/snapshots?paper=egg", {"from_git": True})
    assert st == 500 and "git" in r["error"]
    assert get(app, "/api/papers")[0] == 200


def test_assessment_audit_endpoint(app):
    st, body, _ = get(app, "/api/assessments/audit?paper=egg")
    rows = json.loads(body)["rows"]
    assert st == 200 and rows and rows[0]["state"] == "no git"                  # the scratch egg is not a repository
    assert get(app, "/api/assessments/audit?paper=egg", token=None)[0] == 401
