import argparse
import os

import psutil
import pytest

from chaosfolk import engine


class FakeProcess:
    def __init__(self, created=123.0):
        self.created = created
        self.terminated = False
        self.killed = False

    def create_time(self):
        return self.created

    def is_running(self):
        return True

    def children(self, recursive=False):
        return []

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


@pytest.fixture
def process(monkeypatch):
    process = FakeProcess()
    monkeypatch.setattr(psutil, "Process", lambda pid: process)
    monkeypatch.setattr(psutil, "wait_procs", lambda processes, timeout: (list(processes), []))
    if os.name != "nt":
        monkeypatch.setattr(engine.os, "getpgid", lambda pid: pid)
        monkeypatch.setattr(engine.os, "getsid", lambda pid: pid)
    return process


def identity(**extra):
    return {"pid": 123, "created": 123.0, "group": 123, "session": None if os.name == "nt" else 123, **extra}


def test_reused_pid_is_never_terminated(process):
    with pytest.raises(ValueError, match="reused"):
        engine.stop_owned_process(identity(created=122.0))
    assert not process.terminated and not process.killed


@pytest.mark.parametrize("record", [None, {}, {"pid": 123}, identity(group=999)])
def test_missing_or_wrong_ownership_is_never_terminated(process, record):
    with pytest.raises(ValueError):
        engine.stop_owned_process(record)
    assert not process.terminated and not process.killed


def test_verified_owned_process_is_terminated(process):
    assert engine.stop_owned_process(identity())
    assert process.terminated
    assert not process.killed


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group ownership")
def test_changed_process_group_is_never_terminated(process, monkeypatch):
    monkeypatch.setattr(engine.os, "getpgid", lambda pid: 999)
    with pytest.raises(ValueError, match="group"):
        engine.stop_owned_process(identity())
    assert not process.terminated


def test_stop_app_handles_live_unresponsive_app_without_url_probe(tmp_path, monkeypatch, process):
    record = {"app_pid": 123, "app_identity": identity(), "url": "http://127.0.0.1:1/"}
    engine.ecrire_json(tmp_path / "serveur.json", record)
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "inactive.json")
    monkeypatch.setattr(engine, "url_repond", lambda *_: pytest.fail("URL liveness must not establish ownership"))
    assert engine.commande_arreter_app(argparse.Namespace(dossier=str(tmp_path))) == 0
    assert process.terminated
    saved = engine.lire_json(tmp_path / "serveur.json")
    assert saved["app_pid"] is saved["app_identity"] is None


def test_stop_app_preserves_record_when_identity_mismatches(tmp_path, monkeypatch, process):
    record = {"app_pid": 123, "app_identity": identity(created=1), "url": "http://127.0.0.1:3000/"}
    engine.ecrire_json(tmp_path / "serveur.json", record)
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "inactive.json")
    with pytest.raises(ValueError, match="reused"):
        engine.commande_arreter_app(argparse.Namespace(dossier=str(tmp_path)))
    assert engine.lire_json(tmp_path / "serveur.json") == record
    assert not process.terminated
