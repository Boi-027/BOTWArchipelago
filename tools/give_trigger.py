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
import re
import struct
import sys
import zlib

import evfl
import oead
from evfl import Container, EntryPoint, Event
from evfl.actor import Actor
from evfl.common import ActorIdentifier, StringHolder
from evfl.event import ActionEvent, ForkEvent, JoinEvent, SubFlowEvent, SwitchEvent
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
# the runes the plateau's terminals and Purah download into the Slate (Demo003_0, Demo032_0): ItemType, IsPowerUp
RUNE_DOWNLOAD = {"Obj_RemoteBomb": (0, False), "Obj_RemoteBombLv2": (0, True), "Obj_Magnetglove": (1, False),
                 "Obj_StopTimer": (2, False), "Obj_StopTimerLv2": (2, True), "Obj_IceMaker": (3, False)}
DEMOS = len(ITEMS)  # (worlds/botw/items.py: "!msg <n>" counts on from here)
assert DEMOS == 32, "worlds/botw/items.py's DEMOS"


def banners():
    """[(item name, banner text, event actions before it)] in worlds/botw/items.py's BANNERS order: AP_Q<DEMOS + 1>...
    The game's own centred message (Demo_OpenDungeonMessage), as the Champions' Ballad's and Waikuteru's randomizer's"""
    import ast
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worlds", "botw", "items.py"),
               encoding="utf8").read()
    names = next(ast.literal_eval(n.value) for n in ast.parse(src).body
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "BANNERS")
    out = []
    for n in names:
        text, acts = BANNER_TEXT.get(n, (f"You got {n}!", []))
        if isinstance(acts, str):  # (a flag: the event turns it on, the client off again later)
            acts = [("Demo_FlagON", {"IsWaitFinish": True, "FlagName": acts})]
        out.append((n, text, acts))
    return out


# a trap's or effect's words (and what the event does first); every other item: "You got <name>!"
BANNER_TEXT = {
    "Thunderstorm Trap": ("A thunderstorm is rolling in!", []), "Midnight Trap": ("Night has fallen...", []),
    "Blizzard Trap": ("A blizzard is sweeping in!", []), "Downpour Trap": ("The skies have opened up!", []),
    "No Warping Trap": ("Warping is now disabled", []), "No Saving Trap": ("Saving is now disabled", []),
    "Hunger Trap": ("Eating is now disabled", []), "Ouch Trap": ("Ouch! Half your hearts are gone", []),
    "Rupee Drain Trap": ("50 rupees went missing...", []), "Warp Trap": ("You're being whisked away!", []),
    "Full Recovery": ("Your hearts are fully restored", [("Demo_RecoverPlayerLife", {"IsWaitFinish": True})]),
    "Heat Trap": ("A heat wave is scorching Hyrule!", []),
    "Cold Trap": ("A cold snap is freezing Hyrule!", []),
    "Fire Trap": ("The air is hot enough to burn!", []),
    "Fog Trap": ("A thick fog is rolling in...", []),
    "Darkness Trap": ("Darkness is falling over Hyrule...", []),
    "Bokoblin Trap": ("Bokoblins are on the prowl!", []),
    "Moblin Trap": ("Moblins are on the prowl!", []),
    "Lynel Trap": ("Lynels are on the hunt!", []),
    "Thief Trap": ("A thief went through your pouch!", []),
    "Blood Moon Trap": ("The Blood Moon is rising...", []),
    # (a rune: the Slate's download, as the Final Trial's Demo645_0 has it - ItemType 5 - then a message and the menu
    # closed, as the runes' scenes; its flag after. shortcut: the download screen doesn't show out here (waiting on it
    # soft-locks: the rune menu never gets the motorcycle's slot), so this is the banner only; find what Demo645_0
    # sets up first to have the real animation)
    "Master Cycle Zero": ("You got Master Cycle Zero!", [
        ("Demo_FlagON", {"IsWaitFinish": True, "FlagName": "IsDownloadDemo"}),
        ("Demo_OpenItemDownloadDemo", {"IsWaitFinish": False, "ItemType": 5, "IsEquip": True, "IsPowerUp": False,
                                       "IsPlayerClose": False}),
        ("Demo_WaitFrame", {"IsWaitFinish": True, "Frame": 70}),
        ("Demo_OpenMessageDialog", {"IsCloseMessageDialog": True, "IsWaitFinish": True, "ASName": "",
                                    "IsOverWriteLabelActorName": False, "CloseDialogOption": 0,
                                    "MessageOpenDelayTime": 0, "IsWaitAS": False, "IsBecomingSpeaker": False,
                                    "MessageId": "EventFlowMsg/Archipelago:RuneDownload"}),
        ("Demo_CloseItemMenu", {"IsWaitFinish": True}),
        ("Demo_FlagON", {"IsWaitFinish": True, "FlagName": "IsGet_Obj_Motorcycle"})]),
}

