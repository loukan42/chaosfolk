"""Local preview: the landing page on :8080, the API on :8000 and a worker using the offline demo runner.

    python web/dev.py

No model, Docker or Turnstile is needed. Every audit produces the bundled demo report, whatever the URL.
"""
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn  # noqa: E402

from chaosfolk_web import worker  # noqa: E402
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
    settings = replace(Settings(), data_dir=data, runner="demo", public_url=API, daily_quota=5, per_ip_daily=5,
                       allowed_origins=("http://127.0.0.1:8080", "http://localhost:8080"))
    threading.Thread(target=worker.loop, args=(settings,), daemon=True).start()
    site = ThreadingHTTPServer(("127.0.0.1", 8080), partial(SiteHandler, directory=str(SITE)))
    threading.Thread(target=site.serve_forever, daemon=True).start()
    print("Landing page: http://127.0.0.1:8080/  API: " + API, flush=True)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
