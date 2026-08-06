"""In-memory turn and card-pool engine for playtesting."""

from __future__ import annotations

import random
import math
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from .data_store import load_game_data

from economy import LoanBook, scaled_city_value, treaty_port_bonus, is_settlement_turn
from economy.loans import TIER_BLOCKED
from foreign_powers.relations import RELATION_KEYS, clamp as clamp_relation, relation_bounds, starting_relations

LOANS = LoanBook()


DEFAULT_PLAYERS = ("F", "W", "S", "N")
MAX_HAND_SIZE = 6
FUNCTION_CARD_DRAW_COST = 5
FUNCTION_CARD_DRAW_LIMIT = 2
FOREIGN_RELATION_MIN, FOREIGN_RELATION_MAX = relation_bounds()
WARLORD_CODES = ("F", "W", "S", "N", "Y", "G", "M", "H", "C", "D", "Q")
UNIT_TYPES = ("infantry", "cavalry", "machine_gun", "artillery")
RECRUIT_COSTS = {
    "infantry": {"cash": 3, "factory": 1},
    "cavalry": {"cash": 6, "factory": 1},
    "machine_gun": {"cash": 9, "factory": 3},
    "artillery": {"cash": 14, "factory": 4},
}
LOYALTY_FUNCTION_CARD_IDS = ("unit_promotion", "local_autonomy_agitation")
ABSOLUTE_LOYAL_GENERAL_IDS = {
    "zhang_xueliang",
    "jin_yun_e",
    "li_houji",
    "he_yingqin",
}
FUNCTION_CARD_COPIES = {
    "unit_promotion": 4,
    "local_autonomy_agitation": 4,
    "reserve_gift_infantry": 4,
    "reserve_gift_cavalry": 2,
    "reserve_gift_machine_gun": 2,
    "reserve_gift_artillery": 1,
    "city_development": 8,
    "intel_network": 6,
    "police_system": 4,
    "communist_riot": 3,
    "qing_gang_riot": 3,
    "antiwar_speech_infantry": 5,
    "antiwar_speech_cavalry": 2,
    "antiwar_speech_machine_gun": 2,
    "antiwar_speech_artillery": 1,
    "zhili_infantry_drill": 2,
    "anti_fengtian_alignment": 2,
    "marshal_gratitude": 2,
    "whampoa_spirit": 2,
    "northern_expedition_oath": 2,
    "overseas_chinese_remittance": 2,
    "first_united_front": 1,
    "northeast_army_rearmament": 2,
    "young_marshal_rises": 1,
    "wang_yongjiang_financial_reform": 1,
    "zhili_anti_communist_declaration": 1,
    "forced_march": 4,
    "foreign_relation_jp": 4,
    "foreign_relation_su": 4,
    "foreign_relation_uk": 4,
    "foreign_relation_fr": 4,
    "foreign_relation_us": 4,
}
FOREIGN_FRIENDLY_THRESHOLD = 7
FOREIGN_HOSTILE_THRESHOLD = 3
FOREIGN_PERK_CARD_COPIES = 1
FOREIGN_CONDEMNATION_COPIES = 3
FOREIGN_PERK_CARDS = {
    "jp": [
        "jp_mitsui_arms_shipment",
        "jp_yokohama_specie_loan",
        "jp_infantry_drill_mission",
        "jp_south_manchuria_engineers",
    ],
    "su": [
        "su_rifle_shipment",
        "su_ruble_subsidy",
        "su_galen_advisers",
        "su_military_academy_mission",
    ],
    "uk": [
        "uk_vickers_contract",
        "uk_hsbc_credit",
        "uk_machine_gun_advisers",
        "uk_customs_advisers",
    ],
    "fr": [
        "fr_mountain_gun_mission",
        "fr_banque_indochine_credit",
        "fr_artillery_school",
        "fr_concession_engineers",
    ],
    "us": [
        "us_browning_samples",
        "us_commercial_credit",
        "us_firepower_doctrine",
        "us_industrial_engineers",
    ],
}
FOREIGN_CONDEMNATION_CARDS = {
    "jp": "jp_condemnation",
    "su": "su_condemnation",
    "uk": "uk_condemnation",
    "fr": "fr_condemnation",
    "us": "us_condemnation",
}
FEATURES = {
    "events": False,
    "function_cards": True,
    "event_interval": 3,
    "function_card_draw_cost": FUNCTION_CARD_DRAW_COST,
    "function_card_purchase_limit": FUNCTION_CARD_DRAW_LIMIT,
    "function_card_max_hand_size": MAX_HAND_SIZE,
}
NORTHEAST_PROVINCES = {"奉天", "吉林", "黑龍江"}


FACTION_PROFILES = {
    "F": {
        "treasury": 75,
        "income": 55,
        "unit_reserve": 41,
        "unit_reserves": {"infantry": 27, "cavalry": 7, "machine_gun": 4, "artillery": 3},
        "recruitment_cost_modifier": 1.10,
    },
    "W": {
        "treasury": 50,
        "income": 40,
        "unit_reserve": 30,
        "unit_reserves": {"infantry": 20, "cavalry": 5, "machine_gun": 3, "artillery": 2},
        "recruitment_cost_modifier": 1.00,
    },
    "S": {
        "treasury": 65,
        "income": 58,
        "unit_reserve": 34,
        "unit_reserves": {"infantry": 23, "cavalry": 4, "machine_gun": 4, "artillery": 3},
        "recruitment_cost_modifier": 0.95,
    },
    "N": {
        "treasury": 40,
        "income": 34,
        "unit_reserve": 25,
        "unit_reserves": {"infantry": 18, "cavalry": 3, "machine_gun": 2, "artillery": 2},
        "recruitment_cost_modifier": 0.90,
    },
}


