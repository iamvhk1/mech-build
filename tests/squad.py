"""A crude practice-match scenario: our full Bot vs a 15-bot house squad (offline, NOT the server).

Purpose: exercise whole-match behaviour the recorded stream can't (several hunters, kills, kill
drops, the zone schedule) to find bugs and check that a behaviour does what it should. It is NOT a
score predictor: the house-bot AI below is a guess (the duel harness mispredicted blind fire and
strafing for exactly that reason). Compare presets only for "nothing is obviously broken".

House squad, modelled on the track page: 4 easy, 4 medium, 4 hard, 3 expert, sharing vision, never
fighting each other, hunting us weakest first: one early, one more per kill we make, all of them
from LATE_S. Active hunters path toward us and stop to shoot at their preferred range when they
have a line; each shot hits with a tier probability (lower while we move, falling with range).
They carry a gun only. Kills drop 2 cubes. Real map, real zone schedule from hello.config.

    python3 tests/squad.py --presets best pacing --matches 12
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import random
import sys
import time
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mechfight as mf  # noqa: E402

_real_run = mf.run
mf.run = lambda *a, **k: None
import bot as B  # noqa: E402
mf.run = _real_run
import tuning  # noqa: E402
from combat import wrap  # noqa: E402
from sim import MiniSim  # noqa: E402

# tier: (hit prob standing, hit prob vs a moving target, hp multiplier, speed multiplier, preferred range m)
TIERS = {
    "easy": (0.22, 0.12, 0.9, 0.80, 55.0),
    "medium": (0.35, 0.20, 1.0, 0.90, 65.0),
    "hard": (0.48, 0.30, 1.1, 1.00, 75.0),
    "expert": (0.60, 0.40, 1.2, 1.05, 85.0),
}
SQUAD = ["easy"] * 4 + ["medium"] * 4 + ["hard"] * 4 + ["expert"] * 3
FIRST_RELEASE_S = 8.0
LATE_S = 240.0
PATH_EVERY_S = 1.5
DT = 0.05


def load_hello():
    with gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt") as f:
        hello = json.loads(f.readline())
    hello["map"]["dir"] = os.path.join(ROOT, "arena")
    return hello


class Hunter:
    def __init__(self, hid, tier, pos, base_hp):
        self.id, self.tier = hid, tier
        p_still, p_move, hp_mult, spd, pref = TIERS[tier]
        self.p_still, self.p_move, self.speed_mult, self.pref = p_still, p_move, spd, pref
        self.max_hp = self.hp = base_hp * hp_mult
        self.pos = list(pos)
        self.vel = [0.0, 0.0, 0.0]
        self.active = False
        self.alive = True
        self.path = []
        self.path_t = -1e9
        self.cd = 0.0
        self.ammo = 0
        self.rl = 0.0
        self.seen_t = -1e9


class Zone:
    """The real schedule from hello.config.zone, with seeded next centres."""

    def __init__(self, zc, rng):
        self.phases = []
        c, r, t = list(zc["start_center"]), float(zc["start_radius"]), 0.0
        for ph in zc["phases"]:
            nr = float(ph["radius"])
            ang, off = rng.uniform(0, 2 * math.pi), rng.uniform(0, max(0.0, r - nr) * 0.8)
            nc = [c[0] + off * math.cos(ang), c[1] + off * math.sin(ang)]
            s0, s1 = t + ph["hold_s"], t + ph["hold_s"] + ph["shrink_s"]
            self.phases.append((t, s0, s1, list(c), r, nc, nr, float(ph["dps"])))
            c, r, t = nc, nr, s1
        self.final = (c, r)

    def state(self, t):
        for (t0, s0, s1, c, r, nc, nr, dps) in self.phases:
            if t < s1:
                if t <= s0:
                    cc, rr = c, r
                else:
                    f = (t - s0) / (s1 - s0)
                    cc = [c[0] + (nc[0] - c[0]) * f, c[1] + (nc[1] - c[1]) * f]
                    rr = r + (nr - r) * f
                return {"center": cc, "radius": rr, "next_center": nc, "next_radius": nr,
                        "shrink_start": s0, "shrink_end": s1, "dps": dps}
        c, r = self.final
        last = self.phases[-1]
        return {"center": c, "radius": r, "next_center": c, "next_radius": r,
                "shrink_start": last[2], "shrink_end": last[2], "dps": last[7]}

    @staticmethod
    def inside(z, p):
        return math.hypot(p[0] - z["center"][0], p[1] - z["center"][1]) <= z["radius"]


class Match:
    def __init__(self, hello, preset, seed, max_s=480.0):
        tuning.use(preset)
        self.hello = json.loads(json.dumps(hello))
        self.hello["seed"] = seed
        self.cfg = self.hello["config"]
        self.rng = random.Random(seed)
        self.bot = B.Bot(self.hello)
        self.core = self.bot.core
        self.m = self.cfg["mech"]
        self.g = self.cfg["weapons"]["gun"]
        self.zone = Zone(self.cfg["zone"], self.rng)
        self.max_s = max_s
        spots = self._spawns(16)
        self.sim = MiniSim(self.core, self.cfg, spots[0])
        self.hunters = [Hunter(i + 1, tier, (x, y, self.core.floor_z(x, y)), self.m["hp"])
                        for i, (tier, (x, y)) in enumerate(zip(SQUAD, spots[1:]))]
        for h in self.hunters:
            h.ammo = self.g["mag"]
        self.hp = self.max_hp = float(self.m["hp"])
        self.cubes = 0
        self.aim = [0.0, 0.0]
        self.ammo, self.cd, self.rl = self.g["mag"], 0.0, 0.0
        self.cube_items = {}
        self.next_cube = 5000
        self.lw = self.cfg["weapons"]["lightning"]
        self.slot1 = None          # kind of the weapon in slot 1 (only lightning fires in this sim)
        self.cd1 = 0.0
        self.pickups = {}
        kinds = ["mortar", "laser", "lightning"]
        for i, (x, y) in enumerate(self._spawns(int(self.cfg["loot"].get("floor_count", 40)), sep0=30.0)):
            self.pickups[8000 + i] = {"kind": kinds[i % 3], "pos": [x, y, self.core.floor_z(x, y)]}
        self.events = []
        self.last_combat_t = -1e9
        self.kills = 0
        self.zone_deaths = 0
        self.stats = {"loot": 0, "split": 0, "press": 0, "ganged_s": 0.0, "retreat_s": 0.0, "max_ms": 0.0,
                      "errors": 0, "cubes": 0, "error_text": "", "armed_t": None, "lightning_dmg": 0.0}
        self.hit_log = []  # (t, hunter id)
        self._wrap_pacer()

    def _wrap_pacer(self):
        p = self.bot.pacer
        real = p.plan

        def plan(*a, **k):
            g = real(*a, **k)
            if g is not None:
                key = p.mode.split(" ")[0]
                self.stats[key] += 1
            return g
        p.plan = plan

    def _spawns(self, n, sep0=None):
        zc = self.cfg["zone"]
        cx, cy = zc["start_center"]
        rad = float(zc["start_radius"]) * float(self.cfg["match"].get("spawn_zone_fraction", 0.8))
        sep = float(sep0 if sep0 is not None else self.cfg["match"].get("spawn_min_separation", 130))
        out = []
        tries = 0
        while len(out) < n and tries < 20000:
            tries += 1
            a, d = self.rng.uniform(0, 2 * math.pi), rad * math.sqrt(self.rng.random())
            q = self.core.nearest_walkable(cx + d * math.cos(a), cy + d * math.sin(a), self.m["radius"], True)
            if q is None or any(math.dist(q, o) < sep for o in out):
                if tries > 10000 and q is not None:
                    sep *= 0.9
                continue
            out.append(q)
        return out

    # ------------------------------------------------------------ helpers

    def me(self):
        return (self.sim.x, self.sim.y, self.sim.z)

    def alive_count(self):
        return 1 + sum(1 for h in self.hunters if h.alive)

    def _sees(self, h):
        x, y, z = self.me()
        return self.core.can_see((x, y), z + self.m["eye_height"], self.aim[0], h.pos[:2],
                                 h.pos[2] + self.m["height"] / 2, h.pos[2] + self.m["height"],
                                 45.0, 200.0, 120.0)

    def _hunter_has_shot(self, h):
        e = (h.pos[0], h.pos[1], h.pos[2] + self.m["muzzle_height"])
        x, y, z = self.me()
        return any(self.core.shot_los(e, (x, y, z + hz)) >= 1.0 for hz in (self.m["height"] / 2, self.m["height"]))

    def obs(self, t, tick):
        z = self.zone.state(t)
        x, y, zz = self.me()
        mechs = []
        for h in self.hunters:
            if not h.alive:
                continue
            if self._sees(h):
                h.seen_t = t
            if t - h.seen_t <= 5.0:
                mechs.append({"id": h.id, "kind": "mech", "pos": list(h.pos), "vel": list(h.vel),
                              "aim": [math.atan2(y - h.pos[1], x - h.pos[0]) if h.active else 0.0, 0.0],
                              "hp": h.hp, "max_hp": h.max_hp, "cubes": 0, "weapons": ["gun"], "charging": False})
        cubes = []
        for cid, p in self.cube_items.items():
            d = math.dist(p[:2], (x, y))
            if d <= 45.0 or (d <= 200.0 and self.core.vision_los((x, y, zz + self.m["eye_height"]), (p[0], p[1], p[2] + 0.5))):
                cubes.append({"id": cid, "pos": list(p)})
        pickups = []
        for pid, p in self.pickups.items():
            d = math.dist(p["pos"][:2], (x, y))
            if d <= 45.0 or (d <= 200.0 and self.core.vision_los((x, y, zz + self.m["eye_height"]),
                                                                 (p["pos"][0], p["pos"][1], p["pos"][2] + 0.5))):
                pickups.append({"id": pid, "kind": p["kind"], "pos": list(p["pos"])})
        slot1 = None
        if self.slot1 == "lightning":
            slot1 = {"kind": "lightning", "cooldown": self.cd1,
                     "stats": dict(self.lw, damage=self.lw["damage"] * self._dmg_mult())}
        elif self.slot1 is not None:
            slot1 = {"kind": self.slot1, "cooldown": 0.0, "stats": dict(self.cfg["weapons"][self.slot1])}
        st = dict(self.m)
        o = {"type": "obs", "tick": tick, "t": t, "alive": self.alive_count(),
             "self": {"id": 0, "pos": [x, y, zz], "vel": [0, 0, self.sim.vz], "aim": list(self.aim),
                      "hp": self.hp, "max_hp": self.max_hp, "energy": self.sim.energy, "max_energy": self.m["energy"],
                      "grounded": self.sim.grounded, "cubes": self.cubes, "upgrades": [],
                      "in_zone": Zone.inside(z, (x, y)),
                      "weapons": [{"kind": "gun", "cooldown": self.cd, "ammo": self.ammo, "reload": self.rl,
                                   "stats": dict(self.g, damage=self.g["damage"] * self._dmg_mult())}, slot1],
                      "stats": st},
             "mechs": mechs, "projectiles": [], "crates": [], "cubes": cubes, "pickups": pickups, "sounds": [],
             "beams": [], "events": self.events, "drops": [], "zone": z, "offer": None}
        self.events = []
        return o

    def _dmg_mult(self):
        return 1.0 + float(self.cfg["cubes"]["damage_per_cube"]) * min(self.cubes, self.cfg["cubes"]["stat_cap"])

    def _our_shot(self):
        """Geometric hit test against every hunter: the first cylinder the ray crosses, if no wall first."""
        m, g = self.m, self.g
        s = math.radians(g["spread_deg"])
        yaw, pitch = self.aim[0] + self.rng.gauss(0, s), self.aim[1] + self.rng.gauss(0, s)
        d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
        x, y, z = self.me()
        start = [x + (m["radius"] + 0.5) * d[0], y + (m["radius"] + 0.5) * d[1], z + m["muzzle_height"] + (m["radius"] + 0.5) * d[2]]
        hh = d[0] * d[0] + d[1] * d[1]
        if hh < 1e-9:
            return None
        best, best_u = None, 1e9
        for h in self.hunters:
            if not h.alive:
                continue
            ex, ey, ez = h.pos
            u = ((ex - start[0]) * d[0] + (ey - start[1]) * d[1]) / hh
            if u <= 0 or u * math.sqrt(hh) > g["range"]:
                continue
            px, py = start[0] + d[0] * u, start[1] + d[1] * u
            if math.hypot(px - ex, py - ey) > m["radius"]:
                continue
            pz = start[2] + d[2] * u
            if ez <= pz <= ez + m["height"] and u < best_u and self.core.shot_los(start, (px, py, pz)) >= 1.0:
                best, best_u = h, u
        return best

    def _kill(self, h):
        h.alive = False
        self.kills += 1
        self.events.append({"type": "kill", "target": h.id})
        for _ in range(int(self.cfg["cubes"].get("death_drop_extra", 2))):
            self.cube_items[self.next_cube] = [h.pos[0] + self.rng.uniform(-2, 2),
                                               h.pos[1] + self.rng.uniform(-2, 2), h.pos[2]]
            self.next_cube += 1

    # ------------------------------------------------------------ squad

    def _release(self, t):
        living = [h for h in self.hunters if h.alive]
        if t < FIRST_RELEASE_S:
            want = 0
        elif t >= LATE_S:
            want = len(living)
        else:
            want = min(len(living), 1 + self.kills)
        for h in living:  # weakest first: SQUAD order is easy -> expert
            if sum(1 for o in living if o.active) >= want:
                break
            if not h.active:
                h.active = True

    def _move_hunter(self, h, t, z):
        x, y, _ = self.me()
        d = math.hypot(x - h.pos[0], y - h.pos[1])
        speed = self.m["walk_speed"] * h.speed_mult
        goal = None
        if h.active:
            if d > h.pref or not self._hunter_has_shot(h):
                goal = (x, y)
        elif not Zone.inside(z, h.pos) or math.hypot(h.pos[0] - z["next_center"][0], h.pos[1] - z["next_center"][1]) > z["next_radius"] * 0.8:
            goal = tuple(z["next_center"])
        if goal is None or d < 12.0 and h.active:
            h.vel = [0.0, 0.0, 0.0]
            return
        if not h.path or t - h.path_t > PATH_EVERY_S:
            h.path = self.core.find_path(h.pos[:2], goal, self.m["radius"]) or [goal]
            h.path_t = t
        while h.path and math.dist(h.path[0], h.pos[:2]) < 2.0:
            h.path.pop(0)
        if not h.path:
            h.vel = [0.0, 0.0, 0.0]
            return
        wx, wy = h.path[0]
        dx, dy = wx - h.pos[0], wy - h.pos[1]
        n = math.hypot(dx, dy)
        step = min(n, speed * DT)
        h.pos[0] += dx / n * step
        h.pos[1] += dy / n * step
        h.pos[2] = self.core.floor_z(h.pos[0], h.pos[1])
        h.vel = [dx / n * speed, dy / n * speed, 0.0]

    def _hunter_fire(self, h, t, moving):
        h.cd = max(0.0, h.cd - DT)
        if h.rl > 0:
            h.rl = max(0.0, h.rl - DT)
            if h.rl == 0:
                h.ammo = self.g["mag"]
        if not h.active or h.cd > 0 or h.rl > 0 or h.ammo <= 0:
            return
        x, y, _ = self.me()
        d = math.hypot(x - h.pos[0], y - h.pos[1])
        if d > self.g["range"] or not self._hunter_has_shot(h):
            return
        h.ammo -= 1
        h.cd = self.g["cooldown"]
        if h.ammo == 0:
            h.rl = self.g["reload"]
        p = (h.p_move if moving else h.p_still) * max(0.2, min(1.0, 1.0 - (d - 40.0) / 300.0))
        if self.rng.random() < p:
            bearing = math.atan2(h.pos[1] - y, h.pos[0] - x)
            rear = abs(wrap(bearing - self.aim[0])) > math.pi / 2
            dmg = self.g["damage"] * (self.m["rear_mult"] if rear else 1.0)
            self.hp -= dmg
            self.last_combat_t = t
            self.hit_log.append((t, h.id))
            self.events.append({"type": "damaged", "amount": dmg, "weapon": "gun", "bearing": bearing,
                                "by": h.id, "rear": rear})

    # ------------------------------------------------------------ run

    def run(self):
        act = {"aim": self.aim, "fire": [False, False], "move": [0.0, 0.0]}
        steps = int(self.max_s / DT)
        t = 0.0
        for step in range(steps):
            t = step * DT
            z = self.zone.state(t)
            if step % 2 == 0:
                o = self.obs(t, step)
                t0 = time.perf_counter()
                try:
                    act = self.bot.act(o)
                except Exception:
                    self.stats["errors"] += 1
                    if not self.stats["error_text"]:
                        self.stats["error_text"] = traceback.format_exc(limit=4)
                    act = {"move": [0.0, 0.0], "fire": [False, False], "aim": self.aim}
                self.stats["max_ms"] = max(self.stats["max_ms"], (time.perf_counter() - t0) * 1000)
                if getattr(self.bot.strategy, "state", "") == "retreat":
                    self.stats["retreat_s"] += 2 * DT
            # legs and torso
            px, py = self.sim.x, self.sim.y
            self.sim.apply({k: act.get(k) for k in ("move", "boost", "jump")}, DT)
            moving = math.hypot(self.sim.x - px, self.sim.y - py) / DT > 3.0
            a = act.get("aim") or self.aim
            dy = wrap(a[0] - self.aim[0])
            self.aim[0] = wrap(self.aim[0] + max(-self.m["turn_rate"] * DT, min(self.m["turn_rate"] * DT, dy)))
            dp = a[1] - self.aim[1]
            self.aim[1] = max(self.m["min_pitch"], min(self.m["max_pitch"],
                                                       self.aim[1] + max(-self.m["pitch_rate"] * DT, min(self.m["pitch_rate"] * DT, dp))))
            # our gun
            self.cd = max(0.0, self.cd - DT)
            if self.rl > 0:
                self.rl = max(0.0, self.rl - DT)
                if self.rl == 0:
                    self.ammo = self.g["mag"]
            if act.get("reload") and self.rl == 0 and self.ammo < self.g["mag"]:
                self.rl = self.g["reload"]
            fire = act.get("fire") or [False, False]
            if fire[0] and self.cd == 0 and self.ammo > 0 and self.rl == 0:
                self.ammo -= 1
                self.cd = self.g["cooldown"]
                if self.ammo == 0:
                    self.rl = self.g["reload"]
                self.last_combat_t = t
                h = self._our_shot()
                if h is not None:
                    dmg = self.g["damage"] * self._dmg_mult()
                    h.hp -= dmg
                    h.active = True  # shooting a dormant bot wakes it
                    self.events.append({"type": "hit", "target": h.id, "amount": dmg, "weapon": "gun"})
                    if h.hp <= 0:
                        self._kill(h)
            # take a weapon
            tk = act.get("take")
            if tk is not None and tk in self.pickups:
                p = self.pickups[tk]
                x, y, zz = self.me()
                if math.dist(p["pos"][:2], (x, y)) <= self.cfg["loot"]["pickup_radius"] and abs(p["pos"][2] - zz) <= 4.0:
                    if self.slot1 is None or act.get("drop") == 1:
                        del self.pickups[tk]
                        self.slot1 = p["kind"]
                        self.cd1 = 1.0
                        if p["kind"] == "lightning" and self.stats["armed_t"] is None:
                            self.stats["armed_t"] = t
                        self.events.append({"type": "took", "id": tk, "kind": p["kind"], "slot": 1})
            # our lightning: nearest hunter in the cone within range, with a line
            self.cd1 = max(0.0, self.cd1 - DT)
            if self.slot1 == "lightning" and fire[1] and self.cd1 == 0 and self.sim.energy >= self.lw["energy"]:
                self.cd1 = self.lw["cooldown"]
                self.sim.energy -= self.lw["energy"]
                self.last_combat_t = t
                x, y, zz = self.me()
                mz = (x, y, zz + self.m["muzzle_height"])
                cands = []
                for h in self.hunters:
                    if not h.alive:
                        continue
                    d = math.hypot(h.pos[0] - x, h.pos[1] - y)
                    yaw = math.atan2(h.pos[1] - y, h.pos[0] - x)
                    in_cone = abs(wrap(yaw - self.aim[0])) <= math.radians(self.lw["cone_deg"]) / 2
                    if d <= self.lw["range"] and in_cone and \
                            self.core.shot_los(mz, (h.pos[0], h.pos[1], h.pos[2] + self.m["height"] / 2)) >= 1.0:
                        cands.append((d, h))
                if cands:
                    h = min(cands, key=lambda c: c[0])[1]
                    dmg = self.lw["damage"] * self._dmg_mult()
                    h.hp -= dmg
                    h.active = True
                    self.stats["lightning_dmg"] += dmg
                    self.events.append({"type": "hit", "target": h.id, "amount": dmg, "weapon": "lightning"})
                    if h.hp <= 0:
                        self._kill(h)
            # cube pickups
            x, y, zz = self.me()
            for cid in list(self.cube_items):
                p = self.cube_items[cid]
                if math.hypot(p[0] - x, p[1] - y) <= self.cfg["cubes"]["pickup_radius"] and abs(p[2] - zz) <= 4.0:
                    del self.cube_items[cid]
                    self.cubes += 1
                    self.stats["cubes"] += 1
                    if self.cubes <= self.cfg["cubes"]["stat_cap"]:
                        gain = float(self.m["hp"]) * float(self.cfg["cubes"]["hp_per_cube"])
                        self.max_hp += gain
                        self.hp += gain
                    self.events.append({"type": "pickup", "cubes": self.cubes})
            # squad
            self._release(t)
            for h in self.hunters:
                if h.alive:
                    self._move_hunter(h, t, z)
                    self._hunter_fire(h, t, moving)
            recent = {hid for (ht, hid) in self.hit_log if t - ht <= 2.0}
            if len(recent) >= 2:
                self.stats["ganged_s"] += DT
            self.hit_log = [e for e in self.hit_log if t - e[0] <= 2.0]
            # zone and regen
            inside = Zone.inside(z, (x, y))
            if not inside:
                self.hp -= z["dps"] * DT
                self.last_combat_t = t
            elif t - self.last_combat_t >= self.m["regen_delay"]:
                self.hp = min(self.max_hp, self.hp + self.m["regen_per_s"] * DT)
            for h in self.hunters:
                if h.alive and not Zone.inside(z, h.pos):
                    h.hp -= z["dps"] * DT
                    if h.hp <= 0:
                        h.alive = False
                        self.zone_deaths += 1
            if self.hp <= 0:
                place = self.alive_count()
                return self._result(t, place)
            if not any(h.alive for h in self.hunters):
                return self._result(t, 1)
        place = 1 + sum(1 for h in self.hunters if h.alive and h.hp > self.hp)
        return self._result(t, place)

    def _result(self, t, place):
        return dict(self.stats, points=16 - place, t=t, kills=self.kills, zone_deaths=self.zone_deaths)


def run_preset(hello, preset, matches, seed0, max_s=480.0):
    out = []
    for i in range(matches):
        out.append(Match(hello, preset, seed0 + i, max_s).run())
    return out


def summary(name, rs):
    n = len(rs)
    mean = lambda k: sum(r[k] for r in rs) / n  # noqa: E731
    armed = sum(1 for r in rs if r["armed_t"] is not None)
    armed_t = sum(r["armed_t"] for r in rs if r["armed_t"] is not None) / max(1, armed)
    return (f"{name:14s} points {mean('points'):5.2f}  death t {mean('t'):5.0f}s  kills {mean('kills'):4.2f}  "
            f"cubes {mean('cubes'):4.1f}  ganged {mean('ganged_s'):5.1f}s  retreat {mean('retreat_s'):5.1f}s  "
            f"loot {mean('loot'):5.1f}  split {mean('split'):5.1f}  press {mean('press'):5.1f}  zone deaths {mean('zone_deaths'):4.2f}  "
            f"armed {armed}/{n} (t {armed_t:4.0f}s)  lightning dmg {mean('lightning_dmg'):6.0f}  "
            f"errors {sum(r['errors'] for r in rs)}  max {max(r['max_ms'] for r in rs):5.1f} ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--presets", nargs="+", default=["best", "pacing"])
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-s", type=float, default=480.0)
    a = ap.parse_args()
    hello = load_hello()
    for p in a.presets:
        t0 = time.time()
        rs = run_preset(hello, p, a.matches, a.seed, a.max_s)
        print(summary(p, rs), f"[{time.time() - t0:.0f}s]", flush=True)
        errs = [r["error_text"] for r in rs if r["error_text"]]
        if errs:
            print(errs[0])


if __name__ == "__main__":
    main()
