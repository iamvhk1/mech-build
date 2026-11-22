"""Match recorder for both real server recordings (stream.jsonl.gz) and squad simulations.

Produces standardized replay dictionaries for the 2D debug visualizer.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)

import bot as B
import mechfight as mf
import tests.squad as sq
import tuning


def record_stream() -> dict:
    """Replay real server match from check/stream.jsonl.gz through Bot and record frames."""
    stream_path = os.path.join(ROOT, "check", "stream.jsonl.gz")
    if not os.path.exists(stream_path):
        raise FileNotFoundError(f"Missing {stream_path}")

    with gzip.open(stream_path, "rt") as f:
        hello = json.loads(f.readline())
        hello["map"]["dir"] = os.path.join(ROOT, "arena")
        bot = B.Bot(hello)
        
        frames = []
        events_log = []
        prev_hp = None

        for line in f:
            if not line.strip():
                continue
            msg = json.loads(line)
            if msg.get("type") == "end":
                break
            if msg.get("type") != "obs" and "self" not in msg:
                continue

            obs = msg
            t = float(obs.get("t", 0.0))
            tick = int(obs.get("tick", 0))

            # Intercept decision
            act = bot.act(obs)
            me = obs["self"]
            x, y, z = me["pos"]
            hp = float(me.get("hp", 0.0))

            if prev_hp is not None and hp < prev_hp:
                events_log.append({"t": round(t, 2), "type": "damage", "desc": f"Took {prev_hp - hp:.0f} dmg"})
            prev_hp = hp

            for e in obs.get("events") or []:
                if e.get("type") == "kill":
                    events_log.append({"t": round(t, 2), "type": "kill", "desc": f"Kill target {e.get('target')}"})
                elif e.get("type") == "took":
                    events_log.append({"t": round(t, 2), "type": "pickup", "desc": f"Took {e.get('kind')}"})

            frame = {
                "t": round(t, 2),
                "tick": tick,
                "self": {
                    "pos": [round(x, 1), round(y, 1), round(z, 1)],
                    "vel": [round(v, 2) for v in me.get("vel") or [0, 0, 0]],
                    "aim": [round(a, 3) for a in me.get("aim") or [0, 0]],
                    "hp": round(hp, 1),
                    "max_hp": round(float(me.get("max_hp", 1000.0)), 1),
                    "energy": round(float(me.get("energy", 100.0)), 1),
                    "max_energy": round(float(me.get("stats", {}).get("energy", 100.0)), 1),
                    "cubes": int(me.get("cubes", 0)),
                    "weapons": me.get("weapons") or [],
                    "state": getattr(bot.strategy, "state", "rotate"),
                    "mode": getattr(bot.mode_detector, "mode", "practice"),
                    "goal": list(bot.nav.goal) if bot.nav.goal else None,
                    "path": [[round(p[0], 1), round(p[1], 1)] for p in bot.nav.path[:25]],
                    "strafe": bool(getattr(bot.strafer, "active", False)),
                    "combat_debug": getattr(bot.combat, "debug", ""),
                    "nav_debug": getattr(bot.nav, "last_debug", ""),
                    "pacing_mode": getattr(bot.pacer, "mode", ""),
                    "armer_mode": getattr(bot.armer, "mode", ""),
                    "dropper_mode": getattr(bot.dropper, "mode", ""),
                    "farmer_mode": getattr(bot.farmer, "mode", ""),
                    "act": {
                        "fire": act.get("fire"),
                        "reload": act.get("reload"),
                        "aim": act.get("aim"),
                        "take": act.get("take"),
                        "move": act.get("move"),
                    }
                },
                "zone": {
                    "center": [round(obs["zone"]["center"][0], 1), round(obs["zone"]["center"][1], 1)],
                    "radius": round(obs["zone"]["radius"], 1),
                    "next_center": [round(obs["zone"]["next_center"][0], 1), round(obs["zone"]["next_center"][1], 1)],
                    "next_radius": round(obs["zone"]["next_radius"], 1),
                    "dps": obs["zone"].get("dps", 0)
                },
                "mechs": [
                    {
                        "id": int(m["id"]),
                        "kind": m.get("kind", "mech"),
                        "pos": [round(m["pos"][0], 1), round(m["pos"][1], 1), round(m["pos"][2], 1)],
                        "hp": round(float(m.get("hp", 0)), 1),
                        "aim": m.get("aim") or [0, 0],
                        "charging": bool(m.get("charging", False)),
                    }
                    for m in obs.get("mechs") or []
                ],
                "pickups": [
                    {"id": p["id"], "kind": p.get("kind"), "pos": [round(p["pos"][0], 1), round(p["pos"][1], 1)]}
                    for p in obs.get("pickups") or []
                ],
                "cubes": [
                    {"id": c["id"], "pos": [round(c["pos"][0], 1), round(c["pos"][1], 1)]}
                    for c in obs.get("cubes") or []
                ],
                "drops": [
                    {
                        "id": d["id"],
                        "pos": [round(d["pos"][0], 1), round(d["pos"][1], 1)],
                        "progress": round(float(d.get("progress", 0)), 1),
                        "lands_in": round(float(d.get("lands_in", 0)), 1),
                        "holder": d.get("holder")
                    }
                    for d in obs.get("drops") or []
                ],
                "beams": obs.get("beams") or [],
                "events": obs.get("events") or []
            }
            frames.append(frame)

    return {
        "id": "server_match",
        "title": "Real Server Recording (stream.jsonl.gz)",
        "source": "check/stream.jsonl.gz",
        "preset": tuning.ACTIVE,
        "total_time": frames[-1]["t"] if frames else 0,
        "frames_count": len(frames),
        "events": events_log,
        "frames": frames
    }


def record_squad(seed: int = 42, preset: str = "best") -> dict:
    """Run full match against 15-bot house squad and record frames at 10 Hz."""
    hello = sq.load_hello()
    tuning.use(preset)
    m = sq.Match(hello, seed=seed, preset=preset)

    frames = []
    events_log = []
    orig_act = m.bot.act
    prev_slot1 = None

    def act_wrapper(obs):
        nonlocal prev_slot1
        act = orig_act(obs)
        t = float(obs.get("t", 0.0))
        tick = int(obs.get("tick", 0))

        x, y, zz = m.me()
        hp = float(m.hp)

        # Track milestone events
        for e in obs.get("events") or []:
            if e.get("type") == "kill":
                events_log.append({"t": round(t, 2), "type": "kill", "desc": f"Killed Hunter {e.get('target')}"})
            elif e.get("type") == "took":
                events_log.append({"t": round(t, 2), "type": "pickup", "desc": f"Took {e.get('kind')}"})

        if m.slot1 != prev_slot1:
            if m.slot1 is not None:
                events_log.append({"t": round(t, 2), "type": "arm", "desc": f"Armed with {m.slot1.upper()}"})
            prev_slot1 = m.slot1

        z = m.zone.state(t)
        
        # Build frame
        frame = {
            "t": round(t, 2),
            "tick": tick,
            "self": {
                "pos": [round(x, 1), round(y, 1), round(zz, 1)],
                "vel": [round(v, 2) for v in (0, 0, m.sim.vz)],
                "aim": [round(m.aim[0], 3), round(m.aim[1], 3)],
                "hp": round(hp, 1),
                "max_hp": round(float(m.max_hp), 1),
                "energy": round(float(m.sim.energy), 1),
                "max_energy": round(float(m.m["energy"]), 1),
                "cubes": int(m.cubes),
                "weapons": [
                    {"kind": "gun", "ammo": m.ammo, "reload": round(m.rl, 1), "cd": round(m.cd, 2)},
                    {"kind": m.slot1, "cd": round(m.cd1, 2), "charge": round(m.charge, 2)} if m.slot1 else None
                ],
                "state": getattr(m.bot.strategy, "state", "rotate"),
                "mode": getattr(m.bot.mode_detector, "mode", "practice"),
                "goal": list(m.bot.nav.goal) if m.bot.nav.goal else None,
                "path": [[round(p[0], 1), round(p[1], 1)] for p in m.bot.nav.path[:25]],
                "strafe": bool(getattr(m.bot.strafer, "active", False)),
                "combat_debug": getattr(m.bot.combat, "debug", ""),
                "nav_debug": getattr(m.bot.nav, "last_debug", ""),
                "pacing_mode": getattr(m.bot.pacer, "mode", ""),
                "armer_mode": getattr(m.bot.armer, "mode", ""),
                "dropper_mode": getattr(m.bot.dropper, "mode", ""),
                "farmer_mode": getattr(m.bot.farmer, "mode", ""),
                "act": {
                    "fire": act.get("fire"),
                    "reload": act.get("reload"),
                    "aim": act.get("aim"),
                    "take": act.get("take"),
                    "move": act.get("move"),
                }
            },
            "zone": {
                "center": [round(z["center"][0], 1), round(z["center"][1], 1)],
                "radius": round(z["radius"], 1),
                "next_center": [round(z["next_center"][0], 1), round(z["next_center"][1], 1)],
                "next_radius": round(z["next_radius"], 1),
                "dps": z.get("dps", 0)
            },
            "mechs": [
                {
                    "id": h.id,
                    "tier": h.tier,
                    "pos": [round(h.pos[0], 1), round(h.pos[1], 1), round(h.pos[2], 1)],
                    "hp": round(float(h.hp), 1),
                    "max_hp": round(float(h.max_hp), 1),
                    "active": bool(h.active),
                    "alive": bool(h.alive)
                }
                for h in m.hunters if h.alive
            ],
            "pickups": [
                {"id": pid, "kind": p["kind"], "pos": [round(p["pos"][0], 1), round(p["pos"][1], 1)]}
                for pid, p in m.pickups.items()
            ],
            "cubes": [
                {"id": cid, "pos": [round(p[0], 1), round(p[1], 1)]}
                for cid, p in m.cube_items.items()
            ],
            "drops": [
                {
                    "id": d["id"],
                    "pos": [round(d["pos"][0], 1), round(d["pos"][1], 1)],
                    "progress": round(float(d["progress"]), 1),
                    "lands_in": round(max(0.0, d["land_t"] - t), 1),
                    "holder": 0 if d["progress"] > 0 else None
                }
                for d in m.drops
            ],
            "events": obs.get("events") or []
        }
        frames.append(frame)
        return act

    m.bot.act = act_wrapper
    stats = m.run()

    if m.hp <= 0:
        events_log.append({"t": round(m.stats.get("t", frames[-1]["t"]), 2), "type": "death", "desc": "Bot eliminated"})

    return {
        "id": f"squad_{preset}_seed{seed}",
        "title": f"Squad Simulation (Seed {seed}, Preset '{preset}')",
        "source": "squad.py",
        "preset": preset,
        "seed": seed,
        "kills": m.kills,
        "points": stats.get("points", m.kills),
        "total_time": frames[-1]["t"] if frames else 0,
        "frames_count": len(frames),
        "events": events_log,
        "stats": stats,
        "frames": frames
    }
