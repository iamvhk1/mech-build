"""Strafing tests: every safeguard, reproducibility, no hops while strafing, and the duel screen.

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
from duel import Duel  # noqa: E402
from navigation import Navigator  # noqa: E402
from sim import MiniSim  # noqa: E402
from strafe import LOOK_M, Strafer  # noqa: E402
from test_phase3 import CFG, make_obs  # noqa: E402

ARENA = os.path.join(ROOT, "arena")
EYE = CFG["mech"]["eye_height"]


class StrafeTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        c = cls.core
        g = c.layer(core_api.LAYER_GROUND)
        clear = c.layer(core_api.LAYER_CLEARANCE)
        xy = lambda k: (c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
        cls.open = [xy(k) for k, v in enumerate(g) if v and clear[k] >= 6]
        cls.edge = [xy(k) for k, v in enumerate(g) if v and 2.5 <= clear[k] < 3.5]

    def pos3(self, xy):
        return (xy[0], xy[1], self.core.floor_z(*xy))

    def test_strafes_sideways_in_the_open(self):
        p = self.pos3(self.open[100])
        s = Strafer(self.core, CFG, 1)
        tgt = (p[0] + 80, p[1])
        mv, active = s.adjust(make_obs(p, t=10.0), [0.0, 0.0], tgt, [], None)
        self.assertTrue(active)
        self.assertAlmostEqual(abs(mv[1]), 1.0, places=6)      # perpendicular to the target line
        self.assertAlmostEqual(mv[0], 0.0, places=6)

    def test_reverses_and_is_reproducible(self):
        p = self.pos3(self.open[200])
        tgt = (p[0] + 80, p[1])
        seqs = []
        for _ in range(2):
            s = Strafer(self.core, CFG, 42)
            seq = []
            for k in range(60):
                mv, _ = s.adjust(make_obs(p, t=10.0 + 0.1 * k), [0.0, 0.0], tgt, [], None)
                seq.append(round(mv[1]))
            seqs.append(seq)
        self.assertEqual(seqs[0], seqs[1])                     # same seed, same pattern
        self.assertIn(1, seqs[0])
        self.assertIn(-1, seqs[0])                             # it does reverse

    def test_never_strafes_into_a_wall(self):
        """Every strafe step it takes is walkable for LOOK_M metres."""
        rng = random.Random(3)
        n = 0
        for xy in rng.sample(self.edge, 200):
            p = self.pos3(xy)
            a = rng.uniform(0, 2 * math.pi)
            s = Strafer(self.core, CFG, 7)
            mv, active = s.adjust(make_obs(p, t=10.0), [0.0, 0.0], (p[0] + 80 * math.cos(a), p[1] + 80 * math.sin(a)), [], None)
            if active:
                q = (p[0] + mv[0] * LOOK_M, p[1] + mv[1] * LOOK_M)
                self.assertTrue(self.core.segment_walkable(p[:2], q, CFG["mech"]["radius"] * 0.9))
                n += 1
        self.assertGreater(n, 20)

    def test_never_steps_into_more_hunters_lines(self):
        """With a second hunter, the chosen step is never more exposed than standing still."""
        rng = random.Random(4)
        s = Strafer(self.core, CFG, 9)
        h = CFG["mech"]["height"]
        checked = 0
        for _ in range(400):
            p = self.pos3(rng.choice(self.open))
            a, b = rng.uniform(0, 2 * math.pi), rng.uniform(0, 2 * math.pi)
            tgt = (p[0] + 70 * math.cos(a), p[1] + 70 * math.sin(a))
            other = (p[0] + 60 * math.cos(b), p[1] + 60 * math.sin(b))
            eyes = [[tgt[0], tgt[1], self.core.floor_z(*tgt) + EYE], [other[0], other[1], self.core.floor_z(*other) + EYE]]
            mv, active = s.adjust(make_obs(p, t=10.0 + checked), [0.0, 0.0], tgt, eyes, None)
            if not active:
                continue
            q = (p[0] + mv[0] * LOOK_M, p[1] + mv[1] * LOOK_M)
            self.assertLessEqual(s._exposure(q, eyes, h), s._exposure(p[:2], eyes, h))
            checked += 1
        self.assertGreater(checked, 50)

    def test_stays_inside_the_zone(self):
        p = self.pos3(self.open[300])
        s = Strafer(self.core, CFG, 1)
        tgt = (p[0] + 80, p[1])
        # zone edge 2 m north of us: strafing north (toward +y) would leave the margin
        zone = (p[0], p[1] - 98.0, 100.0)
        for k in range(30):
            mv, active = s.adjust(make_obs(p, t=10.0 + 0.1 * k), [0.0, 0.0], tgt, [], zone)
            if active:
                self.assertLess(mv[1], 0.5)

    def test_blends_with_travel(self):
        p = self.pos3(self.open[400])
        s = Strafer(self.core, CFG, 1)
        mv, active = s.adjust(make_obs(p, t=10.0), [1.0, 0.0], (p[0], p[1] + 80), [], None)
        self.assertTrue(active)
        self.assertGreater(mv[0], 0.5)                       # still making progress east
        self.assertAlmostEqual(math.hypot(*mv), 1.0, places=6)

    def test_navigator_does_not_hop_while_strafing(self):
        """Back-and-forth jinks have little net displacement; with suppress_stuck the navigator
        must not read that as stuck (which would hop under fire)."""
        start = self.open[500]
        nav = Navigator(self.core, CFG)
        nav.set_goal((start[0] + 80, start[1]))
        sim = MiniSim(self.core, CFG, start)
        nav.suppress_stuck = True
        for _ in range(40):                                   # pinned in place for 4 s
            out = nav.step(sim.obs())
            self.assertFalse(out.get("jump"))
            sim.t += 0.1
            sim.tick += 2
        self.assertEqual(nav.stuck_level, 0)

    def test_stuck_detection_paused_only_while_actually_strafing(self):
        """In a fight where both strafe directions are unsafe we walk normally, and real stuck
        detection must stay on; it's paused only after a decision where we really strafed."""
        import types
        import mechfight as mf
        real_run = mf.run
        mf.run = lambda *a, **k: None
        try:
            import bot as B
        finally:
            mf.run = real_run
        dummy = types.SimpleNamespace(strafer=Strafer(self.core, CFG, 1))
        fight = (0.0, 0.0)
        self.assertFalse(B.Bot.stuck_paused(dummy, None))          # no fight
        self.assertFalse(B.Bot.stuck_paused(dummy, fight))         # fight, but haven't strafed yet
        # a fight where the strafer can't find a safe step: active stays False -> detection stays on
        p = self.pos3(self.open[600])
        boxed_in = [[p[0] + 50 * math.cos(a), p[1] + 50 * math.sin(a), p[2] + EYE] for a in (0.0, math.pi)]
        zone = (p[0], p[1], 2.0)                                      # any step leaves the zone margin
        _, active = dummy.strafer.adjust(make_obs(p, t=10.0), [0.0, 0.0], (p[0] + 80, p[1]), boxed_in, zone)
        self.assertFalse(active)
        self.assertFalse(B.Bot.stuck_paused(dummy, fight))
        # after a decision where we did strafe: paused
        dummy.strafer.adjust(make_obs(p, t=11.0), [0.0, 0.0], (p[0] + 80, p[1]), [], None)
        self.assertTrue(dummy.strafer.active)
        self.assertTrue(B.Bot.stuck_paused(dummy, fight))
        # fight over: not paused, and the stale flag is cleared for the next fight
        self.assertFalse(B.Bot.stuck_paused(dummy, None))
        self.assertFalse(dummy.strafer.active)

    def test_duel_strafing_beats_standing(self):
        """Offline screen kept as a regression check (real enemy bullets that lead us)."""
        rng = random.Random(7)
        c = self.core
        g = c.layer(core_api.LAYER_GROUND)
        cl = c.layer(core_api.LAYER_CLEARANCE)
        xy = lambda k: (c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
        cand = [k for k, v in enumerate(g) if v and cl[k] >= 3]
        scen = []
        while len(scen) < 16:
            s = xy(rng.choice(cand))
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(50, 110)
            e = (s[0] + d * math.cos(a), s[1] + d * math.sin(a))
            if not c.is_ground(*e) or c.clearance(*e) < 3:
                continue
            if c.shot_los((e[0], e[1], c.floor_z(*e) + 7), (s[0], s[1], c.floor_z(*s) + 4.5)) < 1:
                continue
            scen.append((s, e))
        saved = tuning.ACTIVE
        try:
            tuning.use("focus")
            taken = {}
            for strafe in (False, True):
                taken[strafe] = sum(Duel(c, CFG, s, e, False, seed=i, enemy_model="bullets", strafe=strafe).run(40)["taken"]
                                    for i, (s, e) in enumerate(scen))
        finally:
            tuning.use(saved)
        self.assertLess(taken[True], taken[False])


if __name__ == "__main__":
    unittest.main()
