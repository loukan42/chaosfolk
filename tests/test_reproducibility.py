import asyncio
import json
import sys
import subprocess
from types import SimpleNamespace

import pytest

from chaosfolk import reproducibility as evidence


def config(tmp_path, **changes):
    value = {"data_id": "fixture-v1", "prepare": {"command": [sys.executable, "-c", "pass"]},
             "verify": {"command": [sys.executable, "-c", 'print(\'{"ready":true,"data_id":"fixture-v1"}\')']}}
    value.update(changes)
    path = tmp_path / "environment.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("verify", [
    {"command": [sys.executable, "-c", 'print(\'{"ready":true,"data_id":"wrong"}\')']},
    {"command": [sys.executable, "-c", "print('private output'); raise SystemExit(1)"]},
    {"command": [sys.executable, "-c", "import time; time.sleep(10)"], "timeout": .1},
    {"command": [sys.executable, "-c", "print('x'*70000)"]},
])
def test_failed_fixture_verification_is_invalid_and_private(tmp_path, verify):
    result = asyncio.run(evidence.prepare(evidence.load_environment(config(tmp_path, verify=verify))))
    assert result["status"] == "invalid"
    assert "private output" not in json.dumps(result)


def test_preparation_and_browser_only_status(tmp_path):
    result = asyncio.run(evidence.prepare(evidence.load_environment(config(tmp_path))))
    assert result == {"status": "reset-verified", "data_id": "fixture-v1"}
    assert asyncio.run(evidence.prepare(None))["status"] == "browser-only"


@pytest.mark.parametrize("changes", [{"verify": None}, {"data_id": ""},
    {"prepare": {"command": "echo unsafe"}}, {"prepare": {"command": ["x"], "timeout": float('inf')}}])
def test_invalid_environment_is_rejected(tmp_path, changes):
    with pytest.raises(ValueError):
        evidence.load_environment(config(tmp_path, **changes))


def test_counts_expose_invalids_without_diluting_failure_rate():
    assert evidence.trial_counts({"demandes": 5, "fois": 4, "casses": 1}) == {
        "requested": 5, "valid": 4, "failures": 1, "invalid": 1, "failure_rate": .25}
    assert evidence.trial_counts({"demandes": 5, "fois": 0, "casses": 0})["failure_rate"] is None
    assert evidence.trial_counts({"demandes": True, "fois": 1, "casses": 0}) is None


def test_manifest_preserves_provenance_without_browser_credentials(tmp_path):
    state = {"cookies": [{"name": "auth", "value": "private-cookie"}], "origins": []}
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    source = tmp_path / "scenario.json"
    source.write_text('{}', encoding="utf-8")
    (tmp_path / "personas.json").write_text(json.dumps({"humains": [{"profil_id": "p1", "etat": state}]}))
    (tmp_path / "tirage.json").write_text(json.dumps({"graine": 42, "provenance": {"profiles_sha256": "old"}}))
    scenario = {"etat": state, "sessions": {"reader": {"etat": "state.json"}}, "pannes": []}
    browser = SimpleNamespace(version="123", browser_type=SimpleNamespace(name="chromium"))
    result = evidence.manifest(scenario, tmp_path, browser, None, source)
    assert result["seed"] == 42
    assert result["profile_provenance"]["profiles_sha256"] == "old"
    assert result["application"] == {"version": None, "git": None}
    assert "private-cookie" not in json.dumps(result)
    assert all(s["sha256"] for s in result["browser_states"])
    before = result["source_sha256"]
    source.write_text('{"changed":true}', encoding="utf-8")
    assert evidence.manifest(scenario, tmp_path, browser, None, source)["source_sha256"] != before


def test_application_git_identity_records_changes_and_missing_repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True, text=True, check=True).stdout.strip()
    git("init")
    (tmp_path / "app.txt").write_text("before")
    git("add", "app.txt")
    git("-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "Fixture")
    assert evidence.git_identity(tmp_path) == {"commit": git("rev-parse", "HEAD"), "dirty": False}
    (tmp_path / "app.txt").write_text("after")
    assert evidence.git_identity(tmp_path)["dirty"] is True
    assert evidence.git_identity(tmp_path / "missing") is None


@pytest.mark.parametrize("failed,valid,status", [(0,3,"all-pass"),(3,3,"failures-observed"),
    (1,3,"intermittent"),(0,2,"inconclusive")])
def test_matrix_summary_does_not_assign_cause_or_severity(failed, valid, status):
    cells = {f"{journey}/{mode}": {"demandes": 3, "fois": valid, "casses": failed}
             for journey in ("observed", "reference") for mode in ("with_faults", "without_faults")}
    assert evidence.matrix_summary(cells)["status"] == status
    assert evidence.matrix_summary({})["status"] == "inconclusive"
