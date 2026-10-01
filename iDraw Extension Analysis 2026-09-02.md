# iDraw 2.0 Inkscape extension: how it works

Analysis of the folder `extensions/` as shipped by UUNA TEK (state 2 September 2026, extension version "2.2.7-2026-06-20" per `idraw2_0.inx`), focused on the extension responsible for the iDraw H A1: "iDraw 2.0 Control". Purpose: a basis for an own, interactive plugin. Sources: the code itself plus the manufacturer pages listed at the end.

## Environment

Inkscape 1.4.2 on macOS, with its own Python 3.10.13 in `/Applications/Inkscape.app/Contents/Resources/bin/python3`. That Python has `tkinter` (8.5) and `pyserial` 3.5. The system Python 3.14 has no pyserial. The extensions were installed identically in `~/Library/Application Support/org.inkscape.Inkscape/config/inkscape/extensions/` and in the project folder (the latter has since been cleaned up; the copy is in `archive/` in the git history, commit 5256766).

## Which files belong together

The folder contains four product families sharing code but with separate dependency folders:

| Family | .inx | Wrapper | Config | Internals |
|---|---|---|---|---|
| AxiDraw (original EMS) | `axidraw.inx` | `axidraw_control.py` | `axidraw_conf.py` | `axidraw_deps/axidrawinternal` |
| iDraw 1.0 | `idraw1_0.inx`, `idraw1_0_laser.inx` | `idraw_control.py` | `idraw_conf.py` | references `axidrawinternal`, missing in `idraw_deps/` |
| iDraw HSE | `idraw_HSE.inx` | `axidraw_control.py` | `axidraw_conf.py` | `axidraw_deps/axidrawinternal` |
| iDraw 2.0 / H | `idraw2_0.inx`, `idraw2_0_laser.inx` | `idraw2_0_control.py`, `idraw2_0_laser_control.py` | `idraw2_0_conf.py`, `idraw2_0_laser_conf.py` | `idraw_deps/idraw2_0internal` + `idraw_deps/drawcore_plotink` |

Plus helper extensions: `idraw2_merge` (mail merge), `idraw2_naming` (set nickname), `idraw_hatch` (hatching via `eggbot_hatch.py`), Hershey text (`hershey_i*.inx`, `hta/`), `process_ai` (clean Illustrator SVG).

The iDraw H A1 belongs to the iDraw 2.0 family. The H series has the DrawCore V2.0 board, and only `idraw2_0.inx` offers "iDraw A1" (model value 5). The laser variant is the same code with `use_pwm_out = 1` in the config and different setup buttons (laser on/off/focus instead of pen up/down).

## Call chain

Inkscape starts a new process for every click on "Apply". No state survives between two clicks.

1. Inkscape reads `idraw2_0.inx`, builds the dialog from it and calls `python idraw2_0_control.py --mode=... --speed_pendown=... <tempfile.svg>`. Every `<param name="x">` becomes `--x=value`. The active notebook tab lands in `--mode`, the sub-tab in `--submode`.
2. `idraw2_0_control.py` (generated wrapper) imports the modules from `idraw_deps/` through `idraw_plot_utils_import.from_dependency_import()`. The trick: `idraw_deps/` is temporarily put at the front of `sys.path` so the bundled packages (lxml, pyserial, requests) do not collide with other installations.
3. The wrapper loads `idraw2_0_conf.py` as a module and passes it as `params` to `idraw2_0internal.idraw_control.iDrawWrapperClass`. Then `exit_status.run(e.affect)`.
4. `inkex.Effect.affect()` (old inkex API, bundled in `ink_extensions/inkex.py`): parses the options with `optparse`, reads the SVG from the temp file, calls `effect()`, and writes the SVG back to stdout only if it changed. Messages to the user go through `inkex.errormsg()` to stderr; Inkscape shows stderr as the "received additional data" dialog.
5. `iDrawWrapperClass.effect()` handles port selection (first found, named, or all devices via threads) and creates one `idraw.iDraw` object per device, copies the relevant options into it and calls its `effect()`.
6. `idraw.iDraw.effect()` is the actual dispatcher by mode.

Ctrl-C (SIGINT) is caught in the wrapper and translated into a `threading.Event` that `iDraw.pause_check()` interprets as a pause. Not reachable from Inkscape, only from the CLI.

## Configuration

