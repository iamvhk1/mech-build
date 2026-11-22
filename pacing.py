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
CHOKE_RANGE_M = 150.0     # choke: with 2+ known hunters this close...
CHOKE_RINGS = (0.0, 6.0, 12.0, 20.0)   # ...look for a fighting spot this far away
CHOKE_LANE_M = 50.0       # a lane is open if a bot this far out in that direction could shoot us
CHOKE_HOLD_S = 3.0        # re-pick at most this often
MPC_HORIZON_S = 1.2       # mpc: roll each manoeuvre forward this long...
MPC_SAMPLES = (0.3, 0.6, 0.9, 1.2)   # ...scoring at these times
MPC_REPLAN_S = 0.3
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
        self.kill_count = 0
        self.narrow: Optional[Tuple[float, float]] = None
        self.narrow_t = -1e9
        self.narrow_key = None
        self.mode = ""
        self.lanes: Dict[Tuple[int, int], int] = {}   # static: open approach lanes per 2 m cell
        self.choke: Optional[Tuple[float, float]] = None
        self.choke_t = -1e9

    def observe(self, obs: dict) -> None:
        """Call before the threat tracker forgets a killed mech: remembers where mechs were."""
        t = float(obs["t"])
        for m in obs.get("mechs") or []:
            if m.get("kind", "mech") == "mech":
                self.last_seen[int(m["id"])] = tuple(m["pos"])
        for e in obs.get("events") or []:
            if e.get("type") == "kill":
                p = self.last_seen.get(int(e.get("target", -1)))
                self.kill_count += 1
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

    def _open_lanes(self, xy, h: float) -> int:
        """How many of 16 directions a bot 50 m out could shoot this spot from (map only, cached)."""
        key = (int(round(xy[0] / 2.0)), int(round(xy[1] / 2.0)))
        if key not in self.lanes:
            z = self.core.floor_z(xy[0], xy[1])
            eye = float(self.cfg["mech"].get("eye_height", 8.0))
            n = 0
            for k in range(16):
                a = 2 * math.pi * k / 16
                ex, ey = xy[0] + CHOKE_LANE_M * math.cos(a), xy[1] + CHOKE_LANE_M * math.sin(a)
                if self.core.shot_los((ex, ey, self.core.floor_z(ex, ey) + eye), (xy[0], xy[1], z + h * 0.5)) >= 1.0:
                    n += 1
            self.lanes[key] = n
        return self.lanes[key]

    def _choke_goal(self, me: dict, pos, hunter_pos, zone, walk: float, t: float) -> Optional[Tuple[float, float]]:
        if self.choke is not None and t - self.choke_t < CHOKE_HOLD_S:
            self.mode = "choke hold"
            return self.choke
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        eyes = [(p[0], p[1], self.core.floor_z(p[0], p[1]) + eye) for p in hunter_pos]
        best, best_s = None, math.inf
        for rad in CHOKE_RINGS:
            for k in range(1 if rad == 0 else 8):
                a = 2 * math.pi * k / 8
                q = (pos[0], pos[1]) if rad == 0 else \
                    self.core.nearest_walkable(pos[0] + rad * math.cos(a), pos[1] + rad * math.sin(a), r, False)
                if q is None or math.dist(q, pos[:2]) > rad + 3.0:
                    continue
                if rad > 0 and not self.core.segment_walkable((pos[0], pos[1]), q, r * 0.9):
                    continue
                if not self._zone_ok(zone, (q[0], q[1], 0.0), pos, walk):
                    continue
                s = 3.0 * self._exposure(q, eyes, h) + 0.5 * self._open_lanes(q, h) + 0.05 * math.dist(q, pos[:2])
                if s < best_s:
                    best, best_s = q, s
        if best is None:
            return None
        self.choke, self.choke_t = (best[0], best[1]), t
        self.mode = f"choke {best_s:.1f}"
        return self.choke

    _threats = None  # set by Bot (mpc.tier needs the aggro order)

    def _force_choke(self, me: dict, pos, h: float, limit: int, zone, walk: float, t: float):
        if getattr(self, "_fc_t", -1e9) > t - 2.0 and getattr(self, "_fc_goal", None) is not None:
            return self._fc_goal
        r = float((me.get("stats") or {}).get("radius", 2.5))
        best, best_s = None, math.inf
        far = float(tuning.get("narrow.force_m"))
        rings = [x for x in (10.0, 20.0, 30.0, 40.0, 55.0, 70.0, 85.0, 100.0) if x <= far]
        for rad in rings:
            for k in range(16):
                a = 2 * math.pi * k / 16
                q = self.core.nearest_walkable(pos[0] + rad * math.cos(a), pos[1] + rad * math.sin(a), r, True)
                if q is None or math.dist(q, pos[:2]) > rad + 4.0:
                    continue
                lanes = self._open_lanes(q, h)
                if lanes > limit or not self._zone_ok(zone, (q[0], q[1], 0.0), pos, walk):
                    continue
                s = math.dist(q, pos[:2]) + 4.0 * lanes
                if s < best_s:
                    best, best_s = (q[0], q[1]), s
            if best is not None:
                break  # nearest ring with a real choke
        self._fc_t, self._fc_goal = t, best
        return best

    def narrow_spot(self, me: dict, zone, walk: float, t: float) -> Optional[Tuple[float, float]]:
        """fight.narrow: after N kills, a base with the fewest open approach lanes within 60 m (inside the
        zone), so bots must come through few lanes instead of surrounding us. Re-picked every 8 s or
        when the next zone circle changes."""
        if self.core is None or self.kill_count < int(tuning.get("narrow.after_kills")):
            return None
        nxt = zone.next_circle() if zone is not None and getattr(zone, "known", False) else None
        key = (round(nxt[0]), round(nxt[1]), round(nxt[2])) if nxt else None
        if self.narrow is not None and t - self.narrow_t < 8.0 and key == self.narrow_key:
            return self.narrow
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        pos = me["pos"]
        best, best_s = None, math.inf
        reach = float(tuning.get("narrow.radius"))
        for rad in [x for x in (0.0, 10.0, 20.0, 35.0, 50.0, 65.0, 80.0, 95.0) if x <= reach]:
            for k in range(1 if rad == 0 else 16):
                a = 2 * math.pi * k / 16
                q = (pos[0], pos[1]) if rad == 0 else \
                    self.core.nearest_walkable(pos[0] + rad * math.cos(a), pos[1] + rad * math.sin(a), r, True)
                if q is None or math.dist(q, pos[:2]) > rad + 4.0:
                    continue
                if nxt is not None and math.hypot(q[0] - nxt[0], q[1] - nxt[1]) > nxt[2] - 15.0:
                    continue  # stay well inside the next circle
                if not self._zone_ok(zone, (q[0], q[1], 0.0), pos, walk):
                    continue
                lanes = self._open_lanes(q, h)
                max_lanes = tuning.get("narrow.max_lanes")
                if max_lanes is not None and lanes > int(max_lanes):
                    continue  # not a real choke (e.g. an open plaza): don't hold it
                s = lanes + 0.03 * math.dist(q, pos[:2])
                if s < best_s:
                    best, best_s = (q[0], q[1]), s
        self.narrow, self.narrow_t, self.narrow_key = best, t, key
        return best

    def _mpc_goal(self, me: dict, pos, hunters, tt: float, zone, walk: float, t: float, retreating: bool = False):
        ck = ("_mpc_t_r", "_mpc_goal_r") if (retreating and tuning.get("mpc.split_cache")) else ("_mpc_t", "_mpc_goal_xy")
        if getattr(self, ck[0], -1e9) > t - MPC_REPLAN_S and getattr(self, ck[1], None) is not None:
            self.mode = "mpc hold"
            return getattr(self, ck[1])
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        mh = float(st.get("muzzle_height", 7.0))
        weapons = [w.get("kind") for w in (me.get("weapons") or []) if w]
        have_light = "lightning" in weapons
        light_rng = float(self.cfg["weapons"]["lightning"].get("range", 45.0))
        speed = float(st.get("walk_speed", walk))
        enemies = []
        for hh in hunters:
            p = hh.pos_at(tt)
            v = getattr(hh, "vel", [0.0, 0.0, 0.0])
            ws = list(getattr(hh, "weapons", []) or ["gun"])
            dps = 100.0 + (240.0 if "lightning" in ws else 0.0) + (130.0 if "laser" in ws else 0.0)
            mult = 1.0
            if tuning.get("mpc.tier") and self._threats is not None:
                mult = self._threats.tier_mult(hh.id)
            enemies.append((p, v, dps, "lightning" in ws, mult))
        nearest = min(enemies, key=lambda e: math.dist(e[0][:2], pos[:2]))
        chase = bool(tuning.get("mpc.chase"))
        w_taken = float(tuning.get("mpc.w_taken")) if not retreating else float(tuning.get("mpc.w_taken_retreat"))
        w_dealt = 1.0 if not retreating else 0.3

        def score_path(end):
            total = 0.0
            for s_t in MPC_SAMPLES:
                f = s_t / MPC_HORIZON_S
                q = (pos[0] + (end[0] - pos[0]) * f, pos[1] + (end[1] - pos[1]) * f)
                z = self.core.floor_z(q[0], q[1])
                taken = dealt = 0.0
                for (p, v, dps, light, mult) in enemies:
                    if chase:
                        dx, dy = q[0] - p[0], q[1] - p[1]
                        dn = math.hypot(dx, dy)
                        step = min(max(0.0, dn - 20.0), speed * s_t)  # close in, stop ~20 m out
                        ep = (p[0] + dx / dn * step, p[1] + dy / dn * step) if dn > 1e-6 else (p[0], p[1])
                    else:
                        ep = (p[0] + v[0] * s_t, p[1] + v[1] * s_t)
                    ez = self.core.floor_z(ep[0], ep[1])
                    d = math.dist(ep, q)
                    sees = self.core.shot_los((ep[0], ep[1], ez + eye), (q[0], q[1], z + h * 0.5)) >= 1.0
                    if sees:
                        taken += mult * (100.0 + (240.0 if (light and d <= light_rng) else 0.0)
                                         + (dps - 100.0 - (240.0 if light else 0.0))) * (0.9 if d <= 60 else 0.6)
                        dealt += 100.0 * (0.9 if d <= 60 else 0.6) + (240.0 if (have_light and d <= light_rng) else 0.0)
                total += w_dealt * dealt - w_taken * taken
            return total

        best, best_s = None, -math.inf
        cands = [(pos[0], pos[1])]
        reach = speed * MPC_HORIZON_S
        if getattr(self, "_force_hold", False):
            reach = 6.0  # narrow.force: holding a real choke
        if tuning.get("narrow.hold") and self.narrow is not None and math.dist(self.narrow, pos[:2]) <= 10.0:
            reach = 6.0  # at the narrow base: hold the gully, let them come through its lanes
        for k in range(12):
            a = 2 * math.pi * k / 12
            q = self.core.nearest_walkable(pos[0] + reach * math.cos(a), pos[1] + reach * math.sin(a), r, False)
            if q is None or math.dist(q, pos[:2]) > reach + 3.0:
                continue
            if not self.core.segment_walkable((pos[0], pos[1]), q, r * 0.9):
                continue
            if not self._zone_ok(zone, (q[0], q[1], 0.0), pos, walk):
                continue
            cands.append((q[0], q[1]))
        w_lanes = float(tuning.get("mpc.w_lanes"))
        for c in cands:
            s = score_path(c) - 0.02 * math.dist(c, nearest[0][:2])
            if w_lanes:
                s -= w_lanes * self._open_lanes(c, h)  # prefer ending in a gully: fewer open approach lanes
            if s > best_s:
                best, best_s = c, s
        setattr(self, ck[0], t)
        setattr(self, ck[1], best)
        self.mode = f"mpc {best_s:.0f}"
        return best

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

        if tuning.get("farm.cap"):
            from farm import at_cap
            if at_cap(self.cfg, me):
                self._skip_loot = True
            else:
                self._skip_loot = False
        else:
            self._skip_loot = False
        # 1) loot the kill's cubes (with pacing.loot_more: every recent kill, see loot_goal); with
        # farm.bank, cash in a remembered cube when hurt, and leave cubes on the floor at high HP
        if tuning.get("farm.bank"):
            if hp < 0.70 and getattr(self, "farmer", None) is not None:
                g = self.farmer.bank_goal(me, zone, walk)
                if g is not None:
                    self.mode = self.farmer.mode
                    return g
        if self._skip_loot or (tuning.get("farm.bank") and hp >= 0.95):
            pass  # at the cube cap (farm.cap) or banking: don't walk to kill cubes
        elif tuning.get("pacing.loot_more"):
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

        # 1b) narrow.force: with 2+ known mechs within 150 m and an open spot under us, go to the nearest
        # real choke (<= narrow.max_lanes open lanes) within 100 m; once there, MPC only adjusts within 6 m
        self._force_hold = False
        if tuning.get("narrow.force") and self.core is not None:
            near = [tr for tr in getattr(threats, "tracks", {}).values()
                    if math.dist(tr.pos_at(tt)[:2], pos[:2]) <= 150.0]
            pre = bool(tuning.get("narrow.force_pre"))
            closest = min((math.dist(tr.pos_at(tt)[:2], pos[:2]) for tr in near), default=1e9)
            quiet = threats is None or not hasattr(threats, "damage_taken") or threats.damage_taken(3.0) <= 0.0
            if len(near) >= 2 and (not pre or (closest > 50.0 and quiet)):
                st = me.get("stats") or {}
                h = float(st.get("height", 9.0))
                limit = int(tuning.get("narrow.max_lanes") or 6)
                if self._open_lanes((pos[0], pos[1]), h) <= limit:
                    self._force_hold = True
                else:
                    g = self._force_choke(me, pos, h, limit, zone, walk, t)
                    if g is not None:
                        self.mode = "force choke"
                        return g

        # 2) press a lone hunter into lightning range (we hold lightning, healthy, energy to spare)
        if tuning.get("fight.press") and len(fresh) == 1 and hp >= PRESS_MIN_HP and \
                float(me.get("energy", 0.0)) >= PRESS_MIN_ENERGY and \
                any(w and w.get("kind") == "lightning" for w in (me.get("weapons") or [])):
            h = fresh[0]
            hp_ = h.pos_at(tt)
            d = math.dist(hp_[:2], pos[:2])
            if max(PRESS_FROM_M, float(tuning.get("press.to_m")) + 5.0) < d <= PRESS_MAX_M:
                ux, uy = (pos[0] - hp_[0]) / d, (pos[1] - hp_[1]) / d
                goal = (hp_[0] + ux * float(tuning.get("press.to_m")), hp_[1] + uy * float(tuning.get("press.to_m")))
                if self.core is not None:
                    r = float((me.get("stats") or {}).get("radius", 2.5))
                    q = self.core.nearest_walkable(goal[0], goal[1], r, bool(tuning.get("nav.ground_goals")))
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
            tr = None
            if len(tracks) == 1:
                tr = tracks[0]
            elif tracks and tuning.get("hunt.local"):
                # isolated, not alone: the nearest mech, with every other known one far behind it
                ds = sorted((math.dist(x.pos_at(tt)[:2], pos[:2]), i) for i, x in enumerate(tracks))
                d0 = ds[0][0]
                if all(d >= max(100.0, d0 + 60.0) for d, _ in ds[1:]):
                    tr = tracks[ds[0][1]]
            if tr is not None:
                p = tr.pos_at(tt)
                d = math.dist(p[:2], pos[:2])
                if PRESS_FROM_M < d <= float(tuning.get("hunt.max_m")):
                    ux, uy = (pos[0] - p[0]) / d, (pos[1] - p[1]) / d
                    goal = (p[0] + ux * PRESS_TO_M, p[1] + uy * PRESS_TO_M)
                    if self.core is not None:
                        r = float((me.get("stats") or {}).get("radius", 2.5))
                        q = self.core.nearest_walkable(goal[0], goal[1], r, bool(tuning.get("nav.ground_goals")))
                        goal = (q[0], q[1]) if q is not None else None
                    if goal is not None and self._zone_ok(zone, goal, pos, walk):
                        self.mode = f"hunt {tr.id} {d:.0f}m"
                        return goal

        # 4) chokepoint: with 2+ known hunters around, fight from the nearby spot with the fewest open
        # approach lanes (and the fewest current hunters able to shoot it), so they come one lane at a time
        if tuning.get("fight.choke") and self.core is not None and hp >= 0.25:
            near = [tr.pos_at(tt) for tr in getattr(threats, "tracks", {}).values()
                    if math.dist(tr.pos_at(tt)[:2], pos[:2]) <= CHOKE_RANGE_M]
            if len(near) >= 2:
                g = self._choke_goal(me, pos, near, zone, walk, t)
                if g is not None:
                    return g

        # 4a) MPC: with 2+ hunters close, roll 12 manoeuvres + "stay" forward 1.2 s and take the one with
        # the best predicted damage dealt minus damage taken (enemies advance along their velocity)
        if tuning.get("fight.mpc") and len(fresh) >= int(tuning.get("mpc.min_hunters")) and self.core is not None:
            g = self._mpc_goal(me, pos, fresh, tt, zone, walk, t)
            if g is not None:
                return g

        # 4b) line-of-sight steering: with 2+ hunters able to shoot us, step to the nearby spot where the
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
                q = self.core.nearest_walkable(goal[0], goal[1], r, bool(tuning.get("nav.ground_goals")))
                if q is None or math.dist(q, goal) > 8.0:
                    return None  # wall behind us: keep the normal plan
                goal = (q[0], q[1])
            if not self._zone_ok(zone, goal, pos, walk):
                return None
            self.mode = f"split {len(fresh)}"
            return goal
        return None
