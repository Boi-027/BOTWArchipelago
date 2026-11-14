"""Builds worlds/botw/data/locations.json from your own extracted game files (romfs + aoc1).

    botw_ap/.venv/Scripts/python -I tools/extract.py "<Savage Wind folder>/extracted"   (oead: the shops)

Every location is one gamedata flag the client reads from game_data.sav: true = checked.
"""
import json
import math
import os
import re
import sys
import zlib
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402

EX = sys.argv[1]
ROMFS, AOC = os.path.join(EX, "romfs"), os.path.join(EX, "aoc1")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worlds", "botw", "data", "locations.json")


def rd(*p):
    with open(os.path.join(*p), "rb") as f:
        return f.read()


# flag name -> hash (validates every flag we emit really exists)
gd = nin.sarc(nin.sarc(rd(ROMFS, "Pack", "Bootup.pack"))["GameData/gamedata.ssarc"])
FLAGS = {}
for blob in gd.values():
    for kind, entries in nin.byml(blob).items():
        for e in entries:
            FLAGS[e["DataName"]] = (kind, e["HashValue"] & 0xFFFFFFFF)

msg = nin.sarc(nin.sarc(rd(ROMFS, "Pack", "Bootup_USen.pack"))["Message/Msg_USen.product.ssarc"])
LOC_NAMES = nin.msbt(msg["StaticMsg/LocationMarker.msbt"])
DUNGEON_NAMES = nin.msbt(msg["StaticMsg/Dungeon.msbt"])

title = nin.sarc(rd(ROMFS, "Pack", "TitleBG.pack"))
field = nin.byml(rd(AOC, "Map", "MainField", "Static.smubin"))

# named places for "nearest landmark" names
places = []
for m in field["LocationMarker"] + field["LocationPointer"]:
    name = LOC_NAMES.get(m.get("MessageID", ""))
    if name and not m["MessageID"].startswith("Dungeon"):
        t = m["Translate"]
        places.append((t["X"], t["Z"], name))


def near(x, z):
    return min(places, key=lambda p: (p[0] - x) ** 2 + (p[1] - z) ** 2)[2]


locs = []
seen = set()
height = {}  # flag -> y, where a location has one (the plateau test)


def add(name, cat, flag, x=None, z=None, dlc=False, **extra):
    if flag not in FLAGS or flag in seen:
        return
    seen.add(flag)
    locs.append(dict(name=name, category=cat, flag=flag, hash=FLAGS[flag][1], dlc=dlc,
                     pos=[round(x), round(z)] if x is not None else None, **extra))


def numbered(items):
    """items: (base, cat, flag, x, z, extra) -> names 'base #n' sorted west->east so they stay stable."""
    groups = defaultdict(list)
    for it in items:
        groups[it[0]].append(it)
    for base, g in groups.items():
        g.sort(key=lambda it: (it[3], it[4]))
        for n, (b, cat, flag, x, z, extra) in enumerate(g, 1):
            add(f"{b} #{n}" if len(g) > 1 else b, cat, flag, x, z, **extra)


# --- shrines (base 000-119, Champions' Ballad 120-135) ---
dungeon_pos = {m["MessageID"]: m["Translate"] for m in field["LocationMarker"] if m.get("MessageID", "").startswith("Dungeon")}
for n in range(136):
    d = f"Dungeon{n:03d}"
    nm = LOC_NAMES.get(d) or DUNGEON_NAMES.get(d)
    if not nm:
        continue
    t = dungeon_pos.get(d, {"X": None, "Z": None})
    add(nm, "Shrine", f"Clear_{d}", t["X"], t["Z"], dlc=n >= 120, dungeon=d)

# --- towers ---
for m in field["LocationMarker"]:
    mid = re.fullmatch(r"Tower(\d\d)", m.get("MessageID", ""))
    if mid:
        add(f"{LOC_NAMES[m['MessageID']]} Activated", "Tower", f"MapTower_{mid.group(1)}", m["Translate"]["X"], m["Translate"]["Z"])

