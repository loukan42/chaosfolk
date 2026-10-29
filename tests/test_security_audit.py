"""Regression cases from the security and reliability audit."""
import io
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from chaosfolk import install, integrations, mcp_server, privacy


@pytest.mark.parametrize("name", [[], {}, ["list_findings"], None, 1, True])
def test_mcp_invalid_tool_names_do_not_terminate_stdio(tmp_path, name):
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name}},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    ]
    incoming = io.BytesIO("\n".join(json.dumps(request) for request in requests).encode())
    outgoing = io.StringIO()
    assert mcp_server.serve(tmp_path, incoming, outgoing) == 0
    replies = [json.loads(line) for line in outgoing.getvalue().splitlines()]
    assert replies[1]["error"]["code"] == -32602
    assert replies[2] == {"jsonrpc": "2.0", "id": 3, "result": {}}


@pytest.mark.parametrize("content", [
    "---\nname: chaosfolk-other\n---\n",
    "---\nname: other\n---\nExample: name: chaosfolk\n",
    "name: chaosfolk\n",
    "---\nname: chaosfolk\nname: other\n---\n",
])
def test_setup_does_not_delete_skills_with_similar_names(tmp_path, content):
    target = tmp_path / "chaosfolk"
    target.mkdir()
    (target / "SKILL.md").write_text(content, encoding="utf-8")
    marker = target / "custom.txt"
    marker.write_text("Keep this customization", encoding="utf-8")
    result = install.copy_skill(install.skill_source(), target)
    assert result.startswith("skipped:")
    assert marker.read_text(encoding="utf-8") == "Keep this customization"
    assert (target / "SKILL.md").read_text(encoding="utf-8") == content


@pytest.mark.parametrize("name", ["chaosfolk", '"chaosfolk"', "'chaosfolk'"])
def test_skill_identity_accepts_exact_frontmatter_names(tmp_path, name):
    (tmp_path / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8-sig")
    assert install.is_chaosfolk(tmp_path)


def installed_skill(tmp_path):
    target = tmp_path / "chaosfolk"
    target.mkdir()
    (target / "SKILL.md").write_text("---\nname: chaosfolk\n---\nOld version", encoding="utf-8")
    (target / "custom.txt").write_text("Keep until update succeeds", encoding="utf-8")
    return target


def test_skill_update_copy_failure_keeps_previous_version(tmp_path, monkeypatch):
    target = installed_skill(tmp_path)
    copy = install.shutil.copyfile

    def fail_mid_copy(source, destination):
        if Path(source).name == "LICENSE":
            raise OSError("disk full")
        return copy(source, destination)

    monkeypatch.setattr(install.shutil, "copyfile", fail_mid_copy)
    with pytest.raises(OSError, match="disk full"):
        install.copy_skill(install.skill_source(), target)
    assert "Old version" in (target / "SKILL.md").read_text(encoding="utf-8")
    assert (target / "custom.txt").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["chaosfolk"]


def test_skill_update_publish_failure_rolls_back(tmp_path, monkeypatch):
    target = installed_skill(tmp_path)
    replace = Path.replace

    def fail_publish(path, destination):
        if path.name == "new":
            raise OSError("publish failed")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_publish)
    with pytest.raises(OSError, match="publish failed"):
        install.copy_skill(install.skill_source(), target)
    assert "Old version" in (target / "SKILL.md").read_text(encoding="utf-8")
    assert (target / "custom.txt").exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["chaosfolk"]


def test_skill_update_retains_backup_when_rollback_also_fails(tmp_path, monkeypatch):
    target = installed_skill(tmp_path)
    replace = Path.replace

    def fail_publish_and_restore(path, destination):
        if path.name in {"new", "previous"}:
            raise OSError("directory locked")
        return replace(path, destination)

    monkeypatch.setattr(Path, "replace", fail_publish_and_restore)
    with pytest.raises(OSError, match="backup kept at"):
        install.copy_skill(install.skill_source(), target)
    backup = next(tmp_path.glob(".chaosfolk-setup-*/previous"))
    assert "Old version" in (backup / "SKILL.md").read_text(encoding="utf-8")
    assert (backup / "custom.txt").exists()


