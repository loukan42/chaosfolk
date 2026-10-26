import argparse
import json
from pathlib import Path
import re

import pytest

from chaosfolk import engine
from chaosfolk.draw import tirer_horde
from chaosfolk.schema import normalize_scenario


def scenario(**extra):
    return {"url": "http://127.0.0.1:3000/", "steps": [], "expect": {"type": "page-not-blank"}, **extra}


def test_seed_reproduces_profiles_and_faults():
    args = ("ux", 100, ["Create a project", "Find a project"], 42, {"nom": "Demo"})
    first = tirer_horde(*args)
    assert first == tirer_horde(*args)
    assert len({p["id"] for p in first[0]["humains"]}) == 100
    assert len({p["nom"] for p in first[0]["humains"]}) == 100
    assert first != tirer_horde("ux", 100, args[2], 43, args[4])
    assert all(f["humains"] in {p["id"] for p in first[0]["humains"]} for f in first[1]["pannes"])
    assert {p["skin"] for p in first[0]["humains"]} == set(range(16))
    assert len({p["profil_id"] for p in first[0]["humains"]}) == 16


def test_every_persona_can_explore_all_goals_without_one_agent_per_use_case():
    goals = ["Create a project", "Find a project", "Edit a project", "Cancel an edit"]
    personas, plan = tirer_horde("ux", 4, goals, 42, {"nom": "Demo"}, budget=20)
    assert len(personas["humains"]) == 4
    assert plan["budget"] == 20
    assert len({tuple(p["objectifs"]) for p in personas["humains"]}) > 1
    for persona in personas["humains"]:
        assert sorted(persona["objectifs"]) == sorted(goals)
        assert all(goal in persona["intention"] for goal in goals)
        assert "20 actions" in persona["intention"]
        assert "does not guarantee" in persona["intention"]
    assert engine.construire_parseur().parse_args(["draw", "--objectives", ";".join(goals), "--folder", "unused"]).nombre == 4


@pytest.mark.parametrize("budget", [1, 2, 5, 20, 40])
def test_faults_are_reachable_within_the_selected_budget(budget):
    for seed in range(5):
        args = ("ux", 100, ["Create a project"], seed, {"nom": "Demo"})
        first = tirer_horde(*args, budget=budget)
        assert first == tirer_horde(*args, budget=budget)
        assert first[0]["budget"] == first[1]["budget"] == budget
        assert first[1]["pannes"]
        assert all(0 <= fault["apres_actions"] < budget for fault in first[1]["pannes"])
        if budget == 1:
            assert {fault["apres_actions"] for fault in first[1]["pannes"]} == {0}


@pytest.mark.parametrize("budget", [0, -1, True, 1.5, 10001])
def test_draw_rejects_invalid_budgets(budget):
    with pytest.raises(ValueError):
        tirer_horde("ux", 4, ["Create a project"], 42, {}, budget=budget)


def test_draw_cli_records_selected_budget(tmp_path):
    assert engine.principal(["draw", "--count", "4", "--seed", "42", "--objectives", "Create a project",
                             "--budget", "1", "--folder", str(tmp_path)]) == 0
    plan = json.loads((tmp_path / "tirage.json").read_text(encoding="utf-8"))
    assert plan["budget"] == 1
    assert all(fault["apres_actions"] == 0 for fault in plan["pannes"])


@pytest.mark.parametrize("count", [0, -1, 101, 1.5, True])
def test_invalid_counts_do_not_generate_profiles(count):
    with pytest.raises(ValueError):
        tirer_horde("ux", count, ["Create a project"], 42, {})


@pytest.mark.parametrize("goals", [[], "goal", [None], [" "]])
def test_invalid_goals_fail_without_writing(goals):
    with pytest.raises(ValueError):
        tirer_horde("ux", 4, goals, 42, {})


def test_public_schema_does_not_rewrite_user_content_or_mutate_input():
    source = scenario(steps=[{"action": "type", "target": {"role": "textbox", "name": "Name"},
                              "args": {"text": "steps: keep this text unchanged", "enter": True}}],
                      expect={"type": "text-visible", "text": "Saved"})
    original = json.dumps(source)
    normalized = normalize_scenario(source)
    assert json.dumps(source) == original
    assert normalized["etapes"][0]["args"] == {"texte": "steps: keep this text unchanged", "entree": True}
    assert normalized["etapes"][0]["cible"]["nom"] == "Name"
    assert normalized["attendu"] == [{"type": "text-visible", "texte": "Saved"}]
    assert normalize_scenario(normalized) == normalized