# --- koroks ---
height.update({k["Flag"]: k["Translate"]["Y"] for k in field["KorokLocation"]})
numbered([(f"Korok Seed - {near(k['Translate']['X'], k['Translate']['Z'])}", "Korok", k["Flag"],
           k["Translate"]["X"], k["Translate"]["Z"], {}) for k in field["KorokLocation"]])

# --- overworld chests (MainField map units; DLC versions of a unit win). Not: three nobody can open - Hateno Village's
# in front of the inn (Purple Rupee) and Rassla Lake's (Royal Shield) fall through the ground when they appear, Aris
# Beach's in the sea (Opal) is stuck in it, Magnesis can't lift it ---
UNREACHABLE = {"MainField_TBox_Field_Stone_753815850", "MainField_TBox_Field_Iron_2279135900",
               "MainField_TBox_Field_Iron_2675135236"}
chests = []
for tile in sorted(os.listdir(os.path.join(ROMFS, "Map", "MainField"))):
    if not re.fullmatch(r"[A-J]-\d", tile):
        continue
    for kind in ("Static", "Dynamic"):
        aoc = os.path.join(AOC, "Map", "MainField", tile, f"{tile}_{kind}.smubin")
        if os.path.exists(aoc):
            blob = rd(aoc)
        elif kind == "Static":
            blob = title[f"Map/MainField/{tile}/{tile}_Static.smubin"]
        else:
            blob = rd(ROMFS, "Map", "MainField", tile, f"{tile}_Dynamic.smubin")
        for o in nin.byml(blob).get("Objs", []):
            u = o["UnitConfigName"]
            if u.startswith("TBox_") and f"MainField_{u}_{o['HashId']}" not in UNREACHABLE:
                x, y, z = o["Translate"]
                p = o.get("!Parameters") or {}
                height[f"MainField_{u}_{o['HashId']}"] = y
                # (only in Master Mode; only during the One-Hit Obliterator's trial, a Champions' Ballad quest)
                extra = {"master_mode": True} if p.get("IsHardModeActor") else {"dlc": True} if p.get("IsIchigekiActor") else {}
                chests.append((f"Chest - {near(x, z)}", "Chest", f"MainField_{u}_{o['HashId']}", x, z, extra))
numbered(chests)

# --- shrine chests (CDungeon map inside each DungeonNNN.pack) ---
shrine_name = {l["dungeon"]: l["name"] for l in locs if l["category"] == "Shrine"}
for d, nm in shrine_name.items():
    p = os.path.join(ROMFS, "Pack", f"{d}.pack")
    dlc = not os.path.exists(p)
    if dlc:
        p = os.path.join(AOC, "Pack", f"{d}.pack")
    if not os.path.exists(p):
        continue
    pack = nin.sarc(rd(p))
    items = []
    for k, v in pack.items():
        if k.endswith(".smubin") and "/CDungeon/" in k:
            for o in nin.byml(v).get("Objs", []):
                if o["UnitConfigName"].startswith("TBox_"):
                    x, _, z = o["Translate"]
                    hard = {"master_mode": True} if (o.get("!Parameters") or {}).get("IsHardModeActor") else {}
                    items.append((f"{nm} Chest", "Shrine Chest", f"CDungeon_{o['UnitConfigName']}_{o['HashId']}", x, z,
                                  {"dlc": dlc, **hard}))
    numbered(items)

# --- the Great Plateau shrines' terminals (each gave its rune; now the rune is an item and the terminal a check: its own
# flag goes on when Link uses it) ---
for d, nm in shrine_name.items():
    p = os.path.join(ROMFS, "Pack", f"{d}.pack")
    if not os.path.exists(p):
        continue
    for k, v in nin.sarc(rd(p)).items():
        if k.endswith(".smubin") and "/CDungeon/" in k:
            for o in nin.byml(v).get("Objs", []):
                if o["UnitConfigName"] == "DgnObj_DownloadTerminal_A_01":  # (where the shrine is on the map)
                    add(f"{nm} Terminal", "Rune Terminal", f"CDungeon_DgnObj_DownloadTerminal_A_01_{o['HashId']}",
                        dungeon_pos[d]["X"], dungeon_pos[d]["Z"], dungeon=d)

