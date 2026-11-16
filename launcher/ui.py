"""The launcher's window: the Sheikah Slate's map of Hyrule. Each setup step is a landmark where it really is - the four
Divine Beasts (the steps Play needs), the Master Sword (the optional Archipelago world and PopTracker pack) and, last,
the Shrine of Resurrection (ready: wake up and Play). A beast still to do glows with Ganon's malice and fills with
Sheikah blue while its step runs; once all four are free, the malice leaves Hyrule Castle. Click a landmark to see its
step; the panel on the right holds the connection and the one big button (Choose / Set up / Play).

Everything is drawn with the player's own game files when Savage Wind's folder is known (botw_assets.py: the font, the
logo, the map, the HUD's Divine Beast / shrine / castle icons, the message window, the selection cursor); a plain look
until then.
"""
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageTk

import launcher as L

W, H = 1120, 720
CREAM, MUTED, DIM = (236, 228, 204), (169, 162, 143), (111, 106, 94)
SHEIKAH, GOLD, RED, ORANGE = (79, 211, 232), (217, 180, 74), (232, 82, 74), (232, 140, 64)
CURSOR = (250, 224, 120)  # (the game's selection cursor)
MALICE = (214, 62, 118)  # (Ganon's)
ENTRY_BG = "#121418"
LINKS = (("ap_deathlink", "DeathLink"), ("ap_traplink", "TrapLink"), ("ap_ringlink", "RingLink"))

# the map: world x -5000..5000, z -4000..4000. At rest the window shows it from (X0, Z0) at S pixels a metre (all of
# Hyrule left of the panel); while setting up, the panel slides away and the camera flies to the beast being freed.
S, X0, Z0 = 0.08, -4300, -3616
OVERVIEW = (X0 + W / 2 / S, Z0 + H / 2 / S, S)  # (camera: centre x, z and pixels a metre)
HI = 0.2  # (the map is kept at this many pixels a metre: room to zoom in)
ZOOM, SLACK = 0.22, 200  # (close-up scale; how far past Hyrule's edge a close-up may look, in pixels)
PAD = 60  # (the kept map's margin past Hyrule's edge, in its pixels)
COL = 728  # (the right column: logo, panel)
SIDE_HIDE = W - COL + 70  # (how far it slides out)
STEP_LM = {"exe": "rudania", "overlay": "medoh", "flags": "naboris", "apworld": "sword", "poptracker": "sword"}
PANEL = (COL, 178, 1094, 640)
PILL = (34, 652, 700, 708)  # (the message window)
CASTLE = (-254, -950)  # (the keep: the map marker sits on Castle Town, south of it)
# key, where (the game's own map markers: a beast's where it rests once freed), icon (solid, outline), name, what it stands for, status() steps
LANDMARKS = (
    ("ruta", (2971, 233), ("Nt_IconSinJuNewMapL_01^s", "Nt_IconSinJuNewLineL_01^s"), "Vah Ruta", "Savage Wind", ("sw",)),
    ("rudania", (2454, -2561), ("Nt_IconSinJuNewMapL_00^s", "Nt_IconSinJuNewLineL_00^s"), "Vah Rudania",
     "Archipelago build", ("exe",)),
    ("medoh", (-3614, -1862), ("Nt_IconSinJuNewMapL_02^s", "Nt_IconSinJuNewLineL_02^s"), "Vah Medoh", "Overlay",
     ("overlay",)),
    ("naboris", (-2111, 2627), ("Nt_IconSinJuNewMapL_03^s", "Nt_IconSinJuNewLineL_03^s"), "Vah Naboris",
     "Launch options", ("flags",)),
    ("sword", (250, -2210), ("Nt_PauseIconL_00^s", None), "Master Sword", "World & tracker", ("apworld", "poptracker")),
    ("sor", (-1102, 1880), ("Nt_MapStartPointNewL_00^t", None), "Shrine of Resurrection", "Play", ()),
)
BEASTS = ("ruta", "rudania", "medoh", "naboris")
REQUIRED = ("sw", "exe", "overlay", "flags")


def hexc(c):
    return "#%02x%02x%02x" % c[:3]


def rounded(size, radius, fill=None, outline=None, width=1):
    im = Image.new("RGBA", size)
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=fill, outline=outline, width=width)
    return im


def fade_bar(w, h, colour, peak):
    """a bar of light, brightest in the middle and fading out to both ends (the game's selected row)"""
    row = Image.new("L", (w, 1))
    row.putdata([int(peak * math.sin(math.pi * (x + 0.5) / w) ** 0.6) for x in range(w)])
    im = Image.new("RGBA", (w, h), colour[:3] + (0,))
    im.putalpha(row.resize((w, h)))
    return im


