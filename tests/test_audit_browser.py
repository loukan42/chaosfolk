import json
import os
import threading

import pytest
from playwright.sync_api import sync_playwright, expect

from chaosfolk.audit_session import Session
from chaosfolk.audit_dashboard import make_server
from test_browser import cli, ref_for, fixture_url  # noqa: F401

pytestmark = pytest.mark.browser


def test_live_selection_drives_real_engine_and_stop(tmp_path, fixture_url):  # noqa: F811
    folder = tmp_path / "session"
    session = Session(folder)
    session.create("deep", max_seconds=180, max_actions=100)
    session.start()
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    launch = cli("launch", "--url", fixture_url, "--folder", folder, "--budget", "20", "--channel", "chromium", env=env)
    assert launch.returncode == 0, launch.stdout + launch.stderr
    info = json.loads((folder / "serveur.json").read_text())
    leader = dict(env, CHAOSFOLK_LEADER_TOKEN=info["jeton_chef"])
    server = make_server(session, token="browser-test")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        scout = folder / "scout.json"
        scout.write_text(json.dumps({"humains":[{"id":"e0","nom":"Scout"}]}))
        assert cli("humans", scout, env=leader).returncode == 0
        fields = cli("fields", "e0", "--save", folder / "fields.json", env=leader)
        assert fields.returncode == 0, fields.stdout + fields.stderr
        assert session.snapshot()["counts"]["measured"] > 0
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width":1100,"height":850})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/#browser-test")
            expect(page.locator("#connection")).to_contain_text("Connecté")
            # A real checkbox changes SQLite, and the next real draw obeys it.
            candidate = next(e for e in session.snapshot()["entries"] if e["selected"] and e["executor"] == "agent" and e["states"].get("pending"))
            page.locator("#search").fill(candidate["title"])
            box = page.get_by_role("checkbox", name=candidate["title"], exact=True)
            box.uncheck()
            expect(box).not_to_be_checked()
            expect(page.locator("#selection-count")).to_contain_text("1 retirés")
            assert candidate["id"] in session.snapshot()["config"]["excluded"]
            page.locator("input[value=quick]").check()
            expect(page.locator("input[value=quick]")).to_be_enabled()
            if candidate["priority"] != "P1":
                page.get_by_role("button", name="Rétablir la sélection du niveau").click()
                expect(page.locator("input[value=quick]")).to_be_enabled()
                assert candidate["id"] in session.snapshot()["config"]["excluded"]
            page.locator("input[value=deep]").check()
            expect(page.locator("input[value=deep]")).to_be_enabled()
            page.reload()
            expect(page.locator("#connection")).to_contain_text("Connecté")
            assert candidate["id"] in session.snapshot()["config"]["excluded"]
            draw = cli("draw", "--count", "2", "--budget", "14", "--seed", "42", "--objectives", "Create a project", "--url", fixture_url, "--folder", folder, env=leader)
            assert draw.returncode == 0, draw.stdout + draw.stderr
            personas = json.loads((folder / "personas.json").read_text())
            generated = [h for h in personas["humains"] if h.get("audit_tasks")]
            assert not any(t["check_id"] == candidate["id"] for h in generated for t in h["audit_tasks"])
            humans = cli("humans", folder / "personas.json", env=leader)
            assert humans.returncode == 0, humans.stdout + humans.stderr
            first = generated[0]
            hid, task = first["id"], first["audit_tasks"][0]
            result = cli(hid, "check-start", task["task_id"], env=env)
            assert result.returncode == 0, result.stdout + result.stderr
            look = cli(hid, "look", env=env)
            assert look.returncode == 0, look.stdout + look.stderr
            typed = cli(hid, "type", ref_for(look.stdout, "Project name"), "Synthetic audit project", env=env)
            assert typed.returncode == 0, typed.stdout + typed.stderr
            result = cli(hid, "check-result", task["task_id"], "inconclusive", "Input exercised; remaining variants not verified in this integration test", env=env)
            assert result.returncode == 0, result.stdout + result.stderr
            assert session.snapshot()["counts"]["inconclusive"] == 1
            # Deactivation is checked for the active task, not just the next draw.
            next_task = first["audit_tasks"][1]
            assert cli(hid, "check-start", next_task["task_id"], env=env).returncode == 0
            session.configure(excluded=[candidate["id"], next_task["check_id"]])
            assert cli(hid, "reload", env=env).returncode != 0
            page.get_by_role("button", name="Arrêter l’audit", exact=True).click()
            expect(page.locator("#state")).to_have_text("Arrêté")
            stopped = cli("e0", "reload", env=leader)
            assert stopped.returncode != 0 and "Audit stopped" in stopped.stdout
            assert cli(hid, "done", "Stopped", env=env).returncode == 0
            assert session.snapshot()["completion"] == "partial"
            for width in (1100,736,360,320):
                page.set_viewport_size({"width":width,"height":850})
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.screenshot(path=str(folder / "dashboard-mobile.png"), full_page=True)
            page.set_viewport_size({"width":1100,"height":850})
            page.screenshot(path=str(folder / "dashboard-desktop.png"), full_page=True)
            report = cli("report", "--folder", folder, "--lang", "fr", env=leader)
            assert report.returncode == 0, report.stdout + report.stderr
            page.goto((folder / "rapport.html").as_uri())
            expect(page.locator("#audit-session-section")).to_be_visible()
            expect(page.locator("#audit-session-summary")).to_contain_text("Audit partiel")
            page.locator("#audit-session-details-label").click()
            assert page.locator("#audit-session-list .coverage-item").count() == 116
            assert errors == []
            browser.close()
    finally:
        cli("stop", env=leader)
        server.shutdown()
        server.server_close()
        worker.join(5)