# --- Purah's rune upgrades at the Hateno Ancient Tech Lab (Remote Bomb+, Stasis+, Sheikah Sensor+): now items, so
# buying one is a check - how many were bought, a counter the game keeps (the client reads "flag >= min") ---
lab = next(p for p in places if p[2] == "Hateno Ancient Tech Lab")
for n in (1, 2, 3):
    key = f"Hateno_SheikPad_Lv2_Total>={n}"
    locs.append(dict(name=f"Hateno Ancient Tech Lab - Rune Upgrade {n}", category="Rune Upgrade",
                     flag="Hateno_SheikPad_Lv2_Total", min=n, hash=zlib.crc32(key.encode()), dlc=False,
                     pos=[round(lab[0]), round(lab[1])]))

# --- divine beasts and Hyrule Castle (their own map packs) ---
BEASTS = {"RemainsWater": "Vah Ruta", "RemainsWind": "Vah Medoh", "RemainsFire": "Vah Rudania",
          "RemainsElectric": "Vah Naboris"}
for key, nm in BEASTS.items():
    add(f"{nm} Cleared", "Divine Beast", f"Clear_{key}")
    # (its Heart Container is no check: tools/strip_rewards.py makes it an Archipelago Item, which sets no flag)
    pack = nin.sarc(rd(ROMFS, "Pack", f"{key}.pack"))
    items = []
    for k, v in pack.items():
        if k.endswith(".smubin"):
            for o in nin.byml(v).get("Objs", []):
                if o["UnitConfigName"].startswith("TBox_"):
                    x, _, z = o["Translate"]
                    hard = {"master_mode": True} if (o.get("!Parameters") or {}).get("IsHardModeActor") else {}
                    items.append((f"{nm} Chest", "Divine Beast Chest", f"MainFieldDungeon_{o['UnitConfigName']}_{o['HashId']}", x, z, hard))
    numbered(items)

# --- memories (pulling the Master Sword is the quest The Hero's Sword: its own flag also goes on when the sword is
# received from the multiworld) ---
for n in range(18):
    add(f"Captured Memory {n + 1}", "Memory", f"IsGet_MemoryPhoto_{n:03d}")

# --- quests: the flag of the last step = done ---
qname = {}
for k, v in msg.items():
    if k.startswith("QuestMsg/QL_"):
        for lab, txt in nin.msbt(v).items():
            if lab.endswith("_Name"):
                qname[lab[3:-5]] = txt
SKIP_QUESTS = {"GanonQuest", "bf2_collabo"}  # the goal itself; an event that can't be started any more
DLC_QUESTS = {"BalladOfHeroes", "BalladOfHeroGerudo", "BalladOfHeroGoron", "BalladOfHeroZora", "BalladOfHeroRito",
              "CarryingBlueFireEXMini", "TutorialDungeon"}
quests = nin.byml(title["Quest/QuestProduct.sbquestpack"])
aocq = os.path.join(AOC, "Pack", "AocMainField.pack")
for q in quests:
    n = q["Name"]
    if n in SKIP_QUESTS:
        continue
    cat = {"Main": "Main Quest", "Sub": "Shrine Quest", "Mini": "Side Quest"}[q["Type"]]
    if n.startswith("MiniGame") or n.endswith("_mini"):
        cat = "Minigame"
    add(qname.get(n, n), cat, q["Steps"][-1]["NextFlag"], dlc=n in DLC_QUESTS or n.startswith("EX_"),
        orderer=q.get("Orderer", ""))

