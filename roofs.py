"""Rooftops: find standable roofs at startup and pick one worth camping on.

A roof is a connected patch of building-roof nav cells (floor kind 1) that fits our radius, with
neighbouring cells within a step of each other. We keep roofs big enough to stand back from the
edge (out of sight of the street) and remember each roof's safest middle spot (the cell farthest
from any wall or edge).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import core_api

MIN_AREA_M2 = 150.0       # room to step back from the edge
MIN_HEIGHT_M = 6.0        # hunters must jump/jet to reach us
MAX_HEIGHT_M = 20.0       # we can climb it with a reasonable energy cost
MIN_ZONE_DEPTH_M = 12.0   # roof middle this far inside the next circle


class Roof:
    __slots__ = ("id", "cells", "floor", "height", "area", "core", "core_clear")

    def __init__(self, rid: int):
        self.id = rid
        self.cells: List[int] = []
        self.floor = 0.0
        self.height = 0.0
        self.area = 0.0
        self.core = (0.0, 0.0)
        self.core_clear = 0.0


class RoofIndex:
    def __init__(self, core, radius: float = 2.5, step_up: float = 1.2):
        self.core = core
        self.roofs: Dict[int, Roof] = {}
        self.label: Dict[int, int] = {}
        if core is None:
            return
        nnx, nny = core.nnx, core.nny
        kind = core.layer(core_api.LAYER_KIND)
        clear = core.layer(core_api.LAYER_CLEARANCE)
        floor = core.layer(core_api.LAYER_FLOOR)
        ok = [kind[c] == core_api.KIND_ROOF and clear[c] >= radius for c in range(nnx * nny)]
        rid = 0
        for s in range(nnx * nny):
            if not ok[s] or s in self.label:
                continue
            roof = Roof(rid)
            stack = [s]
            self.label[s] = rid
            while stack:
                c = stack.pop()
                roof.cells.append(c)
                i, j = c % nnx, c // nnx
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni, nj = i + di, j + dj
                    if 0 <= ni < nnx and 0 <= nj < nny:
                        n = nj * nnx + ni
                        if ok[n] and n not in self.label and abs(floor[n] - floor[c]) <= step_up:
                            self.label[n] = rid
                            stack.append(n)
            roof.area = len(roof.cells) * core.res * core.res
            if roof.area >= MIN_AREA_M2:
                best = max(roof.cells, key=lambda c: clear[c])
                roof.core = self.xy(best)
                roof.core_clear = clear[best]
                fl = sorted(floor[c] for c in roof.cells)
                roof.floor = fl[len(fl) // 2]
                street = core.nearest_walkable(roof.core[0], roof.core[1], radius, True)
                ground = core.floor_z(*street) if street else core.ground_z(*roof.core)
                roof.height = roof.floor - ground
                self.roofs[rid] = roof
            rid += 1

    def xy(self, c: int) -> Tuple[float, float]:
        return self.core.min_x + (c % self.core.nnx) * self.core.res, self.core.min_y + (c // self.core.nnx) * self.core.res

    def cell(self, x: float, y: float) -> int:
        i = int(round((x - self.core.min_x) / self.core.res))
        j = int(round((y - self.core.min_y) / self.core.res))
        return j * self.core.nnx + i

    def roof_at(self, pos: Sequence[float]) -> Optional[Roof]:
        """The roof we're standing on (feet within ~1.5 m of its floor), or None."""
        if self.core is None:
            return None
        r = self.roofs.get(self.label.get(self.cell(pos[0], pos[1]), -1))
        if r is not None and len(pos) > 2 and abs(pos[2] - r.floor) > 1.5:
            return None
        return r

    def usable(self, roof: Roof, zone, max_rise: float) -> bool:
        if not (MIN_HEIGHT_M <= roof.height <= min(MAX_HEIGHT_M, max_rise)):
            return False
        if zone is not None and zone.known:
            if zone.depth(zone.next_circle(), roof.core) < MIN_ZONE_DEPTH_M:
                return False
            if zone.depth(zone.current(), roof.core) < MIN_ZONE_DEPTH_M:
                return False
        return True

    def choose(self, zone, pos: Sequence[float], max_rise: float) -> Optional[Roof]:
        """Closest usable roof, preferring bigger ones."""
        best, best_s = None, math.inf
        for roof in self.roofs.values():
            if not self.usable(roof, zone, max_rise):
                continue
            s = math.dist(roof.core, pos[:2]) - min(roof.area, 2000.0) / 50.0
            if s < best_s:
                best, best_s = roof, s
        return best

    def edge_toward(self, roof: Roof, target: Sequence[float]) -> Tuple[float, float]:
        """The roof cell closest to `target`: the edge spot to shoot from toward it."""
        c = min(roof.cells, key=lambda c: math.dist(self.xy(c), target[:2]))
        return self.xy(c)
