"""End-to-end test of the web UI: python3 test_idraw_e2e.py [--headed] [name ...]

Starts idraw_server with the simulator on a free port, drives the page with Playwright
(Chromium, headless) and prints "ok". Needs: pip install playwright; playwright install chromium.
Each check is one function; add a new check by writing check_<name>(page) and listing it in CHECKS.
reset(page) runs before every check, so checks are independent of their order and a single one
can be run by name: python3 test_idraw_e2e.py splitter zoom_and_pan
"""
import os
import re
import sys
import threading
import time

from playwright.sync_api import expect, sync_playwright

import idraw_core
import idraw_server

HERE = os.path.dirname(os.path.abspath(__file__))
# ponytail: simulator 40x faster than real so home and plot finish in seconds
idraw_core.SimTransport.__init__.__defaults__ = (40.0,)


def tab(page, i):
    page.locator("#steps li").nth(i).click()


def click_cmd(page, selector):
    """Click a command button and wait for the server's reply, so a following wait_idle sees the work."""
    with page.expect_response(lambda r: "/api/cmd" in r.url):
        page.click(selector)


def wait_paper(page, name, w, h):
    """Wait until the page's snapshot shows this paper (name and size in mm)."""
    page.wait_for_function("([n, w, h]) => S && S.paper_name === n && Math.abs(S.paper[0] - w) < 1e-6 && Math.abs(S.paper[1] - h) < 1e-6",
                           arg=[name, w, h])


def wait_idle(page, timeout=15.0):
    """Wait until the plotter's worker has finished (the status chip alone can lag or still say ready)."""
    t0 = time.time()
    while page.evaluate("async () => (await (await fetch('/api/snapshot')).json()).state.busy"):
        assert time.time() - t0 < timeout, "plotter stayed busy"
        time.sleep(0.05)


def reset(page):
    """Ground state before every check: fresh page, no browser storage, mm, A4 landscape,
    1:1, connected to the simulator, homed, pen up, standing at the origin."""
    page.evaluate("() => localStorage.clear()")
    page.reload()
    expect(page.locator("#steps li")).to_have_count(5)
    page.click("#units button[data-unit=mm]")
    tab(page, 0)
    if page.locator("#connBtn").text_content() != "Disconnect":
        page.select_option("#port", "Simulation")
        page.click("#connBtn")
    expect(page.locator("#status")).to_have_text("ready")
    click_cmd(page, "button[data-cmd=home]")
    wait_idle(page)
    tab(page, 2)
    page.click("button[data-cmd=pen_up]")
    expect(page.locator("#penlbl")).to_have_text("pen up", timeout=10000)
    tab(page, 1)
    page.select_option("#fmt", "A4")
    page.select_option("#orient", "landscape")
    wait_paper(page, "A4", 297, 210)
    tab(page, 4)
    page.click("button[data-pl='1:1']")
    tab(page, 0)


def check_connect_and_home(page):
    expect(page).to_have_title("iDraw Interactive")
    page.click("#connBtn")                        # Disconnect
    expect(page.locator("#status")).to_have_text("disconnected")
    expect(page.locator("#penlbl")).to_have_text("pen ?")
    page.select_option("#port", "Simulation")
    page.click("#connBtn")
    expect(page.locator("#status")).to_have_text("ready")
    click_cmd(page, "button[data-cmd=home]")
    wait_idle(page)
    expect(page.locator("#status")).to_have_text("ready")
    expect(page.locator("#pos")).to_have_text("X 0.0  Y 0.0 mm")
    expect(page.locator("#penlbl")).to_have_text("pen ?")   # home does not move the pen


def check_steps_fit_without_scrolling(page):
    for i in range(5):
        tab(page, i)
        over = page.evaluate("() => { const p = document.getElementById('panel'); return p.scrollHeight - p.clientHeight; }")
        assert over <= 1, "step %d overflows by %d px" % (i + 1, over)
        expect(page.locator("#steps li").nth(i)).to_have_class(re.compile("active"))


