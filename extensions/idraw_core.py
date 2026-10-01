"""
idraw_core.py

Control logic for the iDraw H (DrawCore board, GRBL dialect). No GUI dependency.

Architecture (three layers, see README.md in the project folder):

    UI (Tk wizard, later a web UI)  -->  Plotter (this module)  -->  Transport (Serial / Sim)

- Transport: a class with open() / close() / send(line, seconds). It only knows text
  lines and replies. For a different plotter (AxiDraw/EBB, another GRBL firmware) write
  a new transport or adapt the G-code generation in Plotter._move_abs / _z. For a
  different platform (web, CLI) write only a new UI against the Plotter API.
- Plotter: holds the state (position, pen, status, profile), offers blocking commands
  (home, jog, pen_up ...) and a plot run in a background thread. Reports everything to
  the UI through a queue.Queue (event protocol: see the Plotter docstring).
- Helpers: load SVG (through the digest from idraw_deps), placement on paper, test
  patterns, settings as JSON.

Coordinates and units:
- Document mm, origin at the top-left corner of the paper, x to the right, y down.
  The UI and all paths use this system exclusively.
- G-code sent to the firmware: X = -y, Y = -x (mapping taken from the original plugin,
  see the analysis document in the project folder). Only _move_abs knows this mapping.
- Z absolute in mm: small = pen up (0.5), large = pen down (5.0).
- Feed rates in mm/min, as GRBL expects.

Threading: every command that talks to the transport runs in a worker thread
(Plotter.start). The UI must not call Plotter methods on the GUI thread, because
send() blocks. Exceptions: stop(), resume(), connect(), disconnect().

Open points on the hardware (not tested yet, see README "Status"):
- Homing sequence and the sign of the axis mapping.
- Whether the firmware supports realtime commands (! feed hold, ~ resume, ? status).
  Stop therefore takes effect after the current G-code line.
"""

import json
import math
import re
import os
import queue
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "idraw_interactive_settings.json")

PAPER_FORMATS = {  # mm, landscape (width, height)
    "A1": (841, 594), "A2": (594, 420), "A3": (420, 297),
    "A4": (297, 210), "A5": (210, 148), "Letter": (279.4, 215.9),
}
MODELS = {  # travel in mm (x, y)
    # iDraw (DrawCore board, GRBL dialect with Z as the pen); values from idraw2_0_conf.py
    "iDraw A4": (300, 210), "iDraw A3": (430, 297), "iDraw A2": (594, 432),
    "iDraw A1": (864, 594), "iDraw A0": (1189, 841),
    # older models, in the original conf but not in its dropdown
    "iDraw V3 XLX": (595, 218), "iDraw V3/B6": (190, 140), "iDraw MiniKit": (160, 101.6),
    # AxiDraw (EiBotBoard, EBB commands, no G-code); values from axidraw_conf.py
    "AxiDraw V3/A4": (300, 218), "AxiDraw V3/A3": (430, 297), "AxiDraw SE/A2": (594, 432),
    "AxiDraw SE/A1": (864, 594), "AxiDraw V3 XLX": (595, 218), "AxiDraw V3/B6": (190, 140),
    "AxiDraw MiniKit": (160, 101.6), "AxiDraw ArtStation 1824": (609.6, 457.2),
    "AxiDraw ArtStation 2436": (914.4, 609.6),
    # any other GRBL 1.1 pen plotter with Z as the pen and home switches
    "GRBL plotter A4": (300, 210), "GRBL plotter A3": (430, 297),
    "GRBL plotter A2": (594, 432), "GRBL plotter A1": (864, 594),
}
TESTED = {"iDraw A1"}   # the only model this extension has been run on; all others are untested


def dialect(model):
    """drawcore: iDraw (GRBL with the original's axis mapping and homing dance).
    grbl: plain GRBL 1.1, document axes sent as they are. ebb: AxiDraw EiBotBoard."""
    return "ebb" if model.startswith("AxiDraw") else "grbl" if model.startswith("GRBL") else "drawcore"


def model_label(model):
    return model if model in TESTED else model + " (untested)"


# EBB (AxiDraw): 2032 steps per inch in high resolution (16x microstepping), servo pulse range
# from axidraw_conf.py; the profile's pen_up/pen_down are servo percent (0-100) on this dialect.
EBB_STEPS_PER_MM = 2032 / 25.4
EBB_SERVO_MIN, EBB_SERVO_MAX = 9855, 27831
Z_RATE = 5000  # feed rate for Z moves (mm/min), as in the original
REPLY_SLACK = 15.0  # s: a reply may arrive this much later than the expected move time


class LinkLost(IOError):
    """No reply from the board, or the serial port failed: the connection is dropped."""


def _import_serial():
    """pyserial: the installed one if present, else the pure-Python copy in idraw_deps."""
    try:
        import serial
    except ImportError:
        import sys
        sys.path.append(os.path.join(HERE, "idraw_deps"))
        import serial
    return serial


# ---------------------------------------------------------------- Transport
#
# Interface expected by Plotter:
#   name            display name (port or "Simulation")
#   open() -> str   open the connection, return the version string; raise on failure
#   close()
#   send(line, seconds=0.0) -> str
#                   send one line without line ending, return the reply line.
#                   `seconds` is the move duration estimated by the Plotter; a real
#                   transport ignores it (the firmware replies once it accepted the
#                   command), the simulation sleeps for it.
#                   Raise IOError on error:/ALARM: replies.

