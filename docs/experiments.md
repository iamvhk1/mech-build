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
| Shoot any mech in range (run 1d) | **Bad** (2.02, −0.52) | **Likely bad** | Long-range fights reveal us, start fights we don't need, and invite third parties; placement comes from surviving, not kills | off | off (opportunistic) |
| Engage within 60 m / below 35% HP (Phase 3) | Baseline behaviour; 90 m pending (`near90`) | Reasonable | Close mechs are threats anyway; low-HP targets are cheap kills (cubes) | 60 m / 35% (90 m pending) | keep 60 m or stricter |
| Lightning first, late mortar swap with laser check | Not tested separately | Same logic | Weapon triangle applies in both modes | as is | as is |
| Trigger timing fix (always on) | **Good** (2.90, +0.36) | Positive | Bug fix: up to ~20% more gun damage in every fight | on | on |
| Shootability fix (always on): prefer targets we can shoot; aim at the visible part | Tie (2.85 vs 2.90); kept for correctness and FFA | Positive | Bug fix: with two enemies, a hidden attacker blocked a clear shot at the other in 50/50 test cases; a low wall over the middle blocked shots at a visible upper body | on | on |
| Blind fire at unseen attackers (`fight.blind_fire`) | **Bad** (2.40, −0.50), despite the duel screen predicting 37/40 wins | Unknown, likely bad for the same reasons | Bearings can point at blasts or arc origins, guessed shots waste the magazine, and gunfire reveals us | off | off |
| Focus fire (`fight.focus`, B3) | **Bad** (2.63, −0.22) | Unknown, likely bad for the same reasons | Sticking to a hidden target and chasing far wounded ones costs time and HP | off | off |
| Strafing in fights (`fight.strafe`) | Tie (2.88 vs 2.85); duel predicted a large gain | Small positive at best | Only dodges gun bullets; lasers and lightning are instant | on (kept by decision despite the tie) | on (dodges gun fire, which matters vs gun-armed bots) |
| Crates and their cubes (`farm.crates`, C1) | **Good** (3.00, +0.12) | Positive | +4% max HP and damage per cube, upgrade offers; gated on safety, so it happens in quiet moments in both modes. Risk: gunfire and the crate breaking (heard 220 m) reveal us | on | on |
| All visible cubes / kill drops (`farm.cubes`, C3) | **Good** (3.38, +0.38) | Positive | Walking over dropped cubes makes zero gunfire sound (unlike crates which make 220 m noise and need shooting), gives instant HP healing (+4% max HP healed per cube), damage bonus, and faster upgrade offers; safe walks only | on | on |
| Cover fighting (`fight.cover`, B1) | Dropped offline: duel screen no better (0.74 vs 0.75), worse with a wider search | Unknown | Only ~2% of spots within 24 m are hidden from an enemy 40–120 m away (long street sightlines) | off | off |

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
| `fight.cover` | false | B1: fight from cover (step out to fire, back to reload / after hits). Dropped offline |
| `fight.blind_fire` | false | Fire back along the damage bearing at attackers we can't see. Off: 2.40 vs 2.90 |
| `fight.focus` | false | B3: stay on one target (1 s grace), prefer quickest kill (HP / hit chance), finish targets below 25% HP. Off: 2.63 vs 2.85 |
| `fight.strafe` | false | Strafe sideways while fighting, reversing every 0.6–1.5 s (0.35–0.6 s near cover); safeguarded. **On in `best`** |
| `farm.crates` | false | C1: shoot street-level crates and collect their cube when safe. **On in `best`** |
| `farm.cubes` | false | C3: also collect any other visible cube (kill drops) when safe. **On in `best`** |
| `farm.safe_m` / `min_hp` / `max_dist` | 120 / 0.6 / 80 | Farming safety: no hunter within, HP at least, how far to look |

