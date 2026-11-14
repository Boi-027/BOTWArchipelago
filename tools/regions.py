"""Hyrule's regions, as the game draws them: the area each Sheikah Tower's map covers (Ecosystem/MapTower.sbeco in
Bootup.pack, from your own game files). Region lock (worlds/botw) opens them one by one; Savage Wind reads the same
grid to keep Link out of the locked ones (runtime/ap_event.c).

The grid (BECO): a header (0x00112233, rows, the metres per row, 0), each row's start (u32, in u16 units after the
table), then each row as (region u16, length u16) runs across the map from x = -5000 to 5000; rows go from z = -4000.
Region n is the area of tower MapTower_<n+1>.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nin  # noqa: E402

NAMES = ["Hebra", "Tabantha", "Gerudo", "Wasteland", "Woodland", "Central", "Great Plateau", "Dueling Peaks", "Lake",
         "Eldin", "Akkala", "Lanayru", "Hateno", "Faron", "Ridgeland"]
PLATEAU = 6  # (open from the start)


class Grid:
    def __init__(self, ex):
        boot = nin.sarc(open(os.path.join(ex, "romfs", "Pack", "Bootup.pack"), "rb").read())
        d = nin.yaz0(boot["Ecosystem/MapTower.sbeco"])
        magic, self.rows, self.step, _ = struct.unpack_from("<IIII", d, 0)
        assert magic == 0x00112233
        base = 16 + 4 * self.rows
        offs = list(struct.unpack_from(f"<{self.rows}I", d, 16)) + [(len(d) - base) // 2]
        self.runs = []  # per row: [(x start, x end, region)]
        for r in range(self.rows):
            seg, x, row = d[base + 2 * offs[r]:base + 2 * offs[r + 1]], -5000, []
            for k in range(0, len(seg) - 3, 4):
                v, n = struct.unpack_from("<HH", seg, k)
                row.append((x, x + n, v))
                x += n
            self.runs.append(row)

    def region(self, x, z):
        row = self.runs[max(0, min(self.rows - 1, int((z + 4000) // self.step)))]
        for a, b, v in row:
            if x < b:
                return v
        return row[-1][2]

    def adjacency(self):
        """{region: set of regions it borders}"""
        adj = {i: set() for i in range(len(NAMES))}
        for r, row in enumerate(self.runs):
            for (_, _, v), (_, _, w) in zip(row, row[1:]):
                if v != w:
                    adj[v].add(w), adj[w].add(v)
            if r + 1 < self.rows:
                for a, b, v in row:
                    for c, e, w in self.runs[r + 1]:
                        if v != w and a < e and c < b:
                            adj[v].add(w), adj[w].add(v)
        return adj


if __name__ == "__main__":
    g = Grid(sys.argv[1])
    for i, n in sorted(g.adjacency().items()):
        print(f"{NAMES[i]:14} -> {', '.join(NAMES[j] for j in sorted(n))}")
    assert g.region(-700, 1800) == PLATEAU and g.region(1806, 984) == 7  # (the plateau; Kakariko in Dueling Peaks)
