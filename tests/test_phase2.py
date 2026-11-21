"""Phase 2 tests: zone model, destination choice, jump/drop edges, headroom, and navigation driven
end to end through a crude movement simulator (tests/sim.py).

    make -C core && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import gzip
import json
import math
import os
import random
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_api  # noqa: E402
from navigation import Navigator, boost_policy  # noqa: E402
from sim import MiniSim  # noqa: E402
from zone import Zone, choose_destination, rotation_target  # noqa: E402

ARENA = os.path.join(ROOT, "arena")
STREAM = os.path.join(ROOT, "check", "stream.jsonl.gz")
FIELD = (-276.31, 128.71)   # Ohio Stadium field centre (world.json stadium.center)
STREET = (-150.0, 60.0)


def zone_obs(center, radius, nxt, nradius, ss, se, dps=20):
    return {"center": list(center), "radius": radius, "next_center": list(nxt), "next_radius": nradius,
            "shrink_start": ss, "shrink_end": se, "dps": dps}


class ZoneTest(unittest.TestCase):
    """Pure zone math (no core needed)."""

    def test_hold_then_linear_shrink(self):
        z = Zone()
        z.update(zone_obs((0, 0), 500, (100, 0), 300, 60, 110), t=10)
        self.assertEqual(z.circle_at(30), (0, 0, 500))
        cx, cy, r = z.circle_at(85)  # halfway
        self.assertAlmostEqual(cx, 50)
        self.assertAlmostEqual(r, 400)
        self.assertEqual(z.circle_at(200), (100, 0, 300))

    def test_time_until_outside(self):
        z = Zone()
        z.update(zone_obs((0, 0), 500, (0, 0), 300, 60, 110), t=10)
        self.assertEqual(z.time_until_outside((0, 0)), math.inf)        # inside the next circle
        self.assertEqual(z.time_until_outside((600, 0)), 0.0)           # already outside
        tl = z.time_until_outside((400, 0))                              # edge passes r=400 at t=85
        self.assertAlmostEqual(tl, 75.0, delta=0.6)

    def test_live_vs_static_reporting_during_shrink(self):
        # live reporting: radius moves each observation
        z = Zone()
        z.update(zone_obs((0, 0), 440, (0, 0), 300, 60, 110), t=70)
        z.update(zone_obs((0, 0), 436, (0, 0), 300, 60, 110), t=71)
        self.assertFalse(z.static_during_shrink)
        self.assertAlmostEqual(z.circle_at(110)[2], 300)
        self.assertAlmostEqual(z.current()[2], 436)
        # static reporting: radius stays at the shrink's starting value
        s = Zone()
        s.update(zone_obs((0, 0), 500, (0, 0), 300, 60, 110), t=70)
        s.update(zone_obs((0, 0), 500, (0, 0), 300, 60, 110), t=71)
        self.assertTrue(s.static_during_shrink)
        self.assertAlmostEqual(s.current()[2], 500 - 200 * 11 / 50)

    def test_rotation_target_inside_next_circle(self):
        z = Zone()
        z.update(zone_obs((0, 0), 500, (100, 0), 200, 60, 110), t=10)
        (tx, ty), margin = rotation_target(z, (400, 0))
        self.assertAlmostEqual(math.hypot(tx - 100, ty), 200 - margin)
        self.assertGreater(tx, 100)                                      # on our side
        (sx, sy), _ = rotation_target(z, (110, 5))                       # already deep inside: stay
        self.assertEqual((sx, sy), (110, 5))
        z.update(zone_obs((0, 0), 25, (3, 4), 0, 60, 110), t=10)        # final circle: centre
        self.assertEqual(rotation_target(z, (20, 0))[0], (3, 4))

    def test_boost_policy(self):
        me = {"energy": 80}
        self.assertTrue(boost_policy(me, False, 0, 10))       # outside: boost
        self.assertFalse(boost_policy(me, True, 100, 10))     # plenty of time: walk
        self.assertTrue(boost_policy(me, True, 10, 10))       # late: boost
        self.assertFalse(boost_policy({"energy": 20}, True, 10, 10))  # late but keep the jump reserve


class NavTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        with gzip.open(STREAM, "rt") as f:
            cls.cfg = json.loads(f.readline())["config"]
        cls.core = core_api.MapCore.from_dir(ARENA, cls.cfg)
        g = cls.core.layer(core_api.LAYER_GROUND)
        cls.ground = [k for k, v in enumerate(g) if v]
        cls.r = cls.cfg["mech"]["radius"]

    def cell(self, k):
        c = self.core
        return c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res

    def drive(self, start, goal, max_s=90.0):
        sim = MiniSim(self.core, self.cfg, start)
        nav = Navigator(self.core, self.cfg)
        nav.set_goal(goal)
        jumps = 0
        while sim.t < max_s:
            mv = nav.step(sim.obs())
            jumps += bool(mv.get("jump"))
            sim.apply(mv)
            if math.dist((sim.x, sim.y), goal) < 4.0:
                return True, sim, jumps
        return False, sim, jumps

    # ------------------------------------------------------------ core: jump/drop edges, headroom

    def test_stadium_exit_and_entry(self):
        """The bowl is sealed by >= 10 m walls: leaving works on foot (up the stands, off the edge),
        entering needs a jump. Walking-only plans must never claim to reach the field."""
        out = self.core.find_path_ex(FIELD, STREET, self.r)
        self.assertTrue(out and math.dist(out[-1][:2], STREET) < 3)
        walk_in = self.core.find_path_ex(STREET, FIELD, self.r)
        self.assertTrue(walk_in is None or math.dist(walk_in[-1][:2], FIELD) > 50)
        jump_in = self.core.find_path_ex(STREET, FIELD, self.r, max_jump_rise=14)
        self.assertTrue(jump_in and math.dist(jump_in[-1][:2], FIELD) < 3)
        self.assertTrue(any(k == core_api.JUMP for _, _, k in jump_in))

    def test_no_jumps_onto_roofs(self):
        """Rooftops are a later iteration: a goal on a roof snaps to the street even with jumps."""
        with open(os.path.join(ARENA, "v2", "world.json")) as f:
            world = json.load(f)
        rng = random.Random(3)
        n = 0
        for p in world["prisms"]:
            if p["kind"] != "building":
                continue
            xs, ys = p["ring"][0::2], p["ring"][1::2]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            f = self.core.floor_z(cx, cy)
            if not (3.0 < f - self.core.ground_z(cx, cy) < 12.0):
                continue  # low roofs are the ones a jump could reach
            start = self.cell(rng.choice(self.ground))
            path = self.core.find_path_ex(start, (cx, cy), self.r, max_jump_rise=14)
            if path:
                for x, y, _ in path:
                    self.assertLess(self.core.floor_z(x, y) - self.core.ground_z(x, y), 3.0,
                                    f"path onto roof at {(x, y)}")
            n += 1
            if n >= 10:
                break
        self.assertGreater(n, 3)

    def test_headroom_blocks_grown_mech_under_bridge(self):
        """A mech grown by cubes must not plan under a bridge it no longer fits beneath."""
        with open(os.path.join(ARENA, "v2", "world.json")) as f:
            world = json.load(f)
        checked = 0
        for p in world["prisms"]:
            if p["kind"] != "bridge":
                continue
            xs, ys = p["ring"][0::2], p["ring"][1::2]
            x, y = sum(xs) / len(xs), sum(ys) / len(ys)
            head = p["base"] - self.core.floor_z(x, y)
            if not (self.cfg["mech"]["height"] < head < 30) or self.core.clearance(x, y) < self.r:
                continue
            a, b = (x - 1, y), (x + 1, y)
            self.assertTrue(self.core.segment_walkable(a, b, self.r, head - 0.5))
            self.assertFalse(self.core.segment_walkable(a, b, self.r, head + 0.5))
            checked += 1
        self.assertGreater(checked, 0)

    # ------------------------------------------------------------ destination

    def test_destination_inside_next_circle_and_walkable(self):
        rng = random.Random(4)
        for _ in range(20):
            c = self.cell(rng.choice(self.ground))
            nr = rng.choice([240, 140, 70, 25])
            z = Zone()
            z.update(zone_obs(c, nr * 1.6, c, nr, 60, 110), t=10)
            pos = self.cell(rng.choice(self.ground))
            d = choose_destination(self.core, z, (*pos, 0), self.r)
            self.assertIsNotNone(d)
            self.assertGreaterEqual(self.core.clearance(*d) + 1e-6, self.r)
            self.assertTrue(self.core.is_ground(*d))
            self.assertLess(math.dist(d, c), nr + 1e-6, "destination outside the next circle")

    # ------------------------------------------------------------ end to end (mini simulator)

    def test_navigator_reaches_street_destinations(self):
        rng = random.Random(6)
        trials, ok = 30, 0
        fails = []
        for _ in range(trials):
            while True:
                a, b = self.cell(rng.choice(self.ground)), self.cell(rng.choice(self.ground))
                if 60 < math.dist(a, b) < 250:
                    break
            reached, sim, _ = self.drive(a, b)
            ok += reached
            if not reached:
                fails.append((a, b, (round(sim.x), round(sim.y))))
        self.assertGreaterEqual(ok, trials - 2, f"{trials - ok} failures, e.g. {fails[:3]}")

    def test_navigator_jumps_into_stadium(self):
        reached, sim, jumps = self.drive(STREET, FIELD, max_s=90)
        self.assertTrue(reached, f"ended at {(round(sim.x), round(sim.y), round(sim.z, 1))}")
        self.assertGreater(jumps, 0)

    def test_navigator_unsticks(self):
        """Commanding movement without moving escalates: hop, sidestep, replan."""
        nav = Navigator(self.core, self.cfg)
        start = self.cell(self.ground[len(self.ground) // 3])
        nav.set_goal((start[0] + 80, start[1]))
        sim = MiniSim(self.core, self.cfg, start)
        levels, jumped = set(), False
        for _ in range(60):
            mv = nav.step(sim.obs())
            jumped |= bool(mv.get("jump"))
            levels.add(nav.stuck_level)
            sim.t += 0.1   # the mech is pinned in place
            sim.tick += 2
        self.assertTrue({1, 2, 3} <= levels, levels)
        self.assertTrue(jumped)


if __name__ == "__main__":
    unittest.main()