Code-level fixes (not switches, apply to every preset): trigger timing (`READY_WITHIN_S`, run B0);
shootability (`Combat.shot_point`, target preference for shootable mechs; pending).

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
| 7 | `picker_aggressive` (run 1d) | `075cef9` | 2.02 | Shoot any visible mech in range, on the 2.54 baseline: clearly worse (−0.52, ~25 places). Long-range fights against a squad that shares vision cost more than they earn. E2 should pick fights carefully; try a shorter `engage.near_m` (40 m) in Stage G. |
| 8 | `best` + trigger-timing fix (run B0) | `b47593e` | **2.90** | New best (+0.36 over 2.54, ~17 places). Bug fix: hold the trigger when the weapon is ready before the next decision. |
| 9 | `blind` (run B2) | `69d2b6a` | 2.40 | Blind fire on the 2.90 best: clearly worse (−0.50). The duel's assumption (attackers often hidden by foliage) doesn't hold in real matches, or blind shots hurt: the damage bearing points at mortar blasts or arc origins rather than shooters, guessed shots waste the magazine before real targets appear, and gunfire reveals us. Off in both modes. Lesson: the duel harness found a real bug but mispredicted house-bot behaviour. |
| 10 | `near90` | `56b50be` | *skipped* | Pushed but not submitted: the shootability fix (found by the audit) changes which target we shoot, which interacts with the engagement range, so `near90` is re-run on the fixed code. |
| 11 | `best` + shootability fix (run B0b) | `8c5820c` | 2.85 | −0.05: a tie under our rule. Kept anyway: it corrects a real misreading, matters more in free-for-all multi-enemy fights, and its likely practice cost (switching targets spreads damage, fewer kills) is what B3 focus fire addresses. **Baseline for the current code: 2.85.** |
| 12 | `near90` on the fixed code | – | *skipped* | Decided low priority (a tuning number, expected effect small); moved to Stage G. |
| 13 | `focus` (run B3) | `65744ad` | 2.63 | Focus fire on the 2.85 baseline: worse (−0.22, ~10 places). Likely: the 1 s grace keeps aiming at a target that ducked behind cover instead of shooting the one we can hit, and time-to-kill ranking can prefer a far wounded target over a near one that is shooting us. Off in both modes. |
| 15 | `crates` (run C1) | `1f78964` | **3.00** | **New best** (+0.12 over 2.88, ~6 places). Shoot street-level crates and collect their cube, only when safe (no mech to fight, HP ≥ 60%, no hunter within 120 m, zone allows the detour); gun only, stand and shoot within 18 m, within 60 m max. Kept; now part of `best`. |
| 16 | `cubes` (run C3) | `48c2979` | **3.38** | **New best** (+0.38 over 3.00, ~18 places). Walk over any visible cube on the street (kill drops, floor spawns) when safe. Big win: collecting cubes is completely silent (no gunfire or crate destruction sound heard up to 220 m to attract hunters), grants instant HP healing (+4% max HP healed per cube), scales damage, and accelerates upgrade thresholds early. Kept; now part of `best`. |
| 17 | `upgrade_first` (run U1) | pending | *pending* | Re-test upgrade order on the 3.38 baseline: always pick choice 0 (measure value of ranked picker now that cube collection is active; compare against 3.38). Active preset: `upgrade_first`. |
| 14 | `strafe` (run B-strafe) | `11c2b69` | 2.88 | Strafe sideways while fighting, on the 2.85 baseline (rebased off focus fire after B3 lost). Safeguards: walkable steps, zone margin, never more exposed to known hunters, short jinks near cover, no hops (stuck detection paused only after a decision where we actually strafed). Duel screen with real leading bullets: won 31/40 vs 18/40, damage taken −18%. **Scored 2.88 (+0.03): a tie.** Likely small because strafing only dodges gun bullets; lasers (instant) and lightning (auto-target) don't care, and lasers were everywhere in the recorded match. Tie under our rule, but **kept on by decision** (points the right way; plausible mechanism). **New baseline: `best` = this, 2.88.** |

## Batch 1 (done)

| Run | Preset | Question |
| :--- | :--- | :--- |
| 1a | `p3` | Noise: does the same behaviour score 2.33 again? (Verified offline: `p3` gives action-for-action the same output as commit `956e3b7` on the recorded match.) |
| 1b | `p3_picker` | Does the ranked upgrade picker help on its own? |
| 1c | `picker_lastresort` | Retreat only below 35% HP, keep shooting back, no hunter/damage triggers |
| 1d | `picker_aggressive` | Shoot any visible mech in range (score = kills in practice). Rebased on the 2.54 baseline after run 1c. |

## Master plan (decided 2026-11-21; replaces the earlier roadmap)

**Where we stand:** best score **3.38** (run C3). `best` = last-resort retreat + strafing + crate
farming + all visible cubes on the current code; new runs compare against 3.38. Average placement
climbs to ~12th-13th.
Leading teams score ~5–6; qualifying needs a top-32 best practice score. The plan is ordered by
expected gain: first make fights winnable and survivable, then grow the HP/damage pool, then
secure the free-for-all behaviour, then play for the end of the match, then tune.

### Rules for every stage

- **One switch per run**, compared against the current best preset. A new feature ships as a
  switch in `tuning.py` that is off by default.
- **Keep a change** if it beats the best by at least **+0.05** (2–3 places over 48 matches) *and*
  we can explain why it helps. Smaller gains count as ties; prefer the simpler option.
- **Every run updates both tables:** results, and practice vs free-for-all.
- **Screen offline first** where the mini simulator can (duels, movement); spend submissions on
  what only real house bots can answer.
