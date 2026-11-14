"""The launcher's window, dressed as Breath of the Wild's own menus: its font, its logo, its HUD (hearts for the setup's
steps, the inventory's selection frame, the stamina wheel for progress, the message window's arrow, its button
prompts) - all read from the player's own game files when Savage Wind's folder is known (botw_assets.py); a plain look
until then.
"""
import math
import os
import queue
import subprocess
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageTk

import launcher as L

W, H = 1120, 720
CREAM, MUTED, DIM = (236, 228, 204), (169, 162, 143), (111, 106, 94)
SHEIKAH, GOLD, RED, ORANGE = (79, 211, 232), (217, 180, 74), (232, 82, 74), (232, 140, 64)
PANEL = (8, 10, 12, 178)
ENTRY_BG = "#101215"


def hexc(c):
    return "#%02x%02x%02x" % c[:3]


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
        self._fallback = {}

    def text(self, s, size, colour=CREAM, alpha=255):
        if self.a:
            return self.a.normal.render(s, size, colour + (alpha,))
        f = self._fallback.get(size)
        if f is None:
            try:
                f = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf"), int(size * 0.78))
            except OSError:
                f = ImageFont.load_default()
            self._fallback[size] = f
        box = f.getbbox(s or " ")
        im = Image.new("RGBA", (max(1, box[2] + 2), int(size * 1.05)), colour + (0,))
        ImageDraw.Draw(im).text((0, size * 0.08), s, font=f, fill=colour + (alpha,))
        return im

    def sheikah(self, s, size, colour=SHEIKAH, alpha=255):
        return self.a.sheikah.render(s, size, colour + (alpha,)) if self.a else None

    def hud(self, name, colour=None, size=None, channel=None):
        if not self.a or name not in self.a.tex:
            return None
        im = self.a.hud(name)
        if channel is not None:
            m = im.split()[channel]
            im = Image.new("RGBA", im.size, (255, 255, 255, 255))
            im.putalpha(m)
        if colour:
            tint = Image.new("RGBA", im.size, colour[:3] + (255,))
            tint.putalpha(ImageChops.multiply(im.split()[3], Image.new("L", im.size, colour[3] if len(colour) > 3 else 255)))
            im = tint
        return im.resize(size, Image.LANCZOS) if size else im

    def heart(self, state, size=34):
        """a step's state as a heart: full (done), empty (to do), cracked (a problem), dim (optional, off)"""
        if self.a:
            if state == "ok":
                fill = self.hud("Nt_HeartNew_00^f", RED, (size, size), channel=1)
                glow = fill.filter(ImageFilter.GaussianBlur(3))
                out = Image.new("RGBA", (size, size))
                out.alpha_composite(glow)
                out.alpha_composite(fill)
                return out
            if state == "bad":
                return self.hud("Nt_HeartDamage_00^t", ORANGE + (255,), (size, size), channel=1) or self.hud("Nt_HeartNewEmpty_00^d", ORANGE, (size, size))
            return self.hud("Nt_HeartNewEmpty_00^d", (SHEIKAH if state == "todo" else DIM) + (230,), (size, size))
        im = Image.new("RGBA", (size, size))
        d = ImageDraw.Draw(im)
        col = {"ok": RED, "bad": ORANGE, "todo": SHEIKAH, "off": DIM}[state]
        d.ellipse((6, 6, size - 6, size - 6), fill=col + (255,) if state == "ok" else None, outline=col + (255,), width=3)
        return im


def rounded(size, radius, fill=None, outline=None, width=1):
    im = Image.new("RGBA", size)
    ImageDraw.Draw(im).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=fill, outline=outline, width=width)
    return im


