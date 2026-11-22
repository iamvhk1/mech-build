"""Cube economy (master plan Stage C).

C1 `farm.crates`: shoot street-level crates (300 HP, 1 cube, 50% weapon drop) and collect their
cube, only when it's safe: no enemy to fight, HP high enough, no known hunter nearby, the zone
leaves time for the detour.
C3 `farm.cubes`: also walk over any other visible cube (kill drops) when safe.

Crates and cubes are listed only while visible, so we remember them and forget one when we're
close enough that we should see it and don't.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import tuning

FORGET_NEAR_M = 45.0      # protocol §8: within near_range with no building in the way we always see it
MAX_AGE_S = 90.0          # forget remembered items after this long
CRATE_ON_GROUND_M = 2.0   # crate base within this of the street floor: not on a roof
CUBE_SPEED_MARGIN_S = 10.0
SHOOT_FROM_M = 18.0       # stop approaching a crate this close once we have a clear shot


class Item:
    __slots__ = ("id", "pos", "hp", "t")

    def __init__(self, iid: int, pos, hp: float, t: float):
        self.id, self.pos, self.hp, self.t = iid, list(pos), hp, t


BANK_HP = 0.95          # farm.bank: at or above this HP fraction, leave cubes on the floor
BANK_USE_HP = 0.70      # ...and walk over a remembered one within BANK_USE_M below this
BANK_USE_M = 25.0


class Farmer:
    def __init__(self, core, cfg: dict):
        self.core = core
        self.cfg = cfg
        self.crates: Dict[int, Item] = {}
        self.cubes: Dict[int, Item] = {}
        self.drones: Dict[int, Item] = {}
        self.target: Optional[Item] = None   # crate we're shooting
        self.target_drone: Optional[Item] = None  # drone we're shooting
        self.crate_spots: Dict[int, Tuple[float, float]] = {}  # where crates we shot at stood
        self.street: Dict[Tuple[str, int], bool] = {}         # cached on-street check per item
        self.mode = ""

    # ------------------------------------------------------------ memory

    def observe(self, obs: dict) -> None:
        t = float(obs["t"])
        me = obs["self"]["pos"]
        seen_cr = {int(c["id"]) for c in obs.get("crates") or []}
        seen_cu = {int(c["id"]) for c in obs.get("cubes") or []}
        seen_dr = {int(m["id"]) for m in obs.get("mechs") or [] if m.get("kind") == "npc"}
        for c in obs.get("crates") or []:
            self.crates[int(c["id"])] = Item(int(c["id"]), c["pos"], float(c.get("hp", 300.0)), t)
        for c in obs.get("cubes") or []:
            self.cubes[int(c["id"])] = Item(int(c["id"]), c["pos"], 0.0, t)
        for m in obs.get("mechs") or []:
            if m.get("kind") == "npc":
                self.drones[int(m["id"])] = Item(int(m["id"]), m["pos"], float(m.get("hp", 350.0)), t)
        near = float(self.cfg.get("vision", {}).get("near_range", FORGET_NEAR_M))
        for store, seen in ((self.crates, seen_cr), (self.cubes, seen_cu)):
            for iid in list(store):
                it = store[iid]
                if iid in seen:
                    continue
                gone = math.dist(it.pos[:2], me[:2]) < near and self._visible_from(obs, it.pos)
                if gone or t - it.t > MAX_AGE_S:
                    del store[iid]
        for did in list(self.drones):
            it = self.drones[did]
            if did in seen_dr:
                continue
            gone = (math.dist(it.pos[:2], me[:2]) < near and self._visible_from(obs, it.pos)) or (t - it.t > 5.0)
            if gone or it.hp <= 0:
                del self.drones[did]
        # a cube where a crate or drone stood: it was destroyed
        for cid in list(self.crates):
            cp = self.crates[cid].pos
            if any(math.dist(cu.pos[:2], cp[:2]) <= 3.0 for cu in self.cubes.values()):
                del self.crates[cid]
        for did in list(self.drones):
            dp = self.drones[did].pos
            if any(math.dist(cu.pos[:2], dp[:2]) <= 3.0 for cu in self.cubes.values()):
                del self.drones[did]
        if self.target is not None and self.target.id not in self.crates:
            self.target = None
        if self.target_drone is not None and self.target_drone.id not in self.drones:
            self.target_drone = None

    def _visible_from(self, obs: dict, pos) -> bool:
        """Within proximity range, would we see an item at pos? Protocol §8: buildings block the
        proximity sensors, canopy does not, so this is a building/terrain line check."""
        if self.core is None:
            return True
        me = obs["self"]
        x, y, z = me["pos"]
        eye = z + float((me.get("stats") or {}).get("eye_height", 8.0))
        return self.core.shot_los((x, y, eye), (pos[0], pos[1], pos[2] + 1.0)) >= 1.0

    # ------------------------------------------------------------ choice

    def safe(self, me: dict, hunters, threats, has_target: bool) -> bool:
        if has_target:
            return False
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        if hp < tuning.get("farm.min_hp"):
            return False
        safe_m = tuning.get("farm.safe_m")
        return all(math.dist(h.pos_at(threats.t)[:2], me["pos"][:2]) > safe_m for h in hunters)

    def safe_for_drone(self, me: dict, hunters, threats, has_target: bool) -> bool:
        if has_target:
            return False
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        if hp < tuning.get("farm.drone_min_hp"):
            return False
        safe_m = tuning.get("farm.safe_m")
        if any(math.dist(h.pos_at(threats.t)[:2], me["pos"][:2]) <= safe_m for h in hunters):
            return False
        t = threats.t
        for tr in threats.tracks.values():
            if math.dist(tr.pos_at(t)[:2], me["pos"][:2]) <= 90.0:
                return False
        return True

    def bank_goal(self, me: dict, zone, walk: float):
        """farm.bank: the nearest remembered cube within BANK_USE_M when HP is below BANK_USE_HP."""
        if not tuning.get("farm.bank"):
            return None
        hp = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        if hp >= BANK_USE_HP:
            return None
        pos = me["pos"]
        best, bd = None, BANK_USE_M
        for c in self.cubes.values():
            d = math.dist(c.pos[:2], pos[:2])
            if d >= bd:
                continue
            if zone is not None and getattr(zone, "known", False) and \
                    zone.time_until_outside(c.pos) <= d / max(1.0, walk) + 5.0:
                continue
            best, bd = c, d
        if best is None:
            return None
        self.mode = f"bank {best.id}"
        return (best.pos[0], best.pos[1])

    def on_street(self, pos) -> bool:
        if self.core is None:
            return True
        return abs(pos[2] - self.core.floor_z(pos[0], pos[1])) <= CRATE_ON_GROUND_M and \
            self.core.nearest_walkable(pos[0], pos[1], 2.5, True) is not None and \
            not self._on_roof(pos)

    def _street(self, kind: str, it: Item) -> bool:
        """Cached on_street per item (items don't move; the map never changes)."""
        key = (kind, it.id)
        if key not in self.street:
            self.street[key] = self.on_street(it.pos)
        return self.street[key]

    def _on_roof(self, pos) -> bool:
        # the street floor near the crate is well below the crate: it's up on a building
        street = self.core.nearest_walkable(pos[0], pos[1], 2.5, True)
        return street is not None and pos[2] - self.core.floor_z(*street) > CRATE_ON_GROUND_M

    def plan(self, obs: dict, zone, hunters, threats, has_target: bool) -> Optional[Tuple[float, float]]:
        """Where to walk for farming this decision, or None. Sets self.target (crate to shoot)."""
        self.mode = ""
        me = obs["self"]
        if not self.safe(me, hunters, threats, has_target):
            self.target = None
            return None
        st = me.get("stats") or {}
        walk = float(st.get("walk_speed", 11.7))
        pos = me["pos"]
        max_d = tuning.get("farm.max_dist")

        def zone_ok(p) -> bool:
            if zone is None or not zone.known:
                return True
            return zone.time_until_outside(p) > math.dist(p[:2], pos[:2]) / max(1.0, walk) + CUBE_SPEED_MARGIN_S

        # 1) a cube nearby (from our crate, or any cube with farm.cubes); with farm.bank, leave cubes on
        # the floor at high HP and come back for them as instant heals mid-fight
        hp_frac = float(me.get("hp", 1.0)) / max(1.0, float(me.get("max_hp", 1.0)))
        banking = bool(tuning.get("farm.bank")) and hp_frac >= BANK_HP
        if (tuning.get("farm.crates") or tuning.get("farm.cubes")) and not banking:
            cubes = [c for c in self.cubes.values()
                     if math.dist(c.pos[:2], pos[:2]) <= max_d and zone_ok(c.pos) and self._street("cube", c)]
            if not tuning.get("farm.cubes"):
                cubes = [c for c in cubes if self._from_our_crate(c)]
            if cubes:
                c = min(cubes, key=lambda c: math.dist(c.pos[:2], pos[:2]))
                self.mode = f"cube {c.id}"
                return (c.pos[0], c.pos[1])
        # 2) a drone to shoot (C2)
        if tuning.get("farm.drones") and self.safe_for_drone(me, hunters, threats, has_target):
            if self.target_drone is not None and self.target_drone.id in self.drones:
                self.target_drone = self.drones[self.target_drone.id]  # audit A3: latest position, not first seen
            if self.target_drone is None or self.target_drone.id not in self.drones:
                drones = [d for d in self.drones.values()
                          if math.dist(d.pos[:2], pos[:2]) <= max_d and zone_ok(d.pos) and self._street("npc", d)]
                self.target_drone = min(drones, key=lambda d: math.dist(d.pos[:2], pos[:2])) if drones else None
            if self.target_drone is not None:
                self.mode = f"drone {self.target_drone.id}"
                d = math.dist(self.target_drone.pos[:2], pos[:2])
                d_min = float(tuning.get("farm.drone_dist_min"))
                d_max = float(tuning.get("farm.drone_dist_max"))
                if d_min <= d <= d_max and self._clear_shot_at_drone(me):
                    return (pos[0], pos[1])
                return (self.target_drone.pos[0], self.target_drone.pos[1])
        else:
            self.target_drone = None
        # 3) a crate to shoot
        if tuning.get("farm.crates"):
            if self.target is None or self.target.id not in self.crates:
                crates = [c for c in self.crates.values()
                          if math.dist(c.pos[:2], pos[:2]) <= max_d and zone_ok(c.pos) and self._street("crate", c)]
                self.target = min(crates, key=lambda c: math.dist(c.pos[:2], pos[:2])) if crates else None
            if self.target is not None:
                self.mode = f"crate {self.target.id}"
                self.crate_spots[self.target.id] = (self.target.pos[0], self.target.pos[1])
                # close enough with a clear shot: stand and shoot (shots spawn 3 m out along the
                # aim, so walking right up to the crate would make them spawn past it)
                d = math.dist(self.target.pos[:2], pos[:2])
                if d <= SHOOT_FROM_M and self._clear_shot_at_crate(me):
                    return (pos[0], pos[1])
                return (self.target.pos[0], self.target.pos[1])
        return None

    def _from_our_crate(self, cube: Item) -> bool:
        """Cubes that appear where a crate we were shooting stood are ours to collect under C1."""
        return any(math.dist(cube.pos[:2], spot) <= 3.0 for spot in self.crate_spots.values())

    def _clear_shot_at_crate(self, me: dict) -> bool:
        aim = self.crate_aim()
        if aim is None or self.core is None:
            return aim is not None
        x, y, z = me["pos"]
        mz = (x, y, z + float((me.get("stats") or {}).get("muzzle_height", 7.0)))
        return self.core.shot_los(mz, aim) >= 1.0

    def crate_aim(self) -> Optional[List[float]]:
        """Centre of the crate we're shooting (for combat), or None."""
        if self.target is None:
            return None
        h = float(self.cfg.get("crates", {}).get("height", 2.4))
        p = self.target.pos
        return [p[0], p[1], p[2] + h * 0.5]

    def _clear_shot_at_drone(self, me: dict) -> bool:
        if self.target_drone is None or self.core is None:
            return self.target_drone is not None
        x, y, z = me["pos"]
        mz = (x, y, z + float((me.get("stats") or {}).get("muzzle_height", 7.0)))
        p = self.target_drone.pos
        h = float(self.cfg.get("npc", {}).get("height", 3.5))
        aim = (p[0], p[1], p[2] + h * 0.5)
        return self.core.shot_los(mz, aim) >= 1.0
