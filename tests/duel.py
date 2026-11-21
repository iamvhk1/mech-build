"""A crude 1-vs-1 duel on the real map, for screening fight behaviours offline (not the server).

Us: MiniSim movement, the real Combat (aim, fire gates), torso slew at turn_rate, gun cooldown /
magazine / reload, ThreatTracker, and optionally the CoverFighter + Navigator.
Enemy: a stationary gunner that fires at the gun's rate whenever its muzzle has a clear line to
our chest or top; rear hits deal x1.5. Two enemy models:
  "prob"    - each shot hits with a fixed probability (lower while we move). Default; kept so earlier
              screening results stay reproducible.
  "bullets" - each shot is a real bullet aimed where we'll be (leading our current velocity, plus
              aim error and the gun's spread); it hits only if we are actually there when it
              arrives ~0.3 s later and no wall is in the way. Use this to judge movement (strafing).
"""
from __future__ import annotations

import math
import random

from combat import Combat, wrap
from fight import CoverFighter
from navigation import Navigator
from strafe import Strafer
from sim import MiniSim
from threat import ThreatTracker


class Duel:
    def __init__(self, core, cfg, start, enemy_xy, cover: bool, seed: int = 0,
                 enemy_hit=0.5, enemy_hit_moving=0.35, our_hit=0.85, enemy_model: str = "prob",
                 enemy_lead: bool = True, enemy_aim_err_deg: float = 0.8, strafe: bool = False):
        self.core, self.cfg = core, cfg
        self.rng = random.Random(seed)
        self.sim = MiniSim(core, cfg, start)
        self.enemy = [enemy_xy[0], enemy_xy[1], core.floor_z(*enemy_xy)]
        self.cover = cover
        self.combat = Combat(cfg, core)
        self.threats = ThreatTracker()
        self.fighter = CoverFighter(core, cfg)
        self.nav = Navigator(core, cfg)
        self.enemy_hit, self.enemy_hit_moving, self.our_hit = enemy_hit, enemy_hit_moving, our_hit
        self.hp, self.ehp = 1400.0, 1400.0
        self.aim = [math.atan2(enemy_xy[1] - start[1], enemy_xy[0] - start[0]), 0.0]
        g = cfg["weapons"]["gun"]
        self.g = g
        self.ammo, self.cd, self.rl = g["mag"], 0.0, 0.0
        self.e_ammo, self.e_cd, self.e_rl = g["mag"], 0.0, 0.0
        self.dealt = self.taken = 0.0
        self.last_seen = -1e9
        self.moved = 0.0
        self.enemy_model, self.enemy_lead = enemy_model, enemy_lead
        self.enemy_aim_err = math.radians(enemy_aim_err_deg)
        self.strafe = strafe
        self.strafer = Strafer(core, cfg, seed)
        self.vel = (0.0, 0.0)
        self.pending = []  # in-flight enemy bullets: (arrival_t, aim_x, aim_y, aim_z)

    def _visible(self) -> bool:
        m = self.cfg["mech"]
        x, y, z = self.sim.x, self.sim.y, self.sim.z
        e = self.enemy
        return self.core.can_see((x, y), z + m["eye_height"], self.aim[0], e[:2], e[2] + m["height"] / 2,
                                 e[2] + m["height"], 45.0, 200.0, 120.0)

    def _enemy_has_shot(self) -> bool:
        m = self.cfg["mech"]
        e = (self.enemy[0], self.enemy[1], self.enemy[2] + m["muzzle_height"])
        for hz in (m["height"] / 2, m["height"]):
            if self.core.shot_los(e, (self.sim.x, self.sim.y, self.sim.z + hz)) >= 1.0:
                return True
        return False

    def _our_shot_hits(self) -> bool:
        """Geometric hit test: the bullet leaves 3 m out along our *actual* aim plus Gaussian
        spread, stops at walls/terrain (trees don't stop it), and must pass within the enemy's
        cylinder (static enemy, so flight time doesn't matter)."""
        m, g = self.cfg["mech"], self.g
        s = math.radians(g["spread_deg"])
        yaw, pitch = self.aim[0] + self.rng.gauss(0, s), self.aim[1] + self.rng.gauss(0, s)
        d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
        mz = (self.sim.x, self.sim.y, self.sim.z + m["muzzle_height"])
        start = [mz[i] + (m["radius"] + 0.5) * d[i] for i in range(3)]
        ex, ey, ez = self.enemy
        # closest approach of the ray to the enemy's vertical axis (2D)
        hx, hy = d[0], d[1]
        hh = hx * hx + hy * hy
        if hh < 1e-9:
            return False
        u = ((ex - start[0]) * hx + (ey - start[1]) * hy) / hh  # horizontal param along the ray
        if u <= 0:
            return False
        px, py = start[0] + hx * u, start[1] + hy * u
        if math.hypot(px - ex, py - ey) > m["radius"]:
            return False
        pz = start[2] + d[2] * u
        if not (ez <= pz <= ez + m["height"]):
            return False
        end = (px, py, pz)
        return self.core.shot_los(start, end) >= 1.0

    def _hit_us(self, g, m, events) -> None:
        bearing = math.atan2(self.enemy[1] - self.sim.y, self.enemy[0] - self.sim.x)
        rear = abs(wrap(bearing - self.aim[0])) > math.pi / 2
        dmg = g["damage"] * (m["rear_mult"] if rear else 1.0)
        self.hp -= dmg
        self.taken += dmg
        events.append({"type": "damaged", "amount": dmg, "weapon": "gun", "bearing": bearing,
                       "by": 5, "rear": rear})

    def run(self, max_s: float = 40.0) -> dict:
        m, g = self.cfg["mech"], self.g
        dt = 0.05
        events = []
        act = {"aim": self.aim, "fire": [False, False], "move": [0.0, 0.0]}
        steps = int(max_s / dt)
        for step in range(steps):
            t = step * dt
            if step % 2 == 0:
                obs = self.sim.obs()
                obs["t"] = t
                obs["self"]["hp"] = self.hp
                obs["self"]["aim"] = list(self.aim)
                obs["self"]["weapons"] = [{"kind": "gun", "cooldown": self.cd, "ammo": self.ammo, "reload": self.rl,
                                           "stats": dict(g)}, None]
                if self._visible():
                    self.last_seen = t
                if t - self.last_seen <= 5.0:
                    obs["mechs"] = [{"id": 5, "kind": "mech", "pos": list(self.enemy), "vel": [0, 0, 0],
                                     "aim": [math.atan2(self.sim.y - self.enemy[1], self.sim.x - self.enemy[0]), 0],
                                     "hp": self.ehp, "max_hp": 1400, "cubes": 0, "weapons": ["gun"], "charging": False}]
                obs["events"] = events
                events = []
                self.combat.observe(obs)
                self.threats.update(obs)
                targets = self.combat.targets(obs)
                mv = {"move": [0.0, 0.0], "boost": False, "jump": False}
                if self.cover:
                    gun = obs["self"]["weapons"][0]
                    tgt = self.combat.engage_target(targets, t, g["range"])
                    goal = self.fighter.goal(obs, tgt, self.threats.hunters(obs["self"]["pos"]), self.threats, gun)
                    if goal is not None:
                        self.nav.set_goal(goal)
                        mv = self.nav.step(obs)
                if self.strafe:
                    new_move, active = self.strafer.adjust(
                        obs, mv["move"], self.enemy[:2],
                        [[self.enemy[0], self.enemy[1], self.enemy[2] + m["eye_height"]]], None)
                    if active:
                        mv = dict(mv, move=new_move, jump=False, boost=False)
                cmb = self.combat.decide(obs, mv["move"], targets)
                act = {**mv, **cmb}
            # legs
            px, py = self.sim.x, self.sim.y
            self.sim.apply({k: act.get(k) for k in ("move", "boost", "jump")}, dt)
            self.moved = math.hypot(self.sim.x - px, self.sim.y - py) / dt
            self.vel = ((self.sim.x - px) / dt, (self.sim.y - py) / dt)
            # torso slew
            dy = wrap(act["aim"][0] - self.aim[0])
            self.aim[0] = wrap(self.aim[0] + max(-m["turn_rate"] * dt, min(m["turn_rate"] * dt, dy)))
            dp = act["aim"][1] - self.aim[1]
            self.aim[1] += max(-m["pitch_rate"] * dt, min(m["pitch_rate"] * dt, dp))
            # our gun
            self.cd = max(0.0, self.cd - dt)
            if self.rl > 0:
                self.rl = max(0.0, self.rl - dt)
                if self.rl == 0:
                    self.ammo = g["mag"]
            if act["fire"][0] and self.cd == 0 and self.ammo > 0 and self.rl == 0:
                self.ammo -= 1
                self.cd = g["cooldown"]
                if self.ammo == 0:
                    self.rl = g["reload"]
                if self._our_shot_hits():
                    self.ehp -= g["damage"]
                    self.dealt += g["damage"]
            # enemy gun
            self.e_cd = max(0.0, self.e_cd - dt)
            if self.e_rl > 0:
                self.e_rl = max(0.0, self.e_rl - dt)
                if self.e_rl == 0:
                    self.e_ammo = g["mag"]
            if self.e_cd == 0 and self.e_ammo > 0 and self.e_rl == 0 and self._enemy_has_shot():
                self.e_ammo -= 1
                self.e_cd = g["cooldown"]
                if self.e_ammo == 0:
                    self.e_rl = g["reload"]
                if self.enemy_model == "bullets":
                    ex, ey = self.enemy[0], self.enemy[1]
                    dist = math.hypot(self.sim.x - ex, self.sim.y - ey)
                    flight = dist / g["speed"]
                    lead = flight if self.enemy_lead else 0.0
                    ax, ay = self.sim.x + self.vel[0] * lead, self.sim.y + self.vel[1] * lead
                    # aim error + spread, as a lateral/vertical offset at the target distance
                    err = math.hypot(self.enemy_aim_err, math.radians(g["spread_deg"]))
                    off_l = math.tan(self.rng.gauss(0.0, err)) * dist
                    off_v = math.tan(self.rng.gauss(0.0, err)) * dist
                    ux, uy = (ax - ex) / max(1e-6, dist), (ay - ey) / max(1e-6, dist)
                    ax, ay = ax - uy * off_l, ay + ux * off_l
                    az = self.sim.z + m["height"] / 2 + off_v
                    self.pending.append((step * dt + flight, ax, ay, az))
                else:
                    p = self.enemy_hit_moving if self.moved > 3.0 else self.enemy_hit
                    if self.rng.random() < p:
                        self._hit_us(g, m, events)
            # enemy bullets arriving now: hit only if we are where they were aimed
            arrived = [b for b in self.pending if b[0] <= step * dt]
            self.pending = [b for b in self.pending if b[0] > step * dt]
            for _, ax, ay, az in arrived:
                if math.hypot(self.sim.x - ax, self.sim.y - ay) <= m["radius"] and \
                        self.sim.z <= az <= self.sim.z + m["height"]:
                    e = (self.enemy[0], self.enemy[1], self.enemy[2] + m["muzzle_height"])
                    if self.core.shot_los(e, (ax, ay, az)) >= 1.0:
                        self._hit_us(g, m, events)
            if self.hp <= 0 or self.ehp <= 0:
                break
        return {"dealt": self.dealt, "taken": self.taken, "won": self.ehp <= 0 and self.hp > 0,
                "lost": self.hp <= 0, "t": t}
