---
version: alpha
name: iDraw Interactive
description: Material Design 3 components on the drafting palette (light panel, ink black, white controls) around a drafting board that stays a drafting board.
omitted:
  - elevation-levels-4-5
colors:
  primary: "#1B1B1B"
  on-primary: "#FFFFFF"
  primary-container: "#E2E4DD"
  secondary-container: "#E2E4DD"
  on-secondary-container: "#1B1B1B"
  tertiary: "#1F5FBF"
  error: "#C8102E"
  on-error: "#FFFFFF"
  error-container: "#F7D6DA"
  amber: "#C98A00"
  surface: "#ECEDE8"
  on-surface: "#1B1B1B"
  on-surface-variant: "#5C5F58"
  surface-container-lowest: "#FFFFFF"
  surface-container-low: "#ECEDE8"
  surface-container: "#E2E4DD"
  surface-container-high: "#FFFFFF"
  surface-container-highest: "#D6D9D0"
  outline: "#C9CCC3"
  outline-variant: "#D8DBD3"
  mat: "#2E5C4C"
  paper: "#FFFFFF"
  ink: "#1B1B1B"
  ink-faint: "#B8BDB5"
  pen-down: "#C8102E"
  pen-up: "#1F5FBF"
  origin: "#C98A00"
typography:
  headline-medium:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 28px
    lineHeight: 36px
    fontWeight: 400
  title-large:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 22px
    lineHeight: 28px
    fontWeight: 400
  title-small:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 14px
    lineHeight: 20px
    fontWeight: 500
    letterSpacing: 0.1px
  body-medium:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 14px
    lineHeight: 20px
    letterSpacing: 0.25px
  body-small:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 12px
    lineHeight: 16px
    letterSpacing: 0.4px
  label-large:
    fontFamily: Roboto, system-ui, sans-serif
    fontSize: 14px
    lineHeight: 20px
    fontWeight: 500
    letterSpacing: 0.1px
  data:
    fontFamily: Roboto Mono, Menlo, monospace
    fontSize: 14px
  log:
    fontFamily: Roboto Mono, Menlo, monospace
    fontSize: 12px
    lineHeight: 18px
  drafting:
    fontFamily: Barlow, system-ui, sans-serif
    fontSize: 2.6mm
  drafting-mono:
    fontFamily: IBM Plex Mono, Menlo, monospace
    fontSize: 2.6mm
rounded:
  none: 0px
  extra-small: 4px
  small: 8px
  medium: 12px
  large: 16px
  extra-large: 28px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
components:
  top-app-bar:
    height: 56px
    backgroundColor: "{colors.surface}"
    typography: "{typography.title-large}"
  side-sheet:
    width: 440-520px
    backgroundColor: "{colors.surface-container-low}"
    padding: "{spacing.xl} {spacing.lg}"
  primary-tabs:
    height: 44px, top of the side column
    indicator: 3px "{colors.primary}", rounded top
  button-filled:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    height: 40px
    rounded: "{rounded.full}"
    padding: "0 {spacing.xl}"
  button-tonal:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
  button-outlined:
    borderColor: "{colors.outline}"
    textColor: "{colors.primary}"
  button-error:
    backgroundColor: "{colors.error}"
  icon-button:
    size: 48px
    rounded: "{rounded.full}"
  segmented-button:
    height: 40px
    selectedBackground: "{colors.secondary-container}"
    borderColor: "{colors.outline}"
  text-field-outlined:
    height: 56px
    rounded: "{rounded.extra-small}"
    borderColor: "{colors.outline}"
    focusBorder: 2px "{colors.primary}"
  status-chip:
    height: 32px
    rounded: "{rounded.small}"
  dialog:
    backgroundColor: "{colors.surface-container-high}"
    rounded: "{rounded.extra-large}"
    padding: "{spacing.xl}"
  linear-progress:
    height: 4px
    color: "{colors.primary}"
  board:
    backgroundColor: "{colors.mat}"
    grid: 10mm minor, 50mm major
  title-block:
    width: 72mm
    height: 21mm
  log:
    typography: "{typography.log}"
    height: remaining column below the board (board takes 70 %)
    backgroundColor: "{colors.surface-container-low}"
---

## Overview

Two worlds meet on one screen and are kept deliberately distinct. The tool chrome (app bar, step tabs, forms, dialog, log) follows Material Design 3 so it behaves like every other app the operator uses on a Mac or an iPad: familiar buttons, text fields with floating labels, a pause dialog with the expected corner radius. The work surface (the board) stays a drafting table: a green cutting mat with a millimetre grid, a white sheet, rulers, and a title block drawn where a draughtsman writes it. The chrome uses the drafting palette (light neutral panel, ink black, white controls), so both halves read as one workbench.

