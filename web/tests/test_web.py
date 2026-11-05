from dataclasses import replace
from datetime import datetime, timedelta, timezone
import fnmatch
import io
import json
import socket
import types
import zipfile

import pytest
from fastapi.testclient import TestClient

from chaosfolk_web import backends, engine, pack, turnstile, urls
from chaosfolk_web.app import create_app
from chaosfolk_web.config import Settings
from chaosfolk_web.redis_store import RedisStore
from chaosfolk_web.reports import BlobReports, LocalReports, read_member
from chaosfolk_web.store import QuotaExceeded, SQLiteStore


def fake_resolver(table):
    def resolve(host, port, proto=0):
        if host not in table:
            raise socket.gaierror("not found")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in table[host]]
    return resolve


PUBLIC = fake_resolver({"example.org": ["93.184.215.14"], "evil.example.net": ["93.184.215.14", "10.0.0.5"],
                        "meta.example.net": ["169.254.169.254"], "v6.example.net": ["::ffff:127.0.0.1"]})


class FakeRedis:
    """The Upstash REST commands RedisStore uses, with Upstash's string results."""

    def __init__(self):
        self.data = {}

    def pipeline(self, *commands):
        return [self.call(*command) for command in commands]

    def call(self, name, *args):
        args = [str(a) for a in args]
        name = name.upper()
        d = self.data
        if name == "SET":
            key, value, *flags = args
            if "NX" in flags and key in d:
                return None
            d[key] = value
            return "OK"
        if name == "GET":
            value = d.get(args[0])
            return value if isinstance(value, str) else None
        if name == "DEL":
            return sum(1 for key in args if d.pop(key, None) is not None)
        if name in {"INCR", "DECR"}:
            d[args[0]] = str(int(d.get(args[0], "0")) + (1 if name == "INCR" else -1))
            return int(d[args[0]])
        if name == "EXPIRE":
            return 1
        if name == "HSET":
            h = d.setdefault(args[0], {})
            for field, value in zip(args[1::2], args[2::2]):
                h[field] = value
            return 1
        if name == "HGETALL":
            return [item for pair in d.get(args[0], {}).items() for item in pair]
        if name == "RPUSH":
            d.setdefault(args[0], []).extend(args[1:])
            return len(d[args[0]])
        if name == "LINDEX":
            items = d.get(args[0], [])
            return items[int(args[1])] if len(items) > int(args[1]) else None
        if name == "LREM":
            items = d.get(args[0], [])
            if args[2] in items:
                items.remove(args[2])
                return 1
            return 0
        if name == "LPOS":
            items = d.get(args[0], [])
            return items.index(args[1]) if args[1] in items else None
        if name == "ZADD":
            d.setdefault(args[0], {})[args[2]] = float(args[1])
            return 1
        if name == "ZRANGEBYSCORE":
            high = float(args[2])
            return sorted((m for m, s in d.get(args[0], {}).items() if s <= high), key=lambda m: d[args[0]][m])
        if name == "ZREM":
            return 1 if d.get(args[0], {}).pop(args[1], None) is not None else 0
        raise NotImplementedError(name)


class FakeBackend:
    def __init__(self, states=("done",), archive=b"zip"):
        self.states, self.archive, self.started, self.stopped = list(states), archive, [], []

    def start(self, settings, audit):
        self.started.append(audit["id"])
        return json.dumps({"job": audit["id"]})

    def poll(self, handle):
        return (self.states.pop(0) if len(self.states) > 1 else self.states[0]), "boom"

    def collect(self, handle):
        return self.archive

    def stop(self, handle):
        self.stopped.append(handle)


