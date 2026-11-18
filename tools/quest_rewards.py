"""Quests give the Archipelago Item instead of their reward: RomFS overlay files made from your own game files.

A quest's check is its last step's flag (tools/extract.py). Its reward is what an event gives around completing it:
an item-get scene (GetDemo<GetItemByName> / <GetManyItemsByName>) or rupees (Demo_IncreaseRupee) on the same path as a
Demo_FlagON of that flag or a Demo_AdvanceQuest into the last step (within REACH events either way). The scene gets
the Archipelago Item instead; rupees become 0, with an Archipelago Item scene after. A minigame's prizes (every tier,
every run) all become the Archipelago Item, the Trial of the Sword no longer powers up the Master Sword (the item
Progressive Master Sword does), and Hestu's trades add no slot (the Weapon / Bow / Shield Slot items do; the trades
send checks) and his gift is the Archipelago Item, and so is the old man's paraglider. What they gave is in the item pool (worlds/botw/items.py). Event packs
carry their own copies of the flows they use, so every copy of a changed flow is changed.

Left as they are: KEEP, and rewards picked by an argument (the caller decides the item).

Needs oead and evfl (botw_ap/.venv). Reads the overlay folder's copies first (the other tools wrote them):
    botw_ap/.venv/Scripts/python -I tools/quest_rewards.py "<Savage Wind>/extracted" <overlay folder>
"""
import glob
import os
import struct
import sys
from collections import defaultdict

import evfl
import oead
from evfl.util import make_index, make_rindex

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402
from ap_item import NAME  # noqa: E402
from give_trigger import Flow, flow_bytes, rstb_update  # noqa: E402

REACH = 30
KEEP = {
    "CompleteDungeon",   # the monks' Spirit Orb: strip_rewards.py
    "ShieldofKolog",     # the Test of Wood's gear: lent for the trial and taken back, the trial needs it
    "GanonQuest", "bf2_collabo",  # not checks
}
GIVE = ("GetItemByName", "GetManyItemsByName")


def successors(e):
    d = e.data
    n = type(d).__name__
    if n in ("ActionEvent", "SubFlowEvent", "JoinEvent"):
        return [d.nxt.v] if d.nxt.v else []
    if n == "SwitchEvent":
        return [c.v for c in d.cases.values() if c.v]
    if n == "ForkEvent":
        return [x.v for x in d.forks] + ([d.join.v] if d.join.v else [])
    return []


def reach(start):
    seen, front = set(), [(start, 0)]
    while front:
        e, dist = front.pop()
        if e.name in seen or dist > REACH:
            continue
        seen.add(e.name)
        front += [(s, dist + 1) for s in successors(e)]
    return seen


def give_scene(e):
    """the item an item-get scene gives (None: not one, or picked by an argument)"""
    d = e.data
    if type(d).__name__ == "SubFlowEvent" and d.res_flowchart_name == "GetDemo" and d.entry_point_name in GIVE:
        item = d.params.data.get("CheckTargetActorName")
        return item if isinstance(item, str) else None
    return None


def rupees(e):
    """the rupees an event gives (0: none)"""
    d = e.data
    if type(d).__name__ == "ActionEvent" and str(d.actor_action.v) == "Demo_IncreaseRupee":
        v = d.params.data.get("Value")
        return v if isinstance(v, int) and v > 0 else 0
    return 0


def is_minigame(name):
    return name.startswith("MiniGame") or name.endswith("_mini")


SWORD_POWER, SWORD_FULL = "MasterSword_Add_Power", "Open_MasterSword_FullPower"
# the runes and their "+": items now (Progressive Remote Bomb...), so the game's own gifts go nowhere - the plateau
# shrines' terminals (Demo003_0: their own flags are the checks), the Sheikah Sensor (Demo004_0, Purah's Demo032_0) and
# Purah's upgrades (Demo032_0; Hateno_SheikPad_Lv2_Total counts them: the checks)
RUNE_PLUS = ("IsGet_Obj_RemoteBombLv2", "IsGet_Obj_StopTimerLv2", "IsGet_Obj_SheikSensorLv2")
RUNE_FLAGS = ("IsGet_Obj_RemoteBomb", "IsGet_Obj_StopTimer", "IsGet_Obj_Magnetglove", "IsGet_Obj_IceMaker",
              "IsGet_Obj_SheikSensor", "IsStart_Obj_SheikSensor") + RUNE_PLUS
