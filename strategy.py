"""Strategy: which behaviour state we are in and where it wants us to go.

E1 (docs/implementation_plan.md, Phase 4): ROTATE (Phase 2/3 behaviour) and RETREAT heal cycles.
Later experiments add ENGAGE / FARM / HOLD / BURN states.

RETREAT: get to a walkable spot inside the zone that no known hunter can shoot, stop firing
(regen needs 5 s with no damage taken *or dealt*), and stay until healed.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import tuning

ROTATE, RETREAT, ROOF, BURN = "rotate", "retreat", "roof", "burn"

# thresholds and which triggers are active come from tuning.py (retreat.*)
HEAVY_DAMAGE_FRAC = 0.20     # ...or this much of max HP lost in the last 2 s
HEAVY_DAMAGE_HP = 0.85       #    while below this HP fraction
MANY_HUNTERS = 3             # ...or this many hunters within MANY_RANGE_M
MANY_RANGE_M = 100.0
MIN_STATE_S = 1.5            # hysteresis
LULL_CLEAR_M = 100.0         # heal in lulls (heal.lull_hp): no hunter this close...
LULL_SEEN_S = 5.0            # ...seen this recently
LULL_EXIT_HP = 0.95          # heal up to this, unless a hunter shows up
HIDE_REFRESH_S = 1.0
HIDE_RADII = (6.0, 10.0, 15.0, 20.0, 28.0, 36.0, 46.0)
HIDE_DIRS = 16
MAX_HIDE_THREATS = 4
ZONE_MARGIN_M = 5.0


class Decision:
    __slots__ = ("state", "goal", "retreat", "boost", "why", "roofs")

    def __init__(self, state: str, goal=None, retreat: bool = False, boost: bool = False, why: str = "",
                 roofs: bool = False):
        self.state, self.goal, self.retreat, self.boost, self.why = state, goal, retreat, boost, why
        self.roofs = roofs  # navigation may jump onto building roofs


class Strategy:
    def __init__(self, cfg: dict, core, zone, threats, roofs=None):
        self.cfg = cfg
        self.roofs = roofs
        self.roof = None
        self.core = core
        self.zone = zone
        self.threats = threats
        self.state = ROTATE
        self.state_t = -1e9
        self.hide: Optional[Tuple[float, float]] = None
        self.hide_t = -1e9

    # ------------------------------------------------------------ hiding spots

    def _eyes(self, hunters) -> List[List[float]]:
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        t = self.threats.t
        hs = sorted(hunters, key=lambda h: h.t_hit, reverse=True)[:MAX_HIDE_THREATS]
        out = []
        for h in hs:
            p = h.pos_at(t)
            out.append([p[0], p[1], p[2] + eye])
        return out

    def hidden(self, xy: Sequence[float], eyes: List[List[float]], height: float) -> bool:
        """No hunter has a shot at our chest or our top from where it is."""
        if self.core is None:
            return False
        z = self.core.floor_z(xy[0], xy[1])
        for e in eyes:
            for hz in (height * 0.5, height):
                if self.core.shot_los(e, (xy[0], xy[1], z + hz)) >= 1.0:
                    return False
        return True

    def find_hide(self, me: dict, hunters) -> Optional[Tuple[float, float]]:
        """Nearest walkable spot inside the zone hidden from every known hunter, preferring spots
        away from them. Our current spot counts if it's already hidden."""
        if self.core is None:
            return None
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        h = float(st.get("height", 9.0))
        x, y, _ = me["pos"]
        eyes = self._eyes(hunters)
        if not eyes:
            # nobody can see us: where we stand is hidden; stay and regenerate (retreat.fresh_hide)
            return (x, y) if tuning.get("retreat.fresh_hide") else None
        if self.hidden((x, y), eyes, h):
            return (x, y)
        cur = self.zone.current() if self.zone.known else None
        # retreat.away: only spots on the far side from the hunters' centre (pull the pack behind us,
        # don't run into a pincer); falls back to any hidden spot if none is found
        away = None
        if tuning.get("retreat.away"):
            t = self.threats.t
            near = [hh.pos_at(t) for hh in hunters if math.dist(hh.pos_at(t)[:2], (x, y)) <= 100.0]
            if near:
                cx = sum(p[0] for p in near) / len(near)
                cy = sum(p[1] for p in near) / len(near)
                if math.hypot(x - cx, y - cy) > 1e-6:
                    away = (x - cx, y - cy)
        for side in ((away, None) if away is not None else (None,)):
            best = self._hide_search(x, y, r, h, eyes, cur, side)
            if best is not None:
                return best
        if tuning.get("retreat.fallback"):
            return self._cover_fallback(x, y, r, h, eyes, cur, away)
        return None

    def _lanes(self, xy, h: float) -> int:
        """How many of 16 directions a bot 50 m out could shoot this spot from (map only, cached)."""
        if not hasattr(self, "_lane_cache"):
            self._lane_cache = {}
        key = (int(round(xy[0] / 2.0)), int(round(xy[1] / 2.0)))
        if key not in self._lane_cache:
            z = self.core.floor_z(xy[0], xy[1])
            eye = float(self.cfg["mech"].get("eye_height", 8.0))
            n = 0
            for k in range(16):
                a = 2 * math.pi * k / 16
                ex, ey = xy[0] + 50.0 * math.cos(a), xy[1] + 50.0 * math.sin(a)
                if self.core.shot_los((ex, ey, self.core.floor_z(ex, ey) + eye), (xy[0], xy[1], z + h * 0.5)) >= 1.0:
                    n += 1
            self._lane_cache[key] = n
        return self._lane_cache[key]

    def _cover_fallback(self, x, y, r, h, eyes, cur, away) -> Optional[Tuple[float, float]]:
        """No fully hidden spot: the best partial cover within reach (fewest hunters able to shoot it,
        fewest open approach lanes), preferring the far side from the hunters. Better than standing."""
        best, best_s = None, math.inf
        for rad in (8.0, 16.0, 26.0, 38.0):
            for k in range(HIDE_DIRS):
                a = 2 * math.pi * k / HIDE_DIRS
                q = self.core.nearest_walkable(x + rad * math.cos(a), y + rad * math.sin(a), r, bool(tuning.get("nav.ground_goals")))
                if q is None or math.dist(q, (x, y)) > rad + 4:
                    continue
                if cur is not None and self.zone.depth(cur, q) < ZONE_MARGIN_M:
                    continue
                z = self.core.floor_z(q[0], q[1])
                seen = sum(1 for e in eyes if self.core.shot_los(e, (q[0], q[1], z + h * 0.5)) >= 1.0)
                s = 3.0 * seen + 0.5 * self._lanes(q, h) + 0.04 * math.dist(q, (x, y))
                if away is not None and (q[0] - x) * away[0] + (q[1] - y) * away[1] < 0:
                    s += 4.0  # toward the hunters: allowed, but only if clearly better
                if s < best_s:
                    best, best_s = q, s
        here_z = self.core.floor_z(x, y)
        here = 3.0 * sum(1 for e in eyes if self.core.shot_los(e, (x, y, here_z + h * 0.5)) >= 1.0) + \
            0.5 * self._lanes((x, y), h)
        return best if best is not None and best_s < here else None

    def _hide_search(self, x, y, r, h, eyes, cur, away) -> Optional[Tuple[float, float]]:
        best, best_s = None, math.inf
        for rad in HIDE_RADII:
            for k in range(HIDE_DIRS):
                a = 2 * math.pi * k / HIDE_DIRS
                q = self.core.nearest_walkable(x + rad * math.cos(a), y + rad * math.sin(a), r, bool(tuning.get("nav.ground_goals")))
                if q is None or math.dist(q, (x, y)) > rad + 4:
                    continue
                if cur is not None and self.zone.depth(cur, q) < ZONE_MARGIN_M:
                    continue
                if away is not None and (q[0] - x) * away[0] + (q[1] - y) * away[1] < 0:
                    continue  # toward the hunters' side
                if not self.hidden(q, eyes, h):
                    continue
                near = min(math.dist(q, e[:2]) for e in eyes)
                s = math.dist(q, (x, y)) + 30.0 / max(5.0, near) * 10.0
                if s < best_s:
                    best, best_s = q, s
            if best is not None and rad >= 15.0:
                break  # good enough: don't search farther rings once something close is found
        return best

    # ------------------------------------------------------------ state machine

    def _set(self, state: str, t: float) -> None:
        if state != self.state:
            self.state, self.state_t = state, t
            self.hide, self.hide_t = None, -1e9

    def update(self, obs: dict, zone_urgent: bool) -> Decision:
        me = obs["self"]
        t = float(obs["t"])
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        pos = me["pos"]
        hunters = self.threats.hunters(pos)
        # Check burn mode (Stage E, E4)
        if tuning.get("burn.enabled") and self.zone.known:
            nxt_r = self.zone.next_radius
            cur_r = self.zone.radius
            dps = self.zone.dps
            burn_thresh = float(tuning.get("burn.radius"))
            is_burn = (nxt_r <= burn_thresh) or (cur_r <= 70.0 and dps >= 160.0) or (cur_r <= burn_thresh)
            if is_burn:
                self._set(BURN, t)
                cx, cy = self.zone.next_center
                st = me.get("stats") or {}
                r = float(st.get("radius", 2.5))
                target = (cx, cy)
                if self.core is not None:
                    target = self.core.nearest_walkable(cx, cy, r, True) or (cx, cy)
                d_to_center = math.hypot(pos[0] - target[0], pos[1] - target[1])
                goal = (pos[0], pos[1]) if d_to_center <= 3.0 else target
                boost = d_to_center > 15.0 and float(me.get("energy", 0.0)) > 30.0
                return Decision(BURN, goal=goal, retreat=False, boost=boost,
                                why=f"burn r{nxt_r:.0f}m d{d_to_center:.1f}m")
        if self.state == BURN:
            self._set(ROTATE, t)
        roof_after = tuning.get("roof.after")
        if tuning.get("roof.enabled") and self.roofs is not None and not zone_urgent and \
                (roof_after is None or t >= float(roof_after)):
            d = self.roof_decision(me, hp, hunters)
            if d is not None:
                self._set(ROOF, t)
                return d
        if self.state == ROOF:
            self._set(ROTATE, t)  # no usable roof (or the zone comes first): back to the ground states
        if not tuning.get("retreat.enabled"):
            self._set(ROTATE, t)
            return Decision(ROTATE, why="rotate")
        many = sum(1 for hh in hunters if math.dist(hh.pos_at(t)[:2], pos[:2]) <= MANY_RANGE_M) >= MANY_HUNTERS
        # S2: heal in lulls: below heal.lull_hp with no hunter around, stop and regenerate
        lull_hp = tuning.get("heal.lull_hp")
        quiet = not any(math.dist(tr.pos_at(t)[:2], pos[:2]) <= LULL_CLEAR_M and t - tr.t_seen < LULL_SEEN_S
                        for tr in self.threats.tracks.values())
        if lull_hp is not None and self.state == ROTATE and quiet and hp < float(lull_hp) and \
                t - self.state_t >= MIN_STATE_S:
            self.lull = True
            self._set(RETREAT, t)
        if getattr(self, "lull", False):
            if self.state != RETREAT or hp >= LULL_EXIT_HP or not quiet:
                self.lull = False
                if self.state == RETREAT and hp >= tuning.get("retreat.hp_exit"):
                    self._set(ROTATE, t)  # healed enough, or a hunter showed up: back to normal play
                elif self.state == RETREAT and not quiet and hp >= tuning.get("retreat.hp_enter"):
                    self._set(ROTATE, t)  # a hunter arrived while we were only topping up: fight
            else:
                hide = self.hide if self.hide is not None else (pos[0], pos[1])
                return Decision(RETREAT, goal=hide, retreat=False, why=f"heal lull hp {hp:.0%}")
        heavy = self.threats.damage_taken(2.0) > HEAVY_DAMAGE_FRAC * float(me.get("max_hp", 1400)) and hp < HEAVY_DAMAGE_HP
        many = many and tuning.get("retreat.on_hunters")
        # S1: back off earlier when two bots converge (retreat.many_n hunters within 100 m, below many_hp)
        many_n = tuning.get("retreat.many_n")
        if many_n is not None and hp < float(tuning.get("retreat.many_hp")) and \
                sum(1 for hh in hunters if math.dist(hh.pos_at(t)[:2], pos[:2]) <= MANY_RANGE_M) >= int(many_n):
            many = True
        # retreat.scaled: retreat earlier the more hunters are close (2 within 75 m: 50%, 3+: 65%)
        if tuning.get("retreat.scaled"):
            n75 = sum(1 for hh in hunters if math.dist(hh.pos_at(t)[:2], pos[:2]) <= 75.0)
            if (n75 >= 3 and hp < 0.65) or (n75 == 2 and hp < 0.50):
                many = True
        heavy = heavy and tuning.get("retreat.on_heavy_damage")
        want_retreat = hp < tuning.get("retreat.hp_enter") or many or heavy
        healed = hp >= tuning.get("retreat.hp_exit") and not many
        hold_fire = bool(tuning.get("retreat.hold_fire"))

        held = t - self.state_t < MIN_STATE_S
        if self.state == ROTATE and want_retreat and not held:
            self._set(RETREAT, t)
        elif self.state == RETREAT and healed and not held:
            self._set(ROTATE, t)

        if self.state == RETREAT and not zone_urgent and tuning.get("retreat.roof") and self.roofs is not None                 and float(me.get("energy", 0.0)) >= 45.0:
            # rooftop reset: retreat onto a climbable roof within 45 m and hold its middle (ground bots
            # close below lose the line of fire)
            st = me.get("stats") or {}
            v0 = float(st.get("jump_speed", 11.0))
            cap = v0 * v0 / (2 * float(st.get("gravity", 22.0))) +                 0.75 * 85.0 * float(st.get("max_rise_speed", 10.0)) / max(1e-6, float(st.get("jet_drain", 15.0)))
            roof = self.roofs.choose(self.zone, pos, cap)
            if roof is not None and math.dist(roof.core, pos[:2]) <= 45.0:
                return Decision(RETREAT, goal=roof.core, retreat=hold_fire, roofs=True,
                                why=f"retreat roof {roof.height:.0f}m")
        if self.state == RETREAT and not zone_urgent:
            if self.hide is None or t - self.hide_t >= HIDE_REFRESH_S:
                spot = self.find_hide(me, hunters)
                if tuning.get("retreat.fresh_hide"):
                    # never keep a spot chosen against hunters that are gone: only if still hidden now
                    if spot is None and self.hide is not None:
                        eyes = self._eyes(hunters)
                        h_ = float((me.get("stats") or {}).get("height", 9.0))
                        if eyes and not self.hidden(self.hide, eyes, h_):
                            self.hide = None
                    self.hide, self.hide_t = (spot or self.hide), t
                else:
                    self.hide, self.hide_t = (spot or self.hide), t
            goal = self.hide if self.hide is not None else (pos[0], pos[1])
            if self.hide is None and tuning.get("retreat.flee") and hunters and self.core is not None                     and self.threats.damage_taken(2.0) > 0.0:
                # nowhere hidden and still being hit: break contact, ~30 m directly away from the attackers
                cx = sum(hh.pos_at(t)[0] for hh in hunters) / len(hunters)
                cy = sum(hh.pos_at(t)[1] for hh in hunters) / len(hunters)
                dx, dy = pos[0] - cx, pos[1] - cy
                dn = math.hypot(dx, dy)
                if dn > 1e-6:
                    r_ = float((me.get("stats") or {}).get("radius", 2.5))
                    cur_c = self.zone.current() if self.zone.known else None
                    for ang in (0.0, 0.5, -0.5, 1.0, -1.0):
                        ca, sa = math.cos(ang), math.sin(ang)
                        ux, uy = (dx * ca - dy * sa) / dn, (dx * sa + dy * ca) / dn
                        q = self.core.nearest_walkable(pos[0] + 30.0 * ux, pos[1] + 30.0 * uy, r_, True)
                        if q is None or (cur_c is not None and self.zone.depth(cur_c, q) < ZONE_MARGIN_M):
                            continue
                        goal = (q[0], q[1])
                        break
            escaping = any(math.dist(hh.pos_at(t)[:2], pos[:2]) < 60.0 for hh in hunters) and \
                float(me.get("energy", 0.0)) > 30.0
            return Decision(RETREAT, goal=goal, retreat=hold_fire, boost=escaping,
                            why=f"retreat hp {hp:.0%} h{len(hunters)}")
        if self.state == RETREAT:
            # the zone wins: heal where we can, but get inside first (no regen outside the zone)
            return Decision(RETREAT, goal=None, retreat=hold_fire, why="retreat (zone first)")
        return Decision(ROTATE, why="rotate")

    # ------------------------------------------------------------ rooftops

    def roof_decision(self, me: dict, hp: float, hunters) -> Optional[Decision]:
        """Climb a usable roof and hold its middle; step to the edge toward the nearest hunter to
        shoot when healthy. None when there is no usable roof (fall back to the other states)."""
        st = me.get("stats") or {}
        v0 = float(st.get("jump_speed", 11.0))
        cap = v0 * v0 / (2 * float(st.get("gravity", 22.0))) + \
            0.75 * 85.0 * float(st.get("max_rise_speed", 10.0)) / max(1e-6, float(st.get("jet_drain", 15.0)))
        if self.roof is None or not self.roofs.usable(self.roof, self.zone, cap):
            self.roof = self.roofs.choose(self.zone, me["pos"], cap)
        if self.roof is None:
            return None
        roof = self.roof
        on = self.roofs.roof_at(me["pos"])
        if on is not None and on.id == roof.id:
            t = self.threats.t
            near = min(hunters, key=lambda h: math.dist(h.pos_at(t)[:2], me["pos"][:2]), default=None)
            if near is not None and hp >= tuning.get("roof.peek_hp"):
                return Decision(ROOF, goal=self.roofs.edge_toward(roof, near.pos_at(t)), roofs=True,
                                why=f"roof peek {near.id}")
            return Decision(ROOF, goal=roof.core, roofs=True, why="roof hold")
        return Decision(ROOF, goal=roof.core, roofs=True, why=f"roof climb {roof.height:.0f}m")