# The environment traps: the game's own ChangeWeatherTag (what the overworld's mountains, the desert's storm and the
# Divine Beasts set their weather and temperature with), wired as the map wires its own: an Area around Link and a link
# tag that reads the trap's flag both signal an AND link tag, and that signals the weather tag. A link tag only sees a
# flag an event changed, so the client never sets these itself: it sets AP_Want_<flag> and has the event's sync entry
# (SYNC below) copy every want onto its flag (runtime/ui/ap_client.mm). The overworld's static map units are loaded
# whole, so one set in one of them works everywhere (the Area covers the map); link tags do nothing in the dynamic
# units, and the static pack can't grow much (a set in every tile crashed the game). 99999.9: the temperature isn't
# changed, -1: nor that setting.
KEEP = 99999.9
ENV_TRAPS = True
ENV_TILE = "I-8"  # (as Waikuteru's randomizer's: an out-of-the-way corner)
SPAWN_TRAPS = True
ENV = {  # flag: (PaletteSel, Weather, WeatherEff, IgnitedLevel, temperature)
    "AP_Env_Heat": (-1, 0, 2, 0, 50.0),   # (the desert's day is about 40)
    "AP_Env_Cold": (-1, 4, 2, 0, -15.0),  # (snow; Hebra's peaks are about -20)
    "AP_Env_Fire": (-1, -1, -1, 1, KEEP),  # (as on Death Mountain's summit: Link and the grass catch fire)
    "AP_Env_Fog": (8, -1, -1, 0, KEEP),   # (the desert storm's palette: a thick yellow haze)
    "AP_Env_Dark": (45, -1, 0, 0, KEEP),  # (a dark blue, starry gloom; the Lost Woods' 7 turns the screen black)
}

# The enemy traps: these join every area's wildlife the overworld's spawns pick from (Ecosystem/AreaData's Animal
# lists), and the game's own spawn event for them (AutoPlacement_Animal) makes them only while the flag is on (none
# on the Great Plateau before the paraglider: the game holds its spawns back there).
# None of them is in a vanilla spawn event (the Lizalfos and Keese are: they'd spawn always). Their weapons: what the
# map gives that enemy most.
SPAWNS = {"AP_Spawn_Bokoblin": (["Enemy_Bokoblin_Junior", "Enemy_Bokoblin_Middle", "Enemy_Bokoblin_Senior"], 2),
          "AP_Spawn_Moblin": (["Enemy_Moriblin_Junior", "Enemy_Moriblin_Middle"], 1),
          "AP_Spawn_Lynel": (["Enemy_Lynel_Junior"], 1)}  # (the enemies, how many at most in a group)
MSG_FILE = "Archipelago"  # (EventFlowMsg/Archipelago.msbt: the banners' words, labels Banner<k>)

# flags no event reads (where the game's own rune gifts used to go) and none sets (offers that tested a "+" rune)
VOID, NEVER = "AP_Void", "AP_Never"
PENDING, DONE = "AP_Pending", "AP_Done"
QFLAGS = [f"AP_Q{i + 1}" for i in range(DEMOS + 96)]  # (the banners: up to 95)
SYNC = len(QFLAGS)  # (AP_Q128: every AP_Want_<flag> onto its flag, the environment and enemy traps'; no banner)
# the quest log's Archipelago quests (tools/quest_log.py): shown once their first step's flag is on; saved, and set
# through the sync entry too (the quest log, as the map's link tags, may only see a flag an event changed). They are
# quests the game declares flags for but never shipped (their <quest>_Ready already on: a quest only shows with it;
# TurnTestQuest as EIdras' BOTW-Archipelago uses it): Hints, Goal. The log shows quest_log.py's titles.
QUESTS = ["PrezentationOkamura", "TurnTestQuest"]
QUEST_FLAGS = [f"{q}_Activated" for q in QUESTS]
WANTS = list(ENV) + list(SPAWNS) + QUEST_FLAGS


