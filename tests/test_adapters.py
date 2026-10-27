"""Optional adapters, MCP access, usage gates, privacy export and visual comparison."""
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading

import pytest

from chaosfolk import integrations, mcp_server, privacy, usage


# Usage ---------------------------------------------------------------------

def event(id, tokens=(10, 5), cost=0.01, **extra):
    return {"id": id, "source": "host", "input_tokens": tokens[0], "output_tokens": tokens[1],
            "cost": cost, "currency": "USD", **extra}


def test_usage_gate_deduplicates_and_reports_unknown_values():
    result = usage.summarize([event("a"), event("a"), event("b")], max_tokens=100)
    assert result["events"] == 2 and result["tokens"] == 30 and result["gate"] == "continue"
    assert usage.summarize([event("a")], max_tokens=15)["gate"] == "stop"
    unknown = usage.summarize([event("a", tokens=(None, 5))], max_tokens=100)
    assert unknown["tokens"] is None and unknown["gate"] == "unknown"


@pytest.mark.parametrize("events,match", [
    ([event("a"), event("a", cost=1)], "Conflicting duplicate"),
    ([dict(event("a"), source="estimate")], "source must be host"),
    ([dict(event("a"), currency="EUR")], "requested currency"),
    ([{"source": "host"}], "stable string id"),
])
def test_usage_rejects_untrusted_measurements(events, match):
    with pytest.raises(ValueError, match=match):
        usage.summarize(events)


def test_usage_cli_exit_codes(tmp_path):
    path = tmp_path / "usage.jsonl"
    path.write_text(json.dumps(event("a")) + "\n", encoding="utf-8")
    assert usage.main(["--input", str(path), "--max-cost", "1"]) == 0
    assert usage.main(["--input", str(path), "--max-cost", "0.001"]) == 1
    assert usage.main(["--input", str(path), "--output", str(path)]) == 2


# Privacy -------------------------------------------------------------------

def test_sanitize_redacts_secrets_emails_and_literals():
    value = privacy.sanitize({"token": "abc", "state": {"cookies": []}, "note": [
        "Bearer eyJhbGciOi.x", "https://app.test/?token=123&page=2", "Write to ana@example.com", "Ana Lopez"]},
        literals=["Ana Lopez"])
    assert value == {"token": "[redacted]", "note": [
        "Bearer [redacted]", "https://app.test/?token=[redacted]&page=2", "Write to [email]", "[redacted]"]}


def test_mask_selectors_from_environment_are_validated(monkeypatch):
    class Frame:
        def locator(self, selector):
            return selector

    page = type("Page", (), {"frames": [Frame()]})()
    monkeypatch.setenv("CHAOSFOLK_MASK_SELECTORS", '[".balance"]')
    assert ".balance" in privacy.screenshot_masks(page) and 'input[type="password"]' in privacy.screenshot_masks(page)
    monkeypatch.setenv("CHAOSFOLK_MASK_SELECTORS", '".balance"')
    with pytest.raises(ValueError):
        privacy.screenshot_masks(page)


def test_privacy_export_refuses_unsafe_destinations(tmp_path):
    source = tmp_path / "session"
    source.mkdir()
    with pytest.raises(ValueError, match="separate directory"):
        privacy.export_report(source, source / "public", "en")
    with pytest.raises(ValueError, match="constats.json"):
        privacy.export_report(source, tmp_path / "public", "en")


# Files ---------------------------------------------------------------------

def test_file_checks_csv_and_text(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text("name,email\nAna,a@example.test\nBo,b@example.test\n", encoding="utf-8")
    result = integrations.check_file(path, columns=["email"], min_rows=2, max_rows=2)
    assert result["status"] == "passed" and result["rows"] == 2 and "Ana" not in json.dumps(result)
    assert integrations.check_file(path, columns=["phone"])["status"] == "failed"
    path.write_text("name,email\nAna\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row width"):
        integrations.check_file(path, columns=["email"])
    text = tmp_path / "receipt.txt"
    text.write_text("Total: 12.00", encoding="utf-8")
    assert integrations.check_file(text, contains=["Total"])["status"] == "passed"
    with pytest.raises(ValueError, match="require a CSV"):
        integrations.check_file(text, columns=["x"])


def test_remote_targets_need_explicit_permission():
    assert integrations.allowed_origin("http://localhost:8025") == "http://localhost:8025"
    with pytest.raises(ValueError, match="allow-origin"):
        integrations.allowed_origin("https://mail.example.com")
    assert integrations.allowed_origin("https://mail.example.com", ["https://mail.example.com:443"])
    with pytest.raises(ValueError, match="credentials"):
        integrations.origin("http://user:pw@localhost/")


@pytest.fixture
def mailpit_url():
    mail = EmailMessage()
    mail["Subject"], mail["To"] = "Reset your password", "ana@example.test"
    mail.set_content("Open https://app.test/reset?code=1 to continue")
    raw = mail.as_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path.startswith("/api/v1/messages"):
                body = json.dumps({"messages": [{"ID": "m1", "Subject": "Reset your password", "Snippet": "secret"}]}).encode()
            elif self.path == "/api/v1/message/m1/raw":
                body = raw
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def test_mailpit_lists_without_bodies_and_checks_one_message(mailpit_url):
    listed = integrations.mailpit(mailpit_url)
    assert listed["messages"] == [{"id": "m1", "subject": "Reset your password"}]
    result = integrations.mailpit(mailpit_url, "m1", subject="Reset your password",
                                  contains=["/reset?code="], recipient="ANA@example.test")
    assert result["status"] == "passed", result
    assert integrations.mailpit(mailpit_url, "m1", contains=["Welcome"])["status"] == "failed"
    with pytest.raises(ValueError, match="Invalid message ID"):
        integrations.mailpit(mailpit_url, "../m1", subject="x")
    with pytest.raises(ValueError, match="origin"):
        integrations.mailpit(mailpit_url + "/api", subject=None)


def test_external_runner_refuses_shell_wrappers(tmp_path):
    wrapper, script = tmp_path / "k6.cmd", tmp_path / "load.js"
    wrapper.write_text("@echo off", encoding="utf-8")
    script.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="native executable"):
        integrations.run_external("k6", wrapper, script)
    with pytest.raises(ValueError, match="k6 or appium"):
        integrations.run_external("jmeter", wrapper, script)


