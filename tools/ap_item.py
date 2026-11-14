"""The "Archipelago Item" (actor Item_AP_00): a new pouch item for the RomFS overlay, made from your own game files and
Archipelago's logo. Every check gives it in place of its normal reward (tools/strip_rewards.py).
  - Actor/Pack/Item_AP_00.sbactorpack: the Star Fragment's pack (its model and sparkle)
  - UI/StockItem/Item_AP_00.sbitemico: the Star Fragment's icon with the logo drawn in
  - Actor/ActorInfo.product.sbyml: the Star Fragment's entry under the new name
  - Pack/Bootup_<lang>.pack: its name and description
  - System/Resource/ResourceSizeTable.product.srsizetable: room for the bigger files

    python -I tools/ap_item.py "<Savage Wind>/extracted/romfs" <overlay folder> "<Archipelago>/data/icon.png"
"""
import copy
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import byml  # noqa: E402
import nin  # noqa: E402

NAME, TEMPLATE = "Item_AP_00", "Item_Ore_J"
LANGS = ("USen", "EUen")
TEXT = {"Name": "Archipelago Item",
        "Desc": "Something found for the multiworld. Whoever it\nbelongs to - you or another player - Archipelago\nis sending it on its way."}


# ---- PNG (8-bit RGBA, not interlaced: Archipelago's icon)
def png_rgba(path):
    d = open(path, "rb").read()
    w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", d[16:29])
    assert (bd, ct, il) == (8, 6, 0), "an 8-bit RGBA PNG"
    idat, o = b"", 8
    while o < len(d):
        n, kind = struct.unpack(">I4s", d[o:o + 8])
        if kind == b"IDAT":
            idat += d[o + 8:o + 8 + n]
        o += 12 + n
    raw, stride, out = zlib.decompress(idat), w * 4, bytearray()
    prev = bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b, c = prev[i], prev[i - 4] if i >= 4 else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line
        prev = line
    return w, h, bytes(out)


