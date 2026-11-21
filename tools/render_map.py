"""Render the core's nav-grid layers to PNG files for visual inspection (stdlib only).

    python3 tools/render_map.py [--map-dir arena] [--out /tmp/mapviz] [--path x0,y0,x1,y1] [--radius 2.5]

Writes floor.png (height shading), clearance.png, ground.png (walkable street component,
red = passable but not reachable from the street, black = blocked) and cover.png. With --path,
ground.png also shows a planned path in yellow. North is up.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import core_api  # noqa: E402


def write_png(path: str, w: int, h: int, rgb: bytearray) -> None:
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw.extend(rgb[y * w * 3:(y + 1) * w * 3])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 6)))
        f.write(chunk(b"IEND", b""))


def image(core: core_api.MapCore, color) -> bytearray:
    """color(cell_index) -> (r, g, b); rows flipped so north is up."""
    w, h = core.nnx, core.nny
    out = bytearray(w * h * 3)
    for j in range(h):
        row = (h - 1 - j) * w * 3
        for i in range(w):
            r, g, b = color(j * w + i)
            k = row + i * 3
            out[k], out[k + 1], out[k + 2] = r, g, b
    return out


def main() -> None:
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    ap = argparse.ArgumentParser()
    ap.add_argument("--map-dir", default=os.path.join(here, "arena"))
    ap.add_argument("--out", default="/tmp/mapviz")
    ap.add_argument("--path", help="x0,y0,x1,y1: draw a planned path on ground.png")
    ap.add_argument("--radius", type=float, default=2.5)
    a = ap.parse_args()

    config = None
    stream = os.path.join(here, "check", "stream.jsonl.gz")
    if os.path.exists(stream):
        with gzip.open(stream, "rt") as f:
            config = json.loads(f.readline()).get("config")
    core = core_api.MapCore.from_dir(a.map_dir, config)
    os.makedirs(a.out, exist_ok=True)
    w, h = core.nnx, core.nny
    floor = core.layer(core_api.LAYER_FLOOR)
    clear = core.layer(core_api.LAYER_CLEARANCE)
    ground = core.layer(core_api.LAYER_GROUND)
    cover = core.layer(core_api.LAYER_COVER)

    lo, hi = min(floor), max(floor)

    def shade(c):
        v = int(255 * (floor[c] - lo) / (hi - lo + 1e-9))
        return (v, v, v)

    write_png(os.path.join(a.out, "floor.png"), w, h, image(core, shade))
    write_png(os.path.join(a.out, "clearance.png"), w, h,
              image(core, lambda c: (0, int(255 * min(clear[c], 6.0) / 6.0), 0)))
    write_png(os.path.join(a.out, "cover.png"), w, h,
              image(core, lambda c: (int(255 * cover[c]), int(255 * cover[c]), 0) if clear[c] > 0 else (0, 0, 0)))

    def gcol(c):
        if ground[c]:
            return (200, 200, 200)
        if clear[c] >= a.radius:
            return (200, 40, 40)
        return (0, 0, 0)

    img = image(core, gcol)
    if a.path:
        x0, y0, x1, y1 = (float(v) for v in a.path.split(","))
        pts = core.find_path((x0, y0), (x1, y1), a.radius) or []
        pts = [(x0, y0)] + pts
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            n = max(1, int(max(abs(bx - ax), abs(by - ay)) / core.res))
            for k in range(n + 1):
                x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
                i = int(round((x - core.min_x) / core.res))
                j = int(round((y - core.min_y) / core.res))
                if 0 <= i < w and 0 <= j < h:
                    p = ((h - 1 - j) * w + i) * 3
                    img[p], img[p + 1], img[p + 2] = 255, 220, 0
        print(f"path: {len(pts) - 1} waypoints")
    write_png(os.path.join(a.out, "ground.png"), w, h, img)
    print(f"wrote {a.out}/{{floor,clearance,ground,cover}}.png ({w}x{h}, build {core.build_ms:.0f} ms)")


if __name__ == "__main__":
    main()
