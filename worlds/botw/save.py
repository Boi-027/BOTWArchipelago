"""game_data.sav: a 12-byte header, (u32 flag hash, s32 value) pairs, a 4-byte footer. Flag hash = crc32(flag name)."""
import struct


def read_save(path: str) -> dict:
    """hash -> first value. Bool and s32 flags are one entry each, which is all the client reads."""
    with open(path, "rb") as f:
        d = f.read()
    if len(d) < 16 or (len(d) - 16) % 8:
        raise ValueError(f"{path} is not a whole save (size {len(d)}); the game may be writing it")
    vals = {}
    for h, v in struct.iter_unpack("<Ii", d[12:-4]):
        vals.setdefault(h, v)
    return vals


if __name__ == "__main__":  # self-check: python -I save.py
    import os
    import tempfile
    import zlib
    h = zlib.crc32(b"Clear_Dungeon000")
    body = struct.pack("<III", 0x4730, 0xFFFFFFFF, 1) + struct.pack("<Ii", h, 1) + struct.pack("<Ii", 7, -3) + b"\0" * 4
    p = os.path.join(tempfile.mkdtemp(), "game_data.sav")
    with open(p, "wb") as f:
        f.write(body)
    assert read_save(p) == {h: 1, 7: -3}
    with open(p, "wb") as f:
        f.write(body[:-3])
    try:
        read_save(p)
        raise AssertionError("a cut save must be refused")
    except ValueError:
        pass
    print("ok")