VOID, NEVER = "AP_Void", "AP_Never"  # (give_trigger.py adds them)
SLOTS = ("WeaponPorchStockNum", "BowPorchStockNum", "ShieldPorchStockNum")  # (Hestu's trades: what they add)


def fixed_effects(flow):
    """{event name: (what for, what)}: what the Trial of the Sword does to the Master Sword (+10 power per trial,
    awakened for good after the last) - the item Progressive Master Sword does it instead -, a slot Hestu's trade adds
    (Weapon / Bow / Shield Slot items instead) and Hestu's Gift"""
    out = {}
    for e in flow.flowchart.events:
        d = e.data
        if type(d).__name__ != "ActionEvent":
            continue
        act, p = str(d.actor_action.v), d.params.data if d.params else {}
        if act in ("Demo_SetGameDataInt", "Demo_IncreaseGameDataInt") and p.get("GameDataIntName") == SWORD_POWER:
            out[e.name] = ("100enemy", f"sword power {p.get('Value')}")
        elif act == "Demo_IncreaseGameDataInt" and p.get("GameDataIntName") in SLOTS:
            out[e.name] = ("Hestu", f"slot {p['GameDataIntName']}")
        elif act == "Demo_FlagON" and p.get("FlagName") == SWORD_FULL:
            out[e.name] = ("100enemy", "sword awakened")
        elif act == "Demo_FlagON" and p.get("FlagName") in RUNE_FLAGS:
            out[e.name] = ("Runes", "void " + p["FlagName"])
        elif act == "Demo_OpenItemDownloadDemo" and flow.name == "Demo003_0":  # (a plateau shrine's terminal: the rune it shows)
            out[e.name] = ("Runes", "rune download")
        elif act == "Demo_OpenItemDownloadDemo" and p.get("IsPowerUp"):  # (Purah's upgrade, Demo032_0: its "+" shown)
            out[e.name] = ("Runes", "rune download")
        elif act == "Demo_DeletePorchItemInEquip" and str(p.get("PorchItemName", "")).startswith("Obj_HeroSoul_"):
            out[e.name] = ("BalladOfHeroes", "keep " + p["PorchItemName"])
    for e in flow.flowchart.events:
        d = e.data
        if type(d).__name__ == "SwitchEvent" and str(d.actor_query.v) == "CheckFlag" and                 (d.params.data.get("FlagName") or "") in RUNE_PLUS:  # (Purah's offers: open until bought)
            out[e.name] = ("Runes", "never " + d.params.data["FlagName"])
        elif type(d).__name__ == "SubFlowEvent" and (d.res_flowchart_name, d.entry_point_name) ==                 ("OperationGuide", "Guide_ItemUse") and flow.name == "Demo003_0":
            out[e.name] = ("Runes", "skip rune tips")
        elif type(d).__name__ == "SwitchEvent" and str(d.actor_query.v) == "CheckFlag" and flow.name == "Demo004_0" and \
                (d.params.data.get("FlagName") or "") in ("IsGet_Obj_SheikSensor", "IsStart_Obj_SheikSensor"):
            out[e.name] = ("Runes", "skip sensor tour")
    for e in flow.flowchart.events:
        if str(give_scene(e)).startswith("Obj_DLC_HeroSoul_"):  # (the Champions' Ballad's "+": an item now)
            out[e.name] = ("BalladOfHeroes", give_scene(e))
        if give_scene(e) == "Obj_ProofKorok":
            out[e.name] = ("Hestu", "Obj_ProofKorok")
        elif give_scene(e) == "PlayerStole2":  # (the paraglider: the item Paraglider instead)
            out[e.name] = ("FindDungeon", "PlayerStole2")
    return out


