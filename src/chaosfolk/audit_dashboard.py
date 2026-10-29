"""Loopback-only audit dashboard, backed by the session database."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

ASSETS = Path(__file__).with_name("templates")
MAX_BODY = 128 * 1024


def make_server(session, port=0, token=None):
    token = token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_):
            pass  # Never put bearer tokens or local evidence in access logs.

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, code, data=b"", content_type="application/json; charset=utf-8"):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            try:
                self.end_headers()
                if data:
                    self.wfile.write(data)
            except (ConnectionError, OSError):
                self.close_connection = True

        def allowed_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

        def authenticated(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {"error": "Invalid host"})
            url = urlsplit(self.path)
            assets = {"/": ("audit-live.html", "text/html; charset=utf-8"),
                      "/audit-live.js": ("audit-live.js", "text/javascript; charset=utf-8"),
                      "/audit-live.css": ("audit-live.css", "text/css; charset=utf-8")}
            if url.path in assets:
                name, mime = assets[url.path]
                return self.reply(200, (ASSETS / name).read_bytes(), mime)
            if not self.authenticated():
                return self.reply(403, {"error": "Dashboard access token required"})
            if url.path == "/api/state":
                try:
                    query = parse_qs(url.query)
                    after = int(query["after"][0]) if "after" in query else None
                    session.gate()  # Enforce elapsed-time limits even without an engine.
                    value = session.snapshot(after=after)
                    return self.reply(204 if value is None else 200, b"" if value is None else value)
                except (ValueError, OSError) as error:
                    return self.reply(400, {"error": str(error)})
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if (not self.allowed_host() or not self.authenticated()
                    or origin not in {None, f"http://{self.headers.get('Host')}"}):
                return self.reply(403, {"error": "Request not authorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    self.close_connection = True
                    return self.reply(400, {"error": "Expected a bounded JSON request"})
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/selection":
                    if set(value) - {"depth", "excluded", "limits"}:
                        raise ValueError("Unknown selection field")
                    result = session.configure(**value)
                elif self.path == "/api/start":
                    result = session.start()
                elif self.path == "/api/stop":
                    result = session.stop()
                else:
                    return self.reply(404, {"error": "Not found"})
                return self.reply(200, result)
            except (ValueError, OSError, TypeError) as error:
                return self.reply(400, {"error": str(error)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.audit_token = token
    return server


def serve(session, port=0):
    session.snapshot()  # Fail before serving if the session is missing/corrupt.
    server = make_server(session, port)
    import os
    record = {"port": server.server_port, "token": server.audit_token, "pid": os.getpid()}
    path = session.folder / "audit-dashboard.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record), encoding="utf-8")
    temporary.replace(path)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()


def launch(session):
    session.snapshot()
    path = session.folder / "audit-dashboard.json"

    def current():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            url = f"http://127.0.0.1:{int(record['port'])}"
            request = Request(url + "/api/state", headers={"Authorization": "Bearer " + record["token"]})
            with urlopen(request, timeout=1) as response:
                value = json.load(response)
            if value["config"]["created"] != session.snapshot()["config"]["created"]:
                return None
            return {"url": url + "/#" + record["token"], "folder": str(session.folder)}
        except (OSError, ValueError, KeyError):
            return None

    ready = current()
    if ready:
        return ready
    log = session.folder / "audit-dashboard.log"
    with log.open("ab") as stream:
        process = subprocess.Popen([sys.executable, "-m", "chaosfolk", "audit-run", "serve", "--folder", str(session.folder)],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=sys.platform != "win32")
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Dashboard stopped; inspect audit-dashboard.log")
        ready = current()
        if ready:
            return ready
        time.sleep(0.1)
    raise RuntimeError("Dashboard startup is pending; rerun dashboard to recover its URL")
