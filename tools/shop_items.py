"""Shop sanity's wares: every shop slot sells its own Archipelago Item until it's bought, then the shop's own good again.
Called by tools/shop_sanity.py (which adds the saved flags this returns). From your own game files:
  - an actor per slot, Item_AP_<hex of its flag AP_Shop_<hex>> ("_" added up to the good's name length on a
    merchant's list): the Archipelago Item's pack, model and icon, the good's price; in the English message files the
    name "Archipelago Item" and a line on what the shop sells once it's found
  - counters (display shops): one ware of each slot's pile is the slot's Archipelago Item; a link tag on the slot's
    flag deletes it once it's bought and creates the good that stood there (Master Mode's own way to add enemies)
  - merchants' lists (Actor/ShopData/*.bshop in the shopkeeper's pack): the good's entry names the slot's Archipelago
    Item; Savage Wind reads the name as the good again once the slot's flag is on (runtime/ap_shop.c, from the
    overlay's ap_shops.txt written here: "<pack> <offset in the unpacked pack> <Archipelago Item> <good>" a line)
  - mannequins keep their armor (they wear what they sell): buying it is the check, as before
Buying a slot's Archipelago Item sets the slot's flag (runtime/ap_event.c); buying one again (a list read before the
flag went on) gives the good instead.
"""
import copy
import os
import struct
import sys
import zlib

import oead

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import byml  # noqa: E402
import nin  # noqa: E402
from ap_item import LANGS, NAME, msbt_add, put, rstb_grow  # noqa: E402
from shops import field_units, shop_slots  # noqa: E402

SIDECAR = "ap_shops.txt"


def ap_name(slot, good=""):
    """the slot's Archipelago Item's actor name; on a merchant's list (good given) as long as the good's at least"""
    n = "Item_AP_" + slot["flag"][len("AP_Shop_"):]
    return n + "_" * (len(good) - len(n))


def good_names(src):
    """{actor: English name} from the message files"""
    msg = nin.sarc(nin.sarc(src("Pack/Bootup_USen.pack"))["Message/Msg_USen.product.ssarc"])
    out = {}
    for k, v in msg.items():
        if k.startswith("ActorType/") and k.endswith(".msbt"):
            for label, text in nin.msbt(v).items():
                if label.endswith("_Name"):
                    out.setdefault(label[:-5], text)
    return out


