"""
idraw_core.py

Steuerlogik für den iDraw H (DrawCore-Board, GRBL-Dialekt). Keine GUI-Abhängigkeit.

Architektur (drei Schichten, siehe README.md im Projektordner):

    UI (Tk-Wizard, später Web-UI)  -->  Plotter (dieses Modul)  -->  Transport (Serial / Sim)

- Transport: eine Klasse mit open() / close() / send(line, seconds). Sie kennt nur
  Textzeilen und Antworten. Für einen anderen Plotter (AxiDraw/EBB, andere GRBL-
  Firmware) schreibt man einen neuen Transport oder passt die G-Code-Erzeugung in
  Plotter._move_abs / _z an. Für eine andere Plattform (Web, CLI) schreibt man nur
  eine neue UI gegen die Plotter-API.
- Plotter: hält den Zustand (Position, Stift, Status, Profil), bietet blockierende
  Befehle (home, jog, pen_up ...) und einen Plot-Lauf im Hintergrundthread. Meldet
  alles über eine queue.Queue an die UI (Ereignisprotokoll siehe Plotter.emit).
- Hilfsfunktionen: SVG laden (über den Digest aus idraw_deps), Platzierung auf dem
  Papier, Testmuster, Einstellungen als JSON.

Koordinaten und Einheiten:
- Dokument-mm, Ursprung oben links auf dem Papier, x nach rechts, y nach unten.
  Die UI und alle Pfade rechnen ausschliesslich in diesem System.
- G-Code an die Firmware: X = -y, Y = -x (Mapping aus dem Original-Plugin, siehe
  «iDraw Extension Analyse» im Projektordner). Nur _move_abs kennt dieses Mapping.
- Z absolut in mm: klein = Stift oben (0.5), gross = Stift unten (5.0).
- Feedrates in mm/min, wie GRBL sie erwartet.

Threading: Alle Befehle, die den Transport benutzen, laufen in einem Worker-Thread
(Plotter.start). Die UI darf Plotter-Methoden nicht direkt im GUI-Thread aufrufen,
weil send() blockiert. Ausnahmen: stop(), resume(), connect(), disconnect().

Offene Punkte am Gerät (noch nicht getestet, siehe README «Status»):
- Home-Sequenz und Vorzeichen des Achsen-Mappings.
- Ob die Firmware Realtime-Befehle (! Feed Hold, ~ Resume, ? Status) unterstützt.
  Stop wirkt darum erst nach der laufenden G-Code-Zeile.
"""

import json
import math
import os
import queue
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "idraw_interactive_settings.json")

PAPER_FORMATS = {  # mm, Querformat (Breite, Höhe)
    "A1": (841, 594), "A2": (594, 420), "A3": (420, 297),
    "A4": (297, 210), "A5": (210, 148), "Letter": (279.4, 215.9),
}
MODELS = {  # Fahrbereich mm (x, y), Werte aus idraw2_0_conf.py des Originals
    "iDraw A1": (864, 594), "iDraw A0": (1189, 841), "iDraw A2": (594, 432),
    "iDraw A3": (430, 297), "iDraw A4": (300, 210),
}
Z_RATE = 5000  # Feedrate für Z-Fahrten (mm/min), wie im Original


def _import_serial():
    """pyserial: erst das installierte, sonst das reine Python-Paket aus idraw_deps."""
    try:
        import serial
    except ImportError:
        import sys
        sys.path.append(os.path.join(HERE, "idraw_deps"))
        import serial
    return serial


# ---------------------------------------------------------------- Transport
#
# Schnittstelle, die Plotter erwartet:
#   name            Anzeigename (Port oder «Simulation»)
#   open() -> str   Verbindung öffnen, Versionsstring zurückgeben; wirft bei Fehler
#   close()
#   send(line, seconds=0.0) -> str
#                   eine Zeile ohne Zeilenende senden, Antwortzeile zurückgeben.
#                   `seconds` ist die vom Plotter geschätzte Fahrzeit; ein echter
#                   Transport ignoriert sie (die Firmware antwortet erst, wenn sie
#                   den Befehl angenommen hat), die Simulation schläft solange.
#                   Bei error:/ALARM: eine IOError werfen.

