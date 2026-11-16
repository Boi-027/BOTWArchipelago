"""Saved flags Archipelago keeps in the game's own save, added to the game data (gamedata and the save format) -
RomFS overlay files made from your own game files:
  - shop sanity: every shop slot in Hyrule is a check (tools/shops.py has the slots), sold as its own Archipelago
    Item until it's bought (tools/shop_items.py); Savage Wind sets the slot's AP_Shop_ flag then (runtime/ap_event.c)
  - region lock: AP_RegionLock (the slot has it on: the client sets it) and AP_Region_<n>, a region's map received
    (n: tools/regions.py; the Great Plateau's is never locked)

Needs oead (botw_ap/.venv). Reads the overlay folder's copies first (other tools wrote them):
    botw_ap/.venv/Scripts/python -I tools/shop_sanity.py "<Savage Wind>/extracted" <overlay folder>
"""
import os
import sys
import zlib

import oead

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ap_item import put  # noqa: E402
from give_trigger import rstb_update, s32, to_byml  # noqa: E402
from shop_items import build as shop_items  # noqa: E402
from shops import shop_slots  # noqa: E402


def main(ex, out):
    romfs = os.path.join(ex, "romfs")

    def src(rel):
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(romfs, rel), "rb").read()

    slots = shop_slots(ex)
    wares = [f for f, _ in shop_items(ex, out)]  # (each counter's Archipelago Item: bought once, never back)
    boot = oead.Sarc(src("Pack/Bootup.pack"))
    bw = oead.SarcWriter.from_sarc(boot)
    gd = oead.Sarc(oead.yaz0.decompress(bytes(boot.get_file("GameData/gamedata.ssarc").data)))
    gw = oead.SarcWriter.from_sarc(gd)
    name = next(f.name for f in gd.get_files() if f.name.startswith("/bool_data"))  # (not one the Blood Moon resets)
    b = oead.byml.from_binary(bytes(gd.get_file(name).data))
    have = {str(e["DataName"]) for e in b["bool_data"]}
    flags = [f for f in [s["flag"] for s in slots] + wares + ["AP_RegionLock"] + [f"AP_Region_{i:02d}" for i in range(15)]
             if f not in have]
    for fl in flags:
        b["bool_data"].append(to_byml({
            "DataName": fl, "DeleteRev": s32(0xFFFFFFFF), "HashValue": s32(zlib.crc32(fl.encode())),
            "InitValue": s32(0), "IsEventAssociated": False, "IsOneTrigger": False, "IsProgramReadable": True,
            "IsProgramWritable": True, "IsSave": True, "MaxValue": True, "MinValue": False, "ResetType": s32(0)}))
    gw.files[name] = oead.byml.to_binary(b, big_endian=False, version=2)
    # The received items' count (runtime/ui/ap_client.mm). The game saves only what its events set, not a value written
    # in its memory: AP_Given, saved, how many items were carried out, set by the item event from AP_Want_Given (the
    # client's, not saved; tools/give_trigger.py) - a load (a Game Over) goes back to what that save had, and the
    # items after it are given again
    numbers = {"AP_Given": True, "AP_Want_Given": False}
    s32n = next(f.name for f in gd.get_files() if f.name.startswith("/s32_data"))
    n = oead.byml.from_binary(bytes(gd.get_file(s32n).data))
    numbers = {fl: save for fl, save in numbers.items() if fl not in {str(e["DataName"]) for e in n["s32_data"]}}
    for fl, save in numbers.items():
        n["s32_data"].append(to_byml({
            "DataName": fl, "DeleteRev": s32(0xFFFFFFFF), "HashValue": s32(zlib.crc32(fl.encode())),
            "InitValue": s32(0), "IsEventAssociated": False, "IsOneTrigger": False, "IsProgramReadable": True,
            "IsProgramWritable": True, "IsSave": save, "MaxValue": s32(999999), "MinValue": s32(0), "ResetType": s32(0)}))
    gw.files[s32n] = oead.byml.to_binary(n, big_endian=False, version=2)
    flags += [fl for fl, save in numbers.items() if save]  # (the save's format lists the saved ones by name)
    gdata = gw.write()[1]
    bw.files["GameData/gamedata.ssarc"] = oead.yaz0.compress(gdata)
    sv = oead.Sarc(oead.yaz0.decompress(bytes(boot.get_file("GameData/savedataformat.ssarc").data)))
    sw = oead.SarcWriter.from_sarc(sv)
    last = "/saveformat_5.bgsvdata"  # (game_data.sav's last part: 2712 of its 8192)
    f = oead.byml.from_binary(bytes(sv.get_file(last).data))
    assert str(f["file_list"][0]["file_name"]) == "game_data.sav" and len(f["file_list"][1]) + len(flags) <= 8192
    for fl in flags:
        f["file_list"][1].append(to_byml({"DataName": fl, "HashValue": s32(zlib.crc32(fl.encode()))}))
    sw.files[last] = oead.byml.to_binary(f, big_endian=False, version=2)
    sdata = sw.write()[1]
    bw.files["GameData/savedataformat.ssarc"] = oead.yaz0.compress(sdata)
    put(out, "Pack/Bootup.pack", bw.write()[1])
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(out, rel, rstb_update(src(rel), {"GameData/gamedata.sarc": len(gdata) + 0x1000,
                                         "GameData/savedataformat.sarc": len(sdata) + 0x1000}))
    print(f"saved flags: {len(slots)} shop slots, region lock; {len(flags)} flags")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
