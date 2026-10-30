"""Loopback-only audit dashboard, backed by the session database."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import threading
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.error import URLError

ASSETS = Path(__file__).with_name("templates")
MAX_BODY = 128 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


def request_local(record, path, body=None):
    port = record.get("port")
    token = record.get("token")
    if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str) or not token:
        raise ValueError("Invalid local dashboard record")
    headers = {"Authorization": "Bearer " + token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(f"http://127.0.0.1:{port}" + path, data=body, headers=headers)
    return build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=2)


def client_message(error):
    """Validation messages are written for the client; OS and type errors may quote local paths or signatures."""
    if type(error) is ValueError:
        return str(error)
    print(f"audit dashboard: {type(error).__name__}: {error}", file=sys.stderr)
    return "Request could not be processed"


def make_server(session, port=0, token=None, idle_seconds=900):
    token = token or secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        error_message_format = '{"error": "%(code)d %(message)s"}'
        error_content_type = "application/json; charset=utf-8"

        def log_message(self, *_):
            pass  # Never put bearer tokens or local evidence in access logs.

        def version_string(self):
            return "chaosfolk"  # No Python or stdlib version in the Server header.

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
            try:
                valid = hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)
            except TypeError:
                valid = False
            if valid:
                self.server.last_seen = time.monotonic()
            return valid

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
                    return self.reply(400, {"error": client_message(error)})
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if (not self.allowed_host() or not self.authenticated()
                    or origin not in {None, f"http://{self.headers.get('Host')}"}):
                self.close_connection = True
                # Drain a bounded body before closing, otherwise Windows may
                # reset the connection before the client receives its 403.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if 0 < length <= MAX_BODY:
                        self.rfile.read(length)
                except (OSError, ValueError):
                    pass
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
                    if set(value) - {"depth", "excluded", "limits", "test_id", "enabled", "reset"}:
                        raise ValueError("Unknown selection field")
                    result = session.configure(**value)
                elif self.path == "/api/start":
                    if set(value) - {"expected_revision"}:
                        raise ValueError("Unknown start field")
                    revision = value.get("expected_revision")
                    if revision is not None and (type(revision) is not int or revision < 0):
                        raise ValueError("Expected a nonnegative revision")
                    result = session.start(expected_revision=revision)
                elif self.path == "/api/stop":
                    result = session.stop()
                elif self.path == "/api/shutdown":
                    self.reply(200, {"ok": True, "closed": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                else:
                    return self.reply(404, {"error": "Not found"})
                return self.reply(200, result)
            except (ValueError, OSError, TypeError) as error:
                return self.reply(400, {"error": client_message(error)})

    class Server(ThreadingHTTPServer):
        def service_actions(self):
            if idle_seconds and not self.expiring and time.monotonic() - self.last_seen >= idle_seconds:
                self.expiring = True
                threading.Thread(target=self.shutdown, daemon=True).start()

    server = Server(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.audit_token = token
    server.last_seen, server.expiring = time.monotonic(), False
    return server


def serve(session, port=0):
    from .private_state import session_directory
    session_directory(session.folder)
    session.snapshot()  # Fail before serving if the session is missing/corrupt.
    server = make_server(session, port)
    import os
    record = {"port": server.server_port, "token": server.audit_token, "pid": os.getpid()}
    path = session.folder / "audit-dashboard.json"
    from .private_state import write_json
    write_json(path, record)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        try:
            if json.loads(path.read_text(encoding="utf-8")) == record:
                path.unlink()
        except (OSError, ValueError):
            pass


def launch(session):
    from .private_state import session_directory
    session_directory(session.folder)
    session.snapshot()
    path = session.folder / "audit-dashboard.json"

    def current():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            with request_local(record, "/api/state") as response:
                value = json.load(response)
            if value["config"]["created"] != session.snapshot()["config"]["created"]:
                return None
            return {"url": f"http://127.0.0.1:{record['port']}/#" + record["token"], "folder": str(session.folder)}
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


def close(session):
    path = session.folder / "audit-dashboard.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ok": True, "closed": False}
    try:
        with request_local(record, "/api/shutdown", b"{}") as response:
            return json.load(response)
    except URLError as error:
        if isinstance(error.reason, (ConnectionRefusedError, ConnectionResetError)):
            return {"ok": True, "closed": False}
        raise
