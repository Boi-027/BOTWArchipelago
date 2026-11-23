"""Checks give the Archipelago Item (tools/ap_item.py) instead of their normal reward: RomFS overlay files made from
your own game files. Chests: the overworld (every map tile), the shrines and the Divine Beasts. The add-on content's
files go to <overlay>/aoc/0010/ (where Savage Wind looks for them).

    python -I tools/strip_rewards.py "<Savage Wind>/extracted" <overlay folder>
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import byml  # noqa: E402
import nin  # noqa: E402
from ap_item import NAME, put  # noqa: E402


def edit_map(raw, hearts=False):
    """A map unit with every chest giving the Archipelago Item (hearts: the Heart Containers placed in it become one
    too); (new bytes or None when nothing changed, objects changed)"""
    d = nin.yaz0(raw)
    m = byml.read(d)
    n = 0
    for o in m.get("Objs", []):
        if o.get("UnitConfigName", "").startswith("TBox") and isinstance(o.get("!Parameters"), dict):
            o["!Parameters"]["DropActor"] = NAME
            n += 1
        elif hearts and o.get("UnitConfigName") == "Obj_HeartUtuwa_A_01":
            o["UnitConfigName"] = NAME
            n += 1
        elif o.get("UnitConfigName") == "LinkTagNAnd" and isinstance(o.get("!Parameters"), dict) and \
                o["!Parameters"].get("SaveFlag") == "Get_Vagrant_BOKANGI":
            # (the Old Man's cabin chest, Chest - Temple of Time #4: the Warm Doublet's, made only while he hasn't given
            # it - cook his recipe first and the check was gone. A check now: always made. AP_Never: give_trigger.py)
            o["!Parameters"]["SaveFlag"] = "AP_Never"
            n += 1
    if not n:
        return None, 0
    new = byml.write(m, struct.unpack_from("<H", d, 2)[0])
    assert len(new) <= len(d) + 64, "a map unit grew: its size table entry would be too small"
    return (nin.yaz0_store(new, struct.unpack_from(">I", raw, 8)[0]) if raw[:4] == b"Yaz0" else new), n


def patch_strings(data, swaps):
    """An event flow (BFEVFL) with whole strings replaced in its string pool, in place: each is a u16 length, the
    characters and a 0, so a shorter one fits where the old one was. {old: new}; returns (bytes, replacements)."""
    d, n = bytearray(data), 0
    for old, new in swaps.items():
        o, ob, nb = 0, old.encode(), new.encode()
        assert len(nb) <= len(ob)
        while (o := d.find(ob, o)) >= 0:
            if o >= 2 and struct.unpack_from("<H", d, o - 2)[0] == len(ob) and d[o + len(ob)] == 0:
                struct.pack_into("<H", d, o - 2, len(nb))
                d[o:o + len(ob) + 1] = nb + b"\0" * (len(ob) - len(nb) + 1)
                n += 1
            o += len(ob)
    return bytes(d), n


def edit_event_pack(raw, flow, swaps):
    """An event pack (Yaz0 SARC) with strings of one of its flows replaced, every file kept where it was"""
    s = nin.sarc(raw)
    new, n = patch_strings(s[flow], swaps)
    return nin.yaz0_store(nin.sarc_replace_inplace(raw, flow, new), struct.unpack_from(">I", raw, 8)[0]), n


def edit_pack(raw, hearts=False):
    """A pack (SARC) with its map units' chests changed, every other byte kept where it was"""
    files, total = nin.sarc(raw), 0
    out = raw
    for k, v in files.items():
        if k.endswith(".smubin"):
            new, n = edit_map(v, hearts)
            if new is not None:
                out = nin.sarc_replace_inplace(out, k, new)
                total += n
    return out, total


def main(ex, out):
    romfs, aoc = os.path.join(ex, "romfs"), os.path.join(ex, "aoc1")
    rd = lambda p: open(p, "rb").read()
    title = nin.sarc(rd(os.path.join(romfs, "Pack", "TitleBG.pack")))
    counts = {}
    # the overworld: each tile's static and dynamic unit; the add-on content's copy is the one the game reads
    n = 0
    for tile in sorted(os.listdir(os.path.join(romfs, "Map", "MainField"))):
        if not re.fullmatch(r"[A-J]-\d", tile):
            continue
        for kind in ("Static", "Dynamic"):
            rel = f"Map/MainField/{tile}/{tile}_{kind}.smubin"
            a = os.path.join(aoc, rel)
            if os.path.exists(a):
                new, c = edit_map(rd(a))
                if new: put(out, "aoc/0010/" + rel, new)
            elif kind == "Static":
                raise SystemExit(f"{rel}: only in TitleBG.pack (not handled: add-on content expected)")
            else:
                new, c = edit_map(rd(os.path.join(romfs, rel)))
                if new: put(out, rel, new)
            n += c
    counts["overworld chests"] = n
    # shrines (DungeonNNN.pack: the base game's, then the add-on content's) and the Divine Beasts
    for label, names in (("shrine chests", [f"Dungeon{i:03d}" for i in range(137)]),
                         ("Divine Beast chests", ["RemainsWater", "RemainsWind", "RemainsFire", "RemainsElectric"])):
        n = 0
        for nm in names:
            for base, prefix in ((aoc, "aoc/0010/"), (romfs, "")):  # (the add-on content's copy wins)
                p = os.path.join(base, "Pack", nm + ".pack")
                if os.path.exists(p):
                    new, c = edit_pack(rd(p), hearts=nm.startswith("Remains"))
                    if c: put(out, f"{prefix}Pack/{nm}.pack", new)
                    n += c
                    break
        counts[label] = n
    # the rewards events hand out: a Korok's seed, a shrine's Spirit Orb, a Divine Beast's champion power
    t_raw = rd(os.path.join(romfs, "Pack", "TitleBG.pack"))
    flow = nin.sarc(t_raw)["EventFlow/Demo017_0.bfevfl"]
    new, c = patch_strings(flow, {"Obj_KorokNuts": NAME})
    put(out, "Pack/TitleBG.pack", nin.sarc_replace_inplace(t_raw, "EventFlow/Demo017_0.bfevfl", new))
    counts["Korok Seed gifts"] = c
    for pack, flow, swaps, label in (
            ("Npc_DungeonPriest001", "EventFlow/Npc_DungeonPriest001.bfevfl", {"Obj_DungeonClearSeal": NAME}, "Spirit Orb gifts (monk)"),
            ("Demo033_0", "EventFlow/Demo033_0.bfevfl", {"Obj_DungeonClearSeal": NAME}, "Spirit Orb gifts (shrine end)"),
            ("ClearRemains", "EventFlow/ClearRemains.bfevfl",
             {f"Obj_HeroSoul_{r}": NAME for r in ("Zora", "Rito", "Goron", "Gerudo")}, "champion power gifts")):
        new, c = edit_event_pack(rd(os.path.join(romfs, "Event", pack + ".sbeventpack")), flow, swaps)
        put(out, f"Event/{pack}.sbeventpack", new)
        counts[label] = c
    for k, v in counts.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
