"""Self-test for idraw_core: python3 test_idraw_core.py"""
import idraw_core as core


class Capture(core.SimTransport):
    def __init__(self):
        super().__init__(speed_factor=1e9)
        self.lines = []

    def send(self, line, seconds=0.0, timeout=None):
        self.lines.append(line)
        return super().send(line, 0)


class DeadSerial:
    """A pyserial stand-in that never answers."""
    def write(self, data):
        pass

    def readline(self):
        return b""

    def close(self):
        pass


def test_link_lost():
    core.REPLY_SLACK = 0.05
    t = core.SerialTransport("dead")
    t.ser = DeadSerial()
    p = core.Plotter()
    p.transport = t          # skip open(): the handshake needs a live board
    p.status = "ready"
    p.start(p.goto, 10, 0)
    p._worker.join(5)
    assert not p._worker.is_alive()
    kinds = [k for k, _ in list(p.events.queue)]
    assert "error" in kinds and p.status == "disconnected" and p.transport is None, (kinds, p.status)
    core.REPLY_SLACK = 15.0


def test_mapping_and_plot():
    t = Capture()
    p = core.Plotter()
    p.connect(t)
    p.home()
    assert "$H" in t.lines and "G92 X0 Y0" in t.lines
    t.lines.clear()
    p.plot_strokes([([(10, 20), (30, 20)], None, None, 0)], finish_home=False)
    moves = [l for l in t.lines if l.startswith("G1 X")]
    # document (10,20) -> G-code X=-20 Y=-10
    assert moves[0].startswith("G1 X-20.000 Y-10.000 F8000"), moves[0]
    assert moves[1].startswith("G1 X-20.000 Y-30.000 F2000"), moves[1]
    zs = [l for l in t.lines if l.startswith("G1 Z")]
    assert zs == ["G1 Z0.50 F5000", "G1 Z5.00 F5000", "G1 Z0.50 F5000"], zs
    assert p.z_up is True and (p.x, p.y) == (30, 20)


def test_dialects():
    t = Capture()
    p = core.Plotter()
    p.model = "AxiDraw V3/A4"
    p.connect(t)
    p.home()
    assert "EM,1,1" in t.lines and not any(l.startswith("$") for l in t.lines)
    t.lines.clear()
    p.profile.update(pen_up=60, pen_down=30)
    p.plot_strokes([([(10, 20), (30, 20)], None, None, 0)], finish_home=False)
    # (0,0) -> (10,20): a = 30 mm, b = -10 mm at 80 steps/mm; then +20 mm in x
    sm = [l for l in t.lines if l.startswith("SM,")]
    assert sm[0].endswith(",2400,-800") and sm[1].endswith(",1600,1600"), sm
    assert "SC,5,15248" in t.lines and "SC,5,20641" in t.lines, t.lines   # 30 % and 60 %
    assert (p.x, p.y) == (30, 20)
    p.model = "GRBL plotter A3"
    t.lines.clear()
    p.home()
    p.goto(10, 20)
    assert t.lines[:2] == ["$H", "G92 X0 Y0"] and t.lines[-1].startswith("G1 X10.000 Y20.000"), t.lines
    assert core.model_label("iDraw A1") == "iDraw A1" and core.model_label("iDraw A4").endswith("(untested)")


def test_resume_from():
    t = Capture()
    p = core.Plotter()
    p.connect(t)
    p.home()
    t.lines.clear()
    strokes = [([(0, 0), (10, 0)], None, None, 0), ([(20, 0), (30, 0)], None, None, 1), ([(40, 0), (50, 0)], None, None, 1)]
    p.plot_strokes(strokes, {1: "pause layer"}, finish_home=False, start=2)   # layer 1 already begun: no pause
    moves = [l for l in t.lines if l.startswith("G1 X")]
    assert moves[0].startswith("G1 X0.000 Y-40.000") and len(moves) == 2, moves
    kinds = [k for k, _ in list(p.events.queue)]
    assert "pause" not in kinds
    prog = [d for k, d in list(p.events.queue) if k == "progress"]
    assert prog[0]["i"] == 2 and prog[0]["done"] == 20 and prog[-1]["i"] == 3 and prog[-1]["done"] == 30, prog


def test_hide_lines():
    line = [[(0, 5), (20, 5)]]
    square = [[(5, 0), (15, 0), (15, 10), (5, 10)]]
    ring = [[(0, 0), (30, 0), (30, 30), (0, 30)], [(10, 10), (20, 10), (20, 20), (10, 20)]]
    # a filled square hides the middle of the line below it; its own outline stays
    r = core.hide_lines([(line, False, None, True), (square, True, "nonzero", True)])
    assert r[0] == [[(0, 5), (5, 5)], [(15, 5), (20, 5)]] and len(r[1]) == 1, r
    # unfilled square hides nothing; an unstroked fill plots nothing
    r = core.hide_lines([(line, False, None, True), (square, False, None, True), (square, True, None, False)])
    assert r[0] == [[(0, 5), (5, 5)], [(15, 5), (20, 5)]] and r[1] and r[2] == [], r
    # evenodd ring: the hole is see-through
    r = core.hide_lines([([[(-5, 15), (35, 15)]], False, None, True), (ring, True, "evenodd", False)])
    assert r[0] == [[(-5, 15), (0, 15)], [(10, 15), (20, 15)], [(30, 15), (35, 15)]], r
    # through the loader: the test drawing has two lines, a filled square, an open square and a ring
    import os
    _w, _h, layers = core.load_svg(os.path.join(core.HERE, "tests", "A4-landscape-hidden-lines.svg"), hiding=True)
    n_plain = len(core.load_svg(os.path.join(core.HERE, "tests", "A4-landscape-hidden-lines.svg"))[2][0].paths)
    assert len(layers[0].paths) == n_plain + 3, (len(layers[0].paths), n_plain)   # 2 lines each split once, ring line split twice


