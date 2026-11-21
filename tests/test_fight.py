"""Stage B tests: trigger timing, blind fire at unseen attackers, and the duel harness.

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
from combat import Combat  # noqa: E402
from duel import Duel  # noqa: E402
from test_phase3 import CFG, gun, make_obs, mech  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


class FightTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        c = cls.core
        g = c.layer(core_api.LAYER_GROUND)
        clear = c.layer(core_api.LAYER_CLEARANCE)
        cover = c.layer(core_api.LAYER_COVER)
        xy = lambda k: (c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
        cls.open = [xy(k) for k, v in enumerate(g) if v and clear[k] >= 6]
        cand = [k for k, v in enumerate(g) if v and clear[k] >= 3 and cover[k] >= 0.25]
        rng = random.Random(7)
        cls.scen = []
        while len(cls.scen) < 20:
            s = xy(rng.choice(cand))
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(50, 90)
            e = (s[0] + d * math.cos(a), s[1] + d * math.sin(a))
            if not c.is_ground(*e) or c.clearance(*e) < 3:
                continue
            if c.shot_los((e[0], e[1], c.floor_z(*e) + 7), (s[0], s[1], c.floor_z(*s) + 4.5)) < 1:
                continue
            cls.scen.append((s, e))

    def setUp(self):
        self._saved = tuning.ACTIVE

    def tearDown(self):
        tuning.use(self._saved)

    def pos3(self, xy):
        return (xy[0], xy[1], self.core.floor_z(*xy))

    # ------------------------------------------------------------ trigger timing

    def test_trigger_held_when_ready_within_decision(self):
        """The server fires a held trigger the moment the cooldown ends: hold it if that happens
        before our next decision (0.1 s), or we lose ~20% of the fire rate."""
        tuning.use("best")
        c = Combat(CFG, None)
        me = (0.0, 0.0, 0.0)
        tg = (50.0, 0.0, 0.0)
        mz = [0.0, 0.0, CFG["mech"]["muzzle_height"]]
        sol = core_api.gun_lead(mz, [50.0, 0.0, 4.5], [0, 0, 0], 252.0, 3.0)
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]
        for cd, want in ((0.0, True), (0.08, True), (0.12, False)):
            o = make_obs(me, (sol[0], sol[1]), [mech(5, tg)], weapons=[gun(cooldown=cd), None], events=hit)
            c.observe(o)
            self.assertEqual(c.decide(o, (0, 0))["fire"][0], want, f"cooldown {cd}")

    # ------------------------------------------------------------ blind fire

    def _blind_case(self, clear: bool, seed=1):
        rng = random.Random(seed)
        for _ in range(5000):
            s = rng.choice(self.open)
            b = rng.uniform(-math.pi, math.pi)
            e = (s[0] + 60 * math.cos(b), s[1] + 60 * math.sin(b))
            ps = self.pos3(s)
            f = self.core.shot_los((ps[0] + 3 * math.cos(b), ps[1] + 3 * math.sin(b), ps[2] + 7),
                                   (e[0], e[1], self.core.floor_z(*e) + 4.5))
            if (f >= 1.0) == clear:
                return ps, b
        self.fail("no case found")

    def test_blind_fire_along_bearing(self):
        tuning.use("blind")
        me, b = self._blind_case(clear=True)
        c = Combat(CFG, self.core)
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": b, "by": 7}]
        o = make_obs(me, (b, 0.0), events=hit)                       # attacker not visible
        c.observe(o)
        out = c.decide(o, (0, 0))
        self.assertAlmostEqual(out["aim"][0], b, places=3)
        o = make_obs(me, (b, out["aim"][1]))                          # torso has settled
        self.assertTrue(c.decide(o, (0, 0))["fire"][0])
        self.assertIn("blind", c.debug)

    def test_blind_fire_never_into_a_wall(self):
        tuning.use("blind")
        me, b = self._blind_case(clear=False, seed=2)
        c = Combat(CFG, self.core)
        o = make_obs(me, (b, 0.0), events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": b, "by": 7}])
        c.observe(o)
        aim = c.decide(o, (0, 0))["aim"]
        self.assertFalse(c.decide(make_obs(me, aim), (0, 0))["fire"][0])

    def test_blind_fire_off_in_best_and_not_for_visible_attackers(self):
        me, b = self._blind_case(clear=True, seed=3)
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": b, "by": 7}]
        tuning.use("best")
        c = Combat(CFG, self.core)
        o = make_obs(me, (b, 0.0), events=hit)
        c.observe(o)
        self.assertFalse(c.decide(make_obs(me, (b, 0.0)), (0, 0))["fire"][0])   # switch off
        tuning.use("blind")
        c = Combat(CFG, self.core)
        vis = mech(7, (me[0] + 60 * math.cos(b), me[1] + 60 * math.sin(b), me[2]))
        o2 = make_obs(me, (b, 0.0), mechs=[vis], events=hit)
        c.observe(o2)
        c.decide(o2, (0, 0))
        self.assertNotIn("blind", c.debug)                                     # visible: normal aim

    def test_blind_distance_from_incoming_bullet(self):
        """A visible incoming bullet, traced back to the damage bearing, gives the shooter distance."""
        tuning.use("blind")
        c = Combat(CFG, None)
        b = 0.3
        shooter = (100 * math.cos(b), 100 * math.sin(b))
        # bullet 40 m out on its way from the shooter toward a point just beside us
        aimpt = (1.0, -1.0)
        dx, dy = aimpt[0] - shooter[0], aimpt[1] - shooter[1]
        n = math.hypot(dx, dy)
        bullet = {"id": 1, "kind": "gun", "pos": [shooter[0] + dx / n * 60, shooter[1] + dy / n * 60, 5.0],
                  "vel": [dx / n * 252, dy / n * 252, 0.0]}
        o = make_obs((0, 0, 0))
        o["projectiles"] = [bullet]
        sol = c.blind_solution(o, b, [0.0, 0.0, 7.0], 2.5)
        self.assertAlmostEqual(sol[2], 100.0, delta=4.0)

    # ------------------------------------------------------------ duel regression

    def test_duel_blind_fire_beats_best(self):
        """Offline screening result kept as a regression check (geometric hits, tree-hidden shooters)."""
        res = {}
        for preset in ("best", "blind"):
            tuning.use(preset)
            won = sum(Duel(self.core, CFG, s, e, False, seed=i).run(40)["won"] for i, (s, e) in enumerate(self.scen))
            res[preset] = won
        self.assertGreater(res["blind"], res["best"] + 3, res)


if __name__ == "__main__":
    unittest.main()
