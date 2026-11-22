"""Tests for the 2D debug visualizer recorder and data endpoints."""
from __future__ import annotations

import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "visualizer"))

from map_export import generate_map
from recorder import record_squad, record_stream


class VisualizerTest(unittest.TestCase):
    def test_map_export(self):
        meta = generate_map()
        self.assertIn("min_x", meta)
        self.assertIn("max_x", meta)
        self.assertIn("img_w", meta)
        self.assertEqual(meta["img_w"], 1070)
        self.assertEqual(meta["img_h"], 724)
        map_png = os.path.join(ROOT, "visualizer", "static", "map.png")
        self.assertTrue(os.path.exists(map_png))
        self.assertGreater(os.path.getsize(map_png), 1000)

    def test_record_stream(self):
        rec = record_stream()
        self.assertEqual(rec["id"], "server_match")
        self.assertGreaterEqual(rec["frames_count"], 300)
        self.assertIn("frames", rec)
        first_frame = rec["frames"][0]
        self.assertIn("t", first_frame)
        self.assertIn("self", first_frame)
        self.assertIn("zone", first_frame)
        self.assertIn("pos", first_frame["self"])

    def test_record_squad(self):
        rec = record_squad(seed=42, preset="best")
        self.assertTrue(rec["id"].startswith("squad_"))
        self.assertGreater(rec["frames_count"], 100)
        self.assertIn("kills", rec)
        self.assertIn("events", rec)
        first_frame = rec["frames"][0]
        self.assertIn("t", first_frame)
        self.assertIn("self", first_frame)
        self.assertIn("zone", first_frame)


if __name__ == "__main__":
    unittest.main()
