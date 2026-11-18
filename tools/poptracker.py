"""A PopTracker pack for Breath of the Wild Archipelago (Savage Wind), made from your own game files - for your machine
only, it holds the game's map and icons:
  - the Hyrule map (UI/MapTex/MainField, the game's own map tiles) with the regions drawn on it, every check where it is
    (a shrine's chests and terminal with the shrine; nearby checks of one kind and place on one pin; quests where
    whoever gives them stands, memories, minigames, Hestu, a Divine Beast and its chests where it waits)
  - the Regions tab: Hyrule's 15 tower regions as shapes, with the few checks that have no one place (traveling
    merchants...), and the Regions panel: Hyrule in pieces, each in colour once its map is found; click one and the
    Hyrule map zooms onto it (again: all of Hyrule), right-click: its map found or not
  - the logic of worlds/botw (runes, paraglider, Hestu's seeds, the Master Sword's trials, region lock), and
    Archipelago autotracking: items, checked locations and the slot's options (what isn't on is hidden)

    botw_ap/.venv/Scripts/python -I tools/poptracker.py "<Savage Wind folder>/extracted" <out folder>
(Pillow and oead; reads worlds/botw/data. The pack is <out folder>/BotW_AP, and BotW_AP.zip beside it.)
"""
import io
import json
import os
import re
import shutil
import struct
import sys
import zipfile
from collections import defaultdict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "launcher"))  # (botw_assets)
import nin  # noqa: E402
from logo_overlay import deswizzle_px  # noqa: E402
from regions import NAMES, PLATEAU, Grid  # noqa: E402
from rune_items import picture  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD = os.path.join(HERE, "..", "worlds", "botw")
SCALE = 0.3  # (map pixels per metre: Hyrule's 10000 x 8000 m -> 3000 x 2400)
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgiab.ttf")
REGION_COLOURS = [(150, 190, 220), (120, 170, 150), (215, 170, 110), (225, 200, 130), (110, 160, 110), (190, 170, 140),
                  (160, 200, 120), (140, 180, 120), (110, 170, 200), (200, 110, 90), (190, 150, 110), (100, 150, 210),
                  (170, 200, 140), (90, 160, 120), (150, 180, 110)]

# ---- the items: AP name -> (code, kind, stages / max, game icon)
CHAMPIONS = [("Progressive Mipha's Grace", "mipha", "Obj_HeroSoul_Zora"), ("Progressive Daruk's Protection", "daruk", "Obj_HeroSoul_Goron"),
             ("Progressive Revali's Gale", "revali", "Obj_HeroSoul_Rito"), ("Progressive Urbosa's Fury", "urbosa", "Obj_HeroSoul_Gerudo")]
ITEMS = {
    "Paraglider": ("paraglider", "toggle", None, "PlayerStole2"),
    "Progressive Remote Bomb": ("remote_bomb", "progressive", 2, "Obj_RemoteBomb"),
    "Magnesis": ("magnesis", "toggle", None, "Obj_Magnetglove"),
    "Progressive Stasis": ("stasis", "progressive", 2, "Obj_StopTimer"),
    "Cryonis": ("cryonis", "toggle", None, "Obj_IceMaker"),
    "Progressive Sheikah Sensor": ("sensor", "progressive", 2, "Obj_SheikSensor"),
    **{n: (c, "progressive", 2, a) for n, c, a in CHAMPIONS},
    "Progressive Master Sword": ("master_sword", "progressive", 4, "Weapon_Sword_070"),
    "Heart Container": ("heart", "consumable", 12, "Obj_HeartUtuwa_A_01"),
    "Stamina Vessel": ("stamina", "consumable", 10, "Obj_StaminaUtuwa_A_01"),
    "Spirit Orb": ("spirit_orb", "consumable", 20, "Obj_DungeonClearSeal"),
    "Korok Seed": ("korok", "consumable", 1341, "Obj_KorokNuts"),
    "Thunder Helm": ("thunder_helm", "toggle", None, "Armor_115_Head"),
    "Zora Armor": ("zora_armor", "toggle", None, "Armor_006_Upper"),
    "Hestu's Maracas": ("maracas", "toggle", None, "Obj_Maracas"),
    "Travel Medallion": ("travel_medallion", "toggle", None, "Obj_WarpDLC"),
    **{f"{r} Map": (f"map_{i:02d}", "toggle", None, None) for i, r in enumerate(NAMES) if i != PLATEAU},
}
OPTIONS = {"koroks": 1, "chests": 1, "shrine_chests": 1, "divine_beast_chests": 1, "towers": 1, "memories": 1,
           "quests": 1, "minigames": 0, "hestu": 1, "dlc": 0, "master_mode": 0, "shop_sanity": 0, "region_lock": 0}
CATEGORY_OPTION = {"Korok": "koroks", "Chest": "chests", "Shrine Chest": "shrine_chests",
                   "Divine Beast Chest": "divine_beast_chests", "Tower": "towers", "Memory": "memories",
                   "Main Quest": "quests", "Shrine Quest": "quests", "Side Quest": "quests", "Minigame": "minigames",
                   "Hestu": "hestu", "Shop": "shop_sanity"}
