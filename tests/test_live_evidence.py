"""Disk-backed live collections preserve exact values and visible failures."""
import asyncio
from collections import Counter
from contextlib import closing
import json
import random
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chaosfolk import engine
from chaosfolk.evidence import EvidenceStore


def test_small_collections_allocate_no_files(tmp_path):
    store = EvidenceStore(tmp_path / "evidence", limit=10)
    store.errors.append("Error")
    store.messages.append("Downloaded")
    store.requests.increment("GET localhost/api")
    assert store.errors == ["Error"]
    assert store.messages == ["Downloaded"]
    assert store.requests == {"GET localhost/api": 1}
    assert store.path is None and not (tmp_path / "evidence").exists()


def test_all_errors_spill_without_loss_and_remain_readable_after_close(tmp_path):
    notifications = []
    store = EvidenceStore(tmp_path, limit=3, on_spill=notifications.append)
    expected = [f"Error {index} \u2028é" for index in range(5000)]
    for message in expected:
        store.errors.append(message)
    assert store.errors.memory == []
    assert store.errors.memory_bytes == 0
    assert len(store.errors) == len(expected)
    assert store.errors == expected
    assert len(notifications) == 1 and notifications[0]["collection"] == "errors"
    assert notifications[0]["records_preserved"] is True
    store.close()
    assert store.connection is None
    assert store.errors[4999] == expected[4999]
    assert store.errors[:10] == expected[:10]
    store.close()
    with closing(sqlite3.connect(store.path)) as database:
        assert database.execute("SELECT COUNT(*) FROM errors").fetchone()[0] == 5000
    assert not store.path.with_suffix(".sqlite-wal").exists()


@pytest.mark.parametrize("selection", [slice(None), slice(1, 12), slice(-5, None), slice(None, None, -1),
                                       slice(12, 1, -3), slice(2, 13, 3), slice(40, 50), slice(-50, 50, 2),
                                       slice(5, 5), 0, 7, -1, -12])
def test_disk_sequence_preserves_python_indexing_and_slicing(tmp_path, selection):
    store = EvidenceStore(tmp_path, limit=2)
    expected = [f"message-{index}" for index in range(15)]
    try:
        for message in expected:
            store.errors.append(message)
        assert store.errors[selection] == expected[selection]
    finally:
        store.close()


def test_invalid_indices_and_empty_slices_match_list_behavior(tmp_path):
    store = EvidenceStore(tmp_path, limit=0)
    store.errors.append("Error")
    try:
        for index in (-2, 1, 999):
            with pytest.raises(IndexError):
                _ = store.errors[index]
        with pytest.raises(ValueError):
            _ = store.errors[::0]
        with pytest.raises(TypeError):
            _ = store.errors["first"]
        assert store.errors[-3:-4] == []
    finally:
        store.close()


def test_request_counts_and_insertion_order_match_dictionary_after_spill(tmp_path):
    store = EvidenceStore(tmp_path, limit=5)
    expected = Counter()
    randomizer = random.Random(42)
    try:
        for _ in range(5000):
            key = f"GET localhost/api/item-{randomizer.randrange(1000)}"
            expected[key] += 1
            store.requests.increment(key)
        assert store.requests == expected
        assert dict(store.requests) == dict(expected)
        assert list(store.requests) == list(expected)
        assert list(store.requests.sorted_items()) == sorted(expected.items())
        assert store.requests.memory == {} and store.requests.memory_bytes == 0
        key = next(iter(expected))
        del expected[key]
        del store.requests[key]
        expected[key] = 8
        store.requests[key] = 8
        assert list(store.requests.items()) == list(expected.items())
        with pytest.raises(KeyError):
            del store.requests["absent"]
        with pytest.raises(KeyError):
            _ = store.requests["absent"]
        store.close()
        assert store.requests == expected
    finally:
        store.close()


def test_long_keys_trigger_byte_budget_before_count_budget(tmp_path):
    store = EvidenceStore(tmp_path, limit=1000, byte_limit=200)
    try:
        store.requests.increment("GET localhost/" + "a" * 100)
        store.errors.append("é" * 100)
        assert store.requests.disk and store.errors.disk
        assert len(store.requests) == 1 and len(store.errors) == 1
    finally:
        store.close()


def test_messages_clear_preserves_reuse_and_other_evidence(tmp_path):
    store = EvidenceStore(tmp_path, limit=2)
    try:
        for index in range(100):
            store.messages.append(f"Download {index}")
            store.errors.append(f"Error {index}")
        assert list(store.messages) == [f"Download {index}" for index in range(100)]
        store.messages.clear()
        assert not store.messages and list(store.messages) == []
        assert len(store.errors) == 100
        for index in range(5):
            store.messages.append(f"New download {index}")
        assert store.messages == [f"New download {index}" for index in range(5)]
    finally:
        store.close()


