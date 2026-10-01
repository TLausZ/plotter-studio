# Testing

Three levels, all plain scripts that print `ok` (no test framework). Run them from `extensions/`.

Logic, `python3 test_idraw_core.py`: axis mapping and G-code of a plot run, origin after jog and `G92`, stop ends after the current line, resume from path N, plot only one path, plot time estimate and the timing of a run (pauses left out, none after a stop), placement modes, rotation and alignment, test patterns, console parser (G0/G1, G90/G91, G92, `$H`, `$1`).

Server, `python3 test_idraw_server.py`: starts the server with the simulator on a free port and talks HTTP: snapshot with layers and strokes, connect, home, unit, placement (presets, rotate about the centre, align with margin, move, X field, bad values), layer flags, jog, plot to the end, frame around the drawing, plot only one path (no layer pause, bad ranges refused), time factor (not from the simulator or plots under a minute), error on an unknown command.

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
| title_block_corner | button cycles the four corners and off with the matching icon, the title block is a virtual last layer with its own checkbox; off keeps the row with both boxes empty and disabled and no strokes, on again brings the box back as it was; the choice is a server setting and survives a reload |
| reset_button | Reset in the app bar opens a dialog; Cancel changes nothing; Reset restores mm, A4, 1:1, view, layers, clears browser storage (the reloaded page starts at step 1 and stores only its new view), keeps the connection |
| plot_with_pause | plot runs, pause dialog before the `!` layer, continue, finished with all strokes done (drawing plus title block) |
| stop_with_escape | Esc stops a running plot, pen up, status ready |
| stop_button | the red Stop in the app bar stops a running plot like Esc |
| test_drawing_dropdown | Speed step: a file from tests/ replaces the document and clears trace, done marks and progress; the first entry brings the document back |
| outside_sheet_warning | A4 drawing at 1:1 on a 148 × 105 sheet: amber paths, notice in the Plot step, Start plot opens the confirm dialog, Cancel starts nothing, Plot anyway starts |
| travel_trace_during_plot | a plot clears the manual trace, leaves dotted travel segments only, the next plot starts with an empty trace |
| model_dropdown | Untested models carry the label and the hint; after a reconnect an AxiDraw model sends EBB commands, no G-code. |
| resume_from_path | After a stop the Run group shows a slider and Resume from path N; the plot continues from there and finishes. |
| path_picker | Without a stop first the Run group offers the picker at path 1; over a path the board shows the crosshair, a click picks it (thick, the paths before done), a click on the empty mat keeps the pick and drops the crosshair, Plot only draws just that path and the picker moves on to the next. |
| path_stepping | The number field picks a path (Enter; beyond the last means the last), ‹ and › step one path per click and stop at the first, held down they run on and stop when released; Resume from path N follows. |
| large_drawing | Stress test: the engraving with 31'550 paths from tests/ loads and is drawn within 10 s, a click on the board picks a path; no plot (the 40× simulator outruns the page). |
| plot_estimate | The time estimate next to Trace drawing frame equals `idraw_core.estimate` on the same paths and shows it with its parts in the hover text; a measured time factor for the model scales it. |
| view_survives_reload | A reload keeps step 5, zoom 4× with the same viewBox, Machine and the open placement details; a reload during a plot comes back to step 5 with the plot running. |
| hidden_lines | The checkbox in the Plot step reloads the drawing with lines behind fills split; the setting survives a reload. |
| placement_adjust | Position, scale, rotation: rotate by 90°, a preset keeps the rotation, 15° steps and the angle field (rounded to 15°), align right to a 10 mm margin, X field, scale 50 % halves the width, back to 1:1. |
| drag_drawing | With Position, scale, rotation open, dragging the drawing on the board moves it by the dragged distance; 1:1 brings it back. |

The server and e2e runs write their settings to an empty file in a temporary folder, so they start from the defaults and never touch `idraw_interactive_settings.json`. Add a check by writing `check_<name>(page)`, listing it in `CHECKS`, and adding its line to the table above. A click or a select that sends a command goes through `click_cmd` or `select_cmd`, which wait for the server's reply: the server is threaded, so two commands sent back to back can finish in the wrong order.

Not covered: screenshot comparisons, touch and tablet, the real plotter (see TODO.md).
