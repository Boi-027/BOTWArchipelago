# Breath of the Wild (Savage Wind) setup

## What you need
- Savage Wind Recomp 0.5.3-alpha.5 with your own game files set up, built with `savagewind-archipelago.patch`. The
  patch puts the whole Archipelago client inside the game: no Archipelago install or extra window is needed to play.
- To generate a seed: Archipelago 0.6.8 or later with `botwsw.apworld` in `custom_worlds`.

## The Archipelago overlay (recommended)
Changed game files, built from your own: checks give the Archipelago Item instead of their normal reward, items you
receive arrive with the game's own item-get scene, and "ARCHIPELAGO" sits under the logo on the title and loading
screens. Build it once (needs Python with `oead`, `evfl` and `Pillow`, in `botw_ap/.venv`):

```
python -I tools/build_overlay.py "<your Savage Wind folder>"
```

then add to `launch-flags.txt` next to `savagewind.exe` (or Settings > Prelaunch):

```
SAVAGEWIND_ROMFS_OVERLAY=<your Savage Wind folder>/ap_overlay
```

It is your game's files: never share it.

## Play
1. Start a **new game** for the seed.
2. Options > **Archipelago** (on the title screen, or pause menu > System > Options): set Server (like
   `archipelago.gg:38281`), Slot name and Password, turn on the links you want, then **Connect**. The button shows
   Connecting... / Connected / Refused / Disconnected.
3. Play. Notifications show at the bottom left.

## How it works
- **Checks** are sent the moment their game data flag goes on (shrines, Korok Seeds, chests, towers, quests...).
- **Items**: champion powers, Heart Containers, Stamina Vessels, the Master Sword, Spirit Orbs, Korok Seeds, the
  Travel Medallion, the Paraglider, the Thunder Helm, the Blizzard Rod, the Royal Shield and horse gear play the
  game's item-get scene the moment they arrive, wherever Link is (shrines and Divine Beasts
  too; in a menu, a talk or a cutscene, right after it). Everything else goes straight into the pouch. Without the overlay all of them do, and Heart
  Containers and Stamina Vessels take effect at the next loading screen. What each item does comes from the room,
  so a new apworld needs no new game build.
- With the overlay a check gives the Archipelago Item, not its normal reward (chests, Korok Seeds, Spirit Orbs,
  champion powers, quest rewards, the Master Sword's pull, every minigame prize); without it the normal reward comes
  too. The rewards that are gone are in the item pool: the Thunder Helm (Vah Naboris needs it), 500 Rupees from The
  Jewel Trade, the Blizzard Rod, the Royal Shield and the minigames' bridles and saddles. Only the Test of Wood's gear
  stays: it is lent for the trial and taken back.
- **Paraglider**: the old man's gift on the Great Plateau is the Archipelago Item; the Paraglider comes from the
  multiworld. Until it arrives Link can't leave the plateau (the game sends him back, as without it in the normal
  game), so in logic every check off the plateau needs it.
- Pulling the Master Sword is the check "The Hero's Sword". Hestu's Maracas (from a camp chest) are in the pool:
  The Priceless Maracas, and with it Hestu's pouch upgrades, needs them.
- **Hestu** (option, on by default): each of his 35 pouch upgrades and his gift is a check. Trading him Korok Seeds
  sends the check and adds no slot; slots come as Weapon Slot (11), Bow Slot (8) and Shield Slot (16) items, from the
  multiworld either way. 441 Korok Seeds (what all his trades cost) join the pool. In logic a trade counts once you
  have seeds enough for it even after buying all of the other two kinds first, so you can't spend yourself stuck.
- **Progressive Master Sword** (4 with the DLC, else 1): the first is the sword, each of the next three adds what a
  Trial of the Sword adds (+10 power; the fourth also awakens it for good). The three trials are checks of their own
  and no longer power up the sword.
- **Runes and champion abilities**: Remote Bomb, Stasis and the Sheikah Sensor come as progressive items (the second
  copy is the "+"), Magnesis and Cryonis as one each; Mipha's Grace, Daruk's Protection, Revali's Gale and Urbosa's
  Fury are progressive too (2 with the DLC: the second is the Champions' Ballad's "+"). The Great Plateau shrines'
  terminals, Purah's upgrades at the Hateno lab (3 checks: each upgrade bought) and the Champions' Ballad no longer
  give them. In logic a plateau shrine needs its own rune, and everything off the plateau needs all four.
- **Master Mode** (option, off): you play Master Mode, so its 117 chests that exist only there are checks. Three chests
  nobody can open are never checks (Hateno Village's in front of the inn, Rassla Lake's, Aris Beach's in the sea).
- **Shop Sanity** (option, off): every shop slot is a check (about 500: town stores, armor shops, traveling
  merchants, Beedle at every stable, Kilton, the tech labs, Granté). Each one is sold as its own Archipelago Item, at
  the price of the good it stands in for: one ware on each pile of a store's counter, and the goods on a merchant's
  list. Buying it sends the check; then the shop sells its own good there again (on a counter at once, on a
  merchant's list the next time you meet them; buying one again before that gets you the good). Armor on a
  mannequin stays armor: the first one you buy is the check.
- **Region Lock** (option, off): Hyrule opens region by region (the 15 Sheikah Tower regions) from the Great Plateau.
  Each region's map is an item (14 Maps; you start with one region next to the plateau); a region is reached from a
  neighbour once its map is in. A locked region is hidden in thick fog, and stepping into it whites the screen out and
  puts Link back where he last stood clear of it.
- **DeathLink**: your deaths go to everyone in DeathLink; theirs kill Link (at once once he has taken a hit since the
  last load, otherwise at his next hit).
- **TrapLink**: traps you receive go to everyone in TrapLink; theirs become one of ours.
- **Banners**: every item without an item-get scene (filler, traps, gear, maps, pouch slots) is announced by the game's
  own centred message, as in Waikuteru's randomizer ("You got Arrows x10!", "Warping is now disabled"...).
- **Adventure Log**: once connected, *Archipelago Hints* (Side Quests) lists the hints about your items and world,
  newest first, and *Archipelago Goal* (Main Quests) shows your goal and how far along you are.
- **Traps** that change the world: Heat, Cold (1 min), Fire (8 s), Fog, Darkness (2 min) on the overworld (not inside
  shrines or Divine Beasts); Bokoblin, Moblin and Lynel Traps spawn enemies around you in the field (not on the Great
  Plateau before the Paraglider); a Thief Trap takes a weapon, bow or shield you aren't holding.
- **RingLink**: rupees you gain or spend are shared; loading a save isn't counted as spending.
- The room's progress for this slot is kept in `ap/` next to `savagewind.exe`.

The Launcher's *Breath of the Wild Client* is only for stock Savage Wind (no patch); don't run it with the patched game.

## PopTracker
`tools/poptracker.py` makes a PopTracker pack from your own game files (the game's map and icons: for your machine
only, never share it):

```
botw_ap/.venv/Scripts/python -I tools/poptracker.py "<your Savage Wind folder>/extracted" botw_ap/poptracker
```

Put `botw_ap/poptracker/BotW_AP.zip` in PopTracker's `packs` folder. It has the Hyrule map with the regions drawn on
it and every check where it is, a Regions panel (the regions as shapes, with the checks that have no one place), the
region maps laid out like Hyrule, the world's logic, and Archipelago autotracking: connect with the AP button and it
follows your items, checks and options.
