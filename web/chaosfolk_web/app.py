"""Public API called by the GitHub Pages landing page, plus the report pages it links to."""
from datetime import datetime, timedelta
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from . import turnstile, urls
from .config import Settings
from .store import QuotaExceeded, Store, next_reset

QUOTA_MESSAGES = {
    "daily": "No free audits are left today. Come back after the reset, or install Chaosfolk to run it yourself.",
    "ip": "You have already used today's free audit. Install Chaosfolk to run more audits yourself.",
}
REPORT_HEADERS = {
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "private, max-age=300",
}


class AuditRequest(BaseModel):
    url: str = Field(max_length=2000)
    lang: Literal["en", "fr"] = "en"
    authorized: bool = False
    turnstile: str = Field(default="", max_length=4096)


def create_app(settings=None, resolver=None):
    settings = settings or Settings()
    store = Store(settings.database)
    app = FastAPI(title="Chaosfolk web audits", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins),
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def client_ip(request):
        # Behind Caddy, X-Real-IP is overwritten with the real client address, so a visitor cannot forge it.
        if settings.trust_proxy and request.headers.get("x-real-ip", "").strip():
            return request.headers["x-real-ip"].strip()
        return request.client.host if request.client else "unknown"

    def quota():
        used = store.used_today()
        return {"limit": settings.daily_quota, "remaining": max(settings.daily_quota - used, 0),
                "resets_at": next_reset().isoformat()}

    def view(audit):
        result = {key: audit[key] for key in ("id", "url", "status", "phase", "error", "position",
                                                "created_at", "started_at", "finished_at")}
        result["report_url"] = f"{settings.public_url}/reports/{audit['id']}/" if audit["status"] == "done" else None
        result["expires_at"] = None
        if audit["finished_at"] and audit["status"] in {"done", "failed"}:
            result["expires_at"] = (datetime.fromisoformat(audit["finished_at"]) + timedelta(days=settings.report_days)).isoformat()
        result["time_limit_minutes"] = settings.audit_minutes
        return result

    @app.get("/api/health")
    def health():
        return {"ok": True}

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
            audit_id = store.create(url, host, body.lang, ip, settings.daily_quota, settings.per_ip_daily)
        except QuotaExceeded as error:
            raise HTTPException(429, QUOTA_MESSAGES[error.reason]) from None
        return {**view(store.get(audit_id)), "quota": quota()}

    @app.get("/api/audits/{audit_id}")
    def status(audit_id: str):
        audit = store.get(audit_id)
        if audit is None:
            raise HTTPException(404, "This audit does not exist or has been deleted.")
        return view(audit)

    @app.get("/reports/{audit_id}")
    def report_root(audit_id: str):
        return RedirectResponse(f"/reports/{audit_id}/", status_code=308)

    @app.get("/reports/{audit_id}/{path:path}")
    def report(audit_id: str, path: str = ""):
        audit = store.get(audit_id)
        if audit is None or audit["status"] != "done":
            raise HTTPException(404, "This report does not exist or has been deleted.")
        root = (settings.job_dir(audit_id) / "public").resolve()
        target = (root / (path or "rapport.html")).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(404, "File not found.")
        return FileResponse(target, headers=REPORT_HEADERS)

    app.state.settings, app.state.store = settings, store
    return app


def main():
    import uvicorn
    settings = Settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8000, proxy_headers=False)


if __name__ == "__main__":
    main()
