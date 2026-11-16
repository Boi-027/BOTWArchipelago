"""Breath of the Wild x Archipelago - the launcher. Point it at a normal Savage Wind folder (with your game files set up
by Savage Wind) and it does the rest: puts the Archipelago build of Savage Wind in place (the stock exe is kept),
builds the overlay from your own game files, turns it on, installs the apworld into Archipelago and, if you like, a
PopTracker pack - then fills in your server and slot and starts the game. Savage Wind updates go through it too: its
own updater, then the Archipelago build of the new version (from this project's releases).

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
import subprocess
import sys
import tempfile
import time
import urllib.request

VERSION = "0.4.2"
REPO = "https://github.com/Boi-027/BOTWArchipelago"
RELEASES_API = "https://api.github.com/repos/Boi-027/BOTWArchipelago/releases?per_page=30"

# where the bundled files are: next to this script (from source) or unpacked by PyInstaller
if getattr(sys, "frozen", False):
    BASE = sys._MEIPASS
else:
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # (botw_ap/)
TOOLS = os.path.join(BASE, "tools")
PAYLOAD = os.path.join(BASE, "launcher", "payload") if not getattr(sys, "frozen", False) else os.path.join(BASE, "payload")
CONFIG = os.environ.get("BOTW_AP_LAUNCHER_CONFIG") or \
    os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BotW AP Launcher", "config.json")
BUILDS = os.path.join(os.path.dirname(CONFIG), "builds")  # (the Archipelago builds fetched for other versions)

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


def manifest_sha(sw, name):
    """the stock file's sha256, as the version's own sw-manifest.txt lists it ("f <sha256> <size> <name>")"""
    try:
        for line in open(os.path.join(sw, "sw-manifest.txt"), encoding="utf8"):
            parts = line.rstrip("\n").split(" ", 3)
            if len(parts) == 4 and parts[0] == "f" and parts[3] == name:
                return parts[1]
    except OSError:
        pass
    return ""


# ---- the Archipelago build of savagewind.exe: one for each Savage Wind version - the one in the payload (its version in
# savagewind.exe.version), or fetched from this project's releases (savagewind-ap-<version>.exe and its .sha256)
def bundled_version():
    p = os.path.join(PAYLOAD, "savagewind.exe.version")
    return open(p).read().strip() if os.path.exists(p) else ""


def ap_build(ver):
    """(exe, sha256) of the Archipelago build for Savage Wind <ver> here, or (None, "")"""
    if ver and ver == bundled_version():
        p = os.path.join(PAYLOAD, "savagewind.exe")
        s = os.path.join(PAYLOAD, "savagewind.exe.sha256")
        return p, (open(s).read().strip() if os.path.exists(s) else sha256(p))
    p = os.path.join(BUILDS, ver or "-", "savagewind.exe")
    s = p + ".sha256"
    if os.path.exists(p) and os.path.exists(s) and sha256(p) == open(s).read().strip():
        return p, open(s).read().strip()
    return None, ""


def _get(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "BotW-AP-Launcher", "Accept": accept})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def fetch_ap_build(ver, log):
    """the Archipelago build for Savage Wind <ver> from this project's releases, checked; False: there is none (yet)"""
    if ap_build(ver)[0]:
        return True
    name = f"savagewind-ap-{ver}.exe"
    try:
        releases = json.loads(_get(RELEASES_API))
    except OSError as e:
        log(f"Can't reach GitHub for the Archipelago build ({e})")
        return False
    assets = {a["name"]: a for r in releases for a in r.get("assets", [])}
    if name not in assets or name + ".sha256" not in assets:
        log(f"No Archipelago build for Savage Wind {ver} yet.")
        return False
    log(f"Downloading the Archipelago build for Savage Wind {ver}")
    want = _get(assets[name + ".sha256"]["url"], "application/octet-stream").decode().split()[0].strip()
    data = _get(assets[name]["url"], "application/octet-stream")
    if hashlib.sha256(data).hexdigest() != want:
        log("The download didn't match its checksum: not used.")
        return False
    d = os.path.join(BUILDS, ver)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "savagewind.exe"), "wb") as f:
        f.write(data)
    with open(os.path.join(d, "savagewind.exe.sha256"), "w") as f:
        f.write(want)
    return True


# ---- Savage Wind's own updater ("SW Update.exe", in its folder): --check asks GitHub, --apply installs the newest
# release (checked, signed, undone if it fails) and opens Savage Wind Configuration, which builds the new game code
def sw_update_check(sw):
    """{"status": current / available / error, "current", "version" (the newest), ...} or {} (no updater)"""
    up = os.path.join(sw, "SW Update.exe")
    if not os.path.exists(up):
        return {}
    out = os.path.join(tempfile.gettempdir(), "botw_ap_sw_check.txt")
    try:
        subprocess.run([up, "--check", "--out", out], cwd=sw, timeout=60, creationflags=0x08000000)
        res = dict(line.rstrip("\n").split("=", 1) for line in open(out, encoding="utf8") if "=" in line)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return res


def _sw_running(sw):
    """Savage Wind's own programs from this folder still running (the game, its Configuration, the updater) - only
    those: the launcher itself may be kept in the folder too"""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Get-Process | Where-Object { $_.Path } | ForEach-Object { $_.Path }"],
                             capture_output=True, text=True, timeout=30, creationflags=0x08000000).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    own = {os.path.normcase(os.path.join(os.path.abspath(sw), n))
           for n in ("savagewind.exe", "Savage Wind Configuration.exe", "SW Update.exe")}
    return any(os.path.normcase(p.strip()) in own for p in out.splitlines() if p.strip())


