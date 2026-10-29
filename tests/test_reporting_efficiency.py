"""Evidence-preserving report, analysis and extraction regressions."""
import io
import json
import random
import re
import sqlite3
from contextlib import redirect_stdout
from copy import deepcopy

import pytest

from chaosfolk import engine
from chaosfolk.reporting import JournalSpool, write_reports
from chaosfolk.scoring import fault_pillar, score_report, severity


def embedded(path):
    text = path.read_text(encoding="utf-8")
    marker = re.search(r"\bconst\s+data\s*=\s*", text)
    encoded = text[marker.end():]
    assert encoded.startswith("JSON.parse(")
    return json.loads(json.JSONDecoder().raw_decode(encoded[len("JSON.parse("):])[0])


def action(n, human="h01", **changes):
    return {"type": "action", "h": human, "n": n, "t": n * 1000, "action": "click", "resultat": "ok",
            "args": {}, "url": f"http://localhost/{n}", "ecran": ["screen " * 1000],
            "cible": {"nom": "Save"}, "capture": f"captures/{human}-{n}.png", **changes}


def save_session(folder, events):
    (folder / "journal.jsonl").write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    engine.ecrire_json(folder / "personas.json", {"humains": [
        {"id": "h01", "nom": "A", "profil": "Careful", "appareil": "desktop"},
        {"id": "h02", "nom": "B", "appareil": "mobile"}]})
    engine.ecrire_json(folder / "config.json", {"url": "http://localhost/"})


def test_report_streams_all_evidence_and_keeps_anomaly_position_and_counts(tmp_path, monkeypatch):
    anomaly = {"type": "anomalie", "h": "h01", "genre": "console", "message": "Unexpected <value>\u2028", "t": 1500}
    events = [action(1), anomaly, action(2, pense="</script><script>bad()</script>\u2029"), dict(anomaly, t=3500),
              dict(anomaly, t=4500, induite=["p1"]), action(1, url="http://localhost/restarted")]
    save_session(tmp_path, events)
    engine.ecrire_json(tmp_path / "constats.json", {"constats": [{"id": "C1", "evenements": [{"h": "h01", "n": 1}]}]})
    monkeypatch.setattr(engine, "lire_journal", lambda *_a, **_k: pytest.fail("Whole-journal reads are forbidden"))
    assert engine.rapport(tmp_path, "fr") == 0
    english, french = embedded(tmp_path / "report-en.html"), embedded(tmp_path / "rapport-fr.html")
    assert english.pop("lang") == "en" and french.pop("lang") == "fr"
    assert english == french
    assert (tmp_path / "rapport.html").read_bytes() == (tmp_path / "rapport-fr.html").read_bytes()
    journal = english["journal"]
    assert len(journal) == 5
    assert journal[1]["t"] == 1500 and journal[1]["nombre"] == 2
    assert journal[3]["nombre"] == 1 and journal[3]["induite"] == ["p1"]
    assert journal[2]["pense"] == events[2]["pense"]
    assert journal[0]["capture"] == events[0]["capture"] and journal[0]["cible_nom"] == "Save"
    assert "ecran" not in journal[0] and "cible" not in journal[0]
    assert english["constats_infos"]["C1"]["url"] == "http://localhost/restarted"
    assert english["score"] == score_report(english)


@pytest.mark.parametrize("seed", range(12))
def test_disk_backed_score_matches_public_list_score_for_unsorted_journals(seed):
    rng = random.Random(seed)
    events = [action(n, human=rng.choice(["h01", "h02", "e0"]), t=rng.randrange(0, 10000),
                     action=rng.choice(["click", "flag", "done", "giveup", "look"]),
                     resultat=rng.choice(["ok", "echec"]), gravite=rng.choice(["blocking", "minor"])) for n in range(40)]
    events += [{"type": "panne-debut", "id": "p1", "h": None, "t": 1500},
               {"type": "panne-fin", "id": "p1", "t": rng.choice([1600, 4500])},
               {"type": "anomalie", "genre": "console", "message": "warning", "t": 50},
               {"type": "anomalie", "genre": "erreur-js", "message": "Error 123", "t": 20}]
    rng.shuffle(events)
    with JournalSpool(events) as spool:
        data = {"constats": {"constats": []}, "journal": list(spool)}
        assert score_report(data, journal_metrics=spool.scoring_metrics()) == score_report(data)


