# Testing

Three levels, all plain scripts that print `ok` (no test framework). Run them from `extensions/`.

Logic, `python3 test_idraw_core.py`: axis mapping and G-code of a plot run, origin after jog and `G92`, stop ends after the current line, placement modes, test patterns, console parser (G0/G1, G90/G91, G92, `$H`, `$1`).

Server, `python3 test_idraw_server.py`: starts the server with the simulator on a free port and talks HTTP: snapshot with layers and strokes, connect, home, unit, placement, layer flags, jog, plot to the end, error on an unknown command.

Browser, `python3 test_idraw_e2e.py`: starts the server with the simulator (40× faster) and drives the page in headless Chromium with Playwright (once: `pip install playwright`, `playwright install chromium`; `--headed` shows the browser). `reset(page)` runs before every check: fresh page without browser storage, mm, A4 landscape, 1:1, connected to the simulator, homed, pen up. Checks are therefore independent of their order, and one or more can be run by name: `python3 test_idraw_e2e.py splitter zoom_and_pan`. One function per check:

| Check | What it verifies |
|---|---|
| connect_and_home | disconnect, status chip, connect to Simulation, home, position 0/0, pen unknown |
| steps_fit_without_scrolling | each of the five steps fits the panel at 1280 × 690 |
| keyboard_jog_and_pen | keys 2 and arrows move 10 mm, Space toggles the pen, home symbol returns to origin |
| console | hand-typed line updates position and trace, history with arrow up, reference dialog fills the input |
| paper_and_title_block | format and orientation appear in the title block |
| paper_fields_and_orientation | width/height fields and sheet rectangle follow format and orientation; Custom keeps the fields |
| units | cm in readout and title block, back to mm |
| splitter | drag resizes the board, minimums for console and board, double-click resets and forgets |
| zoom_and_pan | 4× quarters the viewBox around the centre, drag pans, 0.5× doubles it, double-click resets |
| title_block_corner | button cycles the four corners and off with the matching icon, the title block is a virtual last layer with its own checkbox, the choice is a server setting and survives a reload |
| reset_button | Reset in the app bar opens a dialog; Cancel changes nothing; Reset restores mm, A4, 1:1, view, layers, clears browser storage, keeps the connection |
| plot_with_pause | plot runs, pause dialog before the `!` layer, continue, finished with all strokes done (drawing plus title block) |
| stop_with_escape | Esc stops a running plot, pen up, status ready |

The e2e run changes paper and unit and restores the settings file afterwards. Add a check by writing `check_<name>(page)`, listing it in `CHECKS`, and adding its line to the table above.

Not covered: screenshot comparisons, touch and tablet, the real plotter (see TODO.md).