@pytest.mark.parametrize("update", [
    {"url": "file:///etc/passwd"}, {"url": "javascript:alert(1)"}, {"url": "http:///"},
    {"steps": [{"action": "invented"}]}, {"steps": [None]}, {"steps": "click"},
    {"steps": [{"action": "done"}]}, {"steps": [{"action": "click", "args": {"ref": "r1"}}]},
    {"steps": [{"action": "type", "target": {"role": "textbox", "name": "Name"}, "args": {}}]},
    {"expect": "anything"}, {"faults": [{"type": "invented"}]},
    {"faults": [{"type": "offline", "start_action": -1}]},
    {"faults": [{"type": "offline", "start_action": 3, "end_action": 1}]},
    {"etapes": [{"action": "reload"}]},
])
def test_malformed_scenarios_are_rejected_before_browser_launch(update):
    with pytest.raises(ValueError):
        normalize_scenario(scenario(**update))


@pytest.mark.parametrize("rule", [
    {"type": "unknown"}, {"type": "count", "text": "Saved"},
    {"type": "count", "text": "Saved", "equals": True},
    {"type": "count", "text": "Saved", "equals": 1.5},
    {"type": "count", "text": "Saved", "equals": -1},
    {"type": "count", "text": "Saved", "min": 3, "max": 2},
    {"type": "text-visible", "text": ""}, None,
])
def test_invalid_assertions_never_become_success(rule):
    with pytest.raises(ValueError):
        engine.valider_attendu([rule])


def test_english_assertion_and_legacy_alias_are_equivalent():
    assert engine.valider_attendu({"type": "count", "text": "Saved", "equals": 1}) == engine.valider_attendu(
        {"type": "compte", "texte": "Saved", "egal": 1})


@pytest.mark.parametrize("identifier", ["../escape", "h/1", "h\\1", "", "h" * 65, 12, "CON", "nul", "COM1", "LPT9"])
def test_persona_ids_cannot_escape_sheet_or_screenshot_directories(identifier):
    with pytest.raises(ValueError):
        engine.validate_id(identifier)


def test_uploads_are_confined_to_fixture_directory(tmp_path):
    upload = tmp_path / "uploads" / "fixture.txt"
    upload.parent.mkdir()
    upload.write_text("synthetic", encoding="utf-8")
    secret = tmp_path / "session.json"
    secret.write_text("private", encoding="utf-8")
    assert engine.fichier_televersable("uploads/fixture.txt", tmp_path) == upload
    for path in ("session.json", "uploads/../session.json", "../outside.txt", "uploads/missing.txt"):
        with pytest.raises(ValueError):
            engine.fichier_televersable(path, tmp_path)


