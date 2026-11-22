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
from drops import DropContester
from farm import Farmer
from fight import CoverFighter
from mode import ModeDetector
from pacing import Pacer
from arm import Armer
from strafe import Strafer
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
            if (self.core is not None and (tuning.get("roof.enabled") or tuning.get("retreat.roof"))) else None
        self.strategy = Strategy(self.cfg, self.core, self.zone, self.threats, self.roofs)
        self.fighter = CoverFighter(self.core, self.cfg)
        self.strafer = Strafer(self.core, self.cfg, int(hello.get("seed", 0)))
        self.farmer = Farmer(self.core, self.cfg)
        self.dropper = DropContester(self.core, self.cfg)
        self.pacer = Pacer(self.core, self.cfg)
        self.armer = Armer(self.core, self.cfg, self.farmer)
        self.pacer.farmer = self.farmer  # farm.bank: the pacer cashes in remembered cubes
        self.probe_idle = False  # diagnostics: set by probe.idle_on_pace
        self.mode_detector = ModeDetector()
        self.mode_detector.reset()
        tuning.set_late(False)
        tuning.set_early(False)
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

    def strafe_target(self, obs: dict, targets) -> Optional[Tuple[float, float]]:
        """Whom we're fighting, for strafing: the engage target, else (if hit in the last 2 s) a
        point along the damage bearing. None when we're not in a fight."""
        me = obs["self"]
        st = me.get("stats") or {}
        x, y, z = me["pos"]
        t = float(obs["t"])
        gi = self.combat.slot_of(me, "gun")
        gun = self.combat.slots(me)[gi] if gi is not None else None
        gun_range = float(((gun or {}).get("stats") or self.cfg["weapons"]["gun"]).get("range", 230.0))
        muzzle = [x, y, z + float(st.get("muzzle_height", 7.0))]
        tg = self.combat.engage_target(targets, t, gun_range, muzzle=muzzle)
        if tg is not None:
            return (tg.pos[0], tg.pos[1])
        ld = self.combat.last_damage
        if ld is not None and t - ld[0] <= 2.0:
            return (x + 60.0 * math.cos(ld[1]), y + 60.0 * math.sin(ld[1]))
        return None

    def farm_goal(self, obs: dict, targets) -> Optional[Tuple[float, float]]:
        """Stage C: where to walk to farm crates/cubes, or None when it isn't safe."""
        me = obs["self"]
        st = me.get("stats") or {}
        x, y, z = me["pos"]
        gi = self.combat.slot_of(me, "gun")
        gun = self.combat.slots(me)[gi] if gi is not None else None
        gun_range = float(((gun or {}).get("stats") or self.cfg["weapons"]["gun"]).get("range", 230.0))
        muzzle = [x, y, z + float(st.get("muzzle_height", 7.0))]
        has_target = self.combat.engage_target(targets, float(obs["t"]), gun_range, muzzle=muzzle) is not None
        return self.farmer.plan(obs, self.zone, self.threats.hunters(me["pos"]), self.threats, has_target)

    def drop_goal(self, obs: dict, targets) -> Optional[Tuple[float, float]]:
        """Stage F: contest supply drop for 3 cubes and full HP heal, or None when unsafe."""
        me = obs["self"]
        st = me.get("stats") or {}
        x, y, z = me["pos"]
        gi = self.combat.slot_of(me, "gun")
        gun = self.combat.slots(me)[gi] if gi is not None else None
        gun_range = float(((gun or {}).get("stats") or self.cfg["weapons"]["gun"]).get("range", 230.0))
        muzzle = [x, y, z + float(st.get("muzzle_height", 7.0))]
        has_target = self.combat.engage_target(targets, float(obs["t"]), gun_range, muzzle=muzzle) is not None
        return self.dropper.plan(obs, self.zone, self.threats.hunters(me["pos"]), self.threats, has_target)

    def _retreat_loot(self, obs: dict):
        """Kill cubes within reach while retreating (pacing.loot_more): computed once per decision."""
        if getattr(self, "_rl_tick", None) != obs["tick"]:
            me = obs["self"]
            walk = float((me.get("stats") or {}).get("walk_speed", self.cfg["mech"]["walk_speed"]))
            self._rl_tick = obs["tick"]
            self._rl_goal = self.pacer.loot_goal(obs, self.zone, self.threats.hunters(me["pos"]), self.threats,
                                                 self.farmer.cubes, walk, retreating=True)
            if self._rl_goal is None and tuning.get("farm.bank"):
                self._rl_goal = self.farmer.bank_goal(me, self.zone, walk)
        return self._rl_goal

    def stuck_paused(self, strafe_xy) -> bool:
        """Pause the navigator's stuck detection only while we are actually strafing: still in a
        fight (strafe_xy) AND the strafer strafed on the previous decision. Back-and-forth jinks
        have little net displacement and would read as "stuck" (triggering a hop under fire); but
        in a fight where both strafe directions are unsafe we walk normally, and real stuck
        detection must stay on."""
        if strafe_xy is None:
            self.strafer.active = False  # fight over: don't carry a stale "was strafing" into the next one
            return False
        return bool(self.strafer.active)

    def hunter_eyes(self, me: dict) -> List[List[float]]:
        """Eye points of up to 4 known hunters, for the strafer's exposure check."""
        eye = float(self.cfg["mech"].get("eye_height", 8.0))
        t = self.threats.t
        out = []
        for hh in sorted(self.threats.hunters(me["pos"]), key=lambda h: math.dist(h.pos_at(t)[:2], me["pos"][:2]))[:4]:
            p = hh.pos_at(t)
            out.append([p[0], p[1], p[2] + eye])
        return out

    def fight_goal(self, obs: dict, targets) -> Optional[Tuple[float, float]]:
        """B1: where to stand while fighting the current target from cover (None = no cover fight)."""
        me = obs["self"]
        gi = self.combat.slot_of(me, "gun")
        gun = self.combat.slots(me)[gi] if gi is not None else None
        gun_range = float(((gun or {}).get("stats") or self.cfg["weapons"]["gun"]).get("range", 230.0))
        target = self.combat.engage_target(targets, float(obs["t"]), gun_range)
        self.fighter_goal = self.fighter.goal(obs, target, self.threats.hunters(me["pos"]), self.threats, gun)
        return self.fighter_goal

    # ------------------------------------------------------------ decision

    def act(self, obs: mf.Observation) -> mf.Action:
        t0 = time.perf_counter()
        me = obs["self"]
        x, y, z = me["pos"]
        t = float(obs["t"])
        idle_at = tuning.get("probe.idle_at")
        if (idle_at is not None and t >= float(idle_at)) or self.probe_idle:
            return {"tick": obs["tick"]}  # diagnostic probe: stand still, hold fire (no more points)
        st = me.get("stats") or {}
        act: mf.Action = {"tick": obs["tick"]}
        pick = upgrades.pick(obs.get("offer"), me, self.cfg, str(tuning.get("upgrades")))
        if pick is not None and tuning.get("upgrades") == "first":
            pick = 0
        if pick is not None:
            act["pick"] = pick

        self.zone.update(obs["zone"], t)
        self.combat.observe(obs)
        self.threats.update(obs)
        self.farmer.observe(obs)
        self.dropper.observe(obs)
        self.pacer.observe(obs)
        self.armer.observe(obs)
        self.mode_detector.observe(obs, self.zone)
        early_until = tuning.get("early.until")
        want_early = early_until is not None and t < float(early_until)
        if want_early != tuning.is_early():
            tuning.set_early(want_early)  # early cube rush on / off (practice only)
        late_at = tuning.get("late.at")
        if late_at is not None and t >= float(late_at) and not tuning.is_late():
            tuning.set_late(True)  # late-match caution from here on (practice only)
        targets = self.combat.targets(obs)
        walk = float(st.get("walk_speed", self.cfg["mech"]["walk_speed"]))
        inside = bool(me.get("in_zone", True))
        time_left = self.zone.time_until_outside((x, y))
        eta = self.nav.path_length((x, y)) / max(1.0, walk)
        zone_urgent = (not inside) or time_left < eta * 1.15 + 3.0

        # ---- goal: escape a charging laser > retreat to heal > wanted pickup (if the zone allows)
        #      > zone destination
        dec = self.strategy.update(obs, zone_urgent)
        farming = False
        goal = self.destination(me, t)
        why = dec.why
        threat = self.combat.laser_threat(targets, [x, y, z + float(st.get("height", 9.0)) / 2])
        if dec.state != "burn" and threat is not None and t >= self.evade_until:
            cover = self.combat.cover_from(threat, me)
            if cover is not None:
                self.evade_goal, self.evade_until = cover, t + EVADE_HOLD_S
        pickup = None if dec.retreat else self.combat.wanted_pickup(obs, targets, self.zone)
        if pickup is None and not dec.retreat and not zone_urgent and tuning.get("arm.early"):
            # arm up: walk to a remembered lightning beyond combat's 40 m view rule
            pickup = self.armer.plan(obs, self.zone, self.threats.hunters(me["pos"]), self.threats, walk)
        if t < self.evade_until and self.evade_goal is not None:
            goal, why = self.evade_goal, "evade laser"
        elif dec.state == "retreat" and not zone_urgent and tuning.get("fight.pacing") and \
                (tuning.get("pacing.loot_more") or tuning.get("farm.bank")) and self._retreat_loot(obs) is not None:
            goal, why = self._retreat_loot(obs), f"pace {self.pacer.mode} (retreating)"
        elif dec.goal is not None:
            goal = dec.goal
        elif tuning.get("fight.cover") and not zone_urgent and self.fight_goal(obs, targets) is not None:
            goal, why = self.fighter_goal, f"fight {self.fighter.mode}"
        elif pickup is not None and self.zone.time_until_outside(pickup["pos"]) >                 math.dist(pickup["pos"][:2], (x, y)) / max(1.0, walk) + 10.0:
            goal, why = (pickup["pos"][0], pickup["pos"][1]), f"get {pickup['kind']}"
        elif dec.state == "rotate" and not zone_urgent:
            # supply drop first; with no safe drop, fall through to farming (audit A1: this used to
            # be an elif that skipped farming whenever drops were enabled)
            # escalation survival first (loot a kill's cubes, split ganging hunters), then drops
            pg = self.pacer.plan(obs, self.zone, self.threats.hunters(me["pos"]), self.threats,
                                 self.farmer.cubes, walk) if tuning.get("fight.pacing") else None
            dg = None
            if pg is None and tuning.get("drops.enabled"):
                dg = self.drop_goal(obs, targets)
            if pg is not None:
                goal, why = pg, f"pace {self.pacer.mode}"
                if tuning.get("probe.idle_on_pace") and self.pacer.mode.startswith(tuning.get("probe.idle_on_pace")):
                    self.probe_idle = True  # diagnostics: from the next decision on, stand still
            elif dg is not None:
                goal, why = dg, f"drop {self.dropper.mode}"
            elif tuning.get("farm.crates") or tuning.get("farm.cubes") or tuning.get("farm.drones"):
                fg = self.farm_goal(obs, targets)
                if fg is not None:
                    goal, why, farming = fg, f"farm {self.farmer.mode}", True
        self.nav.allow_roofs = dec.roofs
        self.nav.set_goal(goal)

        # ---- legs (+ strafing in a fight: only in the normal state, zone not urgent, not evading)
        strafe_xy = None
        if tuning.get("fight.strafe") and dec.state == "rotate" and not zone_urgent and t >= self.evade_until:
            strafe_xy = self.strafe_target(obs, targets)
        self.nav.suppress_stuck = self.stuck_paused(strafe_xy)
        urgent = boost_policy(me, inside, time_left, eta) or dec.boost
        mv = self.nav.step(obs, urgent=urgent, zone_circle=self.zone.current(), shells=self.incoming_shells(obs))
        if strafe_xy is not None and self.nav.climb_target is None and me.get("grounded", True):
            new_move, active = self.strafer.adjust(obs, mv["move"], strafe_xy, self.hunter_eyes(me), self.zone.current())
            if active:
                mv = dict(mv, move=new_move, jump=False, boost=False)
                why += " +strafe"
        else:
            self.strafer.active = False  # not strafing this decision (no fight, airborne or climbing)
        act.update(mv)

        # ---- torso and triggers
        farm_aim = self.farmer.crate_aim() if farming else None
        target_drone_id = self.farmer.target_drone.id if (farming and self.farmer.target_drone is not None) else None
        act.update(self.combat.decide(obs, mv["move"], targets, self.zone, retreat=dec.retreat, farm_aim=farm_aim, target_drone_id=target_drone_id))
        act.update(self.combat.take_action(obs, pickup))

        dbg.path((x, y), self.nav.path, z + 1.0)
        dbg.goal(goal, z)
        dbg.label(f"[{self.mode_detector.mode}] {why} | {self.nav.last_debug} | {self.combat.debug}", (time.perf_counter() - t0) * 1000)
        return act


if __name__ == "__main__":
    mf.run(Bot)