`idraw2_0_conf.py` (identical to `idraw_deps/idraw2_0internal/idraw2_0_conf.py`) has three tiers: defaults for all GUI options, parameters only in the file (e.g. `servo_timeout`, `smoothness`, `cornering`, `use_pwm_out`, `min_gap`, `clip_to_page`), and machine constants.

Values relevant for the A1:

| Parameter | Value | Meaning |
|---|---|---|
| `x_travel_SEA1` | 34.02 in (864 mm) | X travel for model 5 |
| `y_travel_SEA1` | 23.39 in (594 mm) | Y travel for model 5 |
| `native_res_factor` | 1270 | gives `step_scale` 2540 steps/inch = 100 steps/mm in high-res |
| `speed_pendown` | 2000 mm/min | drawing speed, passed raw as `F` to the firmware |
| `speed_penup` | 8000 mm/min | travel |
| `pen_pos_up` / `pen_pos_down` | 0.5 mm / 5 mm | absolute Z positions |
| `pen_rate_raise` / `pen_rate_lower` | 5000 | Z feed rate |
| `accel` | 75 (GUI: 50) | factor for the software planning, see below |
| `start_pos_x` / `start_pos_y` | 0 / 0 | park position after the plot |

All internal calculations are in inches. The model numbers (1 A4, 2 A3, 5 A1, 6 A2, 8 A0) only select the bounds pair; nothing else differs between models. Several constants (`servo_min`, `servo_max`, `speed_lim_xy_*`, `max_step_rate`) are AxiDraw heritage and are no longer used, or only formally, in the DrawCore path.

## Modes in `iDraw.effect()`

The value of `--mode` is the tab name from the .inx. Modes without hardware are handled first (`options`, `version`, `manual` with `strip_data`, `list_names`, `list_port_info`, resume offsets). Then the tab `setup` is mapped to `setup_type` (align, raise_pen, lower_pen, cycle) and `resume` to `res_plot` or `res_home`. Then `serial_connect()`, except in preview.

| Mode | What happens |
|---|---|
| `plot` | digest SVG, optimize, plot all visible layers, `copies` times with `page_delay` between |
| `layers` | like plot, but only layers whose name starts with the number `--layer` |
| `res_plot` | read plot data from `<plotdata>`, crop the digest to `pause_dist`, continue |
| `res_home` | pen up, move to park position, starting from the stored `last_x/last_y` |
| `align` | pen up, `$SLP` (motors off) |
| `raise_pen` / `lower_pen` / `cycle` | Z move, cycle with `G4 P0.5` in between |
| `laser_on` / `laser_off` / `laser_focus` / `cycle_laser` | `M3 S<power*10>` |
| `manual` | see manual commands |
| `sysinfo` | version report, fully commented out in the DrawCore code, prints nothing |

Manual commands (`--manual_cmd`):

| Command | Serial |
|---|---|
| `fw_version` | shows the version string read at connect |
| `walk_x`, `walk_y`, `walk_mmx`, `walk_mmy` | relative move by `--dist`; `G1 F<speed_penup>` then a segment move; position is not saved |
| `walk_home` | empty in the DrawCore code, does nothing |
| `raise_pen`, `lower_pen` | Z move |
| `lock_motor` / `unlock_motor` | `$1=255` / `$1=254` (GRBL step idle delay) |
| `machine_origin` | `$H`, then `G1G91 X<y_bounds_mm> Y0 F5000`, then `$SLP` |
| `list_drawcore_info` | `$$` |
| `default_settings` | `$RST=*` |
| `list_names`, `read_name`, `write_name<NAME>` | `$QT`, `$ST=<NAME>` |
| `strip_data` | removes `plotdata`, `WCB`, `MergeData`, `eggbot` from the SVG |
| `enable_xy` / `disable_xy` | commented out in the .inx |

## Serial connection (drawcore_serial.py)

The DrawCore board enumerates as CH340 (USB VID:PID 1A86:7523) or 1A86:8040. 115200 baud, timeout 1 s, `rts` and `dtr` False (prevents a reset on open). Opening sequence:

1. Send `$B\r`, read and discard two lines (flush).
2. Send `v\r`, the reply must start with `DrawCore`, e.g. `DrawCore V2.xx`. Second attempt on failure.
3. `?\r` (GRBL status). If the reply contains `Alarm`, `$X\r` is sent (clear alarm).

`command()` sends one line and blocks until a line starting with `ok` arrives (up to 100 read attempts of 1 s each). Anything else is logged as an error. `query()` reads one data line and then the `ok` line, except for `v`, `i`, `a`, `mr`, `pi`, `qm`. `query_all()` waits 1 s and reads everything available (for `$$` and `$RST`).

