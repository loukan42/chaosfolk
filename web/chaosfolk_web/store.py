"""Audit ledgers. Both keep the same interface:

- `SQLiteStore` for local development and tests;
- `RedisStore` (redis_store.py) for Vercel, where functions keep no disk between requests.

One audit runs at a time. `claim()` takes the oldest queued audit only when none is running.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3
import time

FIELDS = ("id", "url", "host", "lang", "status", "phase", "error", "handle",
          "created_at", "started_at", "finished_at")

SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    host TEXT NOT NULL,
    lang TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    day TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    handle TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS audits_day ON audits(day);
CREATE INDEX IF NOT EXISTS audits_status ON audits(status, created_at);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locks (name TEXT PRIMARY KEY, until REAL NOT NULL);
"""

PHASES = {"queued": "Waiting in line", "running": "Starting the browsers", "done": "Report ready", "failed": "Stopped",
          "expired": "Report deleted"}


class QuotaExceeded(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def now():
    return datetime.now(timezone.utc)


def today(moment=None):
    return (moment or now()).strftime("%Y-%m-%d")


def next_reset(moment=None):
    moment = moment or now()
    return (moment + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def new_id():
    return secrets.token_urlsafe(18)


def hash_ip(salt, ip):
    """Store a salted hash, not the address: enough to enforce the limit and trace abuse on request."""
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()


class SQLiteStore:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {row[1] for row in db.execute("PRAGMA table_info(audits)")}
            if "handle" not in columns:  # ledgers created before the Vercel backend
                db.execute("ALTER TABLE audits ADD COLUMN handle TEXT NOT NULL DEFAULT ''")
            db.execute("INSERT OR IGNORE INTO meta VALUES ('salt', ?)", (secrets.token_hex(32),))
            self.salt = db.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()[0]

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode = WAL")
        db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield db
        finally:
            db.close()

    def hash_ip(self, ip):
        return hash_ip(self.salt, ip)

    def used_today(self, moment=None):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM audits WHERE day = ?", (today(moment),)).fetchone()[0]

    def create(self, url, host, lang, ip, quota, per_ip, moment=None):
        moment = moment or now()
        day, ip_hash, audit_id = today(moment), self.hash_ip(ip), new_id()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT COUNT(*) FROM audits WHERE day = ?", (day,)).fetchone()[0] >= quota:
                    raise QuotaExceeded("daily")
                mine = db.execute("SELECT COUNT(*) FROM audits WHERE day = ? AND ip_hash = ?", (day, ip_hash)).fetchone()[0]
                if mine >= per_ip:
                    raise QuotaExceeded("ip")
                db.execute("INSERT INTO audits (id, url, host, lang, ip_hash, day, status, phase, created_at)"
                           " VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)",
                           (audit_id, url, host, lang, ip_hash, day, PHASES["queued"], moment.isoformat()))
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return audit_id

    def get(self, audit_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM audits WHERE id = ?", (audit_id,)).fetchone()
            if row is None:
                return None
            audit = {key: row[key] for key in FIELDS}
            audit["position"] = 0
            if audit["status"] == "queued":
                audit["position"] = db.execute(
                    "SELECT COUNT(*) FROM audits WHERE status = 'running'"
                    " OR (status = 'queued' AND created_at <= ?)", (audit["created_at"],)).fetchone()[0]
            return audit

    def running(self):
        with self.connect() as db:
            row = db.execute("SELECT id FROM audits WHERE status = 'running' LIMIT 1").fetchone()
        return self.get(row[0]) if row else None

    def claim(self, moment=None):
        moment = moment or now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                row = None
                if not db.execute("SELECT 1 FROM audits WHERE status = 'running'").fetchone():
                    row = db.execute(
                        "UPDATE audits SET status = 'running', phase = ?, started_at = ?"
                        " WHERE id = (SELECT id FROM audits WHERE status = 'queued' ORDER BY created_at LIMIT 1)"
                        " RETURNING id", (PHASES["running"], moment.isoformat())).fetchone()
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
        return self.get(row[0]) if row else None

    def set_handle(self, audit_id, handle):
        with self.connect() as db:
            db.execute("UPDATE audits SET handle = ? WHERE id = ?", (handle, audit_id))

    def set_phase(self, audit_id, phase):
        with self.connect() as db:
            db.execute("UPDATE audits SET phase = ? WHERE id = ? AND status = 'running'", (phase[:200], audit_id))

    def finish(self, audit_id, status, error="", moment=None):
        moment = moment or now()
        with self.connect() as db:
            db.execute("UPDATE audits SET status = ?, phase = ?, error = ?, finished_at = ? WHERE id = ?",
                       (status, PHASES.get(status, ""), error[:500], moment.isoformat(), audit_id))

    def expire(self, days, moment=None):
        cutoff = ((moment or now()) - timedelta(days=days)).isoformat()
        with self.connect() as db:
            rows = db.execute("UPDATE audits SET status = 'expired', phase = ?"
                              " WHERE status IN ('done', 'failed') AND finished_at < ? RETURNING id",
                              (PHASES["expired"], cutoff)).fetchall()
            return [row[0] for row in rows]

    def lock(self, name, seconds):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT until FROM locks WHERE name = ?", (name,)).fetchone()
            if row and row[0] > time.time():
                db.execute("ROLLBACK")
                return False
            db.execute("INSERT OR REPLACE INTO locks VALUES (?, ?)", (name, time.time() + seconds))
            db.execute("COMMIT")
            return True

    def unlock(self, name):
        with self.connect() as db:
            db.execute("DELETE FROM locks WHERE name = ?", (name,))
