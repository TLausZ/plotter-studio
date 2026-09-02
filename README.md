# iDraw Interactive

Interactive control for the UUNA TEK iDraw H A1 (DrawCore V2.0 board, GRBL dialect) as an Inkscape extension with a local web UI. Wizard flow: Connect, Paper, Pen, Speed, Plot. Runs without a device in simulation mode, and on an iPad in the same network.

This document is for people and agents building on it: other features, other platforms, other plotters.

## Folders

```
inkscape-extension/
  README.md                          this file
  DESIGN.md                          Material Design 3 components on the drafting palette; tokens and rationale of the web UI
  iDraw Extension Analysis 2026-09-02.md   how the original plugin works, firmware commands, axis mapping
  extensions/                        working copy; Inkscape reads ~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions
    idraw_core.py                    plotter logic without UI (transport, state, plot run, tests, SVG loading)
    idraw_server.py                  local HTTP server: one Session around a Plotter, JSON commands, server-sent events
    idraw_web.html                   the web UI, one file (HTML, CSS, JS), served by idraw_server.py
    idraw_interactive.py             Inkscape entry point: copies the document, starts the server detached, returns
    idraw_interactive.inx            menu entry Extensions > iDraw > iDraw Interactive
    idraw_demo.svg                   example with three layers (normal, !-pause, %-notes)
    test_idraw_core.py               self-test for idraw_core
    test_idraw_server.py             self-test for the server (simulator, no browser)
    idraw_interactive_settings.json  created on first run: paper, profiles, model, unit (not in git)
    idraw_interactive_last.svg       copy of the document handed over by Inkscape (not in git)
    idraw2_0.inx, idraw2_0_control.py, idraw2_0_conf.py, idraw_plot_utils_import.py
                                     original "iDraw 2.0 Control" by UUNA TEK, unchanged, as fallback and reference
    idraw_deps/                      dependencies of the original; the new plugin uses its SVG digest
                                     (idraw2_0internal, ink_extensions, drawcore_plotink) and pyserial as a fallback
  archive/
    extensions-original-2026-09-02/  complete copy of the shipped extension folder before cleanup
    nicht-gebraucht/                 unused: AxiDraw, iDraw 1.0, HSE, laser, merge, naming, hatch, Hershey, process_ai
    tk-ui/                           first UI as a tkinter window; replaced by the web UI (Inkscape's Tk 8.5 draws nothing on macOS 26)
```

## Running

Demo without a device, from the terminal:

```
cd extensions
/usr/local/bin/python3 idraw_server.py idraw_demo.svg --sim
```

The server prints its address (default `http://127.0.0.1:8765/`) and opens the browser. Options: `--port N`, `--no-browser`, `--lan` to accept connections from other devices (the LAN address is printed; open it on the iPad). Any Python 3.8+ with lxml works; pyserial is optional, without it the pure-Python copy in `idraw_deps/serial` is used. Inkscape's own Python has both.

Self-tests: `python3 test_idraw_core.py` and `python3 test_idraw_server.py` each print `ok`.

In Inkscape: copy the five new files into Inkscape's extension folder (the originals are already there):

```
cp extensions/idraw_core.py extensions/idraw_server.py extensions/idraw_web.html \
   extensions/idraw_interactive.py extensions/idraw_interactive.inx \
   ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/extensions/
```

Restart Inkscape, open a document, Extensions > iDraw > iDraw Interactive. Tick "Simulation" for a dry run, "Allow other devices" for the iPad. The extension returns at once; Inkscape stays usable and the SVG is not modified. Run the extension again to load a changed drawing (it starts a second server on the next free port only if the first was closed; close the old browser tab first).

Keyboard on the page: arrow keys move the carriage, 1/2/3 set the step, Space toggles the pen, Shift+Up/Down shifts the current pen height by 0.5 mm and writes it into the profile, Esc stops. Keys are ignored while a field has focus. The unit switch (mm, cm, in) changes the readout, the paper fields, the jog steps and the rulers; everything is stored in mm.

## Architecture

Three layers so the UI stays replaceable:

```
browser (idraw_web.html)  <-- HTTP/SSE -->  idraw_server.Session  -->  idraw_core.Plotter  -->  Transport (Serial, Sim)
```

`idraw_core.Plotter` holds the machine state (position in document mm, pen, status, profile) and produces G-code in exactly two places: `_move_abs` (XY, where the axis mapping X = −y, Y = −x lives) and `_z` (pen height). Commands run on its worker thread; it reports through a queue of events.

`idraw_server.Session` adds what a UI needs: the loaded SVG (page, layers), paper, placement, unit, profiles, and a fan-out of the plotter's events to every connected browser. The HTTP interface is three routes: `GET /api/snapshot` (everything), `GET /api/events` (server-sent events), `POST /api/cmd` (`{"cmd": name, ...}`). The command list is in the module docstring of `idraw_server.py`.

`idraw_web.html` keeps one snapshot object, re-renders the side panel from it, and draws the board as inline SVG in millimetre units, so the preview is exact by construction.

### Building another UI

Any client that speaks the three routes works: a native app, a CLI, a different web page. Nothing in `idraw_core` or `idraw_server` knows about the HTML. For a very different interaction (for example a Tk window) use `idraw_core.Plotter` directly, as the archived Tk UI did.

### Another plotter

Same G-code understanding (GRBL with Z as the pen): a new transport is enough, possibly with an adapted handshake in `open()`. AxiDraw/EBB (commands `SM`, `SP`, no G-code): override `_move_abs`, `_z`, `home`, `release_motors` in a subclass of `Plotter`; the rest (plot run, tests, placement, events) stays. Travel ranges go into `MODELS` (and the copy in `idraw_web.html` for the preview).

### New features

Test patterns: add a function following the pattern in `idraw_core.TESTS`; the page builds the button. Placement modes: extend `place()` and the button row in step 5. Resume after abort: `plot_strokes` reports the index in every `progress` event; a resume is a start with `strokes[i:]`. Hidden-line removal, path sorting: apply `plot_optimizations.reorder` from `idraw_deps/idraw2_0internal` to the digest before `load_svg` builds the layers.

## Firmware, short version

DrawCore enumerates as CH340 (USB VID:PID 1A86:7523), 115200 baud, `rts`/`dtr` off. Send one line, wait for `ok`. `$H` homing, `$X` clear alarm, `$SLP` sleep, `$1=254`/`$1=255` motors released/held, `G92 X0 Y0` set origin, `G1 X Y F` move, `G1 Z F` pen, `$B` pause button, `$QP` pen state. Full table and sources in the analysis document.

## Status

As of 2 September 2026. Built and exercised in the simulator: all five steps, jog, pen, profiles, unit switch, four test patterns, plot with layer pause, stop, progress, preview with rulers and title block, LAN access.

Not verified on the device yet:

- Homing sequence and the sign of the axis mapping (taken from the original).
- Whether the firmware knows realtime commands (`!` feed hold, `~` resume, `?` status during a move, `$J=` jog). Stop therefore takes effect after the current G-code line; a stroke is at most one segment long.
- Behaviour after `$SLP` (does the firmware need a reset?).
- `G92` after releasing the motors.

Security note: with `--lan` anyone on the network can move the plotter. There is no authentication; use it only on a trusted network.

Not built: resume after abort, copies, laser, multiple devices, webhook, hidden-line removal, free positioning with the mouse on the board.
