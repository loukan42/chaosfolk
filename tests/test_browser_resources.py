"""Resource release preserves evidence and leaves other users running."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from chaosfolk import engine


def make_horde(tmp_path):
    engine.charger_moteur()
    opts = engine.construire_parseur().parse_args(["serve", "--url", "http://localhost", "--folder", str(tmp_path)])
    return engine.Horde(opts)


def fake_world(horde, status="fini"):
    async def save_state(path):
        engine.ecrire_json(path, {"cookies": [], "origins": [{"origin": "http://localhost", "localStorage": []}]})

    context = SimpleNamespace(on=lambda *_args: None, close=AsyncMock(), storage_state=AsyncMock(side_effect=save_state))
    world = engine.Monde("h01", context, horde.url, journal=horde.journal)
    world.statut = status
    world.erreurs_page.append("Synthetic error")
    world.requetes["GET localhost/api"] = 3
    horde.humains[world.id] = world
    horde.verrous[world.id] = asyncio.Lock()
    return world, context


@pytest.mark.parametrize("status", ["fini", "abandon"])
def test_release_keeps_counts_and_storage_state_and_is_idempotent(tmp_path, status):
    horde = make_horde(tmp_path)
    world, context = fake_world(horde, status)

    async def run():
        page = object()
        world.pages.append(page)
        world.refs[page] = {"n": 5}
        world.ecrans[page] = ["Screen"]
        world.dernier_complet = (page, ["Screen"])
        assert (await horde.liberer_humain({"h": "h01"}))["ok"]
        assert (await horde.liberer_humain({"h": "h01"}))["ok"]
        assert world.closed and world.ctx is None
        assert world.pages == [] and world.refs == {} and world.ecrans == {}
        assert world.dernier_complet is None
        assert world.erreurs_page == ["Synthetic error"]
        assert world.requetes == {"GET localhost/api": 3}
        assert world.released_state.is_file()
        copied = tmp_path / "copied-state.json"
        assert (await horde.sauver_etat({"h": "h01", "fichier": str(copied)}))["ok"]
        assert json.loads(copied.read_text()) == json.loads(world.released_state.read_text())
        assert not (await horde.inspecter({"h": "h01", "js": "document.title"}))["ok"]
        assert not (await horde.auditer({"h": "h01"}))["ok"]

    try:
        asyncio.run(run())
        context.close.assert_awaited_once()
        assert [e["type"] for e in engine.lire_journal(tmp_path)] == ["browser-released"]
        assert not horde.autorise({"cmd": "release", "jeton": horde.jeton})
        assert horde.autorise({"cmd": "release", "jeton": horde.jeton_chef})
    finally:
        horde.journal_f.close()


@pytest.mark.parametrize("status,phase,target", [
    ("en cours", None, None), ("fini", "active", "h01"), ("fini", "programmee", None),
    ("fini", "admission", "h01"), ("fini", "redemarrage", None),
])
def test_release_refuses_active_users_and_pending_or_active_faults(tmp_path, status, phase, target):
    horde = make_horde(tmp_path)
    _, context = fake_world(horde, status)
    if phase:
        horde.pannes = [{"id": "p1", "h": target, "phase": phase}]
    try:
        assert not asyncio.run(horde.liberer_humain({"h": "h01"}))["ok"]
        context.close.assert_not_awaited()
        context.storage_state.assert_not_awaited()
    finally:
        horde.journal_f.close()


def test_failed_storage_capture_keeps_browser_available(tmp_path):
    horde = make_horde(tmp_path)
    world, context = fake_world(horde)
    context.storage_state.side_effect = OSError("disk full")
    try:
        with pytest.raises(OSError, match="disk full"):
            asyncio.run(horde.liberer_humain({"h": "h01"}))
        assert not world.closed and not world.releasing
        context.close.assert_not_awaited()
    finally:
        horde.journal_f.close()


def test_close_joins_background_and_dialog_tasks_before_releasing_context(tmp_path):
    horde = make_horde(tmp_path)
    world, context = fake_world(horde)

    async def run():
        started = asyncio.Event()
        stopped = []

        async def operation(name):
            started.set()
            try:
                await asyncio.Future()
            finally:
                stopped.append(name)

        world.lancer(operation("download"))
        world.tache_suspendue = asyncio.create_task(operation("dialog"))
        await started.wait()
        await world.fermer()
        assert sorted(stopped) == ["dialog", "download"]
        assert world.taches == set() and world.tache_suspendue is None
        assert len(asyncio.all_tasks()) == 1
        await world.fermer()

    try:
        asyncio.run(run())
        context.close.assert_awaited_once()
    finally:
        horde.journal_f.close()


def test_release_waits_for_download_and_rejects_new_faults_during_storage_capture(tmp_path):
    horde = make_horde(tmp_path)
    world, context = fake_world(horde)
    original_save = context.storage_state.side_effect

    async def run():
        download = asyncio.create_task(asyncio.sleep(60))
        world.taches.add(download)
        assert not (await horde.liberer_humain({"h": "h01"}))["ok"]
        download.cancel()
        await asyncio.gather(download, return_exceptions=True)

        async def save_state(path):
            with pytest.raises(ValueError, match="released"):
                await horde.programmer_panne({"type": "offline", "humains": "h01"})
            await original_save(path)

        context.storage_state.side_effect = save_state
        assert (await horde.liberer_humain({"h": "h01"}))["ok"]
        with pytest.raises(ValueError, match="released"):
            await horde.programmer_panne({"type": "offline", "humains": "h01"})

    try:
        asyncio.run(run())
    finally:
        horde.journal_f.close()


@pytest.mark.browser
def test_release_closes_only_finished_browser_and_keeps_journal_and_other_context(tmp_path):
    from playwright.async_api import async_playwright

    horde = make_horde(tmp_path)

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                for hid in ("h01", "h02"):
                    world = await engine.nouveau_monde(browser, hid, {}, horde.url, tmp_path, journal=horde.journal)
                    page = await world.nouvelle_page()
                    await page.set_content(f"<title>{hid}</title><button>Ready</button>")
                    horde.humains[hid] = world
                    horde.verrous[hid] = asyncio.Lock()
                horde.humains["h01"].statut = "fini"
                horde.journal({"type": "action", "h": "h01", "n": 1, "action": "done", "ecran": ["Ready"]})
                assert (await horde.liberer_humain({"h": "h01"}))["ok"]
                assert len(browser.contexts) == 1
                assert await horde.humains["h02"].page.title() == "h02"
                assert engine.lire_journal(tmp_path)[0]["ecran"] == ["Ready"]
                assert horde.humains["h01"].released_state.is_file()
            finally:
                await browser.close()

    try:
        asyncio.run(run())
    finally:
        horde.journal_f.close()
