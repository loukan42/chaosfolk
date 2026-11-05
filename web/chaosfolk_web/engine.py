"""Advance the queue one step. There is no long-running worker on Vercel: the API calls `tick()` when
a visitor submits or polls an audit, and a daily cron job calls it for clean-up.

A tick is short. It starts the next audit, checks the running one, or collects a finished report.
"""
from datetime import datetime
import logging

from . import urls
from .backends import BackendError
from .pack import NoReport
from .store import now

log = logging.getLogger("chaosfolk_web.engine")

START_GRACE = 180       # a claimed audit with no sandbox after this many seconds failed to start
COLLECT_MARGIN = 900    # report writing and archive time allowed after the engine limit


def elapsed(audit, moment):
    return (moment - datetime.fromisoformat(audit["started_at"])).total_seconds() if audit.get("started_at") else 0


def tick(settings, store, reports, backend, moment=None):
    if not store.lock("tick", 300):
        return
    try:
        purge(settings, store, reports, moment)
        if store.running() is not None:
            advance(settings, store, reports, backend, moment)
        if store.running() is None:
            start_next(settings, store, backend, moment)
    finally:
        store.unlock("tick")


def purge(settings, store, reports, moment=None):
    expired = store.expire(settings.report_days, moment)
    if expired:
        reports.delete(expired)


def start_next(settings, store, backend, moment=None):
    audit = store.claim(moment)
    if audit is None:
        return
    try:
        # DNS may have changed since the form was sent; check again just before the browsers start.
        urls.check_public(audit["host"])
        store.set_handle(audit["id"], backend.start(settings, audit))
        store.set_phase(audit["id"], "Simulated users are exploring your site")
    except (urls.RejectedUrl, BackendError) as error:
        store.finish(audit["id"], "failed", str(error), moment)
    except Exception:
        log.exception("audit %s did not start", audit["id"])
        store.finish(audit["id"], "failed", "The audit could not start. Try again tomorrow.", moment)


def advance(settings, store, reports, backend, moment=None):
    moment = moment or now()
    audit = store.running()
    seconds = elapsed(audit, moment)
    if not audit["handle"]:
        if seconds > START_GRACE:
            store.finish(audit["id"], "failed", "The audit could not start. Try again tomorrow.", moment)
        return
    try:
        state, error = backend.poll(audit["handle"])
        if state == "running":
            if seconds > settings.audit_seconds + COLLECT_MARGIN:
                backend.stop(audit["handle"])
                store.finish(audit["id"], "failed", "The audit took too long and was stopped.", moment)
            return
        if state == "done":
            store.set_phase(audit["id"], "Writing the report")
            reports.save(audit["id"], backend.collect(audit["handle"]))
            store.finish(audit["id"], "done", "", moment)
        else:
            store.finish(audit["id"], "failed", error or "The audit failed.", moment)
        backend.stop(audit["handle"])
    except (BackendError, NoReport) as failure:
        backend.stop(audit["handle"])
        store.finish(audit["id"], "failed", str(failure), moment)
    except Exception:
        # Usually a transient API error: keep the audit and try again on the next tick, within the time limit.
        log.exception("audit %s could not be checked", audit["id"])
        if seconds > settings.audit_seconds + COLLECT_MARGIN:
            backend.stop(audit["handle"])
            store.finish(audit["id"], "failed", "The audit took too long and was stopped.", moment)
