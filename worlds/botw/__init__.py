import json
import pkgutil

from BaseClasses import ItemClassification as IC, Location, Region, Tutorial
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .items import CHAMPION_POWERS, DLC_PROGRESSIVE, FILLER, GAME, ITEM_IDS, ITEMS, MAPS, RUNES, TRAPS, BotWItem
from .options import BotWOptions

LOC_BASE = 7_400_000_000
# every location is a gamedata flag; its id is LOC_BASE + the flag's hash, so the client needs no name table
LOCATIONS = json.loads(pkgutil.get_data(__name__, "data/locations.json").decode("utf8"))
LOC_IDS = {l["name"]: LOC_BASE + l["hash"] for l in LOCATIONS}
# region lock: the towers' regions, which border which (tools/regions.py); the Great Plateau's is open from the start
REGIONS = json.loads(pkgutil.get_data(__name__, "data/regions.json").decode("utf8"))
GOAL_FLAG = "GanonQuest_Finished"

CATEGORY_OPTION = {"Korok": "koroks", "Chest": "chests", "Shrine Chest": "shrine_chests",
                   "Divine Beast Chest": "divine_beast_chests", "Tower": "towers", "Memory": "memories",
                   "Main Quest": "quests", "Shrine Quest": "quests", "Side Quest": "quests", "Minigame": "minigames",
                   "Hestu": "hestu", "Shop": "shop_sanity"}
HESTU_SEEDS = 441  # (every trade: tools/extract.py has each one's)
# the runes in logic: the Great Plateau's four shrines each need their own (their terminal gives nothing now); the
# rest of Hyrule all four (puzzles, chests underwater or under rocks, Korok Seeds...). Free: the terminals, the tower
SHRINE_RUNE = {"Dungeon041": "Progressive Remote Bomb", "Dungeon038": "Magnesis", "Dungeon009": "Progressive Stasis",
               "Dungeon065": "Cryonis"}
RUNE_FREE = {"MapTower_07", "FirstTower_Finish"}  # (Great Plateau Tower; Follow the Sheikah Slate)
SHRINE_DUNGEON = {l["name"]: l["dungeon"] for l in LOCATIONS if l["category"] == "Shrine"}
# freeing a Divine Beast is a game state, not an item: an event on its "Cleared" check, which what comes after needs
BEAST_FREED = {f"{b} Cleared": f"{b} Freed" for b in ("Vah Ruta", "Vah Medoh", "Vah Rudania", "Vah Naboris")}
ALL_FREED = list(BEAST_FREED.values())
# what the game asks for beyond Paraglider + runes (a shrine's chests share its shrine's needs; shops by prefix)
NEEDS = {
    "Dagah Keek Shrine": ["Vah Ruta Freed", "Zora Armor"], "The Ceremonial Song": ["Vah Ruta Freed", "Zora Armor"],
    "Frog Catching": ["Vah Ruta Freed"], "The Giant of Ralis Pond": ["Vah Ruta Freed"],
    "Diving is Beauty!": ["Zora Armor"], "Mah Eliya Shrine": ["Zora Armor"],
    "Bareeda Naag Shrine": ["Vah Medoh Freed"], "Voo Lota Shrine": ["Vah Medoh Freed"],
    "Recital at Warbler's Nest": ["Vah Medoh Freed"], "Shop - Teba": ["Vah Medoh Freed"],
    "The Jewel Trade": ["Vah Rudania Freed"],
    "Raqa Zunzo Shrine": ["Vah Naboris Freed"], "The Undefeated Champ": ["Vah Naboris Freed"],
    "Free the Divine Beasts": ALL_FREED, "Shop - Kilton": ALL_FREED,  # (his stock grows with each beast)
    "A Gift from the Monks": ALL_FREED + ["Zora Armor"],  # (every shrine: the beasts' and Dagah Keek's too)
}


def needs(l):
    name = l["name"].split(" Chest")[0] if l["category"] == "Shrine Chest" else l["name"]
    return next((v for k, v in NEEDS.items() if name == k or name.startswith(k + " ")), [])


def launch_client(*args):
    from .client import launch
    launch_subprocess(launch, name="BotWClient", args=args)


components.append(Component("Breath of the Wild Client", func=launch_client, component_type=Type.CLIENT))


class BotWLocation(Location):
    game = GAME


class BotWWeb(WebWorld):
    tutorials = [Tutorial("Setup Guide", "Set up Savage Wind and the client.", "English", "setup_en.md",
                          "setup/en", ["botw_ap"])]


