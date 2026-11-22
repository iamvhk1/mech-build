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


class ModeDetector:
    def __init__(self) -> None:
        self.last_alive: Optional[int] = None
        self.unassisted_deaths: int = 0
        self.mode: str = "practice"
        self.locked: bool = False
        self.infighting: int = 0

    def reset(self) -> None:
        self.last_alive = None
        self.unassisted_deaths = 0
        self.mode = "practice"
        self.locked = False
        self.infighting = 0
        tuning.set_mode("practice")

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
        if self.infighting >= INFIGHT_EVENTS:
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