class SimTransport:
    """Simulated DrawCore: answers ok, sleeps proportionally to the move time."""
    name = "Simulation"

    def __init__(self, speed_factor=4.0):
        self.speed_factor = speed_factor  # 4 = demo runs four times faster than real
        self.version = "DrawCore V2.31 (sim)"

    def open(self):
        return self.version

    def close(self):
        pass

    def send(self, line, seconds=0.0, timeout=None):
        if seconds:
            time.sleep(seconds / self.speed_factor)
        if line.startswith("$B"):
            return "0"          # pause button not pressed
        if line.startswith("?"):
            return "<Idle>"
        return "ok"


class SerialTransport:
    """DrawCore, EBB or plain GRBL over pyserial. Handshake as in the original drawcore_serial.testPort."""
    # ponytail: not tested on the device yet; ? status and realtime commands (! ~) unverified
    # ponytail: EBB and plain GRBL handshakes written from the archived AxiDraw code and the
    # GRBL docs, never run on a board

    def __init__(self, port):
        self.name = port
        self.port = port
        self.ser = None
        self.version = ""

    @staticmethod
    def list_ports():
        """Serial ports, DrawCore (CH340, VID:PID 1A86:7523 or 1A86:8040) first."""
        try:
            comports = _import_serial().tools.list_ports.comports
        except (ImportError, AttributeError):
            try:
                from serial.tools.list_ports import comports
            except ImportError:
                return []
        found = []
        for p in comports():
            hw = getattr(p, "hwid", "") or ""
            if "1A86:7523" in hw or "1A86:8040" in hw or "04D8:FD92" in hw:
                found.insert(0, p.device)  # DrawCore and EBB first
            else:
                found.append(p.device)
        return found

    def open(self):
        serial = _import_serial()
        s = serial.Serial()
        s.port = self.port
        s.baudrate = 115200
        s.timeout = 1
        s.rts = False   # do not reset the board on open
        s.dtr = False
        s.open()
        s.write(b"$B\r")  # flush, as the original does
        s.readline()
        s.readline()
        s.reset_input_buffer()
        s.write(b"v\r")
        v = s.readline().decode("ascii", "replace").strip()
        if not v.startswith(("DrawCore", "EBB")):
            s.reset_input_buffer()      # plain GRBL answers "v" with an error; ask for $I
            s.write(b"$I\r")
            v = s.readline().decode("ascii", "replace").strip()
            s.readline()                # the ok after the [VER:...] line
            if not v.startswith("["):
                s.close()
                raise IOError("No DrawCore, EBB or GRBL on %s (reply: %r)" % (self.port, v))
        self.ser = s
        self.version = v
        if not v.startswith("EBB"):
            status = self.send("?")
            if "Alarm" in status:
                self.send("$X")   # clear alarm (e.g. after an emergency stop)
        return v

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    def send(self, line, seconds=0.0, timeout=None):
        """Send one line, return the reply. seconds is the expected move time; the reply
        may take that plus REPLY_SLACK (or timeout, if given), then LinkLost is raised."""
        limit = timeout if timeout is not None else seconds + REPLY_SLACK
        deadline = time.time() + limit
        resp = ""
        try:
            self.ser.write((line + "\r").encode("ascii"))
            while not resp and time.time() < deadline:
                resp = self.ser.readline().decode("ascii", "replace").strip()
        except (OSError, ValueError) as err:   # cable pulled, port closed
            raise LinkLost("Serial port failed after %s: %s" % (line, err))
        if not resp:
            raise LinkLost("No reply to %s within %d s." % (line, limit))
        if line.startswith("$B") or line.startswith("$QP") or line.startswith("$QT"):
            self.ser.readline()  # these queries return data followed by an ok
        if resp.startswith(("error", "ALARM", "!")):    # "!" is the EBB error prefix
            raise IOError("%s -> %s" % (line, resp))
        return resp


# ---------------------------------------------------------------- Settings
# One JSON file next to this module. Structure (everything optional):
#   {"model": "iDraw A4", "paper": [297, 210], "paper_name": "A4", "orient": "landscape",
#    "pos_mode": "jog", "last_port": "...", "last_profile": "Default",
#    "profiles": {"Default": {pen_up, pen_down, feed_draw, feed_travel, line_width}}}

def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


DEFAULT_PROFILE = {"pen_up": 0.5, "pen_down": 5.0, "feed_draw": 2000,
                   "feed_travel": 8000, "line_width": 0.3}


# ---------------------------------------------------------------- SVG loading

class Layer:
    """One SVG layer: name, polylines in document mm, control flags.

    pause: the plot stops before this layer (prefix "!" in the layer name; the UI can
           override). skip: documentation layer (prefix "%"), never plotted.
    enabled: set by the UI; skip layers start disabled.
    """

    def __init__(self, name, paths, pause=False, skip=False, number=None):
        self.name = name
        self.paths = paths      # list of polylines [(x_mm, y_mm), ...]
        self.pause = pause
        self.skip = skip
        self.number = number    # leading number in the layer name, e.g. 2 for "2 red"
        self.enabled = not skip


