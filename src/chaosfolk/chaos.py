"""Optional injection policies. No model calls, polling service or extra browser actions."""
import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import tomllib
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULTS = {
    "enabled": True, "schedule_enabled": True, "dry_run": False,
    "probability": 1.0, "min_interval": 0, "max_active": None,
    "max_affected_fraction": 1.0, "max_injections": None, "max_fault_duration": None,
    "grouping": "project", "groups": [], "allowed_faults": None,
    "exclude": {"humans": [], "roles": [], "routes": [], "methods": []},
    "forbid_pairs": [], "window": None, "reload_interval": 2,
    "shared_state": None, "shared_key": None,
    "health_check": None, "health_interval": 15, "hook_timeout": 2,
    "tracker": None, "error_counter": None, "secret_env": {},
}
SELECTORS = {"humans", "roles", "routes", "methods"}


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}")


def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{name} must be a list of non-empty strings")


def command(value, name):
    if value is not None:
        strings(value, name)
        if not value:
            raise ValueError(f"{name} needs an executable and optional arguments")


def validate(raw):
    if not isinstance(raw, dict) or raw.keys() - DEFAULTS.keys():
        raise ValueError("Unknown chaos policy field or policy is not an object")
    p = {**DEFAULTS, **raw}
    for key in ("enabled", "schedule_enabled", "dry_run"):
        if type(p[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    for key in ("probability", "max_affected_fraction"):
        number(p[key], key, 0, 1)
    for key in ("min_interval", "reload_interval", "health_interval"):
        number(p[key], key, 0, 86400 * 365)
    number(p["hook_timeout"], "hook_timeout", 0.1, 10)
    for key in ("max_active", "max_injections"):
        if p[key] is not None and (type(p[key]) is not int or not 0 <= p[key] <= 100000):
            raise ValueError(f"{key} must be a nonnegative integer")
    if p["max_fault_duration"] is not None:
        number(p["max_fault_duration"], "max_fault_duration", 0.1, 86400)
    if p["grouping"] not in ("project", "human", "role"):
        raise ValueError("grouping must be project, human or role")
    from .engine import PANNES
    if p["allowed_faults"] is not None:
        strings(p["allowed_faults"], "allowed_faults")
        if set(p["allowed_faults"]) - set(PANNES):
            raise ValueError("Unknown allowed fault")
    if not isinstance(p["exclude"], dict) or p["exclude"].keys() - SELECTORS:
        raise ValueError("exclude supports humans, roles, routes and methods")
    p["exclude"] = {key: p["exclude"].get(key, []) for key in SELECTORS}
    for key, values in p["exclude"].items():
        strings(values, f"exclude.{key}")
    if not isinstance(p["groups"], list):
        raise ValueError("groups must be a list")
    names = set()
    for group in p["groups"]:
        if not isinstance(group, dict) or group.keys() - {"name", "humans", "roles", "routes", "max_active", "min_interval"}:
            raise ValueError("Groups support name, humans, roles and routes")
        if not isinstance(group.get("name"), str) or not group["name"] or group["name"] in names:
            raise ValueError("Groups need unique non-empty names")
        names.add(group["name"])
        for key in ("humans", "roles", "routes"):
            strings(group.get(key, []), f"groups.{key}")
        if "max_active" in group and (type(group["max_active"]) is not int or not 0 <= group["max_active"] <= 100000):
            raise ValueError("Group max_active must be a nonnegative integer")
        if "min_interval" in group:
            number(group["min_interval"], "group min_interval", 0, 86400 * 365)
    if not isinstance(p["forbid_pairs"], list):
        raise ValueError("forbid_pairs must be a list of fault pairs")
    for pair in p["forbid_pairs"]:
        strings(pair, "forbid_pairs")
        if len(pair) != 2 or set(pair) - set(PANNES):
            raise ValueError("Each forbidden pair needs two known fault types")
    if p["window"] is not None:
        validate_window(p["window"])
    for key in ("shared_state", "shared_key"):
        if p[key] is not None and (not isinstance(p[key], str) or not p[key]):
            raise ValueError(f"{key} must be a non-empty string")
    if bool(p["shared_state"]) != bool(p["shared_key"]):
        raise ValueError("shared_state and shared_key must be configured together")
    for key in ("health_check", "tracker", "error_counter"):
        command(p[key], key)
    if not isinstance(p["secret_env"], dict):
        raise ValueError("secret_env must map hook environment names to providers")
    for name, provider in p["secret_env"].items():
        if not isinstance(name, str) or not name.isidentifier() or not isinstance(provider, dict):
            raise ValueError("Invalid secret environment mapping")
        if set(provider) == {"env"}:
            if not isinstance(provider["env"], str) or not provider["env"]:
                raise ValueError("Secret env provider needs a variable name")
        elif set(provider) == {"command"}:
            command(provider["command"], "secret command")
            if provider["command"] is None:
                raise ValueError("Secret command is empty")
        else:
            raise ValueError("Secret provider needs env or command")
    return p


def validate_window(window):
    if not isinstance(window, dict) or window.keys() - {"timezone", "weekdays", "start_hour", "end_hour"}:
        raise ValueError("window supports timezone, weekdays, start_hour and end_hour")
    try:
        timezone_for(window.get("timezone", "UTC"))
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise ValueError("Unknown timezone; on Windows install chaosfolk[chaos] for IANA timezone data") from None
    days = window.get("weekdays", [0, 1, 2, 3, 4])
    if not isinstance(days, list) or any(type(d) is not int or not 0 <= d <= 6 for d in days):
        raise ValueError("weekdays use integers 0 (Monday) through 6 (Sunday)")
    for key, default in (("start_hour", 9), ("end_hour", 15)):
        number(window.get(key, default), key, 0, 24)
    if window.get("start_hour", 9) >= window.get("end_hour", 15):
        raise ValueError("start_hour must be before end_hour (split overnight windows)")


def timezone_for(name):
    return timezone.utc if name == "UTC" else ZoneInfo(name)


def in_window(window, now=None):
    if window is None:
        return True
    now = datetime.fromtimestamp(time.time() if now is None else now, timezone_for(window.get("timezone", "UTC")))
    hour = now.hour + now.minute / 60 + now.second / 3600
    return now.weekday() in window.get("weekdays", [0, 1, 2, 3, 4]) and window.get("start_hour", 9) <= hour < window.get("end_hour", 15)


def read_policy(path):
    path = Path(path)
    with path.open("rb") as stream:
        raw = tomllib.load(stream) if path.suffix.lower() == ".toml" else json.loads(stream.read().decode("utf-8-sig"))
    p = validate(raw)
    if p["shared_state"]:
        p["shared_state"] = str((path.parent / p["shared_state"]).resolve())
    return p


def policy_path(explicit=None, project=None):
    if explicit:
        path = Path(explicit).resolve()
        if not path.is_file():
            raise ValueError(f"Chaos policy does not exist: {path}")
        return path
    if project:
        from .campaigns import project_dir
        path = project_dir(project) / "chaos-policy.json"
        if path.is_file():
            return path
    return None


def matches(patterns, value):
    return any(fnmatchcase(value, pattern) for pattern in patterns)


def selected(rule, human, role, route):
    return all(not rule.get(key) or matches(rule[key], value) for key, value in
               (("humans", human), ("roles", role), ("routes", route)))


class Ledger:
    """Atomic admission across processes on one shared local SQLite database."""
    # Short transactions can still exceed 250 ms on a busy Windows runner.
    # Let SQLite wait for the writer without replaying an admitted injection.
    LOCK_TIMEOUT = 5.0

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS leases (scope TEXT, owner TEXT, fault TEXT, grp TEXT, kind TEXT, expires REAL, PRIMARY KEY(scope,owner,fault))")
            db.execute("CREATE TABLE IF NOT EXISTS history (scope TEXT, grp TEXT, last REAL, PRIMARY KEY(scope,grp))")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=self.LOCK_TIMEOUT)
        try:
            with db:
                yield db
        finally:
            db.close()

    def claim(self, scope, owner, fault, group, kind, policy, now=None, reserve=True):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if reserve:
                db.execute("DELETE FROM leases WHERE expires <= ?", (now,))
            rows = db.execute("SELECT grp,kind FROM leases WHERE scope=? AND expires > ?", (scope, now)).fetchall()
            last = db.execute("SELECT last FROM history WHERE scope=? AND grp=?", (scope, group)).fetchone()
            rule = next((g for g in policy["groups"] if g["name"] == group), {})
            if last and now - last[0] < rule.get("min_interval", policy["min_interval"]):
                return "shared-cooldown"
            if policy["max_active"] is not None and len(rows) >= policy["max_active"]:
                return "shared-max-active"
            if "max_active" in rule and sum(g == group for g, _ in rows) >= rule["max_active"]:
                return "shared-group-max-active"
            for _, active_kind in rows:
                if any(sorted(pair) == sorted([kind, active_kind]) for pair in policy["forbid_pairs"]):
                    return "shared-forbidden-combination"
            if reserve:
                db.execute("INSERT INTO leases VALUES (?,?,?,?,?,?)", (scope, owner, fault, group, kind, now + 30))
                db.execute("INSERT OR REPLACE INTO history VALUES (?,?,?)", (scope, group, now))
        return None

    def heartbeat(self, scope, owner):
        with self.connect() as db:
            db.execute("UPDATE leases SET expires=? WHERE scope=? AND owner=?", (time.time() + 30, scope, owner))

    def release(self, scope, owner, fault=None):
        with self.connect() as db:
            if fault is None:
                db.execute("DELETE FROM leases WHERE scope=? AND owner=?", (scope, owner))
            else:
                db.execute("DELETE FROM leases WHERE scope=? AND owner=? AND fault=?", (scope, owner, fault))


def identity_for(proc):
    import psutil
    from .engine import process_identity
    try:
        return process_identity(proc.pid) if proc.poll() is None else None
    except (psutil.NoSuchProcess, ProcessLookupError):
        return None


class OutputLimitExceeded(ValueError):
    """A command exceeded its output budget; scheduled jobs use exit code 125."""
    exit_code = 125


async def bounded_output(proc, timeout, limit, destination):
    """Drain a pipe without blocking the loop or writing beyond its byte limit."""
    fd = proc.stdout.fileno()
    os.set_blocking(fd, False)  # Pipe support on Windows requires Python 3.12+.
    written = 0
    async with asyncio.timeout(timeout):
        while True:
            # Check for exit before reading: anything the root wrote is then in the pipe,
            # and an empty read means its output is complete. Waiting for EOF instead would
            # block on a descendant that inherited stdout and outlived the command.
            exited = proc.poll() is not None
            try:
                chunk = os.read(fd, min(65536, limit - written + 1))
            except BlockingIOError:
                chunk = None
            if chunk:
                accepted = chunk[:limit - written]
                destination.write(accepted)
                written += len(accepted)
                if len(chunk) != len(accepted):
                    raise OutputLimitExceeded(f"output-limit: command output exceeds {limit} bytes")
                await asyncio.sleep(0)
            elif exited:
                return proc.returncode
            else:
                await asyncio.sleep(0.02)


async def finish_process(proc, identity):
    """Stop an owned command tree, reap the root and close its output pipe."""
    from .engine import stop_owned_process
    try:
        if identity:
            try:
                await asyncio.to_thread(stop_owned_process, identity)
            except (OSError, ValueError):
                pass
    finally:
        try:
            if proc.poll() is None:
                proc.kill()
            try:
                await asyncio.to_thread(proc.wait, timeout=5)
            except subprocess.TimeoutExpired:
                pass  # Still exiting after kill; the recorded identity keeps its PID from being trusted again.
        finally:
            if proc.stdout is not None:
                proc.stdout.close()


PRIVATE_ENVIRONMENT = ("CHAOSFOLK_LEADER_TOKEN",)


def hook_environment(env=None):
    """Hooks get the operator's environment minus the engine's own credentials."""
    return {name: value for name, value in (os.environ if env is None else env).items() if name not in PRIVATE_ENVIRONMENT}


async def execute(argv, payload, timeout, env=None, capture=False):
    """Bounded, shell-free hook; never copy hook output or credentials into evidence."""
    import subprocess
    import tempfile
    import io
    from .engine import charger_moteur, options_detache
    charger_moteur()
    env = hook_environment(env)
    with tempfile.TemporaryFile() as input_file:
        input_file.write(json.dumps(payload).encode("utf-8"))
        input_file.seek(0)
        proc = subprocess.Popen(argv, stdin=input_file, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=env, **options_detache())
        identity = None
        output = io.BytesIO()
        try:
            identity = identity_for(proc)
            if capture:
                await bounded_output(proc, timeout, 65536, output)
            else:
                async with asyncio.timeout(timeout):
                    while proc.poll() is None:
                        await asyncio.sleep(0.02)
            return proc.returncode, output.getvalue().decode("utf-8").strip()
        finally:
            await finish_process(proc, identity)


class Controller:
    def __init__(self, folder, owner, source=None, dry_run=False):
        self.folder, self.owner, self.source = Path(folder), owner, source
        self.policy = read_policy(source) if source else validate({})
        self.force_dry_run = dry_run
        self.paused = False
        self.override = {}
        self.invalid = False
        self.last_refresh = 0
        self.signature = None
        self.last_health = None
        self.health_ok = False
        self.last = {}
        self.count = 0
        self.lock = asyncio.Lock()
        self.ledger = Ledger(self.policy["shared_state"]) if self.policy["shared_state"] else None
        self.leases = {}  # fault id -> (ledger, scope); release with the policy used at admission
        self.last_heartbeat = 0
        self.tasks = set()
        self.metrics = {"planned": 0, "applied": 0, "simulated": 0, "skipped": 0, "cancelled": 0, "engine_errors": 0, "hook_errors": 0}

    @property
    def config(self):
        return {**self.policy, **self.override}

    def dry_run(self):
        return self.force_dry_run or self.config["dry_run"]

    def event(self, event):
        # No notes, URL query strings, typed values, hook outputs or environment values.
        safe = {k: event[k] for k in ("type", "id", "h", "panne", "phase", "reason", "group", "t") if k in event}
        kind = event.get("type")
        if kind not in {"chaos-planned", "chaos-simulated", "chaos-skipped", "chaos-cancelled", "panne-debut", "panne-fin", "erreur-moteur"}:
            return
        metric = {"chaos-planned": "planned", "panne-debut": "applied", "chaos-simulated": "simulated",
                  "chaos-skipped": "skipped", "chaos-cancelled": "cancelled", "erreur-moteur": "engine_errors"}.get(kind)
        if kind == "panne-debut" and event.get("erreur"):
            self.metrics["engine_errors"] += 1
            metric = None
        if metric:
            self.metrics[metric] += 1
        (self.folder / "chaos-metrics.json").write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")
        p = self.config
        hook = p["error_counter"] if kind == "erreur-moteur" or event.get("erreur") else p["tracker"]
        if hook:
            if len(self.tasks) >= 16:
                self.metrics["hook_errors"] += 1
                return
            task = asyncio.create_task(self.notify(hook, safe, p))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def hook_env(self, p):
        if not p["secret_env"]:
            return None
        env = dict(os.environ)
        for name, provider in p["secret_env"].items():
            if "env" in provider:
                if provider["env"] not in os.environ:
                    raise ValueError("Missing hook credential")
                env[name] = os.environ[provider["env"]]
            else:
                code, value = await execute(provider["command"], {}, p["hook_timeout"], capture=True)
                if code:
                    raise ValueError("Credential provider failed")
                env[name] = value
        return env

    async def notify(self, argv, event, p):
        try:
            code, _ = await asyncio.wait_for(self.call_hook(argv, event, p), p["hook_timeout"])
            if code:
                self.metrics["hook_errors"] += 1
        except (OSError, ValueError, RuntimeError, TimeoutError):
            self.metrics["hook_errors"] += 1

    async def call_hook(self, argv, event, p):
        return await execute(argv, event, p["hook_timeout"], await self.hook_env(p))

    async def refresh(self):
        now = time.monotonic()
        if self.source and self.policy["reload_interval"] and now - self.last_refresh >= self.policy["reload_interval"]:
            self.last_refresh = now
            try:
                signature = hashlib.sha256(self.source.read_bytes()).hexdigest()
                if signature != self.signature:
                    policy = read_policy(self.source)
                    ledger = Ledger(policy["shared_state"]) if policy["shared_state"] else None
                    if policy["health_check"] != self.policy["health_check"] or policy["secret_env"] != self.policy["secret_env"]:
                        self.last_health = None
                    self.policy, self.ledger, self.signature = policy, ledger, signature
                self.invalid = False
            except (OSError, ValueError, sqlite3.Error):
                self.invalid = True  # fail closed; retain the last valid policy for cleanup
        if now - self.last_heartbeat >= 5:
            self.last_heartbeat = now
            for ledger, scope in set(self.leases.values()):
                try:
                    await asyncio.to_thread(ledger.heartbeat, scope, self.owner)
                except (sqlite3.Error, OSError):
                    self.invalid = True

    def target(self, fault, horde):
        hid = fault.get("h")
        human = horde.humains.get(hid)
        role = horde.fiches.get(hid, {}).get("role", "")
        route = urlsplit(human.page.url).path if human and human.page else "/"
        p = self.config
        group = (getattr(horde.opts, "project", None) or "session") if p["grouping"] == "project" else (hid or "global")
        if p["grouping"] == "role":
            group = role or "unassigned"
        for rule in p["groups"]:
            if selected(rule, hid or "global", role, route):
                group = rule["name"]
                break
        return hid, role, route, group

    async def admit(self, fault, horde):
        async with self.lock:
            p = self.config
            hid, role, route, group = self.target(fault, horde)
            fault["chaos_group"] = group
            if self.invalid:
                return "invalid-policy-or-ledger"
            if self.paused or not p["enabled"]:
                return "injections-paused"
            if not p["schedule_enabled"] and fault.get("scheduled"):
                return "scheduling-disabled"
            if hid is not None and (hid not in horde.humains or getattr(horde.humains[hid], "statut", "en cours") in ("fini", "abandon")):
                return "inactive-target"
            if not in_window(p["window"]):
                return "outside-window"
            if p["allowed_faults"] is not None and fault["type"] not in p["allowed_faults"]:
                return "fault-not-allowed"
            exclusion = p["exclude"]
            if matches(exclusion["humans"], hid or "global") or matches(exclusion["roles"], role) or matches(exclusion["routes"], route):
                return "excluded-target"
            # Global faults affect every session, regardless of the configured grouping.
            if hid is None:
                for user, human in horde.humains.items():
                    path = urlsplit(human.page.url).path if human.page else "/"
                    if matches(exclusion["humans"], user) or matches(exclusion["roles"], horde.fiches.get(user, {}).get("role", "")) or matches(exclusion["routes"], path):
                        return "excluded-global-target"
            if exclusion["methods"] and fault["type"] not in {"slow", "server-down", "http-error", "lost-response"}:
                return "method-exclusion-needs-request-fault"
            if exclusion["routes"] and fault["type"] not in {"slow", "server-down", "http-error", "lost-response"}:
                return "route-exclusion-needs-request-fault"
            if p["max_injections"] is not None and self.count >= p["max_injections"]:
                return "injection-budget"
            now = time.time()
            rule = next((g for g in p["groups"] if g["name"] == group), {})
            if now - self.last.get(group, -math.inf) < rule.get("min_interval", p["min_interval"]):
                return "cooldown"
            active = [f for f in horde.pannes if f is not fault and f["phase"] in ("active", "redemarrage")]
            if p["max_active"] is not None and len(active) >= p["max_active"]:
                return "max-active"
            if "max_active" in rule and sum(self.target(f, horde)[3] == group for f in active) >= rule["max_active"]:
                return "group-max-active"
            affected = {f["h"] for f in [*active, fault] if f["h"]}
            if any(f["h"] is None for f in [*active, fault]):
                affected = set(horde.humains)
            if len(affected) > math.floor(len(horde.humains) * p["max_affected_fraction"]):
                return "affected-user-budget"
            if any(sorted(pair) == sorted([fault["type"], f["type"]]) for f in active for pair in p["forbid_pairs"]):
                return "forbidden-combination"
            sample = int(hashlib.sha256(f"{self.owner}:{fault['id']}".encode()).hexdigest()[:16], 16) / 2**64
            if sample >= p["probability"]:
                return "probability"
            if p["health_check"]:
                if active and self.last_health is None:
                    return "health-baseline-unavailable-during-injection"
                if not active and (self.last_health is None or time.monotonic() - self.last_health >= p["health_interval"]):
                    try:
                        code, _ = await asyncio.wait_for(self.call_hook(p["health_check"], {"type": "health-check"}, p), p["hook_timeout"])
                        self.health_ok = code == 0
                    except (OSError, ValueError, RuntimeError, TimeoutError):
                        self.health_ok = False
                        self.metrics["hook_errors"] += 1
                    self.last_health = time.monotonic()
                if not self.health_ok:
                    return "outage-or-health-check-failed"
            if self.paused or p != self.config:
                return "policy-changed-during-admission"
            if self.ledger:
                ledger, scope = self.ledger, p["shared_key"]
                reserve = not self.dry_run()
                claim = asyncio.create_task(asyncio.to_thread(ledger.claim, scope, self.owner, fault["id"], group, fault["type"], p, reserve=reserve))
                try:
                    reason = await asyncio.shield(claim)
                except asyncio.CancelledError:
                    try:
                        await claim
                        await asyncio.to_thread(ledger.release, scope, self.owner, fault["id"])
                    except sqlite3.Error:
                        self.invalid = True
                    raise
                except sqlite3.Error:
                    return "shared-ledger-unavailable"
                if reason:
                    return reason
                if reserve:
                    self.leases[fault["id"]] = (ledger, scope)
                if self.paused or p != self.config:
                    await self.release(fault)
                    return "policy-changed-during-admission"
            self.last[group] = now
            self.count += 1
            fault["chaos_admitted"] = True
            fault["chaos_exclude"] = exclusion
            if p["max_fault_duration"] is not None:
                cap = int(p["max_fault_duration"] * 1000)
                fault["duree"] = min(fault.get("duree") or cap, cap)
            return None

    async def release(self, fault):
        entry = self.leases.pop(fault["id"], None)
        if entry:
            ledger, scope = entry
            try:
                await asyncio.to_thread(ledger.release, scope, self.owner, fault["id"])
            except sqlite3.Error:
                self.invalid = True

    async def close(self):
        for fault_id in list(self.leases):
            await self.release({"id": fault_id})
        if self.tasks:
            _, pending = await asyncio.wait(self.tasks, timeout=self.config["hook_timeout"])
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        (self.folder / "chaos-metrics.json").write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")

    def status(self):
        return {"enabled": self.config["enabled"], "schedule_enabled": self.config["schedule_enabled"],
                "dry_run": self.dry_run(), "paused": self.paused, "invalid": self.invalid,
                "source": str(self.source) if self.source else None, "metrics": self.metrics}

    def snapshot(self, faults):
        fields = ("id", "type", "h", "phase", "reason", "chaos_group", "scheduled", "a", "apres", "duree", "debut", "fin")
        states = {"programmee": "planned", "admission": "checking", "active": "active", "redemarrage": "recovering",
                  "terminee": "completed", "simulee": "simulated", "ignoree": "skipped", "annulee": "cancelled"}
        data = {"control": self.status(), "faults": [{**{k: f[k] for k in fields if k in f},
                 "status": states.get(f["phase"], f["phase"])} for f in faults]}
        target = self.folder / "chaos-plan.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(target)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk chaos", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="write an optional project policy; never overwrite")
    dest = init.add_mutually_exclusive_group(required=True)
    dest.add_argument("--file")
    dest.add_argument("--project")
    check = sub.add_parser("check", help="validate policy without running hooks or browsers")
    check.add_argument("file")
    inspect = sub.add_parser("inspect", help="read the recorded injection plan without a running session")
    inspect.add_argument("--folder", required=True)
    for name in ("status", "pause", "resume", "simulate", "live", "enable", "disable", "schedule-on", "schedule-off"):
        item = sub.add_parser(name)
        if name in ("pause", "disable"):
            item.add_argument("--end-active", action="store_true", help="also remove reversible active faults")
    schedule = sub.add_parser("schedule", help="optional finite recurring command jobs")
    schedule.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.cmd == "inspect":
        print((Path(args.folder) / "chaos-plan.json").read_text(encoding="utf-8"))
        return 0
    if args.cmd == "schedule":
        from .chaos_jobs import main as jobs
        return jobs(args.args)
    if args.cmd == "init":
        if args.project:
            from .campaigns import project_dir
            path = project_dir(args.project) / "chaos-policy.json"
        else:
            path = Path(args.file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"enabled": True, "schedule_enabled": True, "dry_run": False,
                       "max_active": 1, "min_interval": 10, "max_injections": 4, "max_fault_duration": 20}, stream, indent=2)
        print(f"Policy: {path.resolve()}")
        return 0
    if args.cmd == "check":
        read_policy(args.file)
        print("Valid policy. No hooks or browsers were started.")
        return 0
    from .engine import relayer, utf8
    utf8()
    return relayer({"cmd": "chaos-control", "action": args.cmd, "end_active": getattr(args, "end_active", False)})
