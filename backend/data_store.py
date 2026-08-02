"""Data loading helpers for the playtest backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_PATHS = {
    "event_cards": "cards/data/event_cards.json",
    "function_cards": "cards/data/function_cards.json",
    "injected_event_cards": "cards/data/injected_event_cards.json",
    "card_pool_rules": "cards/data/card_pool_rules.json",
    "foreign_powers": "foreign_powers/data/foreign_powers.json",
    "npc_factions": "NPC/data/npc_factions.json",
    "general_tree_template": "general_tree/data/general_tree_template.json",
    "general_skills": "general_tree/data/skill_catalog.json",
    "unit_stats": "comabt_system/data/unit_stats.json",
    "tactics": "comabt_system/data/tactics.json",
    "general_traits": "comabt_system/data/general_traits.json",
    "strategic_map": "scenario/data/strategic_map.json",
}


def load_json(relative_path: str) -> Any:
    with (REPO_ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_game_data() -> Dict[str, Any]:
    data = {name: load_json(path) for name, path in DATA_PATHS.items()}
    data["indexes"] = {
        "event_cards": _index_cards(data["event_cards"]["cards"]),
        "function_cards": _index_cards(data["function_cards"]["cards"]),
        "injected_event_cards": _index_cards(data["injected_event_cards"]["cards"]),
    }
    data["metadata"] = {
        "event_cards": len(data["event_cards"]["cards"]),
        "function_cards": len(data["function_cards"]["cards"]),
        "injected_event_cards": len(data["injected_event_cards"]["cards"]),
        "npc_factions": len(data["npc_factions"]["npc_factions"]),
        "foreign_powers": len(data["foreign_powers"]["powers"]),
    }
    return data


def _index_cards(cards: list[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed = {}
    for card in cards:
        card_id = str(card["id"])
        if card_id in indexed:
            raise ValueError(f"duplicate card id: {card_id}")
        indexed[card_id] = card
    return indexed