def test_skill_update_replaces_link_without_deleting_its_destination(tmp_path):
    linked_source = installed_skill(tmp_path)
    target = tmp_path / "linked"
    try:
        target.symlink_to(linked_source, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symbolic links requires permission on this host")
    assert install.copy_skill(install.skill_source(), target).startswith("installed")
    assert not target.is_symlink()
    assert "Old version" in (linked_source / "SKILL.md").read_text(encoding="utf-8")
    assert (linked_source / "custom.txt").exists()


@pytest.mark.parametrize("parameter", [
    "refresh_token", "id_token", "client_secret", "api-key", "access%5Ftoken",
    "code", "session_id", "EMAIL",
])
@pytest.mark.parametrize("delimiter", ["?", "#", "#page=1&"])
def test_sanitize_query_and_fragment_credentials(parameter, delimiter):
    url = f"https://app.test/callback{delimiter}{parameter}=sensitive-value&view=list"
    redacted = privacy.sanitize(url)
    assert "sensitive-value" not in redacted
    assert redacted.endswith(f"{parameter}=[redacted]&view=list")


def test_sanitize_url_userinfo_preserves_non_sensitive_parameters():
    url = "https://alice:password@app.test/items?page=2&sort=name"
    assert privacy.sanitize(url) == "https://[redacted]@app.test/items?page=2&sort=name"


@pytest.mark.parametrize("url,expected", [
    ("wss://user:pw@host/socket", "wss://[redacted]@host/socket"),
    ("postgres://admin:hunter2@db.internal:5432/app", "postgres://[redacted]@db.internal:5432/app"),
    ("redis://:s3cret@cache:6379/0", "redis://[redacted]@cache:6379/0"),
    ("DATABASE_URL=mongodb+srv://app:pw@cluster.example.net/db", "DATABASE_URL=mongodb+srv://[redacted]@cluster.example.net/db"),
])
def test_sanitize_userinfo_in_any_scheme(url, expected):
    assert privacy.sanitize(url) == expected


@pytest.mark.parametrize("parameter", [
    "X-Amz-Signature", "X-Amz-Credential", "x-amz-security-token", "sig", "Signature", "pwd", "pass", "auth",
    "key", "apikey", "access_key", "otp", "SAMLResponse", "assertion", "private_key",
])
def test_sanitize_redacts_whole_credential_parameter_names(parameter):
    redacted = privacy.sanitize(f"https://files.test/report.pdf?{parameter}=sensitive-value&expires=60")
    assert redacted == f"https://files.test/report.pdf?{parameter}=[redacted]&expires=60"


@pytest.mark.parametrize("parameter", ["keyword", "passage", "author", "signal", "page"])
def test_sanitize_keeps_parameters_that_merely_contain_a_credential_name(parameter):
    url = f"https://app.test/search?{parameter}=public-value"
    assert privacy.sanitize(url) == url


@pytest.mark.parametrize("text,expected", [
    ('href="https://h/?token=abc"', 'href="https://h/?token=[redacted]"'),
    ("[link](https://h/?sig=abc)", "[link](https://h/?sig=[redacted])"),
    ('{\\"url\\": \\"https://h/?pwd=abc\\"}', '{\\"url\\": \\"https://h/?pwd=[redacted]\\"}'),
    ("<a href='https://h/?key=abc'>", "<a href='https://h/?key=[redacted]'>"),
])
def test_sanitize_keeps_the_closing_delimiter_after_a_redacted_value(text, expected):
    assert privacy.sanitize(text) == expected


def test_public_export_removes_oauth_secrets_and_preserves_source(tmp_path):
    source, destination = tmp_path / "session", tmp_path / "public"
    source.mkdir()
    (source / "constats.json").write_text('{"constats": []}', encoding="utf-8")
    event = {"type": "action", "h": "A", "n": 1, "args": ["private-input"], "ecran": "private-screen"}
    (source / "journal.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    config = {"url": "https://app.test/callback#id_token=private-token&view=list"}
    original = json.dumps(config)
    (source / "config.json").write_text(original, encoding="utf-8")
    privacy.export_report(source, destination, "en")
    assert (source / "config.json").read_text(encoding="utf-8") == original
    for exported in destination.iterdir():
        if exported.is_file():
            text = exported.read_text(encoding="utf-8")
            assert not any(secret in text for secret in ("private-token", "private-input", "private-screen"))


def test_external_runner_drains_output_and_reads_completed_results(tmp_path):
    script = tmp_path / "runner.py"
    script.write_text(
        "import json, os\nfrom pathlib import Path\n"
        "print('log output')\n"
        "Path(os.environ['CHAOSFOLK_RESULT_PATH']).write_text(json.dumps("
        "dict(tests=2, failures=0, errors=0, skipped=0)))\n", encoding="utf-8")
    result = integrations.run_external("appium", sys.executable, script, timeout=5)
    assert result["status"] == "passed"
    assert result["tests"] == 2 and result["log_bytes"] >= len("log output\n")


def test_external_runner_enforces_output_limit(tmp_path, monkeypatch):
    script = tmp_path / "runner.py"
    script.write_text("print('x' * 4096)\n", encoding="utf-8")
    monkeypatch.setattr(integrations, "MAX_LOG_BYTES", 1024)
    result = integrations.run_external("appium", sys.executable, script, timeout=5)
    assert result["status"] == "error" and result["reason"] == "output_limit"


def test_external_runner_returns_its_own_result_despite_an_inherited_output_pipe(tmp_path):
    import psutil

    script = tmp_path / "runner.py"
    pid_file = tmp_path / "child.pid"
    script.write_text(
        "import json, os, subprocess, sys\nfrom pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'])\n"
        "Path('child.pid').write_text(str(child.pid))\n"
        "print('runner log')\n"
        "Path(os.environ['CHAOSFOLK_RESULT_PATH']).write_text(json.dumps("
        "dict(tests=1, failures=0, errors=0, skipped=0)))\n", encoding="utf-8")
    started = time.monotonic()
    threads_before = set(threading.enumerate())
    try:
        result = integrations.run_external("appium", sys.executable, script, timeout=4)
        # The runner exited; a descendant holding stdout neither delays nor fails the result.
        assert result["status"] == "passed" and result["exit_code"] == 0
        assert result["log_bytes"] >= len("runner log\n")
        assert time.monotonic() - started < 3
        assert set(threading.enumerate()) <= threads_before
    finally:
        if pid_file.exists():
            try:
                child = psutil.Process(int(pid_file.read_text()))
                child.kill()
                child.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass


def test_external_runner_yields_after_eof_until_process_timeout(tmp_path, monkeypatch):
    script = tmp_path / "runner.py"
    script.write_text("import os, time\nos.close(1)\nos.close(2)\ntime.sleep(5)\n", encoding="utf-8")
    sleep = time.sleep
    sleeps = []

    def recorded_sleep(seconds):
        sleeps.append(seconds)
        sleep(seconds)

    monkeypatch.setattr(integrations.time, "sleep", recorded_sleep)
    result = integrations.run_external("appium", sys.executable, script, timeout=1)
    assert result["reason"] == "timeout"
    # A closed output pipe must not turn a still-running process into a busy loop.
    assert 1 <= len(sleeps) <= 30
    assert all(seconds >= 0.01 for seconds in sleeps)
