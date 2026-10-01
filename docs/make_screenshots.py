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

docs/tests/<name>.png (MANUAL.md, "Test drawings"):
    Each SVG in extensions/tests/ on a white sheet with a thin grey edge, 500 px on its long side at
    device scale 2, layers hidden in Inkscape stay hidden. A drawing added to tests/ gets its picture
    on the next run; its paragraph in MANUAL.md is written by hand.

docs/ui/<name>.png (MANUAL.md, next to the paragraph that describes the element):
    Crops of single elements at device scale 2, on the demo drawing, A4 landscape, 1:1, iDraw A4,
    connected and homed: app-bar (status to Stop), placement (Position, scale, rotation unfolded),
    layers, run (Start plot to the estimate), outside-notice and outside-dialog (sheet A5),
    pause-dialog (before "!2 Detail red"), board-tools (corner button and
    zoom), sheet-machine, splitter, command-reference,
    reset-dialog. The MANUAL.md width of each is half its pixel width.
    Made by hand, not by this script (native dropdowns and tooltips are drawn outside the page):
    model-dropdown, test-drawing-dropdown, estimate-tooltip, path-number-tooltip, console-log (log and
    input line after a stopped plot), title-block (zoomed in on the board). Take them again
    with Shift-Cmd-4 on a Retina screen when these controls change.

The other pictures (manual-connect, manual-paper, manual-pen, manual-steps) are cut from single
steps of the panel and are not made by this script.
"""
import glob
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


def test_drawings(browser):
    out = os.path.join(HERE, "tests")
    os.makedirs(out, exist_ok=True)
    page = browser.new_page(device_scale_factor=2)
    for path in sorted(glob.glob(os.path.join(EXT, "tests", "*.svg"))):
        page.goto("file://" + os.path.abspath(path))
        w, h = page.evaluate("""() => {
            const s = document.documentElement, w = s.width.baseVal.value, h = s.height.baseVal.value;
            if (!s.getAttribute('viewBox')) s.setAttribute('viewBox', `0 0 ${w} ${h}`);   // DrawingBot exports: px user units
            const vb = s.viewBox.baseVal, sheet = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            for (const [k, v] of Object.entries({x: vb.x, y: vb.y, width: vb.width, height: vb.height, fill: '#fff',
                stroke: '#bbb', 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke'})) sheet.setAttribute(k, v);
            s.insertBefore(sheet, s.firstChild);
            const k = 500 / Math.max(w, h);
            s.setAttribute('width', Math.round(w * k)); s.setAttribute('height', Math.round(h * k));
            return [Math.round(w * k), Math.round(h * k)]; }""")
        page.set_viewport_size({"width": w, "height": h})
        name = os.path.splitext(os.path.basename(path))[0] + ".png"
        page.screenshot(path=os.path.join(out, name))
        print("  tests/" + name)
    page.close()


def ui_crops(page):
    out = os.path.join(HERE, "ui")
    os.makedirs(out, exist_ok=True)
    def shot(name, locator=None, clip=None):
        page.mouse.move(1, 899)                                   # no hover effect on the element
        page.wait_for_timeout(200)
        path = os.path.join(out, name + ".png")
        if locator is not None:
            locator.screenshot(path=path)
        else:
            page.screenshot(path=path, clip=clip)
        print("  ui/" + name + ".png")
    def around(boxes, pad=8):                                     # clip around the union of bounding boxes
        x0, y0 = min(b["x"] for b in boxes) - pad, min(b["y"] for b in boxes) - pad
        x1, y1 = max(b["x"] + b["width"] for b in boxes) + pad, max(b["y"] + b["height"] for b in boxes) + pad
        return {"x": max(0, x0), "y": max(0, y0), "width": x1 - max(0, x0), "height": y1 - max(0, y0)}
    start(page, "iDraw A4")
    tab(page, 1)
    select(page, "#fmt", "A4")
    select(page, "#orient", "landscape")
    tab(page, 3)
    select(page, "#testFile", "")
    page.wait_for_function("() => S.svg_name === 'idraw_demo.svg'")
    tab(page, 4)
    page.click("button[data-pl='1:1']")
    page.wait_for_function("() => S.placement === '1:1'")
    group = lambda title: page.locator("#panel .grp", has=page.locator("h2", has_text=title))
    dialog = lambda sel: around([page.locator(sel).bounding_box()], pad=16)   # with a margin of the scrim
    page.evaluate("() => cmd('pen_up')")
    expect(page.locator("#penlbl")).to_have_text("pen up")

    shot("app-bar", clip=around([page.locator("#status").bounding_box(), page.locator("#stop").bounding_box()]))
    shot("board-tools", page.locator(".board .tools"))
    shot("sheet-machine", page.locator("#fitseg"))
    sp = page.locator("#splitter").bounding_box()
    shot("splitter", clip={"x": sp["x"] + sp["width"] / 2 - 140, "y": sp["y"] - 24, "width": 280, "height": 64})
    page.click("#refBtn")
    shot("command-reference", clip=dialog("#ref"))
    page.click("#refClose")
    page.click("#resetBtn")
    shot("reset-dialog", clip=dialog("#resetDlg"))
    page.click("#resetCancel")

    page.click("#adj summary")
    shot("placement", page.locator("#adj"))
    page.click("#adj summary")
    shot("layers", group("Layers"))
    shot("run", group("Run").locator(".row").first)

    tab(page, 1)
    select(page, "#fmt", "A5")                                    # the A4 drawing at 1:1 leaves an A5 sheet
    tab(page, 4)
    page.wait_for_function("() => S.outside > 0")
    shot("outside-notice", page.locator("#panel .msg", has_text="leave the sheet"))
    page.click("button[data-cmd=plot]")
    shot("outside-dialog", clip=dialog("#outDlg"))
    page.click("#outCancel")
    tab(page, 1)
    select(page, "#fmt", "A4")
    tab(page, 4)
    page.wait_for_function("() => S.outside === 0")

    pause = page.locator("#panel tr", has_text="!2 Detail red").locator("input[data-k=pause]")
    if not pause.is_checked():
        pause.check()
    page.wait_for_function("() => S.layers[1].pause")
    page.click("button[data-cmd=plot]")
    page.wait_for_selector("#overlay.show", timeout=60000)
    shot("pause-dialog", clip=dialog("#overlay .dialog"))
    page.click("#pauseStop")
    page.wait_for_function("() => S.state.status === 'ready' && !S.state.busy", timeout=30000)


def main():
    httpd = idraw_server.serve(os.path.join(EXT, "idraw_demo.svg"), sim=True, port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            test_drawings(browser)
            for shot in (readme, manual_resume, ui_crops):
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
