"""Mode detection (Stage D, roadmap item E6).

Detects whether the current match is a practice match (1 vs 15-bot squad, where house bots never
kill each other) or a free-for-all match (16 independent bots, where third parties fight and
eliminate each other).

Detection rule:
- An unassisted death occurs when `alive` drops without our mech registering a `kill` event in `events`.
- Before zone shrink begins (t < shrink_start, typically 60 s), the 560 m zone covers the entire map,
  so zero zone damage can occur. In practice mode, house bots never shoot each other, so any unassisted
  death before shrink_start is 100% proof of a Free-For-All match.
- Between shrink_start and 120 s, we require >= 2 unassisted deaths.
- After 120 s (2 minutes), if FFA was not detected, the match is permanently locked to "practice".
  This completely guards against mid/late-game squad zone deaths triggering FFA in practice.
- Once free-for-all mode is detected, the mode latches to "ffa" for the rest of the match and
  applies the free-for-all tuning overlay.
"""
from __future__ import annotations

import math
from typing import Optional
import tuning

INFIGHT_HIT_M = 5.0      # a laser ending this close to a mech hit it (mech radius 2.5 m, grows with cubes)
INFIGHT_CLEAR_M = 30.0   # ...and that mech is at least this far from us (not a shot at us passing by)
INFIGHT_EVENTS = 2       # beams needed to switch to free-for-all
# HP signal (catches gun fights, which leave no beam): a visible mech loses HP we didn't deal
HP_DROP_MIN = 35.0       # per observation; above an NPC bullet (25) and per-tick zone damage (<= 26)
HP_SEEN_GAP_S = 1.0      # compare only consecutive sightings this close in time
OUR_HIT_S = 1.5          # ignore mechs we hit this recently (our gun, lightning chain, mortar splash)
NPC_CLEAR_M = 60.0       # ignore mechs with a visible NPC drone this close (drones shoot house bots)
HP_EVENTS = 3            # HP-drop observations needed to switch to free-for-all


class ModeDetector:
    def __init__(self) -> None:
        self.last_alive: Optional[int] = None
        self.unassisted_deaths: int = 0
        self.mode: str = "practice"
        self.locked: bool = False
        self.infighting: int = 0
        self.hp_events: int = 0
        self.prev_hp = {}   # mech id -> (t, hp)
        self.our_hits = {}  # mech id -> last t we hit it

    def reset(self) -> None:
        self.last_alive = None
        self.unassisted_deaths = 0
        self.mode = "practice"
        self.locked = False
        self.infighting = 0
        self.hp_events = 0
        self.prev_hp = {}
        self.our_hits = {}
        tuning.set_mode("practice")

    def _hp_drops(self, obs: dict, zone) -> int:
        """Third-party damage: a visible mech, far from us and inside the zone, loses HP that we
        didn't deal and no visible NPC drone is near it. House bots never fight each other."""
        t = float(obs.get("t", 0.0))
        me = obs.get("self") or {}
        my_id = me.get("id")
        mp = me.get("pos") or [0.0, 0.0, 0.0]
        for e in obs.get("events") or []:
            if e.get("type") == "hit" and e.get("target") is not None:
                self.our_hits[int(e["target"])] = t
        mechs = obs.get("mechs") or []
        npcs = [m["pos"] for m in mechs if m.get("kind") == "npc"]
        circle = zone.current() if zone is not None and getattr(zone, "known", False) else None
        n = 0
        for m in mechs:
            if m.get("kind", "mech") != "mech" or m.get("id") == my_id or m.get("hp") is None:
                continue
            mid, hp = int(m["id"]), float(m["hp"])
            prev = self.prev_hp.get(mid)
            self.prev_hp[mid] = (t, hp)
            if prev is None or t - prev[0] > HP_SEEN_GAP_S or prev[1] - hp < HP_DROP_MIN:
                continue
            p = m["pos"]
            if t - self.our_hits.get(mid, -1e9) <= OUR_HIT_S:
                continue
            if math.dist(p[:2], mp[:2]) < INFIGHT_CLEAR_M:
                continue  # splash or chains from shots at us
            if any(math.dist(p[:2], q[:2]) <= NPC_CLEAR_M for q in npcs):
                continue
            if circle is not None and math.hypot(p[0] - circle[0], p[1] - circle[1]) > circle[2] - 5.0:
                continue  # zone damage
            n += 1
        return n

    def _infighting(self, obs: dict) -> int:
        """Audit A2: laser beams from one other mech ending on a third mech (not us, not near us).
        House bots never fight each other, so in practice this never happens; it works at any time
        of the match, unlike the death rule below, which locks after 120 s."""
        me = obs.get("self") or {}
        my_id = me.get("id")
        mp = me.get("pos") or [0.0, 0.0, 0.0]
        others = [m for m in obs.get("mechs") or [] if m.get("kind", "mech") == "mech" and m.get("id") != my_id]
        n = 0
        for b in obs.get("beams") or []:
            if b.get("kind") != "laser" or b.get("by") in (None, my_id):
                continue
            path = b.get("path") or []
            if len(path) < 2:
                continue
            end = path[-1]
            if math.dist(end[:2], mp[:2]) < INFIGHT_CLEAR_M:
                continue  # aimed at us, possibly passing a squad mate: not evidence
            for m in others:
                if m.get("id") == b.get("by"):
                    continue
                if math.dist(end[:2], m["pos"][:2]) <= INFIGHT_HIT_M:
                    n += 1
                    break
        return n

    def observe(self, obs: dict, zone) -> str:
        """Update detection state from current observation and zone. Returns current mode."""
        if not tuning.get("mode.detect"):
            return "practice"
        if self.mode == "ffa":
            return "ffa"
        self.infighting += self._infighting(obs)
        self.hp_events += self._hp_drops(obs, zone)
        if self.infighting >= INFIGHT_EVENTS or self.hp_events >= HP_EVENTS:
            self.mode = "ffa"
            tuning.set_mode("ffa")
            return "ffa"
        if self.locked:
            return "practice"

        t = float(obs.get("t", 0.0))
        # After 120s (2 minutes), lock to practice. In FFA, multiple deaths happen in the first
        # 30-60s. In practice, squad bots only die to us or mid/late zone collapse.
        if t > 120.0:
            self.locked = True
            return "practice"

        alive = obs.get("alive")
        if alive is None:
            return self.mode

        if self.last_alive is not None and alive < self.last_alive:
            deaths = self.last_alive - alive
            my_kills = sum(1 for e in (obs.get("events") or []) if e.get("type") == "kill")
            unassisted = max(0, deaths - my_kills)
            if unassisted > 0:
                self.unassisted_deaths += unassisted
                shrink_start = float(getattr(zone, "shrink_start", 60.0))
                # Before zone shrink starts (t < shrink_start), circle is 560m covering entire map.
                # Any unassisted death is 100% FFA. Between shrink_start and 120s, require >= 2 unassisted deaths.
                if t < shrink_start or self.unassisted_deaths >= 2:
                    self.mode = "ffa"
                    tuning.set_mode("ffa")

        self.last_alive = alive
        return self.mode
