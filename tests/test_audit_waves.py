import json
import os

import pytest

from chaosfolk.audit_session import Session
from test_browser import cli, fixture_url  # noqa: F401

pytestmark = pytest.mark.browser


def test_waves_release_finished_browsers_and_keep_coordinated_dependencies(tmp_path, fixture_url):  # noqa: F811
    session = Session(tmp_path / "session")
    session.create("deep", max_seconds=180, max_actions=200)
    session.start()
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    result = cli("launch", "--url", fixture_url, "--folder", session.folder, "--channel", "chromium", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    env["CHAOSFOLK_LEADER_TOKEN"] = json.loads((session.folder / "serveur.json").read_text())["jeton_chef"]

    def run(*args):
        result = cli(*args, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    previous = set()

    def draw(*extra):
        run("draw", "--count", "2", "--budget", "14", "--seed", "42", "--objectives", "Create a project",
            "--url", fixture_url, "--folder", session.folder, *extra)
        personas = json.loads((session.folder / "personas.json").read_text())
        fresh = [p["id"] for p in personas["humains"] if p["id"] not in previous and p["id"] != "e0"]
        previous.update(fresh)
        return fresh

    try:
        scout = session.folder / "scout.json"
        scout.write_text('{"humains":[{"id":"e0","nom":"Scout"}]}')
        run("humans", scout)
        run("fields", "e0", "--save", session.folder / "fields.json")
        run("e0", "done", "Discovery complete")
        first = draw()
        run("humans", session.folder / "personas.json")
        for user in first:
            run(user, "done", "No result claimed")
        second = draw()
        run("humans", session.folder / "personas.json")
        released = cli("inspect", first[0], "document.title", env=env)
        assert released.returncode != 0 and "released" in released.stdout
        for user in second:
            run(user, "done", "No result claimed")
        session.configure(limits={"max_browsers": 2})
        coordinated = draw("--sessions", "coordinated", "--shared", "Synthetic project")
        run("humans", session.folder / "personas.json")
        for user in coordinated:
            run(user, "done", "Coordinated proof not yet collected")
        draw()
        blocked = cli("humans", session.folder / "personas.json", env=env)
        assert blocked.returncode != 0 and "Browser limit" in blocked.stdout
        assert cli("inspect", coordinated[0], "document.title", env=env).returncode == 0
        for user in coordinated:
            run("release", user)
        run("humans", session.folder / "personas.json")
        assert session.snapshot()["completion"] == "partial"
    finally:
        cli("stop", env=env)
