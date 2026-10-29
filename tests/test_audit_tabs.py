import pytest
import threading

from playwright.sync_api import expect, sync_playwright

from chaosfolk.audit_dashboard import make_server
from chaosfolk.audit_session import Session


@pytest.mark.browser
def test_two_open_tabs_do_not_reenable_each_others_exclusions(tmp_path):
    session=Session(tmp_path)
    session.create("deep")
    server=make_server(session)
    worker=threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            first=browser.new_page()
            second=browser.new_page()
            url=f"http://127.0.0.1:{server.server_port}/#{server.audit_token}"
            for page in (first,second):
                page.goto(url)
                expect(page.locator('#connection')).to_contain_text('Connecté')
            # Delay one tab's refresh, as can happen with a slow/inactive tab.
            second.route('**/api/state?after=*',lambda route:route.abort())
            first.locator('#search').fill('email-formats')
            first.locator('#tests input[data-check="email-formats"]').uncheck()
            expect(first.locator('#selection-count')).to_contain_text('1 retirés')
            second.locator('#search').fill('phone-formats')
            second.locator('#tests input[data-check="phone-formats"]').uncheck()
            expect(second.locator('#tests input[data-check="phone-formats"]')).not_to_be_checked()
            expect(second.locator('body')).not_to_have_class('busy')
            saved=session.snapshot()['config']['excluded']
            first.set_viewport_size({"width": 375, "height": 812})
            first.locator('.budget summary').click()
            first.locator('#limits input[name="browsers"]').fill('3')
            first.get_by_role('button', name='Enregistrer les limites').click()
            expect(first.locator('body')).not_to_have_class('busy')
            assert session.snapshot()['config']['limits']['max_browsers'] == 3
            assert first.evaluate('document.documentElement.scrollWidth <= innerWidth')
            first.get_by_role('button', name='Fermer le tableau de bord').click()
            expect(first.locator('#connection')).to_have_text('Tableau de bord fermé')
            assert first.locator('#start').is_disabled()
            assert session.snapshot()['config']['state'] == 'ready'
            browser.close()
            assert set(saved)=={'email-formats','phone-formats'},f'An earlier exclusion was silently lost: {saved}'
    finally:
        server.shutdown()
        server.server_close()
        worker.join(5)
