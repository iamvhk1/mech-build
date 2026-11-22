#!/usr/bin/env python3
"""Run the Local 2D Debug Visualizer.

Usage:
    python3 visualizer/run.py [--port 8000]
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

from server import start_server


def main():
    parser = argparse.ArgumentParser(description="Mech Royale 2D Strategy Visualizer")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    args = parser.parse_args()

    start_server(args.port)


if __name__ == "__main__":
    main()
