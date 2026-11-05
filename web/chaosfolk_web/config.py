"""Settings read from environment variables.

Two modes share the same code:
- `vercel` (default on Vercel): Upstash Redis for the queue, Vercel Blob for reports, Vercel Sandbox for audits.
- `local` (default elsewhere): SQLite and files under CHAOSFOLK_WEB_DATA, and the offline Chaosfolk demo
  instead of a real audit, for development and tests.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path


def _env(*names, default=""):
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _int(name, default, minimum=0):
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    mode: str = field(default_factory=lambda: _env("CHAOSFOLK_WEB_MODE", default="vercel" if os.environ.get("VERCEL") else "local"))
    data_dir: Path = field(default_factory=lambda: Path(_env("CHAOSFOLK_WEB_DATA", default="web-data")).resolve())
    daily_quota: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_DAILY_QUOTA", 3))
    per_ip_daily: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_PER_IP_DAILY", 1, 1))
    allowed_origins: tuple = field(default_factory=lambda: tuple(
        o.strip() for o in _env("CHAOSFOLK_WEB_ALLOWED_ORIGINS", default="https://loukan42.github.io").split(",") if o.strip()))
    public_url: str = field(default_factory=lambda: _env(
        "CHAOSFOLK_WEB_PUBLIC_URL",
        default=f"https://{os.environ['VERCEL_PROJECT_PRODUCTION_URL']}" if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
        else "http://127.0.0.1:8000").rstrip("/"))
    turnstile_secret: str = field(default_factory=lambda: _env("CHAOSFOLK_WEB_TURNSTILE_SECRET"))
    cron_secret: str = field(default_factory=lambda: _env("CRON_SECRET"))
    audit_minutes: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_AUDIT_MINUTES", 10, 1))
    max_actions: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_MAX_ACTIONS", 80, 1))
    users: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_USERS", 3, 1))
    report_days: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_REPORT_DAYS", 7, 1))
    # Vercel mode
    redis_url: str = field(default_factory=lambda: _env("KV_REST_API_URL", "UPSTASH_REDIS_REST_URL"))
    redis_token: str = field(default_factory=lambda: _env("KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_TOKEN"))
    snapshot_id: str = field(default_factory=lambda: _env("CHAOSFOLK_WEB_SNAPSHOT"))
    model: str = field(default_factory=lambda: _env("CHAOSFOLK_WEB_MODEL"))
    openrouter_key: str = field(default_factory=lambda: _env("OPENROUTER_API_KEY"))
    # The sandbox firewall adds the key to requests for openrouter.ai, so the agent never sees it.
    broker_key: bool = field(default_factory=lambda: _bool("CHAOSFOLK_WEB_BROKER_KEY", True))
    vcpus: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_VCPUS", 2, 1))

    @property
    def audit_seconds(self):
        return self.audit_minutes * 60

    @property
    def database(self):
        return self.data_dir / "audits.sqlite3"

    @property
    def reports_dir(self):
        return self.data_dir / "reports"
