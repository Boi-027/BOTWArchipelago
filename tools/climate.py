"""Where Hyrule is hot: the climate of a place, from the game's own Ecosystem data in Bootup.pack - FieldMapArea.sbeco
(the map as rows of (area, length) runs, as MapTower.sbeco is for the towers: runtime/ap_region.c reads that one) and
AreaData.sbyml (each area's climate). Death Mountain's EldinClimateLv1 / Lv2: Link burns without fire protection."""
import os
import struct

import oead


def grid(raw):
    """(rows, step, runs per row): rows `step` metres apart from z = -4000, each a list of (area, x where it ends) from
    x = -5000"""
    d = oead.yaz0.decompress(raw) if raw[:4] == b"Yaz0" else raw
    magic, rows, step, _ = struct.unpack_from("<4I", d, 0)
    assert magic == 0x00112233, "not an Ecosystem grid"
    base = 16 + 4 * rows
    offs = [struct.unpack_from("<I", d, 16 + 4 * r)[0] for r in range(rows)] + [(len(d) - base) // 2]
    out = []
    for r in range(rows):
        x, runs = -5000, []
        for o in range(base + 2 * offs[r], base + 2 * offs[r + 1], 4):
            v, n = struct.unpack_from("<HH", d, o)
            x += n
            runs.append((v, x))
        out.append(runs)
    return rows, step, out


class Climate:
    def __init__(self, romfs):
        boot = oead.Sarc(open(os.path.join(romfs, "Pack", "Bootup.pack"), "rb").read())
        self.rows, self.step, self.runs = grid(bytes(boot.get_file("Ecosystem/FieldMapArea.sbeco").data))
        areas = oead.byml.from_binary(oead.yaz0.decompress(bytes(boot.get_file("Ecosystem/AreaData.sbyml").data)))
        self.climate = {int(a["AreaNumber"]): str(a.get("Climate", "")) for a in areas}
        self.name = {int(a["AreaNumber"]): str(a.get("Area", "")) for a in areas}

    def area(self, x, z):
        r = min(max(int((z + 4000) // self.step), 0), self.rows - 1)
        for v, x1 in self.runs[r]:
            if x < x1:
                return v
        return self.runs[r][-1][0] if self.runs[r] else -1

    def at(self, x, z):
        return self.climate.get(self.area(x, z), "")

    def burning(self, x, z):
        return self.at(x, z) in ("EldinClimateLv1", "EldinClimateLv2")
