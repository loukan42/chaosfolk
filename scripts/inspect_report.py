"""Inspect a generated synthetic demo report and save desktop/mobile previews."""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".horde/checks"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    errors, external = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: external.append(request.url) if request.url.startswith(("http:", "https:")) else None)
        page.goto(args.report.resolve().as_uri())
        page.locator('.finding').first.wait_for()
        page.get_by_role('button', name='EN', exact=True).click()
        assert page.locator('.cast-card').count() == page.evaluate('catalog.length')
        assert page.locator('.screen-card').count() == 4
        assert page.locator('.mini-screen img').count() == 4
        assert page.locator('.finding').count() == 1
        assert page.locator('.finding .good').first.inner_text() == 'Reproduced'
        assert page.locator('.finding-toggle').first.get_attribute('aria-expanded') == 'false'
        assert page.locator('#findings-section').bounding_box()['y'] < page.locator('#overview-title').bounding_box()['y']
        page.get_by_role('button', name='Observed', exact=True).click()
        assert page.locator('.finding').count() == 0
        page.get_by_role('button', name='Reproduced', exact=True).click()
        assert page.locator('.finding').count() == 1
        page.locator('.screen-card').first.click()
        assert page.locator('#person').input_value() == 'before'
        page.get_by_role('button', name='Next event').click()
        assert 'Event 2 of 3' in page.locator('#narrative').inner_text()
        page.get_by_role('button', name='Previous event').click()
        page.locator('#person').select_option('all')
        page.locator('.finding-toggle').first.click()
        page.get_by_text('Inspect trial screenshots', exact=True).click()
        page.locator('.proof-image').last.scroll_into_view_if_needed()
        page.wait_for_function("Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)")
        page.get_by_text('Inspect trial screenshots', exact=True).click()
        page.locator('.finding-toggle').first.click()
        # Regression: a partial series must never be advertised as reproduced.
        assert not page.evaluate("valid({fois:3,demandes:4,casses:3,mode:'traitement'})")
        assert not page.evaluate("proven({condition:'offline',preuves:{avant:{fois:3,demandes:3,casses:3,mode:'traitement'},temoin:{fois:3,demandes:3,casses:0,mode:'traitement'}}})")
        assert not page.evaluate("localImage('https://example.com/private.png')")
        assert not page.evaluate("localImage('../private.png')")
        assert not page.evaluate("localImage('%2e%2e/private.png')")
        page.get_by_role('button', name='All findings').click()
        page.locator('#cast-section').evaluate('e=>e.open=true')
        page.locator('#cast-section').scroll_into_view_if_needed()
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(args.output / 'report-en-desktop.png'), full_page=True)
        page.get_by_role('button', name='FR', exact=True).click()
        assert page.locator('html').get_attribute('lang') == 'fr'
        assert page.locator('#findings-title').inner_text() == 'À corriger'
        assert page.locator('#title').inner_text() == '1 point à vérifier'
        page.get_by_role('button', name='Voir le prompt', exact=True).click()
        assert page.locator('#prompt-panel').is_visible()
        page.get_by_role('button', name='Voir le prompt', exact=True).click()
        page.screenshot(path=str(args.output / 'report-desktop.png'), full_page=True)
        page.set_viewport_size({"width": 375, "height": 812})
        page.evaluate('window.scrollTo(0,0)')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(args.output / 'report-mobile.png'), full_page=True)
        # Persona routing: use a controlled UI fixture without fabricating a real session.
        assert page.evaluate("typeof avatar === 'function'")
        assert not errors, errors
        assert not external, external
        browser.close()
    print('Report verified: FR/EN, compact findings, real screen mosaic, profiles, evidence, filters, timeline, screenshots, mobile layout, no external requests.')


if __name__ == '__main__':
    main()
