"""End-to-end test of the web UI: python3 test_idraw_e2e.py [--headed]

Starts idraw_server with the simulator on a free port, drives the page with Playwright
(Chromium, headless) and prints "ok". Needs: pip install playwright; playwright install chromium.
Each check is one function; add a new check by writing check_<name>(page) and listing it in CHECKS.
"""
import os
import re
import sys
import threading

from playwright.sync_api import expect, sync_playwright

import idraw_core
import idraw_server

HERE = os.path.dirname(os.path.abspath(__file__))
# ponytail: simulator 40x faster than real so home and plot finish in seconds
idraw_core.SimTransport.__init__.__defaults__ = (40.0,)


def tab(page, i):
    page.locator("#steps li").nth(i).click()


def check_connect_and_home(page):
    expect(page).to_have_title("iDraw Interactive")
    expect(page.locator("#status")).to_have_text("disconnected")
    page.click("#units button[data-unit=mm]")     # independent of the stored settings
    page.select_option("#port", "Simulation")
    page.click("#connBtn")
    expect(page.locator("#status")).to_have_text("ready")
    page.click("button[data-cmd=home]")
    expect(page.locator("#status")).to_have_text("moving")
    expect(page.locator("#status")).to_have_text("ready", timeout=15000)
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
    expect(page.locator("#trace line")).to_have_count(4)   # three jog segments plus this one
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
    expect(page.locator("#preview .tb")).to_contain_text("A3 420.0 × 297.0 mm")
    page.select_option("#orient", "portrait")
    expect(page.locator("#preview .tb")).to_contain_text("A3 297.0 × 420.0 mm")
    page.select_option("#fmt", "A4")
    page.select_option("#orient", "landscape")
    expect(page.locator("#preview .tb")).to_contain_text("A4 297.0 × 210.0 mm")


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
    rect = page.locator("#preview .tb rect")
    pw, ph = page.evaluate("() => S.paper")
    def corner():
        x, y, w, h = [float(rect.get_attribute(a)) for a in ("x", "y", "width", "height")]
        return ("t" if y < ph / 2 else "b") + ("l" if x < pw / 2 else "r")
    assert corner() == "br"            # default
    btn = page.locator("#tbpos")
    for icon, want in [("◰", "tl"), ("◳", "tr"), ("◲", "br"), ("◱", "bl"), ("◰", "tl")]:
        btn.click()
        expect(btn).to_have_text(icon)
        assert corner() == want, (want, corner())
    assert page.evaluate("() => localStorage.tbCorner") == "tl"
    page.reload()
    expect(page.locator("#status")).to_have_text("ready")
    assert corner() == "tl"            # remembered
    for _ in range(2):
        btn.click()                    # back to br so the other checks see the default
    expect(btn).to_have_text("◲")


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
    page.fill("#pw", "300")
    page.fill("#ph", "200")
    page.click("#paperApply")
    expect(page.locator("#preview .tb")).to_contain_text("Custom 300.0 × 200.0 mm")
    page.select_option("#orient", "portrait")     # Custom: the fields rule, orientation does not swap them
    expect(page.locator("#preview .tb")).to_contain_text("Custom 300.0 × 200.0 mm")
    page.select_option("#fmt", "A4")
    page.select_option("#orient", "landscape")
    expect(page.locator("#preview .tb")).to_contain_text("A4 297.0 × 210.0 mm")


def check_units(page):
    page.click("#units button[data-unit=cm]")
    expect(page.locator("#pos")).to_contain_text("cm")
    expect(page.locator("#preview .tb")).to_contain_text("29.70 × 21.00 cm")
    page.click("#units button[data-unit=mm]")
    expect(page.locator("#pos")).to_contain_text("mm")


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
    expect(page.locator("#strokes path.done")).to_have_count(8)


def check_stop_with_escape(page):
    tab(page, 4)
    page.click("button[data-cmd=plot]")
    expect(page.locator("#status")).to_have_text("plotting", timeout=10000)
    page.keyboard.press("Escape")
    expect(page.locator("#log")).to_contain_text("Plot stopped.", timeout=30000)
    expect(page.locator("#status")).to_have_text("ready", timeout=15000)
    expect(page.locator("#penlbl")).to_have_text("pen up")


CHECKS = [check_connect_and_home, check_steps_fit_without_scrolling, check_keyboard_jog_and_pen,
          check_console, check_paper_and_title_block, check_paper_fields_and_orientation, check_units,
          check_splitter, check_zoom_and_pan, check_title_block_corner, check_plot_with_pause, check_stop_with_escape]


def main():
    headed = "--headed" in sys.argv
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
            for check in CHECKS:
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
