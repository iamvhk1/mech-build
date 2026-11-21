"""Strafing while fighting (master plan Stage B, switch `fight.strafe`).

Gun bullets take ~0.3 s to cross 80 m, so a shooter has to aim where we'll be; changing direction
in that window makes it miss. Our own aim doesn't suffer (the torso is independent of the legs).

Move sideways relative to the target and reverse at random intervals (seeded, reproducible).
Safeguards, checked for every sideways step before taking it:
  - the step must be walkable (no strafing into walls, which would trigger a hop);
  - it must stay inside the zone with a margin;
  - it must not expose us to more known hunters than our current spot does (never step out of
    cover into another hunter's line of fire);
  - near cover, jinks are short (reverse sooner) so we don't wander away from it.
If one side fails, try the other; if both fail, don't strafe this decision.
"""
from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence, Tuple

LOOK_M = 3.0                  # check this far along the candidate direction
OPEN_INTERVAL_S = (0.6, 1.5)  # reverse every this long in the open
COVER_INTERVAL_S = (0.35, 0.6)  # ...and sooner near cover (short jinks)
COVER_NEAR = 0.3              # nav-cell cover score above which we count as "near cover"
TRAVEL_BLEND = 0.8            # while travelling, sideways weight relative to the travel direction
ZONE_MARGIN_M = 3.0


class Strafer:
    def __init__(self, core, cfg: dict, seed: int = 0):
        self.core = core
        self.cfg = cfg
        self.rng = random.Random(seed)
        self.side = 1
        self.switch_t = -1e9
        self.active = False

    def _exposure(self, xy: Sequence[float], eyes: List[Sequence[float]], h: float) -> int:
        """How many of `eyes` have a shot at our chest or top at xy."""
        z = self.core.floor_z(xy[0], xy[1])
        n = 0
        for e in eyes:
            if (self.core.shot_los(e, (xy[0], xy[1], z + h * 0.5)) >= 1.0 or
                    self.core.shot_los(e, (xy[0], xy[1], z + h)) >= 1.0):
                n += 1
        return n

    def adjust(self, obs: dict, move: Sequence[float], target_xy: Sequence[float],
               eyes: List[Sequence[float]], zone_circle=None) -> Tuple[List[float], bool]:
        """Return (move, strafing). `move` is navigation's move; `target_xy` whom we fight;
        `eyes` known hunters' eye points (including the target's)."""
        self.active = False
        if self.core is None:
            return list(move), False
        me = obs["self"]
        t = float(obs["t"])
        x, y, _ = me["pos"]
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        dx, dy = target_xy[0] - x, target_xy[1] - y
        dn = math.hypot(dx, dy)
        if dn < 1e-6:
            return list(move), False
        perp = (-dy / dn, dx / dn)
        near_cover = self.core.cover(x, y) >= COVER_NEAR
        if t >= self.switch_t:
            self.side = -self.side
            lo, hi = COVER_INTERVAL_S if near_cover else OPEN_INTERVAL_S
            self.switch_t = t + self.rng.uniform(lo, hi)
        mlen = math.hypot(move[0], move[1])
        travelling = mlen > 0.1
        here = self._exposure((x, y), eyes, h) if eyes else 0
        for s in (self.side, -self.side):
            d = (perp[0] * s, perp[1] * s)
            if travelling:
                bx, by = move[0] / mlen + TRAVEL_BLEND * d[0], move[1] / mlen + TRAVEL_BLEND * d[1]
                bn = math.hypot(bx, by)
                if bn < 1e-6:
                    continue
                d = (bx / bn, by / bn)
            q = (x + d[0] * LOOK_M, y + d[1] * LOOK_M)
            if not self.core.segment_walkable((x, y), q, r * 0.9):
                continue
            if zone_circle is not None:
                if zone_circle[2] - math.hypot(q[0] - zone_circle[0], q[1] - zone_circle[1]) < ZONE_MARGIN_M:
                    continue
            if eyes and self._exposure(q, eyes, h) > here:
                continue
            if s != self.side:
                self.side = s
                lo, hi = COVER_INTERVAL_S if near_cover else OPEN_INTERVAL_S
                self.switch_t = t + self.rng.uniform(lo, hi)
            self.active = True
            return [d[0], d[1]], True
        return list(move), False
