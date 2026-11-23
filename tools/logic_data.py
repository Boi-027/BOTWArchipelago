"""worlds/botw/data/logic.json: what each check needs beyond the world's general rules (worlds/botw/__init__.py), as
{location name: {"all": [items], "any": [items]}} - every item in "all", and one of "any" when it has some:
- the climate, from the game's own Ecosystem data (tools/climate.py): Death Mountain's burning areas need the
  Flamebreaker Set
- Gerudo Town, inside its walls (and Vah Naboris, Misae Suma Shrine): the Gerudo Set; Vah Ruta: Zora Armor
- runes, per check: the EIdras world's logic.csv (github.com/EIdras/BOTW-Archipelago), joined by game flag, where it
  has the check; else the nearest Map Genie marker of the same kind's how-to (its words read for a rune, a bomb, a
  check underwater or buried: those need Magnesis). A shrine's chests have their shrine's; the Divine Beasts all four.
Usage: python tools/logic_data.py <EIdras world data folder> <Map Genie map data .json> <extracted folder>
(Neither source is shipped: what is derived from them is only these item lists.)"""
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from climate import Climate  # noqa: E402

RUNES = {"magnesis": "Magnesis", "cryonis": "Cryonis", "stasis": "Progressive Stasis", "bomb": "Progressive Remote Bomb"}
ALL_RUNES = ["Progressive Remote Bomb", "Magnesis", "Progressive Stasis", "Cryonis"]
# Map Genie categories, by the kind of our checks they hold (chests are filed by what's in them)
MG_KIND = {6836: "Korok", 6833: "Chest", 6834: "Chest", 6830: "Chest", 6831: "Chest", 6832: "Chest", 6868: "Chest"}
REACH = {"Korok": 25.0, "Chest": 12.0}  # (metres: the nearest marker of that kind, else nothing taken)
TOWN_INNER = 200.0  # (Gerudo Town's own shops, to find its middle: the town's checks are within TOWN_R of it)
TOWN_R = 160.0
TAGS = [("magnesis", r"magnesis|magnet"), ("cryonis", r"cryonis|ice (pillar|block)"), ("stasis", r"stasis"),
        ("bomb", r"\bbombs?\b(?! arrow)"), ("buried", r"buried|dig |underground|under the ground"),
        ("underwater", r"underwater|bottom of the (lake|pond|river|water)|in the water")]


def mg_tags(desc):
    import re
    d = re.sub(r"\*\*(Weapon Type|Attack Power|Durability|Other effect|Scales into|Armor|Defense|Set bonus|Upgrade)"
               r"[\s\S]*$", "", desc or "")
    return {n for n, rx in TAGS if re.search(rx, d, re.I)}


def runes_of(tags):
    """Map Genie's tags -> (all, any)"""
    need = {RUNES[t] for t in tags if t in RUNES}
    if tags & {"underwater", "buried"}:
        need.add("Magnesis")
    return need, set()


def eidras_runes(s):
    s = (s or "").strip()
    if not s or s == "none":
        return set(), set()
    if s == "all":
        return set(ALL_RUNES), set()
    need, alt = set(), set()
    for part in s.split("|"):
        if "/" in part:
            alt |= set(part.split("/"))
        else:
            need.add(part)
    return need, alt