# --- the Trial of the Sword (DLC): each of its three trials ---
for n, part in (("Junior", "Beginning"), ("Middle", "Middle"), ("Senior", "Final")):
    add(f"Trial of the Sword - {part} Trials", "Side Quest", f"100enemy_Clear_{n}", dlc=True)

# --- Hestu's trades: each pouch upgrade's own flag, and what it costs in Korok Seeds (his event flow
# Npc_OldKorok: 1 2 3 5 8 12 17 25 35 45 55 / 1 2 3 5 8 12 17 25 / 1 2 3 4 5 10x5 15x5 20). korok_seeds: enough to
# reach it whatever else was bought first - its own and the earlier levels', and the other two kinds in full ---
HESTU = {"Weapon": [1, 2, 3, 5, 8, 12, 17, 25, 35, 45, 55], "Bow": [1, 2, 3, 5, 8, 12, 17, 25],
         "Shield": [1, 2, 3, 4, 5, 10, 10, 10, 10, 10, 15, 15, 15, 15, 15, 20]}
for kind, costs in HESTU.items():
    others = sum(sum(c) for k, c in HESTU.items() if k != kind)
    for n in range(len(costs)):
        add(f"Hestu - {kind} Slot {n + 1}", "Hestu", f"Npc_OldKorok_{kind}{n + 1:02d}",
            korok_seeds=sum(costs[:n + 1]) + others)
add("Hestu's Gift", "Hestu", "Npc_OldKorok_FullComp", korok_seeds=sum(sum(c) for c in HESTU.values()))

# --- the Great Plateau: Link can't leave it without the paraglider. Its edge: the areas at the foot of its cliffs that
# send him back, which the game deletes once he has it (LinkTags with SaveFlag IsGet_PlayerStole2, Delete links); their
# centres, in order around the ring, outline it. A location inside is "plateau"; a shrine chest goes with its shrine ---
edge = []
for tile in ("D-6", "D-7", "E-6", "E-7"):
    m = nin.byml(rd(AOC, "Map", "MainField", tile, f"{tile}_Static.smubin"))
    by = {o["HashId"]: o for o in m["Objs"]}
    for o in m["Objs"]:
        if (o.get("!Parameters") or {}).get("SaveFlag") == "IsGet_PlayerStole2":
            for l in o.get("LinksToObj", []):
                a = by.get(l["DestUnitHashId"])
                if l["DefinitionName"] == "Delete" and a and a["UnitConfigName"] == "Area":
                    edge.append((a["Translate"][0], a["Translate"][2], a["Translate"][1]))
cx, cz = sum(e[0] for e in edge) / len(edge), sum(e[1] for e in edge) / len(edge)
edge.sort(key=lambda p: math.atan2(p[1] - cz, p[0] - cx))


def on_plateau(x, z, y=None):
    """inside the ring, and (where its height is known) well above the cliff foot nearest to it: a spot below the
    cliffs is never counted as up there (the other way round only asks for the paraglider sooner)"""
    inside = False
    for (x1, z1, _), (x2, z2, _) in zip(edge, edge[1:] + edge[:1]):
        if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
            inside = not inside
    foot = min(edge, key=lambda e: (e[0] - x) ** 2 + (e[1] - z) ** 2)[2]
    return inside and (y is None or y > foot + 25)


shrine_pos = {l["name"]: l["pos"] for l in locs if l["category"] == "Shrine" and l["pos"]}
for l in locs:
    pos = shrine_pos.get(l["name"].split(" Chest")[0]) if l["category"] == "Shrine Chest" else l["pos"]
    l["plateau"] = bool(pos and on_plateau(*pos, height.get(l["flag"]))) or         l["flag"] in ("FirstTower_Finish", "FindDungeon_Finish")