# --- hidden-line removal (pure Python; Inkscape's Python has no pyclipper)

def _inside(pt, polys, rule):
    """Point in a filled shape made of closed polygons, by SVG fill rule."""
    x, y = pt
    wn = cr = 0
    for poly in polys:
        n = len(poly)
        for i in range(n):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
            if (y0 <= y) != (y1 <= y):              # edge crosses the horizontal ray's height
                xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
                if xi > x:
                    cr += 1
                    wn += 1 if y1 > y0 else -1
    return (cr % 2 == 1) if rule == "evenodd" else (wn != 0)


def _clip_polyline(pts, polys, rule):
    """Parts of the open polyline pts that lie outside the filled shape polys."""
    out, cur = [], []
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        ts = [0.0, 1.0]
        for poly in polys:
            n = len(poly)
            for i in range(n):
                (cx, cy), (dx, dy) = poly[i], poly[(i + 1) % n]
                den = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx)
                if abs(den) < 1e-12:
                    continue
                t = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / den
                u = ((cx - ax) * (by - ay) - (cy - ay) * (bx - ax)) / den
                if 0 < t < 1 and 0 <= u <= 1:
                    ts.append(t)
        ts.sort()
        for t0, t1 in zip(ts, ts[1:]):
            if t1 - t0 < 1e-9:
                continue
            p0 = (ax + (bx - ax) * t0, ay + (by - ay) * t0)
            p1 = (ax + (bx - ax) * t1, ay + (by - ay) * t1)
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            if _inside(mid, polys, rule):
                if len(cur) > 1:
                    out.append(cur)
                cur = []
            else:
                if not cur:
                    cur = [p0]
                cur.append(p1)
    if len(cur) > 1:
        out.append(cur)
    return out


def hide_lines(items):
    """items: [(subpaths, filled, fill_rule, stroked)] in z-order, bottom first; every subpath
    is a point list. Returns [[polyline, ...]] per item: the stroked parts not covered by a
    filled item above. A filled item hides everything below it, its own outline included."""
    # ponytail: every segment against every edge of every fill above; fine for hundreds of
    # shapes, add bounding-box checks if a drawing with thousands of fills feels slow
    result = []
    for i, (subs, _f, _r, stroked) in enumerate(items):
        lines = [list(sp) for sp in subs if len(sp) > 1] if stroked else []
        for subs2, filled, rule, _s in items[i + 1:]:
            if not filled or not lines:
                continue
            polys = [sp for sp in subs2 if len(sp) > 2]
            lines = [piece for ln in lines for piece in _clip_polyline(ln, polys, rule or "nonzero")]
        result.append(lines)
    return result


def load_svg(path, hiding=False):
    """SVG -> (page_w_mm, page_h_mm, [Layer]). hiding: drop the parts of lines that lie
    behind filled shapes drawn later in the document (hidden-line removal).

    Uses the digest from idraw_deps/idraw2_0internal (resolve transforms, flatten
    curves, parse layer names). The digest needs lxml; lxml must be imported before
    idraw_deps enters sys.path, because idraw_deps ships an lxml built for a different
    Python version. For a platform without idraw_deps: replace this function with your
    own SVG-to-polyline parser returning the same tuple.
    """
    import sys
    from lxml import etree
    deps = os.path.join(HERE, "idraw_deps")
    for p in (deps, os.path.join(deps, "ink_extensions")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from idraw2_0internal import digest_svg, plot_warnings
    from idraw2_0internal.plot_utils_import import from_dependency_import
    plot_utils = from_dependency_import("drawcore_plotink.plot_utils")
    simpletransform = from_dependency_import("ink_extensions.simpletransform")

    doc = etree.parse(path)
    svg = doc.getroot()

    class Ref:  # plot_utils expects an Effect-like object with .document and .svg
        pass
    ref = Ref()
    ref.document = doc
    ref.svg = svg
    w_in = plot_utils.getLengthInches(ref, "width")
    h_in = plot_utils.getLengthInches(ref, "height")
    if w_in is None or h_in is None:
        raise ValueError("SVG has no page size in mm or in.")
    if svg.get("viewBox") is None:
        # no viewBox: user units are px (1/96 in) per the SVG spec, whatever unit the size has
        # (DrawingBot writes such files); the digest alone would take them as inches
        svg.set("viewBox", "0 0 %.6f %.6f" % (w_in * 96, h_in * 96))
    sx, sy, ox, oy = plot_utils.vb_scale(svg.get("viewBox"), svg.get("preserveAspectRatio"), w_in, h_in)
    mat = simpletransform.parseTransform("scale(%.6E,%.6E) translate(%.6E,%.6E)" % (sx, sy, ox, oy))
    # digest_params: [width, height (inch), scale x, y, layer selection (-2 = all), curve tolerance inch]
    digest = digest_svg.DigestSVG(default_logging=False).process_svg(
        svg, plot_warnings.PlotWarnings(), [w_in, h_in, sx, sy, -2, 0.002], mat)
    if hiding:
        items = [(p.subpaths, str(p.fill).lower() != "none", p.fill_rule, p.has_stroke())
                 for lyr in digest.layers for p in lyr.paths]
        kept = iter(hide_lines(items))
        for lyr in digest.layers:
            for p in lyr.paths:
                p.subpaths = next(kept)     # empty for hidden or unstroked paths; flatten drops them
    digest.flatten()

    layers = []
    for lyr in digest.layers:
        if not lyr.paths:
            continue
        paths = [[(x * 25.4, y * 25.4) for x, y in p.subpaths[0]] for p in lyr.paths]  # inch -> mm
        name = lyr.name if lyr.name != "__digest-root__" else "(root)"
        layers.append(Layer(name, paths, pause=lyr.props.pause,
                            skip=lyr.props.skip, number=lyr.props.number))
    return w_in * 25.4, h_in * 25.4, layers


# ---------------------------------------------------------------- Geometry

# --- single-stroke text (Hershey Sans 1-stroke, SVG font in this folder; see HersheySans1-LICENSE.txt)
_FONT = None
FONT_CAP = 662.0    # cap height in font units (top of "A")


def _font():
    """{char: (advance, [[(x, y), ...], ...])} in font units, y up. Parsed once."""
    global _FONT
    if _FONT is None:
        import html
        text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "HersheySans1.svg"), encoding="utf-8").read()
        _FONT = {}
        for m in re.finditer(r'<glyph unicode="([^"]+)"[^>]*horiz-adv-x="([\d.]+)"(?:[^>]*d="([^"]*)")?', text):
            paths, cur = [], None
            for c, x, y in re.findall(r"([ML])\s*([-\d.]+)\s+([-\d.]+)", m.group(3) or ""):
                if c == "M":
                    cur = [(float(x), float(y))]
                    paths.append(cur)
                else:
                    cur.append((float(x), float(y)))
            _FONT[html.unescape(m.group(1))] = (float(m.group(2)), paths)
    return _FONT


