"""Builds a RomFS overlay folder that adds an "Archipelago <version>" line to the title screen's bottom-right corner,
from your own game files. Savage Wind loads it with the launch option SAVAGEWIND_ROMFS_OVERLAY=<that folder>.

    python -I tools/title_overlay.py "<Savage Wind folder>/extracted/romfs" "<Savage Wind folder>/ap_overlay" 0.4.0

The overlay holds modified game files: it's for your own machine, never share it.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402

ROMFS, OUT, VERSION = sys.argv[1], sys.argv[2], sys.argv[3]
LINE_UP = 21.0  # the layout's line spacing on that corner (Nintendo -324, DLC -303): one line above the top one


def sections(d):
    hs, n = struct.unpack_from("<H", d, 6)[0], struct.unpack_from("<H", d, 0x10)[0]
    o = hs
    for _ in range(n):
        size = struct.unpack_from("<I", d, o + 4)[0]
        yield o, d[o:o + 4], d[o + 0xC:o + 0x24].split(b"\0")[0].decode("ascii", "replace"), size
        o += size


def add_line(flyt: bytes, text: str) -> bytes:
    secs = list(sections(flyt))
    src = next(s for s in secs if s[1] == b"txt1" and s[2] == "T_Version_00")
    # after the last version pane's user data (usd1 tags the _TW panes for Taiwan only: a pane before it gets the tag)
    i = next(k for k, s in enumerate(secs) if s[1] == b"txt1" and s[2] == "T_AoCVersion_00_TW")
    after = secs[i + 1] if secs[i + 1][1] == b"usd1" else secs[i]
    o, _, _, size = src
    sec = bytearray(flyt[o:o + size])
    text_off = struct.unpack_from("<I", sec, 0x64)[0]
    utf16 = text.encode("utf-16-le") + b"\0\0"
    sec = sec[:text_off] + utf16
    struct.pack_into("<I", sec, 0x80, 0)  # no label, like the "Master Mode" pane: the layout's own text is shown
    sec += b"\0" * (-len(sec) % 4)
    sec[0xC:0x24] = b"T_APVersion_00".ljust(0x18, b"\0")
    struct.pack_into("<HH", sec, 0x54, len(utf16), len(utf16))  # buffer and string bytes
    y = struct.unpack_from("<f", sec, 0x30)[0]
    struct.pack_into("<f", sec, 0x30, y + 2 * LINE_UP)  # Savage Wind's line moves up one when the DLC is there
    struct.pack_into("<I", sec, 4, len(sec))
    at = after[0] + after[3]
    out = bytearray(flyt[:at] + sec + flyt[at:])
    struct.pack_into("<H", out, 0x10, struct.unpack_from("<H", out, 0x10)[0] + 1)
    struct.pack_into("<I", out, 0x0C, len(out))
    return bytes(out)


with open(os.path.join(ROMFS, "Pack", "Title.pack"), "rb") as f:
    pack_raw = f.read()
pack = nin.sarc(pack_raw)
lay_raw = pack["Layout/Title.sblarc"]
lay = nin.sarc(lay_raw)
lay["blyt/Title_00.bflyt"] = add_line(lay["blyt/Title_00.bflyt"], f"Archipelago {VERSION}")
new_lay = nin.sarc_replace_inplace(lay_raw, "blyt/Title_00.bflyt", lay["blyt/Title_00.bflyt"])
assert nin.sarc(new_lay) == lay, "SARC round trip"
pack["Layout/Title.sblarc"] = nin.yaz0_store(new_lay, struct.unpack_from(">I", lay_raw, 8)[0])
new_pack = nin.sarc_write(pack, nin.sarc_aligns(pack_raw))
assert nin.sarc(new_pack)["Layout/Title.sblarc"] == pack["Layout/Title.sblarc"], "SARC round trip"

# (Layout/Title.sblarc has no ResourceSizeTable entry: the game sizes it from the file, so the table stays as is)
for rel, data in ((os.path.join("Pack", "Title.pack"), new_pack),):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    print(p, len(data))
