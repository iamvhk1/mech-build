"""Escalation survival (fight.pacing, pacing.py): loot a kill's cubes, split ganging hunters."""
from __future__ import annotations

import math
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tuning  # noqa: E402
from farm import Item  # noqa: E402
from pacing import LOOT_WINDOW_S, Pacer  # noqa: E402
from test_phase3 import CFG, make_obs, mech  # noqa: E402
from threat import ThreatTracker  # noqa: E402


def aimed(id_, pos):
    """A mech at pos aiming at us (we stand at the origin): counts as a hunter."""
    return mech(id_, pos, aim=(math.atan2(-pos[1], -pos[0]), 0.0))


class FakeZone:
    known = True

    def __init__(self, left=1e9):
        self.left = left

    def time_until_outside(self, p):
        return self.left


class PacingTest(unittest.TestCase):
    def setUp(self):
        self._saved = tuning.ACTIVE
        tuning.use("pacing")
        self.p = Pacer(None, CFG)
        self.th = ThreatTracker()

    def tearDown(self):
        tuning.use(self._saved)

    def step(self, obs):
        self.p.observe(obs)
        self.th.update(obs)
        return obs

    def plan(self, obs, cubes=None, zone=None):
        return self.p.plan(obs, zone, self.th.hunters(obs["self"]["pos"]), self.th, cubes or {}, 11.7)

    def kill_at(self, t=20.0):
        self.step(make_obs((0, 0, 0), mechs=[aimed(5, (30, 0, 0))], t=t - 1.0))
        return self.step(make_obs((0, 0, 0), t=t, events=[{"type": "kill", "target": 5}]))

    def test_preset_is_best_plus_split(self):
        """Since run C2c, best has pacing on with the split rule off (loot only)."""
        b = tuning._resolve("best")
        self.assertTrue(b["fight.pacing"])
        self.assertFalse(b["pacing.split"])
        p, lo = tuning._resolve("pacing"), tuning._resolve("pacing_loot")
        self.assertEqual({k: v for k, v in p.items() if v != lo[k]}, {"pacing.split": True})

    def test_loots_the_kill_drop(self):
        o = self.kill_at()
        cubes = {5001: Item(5001, (31, 2, 0), 0, 20.0), 5002: Item(5002, (28, -1, 0), 0, 20.0),
                 5003: Item(5003, (-40, 0, 0), 0, 20.0)}  # 5003 is not the kill's drop
        self.assertEqual(self.plan(o, cubes), (28, -1))
        self.assertTrue(self.p.mode.startswith("loot"))

    def test_no_loot_after_window_or_when_ganged(self):
        o = self.kill_at()
        cubes = {5001: Item(5001, (31, 2, 0), 0, 20.0)}
        late = make_obs((0, 0, 0), t=20.0 + LOOT_WINDOW_S + 1.0)
        self.th.update(late)
        self.assertIsNone(self.plan(late, cubes))
        ganged = self.step(make_obs((0, 0, 0), mechs=[aimed(6, (35, 10, 0)), aimed(7, (-30, 20, 0))], t=21.0))
        self.assertFalse(self.plan(ganged, cubes) == (31, 2))

    def test_no_loot_into_the_zone(self):
        o = self.kill_at()
        self.assertIsNone(self.plan(o, {5001: Item(5001, (31, 2, 0), 0, 20.0)}, zone=FakeZone(left=1.0)))

    def test_split_steps_away_from_the_trailing_hunters(self):
        o = self.step(make_obs((0, 0, 0), mechs=[aimed(6, (40, 0, 0)), aimed(7, (0, 80, 0))], t=50.0))
        g = self.plan(o)
        self.assertIsNotNone(g)
        self.assertTrue(self.p.mode.startswith("split"))
        self.assertLess(g[1], -10.0)  # away from the hunter in the north
        self.assertAlmostEqual(math.dist(g, (0, 0)), 20.0, delta=0.5)

    def test_one_hunter_is_left_to_normal_fighting(self):
        o = self.step(make_obs((0, 0, 0), mechs=[aimed(6, (40, 0, 0))], t=50.0))
        self.assertIsNone(self.plan(o))

    def lightning_obs(self, mechs, t=50.0, energy=100.0):
        ws = [{"kind": "gun", "cooldown": 0.0, "ammo": 12, "reload": 0, "stats": dict(CFG["weapons"]["gun"])},
              {"kind": "lightning", "cooldown": 0.0, "stats": dict(CFG["weapons"]["lightning"])}]
        return self.step(make_obs((0, 0, 0), mechs=mechs, t=t, weapons=ws, energy=energy))

    def test_press_closes_on_a_lone_hunter_with_lightning(self):
        tuning.use("press")
        o = self.lightning_obs([aimed(6, (70, 0, 0))])
        g = self.plan(o)
        self.assertIsNotNone(g)
        self.assertTrue(self.p.mode.startswith("press"))
        self.assertAlmostEqual(g[0], 45.0, delta=0.5)  # 25 m short of the hunter, on our side

    def test_no_press_without_lightning_energy_hp_or_when_two_hunters(self):
        tuning.use("press")
        self.assertIsNone(self.plan(self.step(make_obs((0, 0, 0), mechs=[aimed(6, (70, 0, 0))], t=50.0))))
        self.assertIsNone(self.plan(self.lightning_obs([aimed(6, (70, 0, 0))], t=51.0, energy=20.0)))
        self.assertIsNone(self.plan(self.lightning_obs([aimed(6, (70, 0, 0)), aimed(7, (-60, 30, 0))], t=52.0)))
        self.assertIsNone(self.plan(self.lightning_obs([aimed(6, (28, 0, 0))], t=53.0)))  # already close
        tuning.use("best")
        self.assertIsNone(self.plan(self.lightning_obs([aimed(6, (70, 0, 0))], t=54.0)))

    def test_hunt_goes_after_the_only_known_mech(self):
        tuning.use("hunt")
        o = self.lightning_obs([mech(6, (150, 0, 0))])  # seen, not hunting us, 150 m away
        g = self.plan(o)
        self.assertIsNotNone(g)
        self.assertTrue(self.p.mode.startswith("hunt"))
        self.assertAlmostEqual(g[0], 125.0, delta=0.5)

    def test_no_hunt_with_two_known_mechs_without_lightning_or_switch_off(self):
        tuning.use("hunt")
        self.assertIsNone(self.plan(self.lightning_obs([mech(6, (150, 0, 0)), mech(7, (-200, 0, 0))])))
        self.th = ThreatTracker()
        self.assertIsNone(self.plan(self.step(make_obs((0, 0, 0), mechs=[mech(6, (150, 0, 0))], t=60.0))))
        self.th = ThreatTracker()
        tuning.use("best")
        self.assertIsNone(self.plan(self.lightning_obs([mech(6, (150, 0, 0))], t=61.0)))

    def test_no_split_into_the_zone(self):
        o = self.step(make_obs((0, 0, 0), mechs=[aimed(6, (40, 0, 0)), aimed(7, (0, 80, 0))], t=50.0))
        self.assertIsNone(self.plan(o, zone=FakeZone(left=1.0)))


if __name__ == "__main__":
    unittest.main()
