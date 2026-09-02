"""
idraw_interactive.py

Inkscape-Einstieg: startet den Tk-Wizard mit dem aktuellen Dokument.
Das SVG wird nicht verändert; darum keine Ausgabe auf stdout.
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
