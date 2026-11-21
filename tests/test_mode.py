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

    def _zone(self, radius=560.0, dps=20.0):
        z = Zone()
        z.update({"center": [0, 0], "radius": radius, "next_center": [0, 0], "next_radius": radius - 100,
                  "shrink_start": 60, "shrink_end": 110, "dps": dps}, 10.0)
        return z

    def test_presets_and_keys(self):
        self.assertIn("mode_detect", tuning.PRESETS)
        self.assertIn("ffa", tuning.PRESETS)
        self.assertTrue(tuning.PRESETS["mode_detect"]["mode.detect"])
        self.assertEqual(tuning.PRESETS["ffa"]["retreat.hp_enter"], 0.55)
        self.assertTrue(tuning.PRESETS["ffa"]["farm.crates"])
        self.assertTrue(tuning.PRESETS["ffa"]["farm.cubes"])
        self.assertTrue(tuning.PRESETS["ffa"]["farm.drones"])

    def test_detection_disabled_when_switch_off(self):
        tuning.use("best")  # mode.detect is False
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        # Unassisted death occurs, but switch is off
        mode = self.detector.observe({"alive": 15, "events": []}, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_stays_practice_with_no_deaths(self):
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        mode = self.detector.observe({"alive": 16, "events": []}, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_stays_practice_when_we_kill(self):
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        # Alive drops from 16 to 15, but our mech scored a kill
        obs = {"alive": 15, "events": [{"type": "kill", "target": 5}]}
        mode = self.detector.observe(obs, z)
        self.assertEqual(mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

    def test_triggers_ffa_on_unassisted_death_early_game(self):
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        # Alive drops without our kill
        mode = self.detector.observe({"alive": 15, "events": []}, z)
        self.assertEqual(mode, "ffa")
        self.assertEqual(tuning.get_mode(), "ffa")
        # Verify overlay is applied
        self.assertEqual(tuning.get("retreat.hp_enter"), 0.55)
        self.assertEqual(tuning.get("retreat.hp_exit"), 0.90)
        self.assertTrue(tuning.get("retreat.hold_fire"))
        self.assertTrue(tuning.get("retreat.on_hunters"))
        self.assertTrue(tuning.get("retreat.on_heavy_damage"))
        self.assertTrue(tuning.get("farm.crates"))
        self.assertTrue(tuning.get("farm.cubes"))
        self.assertTrue(tuning.get("farm.drones"))
        self.assertEqual(tuning.get("engage.near_m"), 60.0)

    def test_guards_against_late_single_death(self):
        # In late zone phases (radius <= 70 and dps >= 160), a single unassisted death
        # could be a house bot dying to zone collapse, so it stays in practice.
        late_z = self._zone(radius=25, dps=160)
        self.detector.observe({"alive": 16, "events": []}, late_z)
        mode1 = self.detector.observe({"alive": 15, "events": []}, late_z)
        self.assertEqual(mode1, "practice")
        self.assertEqual(tuning.get_mode(), "practice")

        # But a second unassisted death confirms FFA even in late game
        mode2 = self.detector.observe({"alive": 14, "events": []}, late_z)
        self.assertEqual(mode2, "ffa")
        self.assertEqual(tuning.get_mode(), "ffa")

    def test_latches_ffa(self):
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        self.detector.observe({"alive": 15, "events": []}, z)
        self.assertEqual(self.detector.mode, "ffa")
        # Next observation with no further deaths stays in FFA
        mode = self.detector.observe({"alive": 15, "events": []}, z)
        self.assertEqual(mode, "ffa")

    def test_reset(self):
        z = self._zone(radius=500, dps=20)
        self.detector.observe({"alive": 16, "events": []}, z)
        self.detector.observe({"alive": 15, "events": []}, z)
        self.assertEqual(self.detector.mode, "ffa")
        self.detector.reset()
        self.assertEqual(self.detector.mode, "practice")
        self.assertEqual(tuning.get_mode(), "practice")
        self.assertEqual(tuning.get("retreat.hp_enter"), 0.35)


if __name__ == "__main__":
    unittest.main()
