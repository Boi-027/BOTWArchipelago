"""The runes as items: what their item-get scene shows. The game never hands out a rune with that scene (its terminals
and Purah have their own), so some of them have no icon and a Japanese placeholder description there. RomFS overlay
files made from your own game files:
  - UI/StockItem/Obj_RemoteBomb(Lv2).sbitemico: the game's own Remote Bomb (+) icons, under the rune's name
  - UI/StockItem/Obj_SheikSensor(Lv2).sbitemico: the Sheikah Sensor (+), drawn in the manner of the other rune icons
    (a flat glyph; the "+" taken from Stasis +)
  - the English descriptions (ActorType/PlayerItem.msbt *_Desc): the game's own where it has one in English, else ours

Needs Pillow. Reads the overlay folder's copies first (other tools wrote them):
    python -I tools/rune_items.py "<Savage Wind>/extracted/romfs" <overlay folder>
"""
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402
from ap_item import LANGS, deswizzle, msbt_add, put, rstb_grow, swizzle  # noqa: E402

ICON_COPIES = {"Obj_RemoteBomb": "Obj_RemoteBombBall", "Obj_RemoteBombLv2": "Obj_RemoteBombBall2"}
SENSOR = (255, 152, 48)  # (its own colour among the runes' magenta, ice blue, yellow, cyan)
# descriptions: the game's own English text (another label of PlayerItem.msbt) or ours
DESC = {
    "Obj_RemoteBomb": "@Obj_RemoteBombBall_MenuDesc",
    "Obj_RemoteBombLv2": "Ancient Sheikah explosive technology,\nimproved. Its bombs are more powerful\nand can be used again sooner.",
    "Obj_StopTimer": "@Obj_StopTimer_MenuDesc",
    "Obj_StopTimerLv2": "Ancient Sheikah technology that can stop\nan object's motion for a short time.\nImproved: it can now stop enemies too.",
    "Obj_Magnetglove": "Ancient Sheikah technology that lets you\nlift and move metallic objects, even\nones hidden under water.",
    "Obj_IceMaker": "@Obj_IceMaker_MenuDesc",
    "Obj_SheikSensor": "Ancient Sheikah technology that senses\nnearby shrines. Its signal grows stronger\nthe closer you are.",
    "Obj_SheikSensorLv2": "Ancient Sheikah technology, improved. It\ncan now seek out anything you've added\nto your Hyrule Compendium.",
}


def icon_px(raw):
    """an item icon's picture: (bntx bytes, its RGBA rows, w, h, block height, data offset, size)"""
    d = bytearray(nin.yaz0(raw))
    k = d.find(b"BNTX")
    r, t = d.find(b"BRTI", k), d.find(b"BRTD", k)
    fmt, w, h, bh = (struct.unpack_from("<I", d, r + o)[0] for o in (0x1c, 0x24, 0x28, 0x34))
    assert fmt >> 8 == 0x0b and w * 4 % 16 == 0, "an RGBA8 icon with whole rows"
    bh = 1 << bh
    rows = (h + 8 * bh - 1) // (8 * bh) * 8 * bh
    size = (w * 4 + 63) // 64 * 64 * rows
    return d, deswizzle(bytes(d[t + 16:t + 16 + size]), w, h, bh), w, h, bh, t + 16, size


def with_picture(raw, img):
    d, _, w, h, bh, at, size = icon_px(raw)
    assert img.size == (w, h)
    d[at:at + size] = swizzle(img.tobytes(), w, h, bh, size)
    return nin.yaz0_store(bytes(d), struct.unpack_from(">I", raw, 8)[0])


def picture(raw):
    _, px, w, h, *_ = icon_px(raw)
    return Image.frombytes("RGBA", (w, h), px[:w * h * 4])


