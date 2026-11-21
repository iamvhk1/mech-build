"""ctypes bindings for core/libmech_core.so (mech_core.dll on Windows).

    core = MapCore.from_hello(hello)          # or MapCore.from_dir("/arena", config)
    core.floor_z(x, y)
    core.shot_los((ax, ay, az), (bx, by, bz))  # 1.0 = clear, else hit fraction
    core.find_path((sx, sy), (gx, gy), radius) # list of (x, y) waypoints

Python parses world.json (stdlib json) and passes flat arrays; the C++ side holds no JSON code.
"""
from __future__ import annotations

import array
import ctypes as C
import json
import math
import os
import sys
import time
from typing import Iterable, List, Optional, Sequence, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_KINDS = {"building": 0, "stadium": 1, "bridge": 2}
_TREE_FIELDS = ("x", "y", "z", "height", "crownR", "crownBase", "trunkR", "crownX", "crownY")
_MAX_PATH = 512

WALK, JUMP, DROP = 0, 1, 2

LAYER_FLOOR, LAYER_CLEARANCE, LAYER_COMPONENT, LAYER_GROUND, LAYER_COVER, LAYER_EDGES = range(6)

_dbl = C.c_double
_pd = C.POINTER(C.c_double)
_pf = C.POINTER(C.c_float)
_pi = C.POINTER(C.c_int)
_pu8 = C.POINTER(C.c_uint8)
_ph = C.c_void_p


def _lib_path() -> str:
    env = os.environ.get("MECH_CORE_LIB")
    if env:
        return env
    name = "mech_core.dll" if sys.platform == "win32" else "libmech_core.so"
    return os.path.join(_HERE, "core", name)


def _load() -> C.CDLL:
    lib = C.CDLL(_lib_path())
    sig = {
        "mc_create": (_ph, []),
        "mc_destroy": (None, [_ph]),
        "mc_set_terrain": (C.c_int, [_ph, C.POINTER(C.c_int16), C.c_int, C.c_int, _dbl, _dbl, _dbl, _dbl]),
        "mc_add_prism": (C.c_int, [_ph, C.c_int, _dbl, _dbl, _pf, C.c_int, _pf, _pi, C.c_int]),
        "mc_set_trees": (C.c_int, [_ph, _pf, C.c_int]),
        "mc_build": (C.c_int, [_ph, _pd, C.c_int]),
        "mc_build_ms": (_dbl, [_ph]),
        "mc_grid_info": (None, [_ph, _pi, _pd]),
        "mc_get_layer": (C.c_int, [_ph, C.c_int, _pf, C.c_int]),
        "mc_ground_z": (_dbl, [_ph, _dbl, _dbl]),
        "mc_floor_z": (_dbl, [_ph, _dbl, _dbl]),
        "mc_clearance": (_dbl, [_ph, _dbl, _dbl]),
        "mc_cover": (_dbl, [_ph, _dbl, _dbl]),
        "mc_component": (C.c_int, [_ph, _dbl, _dbl]),
        "mc_is_ground": (C.c_int, [_ph, _dbl, _dbl]),
        "mc_shot_los": (_dbl, [_ph] + [_dbl] * 6),
        "mc_vision_los": (C.c_int, [_ph] + [_dbl] * 6),
        "mc_shot_los_batch": (None, [_ph, C.c_int, _pd, _pd]),
        "mc_vision_los_batch": (None, [_ph, C.c_int, _pd, _pu8]),
        "mc_can_see": (C.c_int, [_ph] + [_dbl] * 11),
        "mc_nearest_walkable": (C.c_int, [_ph, _dbl, _dbl, _dbl, C.c_int, _pd]),
        "mc_segment_walkable": (C.c_int, [_ph, _dbl, _dbl, _dbl, _dbl, _dbl, _dbl]),
        "mc_find_path": (C.c_int, [_ph, _dbl, _dbl, _dbl, _dbl, _dbl, _dbl, _dbl, _pd, C.c_int, _pd, _dbl, _dbl, C.c_int, _pd, C.c_int]),
        "mc_steer": (C.c_int, [_ph, _dbl, _dbl, _dbl, _dbl, _dbl, _dbl, _pd, _pd, C.c_int, _pd, _pd]),
        "mc_gun_lead": (C.c_int, [_dbl] * 11 + [_pd]),
        "mc_mortar_pitch": (C.c_int, [_dbl] * 9 + [C.c_int, _dbl, _dbl, _pd]),
        "mc_shell_impact": (C.c_int, [_ph] + [_dbl] * 8 + [_pd]),
    }
    for name, (res, args) in sig.items():
        fn = getattr(lib, name)
        fn.restype = res
        fn.argtypes = args
    return lib


