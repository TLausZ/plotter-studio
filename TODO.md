# TODO

Tasks and ideas for Plotter Studio. Move a line to Done when it is finished.

## Next

- Hardware test on the plotter (iDraw A1): homing direction, axis signs, `$SLP` behaviour, `G92` after releasing motors.
- Test realtime commands (`!`, `~`, `?` during a move, `$J=`); if they work, make Stop immediate.
- Copy the five files into Inkscape's extension folder and launch from the menu.

## Ideas

- AxiDraw and plain GRBL dialects exist but were never run on a board: needs an owner to test axis signs, EBB step scale, servo range and the GRBL handshake.

- Tablet: test on the iPad and optimise touch handling (splitter hit area ~24 px, `touch-action: none` on splitter, board and zoom slider, maybe pinch zoom).
- Watercolor and brush setup wizard: guides through placing paint wells and brushes, dipping and rinsing positions.

- Path sorting via `plot_optimizations.reorder` before load_svg.

## Done

- 1 Oct 2026: the Title block row stays in the layer table when the title block is off, greyed with both boxes disabled.
- 1 Oct 2026: a reload keeps the view (step, zoom and pan, Sheet/Machine, placement details open), also during a plot; Reset starts at step 1 again; e2e suite at 27 checks.
- 1 Oct 2026: plot time estimate in the Plot step (drawn length, travel, pen moves) with a time factor per model from the last real plot of a minute or more; e2e suite at 26 checks.
- 1 Oct 2026: stress test drawing A4-portrait-migrant-mother-engraved.svg (31'550 paths) in tests/ with the e2e check large_drawing; e2e suite at 25 checks.
- 1 Oct 2026: path picker layout: slider over the full width, below it ‹ number › with Resume from path N and Plot only; the arrows step one path and run on while held; e2e suite at 24 checks.
- 1 Oct 2026: path picker in the Plot step: click a path on the board (crosshair over a path) or use the slider, Resume from path N or Plot only path N, available without a stop first; Trace drawing frame fixed; server and e2e tests use their own settings file; e2e suite at 23 checks.

- 1 Oct 2026: free placement in the Plot step (X/Y, scale in percent, align to sheet or margin, rotation in 15° or 90° steps and by angle, drag on the board); e2e suite at 22 checks.

- 14 Sep 2026: transport reply timeouts (expected move time plus 15 s, homing 120 s), link loss drops the connection; Resume from path N with slider after a stop; hidden-line removal in pure Python (checkbox in the Plot step, test drawing); AxiDraw (EBB) and plain GRBL dialects, marked untested; e2e suite at 20 checks.

- 4 Sep 2026: e2e suite at 18 checks, all passing (stop button, test drawing dropdown, outside-sheet warning, travel trace).
- 3 Sep 2026: test drawings folder with dropdown in the Speed step (replaces the test pattern buttons); Piter Pasma line test and DrawingBotV3 calibration sheet added.
- 3 Sep 2026: title block is plotted (Hershey single-stroke text, virtual last layer, corner button with off state as server setting).
- 3 Sep 2026: Playwright e2e suite (13 checks, reset before each, run by name), Reset button with dialog, TESTING.md.
- 3 Sep 2026: console input under the log sends hand-typed G-code and $ commands; the state tracks every line (G0/G1, G90/G91, G92, $H, $1, $SLP, $RST); manual moves leave a dashed trace on the board. A ? button opens the command reference; a click fills the input line.
- 3 Sep 2026: step tabs and Back/Next/Stop in the side column, board tools strip (title block corner, zoom, pan).
