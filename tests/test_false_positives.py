"""False-positive regressions: repeatable behavior is not necessarily a defect."""
from copy import deepcopy

import pytest
from playwright.sync_api import sync_playwright

from chaosfolk.audit import AUDIT_JS, TARGET_MIN, UNREACHED_JS
from chaosfolk.scoring import finding_info, score_report


def series(failed=3, mode="traitement"):
    return {"fois": 3, "demandes": 3, "casses": failed, "mode": mode}


def candidate(**overrides):
    return {"id": "C1", "gravite": "bloquant", "statut": "reproduit",
            "preuves": {"avant": series()}, **overrides}


@pytest.mark.parametrize("overrides,state", [
    ({}, "pending"),
    ({"qualification": "defect"}, "pending"),
    ({"qualification": "defect", "expected_basis": "  "}, "pending"),
    ({"qualification": "defect", "expected_basis": ["invented"]}, "pending"),
    ({"qualification": "product-decision"}, "decision"),
    ({"qualification": "suggestion"}, "suggestion"),
    ({"statut": "à décider"}, "decision"),
    ({"statut": "écarté"}, "excluded"),
    ({"statut": "non reproduit"}, "excluded"),
    ({"preuves": {"avant": series(0)}}, "pending"),
])
def test_unsupported_or_intentional_behavior_is_not_a_scored_defect(overrides, state):
    finding = candidate(**overrides)
    original = deepcopy(finding)
    info = finding_info(finding)
    assert info["stage"] == state
    result = score_report({"constats": {"constats": [finding]}})
    assert result["penalty"] == 0
    assert result["cap"]["value"] == 100
    assert "after_fix" not in result
    assert finding == original


def test_reproduction_and_qualification_are_independent():
    finding = candidate()
    assert finding_info(finding)["evidence"] == "proven"
    assert finding_info(finding)["stage"] == "pending"
    finding.update(qualification="defect", expected_basis="The save requirement preserves a failed draft.")
    assert finding_info(finding)["stage"] == "proven"
    assert finding_info(finding)["factor"] == 1
    finding["qualification"] = "product-decision"
    assert finding_info(finding)["evidence"] == "proven"
    assert finding_info(finding)["factor"] == 0


def test_passing_replays_are_not_reproduced_and_declarations_do_not_invent_intermittence():
    finding = candidate(qualification="defect", expected_basis="Documented persistence requirement.",
                        statut="intermittent", preuves={"avant": series(0)})
    assert finding_info(finding)["evidence"] == "not-reproduced"
    assert finding_info(finding)["factor"] == 0
    finding["preuves"]["avant"] = series(1)
    assert finding_info(finding)["factor"] == .6
    finding["condition"] = "offline"
    assert finding_info(finding)["factor"] == 0
    finding["preuves"]["temoin"] = series(0, "temoin")
    assert finding_info(finding)["factor"] == .6


@pytest.mark.parametrize("trials", [
    [{"ok": False}, {"ok": None}, {"ok": False}],
    [{"ok": False}, {"ok": False}],
    [{"ok": False}, {"ok": True}, {"ok": False}],
    [{"ok": False, "divergence": {"etape": 1}}] * 3,
])
def test_contradictory_trial_details_cannot_establish_a_defect(tmp_path, trials):
    from chaosfolk import engine
    finding = candidate(qualification="defect", expected_basis="Documented save contract.")
    finding["preuves"]["avant"]["essais"] = trials
    assert finding_info(finding)["factor"] == 0
    engine.ecrire_json(tmp_path / "proof.json", finding["preuves"]["avant"])
    finding["preuves"]["avant"] = engine.preuve_resolue(tmp_path, "proof.json")
    assert finding["preuves"]["avant"]["trial_integrity"] is False
    assert finding_info(finding)["factor"] == 0


@pytest.mark.browser
def test_audit_excludes_inert_navigation_but_keeps_actual_hidden_focus_targets():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content('''<html lang="en"><title>Navigation</title><body>
                <nav inert aria-hidden="true"><button id="inert-button">Menu</button></nav>
                <div aria-hidden="true"><button id="hidden-focus">Unsafe hidden control</button></div>
                <fieldset disabled><button id="disabled-button">Disabled</button></fieldset>
                <div role="tablist"><button role="tab" tabindex="-1" id="arrow-tab">Arrow tab</button></div>
                <button id="real-button">Continue</button></body></html>''')
            result = page.evaluate(AUDIT_JS, TARGET_MIN)
            assert [el["element"] for el in result["aria_hidden_focusable"]] == ["button#hidden-focus"]
            unreached = page.evaluate(UNREACHED_JS)
            assert not any("inert-button" in el or "arrow-tab" in el or "disabled-button" in el for el in unreached)
            assert any("real-button" in el for el in unreached)
        finally:
            browser.close()


@pytest.mark.browser
def test_audit_requires_full_obstruction_and_correct_small_target_spacing():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content('''<html lang="en"><title>Controls</title><body>
                <button id="partial" style="position:absolute;left:20px;top:20px;width:100px;height:40px">Partial</button>
                <div style="position:absolute;left:65px;top:35px;width:10px;height:10px;z-index:3"></div>
                <button id="covered" style="position:absolute;left:220px;top:20px;width:100px;height:40px">Covered</button>
                <div style="position:absolute;left:220px;top:20px;width:100px;height:40px;z-index:3"></div>
                <button id="spaced-a" style="position:absolute;left:20px;top:150px;width:20px;height:20px;padding:0">A</button>
                <button id="spaced-b" style="position:absolute;left:46px;top:150px;width:20px;height:20px;padding:0">B</button>
                <button id="crowded-a" style="position:absolute;left:200px;top:150px;width:20px;height:20px;padding:0">C</button>
                <button id="crowded-b" style="position:absolute;left:221px;top:150px;width:20px;height:20px;padding:0">D</button>
                <button id="narrow" style="position:absolute;left:20px;top:250px;width:16px;height:16px;padding:0">E</button>
                <button id="wide-short" style="position:absolute;left:36px;top:250px;width:100px;height:20px;padding:0">Wide short target</button>
                </body></html>''')
            result = page.evaluate(AUDIT_JS, TARGET_MIN)
            assert [el["element"] for el in result["covered_controls"]] == ["button#covered"]
            assert {el["element"] for el in result["small_targets"]} == {
                "button#crowded-a", "button#crowded-b", "button#narrow"}
        finally:
            browser.close()
