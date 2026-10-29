"""Publish complete sanitized exports and keep failed exports retryable."""
import json
from pathlib import Path

import pytest

from chaosfolk import engine, privacy


def session(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "constats.json").write_text('{"constats": []}', encoding="utf-8")
    (source / "journal.jsonl").write_text(json.dumps({"type": "action", "n": 1, "h": "h01", "t": 0,
                                                    "action": "done", "pense": "Private Name"}) + "\n", encoding="utf-8")
    return source


@pytest.mark.parametrize("existing", [False, True])
def test_failed_report_leaves_no_partial_export_and_can_retry(tmp_path, monkeypatch, existing):
    source, output = session(tmp_path), tmp_path / "public"
    if existing:
        output.mkdir()
    original = engine.rapport

    def fail(folder, language):
        (folder / "rapport.html").write_text("incomplete", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(engine, "rapport", fail)
    with pytest.raises(OSError, match="disk full"):
        privacy.export_report(source, output, "en", ["Private Name"])
    assert output.exists() == existing
    assert not output.exists() or not list(output.iterdir())
    assert not list(tmp_path.glob(".public-export-*"))
    assert "Private Name" in (source / "journal.jsonl").read_text(encoding="utf-8")
    monkeypatch.setattr(engine, "rapport", original)
    assert privacy.export_report(source, output, "en", ["Private Name"]) == output
    assert "Private Name" not in (output / "rapport.html").read_text(encoding="utf-8")


def test_rename_failure_restores_existing_empty_destination(tmp_path, monkeypatch):
    source, output = session(tmp_path), tmp_path / "public"
    output.mkdir()
    original = Path.rename

    def rename(path, target):
        if path.name == "report" and path.parent.name.startswith(".public-export-"):
            raise OSError("publication unavailable")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError, match="publication unavailable"):
        privacy.export_report(source, output, "en")
    assert output.is_dir() and not list(output.iterdir())
    assert not list(tmp_path.glob(".public-export-*"))


def test_concurrent_output_is_not_replaced(tmp_path, monkeypatch):
    source, output = session(tmp_path), tmp_path / "public"
    output.mkdir()

    def report(folder, language):
        (output / "other-task.txt").write_text("keep", encoding="utf-8")
        (folder / "rapport.html").write_text("generated", encoding="utf-8")

    monkeypatch.setattr(engine, "rapport", report)
    with pytest.raises(OSError):
        privacy.export_report(source, output, "en")
    assert (output / "other-task.txt").read_text(encoding="utf-8") == "keep"
    assert not (output / "rapport.html").exists()


def test_absolute_internal_proof_is_relocated_into_export(tmp_path):
    source, output = session(tmp_path), tmp_path / "public"
    proof = source / "reproductions" / "proof.json"
    proof.parent.mkdir()
    proof.write_text(json.dumps({"nom": "p", "mode": "traitement", "fois": 3, "demandes": 3,
                                 "casses": 0, "essais": [{"ok": True}] * 3}), encoding="utf-8")
    (source / "constats.json").write_text(json.dumps({"constats": [{"id": "C1", "preuves": {"avant": str(proof)}}]}), encoding="utf-8")
    privacy.export_report(source, output, "fr")
    findings = json.loads((output / "constats.json").read_text(encoding="utf-8"))
    assert findings["constats"][0]["preuves"]["avant"] == "reproductions/proof-000001.json"
    assert (output / "reproductions" / "proof-000001.json").is_file()
    assert str(source) not in (output / "rapport.html").read_text(encoding="utf-8")


def test_unsafe_proof_is_rejected_before_reading_it(tmp_path, monkeypatch):
    source, output = session(tmp_path), tmp_path / "public"
    secret = tmp_path / "secret.json"
    secret.write_text("private", encoding="utf-8")
    (source / "constats.json").write_text(json.dumps({"constats": [{"id": "C1", "preuves": {"avant": str(secret)}}]}), encoding="utf-8")
    original = Path.read_text

    def read(path, *args, **kwargs):
        assert path != secret
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    with pytest.raises(ValueError, match="escapes"):
        privacy.export_report(source, output, "en")
    assert not output.exists()


