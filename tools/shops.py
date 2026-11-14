"""Every shop slot in Hyrule, from your own game files (shop sanity: tools/shop_sanity.py gives each one a saved flag,
tools/extract.py makes each one a check).

A slot is (shopkeeper actor, item actor):
  - merchants: the shop data in the shopkeeper's actor pack (Actor/ShopData/*.bshop: tables of items; traveling
    merchants, Beedle, Kilton, Granté, the ancient tech labs...); a display shop's data lists what is on its counter
  - display shops: the wares laid out on a counter, map objects linked "ForSale" to the shopkeeper (the town stores)
  - mannequins: an armor shop's mannequin (ForSale too) sells the armor it wears (its EquipArmorName1)
Left out: what isn't a shop - the horse stables' styling, Symin's photos, the Great Fairies' upgrades, Hateno's dye shop.

A shopkeeper's talk is an event named after its actor (its own event flow), so Savage Wind can tell who sold what: the
first time Link comes out of one of those talks with more of an item that shopkeeper sells, it sets the slot's saved
flag AP_Shop_<crc32 of "shopkeeper/item", 8 hex digits> (runtime/ap_event.c) - the check. The shops still sell what
they sold.
"""
import glob
import os
import re
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402

NOT_SHOPS = re.compile(r"HorseAssociationCustum|^Self_HorseAssociationCustum$|^Npc_AncientAssistant001$|^Npc_DressFairy_"
                       r"|^Npc_HatenoVillage001$")  # (stable styling, Symin's photos, Great Fairies, the dye shop)


def flag_name(npc, item):
    return f"AP_Shop_{zlib.crc32(f'{npc}/{item}'.encode()):08x}"


def bshop_items(data):
    """the items of a shop data file (AAMP), in its order, each once"""
    import oead
    io = oead.aamp.ParameterIO.from_binary(data)
    h = io.objects["Header"].params
    out = []
    for t in range(h["TableNum"].v):
        o = io.objects[str(h[f"Table{t + 1:02d}"].v)].params
        for i in range(o["ColumnNum"].v):
            n = str(o[f"ItemName{i + 1:03d}"].v)
            if n not in out:
                out.append(n)
    return out


def field_units(ex):
    """(tile, kind, relative path, bytes) of each overworld map unit the game reads (the add-on content's copy wins)"""
    romfs, aoc = os.path.join(ex, "romfs"), os.path.join(ex, "aoc1")
    title = None
    for tile in sorted(os.listdir(os.path.join(romfs, "Map", "MainField"))):
        if not re.fullmatch(r"[A-J]-\d", tile):
            continue
        for kind in ("Static", "Dynamic"):
            rel = f"Map/MainField/{tile}/{tile}_{kind}.smubin"
            if os.path.exists(os.path.join(aoc, rel)):
                yield tile, kind, "aoc/0010/" + rel, open(os.path.join(aoc, rel), "rb").read()
            elif kind == "Dynamic":
                yield tile, kind, rel, open(os.path.join(romfs, rel), "rb").read()
            else:
                title = title or nin.sarc(open(os.path.join(romfs, "Pack", "TitleBG.pack"), "rb").read())
                yield tile, kind, None, title[rel]


def shop_slots(ex):
    """[{npc, item, ap, kind ('shop' / 'display' / 'mannequin'), pos (x, z) or None}], sorted"""
    romfs = os.path.join(ex, "romfs")
    slots, pos = {}, {}
    for p in sorted(glob.glob(os.path.join(romfs, "Actor", "Pack", "*.sbactorpack"))):
        npc = os.path.basename(p)[:-len(".sbactorpack")]
        if NOT_SHOPS.search(npc):
            continue
        for k, v in nin.sarc(open(p, "rb").read()).items():
            if k.endswith(".bshop"):
                for item in bshop_items(v):
                    slots.setdefault((npc, item), "shop")
    for tile, kind, _, raw in field_units(ex):
        objs = nin.byml(raw).get("Objs", [])
        by = {o["HashId"]: o for o in objs}
        for o in objs:
            if o["UnitConfigName"] not in pos:  # (where a shopkeeper stands; traveling merchants have no place)
                pos[o["UnitConfigName"]] = (o["Translate"][0], o["Translate"][2])
            sale = [l for l in o.get("LinksToObj", []) if l["DefinitionName"] == "ForSale" and l["DestUnitHashId"] in by]
            if sale:  # (sold by the first shopkeeper it is linked to, if more than one)
                npc = by[sale[0]["DestUnitHashId"]]["UnitConfigName"]
                p = o.get("!Parameters") or {}
                if p.get("EquipArmorName1"):
                    slots[(npc, p["EquipArmorName1"])] = "mannequin"
                else:
                    slots[(npc, o["UnitConfigName"])] = "display"
    # (only shopkeepers whose talk is an event of their own: the runtime knows them by it)
    flows = {os.path.basename(p)[:-len(".sbeventpack")] for p in glob.glob(os.path.join(ex, "*", "Event", "*.sbeventpack"))}
    flows |= {k[len("EventFlow/"):-len(".bfevfl")] for k in nin.sarc(open(os.path.join(romfs, "Pack", "TitleBG.pack"), "rb").read())
              if k.startswith("EventFlow/")}
    return [dict(npc=n, item=i, flag=flag_name(n, i), kind=k, pos=pos.get(n)) for (n, i), k in sorted(slots.items())
            if n in flows]


if __name__ == "__main__":
    import collections
    s = shop_slots(sys.argv[1])
    print(len(s), collections.Counter(x["kind"] for x in s), sum(x["pos"] is None for x in s), "without a place")
    assert len({x["flag"] for x in s}) == len(s), "names collide"
