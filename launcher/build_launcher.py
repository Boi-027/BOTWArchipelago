"""Builds dist/BotW AP Launcher.exe: one file with the launcher, the overlay tools, the world's data and the payload
(the Archipelago build of Savage Wind and botw.apworld). No game files go in: they are read from the player's own.

    botw_ap/.venv/Scripts/python launcher/build_launcher.py
"""
import ast
import glob
import os
import sys

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOLS = os.path.join(ROOT, "tools")

# the tools run with runpy, so PyInstaller can't see what they import: every module they name goes in by hand
mods = set()
for p in glob.glob(os.path.join(TOOLS, "*.py")):
    for node in ast.walk(ast.parse(open(p, encoding="utf8").read())):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            mods.add(node.module)

sep = os.pathsep
args = [os.path.join(HERE, "launcher.py"), "--name", "BotW AP Launcher", "--onefile", "--windowed", "--noconfirm",
        "--icon", os.path.join(HERE, "payload", "launcher.ico"),
        "--paths", HERE, "--paths", TOOLS,
        "--add-data", f"{TOOLS}{sep}tools",
        "--add-data", f"{os.path.join(ROOT, 'worlds', 'botw')}{sep}worlds/botw",
        "--add-data", f"{os.path.join(HERE, 'payload')}{sep}payload",
        "--collect-submodules", "evfl", "--collect-all", "oead",
        "--exclude-module", "__pycache__",
        "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(ROOT, "build", "launcher"),
        "--specpath", os.path.join(ROOT, "build")]
for m in sorted(mods):
    args += ["--hidden-import", m]
print("hidden imports:", ", ".join(sorted(mods)))
PyInstaller.__main__.run(args)
print("->", os.path.join(ROOT, "dist", "BotW AP Launcher.exe"))
sys.exit(0)