class SimTransport:
    """Simulierter DrawCore: antwortet ok, schläft proportional zur Fahrzeit."""
    name = "Simulation"

    def __init__(self, speed_factor=4.0):
        self.speed_factor = speed_factor  # 4 = Demo läuft viermal schneller als real
        self.version = "DrawCore V2.31 (sim)"

    def open(self):
        return self.version

    def close(self):
        pass

    def send(self, line, seconds=0.0):
        if seconds:
            time.sleep(seconds / self.speed_factor)
        if line.startswith("$B"):
            return "0"          # Pause-Taste nicht gedrückt
        if line.startswith("?"):
            return "<Idle>"
        return "ok"


class SerialTransport:
    """Echter DrawCore über pyserial. Handshake wie drawcore_serial.testPort im Original."""
    # ponytail: noch nicht am Gerät getestet; ?-Status und Realtime-Befehle (! ~) ungeprüft

    def __init__(self, port):
        self.name = port
        self.port = port
        self.ser = None
        self.version = ""

    @staticmethod
    def list_ports():
        """Serielle Ports, DrawCore (CH340, VID:PID 1A86:7523 oder 1A86:8040) zuerst."""
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
            if "1A86:7523" in hw or "1A86:8040" in hw:
                found.insert(0, p.device)  # DrawCore zuerst
            else:
                found.append(p.device)
        return found

    def open(self):
        serial = _import_serial()
        s = serial.Serial()
        s.port = self.port
        s.baudrate = 115200
        s.timeout = 1
        s.rts = False   # kein Reset des Boards beim Öffnen
        s.dtr = False
        s.open()
        s.write(b"$B\r")  # Puffer leeren, wie im Original
        s.readline()
        s.readline()
        s.reset_input_buffer()
        s.write(b"v\r")
        v = s.readline().decode("ascii", "replace").strip()
        if not v.startswith("DrawCore"):
            s.close()
            raise IOError("Kein DrawCore an %s (Antwort: %r)" % (self.port, v))
        self.ser = s
        self.version = v
        status = self.send("?")
        if "Alarm" in status:
            self.send("$X")   # Alarm quittieren (z.B. nach Not-Halt)
        return v

    def close(self):
        if self.ser:
            self.ser.close()
            self.ser = None

    def send(self, line, seconds=0.0):
        self.ser.write((line + "\r").encode("ascii"))
        resp = ""
        for _ in range(100):  # bis 100 s auf Antwort warten (lange Fahrten, Homing)
            resp = self.ser.readline().decode("ascii", "replace").strip()
            if resp:
                break
        if line.startswith("$B") or line.startswith("$QP") or line.startswith("$QT"):
            self.ser.readline()  # diese Abfragen liefern Daten und danach ein ok
        if resp.startswith("error") or resp.startswith("ALARM"):
            raise IOError("%s -> %s" % (line, resp))
        return resp


# ---------------------------------------------------------------- Einstellungen
# Eine JSON-Datei neben diesem Modul. Struktur (alles optional):
#   {"model": "iDraw A1", "paper": [297, 210], "paper_name": "A4", "orient": "quer",
#    "pos_mode": "jog", "last_port": "...", "last_profile": "Standard",
#    "profiles": {"Standard": {pen_up, pen_down, feed_draw, feed_travel, line_width}}}

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


# ---------------------------------------------------------------- SVG laden

class Layer:
    """Eine Ebene aus dem SVG: Name, Polylinien in Dokument-mm, Steuerflags.

    pause: Plot hält vor dieser Ebene an (Präfix «!» im Ebenennamen, in der UI
           übersteuerbar). skip: Dokumentationsebene (Präfix «%»), nie plotten.
    enabled: von der UI gesetzt; skip-Ebenen starten ausgeschaltet.
    """

    def __init__(self, name, paths, pause=False, skip=False, number=None):
        self.name = name
        self.paths = paths      # Liste von Polylinien [(x_mm, y_mm), ...]
        self.pause = pause
        self.skip = skip
        self.number = number    # führende Zahl im Ebenennamen, z.B. 2 bei «2 rot»
        self.enabled = not skip


