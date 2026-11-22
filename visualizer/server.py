"""Local HTTP Server and REST API for the 2D Mech Royale Debug Visualizer.

Usage:
    python3 visualizer/server.py [--port 8000]
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import urllib.parse

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from map_export import generate_map
from recorder import record_squad, record_stream

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# In-memory replay cache: replay_id -> data dict
REPLAY_CACHE: dict[str, dict] = {}


def init_replays():
    """Ensure map exists and cache standard match replays on startup."""
    map_png = os.path.join(STATIC_DIR, "map.png")
    if not os.path.exists(map_png):
        print("Rendering map image...")
        generate_map()
        
    print("Pre-recording standard replays...")
    try:
        r1 = record_stream()
        REPLAY_CACHE[r1["id"]] = r1
        print("  Cached: Real Server Recording (stream.jsonl.gz)")
    except Exception as e:
        print(f"  Warning: stream replay failed: {e}")

    try:
        r2 = record_squad(seed=42, preset="best")
        REPLAY_CACHE[r2["id"]] = r2
        print("  Cached: Squad Match (seed 42, preset best)")
    except Exception as e:
        print(f"  Warning: squad replay failed: {e}")


class VisualizerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self.path = "/index.html"
            return super().do_GET()

        elif path == "/api/replays":
            items = []
            for rid, r in REPLAY_CACHE.items():
                items.append({
                    "id": r["id"],
                    "title": r.get("title", rid),
                    "source": r.get("source", ""),
                    "preset": r.get("preset", "best"),
                    "total_time": r.get("total_time", 0),
                    "frames_count": r.get("frames_count", 0),
                    "kills": r.get("kills", 0),
                    "events_count": len(r.get("events", [])),
                })
            self.send_json(items)

        elif path == "/api/replay":
            rid = query.get("id", [""])[0]
            if rid in REPLAY_CACHE:
                self.send_json(REPLAY_CACHE[rid])
            else:
                self.send_error(404, f"Replay '{rid}' not found")

        elif path == "/api/meta":
            meta_path = os.path.join(STATIC_DIR, "map_meta.json")
            if os.path.exists(meta_path):
                with open(meta_path, "r") as f:
                    meta = json.load(f)
                self.send_json(meta)
            else:
                meta = generate_map()
                self.send_json(meta)

        else:
            return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/simulate":
            length = int(self.headers.get("content-length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            try:
                params = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                params = {}

            seed = int(params.get("seed", 42))
            preset = str(params.get("preset", "best"))

            print(f"Running on-demand simulation: seed={seed}, preset={preset}...")
            try:
                replay = record_squad(seed=seed, preset=preset)
                REPLAY_CACHE[replay["id"]] = replay
                self.send_json(replay)
            except Exception as e:
                self.send_json({"error": str(e)}, status=500)
        else:
            self.send_error(404, "Endpoint not found")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Filter static file spam from stdout
        if "GET /api/" in (args[0] if args else "") or "POST /api/" in (args[0] if args else ""):
            super().log_message(format, *args)


def start_server(port: int = 8000):
    init_replays()
    handler = VisualizerHandler
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"\n=======================================================")
        print(f"  Mech Royale 2D Strategy Visualizer Ready!")
        print(f"  Open in Browser: http://localhost:{port}")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default 8000)")
    args = parser.parse_args()
    start_server(args.port)