def test_origin_and_stop():
    t = Capture()
    p = core.Plotter()
    p.connect(t)
    p.home()
    p.jog(50, 40)
    p.set_origin()
    assert (p.x, p.y) == (0, 0) and p.machine_origin == (-50, -40)
    p.stop()
    p.plot_strokes([([(0, 0), (100, 0)], None, None, 0)])
    assert not any(l.startswith("G1 X-0.000 Y-100") for l in t.lines)


def test_raw_tracking():
    t = Capture()
    p = core.Plotter()
    p.connect(t)
    p.home()
    p.raw("G1 X-20 Y-10 F3000")          # machine (-20,-10) -> document (10, 20)
    assert (p.x, p.y) == (10, 20)
    p.raw("G91"); p.raw("G1 X-5")       # relative: document y += 5
    assert (p.x, p.y) == (10, 25)
    p.jog(1, 0)                         # software move restores G90 first
    assert t.lines[-2:] == ["G90", "G1 X-25.000 Y-11.000 F8000"], t.lines[-2:]
    p.raw("G1 Z5"); assert p.z_up is False
    p.raw("Z0.5"); assert p.z_up is True
    p.raw("G92 X0 Y0")
    assert (p.x, p.y) == (0, 0) and p.machine_origin == (-11, -25)
    p.raw("$1=254"); assert p.motors_free and not p.bounds_known
    p.raw("$H"); assert p.homed and p.motors_free is False


def test_text_and_title_block():
    assert core.text_width("AB", 2.0) > core.text_width("A", 2.0) > 0
    a = core.text_strokes("A", 10, 20, 2.0)
    ys = [y for p in a for _, y in p]
    assert abs(max(ys) - 20) < 1e-6 and abs(min(ys) - 18) < 1e-6      # baseline at y, cap height 2 mm
    assert core.text_strokes("\u2603", 0, 0, 1) == core.text_strokes("?", 0, 0, 1)   # unknown glyph -> ?
    rows = [("SHEET", "A4 297.0 x 210.0 mm"), ("FILE", "x" * 80)]
    tb = core.title_block_strokes((297, 210), "br", rows)
    xs = [x for p in tb for x, _ in p]; ys = [y for p in tb for _, y in p]
    assert 297 - 78 - 1e-6 <= min(xs) and max(xs) <= 297 - 6 + 1e-6    # inside the block, right corner
    assert 210 - 27 - 1e-6 <= min(ys) and max(ys) <= 210 - 6 + 1e-6
    tl = core.title_block_strokes((297, 210), "tl", rows)
    assert min(x for p in tl for x, _ in p) >= 6 - 1e-6 and min(y for p in tl for _, y in p) >= 6 - 1e-6


def test_load_svg_without_viewbox(tmp=None):
    import os, tempfile
    path = os.path.join(tempfile.gettempdir(), "idraw_noviewbox.svg")
    open(path, "w").write('<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm">'
                          '<path d="M0 0 L50 25"/></svg>')
    w, h, layers = core.load_svg(path)
    pts = layers[0].paths[0]
    mm = 25.4 / 96                                     # user units are px
    assert (w, h) == (100, 50) and abs(pts[-1][0] - 50 * mm) < 1e-3 and abs(pts[-1][1] - 25 * mm) < 1e-3, pts


def test_place_and_tests():
    lyr = core.Layer("a", [[(0, 0), (297, 210)]])
    fit = core.place([lyr], (297, 210), (420, 297), "fit")[0].paths[0]
    assert abs(fit[0][1] - 10) < 1e-6 and abs(fit[1][1] - 287) < 1e-6  # height fills, 10 mm margin
    cen = core.place([lyr], (297, 210), (420, 297), "center")[0].paths[0]
    assert abs(cen[0][0] - 61.5) < 1e-6
    for name, fn in core.TESTS.items():
        strokes = fn(0, 0)
        assert strokes and all(len(s[0]) >= 2 for s in strokes), name
    assert abs(core.path_length([(0, 0), (3, 4)]) - 5) < 1e-9


if __name__ == "__main__":
    test_mapping_and_plot()
    test_dialects()
    test_link_lost()
    test_resume_from()
    test_hide_lines()
    test_origin_and_stop()
    test_raw_tracking()
    test_text_and_title_block()
    test_load_svg_without_viewbox()
    test_place_and_tests()
    print("ok")
