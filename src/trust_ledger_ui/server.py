"""The HTTP layer (SPEC.md section 10): 127.0.0.1 only, a token for every API call, Host/Origin checks, no CORS.

Static files (the page, its scripts, KaTeX) are public on the loopback interface; they contain no data. Everything
under /api/ needs `Authorization: Bearer <token>`. The token is printed in the URL's fragment (`#...`), which the
browser never sends to a server, and the page forwards it in the header."""
from __future__ import annotations

import hmac
import json
import mimetypes
import re
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .core import agent, papermeta
from .core.attest import AttestError, Attestor
from .core.jobs import KINDS, JobError, JobManager
from .core.ledgerio import Project, ToolError
from .core.render import paper_macros

STATIC = Path(__file__).resolve().parent / "static"
CSP = ("default-src 'none'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
       "img-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
# 'unsafe-eval': Alpine.js compiles its expressions with `new Function`. Only same-origin scripts are allowed.


def _strs(body: dict, key: str) -> list[str]:
    v = body.get(key, [])
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise AttestError(f"{key} must be a list of strings")
    return v


class Warmup:
    """Loads every configured paper in the background so that the overview has its counts without a wait."""

    def __init__(self, project: Project):
        self.project = project
        self.state: dict[str, str] = {}       # paper -> loading | ready | error: message
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        for p in self.project.papers():
            self.state[p.name] = "loading"
        self.thread.start()

    def run(self):
        for p in self.project.papers():
            try:
                self.project.load(p.name)
                self.state[p.name] = "ready"
            except Exception as e:                 # shown in the overview; the paper stays selectable
                self.state[p.name] = f"error: {e}"


class App:
    def __init__(self, project: Project, host: str = "127.0.0.1", port: int = 0, token: str | None = None):
        self.project = project
        self.token = token or secrets.token_urlsafe(24)
        self.warm = Warmup(project)
        self.attestor = Attestor(project, project.cfg.path.with_name("ledger-ui.log"))
        self.jobs = JobManager(project, project.cfg.path.parent / ".ledger-ui")
        self.httpd = ThreadingHTTPServer((host, port), self._handler())
        self.host = host
        self.port = self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/#{self.token}"

    def serve(self):
        self.warm.start()
        self.httpd.serve_forever()

    def shutdown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    # ---- request handling
    def _handler(self):
        app = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ledger-ui"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):           # quiet; writes are logged by the endpoints that write
                pass

            def do_GET(self):
                self.handle_request("GET")

            def do_POST(self):
                self.handle_request("POST")

            def do_HEAD(self):
                self.send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

            def handle_request(self, method):
                try:
                    # Always consume the request body, whether or not the endpoint uses it: on a keep-alive connection an
                    # unread body would be parsed as the start of the next request.
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 1_000_000:
                        self.close_connection = True
                        return self.send_error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request too large")
                    self._body = self.rfile.read(n) if n else b""
                    if not self.host_ok():
                        return self.send_error_json(HTTPStatus.FORBIDDEN, "bad Host or Origin")
                    url = urlsplit(self.path)
                    if url.path.startswith("/api/"):
                        if not self.token_ok():
                            return self.send_error_json(HTTPStatus.UNAUTHORIZED, "missing or wrong token")
                        return app.api(self, method, url.path, parse_qs(url.query))
                    if method != "GET":
                        return self.send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")
                    return self.send_static(url.path)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as e:                   # never leave the browser without an answer
                    self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, f"{type(e).__name__}: {e}")

            # -- checks
            def host_ok(self):
                host = self.headers.get("Host", "")
                allowed = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}
                if host not in allowed:
                    return False
                origin = self.headers.get("Origin")
                return origin is None or origin in {f"http://{h}" for h in allowed}

            def token_ok(self):
                auth = self.headers.get("Authorization", "")
                return auth.startswith("Bearer ") and hmac.compare_digest(auth[7:].encode(), app.token.encode())

            # -- responses
            def common_headers(self):
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")

            def read_json(self):
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    raise AttestError("send application/json")
                try:
                    body = json.loads(self._body or b"{}")
                except json.JSONDecodeError as e:
                    raise AttestError(f"bad JSON: {e}") from e
                if not isinstance(body, dict):
                    raise AttestError("the JSON body must be an object")
                return body

            def send_bytes(self, status, ctype, body, cache="no-store"):
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", cache)
                self.common_headers()
                self.end_headers()
                self.wfile.write(body)

            def send_json(self, obj, status=HTTPStatus.OK):
                self.send_bytes(status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode())

            def send_error_json(self, status, message):
                self.send_json({"error": message}, status)

            def send_static(self, path):
                rel = unquote(path).lstrip("/") or "index.html"
                f = (STATIC / rel).resolve()
                if STATIC not in f.parents or not f.is_file() or f.name == "VENDOR.md" or f.name == "SHA256SUMS":
                    return self.send_error_json(HTTPStatus.NOT_FOUND, "not found")
                ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                    ctype += "; charset=utf-8"
                self.send_bytes(HTTPStatus.OK, ctype, f.read_bytes(), cache="no-cache")

        return Handler

    # ---- the API
    def api(self, h, method, path, q):
        def one(name, default=None):
            return q.get(name, [default])[0]

        paper = one("paper") or None
        if paper is not None and paper not in {p.name for p in self.project.papers()}:
            return h.send_error_json(HTTPStatus.NOT_FOUND, f"unknown paper {paper}")
        try:
            if method == "GET" and path == "/api/papers":
                return h.send_json(self.papers_overview())
            if method == "GET" and path == "/api/claims":
                return h.send_json(self.project.status(paper))
            m = re.fullmatch(r"/api/claims/([A-Za-z0-9_.:-]+)", path)
            if method == "GET" and m:
                try:
                    return h.send_json(self.project.detail(paper, m.group(1)))
                except KeyError:
                    return h.send_error_json(HTTPStatus.NOT_FOUND, f"unknown claim {m.group(1)}")
            m = re.fullmatch(r"/api/(claims|hypotheses)/([A-Za-z0-9_.:-]+)/diff", path)
            if method == "GET" and m:
                try:
                    return h.send_json(self.project.diff(paper, "claim" if m.group(1) == "claims" else "hypothesis", m.group(2)))
                except KeyError:
                    return h.send_error_json(HTTPStatus.NOT_FOUND, f"unknown {m.group(1)[:-1] if m.group(1) == 'claims' else 'hypothesis'} {m.group(2)}")
            if method == "POST" and path == "/api/snapshots":
                b = h.read_json() if h._body else {}
                if b.get("from_git"):
                    return h.send_json({"results": self.project.recover_snapshots(paper, partial=b.get("partial") is True,
                                                                                  dry_run=b.get("dry_run") is True)})
                return h.send_json({"recorded": self.project.record_snapshots(paper)})
            m = re.fullmatch(r"/api/hypotheses/([A-Za-z0-9_.:-]+)", path)
            if method == "GET" and m:
                try:
                    return h.send_json(self.project.hypothesis_detail(paper, m.group(1)))
                except KeyError:
                    return h.send_error_json(HTTPStatus.NOT_FOUND, f"unknown hypothesis {m.group(1)}")
            m = re.fullmatch(r"/api/editions/([A-Za-z0-9_.-]+)/(paper|reviewed|explained)\.pdf", path)
            if method == "GET" and m:
                f = self.meta(m.group(1)).pdfs.get(m.group(2)) if m.group(1) in {p.name for p in self.project.papers()} else None
                if not f:
                    return h.send_error_json(HTTPStatus.NOT_FOUND, "no such edition")
                return h.send_bytes(HTTPStatus.OK, "application/pdf", f.read_bytes())
            if method == "GET" and path == "/api/macros":
                tex = self.project.main_tex(paper) if paper else None
                return h.send_json(paper_macros(tex) if tex else paper_macros(Path("/nonexistent")))
            if method == "GET" and path == "/api/state":
                return h.send_json({"changed": self.project.changed(paper), "warmup": self.warm.state, "agent": agent.agent_state(),
                                    "jobs_running": self.jobs.running()})
            if method == "GET" and path == "/api/attest/options":
                return h.send_json(self.attestor.options(paper))
            if method == "POST" and path == "/api/attest/preview":
                b = h.read_json()
                return h.send_json(self.attestor.preview(
                    b.get("paper") or None, b.get("kind", "claim"), _strs(b, "targets"), str(b.get("level", "")),
                    str(b.get("reason", "")), _strs(b, "checklist"), str(b.get("key", ""))))
            if method == "POST" and path == "/api/attest":
                return h.send_json({"job": self.attestor.start(str(h.read_json().get("preview", "")))})
            m = re.fullmatch(r"/api/attest/jobs/([A-Za-z0-9_-]+)", path)
            if method == "GET" and m:
                j = self.attestor.job(m.group(1))
                return h.send_json(j) if j else h.send_error_json(HTTPStatus.NOT_FOUND, "unknown job")
            if method == "POST" and path == "/api/attest/undo":
                return h.send_json(self.attestor.undo())
            if method == "GET" and path == "/api/jobs":
                return h.send_json({"jobs": self.jobs.list(), "kinds": KINDS})
            if method == "POST" and path == "/api/jobs":
                b = h.read_json()
                jp = b.get("paper") or None
                if jp is not None and jp not in {p.name for p in self.project.papers()}:
                    return h.send_error_json(HTTPStatus.NOT_FOUND, f"unknown paper {jp}")
                return h.send_json({"job": self.jobs.start(str(b.get("kind", "")), jp, _strs(b, "targets"),
                                                           b.get("confirm") is True)})
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)", path)
            if method == "GET" and m:
                try:
                    since = int(one("since", "0"))
                except ValueError:
                    since = 0
                j = self.jobs.get(m.group(1), since)
                return h.send_json(j) if j else h.send_error_json(HTTPStatus.NOT_FOUND, "unknown job")
            m = re.fullmatch(r"/api/jobs/([A-Za-z0-9_-]+)/cancel", path)
            if method == "POST" and m:
                self.jobs.cancel(m.group(1))
                return h.send_json({"ok": True})
            m = re.fullmatch(r"/api/packs/([A-Za-z0-9_-]+)\.pdf", path)
            if method == "GET" and m:
                f = self.jobs.pack_pdf(m.group(1))
                if not f or not f.is_file():
                    return h.send_error_json(HTTPStatus.NOT_FOUND, "no such pack")
                return h.send_bytes(HTTPStatus.OK, "application/pdf", f.read_bytes())
            if method == "POST" and path == "/api/reload":
                self.project.load(paper, force=True)
                agent.forget()
                return h.send_json({"ok": True})
        except (AttestError, JobError) as e:
            return h.send_error_json(HTTPStatus.BAD_REQUEST, str(e))
        except ToolError as e:
            return h.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))
        return h.send_error_json(HTTPStatus.NOT_FOUND, "no such endpoint")

    def meta(self, name: str) -> papermeta.PaperMeta:
        return papermeta.load(self.project.cfg.paper_toml, self.project.root, name, self.project.paper(name).main)

    def papers_overview(self):
        out = []
        for p in self.project.papers():
            e = self.project._cache.get(p.name)
            meta = self.meta(p.name)
            out.append(dict(name=p.name, main=p.main, state=self.warm.state.get(p.name, "loading"),
                            counts=e["data"]["counts"] if e else None, root=e["data"]["root"] if e else None,
                            title=meta.title, editions=sorted(meta.pdfs), meta_warnings=meta.warnings))
        return dict(papers=out, project=self.project.root.name, person=self.project.cfg.person,
                    key=self.project.cfg.key)
