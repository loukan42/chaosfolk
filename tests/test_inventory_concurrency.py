"""Concurrent page discovery must retain every route and its eligible checks."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from chaosfolk import checks
from chaosfolk.audit_session import Session
from chaosfolk.private_state import read_json


def test_overlapping_page_saves_keep_both_routes(tmp_path, monkeypatch):
    path = tmp_path / "fields.json"
    path.write_text('{"pages": []}')
    first_read, second_finished = threading.Event(), threading.Event()
    original_read = Path.read_text

    def read_with_overlap(target, *args, **kwargs):
        content = original_read(target, *args, **kwargs)
        if target == path and threading.current_thread().name.startswith("first"):
            first_read.set()
            # Without serialization the second writer commits this same old
            # inventory before the first writer resumes and overwrites it.
            second_finished.wait(.3)
        return content

    def second():
        assert first_read.wait(5)
        try:
            checks.save_page(path, {"url": "http://localhost/settings", "kinds": ["phone"]})
        finally:
            second_finished.set()

    monkeypatch.setattr(Path, "read_text", read_with_overlap)
    with ThreadPoolExecutor(1, thread_name_prefix="first") as first_pool, ThreadPoolExecutor(1) as second_pool:
        first = first_pool.submit(checks.save_page, path, {"url": "http://localhost/signup", "kinds": ["email"]})
        later = second_pool.submit(second)
        first.result(timeout=10)
        later.result(timeout=10)
    assert {page["url"] for page in json.loads(path.read_text())["pages"]} == {
        "http://localhost/signup", "http://localhost/settings"}


def test_refresh_reads_inventory_after_acquiring_session_transaction(tmp_path, monkeypatch):
    session = Session(tmp_path)
    session.create("deep")
    path = tmp_path / "fields.json"
    checks.save_page(path, {"url": "http://localhost/signup", "kinds": ["email"], "features": ["form"]})
    waiting, release = threading.Event(), threading.Event()
    original_db = session.db

    @contextmanager
    def delayed_db(write=False):
        if threading.current_thread().name.startswith("delayed"):
            waiting.set()
            assert release.wait(5)
        with original_db(write) as db:
            yield db

    monkeypatch.setattr(session, "db", delayed_db)
    with ThreadPoolExecutor(1, thread_name_prefix="delayed") as pool:
        earlier = pool.submit(session.refresh, True)
        assert waiting.wait(5)
        try:
            checks.save_page(path, {"url": "http://localhost/settings", "kinds": ["phone"], "features": ["form"]})
            session.refresh(True)
        finally:
            release.set()
        earlier.result(timeout=5)
    tasks = session.snapshot(details=True)["tasks"]
    assert any(task["check_id"] == "phone-formats" and task["route"] == "http://localhost/settings"
               and task["eligibility"] == "eligible" for task in tasks)


def test_inventory_merge_serializes_separate_cli_processes(tmp_path):
    path = tmp_path / "fields.json"
    path.write_text('{"pages": []}')
    script = """
import sys, time
from pathlib import Path
from chaosfolk.checks import save_page
path, worker = Path(sys.argv[1]), sys.argv[2]
original = Path.read_text
def slow_read(target, *args, **kwargs):
    result = original(target, *args, **kwargs)
    if target == path:
        time.sleep(.01)
    return result
Path.read_text = slow_read
print('ready', flush=True)
sys.stdin.readline()
for number in range(8):
    save_page(path, {'url': 'http://localhost/' + worker + '/' + str(number)})
"""
    processes = []
    try:
        for worker in range(3):
            process = subprocess.Popen([sys.executable, "-c", script, str(path), str(worker)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            processes.append(process)
            assert process.stdout.readline().strip() == "ready"
        for process in processes:
            process.stdin.write("start\n")
            process.stdin.flush()
        deadline = time.monotonic() + 15
        while any(process.poll() is None for process in processes):
            # Production readers tolerate Windows' transient sharing collision
            # while still rejecting incomplete or malformed JSON.
            assert isinstance(read_json(path)["pages"], list)
            assert time.monotonic() < deadline
            time.sleep(.005)
        for process in processes:
            assert process.returncode == 0, process.stderr.read()
        assert len(json.loads(path.read_text())["pages"]) == 24
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