_lib: Optional[C.CDLL] = None


def lib() -> C.CDLL:
    global _lib
    if _lib is None:
        _lib = _load()
    return _lib


def _darr(values: Sequence[float]):
    return (C.c_double * len(values))(*values) if values else None


def gun_lead(muzzle: Sequence[float], target: Sequence[float], vel: Sequence[float], speed: float,
             offset: float) -> Optional[Tuple[float, float, float]]:
    """(yaw, pitch, flight_time) to hit a target moving at constant velocity."""
    out = (C.c_double * 3)()
    if not lib().mc_gun_lead(*muzzle[:3], *target[:3], *vel[:3], speed, offset, out):
        return None
    return out[0], out[1], out[2]


def mortar_pitch(muzzle: Sequence[float], target: Sequence[float], speed: float, gravity: float, offset: float,
                 prefer_high: bool, min_pitch: float, max_pitch: float) -> Optional[Tuple[float, float, float]]:
    """(yaw, pitch, flight_time) for a mortar shell to land on target, or None if out of reach."""
    out = (C.c_double * 3)()
    if not lib().mc_mortar_pitch(*muzzle[:3], *target[:3], speed, gravity, offset, int(prefer_high),
                                 min_pitch, max_pitch, out):
        return None
    return out[0], out[1], out[2]


