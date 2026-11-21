"""Mech Royale bot entrypoint (Phase 1).

Phase 1 scope: build the C++ map core at `hello`, then walk toward the next zone centre along an
A* path. Combat is still the kit example's (aim at the nearest mech, hold both triggers); the real
combat, strategy and upgrade logic land in Phases 2-4 (docs/implementation_plan.md).

If the core fails to load, the bot falls back to straight-line movement instead of crashing.
"""
from __future__ import annotations

import math
import time
import traceback
from typing import List, Optional, Tuple

import debug_draw as dbg
import mechfight as mf

try:
    import core_api
except Exception:  # pragma: no cover - only when the shared library is missing
    core_api = None  # type: ignore[assignment]
    mf.log("core_api import failed:\n" + traceback.format_exc())

REPLAN_TICKS = 20        # replan at most every 1 s of match time (20 sim ticks)
GOAL_MOVED_M = 8.0       # ...or when the goal moved this far
WAYPOINT_REACHED_M = 3.0
OFF_PATH_M = 12.0        # replan if we drift this far from the next waypoint's line


class Bot:
    name = "mech-royale"

    def __init__(self, hello: mf.Hello):
        self.cfg = hello["config"]
        self.reach = self.cfg["loot"]["pickup_radius"]
        self.core: Optional["core_api.MapCore"] = None
        if core_api is not None:
            try:
                self.core = core_api.MapCore.from_hello(hello)
                mf.log(f"core ready: build {self.core.build_ms:.0f} ms, load {self.core.load_ms:.0f} ms, "
                       f"grid {self.core.nnx}x{self.core.nny}")
            except Exception:
                mf.log("core unavailable, using straight-line movement:\n" + traceback.format_exc())
        self.path: List[Tuple[float, float]] = []
        self.path_goal: Optional[Tuple[float, float]] = None
        self.path_tick = -10 ** 9

    # ------------------------------------------------------------ navigation

    def radius(self, me: dict) -> float:
        st = me.get("stats") or {}
        if "radius" in st:
            return float(st["radius"])
        base = self.cfg["mech"]["radius"]
        return base * (1 + self.cfg["cubes"].get("size_per_cube", 0) * me.get("cubes", 0))

    def plan(self, pos: Tuple[float, float], goal: Tuple[float, float], radius: float, tick: int) -> None:
        self.path_goal = goal
        self.path_tick = tick
        self.path = []
        if self.core is None:
            return
        p = self.core.find_path(pos, goal, radius)
        if p:
            self.path = p

    def navigate(self, pos: Tuple[float, float], goal: Tuple[float, float], radius: float, tick: int) -> List[float]:
        if (self.path_goal is None or math.dist(goal, self.path_goal) > GOAL_MOVED_M
                or tick - self.path_tick >= REPLAN_TICKS or not self.path
                or math.dist(pos, self.path[0]) > OFF_PATH_M + 24.0):
            self.plan(pos, goal, radius, tick)
        while len(self.path) > 1 and math.dist(pos, self.path[0]) < WAYPOINT_REACHED_M:
            self.path.pop(0)
        target = self.path[0] if self.path else goal
        if math.dist(pos, target) < 1.0:
            return [0.0, 0.0]
        if self.core is not None:
            dx, dy, _ = self.core.steer(pos, target, radius, 11.7)
            return [dx, dy]
        yaw = math.atan2(target[1] - pos[1], target[0] - pos[0])
        return [math.cos(yaw), math.sin(yaw)]

    # ------------------------------------------------------------ decision

    def act(self, obs: mf.Observation) -> mf.Action:
        t0 = time.perf_counter()
        me = obs["self"]
        x, y, z = me["pos"]
        goal = tuple(obs["zone"]["next_center"][:2])
        act: mf.Action = {"tick": obs["tick"]}
        if obs.get("offer"):
            act["pick"] = 0  # Phase 4: effect-scored upgrade picker
        near = [p for p in obs["pickups"] if math.dist(p["pos"][:2], (x, y)) < self.reach]
        if me["weapons"][1] is None and near and near[0]["kind"] != "gun":
            act["take"] = near[0]["id"]

        move = self.navigate((x, y), goal, self.radius(me), int(obs["tick"]))
        act["move"] = move
        act["boost"] = not me["in_zone"]
        yaw = math.atan2(move[1], move[0]) if move != [0.0, 0.0] else me["aim"][0]
        act["aim"] = [yaw, 0.0]

        enemies = sorted((m for m in obs["mechs"] if m["kind"] == "mech"), key=lambda m: math.dist(m["pos"], me["pos"]))
        if enemies:
            t = enemies[0]["pos"]
            act["aim"] = [math.atan2(t[1] - y, t[0] - x), math.atan2(t[2] - z - 2.5, math.dist(t[:2], (x, y)))]
            act["fire"] = [True, True]

        dbg.path((x, y), self.path, z + 1.0)
        dbg.goal(goal, z)
        dbg.label("rotate", (time.perf_counter() - t0) * 1000)
        return act


if __name__ == "__main__":
    mf.run(Bot)
