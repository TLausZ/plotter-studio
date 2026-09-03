"""Write the built-in test patterns as SVG files: python3 make_test_svgs.py

One A4 landscape file per pattern in idraw_core.TESTS, one layer each, paths in mm.
The files are for looking at and editing in Inkscape; the plugin draws the patterns from code
(Speed step > Test patterns). Feed rates (speed test) and pen heights (pen height test) are
per-stroke settings that an SVG cannot carry; those files show the geometry only.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import idraw_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = (297, 210)


def svg(name, strokes):
    paths = "".join('    <path d="M%s"/>\n' % "L".join("%.3f %.3f" % p for p in s[0]) for s in strokes)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"\n'
            '     width="%dmm" height="%dmm" viewBox="0 0 %d %d">\n'
            '  <g inkscape:groupmode="layer" inkscape:label="%s" fill="none" stroke="#000" stroke-width="0.3">\n'
            '%s  </g>\n</svg>\n' % (PAGE[0], PAGE[1], PAGE[0], PAGE[1], name, paths))


def main():
    for name, fn in core.TESTS.items():
        strokes = fn(30, 30)                       # 30 mm from the sheet corner, like a plot from the origin
        path = os.path.join(HERE, "test-%s.svg" % name.lower().replace(" ", "-"))
        open(path, "w").write(svg(name, strokes))
        print(path, len(strokes), "strokes")


if __name__ == "__main__":
    main()
