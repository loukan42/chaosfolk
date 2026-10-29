"""Browser regressions for interrupted dashboard edits and independent stop control."""
import os
from pathlib import Path
import threading
import time
import zipfile

import pytest
from playwright.sync_api import expect, sync_playwright

from chaosfolk.audit_dashboard import make_server
from chaosfolk.audit_session import Session

pytestmark = pytest.mark.browser


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    if os.environ.get("GAUNTLET_UI_BASELINE"):
        import chaosfolk.audit_dashboard as module
        with zipfile.ZipFile(".horde/gauntlet-20261029/baseline.zip") as archive:
            for suffix in ("html", "js", "css"):
                (tmp_path / f"audit-live.{suffix}").write_bytes(archive.read(f"src/chaosfolk/templates/audit-live.{suffix}"))
        monkeypatch.setattr(module, "ASSETS", tmp_path)
    session = Session(tmp_path / "session")
    session.create("deep")
    session.start()
    server = make_server(session)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        url = f"http://127.0.0.1:{server.server_port}/#{server.audit_token}"
        page.goto(url)
        expect(page.locator("#connection")).to_contain_text("Connecté")
        yield page, session, browser, url
        browser.close()
    server.shutdown()
    server.server_close()
    worker.join(5)


def capture(page, name):
    if folder := os.environ.get("GAUNTLET_UI_EVIDENCE"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(folder) / (name + ".png")), full_page=True)
        page.screenshot(path=str(Path(folder) / (name + "-viewport.png")))


def wait_for_held(page, held):
    deadline = time.monotonic() + 5
    while not held and time.monotonic() < deadline:
        page.wait_for_timeout(20)
    assert held, "The intercepted selection request did not complete on the server"


def budget(page):
    page.locator(".budget summary").click()
    return page.locator('#limits input[name="actions"]')


def test_stop_available_while_selection_response_is_delayed(dashboard):
    page, session, _, _ = dashboard
    held = []
    page.route("**/api/selection", lambda route: held.append((route, route.fetch())))
    page.locator('#tests input:not(:disabled)').first.uncheck()
    expect(page.locator("body")).to_have_class("busy")
    wait_for_held(page, held)
    capture(page, "stop-during-save")
    expect(page.locator("#stop")).to_be_enabled(timeout=1000)
    page.locator("#stop").click()
    expect(page.locator("#state")).to_have_text("Arrêté")
    assert session.snapshot()["config"]["state"] == "stopped"
    held[0][0].fulfill(response=held[0][1])
    expect(page.locator("body")).not_to_have_class("busy")
    expect(page.locator("#state")).to_have_text("Arrêté")


def test_failed_budget_save_preserves_input_and_allows_retry(dashboard):
    page, session, _, _ = dashboard
    actions = budget(page)
    actions.fill("321")
    page.route("**/api/selection", lambda route: route.abort())
    page.get_by_role("button", name="Enregistrer les limites").click()
    expect(page.locator("body")).not_to_have_class("busy")
    expect(page.locator("#message")).to_be_visible()
    page.locator("#search").focus()
    session.configure(limits={"max_browsers": 4})
    expect(page.locator('#limits input[name="browsers"]')).to_have_value("4")
    capture(page, "budget-failed")
    expect(actions).to_have_value("321")
    page.unroute("**/api/selection")
    page.get_by_role("button", name="Enregistrer les limites").click()
    expect(page.locator("body")).not_to_have_class("busy")
    assert session.snapshot()["config"]["limits"]["max_actions"] == 321


def test_budget_saves_only_changed_fields_between_tabs(dashboard):
    first, session, browser, url = dashboard
    second = browser.new_page()
    second.goto(url)
    expect(second.locator("#connection")).to_contain_text("Connecté")
    second.route("**/api/state?after=*", lambda route: route.abort())
    budget(second).fill("321")
    budget(first)
    first.locator('#limits input[name="browsers"]').fill("2")
    first.get_by_role("button", name="Enregistrer les limites").click()
    expect(first.locator("body")).not_to_have_class("busy")
    second.get_by_role("button", name="Enregistrer les limites").click()
    expect(second.locator("body")).not_to_have_class("busy")
    limits = session.snapshot()["config"]["limits"]
    assert limits["max_actions"] == 321
    assert limits["max_browsers"] == 2


def test_unsaved_budget_survives_reload_without_becoming_saved(dashboard):
    page, session, _, _ = dashboard
    budget(page).fill("321")
    page.reload()
    expect(page.locator("#connection")).to_contain_text("Connecté")
    expect(page.locator('#limits input[name="actions"]')).to_have_value("321")
    assert session.snapshot()["config"]["limits"]["max_actions"] != 321


def test_recovered_poll_clears_network_error(dashboard):
    page, _, _, _ = dashboard
    page.route("**/api/state?after=*", lambda route: route.abort())
    expect(page.locator("#connection")).to_have_text("Connexion interrompue")
    expect(page.locator("#message")).to_be_visible()
    page.unroute("**/api/state?after=*")
    expect(page.locator("#connection")).to_contain_text("Connecté")
    expect(page.locator("#message")).to_be_hidden()


def test_stop_remains_in_view_on_mobile_and_desktop(dashboard):
    page, _, _, _ = dashboard
    for width in (1100, 736, 360, 320):
        page.set_viewport_size({"width": width, "height": 850})
        page.locator("footer").scroll_into_view_if_needed()
        capture(page, f"stop-scrolled-{width}")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        expect(page.locator("#stop")).to_be_in_viewport()


def test_edit_during_delayed_save_stays_unsaved_and_discard_restores_server(dashboard):
    page, session, _, _ = dashboard
    actions = budget(page)
    actions.fill("321")
    held = []
    page.route("**/api/selection", lambda route: held.append((route, route.fetch())))
    page.get_by_role("button", name="Enregistrer les limites").click()
    expect(page.locator("body")).to_have_class("busy")
    actions.fill("322")
    page.locator("#search").focus()
    wait_for_held(page, held)
    held[0][0].fulfill(response=held[0][1])
    expect(page.locator("body")).not_to_have_class("busy")
    expect(actions).to_have_value("322")
    assert session.snapshot()["config"]["limits"]["max_actions"] == 321
    expect(page.locator("#limits-note")).to_contain_text("non enregistrées")
    page.locator("#discard-limits").click()
    expect(actions).to_have_value("321")
    page.reload()
    expect(actions).to_have_value("321")


def test_navigation_back_restores_polling_and_draft(dashboard):
    page, session, _, _ = dashboard
    budget(page).fill("321")
    page.goto("about:blank")
    session.stop()
    page.go_back()
    expect(page.locator("#connection")).to_contain_text("Connecté")
    expect(page.locator("#state")).to_have_text("Arrêté")
    expect(page.locator('#limits input[name="actions"]')).to_have_value("321")
    session.start()
    expect(page.locator("#state")).to_have_text("En cours")


def test_stop_invalidates_start_delayed_before_server(dashboard):
    page, session, _, _ = dashboard
    session.stop()
    expect(page.locator("#state")).to_have_text("Arrêté")
    held = []
    page.route("**/api/start", lambda route: held.append(route))
    page.locator("#start").click()
    wait_for_held(page, held)
    expect(page.locator("#stop")).to_be_enabled()
    page.locator("#stop").click()
    expect(page.locator("#stop")).to_have_text("Arrêter l’audit")
    assert session.snapshot()["config"]["state"] == "stopped"
    held[0].continue_()
    expect(page.locator("body")).not_to_have_class("busy")
    expect(page.locator("#state")).to_have_text("Arrêté")
    assert session.snapshot()["config"]["state"] == "stopped"