- **Regression guard:** the best preset gets a `best` alias in `tuning.py`, and the active preset
  is always best + one change.
- **Before each push:** code changes get the full set (tests, the sanitizer build, `check.py`,
  the sandboxed `tools/check_docker.sh`); preset-only changes get the tests (incl. `TuningTest`)
  and `check.py`, since a settings change can't introduce memory or build errors.

### Stage A: finish batch 1 (done)

| Run | Change | Decides |
| :--- | :--- | :--- |
| 1d | `engage.any_in_range` | **Done: 2.02, worse.** Pushing fights doesn't pay; E2 picks fights carefully. |

### Stage B: E2, fight quality (crucial; both modes)

Score in practice is kills; in a free-for-all, winning unavoidable fights is how we outlive
others. Built as four switches, tested in this order:

| Run | Switch | What it does | Offline check first |
| :--- | :--- | :--- | :--- |
| B1 | `fight.cover` | When engaged, move to a nearby spot with cover from the target and step out only to shoot (shoot-and-step-back); reload and heal behind cover | **Dropped offline:** no gain in the duel screen; cover within reach is rare on campus streets |
| B0 | (bug fix) | Trigger timing: hold the trigger when the weapon is ready before the next decision. Found while screening B1: we released it during the window the next shot would fire, losing ~20% of gun damage | Strafer duel: 48 shots instead of 45. **Done: 2.90 (+0.36), new best.** |
| B2 | `fight.blind_fire` | Fire back along the exact damage bearing at attackers we can't see (foliage blocks sight, not bullets). Distance from a traced-back incoming bullet, else gunshot sound band, else 60 m; never into a wall | Duel screen (geometric hits): won 37/40 vs 23/40, damage ratio 1.67 vs 0.81. **Done: 2.40 (−0.50), off.** |
| B3 | `fight.focus` | Target choice by kill potential: lowest effective HP (HP ÷ our damage rate), finish wounded targets, stay on one target | 6 unit tests; `best` stays action-identical to `8c5820c`; audit clean. **Done: 2.63 (−0.22), off.** |
| B3b | `fight.strafe` | Strafe sideways in fights with safeguards (walls, zone, exposure to other hunters, short jinks near cover, no hops) | Duel with real leading enemy bullets: won 31/40 vs 18/40; 9 unit tests; `focus` stays action-identical to `65744ad`. Stuck detection paused only while actually strafing (found and fixed before pushing). **Done: 2.88 (+0.03), tie; kept on by decision.** |
| B4 | `fight.spacing` | Keep the distance where we win: >50 m from lightning carriers, cover against lasers, close in on mortar carriers | Duel sim per enemy weapon |
| B5 | `fight.disengage` | Break off fights we're losing (HP race estimate: their damage rate vs ours) | Duel sim |

Interaction re-test after the timing fix (a stronger gun changes fight economics): `near90` (engage within 90 m), pending. The other eliminated options lost for reasons the fix doesn't touch: early retreat with held fire gives up even more with a stronger gun; roofs failed for reasons unrelated to our damage; the upgrade order waits for cube collection (Stage C).

**Stage B summary:** one real win (trigger timing, 2.90); since then ties or losses (shootability
−0.05, focus −0.22, strafing +0.03). Diminishing returns from fight details, so B4/B5 are deferred.

**Next:** Stage C: C3 `farm.cubes` (collect kill drops and other cubes), C2 `farm.drones`, then
re-test the upgrade order now that offers arrive. B4 `fight.spacing` and B5 `fight.disengage` later
if time allows.

### Stage C: E3, cubes and HP pool (crucial; both modes)

Each cube: +4% max HP and +4% damage (up to 10), plus upgrade offers (run 1b showed upgrades are
neutral today because we rarely get any).

| Run | Switch | What it does |
| :--- | :--- | :--- |
| C1 | `farm.crates` | Shoot and collect crates (1 cube, 50% weapon drop) when no hunter is within ~120 m. **Built:** 10 tests incl. end-to-end; `best` unchanged vs `11c2b69`; activates in the recorded match only while safe. **Done: 3.00 (+0.12), new best, kept.** |
| C3 | `farm.cubes` | Walk over cubes dropped by our kills (all their cubes + 2) and floor cubes when safe. **Built:** tests in `test_farm.py`. **Done: 3.38 (+0.38), new best, kept.** |
| C2 | `farm.drones` | Kill isolated drones (2 cubes each), only at full HP and with no hunter nearby |

Then: **re-test the upgrade order** (run U1 pending: `upgrade_first` on the 3.38 baseline): it only matters once we get offers.

### Stage D: E6, mode detection + free-for-all settings (crucial for qualifiers)

