# Mech Royale Bot: Implementation Plan

Blueprint and roadmap for our `mechfight/1` battle royale bot. Every rule referenced here comes from `protocol.md`; every number must be read from `hello.config` at runtime (defaults are quoted only for reasoning).

---

## 1. Goal and Constraints

- **Objective:** maximize mean placement score (`16 - place`) over 48 practice matches. Outliving opponents beats killing them; kills matter only for the cubes they drop.
- **Timing:** 50 ms wall time per decision on 1 CPU core. Decisions arrive 10×/s (the sim runs 20 ticks/s; each action covers 2 ticks). Echo `tick` exactly. `ready` within 20 s of `hello` (includes container start).
- **Sandbox:** 512 MB RAM, read-only FS (`/tmp` 64 MB writable), uid 65534, no network, ≤128 processes/threads, map mounted at `/arena`.
- **Build:** linux/amd64, network on, ≤10 min, repo ≤20 MB, `Dockerfile` at repo top level.
- **Feedback loop:** `check/check.py` only checks conformance and timing; its observations do not react to our actions. **Practice-match submissions are the only real test of behaviour**, so we ship a minimal bot early and iterate from scores.

---

## 2. Decisions

| Topic | Decision | Rationale |
| :--- | :--- | :--- |
| **Stack** | Python 3.13 (protocol, strategy) + C++ `libmech_core.so` via `ctypes` (geometry, LOS, A*, steering, ballistics) | Keeps per-tick work to a few ms; Python keeps strategy easy to change. |
| **Scope** | MVP first, submit, then iterate | Practice matches are the only behavioural feedback, so get there fast. |
| **Playstyle** | Survival-first: farm safely, rotate early, regen often, finish weak targets late | Regen (45 HP/s after 5 s) refills 1400 HP in ~30 s, so breaking contact usually beats trading. |
| **Weapons** | Gun (slot 0) + Lightning (slot 1) baseline; counter-swap **only between fights** | See §5.3. Mid-fight swaps cost a walk to the pickup plus 1–1.65 s before the new weapon can fire. |
| **Drones** | Farm isolated NPC drones early | 12 drones × 2 cubes is the largest cube pool; each cube is +4% HP and damage (cap 10). |
| **Verticality** | Ground-only in MVP; opportunistic rooftops in a later iteration | Avoids a roof navigation layer and the energy cost of climbing until the base bot scores. |
| **Upgrades** | Score offers from their `effects` in `hello.config.upgrades`, not from a hard-coded id list | Balance changes between matches; scoring effects survives that. |

---

## 3. Architecture

```
 stdin (JSON lines) ──▶ mechfight.py (kit runner: parsing, queue skipping, flush)
                              │
                              ▼
                         bot.py  (tick coordinator, crash guard, timing)
          ┌──────────────┬───────┴────────┬──────────────────┐
          ▼              ▼                ▼                  ▼
     world.py       strategy.py       combat.py         navigation.py
   (obs → model,   (utility FSM,    (aim, fire gates,  (waypoints, steering,
    threat memory)  upgrades, loot)  weapon policy)     jumps, zone)
          └──────────────┴───────┬────────┴──────────────────┘
                                 ▼  ctypes (batched calls)
                      core/libmech_core.so  (C++)
     map model · vision LOS · shot LOS · A* · 16-dir steering · ballistics
```

### Files

```
Dockerfile            (top level, multi-stage: g++ build → python:3.13-slim runtime)
bot.py                entrypoint
mechfight.py          kit wrapper (unchanged)
world.py  strategy.py  combat.py  navigation.py  core_api.py (ctypes bindings)
core/mech_core.cpp  core/mech_core.h  core/Makefile
arena/                (copy of the map for local runs; /arena is mounted in matches)
```

---

## 4. C++ Core (`libmech_core.so`)

### 4.1 Map model (built at `hello`, target < 2 s)

