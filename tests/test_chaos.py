import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sys
import time
from types import SimpleNamespace

import pytest

from chaosfolk import chaos, chaos_jobs, engine
from chaosfolk.cli import main


def horde(tmp_path, policy=None, dry_run=False):
    engine.charger_moteur()
    source = tmp_path / "policy.json"
    source.write_text(json.dumps(policy or {}), encoding="utf-8")
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://localhost:3000", "--folder", str(tmp_path),
                                                 "--chaos-policy", str(source), "--project", "shop"])
    opts.dry_run = dry_run
    result = engine.Horde(opts)
    result.humains = {hid: SimpleNamespace(page=SimpleNamespace(url="http://localhost:3000/orders"), n_gestes=2)
                      for hid in ("h01", "h02", "h03", "h04")}
    result.fiches = {"h01": {"role": "editor"}, "h02": {"role": "reader"}}
    return result


def fault(h, kind="offline", human="h01"):
    f = {"id": f"p{len(h.pannes)+1}", "type": kind, "h": human, "phase": "admission", "scheduled": False,
         "a": 0, "apres": None, "duree": None, "lot": "p1"}
    h.pannes.append(f)
    return f


def admit(h, f):
    return asyncio.run(h.chaos.admit(f, h))


@pytest.mark.parametrize("policy", [
    {"probability": -1}, {"probability": float("nan")}, {"max_active": True}, {"max_active": -1},
    {"dry_run": "yes"}, {"unknown": True}, {"shared_state": "state.db"}, {"health_check": "shell string"},
    {"exclude": {"unknown": []}}, {"forbid_pairs": [["offline", "unknown"]]},
    {"groups": [{"name": "a", "max_active": -1}]}, {"allowed_faults": ["bad-fault"]},
    {"secret_env": {"TOKEN": {"value": "never embed a secret"}}},
    {"window": {"timezone": "UTC", "start_hour": 18, "end_hour": 9}},
])
def test_invalid_policy_is_rejected_before_browser_or_hooks(policy):
    with pytest.raises(ValueError):
        chaos.validate(policy)


def test_default_session_has_no_policy_io_or_hooks(tmp_path):
    engine.charger_moteur()
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://localhost:3000", "--folder", str(tmp_path)])
    h = engine.Horde(opts)
    assert h.chaos is None
    h.journal({"type": "action"})
    h.journal_f.close()
    assert not (tmp_path / "chaos-metrics.json").exists()


def test_simulation_does_not_apply_fault_or_write_real_evidence(tmp_path):
    h = horde(tmp_path, dry_run=True)
    f = fault(h, "storage-empty")
    asyncio.run(h.activer(f, 0))  # Mock users have no appliquer method: a real mutation would fail.
    assert f["phase"] == "simulee"
    h.journal_f.close()
    events = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(e["type"] == "chaos-simulated" for e in events)
    assert not any(e["type"] == "panne-debut" for e in events)
    assert json.loads((tmp_path / "chaos-plan.json").read_text())["faults"][0]["phase"] == "simulee"
    assert h.chaos.metrics["applied"] == 0


def test_concurrent_admissions_obey_active_limit(tmp_path):
    h = horde(tmp_path, {"max_active": 1})
    async def apply(f):
        reason = await h.chaos.admit(f, h)
        if reason is None:
            f["phase"] = "active"
        return reason
    first, second = fault(h), fault(h, human="h02")
    async def run():
        return await asyncio.gather(apply(first), apply(second))
    assert asyncio.run(run()) == [None, "max-active"]
    h.journal_f.close()


@pytest.mark.parametrize("policy,kind,human,reason", [
    ({"enabled": False}, "offline", "h01", "injections-paused"),
    ({"probability": 0}, "offline", "h01", "probability"),
    ({"allowed_faults": ["slow"]}, "offline", "h01", "fault-not-allowed"),
    ({"exclude": {"roles": ["editor"]}}, "offline", "h01", "excluded-target"),
    ({"exclude": {"humans": ["h02"]}}, "app-stop", None, "excluded-global-target"),
    ({"exclude": {"routes": ["/billing/*"]}}, "offline", "h01", "route-exclusion-needs-request-fault"),
    ({"exclude": {"methods": ["POST"]}}, "offline", "h01", "method-exclusion-needs-request-fault"),
    ({"max_affected_fraction": 0.5}, "app-stop", None, "affected-user-budget"),
    ({"max_injections": 0}, "offline", "h01", "injection-budget"),
])
def test_denied_injections_finish_without_waiting(tmp_path, policy, kind, human, reason):
    h = horde(tmp_path, policy)
    f = fault(h, kind, human)
    asyncio.run(h.activer(f, 0))
    assert f["phase"] == "ignoree" and f["reason"] == reason
    assert h.chaos.count == 0
    h.journal_f.close()


