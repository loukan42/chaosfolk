"""Regressions for stop admission, resumption and privacy scope."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
from types import SimpleNamespace

import pytest

from chaosfolk import checks, engine, privacy
from chaosfolk.audit_session import Session, catalog


def session_at(folder):
    session = Session(folder)
    session.create("deep", max_seconds=120)
    source = checks.load()
    (folder / "fields.json").write_text(json.dumps({"pages":[{
        "url":"http://localhost:3000/", "kinds":[k["id"] for k in source["kinds"]]+["text"],
        "features":list(source["features"])}]}), encoding="utf-8")
    session.refresh(True)
    session.start()
    return session


def report_data(path):
    html = path.read_text(encoding="utf-8")
    start = re.search(r"\bconst\s+data\s*=\s*JSON.parse\(", html).end()
    return json.loads(json.JSONDecoder().raw_decode(html[start:])[0])


@pytest.mark.parametrize("interruption", ["stop", "exclusion"])
def test_stop_during_fault_admission_prevents_injection(tmp_path, interruption):
    engine.charger_moteur()
    session = session_at(tmp_path)
    applied = []

    async def admit(fault, horde):
        # Reproduces the user pressing Stop while an async admission hook runs.
        await asyncio.sleep(0)
        if interruption == "stop":
            session.stop()
        else:
            session.configure(excluded=[item["id"] for item in catalog().values() if item["fault"] == "offline"])
        return None

    async def apply(fault):
        applied.append(session.snapshot()["config"]["state"])

    horde = object.__new__(engine.Horde)
    horde.audit_session = session
    async def release(fault):
        fault['released'] = True

    horde.chaos = SimpleNamespace(admit=admit, release=release, dry_run=lambda: False)
    horde.humains = {"h01":SimpleNamespace(appliquer=apply)}
    horde.horodatage = lambda: 100
    horde.journal = lambda event: None
    fault = {"id":"audit-fault", "lot":"audit", "type":"offline", "phase":"admission", "h":"h01"}
    asyncio.run(horde.activer(fault, 0))
    assert not applied, f"Fault was applied after stop: {applied}"
    assert fault["released"] and fault["phase"] == "annulee"


def test_privacy_export_keeps_selected_scope_without_private_material(tmp_path):
    source, public = tmp_path / "source", tmp_path / "public"
    session = session_at(source)
    session.configure(excluded=["email-formats"])
    (source / "constats.json").write_text('{"constats":[]}', encoding="utf-8")
    (source / "journal.jsonl").write_text("", encoding="utf-8")
    (source / "audit-dashboard.json").write_text('{"token":"AUDIT-PRIVATE-TOKEN"}', encoding="utf-8")
    (source / "personas.json").write_text(json.dumps({"humains": [{"id": "h01", "audit_tasks": [
        {"task_id": "synthetic", "claim": "PRIVATE-WORKER-CLAIM"}]}]}), encoding="utf-8")
    engine.rapport(source, "fr")
    assert report_data(source / "rapport.html")["audit_session"]["config"]["excluded"] == ["email-formats"]
    privacy.export_report(source, public, "fr")
    assert not (public / "audit.sqlite3").exists()
    assert not (public / "audit-dashboard.json").exists()
    for path in public.rglob("*"):
        if path.is_file():
            assert b"AUDIT-PRIVATE-TOKEN" not in path.read_bytes()
            assert b"PRIVATE-WORKER-CLAIM" not in path.read_bytes()
    shared = report_data(public / "rapport.html")
    assert shared.get("audit_session"), "The sanitized report lost all audit coverage and exclusions"
    assert shared["audit_session"]["config"]["excluded"] == ["email-formats"]
    assert set(shared["audit_session"]["config"]) == {"depth", "excluded"}
    second = tmp_path / "public-again"
    privacy.export_report(public, second, "fr")
    assert report_data(second / "rapport.html")["audit_session"] == shared["audit_session"]


def test_resume_retries_only_interrupted_attempts_and_rejects_stale_claim(tmp_path):
    session = session_at(tmp_path)
    first, second = session.claim("original", "agent", 2)["tasks"]
    session.record(first["task_id"], "inconclusive", "Expected behavior could not be established",
                   owner="original", claim=first["claim"])
    session.stop()
    session.record(second["task_id"], "inconclusive", "Interrupted by user",
                   owner="original", claim=second["claim"], retryable=True)
    session.start()
    retried = session.claim("replacement", "agent", 25)["tasks"]
    assert first["task_id"] not in {task["task_id"] for task in retried}
    assert second["task_id"] in {task["task_id"] for task in retried}
    with pytest.raises(ValueError, match="claim"):
        session.record(second["task_id"], "inconclusive", "Late result", owner="original", claim=second["claim"])
    session.release("replacement")
    assert second["task_id"] in {task["task_id"] for task in session.claim("third", "agent", 25)["tasks"]}


@pytest.mark.browser
@pytest.mark.parametrize("resume_during_cleanup", [False, True])
def test_interrupted_tool_can_be_reclaimed_after_resume(tmp_path, monkeypatch, resume_during_cleanup):
    session = session_at(tmp_path)
    chosen = next(x for x in catalog().values() if x["configurable"] and x["executor"]=="coordinator" and not x["requires"])
    session.configure(excluded=[x["id"] for x in catalog().values() if x["configurable"] and x["id"] != chosen["id"]])
    task = session.claim("coordinator", "coordinator", 1)["tasks"][0]
    arrived, release = threading.Event(), threading.Event()
    if resume_during_cleanup:
        from chaosfolk.owned_process import OwnedProcess
        original_close = OwnedProcess.close

        def close_while_resuming(process):
            session.start()
            original_close(process)

        monkeypatch.setattr(OwnedProcess, "close", close_while_resuming)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            arrived.set()
            release.wait(20)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<title>Audit fixture</title>")
            except (OSError, ConnectionError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1",0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(session.execute,task["task_id"],["probe",f"http://127.0.0.1:{server.server_port}/",
                 "--clients","1","--rounds","1","--output",str(tmp_path / "tool-output")])
            assert arrived.wait(15)
            session.stop()
            result = running.result(timeout=15)
            assert result["status"] == "inconclusive"
        assert session.start()["ok"]
        session.release("coordinator")
        retry = session.claim("replacement","coordinator",1)["tasks"]
        assert retry and retry[0]["task_id"]==task["task_id"], "Interrupted task remains unresolved but cannot be reclaimed"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(5)
