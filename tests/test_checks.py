import json
import re
from datetime import date

import pytest

from chaosfolk import checks, engine, qa
from chaosfolk.draw import tirer_horde
from chaosfolk.themes import THEMES


CATALOG = checks.load()


def test_catalog_entries_are_complete_and_consistent():
    kinds = {kind["id"] for kind in CATALOG["kinds"]} | {"text"}  # "text": a field with no specific signal
    ids = [check["id"] for check in CATALOG["checks"]]
    assert len(ids) == len(set(ids))
    for check in CATALOG["checks"]:
        assert check["theme"] in THEMES, check["id"]
        assert check["scope"] in CATALOG["scopes"], check["id"]
        assert check["title"] and check["try"] and check["expect"] and check["proof"], check["id"]
        assert set(check["applies"].get("kinds", [])) <= kinds, check["id"]
        assert set(check["applies"].get("features", [])) <= set(CATALOG["features"]), check["id"]
        for name in ("valid", "invalid"):
            values = checks.candidates(check, name)
            assert all(isinstance(value, str) for value, _ in values), check["id"]
            assert all("{{repeat" not in checks.expand(value) for value, _ in values)
            assert {country for _, country in values if country} <= set(CATALOG["countries"]), check["id"]
        assert set(check.get("wcag", [])) <= {f"{a}.{b}.{c}" for a in range(1, 5) for b in range(1, 14) for c in range(1, 14)}


def test_country_dependent_checks_never_rely_on_one_country():
    for check in CATALOG["checks"]:
        if check.get("by_country"):
            assert len(check["by_country"]) >= 4, check["id"]
            assert "country" in check["expect"] or "locale" in check["expect"], check["id"]
    phone = [value for value, _, country in checks.values("phone-formats", selected=["GB"])]
    assert "07700 900123" in phone and "06 39 98 12 34" not in phone and "+33 6 39 98 12 34" in phone
    with pytest.raises(ValueError, match="Unknown countries"):
        checks.countries("FR,XX")


def test_value_macros_expand_without_touching_template_markers():
    today = date(2026, 1, 31)
    assert checks.expand("{{repeat:ab:3}}") == "ababab"
    assert checks.expand("{{date:+1}}", today=today) == "01/02/2026"
    assert checks.expand("nobody-{{seed}}@example.com", seed=42) == "nobody-42@example.com"
    assert checks.expand("{{7*7}}") == "{{7*7}}"
    assert checks.show(checks.expand("{{repeat:a:120}}", repeat=False)) == '"a" repeated 120 times'


@pytest.mark.parametrize("field, kind", [
    ({"tag": "input", "label": "Prénom", "name": "firstName"}, "first-name"),
    ({"tag": "input", "label": "Nom", "name": "lastName"}, "last-name"),
    ({"tag": "input", "label": "Nom complet"}, "full-name"),
    ({"tag": "input", "label": "Prénom et nom"}, "full-name"),
    ({"tag": "input", "type": "number", "label": "Code postal"}, "postal-code"),
    ({"tag": "input", "label": "Ville", "name": "address[city]"}, "city"),
    ({"tag": "input", "name": "phoneNumber"}, "phone"),
    ({"tag": "input", "type": "password", "label": "Confirmer le mot de passe"}, "new-password"),
    ({"tag": "input", "type": "password", "label": "Mot de passe"}, "password"),
    ({"tag": "input", "type": "text", "label": "Mot de passe"}, "password"),
    ({"tag": "input", "type": "date", "label": "Date de naissance"}, "birth-date"),
    ({"tag": "input", "autocomplete": "shipping postal-code", "label": "Zip"}, "postal-code"),
    ({"tag": "input", "label": "IBAN"}, "iban"),
    ({"tag": "textarea", "label": "Votre message"}, "free-text"),
    ({"tag": "input", "type": "search"}, "search"),
    ({"tag": "input", "type": "file"}, "file"),
    ({"tag": "input", "label": "Couleur préférée"}, "text"),
])
def test_field_classification_prefers_labels_and_specific_keywords(field, kind):
    assert checks.classify(field, CATALOG)[0] == kind


