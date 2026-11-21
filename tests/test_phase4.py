"""Phase 4 tests. E1: upgrade picker, threat tracking (hunters), RETREAT heal cycles.

    make -C core && python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import gzip
import json
import math
import os
import random
import sys
import time
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_api  # noqa: E402
import upgrades  # noqa: E402
from combat import Combat  # noqa: E402
from strategy import RETREAT, ROTATE, Strategy  # noqa: E402
from test_phase3 import CFG, gun, make_obs, mech  # noqa: E402
from threat import ThreatTracker  # noqa: E402
from zone import Zone  # noqa: E402

ARENA = os.path.join(ROOT, "arena")


def offer(*ids):
    return {"id": 1, "expires": 99, "choices": [{"id": i, "name": i, "desc": ""} for i in ids]}


def me_with(upgrades_taken=(), weapons=("gun",)):
    return {"upgrades": list(upgrades_taken), "weapons": [{"kind": w} for w in weapons] + [None]}


class UpgradeTest(unittest.TestCase):
    def pick_id(self, ids, taken=(), weapons=("gun",)):
        return offer(*ids)["choices"][upgrades.pick(offer(*ids), me_with(taken, weapons), CFG)]["id"]

    def test_ranking(self):
        self.assertEqual(self.pick_id(["plating", "nanites", "armor"]), "nanites")              # 1st nanites
        self.assertEqual(self.pick_id(["plating", "nanites", "armor"], ["nanites"]), "plating")  # then plating
        self.assertEqual(self.pick_id(["nanites", "plating"], ["nanites", "plating", "plating"]), "plating")  # 3rd plating
        self.assertEqual(self.pick_id(["nanites", "armor"], ["nanites", "plating", "plating", "plating"]), "nanites")
        self.assertEqual(self.pick_id(["armor", "sensors", "servos"]), "armor")
        self.assertEqual(self.pick_id(["servos", "gun_rate", "jets"]), "gun_rate")              # perk for held weapon
        self.assertEqual(self.pick_id(["laser_damage", "servos"]), "servos")                    # not holding a laser
        self.assertEqual(self.pick_id(["lightning_efficiency", "servos"], weapons=("gun", "lightning")),
                         "lightning_efficiency")

    def test_unknown_upgrade_scored_by_effect(self):
        cfg = dict(CFG)
        cfg["upgrades"] = list(CFG["upgrades"]) + [{"id": "mystery_hp", "effects": [{"path": "mech.hp", "mul": 1.1}], "max": 1}]
        o = offer("servos", "mystery_hp")
        self.assertEqual(o["choices"][upgrades.pick(o, me_with(), cfg)]["id"], "mystery_hp")

    def test_no_offer(self):
        self.assertIsNone(upgrades.pick(None, me_with(), CFG))


class ThreatTest(unittest.TestCase):
    def test_hunters(self):
        tr = ThreatTracker()
        me = (0.0, 0.0, 0.0)
        passive = mech(1, (100, 0, 0), vel=(0, 5, 0), aim=(1.0, 0))           # moving sideways, not aiming
        closing = mech(2, (0, 70, 0), vel=(0, -8, 0), aim=(0.0, 0))           # coming at us
        aiming = mech(3, (-120, 0, 0), aim=(0.0, 0))                          # aims east, straight at us
        far = mech(4, (400, 0, 0), vel=(-8, 0, 0), aim=(math.pi, 0))          # beyond 150 m
        tr.update(make_obs(me, mechs=[passive, closing, aiming, far], t=10))
        ids = {h.id for h in tr.hunters(me)}
        self.assertEqual(ids, {2, 3})
        # an unseen attacker becomes a hunter, placed along the bearing
        tr.update(make_obs(me, t=11, events=[{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": math.pi, "by": 7}]))
        self.assertIn(7, {h.id for h in tr.hunters(me)})
        self.assertAlmostEqual(tr.damage_taken(2.0), 45)
        # tracks are forgotten
        tr.update(make_obs(me, t=40))
        self.assertEqual(tr.tracks, {})


class RetreatTest(unittest.TestCase):
    core: core_api.MapCore

    @classmethod
    def setUpClass(cls):
        cls.core = core_api.MapCore.from_dir(ARENA, CFG)
        g = cls.core.layer(core_api.LAYER_GROUND)
        clear = cls.core.layer(core_api.LAYER_CLEARANCE)
        c = cls.core
        cls.open = [(c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res)
                    for k, v in enumerate(g) if v and clear[k] >= 4]

    def setup(self, pos):
        z = Zone()
        z.update({"center": list(pos[:2]), "radius": 400, "next_center": list(pos[:2]), "next_radius": 300,
                  "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 20}, 10.0)
        tr = ThreatTracker()
        return Strategy(CFG, self.core, z, tr), tr

    def obs_hp(self, pos, hp, t, mechs=(), events=()):
        o = make_obs(pos, mechs=mechs, t=t, events=events)
        o["self"]["hp"] = hp
        return o

    def test_enter_and_leave_retreat(self):
        pos = (*self.open[100], self.core.floor_z(*self.open[100]))
        s, tr = self.setup(pos)
        o = self.obs_hp(pos, 1300, 10.0)
        tr.update(o)
        self.assertEqual(s.update(o, False).state, ROTATE)
        o = self.obs_hp(pos, 600, 12.0)                      # 43% HP
        tr.update(o)
        self.assertEqual(s.update(o, False).state, RETREAT)
        o = self.obs_hp(pos, 1300, 12.5)                     # healed but inside the hysteresis window
        tr.update(o)
        self.assertEqual(s.update(o, False).state, RETREAT)
        o = self.obs_hp(pos, 1300, 14.0)                     # healed to 93%
        tr.update(o)
        self.assertEqual(s.update(o, False).state, ROTATE)

    def test_many_hunters_trigger_retreat(self):
        pos = (*self.open[200], self.core.floor_z(*self.open[200]))
        s, tr = self.setup(pos)
        hs = [mech(k, (pos[0] + 60 + 5 * k, pos[1], pos[2]), aim=(math.pi, 0)) for k in range(3)]
        o = self.obs_hp(pos, 1400, 10.0, mechs=hs)
        tr.update(o)
        self.assertEqual(s.update(o, False).state, RETREAT)

    def test_hide_spot_is_hidden_and_walkable(self):
        rng = random.Random(3)
        found = 0
        for _ in range(40):
            p = rng.choice(self.open)
            pos = (p[0], p[1], self.core.floor_z(*p))
            s, tr = self.setup(pos)
            ang = rng.uniform(0, 2 * math.pi)
            hp_ = (pos[0] + 70 * math.cos(ang), pos[1] + 70 * math.sin(ang))
            h = mech(5, (hp_[0], hp_[1], self.core.floor_z(*hp_)), aim=(ang + math.pi, 0))
            o = self.obs_hp(pos, 500, 10.0, mechs=[h],
                            events=[{"type": "damaged", "amount": 90, "weapon": "gun", "bearing": ang, "by": 5}])
            tr.update(o)
            t0 = time.perf_counter()
            spot = s.find_hide(o["self"], tr.hunters(pos))
            self.assertLess((time.perf_counter() - t0) * 1000, 15.0, "hide search too slow")
            if spot is None:
                continue
            found += 1
            eye = [h["pos"][0], h["pos"][1], h["pos"][2] + 8]
            z = self.core.floor_z(*spot)
            self.assertLess(self.core.shot_los(eye, (spot[0], spot[1], z + 4.5)), 1.0)
            self.assertLess(self.core.shot_los(eye, (spot[0], spot[1], z + 9.0)), 1.0)
            if math.dist(spot, pos[:2]) > 0.1:
                self.assertGreaterEqual(self.core.clearance(*spot) + 1e-6, CFG["mech"]["radius"])
        self.assertGreater(found, 20, "cover should usually exist within ~46 m on campus")

    def test_combat_holds_fire_while_retreating(self):
        c = Combat(CFG, None)
        me = (0.0, 0.0, 0.0)
        hit = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]
        c.observe(make_obs(me, events=hit))
        far = c.targets(make_obs(me, mechs=[mech(5, (50, 0, 0))]))
        self.assertIsNotNone(c.engage_target(far, 10.0, 230, retreat=False))
        self.assertIsNone(c.engage_target(far, 10.0, 230, retreat=True))               # hold fire at 50 m
        close = c.targets(make_obs(me, mechs=[mech(5, (20, 0, 0))]))
        self.assertIsNotNone(c.engage_target(close, 10.0, 230, retreat=True))          # cornered
        dying = c.targets(make_obs(me, mechs=[mech(5, (80, 0, 0), hp=150)]))
        self.assertIsNotNone(c.engage_target(dying, 10.0, 230, retreat=True))          # finish the kill


class BotReplayTest(unittest.TestCase):
    def test_replay_no_errors_and_fast(self):
        import mechfight as mf
        real_run = mf.run
        mf.run = lambda *a, **k: None
        try:
            import bot as B
        finally:
            mf.run = real_run
        with gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt") as f:
            L = [json.loads(line) for line in f]
        L[0]["map"]["dir"] = ARENA
        b = B.Bot(L[0])
        worst = 0.0
        states = set()
        for o in L[1:]:
            if o.get("type") != "obs":
                continue
            t0 = time.perf_counter()
            b.act(o)
            worst = max(worst, time.perf_counter() - t0)
            states.add(b.strategy.state)
        self.assertLess(worst * 1000, 30.0)
        self.assertIn(RETREAT, states, "the recorded mech took heavy damage; we should have retreated")


if __name__ == "__main__":
    unittest.main()
