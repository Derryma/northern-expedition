"""Data loading helpers for the playtest backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_PATHS = {
    "function_cards": "cards/data/function_cards.json",
    "event_cards": "cards/data/event_cards.json",
    "card_pool_rules": "cards/data/card_pool_rules.json",
    "foreign_powers": "foreign_powers/data/foreign_powers.json",
    "npc_factions": "NPC/data/npc_factions.json",
    "general_tree_template": "general_tree/data/general_tree_template.json",
    "general_skills": "general_tree/data/skill_catalog.json",
    "generals_in_exile": "general_tree/data/generals_in_exile.json",
    "unit_stats": "comabt_system/data/unit_stats.json",
    "tactics": "comabt_system/data/tactics.json",
    "general_traits": "comabt_system/data/general_traits.json",
    "navy_system": "navy_system/data/navy_rules.json",
    "strategic_map": "scenario/data/strategic_map.json",
}

# 四大可玩勢力的將領樹。引擎本身不管理將領樹（那是前端的事），
# 但開局時要知道哪個陣營帶著〈日本買辦〉這類非戰鬥技能。
PLAYABLE_TREE_PATHS = {
    "N": "general_tree/data/general_tree_playtest.json",
    "F": "general_tree/data/general_tree_fengtian.json",
    "W": "general_tree/data/general_tree_zhili.json",
    "S": "general_tree/data/general_tree_sunfang.json",
}


def load_json(relative_path: str) -> Any:
    with (REPO_ROOT / relative_path).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_game_data() -> Dict[str, Any]:
    data = {name: load_json(path) for name, path in DATA_PATHS.items()}
    data["playable_general_trees"] = {
        faction: load_json(path) for faction, path in PLAYABLE_TREE_PATHS.items()
    }
    data["indexes"] = {
        "function_cards": _index_cards(data["function_cards"]["cards"]),
    }
    data["metadata"] = {
        "function_cards": len(data["function_cards"]["cards"]),
        "event_cards": len(data["event_cards"]["cards"]),
        "navy_divisions": len(data["navy_system"]["initial_divisions"]),
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