def check_keyboard_jog_and_pen(page):
    tab(page, 2)                      # Pen step shows the jog controls
    page.keyboard.press("2")          # 10 mm step
    page.keyboard.press("ArrowRight")
    expect(page.locator("#pos")).to_have_text("X 10.0  Y 0.0 mm", timeout=10000)
    expect(page.locator("#penlbl")).to_have_text("pen up")   # jog raises the pen first
    page.keyboard.press("ArrowDown")
    expect(page.locator("#pos")).to_have_text("X 10.0  Y 10.0 mm", timeout=10000)
    page.keyboard.press("Space")
    expect(page.locator("#penlbl")).to_have_text("pen down", timeout=10000)
    page.keyboard.press("Space")
    expect(page.locator("#penlbl")).to_have_text("pen up", timeout=10000)
    page.click("button[data-cmd=goto]")   # home symbol: back to the origin
    expect(page.locator("#pos")).to_have_text("X 0.0  Y 0.0 mm", timeout=10000)


def check_console(page):
    cli = page.locator("#cli")
    cli.fill("G1 X-20 Y-10 F3000")
    cli.press("Enter")
    expect(page.locator("#pos")).to_have_text("X 10.0  Y 20.0 mm", timeout=10000)
    expect(page.locator("#log")).to_contain_text("> G1 X-20 Y-10 F3000")
    expect(page.locator("#trace line")).to_have_count(1)
    cli.press("ArrowUp")
    expect(cli).to_have_value("G1 X-20 Y-10 F3000")
    cli.fill("")
    page.click("#refBtn")
    expect(page.locator("#ref")).to_be_visible()
    page.click("#ref tr[data-c='$QP'] td")
    expect(page.locator("#ref")).to_be_hidden()
    expect(cli).to_have_value("$QP")
    cli.press("Enter")
    expect(page.locator("#log")).to_contain_text("> $QP")


def check_paper_and_title_block(page):
    tab(page, 1)
    page.select_option("#fmt", "A3")
    wait_paper(page, "A3", 420, 297)
    page.select_option("#orient", "portrait")
    wait_paper(page, "A3", 297, 420)
    page.select_option("#fmt", "A4")
    page.select_option("#orient", "landscape")
    wait_paper(page, "A4", 297, 210)


def drag_splitter(page, dy):
    box = page.locator("#splitter").bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x, y + dy, steps=5)
    page.mouse.up()


def check_splitter(page):
    board, console = page.locator(".board"), page.locator(".console")
    height = lambda loc: loc.evaluate("e => e.offsetHeight")
    h0 = height(board)
    drag_splitter(page, -150)
    assert abs(height(board) - (h0 - 150)) <= 2
    assert page.evaluate("() => +localStorage.boardH") == height(board)
    drag_splitter(page, 2000)                     # console keeps two log lines plus the input line
    assert height(console) >= 74
    drag_splitter(page, -2000)                    # board keeps 120 px
    assert height(board) >= 120
    page.locator("#splitter").dblclick()          # reset to the default and forget the stored height
    assert height(board) == h0
    assert page.evaluate("() => localStorage.boardH") is None


def check_zoom_and_pan(page):
    svg = page.locator("#preview")
    vb0 = [float(v) for v in svg.get_attribute("viewBox").split()]
    zoom = page.locator("#zoom")
    zoom.fill("6")                     # index 6 = 4x
    expect(page.locator("#zoomlbl")).to_have_text("4×")
    vb = [float(v) for v in svg.get_attribute("viewBox").split()]
    assert abs(vb[2] - vb0[2] / 4) < 1e-6 and abs(vb[3] - vb0[3] / 4) < 1e-6
    assert abs((vb[0] + vb[2] / 2) - (vb0[0] + vb0[2] / 2)) < 1e-6   # zoom keeps the centre
    assert svg.evaluate("s => s.classList.contains('pan')")
    box = svg.bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 100, cy + 50, steps=5)
    page.mouse.up()
    vb2 = [float(v) for v in svg.get_attribute("viewBox").split()]
    assert vb2[0] < vb[0] and vb2[1] < vb[1]   # dragging right and down shows what was left and above
    zoom.fill("0")                     # 0.5x
    expect(page.locator("#zoomlbl")).to_have_text("0.5×")
    vb3 = [float(v) for v in svg.get_attribute("viewBox").split()]
    assert abs(vb3[2] - vb0[2] * 2) < 1e-6
    assert not svg.evaluate("s => s.classList.contains('pan')")
    svg.dblclick()
    expect(page.locator("#zoomlbl")).to_have_text("1×")
    assert [float(v) for v in svg.get_attribute("viewBox").split()] == vb0


