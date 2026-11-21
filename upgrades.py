"""Upgrade picker (protocol §10).

Ranking decided for Phase 4 (docs/implementation_plan.md):
  1. first nanites   (heal cycles: full heal ~36 s -> ~23 s)
  2. plating, up to 3 (max HP: every fight, the late all-hunters phase, the final zone burn)
  3. second nanites
  4. armor
  5. then sensors, gyros, perks for weapons we hold, servos, energy upgrades
Unknown ids are scored from their `effects` paths so a balance change can't break the picker.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

WEAPON_PERKS = {
    "gun": ("gun_rate", "gun_damage", "gun_mag", "gun_velocity"),
    "lightning": ("lightning_efficiency", "lightning_range", "lightning_chain"),
    "mortar": ("mortar_reload", "mortar_splash", "mortar_velocity"),
    "laser": ("laser_charge", "laser_damage", "laser_pierce"),
}

# generic scores for unknown upgrades, by effect path
PATH_SCORE = {
    "mech.regen_per_s": 70, "mech.regen_delay": 70, "mech.hp": 60, "mech.armor": 50,
    "mech.near_range_bonus": 30, "mech.vision_bonus": 30, "mech.hearing": 25, "mech.turn_rate": 25,
    "mech.pitch_rate": 20, "mech.walk_speed": 20, "mech.boost_speed": 15, "mech.energy": 15,
    "mech.energy_regen": 15, "mech.boost_drain": 10, "mech.jet_drain": 10,
}


def score(choice_id: str, taken: Sequence[str], held_weapons: Sequence[str], defs: Dict[str, dict]) -> float:
    n = sum(1 for u in taken if u == choice_id)
    if choice_id == "nanites":
        return 100.0 if n == 0 else 80.0
    if choice_id == "plating":
        return 90.0 - n  # all plating stacks rank between the first and second nanites
    if choice_id == "armor":
        return 70.0
    if choice_id == "sensors":
        return 40.0
    if choice_id == "gyros":
        return 35.0
    for w in held_weapons:
        perks = WEAPON_PERKS.get(w, ())
        if choice_id in perks:
            return 30.0 - perks.index(choice_id)
    if choice_id == "servos":
        return 20.0
    if choice_id in ("capacitor", "reactor", "jets"):
        return 15.0
    d = defs.get(choice_id) or {}
    s = 0.0
    for e in d.get("effects") or []:
        path = e.get("path", "")
        s = max(s, PATH_SCORE.get(path, 10.0 if path.startswith("weapons.") else 5.0))
    req = d.get("requires")
    if req and req not in held_weapons:
        s = 0.0
    return s


def pick(offer: Optional[dict], me: dict, cfg: dict) -> Optional[int]:
    """Index of the best choice in the pending offer, or None if there is no offer."""
    if not offer or not offer.get("choices"):
        return None
    defs = {u["id"]: u for u in cfg.get("upgrades") or []}
    taken: List[str] = list(me.get("upgrades") or [])
    held = [w["kind"] for w in (me.get("weapons") or []) if w]
    scores = [score(c.get("id", ""), taken, held, defs) for c in offer["choices"]]
    return max(range(len(scores)), key=lambda i: scores[i])
