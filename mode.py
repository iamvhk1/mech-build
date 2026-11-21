"""Mode detection (Stage D, roadmap item E6).

Detects whether the current match is a practice match (1 vs 15-bot squad, where house bots never
kill each other) or a free-for-all match (16 independent bots, where third parties fight and
eliminate each other).

Detection rule:
- If `alive` drops without our mech registering a `kill` event in `events`, an unassisted death
  occurred.
- Outside the last two zone phases (zone.radius > 70 m or zone.dps < 160 HP/s), an unassisted death
  proves other bots are killing each other (free-for-all).
- Inside the last two zone phases (late collapse), we require >= 2 unassisted deaths to rule out
  squad mechs dying to the zone.
- Once free-for-all mode is detected, the mode latches to "ffa" for the rest of the match and
  applies the free-for-all tuning overlay.
"""
from __future__ import annotations

from typing import Optional
import tuning


class ModeDetector:
    def __init__(self) -> None:
        self.last_alive: Optional[int] = None
        self.unassisted_deaths: int = 0
        self.mode: str = "practice"

    def reset(self) -> None:
        self.last_alive = None
        self.unassisted_deaths = 0
        self.mode = "practice"
        tuning.set_mode("practice")

    def observe(self, obs: dict, zone) -> str:
        """Update detection state from current observation and zone. Returns current mode."""
        if not tuning.get("mode.detect"):
            return "practice"
        if self.mode == "ffa":
            return "ffa"

        alive = obs.get("alive")
        if alive is None:
            return self.mode

        if self.last_alive is not None and alive < self.last_alive:
            deaths = self.last_alive - alive
            my_kills = sum(1 for e in (obs.get("events") or []) if e.get("type") == "kill")
            unassisted = max(0, deaths - my_kills)
            if unassisted > 0:
                self.unassisted_deaths += unassisted
                dps = float(getattr(zone, "dps", 0.0))
                r = float(getattr(zone, "radius", 1e9))
                # Outside the last two zone phases: radius > 70 m or dps < 160 HP/s
                outside_last_phases = (r > 70.0) or (dps < 160.0)
                if outside_last_phases or self.unassisted_deaths >= 2:
                    self.mode = "ffa"
                    tuning.set_mode("ffa")

        self.last_alive = alive
        return self.mode
