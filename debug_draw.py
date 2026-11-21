"""Optional debug drawing on top of mechfight.draw (which enforces hello.config.debug caps).

Off by default; set MECH_DEBUG=1 to enable. Drawings never affect the match, and nothing on the
track shows them (protocol §6), so this is groundwork for later phases and for inspecting
recordings if a viewer becomes available. Keep drawings small: they count toward the 64 KiB line
limit and the 8 MB per-match debug budget.
"""
from __future__ import annotations

import os
from typing import Optional, Sequence

import mechfight as mf

ENABLED = os.environ.get("MECH_DEBUG", "") not in ("", "0", "false", "False")
MAX_PATH_LINES = 30


def path(start: Sequence[float], waypoints: Sequence[Sequence[float]], z: float, color: str = "#ffd060") -> None:
    if not ENABLED or not waypoints:
        return
    prev = (start[0], start[1], z)
    for wp in list(waypoints)[:MAX_PATH_LINES]:
        cur = (wp[0], wp[1], z)
        mf.draw.line(list(prev), list(cur), color)
        prev = cur


def goal(at: Sequence[float], z: float, color: str = "#40c0ff") -> None:
    if ENABLED:
        mf.draw.point([at[0], at[1], z], color, 6)


def label(state: str, tick_ms: Optional[float] = None) -> None:
    if ENABLED:
        mf.draw.label(state if tick_ms is None else f"{state} {tick_ms:.1f}ms")
