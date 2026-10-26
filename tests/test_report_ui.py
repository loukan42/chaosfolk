"""Behavioral checks for the portable bilingual evidence report."""
import json
from pathlib import Path
import shutil

import pytest
from playwright.sync_api import sync_playwright

from chaosfolk import engine

pytestmark = pytest.mark.browser


@pytest.fixture
def report_page(tmp_path):
    shutil.copyfile(Path(engine.__file__).parent / "templates/mascot.png", tmp_path / "shot.png")
    proof = {"fois": 3, "demandes": 3, "casses": 3, "mode": "traitement", "captures": ["shot.png"]}
    control = dict(proof, casses=0, mode="temoin")
    payload = {
        "lang": "fr", "config": {}, "branding": {"columns": 4, "rows": 4},
        "score": {"note": 74, "raw": 86, "level": "fair", "provisional": True,
                  "cap": {"value": 74, "ids": ["C2"], "reason": "open-blocker"},
                  "pillars": [{"id": "defects", "value": 36, "max": 50}]},
        "personas": {"humains": [{"id": "h01", "nom": "Alex", "skin": 0}, {"id": "h02", "nom": "Sam", "skin": 15}]},
        "journal": [{"type": "action", "h": "h01", "n": 1, "action": "click", "resultat": "echec", "capture": "shot.png", "pense": "Original reaction"},
                    {"type": "action", "h": "h01", "n": 2, "action": "look", "resultat": "ok", "capture": "shot.png"},
                    {"type": "action", "h": "h02", "n": 1, "action": "look", "resultat": "ok", "capture": "shot.png"}],
        "constats": {"titre": "Session title", "resume": "Evidence from a test fixture.", "constats": [
            {"id": "C1", "titre": "Draft lost", "condition": "storage-full", "gravite": "bloquant",
             "preuves": {"avant": proof, "temoin": control},
             "correctif": {"consigne": "Keep the draft.", "attendu": "Draft remains available."}},
            {"id": "C2", "titre": "Unconfirmed issue", "condition": "offline", "gravite": "genant", "preuves": {}}
        ], "translations": {"fr": {"titre": "Titre de la séance", "resume": "Preuves sur une maquette.", "constats": [
            {"id": "C1", "titre": "Brouillon perdu", "condition": "stockage plein", "correctif": {"consigne": "Conserver le brouillon.", "attendu": "Le brouillon reste disponible."},
             "preuves": {"avant": {"fois": 99, "demandes": 99, "casses": 0}}}
        ]}}}
    }
    def create(value=payload):
        encoded = json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
        output = tmp_path / "report.html"
        output.write_text(engine.MODELE_RAPPORT.read_text(encoding="utf-8").replace("/*__DONNEES__*/null", encoded), encoding="utf-8")
        return output
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, external = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: external.append(r.url) if r.url.startswith(("http:", "https:")) else None)
        page.goto(create().as_uri())
        yield page, payload, create
        assert not errors, errors
        assert not external, external
        browser.close()


def test_bilingual_score_compact_findings_and_proof_integrity(report_page):
    page, _, _ = report_page
    assert page.locator("html").get_attribute("lang") == "fr"
    assert page.locator(".score-number").inner_text() == "74"
    assert page.locator("#title").inner_text() == "2 points à vérifier"
    assert page.locator("#findings-title").inner_text() == "À corriger"
    assert page.locator(".finding-toggle").first.get_attribute("aria-expanded") == "false"
    assert page.locator("#findings-section").bounding_box()["y"] < page.locator("#overview-title").bounding_box()["y"]
    page.locator(".finding-toggle").first.click()
    assert "3/3 échecs" in page.locator(".finding-body").first.inner_text()
    assert "99" not in page.locator(".proofs").first.inner_text()
    page.get_by_role("button", name="EN", exact=True).click()
    assert page.locator("html").get_attribute("lang") == "en"
    assert page.locator(".finding-toggle").first.inner_text().find("Draft lost") >= 0
    assert "3/3 failures" in page.locator(".finding-body").first.inner_text()
    assert not page.evaluate("valid({fois:3,demandes:4,casses:3,mode:'traitement'})")
    assert not page.evaluate("proven({condition:'offline',preuves:{avant:{fois:3,demandes:3,casses:3,mode:'traitement'},temoin:{fois:3,demandes:3,casses:0,mode:'traitement'}}})")


def test_mosaic_filters_timeline_and_bulk_copy_fallback(report_page):
    page, _, _ = report_page
    assert page.locator(".screen-card").count() == 2
    assert page.locator(".mini-screen img").count() == 2
    page.get_by_role("button", name="Ouvrir le rejeu de Alex").click()
    assert page.locator("#person").input_value() == "h01"
    assert "Événement 1 sur 2" in page.locator("#narrative").inner_text()
    page.get_by_role("button", name="Événement suivant").click()
    assert "Événement 2 sur 2" in page.locator("#narrative").inner_text()
    page.get_by_role("button", name="Observés", exact=True).click()
    assert page.locator(".finding").count() == 1
    assert "Unconfirmed issue" in page.locator(".finding").inner_text()
    page.get_by_role("button", name="Tous les constats", exact=True).click()
    page.get_by_role("checkbox", name="Sélectionner C2", exact=True).uncheck()
    page.get_by_role("button", name="Voir le prompt", exact=True).click()
    assert "Conserver le brouillon." in page.locator("#prompt-text").input_value()
    assert "Unconfirmed" not in page.locator("#prompt-text").input_value()
    page.evaluate("Object.defineProperty(navigator,'clipboard',{value:{writeText:()=>Promise.reject(new Error('denied'))}, configurable:true})")
    page.get_by_role("button", name="Copier le 1 coché", exact=True).click()
    assert page.locator("#prompt-panel").is_visible()
    assert "Sélectionne" in page.locator("#copy-status").inner_text()
    assert page.locator("#prompt-text").evaluate("e=>e.selectionEnd>e.selectionStart")
    page.set_viewport_size({"width": 375, "height": 812})
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")


def test_untrusted_content_and_pending_score(report_page):
    page, payload, create = report_page
    payload.pop("score")
    attack = '</script><img src="https://example.com/leak" onerror="window.pwned=true">'
    payload["constats"]["translations"]["fr"]["constats"][0]["titre"] = attack
    payload["journal"][0]["capture"] = "https://example.com/leak.png"
    page.goto(create(payload).as_uri())
    assert page.locator(".score-pending").inner_text() == "En attente"
    assert attack in page.locator(".finding-toggle").first.inner_text()
    assert not page.evaluate("Boolean(window.pwned)")
    assert page.locator('img[src^="http"]').count() == 0
    for path in ("../private.png", "%2e%2e/private.png", "https://example.com/a.png", "%2f%2fexample.com/a.png"):
        assert not page.evaluate("path=>localImage(path)", path)
