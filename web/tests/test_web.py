from dataclasses import replace
from datetime import datetime, timedelta, timezone
import socket

import pytest
from fastapi.testclient import TestClient

from chaosfolk_web import runner, turnstile, urls, worker
from chaosfolk_web.app import create_app
from chaosfolk_web.config import Settings
from chaosfolk_web.store import QuotaExceeded, Store


def fake_resolver(table):
    def resolve(host, port, proto=0):
        if host not in table:
            raise socket.gaierror("not found")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0)) for address in table[host]]
    return resolve


PUBLIC = fake_resolver({"example.org": ["93.184.215.14"], "evil.example.net": ["93.184.215.14", "10.0.0.5"],
                        "meta.example.net": ["169.254.169.254"], "v6.example.net": ["::ffff:127.0.0.1"]})


@pytest.fixture
def settings(tmp_path):
    return replace(Settings(), data_dir=tmp_path, daily_quota=3, per_ip_daily=1, runner="demo",
                   allowed_origins=("https://loukan42.github.io",), turnstile_secret="", public_url="https://api.test")


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings, resolver=PUBLIC))


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


def test_quota_and_ip_limit_are_enforced(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1)
    with pytest.raises(QuotaExceeded) as same_ip:
        store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1)
    assert same_ip.value.reason == "ip"
    store.create("https://example.org/", "example.org", "en", "2.2.2.2", quota=2, per_ip=1)
    with pytest.raises(QuotaExceeded) as daily:
        store.create("https://example.org/", "example.org", "en", "3.3.3.3", quota=2, per_ip=1)
    assert daily.value.reason == "daily"
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    store.create("https://example.org/", "example.org", "en", "1.1.1.1", quota=2, per_ip=1, moment=tomorrow)