def load_svg(path):
    """SVG -> (page_w_mm, page_h_mm, [Layer]).

    Nutzt den Digest aus idraw_deps/idraw2_0internal (Transforms auflösen, Kurven
    abflachen, Ebenennamen parsen). Der Digest braucht Inkscapes lxml und läuft nur
    mit Inkscapes Python; darum muss lxml importiert sein, bevor idraw_deps im
    sys.path steht (dort liegt ein lxml für eine andere Python-Version).
    Für eine Plattform ohne idraw_deps: diese Funktion durch einen eigenen
    SVG-zu-Polylinien-Parser ersetzen, der dieselbe Rückgabe liefert.
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

    class Ref:  # plot_utils erwartet ein Effect-ähnliches Objekt mit .document und .svg
        pass
    ref = Ref()
    ref.document = doc
    ref.svg = svg
    w_in = plot_utils.getLengthInches(ref, "width")
    h_in = plot_utils.getLengthInches(ref, "height")
    if w_in is None or h_in is None:
        raise ValueError("SVG hat keine Seitengrösse in mm oder in.")
    sx, sy, ox, oy = plot_utils.vb_scale(svg.get("viewBox"), svg.get("preserveAspectRatio"), w_in, h_in)
    mat = simpletransform.parseTransform("scale(%.6E,%.6E) translate(%.6E,%.6E)" % (sx, sy, ox, oy))
    # digest_params: [Breite, Höhe (inch), Skalierung x, y, Ebenenauswahl (-2 = alle), Kurventoleranz inch]
    digest = digest_svg.DigestSVG(default_logging=False).process_svg(
        svg, plot_warnings.PlotWarnings(), [w_in, h_in, sx, sy, -2, 0.002], mat)
    digest.flatten()

    layers = []
    for lyr in digest.layers:
        if not lyr.paths:
            continue
        paths = [[(x * 25.4, y * 25.4) for x, y in p.subpaths[0]] for p in lyr.paths]  # inch -> mm
        name = lyr.name if lyr.name != "__digest-root__" else "(Wurzel)"
        layers.append(Layer(name, paths, pause=lyr.props.pause,
                            skip=lyr.props.skip, number=lyr.props.number))
    return w_in * 25.4, h_in * 25.4, layers


# ---------------------------------------------------------------- Geometrie

def bbox(paths):
    """(x0, y0, x1, y1) über alle Punkte aller Polylinien."""
    xs = [x for p in paths for x, _ in p]
    ys = [y for p in paths for _, y in p]
    if not xs:
        return 0, 0, 0, 0
    return min(xs), min(ys), max(xs), max(ys)


def place(layers, page, paper, mode, margin=10.0):
    """Zeichnung (Seite page) aufs Papier legen. Gibt neue Layer mit verschobenen Pfaden.

    mode '1:1': Seitenursprung auf Papierursprung, keine Skalierung.
    mode 'center': 1:1, Seite auf dem Papier zentriert.
    mode 'fit': proportional skaliert, dass die Seite mit `margin` aufs Papier passt.
    Weitere Modi (freie Position, Drehung) hier ergänzen; die UI reicht nur den Namen durch.
    """
    pw, ph = page
    tw, th = paper
    scale, dx, dy = 1.0, 0.0, 0.0
    if mode == "center":
        dx, dy = (tw - pw) / 2, (th - ph) / 2
    elif mode == "fit":
        scale = min((tw - 2 * margin) / pw, (th - 2 * margin) / ph)
        dx, dy = (tw - pw * scale) / 2, (th - ph * scale) / 2
    out = []
    for lyr in layers:
        paths = [[(x * scale + dx, y * scale + dy) for x, y in p] for p in lyr.paths]
        new = Layer(lyr.name, paths, lyr.pause, lyr.skip, lyr.number)
        new.enabled = lyr.enabled
        out.append(new)
    return out


def path_length(p):
    return sum(math.hypot(p[i][0] - p[i - 1][0], p[i][1] - p[i - 1][1]) for i in range(1, len(p)))


def circle(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
            for i in range(n + 1)]


# ---------------------------------------------------------------- Testmuster
#
# Jede Funktion bekommt den Ursprung (ox, oy) in Dokument-mm und liefert Striche als
# (punkte, feed_oder_None, z_down_oder_None). None = Wert aus dem Profil. Neue Tests:
# Funktion schreiben und in TESTS eintragen, die UI baut daraus automatisch Buttons.

def test_line_width(ox, oy):
    """Nach Piter Pasma: Abstand wächst über 50 mm von 0 auf 5 mm, einfach und doppelt.

    Auswertung: Abstand messen, wo sich die doppelten Linien nicht mehr berühren,
    durch 10 teilen = reale Strichbreite.
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
    """Sechs Zeilen Zickzack plus Kreis bei 1000 bis 8000 mm/min (siehe run_test-Log)."""
    strokes = []
    for row, feed in enumerate((1000, 2000, 3000, 4000, 6000, 8000)):
        y = oy + row * 14
        zig = [(ox + i * 5, y + (6 if i % 2 else 0)) for i in range(13)]
        strokes.append((zig, feed, None))
        strokes.append((circle(ox + 75, y + 3, 4), feed, None))
    return strokes


