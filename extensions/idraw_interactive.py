"""
idraw_interactive.py

Inkscape entry point: starts the Tk wizard with the current document.
The SVG is not modified, so nothing is written to stdout.

Known problem: Inkscape's bundled Python ships Tk 8.5, which draws an empty window on
macOS 26. Workaround candidates: launch the GUI with the system Python via subprocess,
or replace Tk with a web UI. See README "Status".
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import idraw_interactive_gui

args = [a for a in sys.argv[1:] if not a.startswith("--")]
sim = "--sim=true" in sys.argv
svg = args[-1] if args else None
idraw_interactive_gui.main(["idraw_interactive", svg or "", "--sim"] if sim else ["idraw_interactive", svg or ""])
