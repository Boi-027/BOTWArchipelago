"""The look of the launcher, from the player's own game files (nothing of the game ships with it): BotW's fonts
(Font/Font_US.sbfarc: Normal for text, Special for titles, Ancient for Sheikah script), its HUD textures (Bootup.pack
Layout/Common.sblarc: hearts, the selection frame, pause-menu corners, the message window's arrow...), its logo
(Title.pack: the overlay's, with ARCHIPELAGO under it, else the game's own) and a corner of its map for the backdrop.

Everything here returns Pillow images; the launcher turns them into Tk images.
"""
import io
import os
import struct
import sys

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.join(HERE, "..", "tools"), os.path.join(HERE, "tools")):
    if os.path.isdir(p):
        sys.path.insert(0, p)
import nin  # noqa: E402
from logo_overlay import deswizzle_px  # noqa: E402

# BNTX / BFFNT formats: (bytes per block or pixel, block size, decoder)
FORMATS = {0x1d: (8, 4, "ATI1"), 0x1e: (16, 4, "ATI2"), 0x1c: (16, 4, "DXT5"), 0x1a: (8, 4, "DXT1"),
           0x02: (1, 1, "L"), 0x09: (2, 1, "LA"), 0x0b: (4, 1, "RGBA")}


def decode(raw, fmt, w, h, bh):
    """swizzled texture bytes -> an RGBA image (a one-channel format in every channel)"""
    bpp, blk, kind = FORMATS[fmt >> 8 if fmt > 0xff else fmt]
    bw, bhh = (w + blk - 1) // blk, (h + blk - 1) // blk
    lin = deswizzle_px(raw, bw, bhh, bh, bpp)
    if blk == 4:
        four = kind.encode()
        dds = (b"DDS " + struct.pack("<7I", 124, 0x81007, bhh * 4, bw * 4, len(lin), 0, 0) + b"\0" * 44 +
               struct.pack("<2I4s5I", 32, 4, four, 0, 0, 0, 0, 0) + struct.pack("<4I", 0x1000, 0, 0, 0) + b"\0" * 4)
        im = Image.open(io.BytesIO(dds + lin))
        im.load()
        im = im.crop((0, 0, w, h))
        if kind == "ATI1":
            im = im.convert("L")
        elif kind == "ATI2":  # (two channels: red, green)
            r, g = im.split()[:2]
            return Image.merge("RGBA", (r, g, Image.new("L", im.size, 0), r))
    elif kind == "L":
        im = Image.frombytes("L", (w, h), lin[:w * h])
    elif kind == "LA":
        im = Image.frombytes("LA", (w, h), lin[:w * h * 2])
        r, g = im.split()
        return Image.merge("RGBA", (r, g, Image.new("L", (w, h), 0), r))
    else:
        im = Image.frombytes("RGBA", (w, h), lin[:w * h * 4])
    return im.convert("RGBA") if im.mode != "L" else Image.merge("RGBA", (im, im, im, im))


def bntx_textures(data):
    """{name: (fmt, w, h, block height, raw bytes)} of a BNTX"""
    out, o = {}, 0
    while (o := data.find(b"BRTI", o)) >= 0:
        no = struct.unpack_from("<Q", data, o + 0x60)[0]
        n = struct.unpack_from("<H", data, no)[0]
        name = data[no + 2:no + 2 + n].decode(errors="replace")
        fmt, w, h = (struct.unpack_from("<I", data, o + k)[0] for k in (0x1c, 0x24, 0x28))
        bh, size = 1 << struct.unpack_from("<I", data, o + 0x34)[0], struct.unpack_from("<I", data, o + 0x50)[0]
        at = struct.unpack_from("<Q", data, struct.unpack_from("<Q", data, o + 0x70)[0])[0]
        out[name] = (fmt, w, h, bh, bytes(data[at:at + size]))
        o += 4
    return out