There is no send buffer and no character counting as in UGS or other GRBL senders: every line is sent and acknowledged individually.

## Firmware command set

Collected from all calls in the code. The firmware is a GRBL dialect with iDraw extensions (`$` commands with letters).

| Command | Purpose | Reply |
|---|---|---|
| `v` | version string (handshake) | `DrawCore Vx.xx` |
| `V` | version string (query) | `DrawCore Vx.xx` + `ok` |
| `?` | GRBL status report | e.g. `<Idle...>` or `Alarm` |
| `$X` | clear alarm | `ok` |
| `$H` | homing cycle | `ok` when done |
| `$SLP` | sleep, motors unpowered | `ok` |
| `$B` | query pause button | `0` or `1`, then `ok` |
| `$QP` | pen state (0 = down) | digit, then `ok` |
| `$QT` | read nickname | text, then `ok` |
| `$ST=<NAME>` | set nickname (max. 16 chars, uppercase) | `ok` |
| `$TP<up>,<down>` | toggle pen (defined in code, unused) | `ok` |
| `$1=255` / `$1=254` | step idle delay: hold motors permanently / release | `ok` |
| `$$` | all GRBL settings | multi-line |
| `$RST=*` | factory settings | multi-line |
| `G1G91X<mm>Y<mm>` | relative XY move with current F | `ok` |
| `G1G91X<mm>Y<mm>F<f>` | relative XY move with feed rate | `ok` |
| `G1 F<f>` | set feed rate only (modal) | `ok` |
| `G90 G1 F<f>` | absolute + feed rate | `ok` |
| `G1G90 Z<mm>F<f>` | pen to absolute height | `ok` |
| `G1 F<f> M3 S<0..1000>` | laser/PWM (power in per mille) | `ok` |
| `G4 P<s>` | dwell in seconds | `ok` |

All lines end with `\r`. Commented-out EBB commands (`SM`, `EM`, `SC`, `SL`, `QL`, `QC`, `SR`) come from the AxiDraw template and are no longer sent; the corresponding functions in `drawcore_motion.py` are empty shells (`sendEnableMotors`, `setPenUpPos`, `servo_timeout`, `queryVoltage` returns a fixed True).

## Coordinates and axes

Document coordinates in inches, origin top left, X to the right, Y down (after auto-rotate, see below). The conversion to G-code is nested in `motion.compute_segment()` and `drawcore_motion.doXYMove()` and still shows the CoreXY heritage of AxiDraw:

1. `compute_segment` calculates `motor_steps1 = step_scale·(dx+dy)`, `motor_steps2 = step_scale·(dx−dy)` in "native" steps (100 steps/mm at `resolution=1`).
2. `doXYMove(steps2, steps1)` converts back: `XSteps = −(steps2+steps1)/2 = −100·dx_mm`, `YSteps = (steps2−steps1)/2 = −100·dy_mm`.
3. It sends `G1G91 X{YSteps/100} Y{XSteps/100}`, i.e. **G-code X = −dy_mm, G-code Y = −dx_mm**.

The machine axes are swapped and negated relative to the document. This is consistent with `machine_origin` (`$H`, then a move by `y_bounds` along machine X) and with the walk commands (`go_to_position(−f_y, −f_x)`). For a new plugin this means: document (x, y) in mm becomes machine G-code `X = −y`, `Y = −x`; home (`$H`) is rear right, the document origin is front left after the move by `y_bounds`.

Auto-rotate: if the page is taller than wide, the digest is rotated by 90° (`auto_rotate_ccw`) so the long side lies along X.

`resolution=2` halves `step_scale` to 1270; since the firmware works in mm, this only changes the rounding of segment lengths.

## Pen control (pen_handling.py)

`PenHandler` manages the Z state (`phys.z_up`: None = unknown, True, False) and the XY position (`phys.xpos/ypos` in inches). `pen_raise()` skips if the pen is known to be up; `pen_lower()` skips only if `stopped`. Both send:

- `use_pwm_out = 0` (pen): `G1G90 Z<pos>F<rate>`, then `G1 F<speed_pendown|penup>` as the modal feed rate for the following XY moves.
- `use_pwm_out = 1` (laser): `G1 F<speed> M3 S<laser_power·10>` or `S0`.
- `use_pwm_out = 2`: both.

