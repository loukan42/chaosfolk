"""Process the queue one audit at a time: one Chromium fleet and one model session per server."""
import logging
import shutil
import time

from . import runner, urls
from .config import Settings
from .store import Store

log = logging.getLogger("chaosfolk_web.worker")


def purge(settings, store):
    for audit_id in store.expire(settings.report_days):
        shutil.rmtree(settings.job_dir(audit_id), ignore_errors=True)


def process(settings, store, audit):
    job_dir = settings.job_dir(audit["id"])
    try:
        # DNS may have changed since the form was sent; check again just before the browsers start.
        urls.check_public(audit["host"])
        store.set_phase(audit["id"], "Simulated users are exploring your site")
        runner.run(settings, audit, job_dir)
    except (runner.RunFailed, urls.RejectedUrl) as error:
        log.warning("audit %s failed: %s", audit["id"], error)
        store.finish(audit["id"], "failed", str(error))
        return
    except Exception:
        log.exception("audit %s crashed", audit["id"])
        store.finish(audit["id"], "failed", "An unexpected error stopped the audit.")
        return
    store.finish(audit["id"], "done")


def loop(settings=None, idle=3, once=False):
    settings = settings or Settings()
    store = Store(settings.database)
    store.recover()
    last_purge = 0
    while True:
        if time.monotonic() - last_purge > 3600:
            purge(settings, store)
            last_purge = time.monotonic()
        audit = store.claim()
        if audit:
            process(settings, store, audit)
        elif once:
            return
        else:
            time.sleep(idle)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    loop()


if __name__ == "__main__":
    main()
