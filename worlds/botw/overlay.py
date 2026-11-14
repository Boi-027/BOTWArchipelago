"""Archipelago notifications drawn over the bottom-left of the Savage Wind window, styled after the game's UI: a
click-through, always-on-top tkinter window in its own thread. Windows only; borderless/windowed (not exclusive
fullscreen). Shown only while the game has focus.

    python -I overlay.py "<Savage Wind folder>"   # self-check: shows sample notifications over the game
"""
import ctypes
import os
import queue
import threading
import time

GAME_TITLE = "Savage Wind"
SHOW_S = 7.0
SLIDE_S = 0.22
MAX_CARDS = 5
KEY = "#010203"  # the window's see-through colour
# palette taken from the game's menus: cream text, gold rules, Sheikah blue accent
CREAM, GOLD, SHEIKAH, PANEL = "#ece4cc", "#b59a5b", "#4fd3e8", "#121212"
COLORS = {"progression": "#f3c75f", "useful": "#9cc2ff", "filler": CREAM, "trap": "#ff8f7d", "player": "#7fd8ff",
          "location": "#c9c2ae", "text": CREAM}


class _Rect(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class Overlay(threading.Thread):
    def __init__(self, font_dir: str = ""):
        super().__init__(daemon=True, name="BotWOverlay")
        self.q = queue.Queue()
        self.font_dir = font_dir

    def notify(self, *segments):
        """segments: (text, kind) pairs, kind a COLORS key; plain strings are 'text'."""
        self.q.put([(s, "text") if isinstance(s, str) else s for s in segments])

    def game_rect(self):
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, GAME_TITLE)
        if not hwnd or u.IsIconic(hwnd) or u.GetForegroundWindow() != hwnd:
            return None  # only over the game while it has focus, never over other apps
        r = _Rect()
        u.GetClientRect(hwnd, ctypes.byref(r))
        pt = (ctypes.c_long * 2)(0, 0)
        u.ClientToScreen(hwnd, pt)
        return pt[0], pt[1], r.r, r.b

    def run(self):
        import tkinter as tk
        import tkinter.font as tkfont
        from ctypes import wintypes as wt
        u = ctypes.windll.user32
        u.SetWindowPos.argtypes = [wt.HWND, wt.HWND] + [ctypes.c_int] * 4 + [ctypes.c_uint]
        try:
            u.SetProcessDPIAware()  # window rects and tk geometry in the same pixels
        except (AttributeError, OSError):
            pass
        family = "Segoe UI Semibold"
        ttf = os.path.join(self.font_dir, "FiraSans-SemiBold.ttf")
        if os.path.exists(ttf) and ctypes.windll.gdi32.AddFontResourceExW(ttf, 0x10, 0):  # private to this process
            family = "Fira Sans SemiBold"
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", KEY)
        root.attributes("-alpha", 0.93)
        root.configure(bg=KEY)
        font = tkfont.Font(root, family=family, size=15)
        cv = tk.Canvas(root, bg=KEY, highlightthickness=0, width=10, height=10)
        cv.pack()
        root.update_idletasks()
        # click-through and never focused, so the game keeps its input
        hwnd = u.GetParent(root.winfo_id())
        u.SetWindowLongW(hwnd, -20, u.GetWindowLongW(hwnd, -20) | 0x80000 | 0x20 | 0x8000000 | 0x80)
        cards = []  # [segments, width, born]
        H, GAP, PAD = 40, 7, 16

        def ease(t):
            t = max(0.0, min(1.0, t))
            return 1 - (1 - t) ** 3

        def draw(card, x, y):
            segs, w = card[0], card[1]
            cv.create_rectangle(x, y, x + w, y + H, fill=PANEL, outline="")
            cv.create_line(x, y, x + w, y, fill=GOLD)
            cv.create_line(x, y + H - 1, x + w, y + H - 1, fill=GOLD)
            cv.create_line(x + 4, y + 3, x + 4, y + H - 3, fill=SHEIKAH, width=2)
            cy = y + H // 2
            cv.create_polygon(x + 18, cy - 6, x + 24, cy, x + 18, cy + 6, x + 12, cy, fill=SHEIKAH)
            tx = x + 34
            for text, kind in segs:
                cv.create_text(tx, cy, text=text, fill=COLORS.get(kind, CREAM), font=font, anchor="w")
                tx += font.measure(text)

        def tick():
            now = time.monotonic()
            while not self.q.empty():
                segs = self.q.get()
                cards.append([segs, 34 + sum(font.measure(t) for t, _ in segs) + PAD, now])
            while cards and (now - cards[0][2] > SHOW_S + SLIDE_S or len(cards) > MAX_CARDS):
                cards.pop(0)
            rect = self.game_rect()
            if not cards or not rect:
                root.withdraw()
                root.after(150, tick)
                return
            width = max(c[1] for c in cards) + 8
            height = len(cards) * (H + GAP)
            cv.delete("all")
            cv.config(width=width, height=height)
            for i, card in enumerate(cards):
                age = now - card[2]
                shown = ease(age / SLIDE_S) if age < SHOW_S else 1 - ease((age - SHOW_S) / SLIDE_S)
                draw(card, int(-card[1] * (1 - shown)), i * (H + GAP))
            root.deiconify()
            x, y, gw, gh = rect
            u.SetWindowPos(hwnd, wt.HWND(-1), x + 24, y + gh - height - int(gh * 0.12), width, height, 0x10)
            root.after(16, tick)

        tick()
        root.mainloop()


if __name__ == "__main__":
    import sys
    o = Overlay(sys.argv[1] if len(sys.argv) > 1 else "")
    o.start()
    o.notify("Received ", ("Mipha's Grace", "progression"), " from ", ("Player2", "player"))
    time.sleep(0.6)
    o.notify("Sent ", ("Hookshot", "progression"), " to ", ("Player3", "player"), (" · Ja Baij Shrine", "location"))
    time.sleep(0.6)
    o.notify("Received ", ("Thunderstorm Trap", "trap"), " from ", ("Player4", "player"))
    time.sleep(9)
    print("ok")
