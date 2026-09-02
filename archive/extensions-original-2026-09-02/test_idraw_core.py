"""Selbsttest für idraw_core: python3 test_idraw_core.py"""
import idraw_core as core


class Capture(core.SimTransport):
    def __init__(self):
        super().__init__(speed_factor=1e9)
        self.lines = []

    def send(self, line, seconds=0.0):
        self.lines.append(line)
        return super().send(line, 0)


def test_mapping_and_plot():
    t = Capture()
    p = core.Plotter()
    p.connect(t)
    p.home()
    assert "$H" in t.lines and "G92 X0 Y0" in t.lines
    t.lines.clear()
    p.plot_strokes([([(10, 20), (30, 20)], None, None, 0)], finish_home=False)
    moves = [l for l in t.lines if l.startswith("G1 X")]
    # Dokument (10,20) -> G-Code X=-20 Y=-10
    assert moves[0].startswith("G1 X-20.000 Y-10.000 F8000"), moves[0]
    assert moves[1].startswith("G1 X-20.000 Y-30.000 F2000"), moves[1]
    zs = [l for l in t.lines if l.startswith("G1 Z")]
    assert zs == ["G1 Z0.50 F5000", "G1 Z5.00 F5000", "G1 Z0.50 F5000"], zs
    assert p.z_up is True and (p.x, p.y) == (30, 20)


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


def test_place_and_tests():
    lyr = core.Layer("a", [[(0, 0), (297, 210)]])
    fit = core.place([lyr], (297, 210), (420, 297), "fit")[0].paths[0]
    assert abs(fit[0][1] - 10) < 1e-6 and abs(fit[1][1] - 287) < 1e-6  # Höhe füllt, 10 mm Rand
    cen = core.place([lyr], (297, 210), (420, 297), "center")[0].paths[0]
    assert abs(cen[0][0] - 61.5) < 1e-6
    for name, fn in core.TESTS.items():
        strokes = fn(0, 0)
        assert strokes and all(len(s[0]) >= 2 for s in strokes), name
    assert abs(core.path_length([(0, 0), (3, 4)]) - 5) < 1e-9


if __name__ == "__main__":
    test_mapping_and_plot()
    test_origin_and_stop()
    test_place_and_tests()
    print("ok")