def test_analyze_preserves_notes_and_counts_without_loading_the_journal(tmp_path, monkeypatch):
    engine.charger_moteur()
    events = [action(1, resultat="echec", message="Missing target", humeur="confused", dit="Try again"),
              action(2, action="flag", gravite="blocking", args={"texte": "Save failed"}),
              action(3, action="done", args={"texte": "Reviewed"}),
              {"type": "erreur_commande", "h": "h01", "t": 3100},
              {"type": "boite", "h": "h01", "genre": "alert", "message": "Saved?", "t": 3200},
              {"type": "garde-fou", "h": "h02", "action": "goto", "args": {}, "message": "Outside scope", "refus": True, "t": 3300}]
    save_session(tmp_path, events)
    monkeypatch.setattr(engine, "lire_journal", lambda *_a, **_k: pytest.fail("Whole-journal reads are forbidden"))
    output = io.StringIO()
    with redirect_stdout(output):
        engine.analyser(tmp_path)
    text = output.getvalue()
    assert "2 humains, 3 actions" in text and "1 gestes ratés, humeur finale confused" in text
    assert 'signalement blocking n2 /2 : "Save failed"' in text
    assert 'bilan (n3) : "Reviewed"' in text and 'a dit : "Try again"' in text
    assert "raté n1 click : Missing target" in text
    assert "h02 goto {} : Outside scope" in text and 'h01 alert : "Saved?"' in text


def test_extraction_reads_once_for_multiple_users_and_keeps_fault_events_after_cutoff(tmp_path, monkeypatch):
    events = [{"type": "arrivee", "h": "h01", "url": "http://localhost/start", "t": 0},
              action(1), action(1, human="h02", t=1500),
              {"type": "panne-debut", "h": None, "id": "p1", "panne": "app-stop", "t": 1600},
              action(2), {"type": "panne-fin", "h": None, "id": "p1", "panne": "app-stop", "t": 3000}]
    save_session(tmp_path, events)
    original = engine.iterer_journal
    calls = []

    def read(folder, obligatoire=True):
        calls.append(folder)
        yield from original(folder, obligatoire)

    monkeypatch.setattr(engine, "iterer_journal", read)
    monkeypatch.setattr(engine, "lire_journal", lambda *_a, **_k: pytest.fail("Whole-journal reads are forbidden"))
    combined = engine.extraire_plusieurs(tmp_path, ["h01", "h02"])
    assert len(calls) == 1
    assert [step["session"] for step in combined["etapes"]] == ["h01", "h02", "h01"]
    shortened = engine.extraire(tmp_path, "h01", 1)
    assert len(shortened["etapes"]) == 1
    assert [event["type"] for event in shortened["fault_events"]] == ["panne-debut", "panne-fin"]
    assert shortened["pannes"][0]["debut_n"] == 1 and "fin_n" not in shortened["pannes"][0]


def test_incremental_renderer_keeps_existing_output_when_encoding_fails(tmp_path):
    target = tmp_path / "report-en.html"
    target.write_text("previous")
    data = {"journal": None, "invalid": object()}
    with pytest.raises(TypeError):
        write_reports(tmp_path, '<html lang="en"><script>const data=/*__DONNEES__*/null;</script>', data, [], "en")
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_extraction_resets_restarted_users_and_compares_old_tab_screens(tmp_path):
    events = [action(99), {"type": "arrivee", "h": "h01", "t": 10, "url": "http://localhost/new"},
              action(1, onglet="a", url="http://localhost/new"), action(2, onglet="a", url="http://localhost/new"),
              action(3, onglet="b", url="http://localhost/new")]
    original = deepcopy(events)
    save_session(tmp_path, events)
    result = engine.extraire(tmp_path, "h01")
    assert [step["n"] for step in result["etapes"]] == [1, 2, 3]
    assert [step["effet"] for step in result["etapes"]] == [True, False, True]
    assert result["depart"] == "http://localhost/new" and events == original