def make_archive(files=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("chaosfolk-example.org-2026-11-05/README.txt", "readme")
        for name, data in (files or {"rapport.html": "<p>report</p>"}).items():
            bundle.writestr(f"chaosfolk-example.org-2026-11-05/{name}", data)
    return buffer.getvalue()


@pytest.fixture(params=["sqlite", "redis"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SQLiteStore(tmp_path / "db.sqlite3")
    return RedisStore(FakeRedis())


@pytest.fixture
def settings(tmp_path):
    return replace(Settings(), mode="local", data_dir=tmp_path, daily_quota=3, per_ip_daily=1,
                   allowed_origins=("https://loukan42.github.io",), turnstile_secret="", public_url="https://api.test",
                   cron_secret="")


@pytest.fixture
def parts(settings, store):
    return store, LocalReports(settings.reports_dir), FakeBackend()


@pytest.fixture
def client(settings, parts, monkeypatch):
    # The engine re-checks DNS before starting; answer it from the fake table, like the form check.
    original = urls.check_public
    monkeypatch.setattr(urls, "check_public", lambda host, resolver=None: original(host, PUBLIC))
    return TestClient(create_app(settings, resolver=PUBLIC, parts=parts))


# URLs

@pytest.mark.parametrize("raw, expected", [
    ("example.org", "https://example.org/"),
    ("  HTTP://Example.org/path?a=1&b=2#frag ", "http://example.org/path?a=1&b=2"),
    ("https://example.org:443/", "https://example.org:443/"),
])
def test_normalize_accepts_public_addresses(raw, expected):
    assert urls.normalize(raw)[0] == expected


@pytest.mark.parametrize("raw", [
    "", "ftp://example.org", "javascript:alert(1)", "https://user:pw@example.org", "http://localhost:3000",
    "https://app.localhost", "https://printer.local", "https://intranet", "https://example.org:8080",
    "https://db.internal", "x" * 2001,
])
def test_normalize_refuses_unsafe_addresses(raw):
    with pytest.raises(urls.RejectedUrl):
        urls.normalize(raw)


@pytest.mark.parametrize("host", ["evil.example.net", "meta.example.net", "v6.example.net", "missing.example.org"])
def test_resolution_must_be_public(host):
    with pytest.raises(urls.RejectedUrl):
        urls.check_public(host, PUBLIC)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254",
                                     "100.64.0.1", "0.0.0.0", "::1", "fe80::1", "fc00::1", "224.0.0.1"])
def test_private_ranges_are_not_public(address):
    assert not urls.is_public(address)


# Ledgers (each test runs on SQLite and on Redis)

def test_quota_and_ip_limit_are_enforced(store):
    store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1)
    with pytest.raises(QuotaExceeded) as same_ip:
        store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1)
    assert same_ip.value.reason == "ip"
    store.create("https://example.org/", "example.org", "en", "2.2.2.2", quota=2, per_ip=1)
    with pytest.raises(QuotaExceeded) as daily:
        store.create("https://example.org/", "example.org", "en", "3.3.3.3", quota=2, per_ip=1)
    assert daily.value.reason == "daily"
    assert store.used_today() == 2
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1, moment=tomorrow)


def test_ip_is_not_stored(store):
    audit_id = store.create("https://example.org/", "example.org", "en", "203.0.113.9", quota=5, per_ip=1)
    assert "203.0.113.9" not in str(store.get(audit_id))
    if isinstance(store, RedisStore):
        assert "203.0.113.9" not in json.dumps(store.r.data)


def test_one_audit_runs_at_a_time(store):
    first = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    second = store.create("https://example.org/", "example.org", "en", "2.2.2.2", 5, 1)
    assert store.get(first)["position"] == 1 and store.get(second)["position"] == 2
    assert store.claim()["id"] == first
    assert store.claim() is None
    assert store.running()["id"] == first and store.get(second)["position"] == 2
    store.finish(first, "done")
    assert store.running() is None
    assert store.claim()["id"] == second


def test_expiry_and_locks(store):
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    store.finish(audit_id, "done", moment=datetime.now(timezone.utc) - timedelta(days=8))
    assert store.expire(7) == [audit_id]
    assert store.get(audit_id)["status"] == "expired"
    assert store.lock("tick", 60) and not store.lock("tick", 60)
    store.unlock("tick")
    assert store.lock("tick", 60)


# Engine

def test_tick_runs_an_audit_to_its_report(settings, monkeypatch):
    monkeypatch.setattr(urls, "check_public", lambda host: ["93.184.215.14"])
    store, reports, backend = SQLiteStore(settings.database), LocalReports(settings.reports_dir), FakeBackend(("running", "done"))
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    engine.tick(settings, store, reports, backend)
    assert store.get(audit_id)["status"] == "running" and backend.started == [audit_id]
    engine.tick(settings, store, reports, backend)
    assert store.get(audit_id)["status"] == "running"
    engine.tick(settings, store, reports, backend)
    assert store.get(audit_id)["status"] == "done" and reports.load(audit_id) == b"zip" and backend.stopped


