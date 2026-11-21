"""Zone model (protocol §9) and rotation destination choice.

The observation always gives the current circle, the next circle and the shrink window. Before
`shrink_start` the circle holds; between `shrink_start` and `shrink_end` centre and radius move
linearly to the next circle. Beyond `shrink_end` we only know the next circle (the one after is
revealed later), so predictions past it assume the next circle holds.
"""
from __future__ import annotations

import math
from typing import Optional, Sequence, Tuple

Circle = Tuple[float, float, float]  # cx, cy, r


class Zone:
    def __init__(self) -> None:
        self.center = (0.0, 0.0)
        self.radius = 1e9
        self.next_center = (0.0, 0.0)
        self.next_radius = 1e9
        self.shrink_start = 0.0
        self.shrink_end = 0.0
        self.dps = 0.0
        self.t = 0.0
        self.known = False
        # Whether `center`/`radius` during a shrink are the circle the shrink started from (static)
        # or the live circle. The protocol says "current circle"; we detect it: a radius that stays
        # fixed while time advances mid-shrink means static.
        self.static_during_shrink = False

    def update(self, z: dict, t: float) -> None:
        t = float(t)
        shrinking = float(z["shrink_start"]) < t < float(z["shrink_end"])
        if (self.known and shrinking and self.shrink_start < self.t < self.shrink_end
                and float(z["shrink_end"]) == self.shrink_end and t - self.t > 0.05
                and float(z["next_radius"]) != float(z["radius"])):
            self.static_during_shrink = float(z["radius"]) == self.radius
        self.center = (float(z["center"][0]), float(z["center"][1]))
        self.radius = float(z["radius"])
        self.next_center = (float(z["next_center"][0]), float(z["next_center"][1]))
        self.next_radius = float(z["next_radius"])
        self.shrink_start = float(z["shrink_start"])
        self.shrink_end = float(z["shrink_end"])
        self.dps = float(z.get("dps", 0.0))
        self.t = t
        self.known = True

    # ------------------------------------------------------------ geometry over time

    def circle_at(self, t: float) -> Circle:
        """The zone circle at match time t (assumes the next circle holds after shrink_end).

        Interpolates linearly toward the next circle from the reported circle: from now if the
        report is the live circle, from shrink_start if it is the circle the shrink started from."""
        if t <= self.shrink_start or self.shrink_end <= self.shrink_start:
            return (*self.center, self.radius) if t <= self.shrink_start else (*self.next_center, self.next_radius)
        if t >= self.shrink_end:
            return (*self.next_center, self.next_radius)
        t0 = self.shrink_start if self.static_during_shrink else max(self.t, self.shrink_start)
        if t <= t0:
            return (*self.center, self.radius)
        f = (t - t0) / max(1e-6, self.shrink_end - t0)
        cx = self.center[0] + (self.next_center[0] - self.center[0]) * f
        cy = self.center[1] + (self.next_center[1] - self.center[1]) * f
        r = self.radius + (self.next_radius - self.radius) * f
        return cx, cy, r

    def current(self) -> Circle:
        return self.circle_at(self.t) if self.static_during_shrink else (*self.center, self.radius)

    def next_circle(self) -> Circle:
        return (*self.next_center, self.next_radius)

    @staticmethod
    def depth(circle: Circle, pos: Sequence[float]) -> float:
        """Distance inside the circle (negative = outside)."""
        return circle[2] - math.hypot(pos[0] - circle[0], pos[1] - circle[1])

    def inside_now(self, pos: Sequence[float]) -> bool:
        return self.depth(self.current(), pos) >= 0

    def time_until_outside(self, pos: Sequence[float], step: float = 0.5) -> float:
        """Seconds until the shrinking zone leaves `pos` outside (0 if already outside, inf if never
        within what we know, i.e. pos is inside the next circle)."""
        if self.depth(self.current(), pos) < 0:
            return 0.0
        if self.depth(self.next_circle(), pos) >= 0:
            return math.inf
        t = max(self.t, self.shrink_start)
        while t <= self.shrink_end + 1e-6:
            if self.depth(self.circle_at(t), pos) < 0:
                return max(0.0, t - self.t)
            t += step
        return max(0.0, self.shrink_end - self.t)


def rotation_target(zone: Zone, pos: Sequence[float]) -> Tuple[Tuple[float, float], float]:
    """Point to head for inside the next circle, and the depth margin we aim for.

    Aims for a point `margin` inside the next circle on our side of it (short trip, still safe
    from the following shrink's edge); if we are already that deep, stay where we are."""
    cx, cy, r = zone.next_circle()
    margin = min(60.0, max(10.0, 0.35 * r)) if r > 0 else 0.0
    if r <= margin:
        return (cx, cy), r
    dx, dy = pos[0] - cx, pos[1] - cy
    d = math.hypot(dx, dy)
    if d <= r - margin:
        return (float(pos[0]), float(pos[1])), margin
    if d < 1e-6:
        return (cx, cy), margin
    k = (r - margin) / d
    return (cx + dx * k, cy + dy * k), margin


def choose_destination(core, zone: Zone, pos: Sequence[float], radius: float,
                       search_m: float = 16.0, step_m: float = 4.0) -> Optional[Tuple[float, float]]:
    """A walkable spot near the rotation target, inside the next circle, preferring cover."""
    (tx, ty), margin = rotation_target(zone, pos)
    nxt = zone.next_circle()
    if core is None:
        return tx, ty
    best, best_s = None, -math.inf
    n = int(search_m // step_m)
    seen = set()
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            q = core.nearest_walkable(tx + i * step_m, ty + j * step_m, radius, True)
            if q is None or q in seen:
                continue
            seen.add(q)
            if Zone.depth(nxt, q) < min(margin * 0.5, nxt[2] * 0.5):
                continue
            s = 20.0 * core.cover(*q) - 0.5 * math.hypot(q[0] - tx, q[1] - ty)
            if s > best_s:
                best, best_s = q, s
    if best is None:
        best = core.nearest_walkable(tx, ty, radius, True) or (tx, ty)
    return best
