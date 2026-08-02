"""Adapter around the existing combat system module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
COMBAT_PATH = REPO_ROOT / "comabt_system" / "combat.py"


def _load_combat_module():
    spec = importlib.util.spec_from_file_location("northern_combat", COMBAT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load combat module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    combat = _load_combat_module()
    force_a = combat.calculate_force_strength(payload["army_a"].get("units", {}))
    force_b = combat.calculate_force_strength(payload["army_b"].get("units", {}))
    if force_a <= 5:
        raise ValueError("attacking army must have more than 5 force points")
    if force_b <= 5:
        units_a = combat._clean_counts(payload["army_a"].get("units", {}))
        zero_units = {unit: 0 for unit in combat.UNITS}
        return {
            "winner": "A",
            "surrendered": "B",
            "rounds": 0,
            "log": [],
            "remaining": {
                "A": {"label": "A", "units": units_a},
                "B": {"label": "B", "units": zero_units},
            },
        }
    return combat.simulate_battle(
        payload["army_a"],
        payload["army_b"],
        max_rounds=int(payload.get("max_rounds", 20)),
        reinforcements=payload.get("reinforcements"),
    )