def test_path_confinement_follows_symlinks(tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.txt")
    outside.write_text("private", encoding="utf-8")
    upload = tmp_path / "uploads"
    upload.mkdir()
    try:
        (upload / "link.txt").symlink_to(outside)
    except OSError:
        pytest.skip("OS does not permit symlinks for this account")
    with pytest.raises(ValueError):
        engine.fichier_televersable("uploads/link.txt", tmp_path)


def test_incomplete_trials_do_not_claim_reproduction():
    assert engine.verdict_rejeu(2, 2, 3, False) != "reproduit"
    assert engine.verdict_rejeu(0, 0, 3, False) != "reproduit"
    assert engine.verdict_rejeu(3, 3, 3, False) == "reproduit"
    assert engine.verdict_rejeu(0, 3, 3, True) == "témoin propre"
    assert engine.verdict_rejeu(1, 3, 3, True) != "témoin propre"


def test_invalid_action_exit_status_propagates_to_the_cli(monkeypatch):
    monkeypatch.setattr(engine, "envoyer", lambda *_args, **_kwargs: {"ok": False, "texte": "Rejected"})
    assert engine.commande_humain(["h01", "look"]) == 1


@pytest.mark.parametrize("args", [
    ["replay", "scenario.json", "--times", "0"],
    ["launch", "--url", "http://localhost:3000", "--budget", "-1"],
    ["launch", "--url", "http://localhost:3000", "--max-duration", "0"],
])
def test_invalid_execution_budgets_fail_at_argument_parsing(args):
    with pytest.raises(SystemExit) as result:
        engine.construire_parseur().parse_args(args)
    assert result.value.code == 2


def test_report_escapes_script_terminators(tmp_path):
    payload = "</script><script>globalThis.injection=1</script>"
    engine.ecrire_json(tmp_path / "personas.json", {"humains": []})
    engine.ecrire_json(tmp_path / "constats.json", {"titre": payload, "constats": []})
    (tmp_path / "journal.jsonl").write_text("", encoding="utf-8")
    assert engine.rapport(tmp_path) == 0
    report = (tmp_path / "rapport.html").read_text(encoding="utf-8")
    assert payload not in report
    assert "\\u003c/script>" in report


def test_sheet_keeps_fault_and_leader_token_out(tmp_path, monkeypatch):
    personas, _ = tirer_horde("ux", 1, ["Create a project"], 42, {"nom": "Demo"})
    personas["humains"][0]["condition"] = "secret-planned-fault"
    monkeypatch.setenv("CHAOSFOLK_LEADER_TOKEN", "secret-leader-token")
    engine.ecrire_json(tmp_path / "personas.json", personas)
    opts = argparse.Namespace(dossier=str(tmp_path), donnees="Fake names", interdits="External actions", budget=20)
    assert engine.commande_fiches(opts) == 0
    sheet = (tmp_path / "fiches/h01.md").read_text(encoding="utf-8")
    assert "secret-planned-fault" not in sheet
    assert "secret-leader-token" not in sheet
    assert "Create a project" in sheet
    assert "20" in sheet


def test_trace_reader_keeps_valid_lines_after_truncation(tmp_path):
    (tmp_path / "journal.jsonl").write_bytes(b'{"type":"action","action":"cliquer"}\n{"broken":\n{"type":"action","action":"reload"}\n')
    events = engine.lire_journal(tmp_path)
    assert [event["action"] for event in events] == ["click", "reload"]


def test_agent_install_preserves_custom_definition_unless_forced(tmp_path, monkeypatch):
    source, target = tmp_path / "source.md", tmp_path / "agent.md"
    source.write_text("new agent", encoding="utf-8")
    target.write_text("custom agent", encoding="utf-8")
    monkeypatch.setattr(engine, "agent_installe", lambda: (source, target, "different"))
    assert engine.commande_installer_agent(argparse.Namespace(force=False)) == 1
    assert target.read_text() == "custom agent"
    assert engine.commande_installer_agent(argparse.Namespace(force=True)) == 0
    assert target.read_text() == "new agent"
    backups = list(tmp_path.glob("agent.md.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == "custom agent"


def test_report_keeps_requested_trial_count(tmp_path):
    engine.ecrire_json(tmp_path / "proof.json", {"nom": "proof", "mode": "traitement", "fois": 3,
                                                "demandes": 5, "casses": 3, "essais": []})
    proof = engine.preuve_resolue(tmp_path, "proof.json")
    assert proof["demandes"] == 5
    assert proof["mode"] == "traitement"


def embedded_report_data(path):
    html = path.read_text(encoding="utf-8")
    assignment = re.search(r"\bconst\s+data\s*=\s*", html)
    assert assignment, "Report has no embedded evidence assignment"
    return json.JSONDecoder().raw_decode(html[assignment.end():])[0]


@pytest.mark.parametrize("language", ["en", "fr"])
def test_report_languages_share_exact_evidence_and_keep_recorded_text(tmp_path, language):
    original_event = {"type": "action", "h": "h01", "n": 1, "action": "click", "dit": "Mon brouillon a disparu",
                      "resultat": "echec", "args": {}, "t": 1000}
    (tmp_path / "journal.jsonl").write_text(json.dumps(original_event) + "\n", encoding="utf-8")
    engine.ecrire_json(tmp_path / "personas.json", {"humains": [{"id": "h01", "nom": "Alex"}]})
    engine.ecrire_json(tmp_path / "reproductions/before.json", {"nom": "before", "mode": "traitement", "fois": 3,
        "demandes": 3, "casses": 3, "verdict": "reproduit", "essais": [{"capture": None, "raisons": ["Draft lost"]}] * 3})
    findings = {"titre": "A draft disappears", "constats": [{"id": "C1", "titre": "Draft lost", "preuves": {"avant": "reproductions/before.json"}}],
                "translations": {"fr": {"titre": "Un brouillon disparaît", "constats": {"C1": {"titre": "Brouillon perdu"}}}}}
    engine.ecrire_json(tmp_path / "constats.json", findings)
    original_proof = (tmp_path / "reproductions/before.json").read_bytes()
    assert engine.principal(["report", "--folder", str(tmp_path), "--lang", language]) == 0
    english = embedded_report_data(tmp_path / "report-en.html")
    french = embedded_report_data(tmp_path / "rapport-fr.html")
    selected = embedded_report_data(tmp_path / "rapport.html")
    assert selected == (english if language == "en" else french)
    assert english.pop("lang") == "en"
    assert french.pop("lang") == "fr"
    assert english == french
    assert french["journal"][0]["dit"] == "Mon brouillon a disparu"
    assert french["constats"]["translations"] == findings["translations"]
    proof = french["constats"]["constats"][0]["preuves"]["avant"]
    assert (proof["fois"], proof["demandes"], proof["casses"], proof["mode"]) == (3, 3, 3, "traitement")
    assert (tmp_path / "reproductions/before.json").read_bytes() == original_proof


def test_unsupported_report_language_is_rejected_before_output(tmp_path):
    with pytest.raises(ValueError, match="language"):
        engine.rapport(tmp_path, "xx")
    assert not list(tmp_path.iterdir())


def test_posix_sheet_command_quotes_paths(tmp_path, monkeypatch):
    import shlex
    executable = tmp_path / "Python's directory" / "python"
    monkeypatch.setattr(engine.sys, "executable", str(executable))
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "State's directory" / "active.json")
    words = shlex.split(engine.sheet_command("posix"))
    assert words == [executable.as_posix(), "-m", "chaosfolk", "--state-dir", (tmp_path / "State's directory").as_posix()]
