"""
idraw_interactive_gui.py

Tk wizard for the iDraw H. Pure view: all plotter logic lives in idraw_core.

Start from the terminal (a Python with tkinter 8.6+ and lxml; pyserial optional):
    /usr/local/bin/python3 idraw_interactive_gui.py idraw_demo.svg --sim
or from Inkscape through idraw_interactive.py (Extensions > iDraw > iDraw Interactive).

Structure:
- App.build(): the frame. Step bar (STEPS) and status line on top, the active step's
  content on the left, the preview (Canvas) on the right, navigation and log below.
- App.step_0 .. step_4: one wizard step each. show_step() clears the left area and
  rebuilds the step; steps hold no state of their own except Tk variables. State lives
  in App (paper, page, layers, placement) and in the Plotter.
- App.run(fn, *args): the only way to trigger plotter commands. Starts fn on the
  plotter's worker thread; blocking calls on the GUI thread are not allowed.
- App.poll(): reads the plotter's event queue every 50 ms (see the Plotter docstring)
  and updates status, log, progress and preview. This is the only place where worker
  results reach the GUI thread.
- App.draw_preview(): draws the machine frame (when known), paper, strokes
  (grey = pending, black = plotted), pen cross (red = down, blue = up), origin.

For another platform (web UI, other toolkit): rebuild the same steps against
idraw_core.Plotter; its methods and events are the interface.
Colors and spacing: DESIGN.md in the project folder.
"""

import os
import queue
import sys
import tkinter as tk
from tkinter import ttk, messagebox

import idraw_core as core

STEPS = ["Connect", "Paper", "Pen", "Speed", "Plot"]
STEP_SIZES = (1, 10, 50)