def test_failed_spill_keeps_existing_memory_and_refuses_silent_continuation(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path, limit=2)
    monkeypatch.setattr(store, "database", lambda: (_ for _ in ()).throw(OSError("disk full")))
    store.errors.append("First")
    store.errors.append("Second")
    with pytest.raises(OSError, match="disk full"):
        store.errors.append("Third")
    assert store.errors == ["First", "Second", "Third"]
    with pytest.raises(RuntimeError, match="storage failed"):
        store.errors.append("Fourth")
    assert not store.errors.disk


def test_failed_transfer_does_not_rollback_other_collection_records(tmp_path, monkeypatch):
    store = EvidenceStore(tmp_path, limit=2)
    try:
        for index in range(8):
            store.errors.append(str(index))
        database = store.database()
        database.execute("CREATE TRIGGER reject_requests BEFORE INSERT ON requests BEGIN SELECT RAISE(ABORT, 'disk failure'); END")
        store.requests.increment("a")
        store.requests.increment("b")
        with pytest.raises(sqlite3.IntegrityError, match="disk failure"):
            store.requests.increment("c")
        assert store.errors == [str(index) for index in range(8)]
        assert store.requests == {"a": 1, "b": 1, "c": 1}
    finally:
        store.close()


@pytest.mark.parametrize("collection", ["messages", "requests"])
def test_failed_delete_is_explicit_and_preserves_collection(tmp_path, collection):
    store = EvidenceStore(tmp_path, limit=0)
    try:
        store.messages.append("Downloaded")
        store.requests["GET localhost/api"] = 1
        store.flush()
        store.database().execute(f"CREATE TRIGGER reject_delete BEFORE DELETE ON {collection} "
                                 "BEGIN SELECT RAISE(ABORT, 'write failed'); END")
        with pytest.raises(sqlite3.IntegrityError, match="write failed"):
            if collection == "messages":
                store.messages.clear()
            else:
                del store.requests["GET localhost/api"]
        assert store.messages == ["Downloaded"]
        assert store.requests == {"GET localhost/api": 1}
        with pytest.raises(RuntimeError, match="storage failed"):
            store.check()
    finally:
        store.close()


def test_browser_close_failure_still_closes_evidence_database(tmp_path):
    engine.charger_moteur()
    context = SimpleNamespace(on=lambda *_args: None, close=AsyncMock(side_effect=RuntimeError("browser crashed")))
    world = engine.Monde("h01", context, "http://localhost", dossier=tmp_path)
    world.evidence.limit = 0
    world.erreurs_page.append("Error")
    with pytest.raises(RuntimeError, match="browser crashed"):
        asyncio.run(world.fermer())
    assert world.evidence.connection is None
    with closing(sqlite3.connect(world.evidence.path)) as database:
        assert database.execute("SELECT value FROM errors").fetchall() == [("Error",)]


def test_engine_spills_emit_paths_and_close_connections(tmp_path):
    engine.charger_moteur()
    events = []
    context = SimpleNamespace(on=lambda *_args: None, close=AsyncMock())
    world = engine.Monde("h01", context, "http://localhost", journal=events.append, dossier=tmp_path)
    world.evidence.limit = 2
    for index in range(8):
        world._anomalie(None, "erreur-js", f"Error {index}")
        world._requete(SimpleNamespace(resource_type="fetch", method="GET", url=f"http://localhost/item-{index}"))
    assert len([event for event in events if event["type"] == "anomalie"]) == 8
    spills = [event for event in events if event["type"] == "evidence-spilled"]
    assert {event["collection"] for event in spills} == {"errors", "requests"}
    assert all((tmp_path / event["path"]).is_file() for event in spills)
    asyncio.run(world.fermer())
    assert world.evidence.connection is None
    assert len(world.erreurs_page) == 8
    assert world.requetes["GET localhost/item-7"] == 1
    asyncio.run(world.fermer())
    assert world.evidence.connection is None
    context.close.assert_awaited_once()


def test_evidence_storage_error_closes_browser_and_invalidates_assertions(tmp_path, monkeypatch):
    engine.charger_moteur()
    events = []
    context = SimpleNamespace(on=lambda *_args: None, close=AsyncMock())
    world = engine.Monde("h01", context, "http://localhost", journal=events.append, dossier=tmp_path)
    world.evidence.limit = 0
    monkeypatch.setattr(world.evidence, "database", lambda: (_ for _ in ()).throw(OSError("disk full")))

    async def run():
        world._anomalie(None, "erreur-js", "Error")
        await asyncio.gather(*world.taches)
        assert world.closed and world.evidence_failed
        assert world.erreurs_page == ["Error"]
        reasons, invalid = await engine.verifier_attendu(world, [{"type": "no-page-error"}])
        assert reasons == [] and "storage failed" in invalid
        horde = engine.Horde.__new__(engine.Horde)
        horde.humains = {"h01": world}
        with pytest.raises(RuntimeError, match="storage failed"):
            await horde.jouer_action("h01", "done", {}, {})

    asyncio.run(run())
    assert any(event.get("collection_stopped") is True for event in events)
    context.close.assert_awaited_once()


