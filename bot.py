"""Mech Royale bot entrypoint.

Phases 2-3: track the zone, pick a covered destination inside the next circle and get there on
time (navigation.py); combat.py owns the torso and triggers (gun lead and fire gates, lightning
nearest-target check, facing attackers, laser-threat reflex, slot-1 weapon policy). Strategy,
farming and upgrades land in Phase 4 (docs/implementation_plan.md).

If the core fails to load, the bot falls back to straight-line movement instead of crashing.
"""
from __future__ import annotations

import math
import time
import traceback
from typing import List, Optional, Tuple

import debug_draw as dbg
import mechfight as mf
from combat import Combat, EVADE_HOLD_S
from navigation import Navigator, boost_policy
from roofs import RoofIndex
from strategy import Strategy
from threat import ThreatTracker
import tuning
import upgrades
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
                mf.log(f"tuning preset: {tuning.ACTIVE}")
                mf.log(f"core ready: build {self.core.build_ms:.0f} ms, load {self.core.load_ms:.0f} ms, "
                       f"grid {self.core.nnx}x{self.core.nny}")
            except Exception:
                mf.log("core unavailable, using straight-line movement:\n" + traceback.format_exc())
        self.zone = Zone()
        self.nav = Navigator(self.core, self.cfg)
        self.combat = Combat(self.cfg, self.core)
        self.threats = ThreatTracker()
        self.roofs = RoofIndex(self.core, float(self.cfg["mech"]["radius"]), float(self.cfg["mech"]["step_up"])) \
            if (self.core is not None and tuning.get("roof.enabled")) else None
        self.strategy = Strategy(self.cfg, self.core, self.zone, self.threats, self.roofs)
        self.evade_goal: Optional[Tuple[float, float]] = None
        self.evade_until = -1e9
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
        st = me.get("stats") or {}
        act: mf.Action = {"tick": obs["tick"]}
        pick = upgrades.pick(obs.get("offer"), me, self.cfg)
        if pick is not None and tuning.get("upgrades") == "first":
            pick = 0
        if pick is not None:
            act["pick"] = pick

        self.zone.update(obs["zone"], t)
        self.combat.observe(obs)
        self.threats.update(obs)
        targets = self.combat.targets(obs)
        walk = float(st.get("walk_speed", self.cfg["mech"]["walk_speed"]))
        inside = bool(me.get("in_zone", True))
        time_left = self.zone.time_until_outside((x, y))
        eta = self.nav.path_length((x, y)) / max(1.0, walk)
        zone_urgent = (not inside) or time_left < eta * 1.15 + 3.0

        # ---- goal: escape a charging laser > retreat to heal > wanted pickup (if the zone allows)
        #      > zone destination
        dec = self.strategy.update(obs, zone_urgent)
        goal = self.destination(me, t)
        why = dec.why
        threat = self.combat.laser_threat(targets, [x, y, z + float(st.get("height", 9.0)) / 2])
        if threat is not None and t >= self.evade_until:
            cover = self.combat.cover_from(threat, me)
            if cover is not None:
                self.evade_goal, self.evade_until = cover, t + EVADE_HOLD_S
        pickup = None if dec.retreat else self.combat.wanted_pickup(obs, targets, self.zone)
        if t < self.evade_until and self.evade_goal is not None:
            goal, why = self.evade_goal, "evade laser"
        elif dec.goal is not None:
            goal = dec.goal
        elif pickup is not None:
            d = math.dist(pickup["pos"][:2], (x, y))
            if self.zone.time_until_outside(pickup["pos"]) > d / max(1.0, walk) + 10.0:
                goal, why = (pickup["pos"][0], pickup["pos"][1]), f"get {pickup['kind']}"
        self.nav.allow_roofs = dec.roofs
        self.nav.set_goal(goal)

        # ---- legs
        urgent = boost_policy(me, inside, time_left, eta) or dec.boost
        mv = self.nav.step(obs, urgent=urgent, zone_circle=self.zone.current(), shells=self.incoming_shells(obs))
        act.update(mv)

        # ---- torso and triggers
        act.update(self.combat.decide(obs, mv["move"], targets, self.zone, retreat=dec.retreat))
        act.update(self.combat.take_action(obs, pickup))

        dbg.path((x, y), self.nav.path, z + 1.0)
        dbg.goal(goal, z)
        dbg.label(f"{why} | {self.nav.last_debug} | {self.combat.debug}", (time.perf_counter() - t0) * 1000)
        return act


if __name__ == "__main__":
    mf.run(Bot)
