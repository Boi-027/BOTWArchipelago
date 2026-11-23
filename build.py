"""Zips worlds/botw into botwsw.apworld (Savage Wind's Breath of the Wild: the package inside is botwsw, as
Archipelago wants it named like the file). Usage: python build.py [install folder, e.g. C:/ProgramData/Archipelago/custom_worlds]"""
import os
import sys
import zipfile

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, "worlds", "botw")
out = os.path.join(sys.argv[1] if len(sys.argv) > 1 else here, "botwsw.apworld")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            z.write(p, os.path.join("botwsw", os.path.relpath(p, src)))
print(out)