def test_tick_fails_slow_and_broken_audits(settings, monkeypatch):
    monkeypatch.setattr(urls, "check_public", lambda host: ["93.184.215.14"])
    store, reports = SQLiteStore(settings.database), LocalReports(settings.reports_dir)
    slow = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    backend = FakeBackend(("running",))
    engine.tick(settings, store, reports, backend)
    late = datetime.now(timezone.utc) + timedelta(seconds=settings.audit_seconds + engine.COLLECT_MARGIN + 1)
    engine.tick(settings, store, reports, backend, moment=late)
    assert store.get(slow)["status"] == "failed" and "too long" in store.get(slow)["error"]
    broken = store.create("https://example.org/", "example.org", "en", "2.2.2.2", 5, 1)
    engine.tick(settings, store, reports, FakeBackend(("failed",)))
    engine.tick(settings, store, reports, FakeBackend(("failed",)))
    assert store.get(broken)["status"] == "failed" and store.get(broken)["error"] == "boom"


def test_tick_refuses_a_host_that_turned_private(settings, monkeypatch):
    def private(host):
        raise urls.RejectedUrl("Enter a public address, not a local one.")
    monkeypatch.setattr(urls, "check_public", private)
    store, backend = SQLiteStore(settings.database), FakeBackend()
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    engine.tick(settings, store, LocalReports(settings.reports_dir), backend)
    assert store.get(audit_id)["status"] == "failed" and not backend.started


def test_expired_reports_are_deleted(settings):
    store, reports = SQLiteStore(settings.database), LocalReports(settings.reports_dir)
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    reports.save(audit_id, b"zip")
    store.finish(audit_id, "done", moment=datetime.now(timezone.utc) - timedelta(days=8))
    engine.purge(settings, store, reports)
    assert store.get(audit_id)["status"] == "expired" and reports.load(audit_id) is None


# API

def test_api_runs_an_audit_and_serves_the_report(client):
    backend = client.app.state.backend
    backend.archive = make_archive({"rapport.html": "<p>report</p>", "assets/app.js": "js"})
    assert client.get("/api/quota").json()["remaining"] == 3
    response = client.post("/api/audits", json={"url": "example.org", "lang": "fr", "authorized": True},
                           headers={"Origin": "https://loukan42.github.io"})
    assert response.status_code == 201, response.text
    assert response.headers["access-control-allow-origin"] == "https://loukan42.github.io"
    body = response.json()
    assert body["url"] == "https://example.org/" and body["quota"]["remaining"] == 2 and "ip_hash" not in body
    assert body["status"] == "running"          # the POST already started it
    status = client.get(f"/api/audits/{body['id']}").json()
    assert status["status"] == "done"
    assert status["report_url"] == f"https://api.test/reports/{body['id']}/"
    page = client.get(f"/reports/{body['id']}/")
    assert page.status_code == 200 and "report" in page.text and page.headers["x-robots-tag"].startswith("noindex")
    assert page.headers["content-type"].startswith("text/html")
    assert client.get(f"/reports/{body['id']}/assets/app.js").text == "js"
    for bad in ("../README.txt", "..%2FREADME.txt", "assets/../../x", "missing.html"):
        assert client.get(f"/reports/{body['id']}/{bad}").status_code == 404
    zipped = client.get(status["download_url"].replace("https://api.test", ""))
    assert zipped.status_code == 200 and zipped.headers["content-type"] == "application/zip"
    assert "chaosfolk-example.org-" in zipped.headers["content-disposition"]


def test_api_refusals(client):
    assert client.post("/api/audits", json={"url": "example.org"}).status_code == 400
    refused = client.post("/api/audits", json={"url": "http://localhost:3000", "authorized": True})
    assert refused.status_code == 400 and "public" in refused.json()["detail"]
    assert client.post("/api/audits", json={"url": "evil.example.net", "authorized": True}).status_code == 400
    assert client.post("/api/audits", json={"url": "example.org", "authorized": True}).status_code == 201
    assert client.post("/api/audits", json={"url": "example.org", "authorized": True}).status_code == 429
    assert client.get("/api/audits/unknown").status_code == 404
    assert client.get("/api/audits/bad%20id").status_code == 404
    assert client.get("/reports/unknown").status_code == 404
    assert client.get("/api/quota").json()["remaining"] == 2


