"""Strategy: which behaviour state we are in and where it wants us to go.

E1 (docs/implementation_plan.md, Phase 4): ROTATE (Phase 2/3 behaviour) and RETREAT heal cycles.
Later experiments add ENGAGE / FARM / HOLD / BURN states.

RETREAT: get to a walkable spot inside the zone that no known hunter can shoot, stop firing
(regen needs 5 s with no damage taken *or dealt*), and stay until healed.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

ROTATE, RETREAT = "rotate", "retreat"

RETREAT_HP = 0.55            # enter below this HP fraction
RETREAT_DONE_HP = 0.90       # leave once healed to this
HEAVY_DAMAGE_FRAC = 0.20     # ...or this much of max HP lost in the last 2 s
HEAVY_DAMAGE_HP = 0.85       #    while below this HP fraction
MANY_HUNTERS = 3             # ...or this many hunters within MANY_RANGE_M
MANY_RANGE_M = 100.0
MIN_STATE_S = 1.5            # hysteresis
HIDE_REFRESH_S = 1.0
HIDE_RADII = (6.0, 10.0, 15.0, 20.0, 28.0, 36.0, 46.0)
HIDE_DIRS = 16
MAX_HIDE_THREATS = 4
ZONE_MARGIN_M = 5.0


class Decision:
    __slots__ = ("state", "goal", "retreat", "boost", "why")

    def __init__(self, state: str, goal=None, retreat: bool = False, boost: bool = False, why: str = ""):
        self.state, self.goal, self.retreat, self.boost, self.why = state, goal, retreat, boost, why


class Strategy:
    def __init__(self, cfg: dict, core, zone, threats):
        self.cfg = cfg
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
            return None
        if self.hidden((x, y), eyes, h):
            return (x, y)
        cur = self.zone.current() if self.zone.known else None
        best, best_s = None, math.inf
        for rad in HIDE_RADII:
            for k in range(HIDE_DIRS):
                a = 2 * math.pi * k / HIDE_DIRS
                q = self.core.nearest_walkable(x + rad * math.cos(a), y + rad * math.sin(a), r, False)
                if q is None or math.dist(q, (x, y)) > rad + 4:
                    continue
                if cur is not None and self.zone.depth(cur, q) < ZONE_MARGIN_M:
                    continue
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
        many = sum(1 for hh in hunters if math.dist(hh.pos_at(t)[:2], pos[:2]) <= MANY_RANGE_M) >= MANY_HUNTERS
        heavy = self.threats.damage_taken(2.0) > HEAVY_DAMAGE_FRAC * float(me.get("max_hp", 1400)) and hp < HEAVY_DAMAGE_HP
        want_retreat = hp < RETREAT_HP or many or heavy
        healed = hp >= RETREAT_DONE_HP and not many

        held = t - self.state_t < MIN_STATE_S
        if self.state == ROTATE and want_retreat and not held:
            self._set(RETREAT, t)
        elif self.state == RETREAT and healed and not held:
            self._set(ROTATE, t)

        if self.state == RETREAT and not zone_urgent:
            if self.hide is None or t - self.hide_t >= HIDE_REFRESH_S:
                spot = self.find_hide(me, hunters)
                self.hide, self.hide_t = (spot or self.hide), t
            goal = self.hide if self.hide is not None else (pos[0], pos[1])
            escaping = any(math.dist(hh.pos_at(t)[:2], pos[:2]) < 60.0 for hh in hunters) and \
                float(me.get("energy", 0.0)) > 30.0
            return Decision(RETREAT, goal=goal, retreat=True, boost=escaping,
                            why=f"retreat hp {hp:.0%} h{len(hunters)}")
        if self.state == RETREAT:
            # the zone wins: heal where we can, but get inside first (no regen outside the zone)
            return Decision(RETREAT, goal=None, retreat=True, why="retreat (zone first)")
        return Decision(ROTATE, why="rotate")
