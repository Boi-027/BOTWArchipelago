"""BYML (little-endian, as on the Switch) read and write, keeping every value's type so a rewritten file is what the
game expects. Plain Python containers; numbers come back as S32/U32/F32/S64/U64/F64 (int/float subclasses), and a
plain int or float written is s32 / f32.

    python -I byml.py <file.smubin>   # self-check: read, write, read again, compare
"""
import struct
import sys


class S32(int): T = 0xD1
class U32(int): T = 0xD3
class S64(int): T = 0xD4
class U64(int): T = 0xD5
class F32(float): T = 0xD2
class F64(float): T = 0xD6


def read(data: bytes):
    if data[:2] != b"YB":
        raise ValueError("not a little-endian BYML")
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    keys_off, strs_off, root_off = u32(4), u32(8), u32(12)

    def table(off):
        if not off:
            return []
        n = u32(off) >> 8
        return [data[off + u32(off + 4 + 4 * k):data.index(b"\0", off + u32(off + 4 + 4 * k))].decode("utf8")
                for k in range(n)]

    keys, strs = table(keys_off), table(strs_off)

    def node(t, v):
        if t == 0xA0: return strs[v]
        if t == 0xC0: return arr(v)
        if t == 0xC1: return dct(v)
        if t == 0xD0: return bool(v)
        if t == 0xD1: return S32(struct.unpack("<i", struct.pack("<I", v))[0])
        if t == 0xD2: return F32(struct.unpack("<f", struct.pack("<I", v))[0])
        if t == 0xD3: return U32(v)
        if t == 0xD4: return S64(struct.unpack_from("<q", data, v)[0])
        if t == 0xD5: return U64(struct.unpack_from("<Q", data, v)[0])
        if t == 0xD6: return F64(struct.unpack_from("<d", data, v)[0])
        if t == 0xFF: return None
        raise ValueError(f"BYML node type {t:#x}")

    def arr(off):
        n = u32(off) >> 8
        base = off + 4 + ((n + 3) & ~3)
        return [node(data[off + 4 + k], u32(base + 4 * k)) for k in range(n)]

    def dct(off):
        out = {}
        for k in range(u32(off) >> 8):
            w = u32(off + 4 + 8 * k)
            out[keys[w & 0xFFFFFF]] = node(w >> 24, u32(off + 8 + 8 * k))
        return out

    t = data[root_off]
    return arr(root_off) if t == 0xC0 else dct(root_off)


def write(root, version: int = 2) -> bytes:
    keys, strs = set(), set()

    def collect(n):
        if isinstance(n, dict):
            for k, v in n.items():
                keys.add(k), collect(v)
        elif isinstance(n, list):
            for v in n:
                collect(v)
        elif isinstance(n, str):
            strs.add(n)
    collect(root)
    keys, strs = sorted(keys, key=lambda s: s.encode()), sorted(strs, key=lambda s: s.encode())
    kidx, sidx = {k: i for i, k in enumerate(keys)}, {s: i for i, s in enumerate(strs)}
    out = bytearray(16)

    def align(a):
        out.extend(b"\0" * (-len(out) % a))

    def put_table(items):
        if not items:
            return 0
        align(4)
        start = len(out)
        enc = [s.encode("utf8") + b"\0" for s in items]
        out.extend(struct.pack("<I", 0xC2 | len(items) << 8))
        pos = 4 + 4 * (len(items) + 1)
        for e in enc:
            out.extend(struct.pack("<I", pos))
            pos += len(e)
        out.extend(struct.pack("<I", pos))
        for e in enc:
            out.extend(e)
        return start

    k_off, s_off = put_table(keys), put_table(strs)
    big = []  # (place to patch, 8 bytes): 64-bit values go after the containers

    def tv(v):
        if isinstance(v, bool): return 0xD0, int(v)
        if v is None: return 0xFF, 0
        if isinstance(v, str): return 0xA0, sidx[v]
        if isinstance(v, (dict, list)): return (0xC1 if isinstance(v, dict) else 0xC0), None
        t = getattr(type(v), "T", 0xD2 if isinstance(v, float) else 0xD1)
        if t == 0xD1: return t, struct.unpack("<I", struct.pack("<i", v))[0]
        if t == 0xD2: return t, struct.unpack("<I", struct.pack("<f", v))[0]
        if t == 0xD3: return t, int(v) & 0xFFFFFFFF
        fmt = {0xD4: "<q", 0xD5: "<Q", 0xD6: "<d"}[t]
        return t, struct.pack(fmt, v)

    shared = {}  # identical containers are written once, as Nintendo's files do (else maps outgrow their size table)

    def key(n):
        if isinstance(n, dict):
            return ("d",) + tuple((k, key(v)) for k, v in sorted(n.items()))
        if isinstance(n, list):
            return ("a",) + tuple(key(v) for v in n)
        return (type(n).__name__, n)

    def container(n):
        k = key(n)
        if k in shared:
            return shared[k]
        align(4)
        start = len(out)
        shared[k] = start
        items = sorted(n.items(), key=lambda kv: kv[0].encode()) if isinstance(n, dict) else list(enumerate(n))
        if isinstance(n, dict):
            out.extend(struct.pack("<I", 0xC1 | len(items) << 8))
            slots = []
            for k, v in items:
                t, val = tv(v)
                slots.append((len(out) + 4, v, t, val))
                out.extend(struct.pack("<II", kidx[k] | t << 24, 0))
        else:
            out.extend(struct.pack("<I", 0xC0 | len(items) << 8))
            tvs = [tv(v) for _, v in items]
            out.extend(bytes(t for t, _ in tvs))
            align(4)
            slots = []
            for (_, v), (t, val) in zip(items, tvs):
                slots.append((len(out), v, t, val))
                out.extend(b"\0\0\0\0")
        for at, v, t, val in slots:
            if val is None:
                struct.pack_into("<I", out, at, container(v))
            elif isinstance(val, bytes):
                big.append((at, val))
            else:
                struct.pack_into("<I", out, at, val)
        return start

    root_off = container(root)
    for at, val in big:
        align(8)
        struct.pack_into("<I", out, at, len(out))
        out.extend(val)
    out[0:16] = b"YB" + struct.pack("<HIII", version, k_off, s_off, root_off)
    return bytes(out)


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
    import nin
    raw = nin.yaz0(open(sys.argv[1], "rb").read())
    a = read(raw)
    b = read(write(a, struct.unpack_from("<H", raw, 2)[0]))
    assert a == b and repr(a) == repr(b), "round trip differs"
    print("ok", len(raw), "bytes")
