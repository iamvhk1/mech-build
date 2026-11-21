"""Rooftop test (roadmap item 2): roof index, roof choice, climbing in the mini simulator, and the
ROOF strategy state (climb / hold / peek).

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
from navigation import Navigator  # noqa: E402
from roofs import MAX_HEIGHT_M, MIN_AREA_M2, MIN_HEIGHT_M, RoofIndex  # noqa: E402
from sim import MiniSim  # noqa: E402
from strategy import ROOF, Strategy  # noqa: E402
from test_phase3 import CFG, make_obs, mech  # noqa: E402
from threat import ThreatTracker  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


def zone(next_center=(-23.0, 2.0), next_r=380.0):
    z = Zone()
    z.update({"center": [41.3, -72.8], "radius": 560, "next_center": list(next_center), "next_radius": next_r,
              "shrink_start": 60, "shrink_end": 110, "dps": 20}, 5.0)
    return z


class RoofTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        cls.idx = RoofIndex(cls.core, CFG["mech"]["radius"], CFG["mech"]["step_up"])
        g = cls.core.layer(core_api.LAYER_GROUND)
        c = cls.core
        cls.street = [(c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res) for k, v in enumerate(g) if v]

    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("roof_camp")

    def tearDown(self):
        tuning.use(self._saved)

    def test_index(self):
        """Roofs are real roofs: big enough, standing on them is a building top, not the street."""
        self.assertGreater(len(self.idx.roofs), 50)
        for r in list(self.idx.roofs.values())[:30]:
            self.assertGreaterEqual(r.area, MIN_AREA_M2)
            self.assertFalse(self.core.is_ground(*r.core))
            self.assertAlmostEqual(self.core.floor_z(*r.core), r.floor, delta=1.5)
            self.assertIs(self.idx.roof_at((*r.core, r.floor)), r)
            self.assertIsNone(self.idx.roof_at((*r.core, r.floor - 10)))  # under it is not on it

    def test_choice_respects_zone_and_height(self):
        z = zone()
        rng = random.Random(2)
        for _ in range(10):
            start = rng.choice(self.street)
            r = self.idx.choose(z, start, 20.0)
            self.assertIsNotNone(r)
            self.assertTrue(MIN_HEIGHT_M <= r.height <= MAX_HEIGHT_M)
            self.assertGreaterEqual(z.depth(z.next_circle(), r.core), 12.0)
        self.assertIsNone(self.idx.choose(z, self.street[0], 3.0))  # can't climb anything with 3 m

    def test_climb_in_simulator(self):
        """Walk, jump and jet onto the chosen roof from random street spots."""
        z = zone()
        rng = random.Random(1)
        ok = 0
        for _ in range(5):
            start = rng.choice(self.street)
            roof = self.idx.choose(z, start, 20.0)
            sim = MiniSim(self.core, CFG, start)
            nav = Navigator(self.core, CFG)
            nav.allow_roofs = True
            nav.set_goal(roof.core)
            while sim.t < 90:
                sim.apply(nav.step(sim.obs()))
                on = self.idx.roof_at((sim.x, sim.y, sim.z))
                if on is not None and on.id == roof.id:
                    ok += 1
                    break
        self.assertGreaterEqual(ok, 4)

    def test_edge_toward(self):
        r = max(self.idx.roofs.values(), key=lambda r: r.area)
        far = (r.core[0] + 500, r.core[1])
        e = self.idx.edge_toward(r, far)
        self.assertIs(self.idx.roofs[self.idx.label[self.idx.cell(*e)]], r)
        self.assertGreater(e[0], r.core[0])                       # on the side facing the target
        self.assertLess(math.dist(e, far), math.dist(r.core, far))

    def test_strategy_climb_hold_peek(self):
        z = zone()
        tr = ThreatTracker()
        s = Strategy(CFG, self.core, z, tr, self.idx)
        start = self.street[len(self.street) // 2]
        o = make_obs((*start, self.core.floor_z(*start)), t=10.0)
        tr.update(o)
        d = s.update(o, False)
        self.assertEqual(d.state, ROOF)
        self.assertTrue(d.roofs)
        self.assertIn("climb", d.why)
        roof = s.roof
        on = (*roof.core, roof.floor)
        o = make_obs(on, t=11.0)
        tr.update(o)
        d = s.update(o, False)
        self.assertIn("hold", d.why)
        self.assertEqual(d.goal, roof.core)
        hunter = mech(5, (roof.core[0] + 90, roof.core[1], 0.0), aim=(math.pi, 0))
        o = make_obs(on, t=12.0, mechs=[hunter])
        tr.update(o)
        d = s.update(o, False)
        self.assertIn("peek", d.why)
        self.assertGreater(d.goal[0], roof.core[0])               # toward the hunter
        o = make_obs(on, t=13.0, mechs=[hunter])
        o["self"]["hp"] = 400                                      # hurt: stay back in the middle
        tr.update(o)
        self.assertIn("hold", s.update(o, False).why)
        o = make_obs(on, t=14.0)
        tr.update(o)
        self.assertNotEqual(s.update(o, True).state, ROOF)        # the zone comes first


if __name__ == "__main__":
    unittest.main()
