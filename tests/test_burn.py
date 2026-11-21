"""Tests for Stage E: Final-burn positioning (E4, run Z1)."""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_api  # noqa: E402
import tuning  # noqa: E402
from strategy import Strategy, BURN, ROTATE, RETREAT  # noqa: E402
from test_phase3 import CFG, make_obs, mech  # noqa: E402
from threat import ThreatTracker  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


class BurnTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)

    def setUp(self):
        self._saved_preset = tuning.ACTIVE
        tuning.use("burn")

    def tearDown(self):
        tuning.use(self._saved_preset)

    def _zone(self, radius=560.0, next_radius=380.0, center=(0.0, 0.0), next_center=(10.0, 20.0), dps=20.0):
        z = Zone()
        z.update({"center": list(center), "radius": radius,
                  "next_center": list(next_center), "next_radius": next_radius,
                  "shrink_start": 60, "shrink_end": 110, "dps": dps}, 10.0)
        return z

    def test_burn_preset_keys(self):
        self.assertIn("burn", tuning.PRESETS)
        self.assertTrue(tuning.PRESETS["burn"]["burn.enabled"])
        self.assertIn("burn.enabled", tuning.DEFAULTS)
        self.assertIn("burn.radius", tuning.DEFAULTS)
        self.assertEqual(tuning.get("burn.radius"), 25.0)

    def test_burn_inactive_when_tuning_off(self):
        tuning.use("best")  # burn.enabled is False
        z = self._zone(radius=70.0, next_radius=20.0, dps=160.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((0, 0, 0))
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, ROTATE)
        self.assertFalse(dec.why.startswith("burn"))

    def test_burn_inactive_in_early_game(self):
        z = self._zone(radius=560.0, next_radius=380.0, dps=20.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((0, 0, 0))
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, ROTATE)

    def test_burn_activates_in_late_circle(self):
        # next_radius <= 25.0 triggers BURN
        center = (15.0, 25.0)
        z = self._zone(radius=60.0, next_radius=25.0, next_center=center, dps=160.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((-50.0, -50.0, 0.0))
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, BURN)
        self.assertFalse(dec.retreat)
        self.assertIn("burn", dec.why)
        # Goal is near center
        self.assertIsNotNone(dec.goal)

    def test_burn_activates_on_high_dps_late_circle(self):
        # radius <= 70.0 and dps >= 160.0 triggers BURN
        z = self._zone(radius=70.0, next_radius=40.0, next_center=(10.0, 10.0), dps=160.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((-30.0, -30.0, 0.0))
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, BURN)

    def test_burn_holds_position_at_center(self):
        # When bot is already at the center point, it holds position
        center = (10.0, 10.0)
        walkable = self.core.nearest_walkable(center[0], center[1], 2.5, True) or center
        z = self._zone(radius=30.0, next_radius=20.0, next_center=center, dps=160.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((walkable[0], walkable[1], 0.0))
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, BURN)
        # Goal equals current position (within 3m)
        self.assertAlmostEqual(dec.goal[0], walkable[0], places=1)
        self.assertAlmostEqual(dec.goal[1], walkable[1], places=1)

    def test_burn_suppresses_retreat_when_low_hp(self):
        # In final burn, retreating is suppressed so the bot fights to the death rather than fleeing
        center = (10.0, 10.0)
        z = self._zone(radius=30.0, next_radius=20.0, next_center=center, dps=160.0)
        strat = Strategy(CFG, self.core, z, ThreatTracker())
        obs = make_obs((0, 0, 0))
        obs["self"]["hp"] = int(1400 * 0.20)  # 20% HP (normally triggers retreat at < 35%)
        dec = strat.update(obs, False)
        self.assertEqual(dec.state, BURN)
        self.assertFalse(dec.retreat)


if __name__ == "__main__":
    unittest.main()
