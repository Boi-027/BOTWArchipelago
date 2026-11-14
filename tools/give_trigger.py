"""Items from the multiworld handed to Link at once, with the game's own item-get scene, wherever he is.

The client sets AP_Q<n> (which item) and AP_Pending, and Savage Wind starts the event Archipelago<AP_Dispatch> the
way the game starts its own scripted events (runtime/ap_event.c): the game's GetDemo<GetItemByName> for the first
AP_Q<n> that is set (and the heart/stamina gauge scene for those two), then AP_Done goes on and the other flags off.
This adds the event, its flags (not saved) and its registration.

Also packs the overworld's static map units (strip_rewards.py's chest changes) into AocMainField.pack, where the game
reads them.

Needs oead and evfl (botw_ap/.venv). Reads the overlay folder's copies first (the other tools wrote them):
    botw_ap/.venv/Scripts/python -I tools/give_trigger.py "<Savage Wind>/extracted" <overlay folder>
"""
import os
import struct
import sys
import zlib

import evfl
import oead
from evfl import Container, EntryPoint, Event
from evfl.actor import Actor
from evfl.common import ActorIdentifier, StringHolder
from evfl.event import ActionEvent, SubFlowEvent, SwitchEvent
from evfl.util import make_index, make_rindex

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402

# AP_Q<n> = ITEMS[n-1]; the client's order (keep in sync with ui/ap_client.mm)
ITEMS = ["Obj_HeroSoul_Zora", "Obj_HeroSoul_Rito", "Obj_HeroSoul_Goron", "Obj_HeroSoul_Gerudo", "Obj_HeartUtuwa_A_01",
         "Obj_StaminaUtuwa_A_01", "Weapon_Sword_070", "Obj_DungeonClearSeal", "Obj_KorokNuts", "Obj_WarpDLC",
         # what quests and minigames used to give: the Thunder Helm, the Blizzard Rod, horse gear, the Royal Shield
         "Armor_115_Head", "Weapon_Sword_049", "GameRomHorseReins_05", "GameRomHorseSaddle_05", "GameRomHorseReins_03",
         "GameRomHorseSaddle_03", "Weapon_Shield_022", "Obj_Maracas", "Obj_ProofKorok", "PlayerStole2",
         # the champion abilities' "+" (the second Progressive copy: it replaces the first, as the Champions' Ballad
         # does), then the runes and their "+" (quest_rewards.py: the game no longer gives them itself)
         "Obj_DLC_HeroSoul_Zora", "Obj_DLC_HeroSoul_Rito", "Obj_DLC_HeroSoul_Goron", "Obj_DLC_HeroSoul_Gerudo",
         "Obj_RemoteBomb", "Obj_RemoteBombLv2", "Obj_StopTimer", "Obj_StopTimerLv2", "Obj_SheikSensor",
         "Obj_SheikSensorLv2", "Obj_Magnetglove", "Obj_IceMaker"]
# flags no event reads (where the game's own rune gifts used to go) and none sets (offers that tested a "+" rune)
VOID, NEVER = "AP_Void", "AP_Never"
PENDING, DONE = "AP_Pending", "AP_Done"
QFLAGS = [f"AP_Q{i + 1}" for i in range(len(ITEMS))]
FLOW = "Archipelago"


class Flow:
    def __init__(self, fc):
        self.fc = fc

    def actor(self, name, actions=(), queries=()):
        a = next((a for a in self.fc.actors if a.identifier.name == name and not a.identifier.sub_name), None)
        if a is None:
            a = Actor()
            a.identifier = ActorIdentifier(name)
            a.params = Container()
            a.params.data.update({"CreateMode": 0, "IsGrounding": False, "IsWorld": False, "PosX": 0.0, "PosY": 0.0,
                                  "PosZ": 0.0, "RotX": 0.0, "RotY": 0.0, "RotZ": 0.0})
            self.fc.actors.append(a)
        for n in actions:
            if not any(str(x) == n for x in a.actions):
                a.actions.append(StringHolder(n))
        for n in queries:
            if not any(str(x) == n for x in a.queries):
                a.queries.append(StringHolder(n))
        return a

    def _add(self, data):
        e = Event()
        e.data = data
        n = len(self.fc.events)
        while any(x.name == f"AP{n}" for x in self.fc.events):
            n += 1
        e.name = f"AP{n}"
        self.fc.events.append(e)
        return e

    def action(self, actor, name, params, nxt=None):
        a = self.actor(actor, actions=[name])
        d = ActionEvent()
        d.actor, d.actor_action = make_rindex(a), make_rindex(a.find_action(name))
        d.params = Container()
        d.params.data.update(params)
        d.nxt = make_index(nxt)
        return self._add(d)

    def switch(self, actor, query, params, cases):
        a = self.actor(actor, queries=[query])
        d = SwitchEvent()
        d.actor, d.actor_query = make_rindex(a), make_rindex(a.find_query(query))
        d.params = Container()
        d.params.data.update(params)
        d.cases = {k: make_rindex(v) for k, v in cases.items()}
        return self._add(d)

    def subflow(self, flow, entry, params, nxt=None):
        d = SubFlowEvent()
        d.res_flowchart_name, d.entry_point_name = flow, entry
        d.params = Container()
        d.params.data.update(params)
        d.nxt = make_index(nxt)
        return self._add(d)

    def entry(self, name, first):
        ep = EntryPoint(name)
        ep.main_event = make_index(first)
        self.fc.entry_points.append(ep)


