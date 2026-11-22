"""Stage C tests (C1 crates, C3 cubes): memory, safety rules, roof exclusion, stand-and-shoot,
combat gating, and an end-to-end mini-simulation (walk, shoot the crate, collect the cube).

    make -C core && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import os
import random
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_api  # noqa: E402
import tuning  # noqa: E402
from combat import Combat, wrap  # noqa: E402
from farm import Farmer, SHOOT_FROM_M  # noqa: E402
from navigation import Navigator  # noqa: E402
from sim import MiniSim  # noqa: E402
from test_phase3 import CFG, gun, make_obs, mech, weapon  # noqa: E402
from threat import ThreatTracker  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


def zone_big():
    z = Zone()
    z.update({"center": [0, 0], "radius": 5000, "next_center": [0, 0], "next_radius": 4000,
              "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 0}, 10.0)
    return z


class FarmTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        c = cls.core
        g = c.layer(core_api.LAYER_GROUND)
        clear = c.layer(core_api.LAYER_CLEARANCE)
        kind = c.layer(core_api.LAYER_KIND)
        xy = lambda k: (c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
        cls.open = [xy(k) for k, v in enumerate(g) if v and clear[k] >= 6]
        cls.roof = [xy(k) for k, v in enumerate(kind) if v == core_api.KIND_ROOF and clear[k] >= 3]

    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("crates")

    def tearDown(self):
        tuning.use(self._saved)

    def pos3(self, xy):
        return (xy[0], xy[1], self.core.floor_z(*xy))

    def crate(self, cid, xy, hp=300):
        return {"id": cid, "pos": list(self.pos3(xy)), "hp": hp}

    def pair_clear(self, dmin, dmax, seed=1):
        """Us and a crate spot on the street, dmin..dmax apart, with a clear shot."""
        rng = random.Random(seed)
        for _ in range(20000):
            a = rng.choice(self.open)
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(dmin, dmax)
            b = (a[0] + d * math.cos(ang), a[1] + d * math.sin(ang))
            if not self.core.is_ground(*b) or self.core.clearance(*b) < 3:
                continue
            pa, pb = self.pos3(a), self.pos3(b)
            if self.core.shot_los((pa[0], pa[1], pa[2] + 7), (pb[0], pb[1], pb[2] + 1.2)) >= 1.0:
                return pa, pb
        self.fail("no pair")

    def plan(self, f, obs, hunters=(), has_target=False, zone=None):
        tr = ThreatTracker()
        tr.update(obs)
        return f.plan(obs, zone or zone_big(), list(hunters) or tr.hunters(obs["self"]["pos"]), tr, has_target)

    # ------------------------------------------------------------ memory and choice

    def test_remembers_and_forgets_crates(self):
        me, c = self.pair_clear(60, 80, seed=2)
        f = Farmer(self.core, CFG)
        f.observe(make_obs(me, crates=[self.crate(1001, c[:2])]))
        self.assertIn(1001, f.crates)
        f.observe(make_obs(me))                       # beyond proximity range, not listed: remembered
        self.assertIn(1001, f.crates)
        me2, c2 = self.pair_clear(20, 40, seed=3)
        f2 = Farmer(self.core, CFG)
        f2.observe(make_obs(me2, crates=[self.crate(1002, c2[:2])]))
        f2.observe(make_obs(me2))                     # within 45 m, clear line, not listed: gone
        self.assertNotIn(1002, f2.crates)

    def test_cube_at_crate_spot_means_crate_destroyed(self):
        me, c = self.pair_clear(60, 80, seed=8)
        f = Farmer(self.core, CFG)
        f.observe(make_obs(me, crates=[self.crate(1001, c[:2])]))
        o = make_obs(me)
        o["cubes"] = [{"id": 5001, "pos": list(c)}]
        f.observe(o)
        self.assertNotIn(1001, f.crates)

    def test_roof_crates_excluded(self):
        f = Farmer(self.core, CFG)
        r = self.roof[len(self.roof) // 2]
        self.assertFalse(f.on_street(self.pos3(r)))
        self.assertTrue(f.on_street(self.pos3(self.open[50])))

    def test_safety_rules(self):
        me, c = self.pair_clear(30, 60, seed=3)
        f = Farmer(self.core, CFG)
        o = make_obs(me, crates=[self.crate(1001, c[:2])])
        f.observe(o)
        self.assertIsNotNone(self.plan(f, o))
        self.assertIsNone(self.plan(f, o, has_target=True))       # a mech to fight comes first
        hurt = make_obs(me, crates=[self.crate(1001, c[:2])])
        hurt["self"]["hp"] = 700                                  # 50% < 60%
        self.assertIsNone(self.plan(f, hurt))
        hunter = make_obs(me, crates=[self.crate(1001, c[:2])],
                          mechs=[mech(5, (me[0] + 80, me[1], me[2]), aim=(math.pi, 0))])
        self.assertIsNone(self.plan(f, hunter))                   # hunter within 120 m
        z = Zone()                                                 # zone edge reaches the crate soon
        z.update({"center": [me[0], me[1]], "radius": 500, "next_center": [me[0] + 400, me[1]],
                  "next_radius": 1, "shrink_start": 10.0, "shrink_end": 12.0, "dps": 20}, 10.0)
        self.assertIsNone(self.plan(f, o, zone=z))

    def test_stand_and_shoot_when_close(self):
        me, c = self.pair_clear(8, SHOOT_FROM_M - 2, seed=4)
        f = Farmer(self.core, CFG)
        o = make_obs(me, crates=[self.crate(1001, c[:2])])
        f.observe(o)
        self.assertEqual(self.plan(f, o), (me[0], me[1]))         # don't walk into it

    def test_cube_rules(self):
        me, c = self.pair_clear(20, 40, seed=5)
        f = Farmer(self.core, CFG)
        o = make_obs(me, crates=[self.crate(1001, c[:2])])
        f.observe(o)
        self.plan(f, o)                                           # we're shooting crate 1001
        far_cube = (me[0] - (c[0] - me[0]), me[1] - (c[1] - me[1]))
        cubes = [{"id": 5001, "pos": list(c)}]
        if self.core.is_ground(*far_cube):
            cubes.append({"id": 5002, "pos": list(self.pos3(far_cube))})
        o2 = make_obs(me)
        o2["cubes"] = cubes                                       # crate gone, its cube appeared
        f.observe(o2)
        self.assertEqual(self.plan(f, o2), (c[0], c[1]))          # C1: collect our crate's cube
        if len(cubes) > 1:
            f.cubes.pop(5001)
            o3 = make_obs(me)
            o3["cubes"] = cubes[1:]
            self.assertIsNone(self.plan(f, o3))                   # C1 ignores other cubes...
            tuning.SETTINGS["farm.cubes"] = True                  # (restored by tearDown)
            self.assertIsNotNone(self.plan(f, o3))                # ...C3 collects them

    def test_cubes_preset_active(self):
        tuning.use("cubes")
        try:
            self.assertTrue(tuning.get("farm.cubes"))
            self.assertTrue(tuning.get("farm.crates"))
            self.assertTrue(tuning.get("fight.strafe"))
            self.assertEqual(tuning.get("retreat.hp_enter"), 0.35)
        finally:
            tuning.use(tuning.ACTIVE)

    def test_upgrade_first_preset(self):
        tuning.use("upgrade_first")
        try:
            self.assertEqual(tuning.get("upgrades"), "first")
            self.assertTrue(tuning.get("farm.cubes"))
            self.assertTrue(tuning.get("farm.crates"))
            self.assertTrue(tuning.get("fight.strafe"))
        finally:
            tuning.use(tuning.ACTIVE)

    def test_drones_preset_active(self):
        tuning.use("drones")
        try:
            self.assertTrue(tuning.get("farm.drones"))
            self.assertTrue(tuning.get("farm.cubes"))
            self.assertTrue(tuning.get("farm.crates"))
            self.assertTrue(tuning.get("fight.strafe"))
            self.assertEqual(tuning.get("farm.drone_min_hp"), 0.90)
            self.assertEqual(tuning.get("farm.drone_dist_min"), 30.0)
            self.assertEqual(tuning.get("farm.drone_dist_max"), 50.0)
        finally:
            tuning.use(tuning.ACTIVE)

    def test_drone_farming_rules(self):
        me, d = self.pair_clear(35, 45, seed=12)
        f = Farmer(self.core, CFG)
        drone_obs = mech(104, (d[0], d[1], d[2]), kind="npc", hp=350)
        o = make_obs(me, mechs=[drone_obs])
        f.observe(o)
        tuning.SETTINGS["farm.drones"] = True
        # At full HP with no threats, we target the drone and stand to shoot (within 30-50m)
        self.assertEqual(self.plan(f, o), (me[0], me[1]))
        self.assertEqual(f.mode, "drone 104")

        # Below 90% HP (e.g. 85%), drone farming is disallowed
        hurt = make_obs(me, mechs=[drone_obs])
        hurt["self"]["hp"] = int(CFG["mech"]["hp"] * 0.85)
        self.assertIsNone(self.plan(f, hurt))

        # Hunter within 120m blocks drone farming
        hunter = make_obs(me, mechs=[drone_obs, mech(5, (me[0] + 80, me[1], me[2]))])
        self.assertIsNone(self.plan(f, hunter))

        # A player mech in combat takes priority (has_target=True)
        self.assertIsNone(self.plan(f, o, has_target=True))

    def test_drone_target_follows_the_drone(self):
        """Audit A3: the chosen drone's position is refreshed every observation, not frozen."""
        me, d = self.pair_clear(35, 45, seed=12)
        f = Farmer(self.core, CFG)
        tuning.SETTINGS["farm.drones"] = True
        o = make_obs(me, mechs=[mech(104, (d[0], d[1], d[2]), kind="npc", hp=350)])
        f.observe(o)
        self.plan(f, o)
        self.assertIsNotNone(f.target_drone)
        moved = (d[0] + 4.0, d[1] - 3.0, d[2])
        o2 = make_obs(me, mechs=[mech(104, moved, kind="npc", hp=350)])
        o2["t"] = o["t"] + 1.0
        f.observe(o2)
        self.plan(f, o2)
        self.assertEqual(tuple(f.target_drone.pos[:2]), moved[:2])

    def test_combat_engages_farmed_drone(self):
        me, d = self.pair_clear(35, 45, seed=13)
        cb = Combat(CFG, self.core)
        drone = mech(104, (d[0], d[1], d[2]), kind="npc", hp=350)
        ws = [gun(), weapon("lightning")]
        # When target_drone_id is passed, combat aims gun at drone and never lightning
        out = cb.decide(make_obs(me, mechs=[drone], weapons=ws), (0, 0), target_drone_id=104)
        self.assertIn("engage 104", cb.debug)
        self.assertFalse(out["fire"][1])  # lightning never fired at NPC

    # ------------------------------------------------------------ combat gating

    def test_combat_shoots_crate_only_without_mech_target(self):
        me, c = self.pair_clear(20, 40, seed=6)
        cb = Combat(CFG, self.core)
        aim_pt = [c[0], c[1], c[2] + 1.2]
        mz = [me[0], me[1], me[2] + CFG["mech"]["muzzle_height"]]
        yaw = math.atan2(aim_pt[1] - mz[1], aim_pt[0] - mz[0])
        pitch = math.atan2(aim_pt[2] - mz[2], math.dist(aim_pt[:2], mz[:2]))
        ws = [gun(), weapon("lightning")]
        out = cb.decide(make_obs(me, (yaw, pitch), weapons=ws), (0, 0), farm_aim=aim_pt)
        self.assertTrue(out["fire"][0])
        self.assertFalse(out["fire"][1])                          # never lightning on crates
        self.assertEqual(cb.debug, "shoot crate")
        # a mech within 60 m takes priority over the crate
        m = mech(5, (me[0] + 30, me[1] + 30, me[2]))
        cb.decide(make_obs(me, (yaw, pitch), mechs=[m], weapons=ws), (0, 0), farm_aim=aim_pt)
        self.assertEqual(cb.debug, "engage 5")
        # off target: no fire
        out = cb.decide(make_obs(me, (yaw + 0.3, pitch), weapons=ws), (0, 0), farm_aim=aim_pt)
        self.assertFalse(out["fire"][0])

    def test_no_crate_shot_beyond_60m(self):
        me, c = self.pair_clear(70, 90, seed=7)
        cb = Combat(CFG, self.core)
        aim_pt = [c[0], c[1], c[2] + 1.2]
        mz = [me[0], me[1], me[2] + CFG["mech"]["muzzle_height"]]
        yaw = math.atan2(aim_pt[1] - mz[1], aim_pt[0] - mz[0])
        pitch = math.atan2(aim_pt[2] - mz[2], math.dist(aim_pt[:2], mz[:2]))
        self.assertFalse(cb.decide(make_obs(me, (yaw, pitch)), (0, 0), farm_aim=aim_pt)["fire"][0])

    # ------------------------------------------------------------ end to end

    def test_end_to_end_crate_to_cube(self):
        """Walk, shoot the crate (gun timing and torso slew simulated), collect its cube."""
        rng = random.Random(11)
        ok = trials = 0
        m = CFG["mech"]
        g = CFG["weapons"]["gun"]
        while trials < 12:
            me, c = self.pair_clear(25, 70, seed=rng.randrange(10 ** 6))
            trials += 1
            sim = MiniSim(self.core, CFG, me[:2])
            nav = Navigator(self.core, CFG)
            f = Farmer(self.core, CFG)
            cb = Combat(CFG, self.core)
            aim = [0.0, 0.0]
            ammo, cd, rl = g["mag"], 0.0, 0.0
            crate_hp = 300.0
            cube = None
            done = False
            for step in range(int(40 / 0.05)):
                t = step * 0.05
                if step % 2 == 0:
                    o = sim.obs()
                    o["t"] = t
                    o["self"]["aim"] = list(aim)
                    o["self"]["weapons"] = [{"kind": "gun", "cooldown": cd, "ammo": ammo, "reload": rl, "stats": dict(g)}, None]
                    if crate_hp > 0:
                        o["crates"] = [{"id": 1001, "pos": list(c), "hp": crate_hp}]
                    if cube is not None:
                        o["cubes"] = [{"id": 5001, "pos": list(cube)}]
                    f.observe(o)
                    tr = ThreatTracker()
                    tr.update(o)
                    goal = f.plan(o, zone_big(), [], tr, False)
                    if goal is not None:
                        nav.set_goal(goal)
                    mv = nav.step(o)
                    act = cb.decide(o, mv["move"], [], None, farm_aim=f.crate_aim())
                    act.update(mv)
                sim.apply({k: act.get(k) for k in ("move", "boost", "jump")}, 0.05)
                dy = wrap(act["aim"][0] - aim[0])
                aim[0] = wrap(aim[0] + max(-m["turn_rate"] * 0.05, min(m["turn_rate"] * 0.05, dy)))
                aim[1] += max(-m["pitch_rate"] * 0.05, min(m["pitch_rate"] * 0.05, act["aim"][1] - aim[1]))
                cd = max(0.0, cd - 0.05)
                if rl > 0:
                    rl = max(0.0, rl - 0.05)
                    if rl == 0:
                        ammo = g["mag"]
                if act["fire"][0] and cd == 0 and ammo > 0 and rl == 0:
                    ammo -= 1
                    cd = g["cooldown"]
                    if ammo == 0:
                        rl = g["reload"]
                    if crate_hp > 0:
                        crate_hp -= g["damage"]
                        if crate_hp <= 0:
                            cube = list(c)
                if cube is not None and math.dist((sim.x, sim.y), cube[:2]) <= CFG["cubes"]["pickup_radius"]:
                    done = True
                    break
            ok += done
        self.assertGreaterEqual(ok, trials - 2, f"{ok}/{trials} collected")


if __name__ == "__main__":
    unittest.main()
