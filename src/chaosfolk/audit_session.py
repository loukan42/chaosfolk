"""Durable audit selection, work queue and measured usage. No model calls.

SQLite transactions serialize dashboard edits, worker claims and results. The
engine consults the same gate before browser work; the dashboard never owns an
independent copy of the selection or pretends to cancel host model requests.
"""
import argparse
from contextlib import closing, contextmanager
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from . import checks

DB_NAME = "audit.sqlite3"
DEPTHS = {"quick": 1, "standard": 2, "deep": 3}
LIMITS = {
    "quick": {"max_actions": 80, "max_seconds": 600},
    "standard": {"max_actions": 200, "max_seconds": 1200},
    "deep": {"max_actions": 600, "max_seconds": 2700},
}
TEST_KINDS = {"qa-check", "page-check", "fault-scenario", "persistence-check",
              "journey-or-compatibility", "signal-or-integration"}
FINISHED = {"passed", "failed", "inconclusive", "blocked"}
AUDIT_CHECKS = {"responsive-controls", "layout-overflow", "keyboard-reachability", "accessible-names",
                "color-contrast", "target-size", "page-structure", "broken-resources", "javascript-errors",
                "small-screen-reflow"}
FAULTS = dict(zip(range(128, 140), ("offline", "slow", "server-down", "app-stop", "http-error",
             "lost-response", "storage-full", "storage-empty", "storage-corrupt", "clock", "window", "cookies-cleared")))
PREREQUISITES = {131: "managed-app", 165: "coordinated", 167: "multi-browser", 168: "visual-baseline",
                 172: "mailbox", 173: "downloads", 174: "downloads", 175: "pdf", 176: "axe",
                 177: "k6", 178: "appium"}
CAPABILITIES = {"test-account", "two-accounts", "mailbox", "coordinated", *PREREQUISITES.values()}
CAPABILITIES |= {"data-api", "login-throttling-authorized"}


@lru_cache(maxsize=1)
def catalog():
    source = json.loads(Path(__file__).with_name("audit_catalog.json").read_text(encoding="utf-8"))
    qa = {c["id"]: c for c in checks.load()["checks"]}
    result = {}
    for original in source["entries"]:
        item = dict(original)
        item["configurable"] = item["kind"] in TEST_KINDS
        item["executor"] = "coordinator"
        if item["id"] in qa:
            item.update(qa[item["id"]])
            item["executor"] = "audit" if item["id"] in AUDIT_CHECKS else (
                "agent" if item["scope"] in {"safe", "test-account"} else "coordinator")
        elif 117 <= item["source_order"] <= 121:
            item["executor"] = "fields"
        elif 122 <= item["source_order"] <= 127:
            item["executor"] = "audit"
        elif item["source_order"] in {161, 162, 163, 169}:
            item["executor"] = "agent"
        item["requires"] = ([item["scope"]] if item.get("scope", "safe") != "safe" else [])
        if item["source_order"] in PREREQUISITES:
            item["requires"].append(PREREQUISITES[item["source_order"]])
        if item["source_order"] in {130, 132, 133}:
            item["requires"].append("data-api")
        if item["id"] == "login-throttling":
            item["requires"].append("login-throttling-authorized")
        item["fault"] = FAULTS.get(item["source_order"])
        result[item["id"]] = item
    return result