def check_title_block_corner(page):
    """The title block is a server setting and a virtual last layer; the board shows it as strokes."""
    btn = page.locator("#tbpos")
    tb_layer = page.locator("#panel tr", has_text="Title block")
    def corner():
        pw, ph = page.evaluate("() => S.paper")
        pts = page.evaluate("() => S.strokes.filter(s => s.layer === S.layers.length - 1).flatMap(s => s.pts)")
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        assert min(xs) >= 0 and max(xs) <= pw and min(ys) >= 0 and max(ys) <= ph
        return ("t" if max(ys) < ph / 2 else "b") + ("l" if max(xs) < pw / 2 else "r")
    expect(btn).to_have_text("◲")
    assert corner() == "br"
    tab(page, 4)
    expect(tb_layer).to_have_count(1)
    for icon, want in [("◱", "bl"), ("◰", "tl"), ("◳", "tr")]:
        btn.click()
        expect(btn).to_have_text(icon)
        assert corner() == want, (want, corner())
    btn.click()                                            # off: no layer, no strokes
    expect(btn).to_have_text("▢")
    expect(tb_layer).to_have_count(0)
    assert page.evaluate("() => S.tb_corner") == "off"
    page.reload()
    expect(page.locator("#tbpos")).to_have_text("▢")     # remembered on the server
    page.locator("#tbpos").click()
    expect(page.locator("#tbpos")).to_have_text("◲")
    tab(page, 4)
    page.locator("#panel tr", has_text="Title block").locator("input[data-k=enabled]").uncheck()
    page.wait_for_function("() => !S.strokes.some(s => s.layer === S.layers.length - 1)")   # unticked: not in the strokes, so neither plotted nor drawn


def check_paper_fields_and_orientation(page):
    tab(page, 1)
    page.select_option("#fmt", "A5")
    expect(page.locator("#pw")).to_have_value("210.0")
    expect(page.locator("#ph")).to_have_value("148.0")
    expect(page.locator("#preview rect[fill='var(--paper)']").first).to_have_attribute("width", "210")
    page.select_option("#orient", "portrait")
    expect(page.locator("#pw")).to_have_value("148.0")
    expect(page.locator("#ph")).to_have_value("210.0")
    expect(page.locator("#preview rect[fill='var(--paper)']").first).to_have_attribute("height", "210")
    page.select_option("#fmt", "Custom")
    wait_paper(page, "Custom", 148, 210)   # panel re-rendered
    page.fill("#pw", "300")
    page.fill("#ph", "200")
    page.click("#paperApply")
    wait_paper(page, "Custom", 300, 200)
    page.select_option("#orient", "portrait")     # Custom: the fields rule, orientation does not swap them
    wait_paper(page, "Custom", 300, 200)


def check_units(page):
    page.click("#units button[data-unit=cm]")
    expect(page.locator("#pos")).to_contain_text("cm")
    assert page.evaluate("() => S.unit") == "cm"


def check_plot_with_pause(page):
    tab(page, 4)
    expect(page.locator("#layers tr, .layers tr, #panel input[type=checkbox]").first).to_be_visible()
    page.click("button[data-cmd=plot]")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    expect(page.locator("#overlay")).to_have_class(re.compile("show"), timeout=60000)
    expect(page.locator("#pauseName")).to_have_text("!2 Detail red")
    page.click("#pauseGo")
    expect(page.locator("#overlay")).not_to_have_class(re.compile("show"))
    expect(page.locator("#log")).to_contain_text("Plot finished.", timeout=120000)
    expect(page.locator("#status")).to_have_text("ready", timeout=15000)
    n = page.evaluate("() => S.strokes.length")
    expect(page.locator("#strokes path.done")).to_have_count(n)   # drawing plus title block


