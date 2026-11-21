"""Tests for Stage D: Mode detection (E6) and Free-For-All overlay settings."""
from __future__ import annotations

import unittest
from mode import ModeDetector
import tuning
from zone import Zone


class ModeDetectionTest(unittest.TestCase):
    def setUp(self):
        self._saved_preset = tuning.ACTIVE
        self._saved_mode = tuning.get_mode()
        tuning.use("mode_detect")
        tuning.set_mode("practice")
        self.detector = ModeDetector()

    def tearDown(self):
        tuning.use(self._saved_preset)
        tuning.set_mode(self._saved_mode)

    def _zone(self, radius=560.0, dps=20.0, shrink_start=60.0):
        z = Zone()
        z.update({"center": [0, 0], "radius": radius, "next_center": [0, 0], "next_radius": radius - 100,
                  "shrink_start": shrink_start, "shrink_end": shrink_start + 50.0, "dps": dps}, 10.0)
        return z

    def test_presets_and_keys(self):
        self.assertIn("mode_detect", tuning.PRESETS)
        self.assertIn("ffa", tuning.PRESETS)
        self.assertTrue(tuning.PRESETS["mode_detect"]["mode.detect"])
        self.assertEqual(tuning.PRESETS["ffa"]["retreat.hp_enter"], 0.50)
        self.assertFalse(tuning.PRESETS["ffa"]["retreat.hold_fire"])
        self.assertTrue(tuning.PRESETS["ffa"]["farm.crates"])
        self.assertTrue(tuning.PRESETS["ffa"]["farm.cubes"])
        self.assertTrue(tuning.PRESETS["ffa"]["farm.drones"])

    def test_detection_disabled_when_switch_off(self):
        tuning.use("best")  # mode.detect is False
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        # Unassisted death occurs, but switch is off
        mode = self.detector.observe({"alive": 15, "t": 15.0, "events": []}, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_stays_practice_with_no_deaths(self):
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        mode = self.detector.observe({"alive": 16, "t": 15.0, "events": []}, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_stays_practice_when_we_kill(self):
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        # Alive drops from 16 to 15, but our mech scored a kill
        obs = {"alive": 15, "t": 20.0, "events": [{"type": "kill", "target": 5}]}
        mode = self.detector.observe(obs, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_triggers_ffa_on_unassisted_death_before_shrink_start(self):
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        # Alive drops at t=20s without our kill (zone covers entire map, no zone damage possible)
        mode = self.detector.observe({"alive": 15, "t": 20.0, "events": []}, z)
        self.assertEqual(mode, "ffa")
        self.assertEqual(tuning.get_mode(), "ffa")
        # Verify overlay is applied
        self.assertEqual(tuning.get("retreat.hp_enter"), 0.50)
        self.assertEqual(tuning.get("retreat.hp_exit"), 0.80)
        self.assertFalse(tuning.get("retreat.hold_fire"))
        self.assertFalse(tuning.get("retreat.on_hunters"))
        self.assertTrue(tuning.get("farm.crates"))
        self.assertTrue(tuning.get("farm.cubes"))
        self.assertTrue(tuning.get("farm.drones"))
        self.assertEqual(tuning.get("engage.near_m"), 60.0)

    def test_single_death_after_shrink_start_does_not_trigger(self):
        z = self._zone(radius=380, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 65.0, "events": []}, z)
        # 1 unassisted death after shrink_start could be a stuck squad bot in practice
        mode1 = self.detector.observe({"alive": 15, "t": 75.0, "events": []}, z)
        self.assertEqual(mode1, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

        # 2nd unassisted death before 120s confirms FFA
        mode2 = self.detector.observe({"alive": 14, "t": 85.0, "events": []}, z)
        self.assertEqual(mode2, "ffa")
        self.assertEqual(tuning.get_mode(), "ffa")

    def test_locks_to_practice_after_120s(self):
        z = self._zone(radius=240, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 65.0, "events": []}, z)
        # Time passes beyond 120s without FFA being detected
        self.detector.observe({"alive": 16, "t": 125.0, "events": []}, z)
        self.assertTrue(self.detector.locked)
        # Future unassisted deaths (e.g. late zone collapse) cannot switch mode
        mode = self.detector.observe({"alive": 10, "t": 150.0, "events": []}, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_latches_ffa(self):
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        self.detector.observe({"alive": 15, "t": 15.0, "events": []}, z)
        self.assertEqual(self.detector.mode, "ffa")
        # Next observation with no further deaths stays in FFA even past 120s
        mode = self.detector.observe({"alive": 15, "t": 150.0, "events": []}, z)
        self.assertEqual(mode, "ffa")

    def test_reset(self):
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 10.0, "events": []}, z)
        self.detector.observe({"alive": 15, "t": 15.0, "events": []}, z)
        self.assertEqual(self.detector.mode, "ffa")
        self.detector.reset()
        self.assertEqual(self.detector.mode, "practice")
        self.assertFalse(self.detector.locked)
        self.assertEqual(tuning.get_mode(), "practice")
        self.assertEqual(tuning.get("retreat.hp_enter"), 0.35)


if __name__ == "__main__":
    unittest.main()