`servo_init()` calls `find_pen_state()`; there `$QP` is queried, but the result is only used if `queryEBBLV()` returns something other than 0, which never happens in the DrawCore code. In practice every process starts with an unknown pen state and always sends a Z move on the first `pen_raise()`. The timing calculation (`PenLiftTiming.update`) is commented out; `raise_time`/`lower_time` stay 0, so `pen_delay_up/down` have no effect anymore.

Layer heights (`+h`) go through `set_temp_height()` and take effect on the next `pen_lower()`.

## From SVG to motion

### 1. Digest (digest_svg.py, path_objects.py)

`DigestSVG.process_svg()` traverses the SVG (groups, paths, rect, circle, ellipse, line, polyline, polygon, use), resolves transforms, converts everything into cubic Bézier paths, flattens them with `curve_tolerance` (0.002 in) into polylines and stores them as `PathItem`s in `LayerItem`s of a `DocDigest`. Hidden layers, `%` layers, text and bitmaps are skipped; text and bitmaps produce warnings. Only objects with a stroke are plotted.

The digest can be written back into the document as a "Plob" (plot object, a reduced SVG of `<g>` with `<polyline>`) (`to_plob`) and read directly next time (`verify_plob`, `from_plob`). That is the `digest` option, not offered in Inkscape.

### 2. Clipping and optimization

`boundsclip.clip_at_bounds()` clips at machine and page bounds (`clip_to_page`). With `hiding=True`, `clipping.ClipPathsProcess` (pyclipper) runs instead for hidden-line removal based on fills; pyclipper is however missing in `idraw_deps/`, only `axidraw_deps/` has it.

`plot_optimizations.connect_nearby_ends()` joins path ends closer than `min_gap` (0.008 in). `supersample()` thins out points. `reorder()` (option `reordering` 1 or 2) sorts paths via a spatial grid for the shortest travel, with reversal at 2. `randomize_start()` shifts the start points of closed paths with a seed stored in `plotdata` (for resume).

### 3. Trajectory planning (motion.py)

`plot_polyline()` moves with the pen up to the first point (`go_to_position`), then `motion.trajectory()`: `['lower']`, a list of `['SM', (steps2, steps1, ms), seg_data]`, `['raise']`. `plan_trajectory()` is the AxiDraw planner: velocity per vertex from acceleration distance, corner angle (cornering factor) and a backward pass for deceleration. `compute_segment()` splits every segment into 25 ms time slices (`time_slice`) with a trapezoid, triangle or linear profile.

Important finding: the computed duration `move_time` is **not** transmitted to the firmware. `doXYMove` only sends the relative distance; the feed rate is the modal `F` from the last pen up/down. `move_time` only serves the `time.sleep(move_time − 30 ms)` in `dripfeed.feed_sm()`, so Python does not send faster than the machine moves (which can hardly happen anyway because of the blocking `ok` wait). The whole acceleration planning therefore only affects segmentation; the real acceleration is done by GRBL according to `$120/$121`. The `accel` option only influences segment length and the pauses.

In addition: speeds from the GUI (mm/min) are pushed into the planning as inch/s without conversion (`speed_lim_xy_hr / 110` with both values 110). The planner therefore works with absurdly high values, which pushes the trapezoid profile almost always into the case "trapezoid at full speed immediately". The result is still usable because GRBL handles the physics.

### 4. Feed (dripfeed.py)

`feed()` walks the move list, calls `pause_check()` before every move, and sends `lower`, `raise` or `SM`. In preview, times are summed instead of sending serial commands, and lines are collected in `preview.py`, rendered at the end as two layers (pen-up pink, pen-down blue) into the SVG.

## Pause and resume

`pause_check()` queries the pause button with `$B` at most every 50 ms (`button_interval`). Reply `1` sets `stopped = -102`, Ctrl-C `-103`, connection loss `-104`, layer pause (`!`) `-1`. On stop: pen up, make `stopped` positive, write `pause_dist` = pen-down distance so far into `plotdata`.

`<plotdata>` is a custom XML element directly under `<svg>` with `layer`, `pause_dist` and `pause_ref` (µm), `last_x/last_y` (mm), `rand_seed`, `row`, `model`, `plob_version`, `application`. On resume the digest is cropped to the pause distance with `crop(pause_dist)` and plotting continues from `last_x/last_y`. Without a saved SVG, resume after an Inkscape restart is not possible.

Since every Apply click is a new process, the software knows nothing about the machine position after an abort; it relies on `last_x/last_y` in the file.

## Layer name conventions (path_objects.LayerProperties)