def test_accuracy(ox, oy):
    """Quadrat mit Diagonalen und Kreis, je zweimal gegenläufig; Strahlenstern; mm-Lineale.

    Versatz zwischen den gegenläufigen Konturen zeigt Spiel im Riemen. Sternlinien, die
    den Mittelpunkt verfehlen, zeigen Umkehrspiel pro Richtung. Lineale prüfen die
    Skalierung (Steps/mm) je Achse.
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
    """Kurze Linien mit Z von z_from bis z_to in 0.5-mm-Schritten, eine Zeile pro Höhe."""
    strokes = []
    z = z_from
    row = 0
    while z <= z_to + 1e-9:
        strokes.append(([(ox, oy + row * 6), (ox + 40, oy + row * 6)], None, round(z, 2)))
        z += 0.5
        row += 1
    return strokes


TESTS = {
    "Linienbreite": test_line_width, "Geschwindigkeit": test_speed,
    "Genauigkeit": test_accuracy, "Stifthöhe": test_pen_height,
}


# ---------------------------------------------------------------- Plotter

class Plotter:
    """Zustand und Befehle für einen Plotter. Ereignisse landen in self.events.

    Ereignisprotokoll (queue.Queue mit Tupeln (kind, data)):
      ("log", text)            Zeile fürs Protokoll (gesendete Befehle, Hinweise)
      ("state", None)          Zustand geändert: status, x, y, z_up, profile, ...
      ("progress", dict)       i (fertige Striche), n, done/total (mm), eta (s oder None)
      ("pause", ebenenname)    Plot wartet; UI ruft resume() oder stop()
      ("done", "fertig"|"gestoppt")
      ("error", text)          Ausnahme im Worker; status ist dann "fehler"

    Zustand (nur lesen, Schreiben über Methoden):
      x, y (Dokument-mm), z_up (True/False/None unbekannt), status, homed,
      origin_set, bounds_known, machine_origin (Home-Ecke in aktuellen Dokument-mm,
      für die Vorschau des Fahrbereichs), motors_free, profile (dict wie DEFAULT_PROFILE).
    """

    def __init__(self):
        self.events = queue.Queue()
        self.transport = None
        self.model = "iDraw A1"
        self.x = 0.0
        self.y = 0.0
        self.z_up = None            # None = unbekannt (nach Verbinden)
        self.homed = False
        self.origin_set = False
        self.bounds_known = False   # False nach Ausrichten von Hand
        self.machine_origin = (0.0, 0.0)  # Home-Ecke in aktuellen Dokument-mm
        self.motors_free = False
        self.status = "getrennt"    # getrennt, bereit, fährt, plottet, pausiert, fehler
        self.profile = dict(DEFAULT_PROFILE)
        self._stop = threading.Event()
        self._resume = threading.Event()
        self._worker = None

    # --- Ereignisse
    def emit(self, kind, data=None):
        self.events.put((kind, data))

    def log(self, text):
        self.emit("log", text)

    def _set_status(self, status):
        self.status = status
        self.emit("state", None)

    # --- Verbindung
    @property
    def connected(self):
        return self.transport is not None

    def connect(self, transport):
        version = transport.open()
        self.transport = transport
        self.log("Verbunden mit %s: %s" % (transport.name, version))
        self._send("G90")  # absolute Koordinaten, dauerhaft
        self._set_status("bereit")
        return version

    def disconnect(self):
        if self.transport:
            self.transport.close()
        self.transport = None
        self.homed = self.origin_set = False
        self.z_up = None
        self._set_status("getrennt")

    # --- Low level: die einzigen Stellen, die G-Code erzeugen
    def _send(self, line, seconds=0.0):
        resp = self.transport.send(line, seconds)
        self.log("> %s   %s" % (line, resp if resp != "ok" else ""))
        return resp

    def _feed(self):
        return self.profile["feed_travel"] if self.z_up else self.profile["feed_draw"]

    def _move_abs(self, x, y, feed=None):
        """Fahrt zu Dokument-(x, y) mm. Hier passiert das Achsen-Mapping."""
        feed = feed or self._feed()
        dist = math.hypot(x - self.x, y - self.y)
        if dist < 0.005:
            return
        # Mapping Dokument -> Maschine wie im Original: X = -y, Y = -x
        self._send("G1 X%.3f Y%.3f F%d" % (-y, -x, feed), seconds=dist / feed * 60)
        self.x, self.y = x, y
        self.emit("state", None)

    def _z(self, z_mm):
        self._send("G1 Z%.2f F%d" % (z_mm, Z_RATE), seconds=0.15)

    # --- Befehle (blockierend; aus der UI über start() im Worker-Thread aufrufen)
    def home(self):
        """Homing, dann zur Ursprungsecke fahren und diese als (0,0) setzen."""
        self._set_status("fährt")
        self._send("$H", seconds=3.0)
        # ponytail: Home-Sequenz aus dem Original (manual_cmd machine_origin) übernommen:
        # $H, dann relative Fahrt um y_bounds entlang Maschinen-X. Orientierung und
        # Vorzeichen am Gerät prüfen und hier korrigieren.
        my = MODELS[self.model][1]
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
        self._set_status("bereit")

    def pen_up(self):
        if self.z_up is True:
            return
        self._z(self.profile["pen_up"])
        self.z_up = True
        self.emit("state", None)

    def pen_down(self, z=None):
        """Stift auf Profilhöhe oder auf z (mm), z.B. für den Stifthöhen-Test."""
        self._z(z if z is not None else self.profile["pen_down"])
        self.z_up = False
        self.emit("state", None)

    def pen_toggle(self):
        if self.z_up:
            self.pen_down()
        else:
            self.pen_up()

    def nudge_z(self, delta):
        """Aktuelle Stifthöhe um delta mm verschieben und ins Profil schreiben (Kalibrieren)."""
        key = "pen_up" if self.z_up else "pen_down"
        self.profile[key] = round(max(0.0, self.profile[key] + delta), 2)
        self._z(self.profile[key])
        self.emit("state", None)

    def jog(self, dx, dy):
        """Relative Fahrt mit Stift oben, Leerfahrt-Tempo."""
        self._set_status("fährt")
        self.pen_up()
        self._move_abs(self.x + dx, self.y + dy, self.profile["feed_travel"])
        self._set_status("bereit")

    def goto(self, x, y):
        self._set_status("fährt")
        self.pen_up()
        self._move_abs(x, y, self.profile["feed_travel"])
        self._set_status("bereit")

    def set_origin(self):
        """Aktuelle Position wird (0,0) des Dokuments (G92). machine_origin wandert mit."""
        self._send("G92 X0 Y0")
        mx, my = self.machine_origin
        self.machine_origin = (mx - self.x, my - self.y)
        self.x = self.y = 0.0
        self.origin_set = True
        self.emit("state", None)

    def motors_off(self):
        """$SLP: Schlafmodus. Danach ist ein Reset nötig; deshalb homed = False."""
        self.pen_up()
        self._send("$SLP")
        self.log("Motoren aus. Vor der nächsten Fahrt neu verbinden und Home fahren.")
        self.homed = False

    def release_motors(self):
        """Motoren freigeben ($1=254, GRBL step idle delay), Wagen von Hand schiebbar.

        Danach stimmt die Firmware-Position nicht mehr mit der Realität überein.
        Nach lock_motors() und set_origin() ist der Ursprung wieder definiert, der
        Fahrbereich aber unbekannt (bounds_known False).
        """
        self.pen_up()
        self._send("$1=254")
        self.motors_free = True
        self.bounds_known = False
        self.emit("state", None)

    def lock_motors(self):
        self._send("$1=255")
        self.motors_free = False
        self.emit("state", None)

    def frame(self, x0, y0, x1, y1):
        """Rechteck mit Stift oben abfahren (Papier- oder Zeichnungsrahmen prüfen)."""
        self._set_status("fährt")
        self.pen_up()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)):
            if self._stop.is_set():
                break
            self._move_abs(x, y)
        self._set_status("bereit")

    # --- Hintergrundlauf
    def start(self, target, *args):
        """target(*args) im Worker-Thread ausführen; Fehler werden als Ereignis gemeldet."""
        if self._worker and self._worker.is_alive():
            self.log("Es läuft schon ein Vorgang.")
            return
        self._stop.clear()

        def run():
            try:
                target(*args)
            except Exception as err:  # Fehler an die GUI melden, nicht crashen
                self.emit("error", str(err))
                self._set_status("fehler")
        self._worker = threading.Thread(target=run, daemon=True)
        self._worker.start()

    def stop(self):
        """Wirkt nach der laufenden G-Code-Zeile (kein Feed Hold, siehe Modulkopf)."""
        self._stop.set()
        self._resume.set()

    def resume(self):
        self._resume.set()

    @property
    def busy(self):
        return bool(self._worker and self._worker.is_alive())

    def plot_strokes(self, strokes, layer_pauses=None, finish_home=True):
        """Striche der Reihe nach plotten.

        strokes: [(punkte, feed|None, z_down|None, layer_index)]
        layer_pauses: {layer_index: ebenenname}; vor dem ersten Strich dieser Ebene
                      wird ("pause", name) gemeldet und auf resume() gewartet.
        finish_home: am Ende zum Ursprung fahren (nicht bei Tests).
        """
        layer_pauses = layer_pauses or {}
        total = sum(path_length(s[0]) for s in strokes)
        done = 0.0
        t0 = time.time()
        self._set_status("plottet")
        self.emit("progress", {"i": 0, "n": len(strokes), "done": 0, "total": total, "eta": None})
        seen_layers = set()
        for i, (pts, feed, z_down, layer_idx) in enumerate(strokes):
            if self._stop.is_set():
                break
            if layer_idx in layer_pauses and layer_idx not in seen_layers:
                seen_layers.add(layer_idx)
                self.pen_up()
                self._set_status("pausiert")
                self._resume.clear()
                self.emit("pause", layer_pauses[layer_idx])
                self._resume.wait()
                if self._stop.is_set():
                    break
                self._set_status("plottet")
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
            eta = elapsed / done * (total - done) if done > 0 else None
            self.emit("progress", {"i": i + 1, "n": len(strokes), "done": done, "total": total, "eta": eta})
        stopped = self._stop.is_set()
        self.pen_up()
        if finish_home and not stopped:
            self._move_abs(0, 0, self.profile["feed_travel"])
        self._set_status("bereit")
        self.emit("done", "gestoppt" if stopped else "fertig")

    def strokes_from_layers(self, layers):
        """Layer-Liste -> (strokes, layer_pauses) für plot_strokes. Nur enabled-Ebenen."""
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
        """Testmuster aus TESTS an der aktuellen Position zeichnen."""
        strokes = [(p, f, z, 0) for p, f, z in TESTS[name](self.x, self.y)]
        self.log("Test «%s» an (%.1f, %.1f)" % (name, self.x, self.y))
        if name == "Geschwindigkeit":
            for row, feed in enumerate((1000, 2000, 3000, 4000, 6000, 8000)):
                self.log("  Zeile %d: %d mm/min" % (row + 1, feed))
        if name == "Stifthöhe":
            self.log("  Zeilen von oben: Z 3.0, 3.5, 4.0 ... 6.5 mm")
        self.plot_strokes(strokes, finish_home=False)
