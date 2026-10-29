"""Finite recurring jobs, invoked by an external scheduler with `run-due`."""
import argparse
import asyncio
from contextlib import closing, contextmanager
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid

from .chaos import OutputLimitExceeded, bounded_output, command, finish_process, in_window, number, validate_window

DEFAULT_MAX_LOG_BYTES = 10 * 1024 * 1024


@contextmanager
def store():
    from .campaigns import home
    path = home() / "chaos-jobs.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=1)
    try:
        db.execute("CREATE TABLE IF NOT EXISTS jobs (name TEXT PRIMARY KEY, config TEXT, next REAL, runs INTEGER, running_until REAL, last_code INTEGER)")
        with db:
            yield db
    finally:
        db.close()


def validate_job(raw, base):
    allowed = {"name", "argv", "cwd", "interval", "max_runs", "timeout", "enabled", "window", "environment", "max_log_bytes"}
    if not isinstance(raw, dict) or raw.keys() - allowed:
        raise ValueError("Unknown scheduled job field")
    from .campaigns import project_name
    name = project_name(raw.get("name"))
    command(raw.get("argv"), "argv")
    if raw.get("argv") is None:
        raise ValueError("argv is required; use an explicit executable, without a shell string")
    number(raw.get("interval", 86400), "interval", 60, 86400 * 365)
    number(raw.get("timeout", 60), "timeout", 1, 3600)
    log_limit = raw.get("max_log_bytes", DEFAULT_MAX_LOG_BYTES)
    if type(log_limit) is not int or not 1 <= log_limit <= 64 * 1024 * 1024:
        raise ValueError("max_log_bytes must be an integer between 1 and 67108864")
    if type(raw.get("max_runs")) is not int or not 1 <= raw["max_runs"] <= 10000:
        raise ValueError("max_runs is required, between 1 and 10000")
    if type(raw.get("enabled", False)) is not bool:
        raise ValueError("enabled must be a boolean")
    if raw.get("environment") not in ("local", "test"):
        raise ValueError("environment must explicitly be local or test")
    if raw.get("window") is not None:
        validate_window(raw["window"])
    cwd = (base / raw.get("cwd", ".")).resolve()
    if not cwd.is_dir():
        raise ValueError("Job cwd must be an existing directory")
    return {"id": uuid.uuid4().hex, "name": name, "argv": raw["argv"], "cwd": str(cwd), "interval": raw.get("interval", 86400),
            "timeout": raw.get("timeout", 60), "max_runs": raw["max_runs"], "enabled": raw.get("enabled", False),
            "window": raw.get("window"), "environment": raw["environment"], "max_log_bytes": log_limit}


async def run_job(job, run_number):
    """One process tree, bounded in time; no model or agent invocation added by the scheduler."""
    from .engine import charger_moteur, options_detache
    from .chaos import identity_for
    charger_moteur()
    from .campaigns import home
    folder = home() / "chaos-job-logs" / job["name"] / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    # A new state directory prevents a scheduled browser job attaching to an interactive session.
    env = dict(os.environ, CHAOSFOLK_HOME=str(folder / f"state-{run_number}"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    with (folder / f"run-{run_number}.log").open("xb") as log:
        proc = subprocess.Popen(job["argv"], cwd=job["cwd"], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options_detache())
        identity = None
        try:
            identity = identity_for(proc)
            return await bounded_output(proc, job["timeout"], job.get("max_log_bytes", DEFAULT_MAX_LOG_BYTES), log)
        except TimeoutError:
            return 124
        except OutputLimitExceeded:
            return OutputLimitExceeded.exit_code
        finally:
            # Jobs must remain in the foreground so their process tree stays owned.
            await finish_process(proc, identity)


def run_due(limit=1, now=None):
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    outcomes = []
    for _ in range(limit):
        # Earlier jobs can take an hour; every reservation needs a fresh lease.
        current = time.time() if now is None else now
        with store() as db:
            db.execute("BEGIN IMMEDIATE")
            chosen = None
            with closing(db.execute("SELECT name,config,runs FROM jobs WHERE next <= ? AND running_until <= ? ORDER BY next,name", (current, current))) as rows:
                for name, config, runs in rows:
                    job = json.loads(config)
                    if job["enabled"] and runs < job["max_runs"] and in_window(job["window"], current):
                        chosen = (name, job, runs + 1)
                        break
            if chosen is None:
                break
            name, job, run_number = chosen
            # Reserve before execution: crashes count towards the finite attempt budget.
            db.execute("UPDATE jobs SET next=?,runs=?,running_until=? WHERE name=?",
                       (current + job["interval"], run_number, current + job["timeout"] + 30, name))
        code = 130
        try:
            code = asyncio.run(run_job(job, run_number))
        except (OSError, ValueError, RuntimeError):
            code = 2
        finally:
            with store() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT config,runs FROM jobs WHERE name=?", (name,)).fetchone()
                # An expired lease may have been reclaimed, or the job replaced.
                if row and json.loads(row[0])["id"] == job["id"] and row[1] == run_number:
                    db.execute("UPDATE jobs SET running_until=0,last_code=? WHERE name=?", (code, name))
        outcomes.append({"name": name, "run": run_number, "exit_code": code})
    return outcomes


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk chaos schedule", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="register a JSON job; no immediate execution or OS scheduler installation")
    add.add_argument("file")
    sub.add_parser("list")
    for name in ("enable", "disable", "remove"):
        sub.add_parser(name).add_argument("name")
    run = sub.add_parser("run-due", help="run at most one due job by default; never waits for a future window")
    run.add_argument("--limit", type=int, default=1)
    args = parser.parse_args(argv)
    if args.cmd == "run-due":
        if not 1 <= args.limit <= 10:
            raise ValueError("limit must be between 1 and 10")
        outcomes = run_due(args.limit)
        print(json.dumps(outcomes, indent=2))
        return 1 if any(outcome["exit_code"] for outcome in outcomes) else 0
    with store() as db:
        if args.cmd == "add":
            path = Path(args.file).resolve()
            job = validate_job(json.loads(path.read_text(encoding="utf-8-sig")), path.parent)
            try:
                db.execute("INSERT INTO jobs VALUES (?,?,?,0,0,NULL)", (job["name"], json.dumps(job), time.time()))
            except sqlite3.IntegrityError:
                raise ValueError("Job already exists; remove it explicitly before replacing it") from None
            print(f"Registered {job['name']}; enabled={job['enabled']}. No OS schedule installed.")
        elif args.cmd == "list":
            rows = db.execute("SELECT config,next,runs,running_until,last_code FROM jobs ORDER BY name").fetchall()
            print(json.dumps([{**json.loads(config), "next": due, "runs": runs, "running_until": running, "last_code": code}
                              for config, due, runs, running, code in rows], indent=2))
        else:
            row = db.execute("SELECT config,running_until FROM jobs WHERE name=?", (args.name,)).fetchone()
            if row is None:
                raise ValueError("Unknown job")
            if args.cmd == "remove":
                if row[1] > time.time():
                    raise ValueError("Cannot remove a running job; disable it and wait for completion")
                db.execute("DELETE FROM jobs WHERE name=?", (args.name,))
            else:
                job = json.loads(row[0])
                job["enabled"] = args.cmd == "enable"
                db.execute("UPDATE jobs SET config=? WHERE name=?", (json.dumps(job), args.name))
    return 0