SHRINE_RUNE = {"Dungeon041": "remote_bomb", "Dungeon038": "magnesis", "Dungeon009": "stasis", "Dungeon065": "cryonis"}
RUNE_FREE = {"MapTower_07", "FirstTower_Finish"}
# a beast freed is its "Cleared" check done (the tracker sees it checked); beyond Paraglider + runes, as the world has it
BEASTS = ["Vah Ruta", "Vah Medoh", "Vah Rudania", "Vah Naboris"]
NEEDS = {
    "Dagah Keek Shrine": (["Vah Ruta"], True), "The Ceremonial Song": (["Vah Ruta"], True),
    "Frog Catching": (["Vah Ruta"], False), "The Giant of Ralis Pond": (["Vah Ruta"], False),
    "Diving is Beauty!": ([], True), "Mah Eliya Shrine": ([], True),
    "Bareeda Naag Shrine": (["Vah Medoh"], False), "Voo Lota Shrine": (["Vah Medoh"], False),
    "Recital at Warbler's Nest": (["Vah Medoh"], False), "Shop - Teba": (["Vah Medoh"], False),
    "The Jewel Trade": (["Vah Rudania"], False),
    "Raqa Zunzo Shrine": (["Vah Naboris"], False), "The Undefeated Champ": (["Vah Naboris"], False),
    "Free the Divine Beasts": (BEASTS, False), "Shop - Kilton": (BEASTS, False), "A Gift from the Monks": (BEASTS, True),
}


def item_ids():
    """AP name -> id, as worlds/botw/items.py numbers them (its table's order), without Archipelago to import"""
    src = open(os.path.join(WORLD, "items.py"), encoding="utf8").read()
    src = src.replace("from BaseClasses import Item, ItemClassification as IC", "")
    ns = {"IC": type("IC", (), {k: k for k in ("progression", "useful", "filler", "trap", "progression_skip_balancing")}),
          "Item": object}
    exec(compile(src, "items.py", "exec"), ns)
    return ns["ITEM_IDS"]


