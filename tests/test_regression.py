import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
from xml.etree import ElementTree as ET

import pytest

from chaosfolk import regression


def scenario(url="http://127.0.0.1:3000/"):
    return {"url": url, "steps": [
        {"n": 1, "action": "type", "target": {"role": "textbox", "name": "Project name"},
         "args": {"text": "Synthetic project"}},
        {"n": 2, "action": "click", "target": {"role": "button", "name": "Save"}, "args": {}}],
        "expect": [{"type": "text-visible", "text": "Saved"},
                   {"type": "storage", "key": "project", "contains": "Synthetic project"}]}


def write_scenario(tmp_path, value, name="scenario.json"):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize("mutate,match", [
    (lambda s: s.update(expect=[]), "explicit assertion"),
    (lambda s: s.update(faults=[{"type": "clock", "start_action": 0}]), "fault clock"),
    (lambda s: s["steps"][0].update(action="upload", args={"path": "secret.txt"}), "upload"),
    (lambda s: s.update(sessions={"editor": {}}), "multiple sessions"),
    (lambda s: s.update(state={"cookies": [{"name": "secret", "value": "do-not-copy"}]}), "Inline browser state"),
    (lambda s: s.update(url="http://user:password@127.0.0.1/"), "authentication data"),
    (lambda s: s["steps"][0]["target"].update(name="Password"), "credential input"),
    (lambda s: s["steps"][0]["args"].update(unrecognized=True), "unsupported arguments"),
    (lambda s: s["steps"][0].update(echec_original=True), "failed original"),
    (lambda s: s.update(faults=[{"type": "offline", "start_action": 99}]), "schedule warnings"),
])
def test_export_rejects_semantics_it_cannot_preserve(tmp_path, mutate, match):
    data = scenario()
    mutate(data)
    output = tmp_path / "test_regression.py"
    with pytest.raises(ValueError, match=match):
        regression.export_test(write_scenario(tmp_path, data), output)
    assert not output.exists()


def test_export_keeps_state_external_and_does_not_overwrite(tmp_path):
    data = scenario()
    data["state"] = "private-user-login.json"
    source = write_scenario(tmp_path, data)
    output = regression.export_test(source, tmp_path / "test_exported.py")
    text = output.read_text(encoding="utf-8")
    assert "private-user-login" not in text
    assert "CHAOSFOLK_STORAGE_STATE" in text
    assert "from chaosfolk" not in text
    compile(text, str(output), "exec")
    with pytest.raises(FileExistsError):
        regression.export_test(source, output)


def test_invalid_suite_writes_junit_error_and_ignores_stale_results(tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    (output / "old.json").write_text('{"fois":3,"demandes":3,"casses":0}', encoding="utf-8")
    path = write_scenario(tmp_path, {"steps": []})
    assert regression.run_suite([path], output) == 2
    root = ET.parse(output / "junit.xml").getroot()
    assert root.attrib["errors"] == "1"
    assert root.attrib["failures"] == "0"
    assert root.find("testcase/error") is not None


def test_xml_writer_escapes_messages_and_handles_invalid_control_characters(tmp_path):
    regression.write_results(tmp_path, [{"name": '<case & "test">', "status": "failed",
                                        "seconds": 0.1, "message": "expected <ready> & value\x00"}])
    root = ET.parse(tmp_path / "junit.xml").getroot()
    assert root.find("testcase/failure").text == "expected <ready> & value"


@pytest.fixture
def fixture_url(tmp_path):
    (tmp_path / "index.html").write_text('''<!doctype html><html><body>
<label>Project name<input id="name"></label><button onclick="save()">Save</button><p id="status"></p>
<script>function save(){try{localStorage.setItem('project',document.querySelector('input').value);
document.querySelector('#status').textContent='Saved';}catch(e){document.querySelector('#status').textContent='Storage full';}}
</script></body></html>''', encoding="utf-8")

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.browser
def test_generated_test_runs_without_chaosfolk_and_detects_failure(tmp_path, fixture_url):
    source = write_scenario(tmp_path, scenario(fixture_url))
    output = regression.export_test(source, tmp_path / "portable.py")
    passed = subprocess.run([sys.executable, str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    data = scenario(fixture_url)
    data["expect"][0]["text"] = "Not really saved"
    output = regression.export_test(write_scenario(tmp_path, data), tmp_path / "broken.py")
    failed = subprocess.run([sys.executable, str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert failed.returncode != 0
    assert "AssertionError" in failed.stderr


@pytest.mark.browser
def test_exported_storage_fault_is_timed_restored_and_survives_reload(tmp_path, fixture_url):
    data = scenario(fixture_url)
    data["steps"] += [{"n": 3, "action": "reload"},
                      {"n": 4, "action": "click", "target": {"role": "button", "name": "Save"}, "args": {}}]
    data["faults"] = [{"type": "storage-full", "start_action": 1}]
    data["expect"] = [{"type": "text-visible", "text": "Storage full"}]
    output = regression.export_test(write_scenario(tmp_path, data), tmp_path / "fault.py")
    run = subprocess.run([sys.executable, str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    data["faults"][0]["end_action"] = 2
    data["expect"][0]["text"] = "Saved"
    output = regression.export_test(write_scenario(tmp_path, data), tmp_path / "removed.py")
    run = subprocess.run([sys.executable, str(output)], cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.browser
def test_ci_runner_distinguishes_pass_failure_and_invalid(tmp_path, fixture_url):
    source = write_scenario(tmp_path, scenario(fixture_url))
    output = tmp_path / "pass"
    assert regression.run_suite([source], output, times=1) == 0
    assert ET.parse(output / "junit.xml").getroot().attrib["errors"] == "0"
    data = scenario(fixture_url)
    data["expect"][0]["text"] = "Not really saved"
    source = write_scenario(tmp_path, data)
    output = tmp_path / "failed"
    assert regression.run_suite([source], output, times=1) == 1
    assert ET.parse(output / "junit.xml").getroot().attrib["failures"] == "1"
    data["expect"] = [{"type": "field-value", "field": "Missing field", "value": "x"}]
    source = write_scenario(tmp_path, data)
    assert regression.run_suite([source], tmp_path / "invalid", times=1) == 2


def test_cli_returns_clear_errors(tmp_path, capsys):
    assert regression.main(["export", str(tmp_path / "absent.json"), "--output", str(tmp_path / "out.py")]) == 2
    assert "chaosfolk regression" in capsys.readouterr().err