The page has one job: get a drawing from Inkscape onto paper correctly, then watch it plot. The five steps are a real sequence, so they are numbered primary tabs.

## Colors

The palette is the drafting palette, mapped onto M3 colour roles rather than generated from a seed: primary is ink black, so the one filled button per step, the active tab indicator, selected segments and the progress bar are black on the light neutral panel. Controls are white with a light outline. Surface containers are neutral greys (`#ECEDE8`, `#E2E4DD`), the dialog is white.

Three signal colours with one meaning each: error red for pen down and Stop, blue (tertiary) for pen up, amber for paused, notices and the origin. Green is never a status; the mat is green. Single light scheme by choice; the sheet is physical and does not change with the system theme.

Board colours stay outside the roles: pending strokes in `ink-faint`, plotted strokes in `ink`, pen cross red when down and blue when up.

## Typography

Roboto in the M3 type scale for the chrome: headline-medium for the step title, title-large for the app name, label-medium uppercase for section labels (muted), body-medium for guidance, label-large in every button. Roboto Mono for every number the machine will receive: coordinates in the app bar, tab numbers, jog step sizes, numeric text fields, the log. On the board the drafting faces remain (Barlow and IBM Plex Mono in millimetre sizes) because the board is a drawing, not a UI.

## Layout

Top app bar 56 px with the name on the left and, on the right, the status chip, the position readout, the pen state and a segmented unit switch (mm, cm, in). Below it the height is split: the board on the left takes all remaining width (70 % of the column, the log below it takes the rest), the side column on the right is 440 to 520 px wide. The side column is one unit: the five step tabs at its top, the step panel with the step's groups stacked, and Back, Next, Stop as its footer. The Sheet/Machine view toggle floats in the board's top-right corner; a corner button (◰ ◳ ◲ ◱) in the top-left cycles the title block through the four sheet corners and remembers the choice in the browser. Below it a vertical zoom slider snaps to 0.5× to 8× of the fitted view; above 1× the board can be dragged to pan, a double-click resets zoom and pan. With a 1280 px window the board is about 760 px wide, close to the aspect of a landscape sheet, so the sheet fills it. Every step fits the panel without scrolling at 1280 × 690 CSS px.

The board's view fits the sheet by default (rulers and a thin mat margin around it); the Machine toggle zooms out to the whole travel range. All board labels (rulers, title block, machine label, pen cross) are sized in screen pixels and converted to millimetres at render time, so they stay legible at every zoom.

Under 900 px the layout stacks: board first at 60 vw height, then the step panel, then the log, and every button grows to 44 px.

## Elevation & Depth

M3 level 1 on cards and on hovered filled buttons, level 3 on the dialog. The side sheet and bars are flat, separated by outline-variant hairlines and container tones. The board has no elevation; it is the table.

## Shapes

M3 shape scale: buttons and chips full, text fields extra-small (4 px), status chip and hints small (8 px), cards and the notice medium (12 px), dialog extra-large (28 px). Segmented controls are full on their outer ends only. The board keeps right angles: the sheet, the machine frame, the title block.

## Components

App bar: name, status chip whose container follows the state (ink outline when ready, ink fill when moving or plotting, amber when paused, error container on error), position in Roboto Mono, pen state coloured, unit segmented buttons with the M3 check mark on the selection.

Primary tabs: five, numbered, active one in primary with a 3 px indicator; a tick after the number when the step's physical result is verified.

Text fields: outlined, 56 px, label floating in the outline, unit as a suffix; selects share the same outline. Buttons: filled (ink) for the one main action of a step, white outlined for everything else, text for dialog actions, error for Stop. Icon buttons for jogging.

Segmented buttons: unit switch, jog step, placement. Checkboxes and radios use the platform control tinted with primary.

Dialog: pause before a layer, headline, body, text Stop and filled Continue.

Linear progress: 4 px track in surface-container-highest, primary indicator, with a monospace readout below.

Board: unchanged from the drafting design: mat, machine frame, sheet, rulers in the current unit, strokes at the measured line width, pen cross, origin, title block.

## Do's and Don'ts

Follow M3 for anything a person touches; keep the board as a drawing. One filled button per step. Error colour only for Stop and pen-down. No custom shapes inside the chrome, no drop shadows on the board. Labels name what happens ("Set origin here", "Trace paper frame, pen up"). Units live in the field suffix or the label, never in the value. Motion is limited to state-layer opacity, the progress indicator, and strokes appearing on the sheet.
