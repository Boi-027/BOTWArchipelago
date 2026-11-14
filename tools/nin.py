"""Minimal readers for Nintendo Switch BotW formats: Yaz0, SARC, BYML (little-endian). Read-only, no dependencies."""
import struct


def yaz0(data: bytes) -> bytes:
    if data[:4] != b"Yaz0":
        return data
    size = struct.unpack_from(">I", data, 4)[0]
    out = bytearray()
    i = 16
    while len(out) < size:
        code = data[i]; i += 1
        for bit in range(7, -1, -1):
            if len(out) >= size:
                break
            if code >> bit & 1:
                out.append(data[i]); i += 1
            else:
                b1, b2 = data[i], data[i + 1]; i += 2
                dist = ((b1 & 0xF) << 8 | b2) + 1
                n = b1 >> 4
                if n == 0:
                    n = data[i] + 0x12; i += 1
                else:
                    n += 2
                for _ in range(n):
                    out.append(out[-dist])
    return bytes(out)


def sarc(data: bytes) -> dict:
    data = yaz0(data)
    assert data[:4] == b"SARC", "not a SARC"
    bom = data[6:8]
    e = "<" if bom == b"\xff\xfe" else ">"
    data_off = struct.unpack_from(e + "I", data, 0x0C)[0]
    sfat = 0x14
    count = struct.unpack_from(e + "H", data, sfat + 6)[0]
    nodes = sfat + 12
    sfnt = nodes + count * 16
    names = sfnt + 8
    files = {}
    for k in range(count):
        _, attr, start, end = struct.unpack_from(e + "IIII", data, nodes + k * 16)
        name_off = (attr & 0xFFFF) * 4
        name = data[names + name_off:data.index(b"\0", names + name_off)].decode()
        files[name] = data[data_off + start:data_off + end]
    return files


def yaz0_store(data: bytes, align: int) -> bytes:
    """Valid Yaz0 without compression (every byte a literal): the game decodes it like any other.
    align: the original header's (+8): the buffer alignment the game decodes into (layouts: 0x1000, a 0 crashes)."""
    out = bytearray(b"Yaz0" + struct.pack(">II", len(data), align) + b"\0" * 4)
    for i in range(0, len(data), 8):
        out.append(0xFF)
        out += data[i:i + 8]
    return bytes(out)


def sarc_hash(name: str, key: int = 0x65) -> int:
    h = 0
    for c in name.encode():
        h = (h * key + (c if c < 128 else c - 256)) & 0xFFFFFFFF
    return h