def sensor_glyph(w, h):
    """a dot sending its signal out both ways (how the sensor reads, its waves either side), flat, drawn at 4x"""
    k = 4
    im = Image.new("RGBA", (w * k, h * k), SENSOR + (0,))
    dr = ImageDraw.Draw(im)
    cx, cy = 0.5 * w * k, 0.5 * h * k
    r = 0.11 * w * k
    dr.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SENSOR + (255,))
    for rad in (0.24, 0.40):
        R = rad * w * k
        for a in (-40, 140):  # (right, left)
            dr.arc((cx - R, cy - R, cx + R, cy + R), start=a, end=a + 80, fill=SENSOR + (255,), width=int(0.075 * w * k))
    return im.resize((w, h), Image.LANCZOS)


def plus_mark(base, plus):
    """the "+" a rune's upgrade has on its icon: where the two icons differ, as its own layer"""
    a, b = base.load(), plus.load()
    out = Image.new("RGBA", base.size)
    o = out.load()
    for y in range(base.height):
        for x in range(base.width):
            if x > base.width // 2 and y > base.height // 2 and a[x, y] != b[x, y] and min(b[x, y][:3]) > 180:
                o[x, y] = b[x, y]
    return out


def main(romfs, out):
    def rd(*p):
        q = os.path.join(out, *p)
        return open(q if os.path.exists(q) else os.path.join(romfs, *p), "rb").read()

    icons = os.path.join("UI", "StockItem")
    for name, src in ICON_COPIES.items():
        put(out, f"UI/StockItem/{name}.sbitemico", rd(icons, f"{src}.sbitemico"))
    template = rd(icons, "Obj_Magnetglove.sbitemico")
    w, h = picture(template).size
    glyph = sensor_glyph(w, h)
    put(out, "UI/StockItem/Obj_SheikSensor.sbitemico", with_picture(template, glyph))
    plus = plus_mark(picture(rd(icons, "Obj_StopTimer.sbitemico")), picture(rd(icons, "Obj_StopTimerLv2.sbitemico")))
    assert plus.getbbox(), "the + of Stasis +"
    # (the plus sits over the glyph's corner with a gap cut around it, as Stasis + has)
    gap = plus.split()[3].point(lambda v: 255 if v else 0).resize((w, h)).filter(ImageFilter.MaxFilter(9))
    lv2 = glyph.copy()
    lv2.putalpha(Image.composite(Image.new("L", (w, h), 0), lv2.split()[3], gap))
    lv2.alpha_composite(plus)
    put(out, "UI/StockItem/Obj_SheikSensorLv2.sbitemico", with_picture(template, lv2))

    sizes = {}
    for lang in LANGS:
        pack_raw = rd("Pack", f"Bootup_{lang}.pack")
        pack = nin.sarc(pack_raw)
        mkey = f"Message/Msg_{lang}.product.ssarc"
        msg_raw = pack[mkey]
        msg = nin.sarc(msg_raw)
        have = nin.msbt(msg["ActorType/PlayerItem.msbt"])
        texts = {f"{a}_Desc": (have[t[1:]] if t.startswith("@") else t) for a, t in DESC.items()}
        assert all(texts.values()), "the game's own English descriptions are there"
        msg["ActorType/PlayerItem.msbt"] = msbt_add(msg["ActorType/PlayerItem.msbt"], texts)
        assert nin.msbt(msg["ActorType/PlayerItem.msbt"])["Obj_Magnetglove_Desc"] == DESC["Obj_Magnetglove"]
        msg_new = nin.sarc_write(msg, nin.sarc_aligns(msg_raw))
        pack[mkey] = nin.yaz0_store(msg_new, struct.unpack_from(">I", msg_raw, 8)[0])
        put(out, f"Pack/Bootup_{lang}.pack", nin.sarc_write(pack, nin.sarc_aligns(pack_raw)))
        sizes[f"Message/Msg_{lang}.product.sarc"] = len(msg_new) + 0x1000
    rel = "System/Resource/ResourceSizeTable.product.srsizetable"
    put(out, rel, rstb_grow(rd(*rel.split("/")), sizes))
    print(f"rune items: {len(ICON_COPIES) + 2} icons, {len(DESC)} descriptions")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
