"""Bounded campaign publication, replayable recovery and process identities."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from chaosfolk import campaigns, integrations


def snapshots():
    return {"campaigns.json": {"campaigns": [{"id": "one"}]},
            "findings.json": {"issue": {"state": "open"}}, "map.json": {"routes": {}}}


def test_publication_streams_without_serializing_or_decoding_a_second_full_copy(tmp_path, monkeypatch):
    data = snapshots()

    def no_full_copy(*args, **kwargs):
        pytest.fail("Publication must use bounded encoding and the existing validated snapshots")

    monkeypatch.setattr(campaigns.json, "dumps", no_full_copy)
    monkeypatch.setattr(campaigns, "recover_project", no_full_copy)
    campaigns.publish_project(tmp_path, data)
    for name, expected in data.items():
        assert campaigns.read(tmp_path / name, None) == expected
    assert not (tmp_path / campaigns.PENDING_FILE).exists()


def test_failed_file_sync_preserves_the_previous_snapshot(tmp_path, monkeypatch):
    target = tmp_path / "map.json"
    target.write_text('{"previous": true}', encoding="utf-8")

    def fail_sync(_descriptor):
        raise OSError("flush failed")

    monkeypatch.setattr(campaigns.os, "fsync", fail_sync)
    with pytest.raises(OSError, match="flush failed"):
        campaigns.write(target, {"new": True})
    assert campaigns.read(target, None) == {"previous": True}
    assert list(tmp_path.iterdir()) == [target]


def test_journal_is_synced_before_publication_and_removed_after_snapshots(tmp_path, monkeypatch):
    events = []
    replace, unlink = Path.replace, Path.unlink
    current = None
    atomic_write = campaigns._atomic_write

    def writing(path, data, max_bytes=None):
        nonlocal current
        current = Path(path).name
        return atomic_write(path, data, max_bytes)

    def replacing(path, destination):
        events.append(("replace", Path(destination).name))
        return replace(path, destination)

    def unlinking(path, *args, **kwargs):
        if path.name == campaigns.PENDING_FILE:
            events.append(("unlink", path.name))
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(campaigns, "_atomic_write", writing)
    monkeypatch.setattr(campaigns.os, "fsync", lambda descriptor: events.append(("sync", current)))
    monkeypatch.setattr(campaigns, "sync_directory", lambda directory: events.append(("directory", current)))
    monkeypatch.setattr(Path, "replace", replacing)
    monkeypatch.setattr(Path, "unlink", unlinking)
    campaigns.publish_project(tmp_path, snapshots())
    assert events.index(("sync", campaigns.PENDING_FILE)) < events.index(("replace", campaigns.PENDING_FILE))
    removed = events.index(("unlink", campaigns.PENDING_FILE))
    for name in snapshots():
        assert events.index(("replace", campaigns.PENDING_FILE)) < events.index(("sync", name))
        assert events.index(("sync", name)) < events.index(("replace", name))
        assert events.index(("replace", name)) < events.index(("directory", name)) < removed


def test_transaction_byte_limit_counts_utf8_and_leaves_no_partial_files(tmp_path, monkeypatch):
    data = snapshots()
    data["map.json"]["text"] = "é" * 100
    encoded = json.dumps({"version": 1, "files": data}, ensure_ascii=False, indent=2).encode("utf-8")
    monkeypatch.setattr(campaigns, "MAX_PENDING_BYTES", len(encoded) - 1)
    with pytest.raises(ValueError, match="exceeds"):
        campaigns.publish_project(tmp_path, data)
    assert not list(tmp_path.iterdir())
    monkeypatch.setattr(campaigns, "MAX_PENDING_BYTES", len(encoded))
    campaigns.publish_project(tmp_path, data)
    assert campaigns.read(tmp_path / "map.json", {}) == data["map.json"]


def test_recovery_reads_at_most_the_limit_plus_one_byte(tmp_path, monkeypatch):
    pending = tmp_path / campaigns.PENDING_FILE
    pending.write_bytes(b" " * 1000)
    monkeypatch.setattr(campaigns, "MAX_PENDING_BYTES", 64)
    original_open = Path.open
    reads = []

    class LimitedReader:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def read(self, count):
            reads.append(count)
            return self.stream.read(count)

    def opening(path, *args, **kwargs):
        stream = original_open(path, *args, **kwargs)
        return LimitedReader(stream) if path == pending else stream

    monkeypatch.setattr(Path, "open", opening)
    with pytest.raises(ValueError, match="exceeds"):
        campaigns.recover_project(tmp_path)
    assert reads == [65]
    assert list(tmp_path.iterdir()) == [pending]


def test_new_publication_cannot_overwrite_an_unrecovered_transaction(tmp_path, monkeypatch):
    original_write = campaigns.write

    def fail_snapshot(path, data):
        raise OSError("disk failure")

    monkeypatch.setattr(campaigns, "write", fail_snapshot)
    with pytest.raises(OSError, match="disk failure"):
        campaigns.publish_project(tmp_path, snapshots())
    pending = (tmp_path / campaigns.PENDING_FILE).read_bytes()
    with pytest.raises(ValueError, match="Recover the pending"):
        campaigns.publish_project(tmp_path, snapshots())
    assert (tmp_path / campaigns.PENDING_FILE).read_bytes() == pending
    monkeypatch.setattr(campaigns, "write", original_write)
    campaigns.recover_project(tmp_path)
    assert not (tmp_path / campaigns.PENDING_FILE).exists()


def test_session_summary_keeps_only_referenced_urls_in_one_pass(tmp_path, monkeypatch):
    source = [{"type": "action", "h": "h01", "n": index, "url": f"http://localhost/orders/{index}",
               "ecran": "private screen" * 100, "resultat": "ok"} for index in range(100)]
    expected = campaigns.journey_map(tmp_path, deepcopy(source))
    calls = []

    def events(folder):
        calls.append(folder)
        yield from source

    monkeypatch.setattr(campaigns, "session_events", events)
    findings = [{"titre": "Save", "evenements": [{"h": "h01", "n": 5}]},
                {"fingerprint": "explicit", "evenements": [{"h": "h01", "n": 10}]}]
    actions, result = campaigns.session_summary(tmp_path, findings)
    assert calls == [tmp_path]
    assert result == expected
    assert actions == {("h01", 5): {"url": "http://localhost/orders/5"}}
    assert campaigns.fingerprint(findings[0], source) == campaigns.fingerprint(findings[0], actions=actions)


def test_adapter_cleanup_does_not_resolve_an_exited_or_reused_pid(monkeypatch):
    import psutil

    owned = SimpleNamespace(is_running=Mock(return_value=False), children=Mock(), kill=Mock())
    process = SimpleNamespace(pid=42, poll=Mock(return_value=0), kill=Mock())
    monkeypatch.setattr(psutil, "Process", lambda pid: pytest.fail("Cleanup must use the captured process identity"))
    integrations._kill_tree(process, owned)
    owned.children.assert_not_called()
    owned.kill.assert_not_called()
    process.kill.assert_not_called()


def test_adapter_cleanup_uses_the_captured_tree():
    child = SimpleNamespace(kill=Mock())
    owned = SimpleNamespace(is_running=Mock(return_value=True), children=Mock(return_value=[child]), kill=Mock())
    integrations._kill_tree(SimpleNamespace(pid=42), owned)
    owned.children.assert_called_once_with(recursive=True)
    child.kill.assert_called_once_with()
    owned.kill.assert_called_once_with()
