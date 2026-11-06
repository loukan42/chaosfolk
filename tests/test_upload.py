import asyncio
from types import SimpleNamespace

import pytest

from chaosfolk import engine

# A visible button whose real <input type=file> is hidden and detached from it, as Mantine's FileButton renders it.
PAGE = """
<input type="file" id="direct">
<label id="label" for="labelled">Attach</label><input type="file" id="labelled" hidden>
<button id="button" onclick="document.getElementById('hidden').click()">Import</button>
<input type="file" id="hidden" style="display:none">
<button id="plain">Does nothing</button>
<script>
  window.picked = {};
  for (const input of document.querySelectorAll('input[type=file]'))
    input.addEventListener('change', () => { window.picked[input.id] = input.files[0].name; });
</script>
"""


def run_upload(tmp_path, target):
    upload = tmp_path / "uploads" / "contract.pdf"
    upload.parent.mkdir(exist_ok=True)
    upload.write_bytes(b"%PDF-1.4 synthetic")

    async def scenario():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            try:
                page = await browser.new_page()
                await page.set_content(PAGE)
                human = SimpleNamespace(dossier=tmp_path, delai_geste=2000)
                await engine.Monde.geste_upload(human, {"chemin": "uploads/contract.pdf"}, page.locator(target))
                return await page.evaluate("window.picked")
            finally:
                await browser.close()

    return asyncio.run(scenario())


@pytest.mark.browser
@pytest.mark.parametrize("target, field", [("#direct", "direct"), ("#label", "labelled"), ("#button", "hidden")])
def test_upload_fills_file_inputs_and_buttons_that_open_the_picker(tmp_path, target, field):
    assert run_upload(tmp_path, target) == {field: "contract.pdf"}


@pytest.mark.browser
def test_upload_explains_a_target_that_opens_no_picker(tmp_path):
    with pytest.raises(ValueError, match="aucun sélecteur de fichier"):
        run_upload(tmp_path, "#plain")


def test_check_reports_missing_psutil(monkeypatch, capsys):
    import importlib.metadata as metadata
    real = metadata.version

    def fake_version(name):
        if name == "psutil":
            raise metadata.PackageNotFoundError(name)
        return real(name)

    monkeypatch.setattr(metadata, "version", fake_version)
    assert engine.commande_verifier(SimpleNamespace()) == 1
    out = capsys.readouterr().out
    assert "psutil : MANQUE" in out
    assert 'pip install --upgrade "psutil>=6,<8"' in out
