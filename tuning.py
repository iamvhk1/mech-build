"""Behaviour switches for experiments (docs/experiments.md).

Every tunable behaviour reads its setting from here. An experiment is a named preset: change
ACTIVE, commit, push, submit, and record the score in docs/experiments.md. Presets list only the
settings they change from DEFAULTS.
"""
from __future__ import annotations

ACTIVE = "best"

DEFAULTS = {
    # upgrade offers: "first" = always choice 0 (Phase 3 behaviour), "ranked" = upgrades.py ranking
    "upgrades": "ranked",
    # engagement policy (Phase 3, Q1)
    "engage.near_m": 60.0,          # shoot any mech this close
    "engage.low_hp": 0.35,          # ...or any target below this HP fraction
    "engage.any_in_range": False,   # True: shoot any visible mech in gun range
    "lightning.reserve": 20.0,      # energy kept for jumps (unless the target is within 20 m)
    # retreat-to-heal (Phase 4, E1)
    "retreat.enabled": True,
    "retreat.hp_enter": 0.55,       # retreat below this HP fraction
    "retreat.hp_exit": 0.90,        # ...until healed to this
    "retreat.on_hunters": True,     # also retreat with 3+ hunters within 100 m
    "retreat.on_heavy_damage": True,  # also retreat after losing >20% max HP in 2 s
    "retreat.hold_fire": True,      # hold fire while retreating (regen needs no damage dealt)
    "retreat.cornered_m": 25.0,     # ...but fight back this close
    "retreat.finish_hp": 0.15,      # ...or finish a target this low
    # rooftop camping (roadmap item 2)
    "roof.enabled": False,          # climb a roof inside the next circle and fight from its edge
    "roof.peek_hp": 0.5,            # step to the edge toward a hunter only above this HP fraction
}

PRESETS = {
    # Phase 3 as submitted (score 2.33): first upgrade choice, no retreat
    "p3": {"upgrades": "first", "retreat.enabled": False},
    # E1 as submitted (score 1.52)
    "e1": {},
    # batch 1
    "p3_picker": {"retreat.enabled": False},
    "picker_lastresort": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                          "retreat.on_heavy_damage": False, "retreat.hold_fire": False},
    # best so far (run 1c, 2.54): the preset to keep on GitHub between experiments
    "best": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
             "retreat.on_heavy_damage": False, "retreat.hold_fire": False},
    # run 1d (2.02, worse), rebased on the best so far (picker_lastresort, 2.54): only engage.any_in_range changes
    "picker_aggressive": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                          "retreat.on_heavy_damage": False, "retreat.hold_fire": False,
                          "engage.any_in_range": True},
    # roadmap item 2: rooftop test, on top of the best so far (picker_lastresort, 2.54)
    "roof_camp": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "roof.enabled": True},
}


def _resolve(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"unknown tuning preset {name!r}; known: {sorted(PRESETS)}")
    s = dict(DEFAULTS)
    s.update(PRESETS[name])
    return s


SETTINGS = _resolve(ACTIVE)


def get(key: str):
    return SETTINGS[key]


def use(name: str) -> None:
    """Switch preset at runtime (tests)."""
    global SETTINGS, ACTIVE
    SETTINGS = _resolve(name)
    ACTIVE = name