def test_report_is_hidden_until_done(client):
    client.app.state.backend.states = ["running"]
    body = client.post("/api/audits", json={"url": "example.org", "authorized": True}).json()
    assert client.get(f"/reports/{body['id']}/").status_code == 404
    assert client.get(f"/api/audits/{body['id']}/report.zip").status_code == 404


def test_cors_rejects_other_origins(client):
    response = client.get("/api/quota", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cron_needs_its_secret(settings, parts):
    app = create_app(replace(settings, cron_secret="s3cret"), resolver=PUBLIC, parts=parts)
    client = TestClient(app)
    assert client.get("/api/cron").status_code == 401
    assert client.get("/api/cron", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/cron", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_turnstile_is_required_when_configured(settings, parts):
    app = create_app(replace(settings, turnstile_secret="secret"), resolver=PUBLIC, parts=parts)
    assert TestClient(app).post("/api/audits", json={"url": "example.org", "authorized": True}).status_code == 403


def test_turnstile_verify_reads_cloudflare_answer():
    class Answer(io.BytesIO):
        def __enter__(self):
            return self
    assert turnstile.verify("s", "t", "1.1.1.1", opener=lambda *a, **k: Answer(b'{"success": true}'))
    assert not turnstile.verify("s", "t", "1.1.1.1", opener=lambda *a, **k: Answer(b'{"success": false}'))
    assert not turnstile.verify("s", "", "1.1.1.1")
    assert turnstile.verify("", "", "1.1.1.1")


def test_vercel_ip_header_is_used_only_on_vercel(settings, parts):
    headers = [{"X-Real-IP": "198.51.100.1"}, {"X-Real-IP": "198.51.100.2"}]
    vercel = TestClient(create_app(replace(settings, mode="vercel"), resolver=PUBLIC, parts=parts))
    assert [vercel.post("/api/audits", json={"url": "example.org", "authorized": True}, headers=h).status_code
            for h in headers] == [201, 201]


# Archive and report storage

def test_pack_publishes_only_the_report(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "assets").mkdir(parents=True)
    (run_dir / "scenarios").mkdir()
    (run_dir / "rapport.html").write_text("report")
    (run_dir / "assets" / "app.js").write_text("js")
    (run_dir / "scenarios" / "save.json").write_text("{}")
    (run_dir / "audit.sqlite3").write_text("private")
    (run_dir / "state.json").write_text("cookies")
    out = pack.build(run_dir, tmp_path / "r.zip", "chaosfolk-x", "https://example.org/")
    names = sorted(zipfile.ZipFile(out).namelist())
    assert names == ["chaosfolk-x/README.txt", "chaosfolk-x/assets/app.js", "chaosfolk-x/rapport.html",
                     "chaosfolk-x/scenarios/save.json"]
    with pytest.raises(pack.NoReport):
        pack.build(tmp_path / "empty", tmp_path / "e.zip", "x", "u")


def test_read_member_stays_in_the_archive(tmp_path):
    path = tmp_path / "r.zip"
    path.write_bytes(make_archive({"rapport.html": "ok", "a/b.txt": "b"}))
    assert read_member(path, "rapport.html") == b"ok" and read_member(path, "a/b.txt") == b"b"
    for bad in ("../x", "a/../../x", "a\\b.txt", "nope"):
        assert read_member(path, bad) is None


def test_blob_reports_cache_downloads(tmp_path):
    calls = []

    class Blob:
        def put_blob(self, name, data, **kwargs):
            calls.append(("put", name, kwargs["access"]))
            self.data = data

        def get_blob(self, name, access):
            calls.append(("get", name))
            return types.SimpleNamespace(body=self.data)

        def delete_blob(self, names):
            calls.append(("delete", tuple(names)))

    reports = BlobReports(blob=Blob(), cache_dir=tmp_path)
    reports.save("abc", b"zip")
    assert reports.load("abc") == b"zip" and reports.load("abc") == b"zip"
    assert calls == [("put", "reports/abc.zip", "private"), ("get", "reports/abc.zip")]
    reports.delete(["abc"])
    assert not (tmp_path / "abc.zip").exists()


# Sandbox backend (SDK replaced, policy objects from the real SDK)

def test_sandbox_backend_brokers_the_key_and_blocks_private_ranges(settings):
    from vercel.sandbox import sync as real
    created = {}

    class Box:
        name, status = "sbx-1", types.SimpleNamespace(value="running")

        def create_command(self, command, args, **kwargs):
            created.update(command=command, args=args, env=kwargs["env"])
            return types.SimpleNamespace(id="cmd-1")

    sdk = types.SimpleNamespace(**{n: getattr(real, n) for n in ("NetworkPolicy", "NetworkPolicyRule",
                                                                  "NetworkPolicyTransform", "NetworkPolicySubnets",
                                                                  "SnapshotSource", "SandboxResources")})
    sdk.create_sandbox = lambda **kwargs: created.update(kwargs) or Box()
    config = replace(settings, snapshot_id="snap_1", model="openrouter/x/y:free", openrouter_key="sk-secret")
    audit = {"id": "a1", "url": "https://example.org/?a=1&b=2", "lang": "fr", "host": "example.org",
             "created_at": "2026-11-05T10:00:00+00:00"}
    handle = json.loads(backends.SandboxBackend(sdk).start(config, audit))
    assert handle == {"sandbox": "sbx-1", "command": "cmd-1"}
    assert created["persistent"] is False and created["execution_time_limit"] <= 2700
    assert created["env"]["OPENROUTER_API_KEY"] != "sk-secret"
    assert "sk-secret" not in json.dumps(created["args"]) and created["args"][0] == audit["url"]
    policy = repr(created["network_policy"])
    assert "sk-secret" in policy and "openrouter.ai" in policy and "169.254.0.0/16" in policy
    with pytest.raises(backends.BackendError):
        backends.SandboxBackend(sdk).start(replace(config, snapshot_id=""), audit)


def test_sandbox_poll_never_resumes_a_stopped_box():
    class Box:
        status = types.SimpleNamespace(value="stopped")

        def get_command(self, *_):
            raise AssertionError("would resume the sandbox")

    sdk = types.SimpleNamespace(get_sandbox=lambda name: Box())
    state, error = backends.SandboxBackend(sdk).poll(json.dumps({"sandbox": "s", "command": "c"}))
    assert state == "failed" and error


def test_sandbox_files_are_consistent():
    """The snapshot and the backend agree on paths, and the prompt template keys are all filled."""
    from pathlib import Path
    folder = Path(backends.__file__).resolve().parent.parent / "sandbox"
    script = (folder / "run-audit.sh").read_text()
    assert backends.SANDBOX_ROOT in script and "report.zip" in script
    prompt = (folder / "prompt.md").read_text()
    keys = {k for k in ("URL", "LANG", "USERS", "PROJECT", "RUN") if "{" + k + "}" in prompt}
    assert keys == {"URL", "LANG", "USERS", "PROJECT", "RUN"}
    config = json.loads((folder / "opencode.json").read_text())
    assert config["permission"]["webfetch"] == "deny" and config["permission"]["bash"]["*"] == "deny"
    assert fnmatch.fnmatch("chaosfolk report --folder x", next(p for p in config["permission"]["bash"] if p.startswith("chaosfolk")))


@pytest.mark.browser
def test_demo_backend_produces_a_report(settings, monkeypatch):
    """Runs the real offline demo in Chromium: the whole queue without a model."""
    import time
    monkeypatch.setattr(urls, "check_public", lambda host: ["93.184.215.14"])
    store, reports, backend = SQLiteStore(settings.database), LocalReports(settings.reports_dir), backends.DemoBackend()
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    deadline = time.monotonic() + 300
    while store.get(audit_id)["status"] not in {"done", "failed"} and time.monotonic() < deadline:
        engine.tick(settings, store, reports, backend)
        time.sleep(1)
    assert store.get(audit_id)["status"] == "done", store.get(audit_id)["error"]
    names = zipfile.ZipFile(reports.local_path(audit_id)).namelist()
    assert any(n.endswith("/rapport.html") for n in names) and any("/scenarios/" in n for n in names)
