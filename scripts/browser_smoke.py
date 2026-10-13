"""Exercise the production Next.js app through a real Chromium browser.

Requires Python Playwright and a system chromium binary. No external network calls.
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def run():
    output = Path(os.environ.get("CLAIMTRAIL_BROWSER_OUTPUT", "/tmp/claimtrail-browser"))
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:3000", wait_until="networkidle")
        page.get_by_role("button", name="Open sample").wait_for()
        page.screenshot(path=str(output / "home.png"), full_page=True)
        page.get_by_role("button", name="Open sample").click()
        page.get_by_role("heading", name="Correction notice", exact=True).first.wait_for()
        page.get_by_role("button", name="Evidence, 2 findings").hover()
        page.get_by_text("A fuller picture of the cost", exact=True).wait_for()
        page.get_by_role("button", name="Evidence, 2 findings").click()
        page.get_by_role("button", name="Independent payment ledger CT-007").wait_for()
        page.get_by_role("button", name="Explain proposed provenance relationship").focus()
        page.keyboard.press("Enter")
        page.get_by_role("heading", name="Earliest dated source located", exact=True).wait_for()
        assert "CT-008" in page.locator(".timeline").inner_text()
        page.get_by_role("button", name="Warnings, 7 findings").focus()
        page.get_by_text("Follow the earlier figure", exact=True).wait_for()
        page.keyboard.press("Enter")
        page.get_by_role("button", name="Original cost report CT-001", exact=False).wait_for()
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Evidence, 2 findings").click()
        page.screenshot(path=str(output / "workspace.png"), full_page=True)
        page.get_by_role("button", name="Find related occurrences", exact=False).first.click()
        page.get_by_role("heading", name="Related occurrences", exact=True).wait_for()
        page.get_by_label("Filter relationship", exact=True).select_option("Repeats")
        assert page.locator(".occurrence-card").count() == 7
        card = page.locator(".occurrence-card").filter(has=page.get_by_role("heading", name="Original cost report", exact=True))
        card.get_by_role("button", name="Open highlighted passage").click()
        page.locator(".page-image img").wait_for()
        page.wait_for_function("document.querySelector('.page-image img')?.complete && document.querySelector('.page-image img')?.naturalWidth > 0")
        assert page.locator(".passage-highlight").count() > 0
        page.get_by_role("button", name="Open evidence for highlighted claim on page 1").click()
        page.screenshot(path=str(output / "highlighted-passage.png"), full_page=True)
        page.get_by_role("button", name="Compare & review", exact=True).click()
        page.get_by_label("Review relationship", exact=True).select_option("Corrects")
        page.get_by_label("Decision reason", exact=True).fill("Same Meridian project and 1974 period; notice explicitly corrects the original report.")
        page.keyboard.press("Tab")
        assert page.evaluate("Boolean(document.activeElement.closest('[role=dialog]'))")
        page.get_by_role("button", name="Confirm relationship", exact=True).click()
        page.get_by_role("dialog").wait_for(state="hidden")
        page.reload(wait_until="networkidle")
        page.get_by_role("button", name="Find related occurrences", exact=False).first.click()
        page.get_by_text("These documents may repeat a corrected claim.", exact=True).wait_for()
        confirmed = page.locator(".occurrence-card").filter(has=page.get_by_role("heading", name="Original cost report", exact=True))
        assert "Confirmed" in confirmed.inner_text()
        page.get_by_label("Filter relationship", exact=True).select_option("Lookalike")
        lookalike = page.locator(".occurrence-card").filter(has=page.get_by_role("heading", name="Planning estimate — earlier year", exact=True))
        lookalike.get_by_role("button", name="Compare & review").click()
        page.get_by_label("Decision reason", exact=True).fill("Different reporting year; the 1973 estimate is outside this correction's scope.")
        page.get_by_role("button", name="Dismiss match", exact=True).click()
        page.get_by_role("dialog").wait_for(state="hidden")
        with page.expect_download() as download:
            page.get_by_role("link", name="Export report", exact=True).click()
        artifact = download.value
        artifact.save_as(str(output / artifact.suggested_filename))
        assert (output / artifact.suggested_filename).read_bytes().startswith(b"%PDF")
        page.get_by_role("button", name="Audit history", exact=True).click()
        page.get_by_text("Relationship confirmed", exact=True).first.wait_for()
        page.get_by_text("Relationship dismissed", exact=True).first.wait_for()
        mobile = browser.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        mobile.on("pageerror", lambda error: errors.append(str(error)))
        mobile.goto("http://127.0.0.1:3000", wait_until="networkidle")
        mobile.screenshot(path=str(output / "mobile-home.png"), full_page=True)
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        mobile.get_by_role("button", name="Open sample").click()
        mobile.get_by_role("heading", name="Evidence & related passages").wait_for()
        assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        mobile.screenshot(path=str(output / "mobile-workspace.png"), full_page=True)
        assert not errors, errors
        browser.close()
    print("Browser workflow passed: map previews and pins, real passage highlights, persistent confirmation/dismissal, PDF download, audit history, mobile list layout; no page errors.")


if __name__ == "__main__":
    run()
