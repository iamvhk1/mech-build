"""Arm up early (arm.early, arm.py): walk to a remembered lightning while slot 1 is empty."""
from __future__ import annotations

import math
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuning  # noqa: E402
from arm import Armer  # noqa: E402
from test_phase3 import CFG, gun, make_obs, mech  # noqa: E402
from threat import ThreatTracker  # noqa: E402


def pk(pid, kind, xy):
    return {"id": pid, "kind": kind, "pos": [xy[0], xy[1], 0.0]}


class ArmTest(unittest.TestCase):
    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("arm")
        self.a = Armer(None, CFG, None)
        self.th = ThreatTracker()

    def tearDown(self):
        tuning.use(self._saved)

    def plan(self, o):
        self.th.update(o)
        return self.a.plan(o, None, self.th.hunters(o["self"]["pos"]), self.th, 11.7)

    def test_best_includes_arm(self):
        """Since run D1 (4.05), best arms up; the arm preset is the same bot."""
        self.assertTrue(tuning._resolve("best")["arm.early"])
        self.assertEqual(tuning._resolve("arm"), tuning._resolve("best"))

    def test_remembers_a_far_lightning_and_goes_for_it(self):
        o = make_obs((0, 0, 0), t=5.0, pickups=[pk(8001, "lightning", (150, 0)), pk(8002, "laser", (30, 0))])
        self.a.observe(o)
        o2 = make_obs((5, 0, 0), t=6.0)  # out of view now, still remembered
        self.a.observe(o2)
        p = self.plan(o2)
        self.assertIsNotNone(p)
        self.assertEqual(p["id"], 8001)
        self.assertTrue(self.a.mode.startswith("arm lightning"))

    def test_nearest_lightning_within_reach(self):
        o = make_obs((0, 0, 0), t=5.0, pickups=[pk(8001, "lightning", (180, 0)), pk(8003, "lightning", (90, 40)),
                                                 pk(8004, "lightning", (260, 0))])
        self.a.observe(o)
        self.assertEqual(self.plan(o)["id"], 8003)

    def test_not_when_slot1_full_or_hunter_close_or_switch_off(self):
        o = make_obs((0, 0, 0), t=5.0, pickups=[pk(8001, "lightning", (100, 0))],
                     weapons=[gun(), {"kind": "mortar", "cooldown": 0.0, "stats": {}}])
        self.a.observe(o)
        self.assertIsNone(self.plan(o))
        hunted = make_obs((0, 0, 0), t=6.0, mechs=[mech(5, (30, 0, 0), aim=(math.pi, 0.0))])
        self.a.observe(hunted)
        self.assertIsNone(self.plan(hunted))
        tuning.use("pacing_loot")  # arm.early off
        self.assertIsNone(self.plan(make_obs((0, 0, 0), t=7.0)))

    def test_forgets_a_taken_pickup(self):
        o = make_obs((0, 0, 0), t=5.0, pickups=[pk(8001, "lightning", (100, 0))])
        self.a.observe(o)
        near = make_obs((90, 0, 0), t=15.0)  # we're there and it's gone: someone took it
        self.a.observe(near)
        self.assertIsNone(self.plan(near))
        o3 = make_obs((0, 0, 0), t=16.0, pickups=[pk(8002, "lightning", (60, 0))])
        self.a.observe(o3)
        self.a.observe(make_obs((0, 0, 0), t=17.0, events=[{"type": "took", "id": 8002, "kind": "lightning", "slot": 1}]))
        self.assertNotIn(8002, self.a.known)

    def test_keeps_its_target_a_bit_past_max_dist(self):
        o = make_obs((0, 0, 0), t=5.0, pickups=[pk(8001, "lightning", (190, 0))])
        self.a.observe(o)
        self.assertIsNotNone(self.plan(o))
        o2 = make_obs((-30, 0, 0), t=6.0)  # now 220 m away: still the target (no flicker)
        self.a.observe(o2)
        self.assertIsNotNone(self.plan(o2))


if __name__ == "__main__":
    unittest.main()