class App:
    def __init__(self, root, svg_path=None, sim=False):
        self.root = root
        root.title("iDraw Interactive")
        root.geometry("1180x760")
        self.plotter = core.Plotter()
        self.settings = core.load_settings()
        self.profiles = self.settings.setdefault("profiles", {"Default": dict(core.DEFAULT_PROFILE)})
        self.profile_name = self.settings.get("last_profile", "Default")
        self.plotter.profile = dict(self.profiles.get(self.profile_name, core.DEFAULT_PROFILE))
        self.plotter.model = self.settings.get("model", "iDraw A1")
        self.sim = sim
        self.step = 0
        self.step_size = tk.IntVar(value=10)
        self.paper = tuple(self.settings.get("paper", core.PAPER_FORMATS["A4"]))
        self.placement = tk.StringVar(value="1:1")
        self.page = (297.0, 210.0)
        self.layers = []
        self.placed = []
        self.strokes = []
        self.pauses = {}
        self.stroke_ids = []
        self.done_count = 0
        self.svg_name = "(no SVG)"
        if svg_path:
            self.load_svg(svg_path)

        self.build()
        self.bind_keys()
        self.show_step(0)
        self.poll()
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # ------------------------------------------------------------ frame
    def build(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        self.step_buttons = []
        for i, name in enumerate(STEPS):
            b = ttk.Button(top, text="%d  %s" % (i + 1, name), command=lambda i=i: self.show_step(i))
            b.pack(side="left", padx=2)
            self.step_buttons.append(b)
        self.status_var = tk.StringVar(value="disconnected")
        ttk.Label(top, textvariable=self.status_var, font=("", 12, "bold")).pack(side="right", padx=8)
        self.pos_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.pos_var).pack(side="right", padx=8)

        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        self.content = ttk.Frame(main, padding=8, width=420)
        self.content.pack(side="left", fill="y")
        self.content.pack_propagate(False)
        self.canvas = tk.Canvas(main, bg="#e8e8e8", highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.draw_preview())

        bottom = ttk.Frame(self.root, padding=6)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Back", command=lambda: self.show_step(self.step - 1)).pack(side="left")
        ttk.Button(bottom, text="Next", command=lambda: self.show_step(self.step + 1)).pack(side="left", padx=4)
        ttk.Button(bottom, text="Stop", command=self.plotter.stop).pack(side="right")
        self.log = tk.Text(self.root, height=6, font=("Menlo", 10), state="disabled")
        self.log.pack(fill="x")

    def show_step(self, i):
        i = max(0, min(len(STEPS) - 1, i))
        self.step = i
        for j, b in enumerate(self.step_buttons):
            b.state(["pressed"] if j == i else ["!pressed"])
        for w in self.content.winfo_children():
            w.destroy()
        getattr(self, "step_%d" % i)(self.content)
        self.draw_preview()

    def head(self, parent, text):
        ttk.Label(parent, text=text, font=("", 15, "bold")).pack(anchor="w", pady=(0, 6))

    def note(self, parent, text):
        ttk.Label(parent, text=text, wraplength=390, foreground="#444").pack(anchor="w", pady=(2, 8))

    def run(self, fn, *args):
        if not self.plotter.connected:
            self.append_log("Not connected.")
            return
        if self.plotter.busy:
            self.append_log("Busy, command ignored.")
            return
        self.plotter.start(fn, *args)

    # ------------------------------------------------------------ steps
    def step_0(self, p):
        self.head(p, "1  Connect")
        self.note(p, "SVG: %s" % self.svg_name)
        row = ttk.Frame(p)
        row.pack(fill="x")
        ports = ["Simulation"] + core.SerialTransport.list_ports()
        self.port_var = tk.StringVar(value="Simulation" if self.sim else (ports[1] if len(ports) > 1 else "Simulation"))
        ttk.Combobox(row, textvariable=self.port_var, values=ports, width=28).pack(side="left")
        self.conn_btn = ttk.Button(row, text="Disconnect" if self.plotter.connected else "Connect", command=self.toggle_connect)
        self.conn_btn.pack(side="left", padx=4)
        row = ttk.Frame(p)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="Model").pack(side="left")
        self.model_var = tk.StringVar(value=self.plotter.model)
        cb = ttk.Combobox(row, textvariable=self.model_var, values=list(core.MODELS), width=12, state="readonly")
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_model())
        ttk.Button(p, text="Home", command=lambda: self.run(self.plotter.home)).pack(anchor="w", pady=6)
        self.note(p, "Home moves the carriage to the reference corner and sets the origin. "
                     "After that the software knows the travel range and the position.")

    def step_1(self, p):
        self.head(p, "2  Paper")
        self.note(p, "Tape the paper to the table. Choose the format and tell the software where its top-left corner is.")
        row = ttk.Frame(p)
        row.pack(fill="x")
        self.fmt_var = tk.StringVar(value=self.settings.get("paper_name", "A4"))
        self.orient_var = tk.StringVar(value=self.settings.get("orient", "landscape"))
        cb = ttk.Combobox(row, textvariable=self.fmt_var, values=list(core.PAPER_FORMATS) + ["Custom"], width=8, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.set_paper())
        for o in ("landscape", "portrait"):
            ttk.Radiobutton(row, text=o, value=o, variable=self.orient_var, command=self.set_paper).pack(side="left", padx=3)
        row = ttk.Frame(p)
        row.pack(fill="x", pady=4)
        self.pw_var = tk.StringVar(value="%g" % self.paper[0])
        self.ph_var = tk.StringVar(value="%g" % self.paper[1])
        ttk.Label(row, text="Width").pack(side="left")
        ttk.Entry(row, textvariable=self.pw_var, width=7).pack(side="left", padx=3)
        ttk.Label(row, text="Height").pack(side="left")
        ttk.Entry(row, textvariable=self.ph_var, width=7).pack(side="left", padx=3)
        ttk.Label(row, text="mm").pack(side="left")
        ttk.Button(row, text="Apply", command=self.set_paper_custom).pack(side="left", padx=6)

        ttk.Label(p, text="Paper position", font=("", 12, "bold")).pack(anchor="w", pady=(10, 2))
        self.pos_mode = tk.StringVar(value=self.settings.get("pos_mode", "jog"))
        for val, text in (("corner", "Against the stop corner (origin = home)"),
                          ("jog", "Jog to the paper corner"),
                          ("hand", "Push the carriage to the paper corner by hand")):
            ttk.Radiobutton(p, text=text, value=val, variable=self.pos_mode, command=self.pos_mode_changed).pack(anchor="w")
        self.pos_frame = ttk.Frame(p)
        self.pos_frame.pack(fill="x", pady=6)
        self.pos_mode_changed()
        ttk.Button(p, text="Trace paper frame (pen up)", command=self.frame_paper).pack(anchor="w", pady=(10, 0))
        self.note(p, "Shows whether the paper lies where the software assumes it is.")

    def pos_mode_changed(self):
        for w in self.pos_frame.winfo_children():
            w.destroy()
        m = self.pos_mode.get()
        self.settings["pos_mode"] = m
        if m == "corner":
            ttk.Button(self.pos_frame, text="Origin = home", command=lambda: self.run(self.plotter.home)).pack(anchor="w")
        elif m == "jog":
            self.build_jog(self.pos_frame)
            ttk.Button(self.pos_frame, text="Set origin here", command=lambda: self.run(self.plotter.set_origin)).pack(anchor="w", pady=4)
        else:
            row = ttk.Frame(self.pos_frame)
            row.pack(fill="x")
            ttk.Button(row, text="Release motors", command=lambda: self.run(self.plotter.release_motors)).pack(side="left")
            ttk.Button(row, text="Lock motors", command=lambda: self.run(self.plotter.lock_motors)).pack(side="left", padx=4)
            ttk.Button(self.pos_frame, text="Set origin here", command=self.origin_after_hand).pack(anchor="w", pady=4)
            self.note(self.pos_frame, "Release, push the carriage with the pen tip onto the paper corner, lock, set origin. "
                                      "The software then no longer knows the travel range; the machine frame is hidden.")

    def origin_after_hand(self):
        def go():
            self.plotter.lock_motors()
            self.plotter.set_origin()
        self.run(go)

    def step_2(self, p):
        self.head(p, "3  Pen")
        row = ttk.Frame(p)
        row.pack(fill="x")
        ttk.Label(row, text="Profile").pack(side="left")
        self.prof_var = tk.StringVar(value=self.profile_name)
        cb = ttk.Combobox(row, textvariable=self.prof_var, values=list(self.profiles), width=16)
        cb.pack(side="left", padx=4)
        cb.bind("<<ComboboxSelected>>", lambda e: self.load_profile())
        ttk.Button(row, text="Save", command=self.save_profile).pack(side="left")
        self.note(p, "Insert the pen. Lower it, adjust with Shift+Up/Down in 0.5 mm steps until it sits cleanly. "
                     "Raise it and check that it clears the paper. Space toggles up/down.")
        self.pen_vars = {}
        for key, label in (("pen_up", "Up"), ("pen_down", "Down")):
            row = ttk.Frame(p)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="%s (mm Z)" % label, width=14).pack(side="left")
            v = tk.StringVar(value="%g" % self.plotter.profile[key])
            self.pen_vars[key] = v
            e = ttk.Entry(row, textvariable=v, width=7)
            e.pack(side="left")
            e.bind("<Return>", lambda ev, k=key: self.apply_pen_field(k))
            ttk.Button(row, text="−0.5", width=5, command=lambda k=key: self.pen_delta(k, -0.5)).pack(side="left", padx=2)
            ttk.Button(row, text="+0.5", width=5, command=lambda k=key: self.pen_delta(k, 0.5)).pack(side="left")
        row = ttk.Frame(p)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Up", command=lambda: self.run(self.plotter.pen_up)).pack(side="left")
        ttk.Button(row, text="Down", command=lambda: self.run(self.plotter.pen_down)).pack(side="left", padx=4)
        ttk.Button(row, text="Cycle", command=lambda: self.run(self.cycle)).pack(side="left")
        ttk.Button(row, text="Test stroke 30 mm", command=lambda: self.run(self.test_stroke)).pack(side="left", padx=8)
        ttk.Label(p, text="Move carriage", font=("", 12, "bold")).pack(anchor="w", pady=(10, 2))
        self.build_jog(p)

    def step_3(self, p):
        self.head(p, "4  Speed")
        self.feed_vars = {}
        for key, label in (("feed_draw", "Drawing"), ("feed_travel", "Travel")):
            row = ttk.Frame(p)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text="%s (mm/min)" % label, width=20).pack(side="left")
            v = tk.StringVar(value="%d" % self.plotter.profile[key])
            self.feed_vars[key] = v
            e = ttk.Entry(row, textvariable=v, width=7)
            e.pack(side="left")
            e.bind("<Return>", lambda ev: self.apply_feeds())
            e.bind("<FocusOut>", lambda ev: self.apply_feeds())
        row = ttk.Frame(p)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text="Measured line width (mm)", width=26).pack(side="left")
        self.lw_var = tk.StringVar(value="%g" % self.plotter.profile.get("line_width", 0.3))
        ttk.Entry(row, textvariable=self.lw_var, width=7).pack(side="left")
        ttk.Button(p, text="Save profile", command=self.save_profile).pack(anchor="w", pady=4)
        ttk.Label(p, text="Test patterns at the current position", font=("", 12, "bold")).pack(anchor="w", pady=(10, 2))
        for name in core.TESTS:
            ttk.Button(p, text=name, width=18, command=lambda n=name: self.run(self.plotter.run_test, n)).pack(anchor="w", pady=1)
        self.note(p, "Line width: measure where the double lines separate, divide by 10. "
                     "Speed: rows at 1000 to 8000 mm/min. Accuracy: square and circle twice in opposite directions, "
                     "star, rulers. Pen height: rows at Z 3.0 to 6.5 mm.")
        ttk.Label(p, text="Move carriage", font=("", 12, "bold")).pack(anchor="w", pady=(10, 2))
        self.build_jog(p)

    def step_4(self, p):
        self.head(p, "5  Plot")
        self.note(p, "SVG: %s   page %g × %g mm   paper %g × %g mm" % (self.svg_name, self.page[0], self.page[1], self.paper[0], self.paper[1]))
        row = ttk.Frame(p)
        row.pack(fill="x")
        for val, text in (("1:1", "1:1 at page position"), ("center", "1:1 centered"), ("fit", "Fit to paper")):
            ttk.Radiobutton(row, text=text, value=val, variable=self.placement, command=self.update_placement).pack(side="left", padx=2)
        ttk.Label(p, text="Layers", font=("", 12, "bold")).pack(anchor="w", pady=(10, 2))
        hdr = ttk.Frame(p)
        hdr.pack(fill="x")
        ttk.Label(hdr, text="Plot", width=8).pack(side="left")
        ttk.Label(hdr, text="Pause before", width=11).pack(side="left")
        ttk.Label(hdr, text="Layer").pack(side="left")
        self.layer_vars = []
        for lyr in self.layers:
            row = ttk.Frame(p)
            row.pack(fill="x")
            en = tk.BooleanVar(value=lyr.enabled)
            pa = tk.BooleanVar(value=lyr.pause)
            ttk.Checkbutton(row, variable=en, width=6, command=self.update_placement).pack(side="left")
            ttk.Checkbutton(row, variable=pa, width=9, command=self.update_placement).pack(side="left")
            ttk.Label(row, text="%s  (%d paths)" % (lyr.name, len(lyr.paths))).pack(side="left")
            self.layer_vars.append((lyr, en, pa))
        row = ttk.Frame(p)
        row.pack(fill="x", pady=10)
        ttk.Button(row, text="▶ Start plot", command=self.start_plot).pack(side="left")
        ttk.Button(row, text="■ Stop", command=self.plotter.stop).pack(side="left", padx=6)
        ttk.Button(row, text="Trace drawing frame", command=self.frame_drawing).pack(side="left")
        self.progress = ttk.Progressbar(p, maximum=100)
        self.progress.pack(fill="x", pady=4)
        self.prog_var = tk.StringVar(value="")
        ttk.Label(p, textvariable=self.prog_var).pack(anchor="w")
        self.update_placement()

    # ------------------------------------------------------------ jog
    def build_jog(self, parent):
        f = ttk.Frame(parent)
        f.pack(anchor="w")
        s = lambda: self.step_size.get()
        ttk.Button(f, text="↑", width=4, command=lambda: self.run(self.plotter.jog, 0, -s())).grid(row=0, column=1)
        ttk.Button(f, text="←", width=4, command=lambda: self.run(self.plotter.jog, -s(), 0)).grid(row=1, column=0)
        ttk.Button(f, text="⌂", width=4, command=lambda: self.run(self.plotter.goto, 0, 0)).grid(row=1, column=1)
        ttk.Button(f, text="→", width=4, command=lambda: self.run(self.plotter.jog, s(), 0)).grid(row=1, column=2)
        ttk.Button(f, text="↓", width=4, command=lambda: self.run(self.plotter.jog, 0, s())).grid(row=2, column=1)
        g = ttk.Frame(f)
        g.grid(row=0, column=3, rowspan=3, padx=12, sticky="w")
        ttk.Label(g, text="Step mm").pack(anchor="w")
        for v in STEP_SIZES:
            ttk.Radiobutton(g, text=str(v), value=v, variable=self.step_size).pack(anchor="w")
        ttk.Label(parent, text="Arrow keys: move · 1/2/3: step · Space: pen · Shift+Up/Down: pen height ±0.5 · Esc: stop",
                  foreground="#444", wraplength=390).pack(anchor="w", pady=2)

    def bind_keys(self):
        def guard(fn):
            def h(event):
                if isinstance(self.root.focus_get(), (tk.Entry, ttk.Entry, ttk.Combobox)):
                    return
                fn()
                return "break"
            return h
        s = lambda: self.step_size.get()
        r = self.root
        r.bind("<Shift-Up>", guard(lambda: self.run(self.plotter.nudge_z, -0.5)))
        r.bind("<Shift-Down>", guard(lambda: self.run(self.plotter.nudge_z, 0.5)))
        r.bind("<Up>", guard(lambda: self.run(self.plotter.jog, 0, -s())))
        r.bind("<Down>", guard(lambda: self.run(self.plotter.jog, 0, s())))
        r.bind("<Left>", guard(lambda: self.run(self.plotter.jog, -s(), 0)))
        r.bind("<Right>", guard(lambda: self.run(self.plotter.jog, s(), 0)))
        r.bind("<space>", guard(lambda: self.run(self.plotter.pen_toggle)))
        for i, v in enumerate(STEP_SIZES):
            r.bind(str(i + 1), guard(lambda v=v: self.step_size.set(v)))
        r.bind("<Escape>", lambda e: self.plotter.stop())

    # ------------------------------------------------------------ actions
    def toggle_connect(self):
        if self.plotter.connected:
            self.plotter.disconnect()
        else:
            port = self.port_var.get()
            t = core.SimTransport() if port == "Simulation" else core.SerialTransport(port)
            try:
                self.plotter.connect(t)
                self.settings["last_port"] = port
            except Exception as err:
                messagebox.showerror("Connection", str(err))
                return
        self.conn_btn.config(text="Disconnect" if self.plotter.connected else "Connect")

    def set_model(self):
        self.plotter.model = self.model_var.get()
        self.settings["model"] = self.plotter.model
        self.draw_preview()

    def set_paper(self):
        name = self.fmt_var.get()
        if name == "Custom":
            return
        w, h = core.PAPER_FORMATS[name]
        if self.orient_var.get() == "portrait":
            w, h = h, w
        self.paper = (w, h)
        self.pw_var.set("%g" % w)
        self.ph_var.set("%g" % h)
        self.settings.update(paper=self.paper, paper_name=name, orient=self.orient_var.get())
        self.draw_preview()

    def set_paper_custom(self):
        try:
            self.paper = (float(self.pw_var.get()), float(self.ph_var.get()))
        except ValueError:
            return
        self.fmt_var.set("Custom")
        self.settings.update(paper=self.paper, paper_name="Custom")
        self.draw_preview()

    def frame_paper(self):
        self.run(self.plotter.frame, 0, 0, self.paper[0], self.paper[1])

    def frame_drawing(self):
        self.update_placement()
        pts = [p for l in self.placed if l.enabled for p in l.paths]
        if pts:
            self.run(self.plotter.frame, *core.bbox(pts))

    def cycle(self):
        self.plotter.pen_down()
        self.plotter.transport.send("G4 P0.5", seconds=0.5)
        self.plotter.pen_up()

    def test_stroke(self):
        x, y = self.plotter.x, self.plotter.y
        self.plotter.plot_strokes([([(x, y), (x + 30, y)], None, None, 0)], finish_home=False)
        self.plotter.goto(x, y)

    def apply_pen_field(self, key):
        try:
            self.plotter.profile[key] = float(self.pen_vars[key].get())
        except ValueError:
            return
        self.run(self.plotter.pen_up if key == "pen_up" else self.plotter.pen_down)

    def pen_delta(self, key, d):
        self.plotter.profile[key] = round(self.plotter.profile[key] + d, 2)
        self.pen_vars[key].set("%g" % self.plotter.profile[key])
        if self.plotter.connected and (self.plotter.z_up is (key == "pen_up")):
            self.run(self.plotter.pen_up if key == "pen_up" else self.plotter.pen_down)

    def apply_feeds(self):
        for key, v in self.feed_vars.items():
            try:
                self.plotter.profile[key] = int(float(v.get()))
            except ValueError:
                pass
        try:
            self.plotter.profile["line_width"] = float(self.lw_var.get())
        except (ValueError, AttributeError):
            pass

    def load_profile(self):
        name = self.prof_var.get()
        if name in self.profiles:
            self.profile_name = name
            self.plotter.profile = dict(self.profiles[name])
            for k, v in self.pen_vars.items():
                v.set("%g" % self.plotter.profile[k])

    def save_profile(self):
        if hasattr(self, "feed_vars"):
            self.apply_feeds()
        name = self.prof_var.get().strip() if hasattr(self, "prof_var") else self.profile_name
        if not name:
            return
        self.profile_name = name
        self.profiles[name] = dict(self.plotter.profile)
        self.settings["last_profile"] = name
        core.save_settings(self.settings)
        self.append_log("Profile \"%s\" saved." % name)

    def update_placement(self):
        if hasattr(self, "layer_vars"):
            for lyr, en, pa in self.layer_vars:
                lyr.enabled = en.get()
                lyr.pause = pa.get()
        self.placed = core.place(self.layers, self.page, self.paper, self.placement.get())
        self.strokes, self.pauses = self.plotter.strokes_from_layers(self.placed)
        self.done_count = 0
        self.draw_preview()

    def start_plot(self):
        self.update_placement()
        if not self.strokes:
            messagebox.showinfo("Plot", "No paths selected.")
            return
        if not self.plotter.origin_set:
            if not messagebox.askokcancel("Plot", "The origin is not set (step 2). Start anyway?"):
                return
        self.run(self.plotter.plot_strokes, self.strokes, self.pauses)

    # ------------------------------------------------------------ preview
    def draw_preview(self):
        c = self.canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W < 20:
            return
        pl = self.plotter
        xs, ys = [0, self.paper[0]], [0, self.paper[1]]
        if pl.bounds_known:
            mx, my = pl.machine_origin
            mw, mh = core.MODELS[pl.model]
            xs += [mx, mx + mw]
            ys += [my, my + mh]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        scale = min((W - 40) / max(x1 - x0, 1), (H - 40) / max(y1 - y0, 1))
        ox = 20 + ((W - 40) - (x1 - x0) * scale) / 2 - x0 * scale
        oy = 20 + ((H - 40) - (y1 - y0) * scale) / 2 - y0 * scale
        T = lambda x, y: (ox + x * scale, oy + y * scale)
        if pl.bounds_known:
            c.create_rectangle(*T(mx, my), *T(mx + mw, my + mh), outline="#999", dash=(4, 3))
            c.create_text(*T(mx + 2, my + 2), text="Machine %s" % pl.model, anchor="nw", fill="#777")
        c.create_rectangle(*T(0, 0), *T(*self.paper), fill="white", outline="#333")
        c.create_text(*T(2, self.paper[1] - 2), text="Paper %g × %g" % self.paper, anchor="sw", fill="#777")
        self.stroke_ids = []
        for i, (pts, _f, _z, _l) in enumerate(self.strokes):
            flat = [v for p in pts for v in T(*p)]
            col = "#000" if i < self.done_count else "#9ab"
            self.stroke_ids.append(c.create_line(*flat, fill=col, width=1))
        px, py = T(pl.x, pl.y)
        col = "#c00" if pl.z_up is False else "#06c"
        c.create_line(px - 8, py, px + 8, py, fill=col, width=2)
        c.create_line(px, py - 8, px, py + 8, fill=col, width=2)
        c.create_oval(*T(-1.5, -1.5), *T(1.5, 1.5), outline="#080")

    # ------------------------------------------------------------ events
    def poll(self):
        pl = self.plotter
        try:
            while True:
                kind, data = pl.events.get_nowait()
                if kind == "log":
                    self.append_log(data)
                elif kind == "state":
                    self.refresh_state()
                elif kind == "progress":
                    self.done_count = data["i"]
                    for i, sid in enumerate(self.stroke_ids):
                        if i < data["i"]:
                            self.canvas.itemconfig(sid, fill="#000")
                    if hasattr(self, "progress") and self.step == 4:
                        pct = 100 * data["done"] / data["total"] if data["total"] else 0
                        self.progress["value"] = pct
                        eta = "" if data["eta"] is None else "   remaining approx. %d:%02d min" % divmod(int(data["eta"]), 60)
                        self.prog_var.set("Path %d / %d   %.0f %%%s" % (data["i"], data["n"], pct, eta))
                elif kind == "pause":
                    if messagebox.askokcancel("Pause", "Layer \"%s\": change the pen, then OK.\nCancel stops the plot." % data):
                        pl.resume()
                    else:
                        pl.stop()
                elif kind == "done":
                    self.append_log("Plot %s." % data)
                elif kind == "error":
                    messagebox.showerror("Error", data)
        except queue.Empty:
            pass
        except Exception as err:
            self.append_log("GUI error: %s" % err)
        self.root.after(50, self.poll)

    def refresh_state(self):
        pl = self.plotter
        z = "?" if pl.z_up is None else ("up" if pl.z_up else "down")
        self.status_var.set(pl.status)
        self.pos_var.set("X %.1f  Y %.1f   pen %s   Z up %g  Z down %g" % (pl.x, pl.y, z, pl.profile["pen_up"], pl.profile["pen_down"]))
        if hasattr(self, "pen_vars"):
            for k, v in self.pen_vars.items():
                v.set("%g" % pl.profile[k])
        self.draw_preview()

    def append_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def load_svg(self, path):
        try:
            w, h, layers = core.load_svg(path)
            self.page, self.layers = (w, h), layers
            self.svg_name = os.path.basename(path)
        except Exception as err:
            self.svg_name = "error: %s" % err
            self.layers = []

    def quit(self):
        self.settings["paper"] = self.paper
        core.save_settings(self.settings)
        if self.plotter.connected:
            self.plotter.disconnect()
        self.root.destroy()


def main(argv):
    sim = "--sim" in argv
    svgs = [a for a in argv[1:] if a.endswith(".svg")]
    root = tk.Tk()
    App(root, svgs[0] if svgs else None, sim=sim)
    root.mainloop()


if __name__ == "__main__":
    main(sys.argv)