def check_reset_button(page):
    page.click("#units button[data-unit=cm]")
    page.locator("#zoom").fill("6")
    page.locator("#tbpos").click()
    tab(page, 1)
    page.select_option("#fmt", "A3")
    tab(page, 4)
    page.click("button[data-pl=fit]")
    page.locator("#panel input[data-k=enabled]").first.uncheck()
    page.click("#resetBtn")
    expect(page.locator("#resetDlg")).to_be_visible()
    page.click("#resetCancel")                     # cancel changes nothing
    expect(page.locator("#resetDlg")).to_be_hidden()
    expect(page.locator("#pos")).to_contain_text("cm")
    assert page.evaluate("() => S.paper_name") == "A3"
    page.click("#resetBtn")
    page.click("#resetGo")
    expect(page.locator("#steps li")).to_have_count(5)   # page reloaded
    expect(page.locator("#pos")).to_contain_text("mm")
    wait_paper(page, "A4", 297, 210)
    assert page.evaluate("() => S.placement") == "1:1"
    expect(page.locator("#zoomlbl")).to_have_text("1×")
    expect(page.locator("#tbpos")).to_have_text("◲")
    expect(page.locator("#status")).to_have_text("ready")   # connection stays
    tab(page, 4)
    for box in page.locator("#panel input[data-k=enabled]").all():
        expect(box).to_be_checked()
    expect(page.locator("#panel input[data-k=pause]").nth(0)).not_to_be_checked()   # "1 Frame"
    expect(page.locator("#panel input[data-k=pause]").nth(1)).to_be_checked()       # "!2 Detail red"
    assert page.evaluate("() => localStorage.length") == 0


def check_test_drawing_dropdown(page):
    """Speed step: a file from tests/ replaces the document, the first entry brings it back;
    switching clears trace, done marks and progress."""
    tab(page, 2)
    page.keyboard.press("2")
    page.keyboard.press("ArrowRight")                      # leaves one trace segment
    expect(page.locator("#trace line")).to_have_count(1)
    tab(page, 3)
    files = page.locator("#testFile option").all_text_contents()
    assert files[0].startswith("Document: idraw_demo.svg") and "A4-landscape-accuracy.svg" in files, files
    page.select_option("#testFile", "A4-landscape-accuracy.svg")
    page.wait_for_function("() => S.svg_name === 'A4-landscape-accuracy.svg' && S.test_file === 'A4-landscape-accuracy.svg'")
    expect(page.locator("#trace line")).to_have_count(0)
    expect(page.locator("#strokes path.done")).to_have_count(0)
    assert page.evaluate("() => S.progress") is None
    tab(page, 4)
    expect(page.locator("#panel tr", has_text="Accuracy")).to_have_count(1)
    tab(page, 3)
    page.select_option("#testFile", "")
    page.wait_for_function("() => S.svg_name === 'idraw_demo.svg' && S.test_file === ''")
    tab(page, 4)
    expect(page.locator("#panel tr", has_text="1 Frame")).to_have_count(1)


