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

import tuning

LOOT_WINDOW_S = 15.0      # go for a kill's cubes for this long after the kill
LOOT_RADIUS_M = 15.0      # cubes this close to where the mech died are its drop
LOOT_MAX_M = 60.0         # ...and at most this far from us
LOOT_MIN_HP = 0.20        # don't walk into the open for cubes below this HP fraction
LOOT_MORE_WINDOW_S = 30.0  # pacing.loot_more: remember every kill this long (not only the last one)
LOOT_RETREAT_M = 30.0     # ...and loot cubes this close even while retreating, at any HP / hunter count
LOOT_CLOSE_M = 50.0       # skip looting with 2+ hunters this close
SPLIT_RANGE_M = 110.0     # hunters this close count for the split
SPLIT_FRESH_S = 5.0       # ...if seen this recently (a guessed position from a hit is too vague)
SPLIT_STEP_M = 20.0       # step this far away from the trailing hunters
ZONE_MARGIN_S = 10.0      # don't step somewhere the zone covers within ETA + this
PRESS_TO_M = 25.0         # press: close to this distance from a lone hunter (lightning reaches 45 m)
PRESS_FROM_M = 32.0       # ...when it is farther than this
PRESS_MAX_M = 90.0        # ...and not farther than this
PRESS_MIN_HP = 0.50
PRESS_MIN_ENERGY = 35.0   # ~4 s of arcs (3 energy per 0.25 s shot)
LOS_STEP_M = 7.0          # los steering: candidate spots this far away in 16 directions
LOS_RANGE_M = 110.0       # ...counting fresh hunters this close
HUNT_MIN_HP = 0.70        # hunt: go after the only mech we know of (the squad sends one at a time early)
HUNT_MIN_ENERGY = 50.0


