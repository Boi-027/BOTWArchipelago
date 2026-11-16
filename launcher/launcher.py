"""Breath of the Wild x Archipelago - the launcher. Point it at a normal Savage Wind 0.5.3-alpha.5 folder (with your
game files set up by Savage Wind) and it does the rest: puts the Archipelago build of Savage Wind in place (the stock
exe is kept), builds the overlay from your own game files, turns it on, installs the apworld into Archipelago and,
if you like, a PopTracker pack - then fills in your server and slot and starts the game.

Run from source:  botw_ap/.venv/Scripts/python launcher/launcher.py
Build the .exe:   botw_ap/.venv/Scripts/python launcher/build_launcher.py
"""
import contextlib
import hashlib
import io
import json
import os
import runpy
import shutil
import sys

VERSION = "0.2.0"
SW_VERSION = "0.5.3-alpha.5"
STOCK_EXE_SHA = "d40806507ee635203740d9b62896d7989d9388db2bdc802f8d546967dc162749"  # (Savage Wind 0.5.3-alpha.5's)
REPO = "https://github.com/Boi-027/BOTWArchipelago"

# where the bundled files are: next to this script (from source) or unpacked by PyInstaller
if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # (botw_ap/)
TOOLS = os.path.join(BASE, "tools")
PAYLOAD = os.path.join(BASE, "launcher", "payload") if not getattr(sys, "frozen", False) else os.path.join(BASE, "payload")
CONFIG = os.environ.get("BOTW_AP_LAUNCHER_CONFIG") or \
    os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BotW AP Launcher", "config.json")

# ---- colours: dusk over Hyrule, Sheikah blue, Archipelago gold
BG, PANEL, PANEL2, LINE = "#121519", "#1a1f26", "#222a33", "#2e3742"
CREAM, MUTED, DIM = "#ece4cc", "#a9a28f", "#6f6a5e"
SHEIKAH, GOLD, GREEN, RED = "#4fd3e8", "#d9b44a", "#7ccf7a", "#e0735f"
AP_DOTS = ["#c65e5e", "#d98a3a", "#e3c34f", "#7bbf6a", "#5f9fd8", "#a77bd0"]


# ---------------------------------------------------------------- the setup itself
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_version(sw):
    try:
        for line in open(os.path.join(sw, "sw-manifest.txt"), encoding="utf8"):
            if line.startswith("version "):
                return line.split()[1]
    except OSError:
        pass
    return None


def patched_exe():
    return os.path.join(PAYLOAD, "savagewind.exe")


def patched_sha():
    p = os.path.join(PAYLOAD, "savagewind.exe.sha256")
    if os.path.exists(p):
        return open(p).read().strip()
    return sha256(patched_exe()) if os.path.exists(patched_exe()) else ""


def overlay_dir(sw):
    return os.path.join(sw, "ap_overlay")


def overlay_stamp(sw):
    return os.path.join(overlay_dir(sw), ".launcher-version")


def flag_line(sw):
    return "SAVAGEWIND_ROMFS_OVERLAY=" + overlay_dir(sw)


def read_flags(sw):
    p = os.path.join(sw, "launch-flags.txt")
    return open(p, encoding="utf8").read().splitlines() if os.path.exists(p) else []


def write_flags(sw, lines):
    with open(os.path.join(sw, "launch-flags.txt"), "w", encoding="utf8", newline="\n") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def default_archipelago():
    for p in (r"C:\ProgramData\Archipelago", os.path.expandvars(r"%LOCALAPPDATA%\Archipelago")):
        if os.path.isdir(os.path.join(p, "custom_worlds")) or os.path.exists(os.path.join(p, "ArchipelagoLauncher.exe")):
            return p
    return ""


def guess_sw():
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    for p in (here, os.path.dirname(here)):
        if os.path.exists(os.path.join(p, "savagewind.exe")):
            return p
    return ""


