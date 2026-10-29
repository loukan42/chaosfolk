"""Browser regressions for the deterministic page audit."""
import pytest
from playwright.sync_api import sync_playwright

from chaosfolk.audit import AUDIT_JS, TARGET_MIN


@pytest.mark.browser
def test_audit_handles_prototype_named_ids_and_measures_each_element_once():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content("""<!doctype html><html lang="en"><title>Audit fixture</title><body>
                <h1>Form</h1><button id="constructor">Save</button><button id="constructor">Retry</button>
                <p id="__proto__">One</p><p id="__proto__">Two</p>
                <p id="toString">Three</p><p id="toString">Four</p>
                <button style="position:absolute;left:3000px">Outside viewport</button>
                </body></html>""")
            page.evaluate("""() => {
                const original = Element.prototype.getBoundingClientRect;
                window.measurements = new Map();
                Element.prototype.getBoundingClientRect = function(...args) {
                    measurements.set(this, (measurements.get(this) || 0) + 1);
                    return original.apply(this, args);
                };
            }""")
            result = page.evaluate(AUDIT_JS, TARGET_MIN)
            assert set(result["duplicate_ids"]) == {"constructor", "__proto__", "toString"}
            assert result["horizontal_overflow"]["document_width"] > 1280
            assert result["offscreen_controls"][0]["name"] == "Outside viewport"
            assert page.evaluate("Math.max(...measurements.values())") == 1
        finally:
            browser.close()
