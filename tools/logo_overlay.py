""""ARCHIPELAGO" in the Breath of the Wild logo itself, under "BREATH OF THE WILD", on the title screen and the loading
screen: RomFS overlay files made from your own game files.

The word is painted into the English logo's own textures, in the empty space under that line (the sword's tip only
runs down the left there), so it is part of the logo: its colour, its fades, and on the loading screen - whose logo is
its progress bar - it fills with the bar like the rest. Lettering in the logo's manner: heavy serif capitals, narrow and
tight, the first one larger, the edges weathered (Georgia Bold from Windows, shaped; a fixed seed, so every build draws
the same):
  - title screen: Title.pack Layout/Title.sblarc, Logo_W_00^l (382 x 300 RGBA, the lettering's cream)
  - loading screen: Bootup.pack Layout/Common.sblarc, Logo2D_00^d (360 x 257 R8 mask)
Each texture is changed in place (same size): every other byte of the layout archives stays where it was.

Needs Pillow and oead (botw_ap/.venv). Reads the overlay folder's copies first (other tools wrote them):
    botw_ap/.venv/Scripts/python -I tools/logo_overlay.py "<Savage Wind>/extracted/romfs" <overlay folder>
"""
import os
import random
import struct
import sys

import oead
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402
from ap_item import gob_addr  # noqa: E402

WORD = "ARCHIPELAGO"
FONT = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgiab.ttf")
CREAM = (250, 247, 220)  # (the logo's lettering)
# texture: (centre x, top y, capital height, widest) in its pixels - centred under "BREATH OF THE WILD", a little
# smaller than it, below its stacked "OF THE"
TITLE = ("Logo_W_00^l", 258, 259, 21, 214)
LOADING = ("Logo2D_00^d", 228, 198, 18, 176)