def cursor_frame(w, h, spread):
    """the game's selection cursor: four glowing yellow corners around a box, `spread` px out"""
    m = 16
    im = Image.new("RGBA", (w + 2 * m, h + 2 * m))
    d = ImageDraw.Draw(im)
    arm = min(18, h // 2)
    x0, y0, x1, y1 = m - spread, m - spread, m + w + spread - 1, m + h + spread - 1
    for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        d.line((cx, cy, cx + sx * arm, cy), fill=CURSOR + (255,), width=3)
        d.line((cx, cy, cx, cy + sy * arm), fill=CURSOR + (255,), width=3)
    glow = im.filter(ImageFilter.GaussianBlur(4))
    out = Image.new("RGBA", im.size)
    out.alpha_composite(glow)
    out.alpha_composite(glow)
    out.alpha_composite(im)
    return out


def tint(mask, colour, alpha=255):
    """a mask ("L") in a colour"""
    im = Image.new("RGBA", mask.size, colour[:3] + (255,))
    im.putalpha(mask.point(lambda v: v * alpha // 255) if alpha != 255 else mask)
    return im


def glow(size, colour, alpha, blur):
    im = Image.new("RGBA", (size, size), colour[:3] + (0,))
    ImageDraw.Draw(im).ellipse((blur, blur, size - blur, size - blur), fill=colour[:3] + (int(alpha),))
    return im.filter(ImageFilter.GaussianBlur(blur / 2))


class Skin:
    """text and HUD pictures: the game's when its files are there, else drawn"""

    def __init__(self, sw):
        self.a = None
        if sw:
            try:
                import botw_assets
                self.a = botw_assets.Assets(sw)
            except Exception:
                traceback.print_exc()
                self.a = None
        self._fallback, self._masks = {}, {}

    def text(self, s, size, colour=CREAM, alpha=255):
        if self.a:  # (the game's font has no "…")
            return self.a.normal.render(s.replace("…", "..."), size, colour + (alpha,))
        f = self._fallback.get(size)
        if f is None:
            from PIL import ImageFont
            try:
                f = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf"), int(size * 0.78))
            except OSError:
                f = ImageFont.load_default()
            self._fallback[size] = f
        box = f.getbbox(s or " ")
        im = Image.new("RGBA", (max(1, box[2] + 2), int(size * 1.05)), colour + (0,))
        ImageDraw.Draw(im).text((0, size * 0.08), s, font=f, fill=colour + (alpha,))
        return im

    def shadowed(self, s, size, colour=CREAM):
        """text with a soft dark shadow, to read over the map"""
        t = self.text(s, size, colour)
        dark = Image.new("RGBA", t.size, (0, 0, 0, 0))
        dark.putalpha(t.split()[3].point(lambda v: v if v > 60 else 0))  # (the font's faint cell edges cast none)
        blur = Image.new("RGBA", (t.width + 8, t.height + 8))
        blur.alpha_composite(dark, (4, 5))
        blur = blur.filter(ImageFilter.GaussianBlur(3))
        out = Image.new("RGBA", blur.size)
        out.alpha_composite(blur)
        out.alpha_composite(blur)
        out.alpha_composite(t, (4, 4))
        return out

    def sheikah(self, s, size, colour=SHEIKAH, alpha=255):
        return self.a.sheikah.render(s, size, colour + (alpha,)) if self.a else None

    def hud(self, name, colour=None, size=None):
        if not self.a or name not in self.a.tex:
            return None
        return self.a.hud(name, colour + (255,) if colour and len(colour) == 3 else colour, size)

    def mask(self, name, size):
        """a HUD icon's shape (the green channel of the map's two-channel icons), `size` square"""
        k = (name, size)
        if k not in self._masks:
            m = None
            if self.a and name and name in self.a.tex:
                im = self.a.hud(name)
                m = im.split()[1 if name.endswith("^t") else 3]
                box = m.point(lambda v: 255 if v > 20 else 0).getbbox()
                if name.startswith("Nt_MapCastle") and box:  # (its castle is the dark cut-out in its plate)
                    m = ImageChops.invert(im.split()[0]).crop(box)
                    box = m.point(lambda v: 255 if v > 20 else 0).getbbox()
                    m = m.crop(box) if box else m
                    box = (0, 0) + m.size
                if box:  # (trimmed and fitted, kept square)
                    m = m.crop(box)
                    k2 = size / max(m.size)
                    fit = m.resize((max(1, round(m.width * k2)), max(1, round(m.height * k2))), Image.LANCZOS)
                    m = Image.new("L", (size, size))
                    m.paste(fit, ((size - fit.width) // 2, (size - fit.height) // 2))
            self._masks[k] = m
        return self._masks[k]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Breath of the Wild x Archipelago")
        self.configure(bg="#0b0d10")
        self.geometry(f"{W}x{H}")
        self.resizable(False, False)
        ico = os.path.join(L.PAYLOAD, "launcher.ico")
        if os.path.exists(ico):
            self.iconbitmap(ico)
        self.cfg = self.load_cfg()
        self.q, self.busy = queue.Queue(), False
        self.sw_update = {}  # (Savage Wind folder -> its updater's answer: status, version)
        self.live, self.shown, self.active = {}, {}, None  # (the setup's progress, per status() step)
        self.c = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg="#0b0d10")
        self.c.pack()
        self.imgs, self.cache, self.hover_key, self.t0 = {}, {}, None, time.time()
        self.log_lines, self.typing, self.typed = [], "", 0
        self.mode, self.lm_keys = "connect", {}
        self.cam, self.focus, self.focus_t, self.side_off = list(OVERVIEW), None, 0.0, 0
        self.c.create_text(W // 2, H // 2, text="Unfolding the map of Hyrule…", fill=hexc(MUTED), font=("Segoe UI", 14))
        self.update()
        self.fields, self.entries = {}, {}
        self.build()
        self.bind("<Return>", lambda e: self.primary()[1]())
        self.after(30, self.tick)

    # ---------------------------------------------------------------- config
    def load_cfg(self):
        try:
            cfg = L.json.load(open(L.CONFIG, encoding="utf8"))
        except (OSError, ValueError):
            cfg = {}
        cfg.setdefault("sw", L.guess_sw())
        cfg.setdefault("archipelago", L.default_archipelago())
        cfg.setdefault("poptracker", "")
        return cfg

    def save_cfg(self):
        os.makedirs(os.path.dirname(L.CONFIG), exist_ok=True)
        L.json.dump(self.cfg, open(L.CONFIG, "w", encoding="utf8"), indent=1)

    def sw_ready(self):
        sw = self.cfg.get("sw", "")
        return bool(sw) and os.path.isdir(os.path.join(sw, "extracted", "romfs"))

    def choose(self, key, hint):
        p = filedialog.askdirectory(title=hint, initialdir=self.cfg.get(key) or None)
        if p:
            self.cfg[key] = os.path.normpath(p)
            self.save_cfg()
            self.build()

    # ---------------------------------------------------------------- pictures
    def photo(self, key, im):
        p = ImageTk.PhotoImage(im)
        self.imgs[key] = p
        return p

    def put(self, key, im, x, y, anchor="nw", tags=()):
        return self.c.create_image(x, y, image=self.photo(key, im), anchor=anchor, tags=tags)

    def hyrule(self):
        """the game's whole map at HI pixels a metre, dimmed: made once from the player's files, then kept beside the
        launcher's settings (it is theirs: it never leaves their computer)"""
        cache = os.path.join(os.path.dirname(L.CONFIG), "hyrule_map.png")
        t = round(1000 * HI)
        try:
            im = Image.open(cache)
            im.load()
            if im.size != (10 * t, 8 * t):
                raise OSError("an older map")
        except OSError:
            from poptracker import map_tile  # (tools/poptracker.py: the tiles as the game's map has them)
            im = Image.new("RGB", (10 * t, 8 * t))
            for ci, c in enumerate("ABCDEFGHIJ"):
                for r in range(8):
                    im.paste(map_tile(self.skin.a.romfs, f"MapTex1_{c}-{r + 1}").resize((t, t), Image.LANCZOS), (ci * t, r * t))
            try:
                os.makedirs(os.path.dirname(cache), exist_ok=True)
                im.save(cache)
            except OSError:
                pass
        im = ImageEnhance.Brightness(ImageEnhance.Color(im.convert("RGB")).enhance(0.75)).enhance(0.5)
        # past Hyrule's edge: its border colour, the map fading into it (a close-up may look a little past the edge)
        edge = im.crop((0, 0, im.width, 8)).resize((1, 1), Image.BOX).getpixel((0, 0))
        out = Image.new("RGB", (im.width + 2 * PAD, im.height + 2 * PAD), edge)
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).rectangle((24, 24, im.width - 25, im.height - 25), fill=255)
        out.paste(im, (PAD, PAD), mask.filter(ImageFilter.GaussianBlur(14)))
        return out, edge

    def screen(self, x, z):
        """a world spot, in the window, as the camera sees it now"""
        cx, cz, s = self.cam
        return (x - cx) * s + W / 2, (z - cz) * s + H / 2

    def map_frame(self):
        """the window's view of the map through the camera (past Hyrule's edge: its own border colour)"""
        if self.world is None:
            return self.flat
        cx, cz, s = self.cam
        out = Image.new("RGB", (W, H), self.void)
        wx0, wz0, wx1, wz1 = cx - W / 2 / s, cz - H / 2 / s, cx + W / 2 / s, cz + H / 2 / s
        e = PAD / HI  # (the padded world reaches this far past Hyrule)
        ix0, iz0, ix1, iz1 = max(wx0, -5000 - e), max(wz0, -4000 - e), min(wx1, 5000 + e), min(wz1, 4000 + e)
        size = (round((ix1 - ix0) * s), round((iz1 - iz0) * s))
        if size[0] > 0 and size[1] > 0:
            box = ((ix0 + 5000) * HI + PAD, (iz0 + 4000) * HI + PAD, (ix1 + 5000) * HI + PAD, (iz1 + 4000) * HI + PAD)
            out.paste(self.world.resize(size, Image.BILINEAR, box=box, reducing_gap=2.0),
                      (round((ix0 - wx0) * s), round((iz0 - wz0) * s)))
        return out

    def chrome(self):
        """what sits over the map: its vignette, the message window, and the right column (logo, panel) that slides"""
        vign = Image.new("L", (W // 8, H // 8), 0)  # (blurred small, then scaled up: the same softness, fast)
        ImageDraw.Draw(vign).ellipse((-W / 8 * 0.12, -H / 8 * 0.3, W / 8 * 1.12, H / 8 * 1.25), fill=255)
        dark = Image.new("RGBA", (W, H), (4, 5, 7, 255))
        dark.putalpha(ImageChops.invert(vign.filter(ImageFilter.GaussianBlur(110 / 8)).resize((W, H), Image.BILINEAR)))
        # the message window: the game's dark pill with its ornaments at both ends
        x0, y0, x1, y1 = PILL
        pill = Image.new("RGBA", (x1 - x0 + 44, y1 - y0))
        pill.alpha_composite(rounded((x1 - x0, y1 - y0), (y1 - y0) // 2, fill=(0, 0, 0, 200)), (22, 0))
        deco = self.skin.hud("Nt_MsgDecoL_00^s", CREAM + (210,), (15, y1 - y0 - 12))
        if deco:
            pill.alpha_composite(deco, (4, 6))
            pill.alpha_composite(deco.transpose(Image.FLIP_LEFT_RIGHT), (x1 - x0 + 25, 6))
        # the right column: a shade, the logo, then the Sheikah Slate's panel (drawn from x = COL - 60)
        side = Image.new("RGBA", (W - COL + 60, H), (4, 5, 7, 0))
        shade = Image.new("L", (side.width, 1))
        shade.putdata([int(200 * min(1, x / 90)) for x in range(side.width)])
        side.putalpha(shade.resize(side.size))
        logo, has_ap = self.skin.a.logo() if self.skin.a else (None, False)
        mid = (W - COL) // 2 + 60
        if logo:
            k = 166 / logo.height
            logo = logo.resize((int(logo.width * k), 166), Image.LANCZOS)
            sh = Image.new("RGBA", logo.size, (0, 0, 0, 0))
            sh.putalpha(logo.split()[3].filter(ImageFilter.GaussianBlur(6)).point(lambda v: v * 0.8))
            side.alpha_composite(sh, (mid - logo.width // 2 + 3, 9))
            side.alpha_composite(logo, (mid - logo.width // 2, 6))
            if not has_ap:
                t = self.skin.text("ARCHIPELAGO", 22, CREAM)
                side.alpha_composite(t, (mid - t.width // 2 + 20, 150))
        else:
            t = self.skin.text("BREATH OF THE WILD", 18, MUTED)
            side.alpha_composite(t, (mid - t.width // 2, 50))
            t = self.skin.text("ARCHIPELAGO", 46, CREAM)
            side.alpha_composite(t, (mid - t.width // 2, 74))
        x0, y0, x1, y1 = (v - (COL - 60) if i % 2 == 0 else v for i, v in enumerate(PANEL))
        side.alpha_composite(rounded((x1 - x0, y1 - y0), 12, fill=(6, 8, 10, 215), outline=CREAM + (60,), width=1), (x0, y0))
        corner = self.skin.hud("Nt_PauseCorner_00^s", CREAM + (170,), (40, 40))
        if corner:  # (the pause menu's corner ornaments)
            for k, (x, y) in enumerate(((x0 - 6, y0 - 6), (x1 - 34, y0 - 6), (x1 - 34, y1 - 34), (x0 - 6, y1 - 34))):
                side.alpha_composite(corner.transpose([None, Image.FLIP_LEFT_RIGHT, Image.ROTATE_180, Image.FLIP_TOP_BOTTOM][k])
                                     if k else corner, (x, y))
        return dark, pill, side

    # ---------------------------------------------------------------- the window
    def build(self):
        self.c.delete("all")
        for e in self.entries.values():
            e.destroy()
        self.skin = Skin(self.cfg.get("sw") if self.sw_ready() else None)
        self.world, self.void = self.hyrule() if self.skin.a else (None, (14, 17, 22))
        if self.world is None:  # (no game files yet: dusk)
            self.flat = Image.new("RGB", (W, H))
            d = ImageDraw.Draw(self.flat)
            for i in range(H):
                t = i / H
                d.line((0, i, W, i), fill=(int(28 - 14 * t), int(40 - 22 * t), int(58 - 34 * t)))
        self.cache.clear()
        self.lm_keys.clear()
        self.map_key, self.map_photo = None, ImageTk.PhotoImage("RGB", (W, H))
        self.c.create_image(0, 0, image=self.map_photo, anchor="nw", tags=("map",))
        vign, pill, side = self.chrome()
        self.put("vign", vign, 0, 0)
        # (the landmarks' pictures overlap and never take the mouse: the pointer picks the nearest icon, on_motion)
        self.c.create_image(0, 0, anchor="center", tags=("castle",), state="disabled")
        for lm in LANDMARKS:
            self.c.create_image(0, 0, anchor="nw", tags=(f"lm_{lm[0]}", f"lm_{lm[0]}_img"), state="disabled")
        self.c.bind("<Motion>", self.on_motion)
        self.c.bind("<Leave>", lambda e: self.on_motion(None))
        self.c.bind("<Button-1>", lambda e: (k := self.lm_at(e.x, e.y)) and self.show(k))
        self.put("pill", pill, PILL[0] - 22, PILL[1])
        self.put("side", side, COL - 60, 0, tags=("side",))
        swv = L.manifest_version(self.cfg["sw"]) if self.cfg.get("sw") else None
        ver = self.skin.text(f"Launcher {L.VERSION}  ·  Savage Wind {swv or 'not chosen'}  ·", 14, DIM)
        self.put("ver", ver, COL + 4, 668, tags=("side",))
        self.put("gh", self.skin.text("GitHub", 14, SHEIKAH), COL + 10 + ver.width, 668, tags=("link", "side"))
        self.c.tag_bind("link", "<Button-1>", lambda e: webbrowser.open(L.REPO))
        self.c.tag_bind("link", "<Enter>", lambda e: self.c.config(cursor="hand2"))
        self.c.tag_bind("link", "<Leave>", lambda e: self.c.config(cursor=""))
        self.c.move("side", self.side_off, 0)
        self.build_entries()
        self.refresh()
        self.draw_world()
        if not self.log_lines:
            self.say("Click Vah Ruta and choose your Savage Wind folder." if not self.sw_ready()
                     else "Welcome back, hero. Press Play." if self.primary()[0] == "Play"
                     else "Welcome back, hero. Press Set up to free the Divine Beasts.")

    def build_entries(self):
        ini = L.read_ini(self.cfg["sw"]) if self.cfg.get("sw") else {}
        self.entries, self.links = {}, {}
        for key, show in (("ap_server", ""), ("ap_slot", ""), ("ap_password", "•")):
            v = self.fields.get(key) or tk.StringVar(value=ini.get(key, "archipelago.gg:38281" if key == "ap_server" else ""))
            self.fields[key] = v
            self.entries[key] = tk.Entry(self, textvariable=v, show=show, bg=ENTRY_BG, fg=hexc(CREAM),
                                         insertbackground=hexc(CURSOR), relief="flat", font=("Segoe UI", 11),
                                         highlightthickness=0, borderwidth=4)
        for key, _ in LINKS:
            self.links[key] = int(ini.get(key, "0") or 0)

    # -- hover: the game's cursor, and a click
    def hoverable(self, tag, box, action, extra=()):
        """`tag` answers the mouse over `box` (a hit area that moves with it; `extra`: more tags for that area)"""
        self.c.create_rectangle(*box, outline="", fill="", tags=(tag, tag + "_hit") + tuple(extra))
        self.c.tag_bind(tag, "<Enter>", lambda e: self.set_hover((tag, tuple(round(v) for v in self.c.coords(tag + "_hit")))))
        self.c.tag_bind(tag, "<Leave>", lambda e: self.set_hover(None))
        self.c.tag_bind(tag, "<Button-1>", lambda e: action())

    def lm_at(self, x, y):
        """the landmark whose icon is under the pointer (the nearest, within reach), or None"""
        if self.busy or (not self.side_off and x >= COL - 10):
            return None
        best, hit = 30, None
        for lm in LANDMARKS:
            px, py = self.screen(*lm[1])
            d = math.hypot(x - px, y - py)
            if d < best:
                best, hit = d, lm[0]
        return hit

    def on_motion(self, e):
        hit = self.lm_at(e.x, e.y) if e else None
        cur = self.hover_key[0] if self.hover_key else None
        if hit:
            if cur != f"lm_{hit}":
                px, py = (round(v) for v in self.screen(*next(l[1] for l in LANDMARKS if l[0] == hit)))
                self.set_hover((f"lm_{hit}", (px - 24, py - 24, px + 24, py + 24)))
        elif cur and cur.startswith("lm_"):
            self.set_hover(None)

    def set_hover(self, h):
        if h and self.busy and h[0].startswith("lm_"):  # (the map is a show while setting up)
            h = None
        self.hover_key = h
        self.c.config(cursor="hand2" if h else "")
        self.c.delete("hover")

    def draw_hover(self):
        self.c.delete("hover")
        if not self.hover_key or not self.c.find_withtag(self.hover_key[0]):
            return
        tag, (x0, y0, x1, y1) = self.hover_key
        spread = round(2 + 2 * math.sin((time.time() - self.t0) * 5))  # (the cursor breathes, as in the game)
        key = ("cursor", x1 - x0, y1 - y0, spread, tag.startswith("lm_"))
        if key not in self.imgs:
            im = cursor_frame(x1 - x0, y1 - y0, spread)
            if not tag.startswith("lm_"):
                im.alpha_composite(fade_bar(x1 - x0, y1 - y0, CREAM, 46), (16, 16))
            self.imgs[key] = ImageTk.PhotoImage(im)
        # (under the item's own pictures, and never picked by the mouse: it can't steal the hover)
        self.c.create_image(x0 - 16, y0 - 16, image=self.imgs[key], anchor="nw", tags="hover", state="disabled")
        self.c.tag_lower("hover", tag)

    # ---------------------------------------------------------------- the landmarks
    def lm_state(self, lm):
        """(state, fill 0..1, word) - state: ok, todo, busy, bad, off"""
        key, steps = lm[0], lm[5]
        if key == "sor":
            ready = self.ready() and not self.busy
            return ("ok", 1, "Ready") if ready else ("off", 0, "Asleep")
        parts = []
        for s in steps:
            state = self.st.get(s, ("off", ""))[0]
            if self.busy and s in self.live and state != "off":
                f = self.shown.get(s, 0)
                state = "ok" if f >= 1 else "busy" if s == self.active or f > 0 else state
            parts.append((state, 1 if state == "ok" else self.shown.get(s, 0) if state == "busy" else 0))
        on = [p for p in parts if p[0] != "off"]
        if not on:
            return "off", 0, "Optional" if key == "sword" else "Waiting"
        fill = sum(f for _, f in on) / len(on)
        if any(s == "bad" for s, _ in on):
            return "bad", 0, "Needs you"
        if all(s == "ok" for s, _ in on):
            return "ok", 1, "Drawn" if key == "sword" else "Freed"
        if any(s == "busy" for s, _ in on):
            return "busy", fill, f"Freeing… {int(fill * 100)}%" if key != "sword" else f"Drawing… {int(fill * 100)}%"
        return "todo", fill, "Not yet"

    LM_W, LM_CY = 210, 70  # (a landmark's picture: its width; the icon's centre is at (LM_W // 2, LM_CY))

    def lm_img(self, lm, state, fill, word, pulse, shift, big=False):
        """a landmark: its icon, its glow and two labels (moved `shift` px sideways, to stay in the window)"""
        key, pos, (solid, line), name, label, _ = lm
        size, w, h = 64 if big else 38, self.LM_W, 150  # (big: the one the camera is on)
        cx, cy = w // 2, self.LM_CY
        im = Image.new("RGBA", (w, h))
        col = {"ok": CURSOR if key == "sor" else SHEIKAH, "busy": MALICE, "todo": MALICE, "bad": ORANGE, "off": DIM}[state]
        a = {"ok": 150, "busy": 110 + 70 * pulse, "todo": 60 + 50 * pulse, "bad": 120, "off": 0}[state]
        if a:
            g = glow(size * 2, SHEIKAH if state == "busy" and fill > 0.5 else col, a, size // 2)
            im.alpha_composite(g, (cx - size, cy - size))
        m, outline = self.skin.mask(solid, size), self.skin.mask(line, size) if line else None
        if m is None:  # (no game files yet: a marker)
            m = Image.new("L", (size, size))
            ImageDraw.Draw(m).regular_polygon((size / 2, size / 2, size / 2 - 10), 4, rotation=45, fill=255)
        if state == "ok":
            body = tint(m, col)
        else:
            body = tint(outline.point(lambda v: min(255, v * 3)), col) if outline else tint(m, col, 110 if state != "off" else 70)
            if fill > 0:  # (Sheikah blue rising through it)
                cut = Image.new("L", m.size)
                cut.paste(255, (0, round(size * (1 - fill)), size, size))
                body.alpha_composite(tint(ImageChops.multiply(m, cut), SHEIKAH))
        im.alpha_composite(body, (cx - size // 2, cy - size // 2))
        rows = [(label, 15, CREAM), (f"{name}  ·  {word}", 12, col if state != "off" else MUTED)]
        y = cy + size // 2 + 2
        if key == "sor":  # (its labels above it: below, they'd run into Vah Naboris)
            y = cy - size // 2 - 46
        for s, sz, c in rows:
            t = self.skin.shadowed(s, sz, c)
            tx = min(max(cx + shift - t.width // 2, 0), w - t.width)
            im.alpha_composite(t, (tx, y))
            y += t.height - 6
        return im

    def move_camera(self):
        """the camera eases toward its target: all of Hyrule, or (setting up) the beast being freed, which it keeps a
        few seconds after it is free so its turning blue is seen"""
        want = STEP_LM.get(self.active) if self.busy else None
        if want == self.focus:
            self.focus_t = 0.0
        elif self.focus is None:
            self.focus = want
        elif not self.focus_t:
            self.focus_t = time.time()  # (its step just ended: linger a moment)
        elif time.time() - self.focus_t > 2.2:
            self.focus, self.focus_t = want, 0.0
        if self.focus:
            x, z = next(l[1] for l in LANDMARKS if l[0] == self.focus)
            hx, hz = (W / 2 - SLACK) / ZOOM, (H / 2 - SLACK) / ZOOM
            target = (min(max(x, -5000 + hx), 5000 - hx), min(max(z, -4000 + hz), 4000 - hz), ZOOM)
        else:
            target = OVERVIEW
        now = time.time()
        k = 1 - math.exp(-2.6 * min(0.2, now - getattr(self, "cam_t", now)))  # (as fast at any frame rate)
        self.cam_t = now
        cx, cz, s = self.cam
        ns = math.exp(math.log(s) + (math.log(target[2]) - math.log(s)) * k)
        nx, nz = cx + (target[0] - cx) * k, cz + (target[1] - cz) * k
        if abs(nx - target[0]) * ns < 0.3 and abs(nz - target[1]) * ns < 0.3 and abs(ns / target[2] - 1) < 0.002:
            nx, nz, ns = target
        self.cam = [nx, nz, ns]
        return tuple(self.cam) == tuple(OVERVIEW)

    def draw_world(self):
        """the map through the camera, and everything on it where the camera puts it"""
        self.move_camera()
        cx, cz, s = self.cam
        mk = (round(cx * s), round(cz * s), round(s, 4))
        if mk != self.map_key:
            self.map_key = mk
            self.map_photo.paste(self.map_frame())
        pulse = 0.5 + 0.5 * math.sin((time.time() - self.t0) * 3)
        pq = round(pulse * 6) / 6
        if len(self.cache) > 300:  # (a setup's fills make many pictures: drop them all and redraw what's shown)
            self.cache.clear()
            self.lm_keys.clear()
        for lm in LANDMARKS:
            px, py = self.screen(*lm[1])
            state, fill, word = self.lm_state(lm)
            shift = round((min(max(px, 70), W - 70) - px) / 8) * 8  # (labels kept inside the window)
            big = self.busy and self.focus == lm[0]
            k = (lm[0], state, round(fill, 2), word, pq if state in ("busy", "todo") else 0, self.mode == lm[0], shift, big)
            if self.lm_keys.get(lm[0]) != k:
                self.lm_keys[lm[0]] = k
                if k not in self.cache:
                    im = self.lm_img(lm, state, fill, word, k[4], shift, big)
                    if self.mode == lm[0]:  # (the one the panel shows: the cursor stays on it)
                        im.alpha_composite(cursor_frame(44, 44, 1), (self.LM_W // 2 - 38, self.LM_CY - 38))
                    self.cache[k] = ImageTk.PhotoImage(im)
                self.c.itemconfig(f"lm_{lm[0]}_img", image=self.cache[k])
            self.c.coords(f"lm_{lm[0]}_img", round(px) - self.LM_W // 2, round(py) - self.LM_CY)
        # Hyrule Castle: Ganon's malice around it, until the four beasts are free
        freed = all(self.lm_state(lm)[0] == "ok" for lm in LANDMARKS if lm[0] in BEASTS)
        k = ("castle", freed, pq if not freed else 0)
        if self.lm_keys.get("castle") != k:
            self.lm_keys["castle"] = k
            if k not in self.cache:
                im = Image.new("RGBA", (110, 110))
                if not freed:
                    im.alpha_composite(glow(110, MALICE, 120 + 60 * k[2], 22))
                m = self.skin.mask("Nt_MapCastleL_00^t", 28)
                if m:
                    im.alpha_composite(tint(m, CREAM, 230), (41, 41))
                t = self.skin.shadowed("Hyrule Castle", 12, MUTED)
                im.alpha_composite(t, (55 - t.width // 2, 66))
                self.cache[k] = ImageTk.PhotoImage(im)
            self.c.itemconfig("castle", image=self.cache[k])
        self.c.coords("castle", *(round(v) for v in self.screen(*CASTLE)))

    # ---------------------------------------------------------------- the panel
    def ready(self):
        return all(self.st.get(k, ("off",))[0] in ("ok", "off") for k in REQUIRED) and self.st.get("sw", ("bad",))[0] == "ok"

    def primary(self):
        """the big button: (label, action, colour)"""
        if self.busy:
            return "Setting up…", lambda: None, DIM
        if self.st.get("sw", ("bad",))[0] != "ok":
            return "Choose Savage Wind", lambda: self.choose("sw", "Your Savage Wind folder (with savagewind.exe)"), SHEIKAH
        if any(s == "todo" for s, _ in self.st.values()):
            return "Set up", self.do_setup, SHEIKAH
        return "Play", self.do_play, GOLD

    def show(self, mode):
        if self.busy and mode != "connect":
            return
        self.mode = "connect" if mode == self.mode else mode
        self.draw_panel()

    def row(self, tag, label, y, action, colour=CREAM, size=18, arrow=True):
        """a clickable row in the panel"""
        x0, x1 = PANEL[0] + 18, PANEL[2] - 18
        t = self.skin.text(label, size, colour)
        im = Image.new("RGBA", (x1 - x0, t.height + 12))
        im.alpha_composite(t, (28 if arrow else 10, 7))
        if arrow:
            m = im.height // 2
            ImageDraw.Draw(im).polygon((12, m - 5, 19, m, 12, m + 5), fill=CURSOR + (255,))
        self.put(tag, im, x0, y, tags=("panel", tag))
        self.hoverable(tag, (x0, y, x1, y + im.height), action, ("panel",))
        return y + im.height + 4

    def lines(self, s, y, size=16, colour=MUTED, width=40):
        for chunk in self.wrap(s, width):
            self.put(("ln", y, chunk), self.skin.text(chunk, size, colour), PANEL[0] + 26, y, tags=("panel",))
            y += size + 6
        return y

    @staticmethod
    def short(p, n=40):
        return p if len(p) <= n else "…" + p[-(n - 1):]

    def draw_panel(self):
        self.c.delete("panel")
        for e in self.entries.values():
            e.place_forget()
        x0, y0, x1, y1 = PANEL
        lm = next((l for l in LANDMARKS if l[0] == self.mode), None)
        title = "Connect" if not lm else lm[3]
        self.put("p_title", self.skin.text(title, 26, CREAM), x0 + 24, y0 + 14, tags=("panel",))
        self.put("p_line", fade_bar(x1 - x0 - 48, 1, CREAM, 120), x0 + 24, y0 + 52, tags=("panel",))
        y = y0 + 64
        if not lm:
            for key, label in (("ap_server", "Server"), ("ap_slot", "Slot name"), ("ap_password", "Password")):
                self.put(f"p_l_{key}", self.skin.text(label, 15, MUTED), x0 + 24, y, tags=("panel",))
                if not self.side_off:
                    self.entries[key].place(x=x0 + 24, y=y + 20, width=x1 - x0 - 48, height=26)
                self.put(f"p_u_{key}", fade_bar(x1 - x0 - 48, 1, CREAM, 110), x0 + 24, y + 47, tags=("panel",))
                y += 54
            y += 2
            for key, label in LINKS:  # (as the game's Options screen has its settings: name, then < value >)
                tag = f"p_link_{key}"
                self.put(tag, self.toggle_img(label, self.links[key]), x0 + 20, y, tags=("panel", tag, tag + "_img"))
                self.hoverable(tag, (x0 + 16, y - 2, x1 - 16, y + 32), lambda k=key: self.flip_link(k), ("panel",))
                y += 34
            self.lines("Click a landmark on the map to see its step.", y + 4, 15, DIM, 46)
        else:
            state, _, word = self.lm_state(lm)
            self.put("p_sub", self.skin.text(f"{lm[4]}  ·  {word}", 16, SHEIKAH if state == "ok" else
                                             ORANGE if state == "bad" else MUTED), x0 + 24, y, tags=("panel",))
            y += 30
            if lm[0] == "sor":
                left = [n for l in LANDMARKS if l[0] in BEASTS and self.lm_state(l)[0] != "ok" for n in (l[4],)]
                y = self.lines("Hyrule is ready. Press Play and wake up, hero." if not left else
                               "Free the Divine Beasts first: " + ", ".join(left) + ". Press Set up.", y)
            for s in lm[5]:
                st, text = self.st.get(s, ("off", "Waiting for the Savage Wind folder."))
                if lm[0] == "sword":
                    y = self.lines({"apworld": "Archipelago world", "poptracker": "PopTracker pack"}[s], y, 18, CREAM) + 2
                y = self.lines(text, y) + 4
                folder = {"sw": ("sw", "Savage Wind folder", "Your Savage Wind folder (with savagewind.exe)"),
                          "apworld": ("archipelago", "Archipelago folder", "Your Archipelago folder"),
                          "poptracker": ("poptracker", "PopTracker folder", "Your PopTracker folder")}.get(s)
                if folder:
                    k, label, hint = folder
                    y = self.lines(self.short(self.cfg.get(k) or "Not chosen"), y, 14, DIM, 60)
                    y = self.row(f"p_choose_{s}", f"Choose your {label}", y + 2,
                                 lambda k=k, h=hint: self.choose(k, h)) + 8
                if s == "exe" and self.cfg.get("sw") and not self.busy:
                    y = self.row("p_restore", "Restore the original Savage Wind", y + 4, self.do_restore) + 8
                if s == "sw" and st == "ok" and not self.busy:  # (Savage Wind's own updater, asked when it opens)
                    up = self.sw_update.get(self.cfg.get("sw"), {})
                    if up.get("status") == "available":
                        y = self.row("p_update", f"Update Savage Wind to {up.get('version')}", y + 4, self.do_update,
                                     GOLD) + 8
                    else:
                        y = self.lines("Savage Wind is up to date." if up.get("status") == "current" else
                                       "Looking for a Savage Wind update..." if not up else
                                       "Couldn't look for a Savage Wind update.", y, 14, DIM, 60) + 4
            self.row("p_back", "Back to Connect", y1 - 132, lambda: self.show("connect"), MUTED, 16, False)
        # the big button
        label, action, colour = self.primary()
        bx0, by0, bx1, by1 = x0 + 34, y1 - 78, x1 - 34, y1 - 24
        self.put("p_btn", self.button_img(bx1 - bx0, by1 - by0, label, colour), bx0 - 30, by0 - 15, tags=("panel", "p_btn"))
        if not self.busy:
            self.hoverable("p_btn", (bx0, by0, bx1, by1), action, ("panel",))
        self.c.addtag_withtag("side", "panel")
        self.c.move("panel", self.side_off, 0)  # (it slides with the column)
        self.lm_keys.clear()

    def button_img(self, w, h, label, colour):
        im = Image.new("RGBA", (w + 60, h + 30))
        im.alpha_composite(fade_bar(w + 60, h + 30, colour, 90 if colour != DIM else 30).filter(ImageFilter.GaussianBlur(10)))
        im.alpha_composite(fade_bar(w, h, colour, 150 if colour != DIM else 60), (30, 15))
        for yy in (15, 15 + h - 1):
            im.alpha_composite(fade_bar(w, 1, CREAM, 230 if colour != DIM else 90), (30, yy))
        t = self.skin.shadowed(label, 32, (255, 250, 232) if colour != DIM else MUTED)
        im.alpha_composite(t, (30 + (w - t.width) // 2, 15 + (h - t.height) // 2 + 2))
        return im

    def toggle_img(self, label, on):
        w, h = PANEL[2] - PANEL[0] - 40, 30
        im = Image.new("RGBA", (w, h))
        t = self.skin.text(label, 18, CREAM)
        im.alpha_composite(t, (6, (h - t.height) // 2 + 1))
        v = self.skin.text("On" if on else "Off", 18, CURSOR if on else MUTED)
        mid = w - 50
        im.alpha_composite(v, (mid - v.width // 2, (h - v.height) // 2 + 1))
        d = ImageDraw.Draw(im)
        for x, s in ((mid - 38, 1), (mid + 38, -1)):  # (the value's arrows)
            d.polygon((x, h // 2, x + 7 * s, h // 2 - 6, x + 7 * s, h // 2 + 6), fill=MUTED + (255,))
        return im

    def flip_link(self, key):
        self.links[key] ^= 1
        tag = f"p_link_{key}_img"
        self.c.itemconfig(tag, image=self.photo(tag, self.toggle_img(dict(LINKS)[key], self.links[key])))

    # -- the message window: what is happening, typed out, with its arrow
    def say(self, s):
        self.log_lines.append(s)
        self.log_lines = self.log_lines[-60:]
        self.typing = s
        self.typed = 0

    def draw_dialog(self):
        self.c.delete("dlg")
        lines = self.log_lines[-3:]
        if not lines:
            return
        rows = []
        for i, line in enumerate(lines):
            last = i == len(lines) - 1
            text = line[:self.typed] if last and self.typing == line else line
            rows += [(chunk, last) for chunk in self.wrap(text, 68)]
        x0, y0, x1, y1 = PILL
        y = y0 + 6
        for chunk, last in rows[-2:]:  # (the newest two rows, whole messages wrapped)
            key = ("dl", chunk, last)
            if key not in self.imgs:
                self.imgs[key] = ImageTk.PhotoImage(self.skin.text(chunk, 17, CREAM if last else MUTED))
            self.c.create_image(x0 + 32, y, image=self.imgs[key], anchor="nw", tags="dlg")
            y += 23
        if self.typed >= len(self.typing):  # (the message window's arrow, bobbing: it's all said)
            arrow = self.imgs.get("arrow")
            if arrow is None:
                im = self.skin.hud("Nt_ArrowMsg_00^d", CREAM + (255,), (16, 16))
                if im is None:
                    im = Image.new("RGBA", (16, 16))
                    ImageDraw.Draw(im).polygon((2, 4, 14, 4, 8, 13), fill=CREAM + (255,))
                arrow = self.imgs["arrow"] = ImageTk.PhotoImage(im)
            bob = 3 * math.sin((time.time() - self.t0) * 5)
            self.c.create_image(x1 - 30, y1 - 14 + bob, image=arrow, tags="dlg")

    @staticmethod
    def wrap(s, n):
        out, line = [], ""
        for word in s.split():
            if len(line) + len(word) + 1 > n:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        return out + [line] if line else out or [""]

    # ---------------------------------------------------------------- state
    def refresh(self):
        try:
            self.st = L.status(self.cfg)
        except OSError as e:
            self.st = {"sw": ("bad", str(e))}
        sw = self.cfg.get("sw")
        if sw and self.st.get("sw", ("bad",))[0] == "ok" and sw not in self.sw_update:  # (once per folder: GitHub)
            self.sw_update[sw] = {}
            threading.Thread(target=lambda: self.q.put(("swcheck", (sw, L.sw_update_check(sw) or
                                                                    {"status": "error"}))), daemon=True).start()
        self.draw_panel()

    def tick(self):
        try:
            self._tick()
        except Exception:
            traceback.print_exc()
        self.after(33, self.tick)  # (whatever happened: the window keeps living)

    def _tick(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    if not val.startswith(" "):  # (the tools' own output stays out of the message window)
                        self.say(val)
                elif kind == "step":
                    key, f = val
                    self.live[key] = max(self.live.get(key, 0), f)
                    if f < 1:
                        self.active = key
                elif kind == "swcheck":
                    self.sw_update[val[0]] = val[1]
                    if not self.busy and self.side_off == 0:
                        self.draw_panel()
                elif kind == "done":
                    self.busy, self.live, self.shown, self.active = False, {}, {}, None
                    self.build() if val == "rebuild" else self.refresh()
        except queue.Empty:
            pass
        for key, f in self.live.items():  # (fills ease toward the setup's progress; the step running creeps on)
            target = f if f >= 1 or key != self.active else max(f, min(0.95, self.shown.get(key, 0) + 0.0015))
            cur = self.shown.get(key, 0)
            self.shown[key] = 1 if target >= 1 and cur > 0.97 else cur + (target - cur) * 0.15
        if self.typed < len(self.typing):
            self.typed = min(len(self.typing), self.typed + 2)
        target = SIDE_HIDE if self.busy else 0  # (the column slides out while setting up, back after)
        if self.side_off != target:
            new = target if abs(target - self.side_off) < 3 else round(self.side_off + (target - self.side_off) * 0.2)
            if not self.side_off:
                for e in self.entries.values():
                    e.place_forget()
            self.c.move("side", new - self.side_off, 0)
            self.side_off = new
            if not new:
                self.draw_panel()
        self.draw_world()
        self.draw_dialog()
        self.draw_hover()

    # ---------------------------------------------------------------- actions
    def do_setup(self):
        if self.busy or self.st.get("sw", ("bad",))[0] != "ok":
            return
        self.busy, self.live, self.shown = True, {}, {}
        self.draw_panel()

        def work():
            try:
                L.setup(dict(self.cfg), lambda s: self.q.put(("log", "All set. Link awakens: press Play, hero."
                                                              if s == "All set." else s)),
                        lambda key, f: self.q.put(("step", (key, f))))
            except Exception as e:
                self.q.put(("log", f"Stopped: {e}"))
            self.q.put(("done", "rebuild"))  # (the logo now has ARCHIPELAGO under it)
        threading.Thread(target=work, daemon=True).start()

    def do_update(self):
        if self.busy or self.st.get("sw", ("bad",))[0] != "ok":
            return
        sw = self.cfg["sw"]
        if L.inside_sw(sw) and getattr(sys, "frozen", False):
            # (Savage Wind's updater won't run while anything from its folder does: a copy of this launcher from
            # outside it does the update, this one closes)
            try:
                d = os.path.join(os.path.dirname(L.CONFIG), "updating")
                os.makedirs(d, exist_ok=True)
                exe = os.path.join(d, os.path.basename(sys.executable))
                shutil.copy2(sys.executable, exe)
                subprocess.Popen([exe, "--update"], cwd=d)
                self.destroy()
            except OSError as e:
                self.say(f"Couldn't start the update: {e}")
            return
        self.busy, self.live, self.shown = True, {}, {}
        self.draw_panel()

        def work():
            try:
                L.update_sw(dict(self.cfg), lambda s: self.q.put(("log", s)), lambda key, f: self.q.put(("step", (key, f))))
            except Exception as e:
                self.q.put(("log", f"Stopped: {e}"))
            self.sw_update.pop(self.cfg.get("sw"), None)  # (asked again: the new version)
            self.q.put(("done", "rebuild"))
        threading.Thread(target=work, daemon=True).start()

    def do_restore(self):
        if self.busy or not self.cfg.get("sw"):
            return
        try:
            L.restore(self.cfg, self.say)
        except OSError as e:
            self.say(f"Couldn't restore: {e}")
        self.refresh()

    def do_play(self):
        if self.busy or not self.ready():
            return
        sw = self.cfg["sw"]
        vals = {k: v.get() for k, v in self.fields.items()}
        vals.update(self.links)
        try:
            L.write_ini(sw, vals)
        except OSError as e:
            self.say(f"Couldn't save the connection: {e}")
        self.say("Starting Savage Wind… In game: Options > Archipelago > Connect.")
        subprocess.Popen([os.path.join(sw, "savagewind.exe")], cwd=sw)


if __name__ == "__main__":
    App().mainloop()
