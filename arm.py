"""Arm up early (switch `arm.early`, 2026-11-22).

Lightning is our strongest close-range weapon: 240 damage/s, instant, it hits the nearest target in
a 30 deg cone within 45 m with no aiming (the gun sustains ~100/s and must lead). Combat only takes a
lightning that is visible within 40 m right now, so in the recorded match four lightnings were seen
at 81-196 m and slot 1 stayed empty. This remembers every weapon pickup we see and, while slot 1 is
empty and no hunter is close, walks to the nearest known street-level lightning within reach.
Combat's take_action picks it up on arrival (the pickup dict has the same shape as obs.pickups).
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import tuning

FORGET_NEAR_M = 25.0   # a remembered pickup this close that isn't in view is gone (someone took it)
MAX_AGE_S = 150.0      # forget pickups not seen for this long
ZONE_MARGIN_S = 10.0
MIN_HP = 0.40
KEEP_MULT = 1.25      # keep a chosen target out to this multiple of arm.max_dist (no flicker at the edge)


class Armer:
    def __init__(self, core, cfg: dict, farmer):
        self.core = core
        self.cfg = cfg
        self.farmer = farmer   # reuses its street / roof check
        self.known: Dict[int, dict] = {}   # id -> pickup dict, plus "t" last seen
        self.street: Dict[int, bool] = {}
        self.target_id: Optional[int] = None
        self.target_roof = False   # the chosen pickup is up on a roof (navigation must allow roof jumps)
        self.mode = ""

    def observe(self, obs: dict) -> None:
        t = float(obs["t"])
        me = obs["self"]["pos"]
        seen = set()
        for p in obs.get("pickups") or []:
            pid = int(p["id"])
            seen.add(pid)
            self.known[pid] = {"id": pid, "kind": p.get("kind"), "pos": list(p["pos"]), "t": t}
        for e in obs.get("events") or []:
            if e.get("type") in ("took", "take_failed") and e.get("id") is not None:
                if e.get("type") == "took" or e.get("reason") == "gone":
                    self.known.pop(int(e["id"]), None)
        for pid in list(self.known):
            p = self.known[pid]
            if pid in seen:
                continue
            if t - p["t"] > MAX_AGE_S or math.dist(p["pos"][:2], me[:2]) < FORGET_NEAR_M:
                del self.known[pid]

    def _on_street(self, p: dict) -> bool:
        pid = p["id"]
        if pid not in self.street:
            self.street[pid] = self.farmer.on_street(p["pos"]) if self.farmer is not None else True
        return self.street[pid]

    def plan(self, obs: dict, zone, hunters, threats, walk: float) -> Optional[dict]:
        """The pickup to walk to and take, or None."""
        self.mode = ""
        if not tuning.get("arm.early"):
            return None
        me = obs["self"]
        weapons = me.get("weapons") or [None, None]
        kind1 = weapons[1].get("kind") if len(weapons) > 1 and weapons[1] else None
        if kind1 not in (None, "laser"):
            return None  # slot 1 holds lightning or a mortar: combat's own policy handles swaps
        if kind1 == "laser" and float(weapons[1].get("charge", 0.0)) > 0:
            return None  # can't swap a charging laser
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        if hp < MIN_HP:
            return None
        pos = me["pos"]
        tt = getattr(threats, "t", float(obs["t"]))
        safe_m = float(tuning.get("arm.safe_m"))
        if any(math.dist(h.pos_at(tt)[:2], pos[:2]) <= safe_m for h in hunters):
            return None
        max_d = float(tuning.get("arm.max_dist"))
        best, bd = None, max_d
        first = "laser" if tuning.get("arm.prefer_laser") else "lightning"
        roof_until = tuning.get("arm.roof_until")
        roof_ok = roof_until is not None and float(obs["t"]) < float(roof_until) and \
            float(me.get("energy", 0.0)) >= 60.0
        if first == "laser" and kind1 == "laser":
            return None  # already hold the preferred weapon
        for p in self.known.values():
            if p["kind"] != first:
                continue
            d = math.dist(p["pos"][:2], pos[:2])
            limit = bd if p["id"] != self.target_id else max(bd, max_d * KEEP_MULT)
            if d >= limit or (not self._on_street(p) and not roof_ok):
                continue
            if zone is not None and getattr(zone, "known", False) and \
                    zone.time_until_outside(p["pos"]) <= d / max(1.0, walk) + ZONE_MARGIN_S:
                continue
            best, bd = p, d
        laser_after = tuning.get("arm.laser_after")
        if best is None and kind1 is None and laser_after is not None and float(obs["t"]) >= float(laser_after):
            # no lightning within reach: a laser (315 damage, instant, 280 m) beats the gun alone
            bd = max_d
            for p in self.known.values():
                if p["kind"] != "laser":
                    continue
                d = math.dist(p["pos"][:2], pos[:2])
                limit = bd if p["id"] != self.target_id else max(bd, max_d * KEEP_MULT)
                if d >= limit or not self._on_street(p):
                    continue
                if zone is not None and getattr(zone, "known", False) and \
                        zone.time_until_outside(p["pos"]) <= d / max(1.0, walk) + ZONE_MARGIN_S:
                    continue
                best, bd = p, d
        self.target_id = best["id"] if best is not None else None
        self.target_roof = best is not None and not self._on_street(best)
        if best is not None:
            self.mode = f"arm {best['kind']} {bd:.0f}m"
        return best
