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
| Engage within 60 m / below 35% HP (Phase 3) | **60 m is best:** 40 m worse (3.31, G1), 90 m worse (3.23, G1b) | Reasonable | Close mechs are threats anyway; low-HP targets are cheap kills (cubes). Engaging less loses kills; engaging further starts fights the squad wins | 60 m / 35% | keep 60 m (no FFA kill incentive to widen it) |
| Lightning first, late mortar swap with laser check | Not tested separately | Same logic | Weapon triangle applies in both modes | as is | as is |
| Trigger timing fix (always on) | **Good** (2.90, +0.36) | Positive | Bug fix: up to ~20% more gun damage in every fight | on | on |
| Shootability fix (always on): prefer targets we can shoot; aim at the visible part | Tie (2.85 vs 2.90); kept for correctness and FFA | Positive | Bug fix: with two enemies, a hidden attacker blocked a clear shot at the other in 50/50 test cases; a low wall over the middle blocked shots at a visible upper body | on | on |
| Blind fire at unseen attackers (`fight.blind_fire`) | **Bad** (2.40, −0.50), despite the duel screen predicting 37/40 wins | Unknown, likely bad for the same reasons | Bearings can point at blasts or arc origins, guessed shots waste the magazine, and gunfire reveals us | off | off |
| Focus fire (`fight.focus`, B3) | **Bad** (2.63, −0.22) | Unknown, likely bad for the same reasons | Sticking to a hidden target and chasing far wounded ones costs time and HP | off | off |
| Strafing in fights (`fight.strafe`) | Tie (2.88 vs 2.85); duel predicted a large gain | Small positive at best | Only dodges gun bullets; lasers and lightning are instant | on (kept by decision despite the tie) | on (dodges gun fire, which matters vs gun-armed bots) |
| Crates and their cubes (`farm.crates`, C1) | **Good** (3.00, +0.12) | Positive | +4% max HP and damage per cube, upgrade offers; gated on safety, so it happens in quiet moments in both modes. Risk: gunfire and the crate breaking (heard 220 m) reveal us | on | on |
| All visible cubes / kill drops (`farm.cubes`, C3) | **Good** (3.38, +0.38) | Positive | Walking over dropped cubes makes zero gunfire sound (unlike crates which make 220 m noise and need shooting), gives instant HP healing (+4% max HP healed per cube), damage bonus, and faster upgrade offers; safe walks only | on | on |
| Isolated drones (`farm.drones`, C2) | Tie (3.38 vs 3.38) | Positive | Drones drop 2 cubes (+8% HP and damage) with minimal risk, but in practice safe opportunities are rare and gun sound can attract house bots. Kept off in best; candidate for FFA overlay | off | on |
| Supply drops (`drops.enabled`, E5) | **Good** (3.46 vs 3.38, +0.08, run B4). F1's 2.81 was invalid: a bug turned farming off whenever drops were on | Positive | Drops land at ~1:35, 2:45, 3:55, inside the window where we earn and die; each gives full HP, full energy and 3 cubes. Taken only when no hunter is within 80 m | on | on |
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
| `farm.drones` | false | C2: hunt isolated NPC drones (2 cubes each) when safe |
| `farm.drone_min_hp` / `dist_min` / `dist_max` | 0.90 / 30 / 50 | Drone farming safety: HP ≥ 90%, stand-and-shoot 30–50 m |
| `farm.safe_m` / `min_hp` / `max_dist` | 120 / 0.6 / 80 | Farming safety: no hunter within, HP at least, how far to look |
| `mode.detect` | false | D1: detect practice vs free-for-all and apply FFA overlay |
| `burn.enabled` / `radius` | false / 25 | E4: final burn play (center hold in late circles when next radius ≤ 25 m or DPS ≥ 160) |
| `drops.enabled` / `safe_m` / `max_dist` | false / 80 / 150 | E5: contest safe supply drops (3 cubes + full HP heal) |

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
| 14 | `strafe` (run B-strafe) | `11c2b69` | 2.88 | Strafe sideways while fighting, on the 2.85 baseline (rebased off focus fire after B3 lost). Safeguards: walkable steps, zone margin, never more exposed to known hunters, short jinks near cover, no hops (stuck detection paused only after a decision where we actually strafed). Duel screen with real leading bullets: won 31/40 vs 18/40, damage taken −18%. **Scored 2.88 (+0.03): a tie.** Likely small because strafing only dodges gun bullets; lasers (instant) and lightning (auto-target) don't care, and lasers were everywhere in the recorded match. Tie under our rule, but **kept on by decision** (points the right way; plausible mechanism). **New baseline: `best` = this, 2.88.** |
| 15 | `crates` (run C1) | `1f78964` | **3.00** | **New best** (+0.12 over 2.88, ~6 places). Shoot street-level crates and collect their cube, only when safe (no mech to fight, HP ≥ 60%, no hunter within 120 m, zone allows the detour); gun only, stand and shoot within 18 m, within 60 m max. Kept; now part of `best`. |
| 16 | `cubes` (run C3) | `48c2979` | **3.38** | **New best** (+0.38 over 3.00, ~18 places). Walk over any visible cube on the street (kill drops, floor spawns) when safe. Big win: collecting cubes is completely silent (no gunfire or crate destruction sound heard up to 220 m to attract hunters), grants instant HP healing (+4% max HP healed per cube), scales damage, and accelerates upgrade thresholds early. Kept; now part of `best`. |
| 17 | `upgrade_first` (run U1) | `4679dea` | 3.35 | Always take choice 0 on the 3.38 baseline: 3.35 vs 3.38 (−0.03, effectively a tie). Confirms the ranked upgrade picker (`nanites` → `plating` → `armor`) has a slight edge (+0.03, ~2 places) over random choice 0, but defensive upgrades alone don't drastically alter squad focus fights. Kept `ranked` in `best`. Baseline remains **3.38**. |
| 18 | `drones` (run C2) | `b0f806d` | 3.38 | Hunt isolated NPC drones for 2 cubes each on the 3.38 baseline: 3.38 vs 3.38 (exact tie). Drones are scarce (12 on map), safe conditions (HP ≥ 90%, no hunters ≤ 120 m) rarely arise in practice, and gun noise can alert nearby house bots. Under our rule (need ≥ +0.05 to adopt), kept OFF in `best`. Baseline remains **3.38**. |
| 19 | `mode_detect` (run D1) | `2c8c63e` | 3.31 | Initial mode detection: 3.31 vs 3.38 (−0.07). Diagnosis: the broad zone radius check (`r > 70` m) allowed occasional mid-game squad zone deaths to be misclassified as unassisted combat deaths, latching into FFA mode with `retreat.hold_fire: True` and `retreat.on_hunters: True`. Against 15 hunters, holding fire caused the bot to die without fighting back. Fixed in D1b. |
| 20 | `mode_detect` (run D1b) | `c923e9b` | **3.38** | Hardened mode detection + safe FFA overlay: 3.38 vs 3.38 (exact match, zero regression on practice). Pre-shrink check (t < 60s) avoids false triggers on squad zone deaths, and 120s lock prevents late-game false triggers. Mode detection is now proven safe for practice while providing crucial survival adaptation in qualifiers/finals. Kept; incorporated into `best`. Baseline remains **3.38**. |
| 21 | `burn` (run Z1) | `9edce64` | 3.38 | Final burn positioning on the 3.38 baseline: 3.38 vs 3.38 (exact tie). In practice against the 15-bot squad, matches rarely reach the final 25 m collapse at ~6:55, so practice score is dominated by early/mid-game kills. Center holding and suppressed retreat are essential in FFA end-games where surviving the 260 DPS burn decides 1st place. Kept off in practice `best`; enabled in `FFA_OVERLAY`. Baseline remains **3.38**. |
| 22 | `drops` (run F1) | `5bfc603` | 2.81 | **Invalid (audit A1, 2026-11-22):** the drops branch in `bot.py` was an `elif` that skipped crate and cube farming whenever drops were enabled, so this run measured "no farming" (2.81 ≈ the 2.88 pre-farming score), not drops. Re-run as B4 (3.46). Original note: safe supply drop contesting on the 3.38 baseline: 2.81 vs 3.38 (−0.57). Capturing an 8 m drop ring on open ground inside the closing circle pulls the bot into central crossfire where the 15-bot squad concentrates, leading to fatal focus-fire. Kept OFF in `best`. Retained in `FFA_OVERLAY` where enemy mechs scatter and +3 cubes + full HP heal is valuable in quiet pockets. Baseline remains **3.38**. |
| 23 | `near40` (run G1) | `fcda789` | 3.31 | Tighter engagement distance (40 m vs 60 m) on the 3.38 baseline: worse (−0.07, ~3 places). Fewer engagements mean fewer kills, and kills are practice points. Together with run 1d (any range, 2.02) this brackets the best value at 60 m or a bit above. Keep 60 m; next try 90 m (G1b). |
| 24 | `near90` (run G1b) | `f114606` | 3.23 | Wider engagement distance (90 m vs 60 m) on the 3.38 baseline (`near90` rebased on `best`): worse (−0.15, ~7 places). Longer-range fights against a squad that shares vision cost more than the extra kills earn (same lesson as run 1d). With G1 (40 m, −0.07) this confirms **60 m** as the best value; the sweep on `engage.near_m` is closed. |
| 25 | `farm_safe80` (run G5) | `b0c4e78` | 3.35 | Farm with hunters closer (no known hunter within 80 m, was 120 m): −0.03, a tie. Kept 120 m. Stage G fine-tuning stopped here: the top-32 cut is ~6.0, so hundredths don't matter. |
| 26 | `center` (run B1) | `8cd5b4b` | 2.19 | Hold the next zone centre all match (burn mode from t = 0): much worse (−1.19). Confounded: burn mode also turns off farming (~−0.50), retreat (~−0.23), pickups, laser dodging and strafing, and stands still in the open. Even so, the zone only kills house bots at the final burn, which we never reach. Dropped. |
| 27 | `probe_idle120` (run B2, diagnostic) | `c864020` | 1.25 | `best` until 2:00, then stand still and hold fire. Score ≈ points earned by 2:00. |
| 28 | `probe_idle240` (run B3, diagnostic) | `ab5255b` | 3.15 | `best` until 4:00, then idle. Points by 4:00. See "Where our points come from" below. |
| 29 | `drops` (run B4, with fix A1) | `6143491` | **3.46** | **New best** (+0.08). First valid drops test. Drops land in the 1:35–3:55 window where we earn and die; full HP + 3 cubes each. Now part of `best`. |
| 30 | `late180` (run C1) | `23ed45e` | 3.42 | `best` (with drops) + more cautious retreat from 3:00 (retreat on 3+ hunters within 100 m or >20% HP lost in 2 s, enter 50% / exit 90%, keep shooting back): −0.04, a tie. Time-based caution isn't the lever. Not kept. |
| 31 | `pacing` (run C2) | `c8322c6` | 3.46 | `best` + `fight.pacing` (loot a kill's cubes; split ganging hunters): an exact tie. Probe C2a showed the loot rule does fire, so the tie was the two rules cancelling, or chance. |
| 32 | `probe_loot` (run C2a, diagnostic) | `bce0bea` | 1.60 | `pacing`, standing still from the first loot. Far below 3.46, so loot fires early and often in practice. (In the offline squad simulator: 0.95.) |
| 33 | `pacing_loot` (run C2c) | `bf30d0b` | **3.48** | `best` + loot only (`pacing.split` off): +0.02, a tie under the rule, but the highest score so far with a plausible mechanism (kill cubes heal 4% each and add damage just before the next hunters arrive). **Kept by decision; now part of `best`.** Split stays off. |
| 34 | `farm_reach120` (run C3) | `ae40d37` | **3.88** | `best` (3.48) + crates and cubes up to 120 m away (was 80 m). **First score under scorer builders-4** (96 fresh random seeds per run, see below), so not directly comparable with the fixed-seed scores above. Kept (highest score; more cubes is a sound mechanism); now part of `best`. |
| 35 | `arm` (run D1) | `442dfb9` | **4.05** | `best` + arm up early: remember every weapon pickup seen and, while slot 1 is empty and no hunter is within 50 m, walk to the nearest street-level lightning up to 200 m away. Lightning does 240 damage/s within 45 m with no aiming (the gun sustains ~100/s), and combat only took a lightning visible within 40 m: in the recorded match four were seen at 81-196 m and slot 1 stayed empty. Squad simulator: armed in 31/40 matches at ~29 s (vs 24/40 at ~70 s). **4.05, highest so far** (+0.17 over C3, within the ±0.3 noise, but a sound mechanism the simulator confirms). Kept; now part of `best`; picked as final entry. |
| 36 | `press` (run D2) | `98bb86a` | **4.19** | `best` (4.05) + `fight.press`: holding lightning with energy ≥ 35 and HP ≥ 50%, and with exactly one fresh hunter 32-90 m away, step in to 25 m so lightning (45 m range) reaches it. Squad simulator: 4.75 vs 4.00, lightning damage 2,594 vs 1,601 per match; but the simulator's house bots carry only a gun, so stepping into their lightning range isn't modelled.. **4.19, highest so far** (+0.14 over D1, within noise; the feared punishment by house-bot lightning didn't show). Kept; now part of `best`. |
| 36b | `press` + FFA/zone fixes | `8b5a7d5` | **4.30** | D2 plus mode detection catching gun fights between others and arm-up waiting for an urgent zone (no intended practice change). **Highest so far; picked as the final entry.** |
| 37 | `laser` (run D3) | `f0918d6` | **4.46** | `best` (4.19) + laser fallback: from 45 s, with no lightning within reach, take the nearest street-level laser (swap it for a lightning later when one is in reach). Includes a **laser aim fix**: `laser_trigger` released on the *gun's lead* solution (at 60 m vs a 10 m/s target that's ~2.4 m off, about the target's radius); a beam is instant, so once charged it now aims straight at the target and releases when the torso is within its width. Squad simulator: laser taken in 8/60 matches, 106/133 beams hit, points 5.13 vs 4.75 (its bots don't dodge charging lasers).. **4.46, highest so far** (+0.16 over 4.30: a tie on score alone, kept for the sound mechanism). Now part of `best`; picked as final entry. |
| 38 | `hunt` (run D4) | `f1e9cab` | **4.59** | `best` + `fight.hunt`: holding lightning, HP ≥ 70% and energy ≥ 50, when the only mech we know of is 32–250 m away, go to within 25 m of it (the early squad sends one bot at a time). Simulator can't judge it (its bots walk straight at us): 4.83 vs 4.82.. **4.59, highest so far** (+0.13, a tie on its own, but the fifth rise in a row since 3.88: the cumulative gains are real). Kept in practice; **off in free-for-all** (`FFA_OVERLAY`): looking for fights is wrong when outliving others scores. |
| 39 | `drops_bold` (run D5) | `c04de5f` | 4.36 | `best` + `drops.max_threats` 1: contest a supply drop with up to one known mech within 80 m, fighting it if needed. Simulator can't judge it (we rarely live to the drops there): 4.85 vs 4.82.. **4.36: −0.23, a tie leaning negative.** Off (simpler bot wins ties). Likely: 4 s on open ground under fire costs more than the heal returns, a second mech freezes the capture, and we often die before the 2nd drop. After five rises, this also suggests 4.59 was partly luck: the bot's level is ~4.4–4.5. |
| 40 | `best` (final candidate) | – | pending | `best` = the 4.59 bot (hunt on in practice) with the free-for-all guard (`FFA_OVERLAY` forces `fight.hunt` off and `drops.max_threats` 0); bold drops off. The intended qualifier entry. |
| 41 | `fortress` (idea E1, not run) | – | – | `best` + from 3:30 hold the best reachable roof inside the next circle (peek the edge above 60% HP), to live to the final burn. **Rejected offline:** with the simulator's squad held back so we live past 3:30, it climbs a roof in 9/10 matches but scores 4.07 vs `best` 4.83, and neither reaches 6:40 (0/30). A 9 m mech on a roof is a skyline target for distant hunters (the roof only hides us from bots right below), and it gives up covered street spots. Matches run 2's 2.23. Code kept (`roof.after`), off. |
| 42 | `rush` (run E2) | – | pending | `best` + for the first 100 s farm crates and cubes up to 250 m away (was 120 m) with hunters as close as 60 m (was 120 m): more cubes before the escalation. Practice only. The simulator has no crates, so it can't judge this. |
| 44 | `rush_drones` (run E4) | `68f83fd` | **4.67** | `best` + for the first 120 s: the rush (farm up to 250 m, hunters >= 60 m) **and** hunt NPC drones (2 cubes each) down to 60% HP. Drone farming (C2) never triggered before (it needed 90% HP and no mech within 90 m; reach was 80 m); the early phase is when those conditions hold. Squad simulator (now with crates and drones): drones killed 1.15 vs 0.62, cubes 11.5 vs 9.4, points 5.52 vs 5.05.. **4.67, highest so far** (+0.08, a tie on its own; kept for the sound mechanism, about +2 cubes before the escalation). Now part of `best`; picked as final entry. |
| 43 | `loot_more` (run E3) | – | pending | `best` (4.67) + `pacing.loot_more`: loot the cubes of **every** kill in the last 30 s (the old rule only remembered the last kill, for 15 s), and take kill cubes within 30 m **even while retreating**, at any HP and hunter count (running doesn't heal once the squad has found us; each cube heals 4% and adds 4% damage). From visualizer replays: the bot fled from drops at low HP and abandoned the first of two kills' cubes. Simulator (crates and drones): cubes 13.1 vs 11.5. |
| — | (fix) | – | – | `tuning.py` had a dead duplicate `PRESETS` block from commit `34d659d` (an editing slip). Python used the second (live) block, so E2/E4 ran as intended; removed, all 45 presets verified identical. |
| — | simulator realism | – | – | `tests/squad.py`: crates (36, roof ones left out), the 12 NPC drones, and house-bot **second weapons** by tier (25/50/75/100% from easy to expert; lightning auto-hits within 45 m, laser 0.75 s visible charge then 315, mortar an occasional heavy hit). Scores drop to ~3.9–4.0, near practice. The visualizer now draws crates and drones. |
| — | S2 `lull` (not run) | – | – | Heal in lulls: below 75% HP with no hunter within 100 m, stop at a hidden spot and regenerate to 95%. Simulator: 3.70 vs 3.90 (loses farming/loot time: cubes 7.9 vs 8.7; death time unchanged). Off. |
| — | S1 `many2` (not run) | – | – | Back off (still shooting) with 2 hunters within 100 m below 70% HP. Simulator: 3.77 vs 3.90 (lives 3 s longer, kills less). Off. Same lesson as hiding (1.52) and late caution (C1): caution costs more kills than it saves. |
| 45 | `package` (run F1) | `a445c87` | **4.72** | `loot_more` (E3) + three survival-in-fights changes, run together for time: **durable upgrades** (plating ×3, armor ×3, gun / lightning damage, nanites last; simulator with upgrades modelled: 4.13 vs 4.05), **anti-centroid retreat** (hide spots only on the far side from the hunters' centre) and **line-of-sight steering** (with 2+ hunters, step ~7 m to where the fewest can see us). Simulator, 30 matches: away+los 3.60 vs 3.43, time under 2+ attackers 6.8 vs 7.7 s.. **4.72, highest so far; picked as final entry.** |
| — | `pkg_scaled` (not run) | – | – | `package` + retreat at 50% HP with 2 hunters within 75 m, 65% with 3+. Simulator, 30 matches: 3.43 vs 3.53 (more retreating, dies earlier). Off: the fourth time caution against 2–3 bots costs more kills than it saves (C1, S1, S2). |
| 46 | `pkg_hunt` (run F2) | `adfc6cd` | 4.46 | `package` (4.72) + `hunt.local`: hunt the nearest known mech when every other one is at least max(100 m, nearest + 60 m) away (hunt used to need exactly one known mech anywhere). Simulator: 3.53 vs 3.53 (its bots walk straight at us, so hunting can't show there).. **4.46: −0.26, a tie leaning negative.** Off; `a445c87` (4.72) stays the final entry. |
| — | `pkg_choke` (not run) | – | – | `package` + chokepoint: with 2+ known hunters within 150 m, fight from the spot within 20 m with the fewest open approach lanes (16 directions, a bot 50 m out could shoot it; cached per 2 m cell) and the fewest current hunters able to shoot it. Simulator: seeds 1–30 3.83 vs 3.53, seeds 31–60 4.47 vs 4.80, **all 60: 4.15 vs 4.17, a tie**. Holding a spot costs farming / looting (cubes 10.1 vs 11.6) and replaces the line-of-sight steering, which already captures most of the gain. Off. |
| — | `pkg_laser1` (not run) | – | – | Alpha-strike check: a laser in slot 1 instead of lightning. Simulator (its bots don't even dodge): **2.80 vs 3.53**. Lightning's 240/s with no aiming is worth far more in our close 2–3 vs 1 fights than a 315 opener every 2.4 s. Dropping the gun for a laser would also lose crate farming. Off. |
| 47 | `pkg_fallback` (run F3) | `5294e5c` | 4.59 | `package` (4.72) + `retreat.fallback`. Found while checking retreat: **71% of hide-spot searches find no fully hidden spot**, and then the retreat goal fell back to standing still (or a stale spot). Now it flees to the best partial cover within 38 m: fewest current hunters able to shoot it, fewest open approach lanes (the chokepoint idea, cached per 2 m cell), preferring the far side from the hunters, and only if better than staying. Simulator: seeds 1–30 3.83 vs 3.53, seeds 31–60 4.87 vs 4.80, **all 60: 4.35 vs 4.17**, lives longer.. **4.59: −0.13, a tie.** Practice didn't confirm the simulator's +0.18; kept off. Final entry stays `a445c87` (4.72). |
| — | diagnostics | – | – | Simulator on the final bot: 22% of damage taken hits our back (x1.5); lightning is short of energy only 3% of the time in close fights (after modelling the 0.6 s regen delay); **lightning held fire ~9 times per match because a different enemy mech was nearer in its cone**. |
| — | `pkg_anymech` (run H1) | – | not run | `package` + `lightning.any_mech`: fire even when another **enemy mech** is nearest in the cone (it takes the arc; crates and drones still block). Simulator, 60 matches: lightning damage 2,290 vs 2,169 (+6%), blocks 1.8 vs 9.3 per match, points 4.25 vs 4.18. A pure damage fix in the 2-3 vs 1 fights, no trade-off. |
| 49 | `pkg_h1_fb` (run H2) | `5d33ad0` | 4.60 | The final entry (`package`, 4.72) + two fixes for flaws found offline: `lightning.any_mech` (lightning held fire when another enemy was nearer in its cone) and `retreat.fallback` (71% of retreats found no hidden spot and stood still). Simulator, 60 matches: **4.38** vs 4.25 (H1 alone) vs 4.18 (final entry); lightning damage 2,434 vs 2,169.. **4.60: −0.12, a tie leaning negative.** Off; `a445c87` (4.72) stays the final entry. |
| 50 | `h2_roof_scaled` (run R3, requested) | `f2f537a` | 4.55 | H2 + **rooftop retreat** (`retreat.roof`: when retreating with energy >= 45 and a climbable roof within 45 m, go to its middle) + **scaled retreat** (50% with 2 hunters within 75 m, 65% with 3+). Simulator, 60 matches: 4.32 vs H2 4.38 (rooftop retreat alone: 4.17). Its bots can't climb, which flatters the roof. Run once at the team's request.. **4.55: −0.17, a tie leaning negative.** Off; `a445c87` (4.72) stays the final entry. |
| 51 | `h2_mpc` (run M1) | `cfd3437` | **4.78** | H2 + `fight.mpc`: with 2+ hunters close, roll 12 manoeuvres + "stay" forward 1.2 s (enemies advance along their velocity), score each by predicted damage dealt − 1.2 × damage taken (line of fire via `shot_los`, real weapon numbers incl. lightning range), replan every 0.3 s. Replaces line-of-sight steering when active. Simulator: seeds 1–60 **4.72 vs 4.38**, seeds 61–90 **4.10 vs 3.87**; lightning damage +14%, lives longer. Decisions p99 2.7 ms, p99.9 17.8 ms (profiled; spikes are pathfinding with 0 mechs in view).. **4.78, highest so far; picked as final entry** (+0.06 over 4.72: a tie on its own, chosen for the consistent simulator gain and the two flaw fixes it carries). |
| — | `pkg_arc`, `pkg_finish` (not run) | – | – | Front-arc-aware targeting (keep other attackers in front) and finish-the-wounded-first: both identical to H1 in the simulator (target choice already leans that way; rear damage stays 20%). Off. |

## Batch 1 (done)

| Run | Preset | Question |
| :--- | :--- | :--- |
| 1a | `p3` | Noise: does the same behaviour score 2.33 again? (Verified offline: `p3` gives action-for-action the same output as commit `956e3b7` on the recorded match.) |
| 1b | `p3_picker` | Does the ranked upgrade picker help on its own? |
| 1c | `picker_lastresort` | Retreat only below 35% HP, keep shooting back, no hunter/damage triggers |
| 1d | `picker_aggressive` | Shoot any visible mech in range (score = kills in practice). Rebased on the 2.54 baseline after run 1c. |

## Master plan (decided 2026-11-21; replaces the earlier roadmap)

**Update 2026-11-22:** best is **3.48** (run C2c: + loot a kill's cubes; before that 3.46, run B4: `best` +
supply drops after audit fix A1). Offline squad simulator: `tests/squad.py` (bug finding only, not a
score predictor). The
leaderboard has 347 teams; the top 5 score 6.38–6.58 and the top-32 cut is ~6.0, so tuning sweeps
are stopped. Practice house bots are 4 easy, 4 medium, 4 hard and 3 expert (track page). See
"Batch B: where our points come from" below.

**Where we stood on 2026-11-21:** best score **3.38** (run C3). `best` = last-resort retreat + strafing + crate
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
| C2 | `farm.drones` | Hunt isolated drones (2 cubes each) when safe (HP ≥ 90%, no hunter ≤ 120 m, stand-and-shoot at 30–50 m with gun only). **Done: 3.38 (+0.00, tie). Kept off in best.** |

Stage C complete! Best score remains **3.38** (run C3). Next: Stage D (mode detection E6 + free-for-all overlay).

### Stage D: E6, mode detection + free-for-all settings (crucial for qualifiers)

Practice can't reward this directly, but the finals depend on it.

- Mode detection: `alive` dropping without one of our `kill` events means others are dying, so it
  is a free-for-all.
  - Guard against zone deaths: only check before zone shrink begins (`t < shrink_start = 60s`, where
    the 560 m circle covers the entire map and zero zone damage can occur) or require ≥2 unassisted
    deaths before 120s.
  - After 120s (2 minutes), mode permanently locks to `practice` so mid/late-game squad zone deaths
    never trigger FFA.
- A free-for-all overlay in `tuning.py`, applied once detected: early retreat (`hp_enter: 0.50`,
  `hp_exit: 0.80`), keep shooting back (`hold_fire: False`, `on_hunters: False`), opportunistic
  engagement only (60 m), safe cube, crate, and drone farming.
- Built & verified with unit tests in `tests/test_mode.py`.
- **Run D1b (`mode_detect`)**: practice regression check. **Done: 3.38 (exact match, zero regression). Kept in `best`.**

Stage D complete! Mode detection and the FFA overlay are now armed and part of `best`. Baseline remains **3.38**. Next: Stage E (end of match / final burn E4).

### Stage E: E4, the end of the match (crucial once we survive longer)

Worth up to 15 points per match, but only if we are alive at ~6:55.

| Run | What | Decides |
| :--- | :--- | :--- |
| P1 (probe) | A "pacifist" preset: never shoot, always hide | **Skipped:** Run E1 already proved hiding without shooting against the squad yields ~1.52. |
| Z1 | `burn.enabled`: from the second-to-last circle, navigate to and hold the final circle center, last one outside | Center holding + full weapon fire in the final collapse. **Done: 3.38 (tie). Kept in FFA overlay.** |
| Z2 | Late-match healing (retreat thresholds after ~5:30) | Interaction with the burn |

### Stage F: re-tests and options (useful)

- Retreat × E2 2 × 2, only if the B1 re-test is ambiguous.
- E5 supply drops (`drops.enabled`): contest only when no hunter is within ~80 m. **Done: Run F1 scored 2.81 (−0.57 vs 3.38). Kept OFF in `best`, retained in `FFA_OVERLAY`. Baseline remains 3.38.**
- Roofs: re-test only if E2's cover logic makes a specific roof variant look promising.

Stage F complete! Best score remains **3.38**. Next: Stage G (tuning sweeps on `best`: engagement distance, retreat thresholds).

### Final stretch (decided 2026-11-22 ~2:30 AM EST; cutoff 11:00 AM EST)

**Final entry now:** `f0918d6` (4.46; was `8b5a7d5`, 4.30). Every later run builds on it (it is an ancestor), so any
later winner also carries its free-for-all and zone fixes.

Each run is the current winner + one switch. Noise is ~±0.3 per run, so:
- **Keep** a switch if the run scores ≥ the current best + ~0.3 *and* the mechanism is sound; then
  pick that commit as the final entry.
- **Tie** (within ~0.3): keep the simpler bot (switch off) unless the mechanism is strong and the
  score is at least as high.
- **Clearly lower** (≥ 0.4 below): switch off for good.

| Step | Run | Switch | Status |
| :--- | :--- | :--- | :--- |
| 1 | D3 `laser` | `arm.laser_after` 45 (+ laser aim fix) | **4.46, kept; final entry `f0918d6`** |
| 2 | D4 `hunt` | `fight.hunt` | **4.59, kept (practice only)** |
| 3 | D5 `drops_bold` | `drops.max_threats` 1 (practice only) | 4.36, off |
| 3b | final candidate `best` | — | submitted |
| 4 | freeze, last ~1.5 h (from ~9:30 AM EST) | — | final pick = best-scoring commit at or after `8b5a7d5`; rerun tests, check.py, Docker check; confirm the pick on the track page; no new features |

### Scorer builders-4 (from Sun 1:00 AM, 2026-11-22)

Every practice run now plays **96 fresh private random seeds** (was 48 fixed seeds), and identical
code keeps its first builders-4 score. Consequences:

- A run's score is noisy: roughly ±0.3 for one run, so a difference between two runs needs about
  **0.5** to mean anything. The +0.05 rule is retired; only large, well-reasoned changes are worth a
  submission.
- Probes that relied on identical matches (idle-at-T, idle-on-first-rule) no longer work.
- Don't resubmit trivial variants to draw luckier seeds (against the organisers' intent).

### Batch B (2026-11-22): where our points come from

No replays or logs come back from practice, so the score is the only channel. Matches are
deterministic on the fixed seeds, so a probe that changes behaviour only after time T reads out what
happens after T. Probes play `best` until T, then stand still and hold fire (`probe.idle_at`).

| Window | Points | Source |
| :--- | :--- | :--- |
| 0:00–2:00 | 1.25 | B2 |
| 2:00–4:00 | 1.90 | B3 − B2 |
| 4:00–5:25 | 0.23 | 3.38 − B3 |
| after 5:25 | 0 | Z1 tied exactly; burn play starts at ~5:25 |

Reading, with the squad rules ("one early, more as you thin them out, all of them late"): about one
kill against the lone easy bot by 2:00, then our best earning rate (~1 point/min) during the
escalation, then death around 3:00–4:30 when several hunters are on us. Living longer in that window
is the lever (each extra minute ≈ +1 point); hiding alone earns nothing in practice because house
bots die only to us or the zone (and the zone kills them only at the final burn, ~6:55).

### Stage G: tuning sweeps (small gains; last)

Three values each for the settings that mattered, one run per value. Expect about 2–3 runs per
setting:
- `engage.near_m`: **done, 60 m confirmed.** G1 `near40` 3.31 (−0.07), G1b `near90` 3.23 (−0.15).
- G5 `farm_safe80`: 3.35, a tie. **Stage G stopped** (see Batch B): G6/G7 presets kept, not run.
- Farming gates (cube collection was the largest single gain, +0.38, and its gates are untuned):
  `farm_safe80` (`farm.safe_m` 120 → 80), `farm_reach120` (`farm.max_dist` 80 → 120),
  `farm_hp45` (`farm.min_hp` 0.6 → 0.45)
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

5. **Audit of the 2026-11-21/22 commits (drones, mode detection, burn, drops), 2026-11-22:**
   - A1 (critical): the drops branch skipped farming whenever drops were enabled. That invalidated F1 and
     turned farming off in the free-for-all overlay. Fixed; `drops` is now action-identical to `best`
     before the first drop.
   - A2: mode detection locked to practice at 2:00. It now also switches on two laser beams from one mech
     ending on another mech far from us, at any time.
   - A3: the farmed drone's position was frozen at first sight. Fixed.
   - A4: withdrawn, not a bug. `threat` comes from `laser_threat`, which only returns a mech charging a
     laser, so the `kind == "mech"` check only stops lightning at an attacking NPC drone (saves energy).
6. **Review of outside suggestions, 2026-11-22:**
   - Mode detection (passive free-for-all lobbies): the laser-beam signal (A2) misses gun fights, so
     mode.py also counts a visible mech, more than 30 m from us and inside the zone, losing at least 35 HP
     between consecutive sightings that we didn't deal (no `hit` from us within 1.5 s) with no NPC drone
     within 60 m. Three such observations switch to free-for-all, at any time. Squad simulator: never fires
     (40 matches). Rejected: "enemies aiming at each other" and "fire not aimed at us" (both happen in
     practice: lines of fire through squad mates, house bots shooting drones).
   - Zone: the weapon-pickup branch (including arm-up) now waits while the zone is urgent, like the others.
   - Not done: relaxing the 120 m farming block (loot already takes kill cubes near hunters; G5's 80 m
     was a tie) and pathing retreats through heals (4% per cube vs 45 HP/s regen; not measurable now).
7. **Decision timing, 2026-11-22** (squad simulator, 40 matches, plus crowded-view stress test): p99
   0.7 ms, max ~19 ms locally; 15 extra mechs in view cost ~2 ms. The rare spikes are pathfinding
   (max ~18 ms); hide search and GC stay under 7 ms. The 1-CPU container is ~2.7x slower (check.py
   p50 0.9 vs 2.5 ms), so about one late decision per match at worst (a 0.1 s coast). No change made.

Repeat the audit after each new module, and add a synthetic test for every rule the recording
can't exercise.

| — | `mpc_bank` (built, not run) | – | – | Medkit bank (`farm.bank`): at >= 95% HP leave floor and kill cubes on the floor; below 70% HP walk over a remembered cube within 25 m (also while retreating). Simulator, 60 matches: **3.88 vs M1 4.72**, lightning damage −16%: kills happen at high HP, so their cubes (+4% damage each) were left behind exactly when needed. Off. |
| — | MPC upgrades (simulator, 60 matches each, vs M1 4.72) | – | – | `mpc.chase` (predict enemies closing on us instead of drifting along their velocity): 4.77; `mpc.min_hunters` 1 (MPC also with one hunter): 4.70, off; `mpc.retreat` (while retreating, the escape move with the least predicted damage, damage taken weighted 3x): 4.77, damage taken −4%. |
| 52 | `mpc2` (run M2) | `dfcbd23` | **4.82** | M1 (4.78) + `mpc.chase` + `mpc.retreat`. Simulator, 60 matches: **4.97 vs 4.72**; lightning damage 2,976 vs 2,786, damage taken 2,582 vs 2,698.. **4.82, highest so far; picked as final entry** (+0.04 over M1, a tie on its own; sound mechanism, simulator +0.25). |
| — | `mpc3` (built, not run) | – | – | M2 + `mpc.tier`: weight each enemy's predicted damage by its likely tier from aggro order (0.4 / 0.8 / 1.2 / 1.6 for bots 1-4 / 5-8 / 9-12 / 13-15). Simulator, 60 matches: **4.68 vs M2 4.97**, although its squad really is released easy to expert. Down-weighting early bots lets them keep shooting us. Off. |
| — | wave-pausing (reasoned out) | – | – | Leave a bot at ~15% alive until ready. A wounded bot still shoots at full strength, regen needs 5 s without damage, the kill's cubes are what make us ready, and "all of them late" is time-based. Same family as delay farming / heal in lulls, which lost. |
| 53 | `narrow2` (run N1) | `8254fa0` | **4.91** | M2 (4.82) + `fight.narrow` after 2 kills (team observation: after a few kills the bot stood on open ground and got surrounded by 3). From then on the default place to stand is the spot within 60 m (well inside the next circle) with the fewest open approach lanes (16 directions, a bot 50 m out could shoot it; cached per 2 m cell), re-picked every 8 s or when the zone moves; looting / pressing / MPC still act in fights. Simulator, 60 matches: after 1 kill 4.75, **after 2 kills 5.18**, after 3 kills 5.07, M2 4.97; lightning damage +7%.. **4.91, highest so far; picked as final entry.** |