Practice can't reward this, but the finals depend on it.

- Mode detection: `alive` dropping without one of our `kill` events means others are dying, so it
  is a free-for-all. Guard against zone deaths: require such a drop outside the last two zone
  phases, or two such drops.
- A free-for-all overlay in `tuning.py`, applied once detected: early retreat with hold fire
  (E1's settings), opportunistic engagement only, no long-range fights.
- Offline: unit tests with synthetic observation streams (practice-like vs free-for-all-like).
- **One practice run** as a regression check: the score must not drop (detection must never
  trigger in practice).

### Stage E: E4, the end of the match (crucial once we survive longer)

Worth up to 15 points per match, but only if we are alive at ~6:55.

| Run | What | Decides |
| :--- | :--- | :--- |
| P1 (probe) | A "pacifist" preset: never shoot, always hide | Does anyone die without us killing them (zone deaths, the final burn)? A score above 0 means yes, which tells us how much E4 is worth |
| Z1 | `burn.enabled`: from the second-to-last circle, be at full HP at the final centre, last one outside | The value of end-game positioning |
| Z2 | Late-match healing (retreat thresholds after ~5:30) | Interaction with the burn |

### Stage F: re-tests and options (useful)

- Retreat × E2 2 × 2, only if the B1 re-test is ambiguous.
- E5 supply drops (`drops.enabled`): contest only when no hunter is within ~80 m. 1 run.
- Roofs: re-test only if E2's cover logic makes a specific roof variant look promising.

### Stage G: tuning sweeps (small gains; last)

Three values each for the settings that mattered, one run per value. Expect about 2–3 runs per
setting:
- `engage.near_m`: 90 tested in `near90`; then 40 (and 30 if 40 wins), or 120 if 90 wins
- `retreat.hp_enter` (0.25 / 0.35 / 0.45)
- `retreat.hp_exit` (0.7 / 0.8 / 0.9)
- `lightning.reserve` (10 / 20 / 30)
- the cover distances and spacing distances from E2

### Stage H: freeze for qualifiers

1. Test the top 2–3 complete combinations; keep the best as the final practice preset.
2. Check the free-for-all overlay once more by reasoning (no feedback available).
3. Robustness:
   - timing on 1 CPU with many mechs and projectiles in view;
   - memory;
   - crash safety: every module wrapped, and the bot keeps moving if one fails;
   - the sandboxed Docker check.
4. Tag the commit and make the final submission.

### Rough budget

| Stage | Runs | Main cost |
| :--- | :--- | :--- |
| A | 1 | – |
| B | 5 | Building E2 (largest piece) |
| C | 4 | Farming and target logic |
| D | 1 | Mode detection + overlay |
| E | 3 | Burn positioning |
| F | 1–3 | – |
| G | 6–10 | – |
| H | 3–4 | – |
| **Total** | **~25–30 runs** | ~7–8 hours of submission slots, spread across building time |

## Correctness audits

Bugs that misread the rules cost more than any tuning (the trigger-timing bug alone was worth
+0.36). Each audit:

1. **Hard-coded numbers:** search for values that must come from `hello.config` (speeds, ranges,
   heights, cooldowns). 2026-11-21: only `.get()` fallbacks; small simplifications remain (enemy
   eye/muzzle heights use base values, ignoring their cubes).
2. **Invariant audit over the recorded match** (`scratchpad/audit.py` style): no NaN/oversized
   moves, pitch within limits, no jumps or jets while airborne outside a planned climb, no `take`
   out of reach, no gun fired into a wall, no reload with a shootable target engaged, no engaging a
   hidden target while another eligible one is shootable. 2026-11-21: clean for all presets, but
   the recording only ever shows one other mech, so multi-enemy rules need synthetic tests.
3. **Code vs protocol, rule by rule.** 2026-11-21 findings:
   - trigger released while the cooldown ended inside the action window (fixed, run B0, +0.36);
   - target choice ignored line of sight with two enemies (fixed; pending run);
   - shots held when only the upper body was visible (fixed with the above).
4. **Review of new modules before pushing.** 2026-11-21, strafing: stuck detection was paused for
   the whole fight, so a real snag during a fight where strafing isn't possible would go unnoticed.
   Fixed before pushing: paused only after a decision where we actually strafed; stale flags cleared
   between fights and while airborne or climbing; covered by a test.
   Farming (C1): class-level shared state in `Farmer` (would leak between instances) and a
   too-conservative forgetting distance (25 m; protocol §8 makes anything within 45 m with no
   building in the way always visible). Both fixed before pushing; a cube at a crate's spot now also
   proves the crate is gone.

Repeat the audit after each new module, and add a synthetic test for every rule the recording
can't exercise.
