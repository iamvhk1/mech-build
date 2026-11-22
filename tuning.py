"""Behaviour switches for experiments (docs/experiments.md).

Every tunable behaviour reads its setting from here. An experiment is a named preset: change
ACTIVE, commit, push, submit, and record the score in docs/experiments.md. Presets list only the
settings they change from DEFAULTS.
"""
from __future__ import annotations

ACTIVE = "fresh_hide"

DEFAULTS = {
    # upgrade offers: "first" = always choice 0 (Phase 3 behaviour), "ranked" = upgrades.py ranking
    "upgrades": "ranked",
    # mode detection (master plan Stage D, E6)
    "mode.detect": False,           # D1: detect practice vs free-for-all and apply FFA overlay
    # final zone burn (master plan Stage E, E4)
    "burn.enabled": False,          # E4: final burn play (center hold in late circles)
    "burn.radius": 25.0,            # next_radius threshold to enter burn mode
    # supply drops (master plan Stage F, E5)
    "drops.enabled": False,         # E5: contest landed/landing supply drops when safe
    "drops.safe_m": 80.0,           # safe distance from hunters and drop location
    "drops.max_dist": 150.0,        # max distance to travel for a supply drop
    "drops.early_s": 5.0,           # go for a landing drop when it lands within our ETA + this
    "zone.edge_m": None,            # edge play: stand this far inside the next circle (None = 35% of its radius)
    "mortar.swap_r": 70.0,          # swap lightning for a mortar once the zone radius is at most this
    "drops.max_threats": 0,         # D5: known mechs tolerated within drops.safe_m (0 = none, no fight)
    # engagement policy (Phase 3, Q1)
    "engage.near_m": 60.0,          # shoot any mech this close
    "engage.low_hp": 0.35,          # ...or any target below this HP fraction
    "engage.any_in_range": False,   # True: shoot any visible mech in gun range
    "lightning.reserve": 20.0,
    "lightning.any_mech": False,    # H1: fire even if a different enemy mech is nearest in the cone      # energy kept for jumps (unless the target is within 20 m)
    # retreat-to-heal (Phase 4, E1)
    "retreat.enabled": True,
    "retreat.hp_enter": 0.55,       # retreat below this HP fraction
    "retreat.hp_exit": 0.90,        # ...until healed to this
    "retreat.on_hunters": True,     # also retreat with 3+ hunters within 100 m
    "retreat.on_heavy_damage": True,  # also retreat after losing >20% max HP in 2 s
    "retreat.hold_fire": True,      # hold fire while retreating (regen needs no damage dealt)
    "retreat.cornered_m": 25.0,     # ...but fight back this close
    "retreat.finish_hp": 0.15,      # ...or finish a target this low
    "retreat.away": False,          # R1: hide spots only on the far side from the hunters' centre
    "retreat.roof": False,          # R3: retreat onto a climbable roof within 45 m (energy >= 45)
    "retreat.fresh_hide": False,
    "retreat.flee": False,          # N7: retreating, nowhere hidden and still hit -> move ~30 m away from attackers    # N3: no hunter in sight -> stay and heal; drop hide spots chosen against gone hunters
    "retreat.fallback": False,      # G3: no fully hidden spot -> flee to the best partial cover (choke-like)
    "retreat.scaled": False,        # F2: retreat at 50% with 2 hunters within 75 m, 65% with 3+
    "retreat.many_n": None,         # S1: also retreat with this many hunters within 100 m...
    "retreat.many_hp": 0.70,        # ...when below this HP fraction
    "heal.lull_hp": None,           # S2: below this HP with no hunter around, stop and heal to 95%
    # rooftop camping (roadmap item 2)
    "roof.enabled": False,          # climb a roof inside the next circle and fight from its edge
    "roof.peek_hp": 0.5,            # step to the edge toward a hunter only above this HP fraction
    "roof.after": None,             # E1 fortress: roof play only from this match time (None = whole match)
    # fight quality (master plan Stage B)
    "fight.cover": False,           # B1: fight from cover (step out to fire, back to reload / after hits)
    "fight.blind_fire": False,      # fire back along the damage bearing at attackers we can't see
    "fight.focus": False,           # B3: stay on one target, prefer quickest kills, finish wounded targets
    "fight.strafe": False,          # strafe sideways while fighting (safeguarded: walls, zone, exposure)
    "fight.pacing": False,          # C2: escalation survival (loot a kill's cubes, split ganging hunters)
    "pacing.split": True,
    "pacing.loot_more": False,      # E3: loot every recent kill (30 s), and close cubes even while retreating
    "press.to_m": 25.0,             # press closes to this distance from a lone hunter
    "fight.press": False,           # D2: with lightning, close to ~25 m on a lone hunter (pacing.py)
    "fight.choke": False,           # G1: with 2+ hunters near, fight from the spot with the fewest open lanes
    "arm.prefer_laser": False,      # G2 check: go for a laser first instead of lightning
    "fight.finish": False,          # H3: a shootable enemy below 35% HP within 45 m comes first
    "fight.arc": False,             # H2: prefer targets that keep other attackers in our front 180 deg
    "fight.mpc": False,
    "mpc.min_hunters": 2,           # MPC with at least this many fresh hunters within 110 m
    "fight.narrow": False,          # N1: after narrow.after_kills kills, base at the spot with the fewest open lanes
    "narrow.after_kills": 3,
    "narrow.radius": 60.0,          # how far to look for the narrow base
    "narrow.max_lanes": None,       # N4: a narrow base must have at most this many open lanes (else none)
    "narrow.force": False,          # N5: 2+ mechs within 150 m and an open spot -> go to the nearest real choke
    "narrow.force_pre": False,      # ...only before contact: nearest mech > 50 m, no damage in 3 s
    "narrow.force_m": 100.0,        # ...looking for the choke within this distance
    "farm.crate_max_lanes": None,   # skip crates whose spot has more open lanes than this
    "narrow.hold": False,           # at the narrow base, MPC only adjusts within 6 m (hold the gully)
    "mpc.w_lanes": 0.0,             # MPC: penalty per open approach lane at a move's end (prefer gullies)
    "farm.drone_use_safe_m": False, # drone farming: clear radius = farm.safe_m (60 m early) instead of 90 m
    "mpc.tier": False,              # M3: weight each enemy's predicted damage by its tier (aggro order)
    "mpc.chase": False,             # M3: predict enemies closing on us (house bots hunt) instead of drifting
    "mpc.retreat": False,           # M4: while retreating, the escape move with the least predicted damage
    "mpc.w_taken": 1.2,             # score = dealt - w_taken * taken
    "mpc.w_taken_retreat": 3.0,
    "mpc.retreat_m": 110.0,         # retreat planning considers hunters within this distance (far shooters too)     # ...while retreating (dealt weighted 0.3)             # M1: with 2+ hunters, 1.2 s rollouts of 13 manoeuvres (pacing.py)
    "fight.los": False,             # R2: with 2+ hunters, step to where the fewest can see us (pacing.py)
    "fight.hunt": False,            # D4: with lightning, go after the only mech we know of (pacing.py)
    "hunt.max_m": 250.0,
    "hunt.local": False,            # F2: hunt the nearest mech when every other known one is far behind it
    "arm.early": False,             # walk to a remembered lightning (up to arm.max_dist) while slot 1 is empty
    "arm.max_dist": 200.0,
    "arm.roof_until": None,
    "farm.roof_until": None,        # N6: until this match time (energy >= 60), roof crates / cubes count too         # R4: until this match time (energy >= 60), roof lightnings count too
    "arm.laser_after": None,        # D3: from this match time, take a laser if no lightning is within reach
    "arm.safe_m": 50.0,             # ...only with no hunter this close           # ...including the split rule (C2c tests loot alone)
    # cube economy (master plan Stage C)
    "farm.crates": False,           # C1: shoot street-level crates and collect their cube when safe
    "farm.cubes": False,            # C3: also collect any other visible cube (kill drops) when safe
    "farm.drones": False,           # C2: hunt isolated NPC drones (2 cubes each) when safe
    "farm.drone_min_hp": 0.90,      # HP fraction required to farm drones
    "farm.drone_dist_min": 30.0,    # stand-and-shoot minimum distance from drone
    "farm.drone_dist_max": 50.0,    # stand-and-shoot maximum distance from drone
    "farm.safe_m": 120.0,           # farm only with no known hunter within this distance
    "farm.min_hp": 0.6,             # ...and HP at least this fraction (crates/cubes)
    "farm.max_dist": 80.0,
    "farm.bank": False,
    "farm.cap": False,              # N8: at the cube stat cap stop farming / looting cubes (they only add size)
    "farm.wounded": False,          # N8: below 85% HP no crates / drones (dealing damage restarts regen)             # M2: leave cubes on the floor at >= 95% HP; walk over them below 70% HP          # consider crates/cubes/drones within this distance
    # diagnostics (never in a real preset): from this match time on, stand still and hold fire, so
    # the score reads out the place points earned before it
    "probe.idle_at": None,
    "probe.idle_on_pace": "",       # "loot" / "split": stand still from the first time that pacing rule fires
    # late-match caution (practice): from this match time on, apply LATE_OVERLAY (None = never)
    "late.at": None,
    # early-match cube rush (practice): until this match time, apply EARLY_OVERLAY (None = never)
    "early.until": None,
    "early.drones": False,          # E4: during the early phase, also hunt NPC drones (2 cubes each)
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
    # + supply drops with the A1 fix (run B4) 3.46; + loot a kill's cubes (run C2c) 3.48, kept by
    # decision despite the tie (highest score so far; plausible mechanism); + crates/cubes up to 120 m
    # (run C3) 3.88, the first score on builders-4 (96 random seeds), kept; + arm up early with a
    # remembered lightning (run D1) 4.05; + press a lone hunter into lightning range (run D2) 4.19;
    # + FFA/zone fixes (8b5a7d5) 4.30; + laser fallback with the laser aim fix (run D3) 4.46;
    # + hunt the only known mech (run D4) 4.59, practice only (FFA_OVERLAY turns it off);
    # + early phase rush and NPC drone hunting (run E4) 4.67, practice only
    "best": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
             "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
             "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
             "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
             "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True,
             "early.until": 120.0, "early.drones": True},
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
    # Stage G, run G1b: best + engage mechs within 90 m (was 60 m; 40 m lost in G1). Rebased on the
    # current best (the old near90 predated strafing, farming and mode detection).
    "near90": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "mode.detect": True, "engage.near_m": 90.0},
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
    # Stage F, run F1: best + supply drop contesting
    "drops": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True},
    # Stage G: tuning sweeps on best
    # G1: engage closer (40 m vs 60 m baseline) to avoid picking fights with distant squad members
    "near40": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "mode.detect": True, "engage.near_m": 40.0},
    # G2: delay retreat to 25% HP (fight back longer)
    "retreat25": {"retreat.hp_enter": 0.25, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                  "farm.crates": True, "farm.cubes": True, "mode.detect": True},
    # G3: retreat earlier to 45% HP (preserve HP pool)
    "retreat45": {"retreat.hp_enter": 0.45, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                  "farm.crates": True, "farm.cubes": True, "mode.detect": True},
    # G4: exit retreat earlier at 70% HP
    "exit70": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.70, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "mode.detect": True},
    # Stage G, farming gates (cube collection was the largest single gain, +0.38)
    # G5: farm with hunters closer (no known hunter within 80 m instead of 120 m)
    "farm_safe80": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                    "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                    "farm.crates": True, "farm.cubes": True, "mode.detect": True, "farm.safe_m": 80.0},
    # G6 / C3: look further for crates/cubes (120 m instead of 80 m); rebased on best (3.48) for C3
    "farm_reach120": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                      "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                      "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                      "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0},
    # G7: farm at lower HP (45% instead of 60%); cubes also heal
    "farm_hp45": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                  "farm.crates": True, "farm.cubes": True, "mode.detect": True, "farm.min_hp": 0.45},
    # Batch B (2026-11-22), B1: hold the next zone centre all match (burn mode from t = 0: navigate to
    # the centre, fight from there, no retreat) and let the zone thin the squad
    "center": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "mode.detect": True,
               "burn.enabled": True, "burn.radius": 1000.0},
    # B2/B3 diagnostic probes: best until T, then idle (score = place points earned by T)
    "probe_idle120": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                      "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                      "farm.crates": True, "farm.cubes": True, "mode.detect": True, "probe.idle_at": 120.0},
    "probe_idle240": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                      "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                      "farm.crates": True, "farm.cubes": True, "mode.detect": True, "probe.idle_at": 240.0},
    # Batch C, C1: best + more conservative retreat from 3:00 (probes: we earn most points 2:00-4:00
    # and die around 3:00-4:30, when several hunters are on us at once)
    "late180": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                "late.at": 180.0},
    # Batch C, C2: best + escalation survival (pacing.py)
    "pacing": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
               "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
               "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
               "fight.pacing": True},
    # C2 diagnostics: pacing scored 3.46, an exact tie with best. Does each rule ever fire in practice?
    # Each plays `pacing` and stands still from the first time its rule fires (3.46 = never fires).
    "probe_loot": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                   "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                   "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                   "fight.pacing": True, "probe.idle_on_pace": "loot"},
    "probe_split": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                    "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                    "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                    "fight.pacing": True, "probe.idle_on_pace": "split"},
    # C2c: pacing with the loot rule only (probe_loot 1.60: loot fires in practice; does it help?)
    "pacing_loot": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                    "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                    "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                    "fight.pacing": True, "pacing.split": False},
    # D1: best + arm up early (remembered lightning pickups up to 200 m; the gun alone sustains ~100
    # damage/s, lightning adds 240/s within 45 m with no aiming)
    "arm": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
            "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
            "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
            "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True},
    # D2: best (with arm, 4.05) + press a lone hunter into lightning range
    "press": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True},
    # D3: best (with press, 4.19) + laser fallback from 45 s (with the laser aim fix in combat.py)
    "laser": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0},
    # D4: best (4.19) + hunt the lone early hunter (with lightning, up to 250 m)
    "hunt": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
             "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
             "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
             "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
             "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True},
    # D5: best (4.19) + contest drops with up to one known mech near (fighting it if needed)
    "drops_bold": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                   "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                   "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                   "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
                   "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "drops.max_threats": 1},
    # E-ideas (scratch, simulator only so far): best with retreat off (fight to the end)
    "noretreat": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                  "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                  "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
                  "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "retreat.enabled": False},
    # E1 fortress: best, then from 3:30 hold the best reachable roof inside the next circle (peek the
    # edge to shoot above 60% HP): try to live to the final burn, where the most HP dies last
    "fortress": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True,
                 "roof.enabled": True, "roof.after": 210.0, "roof.peek_hp": 0.6},
    # E2 early cube rush: best, and for the first 100 s farm crates/cubes up to 250 m away with hunters
    # as close as 60 m (stronger before the escalation)
    "rush": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 100.0},
    # E4: best + early phase (first 120 s): rush (farm up to 250 m, hunters >= 60 m) and hunt NPC drones
    "rush_drones": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0, "early.drones": True},
    # E3: best (4.67) + loot every kill of the last 30 s (not only the last), and kill cubes within 30 m
    # even while retreating (visualizer replays: fled from drops at low HP, lost the first of two kills)
    "loot_more": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
                  "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
                  "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
                  "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
                  "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
                  "early.drones": True, "pacing.loot_more": True},
    # U2: loot_more + durable upgrade order (plating x3, armor x3, gun / lightning damage, nanites last)
    "durable": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable"},
    # F1 package: loot_more (E3) + durable upgrades + anti-centroid retreat + line-of-sight steering
    "package": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True, "fight.los": True},
    # G candidates on top of the 4.72 package
    "pkg_anymech": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True},
    "pkg_h1_fb": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True},
    "h2_mpc": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True},
    "mpc_chase": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True, "mpc.chase": True},
    "mpc_one": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True, "mpc.min_hunters": 1},
    "mpc_retreat": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True, "mpc.retreat": True},
    "mpc2": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True, "mpc.chase": True, "mpc.retreat": True},
    "mpc3": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "mpc.tier": True},
    "narrow": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True},
    "narrow1": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 1},
    "narrow2": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2},
    "roof_arm": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2, "arm.roof_until": 100.0},
    "fresh_hide": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True},
    "plaza6": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.max_lanes": 6},
    "plaza6_crates": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.max_lanes": 6, "farm.crate_max_lanes": 6},
    "force": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.max_lanes": 6, "narrow.force": True},
    "force40": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.max_lanes": 6, "narrow.force": True, "narrow.force_m": 40.0},
    "force_pre": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.max_lanes": 6, "narrow.force": True, "narrow.force_pre": True,
              "narrow.force_m": 40.0},
    "res0": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "lightning.reserve": 0.0},
    "res0_roof": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "lightning.reserve": 0.0, "farm.roof_until": 100.0},
    "flee": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "retreat.flee": True},
    "drone60": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "farm.drone_use_safe_m": True},
    "n6": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "lightning.reserve": 0.0, "farm.roof_until": 100.0, "retreat.flee": True, "farm.drone_use_safe_m": True},
    "n6b": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "retreat.flee": True, "farm.drone_use_safe_m": True},
    "n6c": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": True, "retreat.cornered_m": 80.0, "mpc.retreat_m": 250.0,
              "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "retreat.flee": True, "farm.drone_use_safe_m": True},
    "volt": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "upgrades": "volt"},
    "press15": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "press.to_m": 15.0},
    "press40": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "press.to_m": 40.0},
    "edge": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "zone.edge_m": 15.0},
    "dropearly": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "drops.early_s": 15.0},
    "mortar_mid": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "mortar.swap_r": 240.0},
    "r_mpc1": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "mpc.min_hunters": 1},
    "r_safe80": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "farm.safe_m": 80.0},
    "r_bold": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "drops.max_threats": 1},
    "r_hold": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "narrow.hold": True},
    "r_drone60": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "farm.drone_use_safe_m": True},
    "cap": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "retreat.fresh_hide": True, "farm.cap": True, "farm.wounded": True},
    "hold": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "narrow.hold": True},
    "defensive": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "mpc.w_taken": 2.0},
    "gully": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "mpc.w_lanes": 30.0, "narrow.radius": 95.0, "farm.drone_use_safe_m": True},
    "gully_mpc": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True,
              "mpc.chase": True, "mpc.retreat": True, "fight.narrow": True, "narrow.after_kills": 2,
              "arm.roof_until": 100.0, "mpc.w_lanes": 30.0},
    "mpc_bank": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "fight.mpc": True, "farm.bank": True},
    "h2_roof": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "retreat.roof": True},
    "h2_roof_scaled": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "retreat.fallback": True, "retreat.roof": True, "retreat.scaled": True},
    "pkg_finish": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "fight.finish": True},
    "pkg_arc": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "fight.arc": True},
    "pkg_h12": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "lightning.any_mech": True, "fight.arc": True},
    "pkg_fallback": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "retreat.fallback": True},
    "pkg_choke": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "fight.choke": True},
    "pkg_laser1": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "arm.prefer_laser": True},
    # F2 candidates on top of the 4.72 package
    "pkg_scaled": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "retreat.scaled": True},
    "pkg_hunt": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "upgrades": "durable", "retreat.away": True,
              "fight.los": True, "hunt.local": True},
    # R1: loot_more + anti-centroid hide spots
    "away": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "retreat.away": True},
    # R2: loot_more + line-of-sight steering with 2+ hunters
    "los": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "fight.los": True},
    # R1 + R2
    "away_los": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "retreat.away": True, "fight.los": True},
    # S2: loot_more + heal in lulls (below 75% HP with no hunter within 100 m: regenerate to 95%)
    "lull": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "heal.lull_hp": 0.75},
    # S1: loot_more + back off when 2 hunters are within 100 m below 70% HP (still shooting)
    "many2": {"retreat.hp_enter": 0.35, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
              "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
              "farm.crates": True, "farm.cubes": True, "mode.detect": True, "drops.enabled": True,
              "fight.pacing": True, "pacing.split": False, "farm.max_dist": 120.0, "arm.early": True,
              "fight.press": True, "arm.laser_after": 45.0, "fight.hunt": True, "early.until": 120.0,
              "early.drones": True, "pacing.loot_more": True, "retreat.many_n": 2},
    # Stage D: Free-for-all overlay preset (for testing / manual verification)
    "ffa": {"retreat.hp_enter": 0.50, "retreat.hp_exit": 0.80, "retreat.on_hunters": False,
            "retreat.on_heavy_damage": False, "retreat.hold_fire": False, "fight.strafe": True,
            "farm.crates": True, "farm.cubes": True, "farm.drones": True,
            "engage.near_m": 60.0, "engage.low_hp": 0.35, "engage.any_in_range": False,
            "mode.detect": False, "burn.enabled": True, "drops.enabled": True},
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
    # final burn play: center holding in late collapse
    "burn.enabled": True,
    # supply drops in FFA: contest when safe
    "drops.enabled": True,
    "drops.max_threats": 0,   # only uncontested drops: in a free-for-all, outliving others is what scores
    # never go looking for fights in a free-for-all (practice-only: hunt scored 4.59 there, D4)
    "fight.hunt": False,
}