def text_width(text, height):
    f = _font()
    return sum(f.get(ch, f["?"])[0] for ch in text) * height / FONT_CAP


def text_strokes(text, x, y, height):
    """Text as polylines in mm. (x, y) is the left end of the baseline, height the cap height."""
    f, k, out = _font(), height / FONT_CAP, []
    for ch in text:
        adv, paths = f.get(ch, f["?"])
        for p in paths:
            out.append([(x + px * k, y - py * k) for px, py in p])
        x += adv * k
    return out


TB_W, TB_H, TB_MARGIN = 72.0, 21.0, 6.0


def title_block_strokes(paper, corner, rows):
    """The drawing's title block as polylines in document mm: frame, divider, one (label, value)
    row per entry. corner: tl, tr, br, bl. Values longer than the cell are cut."""
    pw, ph = paper
    x = pw - TB_W - TB_MARGIN if corner[1] == "r" else TB_MARGIN
    y = ph - TB_H - TB_MARGIN if corner[0] == "b" else TB_MARGIN
    col, rh = 13.0, TB_H / len(rows)
    out = [[(x, y), (x + TB_W, y), (x + TB_W, y + TB_H), (x, y + TB_H), (x, y)],
           [(x + col, y), (x + col, y + TB_H)]]
    for i, (label, value) in enumerate(rows):
        base = y + (i + 0.78) * rh
        out += text_strokes(label, x + 1.5, base, 1.6)
        while value and text_width(value, 2.2) > TB_W - col - 3:
            value = value[:-1]
        out += text_strokes(value, x + col + 1.5, base, 2.2)
    return out


PLACEMENTS = ("1:1", "center", "fit")


def _cos_sin(rot):
    """cos and sin of a clockwise turn by rot degrees; exact for multiples of 90."""
    r = rot % 360
    if r % 90 == 0:
        return {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[r]
    a = math.radians(r)
    return math.cos(a), math.sin(a)


def rotated_size(page, rot):
    """Width and height of the box around the page turned by rot degrees."""
    c, s = _cos_sin(rot)
    pw, ph = page
    return pw * abs(c) + ph * abs(s), pw * abs(s) + ph * abs(c)


def preset(mode, page, paper, rot=0, margin=10.0):
    """Transform for a placement mode, with the page turned by `rot` degrees (multiples of 15 in the UI).

    '1:1': page corner on the paper origin, no scaling. 'center': 1:1, page centered.
    'fit': scaled proportionally so the page fits the paper with `margin`.
    A transform is {x, y, scale, rot}: turn the page clockwise about its centre, put the box around
    the turned page at 0/0, scale, shift by x, y. Presets use that box, so a turned page fits whole.
    """
    pw, ph = rotated_size(page, rot)
    tw, th = paper
    scale, dx, dy = 1.0, 0.0, 0.0
    if mode == "center":
        dx, dy = (tw - pw) / 2, (th - ph) / 2
    elif mode == "fit":
        scale = min((tw - 2 * margin) / pw, (th - 2 * margin) / ph)
        dx, dy = (tw - pw * scale) / 2, (th - ph * scale) / 2
    return {"x": dx, "y": dy, "scale": scale, "rot": rot % 360}


def place(layers, page, tf):
    """Put the drawing (page size `page`) onto the paper with transform `tf` (see preset).
    Returns new layers with moved paths."""
    pw, ph = page
    s, dx, dy = tf["scale"], tf["x"], tf["y"]
    c, sn = _cos_sin(tf["rot"])
    bw, bh = rotated_size(page, tf["rot"])
    cx, cy = pw / 2, ph / 2

    def turn(x, y):   # about the page centre, then the turned page's box to 0/0
        return (bw / 2 + (x - cx) * c - (y - cy) * sn, bh / 2 + (x - cx) * sn + (y - cy) * c)
    out = []
    for lyr in layers:
        paths = [[(u * s + dx, v * s + dy) for u, v in (turn(x, y) for x, y in p)] for p in lyr.paths]
        new = Layer(lyr.name, paths, lyr.pause, lyr.skip, lyr.number)
        new.enabled = lyr.enabled
        out.append(new)
    return out


def bbox(layers):
    """(x0, y0, x1, y1) of all paths in layers that can be plotted (not % layers), or None."""
    pts = [pt for lyr in layers if not lyr.skip for p in lyr.paths for pt in p]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def align(tf, box, paper, h=None, v=None, margin=0.0):
    """Shift tf so the drawing's box sits left/center/right (h) and top/middle/bottom (v)
    on the paper, `margin` mm inside its edges. None leaves that axis alone."""
    x0, y0, x1, y1 = box
    tw, th = paper
    tf = dict(tf)
    if h:
        tf["x"] += {"left": margin - x0, "center": (tw - x1 - x0) / 2, "right": tw - margin - x1}[h]
    if v:
        tf["y"] += {"top": margin - y0, "middle": (th - y1 - y0) / 2, "bottom": th - margin - y1}[v]
    return tf


def path_length(p):
    return sum(math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]) for i in range(1, len(p)))


