"""Audit ledger on Upstash Redis (Vercel Marketplace, free plan), through its REST API.

Keys, all prefixed `cf:`:
- `audit:<id>`   hash of the audit fields, expiring a few days after the report;
- `queue`        list of queued ids, oldest first;
- `running`      id of the running audit (at most one);
- `day:<date>`, `ip:<date>:<hash>`  daily counters;
- `finished`     sorted set of finished ids by time, for expiry;
- `salt`, `lock:<name>`.
"""
from datetime import timedelta
import json
import urllib.request

from .store import FIELDS, PHASES, QuotaExceeded, hash_ip, new_id, now, today

DAY = 86400


class RedisError(RuntimeError):
    pass


class UpstashClient:
    def __init__(self, url, token, opener=urllib.request.urlopen):
        if not url or not token:
            raise RedisError("Set KV_REST_API_URL and KV_REST_API_TOKEN (connect an Upstash Redis database).")
        self.url, self.token, self.opener = url.rstrip("/"), token, opener

    def _post(self, path, payload):
        request = urllib.request.Request(self.url + path, data=json.dumps(payload).encode(), method="POST",
                                         headers={"Authorization": f"Bearer {self.token}",
                                                  "Content-Type": "application/json"})
        with self.opener(request, timeout=15) as response:
            return json.load(response)

    def call(self, *args):
        answer = self._post("", [str(a) for a in args])
        if "error" in answer:
            raise RedisError(answer["error"])
        return answer.get("result")

    def pipeline(self, *commands):
        answers = self._post("/pipeline", [[str(a) for a in command] for command in commands])
        for answer in answers:
            if "error" in answer:
                raise RedisError(answer["error"])
        return [answer.get("result") for answer in answers]


class RedisStore:
    def __init__(self, client, report_days=7, prefix="cf:"):
        self.r, self.days, self.p = client, report_days, prefix
        self.r.call("SET", self.k("salt"), new_id() + new_id(), "NX")
        self.salt = self.r.call("GET", self.k("salt"))

    def k(self, *parts):
        return self.p + ":".join(parts)

    def _hash(self, audit_id):
        values = self.r.call("HGETALL", self.k("audit", audit_id)) or []
        if isinstance(values, dict):
            return values
        return dict(zip(values[::2], values[1::2]))

    def _save(self, audit_id, ttl, **fields):
        flat = [item for pair in fields.items() for item in (pair[0], "" if pair[1] is None else pair[1])]
        self.r.pipeline(["HSET", self.k("audit", audit_id), *flat], ["EXPIRE", self.k("audit", audit_id), ttl])

    def used_today(self, moment=None):
        return int(self.r.call("GET", self.k("day", today(moment))) or 0)

    def create(self, url, host, lang, ip, quota, per_ip, moment=None):
        moment = moment or now()
        day = today(moment)
        day_key, ip_key = self.k("day", day), self.k("ip", day, hash_ip(self.salt, ip))
        # INCR then roll back on refusal: two visitors at the same instant cannot both take the last audit.
        used, _ = self.r.pipeline(["INCR", day_key], ["EXPIRE", day_key, 2 * DAY])
        if int(used) > quota:
            self.r.call("DECR", day_key)
            raise QuotaExceeded("daily")
        mine, _ = self.r.pipeline(["INCR", ip_key], ["EXPIRE", ip_key, 2 * DAY])
        if int(mine) > per_ip:
            self.r.pipeline(["DECR", ip_key], ["DECR", day_key])
            raise QuotaExceeded("ip")
        audit_id = new_id()
        self._save(audit_id, 3 * DAY, id=audit_id, url=url, host=host, lang=lang, status="queued",
                   phase=PHASES["queued"], error="", handle="", created_at=moment.isoformat(),
                   started_at="", finished_at="")
        self.r.call("RPUSH", self.k("queue"), audit_id)
        return audit_id

    def get(self, audit_id):
        raw = self._hash(audit_id)
        if not raw:
            return None
        audit = {key: (raw.get(key) or None) if key.endswith("_at") else raw.get(key, "") for key in FIELDS}
        audit["position"] = 0
        if audit["status"] == "queued":
            index = self.r.call("LPOS", self.k("queue"), audit_id)
            running = self.r.call("GET", self.k("running"))
            audit["position"] = (int(index) + 1 if index is not None else 1) + (1 if running else 0)
        return audit

    def running(self):
        audit_id = self.r.call("GET", self.k("running"))
        audit = self.get(audit_id) if audit_id else None
        if audit_id and (audit is None or audit["status"] != "running"):
            self.r.call("DEL", self.k("running"))
            return None
        return audit

    def claim(self, moment=None):
        moment = moment or now()
        while True:
            audit_id = self.r.call("LINDEX", self.k("queue"), 0)
            if not audit_id:
                return None
            if not self.r.call("SET", self.k("running"), audit_id, "NX"):
                return None
            self.r.call("LREM", self.k("queue"), 1, audit_id)
            if not self._hash(audit_id):
                # The hash expired while it waited: drop the stale id and try the next one.
                self.r.call("DEL", self.k("running"))
                continue
            self._save(audit_id, 3 * DAY, status="running", phase=PHASES["running"], started_at=moment.isoformat())
            return self.get(audit_id)

    def set_handle(self, audit_id, handle):
        self.r.call("HSET", self.k("audit", audit_id), "handle", handle)

    def set_phase(self, audit_id, phase):
        self.r.call("HSET", self.k("audit", audit_id), "phase", phase[:200])

    def finish(self, audit_id, status, error="", moment=None):
        moment = moment or now()
        ttl = (self.days + 2) * DAY
        self._save(audit_id, ttl, status=status, phase=PHASES.get(status, ""), error=error[:500],
                   finished_at=moment.isoformat())
        commands = [["ZADD", self.k("finished"), int(moment.timestamp()), audit_id]]
        if self.r.call("GET", self.k("running")) == audit_id:
            commands.append(["DEL", self.k("running")])
        self.r.pipeline(*commands)

    def expire(self, days, moment=None):
        cutoff = int(((moment or now()) - timedelta(days=days)).timestamp())
        ids = self.r.call("ZRANGEBYSCORE", self.k("finished"), "-inf", cutoff) or []
        for audit_id in ids:
            if self._hash(audit_id):
                self.r.call("HSET", self.k("audit", audit_id), "status", "expired", "phase", PHASES["expired"])
            self.r.call("ZREM", self.k("finished"), audit_id)
        return list(ids)

    def lock(self, name, seconds):
        return bool(self.r.call("SET", self.k("lock", name), "1", "NX", "EX", int(seconds)))

    def unlock(self, name):
        self.r.call("DEL", self.k("lock", name))