def test_replay_references_spilled_evidence_in_its_output_folder(tmp_path, monkeypatch):
    engine.charger_moteur()
    output, source = tmp_path / "output", tmp_path / "source"
    output.mkdir()
    context = SimpleNamespace(on=lambda *_args: None, close=AsyncMock())

    async def create(_browser, hid, _sheet, url, _base, **kwargs):
        world = engine.Monde(hid, context, url, **kwargs)
        world.evidence.limit = 2
        world.nouvelle_page = AsyncMock()
        world.calme = AsyncMock()
        world.capturer = AsyncMock(return_value=None)
        world.lire = AsyncMock(return_value={"lignes": []})
        for index in range(8):
            world._anomalie(None, "erreur-js", f"Error {index}")
        return world

    monkeypatch.setattr(engine, "nouveau_monde", create)
    result = asyncio.run(engine.rejouer_un(None, {"url": "http://localhost", "etapes": [],
                                                "attendu": [{"type": "no-page-error"}]},
                                          False, output, "trial", source))
    assert result["ok"] is False
    assert result["erreurs_page"] == [f"Error {index}" for index in range(8)]
    assert len(result["live_evidence"]) == 1
    evidence_path = output / result["live_evidence"][0]["path"]
    assert evidence_path.is_file() and not source.exists()
    with closing(sqlite3.connect(evidence_path)) as database:
        assert database.execute("SELECT COUNT(*) FROM errors").fetchone()[0] == 8
    json.dumps(result)


@pytest.mark.browser
def test_real_chromium_error_and_request_burst_spills_without_losing_evidence(tmp_path):
    from playwright.async_api import async_playwright

    engine.charger_moteur()
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://127.0.0.1:9999/",
                                                 "--folder", str(tmp_path)])
    horde = engine.Horde(opts)
    count = 520  # Exceed the default collection threshold, not a test-only limit.

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                world = await engine.nouveau_monde(browser, "h01", {}, horde.url, tmp_path,
                                                   journal=horde.journal, dossier=tmp_path)
                horde.humains[world.id] = world
                horde.verrous[world.id] = asyncio.Lock()

                async def respond(route):
                    await route.fulfill(status=200, content_type="text/html", body="<title>Evidence fixture</title>Ready")

                # Every request is fulfilled inside Chromium's route handler; no server or remote network is used.
                await world.ctx.route("**/*", respond)
                page = await world.nouvelle_page(horde.url)
                await page.evaluate("""async n => {
                  for (let start = 0; start < n; start += 20) {
                    await Promise.all(Array.from({length: Math.min(20, n - start)},
                      (_, offset) => fetch('/route-' + (start + offset))));
                  }
                  await new Promise(resolve => {
                    for (let index = 0; index < n; index++) setTimeout(() => {
                      if (index === n - 1) setTimeout(resolve, 20);
                      throw new Error('Synthetic error ' + index);
                    }, 0);
                  });
                }""", count)
                assert len(world.erreurs_page) == count
                assert len(world.requetes) == count
                assert sum(world.requetes.values()) == count
                assert world.evidence.errors.disk and world.evidence.requests.disk
                assert world.erreurs_page[-1] == f"Synthetic error {count - 1}"
                reasons, invalid = await engine.verifier_attendu(world, [{"type": "no-page-error"}])
                assert reasons and invalid == ""
                world.statut = "fini"
                response = await horde.liberer_humain({"h": "h01"})
                assert response["ok"] and world.closed
                assert world.evidence.connection is None
                assert len(browser.contexts) == 0
                with closing(sqlite3.connect(world.evidence.path)) as database:
                    assert database.execute("SELECT COUNT(*) FROM errors").fetchone()[0] == count
                    assert database.execute("SELECT COUNT(*), SUM(value) FROM requests").fetchone() == (count, count)
                events = engine.lire_journal(tmp_path)
                assert len([event for event in events if event["type"] == "anomalie" and event["genre"] == "erreur-js"]) == count
                assert len([event for event in events if event["type"] == "evidence-spilled"]) == 2
            finally:
                await browser.close()
    try:
        asyncio.run(run())
    finally:
        horde.journal_f.close()