def check_outside_sheet_warning(page):
    """A4 drawing at 1:1 on A6: amber paths, a notice in the Plot step, Start plot asks first."""
    tab(page, 1)
    page.select_option("#fmt", "Custom")
    wait_paper(page, "Custom", 297, 210)
    page.fill("#pw", "148")
    page.fill("#ph", "105")
    page.click("#paperApply")
    wait_paper(page, "Custom", 148, 105)
    assert page.evaluate("() => S.outside") > 0 and page.evaluate("() => S.beyond") == 0
    expect(page.locator("#strokes path.out").first).to_be_visible()
    tab(page, 4)
    expect(page.locator("#panel .msg", has_text="leave the sheet")).to_have_count(1)
    page.click("button[data-cmd=plot]")
    expect(page.locator("#outDlg")).to_be_visible()
    expect(page.locator("#outText")).to_contain_text("leave the sheet")
    page.click("#outCancel")
    expect(page.locator("#outDlg")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("ready")           # nothing started
    page.click("button[data-cmd=plot]")
    page.click("#outGo")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    page.keyboard.press("Escape")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    wait_idle(page)
    tab(page, 1)
    page.select_option("#fmt", "A4")
    wait_paper(page, "A4", 297, 210)
    page.wait_for_function("() => S.outside === 0")
    expect(page.locator("#strokes path.out")).to_have_count(0)
    tab(page, 4)
    expect(page.locator("#panel .msg", has_text="leave the sheet")).to_have_count(0)


def check_travel_trace_during_plot(page):
    """A plot leaves a dotted trace for pen-up travel only; it starts empty and clears at the next plot."""
    tab(page, 2)
    page.keyboard.press("2")
    page.keyboard.press("ArrowRight")
    expect(page.locator("#pos")).to_have_text("X 10.0  Y 0.0 mm", timeout=10000)
    expect(page.locator("#trace line.up[x2='10']")).to_have_count(1)   # the jog's segment (reset may leave others)
    tab(page, 4)
    page.locator("#panel tr", has_text="!2 Detail red").locator("input[data-k=pause]").uncheck()
    click_cmd(page, "button[data-cmd=plot]")
    expect(page.locator("#log")).to_contain_text("Plot finished.", timeout=120000)
    wait_idle(page)
    # cleared at plot start: the jog segment is gone; the return to the origin after the plot may remain
    expect(page.locator("#trace line.up[x2='10']")).to_have_count(0)
    assert page.locator("#trace line.travel").count() > 0
    assert page.locator("#trace line.down").count() == 0            # pen-down parts are the strokes
    n_travel = page.locator("#trace line.travel").count()
    dash = page.locator("#trace line.travel").first.get_attribute("stroke-dasharray")
    assert dash and float(dash.split()[0]) < float(dash.split()[1])  # dotted, not dashed
    click_cmd(page, "button[data-cmd=plot]")
    page.wait_for_function("(n) => document.querySelectorAll('#trace line.travel').length < n", arg=n_travel)
    page.keyboard.press("Escape")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    wait_idle(page)


def check_stop_button(page):
    """The red Stop in the app bar ends a plot like Esc."""
    tab(page, 4)
    page.locator("#panel tr", has_text="!2 Detail red").locator("input[data-k=pause]").uncheck()
    click_cmd(page, "button[data-cmd=plot]")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    page.click("#stop")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    wait_idle(page)
    expect(page.locator("#status")).to_have_text("ready")
    expect(page.locator("#penlbl")).to_have_text("pen up")


def check_stop_with_escape(page):
    tab(page, 4)
    page.click("button[data-cmd=plot]")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    page.keyboard.press("Escape")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    expect(page.locator("#status")).to_have_text("ready", timeout=15000)
    expect(page.locator("#penlbl")).to_have_text("pen up")


def check_model_dropdown(page):
    """Untested models carry the label, show the hint and switch the command dialect."""
    tab(page, 0)
    before = page.locator("#model").input_value()
    expect(page.locator("#model option[value='iDraw A1']")).to_have_text("iDraw A1")
    expect(page.locator("#model option[value='AxiDraw V3/A4']")).to_have_text("AxiDraw V3/A4 (untested)")
    page.select_option("#model", "AxiDraw V3/A4")
    expect(page.locator("#panel")).to_contain_text("Only the iDraw A1 has been tested")
    page.click("#connBtn")                    # reconnect: the dialect is set up on connect
    expect(page.locator("#connBtn")).to_have_text("Connect")
    page.click("#connBtn")
    expect(page.locator("#log")).to_contain_text("> EM,1,1", timeout=10000)
    click_cmd(page, "button[data-cmd=home]")  # no $H on an AxiDraw
    wait_idle(page)
    tab(page, 2)
    page.keyboard.press("2")
    page.keyboard.press("ArrowRight")         # 10 mm in x: a = b = 800 steps
    expect(page.locator("#log")).to_contain_text(",800,800", timeout=10000)
    after = page.locator("#log").text_content().split("> EM,1,1", 1)[1]
    assert "$H" not in after and "G1 " not in after, after
    tab(page, 0)
    page.select_option("#model", "iDraw A1")
    expect(page.locator("#panel")).not_to_contain_text("Only the iDraw A1 has been tested")
    page.select_option("#model", before)


def check_resume_from_path(page):
    """After a stop the Run group offers a slider and Resume from path N; the plot continues from there."""
    tab(page, 4)
    page.locator("#panel tr", has_text="!2 Detail red").locator("input[data-k=pause]").uncheck()
    click_cmd(page, "button[data-cmd=plot]")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    page.click("#stop")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    wait_idle(page)
    expect(page.locator("#resumeAt")).to_be_visible()
    n = page.evaluate("() => S.strokes.length")
    page.locator("#resumeAt").fill("1")                       # replot from the second path
    expect(page.locator("#resumeBtn")).to_have_text("Resume from path 2")
    expect(page.locator("#strokes path.done")).to_have_count(1)
    click_cmd(page, "#resumeBtn")
    expect(page.locator("#log")).to_contain_text("Resuming from path 2 of %d." % n, timeout=10000)
    expect(page.locator("#log")).to_contain_text("Plot finished.", timeout=120000)
    expect(page.locator("#status")).to_have_text("ready", timeout=15000)
    expect(page.locator("#strokes path.done")).to_have_count(n)


def check_hidden_lines(page):
    """Plot step: the checkbox reloads the drawing with lines behind fills removed."""
    tab(page, 3)
    page.select_option("#testFile", "A4-landscape-hidden-lines.svg")
    page.wait_for_function("() => S.svg_name === 'A4-landscape-hidden-lines.svg'")
    n = page.evaluate("() => S.strokes.length")
    tab(page, 4)
    expect(page.locator("#hiding")).not_to_be_checked()
    page.check("#hiding")
    page.wait_for_function("(n) => S.hiding && S.strokes.length === n + 3", arg=n)
    page.reload()                                            # the setting is remembered
    expect(page.locator("#steps li")).to_have_count(5)
    tab(page, 4)
    expect(page.locator("#hiding")).to_be_checked()
    page.uncheck("#hiding")
    page.wait_for_function("(n) => !S.hiding && S.strokes.length === n", arg=n)
    tab(page, 3)
    page.select_option("#testFile", "")


CHECKS = [check_connect_and_home, check_steps_fit_without_scrolling, check_keyboard_jog_and_pen,
          check_console, check_paper_and_title_block, check_paper_fields_and_orientation, check_units,
          check_splitter, check_zoom_and_pan, check_title_block_corner, check_reset_button,
          check_plot_with_pause, check_stop_with_escape, check_stop_button, check_test_drawing_dropdown,
          check_outside_sheet_warning, check_travel_trace_during_plot, check_model_dropdown,
          check_resume_from_path, check_hidden_lines]


def main():
    headed = "--headed" in sys.argv
    names = [a for a in sys.argv[1:] if not a.startswith("--")]
    checks = [c for c in CHECKS if not names or c.__name__[6:] in names]
    assert len(checks) == (len(names) or len(CHECKS)), "unknown check name in %s" % names
    settings = os.path.join(HERE, "idraw_interactive_settings.json")
    keep = open(settings, "rb").read() if os.path.exists(settings) else None
    httpd = idraw_server.serve(os.path.join(HERE, "idraw_demo.svg"), sim=True, port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/" % httpd.server_address[1]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not headed)
            page = browser.new_page(viewport={"width": 1280, "height": 690})
            page.goto(base)
            for check in checks:
                reset(page)
                check(page)
                print("  " + check.__name__)
            browser.close()
    finally:
        httpd.shutdown()
        if keep is not None:              # the run changes paper and unit; restore the user's settings
            open(settings, "wb").write(keep)
    print("ok")


if __name__ == "__main__":
    main()
