"""
idraw_server.py

Local web UI for idraw_core: a small HTTP server (standard library only) that holds
one Plotter session and serves idraw_web.html. Any browser on this machine, or on
the LAN with --lan (e.g. an iPad), can operate the plotter.

    python3 idraw_server.py [drawing.svg] [--sim] [--port 8765] [--lan] [--no-browser]

HTTP interface (all JSON, used by idraw_web.html; usable by other clients too):
    GET  /               the page
    GET  /api/snapshot   full state: plotter state, settings, layers, strokes, log
    GET  /api/events     server-sent events; kinds: snapshot, state, log, progress,
                         pause, done, error (see Plotter docstring in idraw_core)
    POST /api/cmd        {"cmd": name, ...args}; reply {"ok": true} or {"error": text}

Commands: connect(port), disconnect, home, jog(dx,dy in mm), goto(x,y), raw(line), pen_up,
pen_down, pen_toggle, nudge_z(delta), set_origin, release_motors, lock_motors,
motors_off, frame(kind=paper|drawing), test(name), test_stroke, cycle, plot, stop,
resume, set_profile(fields), load_profile(name), save_profile(name), set_paper(w,h,
name,orient), set_pos_mode(mode), set_placement(mode), set_layer(index,enabled,pause),
set_model(name), set_unit(unit), set_title_block(corner: tl|tr|br|bl|off), load_test(name from tests/, "" = the document), reset.
    plot takes an optional "start" (stroke index) to resume or replot from that path.
    set_hiding(on): hidden-line removal, lines behind filled shapes are dropped on load.

Session keeps what the UI needs beyond the Plotter: the loaded SVG (page, layers),
paper, placement, unit, profiles. Everything moving the machine goes through
Session.run(), i.e. the plotter's worker thread. Settings persist in
idraw_interactive_settings.json (see idraw_core).
"""

import collections
import json
import os
import queue
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import idraw_core as core

HERE = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(HERE, "idraw_web.html")


