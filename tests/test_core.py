"""Tests for the C++ core (core/libmech_core.so) through core_api.

    make -C core && python3 -m unittest discover -s tests -v

Each test guards a specific in-match failure (see docs/implementation_plan.md and the Phase 1
plan). Timing tests can be skipped on a slow or busy machine with MECH_SKIP_TIMING=1.
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
import core_api  # noqa: E402

ARENA = os.path.join(ROOT, "arena")
STREAM = os.path.join(ROOT, "check", "stream.jsonl.gz")


def pip(ring, x, y) -> bool:
    n = len(ring) // 2
    inside = False
    for k in range(n):
        x0, y0 = ring[2 * k], ring[2 * k + 1]
        x1, y1 = ring[2 * ((k + 1) % n)], ring[2 * ((k + 1) % n) + 1]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def in_prism(p, x, y) -> bool:
    return pip(p["ring"], x, y) and not any(pip(h, x, y) for h in (p.get("holes") or []) if len(h) >= 6)


BOUNDS = (-510.0, 553.0, -331.0, 386.0)  # inside world.json bounds; some buildings extend past the map edge


def interior_point(p, margin: float = 3.0):
    """A point inside prism p, at least `margin` from its outline, inside the map (grid search)."""
    xs, ys = p["ring"][0::2], p["ring"][1::2]
    x0, x1 = max(min(xs), BOUNDS[0]), min(max(xs), BOUNDS[1])
    y0, y1 = max(min(ys), BOUNDS[2]), min(max(ys), BOUNDS[3])
    best = None
    step = max(0.5, min(x1 - x0, y1 - y0) / 20)
    y = y0 + step / 2
    while y < y1:
        x = x0 + step / 2
        while x < x1:
            if all(in_prism(p, x + dx, y + dy) for dx, dy in
                   ((0, 0), (margin, 0), (-margin, 0), (0, margin), (0, -margin))):
                best = (x, y)
                return best
            x += step
        y += step
    return best


class CoreTest(unittest.TestCase):
    core: core_api.MapCore
    world: dict
    config: dict
    stream: list

    @classmethod
    def setUpClass(cls):
        with gzip.open(STREAM, "rt") as f:
            cls.stream = [json.loads(line) for line in f]
        cls.config = cls.stream[0]["config"]
        with open(os.path.join(ARENA, "v2", "world.json")) as f:
            cls.world = json.load(f)
        cls.core = core_api.MapCore.from_dir(ARENA, cls.config)
        c = cls.core
        g = c.layer(core_api.LAYER_GROUND)
        cls.ground_cells = [k for k, v in enumerate(g) if v]
        cls.radius = cls.config["mech"]["radius"]

    def cell_xy(self, k):
        c = self.core
        return c.min_x + (k % c.nnx) * c.res, c.min_y + (k // c.nnx) * c.res

    # ------------------------------------------------------------ terrain and floor

    def test_terrain_matches_raw_file(self):
        """Wrong byte order, row order or offset would corrupt every height and LOS check."""
        import array
        raw = array.array("h")
        with open(os.path.join(ARENA, "v2", "terrain.i16"), "rb") as f:
            raw.frombytes(f.read())
        t = self.world["terrain"]
        rng = random.Random(7)
        for _ in range(500):
            i, j = rng.randrange(t["nx"]), rng.randrange(t["ny"])
            x, y = t["minX"] + i * t["step"], t["minY"] + j * t["step"]
            self.assertAlmostEqual(self.core.ground_z(x, y), raw[j * t["nx"] + i] * t["scale"], places=3)

    def test_floor_tall_building_is_roof_and_not_ground(self):
        """Paths must not go through buildings or onto unclimbable roofs."""
        checked = 0
        for p in self.world["prisms"]:
            if p["kind"] != "building":
                continue
            pt = interior_point(p, 5.0)
            if not pt or p["top"] - self.core.ground_z(*pt) < 15:
                continue
            self.assertGreaterEqual(self.core.floor_z(*pt), p["top"] - 0.01)
            self.assertFalse(self.core.is_ground(*pt), f"roof at {pt} is in the street component")
            checked += 1
            if checked >= 20:
                break
        self.assertGreater(checked, 5)

    def test_floor_street_is_terrain(self):
        """No phantom walls in open streets."""
        rng = random.Random(3)
        for k in rng.sample(self.ground_cells, 300):
            x, y = self.cell_xy(k)
            if self.core.clearance(x, y) >= 6:
                self.assertAlmostEqual(self.core.floor_z(x, y), self.core.ground_z(x, y), delta=0.01)

    def bridges(self, high: bool):
        for p in self.world["prisms"]:
            if p["kind"] != "bridge":
                continue
            pt = interior_point(p, 1.0)
            if not pt:
                continue
            gz = self.core.ground_z(*pt)
            if high and p["base"] - gz >= self.config["mech"]["height"] + 0.5:
                yield p, pt, gz
            if not high and p["base"] - gz < 2.0:
                yield p, pt, gz

    def test_floor_low_bridge_is_deck(self):
        """Low bridges are walked on: the floor is the deck."""
        found = list(self.bridges(high=False))
        self.assertTrue(found)
        for p, pt, gz in found:
            self.assertAlmostEqual(self.core.floor_z(*pt), max(p["top"], gz), delta=0.01)

    def test_floor_under_high_bridge_is_walkable_ground(self):
        """High bridges are walked under, not walls splitting the map."""
        found = list(self.bridges(high=True))
        self.assertTrue(found)
        for p, pt, gz in found:
            self.assertAlmostEqual(self.core.floor_z(*pt), gz, delta=0.01)

    def test_floor_matches_recorded_match(self):
        """Only test against the real server: grounded feet must sit on our floor model."""
        n = 0
        for o in self.stream[1:]:
            if o.get("type") != "obs":
                continue
            samples = []
            if o["self"]["grounded"]:
                samples.append(o["self"]["pos"])
            samples += [m["pos"] for m in o["mechs"] if abs(m["vel"][2]) < 0.01]
            for x, y, z in samples:
                self.assertLess(abs(self.core.floor_z(x, y) - z), 0.3, f"floor mismatch at {(x, y, z)}")
                n += 1
        self.assertGreater(n, 100)

    # ------------------------------------------------------------ line of sight

    def test_los_through_building_blocked(self):
        """The bounding-box bug: shots into walls, or a false sense of cover."""
        checked = 0
        for p in self.world["prisms"]:
            if p["kind"] != "building":
                continue
            pt = interior_point(p, 4.0)
            if not pt:
                continue
            gz = self.core.ground_z(*pt)
            if p["top"] - gz < 12:
                continue
            xs = p["ring"][0::2]
            z = gz + 6
            a = (min(xs) - 5, pt[1], z)
            b = (max(xs) + 5, pt[1], z)
            f = self.core.shot_los(a, b)
            self.assertLess(f, 1.0)
            hx = a[0] + (b[0] - a[0]) * f
            self.assertLessEqual(hx, pt[0] + 0.01, "first hit must be before the interior point")
            # vertical ray from above the roof down into it
            self.assertLess(self.core.shot_los((pt[0], pt[1], p["top"] + 20), (pt[0], pt[1], p["top"] - 1)), 1.0)
            checked += 1
            if checked >= 20:
                break
        self.assertGreater(checked, 5)

    def test_los_open_street_clear(self):
        """Never firing at visible enemies in the open."""
        rng = random.Random(5)
        n = 0
        for k in rng.sample(self.ground_cells, 2000):
            x, y = self.cell_xy(k)
            if self.core.clearance(x, y) < 6:
                continue
            z = self.core.floor_z(x, y) + 8
            self.assertEqual(self.core.shot_los((x - 3, y, z), (x + 3, y, z)), 1.0, f"blocked at {(x, y)}")
            n += 1
            if n >= 100:
                break
        self.assertGreater(n, 50)

    def test_los_beneath_high_bridge_clear(self):
        """Shots go under bridges; the deck itself blocks."""
        for p, pt, gz in self.bridges(high=True):
            x, y = pt
            self.assertEqual(self.core.shot_los((x, y, gz + 1), (x + 0.5, y, gz + 3)), 1.0)
            self.assertLess(self.core.shot_los((x, y, p["base"] - 1), (x, y, p["top"] + 1)), 1.0)

    def test_tree_crown_blocks_vision_not_shots(self):
        """Firing blind into trees at sounds works; dense crowns hide us."""
        t = self.world["trees"]
        f = t["fields"]
        stride = len(f)
        d = t["data"]
        idx = {k: f.index(k) for k in ("z", "height", "crownR", "crownBase", "crownX", "crownY")}
        checked = 0
        for k in range(len(d) // stride):
            row = d[k * stride:(k + 1) * stride]
            r = row[idx["crownR"]]
            if r < 4.5:
                continue
            cz = row[idx["z"]] + 0.5 * (row[idx["crownBase"]] + row[idx["height"]])
            cx, cy = row[idx["crownX"]], row[idx["crownY"]]
            a, b = (cx - r - 0.5, cy, cz), (cx + r + 0.5, cy, cz)
            if self.core.shot_los(a, b) < 1.0:
                continue  # a building or terrain is in the way; not a tree-only line
            self.assertFalse(self.core.vision_los(a, b), f"crown at {(cx, cy)} did not block vision")
            checked += 1
            if checked >= 20:
                break
        self.assertGreater(checked, 5)

    # ------------------------------------------------------------ pathfinding

    def far_pairs(self, n, seed, min_d=300):
        rng = random.Random(seed)
        out = []
        while len(out) < n:
            a, b = self.cell_xy(rng.choice(self.ground_cells)), self.cell_xy(rng.choice(self.ground_cells))
            if math.dist(a, b) > min_d:
                out.append((a, b))
        return out

    def assert_path_ok(self, start, path, radius):
        self.assertTrue(path)
        prev = start
        for wp in path:
            self.assertGreaterEqual(self.core.clearance(*wp) + 1e-6, radius, f"waypoint {wp} too tight")
            self.assertTrue(self.core.segment_walkable(prev, wp, radius), f"segment {prev}->{wp} not walkable")
            prev = wp

    def test_path_across_map_exists(self):
        """A split map means the bot can't reach the zone. Every waypoint fits the mech."""
        for a, b in self.far_pairs(20, 11):
            p = self.core.find_path(a, b, self.radius)
            self.assertIsNotNone(p, f"no path {a}->{b}")
            self.assertLess(math.dist(p[-1], b), 3.0)
            self.assert_path_ok(a, p, self.radius)

    def test_goal_inside_building_snaps_outside(self):
        """A zone centre or drop on a building must still give a usable path."""
        rng = random.Random(4)
        checked = 0
        for p in self.world["prisms"]:
            if p["kind"] != "building":
                continue
            pt = interior_point(p, 5.0)
            if not pt or p["top"] - self.core.ground_z(*pt) < 8:
                continue
            start = self.cell_xy(rng.choice(self.ground_cells))
            path = self.core.find_path(start, pt, self.radius)
            self.assertIsNotNone(path)
            end = path[-1]
            self.assertFalse(in_prism(p, *end), f"goal {pt} not moved out of the building")
            self.assertTrue(self.core.is_ground(*end))
            checked += 1
            if checked >= 10:
                break
        self.assertGreater(checked, 3)

    def test_larger_radius_never_takes_narrower_gap(self):
        """Mechs grow 5% per cube; a big mech must not be routed through small gaps."""
        big = self.radius * 1.5
        clear = self.core.layer(core_api.LAYER_CLEARANCE)
        self.assertLess(sum(1 for v in clear if v >= big), sum(1 for v in clear if v >= self.radius))
        for a, b in self.far_pairs(10, 12):
            a2 = self.core.nearest_walkable(*a, big)
            p = self.core.find_path(a2, b, big)
            if p is None:
                continue
            self.assert_path_ok(a2, p, big)

    def test_threat_path_avoids_threat(self):
        """With a threat, the path keeps further away on average than without."""
        a, b = self.far_pairs(1, 21, min_d=250)[0]
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        plain = self.core.find_path(a, b, self.radius)
        avoid = self.core.find_path(a, b, self.radius, threats=[(mid[0], mid[1], 120, 4.0)])
        self.assertTrue(plain and avoid)

        def closest(path):
            pts = [a] + path
            best = 1e9
            for p, q in zip(pts, pts[1:]):
                for k in range(11):
                    x, y = p[0] + (q[0] - p[0]) * k / 10, p[1] + (q[1] - p[1]) * k / 10
                    best = min(best, math.dist((x, y), mid))
            return best

        self.assertGreaterEqual(closest(avoid), closest(plain))

    def test_steer_open_ground_follows_waypoint(self):
        rng = random.Random(8)
        n = 0
        for k in rng.sample(self.ground_cells, 2000):
            x, y = self.cell_xy(k)
            if self.core.clearance(x, y) < 6:
                continue
            dx, dy, _ = self.core.steer((x, y), (x + 20, y + 20), self.radius, 11.7)
            self.assertGreater(dx * math.sqrt(0.5) + dy * math.sqrt(0.5), 0.9)
            n += 1
            if n >= 30:
                break
        self.assertGreater(n, 10)

    def test_steer_avoids_shell(self):
        x, y = self.cell_xy(self.ground_cells[len(self.ground_cells) // 2])
        # shell landing right where moving toward the waypoint would take us
        dx, dy, _ = self.core.steer((x, y), (x + 30, y), self.radius, 11.7, shells=[(x + 6, y, 7.0, 0.5)])
        self.assertLess(dx, 0.5)

    # ------------------------------------------------------------ ballistics

    def test_gun_lead_hits_moving_target(self):
        """Missing moving targets wastes the main damage source."""
        rng = random.Random(9)
        for _ in range(50):
            m = (0.0, 0.0, 7.0)
            t = (rng.uniform(-150, 150), rng.uniform(-150, 150), rng.uniform(0, 10))
            v = (rng.uniform(-15, 15), rng.uniform(-15, 15), 0.0)
            yaw, pitch, ft = core_api.gun_lead(m, t, v, 252.0, 3.0)
            d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
            bullet = [m[i] + 3.0 * d[i] + 252.0 * ft * d[i] for i in range(3)]
            target = [t[i] + v[i] * ft for i in range(3)]
            self.assertLess(math.dist(bullet, target), 0.2)

    def test_mortar_lands_on_target(self):
        """Lobs over cover and shell-dodge predictions depend on this."""
        w = self.config["weapons"]["mortar"]
        v, g = w["speed"], w["gravity"]
        rng = random.Random(10)
        for high in (False, True):
            for _ in range(30):
                m = (0.0, 0.0, 9.5)
                t = (rng.uniform(-180, 180), rng.uniform(-180, 180), rng.uniform(-5, 10))
                if math.hypot(t[0], t[1]) < 20:
                    continue
                sol = core_api.mortar_pitch(m, t, v, g, 3.0, high, -0.7, 1.5)
                if sol is None:
                    continue
                yaw, pitch, ft = sol
                d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
                o = [m[i] + 3.0 * d[i] for i in range(3)]
                land = [o[0] + v * d[0] * ft, o[1] + v * d[1] * ft, o[2] + v * d[2] * ft - 0.5 * g * ft * ft]
                self.assertLess(math.dist(land, t), 1.0)

    def test_shell_impact_on_open_ground(self):
        g = self.config["weapons"]["mortar"]["gravity"]
        rng = random.Random(12)
        n = 0
        for k in rng.sample(self.ground_cells, 2000):
            x, y = self.cell_xy(k)
            if self.core.clearance(x, y) < 6:
                continue
            z = self.core.floor_z(x, y)
            hit = self.core.shell_impact((x, y, z + 40), (3.0, 0.0, 0.0), g)
            self.assertIsNotNone(hit)
            self.assertLess(abs(hit[2] - self.core.ground_z(hit[0], hit[1])), 1.0)
            n += 1
            if n >= 20:
                break

    # ------------------------------------------------------------ timing

    @unittest.skipIf(os.environ.get("MECH_SKIP_TIMING"), "timing skipped")
    def test_timing(self):
        """Missing the 50 ms decision or 20 s startup budget makes the mech coast, then idle."""
        self.assertLess(self.core.load_ms, 2000)
        rng = random.Random(1)
        segs = []
        while len(segs) < 1000:
            a, b = self.cell_xy(rng.choice(self.ground_cells)), self.cell_xy(rng.choice(self.ground_cells))
            if 50 < math.dist(a, b) < 200:
                segs.append((a[0], a[1], self.core.floor_z(*a) + 8, b[0], b[1], self.core.floor_z(*b) + 4.5))
        t0 = time.perf_counter()
        self.core.shot_los_batch(segs)
        self.assertLess((time.perf_counter() - t0) * 1000, 5.0, "1000 LOS (incl. Python marshalling)")

        times = []
        for a, b in self.far_pairs(100, 2):
            t0 = time.perf_counter()
            self.core.find_path(a, b, self.radius)
            times.append(time.perf_counter() - t0)
        self.assertLess(sum(times) / len(times) * 1000, 5.0, "path average")
        self.assertLess(max(times) * 1000, 20.0, "path max")

        rng = random.Random(3)
        times = []
        for _ in range(50):
            th = [self.cell_xy(rng.choice(self.ground_cells)) + (200, 1.0) for _ in range(3)]
            a, b = self.cell_xy(rng.choice(self.ground_cells)), self.cell_xy(rng.choice(self.ground_cells))
            t0 = time.perf_counter()
            self.core.find_path(a, b, self.radius, threats=th, zone=(0, 0, 250, 1.0), cover_weight=0.3)
            times.append(time.perf_counter() - t0)
        self.assertLess(sum(times) / len(times) * 1000, 5.0, "threat path average")
        self.assertLess(max(times) * 1000, 20.0, "threat path max")


if __name__ == "__main__":
    unittest.main()
