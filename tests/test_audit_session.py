from concurrent.futures import ThreadPoolExecutor
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from chaosfolk import checks
from chaosfolk.audit_session import Session, catalog, CAPABILITIES
from chaosfolk.audit_dashboard import make_server


def inventory(folder, pages=1):
    source = checks.load()
    value = {"pages": [{"url": f"http://localhost:3000/page-{i}",
              "kinds": [k["id"] for k in source["kinds"]] + ["text"],
              "features": list(source["features"])} for i in range(pages)]}
    (folder / "fields.json").write_text(json.dumps(value), encoding="utf-8")
    return value


def setup_run(tmp_path, depth="deep", pages=1):
    session = Session(tmp_path)
    session.create(depth)
    inventory(tmp_path, pages)
    session.configure(capabilities=sorted(CAPABILITIES))
    session.refresh(True)
    session.start()
    return session


def test_depths_exclusions_persist_and_catalog_covers_entire_checklist(tmp_path):
    assert len(catalog()) == 178
    assert {x["id"] for x in checks.load()["checks"]} <= catalog().keys()
    session = Session(tmp_path)
    session.create("quick")
    for depth, count in [("quick", 27), ("standard", 57), ("deep", 69)]:
        result = session.configure(depth=depth)
        assert sum(e["selected"] for e in result["entries"] if e["kind"] == "qa-check") == count
    session.configure(excluded=["email-formats"])
    session.configure(depth="quick")
    restored = Session(tmp_path).configure(depth="deep")
    assert not next(e for e in restored["entries"] if e["id"] == "email-formats")["selected"]
    assert restored["config"]["excluded"] == ["email-formats"]
    with pytest.raises(FileExistsError):
        session.create()
    control = next(e for e in catalog().values() if not e["configurable"])
    with pytest.raises(ValueError):
        session.configure(excluded=[control["id"]])


def test_unknown_inventory_is_not_coverage_and_missing_prerequisites_block(tmp_path):
    session = Session(tmp_path)
    initial = session.create("deep")
    assert initial["counts"]["needs-discovery"] > 69
    assert initial["tested"] == 0 and initial["completion"] == "partial"
    with pytest.raises(ValueError):
        session.refresh(True)
    (tmp_path / "fields.json").write_text(json.dumps({"pages": [{"url": "http://localhost/", "kinds": [], "features": []}]}))
    session.refresh()
    assert session.snapshot()["counts"]["needs-discovery"]
    session.refresh(True)
    assert session.snapshot()["counts"]["not-applicable"]
    assert session.snapshot()["counts"]["blocked"]


def test_queue_drains_all_checks_across_waves_without_duplicates(tmp_path):
    session = setup_run(tmp_path, pages=3)
    observed = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        batches = list(pool.map(lambda i: session.claim(f"worker{i}", "agent", 6), range(4)))
    observed += [t["task_id"] for b in batches for t in b["tasks"]]
    assert len(observed) == len(set(observed))
    for executor in ("agent", "audit", "fields", "coordinator"):
        while tasks := session.claim("later", executor, 25)["tasks"]:
            observed += [t["task_id"] for t in tasks]
    detail = session.snapshot(details=True)
    assert set(observed) == {t["id"] for t in detail["tasks"] if t["eligibility"] == "eligible"}
    assert {t["check_id"] for t in detail["tasks"] if t["id"] in observed} >= {c["id"] for c in checks.load()["checks"]}
    assert detail["tested"] == 0
    session.release("worker0")
    assert session.claim("replacement", "agent", 6)["tasks"]


def test_results_require_evidence_claim_and_measurements_are_reviewed(tmp_path):
    session = setup_run(tmp_path)
    task = session.claim("h01", "agent", 1)["tasks"][0]
    with pytest.raises(ValueError, match="evidence"):
        session.record(task["task_id"], "passed", "It works")
    with pytest.raises(ValueError, match="inside"):
        session.record(task["task_id"], "passed", "It works", ["../outside.json"])
    (tmp_path / "evidence.json").write_text('{"observed":"saved after reload"}')
    with pytest.raises(ValueError, match="claim"):
        session.record(task["task_id"], "passed", "Saved", ["evidence.json"], "h01", "stale")
    session.record(task["task_id"], "passed", "Saved after reload", ["evidence.json"], "h01", task["claim"])
    assert session.snapshot()["tested"] == 1
    session.measure("fields", "http://localhost:3000/page-0", ["evidence.json"])
    measured = session.snapshot()["counts"]["measured"]
    assert measured > 0 and session.snapshot()["tested"] == 1
    reviewed = session.claim("review", "coordinator", 25)["tasks"]
    assert any(t["measurement"] for t in reviewed)