def flow_bytes(f):
    import io
    s = io.BytesIO()
    f.write(s)
    return s.getvalue()


def dispatch_flow():
    f = evfl.EventFlow()
    f.name = FLOW
    f.flowchart = evfl.flowchart.Flowchart()
    f.flowchart.name = FLOW
    fl = Flow(f.flowchart)
    esa = "EventSystemActor"
    # (AP_Done before AP_Pending goes off: the client never sees both off unless a load cleared them; nothing set
    # (a start asked for again): AP_Pending off only, so no delivery is reported)
    clear = fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": PENDING})
    done = fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": DONE}, clear)
    nxt_check = clear
    for i in reversed(range(len(ITEMS))):
        actor = ITEMS[i]
        off = fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": QFLAGS[i]}, done)
        after = off
        if actor == "Obj_HeartUtuwa_A_01":
            after = fl.action(esa, "Demo_StartLifeUpDemo", {"IsWaitFinish": True},
                              fl.action(esa, "Demo_WaitUntilLifeUpDemoEnd", {"IsWaitFinish": True}, off))
        elif actor == "Obj_StaminaUtuwa_A_01":
            after = fl.action(esa, "Demo_StartStaminaUpDemo", {"IsWaitFinish": True},
                              fl.action(esa, "Demo_WaitForStaminaUpDemoEnd", {"IsWaitFinish": True}, off))
        elif actor.startswith("Obj_DLC_HeroSoul_"):  # (the ability it improves leaves the pouch, as in Demo622)
            after = fl.action(esa, "Demo_DeletePorchItemInEquip", {"IsWaitFinish": True, "DeleteNum": -1,
                              "PorchItemName": actor.replace("DLC_", "")}, off)
        give = fl.subflow("GetDemo", "GetItemByName", {"CheckTargetActorName": actor, "IsInvalidOpenPouch": False}, after)
        nxt_check = fl.switch(esa, "CheckFlag", {"FlagName": QFLAGS[i]}, {1: give, 0: nxt_check})
    fl.entry("AP_Dispatch", nxt_check)
    return f


def to_byml(x):
    if isinstance(x, dict):
        h = oead.byml.Hash()
        for k, v in x.items():
            h[k] = to_byml(v)
        return h
    if isinstance(x, list):
        a = oead.byml.Array()
        for v in x:
            a.append(to_byml(v))
        return a
    return x


def s32(v):
    return oead.S32(v if v < 0x80000000 else v - 0x100000000)


def rstb_update(raw, sizes):
    """The size table (Yaz0) with each {resource path: bytes} at least that big; a new path gets an entry, in crc order"""
    r = bytearray(oead.yaz0.decompress(raw))
    cnt = struct.unpack_from("<I", r, 4)[0]
    by = {struct.unpack_from("<I", r, 12 + 8 * k)[0]: 12 + 8 * k for k in range(cnt)}
    for path, need in sizes.items():
        crc = zlib.crc32(path.encode())
        at = by.get(crc)
        if at is None:
            k = sum(1 for c in by if c < crc)
            r[12 + 8 * k:12 + 8 * k] = struct.pack("<II", crc, need)
            cnt += 1
            struct.pack_into("<I", r, 4, cnt)
            by = {struct.unpack_from("<I", r, 12 + 8 * j)[0]: 12 + 8 * j for j in range(cnt)}
        elif struct.unpack_from("<I", r, at + 4)[0] < need:
            struct.pack_into("<I", r, at + 4, need)
    return oead.yaz0.compress(bytes(r))