def circle(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n + 1)]


# ---------------------------------------------------------------- Test patterns
#
# Each function takes the origin (ox, oy) in document mm and returns strokes as
# (points, feed_or_None, z_down_or_None). None = value from the profile. New tests:
# write a function and register it in TESTS; the UI builds the buttons from it.

SPEED_TEST_FEEDS = (1000, 2000, 3000, 4000, 6000, 8000)


def test_line_width(ox, oy):
    """After Piter Pasma: spacing grows from 0 to 5 mm over 50 mm, single and double pass.

    Reading: measure where the double lines stop touching, divide by 10 = real line width.
    """
    strokes = []
    for block, passes in ((0, 1), (60, 2)):
        for i in range(11):
            x0 = ox + block
            p = [(x0, oy + i * 0.0), (x0 + 50, oy + i * 5.0)]
            for _ in range(passes):
                strokes.append((p, None, None))
    return strokes


def test_speed(ox, oy):
    """Six rows of zigzag plus a circle at 1000 to 8000 mm/min (see the run_test log)."""
    strokes = []
    for row, feed in enumerate(SPEED_TEST_FEEDS):
        y = oy + row * 14
        zig = [(ox + i * 5, y + (6 if i % 2 else 0)) for i in range(13)]
        strokes.append((zig, feed, None))
        strokes.append((circle(ox + 75, y + 3, 4), feed, None))
    return strokes


def test_accuracy(ox, oy):
    """Square with diagonals and circle, each drawn twice in opposite directions; star; mm rulers.

    Offset between the two contours shows belt play. Star lines missing the center show
    backlash per direction. Rulers check the scaling (steps/mm) per axis.
    """
    s = 100
    sq = [(ox, oy), (ox + s, oy), (ox + s, oy + s), (ox, oy + s), (ox, oy)]
    strokes = [(sq, None, None), (list(reversed(sq)), None, None),
               ([(ox, oy), (ox + s, oy + s)], None, None), ([(ox + s, oy), (ox, oy + s)], None, None),
               (circle(ox + s / 2, oy + s / 2, s / 2), None, None),
               (list(reversed(circle(ox + s / 2, oy + s / 2, s / 2))), None, None)]
    cx, cy = ox + s + 60, oy + 50
    for k in range(8):
        a = math.pi * k / 4
        strokes.append(([(cx + 40 * math.cos(a), cy + 40 * math.sin(a)), (cx, cy)], None, None))
    ry = oy + s + 15
    strokes.append(([(ox, ry), (ox + s, ry)], None, None))
    strokes.append(([(ox - 15, oy), (ox - 15, oy + s)], None, None))
    for i in range(0, s + 1, 1):
        t = 4 if i % 10 == 0 else (2.5 if i % 5 == 0 else 1.5)
        strokes.append(([(ox + i, ry), (ox + i, ry + t)], None, None))
        strokes.append(([(ox - 15, oy + i), (ox - 15 - t, oy + i)], None, None))
    return strokes


def test_pen_height(ox, oy, z_from=3.0, z_to=6.5):
    """Short lines with Z from z_from to z_to in 0.5 mm steps, one row per height."""
    strokes = []
    z = z_from
    row = 0
    while z <= z_to + 1e-9:
        strokes.append(([(ox, oy + row * 6), (ox + 40, oy + row * 6)], None, round(z, 2)))
        z += 0.5
        row += 1
    return strokes


TESTS = {
    "Line width": test_line_width, "Speed": test_speed,
    "Accuracy": test_accuracy, "Pen height": test_pen_height,
}


