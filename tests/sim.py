"""A crude movement simulator for tests (not the real server).

Moves a mech using our own floor model: walls are rises above `step_up` at the mech's leading
edge, drops fall under gravity, jumps and jets follow the [mech] config. It exercises the
navigation logic end to end (waypoints, look-ahead, jumps, unsticking); it cannot prove
behaviour against the real server's physics.
"""
from __future__ import annotations

import math


class MiniSim:
    def __init__(self, core, cfg: dict, start, energy: float = 100.0):
        self.core = core
        self.m = dict(cfg["mech"])
        self.x, self.y = float(start[0]), float(start[1])
        self.z = core.floor_z(self.x, self.y)
        self.vz = 0.0
        self.grounded = True
        self.energy = energy
        self.t = 0.0
        self.tick = 0
        self.zone = {"center": [0.0, 0.0], "radius": 5000.0, "next_center": [0.0, 0.0], "next_radius": 5000.0,
                     "shrink_start": 1e6, "shrink_end": 1e6 + 1, "dps": 0}

    def obs(self) -> dict:
        st = dict(self.m)
        return {
            "type": "obs", "tick": self.tick, "t": self.t, "alive": 16,
            "self": {"id": 0, "pos": [self.x, self.y, self.z], "vel": [0, 0, self.vz], "aim": [0.0, 0.0],
                     "hp": 1400, "max_hp": 1400, "energy": self.energy, "max_energy": self.m["energy"],
                     "grounded": self.grounded, "cubes": 0, "upgrades": [], "in_zone": True,
                     "weapons": [None, None], "stats": st},
            "mechs": [], "projectiles": [], "crates": [], "cubes": [], "pickups": [], "sounds": [],
            "beams": [], "events": [], "drops": [], "zone": self.zone, "offer": None,
        }

    def _blocked(self, nx: float, ny: float, dx: float, dy: float) -> bool:
        r = self.m["radius"]
        for f in (0.0, r):  # centre and leading edge
            if self.core.floor_z(nx + dx * f, ny + dy * f) > self.z + self.m["step_up"] + 0.05:
                return True
        return False

    def apply(self, act: dict, dt: float = 0.1) -> None:
        m = self.m
        mv = act.get("move") or [0.0, 0.0]
        n = math.hypot(*mv)
        dx, dy = (mv[0] / n, mv[1] / n) if n > 1e-9 else (0.0, 0.0)
        mag = min(1.0, n)
        boost = bool(act.get("boost")) and self.energy > 0
        if act.get("jump") and self.grounded:
            self.vz = m["jump_speed"]
            self.grounded = False
        sub = 5
        h = dt / sub
        for _ in range(sub):
            if self.grounded:
                speed = (m["boost_speed"] if boost else m["walk_speed"]) * mag
                if boost:
                    self.energy = max(0.0, self.energy - m["boost_drain"] * h)
            else:
                speed = m["walk_speed"] * mag  # generous air control
                if boost:
                    self.vz = min(m["max_rise_speed"], self.vz + m["jet_accel"] * h)
                    self.energy = max(0.0, self.energy - m["jet_drain"] * h)
            nx, ny = self.x + dx * speed * h, self.y + dy * speed * h
            if speed > 0 and self._blocked(nx, ny, dx, dy):
                # slide along the wall: keep whichever axis is free
                if not self._blocked(nx, self.y, dx, 0.0):
                    ny = self.y
                elif not self._blocked(self.x, ny, 0.0, dy):
                    nx = self.x
                else:
                    nx, ny = self.x, self.y
            self.x, self.y = nx, ny
            f = self.core.floor_z(self.x, self.y)
            if self.grounded:
                if f < self.z - 0.6:
                    self.grounded = False  # walked off a ledge
                else:
                    self.z = f
            if not self.grounded:
                self.vz -= m["gravity"] * h
                self.z += self.vz * h
                if self.z <= f:
                    self.z, self.vz, self.grounded = f, 0.0, True
        if not boost:
            self.energy = min(m["energy"], self.energy + m["energy_regen"] * dt)
        self.t += dt
        self.tick += 2