def test_exclusions_gate_active_tasks_and_context_requires_evidence(tmp_path):
    session = setup_run(tmp_path)
    task = session.claim("h01", "agent", 1)["tasks"][0]
    assert session.task_allowed(task["task_id"])
    session.configure(excluded=[task["check_id"]])
    assert not session.task_allowed(task["task_id"])
    with pytest.raises(ValueError):
        session.configure(applicability={task["check_id"]: {"state":"not-applicable", "reason":"No such feature"}})
    (tmp_path / "context.json").write_text('{"source":"routes and product owner","feature":"absent"}')
    session.configure(applicability={task["check_id"]: {"state":"not-applicable", "reason":"Feature absent in source and routes", "evidence":["context.json"]}})
    session.configure(excluded=[])
    entry = next(e for e in session.snapshot()["entries"] if e["id"] == task["check_id"])
    assert entry["states"] == {"not-applicable":1}


def test_limits_stop_new_work_without_changing_results(tmp_path, monkeypatch):
    session = setup_run(tmp_path)
    session.configure(limits={"max_actions":2})
    assert session.gate(consume=True) is None
    assert session.gate(consume=True) is None
    assert "Action limit" in session.gate(consume=True)
    assert not session.claim("h01")["tasks"]
    assert session.snapshot()["config"]["actions"] == 2
    session.configure(limits={"max_actions":None,"max_tokens":10})
    assert not session.start()["ok"]
    event = {"id":"request-1","source":"host","input_tokens":2,"output_tokens":3,"cost":.01,"currency":"EUR"}
    session.usage([event], complete=True)
    session.usage([event], complete=True)
    assert session.start()["ok"]
    assert session.snapshot()["config"]["usage"]["tokens"] == 5
    with pytest.raises(ValueError, match="duplicate"):
        session.usage([dict(event, input_tokens=3)])
    with pytest.raises(ValueError, match="currenc"):
        session.usage([dict(event,id="request-2",currency="USD")])
    session.usage([dict(event,id="request-2")], complete=True)
    assert session.snapshot()["config"]["state"] == "stopped"
    session.configure(limits={"max_tokens":None,"max_seconds":1})
    session.start()
    import time
    now = time.time()
    monkeypatch.setattr("chaosfolk.audit_session.time.time", lambda: now + 2)
    assert "Time limit" in session.gate()
    assert session.snapshot()["tested"] == 0


def test_summary_poll_does_not_read_task_evidence_when_unchanged(tmp_path, monkeypatch):
    session = setup_run(tmp_path, pages=20)
    revision = session.snapshot()["config"]["revision"]
    monkeypatch.setattr("chaosfolk.audit_session.catalog", lambda: (_ for _ in ()).throw(AssertionError("catalog should not be read")))
    assert session.snapshot(after=revision) is None


def test_catalog_reference_default_budgets_and_context_promotions(tmp_path):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    assert json.loads((root / "docs/audit-priorities.json").read_text(encoding="utf-8")) == json.loads(
        (root / "src/chaosfolk/audit_catalog.json").read_text(encoding="utf-8"))
    session = Session(tmp_path)
    session.create("quick")
    assert session.configure(depth="deep")["config"]["limits"]["max_actions"] == 600
    session.configure(limits={"max_actions":42})
    assert session.configure(depth="quick")["config"]["limits"]["max_actions"] == 42
    promoted = session.configure(promotions={"iban-checksum":"P1"})
    assert next(e for e in promoted["entries"] if e["id"] == "iban-checksum")["selected"]
    with pytest.raises(ValueError):
        session.configure(promotions={"email-formats":"P3"})


