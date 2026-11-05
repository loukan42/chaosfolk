"""Settings read from environment variables, so the same image runs locally and on the server."""
from dataclasses import dataclass, field
import os
from pathlib import Path


def _int(name, default, minimum=0):
    value = int(os.environ.get(name, default))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def _bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("CHAOSFOLK_WEB_DATA", "web-data")).resolve())
    daily_quota: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_DAILY_QUOTA", 5))
    per_ip_daily: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_PER_IP_DAILY", 1, 1))
    allowed_origins: tuple = field(default_factory=lambda: tuple(
        o.strip() for o in os.environ.get("CHAOSFOLK_WEB_ALLOWED_ORIGINS", "https://loukan42.github.io").split(",") if o.strip()))
    public_url: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"))
    turnstile_secret: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_TURNSTILE_SECRET", ""))
    trust_proxy: bool = field(default_factory=lambda: _bool("CHAOSFOLK_WEB_TRUST_PROXY"))
    runner: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_RUNNER", "docker"))
    runner_image: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_RUNNER_IMAGE", "chaosfolk-runner"))
    runner_network: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_RUNNER_NETWORK", "chaosfolk-audits"))
    model: str = field(default_factory=lambda: os.environ.get("CHAOSFOLK_WEB_MODEL", ""))
    audit_minutes: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_AUDIT_MINUTES", 10, 1))
    max_actions: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_MAX_ACTIONS", 80, 1))
    users: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_USERS", 3, 1))
    report_days: int = field(default_factory=lambda: _int("CHAOSFOLK_WEB_REPORT_DAYS", 7, 1))

    @property
    def database(self):
        return self.data_dir / "audits.sqlite3"

    @property
    def jobs_dir(self):
        return self.data_dir / "jobs"

    def job_dir(self, audit_id):
        return self.jobs_dir / audit_id