def build(ex, out):
    """everything above into the overlay folder `out`; returns the saved flags the new wares need: [(flag, template)]"""
    romfs = os.path.join(ex, "romfs")

    def src(rel):
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(romfs, rel), "rb").read()

    slots = [s for s in shop_slots(ex) if s["kind"] in ("shop", "display")]
    names = good_names(src)
    ai_raw = src("Actor/ActorInfo.product.sbyml")
    ai_d = nin.yaz0(ai_raw)
    ai = byml.read(ai_d)
    info = {a["name"]: a for a in ai["Actors"]}
    sizes, flags, side = {}, [], []

    # ---- merchants: the lists
    actors = {}  # (Archipelago Item: good)
    by_npc = {}
    for s in slots:
        if s["kind"] == "shop":
            by_npc.setdefault(s["npc"], []).append(s)
    for npc, ss in sorted(by_npc.items()):
        rel = f"Actor/Pack/{npc}.sbactorpack"
        raw = src(rel)
        files = nin.sarc(raw)
        swap = {s["item"]: ap_name(s, s["item"]) for s in ss}
        for k in [k for k in files if k.endswith(".bshop")]:
            io = oead.aamp.ParameterIO.from_binary(files[k])
            h = io.objects["Header"].params
            for t in range(h["TableNum"].v):
                o = io.objects[str(h[f"Table{t + 1:02d}"].v)].params
                for i in range(o["ColumnNum"].v):
                    good = str(o[f"ItemName{i + 1:03d}"].v)
                    if good in swap:
                        o[f"ItemName{i + 1:03d}"] = oead.FixedSafeString64(swap[good])
                        o[f"ItemLookGetFlg{i + 1:03d}"] = False  # (shown whether or not Link ever had one)
            files[k] = bytes(io.to_binary())
            sizes[k] = len(files[k]) + 0x1000
        data = nin.sarc_write(files, nin.sarc_aligns(nin.yaz0(raw)))
        put(out, rel, nin.yaz0_store(data, struct.unpack_from(">I", raw, 8)[0]))  # (stored: runtime/ap_shop.c reads it)
        sizes[f"Actor/Pack/{npc}.bactorpack"] = len(data) + 0x1000
        for good, n in swap.items():
            at = data.find(n.encode() + b"\0")
            if at < 0:
                continue  # (the item is on the counter, not on the list)
            while at >= 0:
                side.append(f"{rel} {at} {n} {good}")
                at = data.find(n.encode() + b"\0", at + 1)
            actors[n] = good

    # ---- counters: one ware a slot
    wares = {(s["npc"], s["item"]): s for s in slots if s["kind"] == "display"}
    used_hashes, done = set(), set()
    units = []
    for tile, kind, rel, raw in field_units(ex):
        if rel is None:
            continue
        p = os.path.join(out, rel)
        data = open(p, "rb").read() if os.path.exists(p) else raw
        units.append((rel, data))
        used_hashes.update(o["HashId"] for o in nin.byml(data).get("Objs", []))

    def new_hash(seed):
        h = zlib.crc32(seed.encode())
        while h in used_hashes or h == 0:
            h = (h + 1) & 0xFFFFFFFF
        used_hashes.add(h)
        return byml.U32(h)

    for rel, raw in units:
        d = nin.yaz0(raw)
        m = byml.read(d)
        objs = m.get("Objs", [])
        by = {o["HashId"]: o for o in objs}
        added = []
        for o in sorted(objs, key=lambda o: o["HashId"]):
            sale = [l for l in o.get("LinksToObj", []) if l["DefinitionName"] == "ForSale" and l["DestUnitHashId"] in by]
            if not sale or (o.get("!Parameters") or {}).get("EquipArmorName1"):
                continue
            key = (by[sale[0]["DestUnitHashId"]]["UnitConfigName"], o["UnitConfigName"])
            if key not in wares or key in done:
                continue
            done.add(key)
            s = wares[key]
            n = ap_name(s)
            actors[n] = s["item"]
            ap = copy.deepcopy(o)
            ap["UnitConfigName"] = n
            ap["HashId"] = new_hash(f"{s['flag']}/ware")
            ap["LinksToObj"] = [copy.deepcopy(sale[0])]
            tag = {"!Parameters": {"IncrementSave": False, "MakeSaveFlag": byml.S32(0), "NoChangeSignal": False,
                                   "SaveFlag": s["flag"], "SaveFlagOnOffType": byml.S32(0)},
                   "HashId": new_hash(f"{s['flag']}/tag"),
                   "LinksToObj": [{"!Parameters": {"AppearFade": False}, "DefinitionName": "Create",
                                   "DestUnitHashId": o["HashId"]},
                                  {"DefinitionName": "Delete", "DestUnitHashId": ap["HashId"]}],
                   "SRTHash": byml.S32(0), "Translate": copy.deepcopy(o["Translate"]), "UnitConfigName": "LinkTagAnd"}
            added += [ap, tag]
            flags.append((f"MainField_{n}_{int(ap['HashId'])}", f"MainField_{o['UnitConfigName']}_{int(o['HashId'])}"))
        if not added:
            continue
        objs += added
        objs.sort(key=lambda o: o["HashId"] & 0xFFFFFFFF)
        new = byml.write(m, struct.unpack_from("<H", d, 2)[0])
        put(out, rel, nin.yaz0_store(new, struct.unpack_from(">I", raw, 8)[0]) if raw[:4] == b"Yaz0" else new)
        name = (("Aoc/0010/" + rel[len("aoc/0010/"):]) if rel.startswith("aoc/0010/") else rel).replace(".smubin", ".mubin")
        sizes[name] = len(new) + 0x1000

    # ---- the actors: the Archipelago Item's pack, its own parameter list (the good's price), the actor table
    tp = src(f"Actor/Pack/{NAME}.sbactorpack")
    tfiles = nin.sarc(tp)
    link = oead.aamp.ParameterIO.from_binary(tfiles[f"Actor/ActorLink/{NAME}.bxml"])
    gpu = str(link.objects["LinkTarget"].params["GParamUser"].v)
    gparam = tfiles[f"Actor/GeneralParamList/{gpu}.bgparamlist"]
    tentry = info[NAME]
    hashes = ai["Hashes"]
    signed = type(hashes[0]).__name__ != "U32"
    for n, good in sorted(actors.items()):
        g = info.get(good, {})
        price = int(g.get("itemBuyingPrice", 0))
        if price <= 0:
            print(f"shop items: {good} has no price, 10 rupees")
            price = 10
        files = {k: v for k, v in tfiles.items() if not k.startswith("Actor/ActorLink/")}
        lk = oead.aamp.ParameterIO.from_binary(tfiles[f"Actor/ActorLink/{NAME}.bxml"])
        lk.objects["LinkTarget"].params["GParamUser"] = oead.FixedSafeString64(n)
        files[f"Actor/ActorLink/{n}.bxml"] = bytes(lk.to_binary())
        gp = oead.aamp.ParameterIO.from_binary(gparam)
        gp.objects["Item"].params["BuyingPrice"] = oead.S32(price)  # (a plain int is stored as a float)
        gp.objects["Item"].params["SellingPrice"] = oead.S32(0)
        files[f"Actor/GeneralParamList/{n}.bgparamlist"] = bytes(gp.to_binary())
        put(out, f"Actor/Pack/{n}.sbactorpack",
            nin.yaz0_store(nin.sarc_write(files, nin.sarc_aligns(nin.yaz0(tp))), struct.unpack_from(">I", tp, 8)[0]))
        if n not in info:
            e = copy.deepcopy(tentry)
            e["name"] = n
            e["itemBuyingPrice"] = type(tentry["itemBuyingPrice"])(price)
            e["itemUseIconActorName"] = NAME  # (its icon: the Archipelago Item's)
            h = zlib.crc32(n.encode())
            at = next((i for i, x in enumerate(hashes) if (x & 0xFFFFFFFF) > h), len(hashes))
            hashes.insert(at, type(hashes[0])(struct.unpack("<i", struct.pack("<I", h))[0] if signed else h))
            ai["Actors"].insert(at, e)
            info[n] = e
    ai_new = byml.write(ai, struct.unpack_from("<H", ai_d, 2)[0])
    put(out, "Actor/ActorInfo.product.sbyml", nin.yaz0_store(ai_new, struct.unpack_from(">I", ai_raw, 8)[0]))
    sizes["Actor/ActorInfo.product.byml"] = len(ai_new) + 0x1000

    # ---- the words
    for lang in LANGS:
        rel = f"Pack/Bootup_{lang}.pack"
        pack_raw = src(rel)
        pack = nin.sarc(pack_raw)
        mkey = f"Message/Msg_{lang}.product.ssarc"
        msg = nin.sarc(pack[mkey])
        labels = {}
        for n, good in actors.items():
            labels[f"{n}_Name"] = "Archipelago Item"
            labels[f"{n}_Desc"] = (f"Something for the multiworld. Once it's\nbought, this shop sells "
                                   f"{names.get(good, 'its own goods')}\nhere again.")
        msg["ActorType/Item.msbt"] = msbt_add(msg["ActorType/Item.msbt"], labels)
        msg_new = nin.sarc_write(msg, nin.sarc_aligns(pack[mkey]))
        pack[mkey] = nin.yaz0_store(msg_new, struct.unpack_from(">I", pack[mkey], 8)[0])
        put(out, rel, nin.sarc_write(pack, nin.sarc_aligns(pack_raw)))
        sizes[f"Message/Msg_{lang}.product.sarc"] = len(msg_new) + 0x1000

    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(out, rel, rstb_grow(src(rel), sizes))
    with open(os.path.join(out, SIDECAR), "w", encoding="utf8", newline="\n") as f:
        f.write("".join(x + "\n" for x in side))
        f.writelines(f"- - {n} {g}\n" for n, g in sorted(actors.items()))  # (every one: what buying it again gives)
    print(f"shop items: {len(actors)} Archipelago Items ({len(done)} on counters, {len(side)} list entries)")
    return flags


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