class Pacer:
    def __init__(self, core, cfg: dict):
        self.core = core
        self.cfg = cfg
        self.last_seen: Dict[int, Tuple[float, float, float]] = {}
        self.kill_t = -1e9
        self.kill_pos: Optional[Sequence[float]] = None
        self.kills: List[Tuple[float, Sequence[float]]] = []  # (t, where) of recent kills
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
                    self.kills.append((t, p))
        self.kills = [k for k in self.kills if t - k[0] <= LOOT_MORE_WINDOW_S]

    def _zone_ok(self, zone, p, pos, walk: float) -> bool:
        if zone is None or not getattr(zone, "known", False):
            return True
        return zone.time_until_outside(p) > math.dist(p[:2], pos[:2]) / max(1.0, walk) + ZONE_MARGIN_S

    def loot_goal(self, obs: dict, zone, hunters, threats, cubes, walk: float,
                  retreating: bool) -> Optional[Tuple[float, float]]:
        """pacing.loot_more: the nearest cube dropped by any kill in the last 30 s. Cubes within
        LOOT_RETREAT_M are taken at any HP and hunter count (once the squad has found us, running
        doesn't heal; a cube heals 4% and adds 4% damage). Farther ones (up to LOOT_MAX_M) only
        when not retreating, HP >= LOOT_MIN_HP and at most one hunter within LOOT_CLOSE_M."""
        if not self.kills:
            return None
        me = obs["self"]
        pos = me["pos"]
        t = float(obs["t"])
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        tt = getattr(threats, "t", t)
        close = sum(1 for h in hunters if t - h.t_seen < SPLIT_FRESH_S
                    and math.dist(h.pos_at(tt)[:2], pos[:2]) <= LOOT_CLOSE_M)
        far_ok = not retreating and hp >= LOOT_MIN_HP and close <= 1
        best, bd = None, 1e9
        for c in cubes.values():
            if not any(math.dist(c.pos[:2], kp[:2]) <= LOOT_RADIUS_M for _, kp in self.kills):
                continue
            d = math.dist(c.pos[:2], pos[:2])
            if d > (LOOT_MAX_M if far_ok else LOOT_RETREAT_M) or d >= bd:
                continue
            if not self._zone_ok(zone, c.pos, pos, walk):
                continue
            best, bd = c, d
        if best is None:
            return None
        self.mode = f"loot {best.id}"
        return (best.pos[0], best.pos[1])

    def _exposure(self, xy, eyes, h: float) -> int:
        z = self.core.floor_z(xy[0], xy[1])
        n = 0
        for e in eyes:
            if self.core.shot_los(e, (xy[0], xy[1], z + h * 0.5)) >= 1.0 or \
                    self.core.shot_los(e, (xy[0], xy[1], z + h)) >= 1.0:
                n += 1
        return n

    def _los_goal(self, me: dict, pos, hunter_pos, zone, walk: float) -> Optional[Tuple[float, float]]:
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        eyes = [(p[0], p[1], self.core.floor_z(p[0], p[1]) + eye) for p in hunter_pos
                if math.dist(p[:2], pos[:2]) <= LOS_RANGE_M]
        if len(eyes) < 2:
            return None
        here = self._exposure(pos, eyes, h)
        if here < 2:
            return None
        nearest = min(hunter_pos, key=lambda p: math.dist(p[:2], pos[:2]))
        best, best_s = None, (here, 0.0)
        for k in range(16):
            a = 2 * math.pi * k / 16
            q = self.core.nearest_walkable(pos[0] + LOS_STEP_M * math.cos(a), pos[1] + LOS_STEP_M * math.sin(a), r, False)
            if q is None or math.dist(q, pos[:2]) > LOS_STEP_M + 3.0:
                continue
            if not self.core.segment_walkable((pos[0], pos[1]), q, r * 0.9):
                continue
            if not self._zone_ok(zone, (q[0], q[1], 0.0), pos, walk):
                continue
            e = self._exposure(q, eyes, h)
            s = (e, math.dist(q, nearest[:2]))  # fewest eyes, then stay close to the lead chaser
            if s < best_s:
                best, best_s = q, s
        if best is None:
            return None
        self.mode = f"los {here}->{best_s[0]}"
        return (best[0], best[1])

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

        # 1) loot the kill's cubes (with pacing.loot_more: every recent kill, see loot_goal)
        if tuning.get("pacing.loot_more"):
            g = self.loot_goal(obs, zone, hunters, threats, cubes, walk, retreating=False)
            if g is not None:
                return g
        elif self.kill_pos is not None and t - self.kill_t <= LOOT_WINDOW_S and hp >= LOOT_MIN_HP:
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

        # 2) press a lone hunter into lightning range (we hold lightning, healthy, energy to spare)
        if tuning.get("fight.press") and len(fresh) == 1 and hp >= PRESS_MIN_HP and \
                float(me.get("energy", 0.0)) >= PRESS_MIN_ENERGY and \
                any(w and w.get("kind") == "lightning" for w in (me.get("weapons") or [])):
            h = fresh[0]
            hp_ = h.pos_at(tt)
            d = math.dist(hp_[:2], pos[:2])
            if PRESS_FROM_M < d <= PRESS_MAX_M:
                ux, uy = (pos[0] - hp_[0]) / d, (pos[1] - hp_[1]) / d
                goal = (hp_[0] + ux * PRESS_TO_M, hp_[1] + uy * PRESS_TO_M)
                if self.core is not None:
                    r = float((me.get("stats") or {}).get("radius", 2.5))
                    q = self.core.nearest_walkable(goal[0], goal[1], r, False)
                    goal = (q[0], q[1]) if q is not None else None
                if goal is not None and self._zone_ok(zone, goal, pos, walk):
                    self.mode = f"press {h.id} {d:.0f}m"
                    return goal

        # 3) hunt: the only mech we know of (tracked, hunting us or not), up to hunt.max_m away; the
        # early squad sends one bot at a time, so walking to it instead of waiting speeds up kills
        if tuning.get("fight.hunt") and hp >= HUNT_MIN_HP and \
                float(me.get("energy", 0.0)) >= HUNT_MIN_ENERGY and \
                any(w and w.get("kind") == "lightning" for w in (me.get("weapons") or [])):
            tracks = list(getattr(threats, "tracks", {}).values())
            if len(tracks) == 1:
                tr = tracks[0]
                p = tr.pos_at(tt)
                d = math.dist(p[:2], pos[:2])
                if PRESS_FROM_M < d <= float(tuning.get("hunt.max_m")):
                    ux, uy = (pos[0] - p[0]) / d, (pos[1] - p[1]) / d
                    goal = (p[0] + ux * PRESS_TO_M, p[1] + uy * PRESS_TO_M)
                    if self.core is not None:
                        r = float((me.get("stats") or {}).get("radius", 2.5))
                        q = self.core.nearest_walkable(goal[0], goal[1], r, False)
                        goal = (q[0], q[1]) if q is not None else None
                    if goal is not None and self._zone_ok(zone, goal, pos, walk):
                        self.mode = f"hunt {tr.id} {d:.0f}m"
                        return goal

        # 4) line-of-sight steering: with 2+ hunters able to shoot us, step to the nearby spot where the
        # fewest can (ideally one: our lightning works on it while a building blocks the rest)
        if tuning.get("fight.los") and len(fresh) >= 2 and self.core is not None:
            g = self._los_goal(me, pos, [h.pos_at(tt) for h in fresh], zone, walk)
            if g is not None:
                return g

        # 4) split the hunters
        if tuning.get("pacing.split") and len(fresh) >= 2:
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
