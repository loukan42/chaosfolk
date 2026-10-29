"""Record the real scan settings for the README. Requires Playwright and FFmpeg.

Run from the repository root: python scripts/record_audit_scan.py
The temporary audit never starts. Every recorded selection is verified in SQLite.
English labels are applied to the recording's HTML, JS and API responses only.
"""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from playwright.sync_api import expect, sync_playwright

from chaosfolk.audit_dashboard import make_server
from chaosfolk.audit_session import Session


def english_dashboard(route):
    """Translate recording labels while keeping the real session and controls."""
    response = route.fetch()
    source = response.text()
    translations = json.loads(Path(__file__).with_name("audit_scan_en.json").read_text(encoding="utf-8"))
    if "/api/" in route.request.url:
        if response.status == 204:
            route.fulfill(response=response)
            return
        value = json.loads(source)
        for entry in value.get("entries", []):
            if "category" in entry:
                entry["category"] = translations.get(entry["category"], entry["category"])
        route.fulfill(response=response, json=value)
        return
    for french, english in sorted(translations.items(), key=lambda item: len(item[0]), reverse=True):
        source = source.replace(french, english)
    route.fulfill(response=response, body=source)


def main():
    root = Path(__file__).resolve().parents[1]
    assets = root / "assets"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("Install FFmpeg to encode the recording as a GIF.")
    assets.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="chaosfolk-scan-recording-") as directory:
        folder = Path(directory)
        session = Session(folder / "session")
        session.create("standard")
        server = make_server(session)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        frames = []
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                page = browser.new_page(viewport={"width":1120,"height":1000}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/", english_dashboard)
                page.route("**/audit-live.js", english_dashboard)
                page.route("**/api/**", english_dashboard)
                page.goto(f"http://127.0.0.1:{server.server_port}/#{server.audit_token}")
                expect(page.locator("#connection")).to_contain_text("Connected")

                def capture():
                    expect(page.locator("body")).not_to_have_class("busy")
                    expect(page.locator("html")).to_have_attribute("lang", "en")
                    assert not any(label in page.locator("body").inner_text() for label in
                                   ("sélectionnés", "Catalogue QA", "Indisponible", "Enregistrer", "Approfondi",
                                    "Autoriser l’audit"))
                    path = folder / f"frame-{len(frames):03d}.png"
                    page.screenshot(path=str(path), animations="disabled")
                    frames.append(path)

                def depth(value, count):
                    page.locator(f"input[value={value}]").check()
                    expect(page.locator("#selection-count")).to_contain_text(f"{count} tests selected")
                    assert session.snapshot()["config"]["depth"] == value
                    capture()

                capture()
                depth("quick", 41)
                depth("deep", 116)
                page.locator("#search").fill("email-formats")
                page.locator("#tests").scroll_into_view_if_needed()
                capture()
                page.locator('#tests input[data-check="email-formats"]').uncheck()
                expect(page.locator("#selection-count")).to_contain_text("115 tests selected")
                assert session.snapshot()["config"]["excluded"] == ["email-formats"]
                capture()
                page.locator("#search").fill("")
                page.evaluate("scrollTo(0,0)")
                capture()
                depth("quick", 40)
                depth("deep", 115)
                page.locator(".budget summary").click()
                capture()
                page.locator('#limits input[name="minutes"]').fill("15")
                page.locator('#limits input[name="actions"]').fill("250")
                capture()
                page.get_by_role("button", name="Save limits").click()
                expect(page.locator("#actions")).to_have_text("0 / 250")
                capture()
                state = session.snapshot()
                assert state["config"]["limits"]["max_seconds"] == 900
                assert state["config"]["limits"]["max_actions"] == 250
                assert state["config"]["excluded"] == ["email-formats"]
                assert state["config"]["state"] == "ready" and state["tested"] == 0
                assert state["config"]["usage"]["tokens"] is None and not errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(5)
        shutil.copyfile(frames[0], assets / "audit-scan.png")
        target = assets / "audit-scan.gif"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", "1/2",
                        "-i", str(folder / "frame-%03d.png"), "-filter_complex",
                        "[0:v]split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5",
                        "-loop", "0", str(target)], check=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(json.dumps({"path":str(target),"frames":len(frames),"seconds":len(frames)*2,"bytes":target.stat().st_size}))


if __name__ == "__main__":
    main()