# --- shop sanity: every shop slot (tools/shops.py; its flag is added by tools/shop_sanity.py, so it isn't in the game's
# own data: no check against FLAGS) ---
from shops import shop_slots  # noqa: E402
NPC_NAMES, ITEM_NAMES = {}, {}
for k, v in msg.items():
    if k.startswith("ActorType/") and k.endswith(".msbt"):
        for lab, txt in nin.msbt(v).items():
            if lab.endswith("_Name"):
                (NPC_NAMES if k.endswith(("Npc.msbt", "NPC.msbt")) else ITEM_NAMES).setdefault(lab[:-5], txt)
for s in shop_slots(EX):
    base = re.sub(r"_(\d|DLC2nd)$", "", s["npc"])  # (a second copy of a merchant, as Rhondson's in Tarrey Town)
    who = ("Beedle" if s["npc"].startswith("Npc_TripMaster") else "Ancient Oven" if s["npc"].startswith("TwnObj_AncientOven")
           else NPC_NAMES.get(s["npc"]) or NPC_NAMES.get(base) or s["npc"])
    where = near(*s["pos"]) if s["pos"] else "traveling"
    what = ITEM_NAMES.get(s["item"]) or NPC_NAMES.get(s["item"]) or s["item"]
    locs.append(dict(name=f"Shop - {who} ({where}) - {what}", category="Shop", flag=s["flag"],
                     hash=zlib.crc32(s["flag"].encode()), dlc=False, plateau=False,
                     pos=[round(s["pos"][0]), round(s["pos"][1])] if s["pos"] else None))

# --- region lock: each location's region (tools/regions.py; -1: no one place, it needs them all). Placed things by
# where they are (a shrine's chests and terminal: the shrine's), a quest by where whoever gives it stands, the Divine
# Beasts by where they rest, Hestu and the Trial of the Sword in the Korok Forest ---
from regions import NAMES as REGION_NAMES, PLATEAU, Grid  # noqa: E402
grid = Grid(EX)
who_pos = {}
from shops import field_units  # noqa: E402
for _, _, _, raw in field_units(EX):
    for o in nin.byml(raw).get("Objs", []):
        who_pos.setdefault(o["UnitConfigName"], (o["Translate"][0], o["Translate"][2]))
BEAST_REGION = {"Vah Ruta": 11, "Vah Medoh": 1, "Vah Rudania": 9, "Vah Naboris": 3}
for l in locs:
    pos = shrine_pos.get(l["name"].split(" Chest")[0]) if l["category"] == "Shrine Chest" else l["pos"]
    beast = next((b for b in BEAST_REGION if b in l["name"]), None)
    if beast and l["category"] in ("Divine Beast", "Divine Beast Chest", "Main Quest"):
        l["region"] = BEAST_REGION[beast]
    elif l["category"] == "Hestu" or l["flag"].startswith("100enemy_"):
        l["region"] = REGION_NAMES.index("Woodland")
    elif pos:
        l["region"] = grid.region(*pos)
    elif l.get("orderer") in who_pos:
        l["region"] = grid.region(*who_pos[l["orderer"]])
    else:
        l["region"] = -1
    l.pop("orderer", None)
adj = grid.adjacency()
with open(os.path.join(os.path.dirname(OUT), "regions.json"), "w", encoding="utf8") as f:
    json.dump({"names": REGION_NAMES, "plateau": PLATEAU, "adjacent": [sorted(adj[i]) for i in range(len(REGION_NAMES))]},
              f, indent=1)

# names must be unique for AP
dupes = defaultdict(int)
for l in locs:
    dupes[l["name"]] += 1
for l in locs:
    if dupes[l["name"]] > 1:
        l["name"] = f"{l['name']} ({l['flag']})"

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf8") as f:
    json.dump(locs, f, indent=0, ensure_ascii=False)
cnt = defaultdict(int)
for l in locs:
    cnt[(l["category"], l["dlc"])] += 1
for k in sorted(cnt):
    print(f"{k[0]:20} dlc={k[1]!s:5} {cnt[k]}")
print("total", len(locs), "->", os.path.normpath(OUT))
