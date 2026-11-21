"""Mech Royale bot entrypoint.

Phase 2 scope: track the zone, pick a covered destination inside the next circle, and get there on
time (walking A* first, jumps/jets when walking can't reach, unsticking, boost only when late or
outside). Combat is still the kit example's (aim at the nearest mech, hold both triggers); real
combat, strategy and upgrades land in Phases 3-4 (docs/implementation_plan.md).

If the core fails to load, the bot falls back to straight-line movement instead of crashing.
"""
from __future__ import annotations

import math
import time
import traceback
from typing import List, Optional, Tuple

import debug_draw as dbg
import mechfight as mf
from navigation import Navigator, boost_policy
from zone import Zone, choose_destination

try:
    import core_api
except Exception:  # pragma: no cover - only when the shared library is missing
    core_api = None  # type: ignore[assignment]
    mf.log("core_api import failed:\n" + traceback.format_exc())

DEST_REFRESH_S = 5.0     # re-pick the destination at least this often (cover vs. where we are)


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
        self.zone = Zone()
        self.nav = Navigator(self.core, self.cfg)
        self.dest: Optional[Tuple[float, float]] = None
        self.dest_key = None
        self.dest_t = -1e9
        w = self.cfg["weapons"]["mortar"]
        self.shell_g = float(w.get("gravity", 22.0))
        self.shell_splash = float(w.get("splash_radius", 7.0)) + 1.5

    # ------------------------------------------------------------ helpers

    def incoming_shells(self, obs: dict) -> List[Tuple[float, float, float, float]]:
        """Predicted landing points of visible enemy mortar shells: (x, y, splash, seconds)."""
        out = []
        if self.core is None:
            return out
        for p in obs.get("projectiles") or []:
            if p.get("kind") != "mortar":
                continue
            hit = self.core.shell_impact(p["pos"], p["vel"], self.shell_g, 8.0)
            if hit is not None:
                out.append((hit[0], hit[1], self.shell_splash, hit[3]))
        return out[:8]

    def destination(self, me: dict, t: float) -> Tuple[float, float]:
        nxt = self.zone.next_circle()
        key = (round(nxt[0]), round(nxt[1]), round(nxt[2]))
        if self.dest is None or key != self.dest_key or t - self.dest_t > DEST_REFRESH_S:
            st = me.get("stats") or {}
            self.dest = choose_destination(self.core, self.zone, me["pos"], float(st.get("radius", 2.5)))
            self.dest_key, self.dest_t = key, t
        return self.dest

    # ------------------------------------------------------------ decision

    def act(self, obs: mf.Observation) -> mf.Action:
        t0 = time.perf_counter()
        me = obs["self"]
        x, y, z = me["pos"]
        t = float(obs["t"])
        act: mf.Action = {"tick": obs["tick"]}
        if obs.get("offer"):
            act["pick"] = 0  # Phase 4: effect-scored upgrade picker
        near = [p for p in obs["pickups"] if math.dist(p["pos"][:2], (x, y)) < self.reach]
        if me["weapons"][1] is None and near and near[0]["kind"] != "gun":
            act["take"] = near[0]["id"]

        # ---- zone and movement
        self.zone.update(obs["zone"], t)
        dest = self.destination(me, t)
        self.nav.set_goal(dest)
        walk = float((me.get("stats") or {}).get("walk_speed", self.cfg["mech"]["walk_speed"]))
        eta = self.nav.path_length((x, y)) / max(1.0, walk)
        inside = bool(me.get("in_zone", True))
        urgent = boost_policy(me, inside, self.zone.time_until_outside((x, y)), eta)
        mv = self.nav.step(obs, urgent=urgent, zone_circle=self.zone.current(), shells=self.incoming_shells(obs))
        act.update(mv)

        # ---- aim and fire (kit example; Phase 3 replaces this)
        move = mv["move"]
        yaw = math.atan2(move[1], move[0]) if (move[0] or move[1]) else me["aim"][0]
        act["aim"] = [yaw, 0.0]
        enemies = sorted((m for m in obs["mechs"] if m["kind"] == "mech"), key=lambda m: math.dist(m["pos"], me["pos"]))
        if enemies:
            tp = enemies[0]["pos"]
            act["aim"] = [math.atan2(tp[1] - y, tp[0] - x), math.atan2(tp[2] - z - 2.5, math.dist(tp[:2], (x, y)))]
            act["fire"] = [True, True]

        dbg.path((x, y), self.nav.path, z + 1.0)
        dbg.goal(dest, z)
        dbg.label(self.nav.last_debug, (time.perf_counter() - t0) * 1000)
        return act


if __name__ == "__main__":
    mf.run(Bot)
