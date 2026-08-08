"""City output rules: how a city's cash and factory figures become player income.

Moved out of backend/card_engine.py so the economy rules, the factory rules and
the loan book live together.
"""

from __future__ import annotations

from typing import Any, Dict

# 城市產出由等級決定：1 級 cash 2 / factory 1，每升一級各 +1，最高 5 級。
CITY_LEVEL_MIN = 1
CITY_LEVEL_MAX = 5
CITY_BASE_OUTPUT = {"cash": 2, "factory": 1}
CITY_OUTPUT_PER_LEVEL = {"cash": 1, "factory": 1}

# 租界加成：每三回合結算一次，與城市等級產出分開計算。
# 港口沒有任何經濟效果；city["port"] == "river" 純為河港城市的標示。
TREATY_PORT_INTERVAL = 3
CONCESSION_BONUS = {"cash": 2, "factory": 2}


def city_level(city: Dict[str, Any]) -> int:
    return max(CITY_LEVEL_MIN, min(CITY_LEVEL_MAX, int(city.get("level", CITY_LEVEL_MIN))))


def scaled_city_value(city: Dict[str, Any], field: str) -> int:
    """Per-turn output for one field, derived from the city's level.

    Level 1 pays 2 cash and 1 factory; every level above that adds 1 to each,
    up to level 5. The raw `cash`/`factory` figures in the scenario file are no
    longer read — level is the only input.
    """
    steps = city_level(city) - CITY_LEVEL_MIN
    return CITY_BASE_OUTPUT[field] + CITY_OUTPUT_PER_LEVEL[field] * steps


def is_river_port(city: Dict[str, Any]) -> bool:
    """河港城市。純為標示，不影響產出。"""
    return city.get("port") == "river"


def treaty_port_bonus(city: Dict[str, Any]) -> Dict[str, int]:
    """Cash and factory a single city adds on a settlement turn.

    Only concessions pay. Ports carry no economic effect.
    """
    if not city.get("concession"):
        return {"cash": 0, "factory": 0}
    return {"cash": CONCESSION_BONUS["cash"], "factory": CONCESSION_BONUS["factory"]}


def is_settlement_turn(turn: int) -> bool:
    return turn % TREATY_PORT_INTERVAL == 0
