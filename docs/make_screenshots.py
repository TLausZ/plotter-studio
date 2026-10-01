"""Make the screenshots in docs/ again after a change to the web UI: python3 docs/make_screenshots.py

Needs Playwright (see TESTING.md). Runs the server with the simulator and an empty settings file,
so the user's settings are not touched. Window 1440 x 900 at device scale 2, i.e. 2880 x 1800 px.

docs/screenshot.png (README, picture above the folders):
    The Plot step while a plot runs. Model iDraw A1 (its travel range fits an A3 sheet; with the
    default iDraw A4 the sheet exceeds the travel and Start plot asks first), connected to the
    simulator, homed, paper A3 portrait, test drawing A3-portrait-iDraw-test-sheet.svg from the
    Speed step, placement 1:1. Taken at about path 213 of 471: plotted strokes black, the rest
    grey, the dotted blue travel trace, the pen cross mid-sheet, the progress bar at about 90 %.

docs/manual-resume.png (MANUAL.md, end of "Plot"):
    The path picker after a stop. Demo drawing idraw_demo.svg, paper A4 landscape, placement 1:1,
    pause before "!2 Detail red" switched off. The plot is stopped at about path 60, then the
    curve (path 5) is clicked on the board: drawn thick, paths 1 to 4 done, the field shows 5,
    the buttons read "Resume from path 5" and "Plot only".

The other pictures (manual-connect, manual-paper, manual-pen, manual-steps) are cut from single
steps of the panel and are not made by this script.
"""
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.join(HERE, "..", "extensions")
sys.path.insert(0, EXT)
os.chdir(EXT)   # the server finds tests/ and the demo drawing next to itself

import idraw_core
import idraw_server
from playwright.sync_api import expect, sync_playwright

idraw_core.SimTransport.__init__.__defaults__ = (10.0,)   # fast, but slow enough to catch a running plot
tmp = tempfile.TemporaryDirectory()
idraw_core.SETTINGS_FILE = os.path.join(tmp.name, "settings.json")


def select(page, selector, value):
    """Select and wait for the server's reply, so two selects cannot finish in the wrong order."""
    with page.expect_response(lambda r: "/api/cmd" in r.url):
        page.select_option(selector, value)


def start(page, model):
    page.wait_for_selector("#steps li")
    if page.locator("#connBtn").text_content() == "Disconnect":   # the model is locked while connected
        page.click("#connBtn")
        expect(page.locator("#connBtn")).to_have_text("Connect")
    select(page, "#model", model)
    page.select_option("#port", "Simulation")
    page.click("#connBtn")
    expect(page.locator("#status")).to_have_text("ready")
    page.click("button[data-cmd=home]")
    page.wait_for_function("() => S.state.homed && !S.state.busy")


def tab(page, i):
    page.locator("#steps li").nth(i).click()


def readme(page):
    start(page, "iDraw A1")
    tab(page, 1)
    select(page, "#fmt", "A3")
    select(page, "#orient", "portrait")
    page.wait_for_function("() => S.paper_name === 'A3' && S.paper[0] === 297 && S.paper[1] === 420")
    tab(page, 3)
    select(page, "#testFile", "A3-portrait-iDraw-test-sheet.svg")
    page.wait_for_function("() => S.svg_name === 'A3-portrait-iDraw-test-sheet.svg'")
    tab(page, 4)
    page.click("button[data-cmd=plot]")
    page.wait_for_function("() => S.progress && S.progress.i >= 213", timeout=120000)
    page.mouse.move(1000, 880)
    page.screenshot(path=os.path.join(HERE, "screenshot.png"))
    page.click("#stop")
    page.wait_for_function("() => S.state.status === 'ready' && !S.state.busy", timeout=30000)


def manual_resume(page):
    start(page, "iDraw A4")
    tab(page, 1)
    select(page, "#fmt", "A4")
    select(page, "#orient", "landscape")
    tab(page, 3)
    select(page, "#testFile", "")
    page.wait_for_function("() => S.svg_name === 'idraw_demo.svg'")
    tab(page, 4)
    page.click("button[data-pl='1:1']")
    page.locator("#panel tr", has_text="!2 Detail red").locator("input[data-k=pause]").uncheck()
    page.wait_for_function("() => !S.layers[1].pause")
    page.click("button[data-cmd=plot]")
    page.wait_for_function("() => S.progress && S.progress.i >= 60", timeout=60000)
    page.click("#stop")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    page.wait_for_function("() => S.state.status === 'ready' && !S.state.busy")
    x, y = page.evaluate("""() => { const el = document.querySelectorAll('#strokes path')[4];
        const p = el.getPointAtLength(el.getTotalLength() * 0.3).matrixTransform(el.getScreenCTM()); return [p.x, p.y]; }""")
    page.mouse.click(x, y)
    expect(page.locator("#pickN")).to_have_value("5")
    page.mouse.move(1000, 880)
    page.wait_for_timeout(300)
    page.screenshot(path=os.path.join(HERE, "manual-resume.png"))


def main():
    httpd = idraw_server.serve(os.path.join(EXT, "idraw_demo.svg"), sim=True, port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for shot in (readme, manual_resume):
                page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
                page.goto("http://127.0.0.1:%d/" % httpd.server_address[1])
                shot(page)
                page.close()
                print("  " + shot.__name__)
            browser.close()
    finally:
        httpd.shutdown()
    print("ok")


if __name__ == "__main__":
    main()
