# Practice experiments

Practice = 48 matches against a 15-bot squad, with **fixed seeds for the whole event**, so every
submission plays the same matches. Score = mean of (16 − place). Submissions: 4 per hour, about
2–3 min to score; failed ones never lower the best score.

## Method

1. Every behaviour switch lives in `tuning.py`. An experiment is a named **preset** (only the
   settings it changes); select it with `ACTIVE = "..."`.
2. Change **one thing at a time** from the best known preset, so each score change has one cause.
3. First **re-run a known preset** to measure noise (same seeds, so differences come only from
   timing). Treat differences smaller than that noise as ties.
4. Log every submission below: preset, commit, score, what we learned.
5. **Combine** the best setting of each part into a final preset and confirm it with one more run.

Per run: set `ACTIVE`, run the tests (`TuningTest` catches misspelled keys), commit, push,
submit on the track page, record the score here.

## Settings (defaults in `tuning.py`)

| Key | Default | Meaning |
| :--- | :--- | :--- |
| `upgrades` | `ranked` | `first` = always choice 0; `ranked` = nanites, plating ×3, nanites, armor, … |
| `engage.near_m` | 60 | Shoot any mech this close |
| `engage.low_hp` | 0.35 | …or any target below this HP fraction |
| `engage.any_in_range` | false | Shoot any visible mech in gun range |
| `lightning.reserve` | 20 | Energy kept for jumps |
| `retreat.enabled` | true | Retreat-to-heal on/off |
| `retreat.hp_enter` / `hp_exit` | 0.55 / 0.90 | Retreat below / until healed to |
| `retreat.on_hunters` | true | Also retreat with 3+ hunters within 100 m |
| `retreat.on_heavy_damage` | true | Also retreat after losing >20% max HP in 2 s |
| `retreat.hold_fire` | true | Hold fire while retreating (except cornered / finishing) |
| `retreat.cornered_m` / `finish_hp` | 25 / 0.15 | Exceptions to holding fire |

## Results

| # | Preset | Commit | Score | Notes |
| :--- | :--- | :--- | :--- | :--- |
| 0 | (starter bot) | – | 1.15 | Track baseline |
| 1 | Phase 3 (= `p3`) | `956e3b7` | **2.33** | Movement + combat, first upgrade choice, no retreat |
| 2 | E1 (= `e1`) | `62f6560` | 1.52 | Retreat with all triggers + hold fire + ranked upgrades: worse |
| 3 | `p3` (run 1a) | `22ef4ff` | **2.33** | Noise check: identical to run 1. Scores are reproducible on these seeds, so any difference is caused by the change. |

## Batch 1 (planned, in order)

| Run | Preset | Question |
| :--- | :--- | :--- |
| 1a | `p3` | Noise: does the same behaviour score 2.33 again? (Verified offline: `p3` gives action-for-action the same output as commit `956e3b7` on the recorded match.) |
| 1b | `p3_picker` | Does the ranked upgrade picker help on its own? |
| 1c | `picker_lastresort` | Retreat only below 35% HP, keep shooting back, no hunter/damage triggers |
| 1d | `picker_aggressive` | Shoot any visible mech in range (score = kills in practice) |

Next batches: tune the winner's numbers (e.g. `engage.near_m`, `retreat.hp_enter`), then E2–E5
features as new switches, each tested the same way.
