from BaseClasses import Item, ItemClassification as IC

GAME = "Breath of the Wild"
ITEM_BASE = 7_377_000_000


class BotWItem(Item):
    game = GAME


# name: (classification, give commands, copies in the pool (None = weighted filler), filler weight)
# Append only: the id is the position in this table, a reorder breaks running seeds.
# Each give is "<actor> <count>" for the Savage Wind console's give command; "!trap <kind>" is handled by the client.
# "!msg <n>": the game's banner (BANNERS below), then the actions after it.
# "!demo <n>": the native client hands the item over with the game's own item-get scene (tools/give_trigger.py, AP_Q<n>)
# and skips the rest; without that trigger in the game's files the actions after it give the item directly.
# "@<k> <action>": only for the k-th copy of that item received (progressive items).
ITEMS = {
    # the champion powers people send you; the second copy is the Champions' Ballad's "+" (2 copies with the DLC)
    # "givekey" needs the patched Savage Wind; "!set/!add/!addf <flag> <v>" write live gamedata (next loading screen)
    "Progressive Mipha's Grace": (IC.progression, [
        "@1 !demo 1", "@1 givekey Obj_HeroSoul_Zora 1", "@2 !demo 21", "@2 givekey Obj_DLC_HeroSoul_Zora 1"], 2, 0),
    "Progressive Daruk's Protection": (IC.progression, [
        "@1 !demo 3", "@1 givekey Obj_HeroSoul_Goron 1", "@2 !demo 23", "@2 givekey Obj_DLC_HeroSoul_Goron 1"], 2, 0),
    "Progressive Revali's Gale": (IC.progression, [
        "@1 !demo 2", "@1 givekey Obj_HeroSoul_Rito 1", "@2 !demo 22", "@2 givekey Obj_DLC_HeroSoul_Rito 1"], 2, 0),
    "Progressive Urbosa's Fury": (IC.progression, [
        "@1 !demo 4", "@1 givekey Obj_HeroSoul_Gerudo 1", "@2 !demo 24", "@2 givekey Obj_DLC_HeroSoul_Gerudo 1"], 2, 0),
    # the sword, then what each Trial of the Sword adds (Beginning, Middle, Final: +10 power each, the last one awakens
    # it for good); 4 copies with the DLC, else 1
    "Progressive Master Sword": (IC.progression, [
        "@1 !demo 7", "@1 givekey Weapon_Sword_070 1",
        "@2 !add MasterSword_Add_Power 10", "@3 !add MasterSword_Add_Power 10",
        "@4 !add MasterSword_Add_Power 10", "@4 !set Open_MasterSword_FullPower 1"], 4, 0),
    "Heart Container": (IC.progression, ["!demo 5", "!add MaxHartValue 4", "!add CurrentHart 4"], 12, 0),
    "Stamina Vessel": (IC.useful, ["!demo 6", "!addf StaminaMax 200"], 10, 0),
    "Spirit Orb": (IC.useful, ["!demo 8", "givekey Obj_DungeonClearSeal 1"], 20, 0),
    "Hylian Shield": (IC.useful, ["Weapon_Shield_030 1"], 1, 0),
    "Travel Medallion": (IC.useful, ["!demo 10", "givekey Obj_WarpDLC 1"], 1, 0),  # DLC only, see __init__
    "Climbing Gear Set": (IC.useful, ["Armor_014_Head 1", "Armor_014_Upper 1", "Armor_014_Lower 1"], 1, 0),
    "Rubber Armor Set": (IC.useful, ["Armor_046_Head 1", "Armor_046_Upper 1", "Armor_046_Lower 1"], 1, 0),
    "Barbarian Armor Set": (IC.useful, ["Armor_048_Head 1", "Armor_048_Upper 1", "Armor_048_Lower 1"], 1, 0),
    "Zora Armor": (IC.progression, ["Armor_006_Upper 1"], 1, 0),  # (waterfalls: Dagah Keek, Mah Eliya...)
    "Snowquill Set": (IC.useful, ["Armor_009_Head 1", "Armor_009_Upper 1", "Armor_009_Lower 1"], 1, 0),
    "Flamebreaker Set": (IC.useful, ["Armor_011_Head 1", "Armor_011_Upper 1", "Armor_011_Lower 1"], 1, 0),
    "Royal Claymore": (IC.useful, ["Weapon_Lsword_024 1"], 1, 0),
    "Savage Lynel Sword": (IC.useful, ["Weapon_Sword_018 1"], 1, 0),
    "Savage Lynel Bow": (IC.useful, ["Weapon_Bow_032 1"], 1, 0),
    "Great Eagle Bow": (IC.useful, ["Weapon_Bow_028 1"], 1, 0),
    "Ancient Bladesaw": (IC.useful, ["Weapon_Lsword_023 1"], 1, 0),
    "Guardian Sword++": (IC.useful, ["Weapon_Sword_015 1"], 1, 0),
    "Lightscale Trident": (IC.useful, ["Weapon_Spear_050 1"], 1, 0),
    "Scimitar of the Seven": (IC.useful, ["Weapon_Sword_052 1"], 1, 0),
    "Boulder Breaker": (IC.useful, ["Weapon_Lsword_054 1"], 1, 0),
    "Daybreaker": (IC.useful, ["Weapon_Shield_037 1"], 1, 0),
    "Ancient Arrows x5": (IC.useful, ["AncientArrow 5"], 3, 0),
    # weighted filler
    "Arrows x10": (IC.filler, ["NormalArrow 10"], None, 10),
    "Korok Seed": (IC.progression_skip_balancing, ["!demo 9", "givekey Obj_KorokNuts 1"], None, 20),
    "Fire Arrows x5": (IC.filler, ["FireArrow 5"], None, 4),
    "Ice Arrows x5": (IC.filler, ["IceArrow 5"], None, 4),
    "Shock Arrows x5": (IC.filler, ["ElectricArrow 5"], None, 4),
    "Bomb Arrows x5": (IC.filler, ["BombArrow_A 5"], None, 3),
    "Diamond": (IC.filler, ["Item_Ore_A 1"], None, 3),
    "Ruby": (IC.filler, ["Item_Ore_B 1"], None, 5),
    "Sapphire": (IC.filler, ["Item_Ore_C 1"], None, 5),
    "Topaz": (IC.filler, ["Item_Ore_D 1"], None, 5),
    "Opal x3": (IC.filler, ["Item_Ore_E 3"], None, 5),
    "Amber x5": (IC.filler, ["Item_Ore_F 5"], None, 5),
    "Star Fragment": (IC.filler, ["Item_Ore_J 1"], None, 2),
    "Lynel Guts": (IC.filler, ["Item_Enemy_14 1"], None, 2),
    "Ancient Core": (IC.filler, ["Item_Enemy_30 1"], None, 2),
    "Hearty Durian x3": (IC.filler, ["Item_Fruit_D 3"], None, 5),
    "Big Hearty Truffle x2": (IC.filler, ["Item_Mushroom_N 2"], None, 4),
    "Endura Carrot x2": (IC.filler, ["Item_PlantGet_Q 2"], None, 3),
    "Mighty Bananas x5": (IC.filler, ["Item_Fruit_H 5"], None, 4),
    "Silent Princess x3": (IC.filler, ["Item_PlantGet_J 3"], None, 2),
    "Wood": (IC.filler, ["Obj_FireWoodBundle 1"], None, 2),
    "Royal Guard's Sword": (IC.filler, ["Weapon_Sword_047 1"], None, 4),
    "Ancient Screw x3": (IC.filler, ["Item_Enemy_27 3"], None, 4),
    # traps (weight comes from the trap_percentage option)
    "Thunderstorm Trap": (IC.trap, ["!trap thunderstorm"], None, 0),
    "Midnight Trap": (IC.trap, ["!trap midnight"], None, 0),
    # what quests and minigames used to give (tools/quest_rewards.py makes them give the Archipelago Item)
    "Thunder Helm": (IC.progression, ["!demo 11", "Armor_115_Head 1"], 1, 0),  # Vah Naboris needs it
    "500 Rupees": (IC.filler, ["!add CurrentRupee 500"], 1, 0),  # The Jewel Trade
    "Blizzard Rod": (IC.useful, ["!demo 12", "Weapon_Sword_049 1"], 1, 0),  # Snowling bowling
    # (horse gear isn't a pouch item: only the item-get scene can give it)
    "Extravagant Bridle": (IC.useful, ["!demo 13"], 1, 0),  # the horse race
    "Extravagant Saddle": (IC.useful, ["!demo 14"], 1, 0),
    "Knight's Bridle": (IC.useful, ["!demo 15"], 1, 0),  # horseback archery
    "Knight's Saddle": (IC.useful, ["!demo 16"], 1, 0),
    "Royal Shield": (IC.useful, ["!demo 17", "Weapon_Shield_022 1"], 1, 0),  # shield surfing
    # a camp chest held them: The Priceless Maracas, and with it Hestu's pouch upgrades, needs them
    "Hestu's Maracas": (IC.progression, ["!demo 18", "givekey Obj_Maracas 1"], 1, 0),
    # what Hestu's trades used to add (tools/quest_rewards.py: his trades send checks instead)
    "Weapon Slot": (IC.useful, ["!add WeaponPorchStockNum 1"], 11, 0),
    "Bow Slot": (IC.useful, ["!add BowPorchStockNum 1"], 8, 0),
    "Shield Slot": (IC.useful, ["!add ShieldPorchStockNum 1"], 16, 0),
    "Hestu's Gift": (IC.filler, ["!demo 19", "givekey Obj_ProofKorok 1"], 1, 0),
    # the old man's gift on the Great Plateau (tools/quest_rewards.py): without it Link can't leave the plateau
    "Paraglider": (IC.progression, ["!demo 20", "givekey PlayerStole2 1"], 1, 0),
    # the runes (the Great Plateau's terminals and Purah no longer give them: tools/quest_rewards.py); the second copy
    # of Remote Bomb, Stasis and the Sheikah Sensor is its "+"
    "Progressive Remote Bomb": (IC.progression, [
        "@1 !demo 25", "@1 !set IsGet_Obj_RemoteBomb 1", "@2 !demo 26", "@2 !set IsGet_Obj_RemoteBombLv2 1"], 2, 0),
    "Progressive Stasis": (IC.progression, [
        "@1 !demo 27", "@1 !set IsGet_Obj_StopTimer 1", "@2 !demo 28", "@2 !set IsGet_Obj_StopTimerLv2 1"], 2, 0),
    "Progressive Sheikah Sensor": (IC.useful, [
        "@1 !set IsStart_Obj_SheikSensor 1", "@1 !demo 29", "@1 !set IsGet_Obj_SheikSensor 1",
        "@2 !demo 30", "@2 !set IsGet_Obj_SheikSensorLv2 1"], 2, 0),
    "Magnesis": (IC.progression, ["!demo 31", "!set IsGet_Obj_Magnetglove 1"], 1, 0),
    "Cryonis": (IC.progression, ["!demo 32", "!set IsGet_Obj_IceMaker 1"], 1, 0),
    # region lock: each region's map opens it (AP_Region_<n>, saved; Savage Wind keeps Link out of the others)
    **{f"{r} Map": (IC.progression, [f"!set AP_Region_{i:02d} 1"], 1, 0)
       for i, r in enumerate(["Hebra", "Tabantha", "Gerudo", "Wasteland", "Woodland", "Central", "Great Plateau",
                              "Dueling Peaks", "Lake", "Eldin", "Akkala", "Lanayru", "Hateno", "Faron", "Ridgeland"])
       if r != "Great Plateau"},
    # more traps, as Waikuteru's randomizer has them: weather, the game's own prohibitions (90 seconds), a hit, a
    # thief, a warp to a random stable; and filler: rupees, a full heal
    "Blizzard Trap": (IC.trap, ["!trap blizzard"], None, 0),
    "Downpour Trap": (IC.trap, ["!trap downpour"], None, 0),
    "No Warping Trap": (IC.trap, ["!trap no_warp"], None, 0),
    "No Saving Trap": (IC.trap, ["!trap no_save"], None, 0),
    "Hunger Trap": (IC.trap, ["!trap no_eat"], None, 0),
    "Ouch Trap": (IC.trap, ["!trap ouch"], None, 0),
    "Rupee Drain Trap": (IC.trap, ["!trap drain"], None, 0),
    "Warp Trap": (IC.trap, ["!trap warp"], None, 0),
    "Red Rupee": (IC.filler, ["!add CurrentRupee 20"], None, 6),
    "Purple Rupee": (IC.filler, ["!add CurrentRupee 50"], None, 4),
    "Silver Rupee": (IC.filler, ["!add CurrentRupee 100"], None, 2),
    "Full Recovery": (IC.filler, [], None, 4),  # (the banner's event heals: Demo_RecoverPlayerLife)
    # the environment for a while (the game's own weather tags, switched by a flag: tools/give_trigger.py),
    # enemies that join the wildlife wherever Link goes for a while (as Waikuteru's spawns), a pouch thief
    "Heat Trap": (IC.trap, ["!trap heat"], None, 0),
    "Cold Trap": (IC.trap, ["!trap cold"], None, 0),
    "Fire Trap": (IC.trap, ["!trap fire"], None, 0),
    "Fog Trap": (IC.trap, ["!trap fog"], None, 0),
    "Darkness Trap": (IC.trap, ["!trap dark"], None, 0),
    "Bokoblin Trap": (IC.trap, ["!trap bokoblins"], None, 0),
    "Moblin Trap": (IC.trap, ["!trap moblins"], None, 0),
    "Lynel Trap": (IC.trap, ["!trap lynels"], None, 0),
    "Thief Trap": (IC.trap, ["!trap thief"], None, 0),
    # the game's own Blood Moon: its scene at midnight, and every monster slain comes back
    "Blood Moon Trap": (IC.trap, ["!trap bloodmoon"], None, 0),
}

