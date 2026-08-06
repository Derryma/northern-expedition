"""Foreign-power relations: the scale, the starting positions, and the bands.

The numbers live in data/foreign_powers.json so the diplomacy data and the
lending data stay in their own subsystems and the engine reads both rather than
hardcoding either.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

DATA_PATH = Path(__file__).resolve().parent / "data" / "foreign_powers.json"

# Every power the relation track covers. Germany is deliberately absent: after the
# 1921 Sino-German treaty it held no privileges in China, so it is a neutral
# commercial party (德華銀行) rather than a diplomatic one.
RELATION_KEYS = ("jp", "su", "uk", "fr", "us")


def load_foreign_power_data(path: Optional[Path] = None) -> Dict[str, Any]:
    with (path or DATA_PATH).open(encoding="utf-8") as handle:
        return json.load(handle)


def relation_scale(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return (data or load_foreign_power_data())["global_rules"]["relation_scale"]


def relation_bounds(data: Optional[Dict[str, Any]] = None) -> tuple[int, int]:
    scale = relation_scale(data)
    return int(scale["min"]), int(scale["max"])


def clamp(value: int, data: Optional[Dict[str, Any]] = None) -> int:
    low, high = relation_bounds(data)
    return max(low, min(high, int(value)))


def starting_relations(faction: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """The June-1926 position for a playable faction, as {relations_key: value}."""
    payload = (data or load_foreign_power_data())["initial_relations"]["by_faction"].get(faction)
    if not payload:
        return {key: 0 for key in RELATION_KEYS}
    return {key: int(payload[key]) for key in RELATION_KEYS if key in payload}


def band(value: int, data: Optional[Dict[str, Any]] = None) -> str:
    """hostile / neutral / friendly, using the same cut points as the loan tiers."""
    scale = relation_scale(data)
    if value <= int(scale["hostile_at_or_below"]):
        return "hostile"
    if value >= int(scale["friendly_at_or_above"]):
        return "friendly"
    return "neutral"
