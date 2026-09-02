"""
idraw_interactive.py

Inkscape entry point. Copies the document Inkscape hands over (a temp file that is
deleted when this script returns) next to the extension, starts idraw_server.py as a
detached process with the same Python, and returns immediately so Inkscape stays
usable. The server opens the browser. Nothing is written to stdout, so the SVG in
Inkscape is left unchanged.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

args = [a for a in sys.argv[1:] if not a.startswith("--")]
svg_in = args[-1] if args else None
svg = None
if svg_in and os.path.exists(svg_in):
    svg = os.path.join(HERE, "idraw_interactive_last.svg")
    shutil.copyfile(svg_in, svg)

cmd = [sys.executable, os.path.join(HERE, "idraw_server.py")]
if svg:
    cmd.append(svg)
if "--sim=true" in sys.argv:
    cmd.append("--sim")
if "--lan=true" in sys.argv:
    cmd.append("--lan")
subprocess.Popen(cmd, cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, start_new_session=True)