def legacy_fault_pillar(journal, by_user):
    """Compatibility oracle: the list/window implementation before streaming."""
    faults = {}
    for event in journal:
        if event.get("type") == "panne-debut" and event.get("id") is not None:
            faults[str(event["id"])] = {"h": event.get("h"), "start": event.get("t", 0), "end": None, "error": event.get("erreur")}
        elif event.get("type") == "panne-fin" and str(event.get("id")) in faults:
            faults[str(event["id"])]["end"] = event.get("t", 0)
    judged = []
    for fault in faults.values():
        if fault["error"]:
            continue
        start, end = fault["start"], fault["end"]
        instant = end is not None and end - start < 1000
        touched = []
        candidates = [fault["h"]] if fault["h"] else list(by_user)
        for user in candidates:
            actions = by_user.get(user, [])
            if not actions or actions[-1]["t"] < start or end is not None and actions[0]["t"] > end:
                continue
            after = [action for action in actions if action["t"] >= start]
            if not after:
                continue
            window = after[:10] if instant else after if end is None else [action for action in after if action["t"] <= end + 30000]
            bad = any(action.get("action") == "giveup" or action.get("action") == "flag" and severity(action.get("gravite")) == "blocking" for action in window)
            recovered = instant or end is None or any(action["t"] > end and action.get("resultat") == "ok" and action.get("action") not in ("flag", "giveup", "think", "look") for action in actions)
            recovered = recovered or (actions[-1].get("action") == "done" and actions[-1]["t"] > end)
            touched.append(not bad and recovered)
        if touched:
            judged.append(all(touched))
    return {"id": "faults", "value": 15 * sum(judged) / len(judged), "max": 15} if judged else None


@pytest.mark.parametrize("seed", range(24))
def test_streamed_fault_windows_match_the_original_algorithm(seed):
    rng = random.Random(seed)
    by_user = {human: sorted([action(n, human=human, t=rng.randrange(0, 70000),
                                    action=rng.choice(["click", "done", "giveup", "flag", "look"]),
                                    resultat=rng.choice(["ok", "echec"]), gravite=rng.choice(["blocking", "minor"]))
                             for n in range(rng.randrange(30))], key=lambda event: event["t"])
               for human in ["h01", "h02", "h03"]}
    events = []
    for number in range(5):
        start = rng.randrange(20000)
        events.append({"type": "panne-debut", "id": str(number), "t": start,
                       "h": rng.choice([None, "h01", "h02", "absent"]), "erreur": rng.choice([None, None, "failed"])})
        duration = rng.choice([None, 100, 999, 1000, 2000, 40000])
        if duration is not None:
            events.append({"type": "panne-fin", "id": str(number), "t": start + duration})
    events.sort(key=lambda event: event["t"])
    assert fault_pillar(events, by_user) == legacy_fault_pillar(events, by_user)


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt, GeneratorExit])
def test_spool_closes_database_if_input_iteration_fails(monkeypatch, failure):
    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        return connection

    def interrupted():
        yield action(1)
        raise failure("source interrupted")

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(failure):
        JournalSpool(interrupted())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


def test_report_validation_failure_closes_its_database(tmp_path, monkeypatch):
    save_session(tmp_path, [action(1)])
    engine.ecrire_json(tmp_path / "coverage.json", [])
    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        connection = original(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(ValueError, match="coverage.json"):
        engine.rapport(tmp_path)
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connections[0].execute("SELECT 1")


def test_cancelling_an_event_iterator_releases_its_cursor():
    with JournalSpool([action(1), action(2)]) as spool:
        iterator = spool.events()
        assert next(iterator)["n"] == 1
        iterator.close()
        assert len(list(spool)) == 2
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        spool.db.execute("SELECT 1")