def sarc_write(files: dict, align: dict) -> bytes:
    """Little-endian SARC; align[name] = the data alignment to keep (from sarc_aligns of the original)."""
    names = sorted(files, key=sarc_hash)
    sfnt, name_off = bytearray(), {}
    for n in names:
        name_off[n] = len(sfnt)
        sfnt += n.encode() + b"\0"
        sfnt += b"\0" * (-len(sfnt) % 4)
    head = 0x14 + 0xC + 16 * len(names) + 8 + len(sfnt)
    data_off = head + (-head % max([align.get(n, 4) for n in names] + [4]))
    blob, nodes = bytearray(), bytearray()
    for n in names:
        a = align.get(n, 4)
        blob += b"\0" * (-(data_off + len(blob)) % a)
        start = len(blob)
        blob += files[n]
        nodes += struct.pack("<IIII", sarc_hash(n), 0x01000000 | name_off[n] // 4, start, len(blob))
    out = bytearray(b"SARC" + struct.pack("<HHIIHH", 0x14, 0xFEFF, 0, data_off, 0x100, 0))
    out += b"SFAT" + struct.pack("<HHI", 0xC, len(names), 0x65) + nodes
    out += b"SFNT" + struct.pack("<HH", 8, 0) + sfnt
    out += b"\0" * (data_off - len(out)) + blob
    struct.pack_into("<I", out, 8, len(out))
    return bytes(out)


def sarc_aligns(data: bytes) -> dict:
    """name -> the largest power of two (up to 0x2000) each file's data offset is aligned to in this SARC."""
    data = yaz0(data)
    data_off = struct.unpack_from("<I", data, 0x0C)[0]
    out = {}
    for name, (start, _) in _sarc_ranges(data).items():
        a = 0x2000
        while (data_off + start) % a:
            a //= 2
        out[name] = max(a, 4)
    return out


def sarc_replace_inplace(data: bytes, name: str, new: bytes) -> bytes:
    """The same SARC with one file's bytes replaced where they are, every other byte unchanged: it must fit in
    its slot plus the padding before the next file (a re-laid-out layout archive crashes the game)."""
    data = bytearray(yaz0(data))
    data_off = struct.unpack_from("<I", data, 0x0C)[0]
    ranges = _sarc_ranges(data)
    start, _ = ranges[name]
    nxt = min([s for s, _ in ranges.values() if s > start] + [len(data) - data_off])
    if start + len(new) > nxt:  # (bigger: it moves to the end, aligned as big as anything; the rest stays put)
        data += b"\0" * (-(len(data)) % 0x2000)
        new_start = len(data) - data_off
        data += new
        count = struct.unpack_from("<H", data, 0x14 + 6)[0]
        for k in range(count):
            o = 0x14 + 12 + k * 16
            if struct.unpack_from("<I", data, o + 8)[0] == start:
                struct.pack_into("<II", data, o + 8, new_start, new_start + len(new))
        struct.pack_into("<I", data, 8, len(data))
        return bytes(data)
    data[data_off + start:data_off + nxt] = new + b"\0" * (nxt - start - len(new))
    count = struct.unpack_from("<H", data, 0x14 + 6)[0]
    for k in range(count):
        o = 0x14 + 12 + k * 16
        if struct.unpack_from("<I", data, o + 8)[0] == start:
            struct.pack_into("<I", data, o + 12, start + len(new))
    return bytes(data)


def _sarc_ranges(data: bytes) -> dict:
    count = struct.unpack_from("<H", data, 0x14 + 6)[0]
    nodes, names = 0x14 + 12, 0x14 + 12 + count * 16 + 8
    out = {}
    for k in range(count):
        _, attr, start, end = struct.unpack_from("<IIII", data, nodes + k * 16)
        o = names + (attr & 0xFFFF) * 4
        out[data[o:data.index(b"\0", o)].decode()] = (start, end)
    return out


def msbt(data: bytes) -> dict:
    """label -> text (UTF-16; control tags dropped)."""
    e = "<" if data[8:10] == b"\xff\xfe" else ">"
    nsec = struct.unpack_from(e + "H", data, 0x0E)[0]
    o, secs = 0x20, {}
    for _ in range(nsec):
        magic, size = data[o:o + 4], struct.unpack_from(e + "I", data, o + 4)[0]
        secs[magic] = data[o + 16:o + 16 + size]
        o = (o + 16 + size + 15) & ~15
    lbl, txt = secs[b"LBL1"], secs[b"TXT2"]
    n = struct.unpack_from(e + "I", txt, 0)[0]
    offs = [struct.unpack_from(e + "I", txt, 4 + 4 * k)[0] for k in range(n)] + [len(txt)]
    texts = []
    for k in range(n):
        raw = txt[offs[k]:offs[k + 1]]
        chars, i = [], 0
        while i + 1 < len(raw):
            c = struct.unpack_from(e + "H", raw, i)[0]; i += 2
            if c == 0x0E:  # tag: group, type, param size, params
                size = struct.unpack_from(e + "H", raw, i + 4)[0]; i += 6 + size
            elif c == 0x0F:
                i += 4
            elif c:
                chars.append(chr(c))
        texts.append("".join(chars))
    out = {}
    for k in range(struct.unpack_from(e + "I", lbl, 0)[0]):
        cnt, off = struct.unpack_from(e + "II", lbl, 4 + 8 * k)
        for _ in range(cnt):
            ln = lbl[off]; name = lbl[off + 1:off + 1 + ln].decode()
            out[name] = texts[struct.unpack_from(e + "I", lbl, off + 1 + ln)[0]]; off += 5 + ln
    return out


def byml(data: bytes):
    data = yaz0(data)
    e = "<" if data[:2] == b"YB" else ">"
    u32 = lambda o: struct.unpack_from(e + "I", data, o)[0]
    keys_off, strs_off, root_off = u32(4), u32(8), u32(12)

    def table(off):
        if not off:
            return []
        n = u32(off) >> 8
        return [data[off + u32(off + 4 + 4 * k):data.index(b"\0", off + u32(off + 4 + 4 * k))].decode("utf8", "replace")
                for k in range(n)]

    keys, strs = table(keys_off), table(strs_off)

    def node(t, v):
        if t == 0xA0: return strs[v]
        if t == 0xC0: return arr(v)
        if t == 0xC1: return dct(v)
        if t == 0xD0: return bool(v)
        if t == 0xD1: return struct.unpack(e + "i", struct.pack(e + "I", v))[0]
        if t == 0xD2: return struct.unpack(e + "f", struct.pack(e + "I", v))[0]
        if t == 0xD3: return v
        if t in (0xD4, 0xD5, 0xD6): return struct.unpack_from(e + ("q" if t == 0xD4 else "Q" if t == 0xD5 else "d"), data, v)[0]
        if t == 0xFF: return None
        return v

    def arr(off):
        n = u32(off) >> 8
        types = data[off + 4:off + 4 + n]
        base = off + 4 + ((n + 3) & ~3)
        return [node(types[k], u32(base + 4 * k)) for k in range(n)]

    def dct(off):
        n = u32(off) >> 8
        out = {}
        for k in range(n):
            o = off + 4 + 8 * k
            w = u32(o)
            key, t = (w & 0xFFFFFF, w >> 24) if e == "<" else (w >> 8, w & 0xFF)
            out[keys[key]] = node(t, u32(o + 4))
        return out

    t = data[root_off]
    return arr(root_off) if t == 0xC0 else dct(root_off)
