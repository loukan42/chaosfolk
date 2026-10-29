"""Windows sharing collisions are retried, permanent access failures surface."""
import os
import errno
from pathlib import Path

import pytest

from chaosfolk import engine, private_state

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows file sharing")


def sharing_error(code):
    error = PermissionError(errno.EACCES, "Synthetic Windows sharing failure")
    if code is not None:
        error.winerror = code
    return error


@pytest.mark.parametrize("code", [None, 5, 32, 33])
def test_engine_json_read_recovers_transient_sharing_collision(tmp_path, monkeypatch, code):
    path = tmp_path / "state.json"
    path.write_text('\ufeff{"value": 42}', encoding="utf-8")
    original = Path.read_text
    attempts = []

    def sometimes_locked(target, *args, **kwargs):
        attempts.append(target)
        if len(attempts) == 1:
            raise sharing_error(code)
        return original(target, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", sometimes_locked)
    assert engine.lire_json(path) == {"value": 42}
    assert len(attempts) == 2


def test_atomic_json_write_recovers_transient_replace_collision(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    path.write_text('{"value": "old"}')
    original = os.replace
    attempts = []

    def sometimes_locked(source, target):
        attempts.append(target)
        if len(attempts) == 1:
            raise sharing_error(32)
        return original(source, target)

    monkeypatch.setattr(os, "replace", sometimes_locked)
    private_state.write_json(path, {"value": "new"})
    assert private_state.read_json(path) == {"value": "new"}
    assert len(attempts) == 2
    assert list(tmp_path.glob(".private-*")) == []


@pytest.mark.parametrize("operation", ["read", "write"])
def test_permanent_access_denied_is_bounded_and_preserves_json(tmp_path, monkeypatch, operation):
    path = tmp_path / "state.json"
    path.write_text('{"value": "old"}')
    clock = iter([0, .4, 1.1])
    attempts = []

    def always_locked(*args, **kwargs):
        attempts.append(True)
        raise sharing_error(5)

    with monkeypatch.context() as patch:
        patch.setattr(private_state.time, "monotonic", lambda: next(clock))
        patch.setattr(private_state.time, "sleep", lambda _: None)
        if operation == "read":
            patch.setattr(Path, "read_text", always_locked)
            callback = lambda: private_state.read_json(path)
        else:
            patch.setattr(os, "replace", always_locked)
            callback = lambda: private_state.write_json(path, {"value": "new"})
        with pytest.raises(PermissionError):
            callback()
    assert len(attempts) == 2
    assert private_state.read_json(path) == {"value": "old"}
    assert list(tmp_path.glob(".private-*")) == []
