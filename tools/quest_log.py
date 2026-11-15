"""Two side quests in the game's quest log for the multiworld: "Archipelago Hints" (every hint about your items and
your world) and "Archipelago Goal" (what the goal needs and how far along you are), at "Multiworld: <slot>".

Quests are the game's own: an entry in Quest/QuestProduct (TitleBG.pack) shown once its first step's flag is on
(<quest>_Activated: the game's own saved flags, set by the client through give_trigger.py's sync entry), its
words in QuestMsg/QL_<quest>.msbt. A quest only shows once its <quest>_Ready is on too: the two used are quests the
game declares (Ready on from the start) but never shipped - a side quest for the hints, a main quest for the goal. The words change as you play, and the game reads its message
files only once, at boot: so each changing text is a reserved slot - its words until the client is connected, the
end of the text, room up to CAP characters, then a tag the runtime finds in the game's memory and writes the live
text in front of (runtime/ui/ap_client.mm, quest_text; the same CAPs and tags there).

    python -I tools/quest_log.py "<Savage Wind>/extracted" <overlay folder>
"""
import os
import struct
import sys

import oead

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402
from ap_item import LANGS, msbt_add, put  # noqa: E402
from give_trigger import QUESTS, rstb_update, to_byml  # noqa: E402

LOCATION = "AP_Multiworld"
# (label: words before the client connects, the slot's room in characters, the runtime's tag)
HINTS, GOAL = QUESTS
SLOTS = {
    f"QL_{HINTS}_Desc": ("Connect to the multiworld to see your hints.", 1200, "<APQ:HINTS>"),
    f"QL_{GOAL}_Desc": ("Connect to the multiworld to see your goal.", 700, "<APQ:GOAL>"),
    LOCATION: ("Multiworld", 48, "<APQ:LOC>"),
}
NAMES = {HINTS: "Archipelago Hints", GOAL: "Archipelago Goal"}
TYPES = {HINTS: "Mini", GOAL: "Main"}  # (Mini: Side Quests; Sub: Shrine Quests)


def slot(label):
    text, cap, tag = SLOTS[label]
    assert len(text) < cap
    return text + "\0" + " " * (cap - len(text) - 1) + tag


def quest(name):
    return to_byml({"Location": LOCATION, "Name": name, "NotPostNote": False, "Orderer": "UnknownNPC",
                    "StepDependencyFlags": [], "Type": TYPES[name], "Steps": [
                        {"AttentionOff": False, "MessageName": "Desc", "Name": "Ready",
                         "NextFlag": f"{name}_Activated", "UpdateStep": True},
                        {"AttentionOff": False, "MessageName": "Finish", "Name": "Finish",
                         "NextFlag": f"{name}_Finish", "UpdateStep": True}]})


def main(ex, out):
    romfs = os.path.join(ex, "romfs")

    def src(rel):
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(romfs, rel), "rb").read()

    sizes = {}
    # the quests (TitleBG.pack: in place, every other file where it was - see nin.sarc_replace_inplace)
    raw = src("Pack/TitleBG.pack")
    files = nin.sarc(raw)
    name = "Quest/QuestProduct.sbquestpack"
    quests = oead.byml.from_binary(nin.yaz0(files[name]))
    have = {str(q["Name"]) for q in quests}
    for q in QUESTS:
        if q not in have:
            quests.append(quest(q))
    data = oead.byml.to_binary(quests, big_endian=False, version=2)
    put(out, "Pack/TitleBG.pack", nin.sarc_replace_inplace(raw, name, bytes(oead.yaz0.compress(data))))
    sizes["Quest/QuestProduct.bquestpack"] = len(data) + 0x1000
    # their words and the location's, in the English message files
    for lang in LANGS:
        rel = f"Pack/Bootup_{lang}.pack"
        pack_raw = src(rel)
        pack = nin.sarc(pack_raw)
        mkey = f"Message/Msg_{lang}.product.ssarc"
        msg = nin.sarc(pack[mkey])
        for q in QUESTS:
            msg[f"QuestMsg/QL_{q}.msbt"] = msbt_add(msg["EventFlowMsg/Dummy.msbt"], {
                f"QL_{q}_Name": NAMES[q], f"QL_{q}_Desc": slot(f"QL_{q}_Desc"),
                f"QL_{q}_Finish": "The multiworld is complete."})
        msg["StaticMsg/LocationMarker.msbt"] = msbt_add(msg["StaticMsg/LocationMarker.msbt"], {LOCATION: slot(LOCATION)})
        msg_new = nin.sarc_write(msg, nin.sarc_aligns(pack[mkey]))
        pack[mkey] = nin.yaz0_store(msg_new, struct.unpack_from(">I", pack[mkey], 8)[0])
        put(out, rel, nin.sarc_write(pack, nin.sarc_aligns(pack_raw)))
        sizes[f"Message/Msg_{lang}.product.sarc"] = len(msg_new) + 0x1000
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(out, rel, rstb_update(src(rel), sizes))
    print(f"quest log: {', '.join(NAMES.values())}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