def fit(w, h, rgba, size, inner):
    """The image scaled (box filter) to inner x inner, centred in a transparent size x size"""
    out = bytearray(size * size * 4)
    off = (size - inner) // 2
    for y in range(inner):
        y0, y1 = y * h // inner, max(y * h // inner + 1, (y + 1) * h // inner)
        for x in range(inner):
            x0, x1 = x * w // inner, max(x * w // inner + 1, (x + 1) * w // inner)
            acc, n = [0, 0, 0, 0], 0
            for sy in range(y0, y1):
                for sx in range(x0, x1):
                    p = (sy * w + sx) * 4
                    a = rgba[p + 3]
                    acc[0] += rgba[p] * a; acc[1] += rgba[p + 1] * a; acc[2] += rgba[p + 2] * a; acc[3] += a
                    n += 1
            o = ((y + off) * size + x + off) * 4
            if acc[3]:
                out[o:o + 4] = bytes((acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3], acc[3] // n))
    return bytes(out)


# ---- Tegra block linear (GOB 64 bytes x 8 rows, `bh` GOBs a block), 4 bytes a pixel
def gob_addr(xb, y, width_gobs, bh):
    rows = 8 * bh
    return (((y // rows) * width_gobs * bh + (xb // 64) * bh + (y % rows) // 8) * 512 +
            ((xb % 64) // 32) * 256 + ((y % 8) // 2) * 64 + ((xb % 32) // 16) * 32 + (y % 2) * 16 + xb % 16)


def swizzle(rgba, w, h, bh, size):
    out, wg = bytearray(size), (w * 4 + 63) // 64
    for y in range(h):
        for x in range(0, w * 4, 16):
            a = gob_addr(x, y, wg, bh)
            out[a:a + 16] = rgba[y * w * 4 + x:y * w * 4 + x + 16]
    return bytes(out)


def deswizzle(data, w, h, bh):
    out, wg = bytearray(w * h * 4), (w * 4 + 63) // 64
    for y in range(h):
        for x in range(0, w * 4, 16):
            a = gob_addr(x, y, wg, bh)
            out[y * w * 4 + x:y * w * 4 + x + 16] = data[a:a + 16]
    return bytes(out)


def make_icon(icon_raw, logo):
    d = bytearray(nin.yaz0(icon_raw))
    k = d.find(b"BNTX")
    r, t = d.find(b"BRTI", k), d.find(b"BRTD", k)
    fmt, w, h, bh = (struct.unpack_from("<I", d, r + o)[0] for o in (0x1c, 0x24, 0x28, 0x34))
    assert fmt >> 8 == 0x0b and bh < 6, "an RGBA8 block linear icon"
    bh = 1 << bh
    rows = (h + 8 * bh - 1) // (8 * bh) * 8 * bh
    size = (w * 4 + 63) // 64 * 64 * rows
    old = bytes(d[t + 16:t + 16 + size])
    assert swizzle(deswizzle(old, w, h, bh), w, h, bh, size) == old or True  # (padding bytes may differ)
    # the Star Fragment's own picture faded under the logo, so it still reads as an item of the game
    star = deswizzle(old, w, h, bh)
    lw, lh, lp = logo
    mark = fit(lw, lh, lp, w, int(w * 0.86))
    px = bytearray(star)
    for i in range(0, len(px), 4):
        a = mark[i + 3] / 255
        px[i + 3] = max(int(star[i + 3] * 0.25), mark[i + 3])
        for c in range(3):
            px[i + c] = int(mark[i + c] * a + star[i + c] * 0.25 * (1 - a))
    d[t + 16:t + 16 + size] = swizzle(bytes(px), w, h, bh, size)
    return nin.yaz0_store(bytes(d), struct.unpack_from(">I", icon_raw, 8)[0])


# ---- MSBT: a label added to a message file, every other byte kept
def msbt_add(data, labels):
    """labels: {label: text}. LBL1 / ATR1 / TXT2 (and TSY1) get one entry each (a label it already has: its text is
    replaced); the other sections stay."""
    assert data[:8] == b"MsgStdBn" and data[8:10] == b"\xff\xfe"
    nsec = struct.unpack_from("<H", data, 0x0E)[0]
    o, secs = 0x20, []
    for _ in range(nsec):
        magic, size = data[o:o + 4], struct.unpack_from("<I", data, o + 4)[0]
        secs.append([magic, bytearray(data[o + 16:o + 16 + size])])
        o = (o + 16 + size + 15) & ~15
    sec = {m: b for m, b in secs}
    txt = sec[b"TXT2"]
    n = struct.unpack_from("<I", txt, 0)[0]
    offs = [struct.unpack_from("<I", txt, 4 + 4 * k)[0] for k in range(n)] + [len(txt)]
    texts = [bytes(txt[offs[k]:offs[k + 1]]) for k in range(n)]
    lbl = sec[b"LBL1"]
    nb = struct.unpack_from("<I", lbl, 0)[0]
    buckets = [[] for _ in range(nb)]
    for b in range(nb):
        cnt, off = struct.unpack_from("<II", lbl, 4 + 8 * b)
        for _ in range(cnt):
            ln = lbl[off]
            buckets[b].append((lbl[off + 1:off + 1 + ln], struct.unpack_from("<I", lbl, off + 1 + ln)[0]))
            off += 5 + ln
    have = {bytes(nm): idx for b in buckets for nm, idx in b}
    added = 0
    for name, text in labels.items():
        if name.encode() in have:  # (a label it has: its text replaced)
            texts[have[name.encode()]] = text.encode("utf-16-le") + b"\0\0"
            continue
        h = 0
        for ch in name.encode():
            h = (h * 0x492 + ch) & 0xFFFFFFFF
        buckets[h % nb].append((name.encode(), len(texts)))
        texts.append(text.encode("utf-16-le") + b"\0\0")
        added += 1
    out = bytearray(struct.pack("<I", nb))
    body, pos = bytearray(), 4 + 8 * nb
    for b in buckets:
        out += struct.pack("<II", len(b), pos + len(body))
        for nm, idx in b:
            body += bytes([len(nm)]) + nm + struct.pack("<I", idx)
    sec[b"LBL1"][:] = out + body
    t = bytearray(struct.pack("<I", len(texts)))
    pos = 4 + 4 * len(texts)
    for x in texts:
        t += struct.pack("<I", pos)
        pos += len(x)
    sec[b"TXT2"][:] = t + b"".join(texts)
    if b"ATR1" in sec:
        a = sec[b"ATR1"]
        cnt, esz = struct.unpack_from("<II", a, 0)
        assert len(a) == 8 + cnt * esz, "ATR1 with strings: not handled"
        sec[b"ATR1"][:] = struct.pack("<II", len(texts), esz) + a[8:] + bytes(esz * (len(texts) - cnt))
    if b"TSY1" in sec:
        sec[b"TSY1"] += bytes(4 * added)
    res = bytearray(data[:0x20])
    for magic, body in secs:
        res += magic + struct.pack("<I", len(body)) + b"\0" * 8 + body
        res += b"\xab" * (-len(res) % 16)
    struct.pack_into("<I", res, 0x12, len(res))
    return bytes(res)


def rstb_grow(rstb_raw, sizes):
    """sizes: {resource path: bytes it needs at least}"""
    d = bytearray(nin.yaz0(rstb_raw))
    assert d[:4] == b"RSTB"
    ncrc = struct.unpack_from("<I", d, 4)[0]
    by_crc = {struct.unpack_from("<I", d, 12 + 8 * k)[0]: 12 + 8 * k for k in range(ncrc)}
    for path, need in sizes.items():
        at = by_crc.get(zlib.crc32(path.encode()))
        if at is None:
            print("not in the size table (the game sizes it from the file):", path)
            continue
        old = struct.unpack_from("<I", d, at + 4)[0]
        if need > old:
            struct.pack_into("<I", d, at + 4, need)
            print(f"size table: {path} {old} -> {need}")
    return nin.yaz0_store(bytes(d), struct.unpack_from(">I", rstb_raw, 8)[0])


def put(out, rel, data):
    p = os.path.join(out, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


def main(romfs, out, logo_png):
    rd = lambda *p: open(os.path.join(romfs, *p), "rb").read()
    # (the template's pack, with its ActorLink under the new name too: the game finds an actor's parts through it)
    tp = rd("Actor", "Pack", f"{TEMPLATE}.sbactorpack")
    pk = nin.sarc(tp)
    pk[f"Actor/ActorLink/{NAME}.bxml"] = pk[f"Actor/ActorLink/{TEMPLATE}.bxml"]
    put(out, f"Actor/Pack/{NAME}.sbactorpack", nin.yaz0_store(nin.sarc_write(pk, nin.sarc_aligns(nin.yaz0(tp))),
                                                               struct.unpack_from(">I", tp, 8)[0]))
    put(out, f"UI/StockItem/{NAME}.sbitemico", make_icon(rd("UI", "StockItem", f"{TEMPLATE}.sbitemico"), png_rgba(logo_png)))
    # the actor table: the template's entry under the new name, at its hash's place
    ai_raw = rd("Actor", "ActorInfo.product.sbyml")
    ai_d = nin.yaz0(ai_raw)
    ai = byml.read(ai_d)
    if NAME not in (a["name"] for a in ai["Actors"]):
        entry = copy.deepcopy(next(a for a in ai["Actors"] if a["name"] == TEMPLATE))
        entry["name"] = NAME
        for k, v in (("itemSellingPrice", 0), ("itemBuyingPrice", 0)):
            if k in entry:
                entry[k] = type(entry[k])(v)
        h = zlib.crc32(NAME.encode())
        at = next((i for i, x in enumerate(ai["Hashes"]) if (x & 0xFFFFFFFF) > h), len(ai["Hashes"]))
        ai["Hashes"].insert(at, type(ai["Hashes"][0])(h if type(ai["Hashes"][0]).__name__ == "U32" else
                                                      struct.unpack("<i", struct.pack("<I", h))[0]))
        ai["Actors"].insert(at, entry)
    ai_new = byml.write(ai, struct.unpack_from("<H", ai_d, 2)[0])
    put(out, "Actor/ActorInfo.product.sbyml", nin.yaz0_store(ai_new, struct.unpack_from(">I", ai_raw, 8)[0]))
    sizes = {"Actor/ActorInfo.product.byml": len(ai_new) + 0x1000}
    # the name and description, in the English message files
    for lang in LANGS:
        pack_raw = rd("Pack", f"Bootup_{lang}.pack")
        pack = nin.sarc(pack_raw)
        mkey = f"Message/Msg_{lang}.product.ssarc"
        msg_raw = pack[mkey]
        msg = nin.sarc(msg_raw)
        msg["ActorType/Item.msbt"] = msbt_add(msg["ActorType/Item.msbt"],
                                              {f"{NAME}_{k}": v for k, v in TEXT.items()})
        assert nin.msbt(msg["ActorType/Item.msbt"])[f"{NAME}_Name"] == TEXT["Name"]
        msg_new = nin.sarc_write(msg, nin.sarc_aligns(msg_raw))
        pack[mkey] = nin.yaz0_store(msg_new, struct.unpack_from(">I", msg_raw, 8)[0])
        put(out, f"Pack/Bootup_{lang}.pack", nin.sarc_write(pack, nin.sarc_aligns(pack_raw)))
        sizes[f"Message/Msg_{lang}.product.sarc"] = len(msg_new) + 0x1000
    put(out, "System/Resource/ResourceSizeTable.product.srsizetable",
        rstb_grow(rd("System", "Resource", "ResourceSizeTable.product.srsizetable"), sizes))
    print("Archipelago Item written to", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
