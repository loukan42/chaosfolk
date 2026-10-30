"""Regression tests for the October 2026 security review (see docs/security.md)."""
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

import pytest

from chaosfolk import audit, audit_dashboard, campaigns, chaos, engine, install, planning, privacy, reporting
from chaosfolk.audit_session import Session
from chaosfolk.cli import main as cli_main


@pytest.mark.parametrize("name", ["../escape", "a/b", "a\\b", "", "x" * 65, 5, "-dash", ".hidden"])
def test_audit_names_cannot_leave_the_session_folder(name):
    with pytest.raises(ValueError):
        audit.validate_name(name)


def test_audit_names_and_viewports_accept_portable_values():
    assert audit.validate_name(None) is None
    assert audit.validate_name("Orders_page-1") == "Orders_page-1"
    assert audit.validate_viewports([[320, 640], (1440, 900)]) == [(320, 640), (1440, 900)]
    for sizes in ([[320]], [["320", "640"]], [[50, 50]], [[320, 640]] * 9, "320x640", [[True, 640]]):
        with pytest.raises(ValueError):
            audit.validate_viewports(sizes)


def test_tokens_compare_in_constant_time_and_reject_non_strings():
    assert engine.jeton_egal("abc", "abc")
    assert not engine.jeton_egal("abd", "abc")
    assert not engine.jeton_egal("ab", "abc")
    for candidate in (None, 1, [], {"a": 1}, b"abc"):
        assert not engine.jeton_egal(candidate, "abc")
    horde = SimpleNamespace(jeton="user-token", jeton_chef="leader-token")
    assert engine.Horde.autorise(horde, {"cmd": "look", "jeton": "user-token"})
    assert not engine.Horde.autorise(horde, {"cmd": "release", "jeton": "user-token"})
    assert engine.Horde.autorise(horde, {"cmd": "release", "jeton": "leader-token"})
    assert not engine.Horde.autorise(horde, {"cmd": "release", "jeton": ["leader-token"]})
    assert not engine.Horde.autorise(horde, {"cmd": "look"})


@pytest.mark.parametrize("suggested, expected", [
    ("../../evil.txt", "evil.txt"), ("..\\..\\evil.txt", "evil.txt"), ("report.pdf", "report.pdf"),
    ("", "download"), (None, "download"), ("..", "download"), (" . ", "download"), ("a" * 300, "a" * 150),
])
def test_download_names_are_reduced_to_a_base_name(suggested, expected):
    assert engine.nom_de_fichier_sur(suggested) == expected


def test_reachability_check_does_not_follow_redirects():
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/leak":
                self.send_response(200)
                self.end_headers()
                return
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/leak")
            self.end_headers()

        def log_message(self, *_):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        engine.charger_moteur()
        assert engine.url_repond(f"http://127.0.0.1:{server.server_port}/start") is True
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
    assert hits == ["/start"]


@pytest.mark.parametrize("text, forbidden", [
    ("Set-Cookie: sid=abc123; Path=/; HttpOnly", "abc123"),
    ("request failed: Authorization: Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ==", "QWxhZGRpbj"),
    ("token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", "eyJzdWIi"),
    ("password=hunter2&remember=1", "hunter2"),
    ("login error for password=hunter2 user", "hunter2"),
    ("x-api-key: 1234567890abcdef", "1234567890abcdef"),
])
def test_sanitize_redacts_credentials_without_a_url(text, forbidden):
    redacted = privacy.sanitize(text)
    assert forbidden not in redacted
    assert "[redacted]" in redacted


def test_sanitize_keeps_ordinary_text_and_parameters():
    url = "https://app.test/items?page=2&sort=name"
    assert privacy.sanitize(url) == url
    assert privacy.sanitize("sort=name&page=2") == "sort=name&page=2"
    assert privacy.sanitize("The cookie banner was accepted") == "The cookie banner was accepted"


def test_show_password_fields_are_masked_everywhere():
    assert 'input[autocomplete="current-password"]' in privacy.MASKS
    assert 'input[autocomplete="new-password"]' in privacy.MASKS
    script = (Path(engine.__file__).parent / "screen.js").read_text(encoding="utf-8")
    assert "estSecret" in script and "new-password" in script