Prefixes in the layer name control plotting:

| Pattern | Effect |
|---|---|
| `%Name` | documentation layer, never plotted |
| `!Name` | pause at the start of the layer |
| `5-red` | layer number 5, for the Layers tab |
| `+d500` | 500 ms delay at the start |
| `+h30` | pen-down height 30 for this layer (scale 0–100, does not match the mm scale of the GUI) |
| `+s60` | pen-down speed 60 (1–110, used as the feed rate number) |

Example: `!2+d1000+s40 blue` = pause, number 2, 1 s delay, speed 40.

## Multiple devices

`port_config=3` starts one thread with its own `iDraw` instance per DrawCore found; the "primary" device runs in the main thread and delivers the output SVG. Named devices are found via `$QT`, for which every port is opened briefly.

## Consequences for an interactive plugin

The Inkscape extension interface (.inx) is a static dialog: enter values, Apply, process runs, process ends. There is no feedback during runtime except stderr at the end, no buttons that react during the plot, and no persistent serial connection. UGS-style operation (jog buttons, live status, stop, home, test move, progress) is not possible within this mechanism.

What does work: the extension can start its own process with a GUI. Inkscape's Python ships `tkinter`, `pyserial` is bundled in `idraw_deps/serial`. An extension may open a Tk main loop and keep the port open for the lifetime of the window; Inkscape waits (blocked) meanwhile, or the window is started detached with `subprocess.Popen` and the extension returns immediately. Alternatively a standalone program outside Inkscape to which the extension only hands the SVG file.

Reusable building blocks: `drawcore_serial` (find port, handshake, `command`/`query`), `digest_svg` + `path_objects` + `plot_optimizations` (SVG to polylines, sorting), `boundsclip`. What can be dropped: `motion.py` with its time slices, because GRBL plans itself. A path is then one line `G1 X.. Y.. F..` per vertex in absolute coordinates (`G90`), plus `G1 Z..` for pen up/down. Standard GRBL techniques also fit: `?` polling for position and state (`<Idle|MPos:...>`), `!` (feed hold), `~` (resume), `Ctrl-X` (soft reset), `$J=` (jog). Whether DrawCore supports these realtime commands is not visible in the code and must be checked on the device. Only what is in the command table above is certain.

Decision of 2 September 2026: Stop takes effect after the current G-code line (pen up, position stays known). Feed hold and status query during a move are to be tested on the device before an immediate stop is built. Implementation in `extensions/idraw_core.py`, description in `README.md`.

## Oddities and dead code

`idraw_control.py` (family 1.0) imports `axidrawinternal`, which does not exist in `idraw_deps/`; the 1.0 extensions probably crash at start. `walk_home` does nothing. `sysinfo` prints nothing, since `versions.py` is fully commented out. `pen_delay_up/down` have no effect. `hiding` needs pyclipper, missing in the 2.0 dependency folder. The model help texts in `common_options.py` and `idraw2_0_conf.py` describe AxiDraw models, not iDraw. The servo constants, `servo_timeout`, `check_updates` and the webhook code are AxiDraw leftovers; only the webhook still works (POST with `value1..3` to `webhook_url`). The version in the .inx is "2.2.7-2026-06-20", the one in `idraw.py` "3.9.5 2023-12-06".

## Sources

The code in `extensions/` as installed from the UUNA TEK download (Inkscape extension package for iDraw 1.0 / 2.0 / H / H SE). Manufacturer pages consulted: [iDraw H series product page](https://idrawpenplotter.com/products/idraw-h-version-pen-plotter-a3-a1-a2) (DrawCore V2.0, "UUNA TEK 2.0 Control", GRBL compatible), [downloads page](https://idrawpenplotter.com/pages/downloads), [iDraw H A1 product page](https://uunatek.com/products/uuna-tek%C2%AE-idraw-h-a1-size-drawing-robot-drawing-machine-homework-machine-calligraphy-plotter-handwriting-robot-pen-plotter-laser-engraver). Third party: [Liz Melchor, iDraw H overview](https://lizmelchor.com/idraw-h/) (iDraw H uses iDraw Control 2.0), [PlotterBench](https://github.com/Future-Focus-Studio/plotterbench) (independent DrawCore driver: `G90`, `G92 X0 Y0`, `G1 X Y F`, `G1 Z F`, `G4`, `$QP`, `$SLP`; pauses only between strokes). No firmware documentation from the manufacturer was available; the command table is derived from the code.
