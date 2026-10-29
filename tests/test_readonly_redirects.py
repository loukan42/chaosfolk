"""A browser redirect must not dispatch a request outside the authorized origin."""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from types import SimpleNamespace

import pytest

from chaosfolk import integrations, probe

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("adapter", ["probe", "axe"])
@pytest.mark.parametrize("redirect_at", ["navigation", "resource", None])
def test_readonly_browser_checks_guard_redirects(tmp_path, adapter, redirect_at):
    unauthorized = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.server is other:
                unauthorized.append(self.path)
                body = b"/* unauthorized target */"
            elif (redirect_at == "navigation" or
                  (redirect_at == "resource" and self.path == "/asset.js")):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{other.server_port}/target")
                self.end_headers()
                return
            else:
                body = b'<html><head><title>Fixture</title></head><body><script src="/asset.js"></script></body></html>' if self.path == "/" else b"/* local asset */"
            self.send_response(200)
            self.send_header("Content-Type", "text/html" if self.path == "/" else "application/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    other = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    allowed = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in (other, allowed)]
    for worker in workers:
        worker.start()
    try:
        url = f"http://127.0.0.1:{allowed.server_port}/"
        if adapter == "probe":
            result = asyncio.run(probe.run(SimpleNamespace(url=url, rounds=1, clients=1), tmp_path))
            status = result["attempts"][0]["outcome"]
        else:
            script = tmp_path / "axe.js"
            script.write_text('window.axe={version:"fixture",run:async()=>({violations:[],incomplete:[]})}')
            result = asyncio.run(integrations.axe_audit(url, script))
            status = result["status"]
        assert unauthorized == [], "The browser contacted the redirect target without authorization"
        if redirect_at:
            assert status == "inconclusive"
            assert "Redirect refused" in str(result)
        else:
            assert status == ("ok" if adapter == "probe" else "passed")
    finally:
        for server in (other, allowed):
            server.shutdown()
            server.server_close()
        for worker in workers:
            worker.join(5)