- **Terrain:** `v2/terrain.i16`, little-endian int16 cm, `nx × ny` (1070 × 724), 1 m step, row-major from (`minX`, `minY`). Bilinear sampling.
- **Prisms:** `v2/world.json` `prisms[]` with `kind` (`building`, `stadium`, `bridge`), `base`, `top`, `ring`, `holes`. Store each as a polygon with holes plus a bounding box used **only** as a broad-phase reject. Point-in-prism = inside ring, outside every hole, `base ≤ z ≤ top`.
- **Trees:** parse `trees.fields` / `trees.data` (trunk radius, crown radius, crown base, height) and `rules.canopyDensity` / `canopyBlockT`.
- **Uniform grid acceleration:** bucket prisms and trees into a ~16 m 2D grid for raycasts.

### 4.2 Walkability grid

- 2 m cells over the terrain bounds. A cell is blocked if terrain slope > `max_slope_deg` or a prism with `base` < ground + 9 m covers it (bridges with clearance ≥ mech height stay walkable underneath).
- **Several clearance layers**, one per mech radius bucket (e.g. 2.5, 3.0, 3.5, 4.0 m), because radius grows 5% per cube with no cap. Pathing picks the layer matching our current radius from `self.stats`.
- Static **cover score** per cell: number of nearby directions blocked by prisms tall enough to hide a mech (used by A* and retreat target selection).
- MVP is ground-only: roof surfaces and bridge decks are not walkable nodes.

### 4.3 Line of sight (two different queries)

- **`vision_los(a, b)`:** blocked by prisms, terrain, tree trunks; attenuated by canopy (accumulate crown density, block past `canopyBlockT`). Used to predict what enemies can see and to choose hiding cells.
- **`shot_los(a, b)`:** blocked by prisms and terrain only. **Trees do not stop shots**, so we can fire blind into foliage at a sound.
- Ray vs prism: 2D segment vs polygon edges (ring and holes) within the `[base, top]` z-span, plus top/bottom cap intersections. Terrain: march the heightmap at 1 m.
- Endpoints come from live stats: our eye = `pos.z + self.stats.eye_height`, muzzle = `pos.z + self.stats.muzzle_height`. Enemy centre/top are estimated from their cube count (`size = 1 + size_per_cube × cubes`).

### 4.4 Pathfinding: `find_path`

- A* on the 2 m grid (8-connected, octile heuristic), on the clearance layer for our radius.
- Cost = distance × (1 + zone penalty + threat penalty − cover bonus).
  - Zone penalty: cells outside the circle the zone will be by our estimated arrival time.
  - Threat penalty: cells in range and `vision_los` of tracked threats (passed in as a batch each call).
- Path is returned as simplified waypoints (string-pulled using `shot_los`-free walkability checks).
- Budget: cap expansions; replan at most every 0.5 s or when the goal or threat set changes significantly.

### 4.5 Local steering: `solve_steering`

16 candidate directions scored by:
- alignment with the next waypoint (+)
- clearance from walls along a 3–5 m probe (+)
- staying inside the current and projected zone (+)
- distance from predicted mortar impact points (+, strongly)
- distance from NPC drone home areas when not farming (+)

Returns a unit move vector. Wall sliding is handled by the server; steering just avoids pressing into walls.

### 4.6 Ballistics

- **`solve_gun_lead`:** iterate intercept time `t = |target(t) − muzzle| / speed` (3–4 iterations) with target velocity from `obs.mechs[].vel`. Shot origin is 3 m out along the aim (`radius + 0.5`).
- **`solve_mortar_pitch`:** analytic solution of the projectile equation for `weapons.mortar.speed` and `gravity`; pick the low arc when there is a clear `shot_los`, else the high arc over cover. Clamp to `[min_pitch, max_pitch]`. Reject solutions where splash would reach us (self-damage 50%, and our blast throws us too).
- **`predict_shell_impact`:** for each visible enemy shell in `obs.projectiles` (`kind: "mortar"`), integrate under gravity to its terrain or prism hit point. Feeds steering.

---

## 5. Python Layer

### 5.1 `world.py`: world model

