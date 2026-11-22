"""Stage F tests (E5 supply drops): contesting, safety rules, zone timing, ring holding.

    make -C core && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import math
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_api  # noqa: E402
import tuning  # noqa: E402
from drops import DropContester  # noqa: E402
from test_phase3 import CFG  # noqa: E402
from threat import ThreatTracker  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


def zone_big():
    z = Zone()
    z.update({"center": [0, 0], "radius": 5000, "next_center": [0, 0], "next_radius": 4000,
              "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 0}, 10.0)
    return z


class DropTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)

    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("drops")

    def tearDown(self):
        tuning.use(self._saved)

    def make_obs(self, me_pos=(0, 0, 0), drops=None, hunters=None):
        return {
            "t": 80.0,
            "tick": 800,
            "self": {
                "id": 1,
                "pos": list(me_pos),
                "vel": [0, 0, 0],
                "hp": 800,
                "in_zone": True,
                "stats": {"walk_speed": 11.7, "max_hp": 1000, "radius": 2.5},
            },
            "drops": drops or [],
            "mechs": hunters or [],
        }

    def test_preset_exists_and_active(self):
        self.assertIn("drops", tuning.PRESETS)
        self.assertTrue(tuning.get("drops.enabled"))
        self.assertEqual(tuning.get("drops.safe_m"), 80.0)

    def test_disabled_when_switch_off(self):
        tuning.use("cubes")  # drops.enabled: False (best has drops on since run B4)
        self.assertFalse(tuning.get("drops.enabled"))
        dropper = DropContester(self.core, CFG)
        obs = self.make_obs(drops=[{"id": 10, "pos": [30, 0, 0], "radius": 8.0, "lands_in": 0.0}])
        dropper.observe(obs)
        goal = dropper.plan(obs, zone_big(), [], ThreatTracker(), has_target=False)
        self.assertIsNone(goal)

    def test_approaches_landed_safe_drop(self):
        dropper = DropContester(self.core, CFG)
        drop = {"id": 10, "pos": [50.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0, "capture_s": 4.0}
        obs = self.make_obs(me_pos=(0, 0, 0), drops=[drop])
        dropper.observe(obs)
        threats = ThreatTracker()
        threats.update(obs)
        goal = dropper.plan(obs, zone_big(), threats.hunters((0, 0)), threats, has_target=False)
        self.assertIsNotNone(goal)
        self.assertEqual(dropper.target_id, 10)
        self.assertIn("approach 10", dropper.mode)

    def test_holds_position_inside_ring_to_capture(self):
        dropper = DropContester(self.core, CFG)
        # Drop is at (5, 0), radius is 8.0 m. My pos is (2, 0). Dist is 3 m <= 8.0 - 1.5 = 6.5 m.
        drop = {"id": 10, "pos": [5.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0, "capture_s": 4.0}
        obs = self.make_obs(me_pos=(2, 0, 0), drops=[drop])
        dropper.observe(obs)
        threats = ThreatTracker()
        threats.update(obs)
        goal = dropper.plan(obs, zone_big(), threats.hunters((2, 0)), threats, has_target=False)
        self.assertIsNotNone(goal)
        self.assertEqual(goal, (2, 0))  # Holds current position inside ring
        self.assertIn("capturing 10", dropper.mode)

    def test_unsafe_when_active_combat_target(self):
        dropper = DropContester(self.core, CFG)
        drop = {"id": 10, "pos": [50.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0, "capture_s": 4.0}
        obs = self.make_obs(me_pos=(0, 0, 0), drops=[drop])
        dropper.observe(obs)
        threats = ThreatTracker()
        threats.update(obs)
        goal = dropper.plan(obs, zone_big(), threats.hunters((0, 0)), threats, has_target=True)
        self.assertIsNone(goal)

    def test_unsafe_when_hunter_near_me_or_drop(self):
        dropper = DropContester(self.core, CFG)
        drop = {"id": 10, "pos": [50.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0, "capture_s": 4.0}
        # Hunter at (70, 0, 0), which is within safe_m (80m) of drop at (50, 0, 0) (dist 20m)
        enemy = {"id": 2, "pos": [70.0, 0.0, 0.0], "vel": [0, 0, 0], "hp": 500, "kind": "mech"}
        obs = self.make_obs(me_pos=(0, 0, 0), drops=[drop], hunters=[enemy])
        dropper.observe(obs)
        threats = ThreatTracker()
        threats.update(obs)
        goal = dropper.plan(obs, zone_big(), threats.hunters((0, 0)), threats, has_target=False)
        self.assertIsNone(goal)

    def test_unsafe_when_drop_held_by_enemy(self):
        dropper = DropContester(self.core, CFG)
        drop = {"id": 10, "pos": [50.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0, "holder": 99}
        obs = self.make_obs(me_pos=(0, 0, 0), drops=[drop])
        dropper.observe(obs)
        threats = ThreatTracker()
        threats.update(obs)
        goal = dropper.plan(obs, zone_big(), threats.hunters((0, 0)), threats, has_target=False)
        self.assertIsNone(goal)

    def test_drop_disappears_clears_target(self):
        dropper = DropContester(self.core, CFG)
        drop = {"id": 10, "pos": [50.0, 0.0, 0.0], "radius": 8.0, "lands_in": 0.0}
        obs1 = self.make_obs(me_pos=(0, 0, 0), drops=[drop])
        dropper.observe(obs1)
        threats = ThreatTracker()
        threats.update(obs1)
        goal = dropper.plan(obs1, zone_big(), threats.hunters((0, 0)), threats, has_target=False)
        self.assertEqual(dropper.target_id, 10)

        # Next tick, drop 10 is gone (captured or despawned)
        obs2 = self.make_obs(me_pos=(0, 0, 0), drops=[])
        dropper.observe(obs2)
        self.assertIsNone(dropper.target_id)
        self.assertEqual(dropper.mode, "")


class DropsDoNotBlockFarmingTest(unittest.TestCase):
    """Audit A1: with drops enabled but no drop available (the recorded match ends before the first
    drop is called at 70 s), the bot must act exactly like `best` (farming included)."""

    def actions(self, preset):
        import gzip
        import json
        import mechfight as mf
        real = mf.run
        mf.run = lambda *a, **k: None
        try:
            import bot as B
        finally:
            mf.run = real
        saved = tuning.ACTIVE
        tuning.use(preset)
        try:
            with gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt") as f:
                L = [json.loads(line) for line in f]
            L[0]["map"]["dir"] = os.path.join(ROOT, "arena")
            b = B.Bot(L[0])
            out = []
            for o in L[1:]:
                if o.get("type") == "obs":
                    a = dict(b.act(o))
                    a.pop("debug", None)
                    out.append(a)
            return out
        finally:
            tuning.use(saved)

    def without(self, preset, **changes):
        """Actions of `preset` with some settings changed (a temporary preset)."""
        tuning.PRESETS["_without"] = dict(tuning.PRESETS[preset], **changes)
        try:
            return self.actions("_without")
        finally:
            del tuning.PRESETS["_without"]

    def test_drops_preset_matches_best_before_first_drop(self):
        """Audit A1: drops enabled, no drop yet -> exactly the same as drops disabled (farming runs)."""
        self.assertEqual(self.actions("drops"), self.without("drops", **{"drops.enabled": False}))
        self.assertEqual(self.actions("best"), self.without("best", **{"drops.enabled": False}))

    def test_probe_is_best_until_idle_time(self):
        """Diagnostic probes play exactly like their base before T (the recording ends before 120 s)."""
        self.assertEqual(self.actions("probe_idle120"), self.without("probe_idle120", **{"probe.idle_at": None}))

    def test_probe_idles_after_idle_time(self):
        tuning.PRESETS["_probe_test"] = dict(tuning.PRESETS["best"], **{"probe.idle_at": 20.0})
        try:
            best, probe = self.actions("best"), self.actions("_probe_test")
        finally:
            del tuning.PRESETS["_probe_test"]
        ticks_t = [a["tick"] / 20.0 for a in best]
        for t, a, p in zip(ticks_t, best, probe):
            if t >= 20.0:
                self.assertEqual(p, {"tick": a["tick"]})
        self.assertTrue(any(t < 20.0 for t in ticks_t) and any(t >= 20.0 for t in ticks_t))

    def test_late180_is_best_before_three_minutes(self):
        """The recording ends at 36.8 s, so late180 must act exactly like its base on it."""
        self.assertEqual(self.actions("late180"), self.without("late180", **{"late.at": None}))

    def test_late_switch_turns_on_at_late_at(self):
        tuning.PRESETS["_late_test"] = dict(tuning.PRESETS["best"], **{"late.at": 20.0})
        try:
            self.actions("_late_test")
            # actions() restores the preset afterwards; check the bot flipped it during the replay
            tuning.use("_late_test")
            import bot as B
            import gzip
            import json
            with gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt") as f:
                L = [json.loads(line) for line in f]
            L[0]["map"]["dir"] = os.path.join(ROOT, "arena")
            b = B.Bot(L[0])
            seen = []
            for o in L[1:]:
                if o.get("type") == "obs":
                    b.act(o)
                    seen.append((o["t"], tuning.is_late()))
            self.assertTrue(all(late == (t >= 20.0) for t, late in seen))
        finally:
            tuning.use("best")
            del tuning.PRESETS["_late_test"]

class BoldDropsTest(unittest.TestCase):
    """D5: drops.max_threats tolerates that many known mechs near us or the drop."""

    def setUp(self):
        self._saved = tuning.ACTIVE

    def tearDown(self):
        tuning.use(self._saved)

    def safe(self, preset, mechs, has_target=False):
        from test_phase3 import make_obs, mech
        tuning.use(preset)
        th = ThreatTracker()
        th.update(make_obs((0, 0, 0), mechs=[mech(i + 5, p) for i, p in enumerate(mechs)]))
        return DropContester(None, CFG).is_safe((0, 0, 0), (30, 0, 0), th.hunters((0, 0, 0)), th, has_target)

    def test_bold_tolerates_one_mech_and_a_fight(self):
        self.assertTrue(self.safe("best", []))
        self.assertFalse(self.safe("best", [(60, 0, 0)]))
        self.assertTrue(self.safe("drops_bold", [(60, 0, 0)]))
        self.assertTrue(self.safe("drops_bold", [(60, 0, 0)], has_target=True))
        self.assertFalse(self.safe("best", [], has_target=True))
        self.assertFalse(self.safe("drops_bold", [(60, 0, 0), (-50, 20, 0)]))

if __name__ == "__main__":
    unittest.main()
