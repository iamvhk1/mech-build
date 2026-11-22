"""Supply drop contesting (Stage F, roadmap item E5).

There are three supply drops per match (called at 70, 140, and 210 s).
Each drop lands 25 s after it is called, on open ground inside the circle the zone is closing to.
Capturing a drop (standing alone inside its 8 m ring for 4 s) grants:
- 3 power cubes (+12% max HP, +12% damage)
- Full HP heal (100% max HP)
- Full energy (100% energy)

Safety rules:
- Only contest when no known hunter is within `drops.safe_m` (default: 80 m)
- No enemy player mech is within `drops.safe_m`
- Drop is not already occupied by an enemy (`holder` is not someone else)
- Drop is reachable before the zone overtakes it:
  `zone.time_until_outside(drop_pos) > eta + 4.0 (capture) + 10.0 (buffer)`
- Drop is landed (`lands_in == 0`) or landing within our walk ETA (`lands_in <= eta + 5.0`)
- If already inside the 8 m ring (`dist <= radius - 1.5`), hold position to bank capture seconds.
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Sequence, Tuple
import tuning


class DropContester:
    def __init__(self, core, cfg: dict) -> None:
        self.core = core
        self.cfg = cfg
        self.drops: Dict[int, dict] = {}
        self.target_id: Optional[int] = None
        self.mode: str = ""

    def observe(self, obs: dict) -> None:
        seen = set()
        for d in obs.get("drops") or []:
            did = int(d["id"])
            self.drops[did] = d
            seen.add(did)
        for did in list(self.drops):
            if did not in seen:
                del self.drops[did]
        if self.target_id is not None and self.target_id not in self.drops:
            self.target_id = None
            self.mode = ""

    def is_safe(self, me_pos: Sequence[float], drop_pos: Sequence[float], hunters, threats, has_target: bool) -> bool:
        """Safe to contest drop: at most `drops.max_threats` known mechs (hunters or tracks) within
        safe distance of us or the drop; with max_threats 0 (default) also no active combat target."""
        allowed = int(tuning.get("drops.max_threats"))
        if has_target and allowed == 0:
            return False
        safe_m = float(tuning.get("drops.safe_m"))
        t = getattr(threats, "t", 0.0)
        near = set()
        for h in list(hunters) + list(getattr(threats, "tracks", {}).values()):
            p = h.pos_at(t)
            if math.hypot(p[0] - me_pos[0], p[1] - me_pos[1]) <= safe_m or \
                    math.hypot(p[0] - drop_pos[0], p[1] - drop_pos[1]) <= safe_m:
                near.add(h.id)
        return len(near) <= allowed

    def plan(self, obs: dict, zone, hunters, threats, has_target: bool) -> Optional[Tuple[float, float]]:
        """Return (x, y) goal to contest/capture a safe supply drop, or None."""
        if not tuning.get("drops.enabled"):
            return None
        me = obs["self"]
        pos = me["pos"]
        st = me.get("stats") or {}
        walk = max(1.0, float(st.get("walk_speed", self.cfg.get("mech", {}).get("walk_speed", 11.7))))
        max_dist = float(tuning.get("drops.max_dist"))
        my_id = me.get("id")

        candidates = []
        for did, d in self.drops.items():
            holder = d.get("holder")
            if holder is not None and holder != my_id:
                continue
            dp = d["pos"]
            dist_to_drop = math.hypot(dp[0] - pos[0], dp[1] - pos[1])
            if dist_to_drop > max_dist:
                continue

            eta = dist_to_drop / walk
            capture_time = float(d.get("capture_s", 4.0))
            if zone is not None and hasattr(zone, "time_until_outside"):
                time_left = zone.time_until_outside(dp)
                if time_left < eta + capture_time + 10.0:
                    continue

            lands_in = float(d.get("lands_in", 0.0))
            if lands_in > eta + float(tuning.get("drops.early_s")):
                continue

            if not self.is_safe(pos, dp, hunters, threats, has_target):
                continue

            candidates.append((dist_to_drop, did, d))

        if not candidates:
            self.target_id = None
            self.mode = ""
            return None

        candidates.sort(key=lambda c: c[0])
        dist, did, best_drop = candidates[0]
        self.target_id = did
        dp = best_drop["pos"]
        radius = float(best_drop.get("radius", 8.0))

        if dist <= radius - 1.5:
            self.mode = f"capturing {did}"
            return (pos[0], pos[1])

        self.mode = f"approach {did}"
        target = (dp[0], dp[1])
        if self.core is not None:
            r = float(st.get("radius", 2.5))
            target = self.core.nearest_walkable(dp[0], dp[1], r, True) or target
        return target
