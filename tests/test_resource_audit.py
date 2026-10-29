"""Campaign and scheduler regressions from the resource audit."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from chaosfolk import campaigns, chaos_jobs, usage


def test_rebase_keeps_the_original_scenario_available_for_another_target():
    original = {"url": "http://localhost:3000/a", "steps": [
        {"action": "goto", "args": {"url": "http://localhost:3000/b"}},
        {"action": "goto", "args": {"url": "https://external.example/c"}},
    ]}
    snapshot = deepcopy(original)
    first = campaigns.rebase(original, "http://localhost:4000")
    second = campaigns.rebase(original, "http://localhost:5000")
    assert original == snapshot
    assert first["steps"][0]["args"]["url"] == "http://localhost:4000/b"
    assert second["steps"][0]["args"]["url"] == "http://localhost:5000/b"
    assert second["steps"][1]["args"]["url"] == "https://external.example/c"


def test_campaign_record_reads_the_journal_once_and_contains_fingerprint_paths(tmp_path, monkeypatch):
    root, folder = tmp_path / "project", tmp_path / "session"
    root.mkdir()
    folder.mkdir()
    scenario = folder / "scenario.json"
    scenario.write_text(json.dumps({"expect": [{"type": "text-visible", "text": "Saved"}]}))
    (folder / "proof.json").write_text(json.dumps({"scenario": str(scenario)}))
    finding = {"fingerprint": "../../escaped", "titre": "Save failed", "preuves": {"before": "proof.json"}}
    (folder / "constats.json").write_text(json.dumps({"constats": [finding]}))
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    monkeypatch.setattr(campaigns, "git_revision", lambda folder: None)
    calls = []

    def events(folder):
        calls.append(folder)
        return [{"type": "action", "h": "h01", "n": 1, "url": "http://localhost/orders/42"}]

    monkeypatch.setattr(campaigns, "session_events", events)
    assert campaigns.command_record(SimpleNamespace(dossier=folder, project="shop", label="run", repo=None)) == 0
    assert len(calls) == 1
    registry = campaigns.read(root / "findings.json", {})
    kept = Path(registry["../../escaped"]["scenario"])
    assert kept.parent == root / "scenarios"
    assert kept.is_file()
    assert registry["../../escaped"]["assertions"] == 1
    assert not (tmp_path / "escaped.json").exists()


def test_fingerprints_share_an_index_without_changing_identity():
    events = [
        {"type": "action", "h": "h01", "n": 1, "url": "http://localhost/orders/42"},
        {"type": "action", "h": "h02", "n": 1, "url": "http://localhost/settings"},
    ]
    indexed = campaigns.action_index(events)
    findings = [
        {"titre": "[double-submit] Duplicate order", "evenements": [{"h": "h01", "n": 1}]},
        {"titre": "Missing label", "evenements": [{"h": "h02", "n": 1}]},
        {"titre": "Unknown location"}, {"fingerprint": "explicit"},
    ]
    assert [campaigns.fingerprint(f, events) for f in findings] == [
        campaigns.fingerprint(f, actions=indexed) for f in findings]


def test_usage_streams_jsonl_and_keeps_unknown_measurements(tmp_path, monkeypatch, capsys):
    path = tmp_path / "usage.jsonl"
    event = {"id": "a", "source": "host", "input_tokens": 4, "output_tokens": None, "cost": None}
    path.write_text("\ufeff" + json.dumps(event) + "\n\n" + json.dumps(event) + "\n", encoding="utf-8")

    def no_whole_file_read(*args, **kwargs):
        pytest.fail("Usage JSONL must be processed one line at a time")

    monkeypatch.setattr(Path, "read_text", no_whole_file_read)
    assert usage.main(["--input", str(path), "--max-tokens", "100"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["events"] == 1 and result["known_tokens"] == 4
    assert result["tokens"] is None and result["gate"] == "unknown"


@pytest.mark.parametrize("limit", [True, "1", float("nan")])
def test_usage_rejects_non_numeric_cost_limits(limit):
    with pytest.raises(ValueError, match="max-cost"):
        usage.summarize([], max_cost=limit)


def test_usage_rejects_overflow_in_total_cost():
    events = [{"id": str(i), "source": "host", "cost": 1e308, "currency": "USD"} for i in range(2)]
    with pytest.raises(ValueError, match="Total cost"):
        usage.summarize(events)


@pytest.mark.parametrize("costs", [[10 ** 400], [10 ** 308, 10 ** 308], [10 ** 308, 1e308]])
def test_usage_normalizes_large_integer_cost_failures(costs):
    events = [{"id": str(i), "source": "host", "cost": cost, "currency": "USD"} for i, cost in enumerate(costs)]
    with pytest.raises(ValueError, match="finite"):
        usage.summarize(events)


def test_usage_normalizes_oversized_integer_budget():
    with pytest.raises(ValueError, match="max-cost"):
        usage.summarize([], max_cost=10 ** 400)


def register_jobs(tmp_path, monkeypatch, names):
    monkeypatch.setattr(campaigns, "home", lambda: tmp_path)
    with chaos_jobs.store() as db:
        for name in names:
            job = {"id": name + "-id", "name": name, "max_runs": 1, "enabled": True,
                   "window": None, "interval": 60, "timeout": 10}
            db.execute("INSERT INTO jobs VALUES (?,?,0,0,0,NULL)", (name, json.dumps(job)))


def test_scheduler_renews_the_clock_between_slow_jobs(tmp_path, monkeypatch):
    register_jobs(tmp_path, monkeypatch, ["a", "b"])
    times = iter([100, 300])
    monkeypatch.setattr(chaos_jobs.time, "time", lambda: next(times))
    leases = []

    async def execute(job, run):
        with chaos_jobs.store() as db:
            leases.append(db.execute("SELECT running_until FROM jobs WHERE name=?", (job["name"],)).fetchone()[0])
        return 0

    monkeypatch.setattr(chaos_jobs, "run_job", execute)
    assert len(chaos_jobs.run_due(limit=2)) == 2
    assert leases == [140, 340]


@pytest.mark.parametrize("replace", [False, True])
def test_completed_job_cannot_release_a_successor_lease(tmp_path, monkeypatch, replace):
    register_jobs(tmp_path, monkeypatch, ["a"])

    async def execute(job, run):
        successor = dict(job, id="replacement") if replace else job
        with chaos_jobs.store() as db:
            db.execute("UPDATE jobs SET config=?,runs=?,running_until=500,last_code=7 WHERE name='a'",
                       (json.dumps(successor), run if replace else run + 1))
        return 0

    monkeypatch.setattr(chaos_jobs, "run_job", execute)
    chaos_jobs.run_due(now=100)
    with chaos_jobs.store() as db:
        assert db.execute("SELECT running_until,last_code FROM jobs WHERE name='a'").fetchone() == (500, 7)


@pytest.mark.parametrize("limit", [0, 11, True, 1.5])
def test_scheduler_bounds_direct_api_calls(limit):
    with pytest.raises(ValueError, match="limit"):
        chaos_jobs.run_due(limit=limit)


def map_part(visits=2, failures=1):
    return {"routes": {"/orders": {"visits": visits, "failures": failures, "users": ["h01"]}},
            "edges": {"/ -> /orders": {"from": "/", "to": "/orders", "count": visits, "via": ["Orders"]}},
            "discovered": ["/settings"]}


def test_map_updates_replace_session_counts_without_double_counting():
    total = {"routes": {}, "edges": {}, "discovered": []}
    campaigns.merge_map(total, map_part(), "a")
    first = deepcopy(total)
    campaigns.merge_map(total, map_part(), "a")
    assert total == first
    campaigns.merge_map(total, map_part(3, 0), "b")
    campaigns.merge_map(total, map_part(), "a")
    assert total["routes"]["/orders"] == {"visits": 5, "failures": 1, "campaigns": 2, "last_campaign": "b"}
    campaigns.merge_map(total, map_part(4, 2), "a")
    assert total["routes"]["/orders"] == {"visits": 7, "failures": 2, "campaigns": 2, "last_campaign": "a"}
    assert total["edges"]["/ -> /orders"]["count"] == 7
    campaigns.merge_map(total, {"routes": {}, "edges": {}, "discovered": []}, "a")
    assert total["routes"]["/orders"] == {"visits": 3, "failures": 0, "campaigns": 1, "last_campaign": "b"}
    assert total["edges"]["/ -> /orders"]["count"] == 3


def test_legacy_map_totals_survive_tracking_new_contributions():
    total = {"routes": {"/orders": {"visits": 9, "failures": 2, "campaigns": 3, "last_campaign": "old"}},
             "edges": {}, "discovered": []}
    campaigns.merge_map(total, map_part(), "new")
    campaigns.merge_map(total, map_part(), "new")
    assert total["routes"]["/orders"]["visits"] == 11
    assert total["routes"]["/orders"]["campaigns"] == 4


def test_map_update_survives_an_aggregate_missing_a_recorded_route_or_edge():
    total = {"routes": {}, "edges": {}, "discovered": [],
             "_campaigns": {"a": {"routes": {"/orders": [2, 1], "/gone": [4, 0]},
                            "edges": {"/ -> /orders": 2, "/ -> /gone": 4}}}}
    total["routes"]["/orders"] = {"visits": 2, "failures": 1, "campaigns": 1, "last_campaign": "a"}
    total["edges"]["/ -> /orders"] = {"from": "/", "to": "/orders", "count": 2, "via": ["Orders"]}
    campaigns.merge_map(total, map_part(3, 0), "a")
    assert total["routes"]["/orders"] == {"visits": 3, "failures": 0, "campaigns": 1, "last_campaign": "a"}
    assert total["edges"]["/ -> /orders"]["count"] == 3
    assert "/gone" not in total["routes"] and "/ -> /gone" not in total["edges"]
    assert total["_campaigns"] == {"a": {"routes": {"/orders": [3, 0]}, "edges": {"/ -> /orders": 3}}}


def test_project_lock_reports_unusable_lock_files_as_errors(tmp_path, monkeypatch):
    missing = tmp_path / "absent" / "project"
    with pytest.raises(ValueError, match="not writable"):
        with campaigns.project_lock(missing):
            pass
    root = tmp_path / "project"
    root.mkdir()
    (root / ".campaign-lock.sqlite3").write_bytes(b"not a database" * 100)
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    with pytest.raises(ValueError, match="unreadable"):
        campaigns.command_status(SimpleNamespace(project="shop"))
    assert campaigns.main(["status", "--project", "shop"]) == 1


def test_map_recency_tracks_updates_after_another_session_is_removed():
    total = {"routes": {}, "edges": {}, "discovered": []}
    for campaign, visits in [("a", 1), ("b", 2), ("a", 3), ("c", 4)]:
        campaigns.merge_map(total, map_part(visits, 0), campaign)
    campaigns.merge_map(total, {"routes": {}, "edges": {}, "discovered": []}, "c")
    assert total["routes"]["/orders"]["last_campaign"] == "a"


def test_map_then_record_counts_the_session_once(tmp_path, monkeypatch):
    root, folder = tmp_path / "project", tmp_path / "session"
    root.mkdir()
    folder.mkdir()
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    monkeypatch.setattr(campaigns, "git_revision", lambda folder: None)
    monkeypatch.setattr(campaigns, "session_events", lambda folder: [
        {"type": "action", "h": "h01", "n": 1, "url": "http://localhost/orders"}])
    opts = SimpleNamespace(dossier=folder, project="shop", label="first", repo=None)
    campaigns.command_map(opts)
    campaigns.command_record(opts)
    stored = campaigns.read(root / "map.json", {})
    assert stored["routes"]["/orders"]["visits"] == 1
    assert stored["routes"]["/orders"]["campaigns"] == 1


def test_atomic_write_preserves_previous_json_on_serialization_error(tmp_path):
    target = tmp_path / "map.json"
    campaigns.write(target, {"complete": True})
    with pytest.raises(TypeError):
        campaigns.write(target, {"partial": "must not replace previous data", "invalid": object()})
    assert campaigns.read(target, {}) == {"complete": True}
    assert list(tmp_path.iterdir()) == [target]


def test_record_recovers_the_entire_batch_after_an_interrupted_publication(tmp_path, monkeypatch):
    root, folder = tmp_path / "project", tmp_path / "session"
    root.mkdir()
    folder.mkdir()
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    monkeypatch.setattr(campaigns, "git_revision", lambda folder: None)
    monkeypatch.setattr(campaigns, "session_events", lambda folder: [
        {"type": "action", "h": "h01", "n": 1, "url": "http://localhost/orders"}])
    source = folder / "source.json"
    campaigns.write(source, {"expect": [{"type": "text-visible", "text": "Saved"}]})
    campaigns.write(folder / "proof.json", {"scenario": str(source)})
    campaigns.write(folder / "constats.json", {"constats": [
        {"titre": "Save", "fingerprint": "save", "preuves": {"before": "proof.json"}}]})
    original = campaigns.write
    interrupted = False

    def fail_once(path, data):
        nonlocal interrupted
        if Path(path) == root / "findings.json" and not interrupted:
            interrupted = True
            raise OSError("Simulated failure after publishing campaign history")
        return original(path, data)

    monkeypatch.setattr(campaigns, "write", fail_once)
    with pytest.raises(OSError, match="Simulated failure"):
        campaigns.command_record(SimpleNamespace(dossier=folder, project="shop", label="run", repo=None))
    assert (root / "campaigns.json").exists()
    assert not (root / "findings.json").exists()
    assert (root / campaigns.PENDING_FILE).exists()
    campaigns.command_status(SimpleNamespace(project="shop"))
    assert not (root / campaigns.PENDING_FILE).exists()
    assert campaigns.read(root / "campaigns.json", {})["campaigns"][0]["id"] == "run"
    saved = campaigns.read(root / "findings.json", {})["save"]
    assert Path(saved["scenario"]).is_file() and saved["last_seen"] == "run"
    assert campaigns.read(root / "map.json", {})["routes"]["/orders"]["visits"] == 1


@pytest.mark.parametrize("unsafe", ["../escape.json", "scenarios/../../escape.json", "C:/escape.json"])
def test_recovery_rejects_all_unsafe_targets_before_publishing(tmp_path, unsafe):
    files = {"campaigns.json": {"changed": True}, "findings.json": {}, "map.json": {}, unsafe: {}}
    campaigns.write(tmp_path / campaigns.PENDING_FILE, {"version": 1, "files": files})
    with pytest.raises(ValueError, match="Unsafe path"):
        with campaigns.project_lock(tmp_path):
            pytest.fail("Invalid recovery must not expose partial memory")
    assert not (tmp_path / "campaigns.json").exists()


def test_transaction_limit_is_checked_before_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(campaigns, "MAX_PENDING_BYTES", 10)
    with pytest.raises(ValueError, match="exceeds"):
        campaigns.publish_project(tmp_path, {"campaigns.json": {}, "findings.json": {}, "map.json": {}})
    assert list(tmp_path.iterdir()) == []


def test_parallel_campaign_records_serialize_the_entire_update(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    monkeypatch.setattr(campaigns, "git_revision", lambda folder: None)
    monkeypatch.setattr(campaigns, "session_events", lambda folder: [])
    original = campaigns._record
    active = maximum = 0
    counter_lock = threading.Lock()
    start = threading.Barrier(2)

    def tracked(*args):
        nonlocal active, maximum
        with counter_lock:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.04)
            return original(*args)
        finally:
            with counter_lock:
                active -= 1

    monkeypatch.setattr(campaigns, "_record", tracked)

    def record(label):
        folder = tmp_path / label
        folder.mkdir()
        campaigns.write(folder / "constats.json", {"constats": [{"titre": label, "fingerprint": label}]})
        start.wait(timeout=5)
        return campaigns.command_record(SimpleNamespace(dossier=folder, project="shop", label=label, repo=None))

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(record, ["first", "second"])) == [0, 0]
    assert maximum == 1
    assert {c["id"] for c in campaigns.read(root / "campaigns.json", {})["campaigns"]} == {"first", "second"}
    assert set(campaigns.read(root / "findings.json", {})) == {"first", "second"}


def test_project_lock_serializes_separate_processes(tmp_path):
    worker = """
