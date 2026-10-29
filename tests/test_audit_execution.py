from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

import pytest

from chaosfolk.audit_session import Session
from test_browser import fixture_url  # noqa: F401
from test_audit_session import inventory

pytestmark = pytest.mark.browser


def test_execute_runs_real_tool_and_cancels_owned_process_on_stop(tmp_path, fixture_url):  # noqa: F811
    session = Session(tmp_path)
    session.create("deep", max_seconds=120)
    inventory(tmp_path)
    session.refresh()
    session.start()
    tasks = session.claim("coordinator", "coordinator", 2)["tasks"]
    arrived, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            arrived.set()
            release.wait(15)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<title>Slow test fixture</title>")
            except (BrokenPipeError, ConnectionError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            execution = pool.submit(session.execute, tasks[0]["task_id"], ["probe", f"http://127.0.0.1:{server.server_port}/",
                     "--clients", "1", "--rounds", "1", "--output", str(tmp_path / "interrupted")])
            assert arrived.wait(15), "The real browser never reached the test app"
            session.stop()
            result = execution.result(timeout=15)
            assert not result["ok"] and result["status"] == "inconclusive"
            assert "Stopped by user" in result["reason"]
            assert (tmp_path / result["evidence"]).is_file()
        session.start()
        completed = session.execute(tasks[1]["task_id"], ["probe", fixture_url,
                    "--clients", "1", "--rounds", "1", "--output", str(tmp_path / "completed")])
        assert completed["ok"] and completed["status"] == "measured"
        assert json.loads((tmp_path / "completed/probe.json").read_text())["valid_count"] == 1
        assert session.snapshot()["tested"] == 0
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join(5)
