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
    (tmp_path / "assets").mkdir()
    shutil.copyfile(Path(engine.__file__).parent / "templates/room.js", tmp_path / "assets/room.js")
    proof = {"fois": 3, "demandes": 3, "casses": 3, "mode": "traitement", "captures": ["shot.png"]}
    control = dict(proof, casses=0, mode="temoin")
    payload = {
        "lang": "fr", "config": {}, "branding": {"columns": 4, "rows": 4},
        "score": {"note": 74, "raw": 86, "level": "fair", "provisional": True,
                  "cap": {"value": 74, "ids": ["C2"], "reason": "open-blocker"},
                  "pillars": [{"id": "defects", "value": 45.241870901797974, "max": 50}]},
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
    page.locator("#score-method summary").click()
    assert "45 / 50" in page.locator("#score-detail").inner_text()
    assert "45.241" not in page.locator("#score-detail").inner_text()
    assert page.locator("#title").inner_text() == "2 points à vérifier"
    assert page.locator("#findings-title").inner_text() == "À corriger"
    assert page.locator(".finding-toggle").first.get_attribute("aria-expanded") == "false"
    assert page.locator("#findings-section").bounding_box()["y"] < page.locator("#room").bounding_box()["y"]
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
    page.locator("#room-range").evaluate("e=>{e.value=e.max;e.dispatchEvent(new Event('input',{bubbles:true}))}")
    assert page.locator(".mini-screen img").count() == 2
    page.get_by_role("button", name="Ouvrir le rejeu de Alex").click()
    assert page.locator("#person").input_value() == "h01"
    assert "Événement 2 sur 2" in page.locator("#narrative").inner_text()
    page.get_by_role("button", name="Événement précédent").click()
    assert "Événement 1 sur 2" in page.locator("#narrative").inner_text()
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


def test_synchronized_room_faults_markers_and_languages(report_page):
    page, payload, create = report_page
    payload["journal"] = [
        {"type": "action", "h": "h01", "n": 1, "t": 1000, "action": "look", "resultat": "ok", "capture": "shot.png"},
        {"type": "panne-debut", "id": "p1", "h": "h01", "t": 2000, "panne": "offline"},
        {"type": "action", "h": "h02", "n": 1, "t": 3000, "action": "click", "resultat": "ok", "capture": "shot.png"},
        {"type": "action", "h": "h01", "n": 2, "t": 4000, "action": "flag", "gravite": "blocking", "resultat": "ok", "pense": "Saved reaction"},
        {"type": "panne-fin", "id": "p1", "h": "h01", "t": 5000, "panne": "offline"},
        {"type": "action", "h": "h02", "n": 2, "t": 6000, "action": "done", "resultat": "ok"},
    ]
    payload["constats"]["constats"][0]["evenements"] = [{"h": "h01", "n": 2}]
    page.goto(create(payload).as_uri())
    assert page.locator("#room-time").inner_text() == "00:00 / 00:05"
    assert page.locator(".screen-card").count() == 2
    assert page.locator(".mini-screen img").count() == 1
    assert page.locator("#room-markers .room-band").count() == 1
    assert page.locator("#room-markers .blocking").count() == 1
    assert page.locator("#room-markers .finding-mark").count() == 1
    assert page.get_by_role("button", name="x1", exact=True).get_attribute("aria-pressed") == "true"
    page.locator("#room-range").evaluate("e=>{e.value=3000;e.dispatchEvent(new Event('input',{bubbles:true}))}")
    assert page.locator(".mini-screen img").count() == 2
    assert "Saved reaction" in page.locator(".screen-card").first.inner_text()
    assert "1" in page.locator("#room-stats .room-stat").nth(3).inner_text()
    page.get_by_role("button", name="Avec une panne", exact=True).click()
    assert page.locator(".screen-card").count() == 1
    page.get_by_role("button", name="Ont signalé un bloquant", exact=True).click()
    assert page.locator(".screen-card").count() == 1
    page.get_by_role("button", name="x16", exact=True).click()
    assert page.get_by_role("button", name="x16", exact=True).get_attribute("aria-pressed") == "true"
    page.get_by_role("button", name="EN", exact=True).click()
    assert page.locator("#screens-title").inner_text() == "Session replay"
    assert "Saved reaction" in page.locator(".screen-card").first.inner_text()
    page.get_by_role("button", name="Start over", exact=True).click()
    assert page.locator("#room-range").input_value() == "0"


def test_review_button_focuses_session_playback(report_page):
    page, _, _ = report_page
    for _ in range(3):
        page.get_by_role("button", name="Revoir la séance").click()
        assert page.evaluate("document.activeElement.id") == "room-play"


def test_scout_is_not_counted_as_a_simulated_tester(report_page):
    page, payload, create = report_page
    payload["journal"].insert(0, {"type": "action", "h": "e0", "n": 1, "t": 0,
                                  "action": "look", "resultat": "ok", "capture": "shot.png"})
    page.goto(create(payload).as_uri())
    assert page.locator(".screen-card").count() == 2
    assert page.locator(".screen-card").filter(has_text="e0").count() == 0


def test_selected_themes_report_only_documented_coverage(report_page):
    page, payload, create = report_page
    payload["coverage"] = {"requested": ["accessibility", "security"], "results": [
        {"theme": "accessibility", "status": "partial", "summary": "Keyboard navigation checked",
         "translations": {"fr": {"summary": "Navigation au clavier vérifiée"}}},
    ]}
    page.goto(create(payload).as_uri())
    assert page.locator("#coverage-title").inner_text() == "Périmètre testé"
    assert "Accessibilité" in page.locator("#coverage-list").inner_text()
    assert "Partiel" in page.locator("#coverage-list").inner_text()
    assert "Navigation au clavier vérifiée" in page.locator("#coverage-list").inner_text()
    assert "Non renseigné" in page.locator("#coverage-list").inner_text()
    page.get_by_role("button", name="EN", exact=True).click()
    assert "Keyboard navigation checked" in page.locator("#coverage-list").inner_text()
    assert "Not documented" in page.locator("#coverage-list").inner_text()


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
