import json

import pytest

from chaosfolk import campaigns, engine
from chaosfolk.draw import tirer_horde


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "state" / "active.json")
    return tmp_path


def session(folder, findings, verdict="reproduit"):
    folder.mkdir(parents=True)
    (folder / "scenarios").mkdir()
    (folder / "reproductions").mkdir()
    events = [{"type": "action", "h": "h01", "n": 1, "t": 1, "action": "goto", "url": "http://localhost:3000/orders/42?tab=2", "resultat": "ok"},
              {"type": "action", "h": "h01", "n": 2, "t": 2, "action": "click", "url": "http://localhost:3000/orders/42/edit",
               "cible": {"nom": "Modifier"}, "resultat": "echec"}]
    (folder / "journal.jsonl").write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    scenario = folder / "scenarios" / "save.json"
    scenario.write_text(json.dumps({"url": "http://localhost:3000/orders/42", "etapes": [
        {"n": 1, "action": "goto", "args": {"url": "http://localhost:3000/orders/42"}}],
        "attendu": [{"type": "text-visible", "texte": "Saved"}]}), encoding="utf-8")
    (folder / "reproductions" / "save.json").write_text(json.dumps({"scenario": scenario.as_posix(), "mode": "traitement",
        "fois": 3, "demandes": 3, "casses": 3, "verdict": verdict}), encoding="utf-8")
    (folder / "config.json").write_text(json.dumps({"url": "http://localhost:3000/", "projet": "shop-front"}), encoding="utf-8")
    (folder / "fields.json").write_text(json.dumps({"pages": [{"url": "http://localhost:3000/orders/42",
        "links": ["/settings", "/orders/7"], "kinds": [], "features": []}]}), encoding="utf-8")
    (folder / "constats.json").write_text(json.dumps({"constats": [dict(f, evenements=[{"h": "h01", "n": 1}],
        preuves={"avant": "reproductions/save.json"}) for f in findings]}), encoding="utf-8")


def test_routes_are_templates_and_the_map_lists_unvisited_links(tmp_path):
    assert campaigns.route("http://x/orders/42?tab=2&q=a") == "/orders/:id?q&tab"
    assert campaigns.route("http://x/users/3f2a9c4e-1b2c-4d5e-8f90-1234567890ab") == "/users/:id"
    session(tmp_path / "run", [])
    data = campaigns.journey_map(tmp_path / "run")
    assert data["routes"]["/orders/:id?tab"]["visits"] == 1
    assert data["edges"]["/orders/:id?tab -> /orders/:id/edit"]["via"] == ["Modifier"]
    assert set(campaigns.unexplored(data)[:2]) == {"/settings", "/orders/:id"}


def test_campaigns_are_keyed_by_project_and_compare_findings(state, capsys):
    finding = {"id": "CF-001", "titre": "[double-submit] Order saved twice", "gravite": "bloquant", "statut": "reproduit"}
    other = {"id": "CF-002", "titre": "Label missing", "gravite": "mineur"}
    session(state / "run1", [finding, other])
    session(state / "run2", [dict(finding, titre="[double-submit] order saved twice!")])
    args = lambda folder, label: type("A", (), {"dossier": str(state / folder), "project": None, "label": label, "repo": None})()
    assert campaigns.command_record(args("run1", "c1")) == 0
    assert campaigns.command_record(args("run2", "c2")) == 0
    with pytest.raises(ValueError, match="already recorded"):
        campaigns.command_record(args("run2", "c2"))
    registry = campaigns.read(campaigns.project_dir("shop-front") / "findings.json", {})
    same = [item for item in registry.values() if item["seen"] == 2]
    assert len(registry) == 2 and len(same) == 1 and same[0]["scenario"].endswith(".json")
    capsys.readouterr()
    campaigns.command_compare(type("A", (), {"project": "shop-front", "before": None, "after": None})())
    out = capsys.readouterr().out
    assert "New: 0" in out and "Still present: 1" in out and "Not seen again: 1" in out
    chosen = campaigns.selection(registry, 5)
    assert chosen[0][1]["severity"] == "bloquant"
    with pytest.raises(ValueError):
        campaigns.project_name("../other")


def test_rebase_moves_a_scenario_to_the_new_port_only():
    scenario = {"url": "http://localhost:3000/a", "depart": "http://localhost:3000/b", "etapes": [
        {"action": "goto", "args": {"url": "http://localhost:3000/c"}}, {"action": "goto", "args": {"url": "https://example.com/"}}]}
    moved = campaigns.rebase(scenario, "http://127.0.0.1:5173/")
    assert moved["url"] == "http://127.0.0.1:5173/a" and moved["depart"] == "http://127.0.0.1:5173/b"
    assert [s["args"]["url"] for s in moved["etapes"]] == ["http://127.0.0.1:5173/c", "https://example.com/"]


def test_draw_isolates_or_coordinates_users_and_assigns_roles():
    independent, plan = tirer_horde("ux", 2, ["Edit a project"], 3, {}, roles=[("editor", "etats/editor.json"), ("reader", None)])
    first, second = independent["humains"]
    assert "add H01" in first["intention"] and first["role"] == "editor" and first["etat"] == "etats/editor.json"
    assert second["role"] == "reader" and "etat" not in second
    assert plan["sessions"] == {"mode": "independent", "shared": [], "roles": ["editor", "reader"]}
    shared, plan = tirer_horde("ux", 2, ["Edit a project"], 3, {}, sessions="coordinated", shared=["Projet Alpha"])
    assert all("Projet Alpha" in user["intention"] for user in shared["humains"])
    assert "concurrent-edit-two-users" in plan["checks"]["pool"]
    explored, _ = tirer_horde("ux", 2, ["Edit"], 3, {}, explore=["/a", "/b", "/c", "/d", "/e", "/f"])
    assert "/a, /b, /c" in explored["humains"][0]["intention"] and "/d, /e, /f" in explored["humains"][1]["intention"]


def test_persistence_recipes_and_field_value_assertions_are_validated():
    assert engine.recettes_demandees("reload,retry") == ["reload", "retry"]
    assert engine.recettes_demandees("all") == list(engine.RECETTES)
    with pytest.raises(ValueError, match="Unknown --persist"):
        engine.recettes_demandees("reboot")
    assert engine.valider_attendu([{"type": "field-value", "field": "Titre", "value": "x"}])[0]["champ"] == "Titre"
    with pytest.raises(ValueError, match="field-value needs"):
        engine.valider_attendu([{"type": "field-value", "field": "Titre"}])