class GameEngine:
    def __init__(self, *, seed: Optional[int] = None, data: Optional[Dict[str, Any]] = None) -> None:
        self.data = data or load_game_data()
        self.random = random.Random(seed)
        self.state = self.new_game(seed=seed)

    def new_game(self, *, players: Iterable[str] = DEFAULT_PLAYERS, seed: Optional[int] = None) -> Dict[str, Any]:
        if seed is not None:
            self.random.seed(seed)
        card_ids = {card["id"] for card in self.data["function_cards"]["cards"]}
        event_ids = [card["id"] for card in self.data["event_cards"]["cards"] if card.get("status") == "active"]
        cities = self.data["strategic_map"]["cities"]

        def player_state(player: str) -> Dict[str, Any]:
            profile = deepcopy(FACTION_PROFILES.get(player, {}))
            function_ids = [
                card_id
                for card_id, copies in FUNCTION_CARD_COPIES.items()
                if card_id in card_ids and self._card_allowed_for_player(card_id, player)
                for _ in range(copies)
            ]
            city_economy = [
                {
                    "id": city["id"],
                    "name": city["name"],
                    "province": city["province"],
                    "cash": scaled_city_value(city, "cash"),
                    "factory": scaled_city_value(city, "factory"),
                }
                for city in cities
                if city["faction"] == player
            ]
            profile["city_economy"] = city_economy
            profile["income"] = sum(city["cash"] for city in city_economy)
            profile["factory_income"] = sum(city["factory"] for city in city_economy)
            profile["factory_points"] = profile["factory_income"]
            profile["warlord_relations"] = {
                code: {
                    "status": "peace" if code in DEFAULT_PLAYERS else "war",
                    "war_started_turn": None if code in DEFAULT_PLAYERS else 0,
                    "permanent_war": code not in DEFAULT_PLAYERS,
                }
                for code in WARLORD_CODES
                if code != player
            }
            profile["pending_deals"] = []
            profile["army_reinforcements"] = {}
            profile["id"] = player
            profile["function_deck"] = list(function_ids)
            profile["hand"] = []
            profile["discard"] = []
            profile["pending_draw"] = None
            profile["function_purchase_count"] = 0
            profile["function_purchase_used"] = False
            profile["timed_effects"] = []
            profile["last_debt_service"] = None
            profile["permanent_output_bonus"] = {"cash": 0, "factory": 0}
            profile["foreign_relations"] = starting_relations(player)
            profile["loans"] = []
            profile["next_loan_id"] = 1
            profile["debt"] = 0
            return profile

        self.state = {
            "turn": 0,
            "players": {player: player_state(player) for player in players},
            "city_owners": {city["id"]: city["faction"] for city in cities},
            "city_development": {},
            "city_output_effects": [],
            "npc_accounts": {
                code: {
                    "treasury": 60,
                    "unit_reserves": {"infantry": 20, "cavalry": 5, "machine_gun": 3, "artillery": 2},
                }
                for code in WARLORD_CODES
                if code not in DEFAULT_PLAYERS
            },
            "event_pool": list(event_ids),
            "injected_event_pool": [],
            "event_history": [],
            "turn_log": [],
            "last_event": None,
            "last_action": None,
            "recurring_effects": [],
            "last_economy_log": {},
            "next_deal_id": 1,
        }
        for player in self.state["players"]:
            self._sync_foreign_deck_cards(player)
            self.random.shuffle(self.state["players"][player]["function_deck"])
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
                    "pending_draw": 1 if payload.get("pending_draw") else 0,
                    "function_purchase_used": 1 if int(payload.get("function_purchase_count", 0)) > 0 else 0,
                    "function_purchase_count": int(payload.get("function_purchase_count", 0)),
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
            "strategic_map": self._strategic_map_snapshot(),
            "recruit_costs": RECRUIT_COSTS,
            "features": FEATURES,
            "cards": {
                "event": self.data["event_cards"]["cards"],
                "function": self.data["function_cards"]["cards"],
                "injected_event": self.data["injected_event_cards"]["cards"],
            },
        }

    def next_turn(
        self,
        active_player: Optional[str] = None,
        *,
        force: bool = False,
        riot_garrisons: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        if active_player is not None:
            self._player(active_player)
        blocked_players = [
            player
            for player, payload in self.state["players"].items()
            if FEATURES["function_cards"] and payload.get("pending_draw")
        ]
        if blocked_players:
            if force:
                for player in blocked_players:
                    payload = self.state["players"][player]
                    payload["discard"].append(payload["pending_draw"])
                    payload["pending_draw"] = None
            else:
                names = ", ".join(blocked_players)
                raise ValueError(f"players must resolve pending card draws first: {names}")
        self.state["turn"] += 1
        self.state["last_event"] = None
        self._update_qing_gang_riots(riot_garrisons or {})
        economy_log = self._apply_turn_economy()
        self._tick_timed_effects()
        for player, payload in self.state["players"].items():
            payload["function_purchase_count"] = 0
            payload["function_purchase_used"] = False
            self._sync_foreign_deck_cards(player)
        turn_entry = {
            "turn": self.state["turn"],
            "event": None,
            "function_purchase_offer": active_player if FEATURES["function_cards"] else None,
            "economy": economy_log,
        }
        if FEATURES["events"] and self.state["turn"] % FEATURES["event_interval"] == 0:
            turn_entry["event"] = self.draw_event()["card"]
        self.state["turn_log"].append(turn_entry)
        return {"turn": turn_entry, "state": self.snapshot()}

    def _apply_turn_economy(self) -> Dict[str, Any]:
        self._refresh_city_income()
        turn = int(self.state["turn"])
        log: Dict[str, Any] = {}
        for player, payload in self.state["players"].items():
            loans = payload.setdefault("loans", [])
            relations = payload.get("foreign_relations", {})
            debt_before = LOANS.total_outstanding(loans)

            # 3.4 — one turn of interest on every loan, before anything else happens.
            interest = LOANS.accrue_interest(loans)

            # 3.6.1 — a power that has turned hostile calls its loans in.
            called_in = []
            for bank in LOANS.data["banks"]:
                if bank.get("neutral"):
                    continue
                relation = int(relations.get(bank["relations_key"], 0))
                if LOANS.tier_for_relation(relation) == TIER_BLOCKED:
                    called_in.extend(loan["id"] for loan in LOANS.call_in_bank(loans, bank["id"]))

            # 3.5 — anything past its due turn stops being the player's choice.
            LOANS.mark_overdue(loans, turn)

            gross_income = int(payload.get("income", 0))
            seized_cash = 0
            seized_income = 0
            arrears = LOANS.overdue_outstanding(loans)
            if arrears > 0:
                on_hand = int(payload.get("treasury", 0))
                if on_hand > 0:
                    result = LOANS.repay(loans, min(on_hand, arrears), overdue_only=True)
                    seized_cash = result["paid"]
                    payload["treasury"] = on_hand - seized_cash
                remaining = LOANS.overdue_outstanding(loans)
                if remaining > 0 and gross_income > 0:
                    result = LOANS.repay(loans, min(gross_income, remaining), overdue_only=True)
                    seized_income = result["paid"]

            net_income = gross_income - seized_income
            payload["treasury"] += net_income
            payload["factory_points"] += int(payload.get("factory_income", 0))
            payload["debt"] = LOANS.total_outstanding(loans)
            service = {
                "gross_income": gross_income,
                "interest": interest,
                "seized_cash": seized_cash,
                "seized_income": seized_income,
                "forced_repayment": seized_cash + seized_income,
                "net_income": net_income,
                "debt_before": debt_before,
                "debt_after": payload["debt"],
                "overdue": LOANS.overdue_outstanding(loans),
                "called_in": called_in,
                "cash_effects": [],
            }
            payload["last_debt_service"] = service
            log[player] = deepcopy(service)

        for player, bonus in self._treaty_port_bonuses().items():
            payload = self.state["players"][player]
            payload["treasury"] += bonus["cash"]
            payload["factory_points"] += bonus["factory"]
            entry = {
                "name": "租界與港口加成",
                "amount": bonus["cash"],
                "factory": bonus["factory"],
                "cities": bonus["cities"],
            }
            payload["last_debt_service"].setdefault("cash_effects", []).append(entry)
            log[player].setdefault("cash_effects", []).append(entry)

        for reward in self._qing_gang_riot_rewards():
            initiator = reward["initiator"]
            if initiator not in self.state["players"]:
                continue
            self.state["players"][initiator]["treasury"] += reward["cash"]
            self.state["players"][initiator]["factory_points"] += reward["factory"]
            entry = {
                "effect_id": reward["id"],
                "name": reward["name"],
                "amount": reward["cash"],
                "factory": reward["factory"],
            }
            self.state["players"][initiator]["last_debt_service"].setdefault("cash_effects", []).append(entry)
            log[initiator].setdefault("cash_effects", []).append(entry)

        active_recurring = []
        for effect in self.state.get("recurring_effects", []):
            if int(effect.get("remaining_turns", 0)) <= 0:
                continue
            entries = []
            for player, amount in effect.get("cash_deltas", {}).items():
                if player not in self.state["players"]:
                    continue
                amount = int(amount)
                self.state["players"][player]["treasury"] += amount
                entry = {"effect_id": effect.get("id"), "name": effect.get("name"), "amount": amount}
                self.state["players"][player]["last_debt_service"].setdefault("cash_effects", []).append(entry)
                log[player].setdefault("cash_effects", []).append(entry)
                entries.append({"player": player, "amount": amount})
            effect["remaining_turns"] = int(effect.get("remaining_turns", 0)) - 1
            if effect["remaining_turns"] > 0:
                active_recurring.append(effect)
        self.state["recurring_effects"] = active_recurring
        self.state["last_economy_log"] = log
        return log

    def _tick_timed_effects(self) -> None:
        for payload in self.state["players"].values():
            active_effects = []
            for effect in payload.get("timed_effects", []):
                remaining = int(effect.get("remaining_turns", 0)) - 1
                if remaining > 0:
                    effect["remaining_turns"] = remaining
                    active_effects.append(effect)
            payload["timed_effects"] = active_effects
        active_city_effects = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") == "qing_gang_riot":
                active_city_effects.append(effect)
                continue
            remaining = int(effect.get("remaining_turns", 0)) - 1
            if remaining > 0:
                effect["remaining_turns"] = remaining
                active_city_effects.append(effect)
        self.state["city_output_effects"] = active_city_effects
        self._refresh_city_income()

    def _strategic_map_snapshot(self) -> Dict[str, Any]:
        strategic_map = deepcopy(self.data["strategic_map"])
        for city in strategic_map.get("cities", []):
            bonus = self.state.get("city_development", {}).get(city["id"], {})
            cash, factory = self._adjusted_city_output(
                city["id"],
                scaled_city_value(city, "cash") + int(bonus.get("cash", 0)),
                scaled_city_value(city, "factory") + int(bonus.get("factory", 0)),
            )
            city["cash"] = cash
            city["factory"] = factory
            city["faction"] = self.state.get("city_owners", {}).get(city["id"], city["faction"])
        return strategic_map

    def _treaty_port_bonuses(self) -> Dict[str, Dict[str, Any]]:
        """租界與港口加成，結算週期見 economy/output.py。"""
        if not is_settlement_turn(int(self.state["turn"])):
            return {}
        bonuses: Dict[str, Dict[str, Any]] = {}
        for city in self.data["strategic_map"]["cities"]:
            bonus = treaty_port_bonus(city)
            cash, factory = bonus["cash"], bonus["factory"]
            if not cash and not factory:
                continue
            owner = self.state["city_owners"].get(city["id"], city["faction"])
            if owner not in self.state["players"]:
                continue
            entry = bonuses.setdefault(owner, {"cash": 0, "factory": 0, "cities": []})
            entry["cash"] += cash
            entry["factory"] += factory
            entry["cities"].append(city["name"])
        return bonuses

    def _city_economy_for(self, player: str) -> list[Dict[str, Any]]:
        development = self.state.get("city_development", {})
        economy = []
        for city in self.data["strategic_map"]["cities"]:
            if self.state["city_owners"].get(city["id"], city["faction"]) != player:
                continue
            cash, factory = self._adjusted_city_output(
                city["id"],
                scaled_city_value(city, "cash") + int(development.get(city["id"], {}).get("cash", 0)),
                scaled_city_value(city, "factory") + int(development.get(city["id"], {}).get("factory", 0)),
            )
            economy.append({
                "id": city["id"],
                "name": city["name"],
                "province": city["province"],
                "cash": cash,
                "factory": factory,
            })
        return economy

    def _refresh_city_income(self) -> None:
        for player, payload in self.state["players"].items():
            city_economy = self._city_economy_for(player)
            bonus = payload.get("permanent_output_bonus", {})
            payload["city_economy"] = city_economy
            payload["income"] = sum(item["cash"] for item in city_economy) + int(bonus.get("cash", 0))
            payload["factory_income"] = sum(item["factory"] for item in city_economy) + int(bonus.get("factory", 0))

    def capture_city(self, city_id: str, faction: str) -> Dict[str, Any]:
        if faction not in WARLORD_CODES:
            raise ValueError(f"unknown faction {faction!r}")
        city = next(
            (item for item in self.data["strategic_map"]["cities"] if item["id"] == city_id),
            None,
        )
        if city is None:
            raise ValueError(f"unknown city {city_id!r}")

        previous_owner = self.state["city_owners"].get(city_id, city["faction"])
        self.state["city_owners"][city_id] = faction
        self._refresh_city_income()

        return {
            "city": {
                "id": city["id"],
                "name": city["name"],
                **dict(zip(("cash", "factory"), self._adjusted_city_output(
                    city["id"],
                    scaled_city_value(city, "cash")
                    + int(self.state.get("city_development", {}).get(city["id"], {}).get("cash", 0)),
                    scaled_city_value(city, "factory")
                    + int(self.state.get("city_development", {}).get(city["id"], {}).get("factory", 0)),
                ))),
            },
            "previous_owner": previous_owner,
            "owner": faction,
            "state": self.snapshot(),
        }

    def recruit_captive_general(self, player: str) -> Dict[str, Any]:
        player_state = self._player(player)
        infantry_cost = 5
        if player_state["unit_reserves"].get("infantry", 0) < infantry_cost:
            raise ValueError("recruiting a captive general requires 5 infantry reserves")
        player_state["unit_reserves"]["infantry"] -= infantry_cost
        player_state["unit_reserve"] = sum(player_state["unit_reserves"].values())
        return {"infantry": infantry_cost, "state": self.snapshot()}

    def attempt_defection(self, player: str, loyalty: int) -> Dict[str, Any]:
        return self.attempt_defection_with_force(player, loyalty, 1)

    def attempt_defection_with_force(self, player: str, loyalty: int, force: float) -> Dict[str, Any]:
        player_state = self._player(player)
        loyalty = max(1, min(10, int(loyalty)))
        force = max(1.0, float(force))
        cost = int(math.ceil((10 + force * 3 + loyalty * 2) * 0.5))
        if player_state.get("treasury", 0) < cost:
            raise ValueError(f"defection attempt requires {cost} cash")
        player_state["treasury"] -= cost
        base_chance = 0.45 - loyalty * 0.04 - force * 0.003
        chance = max(0.03, min(0.60, base_chance * 1.25))
        roll = self.random.random()
        return {
            "success": roll < chance,
            "cost": cost,
            "chance": chance,
            "roll": roll,
            "state": self.snapshot(),
        }

    def draw_event(self) -> Dict[str, Any]:
        card_id = self._weighted_event_choice()
        card = self._card_template(card_id)
        entry = {"turn": self.state["turn"], "card": card}
        self.state["event_history"].append(entry)
        self.state["last_event"] = card
        return {"card": card, "state": self.snapshot()}

    def draw_function(self, player: str) -> Dict[str, Any]:
        player_state = self._player(player)
        self._sync_foreign_deck_cards(player)
        if player_state.get("pending_draw"):
            raise ValueError(f"{player!r} must discard a card before drawing again")
        if int(player_state.get("function_purchase_count", 0)) >= FUNCTION_CARD_DRAW_LIMIT:
            raise ValueError("function card purchase limit reached for this turn")
        if not player_state["function_deck"]:
            player_state["function_deck"] = player_state["discard"]
            player_state["discard"] = []
            self.random.shuffle(player_state["function_deck"])
        if not player_state["function_deck"]:
            raise ValueError("function deck is empty")
        if player_state.get("treasury", 0) < FUNCTION_CARD_DRAW_COST:
            raise ValueError(f"drawing a function card requires {FUNCTION_CARD_DRAW_COST} cash")
        player_state["treasury"] -= FUNCTION_CARD_DRAW_COST
        player_state["function_purchase_count"] = int(player_state.get("function_purchase_count", 0)) + 1
        player_state["function_purchase_used"] = True
        card_id = player_state["function_deck"].pop()
        requires_discard = len(player_state["hand"]) >= MAX_HAND_SIZE
        if requires_discard:
            player_state["pending_draw"] = card_id
        else:
            player_state["hand"].append(card_id)
        return {
            "card": self._card_template(card_id),
            "requires_discard": requires_discard,
            "draw_cost": FUNCTION_CARD_DRAW_COST,
            "state": self.snapshot(),
        }

    def discard_for_draw(self, player: str, card_id: str) -> Dict[str, Any]:
        player_state = self._player(player)
        pending_card = player_state.get("pending_draw")
        if not pending_card:
            raise ValueError(f"{player!r} has no pending card draw")
        if card_id not in player_state["hand"]:
            raise ValueError(f"{card_id!r} is not in {player}'s hand")
        player_state["hand"].remove(card_id)
        player_state["discard"].append(card_id)
        player_state["hand"].append(pending_card)
        player_state["pending_draw"] = None
        return {
            "discarded": self._card_template(card_id),
            "received": self._card_template(pending_card),
            "state": self.snapshot(),
        }

    def use_function(
        self,
        player: str,
        card_id: str,
        *,
        target_general_id: Optional[str] = None,
        target_owner: Optional[str] = None,
        target_city_id: Optional[str] = None,
        target_province: Optional[str] = None,
    ) -> Dict[str, Any]:
        player_state = self._player(player)
        if card_id not in player_state["hand"]:
            raise ValueError(f"{card_id!r} is not in {player}'s hand")
        card = self._card_template(card_id)
        self._validate_card_use(player, card)
        mechanic = card.get("mechanic") or ("loyalty" if card_id in LOYALTY_FUNCTION_CARD_IDS else None)
        if mechanic is None:
            raise ValueError("this function card is not implemented in the playtest rules")
        cost = 0
        loyalty_delta = 0
        loyalty_delta_all: Optional[Dict[str, Any]] = None
        loyalty_swings: list[Dict[str, Any]] = []
        reserve_delta: Optional[Dict[str, Any]] = None
        reserve_deltas: list[Dict[str, Any]] = []
        army_unit_delta: Optional[Dict[str, Any]] = None
        city_development: Optional[Dict[str, Any]] = None
        city_developments: list[Dict[str, Any]] = []
        permanent_output_delta: Optional[Dict[str, Any]] = None
        cash_delta = 0
        debt_delta = 0
        foreign_relation_delta: Optional[Dict[str, Any]] = None
        timed_effect: Optional[Dict[str, Any]] = None
        recurring_effect: Optional[Dict[str, Any]] = None
        city_disruption: Optional[Dict[str, Any]] = None
        if mechanic == "loyalty":
            if not target_general_id or not target_owner:
                raise ValueError("a target general is required")
            if target_general_id in ABSOLUTE_LOYAL_GENERAL_IDS:
                raise ValueError("this general has absolute loyalty and cannot be changed by function cards")
            if card_id == "unit_promotion" and target_owner != player:
                raise ValueError("unit promotion must target your own general")
            if card_id == "local_autonomy_agitation" and target_owner == player:
                raise ValueError("local autonomy agitation must target an opposing general")
            loyalty_delta = 1 if card_id == "unit_promotion" else -1
        elif mechanic == "reserve_gain":
            unit_type = str(card["unit_type"])
            amount = self.random.randint(int(card.get("min_units", 2)), int(card.get("max_units", 5)))
            self._add_reserve(player, unit_type, amount)
            reserve_delta = {"owner": player, "unit_type": unit_type, "amount": amount}
            reserve_deltas.append(reserve_delta)
        elif mechanic == "reserve_loss":
            if not target_owner or target_owner == player or target_owner not in self.state["players"]:
                raise ValueError("antiwar speech must target another playable faction")
            target_state = self._player(target_owner)
            unit_type = str(card["unit_type"])
            requested = self.random.randint(int(card.get("min_units", 3)), int(card.get("max_units", 5)))
            amount = min(requested, int(target_state["unit_reserves"].get(unit_type, 0)))
            self._add_reserve(target_owner, unit_type, -amount)
            reserve_delta = {"owner": target_owner, "unit_type": unit_type, "amount": -amount}
            reserve_deltas.append(reserve_delta)
        elif mechanic == "city_development":
            if not target_city_id:
                raise ValueError("city development requires a controlled target city")
            city_entry = next((item for item in player_state.get("city_economy", []) if item["id"] == target_city_id), None)
            if city_entry is None:
                raise ValueError("city development must target your controlled city")
            cash = self.random.randint(int(card.get("min_cash", 1)), int(card.get("max_cash", 3)))
            factory = self.random.randint(int(card.get("min_factory", 1)), int(card.get("max_factory", 2)))
            bonus = self.state.setdefault("city_development", {}).setdefault(target_city_id, {"cash": 0, "factory": 0})
            bonus["cash"] += cash
            bonus["factory"] += factory
            self._refresh_city_income()
            city_development = {"city_id": target_city_id, "cash": cash, "factory": factory}
            city_developments.append(city_development)
        elif mechanic == "joint_reserve_gain":
            for owner in card.get("owners", []):
                for unit_type, amount in card.get("unit_reserves", {}).items():
                    self._add_reserve(str(owner), str(unit_type), int(amount))
                    reserve_deltas.append({"owner": str(owner), "unit_type": str(unit_type), "amount": int(amount)})
            reserve_delta = reserve_deltas[0] if reserve_deltas else None
        elif mechanic == "timed_combat_effect":
            owners = card.get("effect_owners") or [player]
            duration = int(card.get("duration_turns", 1))
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "combat_modifier",
                "remaining_turns": duration,
                "owners": [str(owner) for owner in owners],
                "target_faction": card.get("target_faction"),
                "modifiers": deepcopy(card.get("modifiers", [])),
            }
            for owner in owners:
                self._player(str(owner)).setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "recurring_cash_transfer":
            recurring_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "remaining_turns": int(card.get("duration_turns", 1)),
                "cash_deltas": deepcopy(card.get("cash_deltas", {})),
            }
            self.state.setdefault("recurring_effects", []).append(recurring_effect)
        elif mechanic == "reserve_debt_bundle":
            debt_delta = int(card.get("debt", 0))
            self._record_card_loan(player, card, debt_delta)
            for unit_type, amount in card.get("unit_reserves", {}).items():
                self._add_reserve(player, str(unit_type), int(amount))
                reserve_deltas.append({"owner": player, "unit_type": str(unit_type), "amount": int(amount)})
            reserve_delta = reserve_deltas[0] if reserve_deltas else None
        elif mechanic == "loyalty_all":
            loyalty_delta_all = {"owner": player, "amount": int(card.get("loyalty_delta", 0))}
        elif mechanic == "loyalty_swing":
            for swing in card.get("loyalty_swings", []):
                owners = swing.get("owners")
                if owners == "other_players":
                    owners = [item for item in DEFAULT_PLAYERS if item != player]
                elif owners == "self":
                    owners = [player]
                for owner in owners or []:
                    loyalty_swings.append({"owner": str(owner), "amount": int(swing.get("amount", 0))})
        elif mechanic == "cash_gain":
            cash_delta = int(card.get("cash", 0))
            player_state["treasury"] += cash_delta
        elif mechanic == "reserve_bundle":
            for unit_type, amount in card.get("unit_reserves", {}).items():
                self._add_reserve(player, str(unit_type), int(amount))
                reserve_deltas.append({"owner": player, "unit_type": str(unit_type), "amount": int(amount)})
            reserve_delta = reserve_deltas[0] if reserve_deltas else None
        elif mechanic == "regional_city_development":
            cash = int(card.get("cash", 0))
            factory = int(card.get("factory", 0))
            provinces = set(card.get("provinces") or NORTHEAST_PROVINCES)
            for city in self.data["strategic_map"]["cities"]:
                owner = self.state["city_owners"].get(city["id"], city["faction"])
                if owner != player or city.get("province") not in provinces:
                    continue
                bonus = self.state.setdefault("city_development", {}).setdefault(city["id"], {"cash": 0, "factory": 0})
                bonus["cash"] += cash
                bonus["factory"] += factory
                city_developments.append({"city_id": city["id"], "cash": cash, "factory": factory})
            self._refresh_city_income()
            city_development = city_developments[0] if city_developments else None
        elif mechanic == "debt_cash":
            debt_delta = int(card.get("debt", 0))
            cash_delta = int(card.get("cash", 0))
            self._record_card_loan(player, card, debt_delta)
            player_state["treasury"] += cash_delta
        elif mechanic == "army_unit_bundle":
            army_unit_delta = {
                "owner": player,
                "general_id": str(card.get("target_general_id", "")),
                "unit_reserves": deepcopy(card.get("unit_reserves", {})),
                "requires_active": bool(card.get("requires_active", True)),
            }
        elif mechanic == "permanent_player_output":
            bonus = player_state.setdefault("permanent_output_bonus", {"cash": 0, "factory": 0})
            cash = int(card.get("cash", 0))
            factory = int(card.get("factory", 0))
            bonus["cash"] = int(bonus.get("cash", 0)) + cash
            bonus["factory"] = int(bonus.get("factory", 0)) + factory
            self._refresh_city_income()
            permanent_output_delta = {"owner": player, "cash": cash, "factory": factory}
        elif mechanic == "foreign_relation_delta":
            power = str(card.get("foreign_power_key", ""))
            if power not in player_state.get("foreign_relations", {}):
                raise ValueError("unknown foreign power relation")
            amount = int(card.get("relation_delta", 0))
            before = int(player_state["foreign_relations"].get(power, 0))
            after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + amount))
            player_state["foreign_relations"][power] = after
            foreign_relation_delta = {"power": power, "before": before, "after": after, "amount": after - before}
            self._sync_foreign_deck_cards(player)
        elif mechanic == "rail_movement":
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "rail_movement",
                "remaining_turns": int(card.get("duration_turns", 1)),
                "owners": [player],
                "tiles": int(card.get("tiles", 3)),
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "rural_movement":
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "rural_movement",
                "remaining_turns": int(card.get("duration_turns", 1)),
                "owners": [player],
                "tiles": int(card.get("tiles", 2)),
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "intel_network":
            province = str(target_province or "").strip()
            if not province:
                raise ValueError("intel network requires a target province")
            duration = int(card.get("duration_turns", 1))
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "intel_network",
                "remaining_turns": duration,
                "owners": [player],
                "target_province": province,
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "police_system":
            duration = int(card.get("duration_turns", 3))
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "police_system",
                "remaining_turns": duration,
                "owners": [player],
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "communist_riot":
            if not target_owner or target_owner == player or target_owner not in self.state["players"]:
                raise ValueError("communist riot must target another playable faction")
            target_cities = list(self._player(target_owner).get("city_economy", []))
            if not target_cities:
                raise ValueError("target faction has no cities to disrupt")
            selected = self.random.sample(target_cities, k=min(2, len(target_cities)))
            city_disruption = {
                "id": card_id,
                "name": card.get("name", card_id),
                "target_owner": target_owner,
                "remaining_turns": int(card.get("duration_turns", 3)),
                "city_ids": [city["id"] for city in selected],
                "cities": [{"id": city["id"], "name": city["name"]} for city in selected],
                "cash_multiplier": float(card.get("cash_multiplier", 0)),
                "factory_multiplier": float(card.get("factory_multiplier", 0)),
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
        elif mechanic == "qing_gang_riot":
            if not target_owner or target_owner == player or target_owner not in self.state["players"]:
                raise ValueError("qing gang riot must target another playable faction")
            province = str(target_province or "").strip()
            if not province:
                raise ValueError("qing gang riot requires a target province")
            target_cities = [
                city
                for city in self.data["strategic_map"]["cities"]
                if city.get("province") == province
                and self.state["city_owners"].get(city["id"], city["faction"]) == target_owner
            ]
            if not target_cities:
                raise ValueError("target faction controls no cities in that province")
            city_disruption = {
                "id": f"{card_id}:{self.state['turn']}:{player}:{target_owner}:{province}",
                "card_id": card_id,
                "kind": "qing_gang_riot",
                "name": card.get("name", card_id),
                "initiator": player,
                "target_owner": target_owner,
                "province": province,
                "city_ids": [city["id"] for city in target_cities],
                "cities": [{"id": city["id"], "name": city["name"]} for city in target_cities],
                "cash_multiplier": 0,
                "factory_multiplier": 0,
                "reward_rate": float(card.get("reward_rate", 0.5)),
                "required_force": int(card.get("suppression_force", 15)),
                "required_turns": int(card.get("suppression_turns", 3)),
                "garrison_progress": 0,
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
        elif mechanic == "no_effect":
            pass
        else:
            raise ValueError("this function card is not implemented in the playtest rules")
        if card.get("loyalty_delta_all") is not None and loyalty_delta_all is None:
            loyalty_delta_all = {
                "owner": player,
                "amount": int(card.get("loyalty_delta_all", 0)),
            }
        player_state["treasury"] -= cost
        player_state["hand"].remove(card_id)
        player_state["discard"].append(card_id)
        self.state["last_action"] = {
            "type": "function_card",
            "player": player,
            "card": card,
            "target_general_id": target_general_id,
            "target_owner": target_owner,
            "loyalty_delta": loyalty_delta,
            "loyalty_delta_all": loyalty_delta_all,
            "loyalty_swings": loyalty_swings,
            "reserve_delta": reserve_delta,
            "reserve_deltas": reserve_deltas,
            "army_unit_delta": army_unit_delta,
            "city_development": city_development,
            "city_developments": city_developments,
            "permanent_output_delta": permanent_output_delta,
            "cash_delta": cash_delta,
            "debt_delta": debt_delta,
            "foreign_relation_delta": foreign_relation_delta,
            "timed_effect": timed_effect,
            "recurring_effect": recurring_effect,
            "city_disruption": city_disruption,
        }
        injected = []
        for generated in card.get("generated_event_cards", []):
            generated_id = str(generated["id"])
            template = self._card_template(generated_id)
            copies = int(generated.get("copies", 1))
            for _ in range(max(copies, 1)):
                self.state["event_pool"].append(generated_id)
                self.state["injected_event_pool"].append(generated_id)
            injected.append(template)
        return {
            "card": card,
            "injected": injected,
            "target_general_id": target_general_id,
            "target_owner": target_owner,
            "loyalty_delta": loyalty_delta,
            "loyalty_delta_all": loyalty_delta_all,
            "loyalty_swings": loyalty_swings,
            "reserve_delta": reserve_delta,
            "reserve_deltas": reserve_deltas,
            "army_unit_delta": army_unit_delta,
            "city_development": city_development,
            "city_developments": city_developments,
            "permanent_output_delta": permanent_output_delta,
            "cash_delta": cash_delta,
            "debt_delta": debt_delta,
            "foreign_relation_delta": foreign_relation_delta,
            "timed_effect": timed_effect,
            "recurring_effect": recurring_effect,
            "city_disruption": city_disruption,
            "state": self.snapshot(),
        }

    def set_diplomacy(
        self,
        player: str,
        target: str,
        status: str,
        *,
        peace_card_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if status not in ("peace", "war"):
            raise ValueError("diplomatic status must be 'peace' or 'war'")
        player_state = self._player(player)
        if target == player or target not in player_state["warlord_relations"]:
            raise ValueError(f"invalid warlord target: {target!r}")
        relation = player_state["warlord_relations"][target]
        if relation.get("permanent_war") or target not in DEFAULT_PLAYERS:
            raise ValueError("NPC factions are permanent enemies in this playtest")
        if status == "peace" and relation["status"] == "war":
            war_started = relation.get("war_started_turn")
            war_turns = self.state["turn"] - int(war_started or 0)
            if war_turns < 10:
                if not peace_card_id or peace_card_id not in player_state["hand"]:
                    raise ValueError(f"peace requires 10 turns of war ({war_turns}/10 completed)")
                peace_card = self._card_template(peace_card_id)
                peace_text = f"{peace_card.get('name', '')} {peace_card.get('effect', '')}".lower()
                if not any(term in peace_text for term in ("停戰", "議和", "和平", "peace", "truce")):
                    raise ValueError("the selected function card cannot authorize early peace")
                player_state["hand"].remove(peace_card_id)
                player_state["discard"].append(peace_card_id)
        war_started_turn = self.state["turn"] if status == "war" else None
        relation.update({"status": status, "war_started_turn": war_started_turn})
        if target in self.state["players"]:
            self.state["players"][target]["warlord_relations"][player].update(
                {"status": status, "war_started_turn": war_started_turn}
            )
        self.state["last_action"] = {
            "type": "diplomacy",
            "player": player,
            "target": target,
            "status": status,
        }
        return {"state": self.snapshot()}

    def make_deal(
        self,
        player: str,
        target: str,
        *,
        funds: int = 0,
        unit_type: Optional[str] = None,
        reserve: int = 0,
    ) -> Dict[str, Any]:
        source = self._player(player)
        if target == player or target not in source["warlord_relations"]:
            raise ValueError(f"invalid deal target: {target!r}")
        destination = self.state["players"].get(target)
        if destination is None:
            raise ValueError("deals can only be proposed to playable factions")
        funds = max(0, int(funds))
        reserve = max(0, int(reserve))
        if funds > source["treasury"]:
            raise ValueError("insufficient treasury for deal")
        if reserve:
            if unit_type not in UNIT_TYPES:
                raise ValueError("a valid unit type is required for reserve transfer")
            if reserve > source["unit_reserves"][unit_type]:
                raise ValueError("insufficient unit reserve for deal")
        if not funds and not reserve:
            raise ValueError("a deal must include funds or reserve units")
        deal_id = self.state["next_deal_id"]
        self.state["next_deal_id"] += 1
        proposal = {
            "id": deal_id,
            "from": player,
            "to": target,
            "funds": funds,
            "unit_type": unit_type if reserve else None,
            "reserve": reserve,
            "status": "pending",
            "turn": self.state["turn"],
        }
        destination["pending_deals"].append(proposal)
        self.state["last_action"] = {
            "type": "deal",
            "player": player,
            "target": target,
            "funds": funds,
            "unit_type": unit_type,
            "reserve": reserve,
            "deal_id": deal_id,
        }
        return {"deal": deepcopy(proposal), "state": self.snapshot()}

    def respond_to_deal(self, player: str, deal_id: int, accept: bool) -> Dict[str, Any]:
        destination = self._player(player)
        proposal = next(
            (deal for deal in destination["pending_deals"] if deal["id"] == int(deal_id)),
            None,
        )
        if proposal is None:
            raise ValueError(f"unknown pending deal: {deal_id!r}")
        if accept:
            source = self._player(proposal["from"])
            funds = proposal["funds"]
            reserve = proposal["reserve"]
            unit_type = proposal["unit_type"]
            if funds > source["treasury"]:
                raise ValueError("sender no longer has enough treasury")
            if reserve > source["unit_reserves"].get(unit_type, 0):
                raise ValueError("sender no longer has enough reserve units")
            source["treasury"] -= funds
            destination["treasury"] += funds
            if reserve:
                source["unit_reserves"][unit_type] -= reserve
                destination["unit_reserves"][unit_type] += reserve
            source["unit_reserve"] = sum(source["unit_reserves"].values())
            destination["unit_reserve"] = sum(destination["unit_reserves"].values())
        destination["pending_deals"].remove(proposal)
        proposal["status"] = "accepted" if accept else "declined"
        self.state["last_action"] = {
            "type": "deal_response",
            "player": player,
            "deal": deepcopy(proposal),
        }
        return {"deal": proposal, "state": self.snapshot()}

    def train_unit(self, player: str, unit_type: str, count: int = 1) -> Dict[str, Any]:
        player_state = self._player(player)
        if unit_type not in RECRUIT_COSTS:
            raise ValueError(f"unknown unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("recruit count must be positive")
        cost = RECRUIT_COSTS[unit_type]
        cash_cost = math.ceil(cost["cash"] * player_state.get("recruitment_cost_modifier", 1)) * count
        factory_cost = cost["factory"] * count
        if player_state["treasury"] < cash_cost:
            raise ValueError("insufficient treasury")
        if player_state["factory_points"] < factory_cost:
            raise ValueError("insufficient factory points")
        player_state["treasury"] -= cash_cost
        player_state["factory_points"] -= factory_cost
        player_state["unit_reserves"][unit_type] += count
        player_state["unit_reserve"] = sum(player_state["unit_reserves"].values())
        return {"state": self.snapshot()}

    def reinforce_army(
        self,
        player: str,
        army_id: str,
        city_id: str,
        unit_type: str,
        count: int = 1,
    ) -> Dict[str, Any]:
        player_state = self._player(player)
        if unit_type not in RECRUIT_COSTS:
            raise ValueError(f"unknown unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("recruit count must be positive")
        city = next(
            (item for item in self.data["strategic_map"]["cities"] if item["id"] == city_id),
            None,
        )
        if not city or city["faction"] != player or city["level"] < 3:
            raise ValueError("reinforcement requires a controlled major city")
        if player_state["unit_reserves"][unit_type] < count:
            raise ValueError("insufficient unit reserve")
        player_state["unit_reserves"][unit_type] -= count
        player_state["unit_reserve"] = sum(player_state["unit_reserves"].values())
        reinforcement = player_state["army_reinforcements"].setdefault(
            army_id, {unit: 0 for unit in UNIT_TYPES}
        )
        reinforcement[unit_type] += count
        return {"state": self.snapshot()}

    # ---- 借款系統 ------------------------------------------------------

    CARD_BANKS = {
        "jp_yokohama_specie_loan": "yokohama_specie",
        "uk_hsbc_credit": "hsbc",
        "fr_banque_indochine_credit": "banque_de_l_indochine",
        "us_commercial_credit": "citibank",
        "su_ruble_subsidy": None,
    }

    def _next_loan_id(self, player: str) -> int:
        payload = self._player(player)
        loan_id = int(payload.get("next_loan_id", 1))
        payload["next_loan_id"] = loan_id + 1
        return loan_id

    def _record_card_loan(self, player: str, card: Dict[str, Any], amount: int) -> Optional[Dict[str, Any]]:
        """3.3 — a loan a function card hands out joins the same list as a bank loan.

        Card loans bypass the credit limit (the card is the negotiation) but take the
        bank's current terms, and fall back to 德華 when the card names no lender.
        """
        if amount <= 0:
            return None
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        bank_id = self.CARD_BANKS.get(str(card.get("id"))) or "deutsch_asiatische"
        relations = payload.get("foreign_relations", {})
        terms = LOANS.terms_for_bank(bank_id, relations) or LOANS.terms_for_bank("deutsch_asiatische", {})
        turn = int(self.state["turn"])
        loan = {
            "id": f"L{self._next_loan_id(player)}",
            "bank": bank_id,
            "bank_name": LOANS.banks[bank_id]["name"],
            "principal": amount,
            "outstanding": amount,
            "interest_per_turn": terms["interest_per_turn"],
            "term_turns": terms["term_turns"],
            "tier": terms["tier"],
            "taken_turn": turn,
            "due_turn": turn + terms["term_turns"],
            "overdue": False,
            "source": f"card:{card.get('id')}",
        }
        loans.append(loan)
        payload["debt"] = LOANS.total_outstanding(loans)
        return loan

    def loan_data_for_snapshot(self, player: str) -> Dict[str, Any]:
        return {"offers": self.loan_offers(player)["offers"], "loans": self._loan_rows(player)}

    def loan_offers(self, player: str) -> Dict[str, Any]:
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        return {
            "player": player,
            "turn": int(self.state["turn"]),
            "treasury": int(payload.get("treasury", 0)),
            "debt": LOANS.total_outstanding(loans),
            "offers": LOANS.offers(payload.get("foreign_relations", {}), loans, int(self.state["turn"])),
            "loans": self._loan_rows(player),
        }

    def _loan_rows(self, player: str) -> list:
        payload = self._player(player)
        turn = int(self.state["turn"])
        rows = []
        for loan in payload.get("loans", []):
            rows.append({
                **deepcopy(loan),
                "turns_remaining": int(loan["due_turn"]) - turn,
            })
        return rows

    def take_loan(self, player: str, bank_id: str, amount: int) -> Dict[str, Any]:
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        relations = payload.get("foreign_relations", {})
        # Validate before consuming an id so a rejected request leaves no gap.
        LOANS.borrow(list(loans), str(bank_id), int(amount), relations, int(self.state["turn"]), 0)
        loan = LOANS.borrow(
            loans,
            str(bank_id),
            int(amount),
            relations,
            int(self.state["turn"]),
            self._next_loan_id(player),
        )
        payload["treasury"] = int(payload.get("treasury", 0)) + int(loan["principal"])
        payload["debt"] = LOANS.total_outstanding(loans)
        self.state["last_action"] = {
            "type": "take_loan",
            "player": player,
            "bank": loan["bank"],
            "amount": loan["principal"],
        }
        return {"loan": loan, "state": self.snapshot()}

    def repay_debt(self, player: str, amount: int) -> Dict[str, Any]:
        player_state = self._player(player)
        amount = max(0, int(amount))
        if amount <= 0:
            raise ValueError("debt repayment must be positive")
        loans = player_state.setdefault("loans", [])
        payable = min(amount, int(player_state.get("treasury", 0)), LOANS.total_outstanding(loans))
        if payable <= 0:
            raise ValueError("no debt can be repaid")
        result = LOANS.repay(loans, payable)
        player_state["treasury"] -= result["paid"]
        player_state["debt"] = LOANS.total_outstanding(loans)
        self.state["last_action"] = {
            "type": "repay_debt",
            "player": player,
            "amount": result["paid"],
            "cleared": result["cleared"],
        }
        return {"amount": result["paid"], "cleared": result["cleared"], "state": self.snapshot()}

    def _add_reserve(self, player: str, unit_type: str, amount: int) -> None:
        if unit_type not in UNIT_TYPES:
            raise ValueError(f"unknown unit type: {unit_type!r}")
        payload = self._player(player)
        payload["unit_reserves"][unit_type] = max(0, int(payload["unit_reserves"].get(unit_type, 0)) + int(amount))
        payload["unit_reserve"] = sum(payload["unit_reserves"].values())

    def _base_city_output(self, city_id: str) -> tuple[int, int]:
        city = next((item for item in self.data["strategic_map"]["cities"] if item["id"] == city_id), None)
        if not city:
            return 0, 0
        bonus = self.state.get("city_development", {}).get(city_id, {})
        return (
            scaled_city_value(city, "cash") + int(bonus.get("cash", 0)),
            scaled_city_value(city, "factory") + int(bonus.get("factory", 0)),
        )

    def _qing_gang_riot_rewards(self) -> list[Dict[str, Any]]:
        rewards = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") != "qing_gang_riot":
                continue
            cash = 0
            factory = 0
            for city_id in effect.get("city_ids", []):
                base_cash, base_factory = self._base_city_output(city_id)
                reward_rate = float(effect.get("reward_rate", 0.5))
                cash += math.floor(base_cash * reward_rate + 0.5)
                factory += math.floor(base_factory * reward_rate + 0.5)
            rewards.append({
                "id": effect.get("id"),
                "name": effect.get("name", "青幫暴動"),
                "initiator": effect.get("initiator"),
                "cash": cash,
                "factory": factory,
            })
        return rewards

    def _update_qing_gang_riots(self, riot_garrisons: Dict[str, bool]) -> None:
        active_effects = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") != "qing_gang_riot":
                active_effects.append(effect)
                continue
            has_garrison = bool(riot_garrisons.get(str(effect.get("id"))))
            effect["garrison_progress"] = int(effect.get("garrison_progress", 0)) + 1 if has_garrison else 0
            if effect["garrison_progress"] < int(effect.get("required_turns", 3)):
                active_effects.append(effect)
        self.state["city_output_effects"] = active_effects
        self._refresh_city_income()

    def _adjusted_city_output(self, city_id: str, cash: int, factory: int) -> tuple[int, int]:
        adjusted_cash = int(cash)
        adjusted_factory = int(factory)
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") == "qing_gang_riot":
                if city_id in effect.get("city_ids", []):
                    adjusted_cash = 0
                    adjusted_factory = 0
                continue
            if int(effect.get("remaining_turns", 0)) <= 0 or city_id not in effect.get("city_ids", []):
                continue
            adjusted_cash = int(round(adjusted_cash * float(effect.get("cash_multiplier", 1))))
            adjusted_factory = int(round(adjusted_factory * float(effect.get("factory_multiplier", 1))))
        return max(0, adjusted_cash), max(0, adjusted_factory)

    def _card_count_in_player_zones(self, payload: Dict[str, Any], card_id: str) -> int:
        zones = payload.get("function_deck", []) + payload.get("hand", []) + payload.get("discard", [])
        pending = [payload["pending_draw"]] if payload.get("pending_draw") else []
        return zones.count(card_id) + pending.count(card_id)

    def _remove_card_from_zone(self, zone: list[str], card_id: str, count: int) -> int:
        removed = 0
        index = 0
        while index < len(zone) and removed < count:
            if zone[index] == card_id:
                zone.pop(index)
                removed += 1
            else:
                index += 1
        return removed

    def _remove_undrawn_cards(self, payload: Dict[str, Any], card_id: str, count: int) -> None:
        remaining = count - self._remove_card_from_zone(payload.get("function_deck", []), card_id, count)
        if remaining > 0:
            self._remove_card_from_zone(payload.get("discard", []), card_id, remaining)

    def _sync_foreign_deck_cards(self, player: str) -> None:
        payload = self._player(player)
        card_ids = {card["id"] for card in self.data["function_cards"]["cards"]}
        relations = payload.get("foreign_relations", {})
        for power, cards in FOREIGN_PERK_CARDS.items():
            desired = FOREIGN_PERK_CARD_COPIES if int(relations.get(power, 0)) > FOREIGN_FRIENDLY_THRESHOLD else 0
            for card_id in cards:
                if card_id not in card_ids:
                    continue
                current = self._card_count_in_player_zones(payload, card_id)
                if current < desired:
                    payload["function_deck"].extend([card_id] * (desired - current))
                    self.random.shuffle(payload["function_deck"])
                elif current > desired:
                    self._remove_undrawn_cards(payload, card_id, current - desired)
        for power, card_id in FOREIGN_CONDEMNATION_CARDS.items():
            if card_id not in card_ids:
                continue
            desired = FOREIGN_CONDEMNATION_COPIES if int(relations.get(power, 0)) < FOREIGN_HOSTILE_THRESHOLD else 0
            current = self._card_count_in_player_zones(payload, card_id)
            if current < desired:
                payload["function_deck"].extend([card_id] * (desired - current))
                self.random.shuffle(payload["function_deck"])
            elif current > desired:
                self._remove_undrawn_cards(payload, card_id, current - desired)

    def _card_allowed_for_player(self, card_id: str, player: str) -> bool:
        card = self._card_template(card_id)
        allowed = card.get("allowed_players")
        return not allowed or player in allowed

    def _validate_card_use(self, player: str, card: Dict[str, Any]) -> None:
        allowed = card.get("allowed_players")
        if allowed and player not in allowed:
            raise ValueError("this card is not available to this faction")
        power = card.get("foreign_power_key")
        if power and card.get("requires_relation_min") is not None:
            relation = int(self._player(player).get("foreign_relations", {}).get(power, 0))
            if relation < int(card.get("requires_relation_min")):
                raise ValueError("foreign relation is too low for this card")
        for target in card.get("requires_peace_with", []):
            relation = self._player(player).get("warlord_relations", {}).get(target, {})
            if relation.get("status") == "war":
                raise ValueError("this card requires peace with the listed faction")

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
