"""Movement: path planning, waypoint following, jumps/jets, unsticking and boost policy.

Navigator.step(obs, ...) returns the movement part of an action: {"move", "boost", "jump"}.
Torso aim is not touched here (combat owns it).
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

Waypoint = Tuple[float, float, int]  # x, y, kind: 0 walk, 1 jump, 2 drop off a ledge
JUMP = 1

REPLAN_S = 1.0             # replan at most this often while following a path
GOAL_MOVED_M = 8.0         # ...or when the goal moved this far
WAYPOINT_REACHED_M = 2.5
LOOKAHEAD = 4              # waypoints considered for a straight-line shortcut
REACHED_GOAL_M = 4.0       # a plan "reaches" the goal if it ends this close to the snapped goal
JUMP_APPROACH_M = 10.0     # start a jump when this close (horizontally) to its landing (long edges span up to ~8 m)
CLIMB_TIMEOUT_S = 3.0
LAND_MARGIN_M = 0.6        # feet must clear the landing floor by this much before we stop jetting
STUCK_WINDOW_S = 1.0
STUCK_MIN_MOVE_M = 1.5
FAIL_CACHE_S = 4.0         # don't retry an unreachable goal for this long
WALK_EXPANSIONS = 40000
JUMP_EXPANSIONS = 20000
JUMP_RISE_CAP_M = 20.0
JUMP_PLAN_RANGE_M = 200.0    # plan jumps into an island only from this close; walk to it first
MIN_JUMP_PLAN_RISE_M = 6.0   # ...and only with energy for at least this much climb


class Navigator:
    def __init__(self, core, cfg: dict):
        self.core = core
        m = cfg["mech"]
        self.step_up = float(m.get("step_up", 1.2))
        self.g = float(m.get("gravity", 22.0))
        self.path: List[Waypoint] = []
        self.goal: Optional[Tuple[float, float]] = None
        self.plan_goal: Optional[Tuple[float, float]] = None
        self.plan_t = -1e9
        self.fail_goal: Optional[Tuple[float, float]] = None
        self.fail_t = -1e9
        self.reaches_goal = False
        self.pending_jump_plan = False
        self.allow_roofs = False  # set per decision by the strategy (rooftop play)
        self.jump_route_goal: Optional[Tuple[float, float]] = None  # goal we found a jump route to
        # jump / climb state
        self.climb_target: Optional[Tuple[float, float, float]] = None  # x, y, floor
        self.climb_t0 = 0.0
        # stuck detection
        self.hist: List[Tuple[float, float, float]] = []  # t, x, y while commanding movement
        self.stuck_level = 0
        self.unstick_until = 0.0
        self.unstick_dir = (0.0, 0.0)
        self.last_debug = ""

    # ------------------------------------------------------------ physics helpers

    def jump_rise(self, st: dict, energy: float, reserve: float = 15.0) -> float:
        """How high we can get with a jump plus jets on the energy we have (conservative)."""
        v0 = float(st.get("jump_speed", 11.0))
        rise = v0 * v0 / (2 * float(st.get("gravity", self.g)))
        jet_rate = float(st.get("max_rise_speed", 10.0)) / max(1e-6, float(st.get("jet_drain", 15.0)))  # m per energy
        rise += max(0.0, energy - reserve) * jet_rate * 0.75
        return min(JUMP_RISE_CAP_M, rise)

    # ------------------------------------------------------------ planning

    def set_goal(self, goal: Optional[Sequence[float]]) -> None:
        g = None if goal is None else (float(goal[0]), float(goal[1]))
        if g is None or self.goal is None or math.dist(g, self.goal) > GOAL_MOVED_M:
            self.pending_jump_plan = False
        self.goal = g

    def _plan(self, pos, me: dict, t: float) -> None:
        """Walking plan first; jumps only when walking can't reach the goal. The two searches never
        run in the same decision (each can take ~20 ms when it fails): a failed walk plan keeps
        its partial path and schedules the jump plan for the next decision."""
        self.plan_goal, self.plan_t = self.goal, t
        if self.core is None or self.goal is None:
            self.path, self.reaches_goal = [], False
            return
        st = me.get("stats") or {}
        r, h = float(st.get("radius", 2.5)), float(st.get("height", 9.0))
        if self.fail_goal is not None and math.dist(self.fail_goal, self.goal) < GOAL_MOVED_M and t - self.fail_t < FAIL_CACHE_S:
            self.pending_jump_plan = False
            return  # keep whatever partial path we have
        snapped = self.core.nearest_walkable(self.goal[0], self.goal[1], r, False) or self.goal
        here = self.core.nearest_walkable(pos[0], pos[1], r, False) or pos
        # Walking reaches the goal's area if it's ours or the street (drops lead out of islands to
        # the street, never into them).
        walkable_goal = self.core.component(*snapped) == self.core.component(*here) or self.core.is_ground(*snapped)

        if not self.pending_jump_plan and walkable_goal:
            p = self.core.find_path_ex(pos, self.goal, r, height=h, max_expansions=WALK_EXPANSIONS)
            ok = bool(p) and math.dist(p[-1][:2], snapped) <= REACHED_GOAL_M
            self.path, self.reaches_goal = list(p or []), ok
            self.pending_jump_plan = not ok
            return
        self.pending_jump_plan = False

        # Goal on an island (e.g. the stadium bowl). Jump plans are expensive when they fail, so
        # walk to the street point nearest the goal first, and only plan the jump from close by
        # with enough energy for a real jump (energy recharges while we wait at the staging point).
        rise = self.jump_rise(st, float(me.get("energy", 0.0)))
        committed = self.jump_route_goal is not None and math.dist(self.jump_route_goal, self.goal) < GOAL_MOVED_M
        if not committed and (math.dist(pos, snapped) > JUMP_PLAN_RANGE_M or rise < MIN_JUMP_PLAN_RISE_M):
            stage = self.core.nearest_walkable(self.goal[0], self.goal[1], r, True) or snapped
            p = self.core.find_path_ex(pos, stage, r, height=h, max_expansions=WALK_EXPANSIONS)
            self.path, self.reaches_goal = list(p or []), False
            self.last_debug = "staging"
            return
        p = self.core.find_path_ex(pos, self.goal, r, height=h, max_jump_rise=rise, h_weight=2.0,
                                   allow_roofs=self.allow_roofs, max_expansions=JUMP_EXPANSIONS)
        ok = bool(p) and math.dist(p[-1][:2], snapped) <= REACHED_GOAL_M
        if p and (ok or not self.path or math.dist(p[-1][:2], snapped) < math.dist(self.path[-1][:2], snapped)):
            self.path = list(p)
        self.reaches_goal = ok
        # once a jump route exists, stick with jump plans for this goal (no flip-flopping between
        # "walk to the staging point" and "take the jump route" at the range boundary)
        self.jump_route_goal = self.goal if ok else None
        if not ok:
            self.fail_goal, self.fail_t = self.goal, t

    def path_length(self, pos) -> float:
        pts = [tuple(pos[:2])] + [w[:2] for w in self.path]
        return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))

    # ------------------------------------------------------------ stepping

    def step(self, obs: dict, urgent: bool = False, zone_circle=None, shells: Sequence[Sequence[float]] = ()) -> dict:
        """Movement for this decision: {"move": [dx, dy], "boost": bool, "jump": bool}."""
        me = obs["self"]
        t = float(obs["t"])
        x, y, z = me["pos"]
        pos = (x, y)
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        walk = float(st.get("walk_speed", 11.7))
        energy = float(me.get("energy", 0.0))
        grounded = bool(me.get("grounded", True))
        out = {"move": [0.0, 0.0], "boost": False, "jump": False}

        if self.goal is None:
            self.hist.clear()
            return out
        if (not self.path or self.plan_goal is None or math.dist(self.goal, self.plan_goal) > GOAL_MOVED_M
                or self.pending_jump_plan or (t - self.plan_t >= REPLAN_S and self.climb_target is None)):
            self._plan(pos, me, t)

        # ---- climbing a jump edge: jump, then jet until the feet clear the landing floor
        if self.climb_target is not None:
            cx, cy, cf = self.climb_target
            if z >= cf + LAND_MARGIN_M or t - self.climb_t0 > CLIMB_TIMEOUT_S or (grounded and t - self.climb_t0 > 0.4):
                self.climb_target = None
            else:
                d = math.hypot(cx - x, cy - y) or 1.0
                out["move"] = [(cx - x) / d, (cy - y) / d]
                out["boost"] = (not grounded) and energy > 0.5
                out["jump"] = grounded
                self.last_debug = f"climb {cf - z:+.1f}m"
                return out

        # ---- drop reached waypoints (and ones we've passed)
        while self.path and math.dist(pos, self.path[0][:2]) < WAYPOINT_REACHED_M and \
                (len(self.path) > 1 or math.dist(pos, self.path[0][:2]) < 1.0):
            self.path.pop(0)
        if self.path and len(self.path) > 1:
            a, b = self.path[0][:2], self.path[1][:2]
            # passed waypoint 0: we are closer to 1 than 0 is
            if self.path[1][2] == 0 and math.dist(pos, b) < math.dist(a, b) and self.core is not None \
                    and self.core.segment_walkable(pos, b, r * 0.9):
                self.path.pop(0)

        if not self.path:
            target = self.goal
            if math.dist(pos, target) < 1.0:
                self.hist.clear()
                self.last_debug = "arrived"
                return out
        else:
            # ---- start a jump when close to a jump waypoint
            wp = self.path[0]
            if wp[2] == JUMP and self.core is not None and math.dist(pos, wp[:2]) < JUMP_APPROACH_M:
                cf = self.core.floor_z(wp[0], wp[1])
                if cf > z + self.step_up:
                    self.climb_target = (wp[0], wp[1], cf)
                    self.climb_t0 = t
                    d = math.dist(pos, wp[:2]) or 1.0
                    out["move"] = [(wp[0] - x) / d, (wp[1] - y) / d]
                    out["jump"] = grounded
                    out["boost"] = not grounded
                    self.last_debug = "jump"
                    return out
            # ---- look ahead: farthest of the next few waypoints we can walk to in a straight line
            target = wp[:2]
            if self.core is not None and wp[2] == 0:
                for k in range(1, min(LOOKAHEAD, len(self.path))):
                    if self.path[k][2] != 0:
                        break
                    if self.core.segment_walkable(pos, self.path[k][:2], r * 0.9):
                        target = self.path[k][:2]
                    else:
                        break

        # ---- unstick: if we keep commanding movement but don't move, escalate
        if t < self.unstick_until:
            out["move"] = list(self.unstick_dir)
            out["jump"] = grounded and self.stuck_level == 1
            self.last_debug = f"unstick {self.stuck_level}"
            self._remember(t, x, y)
            return out
        if self._is_stuck(t, x, y):
            self.stuck_level = min(3, self.stuck_level + 1)
            self.hist.clear()
            d = math.dist(pos, target) or 1.0
            fx, fy = (target[0] - x) / d, (target[1] - y) / d
            if self.stuck_level == 1:      # hop: clears small lips the model missed
                self.unstick_dir, self.unstick_until = (fx, fy), t + 0.4
            elif self.stuck_level == 2:    # sidestep, alternating sides
                side = 1 if int(t * 10) % 2 == 0 else -1
                self.unstick_dir, self.unstick_until = (-fy * side, fx * side), t + 0.6
            else:                          # replan with jumps allowed via a fresh plan
                self.unstick_dir, self.unstick_until = (-fx, -fy), t + 0.5
                self.plan_t = -1e9
            out["move"] = list(self.unstick_dir)
            out["jump"] = grounded and self.stuck_level == 1
            self.last_debug = f"stuck {self.stuck_level}"
            return out

        # ---- steer toward the target (walls, zone edge, incoming shells)
        if self.core is not None:
            dx, dy, _ = self.core.steer(pos, target, r, walk, zone=zone_circle, shells=shells)
        else:
            d = math.dist(pos, target) or 1.0
            dx, dy = (target[0] - x) / d, (target[1] - y) / d
        out["move"] = [dx, dy]
        out["boost"] = bool(urgent) and grounded
        self._remember(t, x, y)
        self.last_debug = f"go {len(self.path)}wp"
        return out

    # ------------------------------------------------------------ stuck detection

    def _remember(self, t: float, x: float, y: float) -> None:
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > STUCK_WINDOW_S + 0.5:
            self.hist.pop(0)

    def _is_stuck(self, t: float, x: float, y: float) -> bool:
        old = [h for h in self.hist if t - h[0] >= STUCK_WINDOW_S]
        if not old:
            return False
        moved = math.hypot(x - old[-1][1], y - old[-1][2])
        if moved >= STUCK_MIN_MOVE_M:
            self.stuck_level = 0
            return False
        return True


def boost_policy(me: dict, inside_now: bool, time_left: float, eta_walk: float, reserve: float = 30.0) -> bool:
    """Boost when outside the zone (any energy), or when walking would arrive too late and we can
    spare energy above a reserve kept for jumps."""
    energy = float(me.get("energy", 0.0))
    if not inside_now:
        return energy > 1.0
    return time_left < eta_walk * 1.15 + 3.0 and energy > reserve