def inside_sw(sw):
    """this launcher runs from inside the Savage Wind folder: its updater won't update while anything from there runs"""
    here = os.path.normcase(os.path.abspath(sys.executable))
    return here.startswith(os.path.normcase(os.path.abspath(sw)) + os.sep)


def update_sw(cfg, log, step=lambda key, f: None, finish=True):
    """Savage Wind to its newest release and the Archipelago build of it in place - only when that build exists, so
    the game is never left on a version without one (finish=False: the update alone, Set up after)"""
    sw = cfg["sw"]
    if _sw_running(sw):
        raise RuntimeError("Close Savage Wind first.")
    if inside_sw(sw):
        raise RuntimeError("Savage Wind's updater won't run while the launcher runs from inside its folder: start the "
                           "launcher from somewhere else.")
    chk = sw_update_check(sw)
    new = chk.get("version", "")
    if chk.get("status") != "available" or not new:
        log(f"Savage Wind {manifest_version(sw)} is the newest.")
        return False
    step("sw", 0.1)
    if not fetch_ap_build(new, log):
        raise RuntimeError(f"Savage Wind {new} is out, but its Archipelago build isn't yet: Savage Wind is left as it "
                           f"is. Try again later ({REPO}/releases).")
    step("sw", 0.3)
    log(f"Updating Savage Wind to {new} (its own updater)")
    keep = os.path.join(sw, "savagewind.stock.exe")
    if os.path.exists(keep):  # (the stock exe back first: the updater sees its own files)
        shutil.copy2(keep, os.path.join(sw, "savagewind.exe"))
    subprocess.run([os.path.join(sw, "SW Update.exe"), "--apply"], cwd=sw)
    log("Savage Wind is setting itself up (its window): the launcher goes on once it's closed")
    time.sleep(3)
    while _sw_running(sw):  # (Configuration builds the new game code)
        time.sleep(2)
    if manifest_version(sw) != new:
        raise RuntimeError(f"Savage Wind wasn't updated (still {manifest_version(sw)}): see SW Update.log in its folder.")
    if os.path.exists(keep):
        os.remove(keep)  # (the old version's: the new stock exe is kept on Set up)
    step("sw", 1)
    log(f"Savage Wind {new} is in." + (" Now its Archipelago build:" if finish else ""))
    if finish:
        setup(cfg, log, step)
    return True


def overlay_dir(sw):
    return os.path.join(sw, "ap_overlay")


def overlay_stamp(sw):
    return os.path.join(overlay_dir(sw), ".launcher-version")


def flag_line(sw):
    # (relative: Savage Wind runs in its folder; a launch option's value is at most 127 characters - a longer one is
    # dropped without a word - and the folder can move)
    return "SAVAGEWIND_ROMFS_OVERLAY=ap_overlay"


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
    if not ver:
        out["sw"] = ("bad", "This isn't a Savage Wind release folder (no sw-manifest.txt).")
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
    build, build_sha = ap_build(ver)
    if build and exe == build_sha:
        out["exe"] = ("ok", "Installed. Your original is kept as savagewind.stock.exe.")
    elif not build:
        out["exe"] = ("todo", f"The Archipelago build for Savage Wind {ver} is downloaded on Set up.")
    elif exe == manifest_sha(sw, "savagewind.exe"):
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


def setup(cfg, log, step=lambda key, f: None):
    """step(key, fraction): how far each status() step is (the window fills its landmark as it goes)"""
    sw = cfg["sw"]
    st = status(cfg)
    if st["sw"][0] != "ok":
        raise RuntimeError(st["sw"][1])
    if st["exe"][0] != "ok":
        step("exe", 0.2)
        ver = manifest_version(sw)
        if not fetch_ap_build(ver, log):
            raise RuntimeError(f"There's no Archipelago build for Savage Wind {ver} yet: it comes a while after each "
                               f"Savage Wind release ({REPO}/releases).")
        log("Putting the Archipelago build of Savage Wind in place")
        exe, keep = os.path.join(sw, "savagewind.exe"), os.path.join(sw, "savagewind.stock.exe")
        if not os.path.exists(keep):
            shutil.copy2(exe, keep)
        shutil.copy2(ap_build(ver)[0], exe)
    step("exe", 1)
    if st["overlay"][0] != "ok":
        log("Building the overlay from your game files")
        build_overlay(sw, log, lambda f: step("overlay", f))
    step("overlay", 1)
    if st["flags"][0] != "ok":
        step("flags", 0.5)
        log("Turning the overlay on (launch-flags.txt)")
        lines = [l for l in read_flags(sw) if not l.startswith("SAVAGEWIND_ROMFS_OVERLAY=")]
        write_flags(sw, lines + [flag_line(sw)])
    step("flags", 1)
    if st["apworld"][0] == "todo":
        step("apworld", 0.3)
        log("Installing botw.apworld into Archipelago")
        dest = os.path.join(cfg["archipelago"], "custom_worlds")
        os.makedirs(dest, exist_ok=True)
        shutil.copy2(os.path.join(PAYLOAD, "botw.apworld"), dest)
    step("apworld", 1)
    if st["poptracker"][0] == "todo":
        step("poptracker", 0.05)
        log("Making the PopTracker pack")
        out = os.path.join(sw, "ap_poptracker")
        run_tool("poptracker.py", [os.path.join(sw, "extracted"), out], log)
        os.makedirs(os.path.join(cfg["poptracker"], "packs"), exist_ok=True)
        shutil.copy2(os.path.join(out, "BotW_AP.zip"), os.path.join(cfg["poptracker"], "packs", "BotW_AP.zip"))
    step("poptracker", 1)
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
    if "--update" in sys.argv:  # (Update Savage Wind: a copy from outside its folder, started by do_update)
        app.after(1500, lambda: (app.show("ruta"), app.do_update()))
    app.mainloop()