# ---- pictures
def map_tile(romfs, name):
    d = nin.yaz0(open(os.path.join(romfs, "UI", "MapTex", "MainField", name + ".sbmaptex"), "rb").read())
    r = d.find(b"BRTI", d.find(b"BNTX"))
    fmt, w, h, bh = (struct.unpack_from("<I", d, r + o)[0] for o in (0x1c, 0x24, 0x28, 0x34))
    assert fmt >> 8 == 0x1a, "BC1 map tiles"
    size = struct.unpack_from("<I", d, r + 0x50)[0]
    at = struct.unpack_from("<Q", d, struct.unpack_from("<Q", d, r + 0x70)[0])[0]
    # (the picture sits one GOB in: decoded a GOB wider, its first 32 columns are padding and it ends at 32 + 832)
    wide = (w * 2 + 63) // 64 * 64 // 2
    lin = deswizzle_px(d[at:at + size], wide // 4, h // 4, 1 << bh, 8)
    dds = (b"DDS " + struct.pack("<7I", 124, 0x81007, h, wide, len(lin), 0, 0) + b"\0" * 44 +
           struct.pack("<2I4s5I", 32, 4, b"DXT1", 0, 0, 0, 0, 0) + struct.pack("<4I", 0x1000, 0, 0, 0) + b"\0" * 4)
    im = Image.open(io.BytesIO(dds + lin)).convert("RGB")
    return im.crop((32, 0, wide, h)).resize((w, h), Image.LANCZOS)


def hyrule(romfs):
    """the game's map, x -5000..5000 and z -4000..4000 (tiles A..J, 1..8: 1000 m each)"""
    t = int(1000 * SCALE)
    out = Image.new("RGB", (10 * t, 8 * t))
    for ci, c in enumerate("ABCDEFGHIJ"):
        for r in range(8):
            out.paste(map_tile(romfs, f"MapTex1_{c}-{r + 1}").resize((t, t), Image.LANCZOS), (ci * t, r * t))
    return out


def region_raster(grid, w, h):
    """each pixel's region (an "L" image: its value is the region), for a picture of Hyrule w x h"""
    img = Image.new("L", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        z = -4000 + (y + 0.5) * 8000 / h
        for a, b, v in grid.runs[max(0, min(grid.rows - 1, int((z + 4000) // grid.step)))]:
            x0, x1 = int((a + 5000) * w / 10000 + 0.5), int((b + 5000) * w / 10000 + 0.5) - 1
            if x1 >= x0:
                d.line((x0, y, x1, y), fill=v)
    return img


def borders(img, raster, strength):
    """the regions' borders drawn on img: dark lines with a pale glow"""
    w, h = raster.size
    dx = ImageChops.difference(raster, ImageChops.offset(raster, 1, 0))
    dy = ImageChops.difference(raster, ImageChops.offset(raster, 0, 1))
    edge = ImageChops.lighter(dx, dy).point(lambda v: 255 if v else 0)
    edge.paste(0, (0, 0, w, 1)), edge.paste(0, (0, 0, 1, h))  # (offset wraps round)
    edge = edge.filter(ImageFilter.MaxFilter(3 if w <= 1000 else 5))
    glow = edge.filter(ImageFilter.GaussianBlur(3 if w <= 1000 else 6)).point(lambda v: int(min(255, v * 1.2) * 0.6 * strength))
    img.paste((250, 240, 205), mask=glow)
    img.paste((40, 32, 20), mask=edge.point(lambda v: int(v * strength)))
    return img


def centroids(raster, w, h):
    """each region's middle, in a w x h picture's pixels (from the raster, any size)"""
    acc = defaultdict(lambda: [0, 0, 0])
    px, rw, rh = raster.load(), raster.width, raster.height
    for y in range(rh):
        for x in range(rw):
            a = acc[px[x, y]]
            a[0] += x
            a[1] += y
            a[2] += 1
    return {v: ((a[0] / a[2] + 0.5) * w / rw, (a[1] / a[2] + 0.5) * h / rh) for v, a in acc.items()}


def label(img, xy, text, size):
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, size)
    d.text(xy, text, font=f, fill=(250, 244, 220), anchor="mm", stroke_width=max(2, size // 8), stroke_fill=(30, 24, 14))


def icon(romfs, overlay, actor):
    for base in (overlay, romfs):
        p = os.path.join(base, "UI", "StockItem", f"{actor}.sbitemico")
        if os.path.exists(p):
            return picture(open(p, "rb").read())
    return None


def hud_textures(romfs):
    """{name: texture} of the game's layouts (Bootup.pack's and Layout/*): its map and HUD icons"""
    from botw_assets import bntx_textures  # (launcher/botw_assets.py: BNTX textures)
    out = {}

    def scan(data, depth=0):
        if data[:4] == b"Yaz0":
            data = nin.yaz0(data)
        if data[:4] == b"SARC" and depth < 4:
            for v in nin.sarc(data).values():
                scan(v, depth + 1)
        elif data[:4] == b"BNTX":
            for k, v in bntx_textures(data).items():
                out.setdefault(k, v)
    scan(open(os.path.join(romfs, "Pack", "Bootup.pack"), "rb").read())
    for f in sorted(os.listdir(os.path.join(romfs, "Layout"))):
        scan(open(os.path.join(romfs, "Layout", f), "rb").read())
    return out


def glyph(tex, name, colour):
    """a layout icon as a shape in `colour`: two-channel ones (^t) keep their glyph in green, the rest in alpha"""
    from botw_assets import decode
    fmt, w, h, bh, raw = tex[name]
    im = decode(raw, fmt, w, h, bh)
    mask = im.split()[1] if name.endswith("^t") else im.split()[3]
    out = Image.new("RGBA", im.size, colour + (255,))
    out.putalpha(mask)
    return out.crop(mask.getbbox())


def slot(pic, glow=None, fill=0.78):
    """an inventory slot (dark, a thin gold rim) with the picture in it, a soft glow behind it in `glow`"""
    k = 4
    out = Image.new("RGBA", (64 * k, 64 * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((2 * k, 2 * k, 61 * k, 61 * k), 9 * k, fill=(30, 33, 38, 235), outline=(150, 128, 78, 255),
                        width=2 * k)
    d.rounded_rectangle((5 * k, 5 * k, 58 * k, 58 * k), 7 * k, outline=(255, 240, 200, 28), width=k)
    out = out.resize((64, 64), Image.LANCZOS)
    if glow:
        g = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((14, 14, 50, 50), fill=glow + (150,))
        out.alpha_composite(g.filter(ImageFilter.GaussianBlur(7)))
    k = 64 * fill / max(pic.size)  # (small glyphs up, big icons down)
    pic = pic.resize((max(1, round(pic.width * k)), max(1, round(pic.height * k))), Image.LANCZOS)
    out.alpha_composite(pic, ((64 - pic.width) // 2, (64 - pic.height) // 2))
    return out


def layered(tex, layers):
    """layout glyphs drawn over each other, centred (a marker's core and frame, say)"""
    parts = [glyph(tex, n, c) for n, c in layers]
    size = (max(p.width for p in parts), max(p.height for p in parts))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for p in parts:
        out.alpha_composite(p, ((size[0] - p.width) // 2, (size[1] - p.height) // 2))
    return out


def badge(pic, small):
    """a small icon in the corner of a bigger one (a chest on a shrine, say)"""
    out = pic.copy()
    small = small.copy()
    small.thumbnail((26, 26), Image.LANCZOS)
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 200), (64 - small.width - 4, 64 - small.height - 4), small)
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(2)))
    out.alpha_composite(small, (64 - small.width - 6, 64 - small.height - 6))
    return out


# items the game draws from its layouts: (texture, colour, glow, the + version's texture)
GLYPHS = {"mipha": ("Nt_IconSinJuNewMapL_01^s", (150, 205, 255), (70, 150, 235), "Nt_IconSinJuNewMapDLCL_01^s"),
          "daruk": ("Nt_IconSinJuNewMapL_00^s", (255, 175, 140), (215, 90, 60), "Nt_IconSinJuNewMapDLCL_00^s"),
          "revali": ("Nt_IconSinJuNewMapL_02^s", (160, 240, 215), (70, 190, 160), "Nt_IconSinJuNewMapDLCL_02^s"),
          "urbosa": ("Nt_IconSinJuNewMapL_03^s", (255, 225, 140), (235, 180, 60), "Nt_IconSinJuNewMapDLCL_03^s"),
          "sensor": ("Nt_SeekSensorIcon_00^s", (150, 235, 255), (60, 190, 230), "Nt_SeekSensorIconP_00^s"),
          "spirit_orb": ("Nt_MapDungeonNewL_00^t", (255, 220, 160), (255, 140, 40), None),
          "travel_medallion": ((("DLC_WarpMarkerMapVer_004_1_Frame^t", (255, 220, 120)),
                                ("DLC_WarpMarkerMapVer_004_1_Core^t", (140, 240, 210))), None, (60, 200, 170), None)}
GLOWS = {"paraglider": (120, 170, 220), "remote_bomb": (60, 190, 230), "magnesis": (60, 190, 230),
         "stasis": (60, 190, 230), "cryonis": (60, 190, 230), "master_sword": (90, 150, 255),
         "heart": (230, 70, 70), "stamina": (90, 220, 90), "korok": (240, 200, 60), "thunder_helm": (250, 220, 90),
         "zora_armor": (70, 150, 235), "maracas": (230, 90, 70)}
# the options: what each one adds, as the game draws it (an item's icon, or a layout glyph in a colour)
OPTION_ART = {"koroks": ("icon", "Obj_KorokNuts"), "chests": ("glyph", "Nt_StampIconTBoxL_00^s", (240, 215, 150)),
              "shrine_chests": ("glyph", "Nt_MapDungeonNewL_00^t", (130, 220, 255), "chest"),
              "divine_beast_chests": ("glyph", "Nt_IconSinJuNewMapL_01^s", (130, 220, 255), "chest"),
              "towers": ("glyph", "Nt_MapTowerNewL_00^t", (255, 200, 120)), "memories": ("icon", "Obj_Camera"),
              "quests": ("icon", "Obj_ProofBook"), "minigames": ("icon", "Obj_ProofGiantKiller"),
              "hestu": ("icon", "Obj_Maracas"), "dlc": ("icon", "Obj_Motorcycle"),
              "master_mode": ("glyph", "Nt_MapDeadIconL_00^t", (255, 120, 90)), "shop_sanity": ("icon", "PutRupee"),
              "region_lock": ("icon", "KeySmall")}


PANEL_W, PANEL_H = 290, 232  # (the Regions panel: Hyrule's 10 x 8, in the item column's width)


def region_pieces(base, raster):
    """the Regions panel as Hyrule: each region the game's map cut to its shape where it lies, (r, found picture,
    locked picture, left, top, width, height). Found: in colour, a green rim; locked: dark gray, a pale rim"""
    w, h = PANEL_W * 2, PANEL_H * 2  # (drawn at twice the size: sharp when PopTracker scales it)
    small_r = raster.resize((w, h), Image.NEAREST)
    colour = base.resize((w, h), Image.LANCZOS).convert("RGBA")
    gray = locked_look(colour)
    out = []
    for r in range(len(NAMES)):
        full = small_r.point(lambda v: 255 if v == r else 0)
        box = full.getbbox()
        if not box:
            continue
        box = (max(0, box[0] - 2), max(0, box[1] - 2), min(w, box[2] + 2), min(h, box[3] + 2))
        mask = full.crop(box)
        rim = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(5)))
        pics = []
        for src, edge in ((colour, (150, 235, 120, 255)), (gray, (200, 205, 210, 255))):
            pic = src.crop(box)
            pic.putalpha(mask)
            line = Image.new("RGBA", pic.size, edge)
            line.putalpha(rim)
            pic.alpha_composite(line)
            pics.append(pic)
        out.append((r, pics[0], pics[1], box[0] // 2, box[1] // 2, (box[2] - box[0]) // 2, (box[3] - box[1]) // 2))
    return out


def locked_look(img):
    """a locked region's look: the map gone dark gray"""
    g = img.convert("L").point(lambda v: int(30 + v * 0.35))
    return Image.merge("RGBA", (g, g, g, img.split()[3]))


# ---- the logic, as worlds/botw/__init__.py has it
def rule(l):
    r = {"reg": l.get("region", -1)}
    if "korok_seeds" in l:
        r["seeds"] = l["korok_seeds"]
    elif l["flag"].startswith("100enemy_"):
        r["trial"], r["freed"] = True, BEASTS
    elif l["dlc"]:
        r["powers"], r["freed"] = True, BEASTS
    elif l["flag"] == "Get_MasterSword_Finish":
        r["pull"] = True
    elif l["flag"] == "OldKorok_Help_Finish":
        r["maracas"] = True
    elif "Naboris" in l["name"] and l["category"] in ("Divine Beast", "Divine Beast Chest", "Main Quest"):
        r["helm"] = True
    name = l["name"].split(" Chest")[0] if l["category"] == "Shrine Chest" else l["name"]
    beasts, zora = next((v for k, v in NEEDS.items() if name == k or name.startswith(k + " ")), ([], False))
    if beasts:
        r["freed"] = sorted(set(r.get("freed", []) + beasts))
    if zora:
        r["zora"] = True
    shrine = l.get("dungeon") or SHRINE_DUNGEON.get(l["name"].split(" Chest")[0])
    if l["category"] == "Rune Terminal" or l["flag"] in RUNE_FREE:
        pass
    elif l.get("plateau") and shrine in SHRINE_RUNE:
        r["rune"] = SHRINE_RUNE[shrine]
    else:
        r["runes"] = True
    if not l.get("plateau"):
        r["glider"] = True
    return r


LOGIC = r"""-- the logic of worlds/botw (tools/poptracker.py writes this pack)
MS_HEARTS = 10
CLEARED = {}  -- the checks done (autotracking): a beast freed is its "Cleared" check
local function count(code)
  local o = Tracker:FindObjectForCode(code)
  if not o then return 0 end
  if o.Type == "toggle" then return o.Active and 1 or 0 end
  if o.Type == "progressive" then return o.CurrentStage end
  if o.Type == "consumable" then return o.AcquiredCount end
  return 0
end
function has(code) return count(code) > 0 end
local function all_runes() return has("remote_bomb") and has("magnesis") and has("stasis") and has("cryonis") end
local function powers() return has("mipha") and has("daruk") and has("revali") and has("urbosa") end
-- the regions Link can reach: from the Great Plateau, a neighbour with its map (off the plateau's: the paraglider)
function regions_open()
  local open = {}
  if not has("setting_region_lock") then for i = 0, 14 do open[i] = true end return open end
  open[PLATEAU] = true
  local todo = {PLATEAU}
  while #todo > 0 do
    local i = table.remove(todo)
    for _, j in ipairs(ADJACENT[i]) do
      if not open[j] and (j == PLATEAU or has(string.format("map_%02d", j))) and (i ~= PLATEAU or has("paraglider")) then
        open[j] = true
        table.insert(todo, j)
      end
    end
  end
  return open
end
function botw(id)
  local r = RULES[tonumber(id)]
  if not r then return false end
  if r.glider and not has("paraglider") then return false end
  if r.runes and not all_runes() then return false end
  if r.rune and not has(r.rune) then return false end
  if r.seeds and not (has("maracas") and count("korok") >= r.seeds) then return false end
  if r.trial and not (powers() and count("heart") >= MS_HEARTS and has("master_sword")) then return false end
  if r.powers and not powers() then return false end
  if r.pull and count("heart") < MS_HEARTS then return false end
  if r.maracas and not has("maracas") then return false end
  if r.helm and not has("thunder_helm") then return false end
  if r.zora and not has("zora_armor") then return false end
  if r.freed then for _, id in ipairs(r.freed) do if not CLEARED[id] then return false end end end
  if has("setting_region_lock") then
    if r.reg < 0 then
      for i = 0, 14 do if i ~= PLATEAU and not has(string.format("map_%02d", i)) then return false end end
    elseif not regions_open()[r.reg] then return false end
  end
  return true
end
function region_reachable(i) return regions_open()[tonumber(i)] == true end
"""

REGIONS_PANEL = r"""-- the Regions panel (tools/poptracker.py writes this pack): each region's piece of Hyrule, in colour once its map is
-- found. Click: the Hyrule map zooms onto it (again: back to all of Hyrule). Right-click: its map found or not, by hand
local zoomed = nil
local function piece(r, view)
  local code, map = string.format("region_%02d", r), string.format("map_%02d", r)
  local found = ImageReference:FromPackRelativePath(string.format("images/items/map_%02d.png", r))
  local locked = ImageReference:FromPackRelativePath(string.format("images/items/map_%02d_locked.png", r))
  local it = ScriptHost:CreateLuaItem()
  it.Name = view.name
  local function show() it.Icon = (r == PLATEAU or has(map)) and found or locked end
  it.CanProvideCodeFunc = function(self, c) return c == code end
  it.ProvidesCodeFunc = function(self, c) return 0 end
  it.OnLeftClickFunc = function(self)
    Tracker:UiHint("ActivateTab", "Hyrule")
    if zoomed == r then
      zoomed = nil
      Tracker:UiHint("Zoom Hyrule", "1")
      Tracker:UiHint("Pan Hyrule", HOME)
    else
      zoomed = r
      Tracker:UiHint("Zoom Hyrule", view.zoom)
      Tracker:UiHint("Pan Hyrule", view.pan)
    end
  end
  it.OnRightClickFunc = function(self)
    local o = Tracker:FindObjectForCode(map)
    if o then o.Active = not o.Active end
  end
  show()
  if r ~= PLATEAU then ScriptHost:AddWatchForCode(code, map, show) end
end
for r, view in pairs(REGION_VIEWS) do piece(r, view) end
"""

AUTOTRACKING = r"""-- Archipelago autotracking (tools/poptracker.py writes this pack): items, checked locations, the slot's options
ScriptHost:LoadScript("scripts/mapping.lua")
local function reset()
  for _, code in pairs(ITEM_MAPPING) do
    local o = Tracker:FindObjectForCode(code)
    if o then
      if o.Type == "toggle" then o.Active = false
      elseif o.Type == "progressive" then o.CurrentStage = 0
      elseif o.Type == "consumable" then o.AcquiredCount = 0 end
    end
  end
  for _, path in pairs(LOCATION_MAPPING) do
    local o = Tracker:FindObjectForCode(path)
    if o then o.AvailableChestCount = o.ChestCount end
  end
end
function onClear(slot_data)
  reset()
  CLEARED = {}
  local opts = slot_data and slot_data["options"] or {}
  for k, v in pairs(opts) do
    local o = Tracker:FindObjectForCode("setting_" .. k)
    if o then o.Active = (v == true or v == 1) end
  end
  if slot_data and slot_data["master_sword_hearts"] then MS_HEARTS = slot_data["master_sword_hearts"] end
end
function onItem(index, item_id, item_name, player_number)
  local code = ITEM_MAPPING[item_id]
  local o = code and Tracker:FindObjectForCode(code)
  if not o then return end
  if o.Type == "toggle" then o.Active = true
  elseif o.Type == "progressive" then o.CurrentStage = o.CurrentStage + 1
  elseif o.Type == "consumable" then o.AcquiredCount = o.AcquiredCount + o.Increment end
end
function onLocation(location_id, location_name)
  CLEARED[location_id] = true
  local path = LOCATION_MAPPING[location_id]
  local o = path and Tracker:FindObjectForCode(path)
  if o then o.AvailableChestCount = o.AvailableChestCount - 1 end
end
Archipelago:AddClearHandler("clear handler", onClear)
Archipelago:AddItemHandler("item handler", onItem)
Archipelago:AddLocationHandler("location handler", onLocation)
"""


def lua_table(rules, beast_ids):
    out = ["RULES = {"]
    for i, r in sorted(rules.items()):
        parts = [f"reg={r['reg']}"] + [f"{k}=true" for k in ("glider", "runes", "trial", "powers", "pull", "maracas", "helm",
                                                              "zora") if r.get(k)]
        if r.get("freed"):
            parts.append("freed={" + ",".join(str(beast_ids[b]) for b in r["freed"]) + "}")
        if "rune" in r:
            parts.append(f'rune="{r["rune"]}"')
        if "seeds" in r:
            parts.append(f"seeds={r['seeds']}")
        out.append(f"  [{i}]={{{','.join(parts)}}},")
    out.append("}")
    return "\n".join(out)


SHRINE_DUNGEON = {}


def main(ex, out_dir):
    romfs = os.path.join(ex, "romfs")
    overlay = os.path.join(os.path.dirname(ex.rstrip("/\\")), "ap_overlay")
    locs = json.load(open(os.path.join(WORLD, "data", "locations.json"), encoding="utf8"))
    reg = json.load(open(os.path.join(WORLD, "data", "regions.json"), encoding="utf8"))
    SHRINE_DUNGEON.update({l["name"]: l["dungeon"] for l in locs if l["category"] == "Shrine"})
    shrine_pos = {l["name"]: l["pos"] for l in locs if l["category"] == "Shrine" and l["pos"]}
    pack = os.path.join(out_dir, "BotW_AP")
    if os.path.isdir(pack):
        shutil.rmtree(pack)  # (only ever our own output)
    for d in ("images/items", "items", "locations", "maps", "layouts", "scripts"):
        os.makedirs(os.path.join(pack, d), exist_ok=True)
    grid = Grid(ex)

    # the maps
    base = hyrule(romfs)
    tiny = region_raster(grid, 200, 160)
    big_r = region_raster(grid, *base.size)
    big = Image.blend(base, Image.merge("RGB", [big_r.point([REGION_COLOURS[v][c] if v < len(REGION_COLOURS) else 0
                                                             for v in range(256)]) for c in range(3)]), 0.16)
    borders(big, big_r, 1.0)
    for r, (x, y) in centroids(tiny, *big.size).items():
        label(big, (x, y), NAMES[r], 30)
    big.save(os.path.join(pack, "images", "hyrule.png"))
    sw, sh = 1000, 800
    small = base.resize((sw, sh), Image.LANCZOS)
    sr = region_raster(grid, sw, sh)
    tint = Image.merge("RGB", [sr.point([REGION_COLOURS[v][c] if v < len(REGION_COLOURS) else 0 for v in range(256)])
                               for c in range(3)])
    small = Image.blend(small, tint, 0.55)
    borders(small, sr, 1.0)
    cents = centroids(tiny, sw, sh)
    for r, (x, y) in cents.items():
        label(small, (x, y - 26), NAMES[r], 19)
    small.save(os.path.join(pack, "images", "regions.png"))
    json.dump([{"name": "Hyrule", "location_size": 16, "location_border_thickness": 2, "img": "images/hyrule.png"},
               {"name": "Regions", "location_size": 26, "location_border_thickness": 3, "img": "images/regions.png"}],
              open(os.path.join(pack, "maps", "maps.json"), "w"), indent=1)

    # the items
    ids = item_ids()
    items, mapping = [], {}
    tex = hud_textures(romfs)
    pieces = region_pieces(base, big_r)
    for r, found, locked, *_ in pieces:
        found.save(os.path.join(pack, "images", "items", f"map_{r:02d}.png"))
        locked.save(os.path.join(pack, "images", "items", f"map_{r:02d}_locked.png"))
    items.append({"name": NAMES[PLATEAU], "type": "static", "img": f"images/items/map_{PLATEAU:02d}.png",
                  "codes": f"map_{PLATEAU:02d}"})  # (no map: Link starts there)
    for name, (code, kind, n, actor) in ITEMS.items():
        if name not in ids:
            continue
        img = f"images/items/{code}.png"
        img2 = None  # (the "+" stage's own picture, where the game has one)
        if code in GLYPHS:
            t, colour, glow, plus = GLYPHS[code]
            pic = slot(layered(tex, t) if colour is None else glyph(tex, t, colour), glow)
            if plus:
                img2 = f"images/items/{code}_plus.png"
                slot(glyph(tex, plus, colour), glow).save(os.path.join(pack, img2))
        elif actor:
            pic = icon(romfs, overlay, actor)
            pic = slot(pic, GLOWS.get(code)) if pic else slot(Image.new("RGBA", (8, 8)))
        else:  # (a region's map: its piece of the Regions panel, drawn above)
            items.append({"name": name, "type": "toggle", "img": img, "disabled_img": img.replace(".png", "_locked.png"),
                          "codes": code})
            mapping[ids[name]] = code
            continue
        pic.save(os.path.join(pack, img))
        if kind == "toggle":
            items.append({"name": name, "type": "toggle", "img": img, "codes": code})
        elif kind == "progressive":
            items.append({"name": name, "type": "progressive", "allow_disabled": True, "codes": code,
                          "stages": [{"img": img2 if i and img2 else img, "codes": f"{code}{i + 1}",
                                      "name": f"{name} {i + 1}",
                                      "img_mods": "" if i == 0 or img2 else "overlay|images/plus.png"}
                                     for i in range(n)]})
        else:
            items.append({"name": name, "type": "consumable", "img": img, "codes": code, "max_quantity": n,
                          "min_quantity": 0, "increment": 1})
        mapping[ids[name]] = code
    plus = Image.new("RGBA", (64, 64))
    ImageDraw.Draw(plus).text((52, 50), "+", fill=(255, 250, 220, 255), anchor="mm", stroke_width=3,
                              stroke_fill=(30, 24, 14, 255), font=ImageFont.truetype(FONT, 30))
    plus.save(os.path.join(pack, "images", "plus.png"))
    chest = glyph(tex, "Nt_StampIconTBoxL_00^s", (240, 215, 150))
    for k, on in OPTIONS.items():
        img = f"images/items/setting_{k}.png"
        art = OPTION_ART[k]
        pic = icon(romfs, overlay, art[1]) if art[0] == "icon" else glyph(tex, art[1], art[2])
        pic = slot(pic, fill=0.66)
        if len(art) > 3:
            pic = badge(pic, chest)
        pic.save(os.path.join(pack, img))
        items.append({"name": k.replace("_", " ").title(), "type": "toggle", "img": img, "codes": f"setting_{k}",
                      "initial_active_state": bool(on)})
    json.dump(items, open(os.path.join(pack, "items", "items.json"), "w"), indent=1)

    # the locations: pins on the Hyrule map, and the Regions panel's
    def where(l):
        if l.get("spot"):  # (no place of its own, or a Divine Beast's: where the tracker shows it, tools/extract.py)
            return l["spot_at"], l["spot"]
        if l["category"] in ("Shrine Chest", "Rune Terminal"):
            base = l["name"].split(" Chest")[0].replace(" Terminal", "")
            return base, shrine_pos.get(base)
        if l["category"] == "Shrine":
            return l["name"], l["pos"]
        m = re.match(r"(.*?)(?: #\d+)?(?: \(.*\))?$", l["name"])
        return m.group(1), l["pos"]

    pins = defaultdict(list)
    for l in locs:
        base, pos = where(l)
        pins[("Hyrule", base) if pos else ("Regions", NAMES[l["region"]] + " region" if l["region"] >= 0 else "Anywhere")].append((l, pos))
    rules, loc_map, out_locs = {}, {}, []
    for (mp, pin), members in sorted(pins.items()):
        sections = []
        for l, _ in members:
            own = l["name"].startswith(pin)  # (a pin named for its place holds checks of every name)
            sec = (l["name"][len(pin):].strip(" -") if own else l["name"]) or l["category"] if mp == "Hyrule" else l["name"]
            if mp == "Hyrule" and l["category"] in ("Shrine Chest", "Rune Terminal"):
                sec = l["name"][len(pin):].strip() or l["category"]
            names = {s["name"] for s in sections}
            while sec in names:
                sec += "'"
            lid = l["hash"]
            rules[lid] = rule(l)
            need = ([f"setting_{CATEGORY_OPTION[l['category']]}"] if l["category"] in CATEGORY_OPTION else []) +                 (["setting_dlc"] if l["dlc"] else []) + (["setting_master_mode"] if l.get("master_mode") else [])
            s = {"name": sec, "item_count": 1, "access_rules": [f"$botw|{lid}"]}
            if need:  # (shown only with the options it needs on)
                s["visibility_rules"] = [",".join(need)]
            sections.append(s)
            loc_map[7_400_000_000 + lid] = f"@{pin}/{sec}"
        if mp == "Hyrule":
            xs = [p[0] for _, p in members]
            zs = [p[1] for _, p in members]
            x, z = sum(xs) / len(xs), sum(zs) / len(zs)
            spot = {"map": "Hyrule", "x": int((x + 5000) * SCALE), "y": int((z + 4000) * SCALE)}
        else:
            r = NAMES.index(pin[:-len(" region")]) if pin != "Anywhere" else None
            cx, cy = cents[r] if r is not None else (60, 60)
            spot = {"map": "Regions", "x": int(cx), "y": int(cy + 6)}
        out_locs.append({"name": pin, "sections": sections, "map_locations": [spot]})
    json.dump(out_locs, open(os.path.join(pack, "locations", "locations.json"), "w"), indent=0)

    # scripts
    adj = "ADJACENT = {" + ", ".join(f"[{i}]={{{','.join(map(str, a))}}}" for i, a in enumerate(reg["adjacent"])) + "}"
    beast_ids = {b: 7_400_000_000 + l["hash"] for l in locs for b in BEASTS if l["name"] == f"{b} Cleared"}
    open(os.path.join(pack, "scripts", "logic.lua"), "w").write(f"PLATEAU = {reg['plateau']}\n{adj}\n{lua_table(rules, beast_ids)}\n{LOGIC}")
    with open(os.path.join(pack, "scripts", "mapping.lua"), "w", encoding="utf8") as f:
        f.write("ITEM_MAPPING = {\n" + "".join(f"  [{i}]=\"{c}\",\n" for i, c in mapping.items()) + "}\n")
        f.write("LOCATION_MAPPING = {\n" + "".join(f"  [{i}]={json.dumps(p, ensure_ascii=False)},\n" for i, p in loc_map.items()) + "}\n")
    open(os.path.join(pack, "scripts", "autotracking.lua"), "w").write(AUTOTRACKING)
    # the Regions panel's pieces: where the Hyrule map goes when one is clicked (its middle, a zoom that fits it)
    mw, mh = big.size
    k = mw / PANEL_W
    views = ",\n".join(
        f'  [{r}]={{name={json.dumps(NAMES[r])}, pan="{int((x + w / 2) * k)},{int((y + h / 2) * k)}", '
        f'zoom="{min(mw / (w * k), mh / (h * k)) * 0.85:.2f}"}}' for r, _, _, x, y, w, h in pieces)
    open(os.path.join(pack, "scripts", "regions.lua"), "w").write(
        f'REGION_VIEWS = {{\n{views}\n}}\nHOME = "{mw // 2},{mh // 2}"\n{REGIONS_PANEL}')
    open(os.path.join(pack, "scripts", "init.lua"), "w").write(
        'Tracker:AddItems("items/items.json")\nScriptHost:LoadScript("scripts/logic.lua")\n'
        'Tracker:AddMaps("maps/maps.json")\nTracker:AddLocations("locations/locations.json")\n'
        'ScriptHost:LoadScript("scripts/regions.lua")\nTracker:AddLayouts("layouts/tracker.json")\n'
        'if PopVersion and PopVersion >= "0.18.0" then ScriptHost:LoadScript("scripts/autotracking.lua") end\n')

    # the layout: items on the left (the Regions panel: Hyrule in pieces, each region where it lies), the two maps in
    # tabs. Big pieces first: a small one drawn later stays clickable over a big one's corner
    regions = {"type": "group", "header": "Regions", "content": {
        "type": "canvas", "width": PANEL_W, "height": PANEL_H, "content": [
            {"type": "item", "item": f"region_{r:02d}", "canvas_left": x, "canvas_top": y, "width": w, "height": h}
            for r, _, _, x, y, w, h in sorted(pieces, key=lambda p: -p[5] * p[6])]}}
    main_rows = [["paraglider", "remote_bomb", "magnesis", "stasis", "cryonis"],
                 ["mipha", "daruk", "revali", "urbosa", "sensor"],
                 ["master_sword", "heart", "stamina", "spirit_orb", "korok"],
                 ["thunder_helm", "zora_armor", "maracas", "travel_medallion", ""]]
    option_rows = [[f"setting_{k}" for k in list(OPTIONS)[i:i + 5]] for i in range(0, len(OPTIONS), 5)]
    group = lambda title, rows, size: {"type": "group", "header": title, "content": {
        "type": "itemgrid", "item_margin": "4,4", "item_size": size, "rows": rows}}
    left = {"type": "array", "orientation": "vertical", "content": [
        group("Items", main_rows, 50), regions, group("Options", option_rows, 40)]}
    layout = {
        "tracker_default": {"type": "container", "background": "#14171b", "content": {"type": "dock", "content": [
            {"type": "dock", "dock": "left", "v_alignment": "stretch", "content": left},
            {"type": "tabbed", "tabs": [{"title": "Hyrule", "content": {"type": "map", "maps": ["Hyrule"]}},
                                        {"title": "Regions", "content": {"type": "map", "maps": ["Regions"]}}]}]}},
        "tracker_broadcast": {"type": "array", "orientation": "vertical", "content": [
            group("Items", main_rows, 50), regions]},
    }
    json.dump(layout, open(os.path.join(pack, "layouts", "tracker.json"), "w"), indent=1)
    json.dump({"name": "Breath of the Wild Archipelago (Savage Wind)", "game_name": "Breath of the Wild",
               "package_uid": "botw_ap_savagewind", "package_version": "0.4.8", "platform": "switch",
               "variants": {"standard": {"display_name": "Map Tracker", "flags": ["ap"]}}},
              open(os.path.join(pack, "manifest.json"), "w"), indent=1)
    z = os.path.join(out_dir, "BotW_AP.zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(pack):
            for fn in files:
                p = os.path.join(root, fn)
                zf.write(p, os.path.relpath(p, pack))
    print(f"PopTracker pack: {len(out_locs)} pins, {len(rules)} checks, {len(items)} items -> {z}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
