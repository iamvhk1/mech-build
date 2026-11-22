# Mech Royale 2D Strategy Visualizer

A local, high-performance 2D debug visualizer for inspecting our autonomous bot's movement, combat decisions, tactical pathfinding, and strategy state machine in real-time.

---

## Quick Start

Start the local visualizer server:
```bash
python3 visualizer/run.py --port 8000
```
Then open **[http://localhost:8000](http://localhost:8000)** in any web browser.

---

## Features

### 1. Dual Match Sources
- **Real Server Match (`stream.jsonl.gz`):** Replay the 300-tick real server match observation by observation to inspect how our bot responds to actual server events.
- **Squad Match Simulator (`tests/squad.py`):** Simulate full multi-minute matches against the 15-bot house squad with configurable seeds and presets (`best`, `press`, `arm`, `laser`).

### 2. Interactive 2D Canvas Viewport
- **Pan & Zoom:** Drag to pan around the arena; mouse wheel to zoom in/out.
- **Follow Bot [F]:** Smooth camera lock that keeps our mech centered on screen.
- **Campus Map:** 1070x724 high-resolution top-down rendering of the Ohio State arena (streets, buildings, roofs, bridges).
- **Zone Boundaries:** Real-time visualization of the shrinking safe zone circle, upcoming next circle, and storm danger shading.

### 3. Combat & Tactical Overlays (Toggleable)
- **Planned A\* Path:** Gold navigation path showing computed waypoints to the target destination.
- **60m Engagement Circle:** Dotted circle showing the weapon engagement radius (`engage.near_m`).
- **45m Lightning Cone:** 30° frontal arc showing the instantaneous auto-target zone.
- **Hunter Sightlines:** Real-time line-of-fire rays and threat cones from active enemy hunters.
- **Supply Drops:** 8m capture radius with animated 4-second capture progress rings.
- **Economy:** Floor power cubes, crates with health bars, and weapon pickups (Lightning, Laser, Mortar).

### 4. Live Strategy & Engine HUD
- **State Pill & Reason:** Live state (`ROTATE`, `RETREAT`, `PRESS`, `LOOT`, `ARM`, `DROP`) with the exact `why` string.
- **Vitals:** HP bar with health percentage and Energy bar with 20 & 35 threshold notches.
- **Weapon Telemetry:** Gun ammo/reload timers and auxiliary slot cooldowns/charge meters.
- **Cube Scaling:** Current cube count with damage and max HP multiplier boosts.
- **Entity Tooltip:** Hover over our mech, enemy hunters, crates, or drops to inspect their stats.

### 5. Playback Controls & Keybindings
- **Play / Pause:** Spacebar or click `[▶] / [⏸]`.
- **Step Forward / Backward:** `Right Arrow` / `Left Arrow` (or Shift+Arrow for 10 ticks).
- **Speed Selector:** `0.25x`, `0.5x`, `1.0x`, `2.0x`, `5.0x`.
- **Event Scrubber:** Clickable markers for kills, weapon pickups, and damage events.
- **Reset View:** Press `R`.