class App(tk.Tk):
    STEPS = [("sw", "Savage Wind"), ("exe", "Archipelago build"), ("overlay", "Overlay"),
             ("flags", "Launch options"), ("apworld", "Archipelago world"), ("poptracker", "PopTracker pack")]

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
        self.q, self.busy, self.progress = queue.Queue(), False, 0.0
        self.c = tk.Canvas(self, width=W, height=H, highlightthickness=0, bg="#0b0d10")
        self.c.pack()
        self.imgs, self.hover_key, self.t0 = {}, None, time.time()
        self.log_lines, self.typing = [], ""
        self.c.create_text(W // 2, H // 2, text="Loading Hyrule…", fill=hexc(MUTED), font=("Segoe UI", 14), tags="loading")
        self.update()
        self.build()
        for key, fn in (("<Return>", self.do_play), ("a", self.do_play), ("x", self.do_setup), ("y", self.do_restore)):
            self.bind(key, lambda e, f=fn: None if isinstance(self.focus_get(), tk.Entry) else f())
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

    # ---------------------------------------------------------------- pictures
    def photo(self, key, im):
        p = ImageTk.PhotoImage(im)
        self.imgs[key] = p
        return p

    def put(self, key, im, x, y, anchor="nw", tags=()):
        return self.c.create_image(x, y, image=self.photo(key, im), anchor=anchor, tags=tags)

    def panel(self, bg, box, title):
        x0, y0, x1, y1 = box
        layer = rounded((x1 - x0, y1 - y0), 10, fill=PANEL, outline=CREAM + (60,), width=1)
        bg.alpha_composite(layer, (x0, y0))
        corner = self.skin.hud("Nt_PauseCorner_00^s", CREAM + (170,), (40, 40))
        if corner:  # (the pause menu's corner ornaments)
            for k, (x, y) in enumerate(((x0 - 6, y0 - 6), (x1 - 34, y0 - 6), (x1 - 34, y1 - 34), (x0 - 6, y1 - 34))):
                piece = corner.transpose([None, Image.FLIP_LEFT_RIGHT, Image.ROTATE_180, Image.FLIP_TOP_BOTTOM][k]) if k else corner
                bg.alpha_composite(piece, (x, y))
        t = self.skin.text(title, 26, CREAM)
        bg.alpha_composite(t, (x0 + 22, y0 + 14))
        line = Image.new("RGBA", (x1 - x0 - 44, 1), CREAM + (70,))
        bg.alpha_composite(line, (x0 + 22, y0 + 14 + t.height + 6))
        sh = self.skin.sheikah(title.upper(), 13, SHEIKAH, 110)
        if sh:
            bg.alpha_composite(sh, (x1 - 22 - sh.width, y0 + 22))

    def backdrop(self):
        if self.skin.a:
            bg = self.skin.a.backdrop((W, H)).convert("RGBA")
        else:
            bg = Image.new("RGBA", (W, H), (14, 17, 22, 255))
            d = ImageDraw.Draw(bg)
            for i in range(H):
                t = i / H
                d.line((0, i, W, i), fill=(int(28 - 14 * t), int(40 - 22 * t), int(58 - 34 * t), 255))
        vign = Image.new("L", (W, H), 0)
        ImageDraw.Draw(vign).ellipse((-W * 0.25, -H * 0.4, W * 1.25, H * 1.35), fill=255)
        vign = vign.filter(ImageFilter.GaussianBlur(120))
        bg = Image.composite(bg, Image.new("RGBA", (W, H), (4, 5, 7, 255)), vign)
        # the logo: the game's own (the overlay's has ARCHIPELAGO under it), else drawn
        logo, has_ap = self.skin.a.logo() if self.skin.a else (None, False)
        if logo:
            logo = logo.resize((int(logo.width * 0.62), int(logo.height * 0.62)), Image.LANCZOS)
            shadow = Image.new("RGBA", logo.size, (0, 0, 0, 0))
            shadow.putalpha(logo.split()[3].filter(ImageFilter.GaussianBlur(6)).point(lambda v: v * 0.8))
            bg.alpha_composite(shadow, (38, 18))
            bg.alpha_composite(logo, (34, 12))
            if not has_ap:
                bg.alpha_composite(self.skin.text("ARCHIPELAGO", 26, CREAM), (106, 12 + logo.height - 18))
        else:
            bg.alpha_composite(self.skin.text("BREATH OF THE WILD", 18, MUTED), (40, 40))
            bg.alpha_composite(self.skin.text("ARCHIPELAGO", 54, CREAM), (38, 62))
        bg.alpha_composite(self.skin.text(f"Launcher {L.VERSION}  ·  for Savage Wind {L.SW_VERSION}", 17, MUTED), (310, 150))
        sh = self.skin.sheikah("HYRULE AWAITS ITS MULTIWORLD", 16, SHEIKAH, 120)
        if sh:
            bg.alpha_composite(sh, (310, 120))
        self.panel(bg, (34, 214, 690, 660), "Setup")
        self.panel(bg, (716, 214, 1086, 520), "Connect")
        return bg

    # ---------------------------------------------------------------- the window
    def build(self):
        self.c.delete("all")
        for w in self.place_slaves():
            w.destroy()
        self.skin = Skin(self.cfg.get("sw") if self.sw_ready() else None)
        self.put("bg", self.backdrop(), 0, 0)
        gh = self.put("gh", self.skin.text("GitHub", 17, SHEIKAH), W - 40, 40, "ne", ("link",))
        self.c.tag_bind("link", "<Button-1>", lambda e: webbrowser.open(L.REPO))
        self.c.tag_bind("link", "<Enter>", lambda e: self.c.config(cursor="hand2"))
        self.c.tag_bind("link", "<Leave>", lambda e: self.c.config(cursor=""))
        self.build_setup()
        self.build_connect()
        self.build_dialog()
        self.build_prompts()
        self.refresh()
        if not self.log_lines:
            self.say(f"Point the launcher at your Savage Wind {L.SW_VERSION} folder, press Set up, then Play."
                     if not self.sw_ready() else "Welcome back, hero. Press Play." if self.done
                     else "Welcome back, hero. Press Set up, then Play.")

    # -- setup: the folders, then the steps as a list of hearts
    def build_setup(self):
        y = 268
        self.rows = {}
        for key, label, hint in (("sw", "Savage Wind folder", "Your Savage Wind folder (with savagewind.exe)"),
                                 ("archipelago", "Archipelago folder", "Your Archipelago folder (optional)"),
                                 ("poptracker", "PopTracker folder", "Your PopTracker folder (optional)")):
            self.folder_row(key, label, hint, y)
            y += 34
        y += 12
        for key, name in self.STEPS:
            self.rows[key] = y
            y += 46

    def folder_row(self, key, label, hint, y):
        tag = f"folder_{key}"
        self.put(f"{tag}_l", self.skin.text(label, 17, MUTED), 58, y + 4, tags=(tag,))
        path = self.cfg.get(key, "") or "Not chosen"
        short = path if len(path) < 52 else "..." + path[-49:]
        self.put(f"{tag}_p", self.skin.text(short, 17, CREAM if self.cfg.get(key) else DIM), 230, y + 4, tags=(tag,))

        def browse(e=None):
            p = filedialog.askdirectory(title=hint, initialdir=self.cfg.get(key) or None)
            if p:
                self.cfg[key] = os.path.normpath(p)
                self.save_cfg()
                self.build()
        self.hoverable(tag, (48, y - 2, 676, y + 30), browse)

    def hoverable(self, tag, box, action):
        """a hover selection frame (the inventory's, pulsing) and a click"""
        self.c.create_rectangle(*box, outline="", fill="", tags=(tag, tag + "_hit"))
        self.c.tag_bind(tag, "<Enter>", lambda e: self.set_hover((tag, box)))
        self.c.tag_bind(tag, "<Leave>", lambda e: self.set_hover(None))
        self.c.tag_bind(tag, "<Button-1>", lambda e: action())

    def set_hover(self, h):
        self.hover_key = h
        self.c.config(cursor="hand2" if h else "")
        self.c.delete("hover")

    def draw_hover(self):
        self.c.delete("hover")
        if not self.hover_key:
            return
        tag, (x0, y0, x1, y1) = self.hover_key
        pulse = 0.55 + 0.45 * math.sin((time.time() - self.t0) * 4)
        key = ("frame", x1 - x0, y1 - y0, round(pulse, 1))
        if key not in self.imgs:
            w, h = x1 - x0 + 24, y1 - y0 + 24
            glow = rounded((w, h), 12, outline=SHEIKAH + (int(200 * pulse),), width=4).filter(ImageFilter.GaussianBlur(4))
            frame = rounded((w - 20, h - 20), 8, outline=CREAM + (235,), width=2)
            glow.alpha_composite(frame, (10, 10))
            self.imgs[key] = ImageTk.PhotoImage(glow)
        self.c.create_image(x0 - 12, y0 - 12, image=self.imgs[key], anchor="nw", tags="hover")
        if self.c.find_withtag(tag + "_hit"):
            self.c.tag_lower("hover", tag + "_hit")

    # -- connect: the room, the links, Play
    def build_connect(self):
        ini = L.read_ini(self.cfg["sw"]) if self.cfg.get("sw") else {}
        self.fields = {}
        y = 262
        for key, label, show in (("ap_server", "Server", ""), ("ap_slot", "Slot name", ""), ("ap_password", "Password", "•")):
            self.put(f"lbl_{key}", self.skin.text(label, 16, MUTED), 740, y)
            v = tk.StringVar(value=ini.get(key, "archipelago.gg:38281" if key == "ap_server" else ""))
            e = tk.Entry(self, textvariable=v, show=show, bg=ENTRY_BG, fg=hexc(CREAM), insertbackground=hexc(CREAM),
                         relief="flat", font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#3a3a34",
                         highlightcolor=hexc(SHEIKAH))
            e.place(x=740, y=y + 19, width=322, height=26)
            self.fields[key] = v
            y += 50
        self.links = {}
        x = 740
        for key, label in (("ap_deathlink", "DeathLink"), ("ap_traplink", "TrapLink"), ("ap_ringlink", "RingLink")):
            self.links[key] = int(ini.get(key, "0") or 0)
            tag = f"link_{key}"
            self.put(tag, self.toggle_img(label, self.links[key]), x, y + 2, tags=(tag,))
            self.hoverable(tag, (x - 4, y - 2, x + 104, y + 28), lambda k=key: self.flip_link(k))
            x += 110

    def toggle_img(self, label, on):
        t = self.skin.text(label, 16, CREAM if on else MUTED)
        im = Image.new("RGBA", (t.width + 26, 26))
        d = ImageDraw.Draw(im)
        d.ellipse((2, 6, 16, 20), outline=(SHEIKAH if on else DIM) + (255,), width=2, fill=SHEIKAH + (255,) if on else None)
        im.alpha_composite(t, (24, (26 - t.height) // 2 + 1))
        return im

    def flip_link(self, key):
        self.links[key] ^= 1
        label = {"ap_deathlink": "DeathLink", "ap_traplink": "TrapLink", "ap_ringlink": "RingLink"}[key]
        self.c.itemconfig(f"link_{key}", image=self.photo(f"link_{key}", self.toggle_img(label, self.links[key])))

    # -- the message window: what is happening, typed out, with its arrow
    def build_dialog(self):
        box = rounded((370, 124), 14, fill=(6, 7, 9, 215), outline=CREAM + (90,), width=1)
        self.put("dialog", box, 716, 536)

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
            rows += [(chunk, last) for chunk in self.wrap(text, 44)]
        y = 552
        for chunk, last in rows[-3:]:  # (the newest three rows, whole messages wrapped)
            key = ("dl", chunk, last)
            if key not in self.imgs:
                self.imgs[key] = ImageTk.PhotoImage(self.skin.text(chunk, 16, CREAM if last else MUTED))
            self.c.create_image(738, y, image=self.imgs[key], anchor="nw", tags="dlg")
            y += 22
        if self.typed >= len(self.typing):  # (the message window's arrow, bobbing: it's all said)
            arrow = self.imgs.get("arrow")
            if arrow is None:
                im = self.skin.hud("Nt_ArrowMsg_00^d", CREAM + (255,), (18, 18))
                if im is None:
                    im = Image.new("RGBA", (18, 18))
                    ImageDraw.Draw(im).polygon((2, 4, 16, 4, 9, 14), fill=CREAM + (255,))
                arrow = self.imgs["arrow"] = ImageTk.PhotoImage(im)
            bob = 3 * math.sin((time.time() - self.t0) * 5)
            self.c.create_image(1064, 640 + bob, image=arrow, tags="dlg")

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

    # -- the button prompts (bottom right, as the game's menus have them)
    def prompt_img(self, letter, label, enabled=True, big=False):
        r = 30 if big else 24
        k = 4  # (a round button, as the game draws them, smoothed)
        base = Image.new("RGBA", (r * k, r * k))
        ImageDraw.Draw(base).ellipse((0, 0, r * k - 1, r * k - 1), fill=(GOLD if big else CREAM) + (255,))
        ImageDraw.Draw(base).ellipse((k * 2, k * 2, r * k - 1 - k * 2, r * k - 1 - k * 2), outline=(255, 255, 255, 90), width=k)
        base = base.resize((r, r), Image.LANCZOS)
        glyph = self.skin.text(letter, int(r * 0.78), (20, 18, 12))
        base.alpha_composite(glyph, ((r - glyph.width) // 2, (r - glyph.height) // 2 + 1))
        t = self.skin.text(label, 26 if big else 19, CREAM if enabled else DIM)
        im = Image.new("RGBA", (r + 10 + t.width, max(r, t.height)))
        if not enabled:
            base.putalpha(base.split()[3].point(lambda v: v // 3))
        im.alpha_composite(base, (0, (im.height - r) // 2))
        im.alpha_composite(t, (r + 10, (im.height - t.height) // 2 + 1))
        return im

    def build_prompts(self):
        self.prompts = {}
        for key, letter, label, fn, x, y, big in (("play", "A", "Play", self.do_play, 742, 460, True),
                                                 ("setup", "X", "Set up", self.do_setup, 48, 676, False),
                                                 ("restore", "Y", "Restore original", self.do_restore, 760, 676, False),
                                                 ("close", "B", "Close", self.destroy, 990, 676, False)):
            self.prompts[key] = (letter, label, x, y, big, fn)

    def draw_prompts(self, enabled):
        for key, (letter, label, x, y, big, fn) in self.prompts.items():
            tag = f"prompt_{key}"
            self.c.delete(tag)
            on = enabled.get(key, True)
            im = self.prompt_img(letter, label, on, big)
            self.c.create_image(x, y, image=self.photo(tag, im), anchor="nw", tags=(tag,))
            if on:
                self.hoverable(tag, (x - 4, y - 2, x + im.width + 4, y + im.height + 2), fn)

    # ---------------------------------------------------------------- state
    def refresh(self):
        try:
            st = L.status(self.cfg)
        except OSError as e:
            st = {"sw": ("bad", str(e))}
        self.st = st
        self.c.delete("step")
        for key, name in self.STEPS:
            y = self.rows[key]
            state, text = st.get(key, ("off", "Waiting for the Savage Wind folder."))
            tag = f"step_{key}"
            self.put(f"{tag}_h", self.skin.heart(state), 52, y, tags=("step", tag))
            self.put(f"{tag}_n", self.skin.text(name, 19, CREAM), 98, y + 2, tags=("step", tag))
            self.put(f"{tag}_t", self.skin.text(self.wrap(text, 66)[0], 15, CREAM if state == "bad" else MUTED), 98, y + 24,
                     tags=("step", tag))
        ready = st.get("sw", ("bad",))[0] == "ok"
        todo = any(s == "todo" for s, _ in st.values())
        self.done = done = ready and all(st.get(k, ("off",))[0] in ("ok", "off") for k in ("exe", "overlay", "flags"))
        self.draw_prompts({"play": done and not self.busy, "setup": ready and todo and not self.busy,
                           "restore": not self.busy and bool(self.cfg.get("sw"))})

    def draw_wheel(self):
        """the stamina wheel, filling as the setup goes"""
        self.c.delete("wheel")
        if not self.busy:
            return
        key = ("wheel", round(self.progress, 2))
        if key not in self.imgs:
            s = 40
            im = Image.new("RGBA", (s, s))
            d = ImageDraw.Draw(im)
            d.ellipse((3, 3, s - 3, s - 3), outline=(40, 46, 40, 255), width=6)
            d.arc((3, 3, s - 3, s - 3), -90, -90 + 360 * self.progress, fill=(124, 207, 122, 255), width=6)
            glow = im.filter(ImageFilter.GaussianBlur(2))
            glow.alpha_composite(im)
            self.imgs[key] = ImageTk.PhotoImage(glow)
        self.c.create_image(160, 670, image=self.imgs[key], anchor="nw", tags="wheel")

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
                    self.progress = val
                elif kind == "done":
                    self.busy = False
                    self.build() if val == "rebuild" else self.refresh()
        except queue.Empty:
            pass
        if self.typed < len(self.typing):
            self.typed = min(len(self.typing), self.typed + 2)
        self.draw_dialog()
        self.draw_hover()
        self.draw_wheel()

    # ---------------------------------------------------------------- actions
    def do_setup(self):
        if self.busy or not self.st.get("sw", ("bad",))[0] == "ok":
            return
        self.busy, self.progress = True, 0.0
        self.refresh()

        def work():
            try:
                L.setup(dict(self.cfg), lambda s: self.q.put(("log", "All set. Press Play, hero." if s == "All set." else s)),
                        lambda f: self.q.put(("step", f)))
            except Exception as e:
                self.q.put(("log", f"Stopped: {e}"))
            self.q.put(("done", "rebuild"))  # (the logo now has ARCHIPELAGO under it)
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
        if self.busy or not all(self.st.get(k, ("off",))[0] in ("ok", "off") for k in ("exe", "overlay", "flags")) \
                or self.st.get("sw", ("bad",))[0] != "ok":
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
