"""City output rules: how a city's cash and factory figures become player income.

Moved out of backend/card_engine.py so the economy rules, the factory rules and
the loan book live together.
"""

from __future__ import annotations

from typing import Any, Dict

# Raw city values on the board are scaled down before they become per-turn income.
ECONOMY_SCALE = {"cash": 0.25, "factory": 0.35}

# 租界與港口加成：每三回合結算一次，不經 ECONOMY_SCALE 縮放，租界與港口可疊加。
TREATY_PORT_INTERVAL = 3
CONCESSION_BONUS = {"cash": 1, "factory": 1}
PORT_CASH_BONUS = {"river": 1, "sea": 2}


def scaled_city_value(city: Dict[str, Any], field: str) -> int:
    value = int(city.get(field, 0))
    return max(1, round(value * ECONOMY_SCALE[field])) if value else 0


def port_cash_bonus(city: Dict[str, Any]) -> int:
    port = city.get("port")
    if port == "river_sea":
        return PORT_CASH_BONUS["river"] + PORT_CASH_BONUS["sea"]
    return PORT_CASH_BONUS.get(port, 0)


def treaty_port_bonus(city: Dict[str, Any]) -> Dict[str, int]:
    """Cash and factory a single city adds on a settlement turn."""
    cash = port_cash_bonus(city)
    factory = 0
    if city.get("concession"):
        cash += CONCESSION_BONUS["cash"]
        factory += CONCESSION_BONUS["factory"]
    return {"cash": cash, "factory": factory}


def is_settlement_turn(turn: int) -> bool:
    return turn % TREATY_PORT_INTERVAL == 0
