"""Fight from cover (master plan Stage B, switch `fight.cover`).

When we have a target, pick two nearby spots: a COVER spot hidden from the target and other close
hunters, and a FIRING spot a few metres away with a clear shot at the target. Step out to fire
when the gun is ready and we're healthy; step back into cover while reloading, right after taking
a burst of damage, or when hurt. Recompute the pair when the target moves.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

SEARCH_RADII = (3.0, 6.0, 9.0, 12.0, 16.0)
SEARCH_DIRS = 16
MAX_PAIR_GAP_M = 7.0        # cover and firing spot this close: a short step between them
RECOMPUTE_S = 1.5
TARGET_MOVED_M = 8.0
BURST_WINDOW_S = 1.0
BURST_FRAC = 0.08           # step back after losing this much of max HP within BURST_WINDOW_S
HURT_FRAC = 0.40            # below this HP fraction, stay in cover (the retreat logic decides more)
MIN_TARGET_M = 12.0         # closer than this, cover dancing doesn't help: just fight
MAX_TARGET_M = 150.0


class CoverFighter:
    def __init__(self, core, cfg: dict):
        self.core = core
        self.cfg = cfg
        self.cover: Optional[Tuple[float, float]] = None
        self.fire: Optional[Tuple[float, float]] = None
        self.pair_t = -1e9
        self.pair_target: Optional[Tuple[float, float]] = None
        self.pair_id: Optional[int] = None
        self.mode = ""

    # ------------------------------------------------------------ geometry

    def _chest(self, xy: Sequence[float], h: float) -> Tuple[float, float, float]:
        return (xy[0], xy[1], self.core.floor_z(xy[0], xy[1]) + h * 0.5)

    def _seen_by(self, xy, eyes: List[Sequence[float]], h: float) -> bool:
        """Any of `eyes` has a shot at our chest or top at xy."""
        z = self.core.floor_z(xy[0], xy[1])
        for e in eyes:
            for hz in (h * 0.5, h):
                if self.core.shot_los(e, (xy[0], xy[1], z + hz)) >= 1.0:
                    return True
        return False

    def _can_shoot(self, xy, target_center: Sequence[float], muzzle_h: float) -> bool:
        z = self.core.floor_z(xy[0], xy[1])
        return self.core.shot_los((xy[0], xy[1], z + muzzle_h), target_center) >= 1.0

    def find_pair(self, me: dict, target_center: Sequence[float], other_eyes: List[Sequence[float]]):
        """(cover, firing) spots near us, or (None, None)."""
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        mh = float(st.get("muzzle_height", 7.0))
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        x, y, _ = me["pos"]
        t_eye = (target_center[0], target_center[1], target_center[2] - h * 0.5 + eye)
        eyes = [t_eye] + list(other_eyes)
        covers, fires = [], []
        seen = set()
        for rad in (0.0,) + SEARCH_RADII:
            for k in range(SEARCH_DIRS if rad > 0 else 1):
                a = 2 * math.pi * k / SEARCH_DIRS
                q = self.core.nearest_walkable(x + rad * math.cos(a), y + rad * math.sin(a), r, False)
                if q is None or q in seen or math.dist(q, (x, y)) > rad + 3.0:
                    continue
                seen.add(q)
                if not self.core.segment_walkable((x, y), q, r * 0.9) and math.dist(q, (x, y)) > 1.0:
                    continue
                d_t = math.dist(q, target_center[:2])
                if d_t < MIN_TARGET_M:
                    continue
                if self._seen_by(q, eyes, h):
                    if self._can_shoot(q, target_center, mh):
                        fires.append(q)
                else:
                    covers.append(q)
        best, best_s = (None, None), math.inf
        for c in covers:
            for f in fires:
                gap = math.dist(c, f)
                if gap > MAX_PAIR_GAP_M or not self.core.segment_walkable(c, f, r * 0.9):
                    continue
                s = math.dist((x, y), c) + 2.0 * gap
                if s < best_s:
                    best, best_s = (c, f), s
        return best

    # ------------------------------------------------------------ decision

    def goal(self, obs: dict, target, hunters, threats, gun: Optional[dict]) -> Optional[Tuple[float, float]]:
        """Where to stand this decision while fighting `target` (combat.Target), or None to let
        the other behaviours decide (no target, too close/far, or no cover pair nearby)."""
        if self.core is None or target is None or target.kind != "mech":
            self.mode = ""
            return None
        me = obs["self"]
        t = float(obs["t"])
        if not (MIN_TARGET_M <= target.dist <= MAX_TARGET_M):
            self.mode = "close" if target.dist < MIN_TARGET_M else ""
            return None
        tpos = target.center
        if (self.cover is None or self.pair_id != target.id or t - self.pair_t >= RECOMPUTE_S
                or self.pair_target is None or math.dist(self.pair_target, tpos[:2]) > TARGET_MOVED_M):
            eye = float(self.cfg["mech"].get("eye_height", 8.0))
            others = []
            for hh in hunters:
                if hh.id == target.id:
                    continue
                p = hh.pos_at(threats.t)
                if math.dist(p[:2], me["pos"][:2]) <= 100.0:
                    others.append((p[0], p[1], p[2] + eye))
            self.cover, self.fire = self.find_pair(me, tpos, others[:3])
            self.pair_t, self.pair_target, self.pair_id = t, (tpos[0], tpos[1]), target.id
        if self.cover is None:
            self.mode = "no cover"
            return None
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        burst = threats.damage_taken(BURST_WINDOW_S) > BURST_FRAC * float(me.get("max_hp", 1400.0))
        reloading = gun is not None and (float(gun.get("reload", 0.0)) > 0.0 or float(gun.get("ammo", 1)) <= 0)
        if hp < HURT_FRAC or burst or reloading:
            self.mode = "cover"
            return self.cover
        self.mode = "fire"
        return self.fire
