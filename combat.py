"""Combat: torso aim, firing gates, reloads, the slot-1 weapon policy and the laser-threat reflex.

Navigation owns the legs; this module owns the torso and triggers. Phase 3 decisions
(docs/implementation_plan.md):
  Q1 opportunistic: shoot mechs that hit us in the last 5 s, any mech within 60 m, or any target
     below 35% HP in range; otherwise hold fire.
  Q2 lightning first; late-game (zone r <= 70 m) swap lightning -> mortar only under guards,
     including "fewer than half of nearby known mechs carry a laser"; never take lasers.
  Q3 drones only when they attack us.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import core_api
import tuning

TAU = 2 * math.pi

ATTACKER_MEMORY_S = 5.0      # Q1/Q3: "hit us recently"
FACE_ATTACKER_S = 3.0        # turn the front toward the last attacker for this long
AIM_AT_US_RAD = math.radians(4.0)
SOUND_FACE_S = 2.0
LASER_SOUND_S = 10.0
LASER_MAJORITY_RANGE_M = 150.0
SCAN_AMPL = math.radians(50.0)
SCAN_PERIOD_S = 4.0
RELOAD_IDLE_S = 1.5
LIGHTNING_CLOSE_M = 20.0
MORTAR_MIN_SAFE_M = 12.0
LATE_ZONE_R = 70.0
SWAP_CLEAR_M = 50.0
LIGHTNING_DETOUR_M = 40.0
MORTAR_DETOUR_M = 25.0
EVADE_HOLD_S = 1.5


def wrap(a: float) -> float:
    return (a + math.pi) % TAU - math.pi


def yaw_pitch(a: Sequence[float], b: Sequence[float]) -> Tuple[float, float]:
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    return math.atan2(dy, dx), math.atan2(dz, math.hypot(dx, dy))


class Target:
    """What we know about one visible or tracked actor."""

    __slots__ = ("id", "kind", "pos", "vel", "aim", "hp", "max_hp", "cubes", "weapons", "charging",
                 "radius", "height", "center", "dist")

    def __init__(self, m: dict, cfg: dict, me_pos: Sequence[float]):
        self.id = int(m["id"])
        self.kind = m.get("kind", "mech")
        self.pos = m["pos"]
        self.vel = m.get("vel") or [0.0, 0.0, 0.0]
        self.aim = m.get("aim") or [0.0, 0.0]
        self.hp = float(m.get("hp", 1.0))
        self.max_hp = float(m.get("max_hp", 1.0)) or 1.0
        self.cubes = float(m.get("cubes", 0))
        self.weapons = list(m.get("weapons") or [])
        self.charging = bool(m.get("charging", False))
        if self.kind == "mech":
            s = 1 + cfg["cubes"].get("size_per_cube", 0.05) * self.cubes
            self.radius = cfg["mech"]["radius"] * s
            self.height = cfg["mech"]["height"] * s
        else:
            self.radius = float(cfg["npc"].get("radius", 1.8))
            self.height = float(cfg["npc"].get("height", 3.5))
        self.center = [self.pos[0], self.pos[1], self.pos[2] + self.height / 2]
        self.dist = math.dist(self.center[:2], me_pos[:2])

    def aims_at(self, me_center: Sequence[float]) -> bool:
        yaw = math.atan2(me_center[1] - self.pos[1], me_center[0] - self.pos[0])
        return abs(wrap(yaw - self.aim[0])) < AIM_AT_US_RAD + math.atan2(2.5, max(1.0, self.dist))


class Combat:
    def __init__(self, cfg: dict, core):
        self.cfg = cfg
        self.core = core
        self.last_hit_by: Dict[int, float] = {}            # attacker id -> match time
        self.last_damage: Optional[Tuple[float, float, Optional[int]]] = None  # t, bearing, by
        self.sounds: List[Tuple[float, str, float, str]] = []  # t, kind, bearing, dist
        self.last_engage_t = -1e9
        self.evade_until = -1e9
        self.evade_goal: Optional[Tuple[float, float]] = None
        self.debug = ""

    # ------------------------------------------------------------ memory

    def observe(self, obs: dict) -> None:
        t = float(obs["t"])
        for e in obs.get("events") or []:
            if e.get("type") == "damaged" and e.get("by") is not None:
                self.last_hit_by[int(e["by"])] = t
                if e.get("bearing") is not None:
                    self.last_damage = (t, float(e["bearing"]), int(e["by"]))
        for s in obs.get("sounds") or []:
            self.sounds.append((t - float(s.get("age", 0.0)), s["kind"], float(s["bearing"]), s.get("dist", "far")))
        self.sounds = [s for s in self.sounds if t - s[0] < LASER_SOUND_S]
        self.last_hit_by = {k: v for k, v in self.last_hit_by.items() if t - v < 30.0}

    def attacked_recently(self, tid: int, t: float, window: float = ATTACKER_MEMORY_S) -> bool:
        return t - self.last_hit_by.get(tid, -1e9) < window

    # ------------------------------------------------------------ weapons on hand

    @staticmethod
    def slots(me: dict) -> List[Optional[dict]]:
        w = list(me.get("weapons") or [])
        return (w + [None, None])[:2]

    def slot_of(self, me: dict, kind: str) -> Optional[int]:
        for i, w in enumerate(self.slots(me)):
            if w and w.get("kind") == kind:
                return i
        return None

    # ------------------------------------------------------------ Q2: slot-1 policy

    def laser_majority(self, targets: List[Target], t: float) -> bool:
        """True when at least half of the nearby known mechs carry a laser (seen/tracked within
        150 m, plus one unseen carrier if laser sounds were heard in the last 10 s)."""
        near = [m for m in targets if m.kind == "mech" and m.dist <= LASER_MAJORITY_RANGE_M]
        lasers = sum(1 for m in near if "laser" in m.weapons)
        total = len(near)
        heard = any(k in ("laser", "laser_charge") and d in ("near", "mid") for (_, k, _, d) in self.sounds)
        if heard and lasers == 0:
            lasers += 1
            total += 1
        return total > 0 and lasers * 2 >= total

    def wanted_pickup(self, obs: dict, targets: List[Target], zone) -> Optional[dict]:
        """A visible pickup worth walking to and taking now, or None."""
        me = obs["self"]
        t = float(obs["t"])
        pos = me["pos"]
        s1 = self.slots(me)[1]
        kind1 = s1["kind"] if s1 else None
        enemy_near = min((m.dist for m in targets if m.kind == "mech"), default=1e9)
        late = zone is not None and zone.known and zone.current()[2] <= LATE_ZONE_R

        def visible(kind: str, max_d: float):
            best, bd = None, max_d
            for p in obs.get("pickups") or []:
                if p.get("kind") != kind:
                    continue
                d = math.dist(p["pos"][:2], pos[:2])
                if d < bd and (zone is None or not zone.known or zone.depth(zone.current(), p["pos"]) > 3.0):
                    best, bd = p, d
            return best

        # late-game mortar swap (lightning -> mortar), all guards
        if late and kind1 in ("lightning", None) and enemy_near > SWAP_CLEAR_M and not self.laser_majority(targets, t):
            p = visible("mortar", MORTAR_DETOUR_M)
            if p is not None:
                return p
        # lightning first: into an empty slot any time; replacing a laser/mortar only out of combat,
        # and never undoing a late-game mortar
        if kind1 is None or (kind1 == "laser" and enemy_near > SWAP_CLEAR_M) or \
                (kind1 == "mortar" and not late and enemy_near > SWAP_CLEAR_M):
            if kind1 is None and enemy_near < 30.0:
                return None
            return visible("lightning", LIGHTNING_DETOUR_M)
        return None

    def take_action(self, obs: dict, pickup: Optional[dict]) -> Dict[str, int]:
        """`take` (and `drop` for a swap) when the wanted pickup is within reach."""
        if pickup is None:
            return {}
        me = obs["self"]
        reach = float(self.cfg["loot"].get("pickup_radius", 4.0))
        if math.dist(pickup["pos"][:2], me["pos"][:2]) > reach - 0.3 or abs(pickup["pos"][2] - me["pos"][2]) > 3.8:
            return {}
        s1 = self.slots(me)[1]
        if s1 is not None and s1.get("kind") == "laser" and float(s1.get("charge", 0.0)) > 0:
            return {}  # can't swap out a charging laser
        out = {"take": int(pickup["id"])}
        if s1 is not None:
            out["drop"] = 1
        return out

    # ------------------------------------------------------------ Q1/Q3: who to shoot

    def engage_target(self, targets: List[Target], t: float, gun_range: float, retreat: bool = False) -> Optional[Target]:
        best, best_s = None, -1e9
        for m in targets:
            if retreat and m.dist > tuning.get("retreat.cornered_m") and m.hp / m.max_hp >= tuning.get("retreat.finish_hp"):
                continue  # regen needs 5 s without dealing damage: hold fire while retreating
            hit_us = self.attacked_recently(m.id, t)
            if m.kind != "mech" and not hit_us:
                continue  # Q3: drones only when they attack us
            if m.dist > gun_range:
                continue
            near_m = tuning.get("engage.near_m")
            low = m.hp / m.max_hp < tuning.get("engage.low_hp")
            if not (hit_us or m.dist <= near_m or low or (m.kind == "mech" and tuning.get("engage.any_in_range"))):
                continue
            s = 3.0 * hit_us + 2.0 * (m.dist <= near_m) + 2.0 * low - m.dist / 100.0 - m.hp / m.max_hp
            if s > best_s:
                best, best_s = m, s
        return best

    # ------------------------------------------------------------ laser threat

    def laser_threat(self, targets: List[Target], me_center) -> Optional[Target]:
        rng = float(self.cfg["weapons"]["laser"].get("range", 280.0))
        threats = [m for m in targets if m.kind == "mech" and m.charging and m.dist <= rng and m.aims_at(me_center)]
        return min(threats, key=lambda m: m.dist) if threats else None

    def cover_from(self, threat: Target, me: dict) -> Optional[Tuple[float, float]]:
        """Nearest walkable spot within ~12 m where the threat's muzzle has no shot at our chest."""
        if self.core is None:
            return None
        st = me.get("stats") or {}
        r = float(st.get("radius", 2.5))
        x, y, _ = me["pos"]
        tz = threat.pos[2] + float(self.cfg["mech"].get("muzzle_height", 7.0))
        best, bd = None, 1e9
        for k in range(16):
            a = k * TAU / 16
            for d in (4.0, 8.0, 12.0):
                px, py = x + math.cos(a) * d, y + math.sin(a) * d
                if self.core.clearance(px, py) < r or not self.core.segment_walkable((x, y), (px, py), r * 0.9):
                    break
                pz = self.core.floor_z(px, py) + 4.5
                if self.core.shot_los((threat.pos[0], threat.pos[1], tz), (px, py, pz)) < 1.0 and d < bd:
                    best, bd = (px, py), d
                    break
        return best

    # ------------------------------------------------------------ decision

    def targets(self, obs: dict) -> List[Target]:
        me = obs["self"]
        return [Target(m, self.cfg, me["pos"]) for m in obs.get("mechs") or []]

    def decide(self, obs: dict, move: Sequence[float], targets: Optional[List[Target]] = None, zone=None,
               retreat: bool = False) -> dict:
        """Torso and triggers: {"aim": [yaw, pitch], "fire": [bool, bool], "reload": bool}."""
        me = obs["self"]
        t = float(obs["t"])
        st = me.get("stats") or {}
        x, y, z = me["pos"]
        muzzle = [x, y, z + float(st.get("muzzle_height", 7.0))]
        my_center = [x, y, z + float(st.get("height", 9.0)) / 2]
        my_r = float(st.get("radius", 2.5))
        act_yaw, act_pitch = (me.get("aim") or [0.0, 0.0])[:2]
        targets = self.targets(obs) if targets is None else targets
        slots = self.slots(me)
        fire = [False, False]
        reload_ = False
        aim: Optional[List[float]] = None
        why = ""

        gun_i = self.slot_of(me, "gun")
        gun = slots[gun_i] if gun_i is not None else None
        gstats = (gun or {}).get("stats") or self.cfg["weapons"]["gun"]
        gun_range = float(gstats.get("range", 230.0))
        lightning_i = self.slot_of(me, "lightning")
        mortar_i = self.slot_of(me, "mortar")
        laser_i = self.slot_of(me, "laser")

        threat = self.laser_threat(targets, my_center)
        target = self.engage_target(targets, t, gun_range, retreat)
        if threat is not None and (target is None or target.dist > threat.dist + 30):
            target = threat if threat.dist <= gun_range else target

        # ---- (a) engage: gun lead solution
        solution = None
        if target is not None:
            speed = float(gstats.get("speed", 252.0))
            solution = core_api.gun_lead(muzzle, target.center, target.vel, speed, my_r + 0.5)
            if solution is not None:
                aim = [solution[0], solution[1]]
                why = f"engage {target.id}"
                self.last_engage_t = t
        # ---- (b) last attacker, (c) mech aiming at us / laser threat
        if aim is None and self.last_damage and t - self.last_damage[0] < FACE_ATTACKER_S:
            _, bearing, by = self.last_damage
            src = next((m for m in targets if m.id == by), None)
            aim = [yaw_pitch(muzzle, src.center)[0] if src else bearing, 0.0]
            why = "face attacker"
        if aim is None:
            facing = threat or next((m for m in sorted(targets, key=lambda m: m.dist)
                                     if m.kind == "mech" and m.aims_at(my_center)), None)
            if facing is not None:
                aim = [yaw_pitch(muzzle, facing.center)[0], 0.0]
                why = "face threat"
        # ---- (d) scan: recent combat sounds, else sweep around the movement direction
        if aim is None:
            loud = [s for s in self.sounds if t - s[0] < SOUND_FACE_S and s[1] in
                    ("gun", "laser", "laser_charge", "lightning", "mortar", "explosion") and s[3] in ("near", "mid")]
            if loud:
                aim = [max(loud)[2], 0.0]
                why = "face sound"
            else:
                base = math.atan2(move[1], move[0]) if (move[0] or move[1]) else act_yaw
                aim = [wrap(base + SCAN_AMPL * math.sin(TAU * t / SCAN_PERIOD_S)), 0.0]
                why = "scan"

        # ---- mortar (late-game weapon): takes the torso only when the gun has no usable shot
        # (target behind cover, gun empty or reloading), so the aim never flip-flops between them
        gun_usable = gun is not None and target is not None and solution is not None and \
            float(gun.get("ammo", 1)) > 0 and float(gun.get("reload", 0.0)) <= 0.0 and \
            self.clear_shot(muzzle, solution, target, my_r)
        if mortar_i is not None and target is not None and not gun_usable:
            mres = self.mortar_aim(obs, slots[mortar_i], target, zone)
            if mres is not None:
                aim, why = mres[0], f"mortar {target.id}"
                fire[mortar_i] = mres[1]

        # ---- gun gate (actual torso aim vs the lead solution)
        if gun_usable:
            d = max(1.0, math.dist(muzzle, target.center))
            spread = math.radians(float(gstats.get("spread_deg", 0.6)))
            tol_yaw = math.atan2(target.radius * 0.8, d) + spread
            tol_pitch = math.atan2(target.height * 0.4, d) + spread
            on = abs(wrap(act_yaw - solution[0])) <= tol_yaw and abs(act_pitch - solution[1]) <= tol_pitch
            # the bullet leaves along the *actual* aim: that line must be clear too
            if on and float(gun.get("cooldown", 0.0)) <= 0.05 and d <= gun_range and \
                    self.clear_shot(muzzle, (act_yaw, act_pitch, 0.0), target, my_r):
                fire[gun_i] = True
        # ---- early reload when idle
        if gun is not None and t - self.last_engage_t > RELOAD_IDLE_S and float(gun.get("reload", 0.0)) <= 0 \
                and float(gun.get("ammo", 0)) < float(gstats.get("mag", 12)) / 2:
            reload_ = True

        # ---- lightning
        if lightning_i is not None:
            lw = slots[lightning_i]
            intended = threat if (threat is not None and threat.dist <= self.lightning_range(lw)) else target
            if intended is not None and self.lightning_ok(obs, lw, intended, muzzle, act_yaw, targets):
                fire[lightning_i] = True

        # ---- laser (only if we ended up holding one): minimal charge/release
        if laser_i is not None:
            fire[laser_i] = self.laser_trigger(slots[laser_i], target, solution, act_yaw, act_pitch, targets, muzzle)

        self.debug = why
        return {"aim": [wrap(aim[0]), max(float(st.get("min_pitch", -0.7)), min(float(st.get("max_pitch", 1.3)), aim[1]))],
                "fire": fire, "reload": reload_}

    # ------------------------------------------------------------ gates

    def clear_shot(self, muzzle, solution, target: Target, my_r: float) -> bool:
        """No wall between the shot spawn point and the target (trees don't stop shots)."""
        if self.core is None:
            return True
        yaw, pitch = solution[0], solution[1]
        d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
        start = [muzzle[i] + (my_r + 0.5) * d[i] for i in range(3)]
        if self.core.shot_los(muzzle, start) < 1.0:
            return False  # barrel inside a wall
        dist = math.dist(start, target.center)
        end = [start[i] + dist * d[i] for i in range(3)]  # along this aim, as far as the target
        return self.core.shot_los(start, end) >= 1.0

    @staticmethod
    def lightning_range(w: dict) -> float:
        return float(((w or {}).get("stats") or {}).get("range", 45.0))

    def lightning_ok(self, obs: dict, w: dict, intended: Target, muzzle, act_yaw: float, targets: List[Target]) -> bool:
        """Fire only if the arc will hit the intended target: it is within the narrow half of the
        cone, in range with line of sight, and nothing else (mech, drone, crate) is closer within
        the wide cone. Safe whether cone_deg is a half or a full angle."""
        stats = (w or {}).get("stats") or self.cfg["weapons"]["lightning"]
        if float((w or {}).get("cooldown", 0.0)) > 0.05:
            return False
        rng = float(stats.get("range", 45.0))
        cone = math.radians(float(stats.get("cone_deg", 30.0)))
        energy = float(obs["self"].get("energy", 0.0))
        cost = float(stats.get("energy", 3.0))
        d0 = math.dist(muzzle, intended.center)
        if d0 > rng or energy < cost:
            return False
        if energy - cost < tuning.get("lightning.reserve") and d0 > LIGHTNING_CLOSE_M:
            return False
        if abs(wrap(yaw_pitch(muzzle, intended.center)[0] - act_yaw)) > cone / 2:
            return False
        if self.core is not None and self.core.shot_los(muzzle, intended.center) < 1.0:
            return False
        others = [(m.center, m.id) for m in targets if m.id != intended.id]
        others += [([c["pos"][0], c["pos"][1], c["pos"][2] + 1.2], c["id"]) for c in obs.get("crates") or []]
        for c, _ in others:
            if math.dist(muzzle, c) < d0 and abs(wrap(yaw_pitch(muzzle, c)[0] - act_yaw)) <= cone:
                if self.core is None or self.core.shot_los(muzzle, c) >= 1.0:
                    return False
        return True

    def mortar_aim(self, obs: dict, w: dict, target: Target, zone) -> Optional[Tuple[List[float], bool]]:
        """Lob at the target (leading it), aiming slightly to the target's zone-centre side so the
        blast pushes it outward. Never fire if the shell would land within 12 m of us."""
        me = obs["self"]
        st = me.get("stats") or {}
        ms = (w or {}).get("stats") or self.cfg["weapons"]["mortar"]
        speed, g = float(ms.get("speed", 72.0)), float(ms.get("gravity", 22.0))
        x, y, z = me["pos"]
        tube = [x, y, z + float(st.get("height", 9.0)) + 0.5]
        off = float(st.get("radius", 2.5)) + 0.5
        aim_pt = list(target.pos)
        if zone is not None and zone.known:
            cx, cy, _ = zone.current()
            dx, dy = cx - aim_pt[0], cy - aim_pt[1]
            dn = math.hypot(dx, dy)
            if dn > 1e-6:
                aim_pt = [aim_pt[0] + 2.0 * dx / dn, aim_pt[1] + 2.0 * dy / dn, aim_pt[2]]
        sol = None
        for _ in range(2):  # lead by the flight time
            sol = core_api.mortar_pitch(tube, aim_pt, speed, g, off, False, float(st.get("min_pitch", -0.7)),
                                        float(st.get("max_pitch", 1.3)))
            if sol is None:
                sol = core_api.mortar_pitch(tube, aim_pt, speed, g, off, True, float(st.get("min_pitch", -0.7)),
                                            float(st.get("max_pitch", 1.3)))
            if sol is None:
                return None
            ft = sol[2]
            aim_pt = [target.pos[0] + target.vel[0] * ft, target.pos[1] + target.vel[1] * ft, target.pos[2]]
        yaw, pitch, _ = sol
        if math.dist(aim_pt[:2], (x, y)) < MORTAR_MIN_SAFE_M:
            return [yaw, pitch], False
        ay, ap = (me.get("aim") or [0.0, 0.0])[:2]
        ready = float((w or {}).get("cooldown", 0.0)) <= 0.05
        on = abs(wrap(ay - yaw)) < math.radians(1.5) and abs(ap - pitch) < math.radians(1.5)
        ok = ready and on
        if ok and self.core is not None:
            # where the shell would really land given our *actual* aim: never near ourselves
            d = (math.cos(ap) * math.cos(ay), math.cos(ap) * math.sin(ay), math.sin(ap))
            start = [tube[i] + off * d[i] for i in range(3)]
            hit = self.core.shell_impact(start, [speed * d[0], speed * d[1], speed * d[2]], g, float(ms.get("ttl", 7.0)))
            if hit is None or math.dist(hit[:2], (x, y)) < MORTAR_MIN_SAFE_M:
                ok = False
        return [yaw, pitch], ok

    def laser_trigger(self, w: dict, target: Optional[Target], solution, act_yaw, act_pitch,
                      targets: List[Target], muzzle) -> bool:
        """Minimal laser use: hold to charge with a stable target in sight; release (False) once
        charged >= 0.65 s and on target. Never charge near a lightning carrier (it shorts us)."""
        charge = float((w or {}).get("charge", 0.0))
        if target is None or solution is None:
            return False  # releasing an early charge fires a weak beam at min_charge; acceptable
        if any(m.kind == "mech" and "lightning" in m.weapons and m.dist <= 50.0 for m in targets):
            return False
        on = abs(wrap(act_yaw - solution[0])) < math.radians(1.0) and abs(act_pitch - solution[1]) < math.radians(1.0)
        if charge >= 0.65 and on:
            return False  # release: fires along the current aim
        return float((w or {}).get("cooldown", 0.0)) <= 0.05 or charge > 0
