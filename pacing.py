"""Escalation survival (switch `fight.pacing`, batch C, 2026-11-22).

The practice probes (docs/experiments.md, batch B) show we earn most points between 2:00 and 4:00
and die around 3:00-4:30, when the squad sends more hunters after each kill. Two rules, both only
in the normal (rotate) state, with combat still shooting whatever it would shoot:

1. LOOT: right after a kill, walk over the cubes it dropped (all its cubes + 2). Each heals 4% of
   max HP and adds 4% damage, exactly when the next hunters are on their way. Regular farming
   doesn't do this, because it waits until no hunter is within 120 m.
2. SPLIT: with two or more fresh hunters close, step away from the ones behind the nearest, so we
   keep fighting the nearest one while the others arrive later (one at a time, not together).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

LOOT_WINDOW_S = 15.0      # go for a kill's cubes for this long after the kill
LOOT_RADIUS_M = 15.0      # cubes this close to where the mech died are its drop
LOOT_MAX_M = 60.0         # ...and at most this far from us
LOOT_MIN_HP = 0.20        # don't walk into the open for cubes below this HP fraction
LOOT_CLOSE_M = 50.0       # skip looting with 2+ hunters this close
SPLIT_RANGE_M = 110.0     # hunters this close count for the split
SPLIT_FRESH_S = 5.0       # ...if seen this recently (a guessed position from a hit is too vague)
SPLIT_STEP_M = 20.0       # step this far away from the trailing hunters
ZONE_MARGIN_S = 10.0      # don't step somewhere the zone covers within ETA + this


class Pacer:
    def __init__(self, core, cfg: dict):
        self.core = core
        self.cfg = cfg
        self.last_seen: Dict[int, Tuple[float, float, float]] = {}
        self.kill_t = -1e9
        self.kill_pos: Optional[Sequence[float]] = None
        self.mode = ""

    def observe(self, obs: dict) -> None:
        """Call before the threat tracker forgets a killed mech: remembers where mechs were."""
        t = float(obs["t"])
        for m in obs.get("mechs") or []:
            if m.get("kind", "mech") == "mech":
                self.last_seen[int(m["id"])] = tuple(m["pos"])
        for e in obs.get("events") or []:
            if e.get("type") == "kill":
                p = self.last_seen.get(int(e.get("target", -1)))
                if p is not None:
                    self.kill_t, self.kill_pos = t, p

    def _zone_ok(self, zone, p, pos, walk: float) -> bool:
        if zone is None or not getattr(zone, "known", False):
            return True
        return zone.time_until_outside(p) > math.dist(p[:2], pos[:2]) / max(1.0, walk) + ZONE_MARGIN_S

    def plan(self, obs: dict, zone, hunters, threats, cubes, walk: float) -> Optional[Tuple[float, float]]:
        """(x, y) goal, or None to leave the decision to drops / farming / the zone destination.
        `cubes`: the farmer's remembered cubes (id -> item with .pos)."""
        me = obs["self"]
        pos = me["pos"]
        t = float(obs["t"])
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        self.mode = ""
        tt = getattr(threats, "t", t)
        fresh = [h for h in hunters if t - h.t_seen < SPLIT_FRESH_S
                 and math.dist(h.pos_at(tt)[:2], pos[:2]) <= SPLIT_RANGE_M]

        # 1) loot the kill's cubes
        if self.kill_pos is not None and t - self.kill_t <= LOOT_WINDOW_S and hp >= LOOT_MIN_HP:
            close = sum(1 for h in fresh if math.dist(h.pos_at(tt)[:2], pos[:2]) <= LOOT_CLOSE_M)
            if close <= 1:
                drop = [c for c in cubes.values()
                        if math.dist(c.pos[:2], self.kill_pos[:2]) <= LOOT_RADIUS_M
                        and math.dist(c.pos[:2], pos[:2]) <= LOOT_MAX_M
                        and self._zone_ok(zone, c.pos, pos, walk)]
                if drop:
                    c = min(drop, key=lambda c: math.dist(c.pos[:2], pos[:2]))
                    self.mode = f"loot {c.id}"
                    return (c.pos[0], c.pos[1])

        # 2) split the hunters
        if len(fresh) >= 2:
            fresh.sort(key=lambda h: math.dist(h.pos_at(tt)[:2], pos[:2]))
            rest = [h.pos_at(tt) for h in fresh[1:]]
            cx = sum(p[0] for p in rest) / len(rest)
            cy = sum(p[1] for p in rest) / len(rest)
            dx, dy = pos[0] - cx, pos[1] - cy
            n = math.hypot(dx, dy)
            if n < 1e-6:
                return None
            goal = (pos[0] + dx / n * SPLIT_STEP_M, pos[1] + dy / n * SPLIT_STEP_M)
            if self.core is not None:
                r = float((me.get("stats") or {}).get("radius", 2.5))
                q = self.core.nearest_walkable(goal[0], goal[1], r, False)
                if q is None or math.dist(q, goal) > 8.0:
                    return None  # wall behind us: keep the normal plan
                goal = (q[0], q[1])
            if not self._zone_ok(zone, goal, pos, walk):
                return None
            self.mode = f"split {len(fresh)}"
            return goal
        return None