def test_cooldown_groups_pairs_duration_and_manual_schedule_separation(tmp_path):
    h = horde(tmp_path, {"schedule_enabled": False, "min_interval": 60, "max_fault_duration": 5,
                         "groups": [{"name": "editors", "roles": ["editor"]}],
                         "forbid_pairs": [["offline", "http-error"]]})
    first = fault(h)
    assert admit(h, first) is None
    assert first["chaos_group"] == "editors" and first["duree"] == 5000
    first["phase"] = "active"
    assert admit(h, fault(h, "http-error", "h02")) == "forbidden-combination"
    assert admit(h, fault(h)) == "cooldown"
    scheduled = fault(h, human="h03")
    scheduled["scheduled"] = True
    assert admit(h, scheduled) == "scheduling-disabled"
    h.journal_f.close()


def test_group_limit_leaves_other_group_available(tmp_path):
    h = horde(tmp_path, {"groups": [{"name": "writers", "humans": ["h01", "h02"], "max_active": 1}]})
    f = fault(h)
    assert admit(h, f) is None
    f["phase"] = "active"
    assert admit(h, fault(h, human="h02")) == "group-max-active"
    assert admit(h, fault(h, human="h03")) is None
    h.journal_f.close()


def test_policy_reload_fails_closed_and_recovers(tmp_path):
    h = horde(tmp_path, {"reload_interval": 0.01})
    h.chaos.source.write_text("{bad", encoding="utf-8")
    asyncio.run(h.chaos.refresh())
    assert admit(h, fault(h)) == "invalid-policy-or-ledger"
    h.chaos.source.write_text('{"reload_interval": 0.01, "probability": 0}', encoding="utf-8")
    h.chaos.last_refresh = 0
    asyncio.run(h.chaos.refresh())
    assert not h.chaos.invalid
    assert admit(h, fault(h)) == "probability"
    h.journal_f.close()


def test_outage_hook_cached_without_model_calls_and_failure_is_closed(tmp_path):
    marker = tmp_path / "checks"
    hook = [sys.executable, "-c", f"from pathlib import Path; p=Path({str(marker)!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x')"]
    h = horde(tmp_path, {"health_check": hook})
    assert admit(h, fault(h)) is None
    assert admit(h, fault(h, human="h02")) is None
    assert marker.read_text() == "x"
    h.chaos.policy["health_check"] = [sys.executable, "-c", "raise SystemExit(1)"]
    h.chaos.last_health = None
    assert admit(h, fault(h, human="h03")) == "outage-or-health-check-failed"
    h.journal_f.close()


def test_hooks_have_deadline_and_do_not_leak_secret_output(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAOS_TEST_SECRET", "private-value")
    h = horde(tmp_path, {"secret_env": {"HOOK_TOKEN": {"env": "CHAOS_TEST_SECRET"}}, "hook_timeout": 0.2,
                         "health_check": [sys.executable, "-c", "import time; print('private-value'); time.sleep(10)"]})
    start = time.monotonic()
    assert admit(h, fault(h)) == "outage-or-health-check-failed"
    assert time.monotonic() - start < 5
    h.journal_f.close()
    assert "private-value" not in (tmp_path / "journal.jsonl").read_text(encoding="utf-8")


def test_shared_admission_is_atomic_and_cooldown_survives_release(tmp_path):
    ledger = chaos.Ledger(tmp_path / "state.db")
    policy = chaos.validate({"max_active": 1, "min_interval": 30})
    def claim(i):
        return ledger.claim("recipe", str(i), "f1", "api", "offline", policy, now=100)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(claim, range(4)))
    assert results.count(None) == 1
    for i in range(4):
        ledger.release("recipe", str(i))
    assert ledger.claim("recipe", "new", "f2", "api", "offline", policy, now=110) == "shared-cooldown"
    assert ledger.claim("other-environment", "new", "f2", "api", "offline", policy, now=110) is None
    assert ledger.claim("recipe", "new", "f3", "api", "offline", policy, now=131) is None


def test_dry_run_does_not_reserve_shared_environment(tmp_path):
    h = horde(tmp_path, {"shared_state": "shared.db", "shared_key": "recipe", "max_active": 1}, dry_run=True)
    assert admit(h, fault(h)) is None
    assert h.chaos.leases == {}
    assert h.chaos.ledger.claim("recipe", "other", "f", "shop", "offline", h.chaos.policy) is None
    h.journal_f.close()


def test_window_uses_local_weekday_and_dst():
    window = {"timezone": "UTC", "weekdays": [0], "start_hour": 9, "end_hour": 15}
    def stamp(day, hour):
        return datetime(2026, 10, day, hour, tzinfo=timezone.utc).timestamp()
    assert chaos.in_window(window, stamp(26, 9))
    assert not chaos.in_window(window, stamp(26, 15))
    assert not chaos.in_window(window, stamp(27, 10))


def test_policy_check_never_executes_commands_or_overwrites(tmp_path):
    marker = tmp_path / "must-not-exist"
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"health_check": [sys.executable, "-c", f"open({str(marker)!r}, 'w')"]}))
    assert main(["chaos", "check", str(path)]) == 0
    assert not marker.exists()
    assert main(["chaos", "init", "--file", str(path)]) == 2


