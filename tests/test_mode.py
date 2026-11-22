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
        self.assertTrue(tuning.PRESETS["ffa"]["burn.enabled"])

    def test_detection_disabled_when_switch_off(self):
        tuning.use("crates")  # mode.detect is False
        self.assertFalse(tuning.get("mode.detect"))
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

    def _beam_obs(self, t, end, target_pos, by=5, kind="laser"):
        return {"alive": 16, "t": t, "events": [],
                "self": {"id": 1, "pos": [0.0, 0.0, 0.0]},
                "mechs": [{"id": 5, "kind": "mech", "pos": [200.0, 0.0, 0.0]},
                          {"id": 7, "kind": "mech", "pos": list(target_pos)}],
                "beams": [{"by": by, "kind": kind, "path": [[200.0, 0.0, 7.0], list(end)], "age": 0.0}]}

    def test_infighting_beams_switch_to_ffa_even_late(self):
        """Audit A2: a laser from one mech ending on another (far from us) is a free-for-all,
        at any time of the match, even after the 120 s death-rule lock."""
        z = self._zone(radius=240, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 130.0, "events": []}, z)
        self.assertTrue(self.detector.locked)
        hit = (120.0, 40.0, 4.0)
        self.detector.observe(self._beam_obs(131.0, hit, (121.0, 41.0, 0.0)), z)
        self.assertEqual(self.detector.mode, "practice")  # one beam is not enough
        mode = self.detector.observe(self._beam_obs(132.0, hit, (121.0, 41.0, 0.0)), z)
        self.assertEqual(mode, "ffa")
        self.assertEqual(tuning.get_mode(), "ffa")

    def _hp_obs(self, t, hp, pos=(150.0, 0.0, 0.0), events=(), npc=None):
        mechs = [{"id": 5, "kind": "mech", "pos": list(pos), "hp": hp, "max_hp": 1400}]
        if npc is not None:
            mechs.append({"id": 104, "kind": "npc", "pos": list(npc), "hp": 350, "max_hp": 350})
        return {"alive": 16, "t": t, "events": list(events), "self": {"id": 1, "pos": [0.0, 0.0, 0.0]},
                "mechs": mechs, "beams": []}

    def test_third_party_hp_loss_switches_to_ffa_even_late(self):
        """A visible mech far from us loses gun-sized chunks of HP we didn't deal: a free-for-all."""
        z = self._zone(radius=560, shrink_start=60)
        self.detector.observe({"alive": 16, "t": 125.0, "events": []}, z)  # past the death-rule lock
        hp = 1400.0
        for i in range(3):
            self.assertEqual(self.detector.mode, "practice")
            self.detector.observe(self._hp_obs(130.0 + 0.1 * i, hp), z)
            hp -= 45.0
        self.detector.observe(self._hp_obs(130.3, hp), z)
        self.assertEqual(self.detector.mode, "ffa")

    def test_hp_loss_we_caused_or_from_drones_or_near_us_is_not_ffa(self):
        z = self._zone(radius=560, shrink_start=60)
        hit = [{"type": "hit", "target": 5, "amount": 45, "weapon": "gun"}]
        cases = [
            dict(events=hit),                       # we hit it
            dict(npc=(160.0, 10.0, 0.0)),           # an NPC drone next to it
            dict(pos=(20.0, 0.0, 0.0)),             # it's next to us (splash / chains from shots at us)
        ]
        for c in cases:
            d = ModeDetector()
            d.reset()
            hp = 1400.0
            for i in range(6):
                d.observe(self._hp_obs(10.0 + 0.1 * i, hp, **c), z)
                hp -= 45.0
            self.assertEqual(d.mode, "practice", c)
        d = ModeDetector()
        d.reset()
        hp = 1400.0
        for i in range(6):  # small drops (an NPC bullet is 25)
            d.observe(self._hp_obs(10.0 + 0.1 * i, hp), z)
            hp -= 25.0
        self.assertEqual(d.mode, "practice")

    def test_beams_at_us_or_lightning_are_not_infighting(self):
        z = self._zone(radius=560, shrink_start=60)
        for i in range(5):
            # a laser ending next to us (a squad mate standing near us) and lightning arcs
            self.detector.observe(self._beam_obs(10.0 + i, (10.0, 0.0, 4.0), (11.0, 1.0, 0.0)), z)
            self.detector.observe(self._beam_obs(10.5 + i, (120.0, 40.0, 4.0), (121.0, 41.0, 0.0),
                                                 kind="lightning"), z)
        self.assertEqual(self.detector.mode, "practice")


class LateOverlayTest(unittest.TestCase):
    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("late180")

    def tearDown(self):
        tuning.use(self._saved)

    def test_ffa_turns_off_practice_only_aggression(self):
        """Hunting and contested drops are practice-only; free-for-all keeps them off."""
        tuning.use("drops_bold")
        self.assertTrue(tuning.get("fight.hunt"))
        self.assertEqual(tuning.get("drops.max_threats"), 1)
        tuning.set_mode("ffa")
        self.assertFalse(tuning.get("fight.hunt"))
        self.assertEqual(tuning.get("drops.max_threats"), 0)
        self.assertTrue(tuning.get("fight.press"))      # pressing a hunter already on us stays
        self.assertTrue(tuning.get("arm.early"))
        tuning.set_mode("practice")

    def test_late_overlay_only_in_practice(self):
        self.assertEqual(tuning.get("late.at"), 180.0)
        self.assertFalse(tuning.get("retreat.on_hunters"))
        tuning.set_late(True)
        self.assertTrue(tuning.get("retreat.on_hunters"))
        self.assertTrue(tuning.get("retreat.on_heavy_damage"))
        self.assertEqual(tuning.get("retreat.hp_enter"), 0.50)
        self.assertFalse(tuning.get("retreat.hold_fire"))  # keep shooting back
        tuning.set_mode("ffa")  # free-for-all settings win over the late overlay
        self.assertFalse(tuning.get("retreat.on_hunters"))
        tuning.set_mode("practice")
        self.assertTrue(tuning.get("retreat.on_hunters"))
        tuning.use("late180")  # a fresh preset clears it
        self.assertFalse(tuning.is_late())
        self.assertFalse(tuning.get("retreat.on_hunters"))

if __name__ == "__main__":
    unittest.main()
