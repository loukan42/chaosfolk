"""Run one audit. Production uses a disposable Docker container; `demo` runs the offline Chaosfolk demo for local tests."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

# Only the report and the folders it reads are published. The session also holds browser state,
# the audit database and agent logs, which stay private on the server.
PUBLIC_FILES = ("rapport.html", "report-en.html", "rapport-fr.html", "logo.png")
# scenarios/ holds the recorded journeys: `chaosfolk replay scenarios/NAME.json` replays them on the
# visitor's machine, and the engine finds the session folder from the scenario's location.
PUBLIC_DIRS = ("assets", "captures", "reproductions", "scenarios")

ARCHIVE_README = """Chaosfolk report for {url}

Open rapport.html in a browser. Keep the other folders next to it: they hold the screenshots
and the session replay.

To replay a recorded journey on your machine, install Chaosfolk
(https://github.com/loukan42/chaosfolk#install), then from this folder:

    chaosfolk replay scenarios/NAME.json --times 3

Read a scenario before replaying it: it drives a real browser on the site it names.
The report may contain text and screenshots from the audited site. Share it accordingly.
"""


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


def archive(public_dir, zip_path, folder, url):
    """Pack the published report into one .zip that opens offline once extracted."""
    public_dir, zip_path = Path(public_dir), Path(zip_path)
    partial = zip_path.with_suffix(".zip.part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{folder}/README.txt", ARCHIVE_README.format(url=url))
        for path in sorted(public_dir.rglob("*")):
            if path.is_file() and not path.is_symlink():
                bundle.write(path, f"{folder}/{path.relative_to(public_dir).as_posix()}")
    partial.replace(zip_path)


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
    # The container user has the worker's uid (10001, see web/README.md), so 0700 is enough.
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
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
    archive(job_dir / "public", job_dir / "report.zip", archive_name(audit), audit["url"])


def archive_name(audit):
    host = "".join(c if c.isalnum() or c in ".-" else "-" for c in audit["host"])[:80]
    return f"chaosfolk-{host}-{audit['created_at'][:10]}"
