"""In-memory turn and card-pool engine for playtesting."""

from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from .data_store import load_game_data


DEFAULT_PLAYERS = ("F", "W", "S", "N")


class GameEngine:
    def __init__(self, *, seed: Optional[int] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.data = data or load_game_data()
        self.random = random.Random(seed)
        self.state = self.new_game(seed=seed)

    def new_game(self, *, players: Iterable[str] = DEFAULT_PLAYERS, seed: Optional[int] = None) -> Dict[str, Any]:
        if seed is not None:
            self.random.seed(seed)
        function_ids = [card["id"] for card in self.data["function_cards"]["cards"]]
        event_ids = [card["id"] for card in self.data["event_cards"]["cards"] if card.get("status") == "active"]
        self.state = {
            "turn": 0,
            "players": {
                player: {
                    "id": player,
                    "function_deck": list(function_ids),
                    "hand": [],
                    "discard": [],
                }
                for player in players
            },
            "event_pool": list(event_ids),
            "injected_event_pool": [],
            "event_history": [],
            "turn_log": [],
            "last_event": None,
        }
        for player_state in self.state["players"].values():
            self.random.shuffle(player_state["function_deck"])
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        state = deepcopy(self.state)
        state["counts"] = {
            "event_pool": len(state["event_pool"]),
            "injected_event_pool": len(state["injected_event_pool"]),
            "players": {
                player: {
                    "deck": len(payload["function_deck"]),
                    "hand": len(payload["hand"]),
                    "discard": len(payload["discard"]),
                }
                for player, payload in state["players"].items()
            },
        }
        return state

    def bootstrap(self) -> Dict[str, Any]:
        return {
            "metadata": self.data["metadata"],
            "players": self.data["npc_factions"]["major_playable_factions"],
            "npc_factions": self.data["npc_factions"]["npc_factions"],
            "foreign_powers": self.data["foreign_powers"],
            "card_pool_rules": self.data["card_pool_rules"],
            "unit_stats": self.data["unit_stats"],
            "tactics": self.data["tactics"],
            "general_traits": self.data["general_traits"],
            "general_skills": self.data["general_skills"],
            "cards": {
                "event": self.data["event_cards"]["cards"],
                "function": self.data["function_cards"]["cards"],
                "injected_event": self.data["injected_event_cards"]["cards"],
            },
        }

    def next_turn(self) -> Dict[str, Any]:
        self.state["turn"] += 1
        turn_entry = {
            "turn": self.state["turn"],
            "event": self.draw_event()["card"],
            "function_draws": {},
        }
        for player in self.state["players"]:
            turn_entry["function_draws"][player] = self.draw_function(player)["card"]
        self.state["turn_log"].append(turn_entry)
        return {"turn": turn_entry, "state": self.snapshot()}

    def draw_event(self) -> Dict[str, Any]:
        card_id = self._weighted_event_choice()
        card = self._card_template(card_id)
        entry = {"turn": self.state["turn"], "card": card}
        self.state["event_history"].append(entry)
        self.state["last_event"] = card
        return {"card": card, "state": self.snapshot()}

    def draw_function(self, player: str) -> Dict[str, Any]:
        player_state = self._player(player)
        if not player_state["function_deck"]:
            player_state["function_deck"] = player_state["discard"]
            player_state["discard"] = []
            self.random.shuffle(player_state["function_deck"])
        if not player_state["function_deck"]:
            raise ValueError("function deck is empty")
        card_id = player_state["function_deck"].pop()
        player_state["hand"].append(card_id)
        return {"card": self._card_template(card_id), "state": self.snapshot()}

    def use_function(self, player: str, card_id: str) -> Dict[str, Any]:
        player_state = self._player(player)
        if card_id not in player_state["hand"]:
            raise ValueError(f"{card_id!r} is not in {player}'s hand")
        player_state["hand"].remove(card_id)
        player_state["discard"].append(card_id)
        card = self._card_template(card_id)
        injected = []
        for generated in card.get("generated_event_cards", []):
            generated_id = str(generated["id"])
            template = self._card_template(generated_id)
            copies = int(generated.get("copies", 1))
            for _ in range(max(copies, 1)):
                self.state["event_pool"].append(generated_id)
                self.state["injected_event_pool"].append(generated_id)
            injected.append(template)
        return {"card": card, "injected": injected, "state": self.snapshot()}

    def _player(self, player: str) -> Dict[str, Any]:
        if player not in self.state["players"]:
            raise ValueError(f"unknown player {player!r}")
        return self.state["players"][player]

    def _weighted_event_choice(self) -> str:
        if not self.state["event_pool"]:
            raise ValueError("event pool is empty")
        weighted = []
        for card_id in self.state["event_pool"]:
            card = self._card_template(card_id)
            weight = float(card.get("base_weight") or 1)
            weighted.append((card_id, max(weight, 1.0)))
        total = sum(weight for _, weight in weighted)
        pick = self.random.random() * total
        cursor = 0.0
        for card_id, weight in weighted:
            cursor += weight
            if pick <= cursor:
                return card_id
        return weighted[-1][0]

    def _card_template(self, card_id: str) -> Dict[str, Any]:
        indexes = self.data["indexes"]
        for index_name in ("event_cards", "function_cards", "injected_event_cards"):
            if card_id in indexes[index_name]:
                return deepcopy(indexes[index_name][card_id])
        raise ValueError(f"unknown card id: {card_id}")