def pack_statics(aoc, out):
    """The overworld's static units are read from AocMainField.pack, not the loose files: every static unit this or
    an earlier tool (strip_rewards.py) wrote goes into the overlay's copy of the pack, compressed (the pack is read
    whole: its size counts)"""
    rel = "Pack/AocMainField.pack"
    pack = oead.Sarc(open(os.path.join(aoc, rel), "rb").read())
    w = oead.SarcWriter.from_sarc(pack)
    n = 0
    base = os.path.join(out, "aoc/0010/Map/MainField")
    for tile in sorted(os.listdir(base)):
        f = os.path.join(base, tile, f"{tile}_Static.smubin")
        name = f"Map/MainField/{tile}/{tile}_Static.smubin"
        if os.path.exists(f) and name in w.files:
            data = open(f, "rb").read()  # (stored uncompressed by the map tools)
            w.files[name] = oead.yaz0.compress(nin.yaz0(data), data_alignment=struct.unpack_from(">I", data, 8)[0])
            n += 1
    p = os.path.join(out, "aoc/0010", rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as fh:
        fh.write(w.write()[1])
    print(f"{n} static units packed into {rel}")


def main(ex, out):
    romfs, aoc = os.path.join(ex, "romfs"), os.path.join(ex, "aoc1")

    def src(rel, base=romfs, prefix=""):
        p = os.path.join(out, prefix + rel)
        return open(p if os.path.exists(p) else os.path.join(base, rel), "rb").read()

    def put(rel, data):
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    sizes = {}
    # the event
    f = dispatch_flow()
    w = oead.SarcWriter(oead.Endianness.Little)
    w.files[f"EventFlow/{FLOW}.bfevfl"] = flow_bytes(f)
    pack = w.write()[1]
    align = struct.unpack_from(">I", open(os.path.join(romfs, "Event", "SignalFlowchart.sbeventpack"), "rb").read(), 8)[0]
    put(f"Event/{FLOW}.sbeventpack", oead.yaz0.compress(pack, data_alignment=align))
    sizes[f"Event/{FLOW}.beventpack"] = len(pack) + 0x1000
    sizes[f"EventFlow/{FLOW}.bfevfl"] = len(w.files[f"EventFlow/{FLOW}.bfevfl"]) + 0x1000
    # Bootup.pack: the flags (not saved) and the events' registration
    boot = oead.Sarc(src("Pack/Bootup.pack"))
    bw = oead.SarcWriter.from_sarc(boot)
    gd = oead.Sarc(oead.yaz0.decompress(bytes(boot.get_file("GameData/gamedata.ssarc").data)))
    gw = oead.SarcWriter.from_sarc(gd)
    name = next(f.name for f in gd.get_files() if "bool_data" in f.name)
    b = oead.byml.from_binary(bytes(gd.get_file(name).data))
    have = {str(e["DataName"]) for e in b["bool_data"]}
    for fl in [PENDING, DONE, VOID, NEVER] + QFLAGS:
        if fl not in have:
            b["bool_data"].append(to_byml({
                "DataName": fl, "DeleteRev": s32(0xFFFFFFFF), "HashValue": s32(zlib.crc32(fl.encode())),
                "InitValue": s32(0), "IsEventAssociated": False, "IsOneTrigger": False, "IsProgramReadable": True,
                "IsProgramWritable": True, "IsSave": False, "MaxValue": True, "MinValue": False, "ResetType": s32(0)}))
    gw.files[name] = oead.byml.to_binary(b, big_endian=False, version=2)
    gdata = gw.write()[1]
    bw.files["GameData/gamedata.ssarc"] = oead.yaz0.compress(gdata)
    sizes["GameData/gamedata.sarc"] = len(gdata) + 0x1000
    ei = oead.byml.from_binary(oead.yaz0.decompress(bytes(boot.get_file("Event/EventInfo.product.sbyml").data)))
    ei[f"{FLOW}<AP_Dispatch>"] = to_byml({"is_startable_air": True, "is_timeline": False, "mode": "Seamless",
                                          "subfile": [{"file": "GetDemo.bfevfl"}]})
    eib = oead.byml.to_binary(ei, big_endian=False, version=2)
    bw.files["Event/EventInfo.product.sbyml"] = oead.yaz0.compress(eib)
    sizes["Event/EventInfo.product.byml"] = len(eib) + 0x1000
    put("Pack/Bootup.pack", bw.write()[1])
    pack_statics(aoc, out)
    # the size table (the overlay's own: ap_item.py made one)
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(rel, rstb_update(src(rel), sizes))
    print(f"give trigger: {len(ITEMS)} items, event {FLOW}<AP_Dispatch>")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