class Session:
    def __init__(self, svg_path=None, sim=False):
        self.plotter = core.Plotter()
        self.settings = core.load_settings()
        self.profiles = self.settings.setdefault("profiles", {"Default": dict(core.DEFAULT_PROFILE)})
        self.profile_name = self.settings.get("last_profile", "Default")
        self.plotter.profile = dict(self.profiles.get(self.profile_name, core.DEFAULT_PROFILE))
        self.plotter.model = self.settings.get("model", "iDraw A4")
        self.sim = sim
        self.unit = self.settings.get("unit", "mm")
        self.paper = tuple(self.settings.get("paper", core.PAPER_FORMATS["A4"]))
        self.paper_name = self.settings.get("paper_name", "A4")
        self.orient = self.settings.get("orient", "landscape")
        self.pos_mode = self.settings.get("pos_mode", "jog")
        self.tb_corner = self.settings.get("tb_corner", "br")   # title block: tl, tr, br, bl or off
        self.hiding = bool(self.settings.get("hiding", False))  # hidden-line removal on load
        self.tb_layer = core.Layer("Title block", [])          # virtual last layer; enabled = plot it
        self.placement = "1:1"
        self.page = (297.0, 210.0)
        self.layers = []
        self.svg_name = "(no SVG)"
        self.svg_error = None
        self.clients = []
        self.log = collections.deque(maxlen=300)
        self.progress = None
        self.pause_layer = None
        self.svg_path = svg_path            # the document handed over by Inkscape (or the CLI)
        self.test_file = ""                 # name of the test drawing from tests/ shown instead, or ""
        if svg_path:
            self.load_svg(svg_path)
        threading.Thread(target=self._pump, daemon=True).start()

    # --- events: plotter queue -> every connected browser
    def _pump(self):
        while True:
            kind, data = self.plotter.events.get()
            if kind == "state":
                data = self.state_dict()
            elif kind == "log":
                self.log.append(data)
            elif kind == "progress":
                self.progress = data
            elif kind == "pause":
                self.pause_layer = data
            elif kind == "done":
                self.pause_layer = None
            self.broadcast(kind, data)

    def broadcast(self, kind, data):
        for q in list(self.clients):
            q.put((kind, data))

    def say(self, text):
        self.log.append(text)
        self.broadcast("log", text)

    # --- state
    def load_svg(self, path):
        try:
            w, h, layers = core.load_svg(path, hiding=self.hiding)
            self.page, self.layers = (w, h), layers
            self.svg_name = os.path.basename(path)
            self.svg_error = None
        except Exception as err:
            self.layers = []
            self.svg_name = os.path.basename(path)
            self.svg_error = str(err)

    TESTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tests")

    def test_files(self):
        try:
            return sorted(f for f in os.listdir(self.TESTS_DIR) if f.lower().endswith(".svg"))
        except OSError:
            return []

    def placed(self):
        """Placed SVG layers plus the title block as a virtual last layer (when shown)."""
        layers = core.place(self.layers, self.page, self.paper, self.placement)
        if self.tb_corner == "off":
            return layers
        self.tb_layer.paths = core.title_block_strokes(self.paper, self.tb_corner, self.tb_rows())
        return layers + [self.tb_layer]

    def all_layers(self):
        return self.layers + ([] if self.tb_corner == "off" else [self.tb_layer])

    def tb_rows(self):
        """Label/value rows of the title block, ASCII only (single-stroke font)."""
        k, d = {"mm": 1, "cm": 10, "in": 25.4}[self.unit], {"mm": 1, "cm": 2, "in": 2}[self.unit]
        f = lambda mm: "%.*f" % (d, mm / k)
        pr = self.plotter.profile
        if self.placement == "fit":
            sc = min((self.paper[0] - 20) / self.page[0], (self.paper[1] - 20) / self.page[1])
            scale = "1:%.2f (%.2fx)" % (1 / sc, sc)
        else:
            scale = "1:1"
        return [("SHEET", "%s %s x %s %s" % (self.paper_name, f(self.paper[0]), f(self.paper[1]), self.unit)),
                ("SCALE", scale), ("PEN", "%s - %s mm" % (self.profile_name, pr["line_width"])),
                ("FEED", "%s / %s mm/min" % (pr["feed_draw"], pr["feed_travel"])), ("FILE", self.svg_name)]

    def state_dict(self):
        p = self.plotter
        return {"status": p.status, "x": p.x, "y": p.y, "z_up": p.z_up, "homed": p.homed,
                "origin_set": p.origin_set, "bounds_known": p.bounds_known,
                "machine_origin": p.machine_origin, "motors_free": p.motors_free,
                "model": p.model, "profile": p.profile, "busy": p.busy,
                "connected": p.connected,
                "transport": p.transport.name if p.transport else None}

    def outside(self, pts, rect):
        x0, y0, x1, y1 = rect
        return any(not (x0 - 0.01 <= x <= x1 + 0.01 and y0 - 0.01 <= y <= y1 + 0.01) for x, y in pts)

    def snapshot(self):
        p = self.plotter
        strokes, _pauses = p.strokes_from_layers(self.placed())
        sheet = (0, 0, self.paper[0], self.paper[1])
        machine = None
        if p.bounds_known:
            mw, mh = core.MODELS[p.model]
            machine = (p.machine_origin[0], p.machine_origin[1], p.machine_origin[0] + mw, p.machine_origin[1] + mh)
        out = [self.outside(s[0], sheet) for s in strokes]
        beyond = [machine is not None and self.outside(s[0], machine) for s in strokes]
        return {
            "outside": sum(out), "beyond": sum(beyond),    # strokes leaving the sheet / the machine travel
            "state": self.state_dict(),
            "profiles": self.profiles, "profile_name": self.profile_name,
            "unit": self.unit, "paper": self.paper, "paper_name": self.paper_name,
            "orient": self.orient, "pos_mode": self.pos_mode, "placement": self.placement,
            "page": self.page, "svg_name": self.svg_name, "svg_error": self.svg_error,
            "layers": [{"name": l.name, "enabled": l.enabled, "pause": l.pause, "n": len(l.paths)}
                       for l in self.all_layers()],
            "tb_corner": self.tb_corner, "hiding": self.hiding,
            "test_files": self.test_files(), "test_file": self.test_file,
            "doc_name": os.path.basename(self.svg_path) if self.svg_path else "",
            "strokes": [{"pts": s[0], "layer": s[3], "out": o or b} for s, o, b in zip(strokes, out, beyond)],
            "ports": ["Simulation"] + core.SerialTransport.list_ports(),
            "models": [[m, core.model_label(m)] for m in core.MODELS], "model_sizes": core.MODELS,
            "formats": core.PAPER_FORMATS,
            "tests": list(core.TESTS), "log": list(self.log),
            "progress": self.progress, "pause_layer": self.pause_layer, "sim": self.sim,
        }

    def save(self):
        self.settings.update(unit=self.unit, paper=self.paper, paper_name=self.paper_name,
                             orient=self.orient, pos_mode=self.pos_mode, model=self.plotter.model,
                             tb_corner=self.tb_corner, hiding=self.hiding,
                             last_profile=self.profile_name)
        core.save_settings(self.settings)

    # --- commands
    def run(self, fn, *args):
        if not self.plotter.connected:
            return {"error": "Not connected."}
        if self.plotter.busy:
            return {"error": "Busy: wait for the current operation or press Stop."}
        self.plotter.start(fn, *args)
        return {"ok": True}

    def command(self, a):
        cmd = a.get("cmd")
        p = self.plotter
        f = lambda k, d=0.0: float(a.get(k, d))

        if cmd == "connect":
            port = a.get("port", "Simulation")
            t = core.SimTransport() if port == "Simulation" else core.SerialTransport(port)
            try:
                p.connect(t)
            except Exception as err:
                return {"error": str(err)}
            self.settings["last_port"] = port
            return {"ok": True}
        if cmd == "disconnect":
            p.disconnect()
            return {"ok": True}
        if cmd == "stop":
            p.stop()
            return {"ok": True}
        if cmd == "resume":
            self.pause_layer = None
            p.resume()
            return {"ok": True}

        simple = {"home": p.home, "pen_up": p.pen_up, "pen_down": p.pen_down,
                  "pen_toggle": p.pen_toggle, "set_origin": p.set_origin,
                  "release_motors": p.release_motors, "lock_motors": p.lock_motors,
                  "motors_off": p.motors_off}
        if cmd in simple:
            return self.run(simple[cmd])
        if cmd == "origin_by_hand":
            def go():
                p.lock_motors()
                p.set_origin()
            return self.run(go)
        if cmd == "jog":
            return self.run(p.jog, f("dx"), f("dy"))
        if cmd == "goto":
            return self.run(p.goto, f("x"), f("y"))
        if cmd == "raw":
            return self.run(p.raw, str(a.get("line", ""))[:200])
        if cmd == "nudge_z":
            return self.run(p.nudge_z, f("delta"))
        if cmd == "frame":
            if a.get("kind") == "drawing":
                pts = [path for l in self.placed() if l.enabled for path in l.paths]
                if not pts:
                    return {"error": "No paths selected."}
                return self.run(p.frame, *core.bbox(pts))
            return self.run(p.frame, 0, 0, self.paper[0], self.paper[1])
        if cmd == "test":
            name = a.get("name")
            if name not in core.TESTS:
                return {"error": "Unknown test."}
            return self.run(p.run_test, name)
        if cmd == "test_stroke":
            def go():
                x, y = p.x, p.y
                p.plot_strokes([([(x, y), (x + 30, y)], None, None, 0)], finish_home=False)
                p.goto(x, y)
            return self.run(go)
        if cmd == "cycle":
            def go():
                p.pen_down()
                p.transport.send("G4 P0.5", seconds=0.5)
                p.pen_up()
            return self.run(go)
        if cmd == "plot":
            strokes, pauses = p.strokes_from_layers(self.placed())
            if not strokes:
                return {"error": "No paths selected."}
            start = int(a.get("start", 0))          # resume/replot from this stroke index
            if start:
                p.log("Resuming from path %d of %d." % (start + 1, len(strokes)))
            return self.run(p.plot_strokes, strokes, pauses, True, start)

        # settings; these do not move the machine except a live pen height change
        if cmd == "set_profile":
            for k in ("pen_up", "pen_down", "feed_draw", "feed_travel", "line_width"):
                if k in a:
                    p.profile[k] = float(a[k]) if k in ("pen_up", "pen_down", "line_width") else int(float(a[k]))
            key = "pen_up" if p.z_up else "pen_down"
            if key in a and p.connected and not p.busy and p.z_up is not None:
                p.start(p.pen_up if p.z_up else p.pen_down) if key == "pen_down" else p.start(p.pen_up)
            p.emit("state", None)
            return {"ok": True}
        if cmd == "load_profile":
            name = a.get("name")
            if name not in self.profiles:
                return {"error": "Unknown profile."}
            self.profile_name = name
            p.profile = dict(self.profiles[name])
            p.emit("state", None)
            return {"ok": True}
        if cmd == "save_profile":
            name = (a.get("name") or self.profile_name).strip()
            if not name:
                return {"error": "Profile needs a name."}
            self.profile_name = name
            self.profiles[name] = dict(p.profile)
            self.save()
            self.say("Profile \"%s\" saved." % name)
            return {"ok": True}
        if cmd == "set_paper":
            self.paper = (f("w", self.paper[0]), f("h", self.paper[1]))
            self.paper_name = a.get("name", "Custom")
            self.orient = a.get("orient", self.orient)
            self.save()
            return {"ok": True}
        if cmd == "set_pos_mode":
            self.pos_mode = a.get("mode", "jog")
            self.save()
            return {"ok": True}
        if cmd == "set_placement":
            self.placement = a.get("mode", "1:1")
            return {"ok": True}
        if cmd == "set_layer":
            i, layers = int(a.get("index", -1)), self.all_layers()
            if not 0 <= i < len(layers):
                return {"error": "Unknown layer."}
            if "enabled" in a:
                layers[i].enabled = bool(a["enabled"])
            if "pause" in a:
                layers[i].pause = bool(a["pause"])
            return {"ok": True}
        if cmd == "set_hiding":
            # the drawing is loaded again: clipping needs the fills, which the layers no longer have
            self.hiding = bool(a.get("on"))
            self.progress = None
            self.load_svg(os.path.join(self.TESTS_DIR, self.test_file) if self.test_file else self.svg_path)
            self.save()
            return {"ok": True}
        if cmd == "load_test":
            # a test drawing from tests/ replaces the document; "" brings the document back
            name = str(a.get("name", ""))
            if name and name not in self.test_files():
                return {"error": "Unknown test drawing."}
            self.test_file = name
            self.progress = None                 # the old plot's progress belongs to the old drawing
            if name:
                self.load_svg(os.path.join(self.TESTS_DIR, name))
            elif self.svg_path:
                self.load_svg(self.svg_path)
            else:
                self.layers, self.svg_name = [], "(no SVG)"
            return {"ok": True}
        if cmd == "set_title_block":
            if a.get("corner") not in ("tl", "tr", "br", "bl", "off"):
                return {"error": "Unknown corner."}
            self.tb_corner = a["corner"]
            self.save()
            return {"ok": True}
        if cmd == "set_model":
            if a.get("name") not in core.MODELS:
                return {"error": "Unknown model."}
            p.model = a["name"]
            self.save()
            p.emit("state", None)
            return {"ok": True}
        if cmd == "reset":
            # everything but the connection and the saved pen profiles goes back to the defaults
            self.unit, self.paper, self.paper_name, self.orient = "mm", core.PAPER_FORMATS["A4"], "A4", "landscape"
            self.pos_mode, self.placement = "jog", "1:1"
            for lyr in self.layers:
                lyr.enabled, lyr.pause = not lyr.skip, lyr.name.startswith("!")
            self.tb_corner, self.tb_layer.enabled = "br", True
            p.origin_set = False
            self.save()
            p.emit("state", None)
            return {"ok": True}
        if cmd == "set_unit":
            if a.get("unit") not in ("mm", "cm", "in"):
                return {"error": "Unknown unit."}
            self.unit = a["unit"]
            self.save()
            return {"ok": True}
        return {"error": "Unknown command: %s" % cmd}