def rewards(flow, flow_name, quests):
    """{event name: (quest, what it gives)} for the rewards of quests completed in this flow, and every prize of a
    minigame's own flow"""
    events = flow.flowchart.events
    if is_minigame(flow_name):
        return {e.name: (flow_name, give_scene(e)) for e in events if give_scene(e)}
    done = defaultdict(set)  # quest -> its completing events here
    for e in events:
        d = e.data
        if type(d).__name__ != "ActionEvent":
            continue
        act, p = str(d.actor_action.v), d.params.data if d.params else {}
        for q, (flag, last) in quests.items():
            if (act == "Demo_FlagON" and p.get("FlagName") == flag) or                     (act == "Demo_AdvanceQuest" and (p.get("QuestName") or flow_name) == q and p.get("StepName") == last):
                done[q].add(e.name)
    if not done:
        return {}
    out = {}
    reached = {}
    by_name = {x.name: x for x in events}
    for e in events:
        what = give_scene(e) or (f"{rupees(e)} rupees" if rupees(e) else None)
        if not what:
            continue
        after = reached.setdefault(e.name, reach(e))
        for q, names in done.items():
            if names & after or any(e.name in reached.setdefault(c, reach(by_name[c])) for c in names):
                out[e.name] = (q, what)
    return out


def main(ex, out):
    romfs, aoc = os.path.join(ex, "romfs"), os.path.join(ex, "aoc1")

    def src(rel):
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(romfs, rel), "rb").read()

    def put(rel, data):
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    title_raw = src("Pack/TitleBG.pack")
    quests = {}
    for q in nin.byml(nin.sarc(title_raw)["Quest/QuestProduct.sbquestpack"]):
        n = q["Name"]
        if n in KEEP or is_minigame(n):
            continue
        quests[n] = (q["Steps"][-1]["NextFlag"], q["Steps"][-1]["Name"])
    # the packs and their flows (the add-on content's event packs too)
    packs = [("Pack/TitleBG.pack", None)]
    for base, prefix in ((romfs, ""), (aoc, "aoc/0010/")):
        for p in sorted(glob.glob(os.path.join(base, "Event", "*.sbeventpack"))):
            packs.append((prefix + "Event/" + os.path.basename(p), base))
    def read_pack(rel, base):
        if base is None:
            return title_raw
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(base, "Event", os.path.basename(rel)), "rb").read()
    # pass 1: which events of which flows (by file name) are quest rewards
    change = {}  # flow file -> {event name: (quest, item)}
    for rel, base in packs:
        for k, v in nin.sarc(read_pack(rel, base)).items():
            if not k.endswith(".bfevfl") or k in change:
                continue
            f = evfl.EventFlow()
            f.read(v)
            found = rewards(f, os.path.basename(k)[:-7], quests)
            found.update(fixed_effects(f))
            if found:
                change[k] = found
    # pass 2: every copy of those flows
    sizes, packs_changed, by_quest = {}, 0, defaultdict(set)
    new_scene = {os.path.basename(k) for k, ev in change.items()
                 if any(w.endswith(" rupees") or w == "rune download" for _, w in ev.values())}
    for rel, base in packs:
        raw = read_pack(rel, base)
        files = nin.sarc(raw)
        mine = [k for k in files if k in change]
        if not mine:
            continue
        new_files = {}
        for k in mine:
            f = evfl.EventFlow()
            f.read(files[k])
            fl = Flow(f.flowchart)
            for e in list(f.flowchart.events):
                if e.name not in change[k]:
                    continue
                q, item = change[k][e.name]
                by_quest[q].add(item)
                if item.startswith("void "):
                    e.data.params.data["FlagName"] = VOID
                elif item.startswith("never "):
                    e.data.params.data["FlagName"] = NEVER
                elif item.startswith("keep "):  # (the item it was going to replace: the Archipelago Item instead)
                    e.data.params.data["PorchItemName"] = NAME
                elif item == "skip rune tips":  # (how to use a rune Link didn't get: whatever led here goes past)
                    for x in f.flowchart.events:
                        if hasattr(x.data, "nxt") and x.data.nxt.v is e:
                            x.data.nxt = make_index(e.data.nxt.v)
                elif item == "skip sensor tour":
                    # (a tower, Demo004_0: the first one gave the sensor and showed it off - its gauge waits for a
                    # sensor Link may not have, so the event never ended. Always the way for one he already has)
                    e.data.cases = {c: e.data.cases[1] for c in e.data.cases}
                elif item == "rune download":
                    # the rune's screen -> the Archipelago Item's scene, then what came after (a plateau terminal: after
                    # Zelda's words about the rune, which close that screen)
                    after = e.data.nxt.v
                    if f.name == "Demo003_0":
                        talk = after.data.nxt.v
                        assert str(talk.data.actor_action.v) == "Demo_OpenMessageDialog", talk.name
                        after = talk.data.nxt.v
                    ap = fl.subflow("GetDemo", "GetItemByName", {"CheckTargetActorName": NAME,
                                                                 "IsInvalidOpenPouch": False}, after)
                    for x in f.flowchart.events:
                        t = type(x.data).__name__
                        if t == "ForkEvent":
                            x.data.forks = [make_rindex(ap) if b.v is e else b for b in x.data.forks]
                        elif t == "SwitchEvent":
                            x.data.cases = {c: make_rindex(ap) if b.v is e else b for c, b in x.data.cases.items()}
                        elif hasattr(x.data, "nxt") and x.data.nxt.v is e:
                            x.data.nxt = make_index(ap)
                    for ep in f.flowchart.entry_points:
                        if ep.main_event.v is e:
                            ep.main_event = make_index(ap)
                elif item.startswith("slot "):
                    e.data.params.data["Value"] = 0
                elif item.startswith("sword power"):  # (+0: the action the flow already has for it)
                    a = fl.actor(e.data.actor.v.identifier.name, actions=["Demo_IncreaseGameDataInt"])
                    e.data.actor_action = make_rindex(a.find_action("Demo_IncreaseGameDataInt"))
                    e.data.params.data["Value"] = 0
                elif item == "sword awakened":  # (the trial's own clear flag instead: it goes on right after anyway)
                    e.data.params.data["FlagName"] = "100enemy_Clear_Senior"
                elif give_scene(e):
                    e.data.params.data["CheckTargetActorName"] = NAME
                else:  # (rupees: none, and the Archipelago Item's scene right after)
                    e.data.params.data["Value"] = 0
                    e.data.nxt = make_index(fl.subflow("GetDemo", "GetItemByName", {
                        "CheckTargetActorName": NAME, "IsInvalidOpenPouch": False}, e.data.nxt.v))
            new_files[k] = flow_bytes(f)
            sizes[k] = len(new_files[k]) + 0x800
        if base is None:  # TitleBG.pack: in place, every other file kept where it was
            for k, v in new_files.items():
                raw = nin.sarc_replace_inplace(raw, k, v)
            put(rel, raw)
        else:
            w = oead.SarcWriter.from_sarc(oead.Sarc(oead.yaz0.decompress(raw)))
            for k, v in new_files.items():
                w.files[k] = v
            data = w.write()[1]
            put(rel, oead.yaz0.compress(data, data_alignment=struct.unpack_from(">I", raw, 8)[0]))
            sizes[("Aoc/0010/" if rel.startswith("aoc/") else "") + "Event/" + os.path.basename(rel)[:-12] +
                  ".beventpack"] = len(data) + 0x1000
        packs_changed += 1
    # an event now playing the item-get scene where it didn't lists GetDemo among the flows it loads, as the game's do
    if new_scene:
        boot = oead.Sarc(src("Pack/Bootup.pack"))
        ei = oead.byml.from_binary(oead.yaz0.decompress(bytes(boot.get_file("Event/EventInfo.product.sbyml").data)))
        for key in list(ei.keys()):
            info = ei[key]
            subs = [str(x["file"]) for x in info["subfile"]] if "subfile" in info else []
            if (key.split("<")[0] + ".bfevfl" in new_scene or new_scene & set(subs)) and "GetDemo.bfevfl" not in subs:
                h = oead.byml.Hash()
                h["file"] = "GetDemo.bfevfl"
                if "subfile" not in info:
                    info["subfile"] = oead.byml.Array()
                info["subfile"].append(h)
        bw = oead.SarcWriter.from_sarc(boot)
        eib = oead.byml.to_binary(ei, big_endian=False, version=2)
        bw.files["Event/EventInfo.product.sbyml"] = oead.yaz0.compress(eib)
        sizes["Event/EventInfo.product.byml"] = len(eib) + 0x1000
        put("Pack/Bootup.pack", bw.write()[1])
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(rel, rstb_update(src(rel), sizes))
    for q in sorted(by_quest):
        print(f"  {q}: {', '.join(sorted(by_quest[q]))}")
    print(f"quest rewards: {len(by_quest)} quests, {sum(len(v) for v in change.values())} reward scenes in "
          f"{len(change)} flows, {packs_changed} packs")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