def test_page_analysis_reports_structural_defects_and_matching_checks():
    page = {"url": "http://127.0.0.1:3000/signup?email=a@example.com", "title": "Créer un compte",
            "actions": ["Créer mon compte", "Se déconnecter"], "cookies": ["sessionid", "theme"], "fields": [
                {"tag": "input", "type": "number", "label": "Code postal", "label_source": "label"},
                {"tag": "input", "type": "password", "label": "Mot de passe", "label_source": "label",
                 "autocomplete": "new-password", "form_method": "get", "form_has_action": True},
                {"tag": "input", "type": "text", "name": "x", "label": "", "label_source": ""}]}
    analysis = checks.analyze_page(page, CATALOG)
    assert {"form", "signup", "logged-in"} <= set(analysis["features"])
    messages = " ".join(note["message"] for note in analysis["observations"])
    assert "type=number" in messages and "submitted with GET" in messages
    assert "no accessible name" in messages and "sessionid" in messages and "email" in messages
    assert "theme" not in messages
    assert {"postal-code-formats", "new-password-rules", "logout-session"} <= set(analysis["checks"])


def test_draw_spreads_seeded_checks_without_changing_the_persona_draw():
    args = ("ux", 4, ["Create an account"], 42, {"nom": "Demo"})
    plain, _ = tirer_horde(*args, checks="none")
    first, plan = tirer_horde(*args, themes="functional,security")
    assert first == tirer_horde(*args, themes="functional,security")[0]
    for before, after in zip(plain["humains"], first["humains"]):
        assert (before["nom"], before["profil"], before["condition"]) == (after["nom"], after["profil"], after["condition"])
        assert len(after["checks"]) == checks.per_user(20)
    assigned = [entry["id"] for user in first["humains"] for entry in user["checks"]]
    assert len(set(assigned)) == len(assigned)
    known = {check["id"]: check for check in CATALOG["checks"]}
    assert all(known[name]["theme"] in ("functional", "security") and known[name]["scope"] == "safe" for name in assigned)
    assert plan["checks"]["assigned"]["h01"] == [entry["id"] for entry in first["humains"][0]["checks"]]


def test_auto_selection_follows_detected_pages_and_explicit_ids_include_any_scope():
    detected = ({"phone"}, {"form"})
    pool = {check["id"] for check in checks.select("auto", ["functional"], CATALOG, detected)}
    assert "phone-formats" in pool and "postal-code-formats" not in pool and "double-submit" in pool
    chosen = checks.select("reset-enumeration,phone-formats", ["ux"], CATALOG)
    assert [check["id"] for check in chosen] == ["reset-enumeration", "phone-formats"]
    with pytest.raises(ValueError, match="Unknown checks"):
        checks.select("no-such-check", ["ux"], CATALOG)


def test_sheet_lists_checks_with_values_and_flag_prefix(tmp_path):
    personas, _ = tirer_horde("ux", 1, ["Create an account"], 7, {"nom": "Demo"}, checks="phone-formats")
    (tmp_path / "personas.json").write_text(json.dumps(personas, ensure_ascii=False), encoding="utf-8")

    class Options:
        dossier, donnees, interdits, budget, shell = str(tmp_path), "Synthetic", "Real accounts", 20, "posix"

    engine.commande_fiches(Options())
    sheet = (tmp_path / "fiches" / "h01.md").read_text(encoding="utf-8")
    assert "QA CHECKS" in sheet and "[phone-formats]" in sheet and "Should be refused:" in sheet
    assert re.search(r"Should be accepted: .*\d", sheet)
    gb, _ = tirer_horde("ux", 1, ["Create an account"], 7, {"nom": "Demo"}, checks="postal-code-formats", countries="GB")
    entry = gb["humains"][0]["checks"][0]
    assert all(checks.parts(item)[1] in (None, "GB") for item in entry["valid"] + entry["invalid"])


def test_compare_masks_typed_values_and_ignored_patterns():
    masks = ["test-account@example.com", "nobody-1@example.com", "ab"]
    a = qa.normalized({"url": "http://x/reset", "text": "Sent to test-account@example.com\nab ok"}, masks, [])
    b = qa.normalized({"url": "http://x/reset", "text": "Sent to nobody-1@example.com\nab ok"}, masks, [])
    assert a == b and "ab ok" in a[1]
    c = qa.normalized({"url": "http://x/reset", "text": "No account for nobody-1@example.com"}, masks, [])
    assert qa.differences(a, c)
    stamped = [qa.normalized({"url": "", "text": f"Request {n} received"}, [], [re.compile(r"\d+")]) for n in (1, 2)]
    assert not qa.differences(*stamped)