- Parses `obs` into typed state. Computes the **current interpolated zone** (linear between `shrink_start` and `shrink_end`) and time until the next shrink.
- **Threat memory:** for each mech id, store `(pos, vel, t_seen, confidence, weapons, cubes, hp)`. The server already keeps tracking seen mechs for `memory_s` (5 s); beyond that we extrapolate and decay confidence over ~10 s.
- **Sound threats:** each sound gives a noisy bearing (σ = `bearing_noise_deg`) and `near`/`mid`/`far`. Convert to a low-confidence threat at the band's midpoint and merge with known tracks along that bearing. The sound `kind` tells us the weapon held.
- **Damage events:** `damaged.by` + `bearing` refresh the attacker's track even when unseen; `rear: true` flags that we were facing the wrong way.
- **Drones:** track NPC home positions (first-seen position as an estimate) and which drones are currently aggroed on us.

### 5.2 `strategy.py`: utility state machine

States, each scored 0–1 every decision tick:

| State | Wants to run when | Does |
| :--- | :--- | :--- |
| `FARM` | early game, healthy, no mech threats near | Kill isolated drones and crates, collect cubes, grab lightning. |
| `ROTATE` | zone shrink is near or we are near the edge | A* to a covered cell inside the next circle, arriving early. |
| `ENGAGE` | target is weak, isolated, or rushing us; our HP is good | Fight at our preferred range; kite backwards along cover while firing. |
| `RETREAT` | HP low, outnumbered, or taking sustained damage | Break `vision_los` to all threats and stay unseen, not shooting, for `regen_delay` to start regen. |
| `HOLD` | nothing else scores high | Sit in a covered cell inside the zone, torso scanning likely threat directions. |

- **Hysteresis:** a state stays active for at least ~1.5 s unless a hard override fires (zone damage, HP below a critical floor, or incoming mortar).
- **Regen awareness:** regen needs 5 s with no damage taken **or dealt** and being in the zone. `RETREAT` therefore suppresses all firing, including lightning.
- **Endgame:** if the 8:00 clock is near, survivors are ranked by HP, so favour staying topped up over fighting.
- **Supply drops:** contest when we can reach the ring first and no other mech is tracked within ~60 m, or as a third party once two others are fighting over it. A capture gives 3 cubes, full HP and full energy.

### 5.3 `combat.py`: aiming and weapons

**Torso control (independent of legs):**
- Legs follow the navigation vector. The torso aims at the highest-priority threat.
- Rear armor: hits from outside the 180° front arc deal ×1.5. While fleeing, keep the attacker within ±90° of our aim yaw. Turn rate is limited (`turn_rate` 4 rad/s), so start turning early.
- When no threat is known, slowly sweep the torso to use the 120° vision wedge; the 45 m proximity sensors cover what is behind us.

**Fire gates:**
- **Gun:** fire when the angle between actual aim (`self.aim`) and the lead solution is below `atan(target_radius / dist) + spread`, and `shot_los` from the muzzle is clear. Reload early when out of combat and the magazine is below half.
- **Lightning:** it hits the **nearest** mech, NPC or crate within `range` and `cone_deg`, with LOS. Fire only when the intended target is that nearest candidate, so we don't accidentally hit a drone or crate. It costs `energy` per shot, so keep a reserve for boosting.
- **Laser (when held):** charge only with a stable target and clear `shot_los`; release at ≥ 0.65 s or when the target is about to break LOS. We move at half speed while charging.
- **Mortar (when held):** lob at targets behind cover using the threat track; never fire when the predicted splash reaches us.

**Defensive reflexes:**
- **Incoming mortar shell:** steer out of the predicted splash radius (shells take seconds to land, so this is reliable).
- **Enemy laser charging at us** (`charging: true`, aim pointing at us): break LOS behind the nearest cover if reachable in time; otherwise lightning them (if in range) to cancel the charge; otherwise turn our front armor to them. Strafing alone does not dodge a hitscan beam from a tracking bot.

**Weapon policy:**
- Baseline: gun in slot 0, lightning in slot 1. Gun plus lightning is weak only to mortars, and the gun keeps working when mortars drain our energy. Lightning covers the gun's close-range weakness and cancels rushing lasers.
- Take lightning whenever slot 1 is empty or holds something else and a lightning pickup is safely reachable.
- **Counter-swap only between fights** (no enemy within ~80 m, pickup within a short detour). Choose by what threats remain: several mortar users alive → laser beats mortar.
- Remember the cost of what we carry: a mortar takes +60% from lasers (cook-off), a laser can be shut off by lightning (short).

