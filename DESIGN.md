---
version: alpha
name: iDraw Interactive
description: Workshop UI for a pen plotter. Tk today, web UI later. Calm, high contrast, no decoration.
omitted:
  - elevation
colors:
  ground: "#e8e8e8"
  paper: "#ffffff"
  ink: "#000000"
  ink-muted: "#444444"
  frame: "#333333"
  machine: "#999999"
  path-pending: "#99aabb"
  path-done: "#000000"
  pen-down: "#cc0000"
  pen-up: "#0066cc"
  origin: "#008800"
  status-error: "#cc0000"
typography:
  h1:
    fontFamily: System
    fontSize: 15pt
    fontWeight: bold
  h2:
    fontFamily: System
    fontSize: 12pt
    fontWeight: bold
  body:
    fontFamily: System
    fontSize: 13pt
  note:
    fontFamily: System
    fontSize: 13pt
    color: "{colors.ink-muted}"
  mono:
    fontFamily: Menlo
    fontSize: 10pt
rounded:
  none: 0px
spacing:
  xs: 2px
  sm: 4px
  md: 8px
  lg: 12px
  xl: 20px
components:
  step-bar:
    padding: "{spacing.md}"
    height: 40px
  content-column:
    width: 420px
    padding: "{spacing.md}"
  preview:
    backgroundColor: "{colors.ground}"
    padding: "{spacing.xl}"
  log:
    typography: "{typography.mono}"
    height: 6 lines
  jog-button:
    width: 4 chars
  primary-button:
    textColor: "{colors.ink}"
---

## Overview

The interface is a tool on the workbench, not a brand. It is operated next to a running plotter, often with one hand, sometimes from a tablet. Everything visible has a function: show state, trigger a command, show the result. There are no icons except the arrows for jogging, no illustrations, no animations.

The screen is split in two. On the left the active wizard step with text, fields and buttons in a fixed width. On the right the preview, filling the rest of the window and always visible, because it is the only feedback about what the machine is doing. Below, the log as plain text of what was sent.

## Colors

Grey as the ground (`ground`), the paper as the only white, strokes in black. Only three signal colors, each with exactly one meaning: red is pen down (ink flowing) and error; blue is pen up; green is the origin. Pending strokes in muted blue-grey (`path-pending`), plotted strokes in black, so progress is readable in the preview without a bar. The machine frame is dashed and light grey because it is context, not an object.

No gradients, no transparency, no hover colors. The active step in the bar is the pressed button, nothing more.

## Typography

System font in three sizes: step heading (`h1`), section within a step (`h2`), text and controls (`body`). Hints below fields in `note`, same size but muted. The log and everything that is G-code in `mono`. No small caps, no italics, no uppercase for emphasis. Labels are short nouns ("Up", "Down", "Home"), buttons are verbs or the target.

Measurements always carry the unit in the label, never in the value: "Drawing (mm/min)" and then `2000`.

## Layout

Window 1180 × 760 by default, the preview grows with it. Left column fixed at 420 px so text does not reflow when the window grows. Elements stack with `sm` to `md` spacing; related fields share one row. The jog cross is a 3×3 grid, step size beside it, not below. Spacing between sections `lg`, above an `h2` `lg`, below it `xs`.

Navigation always in the same place: Back and Next bottom left, Stop bottom right, reachable in every step. The step bar at the top is both progress indicator and jump target.

## Elevation & Depth

None. Everything sits on one plane. Dialogs (pause before a layer, errors) are the only elements above the window and come from the system.

## Shapes

Rectangles without rounding, as the platform provides them. The paper has a 1 px frame in `frame`, the machine frame is dashed (4 on, 3 off). The pen cross is 16 px, 2 px thick. The origin is a circle of 3 mm at preview scale.

## Components

Step bar: five numbered buttons, the active one pressed. To the right, position and pen state as text; far right, the status in bold.

Jog cross: four arrow buttons around a home button, radio buttons for the step beside it. Below, a `note` with the keyboard shortcuts.

Field with steppers: label, entry, buttons "−0.5" and "+0.5". Enter applies the value and executes it.

Layer list: one row per layer, two checkboxes (Plot, Pause before), then name and path count. No icons, no colors.

Progress: bar across the column width, below it "Path 143 / 812   42 %   remaining approx. 12:00 min".

Log: six lines of `mono`, read-only, scrolls along. Sent lines prefixed with "> ", replies after them, `ok` omitted.

## Do's and Don'ts

Every color has a meaning, so no color for decoration. Never red for a normal button. No text in the preview except the paper and machine labels in `machine` grey. No tooltips as a substitute for a clear label. No confirmation dialogs for reversible actions; only Stop and Pause may interrupt. Values that move the machine always carry a unit in the label. If a web variant is built: same colors, same five steps, same shortcuts, and buttons at least 44 px tall for a finger.
