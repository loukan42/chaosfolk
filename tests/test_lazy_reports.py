"""Large local reports load complete event/proof details with bounded retention."""
import json
from pathlib import Path
import re
import shutil

import pytest
from playwright.sync_api import sync_playwright

from chaosfolk import engine, privacy, reporting
from chaosfolk.scoring import finding_info


def embedded(path):
    text = path.read_text(encoding="utf-8")
    marker = re.search(r"\bconst\s+data\s*=\s*", text)
    encoded = text[marker.end():]
    assert encoded.startswith("JSON.parse(")
    return json.loads(json.JSONDecoder().raw_decode(encoded[len("JSON.parse("):])[0])


def chunk_payload(path):
    script = path.read_text(encoding="utf-8")
    encoded = script.split(",JSON.parse(", 1)[1].rsplit("));", 1)[0]
    return json.loads(json.loads(encoded))


def session(folder, count=40):
    shutil.copyfile(Path(engine.__file__).parent / "templates/mascot.png", folder / "shot.png")
    engine.ecrire_json(folder / "personas.json", {"humains": [{"id": "h01", "nom": "Alex", "appareil": "desktop"}]})
    proof = {"nom": "save", "mode": "traitement", "fois": 3, "demandes": 3, "casses": 3,
             "captures": ["shot.png"] * 3, "raisons": [["Original failure"]] * 3, "trial_integrity": True}
    engine.ecrire_json(folder / "constats.json", {"constats": [{"id": "C1", "titre": "Save failed",
        "qualification": "defect", "expected_basis": "Documented save contract.",
        "preuves": {"avant": proof}, "evenements": [{"h": "h01", "n": 1}]}]})
    events = [{"type": "action", "h": "h01", "n": n, "t": n * 1000, "action": "click", "resultat": "ok",
               "capture": "shot.png", "cible": {"nom": "Save"}, "url": f"http://localhost/{n}",
               "args": {"texte": f"Full original value {n}"}, "pense": f"Reaction {n}: café </script> " + "x" * 100,
               "message": f"Diagnostic {n}", "custom_evidence": {"original": n}} for n in range(count)]
    (folder / "journal.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    return events, proof


def force_chunks(monkeypatch):
    monkeypatch.setattr(reporting, "INLINE_JOURNAL_BYTES", 1)
    monkeypatch.setattr(reporting, "DETAIL_CHUNK_EVENTS", 4)


def test_large_report_chunks_preserve_every_projected_event_and_proof(tmp_path, monkeypatch):
    force_chunks(monkeypatch)
    events, proof = session(tmp_path)
    engine.rapport(tmp_path)
    data = embedded(tmp_path / "report-en.html")
    manifest = data["journal_details"]
    assert manifest["total_events"] == len(events) == len(data["journal"])
    reconstructed = []
    for descriptor in manifest["chunks"]:
        assert descriptor["start"] == len(reconstructed)
        payload = chunk_payload(tmp_path / descriptor["file"])
        assert len(payload["events"]) == descriptor["count"]
        reconstructed.extend(payload["events"])
    with reporting.JournalSpool(engine.iterer_journal(tmp_path)) as expected:
        assert reconstructed == list(expected)
    assert all("pense" not in event and "args" not in event and "custom_evidence" not in event for event in data["journal"])
    summary = data["constats"]["constats"][0]["preuves"]["avant"]
    assert "captures" not in summary and summary["fois"] == 3
    descriptor = manifest["proofs"][summary["_proof_detail"]]
    assert chunk_payload(tmp_path / descriptor["file"])["proof"] == proof
    assert embedded(tmp_path / "rapport-fr.html")["journal_details"] == manifest
    assert (tmp_path / "report-en.html").read_bytes() == (tmp_path / "rapport.html").read_bytes()


def test_small_report_keeps_the_inline_format(tmp_path):
    events, _ = session(tmp_path, 2)
    engine.rapport(tmp_path)
    data = embedded(tmp_path / "report-en.html")
    assert "journal_details" not in data
    assert data["journal"][0]["pense"] == events[0]["pense"]
    assert not (tmp_path / "assets/journal").exists()


def prototype_session(folder):
    events, proof = session(folder, 2)
    text = '</script><script>window.evidenceInjected=true</script> " \\ café \u2028 \u2029'
    finding = {"id": "forged", "titre": text, "gravite": "bloquant", "__proto__": {
        "qualification": "defect", "expected_basis": "Forged contract", "preuves": {"avant": proof}}}
    events[0].update({"pense": text, "__proto__": {"inheritedEvidence": True}})
    engine.ecrire_json(folder / "constats.json", {"constats": [finding]})
    (folder / "journal.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    engine.rapport(folder)
    return finding, events, text


def test_inline_json_parser_preserves_prototype_fields_and_script_characters(tmp_path):
    finding, events, text = prototype_session(tmp_path)
    for filename in ("report-en.html", "rapport-fr.html"):
        data = embedded(tmp_path / filename)
        assert data["constats"]["constats"][0] == finding
        assert data["journal"][0]["__proto__"] == events[0]["__proto__"]
        assert data["journal"][0]["pense"] == text
        assert text not in (tmp_path / filename).read_text(encoding="utf-8")
        assert finding_info(data["constats"]["constats"][0])["stage"] == "pending"
        assert "forged" not in data["score"]["cap"]["ids"]


@pytest.mark.browser
@pytest.mark.parametrize("lazy", [False, True])
def test_engine_to_chromium_preserves_json_without_inherited_confirmation(tmp_path, monkeypatch, lazy):
    if lazy:
        force_chunks(monkeypatch)
    finding, events, text = prototype_session(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        for filename in ("report-en.html", "rapport-fr.html"):
            page.goto((tmp_path / filename).as_uri())
            assert page.evaluate("window.evidenceInjected") is None
            # Playwright's object transport drops __proto__; JSON preserves it.
            assert json.loads(page.evaluate("JSON.stringify(data.constats.constats[0])")) == finding
            assert page.evaluate("Object.hasOwn(data.constats.constats[0], '__proto__')")
            assert page.evaluate("Object.getPrototypeOf(data.constats.constats[0]) === Object.prototype")
            assert page.evaluate("proven(data.constats.constats[0])") is False
            assert page.evaluate("findingState(data.constats.constats[0])") == "needsEvidence"
            assert "forged" not in page.evaluate("data.score.cap.ids")
            original = json.loads(page.evaluate("async () => JSON.stringify(await evidenceStore.event(data.journal[0]))"))
            assert original["pense"] == text
            assert original["__proto__"] == events[0]["__proto__"]
        assert not errors
        browser.close()


def test_lazy_matrix_retains_trial_evidence_and_preparation_status(tmp_path, monkeypatch):
    force_chunks(monkeypatch)
    session(tmp_path, 2)
    cell = {"fois": 3, "demandes": 3, "casses": 0, "mode": "traitement", "essais": [
        {"ok": True, "capture": "shot.png", "preparation": {"status": "reset-verified"}, "extra": "Full evidence"}] * 3}
    engine.ecrire_json(tmp_path / "reproductions/matrix.json", {"cells": {"observed/with_faults": cell}})
    engine.rapport(tmp_path)
    data = embedded(tmp_path / "rapport.html")
    summary = data["replay_matrices"][0]["cells"]["observed/with_faults"]
    assert "essais" not in summary and summary["_preparation_verified"] is True
    descriptor = data["journal_details"]["proofs"][summary["_proof_detail"]]
    assert chunk_payload(tmp_path / descriptor["file"])["proof"] == cell


def test_private_export_regenerates_only_sanitized_local_chunks(tmp_path, monkeypatch):
    force_chunks(monkeypatch)
    source, destination = tmp_path / "private", tmp_path / "public"
    source.mkdir()
    events, _ = session(source, 8)
    events[0]["pense"] = "private-marker-82731 jane@example.com"
    (source / "journal.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    engine.rapport(source)
    privacy.export_report(source, destination, "fr", literals=["private-marker-82731"])
    data = embedded(destination / "rapport.html")
    assert data["lang"] == "fr"
    for descriptor in [*data["journal_details"]["chunks"], *data["journal_details"]["proofs"].values()]:
        text = json.dumps(chunk_payload(destination / descriptor["file"]), ensure_ascii=False)
        assert "private-marker-82731" not in text and "jane@example.com" not in text
    values = chunk_payload(destination / data["journal_details"]["chunks"][0]["file"])["events"]
    assert values[0]["pense"] == "[redacted] [email]"
    assert all(event.get("capture") is None and "args" not in event for event in values)
    assert not (destination / "captures").exists()


@pytest.fixture
def lazy_page(tmp_path, monkeypatch):
    force_chunks(monkeypatch)
    session(tmp_path)
    engine.rapport(tmp_path)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: external.append(request.url) if request.url.startswith(("http:", "https:")) else None)
        page.goto((tmp_path / "report-en.html").as_uri())
        page.wait_for_function("evidenceStore.stats().pending === 0")
        yield page, tmp_path
        assert not errors, errors
        assert not external, external
        browser.close()


@pytest.mark.browser
def test_file_report_loads_details_on_seek_in_both_languages(lazy_page):
    page, _ = lazy_page
    assert page.evaluate("evidenceStore.stats().loads") == 1
    assert page.evaluate("proven(data.constats.constats[0])") is True
    assert page.locator(".finding-status").first.inner_text() == "Confirmed defect"
    assert "3/3 failures" in page.locator(".proofs").first.text_content()
    assert page.evaluate("data.journal[39].pense") is None
    page.locator("#detail-summary").click()
    page.evaluate("document.querySelector('#timeline').value=39; document.querySelector('#timeline').dispatchEvent(new Event('input'))")
    page.wait_for_function("document.querySelector('#narrative').textContent.includes('Reaction 39: café </script>')")
    assert "Diagnostic 39" in page.locator("#narrative").inner_text()
    page.locator('[data-lang="fr"]').click()
    assert "réaction originale" in page.locator("#narrative").inner_text().casefold()
    assert page.locator("#screen img").get_attribute("src") == "shot.png"
    assert page.evaluate("data.journal[39].pense") is None  # Loaded objects never expand the index in place.
    page.locator(".finding-toggle").first.click()
    page.locator(".finding-body details summary").click()
    page.wait_for_function("document.querySelectorAll('.proof-image').length === 3")
    assert page.evaluate("data.constats.constats[0].preuves.avant.captures") is None
    page.locator(".finding-body details summary").click()
    page.wait_for_function("document.querySelectorAll('.proof-image').length === 0")


@pytest.mark.browser
def test_detail_cache_evicts_and_reloads_without_losing_fields(lazy_page):
    page, _ = lazy_page
    result = page.evaluate("""async () => {
      for (let i=0; i<data.journal.length; i+=4) {
        const value=await evidenceStore.event(data.journal[i]);
        if(value.custom_evidence.original!==i) throw new Error('evidence lost');
        const stats=evidenceStore.stats();
        if(stats.chunks>4||stats.bytes>1048576) throw new Error('unbounded cache');
      }
      const loads=evidenceStore.stats().loads;
      const first=await evidenceStore.event(data.journal[0]);
      return {reloaded:evidenceStore.stats().loads>loads,value:first.args.texte,stats:evidenceStore.stats()};
    }""")
    assert result["reloaded"] and result["value"] == "Full original value 0"
    assert result["stats"]["chunks"] <= 4
    assert page.evaluate("document.querySelectorAll('script[src*=\"assets/journal/\"]').length") == 0


@pytest.mark.browser
def test_late_detail_response_cannot_replace_the_current_event(lazy_page):
    page, _ = lazy_page
    page.locator("#detail-summary").click()
    page.evaluate("""() => {
      const original=evidenceStore.event.bind(evidenceStore);
      evidenceStore.event=(event,current)=>original(event,current).then(value=>event._detail===8?
        new Promise(resolve=>setTimeout(()=>resolve(value),150)):value);
      const slider=document.querySelector('#timeline');
      slider.value=8;slider.dispatchEvent(new Event('input'));
      slider.value=20;slider.dispatchEvent(new Event('input'));
    }""")
    page.wait_for_function("document.querySelector('#narrative').textContent.includes('Reaction 20:')")
    page.wait_for_timeout(220)
    assert "Reaction 20:" in page.locator("#narrative").inner_text()
    assert "Reaction 8:" not in page.locator("#narrative").inner_text()


@pytest.mark.browser
def test_missing_chunk_is_visible_and_can_be_retried(lazy_page):
    page, folder = lazy_page
    descriptor = embedded(folder / "report-en.html")["journal_details"]["chunks"][-1]
    path = folder / descriptor["file"]
    original = path.read_bytes()
    path.unlink()
    page.locator("#detail-summary").click()
    page.evaluate("document.querySelector('#timeline').value=39; document.querySelector('#timeline').dispatchEvent(new Event('input'))")
    page.get_by_text("Details unavailable. Keep the report with its assets/journal folder.", exact=True).wait_for()
    path.write_bytes(original)
    page.locator("#narrative").get_by_role("button", name="Retry").click()
    page.wait_for_function("document.querySelector('#narrative').textContent.includes('Reaction 39:')")


@pytest.mark.browser
def test_manifest_cannot_request_remote_detail_scripts(lazy_page):
    page, _ = lazy_page
    page.locator("#detail-summary").click()
    page.evaluate("""() => {
      data.journal_details.chunks.at(-1).file='https://example.com/exfiltrate.js';
      const slider=document.querySelector('#timeline');slider.value=39;slider.dispatchEvent(new Event('input'));
    }""")
    page.get_by_text("Details unavailable. Keep the report with its assets/journal folder.", exact=True).wait_for()