def existing(folder):
    return Session(folder) if (Path(folder) / DB_NAME).is_file() else None


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class Session:
    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        self.path = self.folder / DB_NAME

    @contextmanager
    def db(self, write=False):
        if not self.path.is_file():
            raise ValueError("No audit session. Run audit-run init first.")
        if self.path.is_symlink() or not self.path.resolve().is_relative_to(self.folder) or self.path.stat().st_nlink > 1:
            raise ValueError("Audit database must be a private file inside the session")
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=10000")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def config(db):
        return json.loads(db.execute("SELECT value FROM metadata WHERE key='config'").fetchone()[0])

    @staticmethod
    def save(db, config, event, detail=None):
        config["revision"] += 1
        db.execute("UPDATE metadata SET value=? WHERE key='config'", (dumps(config),))
        db.execute("INSERT INTO events(at,kind,detail) VALUES(?,?,?)", (time.time(), event, dumps(detail or {})))

    def create(self, depth="standard", excluded=(), max_tokens=None, max_seconds=None, max_actions=None):
        if depth not in DEPTHS:
            raise ValueError("Unknown audit depth")
        self.validate_ids(excluded)
        limits = {**LIMITS[depth], "max_tokens": max_tokens, "max_browsers": 6}
        for name, value in (("max_seconds", max_seconds), ("max_actions", max_actions)):
            if value is not None:
                limits[name] = value
        self.validate_limits(limits)
        from .private_state import session_directory, secure
        session_directory(self.folder)
        # Exclusive creation prevents replacing an existing selection or evidence.
        with self.path.open("xb"):
            pass
        secure(self.path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE tasks(id TEXT PRIMARY KEY,check_id TEXT NOT NULL,route TEXT NOT NULL,
                    eligibility TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
                    owner TEXT,claim TEXT,result TEXT,updated REAL NOT NULL);
                CREATE INDEX task_queue ON tasks(status,check_id);
                CREATE TABLE events(seq INTEGER PRIMARY KEY,at REAL NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);
                CREATE TABLE usage(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            """)
            config = {"schema_version": 1, "depth": depth, "excluded": list(dict.fromkeys(excluded)),
                      "promotions": {}, "capabilities": [], "applicability": {}, "discovery_complete": False, "state": "ready",
                      "created": time.time(), "started": None, "elapsed": 0, "stopped": None,
                      "reason": "", "actions": 0, "revision": 0, "wave": 0, "limits": limits,
                      "usage": {"tokens": None, "known_tokens": 0, "cost": None, "currency": None,
                                "updated": None, "complete": False}}
            db.execute("INSERT INTO metadata VALUES('config',?)", (dumps(config),))
        self.refresh()
        return self.snapshot()

    @staticmethod
    def validate_ids(ids):
        if not isinstance(ids, (list, tuple)) or any(not isinstance(v, str) for v in ids):
            raise ValueError("Expected a list of test ids")
        invalid = [v for v in ids if v not in catalog() or not catalog()[v]["configurable"]]
        if invalid:
            raise ValueError("Unknown or non-configurable test: " + ", ".join(invalid))

    @staticmethod
    def validate_limits(limits):
        if set(limits) - {"max_actions", "max_seconds", "max_tokens", "max_browsers"}:
            raise ValueError("Unknown audit limit")
        for name, value in limits.items():
            if name == "max_browsers" and (type(value) is not int or not 1 <= value <= 64):
                raise ValueError("max_browsers must be between 1 and 64")
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer or null")

    @staticmethod
    def selected(item, config):
        priority = config["promotions"].get(item["id"], item["priority"])
        return (item["configurable"] and item["id"] not in config["excluded"]
                and int(priority[1:]) <= DEPTHS[config["depth"]])

    def configure(self, *, depth=None, excluded=None, limits=None, promotions=None, capabilities=None, applicability=None,
                  test_id=None, enabled=None, reset=False):
        if test_id is not None or enabled is not None:
            self.validate_ids([test_id])
            if type(enabled) is not bool or excluded is not None or reset:
                raise ValueError("Toggle needs a boolean enabled value and cannot replace the exclusion list")
        if type(reset) is not bool:
            raise ValueError("reset must be a boolean")
        if depth is not None and depth not in DEPTHS:
            raise ValueError("Unknown audit depth")
        if excluded is not None:
            self.validate_ids(excluded)
        if limits is not None:
            if not isinstance(limits, dict):
                raise ValueError("limits must be an object")
            self.validate_limits(limits)
        if promotions is not None:
            if not isinstance(promotions, dict):
                raise ValueError("promotions must be an object")
            self.validate_ids(list(promotions))
            if any(v not in {"P1", "P2", "P3"} or int(v[1]) > int(catalog()[k]["priority"][1])
                   for k, v in promotions.items()):
                raise ValueError("Context may promote priority, not lower it")
        if capabilities is not None and (not isinstance(capabilities, list) or any(v not in CAPABILITIES for v in capabilities)):
            raise ValueError("Unknown prerequisite capability")
        if applicability is not None:
            if not isinstance(applicability, dict):
                raise ValueError("applicability must be an object")
            self.validate_ids(list(applicability))
            for decision in applicability.values():
                if (not isinstance(decision, dict) or decision.get("state") not in {"eligible", "not-applicable", "blocked"}
                        or not isinstance(decision.get("reason"), str) or not decision["reason"].strip()):
                    raise ValueError("Applicability needs a state and a factual reason")
                self.evidence(decision.get("evidence"))
        with self.db(True) as db:
            config = self.config(db)
            if depth is not None and depth != config["depth"]:
                for key, default in LIMITS[config["depth"]].items():
                    if config["limits"][key] == default and (limits is None or key not in limits):
                        config["limits"][key] = LIMITS[depth][key]
            for key, value in (("depth", depth), ("excluded", excluded), ("promotions", promotions),
                               ("capabilities", capabilities), ("applicability", applicability)):
                if value is not None:
                    config[key] = list(dict.fromkeys(value)) if key in {"excluded", "capabilities"} else value
            if limits is not None:
                config["limits"].update(limits)
            if test_id is not None:
                current = set(config["excluded"])
                current.discard(test_id) if enabled else current.add(test_id)
                config["excluded"] = sorted(current)
            if reset:
                config["excluded"] = [key for key in config["excluded"] if
                    int(config["promotions"].get(key, catalog()[key]["priority"])[1:]) > DEPTHS[config["depth"]]]
            self.save(db, config, "selection", {"depth": config["depth"], "excluded": config["excluded"]})
        if capabilities is not None or applicability is not None:
            self.refresh()
        return self.snapshot()

    def refresh(self, discovery_complete=None):
        from .private_state import read_json
        path = self.folder / "fields.json"
        with self.db(True) as db:
            # Read after acquiring the transaction: a refresh that waited for
            # another writer must not restore an older inventory's task set.
            inventory = read_json(path) if path.is_file() else {"pages": []}
            pages = inventory.get("pages", [])
            if not isinstance(pages, list) or any(not isinstance(p, dict) or not isinstance(p.get("url"), str) for p in pages):
                raise ValueError("Invalid fields inventory")
            if discovery_complete and not pages:
                raise ValueError("Complete discovery requires a saved page inventory")
            config = self.config(db)
            if discovery_complete is not None:
                config["discovery_complete"] = bool(discovery_complete)
            for item in catalog().values():
                if not item["configurable"]:
                    continue
                matching = [p for p in pages if checks.applicable([dict(item, scope="safe")], p.get("kinds", []),
                                                                   p.get("features", []), scopes=None)]
                # Generic coordination work is once per run; QA/inspection is per discovered page.
                page_scoped = item["kind"] in {"qa-check", "page-check"}
                targets = matching if page_scoped else ([{"url": ""}] if pages else [])
                need = set(item["requires"]) - set(config["capabilities"])
                if not targets:
                    eligibility = "not-applicable" if config["discovery_complete"] else "needs-discovery"
                    targets = [{"url": ""}]
                    reason = "No matching controls in the completed inventory" if config["discovery_complete"] else "Page inventory is incomplete"
                elif need:
                    eligibility, reason = "blocked", "Missing: " + ", ".join(sorted(need))
                else:
                    eligibility, reason = "eligible", ""
                decision = config.get("applicability", {}).get(item["id"])
                if decision:
                    eligibility, reason = decision["state"], decision["reason"]
                    if eligibility == "eligible" and need:
                        eligibility, reason = "blocked", "Missing: " + ", ".join(sorted(need))
                wanted = set()
                for target in targets:
                    route = target["url"] if page_scoped else ""
                    task_id = item["id"] + ":" + hashlib.sha256(route.encode()).hexdigest()[:12]
                    wanted.add(task_id)
                    db.execute("""INSERT INTO tasks(id,check_id,route,eligibility,reason,updated) VALUES(?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET eligibility=excluded.eligibility,reason=excluded.reason""",
                               (task_id, item["id"], route, eligibility, reason, time.time()))
                for previous in db.execute("SELECT id,status FROM tasks WHERE check_id=?", (item["id"],)).fetchall():
                    if previous["id"] not in wanted:
                        if previous["status"] == "pending":
                            db.execute("DELETE FROM tasks WHERE id=?", (previous["id"],))
                        else:
                            db.execute("UPDATE tasks SET eligibility='review-context',reason='Context changed; result retained' WHERE id=?", (previous["id"],))
            self.save(db, config, "inventory", {"pages": len(pages), "complete": config["discovery_complete"]})

    @staticmethod
    def elapsed(config):
        return config["elapsed"] + (time.time() - config["started"] if config["started"] else 0)

    def _gate(self, db, config):
        if config["state"] != "running":
            return config["reason"] or "Audit is " + config["state"]
        limits = config["limits"]
        reason = None
        if limits["max_seconds"] and self.elapsed(config) >= limits["max_seconds"]:
            reason = "Time limit reached"
        elif limits["max_actions"] and config["actions"] >= limits["max_actions"]:
            reason = "Action limit reached"
        elif limits["max_tokens"] is not None:
            if config["usage"]["known_tokens"] >= limits["max_tokens"]:
                reason = "Measured token limit reached"
            elif not config["usage"]["complete"]:
                reason = "Token limit configured but complete host usage is unavailable"
            elif not config["usage"]["updated"] or time.time() - config["usage"]["updated"] > 30:
                reason = "Host token measurements are stale (more than 30 seconds)"
        if reason:
            self._stop(db, config, reason)
        return reason

    def gate(self, consume=False):
        with self.db(True) as db:
            config = self.config(db)
            reason = self._gate(db, config)
            if not reason and consume:
                config["actions"] += 1
                self.save(db, config, "action", {"actions": config["actions"]})
            return reason

    def _stop(self, db, config, reason):
        config["elapsed"] = self.elapsed(config)
        config.update(state="stopped", started=None, stopped=time.time(), reason=reason)
        self.save(db, config, "stopped", {"reason": reason})

    def stop(self, reason="Stopped by user"):
        with self.db(True) as db:
            config = self.config(db)
            # Even a repeated Stop invalidates an older delayed Start request.
            self._stop(db, config, reason)
        return self.snapshot()

    def start(self, expected_revision=None):
        if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
            raise ValueError("Expected revision must be a non-negative integer")
        with self.db(True) as db:
            config = self.config(db)
            if expected_revision is not None and config["revision"] != expected_revision:
                raise ValueError("Audit changed; refresh before starting")
            changed = db.execute("""UPDATE tasks SET status='pending',owner=NULL,claim=NULL,updated=?
                WHERE status='inconclusive' AND json_extract(result,'$.retryable')=1""", (time.time(),)).rowcount
            if changed:
                self.save(db, config, "resumed-tasks", {"tasks": changed})
            if config["state"] != "running":
                config.update(state="running", started=time.time(), stopped=None, reason="")
                self.save(db, config, "started")
            reason = self._gate(db, config)
        return {"ok": not reason, "reason": reason, **self.snapshot()}

    def claim(self, owner, executor="agent", limit=2, route=None):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", owner) or executor not in {"agent", "audit", "fields", "coordinator"}:
            raise ValueError("Invalid owner or executor")
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError("Claim limit must be between 1 and 25")
        with self.db(True) as db:
            config = self.config(db)
            reason = self._gate(db, config)
            if reason:
                return {"tasks": [], "reason": reason}
            selected = [item for item in catalog().values() if self.selected(item, config)]
            clauses, parameters = [], []
            for status, ids in (("pending", [item["id"] for item in selected if item["executor"] == executor]),
                                ("measured", [item["id"] for item in selected] if executor == "coordinator" else [])):
                if ids:
                    clauses.append("(status=? AND check_id IN (" + ",".join("?" for _ in ids) + "))")
                    parameters.extend([status, *ids])
            if not clauses:
                return {"tasks": [], "reason": None}
            query = "SELECT id,check_id,route,status,result FROM tasks WHERE eligibility='eligible' AND (" + " OR ".join(clauses) + ")"
            if route is not None:
                query += " AND route=?"
                parameters.append(route)
            query += " ORDER BY CASE check_id " + " ".join("WHEN ? THEN ?" for _ in selected) + " END,route,id LIMIT ?"
            for item in selected:
                parameters.extend([item["id"], int(config["promotions"].get(item["id"], item["priority"])[1:])])
            candidates = db.execute(query, (*parameters, limit)).fetchall()
            chosen = []
            for row in candidates:
                claim = uuid.uuid4().hex
                db.execute("UPDATE tasks SET status='running',owner=?,claim=?,updated=? WHERE id=?", (owner, claim, time.time(), row["id"]))
                item = catalog()[row["check_id"]]
                chosen.append({"task_id": row["id"], "check_id": row["check_id"], "route": row["route"], "claim": claim,
                               "title": item["title"], "try": item.get("try", item["title"]),
                               "expect": item.get("expect", "Establish the expected behavior from the product before judging."),
                               "proof": item.get("proof", "Record the actual outcome and local evidence."), "executor": executor,
                               "measurement": json.loads(row["result"]) if row["result"] else None})
            if chosen:
                self.save(db, config, "claimed", {"owner": owner, "tasks": [t["task_id"] for t in chosen]})
        return {"tasks": chosen, "reason": None}

    def evidence(self, references):
        if not isinstance(references, list) or not references:
            raise ValueError("A result requires recorded evidence")
        for ref in references:
            if not isinstance(ref, str) or not ref.strip():
                raise ValueError("Invalid evidence reference")
            path = (self.folder / ref).resolve()
            if not path.is_relative_to(self.folder) or not path.is_file() or path.stat().st_size == 0:
                raise ValueError("Evidence must be a non-empty file inside the audit session")
        return references

    def record(self, task_id, status, summary, evidence=None, owner=None, claim=None, retryable=False):
        if type(retryable) is not bool or (retryable and status != "inconclusive"):
            raise ValueError("Only inconclusive attempts can be retryable")
        if status not in FINISHED | {"measured"} or not isinstance(summary, str) or not summary.strip() or len(summary) > 4000:
            raise ValueError("Supply a valid result status and a concise outcome")
        references = self.evidence(evidence) if status in {"passed", "failed", "measured"} else (self.evidence(evidence) if evidence else [])
        with self.db(True) as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown audit task")
            if owner is not None and (row["owner"] != owner or row["claim"] != claim or row["status"] != "running"):
                raise ValueError("This task is not assigned to this worker claim")
            config = self.config(db)
            result = {"status": status, "summary": summary, "evidence": references, "recorded": time.time(), "owner": owner,
                      "retryable": retryable}
            stored_status = "pending" if retryable and config["state"] == "running" else status
            db.execute("UPDATE tasks SET status=?,result=?,updated=? WHERE id=?", (stored_status, dumps(result), time.time(), task_id))
            self.save(db, config, "result", {"task_id": task_id, **result})
        return result

    def release(self, owner, reason="Worker finished without a result"):
        # Requeue work, never convert an unreported check into a pass.
        with self.db(True) as db:
            changed = db.execute("UPDATE tasks SET status=CASE WHEN json_extract(result,'$.status')='measured' THEN 'measured' ELSE 'pending' END,owner=NULL,claim=NULL,updated=? WHERE owner=? AND status='running'",
                                 (time.time(), owner)).rowcount
            if changed:
                self.save(db, self.config(db), "released", {"owner": owner, "reason": reason, "tasks": changed})

    def task_allowed(self, task_id):
        with self.db() as db:
            row = db.execute("SELECT check_id,status,eligibility FROM tasks WHERE id=?", (task_id,)).fetchone()
            return bool(row and row["status"] == "running" and row["eligibility"] == "eligible"
                        and self.selected(catalog()[row["check_id"]], self.config(db)))

    def fault_allowed(self, fault_type):
        return fault_type in self.fault_selection()

    def fault_selection(self):
        with self.db() as db:
            config = self.config(db)
            return {item["fault"] for item in catalog().values() if item["fault"] and self.selected(item, config)
                    and set(item["requires"]) <= set(config["capabilities"])
                    and config.get("applicability", {}).get(item["id"], {}).get("state", "eligible") == "eligible"}

    def measure(self, executor, route, evidence):
        """Store deterministic signals for review, never turn a tool run into a pass."""
        references = self.evidence(evidence)
        with self.db(True) as db:
            config = self.config(db)
            # A running review owns the previously saved measurement. A later
            # page scan must not invalidate that claim or replace its evidence.
            rows = list(db.execute("""SELECT id,check_id FROM tasks WHERE route=?
                AND status IN ('pending','running') AND eligibility='eligible'
                AND NOT (status='running' AND COALESCE(json_extract(result,'$.status'),'')='measured')""", (route,)))
            ids = [r["id"] for r in rows if catalog()[r["check_id"]]["executor"] == executor
                   and self.selected(catalog()[r["check_id"]], config)]
            result = {"status": "measured", "summary": "Tool signals recorded; review expected behavior before judging",
                      "evidence": references, "recorded": time.time(), "owner": executor}
            for task_id in ids:
                db.execute("UPDATE tasks SET status='measured',result=?,owner=NULL,claim=NULL,updated=? WHERE id=?",
                           (dumps(result), time.time(), task_id))
            if ids:
                self.save(db, config, "measured", {"tasks": ids, "evidence": references})

    def next_wave(self):
        with self.db(True) as db:
            config = self.config(db)
            config["wave"] += 1
            self.save(db, config, "wave")
            return config["wave"]

    def execute(self, task_id, command):
        """Run a coordinator tool under this task's stop gate; record output for review."""
        import sys
        from .owned_process import OwnedProcess
        allowed = {"fields", "audit", "replay", "vary", "compare", "probe", "integrations", "visual", "regression"}
        if not command or command[0] not in allowed:
            raise ValueError("execute accepts a Chaosfolk test command: " + ", ".join(sorted(allowed)))
        refusal = self.gate(consume=True)
        if refusal or not self.task_allowed(task_id):
            raise ValueError(refusal or "Claim an enabled task before executing its tool")
        with self.db() as db:
            task = dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
        relative = "audit-evidence/tool-" + uuid.uuid4().hex + ".log"
        output = self.folder / relative
        output.parent.mkdir(exist_ok=True)
        reason, retryable = None, False
        with output.open("wb") as stream:
            stream.write(("chaosfolk " + " ".join(command) + "\n").encode())
            stream.flush()
            process = OwnedProcess([sys.executable, "-m", "chaosfolk", *command], stdout=stream, stderr=stream)
            try:
                while process.poll() is None:
                    reason = self.gate()
                    retryable = bool(reason)
                    if not reason:
                        with self.db() as db:
                            row = db.execute("SELECT status,check_id,eligibility,claim FROM tasks WHERE id=?", (task_id,)).fetchone()
                            selected = (row and row["eligibility"] == "eligible"
                                        and self.selected(catalog()[row["check_id"]], self.config(db)))
                        # fields/audit may have saved their measurement. A
                        # replacement running claim belongs to another attempt.
                        owned = row and row["status"] == "running" and row["claim"] == task["claim"]
                        if not selected or not (owned or row["status"] == "measured"):
                            reason = "Test disabled or claim released"
                            retryable = True
                    if output.stat().st_size > 10 * 1024 * 1024:
                        reason = "Tool output exceeded 10 MiB"
                        retryable = False
                    if reason:
                        break
                    time.sleep(0.2)
            finally:
                process.close()
        status = "inconclusive" if reason or process.returncode else "measured"
        summary = reason or f"Tool exit {process.returncode}; review the recorded output and assertions"
        # The tool may already have released its measurement; coordinator review remains required.
        with self.db() as db:
            current = db.execute("SELECT status,owner,claim FROM tasks WHERE id=?", (task_id,)).fetchone()
        if current and current["status"] == "running" and current["claim"] == task["claim"]:
            self.record(task_id, status, summary, [relative], task["owner"], task["claim"], retryable=retryable)
        elif not current or current["status"] != "measured":
            return {"ok": False, "status": "inconclusive", "evidence": relative,
                    "reason": "Task claim changed; output preserved without replacing its newer result", "returncode": process.returncode}
        return {"ok": not reason and process.returncode == 0, "status": status, "evidence": relative,
                "reason": reason, "returncode": process.returncode, "owner": task["owner"]}

    def usage(self, events, complete=False):
        from .usage import summarize
        if not isinstance(events, list) or len(events) > 10000:
            raise ValueError("Supply up to 10000 host usage events per import")
        with self.db(True) as db:
            config = self.config(db)
            aggregate = config.get("usage_totals", {"events": 0, "tokens": 0, "cost": 0,
                         "missing_tokens": 0, "missing_cost": 0, "currency": None})
            for event in events:
                # Reuse existing strict source, number, currency and duplicate validation.
                currency = event.get("currency", config["usage"]["currency"] or "USD") if isinstance(event, dict) else "USD"
                summarize([event], currency=currency)
                previous = db.execute("SELECT payload FROM usage WHERE id=?", (event["id"],)).fetchone()
                if previous and json.loads(previous[0]) != event:
                    raise ValueError("Conflicting duplicate usage event")
                if previous:
                    continue
                if event.get("cost") is not None:
                    if aggregate["currency"] not in {None, event["currency"]}:
                        raise ValueError("Mixed currencies are not supported")
                    aggregate["currency"] = event["currency"]
                aggregate["events"] += 1
                aggregate["tokens"] += (event.get("input_tokens") or 0) + (event.get("output_tokens") or 0)
                aggregate["cost"] += event.get("cost") or 0
                aggregate["missing_tokens"] += int(event.get("input_tokens") is None or event.get("output_tokens") is None)
                aggregate["missing_cost"] += int(event.get("cost") is None)
                db.execute("INSERT INTO usage VALUES(?,?)", (event["id"], dumps(event)))
            known = bool(complete and aggregate["events"] and not aggregate["missing_tokens"])
            config["usage_totals"] = aggregate
            config["usage"] = {"tokens": aggregate["tokens"] if known else None, "known_tokens": aggregate["tokens"],
                               "cost": round(aggregate["cost"], 8) if complete and aggregate["events"] and not aggregate["missing_cost"] else None,
                               "currency": aggregate["currency"], "updated": time.time(), "complete": known}
            self.save(db, config, "usage", config["usage"])
            self._gate(db, config)
        return self.snapshot()

    def snapshot(self, after=None, details=False):
        with self.db() as db:
            config = self.config(db)
            if after is not None and config["revision"] == after:
                return None
            by_check = {}
            counts = {}
            tasks = []
            query = ("SELECT *,1 AS n FROM tasks ORDER BY check_id,route" if details else
                     "SELECT check_id,eligibility,status,COUNT(*) AS n FROM tasks GROUP BY check_id,eligibility,status")
            for row in db.execute(query):
                item = catalog()[row["check_id"]]
                selected = self.selected(item, config)
                state = ("excluded-by-user" if item["id"] in config["excluded"] else "outside-depth") if not selected else (
                    row["eligibility"] if row["eligibility"] != "eligible" else row["status"])
                counts[state] = counts.get(state, 0) + row["n"]
                bucket = by_check.setdefault(item["id"], {})
                bucket[state] = bucket.get(state, 0) + row["n"]
                if details:
                    tasks.append({**dict(row), "effective_status": state,
                                  "result": json.loads(row["result"]) if row["result"] else None})
            items = [{k: v for k, v in item.items() if k in {"id", "title", "category", "priority", "executor", "requires", "configurable", "kind"}}
                     | {"selected": self.selected(item, config), "states": by_check.get(item["id"], {}),
                        "excluded": item["id"] in config["excluded"], "priority": config["promotions"].get(item["id"], item["priority"])}
                     for item in catalog().values()]
            unresolved = sum(counts.get(s, 0) for s in ("pending", "running", "measured", "blocked", "needs-discovery", "inconclusive", "review-context"))
            tested = sum(counts.get(s, 0) for s in ("passed", "failed"))
            result = {"config": config, "elapsed": round(self.elapsed(config), 1), "counts": counts, "entries": items,
                      "completion": "complete" if config["discovery_complete"] and tested > 0 and not unresolved else "partial",
                      "tested": tested, "unresolved": unresolved,
                      "measurement_note": "Host measurements only. Active model requests cannot be cancelled by this browser engine."}
            if details:
                result["tasks"] = tasks
            elif after is not None:
                result["entries_mode"] = "patch"
                result["entries"] = [{key: item[key] for key in ("id", "priority", "selected", "excluded", "states")}
                                     for item in items if item["configurable"]]
            return result

    def outstanding(self, limit=25, offset=0):
        """Bounded coordinator view for blockers and unassigned work, without evidence bodies."""
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
            raise ValueError("Use a limit between 1 and 100 and a non-negative offset")
        with self.db() as db:
            config = self.config(db)
            selected = [item["id"] for item in catalog().values() if self.selected(item, config)]
            if not selected:
                return {"tasks": [], "next_offset": None}
            marks = ",".join("?" for _ in selected)
            rows = list(db.execute(f"""SELECT id,check_id,route,eligibility,reason,status,owner FROM tasks
                WHERE check_id IN ({marks}) AND eligibility!='not-applicable'
                AND (status NOT IN ('passed','failed') OR eligibility!='eligible')
                ORDER BY check_id,route LIMIT ? OFFSET ?""", (*selected, limit + 1, offset)))
            return {"tasks": [dict(row) | {"executor": catalog()[row["check_id"]]["executor"]} for row in rows[:limit]],
                    "next_offset": offset + limit if len(rows) > limit else None}


def compact(snapshot):
    """Human/agent CLI responses stay small; the browser receives the catalog separately."""
    config = snapshot["config"]
    return {key: snapshot[key] for key in ("elapsed", "counts", "completion", "tested", "unresolved")} | {
        "depth": config["depth"], "state": config["state"], "reason": snapshot.get("reason") or config["reason"],
        "revision": config["revision"], "actions": config["actions"], "limits": config["limits"], "usage": config["usage"],
        "selected_tests": sum(e["selected"] for e in snapshot["entries"]), "excluded_tests": len(config["excluded"]),
        **({"ok": snapshot["ok"]} if "ok" in snapshot else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="chaosfolk audit-run", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--depth", choices=DEPTHS, default="standard")
    init.add_argument("--exclude", default="")
    for key in ("tokens", "seconds", "actions"):
        init.add_argument("--max-" + key, type=int)
    configure = sub.add_parser("configure")
    configure.add_argument("--input", type=Path, required=True)
    refresh = sub.add_parser("refresh")
    refresh.add_argument("--complete", action="store_true", default=None)
    sub.add_parser("start")
    sub.add_parser("stop")
    status = sub.add_parser("status")
    status.add_argument("--details", action="store_true")
    status.add_argument("--pending", action="store_true", help="bounded page of outstanding tasks")
    status.add_argument("--limit", type=int, default=25)
    status.add_argument("--offset", type=int, default=0)
    claim = sub.add_parser("next")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--executor", choices=("agent", "audit", "fields", "coordinator"), default="coordinator")
    claim.add_argument("--limit", type=int, default=5)
    record = sub.add_parser("record")
    record.add_argument("--input", type=Path, required=True)
    release = sub.add_parser("release")
    release.add_argument("--owner", required=True)
    execute = sub.add_parser("execute")
    execute.add_argument("--task", required=True)
    usage = sub.add_parser("usage")
    usage.add_argument("--input", type=Path, required=True)
    usage.add_argument("--complete", action="store_true", help="measurements include coordinator and every worker")
    sub.add_parser("dashboard")
    sub.add_parser("dashboard-close")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=0)
    for child in sub.choices.values():
        child.add_argument("--folder", required=True)
    execute.add_argument("tool", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    session = Session(args.folder)
    if args.command == "init":
        value = session.create(args.depth, [v for v in args.exclude.split(",") if v], args.max_tokens, args.max_seconds, args.max_actions)
    elif args.command == "configure":
        value = session.configure(**json.loads(args.input.read_text(encoding="utf-8-sig")))
    elif args.command == "refresh":
        session.refresh(args.complete)
        value = session.snapshot()
    elif args.command in {"start", "stop"}:
        value = getattr(session, args.command)()
    elif args.command == "next":
        value = session.claim(args.owner, args.executor, args.limit)
    elif args.command == "record":
        data = json.loads(args.input.read_text(encoding="utf-8-sig"))
        value = [session.record(**item) for item in (data if isinstance(data, list) else [data])]
    elif args.command == "release":
        session.release(args.owner)
        value = session.snapshot()
    elif args.command == "execute":
        command = args.tool[1:] if args.tool[:1] == ["--"] else args.tool
        value = session.execute(args.task, command)
    elif args.command == "usage":
        value = session.usage([json.loads(line) for line in args.input.read_text(encoding="utf-8-sig").splitlines() if line.strip()], args.complete)
    elif args.command in {"serve", "dashboard", "dashboard-close"}:
        from .audit_dashboard import serve, launch, close
        if args.command == "serve":
            serve(session, args.port)
            return 0
        value = close(session) if args.command == "dashboard-close" else launch(session)
    else:
        value = session.outstanding(args.limit, args.offset) if args.pending else session.snapshot(details=args.details)
    if isinstance(value, dict) and "entries" in value and not (args.command == "status" and args.details):
        value = compact(value)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 1 if isinstance(value, dict) and value.get("ok") is False else 0
