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
set_model(name), set_unit(unit), reset.

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
        self.placement = "1:1"
        self.page = (297.0, 210.0)
        self.layers = []
        self.svg_name = "(no SVG)"
        self.svg_error = None
        self.clients = []
        self.log = collections.deque(maxlen=300)
        self.progress = None
        self.pause_layer = None
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
            w, h, layers = core.load_svg(path)
            self.page, self.layers = (w, h), layers
            self.svg_name = os.path.basename(path)
            self.svg_error = None
        except Exception as err:
            self.layers = []
            self.svg_name = os.path.basename(path)
            self.svg_error = str(err)

    def placed(self):
        return core.place(self.layers, self.page, self.paper, self.placement)

    def state_dict(self):
        p = self.plotter
        return {"status": p.status, "x": p.x, "y": p.y, "z_up": p.z_up, "homed": p.homed,
                "origin_set": p.origin_set, "bounds_known": p.bounds_known,
                "machine_origin": p.machine_origin, "motors_free": p.motors_free,
                "model": p.model, "profile": p.profile, "busy": p.busy,
                "connected": p.connected,
                "transport": p.transport.name if p.transport else None}

    def snapshot(self):
        strokes, _pauses = self.plotter.strokes_from_layers(self.placed())
        return {
            "state": self.state_dict(),
            "profiles": self.profiles, "profile_name": self.profile_name,
            "unit": self.unit, "paper": self.paper, "paper_name": self.paper_name,
            "orient": self.orient, "pos_mode": self.pos_mode, "placement": self.placement,
            "page": self.page, "svg_name": self.svg_name, "svg_error": self.svg_error,
            "layers": [{"name": l.name, "enabled": l.enabled, "pause": l.pause, "n": len(l.paths)}
                       for l in self.layers],
            "strokes": [{"pts": s[0], "layer": s[3]} for s in strokes],
            "ports": ["Simulation"] + core.SerialTransport.list_ports(),
            "models": list(core.MODELS), "formats": core.PAPER_FORMATS,
            "tests": list(core.TESTS), "log": list(self.log),
            "progress": self.progress, "pause_layer": self.pause_layer, "sim": self.sim,
        }

    def save(self):
        self.settings.update(unit=self.unit, paper=self.paper, paper_name=self.paper_name,
                             orient=self.orient, pos_mode=self.pos_mode, model=self.plotter.model,
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
            return self.run(p.plot_strokes, strokes, pauses)

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
            i = int(a.get("index", -1))
            if not 0 <= i < len(self.layers):
                return {"error": "Unknown layer."}
            if "enabled" in a:
                self.layers[i].enabled = bool(a["enabled"])
            if "pause" in a:
                self.layers[i].pause = bool(a["pause"])
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
                               "set_unit", "set_pos_mode", "connect", "disconnect", "set_model"):
            self.session.broadcast("snapshot", self.session.snapshot())
        self._json(result)


def serve(svg_path=None, sim=False, port=8765, lan=False, open_browser=True):
    Handler.session = Session(svg_path, sim)
    httpd = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", port), Handler)
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    print("iDraw Interactive at %s" % url)
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
