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
        """Since run D1 (4.05), best arms up; since D2 (4.19) it also presses."""
        b = tuning._resolve("best")
        self.assertTrue(b["arm.early"] and b["fight.press"])
        self.assertEqual({k: v for k, v in tuning._resolve("arm").items() if v != b[k]},
                         {"fight.press": False, "arm.laser_after": None})
        self.assertEqual(tuning._resolve("laser"), b)  # since run D3 (4.46) best has the laser fallback

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


class LaserTest(unittest.TestCase):
    """D3: laser fallback (arm.laser_after) and the laser aim fix in combat.laser_trigger."""

    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("laser")
        self.a = Armer(None, CFG, None)
        self.th = ThreatTracker()

    def tearDown(self):
        tuning.use(self._saved)

    def plan(self, o):
        self.th.update(o)
        return self.a.plan(o, None, self.th.hunters(o["self"]["pos"]), self.th, 11.7)

    def test_takes_a_laser_only_after_the_wait_and_without_lightning(self):
        o = make_obs((0, 0, 0), t=10.0, pickups=[pk(8001, "laser", (100, 0))])
        self.a.observe(o)
        self.assertIsNone(self.plan(o))  # before 45 s: keep looking for lightning
        o2 = make_obs((0, 0, 0), t=50.0)
        self.a.observe(o2)
        self.assertEqual(self.plan(o2)["id"], 8001)
        o3 = make_obs((0, 0, 0), t=51.0, pickups=[pk(8002, "lightning", (150, 0))])
        self.a.observe(o3)
        self.assertEqual(self.plan(o3)["id"], 8002)  # lightning wins when one is within reach

    def test_with_a_laser_still_goes_for_lightning_but_not_while_charging(self):
        laser = {"kind": "laser", "cooldown": 0.0, "charge": 0.0, "stats": dict(CFG["weapons"]["laser"])}
        o = make_obs((0, 0, 0), t=60.0, weapons=[gun(), laser], pickups=[pk(8002, "lightning", (120, 0))])
        self.a.observe(o)
        self.assertEqual(self.plan(o)["id"], 8002)
        charging = dict(laser, charge=0.3)
        o2 = make_obs((0, 0, 0), t=61.0, weapons=[gun(), charging])
        self.a.observe(o2)
        self.assertIsNone(self.plan(o2))

    def test_laser_aims_straight_at_a_moving_target_and_releases_on_it(self):
        from combat import Combat, yaw_pitch
        c = Combat(CFG, None)
        target = c.targets(make_obs((0, 0, 0), mechs=[mech(5, (60, 0, 0), vel=(0, 10, 0))]))[0]
        muzzle = [0.0, 0.0, 7.0]
        aim_pt = list(target.center)
        w = {"kind": "laser", "cooldown": 0.0, "charge": 0.0, "stats": dict(CFG["weapons"]["laser"])}
        hold, aim = c.laser_trigger(w, target, aim_pt, 0.3, 0.0, [target], muzzle)
        self.assertTrue(hold)          # start charging
        self.assertIsNone(aim)         # the gun keeps its lead aim while charging
        charged = dict(w, charge=0.7)
        yaw, pitch = yaw_pitch(muzzle, aim_pt)
        hold, aim = c.laser_trigger(charged, target, aim_pt, yaw + 0.05, pitch, [target], muzzle)
        self.assertTrue(hold)          # charged but off target (e.g. on the gun lead): keep holding
        self.assertAlmostEqual(aim[0], yaw, places=6)  # aim straight at it, no lead
        hold, _ = c.laser_trigger(charged, target, aim_pt, yaw, pitch, [target], muzzle)
        self.assertFalse(hold)         # on target: let go, the beam fires

if __name__ == "__main__":
    unittest.main()