### 5.4 Upgrade picker

Answer `offer` on the same tick it appears (the timeout applies choice 0). Score each choice from its `effects`:

| Priority | Ids (current config) | Why |
| :--- | :--- | :--- |
| 1 | `nanites` (regen ×1.6, delay −1.5 s, max 2) | Directly powers the retreat-and-regen loop. |
| 2 | `plating` (+15% HP, max 3), `armor` (+8% armor, max 3) | Raw survivability. |
| 3 | `sensors` (max 2), `gun_rate`, `gun_damage`, `lightning_efficiency` | Information and the weapons we keep. |
| 4 | `servos`, `capacitor`, `reactor`, `gyros`, `jets`, others | Useful but secondary. |

Unknown ids fall back to a generic score by effect path (`mech.hp`, `mech.armor`, regen paths high; weapon paths only for weapons we hold).

### 5.5 `bot.py`: safety and timing

- Wrap every tick in `try/except`. On error, send a safe action (move toward the zone centre, keep aim) and log to stderr.
- Measure tick time; if over ~30 ms, skip replanning next tick and reuse the last path.
- `gc.freeze()` after `hello` and run collection manually between ticks to avoid pauses.
- Nothing but protocol lines on stdout.

---

## 6. Roadmap

### MVP (first submission)

- [x] **Phase 1: Core and build** (done 2026-11-21)
  - Map loading, terrain sampling, prism polygons with holes, trees.
  - `vision_los` and `shot_los`, the walkability grid with clearance layers, A*, steering.
  - `core/Makefile`, `ctypes` bindings, and unit tests against known map coordinates.
  - Multi-stage `Dockerfile` (compile `.so` in a builder image, copy it into `python:3.13-slim`).
  - Results: core build ~0.4 s; floor model within 5 mm of all 378 grounded positions in the recorded match; LOS ~2 µs/ray; A* cross-map avg ~1 ms (max ~5 ms), with threats avg ~2 ms (max ~9 ms); sandboxed `check.py` PASS, p99 < 4 ms.
  - Implementation notes: one clearance value per cell (not per-radius layers) covers cube growth; A* uses an inflated heuristic (1.3, or 2.0 with threat/zone penalties) for speed at ~2% longer paths; threat visibility is cached per 8 m block.
