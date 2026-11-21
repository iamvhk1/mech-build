"""Behaviour switches for experiments (docs/experiments.md).

Every tunable behaviour reads its setting from here. An experiment is a named preset: change
ACTIVE, commit, push, submit, and record the score in docs/experiments.md. Presets list only the
settings they change from DEFAULTS.
"""
from __future__ import annotations

ACTIVE = "burn"

DEFAULTS = {
    # upgrade offers: "first" = always choice 0 (Phase 3 behaviour), "ranked" = upgrades.py ranking
    "upgrades": "ranked",
    # mode detection (master plan Stage D, E6)
    "mode.detect": False,           # D1: detect practice vs free-for-all and apply FFA overlay
    # final zone burn (master plan Stage E, E4)
    "burn.enabled": False,          # E4: final burn play (center hold in late circles)
    "burn.radius": 25.0,            # next_radius threshold to enter burn mode
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
    # fight quality (master plan Stage B)
    "fight.cover": False,           # B1: fight from cover (step out to fire, back to reload / after hits)
    "fight.blind_fire": False,      # fire back along the damage bearing at attackers we can't see
    "fight.focus": False,           # B3: stay on one target, prefer quickest kills, finish wounded targets
    "fight.strafe": False,          # strafe sideways while fighting (safeguarded: walls, zone, exposure)
    # cube economy (master plan Stage C)
    "farm.crates": False,           # C1: shoot street-level crates and collect their cube when safe
    "farm.cubes": False,            # C3: also collect any other visible cube (kill drops) when safe
    "farm.drones": False,           # C2: hunt isolated NPC drones (2 cubes each) when safe
    "farm.drone_min_hp": 0.90,      # HP fraction required to farm drones
    "farm.drone_dist_min": 30.0,    # stand-and-shoot minimum distance from drone
    "farm.drone_dist_max": 50.0,    # stand-and-shoot maximum distance from drone
    "farm.safe_m": 120.0,           # farm only with no known hunter within this distance
    "farm.min_hp": 0.6,             # ...and HP at least this fraction (crates/cubes)
    "farm.max_dist": 80.0,          # consider crates/cubes/drones within this distance
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
    # best so far: run 1c settings (2.54); + trigger-timing fix (code, run B0) 2.90; + shootability
    # fix (code, B0b) 2.85; + strafing (run B-strafe) 2.88, kept by decision despite the tie;
    # + crate farming (run C1) 3.00; + all visible cubes (run C3) 3.38; + mode detection (run D1b) 3.38
    "best": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
             "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
             "farm.crates": True, "farm.cubes": True, "mode.detect": True},
    # Stage B, run B1: best + fight from cover
    "cover": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.cover": True},
    # best + blind fire at unseen attackers (foliage hides them; bullets pass trees)
    "blind": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.blind_fire": True},
    # Stage B, run B3: best + focus fire
    "focus": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.focus": True},
    # Stage C, run C1: best (incl. strafing) + crates
    "crates": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True},
    # Stage C, run C3: best + collect any visible cube (kill drops, floor cubes)
    "cubes": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True},
    # Stage C: re-test upgrade order (run U1): best + choice 0 only (compare against 3.38)
    "upgrade_first": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                      "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                      "farm.crates": True, "farm.cubes": True, "upgrades": "first"},
    # Stage C, run C2: best + hunt isolated drones for 2 cubes each
    "drones": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "farm.drones": True},
    # Stage B: strafing on the plain best (used if focus fire doesn't win)
    "strafe": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True},
    # Stage B: focus fire + strafing (compared against the focus run)
    "focus_strafe": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                     "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.focus": True,
                     "fight.strafe": True},
    # interaction re-test after the trigger-timing fix: engage mechs within 90 m (was 60 m)
    "near90": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "engage.near_m": 90.0},
    # run 1d (2.02, worse), rebased on the best so far (picker_lastresort, 2.54): only engage.any_in_range changes
    "picker_aggressive": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                          "retreat.on_heavy_damage": False, "retreat.hold_fire": False,
                          "engage.any_in_range": True},
    # roadmap item 2: rooftop test, on top of the best so far (picker_lastresort, 2.54)
    "roof_camp": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "roof.enabled": True},
    # Stage D, run D1: best + mode detection & FFA overlay
    "mode_detect": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                    "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                    "farm.crates": True, "farm.cubes": True, "mode.detect": True},
    # Stage E, run Z1: best + final burn positioning
    "burn": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
             "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
             "farm.crates": True, "farm.cubes": True, "mode.detect": True, "burn.enabled": True},
    # Stage D: Free-for-all overlay preset (for testing / manual verification)
    "ffa": {"retreat.hp_enter": 0.50, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
            "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
            "farm.crates": True, "farm.cubes": True, "farm.drones": True,
            "engage.near_m": 60.0, "engage.low_hp": 0.35, "engage.any_in_range": False,
            "mode.detect": False},
}


FFA_OVERLAY = {
    # retreat-to-heal: retreat earlier to preserve HP, but keep shooting back
    "retreat.hp_enter": 0.50,
    "retreat.hp_exit": 0.80,
    "retreat.on_hunters": False,
    "retreat.on_heavy_damage": False,
    "retreat.hold_fire": False,
    # farming in FFA: silent cubes + safe crates & safe drones
    "farm.crates": True,
    "farm.cubes": True,
    "farm.drones": True,
    # opportunistic engagement only
    "engage.near_m": 60.0,
    "engage.low_hp": 0.35,
    "engage.any_in_range": False,
}

CURRENT_MODE = "practice"


def _resolve(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"unknown tuning preset {name!r}; known: {sorted(PRESETS)}")
    s = dict(DEFAULTS)
    s.update(PRESETS[name])
    return s


SETTINGS = _resolve(ACTIVE)


def get(key: str, default=None):
    return SETTINGS.get(key, default)


def set_mode(mode: str) -> None:
    """Apply mode overlay ('practice' or 'ffa')."""
    global SETTINGS, CURRENT_MODE
    CURRENT_MODE = mode
    s = _resolve(ACTIVE)
    if mode == "ffa":
        s.update(FFA_OVERLAY)
    SETTINGS = s


def get_mode() -> str:
    return CURRENT_MODE


def use(name: str) -> None:
    """Switch preset at runtime (tests)."""
    global SETTINGS, ACTIVE, CURRENT_MODE
    CURRENT_MODE = "practice"
    SETTINGS = _resolve(name)
    ACTIVE = name