# MCP -----------------------------------------------------------------------

def call(server, method, params=None, id=1):
    return server.handle({"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})


def test_mcp_exposes_metadata_only(tmp_path):
    (tmp_path / "findings.json").write_text(json.dumps({
        "abc123": {"title": "Card number visible: 4111", "state": "open", "severity": "blocking", "seen": 2},
        "def456": {"title": "Old", "state": "fixed", "severity": "minor", "seen": 1}}), encoding="utf-8")
    (tmp_path / "campaigns.json").write_text(json.dumps({"campaigns": [{"revision": "a1b2c3d"}]}), encoding="utf-8")
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "login.json").write_text('{"state": "secret"}', encoding="utf-8")
    server = mcp_server.Server(tmp_path)
    assert call(server, "tools/list")["error"]["code"] == -32000
    assert call(server, "initialize")["result"]["serverInfo"]["name"] == "chaosfolk"
    assert {t["name"] for t in call(server, "tools/list")["result"]["tools"]} == {"campaign_status", "list_findings", "list_scenarios"}
    status = call(server, "tools/call", {"name": "campaign_status"})["result"]["structuredContent"]
    assert status["states"]["open"] == 1 and status["latest_revision"] == "a1b2c3d"
    findings = call(server, "tools/call", {"name": "list_findings", "arguments": {"limit": 1}})["result"]
    assert "4111" not in json.dumps(findings) and findings["structuredContent"]["next_offset"] == 1
    scenarios = call(server, "tools/call", {"name": "list_scenarios"})["result"]["structuredContent"]
    assert scenarios["scenarios"] == ["login"] and "secret" not in json.dumps(scenarios)
    assert call(server, "tools/call", {"name": "list_findings", "arguments": {"limit": 1000}})["error"]["code"] == -32602
    assert call(server, "tools/call", {"name": "delete_everything"})["error"]["code"] == -32602
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_mcp_stdio_loop_answers_parse_errors(tmp_path):
    lines = b'{"jsonrpc":"2.0","id":1,"method":"initialize"}\nnot json\n{"jsonrpc":"2.0","id":2,"method":"ping"}\n'
    output = io.StringIO()
    assert mcp_server.serve(tmp_path, io.BytesIO(lines), output) == 0
    replies = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2]
    assert replies[1]["error"]["code"] == -32700


# Visual --------------------------------------------------------------------

def test_visual_compare_flags_changes_without_calling_them_bugs(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    from chaosfolk import visual
    before, after = tmp_path / "a.png", tmp_path / "b.png"
    Image.new("RGB", (100, 100), "white").save(before)
    image = Image.new("RGB", (100, 100), "white")
    image.paste((255, 0, 0), (0, 0, 10, 10))
    image.save(after)
    same = visual.compare(before, before, tmp_path / "same")
    assert same["passed"] and same["changed_pixels"] == 0
    changed = visual.compare(before, after, tmp_path / "changed")
    assert not changed["passed"] and changed["changed_pixels"] == 100
    assert (tmp_path / "changed" / "diff.png").is_file() and "not an automatic" in changed["interpretation"]
    with pytest.raises(ValueError, match="empty output"):
        visual.compare(before, after, tmp_path / "changed")
    resized = tmp_path / "c.png"
    Image.new("RGB", (50, 100), "white").save(resized)
    assert visual.compare(before, resized, tmp_path / "resized")["same_size"] is False


def test_cli_routes_extension_commands(capsys):
    from chaosfolk import cli
    assert cli.main(["benchmark", "list"]) == 0
    assert "storage-draft-loss" in capsys.readouterr().out