class MapCore:
    """The static map model. Build once at `hello`; every query is then a single C call."""

    def __init__(self, world: dict, terrain: array.array, config: Optional[dict] = None):
        t0 = time.perf_counter()
        L = lib()
        self._lib = L
        self._h = L.mc_create()
        if not self._h:
            raise RuntimeError("mc_create failed")
        mech = (config or {}).get("mech", {})
        rules = world.get("rules", {})
        tr = world["terrain"]
        nx, ny = int(tr["nx"]), int(tr["ny"])
        if len(terrain) != nx * ny:
            raise ValueError(f"terrain has {len(terrain)} samples, expected {nx * ny}")
        tbuf = (C.c_int16 * len(terrain)).from_buffer(terrain)
        L.mc_set_terrain(self._h, tbuf, nx, ny, tr["minX"], tr["minY"], tr["step"], tr.get("scale", 0.01))

        for p in world["prisms"]:
            ring = p["ring"]
            holes = [h for h in (p.get("holes") or []) if len(h) >= 6]
            flat = [v for h in holes for v in h]
            rbuf = (C.c_float * len(ring))(*ring)
            hbuf = (C.c_float * max(1, len(flat)))(*flat)
            cbuf = (C.c_int * max(1, len(holes)))(*[len(h) // 2 for h in holes])
            L.mc_add_prism(self._h, _KINDS.get(p.get("kind"), 0), p["base"], p["top"], rbuf, len(ring) // 2,
                           hbuf, cbuf, len(holes))

        trees = world.get("trees") or {}
        fields = trees.get("fields") or []
        data = trees.get("data") or []
        if fields and data:
            stride = len(fields)
            idx = [fields.index(f) for f in _TREE_FIELDS]
            n = len(data) // stride
            flat = [data[k * stride + i] for k in range(n) for i in idx]
            L.mc_set_trees(self._h, (C.c_float * len(flat))(*flat), n)

        params = [
            mech.get("step_up", 1.2),
            mech.get("max_slope_deg", rules.get("maxSlopeDeg", 50)),
            mech.get("height", 9.0),
            mech.get("radius", 2.5),
            rules.get("canopyDensity", 0.35),
            rules.get("canopyBlockT", 0.25),
        ]
        if not L.mc_build(self._h, _darr(params), len(params)):
            raise RuntimeError("mc_build failed")

        gi = (C.c_int * 2)()
        gd = (C.c_double * 3)()
        L.mc_grid_info(self._h, gi, gd)
        self.nnx, self.nny = gi[0], gi[1]
        self.min_x, self.min_y, self.res = gd[0], gd[1], gd[2]
        self.build_ms = L.mc_build_ms(self._h)
        self.load_ms = (time.perf_counter() - t0) * 1000.0

        # reusable buffers
        self._path_buf = (C.c_double * (3 * _MAX_PATH))()
        self._xy = (C.c_double * 2)()
        self._out3 = (C.c_double * 3)()
        self._out4 = (C.c_double * 4)()

    # ------------------------------------------------------------ construction

    @classmethod
    def from_dir(cls, map_dir: str, config: Optional[dict] = None,
                 files: Iterable[str] = ("v2/world.json", "v2/terrain.i16")) -> "MapCore":
        files = list(files)
        world_rel = next((f for f in files if f.endswith(".json")), "v2/world.json")
        with open(os.path.join(map_dir, world_rel), "r", encoding="utf-8") as f:
            world = json.load(f)
        terr_rel = next((f for f in files if f.endswith(".i16")), None)
        if terr_rel is None:
            terr_rel = os.path.join(os.path.dirname(world_rel), world["terrain"].get("file", "terrain.i16"))
        terrain = array.array("h")
        with open(os.path.join(map_dir, terr_rel), "rb") as f:
            terrain.frombytes(f.read())
        if sys.byteorder != "little":
            terrain.byteswap()
        return cls(world, terrain, config)

    @classmethod
    def from_hello(cls, hello: dict) -> "MapCore":
        m = hello.get("map") or {}
        return cls.from_dir(m.get("dir", "/arena"), hello.get("config"), m.get("files") or ("v2/world.json", "v2/terrain.i16"))

    def close(self) -> None:
        if getattr(self, "_h", None):
            self._lib.mc_destroy(self._h)
            self._h = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------ point queries

    def ground_z(self, x: float, y: float) -> float:
        return self._lib.mc_ground_z(self._h, x, y)

    def floor_z(self, x: float, y: float) -> float:
        return self._lib.mc_floor_z(self._h, x, y)

    def clearance(self, x: float, y: float) -> float:
        return self._lib.mc_clearance(self._h, x, y)

    def cover(self, x: float, y: float) -> float:
        return self._lib.mc_cover(self._h, x, y)

    def component(self, x: float, y: float) -> int:
        return self._lib.mc_component(self._h, x, y)

    def is_ground(self, x: float, y: float) -> bool:
        return bool(self._lib.mc_is_ground(self._h, x, y))

    def layer(self, which: int) -> array.array:
        out = array.array("f", bytes(4 * self.nnx * self.nny))
        buf = (C.c_float * len(out)).from_buffer(out)
        self._lib.mc_get_layer(self._h, which, buf, len(out))
        return out

    # ------------------------------------------------------------ line of sight

    def shot_los(self, a: Sequence[float], b: Sequence[float]) -> float:
        """Hit fraction along a->b against buildings, bridges and terrain (1.0 = clear)."""
        return self._lib.mc_shot_los(self._h, a[0], a[1], a[2], b[0], b[1], b[2])

    def vision_los(self, a: Sequence[float], b: Sequence[float]) -> bool:
        """shot_los plus tree trunks and canopy."""
        return bool(self._lib.mc_vision_los(self._h, a[0], a[1], a[2], b[0], b[1], b[2]))

    def shot_los_batch(self, segs: Sequence[Sequence[float]]) -> List[float]:
        n = len(segs)
        if not n:
            return []
        flat = (C.c_double * (6 * n))(*[v for s in segs for v in s[:6]])
        out = (C.c_double * n)()
        self._lib.mc_shot_los_batch(self._h, n, flat, out)
        return list(out)

    def vision_los_batch(self, segs: Sequence[Sequence[float]]) -> List[bool]:
        n = len(segs)
        if not n:
            return []
        flat = (C.c_double * (6 * n))(*[v for s in segs for v in s[:6]])
        out = (C.c_uint8 * n)()
        self._lib.mc_vision_los_batch(self._h, n, flat, out)
        return [bool(v) for v in out]

    def can_see(self, observer: Sequence[float], eye_z: float, aim_yaw: float, target: Sequence[float],
                center_z: float, top_z: float, near_range: float, rng: float, fov_deg: float) -> bool:
        return bool(self._lib.mc_can_see(self._h, observer[0], observer[1], eye_z, aim_yaw, target[0], target[1],
                                         center_z, top_z, near_range, rng, fov_deg))

    # ------------------------------------------------------------ navigation

    def nearest_walkable(self, x: float, y: float, radius: float, ground_only: bool = True) -> Optional[Tuple[float, float]]:
        if not self._lib.mc_nearest_walkable(self._h, x, y, radius, int(ground_only), self._xy):
            return None
        return self._xy[0], self._xy[1]

    def segment_walkable(self, a: Sequence[float], b: Sequence[float], radius: float, height: float = 0.0) -> bool:
        """Straight walk a->b with no jumps. height: mech height for headroom (0 = base)."""
        return bool(self._lib.mc_segment_walkable(self._h, a[0], a[1], b[0], b[1], radius, height))

    def find_path_ex(self, start: Sequence[float], goal: Sequence[float], radius: float, height: float = 0.0,
                     max_jump_rise: float = 0.0, threats: Sequence[Sequence[float]] = (),
                     zone: Optional[Sequence[float]] = None, cover_weight: float = 0.0,
                     h_weight: Optional[float] = None,
                     max_expansions: int = 60000) -> Optional[List[Tuple[float, float, int]]]:
        """Waypoints (x, y, kind) from start to goal (start excluded, snapped goal included), or None.
        kind: WALK (0), JUMP (1: reaching it needs a jump) or DROP (2: walk off a ledge to reach it). height: mech height for headroom (0 = base).
        max_jump_rise: allow steps up to this height as jumps (0 = walk only; never onto roofs).
        threats: (x, y, range, weight) up to 8. zone: (cx, cy, r, penalty) or None.
        h_weight: heuristic inflation; default 1.3, or 2.0 when penalties are active (they raise
        step costs, so a plain heuristic explores far more cells: measured 8 ms vs 2 ms average)."""
        th = list(threats)[:8]
        if h_weight is None:
            h_weight = 2.0 if (th or zone) else 1.3
        tbuf = _darr([v for t in th for v in t[:4]])
        zbuf = _darr(list(zone[:4])) if zone else None
        n = self._lib.mc_find_path(self._h, start[0], start[1], goal[0], goal[1], radius, height, max_jump_rise,
                                   tbuf, len(th), zbuf, cover_weight, h_weight, max_expansions,
                                   self._path_buf, _MAX_PATH)
        if n <= 0:
            return None
        b = self._path_buf
        return [(b[3 * k], b[3 * k + 1], int(round(b[3 * k + 2]))) for k in range(n)]

    def find_path(self, start: Sequence[float], goal: Sequence[float], radius: float,
                  **kw) -> Optional[List[Tuple[float, float]]]:
        """Like find_path_ex, but returns (x, y) waypoints only."""
        p = self.find_path_ex(start, goal, radius, **kw)
        return None if p is None else [(x, y) for x, y, _ in p]

    def steer(self, pos: Sequence[float], waypoint: Sequence[float], radius: float, speed: float,
              zone: Optional[Sequence[float]] = None, shells: Sequence[Sequence[float]] = (),
              weights: Optional[Sequence[float]] = None) -> Tuple[float, float, float]:
        """Best of 16 directions: (dx, dy, score). shells: (x, y, splash_radius, seconds_to_impact)."""
        sbuf = _darr([v for s in shells for v in s[:4]])
        self._lib.mc_steer(self._h, pos[0], pos[1], waypoint[0], waypoint[1], radius, speed,
                           _darr(list(zone[:3])) if zone else None, sbuf, len(shells),
                           _darr(list(weights[:4])) if weights else None, self._out3)
        return self._out3[0], self._out3[1], self._out3[2]

    # ------------------------------------------------------------ ballistics

    def shell_impact(self, pos: Sequence[float], vel: Sequence[float], gravity: float,
                     max_t: float = 12.0) -> Optional[Tuple[float, float, float, float]]:
        """Where and when (x, y, z, t) a falling shell hits geometry."""
        if not self._lib.mc_shell_impact(self._h, *pos[:3], *vel[:3], gravity, max_t, self._out4):
            return None
        o = self._out4
        return o[0], o[1], o[2], o[3]


def yaw_to(a: Sequence[float], b: Sequence[float]) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])