def test_ip_is_stored_hashed(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    audit_id = store.create("https://example.org/", "example.org", "en", "203.0.113.9", quota=5, per_ip=1)
    assert "203.0.113.9" not in str(store.get(audit_id))


def test_queue_position_and_claim_order(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    first = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    second = store.create("https://example.org/", "example.org", "en", "2.2.2.2", 5, 1)
    assert store.get(first)["position"] == 1 and store.get(second)["position"] == 2
    assert store.claim()["id"] == first
    assert store.get(second)["position"] == 2
    store.recover()
    assert store.get(first)["status"] == "failed"


def test_api_creates_and_reports_an_audit(client):
    assert client.get("/api/quota").json()["remaining"] == 3
    response = client.post("/api/audits", json={"url": "example.org", "lang": "fr", "authorized": True},
                           headers={"Origin": "https://loukan42.github.io"})
    assert response.status_code == 201, response.text
    assert response.headers["access-control-allow-origin"] == "https://loukan42.github.io"
    body = response.json()
    assert body["status"] == "queued" and body["url"] == "https://example.org/" and body["quota"]["remaining"] == 2
    assert "ip_hash" not in body
    status = client.get(f"/api/audits/{body['id']}").json()
    assert status["position"] == 1 and status["report_url"] is None
    assert client.get(f"/reports/{body['id']}/").status_code == 404


def test_api_refusals(client):
    assert client.post("/api/audits", json={"url": "example.org"}).status_code == 400
    refused = client.post("/api/audits", json={"url": "http://localhost:3000", "authorized": True})
    assert refused.status_code == 400 and "public" in refused.json()["detail"]
    assert client.post("/api/audits", json={"url": "evil.example.net", "authorized": True}).status_code == 400
    assert client.post("/api/audits", json={"url": "example.org", "authorized": True}).status_code == 201
    again = client.post("/api/audits", json={"url": "example.org", "authorized": True})
    assert again.status_code == 429
    assert client.get("/api/audits/unknown").status_code == 404
    assert client.get("/api/quota").json()["remaining"] == 2


def test_cors_rejects_other_origins(client):
    response = client.get("/api/quota", headers={"Origin": "https://attacker.example"})
    assert "access-control-allow-origin" not in response.headers


def test_turnstile_is_required_when_configured(settings):
    app = create_app(replace(settings, turnstile_secret="secret"), resolver=PUBLIC)
    response = TestClient(app).post("/api/audits", json={"url": "example.org", "authorized": True})
    assert response.status_code == 403


def test_turnstile_verify_reads_cloudflare_answer():
    class Answer:
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self, *_):
            return self.body
    assert turnstile.verify("s", "t", "1.1.1.1", opener=lambda *a, **k: Answer(b'{"success": true}'))
    assert not turnstile.verify("s", "t", "1.1.1.1", opener=lambda *a, **k: Answer(b'{"success": false}'))
    assert not turnstile.verify("s", "", "1.1.1.1")
    assert turnstile.verify("", "", "1.1.1.1")


def test_trusted_proxy_header(settings):
    app = create_app(replace(settings, trust_proxy=True), resolver=PUBLIC)
    client = TestClient(app)
    ok = client.post("/api/audits", json={"url": "example.org", "authorized": True}, headers={"X-Real-IP": "198.51.100.1"})
    other = client.post("/api/audits", json={"url": "example.org", "authorized": True}, headers={"X-Real-IP": "198.51.100.2"})
    assert ok.status_code == other.status_code == 201


def test_publish_copies_only_the_report(tmp_path):
    run_dir, public = tmp_path / "run", tmp_path / "public"
    (run_dir / "assets").mkdir(parents=True)
    (run_dir / "rapport.html").write_text("report")
    (run_dir / "assets" / "app.js").write_text("js")
    (run_dir / "audit.sqlite3").write_text("private")
    (run_dir / "state.json").write_text("cookies")
    runner.publish(run_dir, public)
    assert sorted(p.relative_to(public).as_posix() for p in public.rglob("*") if p.is_file()) == ["assets/app.js", "rapport.html"]
    with pytest.raises(runner.RunFailed):
        runner.publish(tmp_path / "empty", tmp_path / "out")


def test_report_route_blocks_traversal(client, settings):
    store = client.app.state.store
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    store.finish(audit_id, "done")
    public = settings.job_dir(audit_id) / "public"
    public.mkdir(parents=True)
    (public / "rapport.html").write_text("<p>report</p>")
    (settings.job_dir(audit_id) / "agent.log").write_text("secret")
    page = client.get(f"/reports/{audit_id}/")
    assert page.status_code == 200 and "report" in page.text and page.headers["x-robots-tag"].startswith("noindex")
    assert client.get(f"/reports/{audit_id}/..%2Fagent.log").status_code == 404
    assert client.get(f"/reports/{audit_id}/../agent.log").status_code == 404
    assert client.get(f"/api/audits/{audit_id}").json()["report_url"] == f"https://api.test/reports/{audit_id}/"
    assert client.get(f"/api/audits/{audit_id}/report.zip").status_code == 404


def test_archive_is_downloadable(client, settings):
    import io
    import zipfile
    store = client.app.state.store
    audit_id = store.create("https://example.org/a?b=1", "example.org", "en", "1.1.1.1", 5, 1)
    public = settings.job_dir(audit_id) / "public"
    (public / "scenarios").mkdir(parents=True)
    (public / "rapport.html").write_text("<p>report</p>")
    (public / "scenarios" / "save.json").write_text("{}")
    audit = store.get(audit_id)
    runner.archive(public, settings.job_dir(audit_id) / "report.zip", runner.archive_name(audit), audit["url"])
    assert client.get(f"/api/audits/{audit_id}/report.zip").status_code == 404
    store.finish(audit_id, "done")
    body = client.get(f"/api/audits/{audit_id}").json()
    assert body["download_url"] == f"https://api.test/api/audits/{audit_id}/report.zip"
    response = client.get(f"/api/audits/{audit_id}/report.zip")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    folder = runner.archive_name(audit)
    assert folder.startswith("chaosfolk-example.org-") and folder in response.headers["content-disposition"]
    names = sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist())
    assert names == [f"{folder}/README.txt", f"{folder}/rapport.html", f"{folder}/scenarios/save.json"]


def test_worker_marks_a_failed_run(settings, monkeypatch):
    store = Store(settings.database)
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    monkeypatch.setattr(urls, "check_public", lambda host: ["93.184.215.14"])
    def boom(*_):
        raise runner.RunFailed("The audit ended without a report.")
    monkeypatch.setattr(runner, "run", boom)
    worker.loop(settings, once=True)
    audit = store.get(audit_id)
    assert audit["status"] == "failed" and audit["error"] == "The audit ended without a report."


def test_expired_reports_are_deleted(settings):
    store = Store(settings.database)
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    store.finish(audit_id, "done", moment=datetime.now(timezone.utc) - timedelta(days=8))
    settings.job_dir(audit_id).mkdir(parents=True)
    worker.purge(settings, store)
    assert store.get(audit_id)["status"] == "expired" and not settings.job_dir(audit_id).exists()


@pytest.mark.browser
def test_demo_runner_produces_a_public_report(settings, monkeypatch):
    """Runs the real offline demo in Chromium: the whole queue without a model."""
    store = Store(settings.database)
    audit_id = store.create("https://example.org/", "example.org", "en", "1.1.1.1", 5, 1)
    monkeypatch.setattr(urls, "check_public", lambda host: ["93.184.215.14"])
    worker.loop(settings, once=True)
    assert store.get(audit_id)["status"] == "done", store.get(audit_id)["error"]
    assert (settings.job_dir(audit_id) / "public" / "rapport.html").is_file()
    assert (settings.job_dir(audit_id) / "public" / "scenarios").is_dir()
    assert (settings.job_dir(audit_id) / "report.zip").is_file()
