import functools
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from chaosfolk import engine

pytestmark = pytest.mark.browser


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass


@pytest.fixture
def fixture_url():
    handler = functools.partial(QuietHandler, directory=str(Path(engine.__file__).parent / "demo"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def cli(*args, env=None, timeout=90):
    return subprocess.run([sys.executable, "-m", "chaosfolk", *map(str, args)],
                          env=env, capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def ref_for(screen, label):
    for line in screen.splitlines():
        if label in line:
            match = re.search(r"\b(r\d+)\b", line)
            if match:
                return match.group(1)
    raise AssertionError(f"No reference for {label!r} in screen:\n{screen}")


def test_daemon_authentication_actions_and_storage_isolation(tmp_path, fixture_url):
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    folder = tmp_path / "session"
    result = cli("launch", "--url", fixture_url, "--folder", folder, "--budget", "5", "--channel", "chromium", env=env)
    assert result.returncode == 0, result.stderr
    info = json.loads((folder / "serveur.json").read_text(encoding="utf-8"))
    leader = dict(env, CHAOSFOLK_LEADER_TOKEN=info["jeton_chef"])
    try:
        # A valid ordinary user token does not grant leader commands.
        assert cli("fault", "offline", env=env).returncode == 1
        personas = folder / "personas.json"
        personas.write_text(json.dumps({"humains": [{"id": "h01", "nom": "Alex"}, {"id": "h02", "nom": "Sam"}]}), encoding="utf-8")
        assert cli("humans", personas, env=env).returncode == 1
        result = cli("humans", personas, env=leader)
        assert result.returncode == 0, result.stdout
        look = cli("h01", "look", env=env)
        assert look.returncode == 0, look.stdout
        textbox = ref_for(look.stdout, "Project name")
        result = cli("h01", "type", textbox, "Synthetic project", env=env)
        assert result.returncode == 0, result.stdout
        button = ref_for(result.stdout, "Save project") if "Save project" in result.stdout else ref_for(look.stdout, "Save project")
        result = cli("h01", "click", button, env=env)
        assert result.returncode == 0, result.stdout
        first = cli("inspect", "h01", "localStorage.getItem('fieldnotes.project')", env=leader)
        second = cli("inspect", "h02", "localStorage.getItem('fieldnotes.project')", env=leader)
        assert first.returncode == second.returncode == 0
        assert json.loads(first.stdout) == "Synthetic project"
        assert json.loads(second.stdout) is None
        assert cli("inspect", "h01", "document.title", env=env).returncode == 1
        assert cli("h99", "look", env=env).returncode == 1
        # Budget-one draws inject at action zero, before the user's first gesture.
        injected = cli("fault", "storage-full", "--humans", "h02", "--after-actions", "0", env=leader)
        assert injected.returncode == 0, injected.stdout
        blocked = cli("inspect", "h02", "(() => {try {localStorage.setItem('probe','synthetic');return false;} catch {return true;}})()", env=leader)
        assert blocked.returncode == 0, blocked.stdout
        assert json.loads(blocked.stdout) is True
        # Browser screenshots were actually written, not fabricated in a report.
        assert list((folder / "captures").glob("*.jpg"))
    finally:
        result = cli("stop", env=leader)
        assert result.returncode == 0, result.stdout


def test_opt_in_faults_affect_only_the_test_browser_and_preserve_real_backend_effects(tmp_path):
    class ApiHandler(QuietHandler):
        writes = 0

        def do_GET(self):
            if self.path == "/api/probe":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
            else:
                super().do_GET()

        def do_POST(self):
            type(self).writes += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"saved")

    handler = functools.partial(ApiHandler, directory=str(Path(engine.__file__).parent / "demo"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/"
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    folder = tmp_path / "session"
    try:
        launch = cli("launch", "--url", url, "--folder", folder, "--budget", "5", env=env)
        assert launch.returncode == 0, launch.stdout + launch.stderr
        leader = dict(env, CHAOSFOLK_LEADER_TOKEN=json.loads((folder / "serveur.json").read_text(encoding="utf-8"))["jeton_chef"])
        personas = folder / "personas.json"
        personas.write_text(json.dumps({"humains": [{"id": "h01"}]}), encoding="utf-8")
        assert cli("humans", personas, env=leader).returncode == 0

        def inspect(expression):
            result = cli("inspect", "h01", expression, env=leader)
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout)

        assert inspect("fetch('/api/probe').then(r=>r.status)") == 200
        result = cli("fault", "http-error", "--humans", "h01", "--after-actions", "0", "--pattern", "*/api/*", "--duration", "30", env=leader)
        assert result.returncode == 0, result.stdout
        assert inspect("fetch('/api/probe').then(r=>r.status)") == 500
        assert cli("fault-end", "p1", env=leader).returncode == 0
        assert inspect("fetch('/api/probe').then(r=>r.status)") == 200

        result = cli("fault", "lost-response", "--humans", "h01", "--after-actions", "0", "--pattern", "*/api/*", "--method", "POST", env=leader)
        assert result.returncode == 0, result.stdout
        assert inspect("fetch('/api/probe',{method:'POST'}).then(()=>false).catch(()=>true)") is True
        assert ApiHandler.writes == 1

        assert inspect("localStorage.setItem('synthetic','valid'); localStorage.getItem('synthetic')") == "valid"
        result = cli("fault", "storage-corrupt", "--humans", "h01", "--after-actions", "0", "--key", "synthetic", env=leader)
        assert result.returncode == 0, result.stdout
        assert inspect("localStorage.getItem('synthetic')") != "valid"
        assert inspect("document.cookie='synthetic=1; path=/'; document.cookie.includes('synthetic=1')") is True
        result = cli("fault", "cookies-cleared", "--humans", "h01", "--after-actions", "0", env=leader)
        assert result.returncode == 0, result.stdout
        assert inspect("document.cookie.includes('synthetic=1')") is False
    finally:
        if (folder / "serveur.json").exists():
            info = json.loads((folder / "serveur.json").read_text(encoding="utf-8"))
            cli("stop", env=dict(env, CHAOSFOLK_LEADER_TOKEN=info["jeton_chef"]))
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("expect,code", [
    ({"type": "text-visible", "text": "Project name"}, 0),
    ({"type": "text-visible", "text": "This text is absent"}, 1),
    ({"type": "js", "expression": "(() => {throw new Error('cannot evaluate')})()"}, 2),
])
def test_replay_exit_codes_distinguish_pass_failure_and_inconclusive(tmp_path, fixture_url, expect, code):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps({"url": fixture_url, "session_dir": str(tmp_path), "steps": [], "expect": expect}), encoding="utf-8")
    result = cli("replay", path, "--times", "1", "--fail-on-bug", "--output", tmp_path / "results")
    assert result.returncode == code, result.stdout + result.stderr
    evidence = json.loads(next((tmp_path / "results").glob("*.json")).read_text(encoding="utf-8"))
    if code == 2:
        assert evidence["fois"] == 0
        assert evidence["casses"] == 0
    else:
        assert evidence["fois"] == 1
        assert evidence["casses"] == code


def test_demo_measures_failure_control_and_fix(tmp_path):
    result = cli("demo", "--output", tmp_path / "demo", "--lang", "fr", timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    for name, failures in (("before", 3), ("before-temoin", 0), ("after", 0), ("after-temoin", 0)):
        evidence = json.loads((tmp_path / f"demo/reproductions/{name}.json").read_text(encoding="utf-8"))
        assert evidence["fois"] == 3
        assert evidence["casses"] == failures
        assert all(Path(trial["capture"]).is_file() for trial in evidence["essais"])
    assert (tmp_path / "demo/rapport.html").is_file()
    assert '"lang": "fr"' in (tmp_path / "demo/rapport.html").read_text(encoding="utf-8")
    # A second run must not silently overwrite evidence.
    assert cli("demo", "--output", tmp_path / "demo", "--lang", "fr").returncode != 0


def test_noninteractive_report_and_demo_require_explicit_language(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    (session / "journal.jsonl").write_text("", encoding="utf-8")
    result = cli("report", "--folder", session)
    assert result.returncode != 0 and "--lang" in result.stdout + result.stderr
    assert not (session / "rapport.html").exists()
    demo = tmp_path / "demo"
    result = cli("demo", "--output", demo)
    assert result.returncode != 0 and "--lang" in result.stdout + result.stderr
    assert not demo.exists()


def test_ci_gate_rejects_empty_assertions_without_contacting_target(tmp_path):
    scenario = tmp_path / "empty.json"
    scenario.write_text(json.dumps({"url": "http://127.0.0.1:1/", "steps": []}), encoding="utf-8")
    result = cli("replay", scenario, "--fail-on-bug", "--output", tmp_path / "results")
    assert result.returncode == 2
    assert "explicit assertion" in result.stderr
    assert not (tmp_path / "results").exists()


def test_local_concurrency_probe_has_isolated_trials_and_blocks_writes(tmp_path):
    class ProbeHandler(QuietHandler):
        posts = 0

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><body><input><img src='/x'><button></button>"
                             b"<script>fetch('/write',{method:'POST'}).catch(()=>{});</script></body></html>")

        def do_POST(self):
            type(self).posts += 1
            self.send_response(200)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), ProbeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        output = tmp_path / "probe"
        result = cli("probe", url, "--clients", "2", "--rounds", "2", "--output", output)
        assert result.returncode == 0, result.stdout + result.stderr
        evidence = json.loads((output / "probe.json").read_text(encoding="utf-8"))
        assert evidence["valid_count"] == 4 and evidence["inconclusive_count"] == 0
        assert evidence["http_error_count"] == 0 and evidence["median_ms"] >= 0
        assert evidence["attempts"][0]["review_signals"] == {"images_without_alt": 1, "inputs_without_label": 1, "buttons_without_name": 1}
        assert evidence["attempts"][0]["header_presence"]["content-security-policy"] is False
        assert (output / "screen.png").is_file()
        assert ProbeHandler.posts == 0
        assert cli("probe", url, "--output", output).returncode == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("url", ["http://example.com/", "http://127.0.0.2/", "http://user@localhost/", "file:///tmp/test"])
def test_probe_rejects_non_loopback_or_credential_urls_without_launching_browser(tmp_path, url):
    result = cli("probe", url, "--output", tmp_path / "probe")
    assert result.returncode == 2
    assert not (tmp_path / "probe").exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell integration runs on Windows")
def test_powershell_sheet_command_executes(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "FICHIER_ACTIF", tmp_path / "State's directory" / "active.json")
    result = subprocess.run(["powershell", "-NoProfile", "-Command", engine.sheet_command("powershell") + " help"],
        capture_output=True, text=True, encoding="utf-8", timeout=15,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr
    assert "click" in result.stdout


def test_managed_app_identity_survives_keep_app_and_stops_owned_tree(tmp_path):
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    command = [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"]
    app_command = subprocess.list2cmdline(command) if os.name == "nt" else shlex.join(command)
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    folder = tmp_path / "session"
    result = cli("launch", "--url", f"http://127.0.0.1:{port}/", "--folder", folder,
                 "--app-command", app_command, "--app-folder", Path(engine.__file__).parent / "demo",
                 "--app-wait", "10", env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    info = engine.lire_json(folder / "serveur.json")
    leader = dict(env, CHAOSFOLK_LEADER_TOKEN=info["jeton_chef"])
    try:
        assert info["app_identity"]["pid"] == info["app_pid"]
        assert info["app_identity"]["created"] > 0
        assert cli("stop", "--keep-app", env=leader).returncode == 0
        # Server shutdown completes asynchronously after its acknowledgement.
        import time
        active = Path(env["CHAOSFOLK_HOME"]) / "active.json"
        deadline = time.monotonic() + 10
        while active.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not active.exists()
        result = cli("stop-app", "--folder", folder, env=env)
        assert result.returncode == 0, result.stdout + result.stderr
        assert engine.lire_json(folder / "serveur.json")["app_pid"] is None
    finally:
        if (Path(env["CHAOSFOLK_HOME"]) / "active.json").exists():
            cli("stop", env=leader)
        current = engine.lire_json(folder / "serveur.json")
        if current.get("app_pid"):
            engine.stop_owned_process(current["app_identity"])


@pytest.fixture
def qa_app_url():
    handler = functools.partial(QuietHandler, directory=str(Path(__file__).parent / "qa_app"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def write_scenario(path, url, steps):
    path.write_text(json.dumps({"url": url, "steps": steps}, ensure_ascii=False), encoding="utf-8")
    return path


def reset_steps(email):
    return [{"n": 1, "action": "type", "target": {"role": "textbox", "name": "Adresse email"}, "args": {"text": email}},
            {"n": 2, "action": "click", "target": {"role": "button", "name": "Recevoir un lien"}, "args": {}}]


def test_compare_proves_account_enumeration_and_passes_a_neutral_reset(tmp_path, qa_app_url):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    known = write_scenario(scenarios / "known.json", qa_app_url + "reset.html", reset_steps("test-account@example.com"))
    unknown = write_scenario(scenarios / "unknown.json", qa_app_url + "reset.html", reset_steps("nobody-1@example.com"))
    result = cli("compare", known, unknown, "--times", "2", "--fail-on-bug")
    assert result.returncode == 1, result.stdout + result.stderr
    proof = json.loads((tmp_path / "reproductions" / "known-vs-unknown.json").read_text(encoding="utf-8"))
    assert (proof["mode"], proof["fois"], proof["casses"], proof["verdict"]) == ("traitement", 2, 2, "reproduit")
    assert any("Aucun compte" in reason for reason in proof["essais"][0]["raisons"])
    safe_known = write_scenario(scenarios / "safe-known.json", qa_app_url + "reset.html?safe", reset_steps("test-account@example.com"))
    safe_unknown = write_scenario(scenarios / "safe-unknown.json", qa_app_url + "reset.html?safe", reset_steps("nobody-1@example.com"))
    result = cli("compare", safe_known, safe_unknown, "--times", "2", "--fail-on-bug")
    assert result.returncode == 0, result.stdout + result.stderr


def test_vary_replays_catalog_values_and_writes_failing_variants(tmp_path, qa_app_url):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    scenario = write_scenario(scenarios / "signup.json", qa_app_url + "signup.html", [
        {"n": 1, "action": "type", "target": {"role": "textbox", "name": "Prénom"}, "args": {"text": "Zoé"}},
        {"n": 2, "action": "type", "target": {"role": "textbox", "name": "Téléphone"}, "args": {"text": "0639981234"}},
        {"n": 3, "action": "click", "target": {"role": "button", "name": "Créer mon compte"}, "args": {}}])
    values = json.dumps({"valid": ["0639981234", "06 39 98 12 34"], "invalid": ["0639"]})
    result = cli("vary", scenario, "--field", "Téléphone", "--values", values, "--fail-on-bug", "--name", "phone",
                 "--accept", '{"type": "text-visible", "text": "Bienvenue"}',
                 "--reject", '{"type": "text-visible", "text": "Numéro invalide"}', timeout=180)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((tmp_path / "reproductions" / "phone.json").read_text(encoding="utf-8"))
    verdicts = {row["value"]: row["verdict"] for row in report["valeurs"]}
    assert verdicts == {"0639981234": "pass", "06 39 98 12 34": "fail", "0639": "pass"}
    failing = next(row for row in report["valeurs"] if row["verdict"] == "fail")
    assert failing["invalid_fields"][0]["field"] == "Téléphone"
    variant = json.loads(Path(failing["scenario"]).read_text(encoding="utf-8"))
    assert variant["etapes"][1]["args"]["texte"] == "06 39 98 12 34"
    replay = cli("replay", failing["scenario"], "--times", "1", "--fail-on-bug")
    assert replay.returncode == 1, replay.stdout + replay.stderr


def test_persistence_recipes_expose_false_success_and_duplicates(tmp_path, qa_app_url):
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    steps = [{"n": 1, "action": "type", "target": {"role": "textbox", "name": "Titre"}, "args": {"text": "Réunion lundi"}},
             {"n": 2, "action": "click", "target": {"role": "button", "name": "Enregistrer"}, "args": {}}]
    expect = [{"type": "count", "text": "Réunion lundi", "exact": True, "equals": 1},
              {"type": "field-value", "field": "Titre", "value": "Réunion lundi"}]
    for name, query in (("lost", ""), ("kept", "?keep")):
        (scenarios / f"{name}.json").write_text(json.dumps({"url": qa_app_url + "notes.html" + query, "steps": steps,
                                                             "expect": expect}, ensure_ascii=False), encoding="utf-8")
    result = cli("replay", scenarios / "lost.json", scenarios / "kept.json", "--times", "1", "--persist", "reload,local-only,retry",
                 timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    verdicts = {path.stem: json.loads(path.read_text(encoding="utf-8"))["casses"] for path in (tmp_path / "reproductions").glob("*.json")}
    assert verdicts == {"lost-persist-reload-traitement": 1, "lost-persist-local-only-traitement": 1, "lost-persist-retry-traitement": 1,
                        "kept-persist-reload-traitement": 0, "kept-persist-local-only-traitement": 1, "kept-persist-retry-traitement": 1}


def test_coordinated_replay_shows_a_lost_update_between_two_sessions(tmp_path):
    class SharedNote(QuietHandler):
        note = "Initial"

        def do_GET(self):
            body = (b"<!doctype html><html lang=fr><body><label for=n>Note</label><input id=n>"
                    b"<button onclick=\"fetch('/save',{method:'POST',body:n.value}).then(()=>s.textContent='OK')\">Enregistrer</button>"
                    b"<p id=s role=status></p><script>fetch('/note').then(r=>r.text()).then(t=>n.value=t)</script></body></html>")
            if self.path == "/note":
                body = type(self).note.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            type(self).note = self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8")
            self.send_response(204)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), SharedNote)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        write = lambda who, text: [
            {"n": 1, "session": who, "action": "type", "target": {"role": "textbox", "name": "Note"}, "args": {"text": text}},
            {"n": 2, "session": who, "action": "click", "target": {"role": "button", "name": "Enregistrer"}, "args": {}}]
        scenario = tmp_path / "scenarios" / "two-editors.json"
        scenario.parent.mkdir()
        scenario.write_text(json.dumps({"url": url, "sessions": {"a": {}, "b": {}},
            "steps": [{"n": 0, "session": "b", "action": "wait", "args": {"seconds": 0}}] + write("a", "Texte de A") + write("b", "Texte de B")
                     + [{"n": 3, "session": "a", "action": "reload", "args": {}}],
            "expect": [{"type": "field-value", "session": "a", "field": "Note", "value": "Texte de A"}]}), encoding="utf-8")
        result = cli("replay", scenario, "--times", "1", "--fail-on-bug", timeout=180)
        assert result.returncode == 1, result.stdout + result.stderr
        proof = json.loads((tmp_path / "reproductions" / "two-editors-traitement.json").read_text(encoding="utf-8"))
        assert "Texte de B" in proof["essais"][0]["raisons"][0]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_audit_measures_layout_accessibility_resources_and_keyboard(tmp_path, qa_app_url):
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    folder = tmp_path / "session"
    assert cli("launch", "--url", qa_app_url + "ui.html", "--folder", folder, "--budget", "5", env=env).returncode == 0
    env["CHAOSFOLK_LEADER_TOKEN"] = json.loads((folder / "serveur.json").read_text(encoding="utf-8"))["jeton_chef"]
    try:
        (tmp_path / "scout.json").write_text('{"humains":[{"id":"e0","nom":"Scout"}]}', encoding="utf-8")
        assert cli("humans", tmp_path / "scout.json", env=env).returncode == 0
        result = cli("audit", "e0", "--viewports", "320x640,1440x900", "--keyboard", env=env, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        for signal in ("[layout-overflow] horizontal scrolling", "submit buttons outside the screen", "[target-size] 1 targets",
                       "controls without an accessible name", "low-contrast text", "broken images", "skipped heading levels",
                       "clickable-looking elements", "does not declare its language", "browser zoom is limited",
                       "no outline or shadow on focus"):
            assert signal in result.stdout, signal
        audit = json.loads((folder / "audits" / "ui-html.json").read_text(encoding="utf-8"))
        assert [v["viewport"] for v in audit["viewports"]] == ["320x640", "1440x900"]
        assert not audit["viewports"][1].get("horizontal_overflow")
        assert all(Path(v["screenshot"]).is_file() for v in audit["viewports"])
    finally:
        cli("stop", env=env)


def test_chaos_simulation_controls_and_request_exclusions(tmp_path, fixture_url):
    env = dict(os.environ, CHAOSFOLK_HOME=str(tmp_path / "state"))
    env.pop("CHAOSFOLK_LEADER_TOKEN", None)
    folder = tmp_path / "session"
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"dry_run": True, "max_active": 1, "exclude": {"routes": ["/index.html"]}}))
    launch = cli("launch", "--url", fixture_url, "--folder", folder, "--chaos-policy", policy, env=env)
    assert launch.returncode == 0, launch.stdout + launch.stderr
    leader = dict(env, CHAOSFOLK_LEADER_TOKEN=json.loads((folder / "serveur.json").read_text())["jeton_chef"])
    try:
        assert cli("chaos", "pause", env=env).returncode == 1
        personas = folder / "personas.json"
        personas.write_text('{"humains":[{"id":"h01","nom":"Alex"},{"id":"h02","nom":"Sam"}]}')
        assert cli("humans", personas, env=leader).returncode == 0
        # Simulation records intent without intercepting requests or producing real fault evidence.
        assert cli("fault", "http-error", "--humans", "h01", "--status", "503", env=leader).returncode == 0
        assert cli("inspect", "h01", "fetch('/index.html').then(r=>r.status)", env=leader).stdout.strip() == "200"
        events = [json.loads(line) for line in (folder / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
        assert any(e["type"] == "chaos-simulated" for e in events)
        assert not any(e["type"] == "panne-debut" for e in events)
        assert cli("chaos", "live", env=leader).returncode == 0
        assert cli("fault", "http-error", "--humans", "h01", "--status", "503", env=leader).returncode == 0
        assert cli("inspect", "h01", "fetch('/api/order').then(r=>r.status)", env=leader).stdout.strip() == "503"
        assert cli("inspect", "h01", "fetch('/index.html').then(r=>r.status)", env=leader).stdout.strip() == "200"
        assert cli("fault", "http-error", "--humans", "h02", "--status", "503", env=leader).returncode == 0
        plan = json.loads((folder / "chaos-plan.json").read_text())
        assert plan["faults"][-1]["reason"] == "max-active"
        assert cli("chaos", "pause", "--end-active", env=leader).returncode == 0
        assert cli("inspect", "h01", "fetch('/api/order').then(r=>r.status)", env=leader).stdout.strip() == "404"
        assert cli("fault", "http-error", "--humans", "h02", env=leader).returncode == 0
        plan = json.loads((folder / "chaos-plan.json").read_text())
        assert plan["faults"][-1]["reason"] == "injections-paused"
        assert cli("chaos", "inspect", "--folder", folder, env=env).returncode == 0
    finally:
        cli("stop", env=leader)
