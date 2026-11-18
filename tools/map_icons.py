"""The in-game map tracker's icons, from your own game files: a 64 px picture for each kind of check, side by side in
<overlay>/ap_map_icons.png (Savage Wind runtime/ui/ap_client.mm map_draw; tools/map_points.py KINDS, in that order),
each with a dark rim so it reads over the map. For your machine only, like the rest of the overlay.

    python -I tools/map_icons.py "<extracted folder>" "<overlay folder>"
"""
import os
import sys

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "launcher")]
import poptracker  # noqa: E402  (its icon helpers)

# shrine, Korok, chest, shop, quest, tower, other: an item's icon, or a layout glyph in a colour
ART = [("glyph", "Nt_MapDungeonNewL_03^t", (130, 220, 255)), ("icon", "Obj_KorokNuts"),
       ("glyph", "Nt_StampIconTBoxL_00^s", (240, 205, 120)), ("icon", "PutRupee"), ("icon", "Obj_ProofBook"),
       ("glyph", "Nt_MapTowerNewL_00^t", (255, 170, 100)), ("icon", "Obj_ProofGiantKiller")]
SIZE = 64


def main(ex, out):
    romfs = os.path.join(ex, "romfs")
    tex = poptracker.hud_textures(romfs)
    sheet = Image.new("RGBA", (SIZE * len(ART), SIZE), (0, 0, 0, 0))
    for i, (kind, name, *colour) in enumerate(ART):
        pic = poptracker.glyph(tex, name, colour[0]) if kind == "glyph" else poptracker.icon(romfs, out, name)
        pic = pic.convert("RGBA")
        pic = pic.crop(pic.split()[3].getbbox())  # (item icons have room around them)
        pic.thumbnail((SIZE - 12, SIZE - 12), Image.LANCZOS)
        if max(pic.size) < SIZE - 12:  # (small ones up)
            k = (SIZE - 12) / max(pic.size)
            pic = pic.resize((round(pic.width * k), round(pic.height * k)), Image.LANCZOS)
        cell = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        at = ((SIZE - pic.width) // 2, (SIZE - pic.height) // 2)
        rim = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        rim.paste((8, 12, 14, 230), at, pic.split()[3])
        cell.alpha_composite(rim.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1)))
        cell.alpha_composite(pic, at)
        sheet.alpha_composite(cell, (i * SIZE, 0))
    sheet.save(os.path.join(out, "ap_map_icons.png"))
    print("map tracker icons ->", os.path.join(out, "ap_map_icons.png"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