# ---------------------------------------------------------------- Plotter

class Plotter:
    """State and commands for one plotter. Events go to self.events.

    Event protocol (queue.Queue of tuples (kind, data)):
      ("log", text)            line for the log (sent commands, hints)
      ("state", None)          state changed: status, x, y, z_up, profile, ...
      ("progress", dict)       i (finished strokes), n, done/total (mm), eta (s or None)
      ("pause", layer_name)    plot is waiting; UI calls resume() or stop()
      ("done", "finished"|"stopped")
      ("error", text)          exception in the worker; status is then "error"

    State (read only; write through methods):
      x, y (document mm), z_up (True/False/None unknown), status, homed, origin_set,
      bounds_known, machine_origin (home corner in current document mm, for the travel
      preview), motors_free, profile (dict like DEFAULT_PROFILE).
    """

    def __init__(self):
        self.events = queue.Queue()
        self.transport = None
        self.model = "iDraw A4"     # default for new users; most owners have the small model
        self.x = 0.0
        self.y = 0.0
        self.z_up = None            # None = unknown (after connecting)
        self.homed = False
        self.origin_set = False
        self.bounds_known = False   # False after aligning by hand
        self.machine_origin = (0.0, 0.0)  # home corner in current document mm
        self.motors_free = False
        self._rel = False           # True after a hand-typed G91 (see _track)
        self.status = "disconnected"  # disconnected, ready, moving, plotting, paused, error
        self.profile = dict(DEFAULT_PROFILE)
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._worker = None

    # --- events
    def emit(self, kind, data=None):
        self.events.put((kind, data))

    def log(self, text):
        self.emit("log", text)

    def _set_status(self, status):
        self.status = status
        self.emit("state", None)

    # --- connection
    @property
    def connected(self):
        return self.transport is not None

    @property
    def dialect(self):
        return dialect(self.model)

    def connect(self, transport):
        version = transport.open()
        self.transport = transport
        self.log("Connected to %s: %s" % (transport.name, version))
        if self.model not in TESTED:
            self.log("%s is untested: verify axis directions and the pen with small moves first." % self.model)
        if self.dialect == "ebb":
            self._send("EM,1,1")  # motors on, 16x microstepping
            self.log("Pen heights are servo percent (0-100) on this model, higher = up.")
        else:
            self._send("G90")  # absolute coordinates, permanently
        self._set_status("ready")
        return version

    def disconnect(self):
        if self.transport:
            self.transport.close()
        self.transport = None
        self.homed = self.origin_set = False
        self.z_up = None
        self._set_status("disconnected")

    # --- low level: the only places that produce G-code
    def _send(self, line, seconds=0.0, timeout=None):
        resp = self.transport.send(line, seconds, timeout=timeout)
        self.log("> %s   %s" % (line, resp if resp != "ok" else ""))
        return resp

    def _feed(self):
        return self.profile["feed_travel"] if self.z_up else self.profile["feed_draw"]

    def _move_abs(self, x, y, feed=None):
        """Move to document (x, y) mm. The axis mapping lives here."""
        feed = feed or self._feed()
        dist = math.hypot(x - self.x, y - self.y)
        if dist < 0.005:
            return
        seconds = dist / feed * 60
        if self.dialect == "ebb":
            # ponytail: mixed axes as in the AxiDraw code (a = x + y, b = x - y); signs unverified
            dx, dy = x - self.x, y - self.y
            a, b = round((dx + dy) * EBB_STEPS_PER_MM), round((dx - dy) * EBB_STEPS_PER_MM)
            self._send("SM,%d,%d,%d" % (max(1, round(seconds * 1000)), a, b), seconds=seconds)
        else:
            if self._rel:               # a hand-typed G91 is still modal in the firmware
                self._send("G90")
                self._rel = False
            if self.dialect == "drawcore":
                # document -> machine mapping as in the original: X = -y, Y = -x
                self._send("G1 X%.3f Y%.3f F%d" % (-y, -x, feed), seconds=seconds)
            else:
                self._send("G1 X%.3f Y%.3f F%d" % (x, y, feed), seconds=seconds)
        self.x, self.y = x, y
        self.emit("state", None)

    def _z(self, z_mm):
        if self.dialect == "ebb":
            pct = min(100.0, max(0.0, z_mm))
            val = round(EBB_SERVO_MIN + (EBB_SERVO_MAX - EBB_SERVO_MIN) * pct / 100)
            self._send("SC,5,%d" % val)         # the "pen down" servo position is reused for every height
            self._send("SP,0", seconds=0.3)
            return
        self._send("G1 Z%.2f F%d" % (z_mm, Z_RATE), seconds=0.15)

    # --- commands (blocking; call from the UI through start() on the worker thread)
    def home(self):
        """Homing, then move to the origin corner and declare it (0,0)."""
        self._set_status("moving")
        if self.dialect == "ebb":
            # no home switches: wherever the carriage stands now is the home corner
            self.pen_up()
            self._send("EM,1,1")
            self.log("AxiDraw has no home switches: the current position is taken as the home corner.")
        else:
            self._send("$H", seconds=3.0, timeout=120)   # homing an A1 takes a while
            if self.dialect == "drawcore":
                # ponytail: homing sequence taken from the original (manual_cmd machine_origin):
                # $H, then a relative move of y_bounds along machine X. Verify orientation and
                # sign on the device and correct here.
                my = MODELS[self.model][1]
                if self.model == "iDraw A4":
                    my -= 5     # the original moves 5 mm less on this model
                self._send("G91")
                self._send("G1 X%.1f Y0 F5000" % my, seconds=my / 5000 * 60)
                self._send("G90")
            self._send("G92 X0 Y0")
        self.x = self.y = 0.0
        self.machine_origin = (0.0, 0.0)
        self.homed = True
        self.origin_set = True
        self.bounds_known = True
        self.motors_free = False
        self._set_status("ready")

    def pen_up(self):
        if self.z_up is True:
            return
        self._z(self.profile["pen_up"])
        self.z_up = True
        self.emit("state", None)

    def pen_down(self, z=None):
        """Pen to the profile height, or to z (mm), e.g. for the pen height test."""
        self._z(z if z is not None else self.profile["pen_down"])
        self.z_up = False
        self.emit("state", None)

    def pen_toggle(self):
        if self.z_up:
            self.pen_down()
        else:
            self.pen_up()

    def nudge_z(self, delta):
        """Shift the current pen height by delta mm and store it in the profile (calibration)."""
        key = "pen_up" if self.z_up else "pen_down"
        self.profile[key] = round(max(0.0, self.profile[key] + delta), 2)
        self._z(self.profile[key])
        self.emit("state", None)

    def jog(self, dx, dy):
        """Relative move with the pen up, at travel speed."""
        self._set_status("moving")
        self.pen_up()
        self._move_abs(self.x + dx, self.y + dy, self.profile["feed_travel"])
        self._set_status("ready")

    def raw(self, line):
        """Send one line typed by hand (console) and mirror its effect on the tracked state,
        so position, pen and flags stay right after hand-typed commands."""
        line = line.strip()
        if not line:
            return
        self._set_status("moving")
        self._send(line)
        self._track(line)
        self._set_status("ready")

    def _track(self, line):
        """Update x, y, z_up, origin and flags from one G-code / $ line (GRBL subset).
        Handles G0/G1 (also bare axis words), G90/G91, G92, $H, $1=254/255, $SLP, $RST."""
        u = line.upper().replace(" ", "")
        if u.startswith("$"):
            if u == "$H":
                # after homing the head is at the home corner: the origin corner shifted by
                # the y travel (see home()); the origin itself is unchanged
                mx, my = self.machine_origin
                self.x, self.y = mx, my + MODELS[self.model][1]
                self.homed = self.bounds_known = True
                self.motors_free = False
            elif u == "$1=254" or u == "$SLP":
                self.motors_free = True
                self.bounds_known = False
                if u == "$SLP":
                    self.homed = False
            elif u == "$1=255":
                self.motors_free = False
            elif u.startswith("$RST"):
                self.homed = self.origin_set = self.bounds_known = False
            self.emit("state", None)
            return
        words = dict((w[0], float(w[1:])) for w in re.findall(r"[A-Z]-?\d*\.?\d+", u))
        g = words.get("G")
        if g == 90:
            self._rel = False
        elif g == 91:
            self._rel = True
        elif g == 92:
            # machine X = -y, Y = -x; the new value is declared at the current spot
            nx, ny = -words.get("Y", -self.x), -words.get("X", -self.y)
            mx, my = self.machine_origin
            self.machine_origin = (mx + (nx - self.x), my + (ny - self.y))
            self.x, self.y = nx, ny
            self.origin_set = True
        elif g in (0, 1) or (g is None and ("X" in words or "Y" in words or "Z" in words)):
            if self._rel:
                self.x -= words.get("Y", 0.0)
                self.y -= words.get("X", 0.0)
            else:
                if "Y" in words:
                    self.x = -words["Y"]
                if "X" in words:
                    self.y = -words["X"]
            if "Z" in words:
                self.z_up = words["Z"] < (self.profile["pen_up"] + self.profile["pen_down"]) / 2
        self.emit("state", None)

    def goto(self, x, y):
        self._set_status("moving")
        self.pen_up()
        self._move_abs(x, y, self.profile["feed_travel"])
        self._set_status("ready")

    def set_origin(self):
        """The current position becomes document (0,0) (G92). machine_origin moves along."""
        if self.dialect != "ebb":   # EBB moves are relative anyway
            self._send("G92 X0 Y0")
        mx, my = self.machine_origin
        self.machine_origin = (mx - self.x, my - self.y)
        self.x = self.y = 0.0
        self.origin_set = True
        self.emit("state", None)

    def motors_off(self):
        """$SLP: sleep mode. A reset is needed afterwards, hence homed = False."""
        self.pen_up()
        if self.dialect == "ebb":
            self._send("EM,0,0")
            self.log("Motors off. Home before the next move.")
        else:
            self._send("$SLP")
            self.log("Motors off. Reconnect and home before the next move.")
        self.homed = False

    def release_motors(self):
        """Release the motors ($1=254, GRBL step idle delay) so the carriage can be pushed by hand.

        Afterwards the firmware position no longer matches reality. After lock_motors()
        and set_origin() the origin is defined again, but the travel bounds are unknown
        (bounds_known False).
        """
        self.pen_up()
        self._send("EM,0,0" if self.dialect == "ebb" else "$1=254")
        self.motors_free = True
        self.bounds_known = False
        self.emit("state", None)

    def lock_motors(self):
        self._send("EM,1,1" if self.dialect == "ebb" else "$1=255")
        self.motors_free = False
        self.emit("state", None)

    def frame(self, x0, y0, x1, y1):
        """Trace a rectangle with the pen up (check paper or drawing frame)."""
        self._set_status("moving")
        self.pen_up()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
            if self._stop.is_set():
                break
            self._move_abs(x, y)
        self._set_status("ready")

    # --- background run
    def start(self, target, *args):
        """Run target(*args) on the worker thread; exceptions are reported as events."""
        if self._worker and self._worker.is_alive():
            self.log("An operation is already running.")
            return
        self._stop.clear()

        def run():
            try:
                target(*args)
            except LinkLost as err:    # board gone: drop the connection, the UI shows it
                self.emit("error", str(err))
                self.disconnect()
            except Exception as err:  # report to the GUI, do not crash
                self.emit("error", str(err))
                self._set_status("error")
        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def stop(self):
        """Takes effect after the current G-code line (no feed hold, see module docstring)."""
        self._stop.set()
        self._resume.set()

    def resume(self):
        self._resume.set()

    @property
    def busy(self):
        w = self._worker
        if w and w.is_alive() and self.status in ("ready", "error", "disconnected"):
            w.join(0.5)     # the worker reported its final status; let it exit before answering
        return bool(w and w.is_alive())

    def plot_strokes(self, strokes, layer_pauses=None, finish_home=True, start=0, end=None):
        """Plot strokes in order.

        strokes: [(points, feed|None, z_down|None, layer_index)]
        layer_pauses: {layer_index: layer_name}; before the first stroke of such a layer
                      ("pause", name) is emitted and the run waits for resume().
        finish_home: move to the origin at the end (not for tests).
        start: first stroke index; strokes before it count as done (resume after a stop,
               or replot from an earlier path when the pen ran dry).
        end: stop before this stroke index (start + 1 plots one path); None = to the last.
        """
        layer_pauses = layer_pauses or {}
        start = max(0, min(start, len(strokes)))
        end = len(strokes) if end is None else max(start, min(end, len(strokes)))
        total = sum(path_length(s[0]) for s in strokes)
        done = sum(path_length(s[0]) for s in strokes[:start])
        done0 = done
        t0 = time.time()
        self._set_status("plotting")
        self.emit("progress", {"i": start, "n": len(strokes), "done": done, "total": total, "eta": None})
        seen_layers = set(s[3] for s in strokes[:start])   # no pause for a layer already begun
        for i, (pts, feed, z_down, layer_idx) in enumerate(strokes):
            if i < start:
                continue
            if i >= end:
                break
            if self._stop.is_set():
                break
            if layer_idx in layer_pauses and layer_idx not in seen_layers:
                seen_layers.add(layer_idx)
                self.pen_up()
                self._set_status("paused")
                self._resume.clear()
                self.emit("pause", layer_pauses[layer_idx])
                self._resume.wait()
                if self._stop.is_set():
                    break
                self._set_status("plotting")
            seen_layers.add(layer_idx)
            self.pen_up()
            self._move_abs(pts[0][0], pts[0][1], self.profile["feed_travel"])
            self.pen_down(z_down)
            f = feed or self.profile["feed_draw"]
            for x, y in pts[1:]:
                if self._stop.is_set():
                    break
                self._move_abs(x, y, f)
            self.pen_up()
            done += path_length(pts)
            elapsed = time.time() - t0
            eta = elapsed / (done - done0) * (total - done) if done > done0 else None
            self.emit("progress", {"i": i + 1, "n": len(strokes), "done": done, "total": total, "eta": eta})
        stopped = self._stop.is_set()
        self.pen_up()
        if finish_home and not stopped:
            self._move_abs(0, 0, self.profile["feed_travel"])
        self._set_status("ready")
        self.emit("done", "stopped" if stopped else "finished")

    def strokes_from_layers(self, layers):
        """Layer list -> (strokes, layer_pauses) for plot_strokes. Enabled layers only."""
        strokes, pauses = [], {}
        for idx, lyr in enumerate(layers):
            if not lyr.enabled:
                continue
            if lyr.pause:
                pauses[idx] = lyr.name
            for p in lyr.paths:
                if len(p) >= 2:
                    strokes.append((p, None, None, idx))
        return strokes, pauses

    def run_test(self, name):
        """Draw a test pattern from TESTS at the current position."""
        strokes = [(p, f, z, 0) for p, f, z in TESTS[name](self.x, self.y)]
        self.log("Test \"%s\" at (%.1f, %.1f)" % (name, self.x, self.y))
        if name == "Speed":
            for row, feed in enumerate(SPEED_TEST_FEEDS):
                self.log("  row %d: %d mm/min" % (row + 1, feed))
        if name == "Pen height":
            self.log("  rows from the top: Z 3.0, 3.5, 4.0 ... 6.5 mm")
        self.plot_strokes(strokes, finish_home=False)
