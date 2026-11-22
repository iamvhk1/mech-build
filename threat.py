"""Threat memory and the squad model.

Remembers every enemy mech we have seen (vision plus the server's 5 s tracking) or that hit us,
extrapolates where it is now, and decides who is *hunting* us. Practice house bots share vision,
so if any of them can see us we assume all of them know where we are.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

FORGET_S = 15.0         # drop a track not refreshed for this long
EXTRAPOLATE_S = 3.0     # extrapolate positions at most this far past the last sighting
HUNTER_RANGE_M = 150.0
HIT_RECENT_S = 8.0      # "hit us recently" for hunter status
CLOSING_SPEED = 2.0     # m/s toward us to count as closing in
NEAR_M = 80.0


class Track:
    __slots__ = ("id", "pos", "vel", "aim", "t_seen", "t_hit", "hp", "max_hp", "weapons", "cubes", "charging")

    def __init__(self, tid: int):
        self.id = tid
        self.pos = [0.0, 0.0, 0.0]
        self.vel = [0.0, 0.0, 0.0]
        self.aim = [0.0, 0.0]
        self.t_seen = -1e9
        self.t_hit = -1e9
        self.hp = 1.0
        self.max_hp = 1.0
        self.weapons: List[str] = []
        self.cubes = 0.0
        self.charging = False

    def pos_at(self, t: float) -> List[float]:
        dt = max(0.0, min(EXTRAPOLATE_S, t - self.t_seen))
        return [self.pos[0] + self.vel[0] * dt, self.pos[1] + self.vel[1] * dt, self.pos[2]]


class ThreatTracker:
    def __init__(self) -> None:
        self.tracks: Dict[int, Track] = {}
        self.t = 0.0
        self.damage: List[Tuple[float, float]] = []  # (t, amount) damage we took
        self.aggro_order: List[int] = []  # mech ids in the order they first hit us (practice: weakest first)

    def update(self, obs: dict) -> None:
        t = float(obs["t"])
        self.t = t
        me = obs["self"]
        for m in obs.get("mechs") or []:
            if m.get("kind") != "mech":
                continue
            tr = self.tracks.setdefault(int(m["id"]), Track(int(m["id"])))
            tr.pos = list(m["pos"])
            tr.vel = list(m.get("vel") or [0.0, 0.0, 0.0])
            tr.aim = list(m.get("aim") or [0.0, 0.0])
            tr.t_seen = t
            tr.hp = float(m.get("hp", tr.hp))
            tr.max_hp = float(m.get("max_hp", tr.max_hp)) or 1.0
            tr.weapons = list(m.get("weapons") or tr.weapons)
            tr.cubes = float(m.get("cubes", tr.cubes))
            tr.charging = bool(m.get("charging", False))
        for e in obs.get("events") or []:
            if e.get("type") == "damaged":
                self.damage.append((t, float(e.get("amount", 0.0))))
                by = e.get("by")
                if by is not None and int(by) < 100:  # mechs are ids 0-15
                    tr = self.tracks.setdefault(int(by), Track(int(by)))
                    tr.t_hit = t
                    if int(by) not in self.aggro_order:
                        self.aggro_order.append(int(by))
                    if tr.t_seen < t - 1.0 and e.get("bearing") is not None:
                        # unseen attacker: place it roughly along the bearing
                        b = float(e["bearing"])
                        tr.pos = [me["pos"][0] + 60 * math.cos(b), me["pos"][1] + 60 * math.sin(b), me["pos"][2]]
                        tr.vel = [0.0, 0.0, 0.0]
                        tr.t_seen = t - 1.0
            elif e.get("type") == "kill":
                self.tracks.pop(int(e.get("target", -1)), None)
        self.damage = [d for d in self.damage if t - d[0] < 10.0]
        self.tracks = {k: v for k, v in self.tracks.items() if t - max(v.t_seen, v.t_hit) < FORGET_S}

    def tier_mult(self, mid: int) -> float:
        """Practice squad sends weakest first: the n-th bot to hit us is roughly tier n // 4
        (4 easy, 4 medium, 4 hard, 3 expert). Unknown attackers count as the next one."""
        n = self.aggro_order.index(mid) if mid in self.aggro_order else len(self.aggro_order)
        return (0.4, 0.8, 1.2, 1.6)[min(3, n // 4)]

    def damage_taken(self, window: float) -> float:
        return sum(a for (tt, a) in self.damage if self.t - tt <= window)

    def last_damage_t(self) -> float:
        return max((tt for tt, _ in self.damage), default=-1e9)

    def hunters(self, me_pos: Sequence[float], rng: float = HUNTER_RANGE_M) -> List[Track]:
        """Mechs within range that hit us recently, are closing on us, or aim at us."""
        out = []
        for tr in self.tracks.values():
            p = tr.pos_at(self.t)
            dx, dy = me_pos[0] - p[0], me_pos[1] - p[1]
            d = math.hypot(dx, dy)
            if d > rng:
                continue
            hit = self.t - tr.t_hit < HIT_RECENT_S
            closing = d > 1e-6 and (tr.vel[0] * dx + tr.vel[1] * dy) / d > CLOSING_SPEED
            yaw = math.atan2(dy, dx)
            aiming = abs((tr.aim[0] - yaw + math.pi) % (2 * math.pi) - math.pi) < math.radians(10)
            fresh = self.t - tr.t_seen < 5.0
            if hit or (fresh and (aiming or (closing and d < NEAR_M))):
                out.append(tr)
        return out

    def nearest(self, me_pos: Sequence[float], tracks: Optional[List[Track]] = None) -> Optional[Track]:
        tracks = list(self.tracks.values()) if tracks is None else tracks
        return min(tracks, key=lambda tr: math.dist(tr.pos_at(self.t)[:2], me_pos[:2]), default=None)
