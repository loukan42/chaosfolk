"""Replay provenance, bounded fixture preparation and descriptive trial counts."""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
from datetime import datetime, timezone


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trial_counts(series):
    requested, valid, failed = (series.get(k) for k in ("demandes", "fois", "casses"))
    if any(type(x) is not int for x in (requested, valid, failed)) or not 0 <= failed <= valid <= requested:
        return None
    return {"requested": requested, "valid": valid, "failures": failed, "invalid": requested - valid,
            "failure_rate": failed / valid if valid else None}


def load_environment(path):
    if not path:
        return None
    path = Path(path).resolve()
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or value.keys() - {"prepare", "verify", "data_id", "app_version", "app_repo"}:
        raise ValueError("Environment supports prepare, verify, data_id, app_version and app_repo")
    for key in ("data_id", "app_version", "app_repo"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError(f"Environment {key} must be a non-empty string")
    if bool(value.get("prepare")) != bool(value.get("verify")):
        raise ValueError("Environment needs both prepare and verify commands")
    if value.get("prepare") and not value.get("data_id"):
        raise ValueError("Verified preparation requires a data_id")
    for key in ("prepare", "verify"):
        hook = value.get(key)
        if hook is None:
            continue
        if not isinstance(hook, dict) or hook.keys() - {"command", "timeout"}:
            raise ValueError(f"{key} needs command and optional timeout")
        command, timeout = hook.get("command"), hook.get("timeout", 30)
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise ValueError(f"{key}.command must be a non-empty argument list")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError(f"{key}.timeout must be between 0 and 300 seconds")
    value["directory"] = path.parent
    return value


async def _hook(hook, directory, read_result=False):
    # No shell interpolation. Redirect to a temporary file to bound memory even
    # when a configured command is noisy. Never include command output in errors.
    import tempfile
    with tempfile.TemporaryFile() as output:
        proc = await asyncio.create_subprocess_exec(
            *hook["command"], cwd=directory, stdout=output, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
        try:
            await asyncio.wait_for(proc.wait(), hook.get("timeout", 30))
        except BaseException:
            if proc.returncode is None:
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)  # The whole session, including detached grandchildren.
                    except (OSError, ProcessLookupError):
                        pass
                import psutil
                try:
                    parent = psutil.Process(proc.pid)
                    for child in reversed(parent.children(recursive=True)):
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                    parent.kill()
                except psutil.NoSuchProcess:
                    pass
            await proc.wait()
            raise
        if proc.returncode:
            raise ValueError("command failed")
        if read_result:
            output.seek(0)
            data = output.read(65537)
            if len(data) > 65536:
                raise ValueError("verification result too large")
            return json.loads(data)


async def prepare(environment):
    if not environment or not environment.get("prepare"):
        return {"status": "browser-only", "data_id": None}
    try:
        await _hook(environment["prepare"], environment["directory"])
        result = await _hook(environment["verify"], environment["directory"], True)
        if not isinstance(result, dict) or result.get("ready") is not True or result.get("data_id") != environment["data_id"]:
            raise ValueError("fixture identity mismatch")
        return {"status": "reset-verified", "data_id": environment["data_id"]}
    except (OSError, ValueError, asyncio.TimeoutError):
        return {"status": "invalid", "data_id": environment["data_id"],
                "reason": "Fixture preparation or verification failed; command output omitted"}


def git_identity(repo):
    if not repo:
        return None
    def git(*args):
        return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=", "-C", str(repo), *args],
                              capture_output=True, text=True,
                              timeout=5, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.SubprocessError):
        return None


def draw_provenance():
    from . import __version__
    root = Path(__file__).parent
    return {"chaosfolk": __version__, "profiles_sha256": file_hash(root / "profiles.json"),
            "persona_template_sha256": file_hash(root / "templates" / "persona.md"),
            "agent_template_sha256": file_hash(root / "templates" / "agent.md")}


def manifest(scenario, directory, browser, environment, source=None):
    from . import __version__
    from importlib.metadata import version
    directory = Path(directory)
    def read(name):
        path = directory / name
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    personas, draw = read("personas.json"), read("tirage.json")
    initial = []
    for name, settings in [("default", scenario), *scenario.get("sessions", {}).items()]:
        state = settings.get("etat")
        if state is None:
            initial.append({"session": name, "kind": "empty"})
        elif isinstance(state, dict):
            initial.append({"session": name, "kind": "inline", "sha256": fingerprint(state)})
        else:
            path = directory / state
            if not path.exists():
                path = directory / "etats" / Path(state).name
            initial.append({"session": name, "kind": "file", "sha256": file_hash(path) if path.is_file() else None})
    env = environment or {}
    repo = env.get("app_repo")
    repo = env["directory"] / repo if repo else None
    # The scenario itself remains a private replay artifact. Store only the
    # browser-state fingerprint here, never inline authentication data.
    from copy import deepcopy
    snapshot = deepcopy(scenario)
    snapshot.pop("etat", None)
    for settings in snapshot.get("sessions", {}).values():
        settings.pop("etat", None)
    profiles = deepcopy(personas.get("humains"))
    if isinstance(profiles, list):
        for profile in profiles:
            profile.pop("etat", None)
    return {"schema_version": 1, "created": datetime.now(timezone.utc).isoformat(),
            "chaosfolk": __version__, "playwright": version("playwright"),
            "browser": {"version": browser.version, "type": browser.browser_type.name},
            "application": {"version": env.get("app_version"), "git": git_identity(repo)},
            "seed": draw.get("graine", personas.get("graine")), "profile_provenance": draw.get("provenance"),
            "profiles": profiles, "scenario": snapshot, "scenario_sha256": fingerprint(scenario),
            "source_sha256": file_hash(source) if source else None,
            "browser_states": initial, "fault_schedule": scenario.get("pannes", []),
            "source_fault_events": scenario.get("fault_events"),
            "data": {"id": env.get("data_id"), "preparation_configured": bool(env.get("prepare")),
                     "configuration_sha256": fingerprint({k: v for k, v in env.items() if k != "directory"})},
            "limitations": ["Seed reproduces the draw, not model decisions.",
                            "Fault replay uses action anchors, not exact wall-clock timing.",
                            "Browser-state contents and backend snapshots must be retained separately."]}


def matrix_summary(cells):
    counts = {key: trial_counts(value) for key, value in cells.items()}
    expected = {f"{journey}/{mode}" for journey in ("observed", "reference")
                for mode in ("with_faults", "without_faults")}
    if counts.keys() != expected or any(value is None or value["invalid"] or not value["valid"] for value in counts.values()):
        status = "inconclusive"
    elif any(0 < value["failures"] < value["valid"] for value in counts.values()):
        status = "intermittent"
    elif any(value["failures"] for value in counts.values()):
        status = "failures-observed"
    else:
        status = "all-pass"
    return {"status": status, "counts": counts,
            "interpretation": "Compare each journey against its own expected behavior; severity requires product review."}