class Font:
    """a BFFNT bitmap font (version 4, Switch): glyph sheets, widths, character map"""

    def __init__(self, d):
        o = 20
        self.widths, self.cmap = {}, {}
        while o + 8 <= len(d):
            magic, size = struct.unpack_from("<4sI", d, o)
            if magic == b"FINF":
                self.line = d[o + 9]
            elif magic == b"TGLP":
                (self.cw, self.ch, sheets, _, ssz, self.base, fmt, self.cols, self.rows, sw, sh,
                 doff) = struct.unpack_from("<BBBBIHHHHHHI", d, o + 8)
                need = sw * sh // 2
                self._pending = (d, doff, ssz, need, sheets, fmt, sw, sh)
            elif magic == b"CWDH":
                first, last = struct.unpack_from("<HH", d, o + 8)
                for i in range(last - first + 1):
                    self.widths[first + i] = struct.unpack_from("<bBB", d, o + 16 + 3 * i)
            elif magic == b"CMAP":
                self._cmap(d, o)
            o += size if size else len(d)
        d, doff, ssz, need, sheets, fmt, sw, sh = self._pending
        # (each sheet is stored bottom row first; where it starts, how its halves wrap and whether it sits one GOB in
        # differ: the arrangement whose cell borders are empty and whose glyphs are as wide as the font says is the one)
        self.sheets = []
        for i in range(sheets):
            best = None
            for start in (doff + i * ssz, doff + i * need, doff + i * ((ssz + 0xFFF) // 0x1000 * 0x1000)):
                if start + need > len(d):
                    continue
                raw = decode(d[start:start + need], 0x1d if fmt == 0xc else fmt, sw, sh, 16).split()[3]
                for roll in ((0, 0), (0, sh // 4), (sh // 4, 0), (sh // 4, sh // 4)):
                    for shift in (0, -32):
                        im = ImageChops.offset(self._arrange(raw, roll), shift, 0)
                        sc = self._gaps(im) + 400 * self._fit(im, i)
                        if best is None or sc < best[0]:
                            best = (sc, im)
            self.sheets.append(best[1])

    def _cmap(self, d, o):
        lo, hi, method = struct.unpack_from("<IIH", d, o + 8)
        p = o + 24
        if method == 0:  # direct
            off = struct.unpack_from("<H", d, p)[0]
            for c in range(lo, hi + 1):
                self.cmap[c] = off + c - lo
        elif method == 1:  # table
            for i, c in enumerate(range(lo, hi + 1)):
                idx = struct.unpack_from("<H", d, p + 2 * i)[0]
                if idx != 0xFFFF:
                    self.cmap[c] = idx
        else:  # scan
            n = struct.unpack_from("<H", d, p)[0]
            for i in range(n):
                c, idx = struct.unpack_from("<IH", d, p + 4 + 8 * i)
                self.cmap[c] = idx

    def _fit(self, im, sheet):
        """how far the glyphs' ink is from the widths the font gives them (a few on the sheet)"""
        per, bad = self.cols * self.rows, 0
        for idx in range(sheet * per, sheet * per + per, 7):
            if idx not in self.widths:
                continue
            x, y = (idx % per % self.cols) * (self.cw + 1) + 1, (idx % per // self.cols) * (self.ch + 1) + 1
            box = im.crop((x, y, x + self.cw, y + self.ch)).point(lambda v: 255 if v > 96 else 0).getbbox()
            ink = box[2] - box[0] if box else 0
            bad += abs(ink - self.widths[idx][1]) > 3
        return bad

    @staticmethod
    def _arrange(im, rolls):
        im = ImageOps.flip(im)
        h = im.height // 2
        out = Image.new("L", im.size)
        for k in range(2):
            out.paste(ImageChops.offset(im.crop((0, k * h, im.width, (k + 1) * h)), 0, rolls[k]), (0, k * h))
        return out

    def _gaps(self, im):
        px, s = im.load(), 0
        w, h = min(im.width, self.cols * (self.cw + 1)), min(im.height, self.rows * (self.ch + 1))
        for r in range(self.rows + 1):
            y = r * (self.ch + 1)
            if y < im.height:
                s += sum(px[x, y] for x in range(0, w, 2))
        for c in range(self.cols + 1):
            x = c * (self.cw + 1)
            if x < im.width:
                s += sum(px[x, y] for y in range(0, h, 2))
        return s

    def glyph(self, idx):
        per = self.cols * self.rows
        sheet, cell = self.sheets[idx // per], idx % per
        x, y = (cell % self.cols) * (self.cw + 1) + 1, (cell // self.cols) * (self.ch + 1) + 1
        return sheet.crop((x, y, x + self.cw, y + self.ch))

    def render(self, text, height, colour, tracking=0):
        """the text as an RGBA image whose line is `height` pixels"""
        k = height / self.ch
        pieces, x = [], 0
        for ch in text:
            idx = self.cmap.get(ord(ch), self.cmap.get(ord("?"), 0))
            left, gw, adv = self.widths.get(idx, (0, self.cw, self.cw))
            if ch == "_":  # (its cell straddles a sheet's wrap and comes out garbled: drawn here instead)
                bar = Image.new("L", (max(1, gw), self.ch))
                bar.paste(255, (0, self.base + 1, gw, min(self.ch, self.base + 3)))
                pieces.append((x + left, bar))
            elif ch != " ":
                pieces.append((x + left, self.glyph(idx).crop((0, 0, max(1, gw), self.ch))))
            x += adv + tracking
        mask = Image.new("L", (max(1, x), self.ch))
        for px, g in pieces:
            mask.paste(ImageChops.lighter(mask.crop((px, 0, px + g.width, self.ch)), g), (px, 0))
        mask = mask.resize((max(1, int(mask.width * k)), max(1, int(self.ch * k))), Image.LANCZOS)
        out = Image.new("RGBA", mask.size, colour)
        out.putalpha(mask)
        return out


class Assets:
    def __init__(self, sw):
        romfs = os.path.join(sw, "extracted", "romfs")
        fonts = nin.sarc(open(os.path.join(romfs, "Font", "Font_US.sbfarc"), "rb").read())
        self.normal = Font(fonts["Normal_00.bffnt"])
        self.title = Font(fonts["Special_00.bffnt"])
        self.sheikah = Font(fonts["Ancient_00.bffnt"])
        boot = nin.sarc(open(os.path.join(romfs, "Pack", "Bootup.pack"), "rb").read())
        self.tex = bntx_textures(nin.sarc(nin.yaz0(boot["Layout/Common.sblarc"]))["timg/__Combined.bntx"])
        self.sw, self.romfs = sw, romfs

    def hud(self, name, colour=None, size=None):
        """a HUD texture (its mask in `colour`, if given)"""
        fmt, w, h, bh, raw = self.tex[name]
        im = decode(raw, fmt, w, h, bh)
        if colour:
            tint = Image.new("RGBA", im.size, colour)
            tint.putalpha(ImageChops.multiply(im.split()[3], Image.new("L", im.size, colour[3] if len(colour) > 3 else 255)))
            im = tint
        return im.resize(size, Image.LANCZOS) if size else im

    def logo(self):
        """the BotW logo (the overlay's, with ARCHIPELAGO, when it has been built)"""
        for base in (os.path.join(self.sw, "ap_overlay"), self.romfs):
            p = os.path.join(base, "Pack", "Title.pack")
            if os.path.exists(p):
                lay = nin.sarc(nin.sarc(open(p, "rb").read())["Layout/Title.sblarc"])
                tex = bntx_textures(nin.yaz0(lay["timg/__Combined.bntx"]) if lay["timg/__Combined.bntx"][:4] == b"Yaz0"
                                    else lay["timg/__Combined.bntx"])
                if "Logo_W_00^l" in tex:
                    fmt, w, h, bh, raw = tex["Logo_W_00^l"]
                    return decode(raw, fmt, w, h, bh), base != self.romfs
        return None, False

    def backdrop(self, size):
        """a stretch of the game's map (around the Great Plateau and Hyrule Castle), dark and soft"""
        from poptracker import map_tile  # (tools/poptracker.py: the tiles as the game's map has them)
        t = 420
        im = Image.new("RGB", (3 * t, 3 * t))
        for i, c in enumerate("DEF"):
            for j, r in enumerate("456"):
                im.paste(map_tile(self.romfs, f"MapTex1_{c}-{r}").resize((t, t), Image.LANCZOS), (i * t, j * t))
        im = ImageOps.fit(im, size, Image.LANCZOS)
        im = ImageEnhance.Color(im).enhance(0.55)
        im = ImageEnhance.Brightness(im.filter(ImageFilter.GaussianBlur(2)), ).enhance(0.32)
        return im