# The game's own banner (its centred message, as Waikuteru's randomizer shows them) for every item without an
# item-get scene: "!msg <DEMOS + 1 + its place here>" goes first (tools/give_trigger.py reads this list for the words
# and the events: keep it a plain list; append only, as ITEMS).
DEMOS = 32  # (tools/give_trigger.py's ITEMS: the item-get scenes)
BANNERS = [
    "Hylian Shield", "Climbing Gear Set", "Rubber Armor Set", "Barbarian Armor Set", "Zora Armor", "Snowquill Set",
    "Flamebreaker Set", "Royal Claymore", "Savage Lynel Sword", "Savage Lynel Bow", "Great Eagle Bow",
    "Ancient Bladesaw", "Guardian Sword++", "Lightscale Trident", "Scimitar of the Seven", "Boulder Breaker",
    "Daybreaker", "Ancient Arrows x5", "Arrows x10", "Fire Arrows x5", "Ice Arrows x5", "Shock Arrows x5",
    "Bomb Arrows x5", "Diamond", "Ruby", "Sapphire", "Topaz", "Opal x3", "Amber x5", "Star Fragment", "Lynel Guts",
    "Ancient Core", "Hearty Durian x3", "Big Hearty Truffle x2", "Endura Carrot x2", "Mighty Bananas x5",
    "Silent Princess x3", "Wood", "Royal Guard's Sword", "Ancient Screw x3", "Thunderstorm Trap", "Midnight Trap",
    "500 Rupees", "Weapon Slot", "Bow Slot", "Shield Slot",
    "Hebra Map", "Tabantha Map", "Gerudo Map", "Wasteland Map", "Woodland Map", "Central Map", "Dueling Peaks Map",
    "Lake Map", "Eldin Map", "Akkala Map", "Lanayru Map", "Hateno Map", "Faron Map", "Ridgeland Map",
    "Blizzard Trap", "Downpour Trap", "No Warping Trap", "No Saving Trap", "Hunger Trap", "Ouch Trap",
    "Rupee Drain Trap", "Warp Trap", "Red Rupee", "Purple Rupee", "Silver Rupee", "Full Recovery",
    "Heat Trap", "Cold Trap", "Fire Trap", "Fog Trap", "Darkness Trap", "Bokoblin Trap", "Moblin Trap", "Lynel Trap",
    "Thief Trap", "Blood Moon Trap",
]
for _i, _n in enumerate(BANNERS):
    _c, _acts, _copies, _w = ITEMS[_n]
    ITEMS[_n] = (_c, [f"!msg {DEMOS + 1 + _i}"] + _acts, _copies, _w)

ITEM_IDS = {name: ITEM_BASE + i for i, name in enumerate(ITEMS)}
CHAMPION_POWERS = ["Progressive Mipha's Grace", "Progressive Daruk's Protection", "Progressive Revali's Gale",
                   "Progressive Urbosa's Fury"]
RUNES = ["Progressive Remote Bomb", "Magnesis", "Progressive Stasis", "Cryonis"]  # (what Link needs off the plateau)
MAPS = [n for n in ITEMS if n.endswith(" Map")]  # (region lock only)
DLC_PROGRESSIVE = CHAMPION_POWERS + ["Progressive Master Sword"]  # (their later copies are DLC content)
# The enemy traps (Bokoblin, Moblin, Lynel) are left out of seeds and TrapLink - the overworld's spawns rarely pick
# them (tested 2026-11-16); the Blood Moon Trap took their place. Still defined: item ids and older seeds keep working
ENEMY_TRAPS = {"Bokoblin Trap", "Moblin Trap", "Lynel Trap"}
TRAPS = [n for n, v in ITEMS.items() if v[0] == IC.trap and n not in ENEMY_TRAPS]
FILLER = {n: v[3] for n, v in ITEMS.items() if v[2] is None and v[0] != IC.trap}
