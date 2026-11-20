"""Isolation of the simulated users and the guards around the journey guide.

Each test fails on the engine before these changes: a user could run any leader command through the one
command it was allowed, act in another user's browser, type an address on another origin, and so on.
"""
import argparse
import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from chaosfolk import branding, campaigns, chaos_jobs, cli, engine, planning, reproducibility, user
from chaosfolk.draw import tirer_horde
from chaosfolk.schema import normalize_scenario


@pytest.fixture
def user_env(monkeypatch):
    """`user.main` sets a state folder and a key in the environment: give both back after each test."""
    for name in ("CHAOSFOLK_HOME", "CHAOSFOLK_USER_KEY"):
        monkeypatch.setenv(name, "x")
        monkeypatch.delenv(name)
    monkeypatch.setattr(engine, "FICHIER_ACTIF", engine.FICHIER_ACTIF)


# --------------------------------------------------------------------------- one command for the users

LEADER_COMMANDS = sorted(engine.COMMANDES_CHEF | set(cli.EXTENSIONS) | cli.DIRECT_COMMANDS)


@pytest.mark.parametrize("command", LEADER_COMMANDS)
def test_the_user_entry_point_refuses_every_leader_command(command, user_env, capsys):
    assert user.main([command]) == 2
    assert "not a user action" in capsys.readouterr().err


def test_the_user_entry_point_never_starts_the_application_under_test(tmp_path):
    marker = tmp_path / "PWNED"
    for args in (["serve", "--url", "http://127.0.0.1:9/", "--folder", str(tmp_path), "--app-command", f'touch "{marker}"'],
                 ["launch"], ["replay"], ["integrations"], ["--state-dir", str(tmp_path), "regression"], ["../x"]):
        result = subprocess.run([sys.executable, "-m", "chaosfolk.user", *args], capture_output=True, text=True, timeout=60)
        assert result.returncode == 2, result.stderr
    assert not marker.exists()


def test_every_command_cli_answers_before_the_engine_is_refused_to_users():
    # A command added to cli.main must also be added to the lists user.py refuses: this fails until it is.
    answered = {name for name in re.findall(r'args\[0\] == "([^"]+)"', inspect.getsource(cli.main))
                if not name.startswith("-")}
    assert answered and answered <= cli.DIRECT_COMMANDS | set(cli.EXTENSIONS)


def test_the_user_key_must_be_a_session_key_shape(user_env):
    for args in (["--key", "not-a-key", "h01", "look"], ["--key", "a" * 32]):
        assert user.main(args) == 2


def test_the_sheet_command_calls_the_user_entry_point():
    # -P: the tested project, which is the working folder of the users, cannot shadow the module
    assert "-P -m chaosfolk.user" in engine.sheet_command("posix")
    assert "-P -m chaosfolk.user" in engine.sheet_command("powershell")


# --------------------------------------------------------------------------- one key per user

def test_a_user_cannot_act_for_another_user():
    horde = engine.Horde.__new__(engine.Horde)
    horde.jeton, horde.jeton_chef, horde.cle_seance = "user-token", "leader-token", "session-key"
    key = engine.cle_humain(horde.cle_seance, "h01")
    action = {"cmd": "action", "jeton": horde.jeton, "action": "done"}
    assert horde.autorise({**action, "h": "h01", "cle": key})
    assert not horde.autorise({**action, "h": "h02", "cle": key})
    assert not horde.autorise({**action, "h": "h01"})
    assert not horde.autorise({**action, "h": "h01", "cle": 7})
    assert horde.autorise({**action, "h": "h02", "jeton": horde.jeton_chef})
    assert key != engine.cle_humain(horde.cle_seance, "h02")
    assert "--key" in horde.refus_jeton({**action, "h": "h01"})


def test_a_session_without_keys_still_accepts_the_users_token():
    horde = engine.Horde.__new__(engine.Horde)
    horde.jeton, horde.jeton_chef = "user-token", "leader-token"
    assert horde.autorise({"cmd": "action", "jeton": "user-token", "h": "h01"})


