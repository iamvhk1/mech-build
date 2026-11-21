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

**Interactions:** a one-at-a-time result means "best given everything else as it is now". A later
feature can turn a losing option into a winner (e.g. retreat may pay off once E2 fights from cover
and E3 adds HP and nanites, and healing late may matter for the E4 zone burn). So:

- Never delete a losing option; keep it as a switch so re-testing costs one line and one run.
- After each new feature lands, re-test the options likely to interact with it (after E2: retreat
  on/off; after E3: upgrade order; after E4: late-match healing).
- For strongly suspected pairs, run all four combinations (2 × 2) to see each effect and the
  interaction.
- Pick the final mix by testing the top complete combinations, not by stacking batch winners.
- Remember the practice seeds are fixed: prefer clear wins over tiny ones that may not carry over
  to the qualifier and final seeds.

Per run: set `ACTIVE`, run the tests (`TuningTest` catches misspelled keys), commit, push,
submit on the track page, record the score here, **and update the practice vs free-for-all table
below**.

## Practice vs free-for-all (don't overfit to practice)

Practice is the only thing we can measure, but qualifiers and finals are free-for-alls between
teams' bots, with no scores published until the end. The incentives differ:

| | Practice (1 vs a 15-bot squad) | Free-for-all (16 independent bots) |
| :--- | :--- | :--- |
| Who hunts us | Everyone, sharing vision | Whoever happens to find us |
| How to place well | Kills (house bots die only by us or the zone) + outlasting the final burn | Outliving others: they kill each other, survival alone climbs the ranking |
| Shooting | Needed for points | Reveals us (gun heard 320 m), invites third parties, resets our regen timer |
| Healing | Hard: the squad keeps finding us | Easy and valuable: nobody focuses us, the field thins while we heal |

**Rule:** every setting gets a practice value (measured) and a free-for-all value (reasoned from
the rules). The final bot carries both and switches on mode detection (E6: `alive` dropping
without our kills means a free-for-all). Until E6 exists, the bot plays practice settings.

| Setting / experiment | Practice (measured) | Free-for-all (expected) | Why | Practice value | FFA value |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Ranked upgrades (run 1b) | Neutral (2.31 vs 2.33) | Positive | Longer matches, more cubes from crates/kills; nanites and plating help survival | ranked | ranked |
| Early retreat + hold fire (E1) | **Bad** (1.52 vs ~2.3) | **Likely good** | No one focuses us, so hiding works and healing is cheap; holding fire keeps us hidden and lets others thin each other | off | on (retune later) |
| Last-resort retreat, keep firing (run 1c) | **Good** (2.54, +0.23) | Good, but weaker than early retreat | Saves us when nearly dead without giving up fights | on | superseded by early retreat |
| Roof camping (run 2) | **Bad** (2.23, −0.31) | Unknown | Cause unclear (the squad copes with roofs, or our climbing fails on the real server). In a FFA a roof could be a safe overlook, but we have no evidence it works at all | off | off unless evidence |
| Shoot any mech in range (run 1d) | pending | **Likely bad** | Long-range fights reveal us, start fights we don't need, and invite third parties; placement comes from surviving, not kills | per result | off (opportunistic) |
| Engage within 60 m / below 35% HP (Phase 3) | Baseline behaviour | Reasonable | Close mechs are threats anyway; low-HP targets are cheap kills (cubes) | 60 m / 35% | keep, maybe stricter |
| Lightning first, late mortar swap with laser check | Not tested separately | Same logic | Weapon triangle applies in both modes | as is | as is |

Implementation note (E6): `tuning.py` presets gain a free-for-all overlay (e.g.
`"ffa": {"retreat.hp_enter": 0.55, "retreat.hold_fire": True, "engage.any_in_range": False}`),
applied once mode detection says free-for-all.

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
| `roof.enabled` | false | Climb a usable roof (6–20 m high, ≥150 m², 12 m inside the next circle) and fight from it |
| `roof.peek_hp` | 0.5 | Step to the roof edge toward the nearest hunter only above this HP fraction |

## Results

| # | Preset | Commit | Score | Notes |
| :--- | :--- | :--- | :--- | :--- |
| 0 | (starter bot) | – | 1.15 | Track baseline |
| 1 | Phase 3 (= `p3`) | `956e3b7` | **2.33** | Movement + combat, first upgrade choice, no retreat |
| 2 | E1 (= `e1`) | `62f6560` | 1.52 | Retreat with all triggers + hold fire + ranked upgrades: worse |
| 3 | `p3` (run 1a) | `22ef4ff` | **2.33** | Noise check: identical to run 1. Scores are reproducible on these seeds, so any difference is caused by the change. |
| 4 | `p3_picker` (run 1b) | `db05867` | 2.31 | Ranked upgrade order alone: neutral (one place in one match). The bot likely gets few offers without cube collection (E3). Keep it; compare 1c/1d against 2.31. |
| 5 | `picker_lastresort` (run 1c) | `9144f7e` | **2.54** | Best so far (+0.23, ~11 places over 48 matches). Retreat only below 35% HP until 80%, keep shooting back, no hunter/damage triggers. **New baseline.** |
| 6 | `roof_camp` (run 2) | `6140823` | 2.23 | Roof camping on top of the 2.54 baseline: worse (−0.31). Either the squad handles roofs fine (climbs, mortars, sees us) or our climbing fails on the real server; can't tell without diagnostics. Roofs off for practice; switch kept for a later re-test. |

## Batch 1 (planned, in order)

| Run | Preset | Question |
| :--- | :--- | :--- |
| 1a | `p3` | Noise: does the same behaviour score 2.33 again? (Verified offline: `p3` gives action-for-action the same output as commit `956e3b7` on the recorded match.) |
| 1b | `p3_picker` | Does the ranked upgrade picker help on its own? |
| 1c | `picker_lastresort` | Retreat only below 35% HP, keep shooting back, no hunter/damage triggers |
| 1d | `picker_aggressive` | Shoot any visible mech in range (score = kills in practice). Rebased on the 2.54 baseline after run 1c. |

## Roadmap (decided 2026-11-21: major items first, small tuning last)

Budget: 4 runs per hour. Every run must change a decision; interaction re-tests only with a
concrete reason.

| # | Item | Runs | Why here |
| :--- | :--- | :--- | :--- |
| 1 | Finish batch 1 (1c, 1d) | 2 | Already built |
| 2 | **Rooftop test** ("roof camp": climb a roof inside the next circle, shoot from the edge, drop when the zone moves). **Built:** preset `roof_camp` | 1–2 | Decides whether house bots can follow us up; if not, roofs become the core plan and shape E2 |
| 3 | **E2 fight quality** (cover, shoot-and-step-back, focus fire, finishing kills) | 2–3 | Practice score = kills |
| 4 | **E4 final zone burn** | 1–2 | Up to 15 points a match if we survive to ~6:55 |
| 5 | **E3 cubes and HP pool** | 1–2 | Makes upgrades matter (run 1b) and feeds the burn |
| 6 | Retreat re-test (after E2 / roofs) | 1–2 | Interaction rule |
| 7 | E5 supply drops; E6 free-for-all mode | 1 + 0 | E6 needed for qualifiers; practice can't measure it |
| 8 | Small tuning (thresholds, distances, reserves) | as budget allows | |
