"""Small, isolated helpers for the experimental navy layer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "data" / "navy_rules.json"


def load_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def repair_cost(missing_hp: int, *, cost_per_hp: int = 2) -> int:
    missing = max(0, int(missing_hp))
    return missing * max(0, int(cost_per_hp))


def validate_initial_divisions(rules: Mapping[str, Any]) -> None:
    unit_rules = rules.get("units", {})
    if "gun_boat" not in unit_rules or "cargo_boat" not in unit_rules:
        raise ValueError("navy rules must define gun_boat and cargo_boat")
    seen = set()
    for division in rules.get("initial_divisions", []):
        division_id = str(division.get("id", ""))
        if not division_id:
            raise ValueError("navy division requires an id")
        if division_id in seen:
            raise ValueError(f"duplicate navy division id: {division_id}")
        seen.add(division_id)
        if int(division.get("gun_boats", 0)) < 1:
            raise ValueError(f"{division_id} requires at least one gun boat")
        if int(division.get("cargo_boats", 0)) < 1:
            raise ValueError(f"{division_id} requires at least one cargo boat")
