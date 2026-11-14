from dataclasses import dataclass

from Options import DefaultOnToggle, PerGameCommonOptions, Range, Toggle


class RequiredChampionPowers(Range):
    """How many champion powers (Mipha's Grace, Daruk's Protection, Revali's Gale, Urbosa's Fury) you need from the
    multiworld before defeating Calamity Ganon counts as your goal."""
    display_name = "Required Champion Powers"
    range_start = 0
    range_end = 4
    default = 4


class GoalNeedsMasterSword(Toggle):
    """The goal also needs the Master Sword item."""
    display_name = "Goal Needs Master Sword"


class MasterSwordHearts(Range):
    """Heart Containers from the multiworld the Master Sword check expects in logic (13 hearts in game = 10 more)."""
    display_name = "Master Sword Hearts"
    range_start = 10  # (the game's own minimum: fewer and logic would expect the sword before the game allows it)
    range_end = 12
    default = 10


class Koroks(DefaultOnToggle):
    """The 900 Korok Seeds are checks."""
    display_name = "Korok Seeds"


class Chests(DefaultOnToggle):
    """Overworld treasure chests are checks (about 1300)."""
    display_name = "Overworld Chests"


class ShrineChests(DefaultOnToggle):
    """Chests inside shrines are checks."""
    display_name = "Shrine Chests"


class DivineBeastChests(DefaultOnToggle):
    """Chests inside the four Divine Beasts are checks."""
    display_name = "Divine Beast Chests"


class Towers(DefaultOnToggle):
    """Activating each Sheikah Tower is a check."""
    display_name = "Towers"


class Memories(DefaultOnToggle):
    """Each captured memory is a check."""
    display_name = "Memories"


class Quests(DefaultOnToggle):
    """Main quests, shrine quests and side quests are checks."""
    display_name = "Quests"


class Minigames(Toggle):
    """Minigames (races, archery, Snowling bowling...) are checks."""
    display_name = "Minigames"


class Hestu(DefaultOnToggle):
    """Hestu's 35 pouch upgrades and his gift are checks: trading him Korok Seeds sends a check instead of adding a
    slot. Weapon, Bow and Shield Slots come from the multiworld either way, and 441 Korok Seeds join the pool."""
    display_name = "Hestu"


class DLC(Toggle):
    """The Champions' Ballad shrines and quests are checks (needs DLC 2). In logic they need all four champion powers."""
    display_name = "Champions' Ballad"


class RegionLock(Toggle):
    """Hyrule opens region by region (the areas of its 15 Sheikah Towers), from the Great Plateau: each region's map
    comes from the multiworld (14 Map items) and opens it. A locked region is hidden in thick fog, and Link is sent
    back if he steps into it."""
    display_name = "Region Lock"


class ShopSanity(Toggle):
    """Every shop slot in Hyrule is a check (about 500): the first time you buy each thing a shopkeeper sells - town
    stores, armor shops, traveling merchants, Beedle at every stable, Kilton, the ancient tech labs. You still get
    what you bought."""
    display_name = "Shop Sanity"


class MasterMode(Toggle):
    """You play Master Mode: its 117 chests that only exist there (on the overworld) are checks too."""
    display_name = "Master Mode"


class TrapPercentage(Range):
    """Share of the filler that is traps (Thunderstorm: forces a thunderstorm for 2 minutes, Midnight: jumps to night)."""
    display_name = "Trap Percentage"
    range_start = 0
    range_end = 50
    default = 5


@dataclass
class BotWOptions(PerGameCommonOptions):
    required_champion_powers: RequiredChampionPowers
    goal_needs_master_sword: GoalNeedsMasterSword
    master_sword_hearts: MasterSwordHearts
    koroks: Koroks
    chests: Chests
    shrine_chests: ShrineChests
    divine_beast_chests: DivineBeastChests
    towers: Towers
    memories: Memories
    quests: Quests
    minigames: Minigames
    hestu: Hestu
    dlc: DLC
    master_mode: MasterMode
    shop_sanity: ShopSanity
    region_lock: RegionLock
    trap_percentage: TrapPercentage
