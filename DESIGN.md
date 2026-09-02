---
version: alpha
name: iDraw Interactive
description: A drafting workbench for a pen plotter. Cutting mat, white sheet, technical lettering, one title block.
omitted:
  - elevation
colors:
  mat: "#2E5C4C"
  mat-line: "rgba(255,255,255,0.09)"
  mat-line-strong: "rgba(255,255,255,0.16)"
  paper: "#FFFFFF"
  ink: "#1B1B1B"
  ink-muted: "#5C5F58"
  ink-faint: "#B8BDB5"
  panel: "#ECEDE8"
  panel-2: "#E2E4DD"
  line: "#C9CCC3"
  red: "#C8102E"
  blue: "#1F5FBF"
  amber: "#C98A00"
typography:
  display:
    fontFamily: Barlow, system-ui, sans-serif
    fontSize: 22px
    fontWeight: 600
    letterSpacing: -0.01em
  section:
    fontFamily: Barlow, system-ui, sans-serif
    fontSize: 13px
    fontWeight: 600
    letterSpacing: 0.08em
    textTransform: uppercase
    color: "{colors.ink-muted}"
  body:
    fontFamily: Barlow, system-ui, sans-serif
    fontSize: 15px
    lineHeight: 1.4
  data:
    fontFamily: IBM Plex Mono, Menlo, monospace
    fontSize: 14px
  log:
    fontFamily: IBM Plex Mono, Menlo, monospace
    fontSize: 12px
    lineHeight: 1.5
  title-block-key:
    fontFamily: Barlow, system-ui, sans-serif
    fontSize: 2.1mm
    letterSpacing: 0.1mm
    color: "{colors.ink-muted}"
  title-block-value:
    fontFamily: IBM Plex Mono, Menlo, monospace
    fontSize: 2.6mm
rounded:
  none: 0px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 20px
components:
  top-bar:
    height: 48px
    backgroundColor: "{colors.panel}"
    padding: "0 {spacing.lg}"
  side-column:
    width: 360px
    backgroundColor: "{colors.panel}"
    padding: "{spacing.lg}"
  step-tab:
    typography: "{typography.data}"
    height: 52px
  board:
    backgroundColor: "{colors.mat}"
    grid: 10mm minor, 50mm major
  button:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    height: 38px
    rounded: "{rounded.none}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.paper}"
  button-danger:
    backgroundColor: "{colors.red}"
    textColor: "{colors.paper}"
  jog-button:
    size: 44px
  title-block:
    width: 72mm
    height: 21mm
    backgroundColor: "{colors.paper}"
    borderColor: "{colors.ink}"
  log:
    typography: "{typography.log}"
    height: 96px
    backgroundColor: "{colors.paper}"
---

## Overview

The subject is a pen plotter, which is a drawing instrument, so the interface borrows its language from the drafting table rather than from software dashboards: a green self-healing cutting mat as the ground, one white sheet on it, rulers along the sheet's edges, DIN-style lettering, and a title block in the corner of the sheet as on a technical drawing. The audience is one person at the workbench, sometimes operating from a tablet propped next to the machine. The page has one job: get a drawing from Inkscape onto paper correctly, then watch it plot.

Two areas. The side column carries the five steps and the active step's controls; it is the only place with forms. The board carries the mat, the sheet, the drawing and the pen, and is the only feedback about what the machine does. The log below the board shows the exact lines sent to the firmware.

## Colors

The mat green `mat` is the ground and the only saturated surface; it is context, so the machine frame and rulers on it are drawn in translucent white, never in ink. The sheet is the only pure white. Ink `ink` is for everything that has been drawn or is text. Pending strokes are `ink-faint` on the sheet so progress reads directly from the drawing without a bar.

Three signal colors with exactly one meaning each: `red` is pen down (ink flowing) and Stop; `blue` is pen up; `amber` is a pause or an origin that needs attention. Green is never a status, because the mat is green. No gradients, no shadows, no hover tints beyond the panel grey. Buttons are white on the panel; the primary action of a step is inverted (ink on white becomes white on ink).

## Typography

Barlow, a DIN-derived grotesk, is the lettering of technical drawings and carries all labels, headings and prose. IBM Plex Mono carries every number that means something to the machine: coordinates, feed rates, Z heights, the step numbers, the log, and the values in the title block. The rule: if the value could be typed into the firmware, it is monospaced.

Display size is used once per step for its name. Section labels are small uppercase with wide tracking, the only place tracking is used. No italics, no bold for emphasis in prose. Units always sit in the label or after the field, never inside the value.

## Layout

Desktop: a 360 px side column and a board that takes the rest, with the log under the board. The five steps are tabs across the top of the column, numbered because they are a sequence; a tick marks a step whose physical outcome is verified (connected and homed, origin set). Controls stack in rows with `sm` gaps; a row is a label, a field, a unit. The jog cross is a 3×3 grid of 44 px buttons with step sizes beside it.

Tablet and phone: one column with the board first at 56 vw height, then the step, then the log. All buttons grow to 44 px for touch.

## Elevation & Depth

None. Everything is on one plane, as on a table. The pause dialog is the only element above the page, with an amber top rule.

## Shapes

Right angles everywhere; the platform's rounded corners are removed. Lines are 1 px in `line`. On the board, geometry is drawn in millimetres: the sheet has a 0.4 mm frame, the machine frame is dashed 4 on 3 off, the pen is a 3.2 mm circle with a cross, the origin a 2 mm amber circle. Strokes are drawn at the measured line width of the pen profile, so the preview looks like the plot will.

## Components

Top bar: brand, then status as a small uppercase chip whose fill changes with state (inverted while moving or plotting, amber when paused, red on error), the position in monospace, the pen state in its signal color, and the unit switch mm / cm / in as a segmented control.

Step tabs: five equal cells, the active one white. Content panel: heading, one line of guidance, then rows.

Jog cross: arrows around a home glyph, step sizes in the current unit as small monospace buttons, one line of keyboard hints in `kbd` styling.

Layer table: three columns, Plot, Pause before, Layer with its path count in monospace.

Board: mat with 10 mm grid and stronger 50 mm grid, machine frame when known, sheet with rulers along top and left in the current unit, strokes, pen, origin, title block.

Title block: the signature. A 72 × 21 mm box in the sheet's lower right corner, split by a vertical rule into keys (SHEET, SCALE, PEN, FEED, FILE) and monospace values. It is the live summary of every setting the plot depends on, drawn where a draughtsman would write it.

Log: 96 px of monospace, sent lines prefixed with "> ", replies after them, "ok" omitted, errors prefixed with "! ".

## Do's and Don'ts

Keep the mat free of text except the machine label and ruler numbers. Never put a status in green. Never round a corner. Every number the machine will receive is monospaced; every number the person reads casually is not. A button says what happens ("Set origin here", "Trace paper frame, pen up"), not what the system does. Errors say what went wrong and what to do, in the interface's voice. Motion is limited to the strokes appearing on the sheet as they are plotted and the progress bar filling; nothing else moves. If a control needs a tooltip to be understood, rewrite its label instead.
