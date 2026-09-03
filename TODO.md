# TODO

Tasks and ideas for iDraw Interactive. Move a line to Done when it is finished.

## Next

- Hardware test on the plotter: homing direction, axis signs, `$SLP` behaviour, `G92` after releasing motors.
- Test realtime commands (`!`, `~`, `?` during a move, `$J=`); if they work, make Stop immediate.
- Copy the five files into Inkscape's extension folder and launch from the menu.

## Ideas

- Built-in GRBL command reference (list of commands with short explanations).
- Watercolor and brush setup wizard: guides through placing paint wells and brushes, dipping and rinsing positions.

- Resume a plot after abort (progress index is already reported).
- Free positioning of the drawing with the mouse on the board.
- Path sorting / hidden-line removal via `plot_optimizations.reorder` before load_svg.

## Done

- 3 Sep 2026: console input under the log sends hand-typed G-code and $ commands; the state tracks every line (G0/G1, G90/G91, G92, $H, $1, $SLP, $RST); manual moves leave a dashed trace on the board.
- 3 Sep 2026: step tabs and Back/Next/Stop in the side column, board tools strip (title block corner, zoom, pan).
