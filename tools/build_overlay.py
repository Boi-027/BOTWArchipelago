"""The whole RomFS overlay for Archipelago, from your own game files: the title screen's version line and "ARCHIPELAGO"
under the logo on the title and loading screens (logo_overlay.py, needs Pillow), the Archipelago
Item, a saved flag for every shop slot (shop_sanity.py), the runes' item-get pictures and words (rune_items.py), every check's normal reward replaced by the Archipelago
Item (quest rewards and the runes: quest_rewards.py), and the trigger that hands received items to Link with the game's
item-get scene (give_trigger.py: needs oead and evfl, from botw_ap/.venv), and the quest log's Archipelago Hints and Goal
(quest_log.py), and the map tracker's icons (map_icons.py). Savage Wind loads it with the launch option
SAVAGEWIND_ROMFS_OVERLAY=<Savage Wind folder>/ap_overlay. It holds changed game files: for your machine only.

    python -I tools/build_overlay.py "<Savage Wind folder>" [<Archipelago folder>]
"""
import os
import shutil
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
sw = sys.argv[1]
ap = sys.argv[2] if len(sys.argv) > 2 else r"C:\ProgramData\Archipelago"
ex, out = os.path.join(sw, "extracted"), os.path.join(sw, "ap_overlay")
if os.path.isdir(out):
    shutil.rmtree(out)  # (only ever our own output)
for script, args in (("title_overlay.py", [os.path.join(ex, "romfs"), out, "0.4.7"]),
                     ("ap_item.py", [os.path.join(ex, "romfs"), out, os.path.join(ap, "data", "icon.png")]),
                     ("strip_rewards.py", [ex, out])):
    subprocess.run([sys.executable, "-I", os.path.join(here, script)] + args, check=True)
venv = os.path.join(here, "..", ".venv", "Scripts", "python.exe")
for script, args in (("shop_sanity.py", [ex, out]), ("rune_items.py", [os.path.join(ex, "romfs"), out]),
                     ("quest_rewards.py", [ex, out]), ("give_trigger.py", [ex, out]), ("quest_log.py", [ex, out]),
                     ("map_icons.py", [ex, out]), ("logo_overlay.py", [os.path.join(ex, "romfs"), out])):  # (last: it adds to Bootup.pack too)
    subprocess.run([venv if os.path.exists(venv) else sys.executable, "-I", os.path.join(here, script)] + args,
                   check=True)
print("overlay ready:", out)
