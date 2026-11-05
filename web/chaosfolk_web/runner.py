"""Run one audit. Production uses a disposable Docker container; `demo` runs the offline Chaosfolk demo for local tests."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Only the report and the folders it reads are published. The session also holds browser state,
# the audit database and agent logs, which stay private on the server.
PUBLIC_FILES = ("rapport.html", "report-en.html", "rapport-fr.html", "logo.png")
PUBLIC_DIRS = ("assets", "captures", "reproductions")


class RunFailed(Exception):
    pass


def publish(run_dir, public_dir):
    run_dir, public_dir = Path(run_dir), Path(public_dir)
    if not (run_dir / "rapport.html").is_file():
        raise RunFailed("The audit ended without a report.")
    public_dir.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        if (run_dir / name).is_file():
            shutil.copy2(run_dir / name, public_dir / name)
    for name in PUBLIC_DIRS:
        source = run_dir / name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(source, public_dir / name, symlinks=False, dirs_exist_ok=True,
                            ignore=lambda folder, names: [n for n in names if (Path(folder) / n).is_symlink()])


def _run(command, timeout, on_timeout=None, log=None):
    try:
        with open(log, "ab") if log else open(os.devnull, "wb") as output:
            completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        if on_timeout:
            on_timeout()
        raise RunFailed("The audit took too long and was stopped.") from None
    return completed.returncode


def demo(settings, audit, job_dir):
    """Ignore the URL and build the bundled demo report: it exercises the queue and the report pages offline."""
    run_dir = job_dir / "run"
    _run([sys.executable, "-m", "chaosfolk", "demo", "--output", str(run_dir), "--lang", audit["lang"]],
         timeout=600, log=job_dir / "runner.log")
    publish(run_dir, job_dir / "public")


def docker(settings, audit, job_dir):
    if not settings.model:
        raise RunFailed("No model is configured on the server.")
    name = f"chaosfolk-audit-{audit['id'][:12].lower().replace('_', '-')}"
    work = job_dir / "work"
    work.mkdir(parents=True, exist_ok=True)
    os.chmod(work, 0o777)
    seconds = settings.audit_minutes * 60
    command = [
        "docker", "run", "--rm", "--name", name,
        "--network", settings.runner_network,
        "--memory", "3g", "--cpus", "2", "--pids-limit", "1024", "--shm-size", "1g",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "-e", "OPENROUTER_API_KEY", "-e", f"CHAOSFOLK_MODEL={settings.model}",
        "-v", f"{work}:/work",
        settings.runner_image,
        audit["url"], audit["lang"], str(seconds), str(settings.max_actions), str(settings.users), audit["host"],
    ]
    # The container stops its own audit at the time limit; the extra margin lets it write the report.
    code = _run(command, timeout=seconds + 420, log=job_dir / "runner.log",
                on_timeout=lambda: subprocess.run(["docker", "kill", name], capture_output=True, check=False))
    if code != 0 and not (work / "run" / "rapport.html").is_file():
        raise RunFailed("The audit failed before producing a report.")
    publish(work / "run", job_dir / "public")


RUNNERS = {"demo": demo, "docker": docker}


def run(settings, audit, job_dir):
    try:
        runner = RUNNERS[settings.runner]
    except KeyError:
        raise RunFailed(f"Unknown runner {settings.runner!r}.") from None
    job_dir.mkdir(parents=True, exist_ok=True)
    runner(settings, audit, job_dir)
