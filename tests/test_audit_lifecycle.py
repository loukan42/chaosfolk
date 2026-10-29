import json
from contextlib import suppress
import os
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psutil
import pytest

from chaosfolk import engine, integrations
from chaosfolk.audit_dashboard import launch, close, make_server
from chaosfolk.audit_session import Session


@pytest.mark.parametrize("finish", ["normal", "timeout", "error"])
def test_external_runner_reaps_descendants_even_after_parent_exit(tmp_path, finish):
    pid_file = tmp_path / "child.pid"
    script = tmp_path / "runner.py"
    script.write_text("import json,os,subprocess,sys,time\nfrom pathlib import Path\n"
        "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
        f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
        "Path(os.environ['CHAOSFOLK_RESULT_PATH']).write_text(json.dumps({'tests':1,'failures':0,'errors':0,'skipped':0}))\n"
        + ("time.sleep(30)\n" if finish == "timeout" else "time.sleep(.1)\n")
        + ("sys.exit(7)\n" if finish == "error" else ""), encoding="utf-8")
    child = None
    try:
        result = integrations.run_external("appium", sys.executable, script, timeout=2)
        try:
            child = psutil.Process(int(pid_file.read_text()))
            assert not child.is_running() or child.status() == psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            pass
        assert result["status"] == ("passed" if finish == "normal" else "error")
        if finish == "timeout":
            assert result["reason"] == "timeout"
    finally:
        if child is not None and child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
            child.kill()
            child.wait(timeout=5)


def test_dashboard_closes_its_own_server_and_removes_credentials(tmp_path):
    session = Session(tmp_path)
    session.create()
    launch(session)
    record = json.loads((tmp_path / "audit-dashboard.json").read_text())
    identity = engine.process_identity(record["pid"])
    dashboard = psutil.Process(record["pid"])
    try:
        result = close(session)
        assert result["closed"]
        deadline = time.monotonic() + 5
        while (tmp_path / "audit-dashboard.json").exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert not (tmp_path / "audit-dashboard.json").exists()
        assert close(session) == {"ok": True, "closed": False}
        assert session.snapshot()["config"]["state"] == "ready"
        with suppress(psutil.NoSuchProcess):
            dashboard.wait(timeout=5)
    finally:
        # The server can finish before cleanup; never kill a PID reused meanwhile.
        with suppress(ValueError):
            engine.stop_owned_process(identity)


def test_dashboard_idle_server_exits_without_clients(tmp_path):
    session = Session(tmp_path)
    session.create()
    server = make_server(session, idle_seconds=.05)
    worker = threading.Thread(target=lambda: server.serve_forever(poll_interval=.01), daemon=True)
    worker.start()
    try:
        worker.join(5)
        assert not worker.is_alive()
    finally:
        server.shutdown()
        server.server_close()


def test_rejected_dashboard_posts_keep_server_and_session_available(tmp_path):
    session = Session(tmp_path)
    session.create()
    server = make_server(session)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for _ in range(12):
            request = Request(base + "/api/shutdown", data=b'{}', headers={"Content-Type": "application/json"})
            with pytest.raises(HTTPError) as rejected:
                urlopen(request, timeout=5)
            assert rejected.value.code == 403
            rejected.value.close()
        with urlopen(Request(base + "/api/state", headers={"Authorization": "Bearer " + server.audit_token}), timeout=5) as response:
            assert json.load(response)["config"]["state"] == "ready"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_private_state_never_changes_hardlinked_external_file(tmp_path):
    from chaosfolk.private_state import session_directory
    outside = tmp_path / "outside.json"
    outside.write_text("private fixture")
    before = outside.stat().st_mode
    folder = tmp_path / "session"
    folder.mkdir()
    os.link(outside, folder / "linked.json")
    with pytest.raises(ValueError, match="hard-linked"):
        session_directory(folder)
    assert outside.stat().st_mode == before
    assert outside.read_text() == "private fixture"


def test_audit_database_refuses_external_hardlink(tmp_path):
    original = Session(tmp_path / "original")
    original.create()
    linked = Session(tmp_path / "linked")
    linked.folder.mkdir()
    os.link(original.path, linked.path)
    with pytest.raises(ValueError, match="private file"):
        linked.snapshot()


def test_private_state_refuses_repository_root_and_seals_existing_files(tmp_path):
    from chaosfolk.private_state import session_directory
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".git").mkdir()
    with pytest.raises(ValueError, match="dedicated"):
        session_directory(repository)
    session = tmp_path / "session"
    session.mkdir()
    state = session / "serveur.json"
    state.write_text('{"jeton_chef":"synthetic"}')
    session_directory(session)
    if os.name == "nt":
        # Translate the actual DACL to SID form; broad local groups must be absent.
        command = "$acl=Get-Acl -LiteralPath $env:CHAOSFOLK_TEST_ACL_PATH; $acl.Access | ForEach-Object {$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value}"
        result = subprocess.run(["powershell", "-NoProfile", "-Command", command],
            env=dict(os.environ, CHAOSFOLK_TEST_ACL_PATH=str(state)), capture_output=True, text=True, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert "S-1-5-32-545" not in result.stdout  # Users
        assert "S-1-5-11" not in result.stdout      # Authenticated users
        assert "S-1-1-0" not in result.stdout       # Everyone
    else:
        assert session.stat().st_mode & 0o077 == 0
        assert state.stat().st_mode & 0o077 == 0
