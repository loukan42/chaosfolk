"""Cleanup also runs when startup validation or the caller is interrupted."""
import asyncio
import io
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from chaosfolk import campaigns, chaos, chaos_jobs


def fake_process():
    return SimpleNamespace(pid=123, poll=Mock(return_value=None), kill=Mock(), wait=Mock(return_value=0),
                           stdout=io.BytesIO())


def test_hook_identity_lookup_failure_still_reaps_the_spawned_process(monkeypatch):
    process = fake_process()
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(chaos, "identity_for", Mock(side_effect=OSError("identity unavailable")))
    with pytest.raises(OSError, match="identity unavailable"):
        asyncio.run(chaos.execute(["trusted-runner"], {}, 1, capture=True))
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    assert process.stdout.closed


def test_job_identity_lookup_failure_still_reaps_the_spawned_process(tmp_path, monkeypatch):
    process = fake_process()
    monkeypatch.setattr(campaigns, "home", lambda: tmp_path)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(chaos, "identity_for", Mock(side_effect=OSError("identity unavailable")))
    job = chaos_jobs.validate_job({"name": "job", "argv": ["trusted-runner"], "max_runs": 1,
                                  "environment": "test"}, tmp_path)
    with pytest.raises(OSError, match="identity unavailable"):
        asyncio.run(chaos_jobs.run_job(job, 1))
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
    assert process.stdout.closed


def test_hook_without_capture_cancellation_reaps_the_child(monkeypatch):
    processes = []
    spawn = subprocess.Popen

    def record(*args, **kwargs):
        process = spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", record)

    async def run():
        task = asyncio.create_task(chaos.execute([sys._base_executable, "-c", "import time; time.sleep(5)"], {}, 10))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len(processes) == 1
    assert processes[0].poll() is not None


def test_scheduler_closes_database_when_schema_initialization_fails(tmp_path, monkeypatch):
    connection = SimpleNamespace(execute=Mock(side_effect=sqlite3.DatabaseError("corrupt database")), close=Mock())
    monkeypatch.setattr(campaigns, "home", lambda: tmp_path)
    monkeypatch.setattr(chaos_jobs.sqlite3, "connect", lambda *args, **kwargs: connection)
    with pytest.raises(sqlite3.DatabaseError, match="corrupt"):
        with chaos_jobs.store():
            pytest.fail("Invalid database cannot expose a transaction")
    connection.close.assert_called_once()
