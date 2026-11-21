"""Phase 3 tests: combat gates and policies, plus a simulated duel against a strafing mech.

    make -C core && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import copy
import gzip
import json
import math
import os
import random
import sys
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import core_api  # noqa: E402
import tuning  # noqa: E402
from combat import Combat, wrap  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")
STREAM = os.path.join(ROOT, "check", "stream.jsonl.gz")

with gzip.open(STREAM, "rt") as _f:
    CFG = json.loads(_f.readline())["config"]


def gun(ammo=12, cooldown=0.0, reload=0.0):
    return {"kind": "gun", "cooldown": cooldown, "ammo": ammo, "reload": reload, "stats": dict(CFG["weapons"]["gun"])}


def weapon(kind, cooldown=0.0, charge=0.0):
    return {"kind": kind, "cooldown": cooldown, "charge": charge, "stats": dict(CFG["weapons"][kind])}


def make_obs(pos, aim=(0.0, 0.0), mechs=(), weapons=None, energy=100.0, t=10.0, events=(), sounds=(),
             crates=(), pickups=(), zone=None):
    return {
        "type": "obs", "tick": int(t * 20), "t": t, "alive": 16,
        "self": {"id": 0, "pos": list(pos), "vel": [0, 0, 0], "aim": list(aim), "hp": 1400, "max_hp": 1400,
                 "energy": energy, "max_energy": 100, "grounded": True, "cubes": 0, "upgrades": [], "in_zone": True,
                 "weapons": weapons if weapons is not None else [gun(), None], "stats": dict(CFG["mech"])},
        "mechs": list(mechs), "projectiles": [], "crates": list(crates), "cubes": [], "pickups": list(pickups),
        "sounds": list(sounds), "beams": [], "events": list(events), "drops": [],
        "zone": zone or {"center": [0, 0], "radius": 5000, "next_center": [0, 0], "next_radius": 5000,
                         "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 0},
        "offer": None,
    }


def mech(id_, pos, vel=(0, 0, 0), hp=1400, weapons=("gun",), charging=False, aim=(0.0, 0.0), kind="mech"):
    m = {"id": id_, "kind": kind, "pos": list(pos), "vel": list(vel), "aim": list(aim), "hp": hp,
         "max_hp": 1400 if kind == "mech" else 350}
    if kind == "mech":
        m.update(cubes=0, weapons=list(weapons), charging=charging)
    return m


class Phase3Test(unittest.TestCase):
    """Phase 3 behaviour, always under the Phase 3 settings (preset p3), whatever ACTIVE is."""
    core: core_api.MapCore

    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("p3")

    def tearDown(self):
        tuning.use(self._saved)

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        g = cls.core.layer(core_api.LAYER_GROUND)
        c = cls.core
        clear = c.layer(core_api.LAYER_CLEARANCE)
        cls.open = [(c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
                    for k, v in enumerate(g) if v and clear[k] >= 6]

    def pos3(self, xy):
        return (xy[0], xy[1], self.core.floor_z(*xy))

    def pair(self, dist, clear: bool, seed=1):
        """Two open street spots `dist` apart with (clear=True) or without a clear chest-high shot."""
        rng = random.Random(seed)
        for _ in range(20000):
            a = rng.choice(self.open)
            ang = rng.uniform(0, 2 * math.pi)
            b = (a[0] + dist * math.cos(ang), a[1] + dist * math.sin(ang))
            if self.core.clearance(*b) < 3 or not self.core.is_ground(*b):
                continue
            pa, pb = self.pos3(a), self.pos3(b)
            f = self.core.shot_los((pa[0], pa[1], pa[2] + 7), (pb[0], pb[1], pb[2] + 4.5))
            if (f >= 1.0) == clear:
                return pa, pb
        self.fail("no suitable pair found")

    def lead_aim(self, me, tgt, vel=(0, 0, 0)):
        mz = [me[0], me[1], me[2] + CFG["mech"]["muzzle_height"]]
        sol = core_api.gun_lead(mz, [tgt[0], tgt[1], tgt[2] + 4.5], vel, 252.0, 3.0)
        return sol[0], sol[1]

    # ------------------------------------------------------------ gun gate

    def test_gun_fires_on_target_not_off_target(self):
        me, tg = self.pair(80, clear=True)
        c = Combat(CFG, self.core)
        aim = self.lead_aim(me, tg)
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": aim[0], "by": 5}]
        o = make_obs(me, aim, [mech(5, tg)], events=hit)
        c.observe(o)
        self.assertTrue(c.decide(o, (0, 0))["fire"][0])
        o2 = make_obs(me, (aim[0] + math.radians(5), aim[1]), [mech(5, tg)])
        self.assertFalse(c.decide(o2, (0, 0))["fire"][0])

    def test_gun_never_fires_into_wall(self):
        me, tg = self.pair(60, clear=False, seed=2)
        c = Combat(CFG, self.core)
        o = make_obs(me, self.lead_aim(me, tg), [mech(5, tg)])
        out = c.decide(o, (0, 0))
        self.assertFalse(out["fire"][0])

    def test_reload_when_idle_and_low(self):
        c = Combat(CFG, self.core)
        me = self.pos3(self.open[0])
        self.assertTrue(c.decide(make_obs(me, weapons=[gun(ammo=4), None], t=20), (1, 0))["reload"])
        self.assertFalse(c.decide(make_obs(me, weapons=[gun(ammo=10), None], t=20), (1, 0))["reload"])
        self.assertFalse(c.decide(make_obs(me, weapons=[gun(ammo=4, reload=1.0), None], t=20), (1, 0))["reload"])

    # ------------------------------------------------------------ engagement policy (Q1/Q3)

    def test_engagement_policy(self):
        c = Combat(CFG, self.core)
        me = (0.0, 0.0, 0.0)
        far = mech(5, (120, 0, 0))
        o = make_obs(me, mechs=[far])
        self.assertIsNone(c.engage_target(c.targets(o), 10.0, 230))                     # far, healthy, passive
        self.assertIsNotNone(c.engage_target(c.targets(make_obs(me, mechs=[mech(5, (50, 0, 0))])), 10.0, 230))  # near
        self.assertIsNotNone(c.engage_target(c.targets(make_obs(me, mechs=[mech(5, (120, 0, 0), hp=300)])), 10.0, 230))  # low hp
        c.observe(make_obs(me, events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]))
        self.assertIsNotNone(c.engage_target(c.targets(o), 10.0, 230))                  # hit us recently
        self.assertIsNone(c.engage_target(c.targets(o), 20.0, 230))                     # ...5 s ago is forgotten
        drone = mech(104, (20, 0, 0), kind="npc")
        self.assertIsNone(c.engage_target(c.targets(make_obs(me, mechs=[drone])), 30.0, 230))  # Q3: passive drone
        c.observe(make_obs(me, t=30.0, events=[{"type": "damaged", "amount": 25, "weapon": "npc", "bearing": 0.0, "by": 104}]))
        self.assertEqual(c.engage_target(c.targets(make_obs(me, mechs=[drone], t=30.0)), 30.0, 230).id, 104)

    # ------------------------------------------------------------ lightning

    def test_lightning_only_when_target_is_nearest_in_cone(self):
        me, tg = self.pair(30, clear=True, seed=3)
        c = Combat(CFG, self.core)
        aim = self.lead_aim(me, tg)
        ws = [gun(), weapon("lightning")]
        o = make_obs(me, aim, [mech(5, tg)], weapons=ws)
        self.assertTrue(c.decide(o, (0, 0))["fire"][1])
        # a drone closer, inside the cone: the arc would hit it instead (and aggro it)
        dz = (me[0] + (tg[0] - me[0]) * 0.5, me[1] + (tg[1] - me[1]) * 0.5, me[2])
        o = make_obs(me, aim, [mech(5, tg), mech(104, dz, kind="npc")], weapons=ws)
        if self.core.shot_los((me[0], me[1], me[2] + 7), (dz[0], dz[1], dz[2] + 1.75)) >= 1.0:
            self.assertFalse(c.decide(o, (0, 0))["fire"][1])
        # a crate closer in the cone blocks the arc too
        o = make_obs(me, aim, [mech(5, tg)], weapons=ws, crates=[{"id": 1001, "pos": list(dz), "hp": 300}])
        if self.core.shot_los((me[0], me[1], me[2] + 7), (dz[0], dz[1], dz[2] + 1.2)) >= 1.0:
            self.assertFalse(c.decide(o, (0, 0))["fire"][1])

    def test_lightning_energy_reserve(self):
        me, tg = self.pair(35, clear=True, seed=4)
        c = Combat(CFG, self.core)
        ws = [gun(), weapon("lightning")]
        aim = self.lead_aim(me, tg)
        self.assertFalse(c.decide(make_obs(me, aim, [mech(5, tg)], weapons=ws, energy=18), (0, 0))["fire"][1])
        me2, tg2 = self.pair(15, clear=True, seed=5)
        aim2 = self.lead_aim(me2, tg2)
        self.assertTrue(c.decide(make_obs(me2, aim2, [mech(5, tg2)], weapons=ws, energy=18), (0, 0))["fire"][1])

    # ------------------------------------------------------------ torso priority

    def test_torso_priority(self):
        c = Combat(CFG, self.core)
        me = self.pos3(self.open[10])
        # attacker we can't see: face its bearing
        c.observe(make_obs(me, events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 2.0, "by": 7}], t=10))
        self.assertAlmostEqual(c.decide(make_obs(me, t=10.5), (1, 0))["aim"][0], 2.0, places=3)
        # later: a nearby gunshot sound
        c.observe(make_obs(me, t=20, sounds=[{"kind": "gun", "bearing": -1.0, "dist": "near", "age": 0.1}]))
        self.assertAlmostEqual(c.decide(make_obs(me, t=20.2), (1, 0))["aim"][0], -1.0, places=3)
        # nothing: scan around the movement direction (east)
        yaw = c.decide(make_obs(me, t=40.0), (1, 0))["aim"][0]
        self.assertLessEqual(abs(wrap(yaw)), math.radians(50) + 1e-6)

    # ------------------------------------------------------------ Q2: weapon policy

    def test_laser_majority(self):
        c = Combat(CFG, self.core)
        me = (0.0, 0.0, 0.0)
        two_of_three = [mech(1, (50, 0, 0), weapons=["gun", "laser"]), mech(2, (60, 0, 0), weapons=["gun", "laser"]),
                        mech(3, (70, 0, 0), weapons=["gun"])]
        self.assertTrue(c.laser_majority(c.targets(make_obs(me, mechs=two_of_three)), 10))
        one_of_three = [mech(1, (50, 0, 0), weapons=["gun", "laser"]), mech(2, (60, 0, 0)), mech(3, (70, 0, 0))]
        self.assertFalse(c.laser_majority(c.targets(make_obs(me, mechs=one_of_three)), 10))
        far = [mech(1, (300, 0, 0), weapons=["gun", "laser"])]
        self.assertFalse(c.laser_majority(c.targets(make_obs(me, mechs=far)), 10))  # beyond 150 m
        c.observe(make_obs(me, t=10, sounds=[{"kind": "laser", "bearing": 1.0, "dist": "mid", "age": 0.1}]))
        self.assertTrue(c.laser_majority([], 10))                                   # heard, unseen

    def zone_r(self, r):
        z = Zone()
        z.update({"center": [0, 0], "radius": r, "next_center": [0, 0], "next_radius": r * 0.5,
                  "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 100}, 10.0)
        return z

    def test_pickup_policy(self):
        c = Combat(CFG, self.core)
        me = (0.0, 0.0, 0.0)
        lightning = {"id": 8001, "kind": "lightning", "pos": [10, 0, 0]}
        mortar = {"id": 8002, "kind": "mortar", "pos": [15, 0, 0]}
        laser = {"id": 8003, "kind": "laser", "pos": [5, 0, 0]}
        early, late = self.zone_r(300), self.zone_r(60)
        o = make_obs(me, pickups=[laser, lightning])
        self.assertEqual(c.wanted_pickup(o, [], early)["id"], 8001)                 # lightning, never laser
        o = make_obs(me, pickups=[laser])
        self.assertIsNone(c.wanted_pickup(o, [], early))
        held = [gun(), weapon("lightning")]
        o = make_obs(me, weapons=held, pickups=[mortar])
        self.assertIsNone(c.wanted_pickup(o, [], early))                            # mortar only late
        self.assertEqual(c.wanted_pickup(o, [], late)["id"], 8002)                  # late, all guards pass
        lasers = c.targets(make_obs(me, mechs=[mech(1, (90, 0, 0), weapons=["gun", "laser"])]))
        self.assertIsNone(c.wanted_pickup(o, lasers, late))                         # laser majority nearby
        close = c.targets(make_obs(me, mechs=[mech(1, (40, 0, 0))]))
        self.assertIsNone(c.wanted_pickup(o, close, late))                          # enemy within 50 m
        o = make_obs(me, weapons=[gun(), weapon("mortar")], pickups=[lightning])
        self.assertIsNone(c.wanted_pickup(o, [], late))                             # keep the late mortar
        self.assertEqual(c.wanted_pickup(o, [], early)["id"], 8001)                 # early: lightning first

    def test_take_action_swaps_into_slot_1(self):
        c = Combat(CFG, self.core)
        p = {"id": 8002, "kind": "mortar", "pos": [2, 0, 0]}
        self.assertEqual(c.take_action(make_obs((0, 0, 0), weapons=[gun(), weapon("lightning")]), p),
                         {"take": 8002, "drop": 1})
        self.assertEqual(c.take_action(make_obs((0, 0, 0), weapons=[gun(), None]), p), {"take": 8002})
        self.assertEqual(c.take_action(make_obs((0, 0, 0)), {"id": 1, "kind": "lightning", "pos": [9, 0, 0]}), {})

    def test_mortar_never_fires_near_us(self):
        me, tg = self.pair(9, clear=True, seed=6)
        c = Combat(CFG, self.core)
        ws = [gun(ammo=0, reload=1.0), weapon("mortar")]   # gun unusable -> mortar takes the torso
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]
        o = make_obs(me, mechs=[mech(5, tg)], weapons=ws, events=hit)
        c.observe(o)
        aim = c.decide(o, (0, 0), zone=self.zone_r(60))["aim"]
        o = make_obs(me, aim, [mech(5, tg)], weapons=ws)
        self.assertFalse(c.decide(o, (0, 0), zone=self.zone_r(60))["fire"][1])

    def test_mortar_fires_at_safe_range(self):
        me, tg = self.pair(90, clear=False, seed=7)          # behind cover: the gun has no shot
        c = Combat(CFG, self.core)
        ws = [gun(), weapon("mortar")]
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]
        o = make_obs(me, mechs=[mech(5, tg)], weapons=ws, events=hit)
        c.observe(o)
        fired = False
        aim = c.decide(o, (0, 0))["aim"]
        for _ in range(3):  # torso settles on the solution
            out = c.decide(make_obs(me, aim, [mech(5, tg)], weapons=ws), (0, 0))
            aim, fired = out["aim"], fired or out["fire"][1]
        self.assertTrue(fired)

    # ------------------------------------------------------------ simulated duel

    def test_duel_hit_rate_vs_strafing_mech(self):
        """Our torso slews at turn_rate; the gun follows its cooldown/mag/reload; bullets fly at 252 m/s
        with spread. The enemy strafes and reverses at random every 1-2.5 s (accel 58.5 m/s^2)."""
        rng = random.Random(11)
        m = CFG["mech"]
        g = CFG["weapons"]["gun"]
        c = Combat(CFG, None)            # open ground: no walls
        me = [0.0, 0.0, 0.0]
        aim = [0.0, 0.0]
        en = [80.0, 0.0, 0.0]
        ev = [0.0, 0.0]
        want = m["walk_speed"]
        switch_t = 0.0
        ammo, cd, rl = g["mag"], 0.0, 0.0
        bullets = []                    # [pos, vel, travelled]
        shots = hits = 0
        t, dt = 0.0, 0.05               # sim at 20 Hz; decide every 2 ticks
        last_act = {"aim": aim, "fire": [False, False]}
        c.last_hit_by[5] = 0.0
        for step in range(int(20 / dt)):
            if step % 2 == 0:
                c.last_hit_by[5] = t     # keep the duel "engaged" (it hit us)
                o = make_obs(me, aim, [mech(5, en, (ev[0], ev[1], 0))],
                             weapons=[{"kind": "gun", "cooldown": cd, "ammo": ammo, "reload": rl, "stats": dict(g)}, None], t=t)
                last_act = c.decide(o, (0, 0))
            # torso slew toward the commanded aim
            dy = wrap(last_act["aim"][0] - aim[0])
            aim[0] = wrap(aim[0] + max(-m["turn_rate"] * dt, min(m["turn_rate"] * dt, dy)))
            dp = last_act["aim"][1] - aim[1]
            aim[1] += max(-m["pitch_rate"] * dt, min(m["pitch_rate"] * dt, dp))
            # gun
            cd = max(0.0, cd - dt)
            if rl > 0:
                rl = max(0.0, rl - dt)
                if rl == 0:
                    ammo = g["mag"]
            if last_act["fire"][0] and cd == 0 and ammo > 0 and rl == 0:
                s = math.radians(g["spread_deg"])
                yaw, pitch = aim[0] + rng.gauss(0, s), aim[1] + rng.gauss(0, s)
                d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
                p0 = [me[0] + 3 * d[0], me[1] + 3 * d[1], me[2] + m["muzzle_height"] + 3 * d[2]]
                bullets.append([p0, [g["speed"] * d[i] for i in range(3)], 0.0])
                shots += 1
                ammo -= 1
                cd = g["cooldown"]
                if ammo == 0:
                    rl = g["reload"]
            # enemy strafing perpendicular to the line of fire
            if t >= switch_t:
                want = -want if rng.random() < 0.8 else 0.0 if want else m["walk_speed"]
                switch_t = t + rng.uniform(1.0, 2.5)
            acc = m["ground_accel"] * dt
            ev[1] += max(-acc, min(acc, want - ev[1]))
            en[1] += ev[1] * dt
            # bullets
            for b in bullets:
                for _ in range(5):
                    h = dt / 5
                    b[0] = [b[0][i] + b[1][i] * h for i in range(3)]
                    b[2] += g["speed"] * h
                    if math.hypot(b[0][0] - en[0], b[0][1] - en[1]) <= m["radius"] and en[2] <= b[0][2] <= en[2] + m["height"]:
                        hits += 1
                        b[2] = 1e9
                        break
            bullets = [b for b in bullets if b[2] < g["range"]]
            t += dt
        rate = hits / max(1, shots)
        if os.environ.get("MECH_VERBOSE"):
            print(f"duel: {hits}/{shots} hits ({rate:.0%}) in 20 s at 80 m")
        self.assertGreater(shots, 30, "the gate should let the gun fire in a duel")
        self.assertGreaterEqual(rate, 0.70, f"hit rate {rate:.2f} ({hits}/{shots})")

    # ------------------------------------------------------------ timing

    @unittest.skipIf(os.environ.get("MECH_SKIP_TIMING"), "timing skipped")
    def test_decide_timing(self):
        c = Combat(CFG, self.core)
        me, tg = self.pair(40, clear=True, seed=8)
        crates = [{"id": 1000 + k, "pos": [tg[0] + k, tg[1] - k, tg[2]], "hp": 300} for k in range(5)]
        ms = [mech(k, (tg[0] + 3 * k, tg[1] + 2 * k, tg[2]), weapons=["gun", "laser"]) for k in range(6)]
        o = make_obs(me, self.lead_aim(me, tg), ms, weapons=[gun(), weapon("lightning")], crates=crates)
        t0 = time.perf_counter()
        for _ in range(100):
            c.decide(o, (1, 0))
        self.assertLess((time.perf_counter() - t0) * 10, 2.0, "average decide() ms")


if __name__ == "__main__":
    unittest.main()
