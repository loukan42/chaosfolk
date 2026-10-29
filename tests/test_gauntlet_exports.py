import json

import pytest
from playwright.sync_api import sync_playwright

from chaosfolk import engine, regression, scoring, privacy


@pytest.mark.parametrize("suffix", ["?code=fixture", "?session=fixture", "?pwd=fixture", "?X-Amz-Credential=fixture",
                                    "#access_token=fixture", "#/callback?code=fixture", "?%74oken=fixture"])
def test_portable_export_refuses_authentication_urls_before_writing(tmp_path, suffix):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"url": "http://localhost/" + suffix, "steps": [],
                                  "expect": [{"type": "no-page-error"}]}))
    output = tmp_path / "portable.py"
    with pytest.raises(ValueError, match="authentication"):
        regression.export_test(source, output)
    assert not output.exists()


@pytest.mark.browser
@pytest.mark.parametrize("attributes", ['type="password"', 'type="text" autocomplete="ONE-TIME-CODE"',
                                       'type="text" autocomplete="CURRENT-PASSWORD"', 'type="text" autocomplete="NEW-PASSWORD"'])
def test_real_password_descriptor_prevents_export_with_uninformative_label(tmp_path, attributes):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content(f'<label>Accès<input {attributes} id="entry" data-horde-ref="r1"></label>')
        descriptor = page.evaluate(engine.script_ecran(), {"mode": "decrire", "ref": "r1"})
        browser.close()
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"url": "http://localhost/", "steps": [{"action": "type", "target": descriptor,
        "args": {"text": "SYNTHETIC-CREDENTIAL"}}], "expect": [{"type": "no-page-error"}]}))
    output = tmp_path / "portable.py"
    with pytest.raises(ValueError, match="credential"):
        regression.export_test(source, output)
    assert not output.exists()


@pytest.mark.parametrize("label", ["Mot de passe", "Nouveau mot de passe", "pwd"])
def test_legacy_password_descriptors_are_refused(tmp_path, label):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"url": "http://localhost/", "steps": [{"action": "type",
        "target": {"role": "textbox", "name": label}, "args": {"text": "SYNTHETIC"}}],
        "expect": [{"type": "no-page-error"}]}))
    with pytest.raises(ValueError, match="credential"):
        regression.export_test(source, tmp_path / "portable.py")


def test_public_search_parameters_still_export(tmp_path):
    source = tmp_path / "scenario.json"
    source.write_text(json.dumps({"url": "http://localhost/?page=2&sort=name#results", "steps": [],
                                  "expect": [{"type": "no-page-error"}]}))
    assert regression.export_test(source, tmp_path / "portable.py").is_file()


def test_hash_route_authentication_is_redacted():
    assert "SYNTHETIC" not in privacy.sanitize("http://localhost/#/callback?code=SYNTHETIC")


@pytest.mark.parametrize("tested", [0, 1])
def test_unfinished_audit_never_gets_a_final_score(tested):
    result = scoring.score_report({"constats": {"constats": []},
        "journal": [{"type": "action", "h": "h01", "action": "done", "t": 1}],
        "audit_session": {"completion": "partial", "tested": tested, "unresolved": 73}})
    assert result["provisional"]
    if not tested:
        assert result["note"] is None


def test_public_proofs_omit_raw_screens_and_inputs_recursively(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    proof = {"mode": "traitement", "fois": 3, "demandes": 3, "casses": 0,
             "essais": [{"ok": True, "ecran": ["PRIVATE_TYPED_NAME"],
                          "raisons": ['field differs (seen PRIVATE_TYPED_NAME)'],
                          "observation": {"field": "PRIVATE_TYPED_NAME"},
                          "args": {"texte": "PRIVATE_TYPED_NAME"}} for _ in range(3)]}
    (source / "proof.json").write_text(json.dumps(proof))
    (source / "constats.json").write_text(json.dumps({"constats": [{"id": "C1", "titre": "Evidence",
        "preuves": {"avant": "proof.json", "temoin": proof}}]}))
    (source / "journal.jsonl").write_text("")
    destination = tmp_path / "public"
    privacy.export_report(source, destination, "en")
    for path in destination.rglob("*"):
        if path.is_file():
            assert b"PRIVATE_TYPED_NAME" not in path.read_bytes()
    exported = json.loads((destination / "reproductions/proof-000001.json").read_text())
    assert exported["casses"] == 0 and len(exported["essais"]) == 3
    assert all(trial["ok"] for trial in exported["essais"])


@pytest.mark.browser
def test_partial_score_notice_is_visible_without_expanding_methodology(tmp_path):
    (tmp_path / "constats.json").write_text('{"constats": []}')
    (tmp_path / "journal.jsonl").write_text(json.dumps({"type": "action", "h": "h01", "t": 1, "action": "done"}) + "\n")
    (tmp_path / "audit-coverage.json").write_text(json.dumps({"export_schema": 1, "completion": "partial",
        "tested": 1, "unresolved": 73, "entries": [], "config": {"depth": "deep", "excluded": []}}))
    engine.rapport(tmp_path, "en")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto((tmp_path / "rapport.html").as_uri())
        from playwright.sync_api import expect
        expect(page.locator("#score-cap")).to_contain_text("Provisional")
        expect(page.locator("#score-cap")).to_be_visible()
        browser.close()
