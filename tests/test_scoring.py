from copy import deepcopy
import math

import pytest

from chaosfolk.scoring import score_report, finding_info


def proof(failed=3, mode="traitement", count=3, requested=3):
    return {"fois": count, "demandes": requested, "casses": failed, "mode": mode}


def finding(severity="blocking", **extra):
    return {"id": "C1", "gravite": severity, "statut": "reproduit", "qualification": "defect",
            "expected_basis": "Documented save contract: retain a draft when saving fails.",
            "preuves": {"avant": proof()}, **extra}


def report(*findings, journal=None, properties=None):
    return {"constats": {"constats": list(findings), "proprietes": properties or []}, "journal": journal or []}


@pytest.mark.parametrize("severity,penalty,cap", [("blocking", 10, 59), ("annoying", 4, 89), ("minor", 1, 100)])
def test_original_severity_weights_exponential_formula_and_caps(severity, penalty, cap):
    data = report(finding(severity), journal=[{"type": "action", "h": "h01", "t": 0, "action": "done"}])
    score = score_report(data)
    expected_raw = 100 * (50 * math.exp(-penalty / 30) + 15) / 65
    assert score["penalty"] == penalty
    assert score["raw"] == pytest.approx(expected_raw)
    assert score["cap"]["value"] == cap
    assert score["note"] == math.floor(min(expected_raw, cap) + 0.5)


@pytest.mark.parametrize("status,proofs,expected", [
    ("observed", {}, 0), ("intermittent", {}, 0), ("à décider", {}, 0), ("écarté", {}, 0),
    ("réparé", {"avant": proof(), "apres": proof(0)}, 0.3),
    ("réparé", {"avant": proof(), "apres": proof(0), "demontee": proof()}, 0.15),
    ("réparé", {"apres": proof(0), "demontee": proof()}, 0),
])
def test_evidence_factors_and_declared_fix_cannot_invent_baseline(status, proofs, expected):
    info = finding_info(finding(statut=status, preuves=proofs))
    assert info["factor"] == expected


@pytest.mark.parametrize("invalid", [proof(count=3, requested=5), proof(mode="temoin"),
                                    proof(count=True, requested=True, failed=True), {"fois": 3, "casses": 3}])
def test_wrong_mode_or_incomplete_trials_never_establish_reproduction(invalid):
    result = score_report(report(finding(preuves={"avant": invalid})))
    assert result["penalty"] == 0
    assert result["cap"]["value"] == 100


def test_condition_needs_complete_control_and_fix_removal():
    f = finding(statut="fixed", condition="offline", preuves={"avant": proof(), "apres": proof(0), "demontee": proof()})
    assert finding_info(f)["repair"] is None
    f["preuves"]["temoin"] = proof(0, "temoin")
    assert finding_info(f)["repair"] == "complete"
    score = score_report(report(f))
    assert score["penalty"] == 1.5
    assert score["cap"] == {"value": 74, "ids": ["C1"], "reason": "open-blocker"}


def test_empty_report_has_no_score_and_is_provisional():
    score = score_report(report())
    assert score["note"] is score["raw"] is score["level"] is None
    assert score["provisional"]
    assert score["pillars"] == []


def test_unreviewed_flags_do_not_count_as_defects():
    score = score_report({"journal": [{"type": "action", "h": "h01", "action": "flag", "gravite": "blocking"}]})
    assert score["provisional"]
    assert score["penalty"] == 0


def test_property_pillar_is_optional_and_fixed_receives_partial_credit():
    data = report(properties=[{"statut": "tenue"}, {"statut": "réparée"}, {"statut": "cassée"}, {"statut": "non testée"}])
    score = score_report(data)
    properties = next(p for p in score["pillars"] if p["id"] == "properties")
    assert properties["value"] == pytest.approx(20 * 1.8 / 3)
    assert properties["max"] == 20
    assert score["note"] is not None


def test_console_penalty_groups_duplicates_and_excludes_injected_errors():
    journal = [{"type": "action", "h": "h01", "action": "done"}]
    journal += [{"type": "anomalie", "genre": "erreur-js", "message": "Error 123"},
                {"type": "anomalie", "genre": "erreur-js", "message": "Error 456"},
                {"type": "anomalie", "genre": "console", "message": "[vite] reconnecting"},
                {"type": "anomalie", "genre": "crash", "message": "Injected", "induite": ["fault"]}]
    score = score_report(report(journal=journal))
    journeys = next(p for p in score["pillars"] if p["id"] == "journeys")
    assert journeys["value"] == pytest.approx(10 + 5 * math.exp(-2 / 4))


@pytest.mark.parametrize("last_action,expected", [("done", 15), ("giveup", 0)])
def test_fault_resilience_uses_observed_recovery(last_action, expected):
    journal = [{"type": "action", "h": "h01", "action": "click", "resultat": "ok", "t": 0},
               {"type": "panne-debut", "id": "f1", "h": "h01", "panne": "offline", "t": 100},
               {"type": "action", "h": "h01", "action": "look", "t": 150},
               {"type": "panne-fin", "id": "f1", "t": 1500},
               {"type": "action", "h": "h01", "action": last_action, "resultat": "ok", "t": 1600}]
    score = score_report(report(journal=journal))
    assert next(p["value"] for p in score["pillars"] if p["id"] == "faults") == expected


def test_projection_is_explicit_and_does_not_fabricate_or_mutate_evidence():
    data = report(finding())
    original = deepcopy(data)
    score = score_report(data)
    assert score["after_fix"]["projected"] is True
    assert score["after_fix"]["cap"]["value"] == 74
    assert score["after_fix"]["raw"] > score["raw"]
    assert data == original


def test_scout_events_cannot_inflate_mission_success():
    data = report(journal=[{"type": "action", "h": "e0", "action": "done", "t": 0}])
    assert score_report(data)["note"] is None


def test_lifecycle_events_without_tests_do_not_create_a_score():
    data = report(journal=[{"type": "debut", "t": 0}, {"type": "fin-horde", "t": 1}])
    assert score_report(data)["note"] is None