def status(cfg):
    """{step: (state, text)} - state: 'ok', 'todo', 'bad', 'off'"""
    sw, out = cfg.get("sw", ""), {}
    if not sw or not os.path.exists(os.path.join(sw, "savagewind.exe")):
        out["sw"] = ("bad", "Choose your Savage Wind folder (the one with savagewind.exe).")
        return out
    ver = manifest_version(sw)
    if ver != SW_VERSION:
        out["sw"] = ("bad", f"This launcher needs Savage Wind {SW_VERSION} (found {ver or 'an unknown version'}).")
        return out
    romfs = os.path.join(sw, "extracted", "romfs")
    if not os.path.isdir(romfs):
        out["sw"] = ("bad", "Start Savage Wind once and set up your game files first.")
        return out
    if not os.path.exists(os.path.join(sw, "extracted", "aoc1", "Pack", "AocMainField.pack")):
        out["sw"] = ("bad", "The Expansion Pass files are needed (add them in Savage Wind).")
        return out
    out["sw"] = ("ok", f"Savage Wind {ver}, game files ready.")
    exe = sha256(os.path.join(sw, "savagewind.exe"))
    if exe == patched_sha():
        out["exe"] = ("ok", "Installed. Your original is kept as savagewind.stock.exe.")
    elif exe == STOCK_EXE_SHA:
        out["exe"] = ("todo", "Stock Savage Wind: the Archipelago build goes in on Set up.")
    else:
        out["exe"] = ("todo", "Another savagewind.exe: kept, the Archipelago build goes in.")
    stamp = overlay_stamp(sw)
    have = open(stamp).read().strip() if os.path.exists(stamp) else ""
    out["overlay"] = ("ok", "Built from your game files.") if have == VERSION else \
        ("todo", "Built from your game files on Set up (a few minutes)." if not have else
         f"Made by launcher {have}: rebuilt for {VERSION} on Set up.")
    out["flags"] = ("ok", "Savage Wind loads the overlay.") if flag_line(sw) in read_flags(sw) else \
        ("todo", "Savage Wind will be told to load the overlay.")
    ap = cfg.get("archipelago", "")
    if ap and os.path.isdir(ap):
        dest = os.path.join(ap, "custom_worlds", "botw.apworld")
        same = os.path.exists(dest) and sha256(dest) == sha256(os.path.join(PAYLOAD, "botw.apworld"))
        out["apworld"] = ("ok", "Installed in Archipelago's custom_worlds.") if same else \
            ("todo", "Installed into Archipelago's custom_worlds on Set up.")
    else:
        out["apworld"] = ("off", "Optional: choose Archipelago's folder to install the world.")
    pt = cfg.get("poptracker", "")
    if pt and os.path.isdir(pt):
        out["poptracker"] = ("ok", "Pack installed.") if os.path.exists(os.path.join(pt, "packs", "BotW_AP.zip")) and \
            have == VERSION else ("todo", "A tracker pack is made from your game files on Set up.")
    else:
        out["poptracker"] = ("off", "Optional: choose PopTracker's folder for a map tracker.")
    return out


def run_tool(name, args, log):
    """one of the overlay tools, here in this process (they are scripts: run as __main__)"""
    log(f"  {name}")
    old_argv, old_path = sys.argv, list(sys.path)
    sys.argv = [name] + args
    sys.path.insert(0, TOOLS)
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            runpy.run_path(os.path.join(TOOLS, name), run_name="__main__")
    finally:
        sys.argv, sys.path[:] = old_argv, old_path
        for line in buf.getvalue().splitlines()[-3:]:
            log("    " + line)