# Late-match caution (practice only): back off and heal earlier when hunters gang up, but keep
# shooting back (holding fire lost badly in E1: placement in practice comes from kills)
LATE_OVERLAY = {
    "retreat.hp_enter": 0.50,
    "retreat.hp_exit": 0.90,
    "retreat.on_hunters": True,
    "retreat.on_heavy_damage": True,
    "retreat.hold_fire": False,
}

# Early-match cube rush (practice only): farm farther, with hunters closer
EARLY_OVERLAY = {
    "farm.max_dist": 250.0,
    "farm.safe_m": 60.0,
}

# Early drone hunting (with early.drones): drones (350 HP, 2 cubes) while no hunter is around yet
EARLY_DRONES_OVERLAY = {
    "farm.drones": True,
    "farm.drone_min_hp": 0.6,
}

CURRENT_MODE = "practice"
CURRENT_LATE = False
CURRENT_EARLY = False


def _resolve(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"unknown tuning preset {name!r}; known: {sorted(PRESETS)}")
    s = dict(DEFAULTS)
    s.update(PRESETS[name])
    return s


SETTINGS = _resolve(ACTIVE)


def get(key: str, default=None):
    return SETTINGS.get(key, default)


def _apply() -> None:
    global SETTINGS
    s = _resolve(ACTIVE)
    if CURRENT_MODE == "ffa":
        s.update(FFA_OVERLAY)
    else:
        if CURRENT_EARLY:
            s.update(EARLY_OVERLAY)
            if s.get("early.drones"):
                s.update(EARLY_DRONES_OVERLAY)
        if CURRENT_LATE:
            s.update(LATE_OVERLAY)
    SETTINGS = s


def set_mode(mode: str) -> None:
    """Apply mode overlay ('practice' or 'ffa')."""
    global CURRENT_MODE
    CURRENT_MODE = mode
    _apply()


def set_late(late: bool) -> None:
    """Apply (or clear) the late-match overlay; ignored in free-for-all mode."""
    global CURRENT_LATE
    CURRENT_LATE = bool(late)
    _apply()


def is_late() -> bool:
    return CURRENT_LATE


def set_early(early: bool) -> None:
    """Apply (or clear) the early-match overlay; ignored in free-for-all mode."""
    global CURRENT_EARLY
    CURRENT_EARLY = bool(early)
    _apply()


def is_early() -> bool:
    return CURRENT_EARLY


def get_mode() -> str:
    return CURRENT_MODE


def use(name: str) -> None:
    """Switch preset at runtime (tests)."""
    global SETTINGS, ACTIVE, CURRENT_MODE, CURRENT_LATE, CURRENT_EARLY
    CURRENT_MODE = "practice"
    CURRENT_LATE = False
    CURRENT_EARLY = False
    SETTINGS = _resolve(name)
    ACTIVE = name