- [x] **Phase 2: Movement and zone** (done 2026-11-21)
  - Waypoint following, steering, ledge jumps (`jump` when blocked by > `step_up`).
  - **Jump edges in the nav grid:** the Ohio Stadium bowl is sealed by >= 10 m walls in the solid geometry (the `openings` gates in `world.json` are drawing-only scenery). Leaving works on foot (up the stands, off the outer edge); entering needs a ~10-13 m jump + jet (~15 energy).
  - Zone interpolation and early rotation to covered cells.
  - Results: the core gained floor kind and headroom (grown mechs no longer plan under bridges they don't fit), jump and drop edges spanning up to 8 m in any direction (never onto building roofs), and waypoint kinds (walk/jump/drop). `zone.py`: interpolated circle, time until the edge reaches us, detection of live vs. static circle reporting during shrinks, covered destination inside the next circle. `navigation.py`: walk-first planning, jump plans only near islands and with enough energy, never two searches in one tick, jump + jet execution, stuck escalation (hop, sidestep, replan), boost only when outside or late, mortar-impact avoidance. Worst planning tick 19 ms; mini-simulator drives reach at least 28 of 30 street destinations and the stadium field.
  - Not verifiable offline: the real server's jump/jet physics and wall sliding; the mini simulator (`tests/sim.py`) uses our own floor model.
- [x] **Phase 3: Combat basics** (done 2026-11-21; decisions Q1–Q4 settled the same day)

  **Goal:** the bot shoots well when it shoots, never wastes shots into walls or onto drones, and keeps its front toward whoever is hurting it. *Who* to fight and *when* to disengage is Phase 4 (strategy); Phase 3 provides the mechanics and a simple default policy.

  **Facts from the config and the recorded match**
  - Torso turns at `turn_rate` 4 rad/s, so 0.4 rad (23°) per decision; pitch 3 rad/s, limits −0.7…1.3. Shots leave along the *actual* aim (`self.aim`), not the commanded one.
  - Gun: 45 dmg, 0.24 s, 252 m/s, 230 m range, 0.6° spread, 12-round mag, 2.4 s reload. The shot spawns 3 m out along the aim.
  - Lightning: 60 dmg, 0.25 s, 45 m, cone 30°, 3 energy per shot, chains 2× within 14 m. It hits the **nearest** mech, drone or crate in the cone with line of sight.
  - Rear hits (outside ±90° of aim yaw) take ×1.5.
  - The server keeps reporting a seen mech's **true** position for 5 s after it leaves view, and trees don't stop shots, so a target that just went behind trees can still be shot.
  - Every opponent in the recorded match carried **gun + laser**, so expect lasers.

  **New module `combat.py`**
  1. **Target model:** for each visible or tracked mech: position, velocity, centre height (`height × (1 + 0.05 × cubes) / 2`), radius, HP, weapons, `charging`, whether its aim points at us (within ~4°), and the time it last hit us (from `damaged.by`).
  2. **Torso priority** (one aim per decision):
     - (a) The engage target: the gun lead solution.
     - (b) Otherwise the most recent attacker (≤ 3 s): face it, so hits land on the front.
     - (c) Otherwise a visible mech aiming at us or charging a laser: face it.
     - (d) Otherwise scan: aim along our movement, sweeping ±50° every ~2 s, and toward any `gun`/`laser`/`laser_charge` sound heard in the last 2 s.
  3. **Gun:**
     - Aim at `gun_lead(muzzle, target centre, target velocity, speed, radius + 0.5)`, with muzzle = `pos.z + stats.muzzle_height`.
     - **Fire only if all hold:** the actual aim is within `atan(target radius / distance) + spread` of the solution in yaw, and within the same tolerance in pitch; distance ≤ range; `shot_los` from the shot spawn point to the aim point is clear; ammo > 0 and cooldown 0.
     - **Reload early** when no target has been in range for 1.5 s and ammo < half a magazine. Never fire into a known wall.
  4. **Lightning** (only if held): fire only when the intended target is within ±15° of the actual aim and inside range with `shot_los`, **and** no other candidate (mech, drone or crate) is closer within ±30°. That's safe whether `cone_deg` means a half-angle or a full angle. Keep ≥ 20 energy for jumps unless the target is within 20 m. Also fire at any laser-charging mech in range, since lightning cancels its charge.
  5. **Laser threat reflex (basic):** a visible mech with `charging: true` whose aim is within ~4° of us. Lightning it if in range; otherwise face it (front armour); if cover is reachable within ~1 s, ask navigation to break line of sight (a short side-goal). Strafing alone is useless against a tracking hitscan beam.
  6. **Default engagement policy until Phase 4 (Q1: opportunistic):** the gun takes a mech only if it hit us in the last 5 s, or it is within 60 m, or its HP is below 35% and it is in range. Otherwise hold fire (gunfire is heard up to 320 m, and dealing damage resets our regen timer) and keep rotating.
  7. **Drones (Q3: only if they attack us):** never target a drone unless it damaged us in the last 5 s. Lightning's nearest-target check prevents hitting one by accident. Deliberate farming is Phase 4.
  8. **Slot-1 weapon policy (Q2):**
     - **Lightning first, all match.** Take a lightning pickup into an empty slot, or in place of a laser/mortar we're holding, when out of combat (no enemy within 50 m).
     - **Late-game mortar swap (lightning → mortar)** only if all hold:
       - the zone radius is ≤ 70 m;
       - a mortar pickup is within ~25 m and inside the zone;
       - no enemy is within 50 m;
       - **laser majority check:** among nearby known mechs (seen or tracked within 150 m, plus `laser`/`laser_charge` sounds heard in the last 10 s), **fewer than half carry a laser**. A mech holding a mortar takes +60% from lasers (cook-off). If no mechs are known nearby, this check passes.
     - **Mortar use:** `mortar_pitch` lob at visible or tracked targets, including behind cover. Never fire when the predicted impact is within 12 m of us (50% self-splash, plus knockback). Prefer shots whose blast pushes the target toward the zone edge (zone damage is 160–260 HP/s in the last circles). After taking it, wait out the 2.6 s equip delay.
     - Don't take lasers. If we somehow hold one (e.g. no other option), use a minimal controller: charge to ≥ 0.65 s with a stable target, release when on target, never charge within 45 m of a lightning carrier.

  **Integration:** `bot.py` calls `combat.decide(obs) → aim, fire, reload, nav hints`. Navigation keeps the legs; combat owns the torso. Shell dodging is already in steering (Phase 2).

  **Tests**
  - Fire-gate maths: no fire beyond tolerance; fire within it.
  - Lightning safety: never fires when a drone or crate is closer in the cone.
  - Torso priority order.
  - Reload logic.
  - Replay the recorded match: count how many gun shots the bot would fire into walls (target: 0) and how quickly the aim settles on visible mechs.
  - Extend `tests/sim.py` with a scripted enemy (strafing, stopping, jumping) and simulated bullets. Target: **≥ 70% hits at 80 m on a strafing mech** and 0 shots fired outside the gate.
  - Timing: the combat part adds < 2 ms per decision.

  - Mortar policy: the swap triggers only under all guards, and the laser majority check counts seen, tracked and heard laser carriers. No mortar shot lands within 12 m of us.

  **Done when:** all tests pass and the sandboxed `check.py` passes. Then **make the first practice submission (Q4)** to get a baseline score before Phase 4.

  **Results:** `combat.py` implements all of the above. 14 Phase 3 tests (49 total) pass. Simulated duel at 80 m against a randomly reversing strafer: 42/45 hits (93%), near the gun's maximum fire rate. Replaying the recorded match: 0 shots into walls, combat adds ~0.25 ms per decision. Sandboxed `check.py` passes. Not verifiable offline: real opponents' dodging, and the real server's lightning cone and laser/mortar behaviour.
- [ ] **Phase 4: Strategy** (rewritten 2026-11-21 after the first practice score, 2.33)

  **What practice actually is** (track page): 48 matches against **15 house bots acting as one squad**. They "share vision, never fight each other, and hunt you weakest first (one early, more as you thin them out, all of them late)." Qualifiers and finals are real free-for-alls between teams' bots (top 32 by best practice score qualify). The starter bot scores 1.15; leading teams score about 5–6. Submissions: 4 per hour, about 2 min to score; failed ones never lower the best score.

  **Scoring consequences (practice)**
  - House bots die only by our hand or the zone. Our place = mechs alive when we die, so **each kill is +1**. 2.33 ≈ 2.3 bots dead before us per match.
  - **The final zone burn:** the last circle reaches radius 0 at about 6:55. Everyone is then outside at 260 HP/s, with no armor and no regen, so **the mech with the most HP dies last**. A 1400 HP house bot lasts ~5.4 s. With 10 cubes and 3 plating we'd have ~2,980 HP (~11.5 s), which could win the match even without kills (if house bots don't stack HP too).

  **Decisions**
  - **Strategy: hybrid (C).**
    - Kill early lone hunters in controlled fights.
    - Heal fully between fights.
    - Collect cubes.
    - Avoid fights against 3 or more hunters.
    - Play for the final burn at full HP.
  - **Modes:** detect practice vs free-for-all, **assuming practice until there is evidence of a free-for-all**. Free-for-all keeps the original survival-first plan (others fight each other; we stay healthy and let the field thin).
  - **Upgrade ranking:**
    1. nanites (first pick: full heal ~36 s → ~23 s);
    2. plating up to 3 (max HP: every fight, the late all-hunters phase, the final burn);
    3. second nanites;
    4. armor;
    5. then sensors, gyros, weapon perks for weapons we hold (gun rate/damage, lightning efficiency/range), servos, energy.

    Unknown ids get a generic score from their `effects` paths. Always answer the offer on the tick it appears.
  - **Build and test incrementally:** one change per submission, keep what raises the score.

  **New modules**
  - `threat.py`, the squad model:
    - Per mech: last position and velocity, last seen time, HP, weapons, whether it's approaching or aiming at us.
    - Sources: vision, the server's 5 s tracking, `damaged.by`, sound bearings.
    - **Hunters** = mechs within ~150 m that hit us recently, are closing on us, or aim at us.
    - **Shared vision:** if any hunter sees us, assume all of them know where we are.
  - `strategy.py`, states with utility scores and hysteresis (at least ~1.5 s in a state unless a hard override fires):
    - `ROTATE`: zone first (Phase 2 navigation).
    - `FARM`: crates, isolated drones and cubes when no hunter is within ~120 m.
    - `ENGAGE`: at most 1 hunter, or 2 when our HP is clearly higher. Peek-shoot from cover; prefer finishing low-HP targets (a kill is +1).
    - `RETREAT`: HP below ~55%, 3+ hunters, or losing the HP race. Break line of sight from all known hunters, stop firing (regen needs no damage dealt), heal to ≥ 90%.
    - `HOLD`: covered spot in the zone, scanning.
    - `BURN`: from the second-to-last circle, be at full HP and at the final centre, so we're the last one outside.
  - **Mode detection:**
    - The `alive` count falling without one of our `kill` events means others are dying, which means a free-for-all.
    - Guard against house bots dying to the zone: require such a drop outside the last two zone phases, or two such drops.
  - **Cube collection:** walk over cubes (pickup radius 3.5 m) when safe, including those dropped by our kills.

  **Experiment order** (one submission each; compare against 2.33)

  | # | Change | What we learn |
  | :--- | :--- | :--- |
  | E1 | Upgrade picker + `RETREAT` heal cycles (+ threat model). **Built 2026-11-21** (`upgrades.py`, `threat.py`, `strategy.py`); score pending | Does disengaging to heal raise placement? |
  | E2 | Fight selection (`ENGAGE` only vs 1–2 hunters) + peek-shooting + kill finishing | Kill rate vs survival |
  | E3 | Cube economy (`FARM`: crates, isolated drones, kill drops) | Do bigger HP/damage pay off? |
  | E4 | Final-burn play (`BURN`) | Do house bots die to the zone? Can we outlast them? |
  | E5 | Supply drops (full HP + 3 cubes) when the squad isn't on them | |
  | E6 | Mode detection + free-for-all behaviour | Needed before qualifiers; no practice signal expected |

  **Unknowns these experiments should reveal:** whether house bots die to the zone, collect cubes or upgrade; how fast hunters escalate after a kill; what "weakest first" means.