def _item_writes(op):
    """the flags received items write ("!set <flag>" / "!add <flag>" in worlds/botw/items.py)"""
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worlds", "botw", "items.py"),
               encoding="utf8").read()
    names = set(re.findall(rf'"{op} (\w+) ', src)) | set(re.findall(rf'"{op} (AP_Region_)\{{i:02d\}}', src))
    out = set()
    for n in names:
        out |= {f"AP_Region_{i:02d}" for i in range(15)} if n == "AP_Region_" else {n}
    return sorted(out)


# What items write into the game data is saved only when an event sets it: the client writes it, and its want, and
# the sync entry (AP_Q128) sets the flag from the want - KEEP_ON: turned on (never off: the want is 0 after a load);
# KEEP_INT: the number copied, when its AP_Set_<flag> is on
KEEP_ON = _item_writes("!set")
KEEP_INT = [f for f in _item_writes("!add") if f != "CurrentHart"]  # (the hearts Link has now: not a stale copy)
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
    CALC = "GameDataCalcMachine"  # (the game's own events copy numbers with it: 100enemy)
    # (AP_Done before AP_Pending goes off: the client never sees both off unless a load cleared them; nothing set
    # (a start asked for again): AP_Pending off only, so no delivery is reported)
    clear = fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": PENDING})
    done = fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": DONE}, clear)
    # (every run ends committing the client's count of items given into the save's AP_Given: only what an event sets
    # is saved - a scene and the count of it go together, tools/shop_sanity.py)
    # (only once the client has its count right since the last load - AP_Set_Given, not saved: a want of 0 after a load
    # isn't copied over the save's)
    done = fl.switch(esa, "CheckFlag", {"FlagName": "AP_Set_Given"}, {1: fl.action(
        CALC, "Demo_GameDataCopyInt", {"IsWaitFinish": True, "GameDataIntSrcName": "AP_Want_Given",
                                      "GameDataIntDstName": "AP_Given"}, done), 0: done})
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
        if actor in RUNE_DOWNLOAD:  # (the item-get scene only sets a rune's flag: the Slate's download puts it in the pouch)
            kind, plus = RUNE_DOWNLOAD[actor]  # (as Demo003_0 has it: the download, a moment, the item menu it opened closed)
            give = fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": "IsDownloadDemo"}, fl.action(
                esa, "Demo_OpenItemDownloadDemo", {"IsWaitFinish": False, "ItemType": kind, "IsEquip": True,
                                                   "IsPowerUp": plus, "IsPlayerClose": False},
                # (then a message, closed, as the game's own downloads have it: without one the item menu stayed open
                # out in the world - a soft lock at Stasis +)
                fl.action(esa, "Demo_WaitFrame", {"IsWaitFinish": True, "Frame": 70},
                          fl.action(esa, "Demo_OpenMessageDialog", {
                              "IsCloseMessageDialog": True, "IsWaitFinish": True, "ASName": "",
                              "IsOverWriteLabelActorName": False, "CloseDialogOption": 0, "MessageOpenDelayTime": 0,
                              "IsWaitAS": False, "IsBecomingSpeaker": False,
                              "MessageId": f"EventFlowMsg/{MSG_FILE}:RuneDownload"},
                              fl.action(esa, "Demo_CloseItemMenu", {"IsWaitFinish": True},
                                        fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": "IsGet_" + actor},
                                                  after))))))
        else:
            give = fl.subflow("GetDemo", "GetItemByName", {"CheckTargetActorName": actor, "IsInvalidOpenPouch": False},
                              after)
        nxt_check = fl.switch(esa, "CheckFlag", {"FlagName": QFLAGS[i]}, {1: give, 0: nxt_check})
    for k, (name, text, acts) in reversed(list(enumerate(banners()))):
        i = DEMOS + k
        off = fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": QFLAGS[i]}, done)
        first = fl.action(esa, "Demo_OpenDungeonMessage", {"IsWaitFinish": True,
                                                           "MessageId": f"EventFlowMsg/{MSG_FILE}:Banner{k}"}, off)
        for a, params in reversed(acts):  # ("Actor.Action": another actor's; else the event system's)
            actor, _, a = a.rpartition(".")
            first = fl.action(actor or esa, a, params, first)
        nxt_check = fl.switch(esa, "CheckFlag", {"FlagName": QFLAGS[i]}, {1: first, 0: nxt_check})
    off = fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": QFLAGS[SYNC - 1]}, done)
    for flag in reversed(KEEP_INT):  # (a received item's number: the client's value, so the save has it)
        copy_ = fl.action(CALC, "Demo_GameDataCopyInt", {"IsWaitFinish": True, "GameDataIntSrcName": f"AP_Want_{flag}",
                                                        "GameDataIntDstName": flag},
                        fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": f"AP_Set_{flag}"}, off))
        off = fl.switch(esa, "CheckFlag", {"FlagName": f"AP_Set_{flag}"}, {1: copy_, 0: off})
    for flag in reversed(KEEP_ON):  # (a received item's flag: on, so the save has it)
        on_ = fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": flag}, off)
        off = fl.switch(esa, "CheckFlag", {"FlagName": f"AP_Want_{flag}"}, {1: on_, 0: off})
    for flag in reversed(WANTS):  # (each flag as its want: changed by the event, so the map's link tags see it)
        on_ = fl.action(esa, "Demo_FlagON", {"IsWaitFinish": True, "FlagName": flag}, off)
        if flag in QUEST_FLAGS:  # (a quest starts as the game's own do: its first step, then its flag - once:
            # advancing again would finish it)
            on_ = fl.action(esa, "Demo_AdvanceQuest", {"IsWaitFinish": True, "QuestName": flag[:-len("_Activated")],
                                                       "StepName": "", "ForceRunTelop": False}, on_)
            on_ = fl.switch(esa, "CheckFlag", {"FlagName": flag}, {1: off, 0: on_})
        off_ = (off if flag in QUEST_FLAGS else  # (a quest once shown stays: its want resets with every load)
                fl.action(esa, "Demo_FlagOFF", {"IsWaitFinish": True, "FlagName": flag}, off))
        off = fl.switch(esa, "CheckFlag", {"FlagName": f"AP_Want_{flag}"}, {1: on_, 0: off_})
    nxt_check = fl.switch(esa, "CheckFlag", {"FlagName": QFLAGS[SYNC - 1]}, {1: off, 0: nxt_check})
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


def env_tags(ex, out, sizes):
    """ENV's weather tags, wired to their flags and to an Area over the whole map, into ENV_TILE's static unit (the
    overlay's copy if a tool wrote one), at its middle"""
    import byml
    from shops import field_units
    units = [(tile, rel, raw) for tile, kind, rel, raw in field_units(ex) if rel]
    used = {o["HashId"] for _, _, raw in units for o in nin.byml(raw).get("Objs", [])}

    def new_hash(seed):
        h = zlib.crc32(seed.encode())
        while h in used or h == 0:
            h = (h + 1) & 0xFFFFFFFF
        used.add(h)
        return byml.U32(h)

    def sig(dest):  # (as the map's own: a signal, no demo member)
        return {"!Parameters": {"NoAutoDemoMember": False}, "DefinitionName": "BasicSig", "DestUnitHashId": dest}

    def link_tag(h, dest, pos, flag=None):
        p = {"IncrementSave": False, "MakeSaveFlag": byml.S32(0), "NoChangeSignal": False,
             "SaveFlagOnOffType": byml.S32(0)}
        if flag:
            p["SaveFlag"] = flag
        return {"!Parameters": p, "HashId": h, "LinksToObj": [sig(dest)], "SRTHash": byml.S32(0), "Translate": pos,
                "UnitConfigName": "LinkTagAnd"}

    for tile, rel, raw in units:
        if not rel.endswith(f"/{ENV_TILE}/{ENV_TILE}_Static.smubin"):
            continue
        p = os.path.join(out, rel)
        raw = open(p, "rb").read() if os.path.exists(p) else raw
        d = nin.yaz0(raw)
        m = byml.read(d)
        objs = m.setdefault("Objs", [])
        ys = sorted(float(o["Translate"][1]) for o in objs if "Translate" in o) or [200.0]
        x, y, z = -4500.0 + 1000 * (ord(tile[0]) - ord("A")), ys[len(ys) // 2], -3500.0 + 1000 * (int(tile[2:]) - 1)
        area = {"!Parameters": {"AutoSave": False, "CameraPriority": byml.S32(1), "CameraSet": "-",
                                "ForceCalcInEvent": False, "Shape": "Sphere"},
                "HashId": new_hash(f"{tile}/area"), "LinksToObj": [], "SRTHash": byml.S32(0),
                "Scale": byml.F32(12000.0),  # (from any tile's middle to the farthest corner of the map)
                "Translate": [byml.F32(x), byml.F32(y), byml.F32(z)], "UnitConfigName": "Area"}
        objs.append(area)
        for k, (flag, (pal, weather, eff, ignite, temp)) in enumerate(ENV.items()):
            pos = lambda dy: [byml.F32(x + 2 * k), byml.F32(y + dy), byml.F32(z)]
            tag, both = new_hash(f"{tile}/{flag}/weather"), new_hash(f"{tile}/{flag}/and")
            objs.append({"!Parameters": {"BluffThunderOff": False, "CloudShadowOff": False,
                                         "FogMinusCorrection": False, "IgnitedLevel": byml.S32(ignite),
                                         "PSelSpeed": byml.S32(0), "PaletteSel": byml.S32(pal),
                                         "TemperatureDay": byml.F32(temp), "TemperatureDirectDay": byml.F32(temp),
                                         "TemperatureDirectNight": byml.F32(temp), "TemperatureNight": byml.F32(temp),
                                         "Weather": byml.S32(weather), "WeatherEff": byml.S32(eff)},
                         "HashId": tag, "SRTHash": byml.S32(0), "Translate": pos(4), "UnitConfigName": "ChangeWeatherTag"})
            objs.append(link_tag(both, tag, pos(2)))
            objs.append(link_tag(new_hash(f"{tile}/{flag}/flag"), both, pos(0), flag))
            area["LinksToObj"].append(sig(both))
        objs.sort(key=lambda o: o["HashId"] & 0xFFFFFFFF)
        new = byml.write(m, struct.unpack_from("<H", d, 2)[0])
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(nin.yaz0_store(new, struct.unpack_from(">I", raw, 8)[0]) if raw[:4] == b"Yaz0" else new)
        name = ("Aoc/0010/" + rel[len("aoc/0010/"):]) if rel.startswith("aoc/0010/") else rel
        sizes[name.replace(".smubin", ".mubin")] = len(new) + 0x1000


def spawn_weapons(ex):
    """{enemy: [(EquipItem1[,EquipItem2], how often)]}: the six the overworld's map gives each of SPAWNS' most"""
    import collections
    from shops import field_units
    want = {e for es, _ in SPAWNS.values() for e in es}
    c = collections.defaultdict(collections.Counter)
    for _, _, _, raw in field_units(ex):
        for o in nin.byml(raw).get("Objs", []):
            if o.get("UnitConfigName") in want:
                p = o.get("!Parameters") or {}
                w = [p[k] for k in ("EquipItem1", "EquipItem2") if str(p.get(k, "Default")) not in ("Default", "")]
                if w:
                    c[o["UnitConfigName"]][",".join(w)] += 1
    return {e: c[e].most_common(6) for e in want}


def spawn_edit(ex, files, sizes):
    """SPAWNS into Bootup.pack's {name: bytes}: every area's Enemy list, and the spawn event's gated branches"""
    weapons = spawn_weapons(ex)
    raw = files["Ecosystem/AreaData.sbyml"]
    areas = oead.byml.from_binary(nin.yaz0(raw))
    for a in areas:  # (the Animal lists, as Waikuteru's big enemies: from the Enemy lists too, a crowd swarmed Link)
        for kind in ("Animal",):
            if not isinstance(a.get(kind), oead.byml.Array):  # (missing, or an empty string)
                a[kind] = oead.byml.Array()
            for es, _ in SPAWNS.values():
                for e in es:
                    a[kind].append(to_byml({"name": e, "num": oead.F32(1.0), "weapons": [
                        {"name": w, "prob": oead.F32(float(n))} for w, n in weapons[e]]}))
    data = oead.byml.to_binary(areas, big_endian=False, version=2)
    files["Ecosystem/AreaData.sbyml"] = oead.yaz0.compress(data) if raw[:4] == b"Yaz0" else data
    sizes["Ecosystem/AreaData.byml"] = len(data) + 0x1000
    # the overworld's spawns as Link travels (the Animal lists' event; the game's NearCreate branch - near him, on flat
    # dry ground, not while he rides - is kept for other events)
    for name, near in (("EventFlow/AutoPlacement_Animal.bfevfl", False),):
        f = evfl.EventFlow()
        f.read(files[name])
        fl = Flow(f.flowchart)
        root = f.flowchart.entry_points[0].main_event.v
        if not isinstance(root.data, ForkEvent):  # (the Animal event starts with a check: a fork before it, as Waikuteru's)
            join = fl._add(JoinEvent())
            fork = ForkEvent()
            fork.forks, fork.join = [make_rindex(root)], make_rindex(join)
            root = fl._add(fork)
            f.flowchart.entry_points[0].main_event = make_index(root)
        for flag, (es, most) in SPAWNS.items():
            first = fl.action("AutoPlacement", "CreateData", {"MinNum": 1, "MaxNum": most, "GroupRadius": 8.0,
                                                              "OffsetPosY": 0.0, "RideList": "", "Mimicry": False,
                                                              "EquipWeaponActorCount": -1})
            if near:
                first = fl.switch("AutoPlacement", "WaterDepth", {"Depth": 0.0}, {0: first})
                first = fl.switch("AutoPlacement", "GroundNorm", {"Angle": 10.0}, {1: first})
                first = fl.action("AutoPlacement", "NearCreate", {"WaitFrame": 1}, first)
                first = fl.switch("AutoPlacement", "PlayerRideHorse", {}, {0: first})
            gate = fl.switch("AutoPlacement", "CheckGameData", {"Label": flag}, {1: first})
            for e in es:
                root.data.forks.append(make_rindex(fl.switch("AutoPlacement", "EcoAreaActorName", {"ActorName": e},
                                                             {1: gate})))
        files[name] = flow_bytes(f)
        sizes[name] = len(files[name]) + 0x1000

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
    # (the first bool list is a revival one - the game's per-object flags; the spawn events' checks read the spawn
    # flags only from a plain one, as Waikuteru's randomizer keeps its own)
    first = next(f.name for f in gd.get_files() if "bool_data" in f.name)
    plain = next(f.name for f in gd.get_files() if f.name.lstrip("/").startswith("bool_data"))
    for name, flags in ((first, [PENDING, DONE, VOID, NEVER, "AP_GoalReady"] + QFLAGS + list(ENV) + [f"AP_Want_{w}" for w in WANTS + KEEP_ON]
                         + [f"AP_Set_{f}" for f in KEEP_INT + ["Given"]]),
                        (plain, list(SPAWNS))):  # (the quests' own flags: the game has them, saved)
        b = oead.byml.from_binary(bytes(gw.files[name] if name in gw.files else gd.get_file(name).data))
        have = {str(e["DataName"]) for e in b["bool_data"]}
        for fl in flags:
            if fl not in have:
                b["bool_data"].append(to_byml({
                    "DataName": fl, "DeleteRev": s32(0xFFFFFFFF), "HashValue": s32(zlib.crc32(fl.encode())),
                    "InitValue": s32(0), "IsEventAssociated": False, "IsOneTrigger": False, "IsProgramReadable": True,
                    "IsProgramWritable": True, "IsSave": False, "MaxValue": True, "MinValue": False,
                    "ResetType": s32(0)}))
        gw.files[name] = oead.byml.to_binary(b, big_endian=False, version=2)
    # (the numbers' wants: not saved)
    s32n = next(f.name for f in gd.get_files() if f.name.startswith("/s32_data"))
    b = oead.byml.from_binary(bytes(gw.files[s32n] if s32n in gw.files else gd.get_file(s32n).data))
    have = {str(e["DataName"]) for e in b["s32_data"]}
    for fl in [f"AP_Want_{f}" for f in KEEP_INT]:
        if fl not in have:
            b["s32_data"].append(to_byml({
                "DataName": fl, "DeleteRev": s32(0xFFFFFFFF), "HashValue": s32(zlib.crc32(fl.encode())),
                "InitValue": s32(0), "IsEventAssociated": False, "IsOneTrigger": False, "IsProgramReadable": True,
                "IsProgramWritable": True, "IsSave": False, "MaxValue": s32(999999), "MinValue": s32(0),
                "ResetType": s32(0)}))
    gw.files[s32n] = oead.byml.to_binary(b, big_endian=False, version=2)
    gdata = gw.write()[1]
    bw.files["GameData/gamedata.ssarc"] = oead.yaz0.compress(gdata)
    sizes["GameData/gamedata.sarc"] = len(gdata) + 0x1000
    ei = oead.byml.from_binary(oead.yaz0.decompress(bytes(boot.get_file("Event/EventInfo.product.sbyml").data)))
    ei[f"{FLOW}<AP_Dispatch>"] = to_byml({"is_startable_air": True, "is_timeline": False, "mode": "Seamless",
                                          "subfile": [{"file": "GetDemo.bfevfl"}]})
    eib = oead.byml.to_binary(ei, big_endian=False, version=2)
    bw.files["Event/EventInfo.product.sbyml"] = oead.yaz0.compress(eib)
    sizes["Event/EventInfo.product.byml"] = len(eib) + 0x1000
    spawn = {k: bytes(boot.get_file(k).data) for k in ("Ecosystem/AreaData.sbyml",
                                                        "EventFlow/AutoPlacement_Animal.bfevfl")}
    if SPAWN_TRAPS:
        spawn_edit(ex, spawn, sizes)
    for k, v in spawn.items():
        bw.files[k] = v
    put("Pack/Bootup.pack", bw.write()[1])
    # the banners' words, in the English message files (the game's empty Dummy.msbt as the start)
    from ap_item import LANGS, msbt_add
    bn = banners()
    assert len(bn) < SYNC - DEMOS, "more banners than flags"
    for lang in LANGS:
        rel = f"Pack/Bootup_{lang}.pack"
        pack_raw = src(rel)
        pack = nin.sarc(pack_raw)
        mkey = f"Message/Msg_{lang}.product.ssarc"
        msg = nin.sarc(pack[mkey])
        msg[f"EventFlowMsg/{MSG_FILE}.msbt"] = msbt_add(
            msg["EventFlowMsg/Dummy.msbt"], {**{f"Banner{k}": text for k, (_, text, _) in enumerate(bn)},
                                               "RuneDownload": "Downloaded to the Sheikah Slate.",
                                               "SanctumSealed": "The sanctum is sealed. Return when your goal is complete."})
        msg_new = nin.sarc_write(msg, nin.sarc_aligns(pack[mkey]))
        pack[mkey] = nin.yaz0_store(msg_new, struct.unpack_from(">I", pack[mkey], 8)[0])
        put(rel, nin.sarc_write(pack, nin.sarc_aligns(pack_raw)))
        sizes[f"Message/Msg_{lang}.product.sarc"] = len(msg_new) + 0x1000
    if ENV_TRAPS:
        env_tags(ex, out, sizes)
    pack_statics(aoc, out)
    # the size table (the overlay's own: ap_item.py made one)
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(rel, rstb_update(src(rel), sizes))
    print(f"give trigger: {len(ITEMS)} items, {len(banners())} banners, event {FLOW}<AP_Dispatch>")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