class BotWWorld(World):
    """Breath of the Wild on the Savage Wind recomp. Shrines, Korok Seeds, chests, towers, memories, quests and the
    Divine Beasts are checks. Champion powers, the Master Sword and Heart Containers come from the multiworld."""
    game = GAME
    web = BotWWeb()
    options_dataclass = BotWOptions
    options: BotWOptions
    item_name_to_id = ITEM_IDS
    location_name_to_id = LOC_IDS
    item_name_groups = {"Champion Powers": set(CHAMPION_POWERS), "Maps": set(MAPS)}
    location_name_groups = {}
    for _l in LOCATIONS:
        location_name_groups.setdefault(_l["category"], set()).add(_l["name"])

    def active_locations(self):
        o = self.options
        return [l for l in LOCATIONS
                if (o.dlc or not l["dlc"]) and (o.master_mode or not l.get("master_mode"))
                and getattr(o, CATEGORY_OPTION.get(l["category"], ""), True)]

    def create_item(self, name: str) -> BotWItem:
        return BotWItem(name, ITEMS[name][0], ITEM_IDS[name], self.player)

    def create_regions(self):
        p, o = self.player, self.options
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        if o.region_lock:
            # one region per tower's area; into one from a neighbour with its map (and off the Great Plateau's with
            # the paraglider)
            names, plateau = REGIONS["names"], REGIONS["plateau"]
            areas = [Region(n, p, self.multiworld) for n in names]
            self.multiworld.regions += areas
            menu.connect(areas[plateau])
            for i, near in enumerate(REGIONS["adjacent"]):
                for j in near:
                    need = [] if j == plateau else [f"{names[j]} Map"]
                    if i == plateau:
                        need.append("Paraglider")
                    areas[i].connect(areas[j], f"{names[i]} -> {names[j]}", lambda s, n=need: s.has_all(n, p))
            home = lambda l: areas[l["region"]] if l["region"] >= 0 else areas[plateau]
            goal_area = areas[names.index("Central")]
        else:
            hyrule = Region("Hyrule", p, self.multiworld)
            self.multiworld.regions.append(hyrule)
            menu.connect(hyrule)
            home = lambda l: hyrule
            goal_area = hyrule
        for l in self.active_locations():
            area = home(l)
            loc = BotWLocation(p, l["name"], LOC_IDS[l["name"]], area)
            if "korok_seeds" in l:  # (a Hestu trade: his maracas back, and seeds enough whatever was bought before)
                seeds = l["korok_seeds"]
                loc.access_rule = lambda s, n=seeds: s.has("Hestu's Maracas", p) and s.has("Korok Seed", p, n)
            elif l["flag"].startswith("100enemy_"):  # (the Trial of the Sword: from the sword's pedestal, once pulled)
                hearts = o.master_sword_hearts.value
                loc.access_rule = lambda s: (s.has_all(CHAMPION_POWERS + ALL_FREED, p)
                                             and s.has("Heart Container", p, hearts)
                                             and s.has("Progressive Master Sword", p))
            elif l["dlc"]:  # (the Champions' Ballad opens once all four beasts are freed; their powers too, to be safe)
                loc.access_rule = lambda s: s.has_all(CHAMPION_POWERS + ALL_FREED, p)
            elif l["flag"] == "Get_MasterSword_Finish":  # (The Hero's Sword: pulling it)
                hearts = o.master_sword_hearts.value
                loc.access_rule = lambda s: s.has("Heart Container", p, hearts)
            elif l["flag"] == "OldKorok_Help_Finish":  # (The Priceless Maracas)
                loc.access_rule = lambda s: s.has("Hestu's Maracas", p)
            elif "Naboris" in l["name"] and l["category"] in ("Divine Beast", "Divine Beast Chest", "Main Quest"):
                # (Vah Naboris's lightning: the Thunder Helm)
                loc.access_rule = lambda s: s.has("Thunder Helm", p)
            if needs(l):
                rule = loc.access_rule
                loc.access_rule = lambda s, r=rule, n=needs(l): s.has_all(n, p) and r(s)
            shrine = SHRINE_DUNGEON.get(l["name"].split(" Chest")[0])
            if l["category"] == "Rune Terminal" or l["flag"] in RUNE_FREE:
                runes = []
            elif l.get("plateau") and shrine in SHRINE_RUNE:
                runes = [SHRINE_RUNE[shrine]]
            else:
                runes = RUNES
            if runes:
                rule = loc.access_rule
                loc.access_rule = lambda s, r=rule, need=runes: s.has_all(need, p) and r(s)
            if not l.get("plateau"):  # (off the Great Plateau: the paraglider first; tools/extract.py)
                rule = loc.access_rule
                loc.access_rule = lambda s, r=rule: s.has("Paraglider", p) and r(s)
            if o.region_lock and l["region"] < 0:  # (no one place: anywhere, so every map)
                rule = loc.access_rule
                loc.access_rule = lambda s, r=rule: s.has_all(MAPS, p) and r(s)
            area.locations.append(loc)
            if l["name"] in BEAST_FREED:  # (the beast freed: an event where its check is, as hard to reach)
                ev = BotWLocation(p, BEAST_FREED[l["name"]] + " (event)", None, area)
                ev.access_rule = loc.access_rule
                ev.place_locked_item(BotWItem(BEAST_FREED[l["name"]], IC.progression, None, p))
                area.locations.append(ev)
        goal = BotWLocation(p, "Defeat Calamity Ganon", None, goal_area)
        need, sword = o.required_champion_powers.value, bool(o.goal_needs_master_sword)
        goal.access_rule = lambda s: (s.has("Paraglider", p) and s.has_all(RUNES, p)
                                      and sum(s.has(c, p) for c in CHAMPION_POWERS) >= need
                                      and (not sword or s.has("Progressive Master Sword", p)))
        goal.place_locked_item(BotWItem("Victory", IC.progression, None, p))
        goal_area.locations.append(goal)
        self.multiworld.completion_condition[p] = lambda s: s.has("Victory", p)

    def create_items(self):
        slots = len(self.active_locations())
        pool = []
        start_map = None
        if self.options.region_lock:  # (one region next to the Great Plateau starts open: room to begin)
            names = REGIONS["names"]
            start_map = f"{names[self.random.choice(REGIONS['adjacent'][REGIONS['plateau']])]} Map"
            self.multiworld.push_precollected(self.create_item(start_map))
        for name, (cls, _, copies, _) in ITEMS.items():
            if name in DLC_PROGRESSIVE and not self.options.dlc:
                copies = 1  # (the later copies are the DLC's: the Trial of the Sword, the Champions' Ballad's "+")
            if name in MAPS and (not self.options.region_lock or name == start_map):
                continue
            if copies and (name != "Travel Medallion" or self.options.dlc):
                pool += [self.create_item(name) for _ in range(copies)]
        if self.options.hestu:
            pool += [self.create_item("Korok Seed") for _ in range(HESTU_SEEDS)]
        if len(pool) > slots:  # tiny settings: keep progression first, drop the rest
            pool.sort(key=lambda i: not i.advancement)
            pool = pool[:slots]
        traps = self.options.trap_percentage.value
        for _ in range(slots - len(pool)):
            pool.append(self.create_item(self.get_filler_item_name() if self.random.randrange(100) >= traps
                                         else self.random.choice(TRAPS)))
        self.multiworld.itempool += pool

    def get_filler_item_name(self) -> str:
        return self.random.choices(list(FILLER), weights=list(FILLER.values()))[0]

    def fill_slot_data(self):
        # actions: what the game does for each of its items (Savage Wind's native client reads them from here)
        return {"required_champion_powers": self.options.required_champion_powers.value,
                "goal_needs_master_sword": bool(self.options.goal_needs_master_sword),
                "goal_flag": GOAL_FLAG,
                "actions": {str(ITEM_IDS[n]): v[1] for n, v in ITEMS.items()},
                "champion_powers": [ITEM_IDS[n] for n in CHAMPION_POWERS],
                "region_lock": bool(self.options.region_lock),
                "master_sword_hearts": self.options.master_sword_hearts.value,
                # (the options, for trackers: tools/poptracker.py)
                "options": {k: getattr(self.options, k).value for k in (
                    "koroks", "chests", "shrine_chests", "divine_beast_chests", "towers", "memories", "quests",
                    "minigames", "hestu", "dlc", "master_mode", "shop_sanity", "region_lock")},
                # checks that are a count the game keeps reaching a number, not a flag going on: id -> [name, number]
                "counters": {str(LOC_IDS[l["name"]]): [l["flag"], l["min"]] for l in LOCATIONS if "min" in l},
                "master_sword": ITEM_IDS["Progressive Master Sword"],
                "traps": {n: next(a for a in ITEMS[n][1] if a.startswith("!trap")).split()[1] for n in TRAPS}}
