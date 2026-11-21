# mech-royale-bot

Autonomous bot for the Mech Royale `mechfight/1` battle royale.

- Rules and protocol: [docs/protocol.md](docs/protocol.md)
- Plan and roadmap: [docs/implementation_plan.md](docs/implementation_plan.md)
- Original kit README: [docs/kit_README.md](docs/kit_README.md)

## Layout

| Path | Purpose |
| --- | --- |
| `Dockerfile` | Submission image (must stay at the top level). Two stages: compile the core, then a slim runtime. |
| `bot.py` | Entrypoint. Builds the map core at `hello`, falls back to straight-line movement if it can't. |
| `zone.py` | Zone circle over time, time until the edge reaches a point, destination inside the next circle. |
| `roofs.py` | Roof index (standable roofs, height, area, safest middle spot) and roof choice. |
| `tuning.py` | Experiment presets: every behaviour switch in one place (`ACTIVE` selects). |
| `strategy.py` | Behaviour states (E1: rotate, retreat-to-heal with hidden-spot search). |
| `threat.py` | Threat memory: enemy tracks, who is hunting us, damage taken. |
| `upgrades.py` | Upgrade picker: nanites, plating x3, nanites, armor, then the rest. |
| `combat.py` | Torso aim, gun/lightning/mortar firing gates, reloads, slot-1 weapon policy, laser-threat reflex. |
| `navigation.py` | Walk-first planning, jumps/jets, waypoint following, unsticking, boost policy. |
| `core_api.py` | ctypes bindings: `MapCore` (floor, LOS, A*, steering, shell impact), `gun_lead`, `mortar_pitch`. |
| `core/` | C++ core: `map.cpp` (terrain, prisms, floor model), `los.cpp`, `nav.cpp`, `aim.cpp`, C ABI in `mech_core.h`. |
| `debug_draw.py` | Optional debug drawing (`MECH_DEBUG=1`); never affects play. |
| `mechfight.py` | Kit protocol wrapper (unchanged). |
| `example_bot.py` | Kit example bot, kept for reference. |
| `tests/` | Core and Phase 2-4 tests; `tests/sim.py` is a crude movement simulator (our floor model, not the server). |
| `tools/` | `render_map.py` (nav-grid PNGs), `check_docker.sh` (sandboxed conformance check). |
| `arena/` | Map files for local runs (`/arena` is mounted in matches). |
| `check/` | Kit conformance check. |
| `mechfight.schema.json` | Message schema (used by `check/check.py`). |

## Build and test (Linux or WSL)

The core is a Linux shared library; build and test on Linux, WSL or in Docker. (On this Windows
machine, application control blocks loading an unsigned locally built DLL.)

```sh
make -C core                                   # builds core/libmech_core.so
python3 -m unittest discover -s tests -v       # MECH_SKIP_TIMING=1 to skip timing asserts
python3 check/check.py -- python3 -u bot.py    # stderr must show "core ready"
MECH_DEBUG=1 python3 check/check.py -- python3 -u bot.py
python3 tools/render_map.py --out /tmp/mapviz --path=-300,-250,400,300
tools/check_docker.sh                          # builds the image, runs the match sandbox, fails if the core didn't load
```

`check.py` alone can't tell whether the core loaded (the bot falls back to straight-line movement),
so use `tools/check_docker.sh`, or look for `core ready` in the output. Run `check.py` from Linux/WSL:
on Windows it rewrites `--map-dir /arena` to `C:\arena`.