def test_fault_selection_changes_and_final_report_retains_untested_work(tmp_path):
    from chaosfolk import engine
    from test_core import embedded_report_data
    session = setup_run(tmp_path)
    assert session.fault_allowed("offline")
    offline = next(e for e in catalog().values() if e["fault"] == "offline")
    session.configure(excluded=[offline["id"]])
    assert not session.fault_allowed("offline")
    (tmp_path / "journal.jsonl").write_text("")
    engine.rapport(tmp_path, "fr")
    data = embedded_report_data(tmp_path / "rapport.html")
    assert data["audit_session"]["config"]["excluded"] == [offline["id"]]
    assert data["audit_session"]["completion"] == "partial"
    coverage = json.loads((tmp_path / "audit-coverage.json").read_text(encoding="utf-8"))
    assert coverage["tasks"] and coverage["tested"] == 0


def test_host_usage_staleness_and_empty_import_never_fake_zero(tmp_path, monkeypatch):
    import time
    session = setup_run(tmp_path)
    assert session.usage([], complete=True)["config"]["usage"]["tokens"] is None
    session.usage([{"id":"real-1","source":"host","input_tokens":12,"output_tokens":7}], complete=True)
    session.configure(limits={"max_tokens":100})
    now = time.time()
    monkeypatch.setattr("chaosfolk.audit_session.time.time", lambda: now + 31)
    assert "stale" in session.gate()


def test_cli_summaries_and_outstanding_pages_bound_model_context(tmp_path, capsys):
    from chaosfolk.audit_session import main
    main(["init", "--folder", str(tmp_path), "--depth", "deep"])
    output = capsys.readouterr().out
    value = json.loads(output)
    assert "entries" not in value and len(output) < 2000
    assert value["selected_tests"] == 116 and value["tested"] == 0
    session = Session(tmp_path)
    first = session.outstanding(limit=3)
    second = session.outstanding(limit=3, offset=first["next_offset"])
    assert len(first["tasks"]) == len(second["tasks"]) == 3
    assert not {t["id"] for t in first["tasks"]} & {t["id"] for t in second["tasks"]}
    assert all("result" not in task for task in first["tasks"])


def test_session_creation_closes_database_handles(tmp_path, monkeypatch):
    import sqlite3
    connections = []
    connect = sqlite3.connect

    def track(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr("chaosfolk.audit_session.sqlite3.connect", track)
    Session(tmp_path).create()
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


@pytest.fixture
def dashboard(tmp_path):
    session = setup_run(tmp_path)
    server = make_server(session, token="test-token")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield session, f"http://127.0.0.1:{server.server_port}", server.audit_token
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_dashboard_changes_real_session_and_requires_local_authorized_requests(dashboard):
    session, base, token = dashboard
    def request(path, data=None, **headers):
        return urlopen(Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                       headers={"Authorization":"Bearer " + token, "Content-Type":"application/json", **headers}), timeout=5)
    with request("/api/state") as response:
        value = json.load(response)
    with request("/api/state?after=" + str(value["config"]["revision"])) as response:
        assert response.status == 204 and not response.read()
    with request("/api/selection", {"excluded":["email-formats"]}) as response:
        assert json.load(response)["config"]["excluded"] == ["email-formats"]
    with request("/api/state?after=" + str(value["config"]["revision"])) as response:
        update = json.load(response)
        assert update["entries_mode"] == "patch"
        assert all("title" not in entry for entry in update["entries"])
        assert next(e for e in update["entries"] if e["id"] == "email-formats")["excluded"]
    assert Session(session.folder).snapshot()["config"]["excluded"] == ["email-formats"]
    with request("/api/stop", {}) as response:
        assert json.load(response)["config"]["state"] == "stopped"
    assert session.gate() and not session.claim("h01")["tasks"]
    for headers in ({"Authorization":"Bearer bad"}, {"Origin":"https://example.com"}, {"Host":"evil.test"}):
        with pytest.raises(HTTPError) as error:
            request("/api/start", {}, **headers)
        assert error.value.code == 403
    with request("/") as response:
        assert "script-src 'self'" in response.headers["Content-Security-Policy"]
        assert b"audit-live.js" in response.read()