def main(eidras, mapgenie, ex):
    data = os.path.join(HERE, "..", "worlds", "botw", "data")
    locs = json.load(open(os.path.join(data, "locations.json"), encoding="utf8"))
    climate = Climate(os.path.join(ex, "romfs"))
    # EIdras: their rows by game flag
    flag_of = {l["name"]: l["gamedata_flag"] for l in json.load(open(os.path.join(eidras, "locations.json")))}
    eid = {}
    for row in csv.DictReader(open(os.path.join(eidras, "logic.csv"), encoding="utf8")):
        if row["location"] in flag_of:
            eid[flag_of[row["location"]]] = row
    # Map Genie: its markers, in game coordinates (fitted on the shrines both have)
    mg = json.load(open(mapgenie, encoding="utf8"))["locations"]
    shrine_pos = {l["name"]: l["pos"] for l in locs if l["category"] == "Shrine" and l.get("pos")}
    pairs = [(float(m["longitude"]), float(m["latitude"]), *shrine_pos[m["title"]]) for m in mg
             if m["category_id"] == 6816 and m["title"] in shrine_pos]
    fx, fz = fit(pairs, 2), fit(pairs, 3)
    marks = {"Korok": [], "Chest": []}
    for m in mg:
        k = MG_KIND.get(m["category_id"])
        if k and "Master Mode Only" not in (m["description"] or "") and "Can't be opened" not in (m["description"] or ""):
            lo, la = float(m["longitude"]), float(m["latitude"])
            marks[k].append((fx[0] * lo + fx[1] * la + fx[2], fz[0] * lo + fz[1] * la + fz[2], mg_tags(m["description"])))
    shops = [l["pos"] for l in locs if l["category"] == "Shop" and "(Gerudo Town)" in l["name"] and l.get("pos")]
    mx, mz = sum(p[0] for p in shops) / len(shops), sum(p[1] for p in shops) / len(shops)
    inner = [p for p in shops if math.hypot(p[0] - mx, p[1] - mz) < TOWN_INNER]
    town = (sum(p[0] for p in inner) / len(inner), sum(p[1] for p in inner) / len(inner))

    out, stats = {}, {"eidras": 0, "mapgenie": 0, "heat": 0, "gerudo": 0, "unmatched": 0}
    by_name = {}
    for l in locs:
        need, alt = set(), set()
        pos = l.get("pos")
        row = eid.get(l["flag"])
        if row:
            n, a = eidras_runes(row["runes"])
            need |= n
            alt |= a
            stats["eidras"] += 1
        elif pos and l["category"] in REACH:
            kind = "Korok" if l["category"] == "Korok" else "Chest"
            best = min(marks[kind], key=lambda m: (m[0] - pos[0]) ** 2 + (m[1] - pos[1]) ** 2, default=None)
            if best and math.hypot(best[0] - pos[0], best[1] - pos[1]) <= REACH[l["category"]]:
                n, a = runes_of(best[2])
                need |= n
                stats["mapgenie"] += 1
            else:  # (no marker to go by: as before, all four - not a guess that it needs none)
                need |= set(ALL_RUNES)
                stats["unmatched"] += 1
        if pos and climate.burning(*pos):
            need.add("Flamebreaker Set")
            stats["heat"] += 1
        if (pos and l["category"] != "Korok" and math.hypot(pos[0] - town[0], pos[1] - town[1]) <= TOWN_R) or \
                "Naboris" in l["name"] or l["name"] == "Misae Suma Shrine":
            need.add("Gerudo Set")
            stats["gerudo"] += 1
        if "Vah Ruta" in l["name"]:
            need.add("Zora Armor")
        if l["category"] in ("Divine Beast", "Divine Beast Chest"):
            need |= set(ALL_RUNES)
        by_name[l["name"]] = (need, alt)
    for l in locs:  # (a shrine's chests: its own needs too)
        if l["category"] == "Shrine Chest":
            base = l["name"].split(" Chest")[0]
            if base in by_name:
                by_name[l["name"]] = (by_name[l["name"]][0] | by_name[base][0], by_name[l["name"]][1] | by_name[base][1])
    for name, (need, alt) in by_name.items():
        if need or alt:
            out[name] = {"all": sorted(need), "any": sorted(alt - need)}
    json.dump(out, open(os.path.join(data, "logic.json"), "w", encoding="utf8"), indent=0, sort_keys=True)
    print(f"{len(out)} checks with needs; {stats}; Gerudo Town at {town[0]:.0f}, {town[1]:.0f}")


def fit(p, k):
    """least squares: game coordinate k = a * longitude + b * latitude + c"""
    S = [[0.0] * 4 for _ in range(3)]
    for q in p:
        v = (q[0], q[1], 1.0)
        for i in range(3):
            S[i][3] += v[i] * q[k]
            for j in range(3):
                S[i][j] += v[i] * v[j]
    for i in range(3):
        piv = max(range(i, 3), key=lambda r: abs(S[r][i]))
        S[i], S[piv] = S[piv], S[i]
        for r in range(3):
            if r != i:
                f = S[r][i] / S[i][i]
                S[r] = [a - f * b for a, b in zip(S[r], S[i])]
    return [S[i][3] / S[i][i] for i in range(3)]


if __name__ == "__main__":
    main(*sys.argv[1:4])