- [ ] **Phase 5: Conformance and submit**
  - `python3 check/check.py -- python3 -u bot.py`
  - Docker run with match sandbox flags:
    `python3 check/check.py --map-dir /arena -- docker run --rm -i --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" my-bot`
  - Confirm average tick ≤ 5 ms, worst tick < 25 ms, `ready` < 5 s. Submit.

### Iterations (driven by practice-match scores)

- [ ] Supply drop contesting and third-partying.
- [ ] Laser and mortar handling (charge/release, lob over cover, cook-off avoidance), and the laser-threat reflex.
- [ ] Between-fight counter-swapping.
- [ ] Opportunistic rooftops: roof surface layer, launch points beside low edges, `jump + boost` climb only with near-full energy and inside the safe zone; roof crates and loot.
- [ ] Tuning of utility weights, engagement ranges and retreat thresholds from match results.

---

## 7. Known Risks

- **No local simulator:** behaviour bugs only show up as practice scores. Keep each submission's changes small enough to attribute score changes.
- **Two different opponents:** practice is a 15-bot squad that shares vision and hunts us; qualifiers/finals are free-for-alls. The bot must detect which it is in (Phase 4).
- **Multi-level geometry:** a ground-only grid misroutes near bridges and roof edges; verify those areas explicitly in Phase 1 tests.
- **Growth with cubes:** larger radius and eye/muzzle height change paths and LOS; always read `self.stats`.
