"""Resource bounds, metadata snapshots and evidence confinement."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import threading

import pytest

from chaosfolk import campaigns, mcp_server, privacy, usage


def measurement(identifier="a", **extra):
    return {"id": identifier, "source": "host", "input_tokens": 10, "output_tokens": 3,
            "cost": 0.125, "currency": "USD", **extra}


@pytest.mark.parametrize("events,limits", [
    ([], {"max_tokens": 50}),
    ([measurement(), measurement()], {}),
    ([measurement(), measurement("b")], {"max_cost": 0.2}),
    ([measurement(output_tokens=None), measurement("b", cost=None)], {"max_cost": 1, "max_tokens": 100}),
    ([measurement(metadata={"source": [1, True, None, "é" * 30]}),
      measurement(metadata={"source": [1.0, 1, None, "é" * 30]})], {}),
])
def test_disk_usage_matches_memory_with_exact_duplicate_semantics(events, limits):
    assert usage.summarize(iter(events), **limits, dedup_storage="disk") == usage.summarize(iter(events), **limits)


def test_disk_usage_detects_conflicts_after_many_unique_events():
    def events():
        for index in range(5000):
            yield measurement(str(index))
        yield measurement("0", input_tokens=11)

    with pytest.raises(ValueError, match="Conflicting duplicate"):
        usage.summarize(events(), dedup_storage="disk")


@pytest.mark.parametrize("conflicting", [False, True])
def test_disk_usage_closes_database_and_removes_temporary_measurements(tmp_path, monkeypatch, conflicting):
    temporary_directory = usage.tempfile.TemporaryDirectory
    folders = []

    def directory(**kwargs):
        result = temporary_directory(dir=tmp_path, **kwargs)
        folders.append(Path(result.name))
        return result

    monkeypatch.setattr(usage.tempfile, "TemporaryDirectory", directory)
    events = [measurement(), measurement(input_tokens=999)] if conflicting else [measurement()]
    if conflicting:
        with pytest.raises(ValueError, match="Conflicting duplicate"):
            usage.summarize(events, dedup_storage="disk")
    else:
        assert usage.summarize(events, dedup_storage="disk")["events"] == 1
    assert folders and all(not folder.exists() for folder in folders)


def test_usage_disk_cli_and_hardlink_output_do_not_replace_measurements(tmp_path, capsys):
    source, destination = tmp_path / "usage.jsonl", tmp_path / "alias.json"
    original = json.dumps(measurement()) + "\n"
    source.write_text(original, encoding="utf-8")
    destination.hardlink_to(source)
    assert usage.main(["--input", str(source), "--dedup-storage", "disk", "--max-tokens", "13"]) == 1
    assert json.loads(capsys.readouterr().out)["gate"] == "stop"
    assert usage.main(["--input", str(source), "--dedup-storage", "disk", "--output", str(destination)]) == 2
    assert "must not replace" in capsys.readouterr().out
    assert source.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("method", ["status", "findings", "scenarios"])
def test_mcp_reads_recovered_campaign_snapshot(tmp_path, method):
    snapshot = {"version": 1, "files": {
        "campaigns.json": {"campaigns": [{"revision": "a1b2c3d"}]},
        "findings.json": {"one": {"state": "open", "seen": 1}},
        "map.json": {}, "scenarios/abcdef123456.json": {"private": "not-exposed"},
    }}
    campaigns.write(tmp_path / campaigns.PENDING_FILE, snapshot)
    reader = mcp_server.ProjectReader(tmp_path)
    result = getattr(reader, method)()
    assert not (tmp_path / campaigns.PENDING_FILE).exists()
    assert "not-exposed" not in json.dumps(result)
    assert reader.status()["findings"] == 1
    assert reader.status()["campaigns"] == 1
    assert reader.scenarios()["scenarios"] == ["abcdef123456"]


def test_mcp_status_waits_until_both_campaign_files_are_published(tmp_path):
    reader = mcp_server.ProjectReader(tmp_path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with campaigns.project_lock(tmp_path):
            campaigns.write(tmp_path / "campaigns.json", {"campaigns": [{}]})
            entered = threading.Event()

            def read():
                entered.set()
                return reader.status()

            response = pool.submit(read)
            assert entered.wait(2)
            assert not response.done()
            campaigns.write(tmp_path / "findings.json", {"one": {"state": "open"}})
        result = response.result(timeout=5)
    assert result["findings"] == result["campaigns"] == 1


def test_mcp_rejects_invalid_pending_paths_without_partial_publication(tmp_path):
    snapshot = {"version": 1, "files": {"campaigns.json": {}, "findings.json": {}, "map.json": {}, "../escape.json": {}}}
    campaigns.write(tmp_path / campaigns.PENDING_FILE, snapshot)
    server = mcp_server.Server(tmp_path)
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "campaign_status"}})
    assert response["result"]["isError"]
    assert not (tmp_path / "campaigns.json").exists()


def test_mcp_corrupt_lock_database_returns_tool_error(tmp_path):
    (tmp_path / ".campaign-lock.sqlite3").write_bytes(b"corrupt database" * 100)
    server = mcp_server.Server(tmp_path)
    server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    response = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "campaign_status"}})
    assert response["result"]["isError"]
    assert server.handle({"jsonrpc": "2.0", "id": 3, "method": "ping"})["result"] == {}


def test_privacy_rejects_journal_symlink_outside_source(tmp_path):
    source, output = tmp_path / "session", tmp_path / "public"
    source.mkdir()
    (source / "constats.json").write_text('{"constats": []}', encoding="utf-8")
    private = tmp_path / "private.jsonl"
    private.write_text('{"type": "action", "pense": "confidential"}\n', encoding="utf-8")
    try:
        (source / "journal.jsonl").symlink_to(private)
    except OSError:
        pytest.skip("Creating symbolic links requires permission on this host")
    with pytest.raises(ValueError, match="escapes"):
        privacy.export_report(source, output, "en")
    assert not output.exists()
