# iDraw Interactive

Interactive control for the UUNA TEK iDraw H A1 (DrawCore V2.0 board, GRBL dialect) as an Inkscape extension with its own window. Wizard flow: Connect, Paper, Pen, Speed, Plot. Runs without a device in simulation mode.

This document is for people and agents building on it: other features, other platforms (web UI, iPad), other plotters.

## Folders

```
inkscape-extension/
  README.md                          this file
  DESIGN.md                          colors, typography, spacing of the UI
  iDraw Extension Analysis 2026-09-02.md   how the original plugin works, firmware commands, axis mapping
  extensions/                        working copy; Inkscape reads ~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions
    idraw_core.py                    plotter logic without GUI (transport, state, plot run, tests, SVG loading)
    idraw_interactive_gui.py         Tk wizard, pure view
    idraw_interactive.py             Inkscape entry point (starts the GUI with the current document)
    idraw_interactive.inx            menu entry Extensions > iDraw > iDraw Interactive
    idraw_demo.svg                   example with three layers (normal, !-pause, %-notes)
    test_idraw_core.py               self-test for idraw_core
    idraw_interactive_settings.json  created on first run: paper, profiles, model (not in git)
    idraw2_0.inx, idraw2_0_control.py, idraw2_0_conf.py, idraw_plot_utils_import.py
                                     original "iDraw 2.0 Control" by UUNA TEK, unchanged, as fallback and reference
    idraw_deps/                      dependencies of the original; the new plugin uses its SVG digest
                                     (idraw2_0internal, ink_extensions, drawcore_plotink) and pyserial as a fallback
  archive/
    extensions-original-2026-09-02/  complete copy of the shipped extension folder before cleanup
    nicht-gebraucht/                 unused: AxiDraw, iDraw 1.0, HSE, laser, merge, naming, hatch, Hershey, process_ai
```

## Running

Demo without a device, from the terminal:

```
cd extensions
/usr/local/bin/python3 idraw_interactive_gui.py idraw_demo.svg --sim
```

Requirements for the Python: tkinter 8.6 or newer and lxml. pyserial is optional; without it the pure-Python copy in `idraw_deps/serial` is used. Inkscape's own Python (`/Applications/Inkscape.app/Contents/Resources/bin/python3`) has everything, but its Tk 8.5 draws an empty window on macOS 26, so use the system Python for the demo. Launching from Inkscape has the same limitation, see Status.

Self-test: `/usr/local/bin/python3 test_idraw_core.py` prints `ok`.

In Inkscape: first copy the four new files into Inkscape's extension folder (the originals are already there):

```
cp extensions/idraw_core.py extensions/idraw_interactive.py extensions/idraw_interactive_gui.py extensions/idraw_interactive.inx \
   ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/extensions/
```

Restart Inkscape, open a document, Extensions > iDraw > iDraw Interactive, tick "Simulation" for a dry run. The SVG is not modified.

Keyboard in the window: arrow keys move the carriage, 1/2/3 set the step (1/10/50 mm), Space toggles the pen, Shift+Up/Down shifts the current pen height by 0.5 mm and writes it into the profile, Esc stops. Keys are ignored while an entry field has focus.

## Architecture

Three layers so the UI stays replaceable:

```
UI (Tk today, web UI later)  -->  Plotter (idraw_core)  -->  Transport (SerialTransport, SimTransport)
```

The UI calls plotter methods through `Plotter.start(fn, *args)` on the worker thread and reads events from `Plotter.events` (queue.Queue). The Plotter holds the state (position in document mm, pen, status, profile) and produces G-code in exactly two places: `_move_abs` (XY, where the axis mapping X = −y, Y = −x lives) and `_z` (pen height). The transport only knows text lines and replies.

Details, event protocol and interfaces are in the module docstrings of `idraw_core.py` and `idraw_interactive_gui.py`.

### Building another UI

For example a web UI for the iPad: a small HTTP server on the Mac (the Mac stays the USB bridge) holding the same `Plotter` instance, taking commands as POST and forwarding the event queue through server-sent events or a WebSocket. The five wizard steps can be rebuilt 1:1; nothing in `idraw_core` knows about Tk.

### Another plotter

Same G-code understanding (GRBL with Z as the pen): a new transport is enough, possibly with an adapted handshake in `open()`. AxiDraw/EBB (commands `SM`, `SP`, no G-code): override `_move_abs`, `_z`, `home`, `release_motors` in a subclass of `Plotter`; the rest (plot run, tests, placement, events) stays. Travel ranges go into `MODELS`.

### New features

Test patterns: add a function following the pattern in `idraw_core.TESTS`; the UI creates the button. Placement modes: extend `place()`. Resume after abort: `plot_strokes` reports the index in every `progress` event; a resume is a start with `strokes[i:]`. Hidden-line removal, path sorting: apply `plot_optimizations.reorder` from `idraw_deps/idraw2_0internal` to the digest before `load_svg` builds the layers.

## Firmware, short version

DrawCore enumerates as CH340 (USB VID:PID 1A86:7523), 115200 baud, `rts`/`dtr` off. Send one line, wait for `ok`. `$H` homing, `$X` clear alarm, `$SLP` sleep, `$1=254`/`$1=255` motors released/held, `G92 X0 Y0` set origin, `G1 X Y F` move, `G1 Z F` pen, `$B` pause button, `$QP` pen state. Full table and sources in the analysis document.

## Status

As of 2 September 2026. Built and exercised in the simulator: all five steps, jog, pen, profiles, four test patterns, plot with layer pause, stop, progress, preview.

Known problem: launched from Inkscape the GUI runs on Inkscape's Tk 8.5, which shows an empty window on macOS 26. Fix open; candidates: `idraw_interactive.py` launches the GUI with the system Python via `subprocess`, or a web UI instead of Tk.

Not verified on the device yet:

- Homing sequence and the sign of the axis mapping (taken from the original).
- Whether the firmware knows realtime commands (`!` feed hold, `~` resume, `?` status during a move, `$J=` jog). Stop therefore takes effect after the current G-code line; a stroke is at most one segment long.
- Behaviour after `$SLP` (does the firmware need a reset?).
- `G92` after releasing the motors.

Not built: resume after abort, copies, laser, multiple devices, webhook, hidden-line removal, free positioning with the mouse in the preview.