def test_reports_mask_typed_secrets_while_the_private_journal_keeps_them(tmp_path):
    shutil.copyfile(Path(engine.__file__).parent / "templates/mascot.png", tmp_path / "shot.png")
    engine.ecrire_json(tmp_path / "personas.json", {"humains": [{"id": "h01", "nom": "Alex", "appareil": "desktop"}]})
    engine.ecrire_json(tmp_path / "constats.json", {"constats": []})
    events = [
        {"type": "action", "h": "h01", "n": 1, "t": 1000, "action": "type", "resultat": "ok", "capture": "shot.png",
         "cible": {"nom": "Password", "sensitive": True}, "url": "http://localhost/login", "args": {"texte": "s3cret-value"}},
        {"type": "action", "h": "h01", "n": 2, "t": 2000, "action": "type", "resultat": "ok", "capture": "shot.png",
         "cible": {"nom": "Search"}, "url": "http://localhost/", "args": {"texte": "visible-query"}},
    ]
    (tmp_path / "journal.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    engine.rapport(tmp_path)
    assert "s3cret-value" in (tmp_path / "journal.jsonl").read_text(encoding="utf-8")
    for path in tmp_path.rglob("*"):
        if path.suffix in {".html", ".js"} and path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "s3cret-value" not in text, path.name
    report = (tmp_path / "report-en.html").read_text(encoding="utf-8")
    assert "visible-query" in report and "[masked]" in report
    assert "Content-Security-Policy" in report


def test_write_reports_rejects_unknown_languages(tmp_path):
    with pytest.raises(ValueError, match="en or fr"):
        reporting.write_reports(tmp_path, "<html lang=\"en\"></html>", {}, [], 'en"><script>')


def test_campaign_evidence_paths_stay_inside_the_session(tmp_path):
    session = tmp_path / "session"
    (session / "reproductions").mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"nom": "x", "verdict": "reproduit", "scenario": str(outside)}), encoding="utf-8")
    inside = session / "reproductions" / "save.json"
    inside.write_text(json.dumps({"nom": "save", "verdict": "reproduit"}), encoding="utf-8")
    assert campaigns.inside(session, "reproductions/save.json") == inside.resolve()
    assert campaigns.inside(session, str(inside)) == inside.resolve()
    for path in ("../outside.json", str(outside), "", None, 3, "C:/Windows/system.json", "/etc/passwd"):
        assert campaigns.inside(session, path) is None
    assert campaigns.proof_summary(session, "../outside.json") is None
    assert campaigns.proof_summary(session, "reproductions/save.json")["verdict"] == "reproduit"


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_planning_git_never_runs_commands_configured_by_the_repository(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "config", "user.name", "Synthetic Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / "a.txt").write_text("original", encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Fixture")
    marker = repo / "fsmonitor-ran"
    python = sys.executable.replace("\\", "/")
    git(repo, "config", "core.fsmonitor", f"{python} -c \"open('{marker.as_posix()}','w').close()\"")
    git(repo, "config", "diff.external", f"{python} -c \"open('{marker.as_posix()}','w').close()\"")
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    assert planning.changed_files(repo, "HEAD")
    assert not marker.exists()
    with pytest.raises(ValueError) as error:
        planning.git(repo, "rev-parse", "--verify", "no-such-revision^{commit}")
    assert "\n" not in str(error.value) and len(str(error.value)) <= 200


def test_hooks_and_runners_do_not_inherit_the_leader_token(monkeypatch):
    monkeypatch.setenv("CHAOSFOLK_LEADER_TOKEN", "leader-secret")
    monkeypatch.setenv("CHAOS_KEEP", "kept")
    env = chaos.hook_environment()
    assert "CHAOSFOLK_LEADER_TOKEN" not in env and env["CHAOS_KEEP"] == "kept"
    assert "CHAOSFOLK_LEADER_TOKEN" not in chaos.hook_environment({"CHAOSFOLK_LEADER_TOKEN": "x", "PATH": "p"})
    import asyncio
    code, output = asyncio.run(chaos.execute(
        [sys.executable, "-c", "import os; print(sorted(k for k in os.environ if k.startswith('CHAOSFOLK_LEADER')))"],
        {}, 20, capture=True))
    assert code == 0 and output == "[]"


def test_dashboard_errors_do_not_echo_local_details(tmp_path):
    assert audit_dashboard.client_message(ValueError("Choose a known check")) == "Choose a known check"
    assert "private" not in audit_dashboard.client_message(OSError("C:/private/session/state.sqlite3"))
    assert "snapshot()" not in audit_dashboard.client_message(TypeError("snapshot() got an unexpected keyword"))
    session = Session(tmp_path)
    session.create("quick")
    server = audit_dashboard.make_server(session, token="test-token")
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(Request(base + "/", headers={"Authorization": "Bearer test-token"}), timeout=5) as response:
            assert response.headers["Server"] == "chaosfolk"
            assert "Python" not in response.headers["Server"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)


def test_setup_skips_a_link_to_another_skill(tmp_path):
    other = tmp_path / "other-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("---\nname: something-else\n---\n", encoding="utf-8")
    target = tmp_path / "linked"
    try:
        target.symlink_to(other, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires permission on this host")
    assert install.copy_skill(install.skill_source(), target).startswith("skipped")
    assert target.is_symlink()
    assert "something-else" in (other / "SKILL.md").read_text(encoding="utf-8")


def test_install_browser_accepts_known_flags_only(capsys):
    assert cli_main(["install-browser", "--help"]) == 2
    assert cli_main(["install-browser", "--with-deps", "--chromium-channel"]) == 2
    assert "accepts only" in capsys.readouterr().err


def test_visual_compare_refuses_large_images_before_decoding(tmp_path, monkeypatch):
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from chaosfolk import visual
    big = tmp_path / "big.png"
    Image.new("1", (30000, 1000)).save(big)
    small = tmp_path / "small.png"
    Image.new("RGB", (4, 4)).save(small)
    monkeypatch.setattr(Image.Image, "convert", lambda *a, **k: pytest.fail("decoded before the size check"))
    with pytest.raises(ValueError, match="20 million"):
        visual.compare(big, small, tmp_path / "out")
    assert PIL is not None


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_state_directories_are_owner_only(tmp_path):
    from chaosfolk import private_state
    target = tmp_path / "home" / ".chaosfolk" / "active.json"
    private_state.write_json(target, {"port": 1})
    assert (target.parent.stat().st_mode & 0o077) == 0
    assert (target.stat().st_mode & 0o077) == 0


def test_install_scripts_pin_the_released_version():
    from chaosfolk import __version__
    root = Path(__file__).resolve().parents[1]
    shell = (root / "install.sh").read_text(encoding="utf-8")
    powershell = (root / "install.ps1").read_text(encoding="utf-8")
    assert f'VERSION="${{CHAOSFOLK_VERSION:-{__version__}}}"' in shell
    assert f"else {{ '{__version__}' }}" in powershell
    assert "refs/heads/main" not in shell and "refs/heads/main" not in powershell
    assert "CHAOSFOLK_SHA256" in shell and "CHAOSFOLK_SHA256" in powershell