def test_the_fault_plan_and_the_leader_commands_need_the_leader_token():
    assert {"faults", "fault", "fault-end", "save-state", "humans", "stop"} <= engine.COMMANDES_RESERVEES


def _fake_connection(sent):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def sendall(self, data):
            sent.append(json.loads(data))
            self.replied = False

        def recv(self, _size):
            if self.replied:
                return b""
            self.replied = True
            return b'{"ok": true, "texte": ""}\n'
    return Connection


def test_the_client_sends_the_user_key_or_the_leader_token(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(engine, "info_serveur", lambda: {"port": 1, "jeton": "user-token", "dossier": str(tmp_path)})
    monkeypatch.setattr(engine.socket, "create_connection", lambda *_args, **_kwargs: _fake_connection(sent)())
    engine.ecrire_json(tmp_path / "serveur.json", {"jeton_chef": "leader-token"})
    monkeypatch.setenv("CHAOSFOLK_USER_KEY", "k" * 32)
    monkeypatch.delenv("CHAOSFOLK_LEADER_TOKEN", raising=False)
    engine.envoyer({"cmd": "action", "h": "h01", "action": "look"})
    assert (sent[-1]["jeton"], sent[-1]["cle"]) == ("user-token", "k" * 32)
    # the coordinator plays any user, the scout included, with its token alone
    monkeypatch.setenv("CHAOSFOLK_LEADER_TOKEN", "leader-token")
    monkeypatch.delenv("CHAOSFOLK_USER_KEY")
    engine.envoyer({"cmd": "action", "h": "e0", "action": "look"})
    assert sent[-1]["jeton"] == "leader-token"
    # a wrong token is never sent in its place
    monkeypatch.setenv("CHAOSFOLK_LEADER_TOKEN", "guess")
    engine.envoyer({"cmd": "action", "h": "e0", "action": "look"})
    assert sent[-1]["jeton"] == "user-token"


def test_a_sheet_carries_the_key_of_its_user_and_single_quotes(tmp_path):
    personas, _ = tirer_horde("ux", 2, ["Create a project"], 42, {"nom": "Demo"})
    engine.ecrire_json(tmp_path / "personas.json", personas)
    engine.ecrire_json(tmp_path / "serveur.json", {"cle_seance": "a" * 64})
    opts = argparse.Namespace(dossier=str(tmp_path), donnees="Fake names", interdits="External actions", budget=20,
                              shell="posix")
    assert engine.commande_fiches(opts) == 0
    keys = set()
    for human in personas["humains"]:
        sheet = (tmp_path / "fiches" / f"{human['id']}.md").read_text(encoding="utf-8")
        key = engine.cle_humain("a" * 64, human["id"])
        keys.add(key)
        assert f"--key {key}" in sheet and "chaosfolk.user" in sheet
        # a promo code between double quotes would be expanded by the shell: the sheet teaches single quotes
        assert "--thought 'short reaction'" in sheet and '--thought "' not in sheet
        assert "{apostrophe}" not in sheet and "'it'\\''s blocked'" in sheet
    assert len(keys) == 2


def test_a_sheet_without_a_running_session_has_no_key(tmp_path, capsys):
    personas, _ = tirer_horde("ux", 1, ["Create a project"], 42, {"nom": "Demo"})
    engine.ecrire_json(tmp_path / "personas.json", personas)
    opts = argparse.Namespace(dossier=str(tmp_path), donnees="Fake names", interdits="External actions", budget=20,
                              shell="powershell")
    assert engine.commande_fiches(opts) == 0
    assert "--key" not in (tmp_path / "fiches/h01.md").read_text(encoding="utf-8")
    assert "sans --key" in capsys.readouterr().out
    assert "''" in (tmp_path / "fiches/h01.md").read_text(encoding="utf-8")  # PowerShell doubles the apostrophe


# --------------------------------------------------------------------------- what a user may do

def test_goto_and_tab_stay_on_the_tested_origin():
    engine.charger_moteur()
    base = "http://127.0.0.1:5180/"
    assert engine.adresse_http("/offers", base, meme_origine=True) == "http://127.0.0.1:5180/offers"
    for url in ("https://example.invalid/?d=1", "http://127.0.0.1:5181/", "//example.invalid/x", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            engine.adresse_http(url, base, meme_origine=True)
    # an address the app itself provides (a start address, a redirect) is not typed by a user
    assert engine.adresse_http("https://example.invalid/", base) == "https://example.invalid/"


def test_a_page_cannot_fill_the_disk_with_downloads(tmp_path):
    events, saved, cancelled = [], [], []
    world = engine.Monde.__new__(engine.Monde)
    world.id, world.dossier, world.messages = "h01", tmp_path, []
    world.journal = events.append
    world._record_evidence = lambda add, text: add(text)

    class Download:
        suggested_filename = "report.csv"

        async def save_as(self, destination):
            saved.append(destination)

        async def cancel(self):
            cancelled.append(1)

    async def play():
        for _ in range(engine.TELECHARGEMENTS_MAX + 5):
            await world._telechargement(Download())

    asyncio.run(play())
    assert len(saved) == engine.TELECHARGEMENTS_MAX and len(cancelled) == 5
    assert sum(1 for event in events if event.get("refuse")) == 5


def test_save_state_refuses_a_path_under_uploads(tmp_path):
    fake = SimpleNamespace(humains={"h01": object()}, dossier=tmp_path, verrous={})
    reply = asyncio.run(engine.Horde.sauver_etat(fake, {"h": "h01", "fichier": "uploads/state.json"}))
    assert reply["ok"] is False and "uploads" in reply["texte"]
    assert not (tmp_path / "uploads").exists()


# --------------------------------------------------------------------------- report, scenario, jobs

def _empty_session(folder, config, constats=None):
    (folder / "journal.jsonl").write_text("", encoding="utf-8")
    (folder / "config.json").write_text(json.dumps(config), encoding="utf-8")
    if constats is not None:
        (folder / "constats.json").write_text(json.dumps(constats), encoding="utf-8")


def test_the_report_leaves_out_the_startup_command(tmp_path):
    # --app-command can carry a secret and a report is shared
    _empty_session(tmp_path, {"nom": "Trial", "url": "http://127.0.0.1:5180/",
                              "app_commande": "TOKEN=value-never-to-share npm start"})
    engine.rapport(tmp_path)
    html = (tmp_path / "rapport.html").read_text(encoding="utf-8")
    assert "http://127.0.0.1:5180/" in html
    assert "value-never-to-share" not in html and "app_commande" not in html


def test_a_summarised_proof_outside_the_session_is_not_read(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    _empty_session(session, {})
    (tmp_path / "outside.json").write_text('{"scenario":"SCENARIO-OUTSIDE.json"}', encoding="utf-8")
    (session / "inside.json").write_text('{"scenario":"scenario-of-the-session.json"}', encoding="utf-8")
    findings = {"constats": [
        {"id": "c1", "titre": "Up", "evenements": [], "preuves": {"replay": {"source": "../outside.json"}}},
        {"id": "c2", "titre": "Absolute", "evenements": [],
         "preuves": {"replay": {"source": str(tmp_path / "outside.json")}}},
        {"id": "c3", "titre": "Inside", "evenements": [], "preuves": {"replay": {"source": "inside.json"}}}]}
    (session / "constats.json").write_text(json.dumps(findings), encoding="utf-8")
    engine.rapport(session)
    html = (session / "rapport.html").read_text(encoding="utf-8")
    assert "scenario-of-the-session.json" in html
    assert "SCENARIO-OUTSIDE" not in html


@pytest.mark.skipif(os.name == "nt", reason="symbolic links need a privilege on Windows")
def test_report_assets_are_not_written_through_a_link(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep", encoding="utf-8")
    session = tmp_path / "session"
    (session / "assets").mkdir(parents=True)
    (session / "assets" / "room.js").symlink_to(victim)
    branding.report_branding(session)
    assert victim.read_text(encoding="utf-8") == "keep"
    assert (session / "assets" / "room.js").read_text(encoding="utf-8") != "keep"
    elsewhere, linked = tmp_path / "elsewhere", tmp_path / "linked"
    elsewhere.mkdir()
    linked.mkdir()
    (linked / "assets").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError):
        branding.report_branding(linked)
    assert list(elsewhere.iterdir()) == []


def test_a_scenario_start_must_be_http():
    base = {"url": "http://127.0.0.1:5180/", "steps": []}
    for start in ("/offers", "http://127.0.0.1:5180/quote", "https://staging.example.invalid/", None, ""):
        assert normalize_scenario({**base, "start": start}).get("depart") == start
    for start in ("file:///etc/hosts", "javascript:alert(1)", "data:text/html,x", "view-source:http://127.0.0.1/", 7):
        with pytest.raises(ValueError):
            normalize_scenario({**base, "start": start})
        with pytest.raises(ValueError):
            normalize_scenario({**base, "sessions": {"admin": {"start": start}}})


def test_a_scheduled_job_is_always_registered_disabled(tmp_path):
    job = chaos_jobs.validate_job({"name": "nightly", "argv": [sys.executable, "-c", "pass"], "max_runs": 3,
                                   "environment": "local", "enabled": True}, tmp_path)
    assert job["enabled"] is False


# --------------------------------------------------------------------------- git and hooks

GIT = shutil.which("git")
GIT_ENV = {name: value for name, value in os.environ.items()
           if name not in ("GIT_NO_LAZY_FETCH", "GIT_ALLOW_PROTOCOL", "GIT_DIR", "GIT_WORK_TREE")}
GIT_ENV.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT="0",
               GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
               GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
TRAPS = ("transport ext", "uploadpack", "sshCommand")


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "commit.gpgsign=false", *args], check=True,
                          capture_output=True, text=True, env=GIT_ENV).stdout.strip()


def _trapped_repo(base, trap, name):
    """A repository that declares itself a partial clone: a missing tree must come from a command it names."""
    repo = base / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a.py").write_text("print('one')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    (repo / "a.py").write_text("print('two')\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "two")
    marker = base / f"MARKER-{name}"
    tree = _git(repo, "rev-parse", "HEAD~1^{tree}")
    (repo / ".git" / "objects" / tree[:2] / tree[2:]).unlink()
    _git(repo, "config", "extensions.partialClone", "origin")
    _git(repo, "config", "remote.origin.promisor", "true")
    if trap == "transport ext":
        _git(repo, "config", "remote.origin.url", "ext::sh -c touch%% %s" % str(marker).replace(" ", "% "))
        _git(repo, "config", "protocol.ext.allow", "always")
    elif trap == "uploadpack":
        source = base / f"source-{name}"
        source.mkdir()
        _git(source, "init", "-q", "--bare")
        _git(repo, "config", "remote.origin.url", str(source))
        _git(repo, "config", "remote.origin.uploadpack", f"touch '{marker}'; git-upload-pack")
        _git(repo, "config", "protocol.file.allow", "always")
    else:
        _git(repo, "config", "remote.origin.url", "ssh://example.invalid/x.git")
        _git(repo, "config", "core.sshCommand", f"touch '{marker}'; false")
    return repo, marker


@pytest.mark.skipif(not GIT or os.name == "nt", reason="traps are written for sh and need git")
@pytest.mark.parametrize("trap", TRAPS)
def test_git_never_runs_a_command_declared_by_a_received_repository(tmp_path, trap):
    repo, marker = _trapped_repo(tmp_path, trap, "control")
    subprocess.run(["git", "-C", str(repo), "diff", "--name-status", "HEAD~1", "--"], capture_output=True,
                   env=GIT_ENV, timeout=60)
    if not marker.exists():
        pytest.skip("this git does not fetch missing objects: the trap is inactive")
    repo, marker = _trapped_repo(tmp_path, trap, "engine")
    with patch.dict(os.environ, GIT_ENV, clear=True), pytest.raises(ValueError):
        planning.changed_files(repo, "HEAD~1")
    assert not marker.exists(), f"planning ran the command the repository declares ({trap})"


def test_every_git_caller_uses_the_protected_environment(monkeypatch, tmp_path):
    seen = []

    def fake_run(command, **kwargs):
        seen.append(kwargs.get("env"))
        return SimpleNamespace(stdout="abc\n", returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    campaigns.git_revision(tmp_path)
    reproducibility.git_identity(tmp_path)
    assert len(seen) >= 2
    for env in seen:
        assert env and env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_ALLOW_PROTOCOL"] == ":"


def test_reproducibility_hooks_do_not_inherit_the_leader_token(monkeypatch, tmp_path):
    monkeypatch.setenv("CHAOSFOLK_LEADER_TOKEN", "leader-secret")
    code = "import json, os; print(json.dumps({'leader': 'CHAOSFOLK_LEADER_TOKEN' in os.environ}))"
    result = asyncio.run(reproducibility._hook({"command": [sys.executable, "-c", code], "timeout": 30}, tmp_path, True))
    assert result == {"leader": False}


# --------------------------------------------------------------------------- journey guide support

@pytest.mark.parametrize("value, expected", [(None, 60), (600, 600.0), ("90", 90.0), (1, 1.0), (1800, 1800.0)])
def test_a_sheet_can_raise_the_cumulative_wait(value, expected):
    assert engine.lire_attente_max(value) == expected


@pytest.mark.parametrize("value", [0, 0.5, 1801, -5, True, "slow", [], {}])
def test_a_bad_cumulative_wait_is_refused(value):
    with pytest.raises(ValueError, match="attente_max"):
        engine.lire_attente_max(value)


def test_the_wait_limit_belongs_to_each_user():
    slow = SimpleNamespace(attente=0.0, attente_max=25)
    assert [engine.Horde._borner_attente(slow, {"secondes": 10})["secondes"] for _ in range(3)] == [10, 10, 5]
    horde = engine.Horde.__new__(engine.Horde)
    horde.audit_session, horde.lance_a, horde.duree_max = None, 0, 0
    human = SimpleNamespace(statut="actif", duree=None, debut_reel=None, budget=None, n_gestes=0, bloque_jusqua=0,
                            dernier_inutile=False, repetitions=0, dernier_cle=None, attente=60.0, attente_max=600.0)
    assert horde.garde_fou(human, "wait", {}) is None
    human.attente, human.attente_max = 60.0, engine.ATTENTE_MAX
    assert "attendu" in horde.garde_fou(human, "wait", {})


def test_draw_keeps_the_hand_written_users(tmp_path):
    engine.ecrire_json(tmp_path / "personas.json",
                       {"humains": [{"id": "t01", "nom": "Tester", "intention": "Play M01"}]})
    for seed in ("42", "43"):
        assert engine.principal(["draw", "--objectives", "Explore", "--folder", str(tmp_path), "--level", "low",
                                 "--seed", seed]) == 0
        ids = [human["id"] for human in json.loads((tmp_path / "personas.json").read_text(encoding="utf-8"))["humains"]]
        assert ids.count("t01") == 1 and "h01" in ids
    assert len(ids) == len(set(ids))


def test_the_sheet_asks_for_the_journey_and_reports_values_chosen_for_the_user(tmp_path):
    personas, _ = tirer_horde("ux", 1, ["Create a project"], 42, {"nom": "Demo"})
    engine.ecrire_json(tmp_path / "personas.json", personas)
    opts = argparse.Namespace(dossier=str(tmp_path), donnees="Fake names", interdits="External actions", budget=20,
                              shell="posix")
    assert engine.commande_fiches(opts) == 0
    sheet = (tmp_path / "fiches/h01.md").read_text(encoding="utf-8")
    assert "switch in the middle" in sheet and "a value chosen for you without being asked is reported" in sheet