def test_private_journal_fields_are_dropped_before_redaction(tmp_path, monkeypatch):
    source, output = session(tmp_path), tmp_path / "public"
    event = {"type": "action", "h": "h01", "n": 1, "t": 0, "action": "fill", "url": "http://localhost/",
             "ecran": ["private screen"], "args": {"text": "typed secret"}, "live_evidence": [{"path": "x.sqlite"}]}
    (source / "journal.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
    original, sanitized = privacy._sanitize, []

    def recording(value, literals):
        if isinstance(value, dict) and value.get("type") == "action":
            sanitized.append(set(value))
        return original(value, literals)

    monkeypatch.setattr(privacy, "_sanitize", recording)
    privacy.export_report(source, output, "en")
    assert sanitized and all(not keys & {"ecran", "args", "live_evidence"} for keys in sanitized)
    exported = (output / "journal.jsonl").read_text(encoding="utf-8")
    assert "private screen" not in exported and "typed secret" not in exported and "x.sqlite" not in exported


def test_literal_iterator_covers_every_nested_field():
    value = {"a": "Private Name", "b": ["Private Name", {"c": "Private"}]}
    assert privacy.sanitize(value, iter(["Private", "Private Name"])) == {
        "a": "[redacted]", "b": ["[redacted]", {"c": "[redacted]"}]}


def test_summarized_proofs_and_private_names_keep_safe_working_links(tmp_path):
    source, output = session(tmp_path), tmp_path / "public"
    proof = source / "Private Name.json"
    proof.write_text(json.dumps({"nom": "Private Name", "mode": "traitement", "fois": 3, "demandes": 3,
                                 "casses": 0, "scenario": str(source / "private-scenario.json"),
                                 "live_evidence": [{"path": str(source / "private.sqlite")}],
                                 "essais": [{"ok": True}] * 3}), encoding="utf-8")
    findings = {"constats": [{"id": "C1", "preuves": {"avant": {"source": str(proof), "fois": 3},
                                                      "temoin": "Private Name.json"}}]}
    (source / "constats.json").write_text(json.dumps(findings), encoding="utf-8")
    privacy.export_report(source, output, "en", ["Private Name"])
    exported = json.loads((output / "constats.json").read_text(encoding="utf-8"))
    links = exported["constats"][0]["preuves"]
    assert links["avant"]["source"] == links["temoin"] == "reproductions/proof-000001.json"
    for path in output.rglob("*"):
        assert "Private Name" not in path.name
        if path.is_file() and path.suffix in (".json", ".html", ".jsonl", ".js"):
            contents = path.read_text(encoding="utf-8")
            assert "Private Name" not in contents and "private-scenario" not in contents and "private.sqlite" not in contents


def test_reviewed_capture_lookup_uses_original_filename_and_live_paths_are_removed(tmp_path):
    source, output = session(tmp_path), tmp_path / "public"
    image = source / "Private Name.png"
    image.write_bytes(b"synthetic image fixture")
    events = [{"type": "action", "h": "h01", "n": 1, "t": 0, "action": "done", "capture": image.name},
              {"type": "evidence-spilled", "h": "h01", "t": 1,
               "path": str(source / "sensitive.sqlite"), "records_preserved": True,
               "live_evidence": [{"path": "private.sqlite"}]}]
    (source / "journal.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    privacy.export_report(source, output, "en", ["Private Name"], include_captures=True)
    exported = list(engine.iterer_journal(output))
    assert (output / exported[0]["capture"]).read_bytes() == image.read_bytes()
    assert "path" not in exported[1] and "records_preserved" not in exported[1]
    assert "live_evidence" not in exported[1] and exported[1]["private_evidence_excluded"] is True


def test_external_summarized_source_cannot_be_read_by_report_generation(tmp_path):
    source, output = session(tmp_path), tmp_path / "public"
    outside = tmp_path / "secret.json"
    outside.write_text('{"scenario":"private"}', encoding="utf-8")
    (source / "constats.json").write_text(json.dumps({"constats": [{"id": "C1", "preuves": {
        "avant": {"source": str(outside)}}}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        privacy.export_report(source, output, "en")
    assert not output.exists()
