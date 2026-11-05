"""SQLite ledger of audits. The daily quota and the per-IP limit are checked in the same transaction as the insert."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import sqlite3

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
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS audits_day ON audits(day);
CREATE INDEX IF NOT EXISTS audits_status ON audits(status, created_at);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

ACTIVE = ("queued", "running")


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


class Store:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            row = db.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()
            if row is None:
                db.execute("INSERT INTO meta VALUES ('salt', ?)", (secrets.token_hex(32),))
                row = db.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()
            self.salt = row[0]

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
        """Store a salted hash, not the address: enough to enforce the limit and trace abuse on request."""
        return hashlib.sha256(f"{self.salt}:{ip}".encode()).hexdigest()

    def used_today(self, moment=None):
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM audits WHERE day = ?", (today(moment),)).fetchone()[0]

    def create(self, url, host, lang, ip, quota, per_ip, moment=None):
        moment = moment or now()
        day, ip_hash = today(moment), self.hash_ip(ip)
        audit_id = secrets.token_urlsafe(18)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                if db.execute("SELECT COUNT(*) FROM audits WHERE day = ?", (day,)).fetchone()[0] >= quota:
                    raise QuotaExceeded("daily")
                mine = db.execute("SELECT COUNT(*) FROM audits WHERE day = ? AND ip_hash = ?", (day, ip_hash)).fetchone()[0]
                if mine >= per_ip:
                    raise QuotaExceeded("ip")
                db.execute(
                    "INSERT INTO audits (id, url, host, lang, ip_hash, day, status, phase, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'queued', 'Waiting in line', ?)",
                    (audit_id, url, host, lang, ip_hash, day, moment.isoformat()))
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
            audit = dict(row)
            audit["position"] = 0
            if audit["status"] == "queued":
                audit["position"] = db.execute(
                    "SELECT COUNT(*) FROM audits WHERE status = 'running'"
                    " OR (status = 'queued' AND created_at <= ?)", (audit["created_at"],)).fetchone()[0]
            return audit

    def claim(self, moment=None):
        moment = moment or now()
        with self.connect() as db:
            row = db.execute(
                "UPDATE audits SET status = 'running', phase = 'Starting the browsers', started_at = ?"
                " WHERE id = (SELECT id FROM audits WHERE status = 'queued' ORDER BY created_at LIMIT 1)"
                " AND status = 'queued' RETURNING *", (moment.isoformat(),)).fetchone()
            return dict(row) if row else None

    def set_phase(self, audit_id, phase):
        with self.connect() as db:
            db.execute("UPDATE audits SET phase = ? WHERE id = ? AND status = 'running'", (phase[:200], audit_id))

    def finish(self, audit_id, status, error="", moment=None):
        moment = moment or now()
        phase = {"done": "Report ready", "failed": "Stopped"}.get(status, "")
        with self.connect() as db:
            db.execute("UPDATE audits SET status = ?, phase = ?, error = ?, finished_at = ? WHERE id = ?",
                       (status, phase, error[:500], moment.isoformat(), audit_id))

    def recover(self):
        """After a restart, an audit marked running has no process behind it any more."""
        with self.connect() as db:
            db.execute("UPDATE audits SET status = 'failed', phase = 'Stopped', error = 'The server restarted during the audit.',"
                       " finished_at = ? WHERE status = 'running'", (now().isoformat(),))

    def expire(self, days, moment=None):
        cutoff = ((moment or now()) - timedelta(days=days)).isoformat()
        with self.connect() as db:
            rows = db.execute("UPDATE audits SET status = 'expired', phase = 'Report deleted'"
                              " WHERE status IN ('done', 'failed') AND finished_at < ? RETURNING id", (cutoff,)).fetchall()
            return [row[0] for row in rows]
