"""Render the ami orb as PNG icons (16/32/48/128) using only the standard library."""
import math
import struct
import sys
import zlib
from pathlib import Path

TEAL = (20, 163, 139)
DEEP = (8, 72, 62)


def orb(size: int) -> bytes:
    rows = []
    c = (size - 1) / 2
    r = size * 0.46
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            d = math.hypot(x - c, y - c)
            alpha = max(0.0, min(1.0, r - d + 0.5))  # anti-aliased edge
            # body: radial blend from teal (center-low) to deep (edge)
            t = min(1.0, math.hypot(x - c, y - c * 1.15) / r)
            col = [TEAL[i] * (1 - t) + DEEP[i] * t for i in range(3)]
            # highlight near top-left
            hl = max(0.0, 1 - math.hypot(x - size * 0.34, y - size * 0.28) / (size * 0.22))
            col = [v + (255 - v) * hl * 0.85 for v in col]
            row += bytes([int(col[0]), int(col[1]), int(col[2]), int(alpha * 255)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "extension/icons")
    out.mkdir(parents=True, exist_ok=True)
    for s in (16, 32, 48, 128):
        (out / f"icon-{s}.png").write_bytes(orb(s))
    print(f"wrote icons to {out}")
