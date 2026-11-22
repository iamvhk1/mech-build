"""Generate the 2D top-down map image of the Ohio State arena for the debug visualizer.

Outputs:
  visualizer/static/map.png (1070x724 high-res top-down campus map)
"""
from __future__ import annotations

import gzip
import json
import os
import sys

from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import core_api

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


def generate_map():
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "map.png")
    
    cfg = None
    stream_path = os.path.join(ROOT, "check", "stream.jsonl.gz")
    if os.path.exists(stream_path):
        with gzip.open(stream_path, "rt") as f:
            cfg = json.loads(f.readline()).get("config")
            
    arena_dir = os.path.join(ROOT, "arena")
    core = core_api.MapCore.from_dir(arena_dir, cfg)
    
    w, h = core.nnx, core.nny
    kinds = core.layer(core_api.LAYER_KIND)
    clear = core.layer(core_api.LAYER_CLEARANCE)
    ground = core.layer(core_api.LAYER_GROUND)
    floor = core.layer(core_api.LAYER_FLOOR)
    cover = core.layer(core_api.LAYER_COVER)
    
    # 2x scale for sharp rendering (1 pixel = 1 meter)
    img = Image.new("RGB", (w, h))
    pixels = img.load()
    
    for j in range(h):
        row_y = h - 1 - j  # flip so North (+y) is up
        for i in range(w):
            idx = j * w + i
            k = kinds[idx]
            c = clear[idx]
            g = ground[idx]
            cov = cover[idx]
            
            if k == 1.0:  # Roof
                col = (65, 75, 100)
            elif k == 2.0:  # Stadium
                col = (38, 55, 75)
            elif k == 3.0:  # Bridge deck
                col = (75, 95, 115)
            elif c < 2.5 and not g:  # Building walls / impassable structures
                col = (42, 48, 64)
            elif g:  # Walkable street
                if cov > 0.4:
                    col = (35, 45, 52)  # subtle cover hue
                else:
                    col = (25, 30, 40)  # asphalt
            elif c >= 2.5:  # Passable open terrain
                col = (20, 25, 34)
            else:
                col = (13, 15, 20)  # Out of bounds / void
                
            pixels[i, row_y] = col

    # Scale 2x for retina / sharp 1-meter-per-pixel resolution
    img_2x = img.resize((w * 2, h * 2), Image.NEAREST)
    img_2x.save(out_path)
    
    meta = {
        "min_x": core.min_x,
        "min_y": core.min_y,
        "max_x": core.min_x + core.nnx * core.res,
        "max_y": core.min_y + core.nny * core.res,
        "width_m": core.nnx * core.res,
        "height_m": core.nny * core.res,
        "img_w": w * 2,
        "img_h": h * 2,
        "res": core.res
    }
    
    with open(os.path.join(OUT_DIR, "map_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
        
    print(f"Map rendered: {out_path} ({w*2}x{h*2}), metadata saved.")
    return meta


if __name__ == "__main__":
    generate_map()