# ---- the word
def word_mask(cap):
    """the word as an 8-bit mask whose capitals are `cap` pixels tall (cropped to its ink, a little margin)"""
    k = 4  # (drawn 4x, then scaled down: smooth edges)
    small = ImageFont.truetype(FONT, int(cap * k / 0.70))  # (Georgia's capitals: 0.70 of the size)
    big = ImageFont.truetype(FONT, int(cap * k * 1.22 / 0.70))
    track = -cap * k * 0.02
    parts = [(WORD[0], big)] + [(c, small) for c in WORD[1:]]
    w = int(sum(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(c, font=f) for c, f in parts) + 40 * k)
    img = Image.new("L", (w, int(cap * k * 2.2)), 0)
    d = ImageDraw.Draw(img)
    x, base = 20 * k, int(cap * k * 1.7)
    for c, f in parts:
        d.text((x, base), c, font=f, fill=255, anchor="ls")
        x += d.textlength(c, font=f) + track
    img = img.crop(img.getbbox())
    img = img.resize((int(img.width * 0.86), img.height), Image.LANCZOS)  # (narrow, as the logo's)
    img = img.filter(ImageFilter.MaxFilter(3))  # (heavier)
    # weathered edges: a smooth random field, and the outline cut where it is low
    rnd = random.Random(7)
    noise = Image.new("L", (img.width // 6 + 1, img.height // 6 + 1))
    noise.putdata([rnd.randrange(256) for _ in range(noise.width * noise.height)])
    noise = noise.resize(img.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
    edge = ImageChops.subtract(img, img.filter(ImageFilter.MinFilter(7)))
    cut = Image.eval(noise, lambda v: 255 if v < 92 else 0)
    img = ImageChops.subtract(img, ImageChops.multiply(edge, cut))
    pad = 4 * k
    out = Image.new("L", (img.width + 2 * pad, img.height + 2 * pad))
    out.paste(img, (pad, pad))
    return out.resize((max(1, out.width // k), max(1, out.height // k)), Image.LANCZOS)


def place(cap, widest):
    m = word_mask(cap)
    if m.width > widest:  # (it has to fit under the line)
        m = m.resize((widest, m.height), Image.LANCZOS)
    return m


# ---- textures
def deswizzle_px(data, w, h, bh, bpp):
    """Tegra block linear (GOB 64 bytes x 8 rows, `bh` GOBs a block) to rows of `bpp`-byte pixels; a row's last piece
    may be short (382 x 4 bytes isn't a multiple of 16)"""
    row = w * bpp
    out, wg = bytearray(row * h), (row + 63) // 64
    for y in range(h):
        for x in range(0, row, 16):
            n = min(16, row - x)
            a = gob_addr(x, y, wg, bh)
            out[y * row + x:y * row + x + n] = data[a:a + n]
    return bytes(out)


def swizzle_px(px, w, h, bh, bpp, size):
    row = w * bpp
    out, wg = bytearray(size), (row + 63) // 64
    for y in range(h):
        for x in range(0, row, 16):
            n = min(16, row - x)
            a = gob_addr(x, y, wg, bh)
            out[a:a + n] = px[y * row + x:y * row + x + n]
    assert len(out) == size
    return bytes(out)


def stamp(img, m, cx, top, cap):
    """the word put into a texture's image: R8 (a mask the layout tints) or RGBA (the cream, straight alpha, as the
    logo's own edges are)"""
    x0, y0 = cx - m.width // 2, top - (m.height - cap) // 2
    assert x0 >= 0 and x0 + m.width <= img.width and y0 + m.height <= img.height, "the word fits in the texture"
    if img.mode == "L":
        img.paste(ImageChops.lighter(img.crop((x0, y0, x0 + m.width, y0 + m.height)), m), (x0, y0))
    else:
        word = Image.new("RGBA", m.size, CREAM + (0,))
        word.putalpha(m)
        img.alpha_composite(word, (x0, y0))
    return img


def paint(bntx, texture, cx, top, cap, widest):
    """the BNTX with the word painted into `texture` (in place)"""
    d = bytearray(bntx)
    o = 0
    while (o := d.find(b"BRTI", o)) >= 0:
        name_off = struct.unpack_from("<Q", d, o + 0x60)[0]
        n = struct.unpack_from("<H", d, name_off)[0]
        if d[name_off + 2:name_off + 2 + n].decode() == texture:
            break
        o += 4
    else:
        raise SystemExit(f"{texture}: not in this layout archive")
    fmt, w, h = (struct.unpack_from("<I", d, o + k)[0] for k in (0x1c, 0x24, 0x28))
    bh, size = 1 << struct.unpack_from("<I", d, o + 0x34)[0], struct.unpack_from("<I", d, o + 0x50)[0]
    assert struct.unpack_from("<H", d, o + 0x16)[0] == 1, "no mipmaps"
    data = struct.unpack_from("<Q", d, struct.unpack_from("<Q", d, o + 0x70)[0])[0]
    m = place(cap, widest)
    if fmt == 0x201:
        img = stamp(Image.frombytes("L", (w, h), deswizzle_px(d[data:data + size], w, h, bh, 1)), m, cx, top, cap)
        d[data:data + size] = swizzle_px(img.tobytes(), w, h, bh, 1, size)
    elif fmt >> 8 == 0x0b:
        img = stamp(Image.frombytes("RGBA", (w, h), deswizzle_px(d[data:data + size], w, h, bh, 4)), m, cx, top, cap)
        d[data:data + size] = swizzle_px(img.tobytes(), w, h, bh, 4, size)
    else:
        raise SystemExit(f"{texture}: format {fmt:#x} not handled")
    assert len(d) == len(bntx)
    return bytes(d)


def edit_layouts(blarc_raw, target, compress):
    out = nin.sarc_replace_inplace(blarc_raw, "timg/__Combined.bntx",
                                   paint(nin.sarc(blarc_raw)["timg/__Combined.bntx"], *target))
    align = struct.unpack_from(">I", blarc_raw, 8)[0]
    # (Bootup.pack stays in memory: its common layouts stored would double it, which crashes at boot - compressed;
    # the title's are stored, as tools/title_overlay.py has them)
    return bytes(oead.yaz0.compress(out, data_alignment=align)) if compress else nin.yaz0_store(out, align)


def main(romfs, out, which=("title", "loading")):
    def src(rel):
        p = os.path.join(out, rel)
        return open(p if os.path.exists(p) else os.path.join(romfs, rel), "rb").read()

    def put(rel, data):
        p = os.path.join(out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)

    # (same sizes: no size table entry changes)
    if "title" in which:
        raw = src("Pack/Title.pack")
        pack = nin.sarc(raw)
        pack["Layout/Title.sblarc"] = edit_layouts(pack["Layout/Title.sblarc"], TITLE, False)
        put("Pack/Title.pack", nin.sarc_write(pack, nin.sarc_aligns(raw)))
    if "loading" in which:
        boot = oead.Sarc(src("Pack/Bootup.pack"))
        w = oead.SarcWriter.from_sarc(boot)
        w.files["Layout/Common.sblarc"] = edit_layouts(bytes(boot.get_file("Layout/Common.sblarc").data), LOADING, True)
        put("Pack/Bootup.pack", w.write()[1])
    print(f'logo overlay: "{WORD}" in the logo on the {" and ".join(which)} screen')


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *([sys.argv[3].split(",")] if len(sys.argv) > 3 else []))
