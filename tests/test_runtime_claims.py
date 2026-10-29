"""Keep measurements and tool lifetime attached to the attempt that owns them."""
import pytest

from chaosfolk import owned_process
from chaosfolk.audit_session import catalog
from test_audit_session import setup_run


def task_state(session, task_id):
    with session.db() as db:
        return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())


@pytest.mark.parametrize("executor", ["audit", "fields"])
def test_new_measurement_preserves_coordinator_review_claim(tmp_path, executor):
    session = setup_run(tmp_path)
    selected = next(item for item in catalog().values() if item["executor"] == executor)
    session.configure(excluded=[item["id"] for item in catalog().values()
                               if item["configurable"] and item["id"] != selected["id"]])
    (tmp_path / "first.json").write_text('{"measurement": 1}')
    (tmp_path / "later.json").write_text('{"measurement": 2}')
    session.measure(executor, "http://localhost:3000/page-0", ["first.json"])
    task = session.claim("reviewer", "coordinator", 1)["tasks"][0]
    before = task_state(session, task["task_id"])

    session.measure(executor, task["route"], ["later.json"])

    assert task_state(session, task["task_id"]) == before
    session.record(task["task_id"], "passed", "Reviewed the original measurement", ["first.json"],
                   "reviewer", task["claim"])


def test_execute_stops_when_same_task_is_reassigned(tmp_path, monkeypatch):
    session = setup_run(tmp_path)
    task = session.claim("original", "coordinator", 1)["tasks"][0]
    session.configure(excluded=[item["id"] for item in catalog().values()
                               if item["configurable"] and item["id"] != task["check_id"]])
    instances = []

    class Process:
        def __init__(self, *args, **kwargs):
            self.polls = 0
            self.closed = False
            self.returncode = None
            instances.append(self)

        def poll(self):
            self.polls += 1
            if self.polls == 1:
                session.release("original")
                replacement = session.claim("replacement", "coordinator", 1)["tasks"][0]
                assert replacement["task_id"] == task["task_id"]
                return None
            self.returncode = 0
            return 0

        def close(self):
            self.closed = True
            self.returncode = self.returncode if self.returncode is not None else -1

    monkeypatch.setattr(owned_process, "OwnedProcess", Process)
    result = session.execute(task["task_id"], ["probe", "http://localhost/"])

    assert instances[0].closed
    assert instances[0].polls == 1, "Released tool continued while a replacement owned the task"
    assert not result["ok"]
    assert task_state(session, task["task_id"])["owner"] == "replacement"
    assert task_state(session, task["task_id"])["status"] == "running"


def test_delayed_start_cannot_undo_a_more_recent_stop(tmp_path):
    session = setup_run(tmp_path)
    session.stop()
    revision = session.snapshot()["config"]["revision"]
    session.start()
    stopped = session.stop()
    with pytest.raises(ValueError, match="changed"):
        session.start(expected_revision=revision)
    assert session.snapshot()["config"] == stopped["config"]
    assert session.start(expected_revision=stopped["config"]["revision"])["ok"]


def test_stop_while_already_stopped_invalidates_delayed_resume(tmp_path):
    session = setup_run(tmp_path)
    prior_stop = session.stop()
    repeated_stop = session.stop()
    with pytest.raises(ValueError, match="changed"):
        session.start(expected_revision=prior_stop["config"]["revision"])
    assert session.snapshot()["config"] == repeated_stop["config"]
    assert repeated_stop["config"]["elapsed"] == prior_stop["config"]["elapsed"]


@pytest.mark.parametrize("revision", [True, -1, "1", 1.0])
def test_start_revision_requires_nonnegative_integer(tmp_path, revision):
    session = setup_run(tmp_path)
    before = session.snapshot()["config"]
    with pytest.raises(ValueError, match="revision"):
        session.start(expected_revision=revision)
    assert session.snapshot()["config"] == before


def test_private_session_rejects_directory_links_before_writing(tmp_path):
    import os
    from chaosfolk.private_state import session_directory

    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "existing.txt"
    sentinel.write_text("unchanged")
    folder = tmp_path / "session"
    folder.mkdir()
    link = folder / "audit-evidence"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="link"):
            session_directory(folder)
        assert sentinel.read_text() == "unchanged"
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()
