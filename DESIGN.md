---
version: alpha
name: iDraw Interactive
description: Material Design 3 chrome, seeded from the cutting-mat green, around a drafting board that stays a drafting board.
omitted:
  - elevation-levels-4-5
colors:
  primary: "#276A55"
  on-primary: "#FFFFFF"
  primary-container: "#ABF2D6"
  on-primary-container: "#002114"
  secondary: "#4C6359"
  secondary-container: "#CEE9DB"
  on-secondary-container: "#092017"
  tertiary: "#3E6373"
  tertiary-container: "#C1E8FB"
  on-tertiary-container: "#001F2A"
  error: "#BA1A1A"
  error-container: "#FFDAD6"
  on-error-container: "#410002"
  surface: "#F5FBF5"
  on-surface: "#171D1A"
  surface-variant: "#DBE5DE"
  on-surface-variant: "#404944"
  surface-container-lowest: "#FFFFFF"
  surface-container-low: "#EFF5EF"
  surface-container: "#E9EFEA"
  surface-container-high: "#E3EAE4"
  surface-container-highest: "#DDE4DE"
  outline: "#707973"
  outline-variant: "#BFC9C2"
  dark-primary: "#8FD5BB"
  dark-on-primary: "#003828"
  dark-secondary-container: "#354B41"
  dark-tertiary: "#A6CCDF"
  dark-error: "#FFB4AB"
  dark-surface: "#0F1512"
  dark-on-surface: "#DEE4DF"
  dark-surface-container-low: "#171D1A"
  dark-surface-container-high: "#252B28"
  dark-outline: "#89938C"
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
    height: 64px
    backgroundColor: "{colors.surface}"
    typography: "{typography.title-large}"
  side-sheet:
    width: 380px
    backgroundColor: "{colors.surface-container-low}"
    padding: "{spacing.xl} {spacing.lg}"
  primary-tabs:
    height: 64px
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
    height: 104px
    backgroundColor: "{colors.surface-container-low}"
---

## Overview

Two worlds meet on one screen and are kept deliberately distinct. The tool chrome (app bar, step tabs, forms, dialog, log) follows Material Design 3 so it behaves like every other app the operator uses on a Mac or an iPad: familiar buttons, text fields with floating labels, a pause dialog with the expected corner radius. The work surface (the board) stays a drafting table: a green cutting mat with a millimetre grid, a white sheet, rulers, and a title block drawn where a draughtsman writes it. The M3 colour scheme is seeded from that mat green, which is what ties the two together.

The page has one job: get a drawing from Inkscape onto paper correctly, then watch it plot. The five steps are a real sequence, so they are numbered primary tabs.

## Colors

The scheme is M3 tonal, seed `#2E5C4C`. Primary carries the main action of each step (filled button), the active tab indicator, and progress. Secondary container carries tonal buttons and the selected segment of segmented controls. Tertiary is reserved for the pen-up state and the paused chip. Error is Stop and the pen-down state, because ink flowing and stopping are the two things that must never be missed. Surface containers build the side sheet (low), the top bar (surface), the bottom bar (container) and the dialog (high).

Dark scheme follows the system setting with the corresponding M3 dark tones; the board keeps its mat and white sheet in both, because the paper is physical and does not change with the theme.

Board colours are outside the M3 scheme on purpose: pending strokes in `ink-faint`, plotted strokes in `ink`, pen cross red when down and blue when up, origin amber.

## Typography

Roboto in the M3 type scale for the chrome: headline-medium for the step title, title-large for the app name, title-small for section labels (in primary colour), body-medium for guidance, label-large in every button. Roboto Mono for every number the machine will receive: coordinates in the app bar, tab numbers, jog step sizes, numeric text fields, the log. On the board the drafting faces remain (Barlow and IBM Plex Mono in millimetre sizes) because the board is a drawing, not a UI.

## Layout

Top app bar 64 px with the name on the left and, on the right, the status chip, the position readout, the pen state and a segmented unit switch (mm, cm, in). Below it a 380 px side sheet with the five tabs and the active step, and the board filling the rest. The log and the bottom bar (Back, Next, Stop) sit under the board. Rows inside a step are flex rows with 8 px gaps; a numeric field is 110 px wide with its unit as a suffix inside the field. The jog cross is 3×3 icon buttons of 48 px with a vertical segmented step selector beside it.

Under 900 px the layout stacks: board first, then the step, then the log, and every button grows to 44 px.

## Elevation & Depth

M3 level 1 on cards and on hovered filled buttons, level 3 on the dialog. The side sheet and bars are flat, separated by outline-variant hairlines and container tones. The board has no elevation; it is the table.

## Shapes

M3 shape scale: buttons and chips full, text fields extra-small (4 px), status chip and hints small (8 px), cards and the notice medium (12 px), dialog extra-large (28 px). Segmented controls are full on their outer ends only. The board keeps right angles: the sheet, the machine frame, the title block.

## Components

App bar: name, status chip whose container follows the state (secondary container when ready, primary when moving or plotting, tertiary container when paused, error container on error), position in Roboto Mono, pen state coloured, unit segmented buttons with the M3 check mark on the selection.

Primary tabs: five, numbered, active one in primary with a 3 px indicator; a tick after the number when the step's physical result is verified.

Text fields: outlined, 56 px, label floating in the outline, unit as a suffix; selects share the same outline. Buttons: filled for the one main action of a step, tonal for machine actions (pen up/down, tests, trace), outlined for secondary actions, text for dialog actions, error for Stop. Icon buttons for jogging.

Segmented buttons: unit switch, jog step, placement. Checkboxes and radios use the platform control tinted with primary.

Dialog: pause before a layer, headline, body, text Stop and filled Continue.

Linear progress: 4 px track in surface-container-highest, primary indicator, with a monospace readout below.

Board: unchanged from the drafting design: mat, machine frame, sheet, rulers in the current unit, strokes at the measured line width, pen cross, origin, title block.

## Do's and Don'ts

Follow M3 for anything a person touches; keep the board as a drawing. One filled button per step. Error colour only for Stop and pen-down. No custom shapes inside the chrome, no drop shadows on the board. Labels name what happens ("Set origin here", "Trace paper frame, pen up"). Units live in the field suffix or the label, never in the value. Motion is limited to state-layer opacity, the progress indicator, and strokes appearing on the sheet.
