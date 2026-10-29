"""Regression checks for journal memory use and failed browser startup cleanup."""
import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chaosfolk import engine


def test_journal_iteration_is_lazy_and_closes_early(monkeypatch, tmp_path):
    class Journal(io.StringIO):
        lines_read = 0

        def __next__(self):
            self.lines_read += 1
            return super().__next__()

        def read(self, *_args):
            raise AssertionError("The complete journal must not be buffered")

    source = Journal('{"type":"action","action":"cliquer"}\n' * 1000)
    monkeypatch.setattr(Path, "open", lambda *_args, **_kwargs: source)
    events = engine.iterer_journal(tmp_path)
    assert next(events)["action"] == "click"
    assert source.lines_read == 1
    events.close()
    assert source.closed


def test_journal_preserves_unicode_line_separators_and_skips_broken_records(tmp_path):
    event = {"type": "action", "action": "type", "args": {"text": "First\u2028second\u2029third"}}
    path = tmp_path / "journal.jsonl"
    path.write_bytes((json.dumps(event, ensure_ascii=False) + '\nnull\n[]\n{"missing":"type"}\n').encode()
                     + b'{"cut":"\xe2\n{"type":"action","action":"reload"}\n')
    events = engine.lire_journal(tmp_path)
    assert len(events) == 2
    assert events[0]["args"]["text"] == event["args"]["text"]
    assert events[1]["action"] == "reload"


def test_missing_journal_keeps_optional_and_required_behavior(tmp_path):
    assert engine.lire_journal(tmp_path, obligatoire=False) == []
    with pytest.raises(SystemExit, match="pas de journal"):
        engine.lire_journal(tmp_path)


def test_resume_scans_events_without_building_a_list(tmp_path, monkeypatch):
    engine.charger_moteur()
    events = [{"type": "action", "h": "h01", "n": 41, "t": 2000},
              {"type": "panne-debut", "id": "p7", "t": 3000},
              {"type": "action", "h": "h01", "n": 42, "t": 4000}]
    (tmp_path / "journal.jsonl").write_text("\n".join(map(json.dumps, events)), encoding="utf-8")
    monkeypatch.setattr(engine, "lire_journal", lambda *_args, **_kwargs: pytest.fail("resume buffered all events"))
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://localhost", "--folder", str(tmp_path)])
    horde = engine.Horde(opts)
    try:
        assert horde.n_repris == {"h01": 42}
        assert horde.horodatage() >= 4000
    finally:
        horde.journal_f.close()


def test_fragmented_socket_response_preserves_unicode(monkeypatch):
    expected = {"ok": True, "texte": "é" * 10000}
    payload = (json.dumps(expected, ensure_ascii=False) + "\n").encode()

    class Connection:
        def __enter__(self):
            self.parts = iter(payload[i:i + 127] for i in range(0, len(payload), 127))
            return self

        def __exit__(self, *_args):
            pass

        def sendall(self, _data):
            pass

        def recv(self, _size):
            return next(self.parts, b"")

    monkeypatch.setattr(engine, "info_serveur", lambda: {"port": 1234, "jeton": "test"})
    monkeypatch.setattr(engine.socket, "create_connection", lambda *_args, **_kwargs: Connection())
    assert engine.envoyer({"cmd": "status"}) == expected


@pytest.mark.parametrize("error", [RuntimeError("init failed"), asyncio.CancelledError()])
def test_context_is_closed_when_initialization_fails(tmp_path, error):
    engine.charger_moteur()
    context = SimpleNamespace(add_init_script=AsyncMock(side_effect=error), close=AsyncMock())
    browser = SimpleNamespace(new_context=AsyncMock(return_value=context))
    with pytest.raises(type(error)):
        asyncio.run(engine.nouveau_monde(browser, "h01", {}, "http://localhost", tmp_path))
    context.close.assert_awaited_once()


@pytest.mark.parametrize("error", [RuntimeError("navigation failed"), asyncio.CancelledError()])
def test_replay_closes_context_when_initial_navigation_fails(tmp_path, monkeypatch, error):
    engine.charger_moteur()
    context = SimpleNamespace(close=AsyncMock())
    world = SimpleNamespace(ctx=context, pannes=[], nouvelle_page=AsyncMock(side_effect=error), fermer=context.close)
    monkeypatch.setattr(engine, "nouveau_monde", AsyncMock(return_value=world))
    scenario = {"url": "http://localhost", "etapes": []}
    with pytest.raises(type(error)):
        asyncio.run(engine.rejouer_un(None, scenario, False, tmp_path, "trial", tmp_path))
    context.close.assert_awaited_once()


def test_browser_startup_failure_cancels_app_start_before_cleanup(tmp_path, monkeypatch):
    from playwright import async_api

    engine.charger_moteur()
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://localhost", "--folder", str(tmp_path)])
    horde = engine.Horde(opts)
    order = []

    async def run():
        started = asyncio.Event()

        async def start_app():
            started.set()
            try:
                await asyncio.Future()
            finally:
                order.append("app-cancelled")

        async def start_browser(*_args):
            await started.wait()
            raise RuntimeError("browser failed")

        async def close():
            order.append("cleanup")

        monkeypatch.setattr(horde, "app_au_demarrage", start_app)
        monkeypatch.setattr(horde, "fermer", close)
        monkeypatch.setattr(engine, "lancer_navigateur", start_browser)
        monkeypatch.setattr(async_api, "async_playwright", lambda: SimpleNamespace(start=AsyncMock()))
        with pytest.raises(RuntimeError, match="browser failed"):
            await horde.lancer_horde()

    try:
        asyncio.run(run())
        assert order == ["app-cancelled", "cleanup"]
    finally:
        horde.journal_f.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_action_timeout_or_cancellation_joins_its_browser_task(cancel):
    engine.charger_moteur()

    async def run():
        world = engine.Monde("h01", SimpleNamespace(on=lambda *_args: None), "http://localhost")
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def gesture():
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.set()

        task = asyncio.create_task(world.executer(gesture(), delai=0.01 if not cancel else 60))
        await started.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await task
        assert stopped.is_set()
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


def test_dialog_keeps_action_alive_until_answer():
    engine.charger_moteur()

    async def run():
        world = engine.Monde("h01", SimpleNamespace(on=lambda *_args: None), "http://localhost")
        answered = asyncio.Event()
        dialog = SimpleNamespace(accept=AsyncMock(side_effect=lambda _text: answered.set()))

        async def gesture():
            world.dialogue = dialog
            world.evt_dialogue.set()
            await answered.wait()
            return "ok"

        assert await world.executer(gesture()) == "boite"
        suspended = world.tache_suspendue
        assert not suspended.done()
        await world.repondre_boite(True)
        assert suspended.done() and suspended.result() == "ok"
        assert world.tache_suspendue is None
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())
