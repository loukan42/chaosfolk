"""Public API called by the landing page, plus the report pages and archives it links to."""
from datetime import datetime, timedelta
import hmac
import logging
import mimetypes
import re
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from . import engine, pack, turnstile, urls
from .config import Settings
from .reports import read_member
from .store import QuotaExceeded, next_reset

log = logging.getLogger("chaosfolk_web.app")

QUOTA_MESSAGES = {
    "daily": "No free audits are left today. Come back after the reset, or install Chaosfolk to run it yourself.",
    "ip": "You have already used today's free audit. Install Chaosfolk to run more audits yourself.",
}
AUDIT_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
REPORT_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, max-age=300",
}


class AuditRequest(BaseModel):
    url: str = Field(max_length=2000)
    lang: Literal["en", "fr"] = "en"
    authorized: bool = False
    turnstile: str = Field(default="", max_length=4096)


def build(settings):
    """The ledger, report storage and audit backend for the configured mode."""
    if settings.mode == "vercel":
        from .backends import SandboxBackend
        from .redis_store import RedisStore, UpstashClient
        from .reports import BlobReports
        return (RedisStore(UpstashClient(settings.redis_url, settings.redis_token), settings.report_days),
                BlobReports(), SandboxBackend())
    if settings.mode == "local":
        from .backends import DemoBackend
        from .reports import LocalReports
        from .store import SQLiteStore
        return SQLiteStore(settings.database), LocalReports(settings.reports_dir), DemoBackend()
    raise ValueError(f"Unknown CHAOSFOLK_WEB_MODE {settings.mode!r}")


def create_app(settings=None, resolver=None, parts=None):
    settings = settings or Settings()
    store, reports, backend = parts or build(settings)
    app = FastAPI(title="Chaosfolk web audits", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def advance():
        try:
            engine.tick(settings, store, reports, backend)
        except Exception:
            log.exception("queue tick failed")

    def client_ip(request):
        # Vercel sets x-real-ip to the visitor's address and overwrites any value the visitor sends.
        real = request.headers.get("x-real-ip", "").strip() if settings.mode == "vercel" else ""
        return real or (request.client.host if request.client else "unknown")

    def quota():
        used = store.used_today()
        return {"limit": settings.daily_quota, "remaining": max(settings.daily_quota - used, 0),
                "resets_at": next_reset().isoformat()}

    def find(audit_id):
        return store.get(audit_id) if AUDIT_ID.fullmatch(audit_id) else None

    def view(audit):
        done = audit["status"] == "done"
        result = {key: audit[key] for key in ("id", "url", "status", "phase", "error", "position",
                                                "created_at", "started_at", "finished_at")}
        result["report_url"] = f"{settings.public_url}/reports/{audit['id']}/" if done else None
        result["download_url"] = f"{settings.public_url}/api/audits/{audit['id']}/report.zip" if done else None
        result["expires_at"] = None
        if audit["finished_at"] and audit["status"] in {"done", "failed"}:
            result["expires_at"] = (datetime.fromisoformat(audit["finished_at"]) + timedelta(days=settings.report_days)).isoformat()
        result["time_limit_minutes"] = settings.audit_minutes
        return result

    @app.get("/api/health")
    def health():
        return {"ok": True, "mode": settings.mode}

    @app.get("/api/quota")
    def get_quota():
        return quota()

    @app.post("/api/audits", status_code=201)
    async def create(body: AuditRequest, request: Request):
        ip = client_ip(request)
        if not body.authorized:
            raise HTTPException(400, "Confirm that you own this site or are authorized to test it.")
        if not await run_in_threadpool(turnstile.verify, settings.turnstile_secret, body.turnstile, ip):
            raise HTTPException(403, "The anti-robot check failed. Reload the page and try again.")
        try:
            url, host = await run_in_threadpool(urls.validate, body.url, *([resolver] if resolver else []))
        except urls.RejectedUrl as error:
            raise HTTPException(400, str(error)) from None
        try:
            audit_id = await run_in_threadpool(store.create, url, host, body.lang, ip,
                                               settings.daily_quota, settings.per_ip_daily)
        except QuotaExceeded as error:
            raise HTTPException(429, QUOTA_MESSAGES[error.reason]) from None
        await run_in_threadpool(advance)
        return {**view(store.get(audit_id)), "quota": quota()}

    @app.get("/api/audits/{audit_id}")
    def status(audit_id: str):
        if AUDIT_ID.fullmatch(audit_id):
            advance()
        audit = find(audit_id)
        if audit is None:
            raise HTTPException(404, "This audit does not exist or has been deleted.")
        return view(audit)

    @app.get("/api/cron")
    def cron(request: Request):
        # A tick only does what any status poll does, so a secret is optional. When CRON_SECRET is set,
        # Vercel sends it and other callers are refused.
        expected = f"Bearer {settings.cron_secret}"
        if settings.cron_secret and not hmac.compare_digest(request.headers.get("authorization", ""), expected):
            raise HTTPException(401, "Unauthorized.")
        advance()
        return {"ok": True}

    @app.get("/api/audits/{audit_id}/report.zip")
    def download(audit_id: str):
        audit = find(audit_id)
        data = reports.load(audit_id) if audit and audit["status"] == "done" else None
        if data is None:
            raise HTTPException(404, "This report does not exist or has been deleted.")
        name = pack.archive_name(audit["host"], audit["created_at"])
        return Response(data, media_type="application/zip",
                        headers={**REPORT_HEADERS, "Content-Disposition": f'attachment; filename="{name}.zip"'})

    @app.get("/reports/{audit_id}")
    def report_root(audit_id: str):
        # Redirect only to an id read back from the ledger, never to text taken from the request.
        audit = find(audit_id)
        if audit is None:
            raise HTTPException(404, "This report does not exist or has been deleted.")
        return RedirectResponse(f"/reports/{audit['id']}/", status_code=308)

    @app.get("/reports/{audit_id}/{path:path}")
    def report(audit_id: str, path: str = ""):
        audit = find(audit_id)
        archive = reports.local_path(audit_id) if audit and audit["status"] == "done" else None
        if archive is None:
            raise HTTPException(404, "This report does not exist or has been deleted.")
        path = path or "rapport.html"
        data = read_member(archive, path)
        if data is None:
            raise HTTPException(404, "File not found.")
        media = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if media.startswith("text/") or media in {"application/javascript", "application/json"}:
            media += "; charset=utf-8"
        return Response(data, media_type=media, headers={**REPORT_HEADERS, "X-Frame-Options": "DENY"})

    app.state.settings, app.state.store, app.state.reports, app.state.backend = settings, store, reports, backend
    return app