def test_job_is_opt_in_finite_and_foreground(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "state" / "active.json")
    marker = tmp_path / "job-result"
    job = {"name": "replay", "argv": [sys.executable, "-c", f"open({str(marker)!r}, 'a').write('x')"],
           "max_runs": 2, "interval": 60, "environment": "test"}
    path = tmp_path / "job.json"
    path.write_text(json.dumps(job))
    assert main(["chaos", "schedule", "add", str(path)]) == 0
    assert chaos_jobs.run_due() == []
    assert main(["chaos", "schedule", "enable", "replay"]) == 0
    now = time.time() + 1
    assert chaos_jobs.run_due(now=now)[0]["exit_code"] == 0
    assert chaos_jobs.run_due(now=now + 1) == []
    assert chaos_jobs.run_due(now=now + 61)[0]["exit_code"] == 0
    assert chaos_jobs.run_due(now=now + 122) == []
    assert marker.read_text() == "xx"


def test_job_timeout_kills_command(tmp_path):
    job = chaos_jobs.validate_job({"name": "timeout", "argv": [sys.executable, "-c", "import time; time.sleep(10)"],
                                   "max_runs": 1, "timeout": 1, "environment": "local"}, tmp_path)
    from unittest.mock import patch
    with patch("chaosfolk.campaigns.home", return_value=tmp_path):
        assert asyncio.run(chaos_jobs.run_job(job, 1)) == 124


def test_pause_during_health_check_cannot_start_a_fault(tmp_path):
    h = horde(tmp_path, {"health_check": [sys.executable, "-c", "pass"]})
    async def check(*args):
        h.chaos.paused = True
        return 0, ""
    h.chaos.call_hook = check
    f = fault(h)
    assert admit(h, f) == "policy-changed-during-admission"
    assert not f.get("chaos_admitted")
    h.journal_f.close()


def test_shutdown_during_shared_claim_releases_reservation(tmp_path):
    h = horde(tmp_path, {"shared_state": "shared.db", "shared_key": "recipe", "max_active": 1})
    ledger = h.chaos.ledger
    original = ledger.claim
    import threading
    started = threading.Event()
    def slow_claim(*args, **kwargs):
        started.set()
        time.sleep(0.05)
        return original(*args, **kwargs)
    ledger.claim = slow_claim
    async def run():
        task = asyncio.create_task(h.chaos.admit(fault(h), h))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert original("recipe", "another", "f2", "shop", "offline", h.chaos.policy) is None
    h.journal_f.close()


def test_extracted_request_exclusions_are_validated_and_replayed(tmp_path):
    h = horde(tmp_path, {"exclude": {"routes": ["/index.html"], "methods": ["GET"]}})
    (tmp_path / "config.json").write_text(json.dumps({"url": h.url}))
    async def apply(f):
        pass
    h.humains["h01"].appliquer = apply
    h.journal({"type": "arrivee", "h": "h01", "url": "http://localhost:3000/"})
    f = fault(h, "http-error")
    asyncio.run(h.activer(f, 0))
    h.journal_f.close()
    sc = engine.extraire(tmp_path, "h01")
    exclusions = {"routes": ["/index.html"], "methods": ["GET"]}
    assert sc["pannes"][0]["chaos_exclude"] == exclusions
    from chaosfolk.schema import normalize_scenario
    assert normalize_scenario(sc)["pannes"][0]["chaos_exclude"] == exclusions
    sc["pannes"][0]["chaos_exclude"] = {"routes": "not-a-list"}
    with pytest.raises(ValueError):
        normalize_scenario(sc)


def test_toml_and_saved_project_policy_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "state" / "active.json")
    path = tmp_path / "policy.toml"
    path.write_text('max_active = 2\n[window]\ntimezone = "UTC"\nstart_hour = 0\nend_hour = 24\n')
    assert chaos.read_policy(path)["max_active"] == 2
    assert main(["chaos", "init", "--project", "shop"]) == 0
    saved = chaos.policy_path(project="shop")
    assert saved.is_file() and saved.name == "chaos-policy.json"
    assert chaos.policy_path(str(path), "shop") == path


def test_health_baseline_survives_reload_without_probing_induced_outage(tmp_path):
    h = horde(tmp_path, {"health_check": [sys.executable, "-c", "pass"], "health_interval": 0})
    checks = []
    async def check(*args):
        checks.append(True)
        return 0, ""
    h.chaos.call_hook = check
    f = fault(h)
    assert admit(h, f) is None
    f["phase"] = "active"
    asyncio.run(h.chaos.refresh())
    assert admit(h, fault(h, human="h02")) is None
    assert len(checks) == 1
    h.journal_f.close()


def test_simulation_checks_shared_limits_without_taking_a_lease(tmp_path):
    h = horde(tmp_path, {"shared_state": "shared.db", "shared_key": "recipe", "max_active": 1}, dry_run=True)
    ledger = h.chaos.ledger
    assert ledger.claim("recipe", "other", "f1", "shop", "offline", h.chaos.policy) is None
    assert admit(h, fault(h)) == "shared-max-active"
    assert h.chaos.leases == {}
    h.journal_f.close()