import sys, time
from pathlib import Path
from chaosfolk import campaigns
root = Path(sys.argv[1])
for _ in range(10):
    with campaigns.project_lock(root):
        data = campaigns.read(root / 'counter.json', {'count': 0})
        time.sleep(0.005)
        campaigns.write(root / 'counter.json', {'count': data['count'] + 1})
"""

    def run(_):
        return subprocess.run([sys.executable, "-c", worker, str(tmp_path)], capture_output=True, text=True, timeout=20)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
    assert campaigns.read(tmp_path / "counter.json", {})["count"] == 20


def test_replay_does_not_overwrite_a_concurrent_campaign_or_escape_paths(tmp_path, monkeypatch):
    from chaosfolk import engine

    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(campaigns, "project_dir", lambda project: root)
    monkeypatch.setattr(engine, "charger_moteur", lambda: None)
    source = root / "original.json"
    campaigns.write(source, {"url": "http://localhost/", "expect": [{"type": "text-visible", "text": "Saved"}]})
    key = "../../escaped"
    finding = {"state": "open", "seen": 1, "title": "Save", "scenario": str(source)}
    campaigns.write(root / "findings.json", {key: finding})

    async def replay(args):
        assert Path(args.scenario[0]).parent.parent.parent == root / "replays"
        assert "/" not in args.nom and "\\" not in args.nom
        with campaigns.project_lock(root):
            campaigns.write(root / "findings.json", {key: dict(finding, seen=2), "new": {"state": "open"}})
        campaigns.write(Path(args.sortie) / f"{args.nom}.json", {"fois": 3, "casses": 0, "verdict": "passed"})

    monkeypatch.setattr(engine, "rejouer", replay)
    opts = SimpleNamespace(project="shop", limit=1, replay=True, url=None, times=3)
    assert campaigns.command_select(opts) == 1
    current = campaigns.read(root / "findings.json", {})
    assert current[key]["seen"] == 2 and current[key]["state"] == "open"
    assert "new" in current
    assert not (tmp_path / "escaped.json").exists()
