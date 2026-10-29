"""Real child-process checks for hook capture and scheduled log budgets."""
import asyncio
import os
import sys
import time

import psutil
import pytest

from chaosfolk import campaigns, chaos, chaos_jobs, engine


@pytest.mark.parametrize("size", [65535, 65536])
def test_hook_capture_accepts_output_up_to_the_limit(size):
    result = asyncio.run(chaos.execute(
        [sys.executable, "-c", f"import sys; sys.stdout.write('x' * {size})"], {}, 5, capture=True))
    assert result == (0, "x" * size)


def test_hook_capture_preserves_stdin_environment_exit_code_and_stripping():
    script = "import json,os,sys; value=json.load(sys.stdin); print(os.environ['QA_OUTPUT_TEST']+value['value']); sys.exit(7)"
    result = asyncio.run(chaos.execute([sys.executable, "-c", script], {"value": "payload"}, 5,
                                      env=dict(os.environ, QA_OUTPUT_TEST="prefix-"), capture=True))
    assert result == (7, "prefix-payload")


def test_hook_overflow_stops_the_owned_process_before_further_work(tmp_path, monkeypatch):
    pid_file, later = tmp_path / "pid", tmp_path / "must-not-run"
    script = (f"import os,sys,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); "
              "sys.stdout.write('x' * 65537); sys.stdout.flush(); time.sleep(10); "
              f"Path({str(later)!r}).touch()")
    stopped = []
    original = engine.stop_owned_process

    def stop(identity):
        stopped.append(identity["pid"])
        return original(identity)

    monkeypatch.setattr(engine, "stop_owned_process", stop)
    with pytest.raises(chaos.OutputLimitExceeded, match="output-limit") as error:
        asyncio.run(chaos.execute([sys.executable, "-c", script], {}, 5, capture=True))
    assert error.value.exit_code == 125
    pid = int(pid_file.read_text())
    # Windows virtualenv launchers can create a separate interpreter child.
    assert stopped and not psutil.pid_exists(pid)
    assert not later.exists()


def test_hook_capture_timeout_with_no_output_reaps_process(tmp_path):
    pid_file = tmp_path / "pid"
    script = f"import os,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(10)"
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        asyncio.run(chaos.execute([sys.executable, "-c", script], {}, 1, capture=True))
    assert time.monotonic() - started < 5
    assert not psutil.pid_exists(int(pid_file.read_text()))


def test_hook_returns_when_it_exits_although_a_child_keeps_its_output_open(tmp_path):
    pid_file = tmp_path / "child-pid"
    script = ("import subprocess,sys; from pathlib import Path; "
              "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)']); "
              f"Path({str(pid_file)!r}).write_text(str(child.pid)); print('done'); sys.exit(3)")
    started = time.monotonic()
    try:
        result = asyncio.run(chaos.execute([sys.executable, "-c", script], {}, 5, capture=True))
        # The hook's own exit code and output come back without waiting for the pipe to close.
        assert result == (3, "done")
        assert time.monotonic() - started < 2
    finally:
        try:
            child = psutil.Process(int(pid_file.read_text()))
            child.kill()
            child.wait(timeout=5)
        except (psutil.NoSuchProcess, FileNotFoundError, ValueError):
            pass


def test_job_log_stops_at_byte_limit_and_returns_output_limit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "home", lambda: tmp_path)
    pid_file = tmp_path / "pid"
    script = (f"import os,sys,time; from pathlib import Path; Path({str(pid_file)!r}).write_text(str(os.getpid())); "
              "sys.stderr.write('z' * 4096); sys.stderr.flush(); time.sleep(10)")
    job = chaos_jobs.validate_job({"name": "loud", "argv": [sys.executable, "-c", script], "max_runs": 1,
                                   "environment": "local", "max_log_bytes": 1024, "timeout": 5}, tmp_path)
    assert asyncio.run(chaos_jobs.run_job(job, 1)) == 125
    log = tmp_path / "chaos-job-logs" / "loud" / job["id"] / "run-1.log"
    assert log.read_bytes() == b"z" * 1024
    assert not psutil.pid_exists(int(pid_file.read_text()))


def test_job_preserves_normal_output_and_exit_status(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "home", lambda: tmp_path)
    job = chaos_jobs.validate_job({"name": "normal", "argv": [sys.executable, "-c",
        "import sys; print('out',flush=True); print('error',file=sys.stderr,flush=True); sys.exit(7)"],
        "max_runs": 1, "environment": "local"}, tmp_path)
    assert asyncio.run(chaos_jobs.run_job(job, 1)) == 7
    log = tmp_path / "chaos-job-logs" / "normal" / job["id"] / "run-1.log"
    assert log.read_text().splitlines() == ["out", "error"]
    assert job["max_log_bytes"] == 10 * 1024 * 1024


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, 64 * 1024 * 1024 + 1])
def test_invalid_job_log_limits_are_rejected(tmp_path, limit):
    with pytest.raises(ValueError, match="max_log_bytes"):
        chaos_jobs.validate_job({"name": "invalid", "argv": [sys.executable, "-c", "pass"], "max_runs": 1,
                                 "environment": "local", "max_log_bytes": limit}, tmp_path)
