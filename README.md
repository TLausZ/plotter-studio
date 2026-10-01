# Plotter Studio

Pen plotter control for Inkscape with a local web UI. Built for the UUNA TEK iDraw; AxiDraw and plain GRBL plotters are supported but untested. Five steps: Connect, Paper, Pen, Speed, Plot. Runs without a device in a simulator, and on an iPad in the same network.

**Alpha.** Everything runs in the simulator, nothing has run on a real plotter yet. Have a plotter? Try it and tell us how it went in [issue #1](https://github.com/TLausZ/plotter-studio/issues/1); a note like "homing went to the wrong corner" already helps. Bug reports, pull requests and other plotters are welcome.

How to use it: [MANUAL.md](MANUAL.md), online at [tlausz.github.io/plotter-studio/MANUAL.html](https://tlausz.github.io/plotter-studio/MANUAL.html).

![Plotter Studio: web UI plotting the iDraw A3 test sheet in the simulator](docs/screenshot.png)

## Running

Without a device:

```
cd extensions
/usr/local/bin/python3 idraw_server.py idraw_demo.svg --sim
```

The browser opens at `http://127.0.0.1:8765/`. Other options are `--port N`, `--no-browser` and `--lan` for the iPad. Needs Python 3.8 or newer with lxml. With `--lan` anyone on the network can move the plotter, there is no login.

In Inkscape, copy the five files into the extension folder:

```
cp extensions/idraw_core.py extensions/idraw_server.py extensions/idraw_web.html \
   extensions/idraw_interactive.py extensions/idraw_interactive.inx \
   ~/Library/Application\ Support/org.inkscape.Inkscape/config/inkscape/extensions/
```

Restart Inkscape, then Extensions > Plotter > Plotter Studio. After changing the drawing, close the browser tab and run the extension again.

Tests: `python3 test_idraw_core.py`, `test_idraw_server.py` and `test_idraw_e2e.py` in `extensions/`, each prints `ok`. More in [TESTING.md](TESTING.md).

## Files

```
MANUAL.md, DESIGN.md, TESTING.md, TODO.md
iDraw Extension Analysis 2026-09-02.md   the original plugin and the firmware commands
docs/                        pictures for the manual; make_screenshots.py makes them again
extensions/
  idraw_core.py              plotter logic: transport, state, plot run, SVG loading
  idraw_server.py            local HTTP server
  idraw_web.html             the web UI in one file
  idraw_interactive.py/.inx  Inkscape entry point and menu entry
  idraw_demo.svg             example with three layers
  tests/                     test drawings for the Speed step
  test_idraw_*.py            tests
  idraw2_0*, idraw_deps/     the original iDraw 2.0 plugin by UUNA TEK, unchanged, and its dependencies
```

## Architecture

```
browser (idraw_web.html)  <-- HTTP/SSE -->  idraw_server.Session  -->  idraw_core.Plotter  -->  Transport (Serial, Sim)
```

`Plotter` holds the machine state and writes all G-code in two methods: `_move_abs` (XY, with the axis mapping) and `_z` (pen). `Session` adds the drawing, paper, placement and profiles. The server has three routes: `GET /api/snapshot`, `GET /api/events` and `POST /api/cmd`; the commands are listed at the top of `idraw_server.py`. Another UI only has to speak these three routes.

## Other plotters

`MODELS` in `idraw_core.py` lists the models, `dialect()` picks the command set: `drawcore` for the iDraw, `grbl` for GRBL 1.1 with Z as the pen, `ebb` for the AxiDraw. The AxiDraw and GRBL code is written from the vendors' code and has never run on a device, so start with small moves.

## Adding features

- Test drawings: drop an SVG into `extensions/tests/`, it shows up in the Speed step.
- Placement: `preset()` builds the transform for the buttons in step 5, `place()` applies it, `align()` moves the drawing's box.
- Path sorting: run `plot_optimizations.reorder` from `idraw_deps/idraw2_0internal` on the digest before `load_svg` builds the layers.

## Status

As of 2 October 2026. Working in the simulator:

- all five steps, jog, pen, profiles, mm and inch
- test drawings, including a stress test with 31'550 paths
- plot with layer pause, stop and progress
- resume from path N, or plot a single path picked on the board
- free placement: position, scale, rotation, align, drag on the board
- plot time estimate that learns from the last real plot
- preview with rulers and title block
- hidden-line removal
- transport timeouts
- a reload keeps the view
- LAN access

Not verified on a device yet, the iDraw H A1 comes first:

- homing and the direction of the axes
- realtime commands; until then stop waits for the current G-code line
- behaviour after `$SLP`
- `G92` after releasing the motors

Not built: copies, laser, multiple devices, webhook, path sorting.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The bundled original code in `extensions/idraw_deps/` keeps its own licenses: `idraw2_0internal` and `ink_extensions` are GPL-2.0-or-later, `drawcore_plotink` and `serial` are MIT/BSD. The Hershey font has its own license in `extensions/HersheySans1-LICENSE.txt`.