def build_overlay(sw, log, step):
    ex, out = os.path.join(sw, "extracted"), overlay_dir(sw)
    romfs = os.path.join(ex, "romfs")
    if os.path.isdir(out):
        shutil.rmtree(out)
    logo = os.path.join(PAYLOAD, "archipelago.png")
    tools = [("title_overlay.py", [romfs, out, VERSION]), ("ap_item.py", [romfs, out, logo]),
             ("strip_rewards.py", [ex, out]), ("shop_sanity.py", [ex, out]), ("rune_items.py", [romfs, out]),
             ("quest_rewards.py", [ex, out]), ("give_trigger.py", [ex, out]), ("quest_log.py", [ex, out]),
             ("logo_overlay.py", [romfs, out])]  # (tools/build_overlay.py's order)
    for i, (name, args) in enumerate(tools):
        step(i / len(tools))
        run_tool(name, args, log)
    with open(overlay_stamp(sw), "w") as f:
        f.write(VERSION)


def setup(cfg, log, step):
    sw = cfg["sw"]
    st = status(cfg)
    if st["sw"][0] != "ok":
        raise RuntimeError(st["sw"][1])
    if st["exe"][0] != "ok":
        log("Putting the Archipelago build of Savage Wind in place")
        exe, keep = os.path.join(sw, "savagewind.exe"), os.path.join(sw, "savagewind.stock.exe")
        if not os.path.exists(keep):
            shutil.copy2(exe, keep)
        shutil.copy2(patched_exe(), exe)
    if st["overlay"][0] != "ok":
        log("Building the overlay from your game files")
        build_overlay(sw, log, lambda f: step(0.05 + 0.75 * f))
    step(0.82)
    if st["flags"][0] != "ok":
        log("Turning the overlay on (launch-flags.txt)")
        lines = [l for l in read_flags(sw) if not l.startswith("SAVAGEWIND_ROMFS_OVERLAY=")]
        write_flags(sw, lines + [flag_line(sw)])
    if st["apworld"][0] == "todo":
        log("Installing botw.apworld into Archipelago")
        dest = os.path.join(cfg["archipelago"], "custom_worlds")
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(os.path.join(PAYLOAD, "botw.apworld"), dest)
    step(0.88)
    if st["poptracker"][0] == "todo":
        log("Making the PopTracker pack")
        out = os.path.join(sw, "ap_poptracker")
        run_tool("poptracker.py", [os.path.join(sw, "extracted"), out], log)
        os.makedirs(os.path.join(cfg["poptracker"], "packs"), exist_ok=True)
        shutil.copy2(os.path.join(out, "BotW_AP.zip"), os.path.join(cfg["poptracker"], "packs", "BotW_AP.zip"))
    step(1)
    log("All set.")


def restore(cfg, log):
    sw = cfg["sw"]
    keep = os.path.join(sw, "savagewind.stock.exe")
    if os.path.exists(keep):
        shutil.copy2(keep, os.path.join(sw, "savagewind.exe"))
        log("Your original savagewind.exe is back.")
    write_flags(sw, [l for l in read_flags(sw) if not l.startswith("SAVAGEWIND_ROMFS_OVERLAY=")])
    log("The overlay is off (its folder is left in place).")


def read_ini(sw):
    p = os.path.join(sw, "savagewind.ini")
    vals = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf8", errors="replace"):
            if "=" in line and not line.lstrip().startswith(("#", ";", "[")):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals


def write_ini(sw, values):
    """the ap_* keys set, every other line of savagewind.ini kept"""
    p = os.path.join(sw, "savagewind.ini")
    lines = open(p, encoding="utf8", errors="replace").read().splitlines() if os.path.exists(p) else []
    done = set()
    for i, line in enumerate(lines):
        k = line.split("=", 1)[0].strip() if "=" in line else None
        if k in values:
            lines[i] = f"{k} = {values[k]}"
            done.add(k)
    lines += [f"{k} = {v}" for k, v in values.items() if k not in done]
    with open(p, "w", encoding="utf8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ui import App  # (the window: launcher/ui.py)
    app = App()
    if "--setup" in sys.argv:  # (Set up pressed as soon as the window is up: unattended installs)
        app.after(1000, app.do_setup)
    app.mainloop()