class Handler(BaseHTTPRequestHandler):
    session = None  # set in serve()

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser closed the connection (reload, closed tab); nobody left to answer

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        s = self.session
        if self.path in ("/", "/index.html"):
            with open(HTML_FILE, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/snapshot":
            self._json(s.snapshot())
        elif self.path == "/api/events":
            q = queue.Queue()
            s.clients.append(q)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                self._event("snapshot", s.snapshot())
                while True:
                    try:
                        kind, data = q.get(timeout=15)
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        continue
                    self._event(kind, data)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                if q in s.clients:
                    s.clients.remove(q)
        else:
            self._json({"error": "not found"}, 404)

    def _event(self, kind, data):
        self.wfile.write(("event: %s\ndata: %s\n\n" % (kind, json.dumps(data))).encode("utf-8"))
        self.wfile.flush()

    def do_POST(self):
        if self.path != "/api/cmd":
            return self._json({"error": "not found"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            args = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        result = self.session.command(args)
        # settings commands change what the preview shows; push a fresh snapshot
        if args.get("cmd") in ("set_paper", "set_placement", "set_layer", "load_profile",
                               "set_unit", "set_pos_mode", "connect", "disconnect", "set_model",
                               "set_title_block", "save_profile", "reset", "load_test", "set_hiding"):
            self.session.broadcast("snapshot", self.session.snapshot())
        self._json(result)


def serve(svg_path=None, sim=False, port=8765, lan=False, open_browser=True):
    Handler.session = Session(svg_path, sim)
    httpd = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("Plotter Studio at %s" % url)
    if lan:
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
            print("On the LAN (iPad): http://%s:%d/" % (ip, httpd.server_address[1]))
        except OSError:
            pass
    if open_browser:
        webbrowser.open(url)
    return httpd


def main(argv):
    svgs = [a for a in argv[1:] if a.lower().endswith(".svg")]
    port = 8765
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    httpd = serve(svgs[0] if svgs else None, sim="--sim" in argv, port=port,
                  lan="--lan" in argv, open_browser="--no-browser" not in argv)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv)
