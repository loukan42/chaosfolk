"""Local preview: the landing page on :8080 and the API on :8000, in local mode (SQLite, files and the
offline Chaosfolk demo instead of Vercel). No account, model or Turnstile is needed.

    python web/dev.py

Every audit produces the bundled demo report, whatever the URL.
"""
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn  # noqa: E402

from chaosfolk_web import engine  # noqa: E402
from chaosfolk_web.app import create_app  # noqa: E402
from chaosfolk_web.config import Settings  # noqa: E402

SITE = Path(__file__).resolve().parent.parent / "site"
API = "http://127.0.0.1:8000"


class SiteHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/config.js":
            body = f'window.CHAOSFOLK_CONFIG = {{ apiBase: "{API}", turnstileSiteKey: "" }};\n'.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *_):
        pass


def main():
    data = Path(__file__).resolve().parent.parent / ".horde" / "web-dev"
    settings = replace(Settings(), mode="local", data_dir=data, public_url=API, daily_quota=5, per_ip_daily=5,
                       allowed_origins=("http://127.0.0.1:8080", "http://localhost:8080"))
    app = create_app(settings)
    state = app.state

    def keep_ticking():
        # On Vercel, polls and the daily cron move the queue; here a thread does it too.
        while True:
            engine.tick(settings, state.store, state.reports, state.backend)
            time.sleep(2)

    threading.Thread(target=keep_ticking, daemon=True).start()
    site = ThreadingHTTPServer(("127.0.0.1", 8080), partial(SiteHandler, directory=str(SITE)))
    threading.Thread(target=site.serve_forever, daemon=True).start()
    print("Landing page: http://127.0.0.1:8080/  API: " + API, flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
