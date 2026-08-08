"""In-memory turn and card-pool engine for playtesting."""

from __future__ import annotations

import random
import math
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from .data_store import load_game_data

from economy import LoanBook, scaled_city_value, treaty_port_bonus, is_settlement_turn
from economy.loans import TIER_BLOCKED
from foreign_powers.relations import (
    RELATION_KEYS,
    clamp as clamp_relation,
    relation_bounds,
    relation_scale,
    starting_relations,
)

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
    "du_yuesheng_gamble": 2,
    "hongmen_uprising": 2,
    "behind_enemy_lines_sabotage": 4,
    "antiwar_speech_infantry": 5,
    "antiwar_speech_cavalry": 2,
    "antiwar_speech_machine_gun": 2,
    "antiwar_speech_artillery": 1,
    "zhili_infantry_drill": 2,
    "anti_fengtian_alignment": 2,
    "marshal_gratitude": 2,
    "national_bulwark": 2,
    "northern_expedition_oath": 2,
    "overseas_chinese_remittance": 2,
    "northeast_army_rearmament": 2,
    "young_marshal_rises": 1,
    "wang_yongjiang_financial_reform": 1,
    "zhili_anti_communist_declaration": 1,
    "wang_jingwei_return": 1,
    "railway_saboteur": 4,
    "wang_yaqiao_assassination": 4,
    "body_guard_squad": 8,
    "function_軍閥公債": 4,
    "jiangzhe_financiers": 1,
    "free_china_educators": 2,
    "peking_university_movement": 2,
    "forced_march": 4,
    "foreign_relation_jp": 4,
    "foreign_relation_su": 4,
    "foreign_relation_uk": 4,
    "foreign_relation_fr": 4,
    "foreign_relation_us": 4,
}
# 與 foreign_powers/data/foreign_powers.json 同一組切點：友好 >= 6、交惡 <= -4。
# 這兩個常數原本是舊的 0~10 刻度遺留值（7 與 3），在 -10~10 刻度下會讓關係 0~2
# 誤判為交惡。
_RELATION_SCALE = relation_scale()
FOREIGN_FRIENDLY_THRESHOLD = int(_RELATION_SCALE["friendly_at_or_above"])
FOREIGN_HOSTILE_THRESHOLD = int(_RELATION_SCALE["hostile_at_or_below"])
FOREIGN_PERK_CARD_COPIES = 1
# 少數 perk 卡發兩份以上
FOREIGN_PERK_CARD_COPIES_BY_ID = {"communist_riot": 2, "red_army_uprising": 2}
FOREIGN_CONDEMNATION_COPIES = 3
FOREIGN_PERK_CARDS = {
    "jp": [
        "jp_mitsui_arms_shipment",
        "jp_yokohama_specie_loan",
        "jp_infantry_drill_mission",
        "jp_south_manchuria_engineers",
    ],
    "su": [
        "communist_riot",
        "red_army_uprising",
        "su_rifle_shipment",
        "su_ruble_subsidy",
        "su_galen_advisers",
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
POWER_NAMES = {"jp": "日", "su": "蘇", "uk": "英", "fr": "法", "us": "美", "de": "德"}


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
            # 軍閥公債留下的信用瑕疵；None 代表借款必成。
            profile["bank_success_rate"] = None
            # 孔祥熙從政之後新借款的期限加成。
            profile["loan_term_bonus"] = 0
            profile["loan_penalties"] = []
            profile["unlocks"] = []
            # 汪精衛復出這類卡片對單位生產成本的固定加減，單位是現金。
            profile["recruit_cost_adjustment"] = {}
            profile["notifications"] = []
            profile["debt"] = 0
            return profile

        self.state = {
            "turn": 0,
            "players": {player: player_state(player) for player in players},
            "city_owners": {city["id"]: city["faction"] for city in cities},
            "city_development": {},
            "city_output_effects": [],
            # 崩鐵玩家癱瘓中的鐵路。
            "railway_effects": [],
            # 組建親衛隊：general_id -> 一支永久親衛隊。全場每人只能有一支。
            "body_guards": {},
            # 每次暗殺的結果，成敗都留紀錄。
            "assassination_log": [],
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
        city_garrisons: Optional[Dict[str, int]] = None,
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
        self._update_red_army_uprisings(city_garrisons or {})
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
            newly_overdue = LOANS.mark_overdue(loans, turn)
            # 專案貸款逾期會另外觸發列強的接管條款，與下面的強制扣款疊加。
            triggered = self._trigger_loan_penalties(player, newly_overdue)

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

            # 列強接管的產出在強制扣款之後才拿走，兩者互不抵銷。
            penalty_cash, penalty_factory, penalty_entries = self._apply_loan_penalties(player)
            net_income = max(0, gross_income - seized_income - penalty_cash)
            net_factory = max(0, int(payload.get("factory_income", 0)) - penalty_factory)
            payload["treasury"] += net_income
            payload["factory_points"] += net_factory
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
                "penalties_triggered": triggered,
                "penalty_cash": penalty_cash,
                "penalty_factory": penalty_factory,
                "penalties": penalty_entries,
                "cash_effects": [],
            }
            payload["last_debt_service"] = service
            log[player] = deepcopy(service)

        for player, bonus in self._concession_bonuses().items():
            payload = self.state["players"][player]
            payload["treasury"] += bonus["cash"]
            payload["factory_points"] += bonus["factory"]
            entry = {
                "name": "租界加成",
                "amount": bonus["cash"],
                "factory": bonus["factory"],
                "cities": bonus["cities"],
            }
            payload["last_debt_service"].setdefault("cash_effects", []).append(entry)
            log[player].setdefault("cash_effects", []).append(entry)

        # 上海灘宋貴人：與租界同一個三回合週期，前提是上海還在手上。
        if is_settlement_turn(turn):
            for code, payload in self.state["players"].items():
                patronage = payload.get("soong_patronage")
                if not patronage:
                    continue
                city_id = str(patronage.get("city_id", "shanghai"))
                if self.state["city_owners"].get(city_id) != code:
                    continue
                payload["treasury"] += int(patronage.get("cash", 0))
                payload["factory_points"] += int(patronage.get("factory", 0))
                entry = {
                    "name": "上海宋家支持",
                    "amount": int(patronage.get("cash", 0)),
                    "factory": int(patronage.get("factory", 0)),
                    "cities": [self._city_name(city_id)],
                }
                payload["last_debt_service"].setdefault("cash_effects", []).append(entry)
                log[code].setdefault("cash_effects", []).append(entry)

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
        self._tick_railway_effects()
        active_city_effects = []
        for effect in self.state.get("city_output_effects", []):
            # 這兩種暴動沒有回合上限，解除條件是駐軍而不是時間。
            if effect.get("kind") in ("qing_gang_riot", "red_army_uprising"):
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

    def _concession_bonuses(self) -> Dict[str, Dict[str, Any]]:
        """租界加成，結算週期見 economy/output.py。港口無經濟效果。"""
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
        target_railway: Optional[str] = None,
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
        railway_effect: Optional[Dict[str, Any]] = None
        unlock_effect: Optional[Dict[str, Any]] = None
        assassination: Optional[Dict[str, Any]] = None
        body_guard: Optional[Dict[str, Any]] = None
        loan_effect: Optional[Dict[str, Any]] = None
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
                elif owners == "pro_soviet":
                    owners = self._pro_soviet_players()
                for owner in owners or []:
                    loyalty_swings.append({"owner": str(owner), "amount": int(swing.get("amount", 0))})
        elif mechanic == "cash_per_province":
            provinces = list(card.get("provinces", []))
            per_province = int(card.get("cash_per_province", 0))
            owned = self._controlled_provinces(player, provinces)
            if not owned:
                raise ValueError(f"需控制 {'、'.join(provinces)} 其中至少一省才可使用")
            cash_delta = per_province * len(owned)
            player_state["treasury"] += cash_delta
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
        elif mechanic == "soong_patronage":
            # 上海灘宋貴人：持久狀態，結算回合加給，並擋下杜月笙的豪賭。
            patronage = player_state.get("soong_patronage")
            if patronage:
                raise ValueError("宋家支持已經生效，不能重複使用")
            player_state["soong_patronage"] = {
                "city_id": str(card.get("city_id", "shanghai")),
                "cash": int(card.get("cash", 0)),
                "factory": int(card.get("factory", 0)),
                "immune_cards": list(card.get("immune_cards") or []),
                "since_turn": int(self.state["turn"]),
            }
            unlock_effect = {"owner": player, "name": card.get("name", card_id), "kind": "soong_patronage"}
        elif mechanic == "central_bank":
            # 孔祥熙從政：只影響之後新借的每一筆。
            if player_state.get("loan_interest_override") is not None:
                raise ValueError("中央銀行已經成立，不能重複使用")
            player_state["loan_interest_override"] = float(card.get("loan_interest_override", 0.02))
            player_state["loan_term_bonus"] = int(player_state.get("loan_term_bonus", 0)) + int(card.get("loan_term_bonus", 0))
            unlock_effect = {
                "owner": player,
                "name": card.get("name", card_id),
                "kind": "central_bank",
                "interest_per_turn": player_state["loan_interest_override"],
                "loan_term_bonus": player_state["loan_term_bonus"],
            }
        elif mechanic == "ideology_shield":
            # 自由中國教育家：10 回合免疫，並取消本回合已經落在自己頭上的那兩張牌。
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "ideology_shield",
                "remaining_turns": int(card.get("duration_turns", 10)),
                "owners": [player],
                "shields_cards": list(card.get("shields_cards") or []),
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
            cancelled = self._cancel_same_turn_disruptions(player, timed_effect["shields_cards"])
            timed_effect["cancelled_effects"] = cancelled
        elif mechanic == "ideology_counter":
            # 北京大學共運：把場上生效中的自由中國教育家全部打掉。
            kind = str(card.get("cancels_effect_kind", "ideology_shield"))
            cleared = []
            for code, other in self.state["players"].items():
                keep = []
                for effect in other.get("timed_effects", []):
                    if effect.get("kind") == kind and int(effect.get("remaining_turns", 0)) > 0:
                        cleared.append(code)
                        continue
                    keep.append(effect)
                other["timed_effects"] = keep
            if not cleared:
                raise ValueError("場上沒有生效中的「自由中國教育家」可以壓制")
            for code in set(cleared):
                self._notify(code, f"{card.get('name', card_id)}：你的自由中國教育家效果被壓制失效。")
            unlock_effect = {"owner": player, "name": card.get("name", card_id), "kind": "ideology_counter", "cleared": cleared}
        elif mechanic in ("project_loan", "warlord_bond"):
            # 專案貸款：卡片自帶利率與到期日，不佔用該行授信額度。
            cash_delta = int(card.get("cash", 0))
            debt_delta = int(card.get("debt", 0))
            loan = self._record_card_loan(player, card, debt_delta)
            player_state["treasury"] += cash_delta
            if mechanic == "warlord_bond":
                # 發行公債後信用受損，之後向列強銀行借款只有一定成功率。
                rate = float(card.get("bank_success_rate", 0.75))
                current = player_state.get("bank_success_rate")
                player_state["bank_success_rate"] = rate if current is None else min(float(current), rate)
            loan_effect = {
                "owner": player,
                "loan_id": loan["id"] if loan else None,
                "cash": cash_delta,
                "debt": debt_delta,
                "interest_per_turn": loan["interest_per_turn"] if loan else None,
                "due_turn": loan["due_turn"] if loan else None,
                "bank_success_rate": player_state.get("bank_success_rate"),
            }
        elif mechanic == "concession_city_development":
            # 怡和洋行／美商投資：加成落在「你控制的、掛該國租界」的城市上。
            power = str(card.get("concession_power", ""))
            cash = int(card.get("cash", 0))
            factory = int(card.get("factory", 0))
            for city in self._concession_cities(player, power):
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
            # 交涉不一定談得成；失敗就是白費一張牌，關係不動。
            success_rate = float(card.get("success_rate", 1.0))
            roll = self.random.random()
            negotiation_succeeded = roll < success_rate
            before = int(player_state["foreign_relations"].get(power, 0))
            after = before
            if negotiation_succeeded:
                amount = int(card.get("relation_delta", 0))
                after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + amount))
                player_state["foreign_relations"][power] = after
                self._sync_foreign_deck_cards(player)
            foreign_relation_delta = {
                "power": power,
                "before": before,
                "after": after,
                "amount": after - before,
                "success": negotiation_succeeded,
                "chance": success_rate,
                "roll": roll,
            }
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
            self._require_no_ideology_shield(target_owner, card_id)
            target_cities = list(self._player(target_owner).get("city_economy", []))
            if not target_cities:
                raise ValueError("target faction has no cities to disrupt")
            selected = self.random.sample(target_cities, k=min(2, len(target_cities)))
            city_disruption = {
                "id": card_id,
                "card_id": card_id,
                "created_turn": int(self.state["turn"]),
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
            allowed_provinces = card.get("provinces")
            if allowed_provinces and province not in allowed_provinces:
                raise ValueError(f"{card.get('name', card_id)}只能指定 {'、'.join(allowed_provinces)}")
            patronage = self._player(target_owner).get("soong_patronage")
            if patronage and card_id in (patronage.get("immune_cards") or []):
                raise ValueError(f"{target_owner} 有上海宋家撐腰，{card.get('name', card_id)}對其無效")
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
        elif mechanic == "red_army_uprising":
            # 紅軍起義：兩座隨機城市產出歸零，無期限，直到目標自己派一個旅（5 營）進駐。
            if not target_owner or target_owner == player or target_owner not in self.state["players"]:
                raise ValueError("red army uprising must target another playable faction")
            self._require_no_ideology_shield(target_owner, card_id)
            target_cities = list(self._player(target_owner).get("city_economy", []))
            if not target_cities:
                raise ValueError("target faction has no cities to disrupt")
            count = int(card.get("target_city_count", 2))
            selected = self.random.sample(target_cities, k=min(count, len(target_cities)))
            required = int(card.get("required_battalions", 5))
            city_disruption = {
                "id": f"{card_id}:{self.state['turn']}:{player}:{target_owner}",
                "card_id": card_id,
                "created_turn": int(self.state["turn"]),
                "kind": "red_army_uprising",
                "name": card.get("name", card_id),
                "initiator": player,
                "target_owner": target_owner,
                "city_ids": [city["id"] for city in selected],
                "cities": [{"id": city["id"], "name": city["name"]} for city in selected],
                "cash_multiplier": 0,
                "factory_multiplier": 0,
                "required_battalions": required,
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
            self._notify(
                target_owner,
                f"{card.get('name', card_id)}：{'、'.join(city['name'] for city in selected)} 產出歸零，"
                f"每城需駐紮至少 {required} 營才能恢復。",
            )
        elif mechanic == "railway_sabotage":
            # 崩鐵玩家：一條鐵路停運，沿線部隊每回合只能走 1 格。
            railway = str(target_railway or "").strip()
            allowed = card.get("railways") or []
            if not railway:
                raise ValueError("崩鐵玩家需要指定一條鐵路")
            if allowed and railway not in allowed:
                raise ValueError(f"{card.get('name', card_id)}只能指定 {'、'.join(allowed)}")
            known = {line["name"] for line in self.data["strategic_map"].get("railroads", [])}
            if railway not in known:
                raise ValueError(f"地圖上沒有 {railway}")
            if any(effect.get("railway") == railway for effect in self.state.get("railway_effects", [])):
                raise ValueError(f"{railway}已經在搶修中")
            railway_effect = {
                "id": f"{card_id}:{self.state['turn']}:{player}:{railway}",
                "card_id": card_id,
                "name": card.get("name", card_id),
                "railway": railway,
                "initiator": player,
                "remaining_turns": int(card.get("duration_turns", 3)),
                "move_limit_tiles": int(card.get("move_limit_tiles", 1)),
            }
            self.state.setdefault("railway_effects", []).append(deepcopy(railway_effect))
            for code in self.state["players"]:
                if code == player:
                    continue
                self._notify(code, f"{railway}遭破壞停運，搶修 {railway_effect['remaining_turns']} 回合。")
        elif mechanic == "faction_unlock":
            # 汪精衛復出：持久狀態，解鎖卡片並改變生產。
            unlock_key = str(card.get("unlock_key") or card_id)
            unlocks = player_state.setdefault("unlocks", [])
            if unlock_key in unlocks:
                raise ValueError(f"「{card.get('name', card_id)}」已經生效，不能重複使用")
            unlocks.append(unlock_key)
            per_province = int(card.get("cash_per_province", 0))
            if per_province:
                owned = self._controlled_provinces(player, card.get("provinces", []))
                cash_delta = per_province * len(owned)
                player_state["treasury"] += cash_delta
            cash = int(card.get("cash", 0))
            factory = int(card.get("factory", 0))
            if cash or factory:
                bonus = player_state.setdefault("permanent_output_bonus", {"cash": 0, "factory": 0})
                bonus["cash"] = int(bonus.get("cash", 0)) + cash
                bonus["factory"] = int(bonus.get("factory", 0)) + factory
                self._refresh_city_income()
                permanent_output_delta = {"owner": player, "cash": cash, "factory": factory}
            adjustments = player_state.setdefault("recruit_cost_adjustment", {})
            for unit_type, delta in (card.get("recruit_cost_adjustment") or {}).items():
                entry = adjustments.setdefault(str(unit_type), {"cash": 0, "factory": 0})
                entry["cash"] = int(entry.get("cash", 0)) + int(delta.get("cash", 0))
                entry["factory"] = int(entry.get("factory", 0)) + int(delta.get("factory", 0))
            unlocked_cards = []
            for entry in card.get("unlocks_cards", []):
                unlocked_id = str(entry["id"])
                copies = int(entry.get("copies", 1))
                if not self._card_allowed_for_player(unlocked_id, player):
                    continue
                already = self._card_count_in_player_zones(player_state, unlocked_id)
                missing = max(0, copies - already)
                if missing:
                    player_state["function_deck"].extend([unlocked_id] * missing)
                    self.random.shuffle(player_state["function_deck"])
                unlocked_cards.append({"id": unlocked_id, "copies": missing})
            unlock_effect = {
                "owner": player,
                "unlock": unlock_key,
                "name": card.get("name", card_id),
                "cash": cash,
                "factory": factory,
                "recruit_cost_adjustment": deepcopy(card.get("recruit_cost_adjustment") or {}),
                "unlocked_cards": unlocked_cards,
            }
        elif mechanic == "assassination":
            # 王亞樵來投：一次性擲骰。引擎不持有將領資料（將領樹是唯讀檔案），
            # 目標由前端指定，這裡的職責是算成功率、擲骰、記錄結果。
            if not target_general_id:
                raise ValueError("暗殺需要指定目標人物")
            if not target_owner:
                raise ValueError("暗殺需要指定目標所屬勢力")
            if target_owner == player:
                raise ValueError("不能暗殺自己陣營的人物")
            assassination = self._resolve_assassination(player, card, target_general_id, target_owner)
        elif mechanic == "body_guard":
            # 組建親衛隊：下一回合起生效，之後永久有效，每人限一支。
            if not target_general_id:
                raise ValueError("組建親衛隊需要指定人物")
            if target_owner and target_owner != player:
                raise ValueError("親衛隊只能指派給自己陣營的人物")
            guards = self.state.setdefault("body_guards", {})
            if target_general_id in guards:
                raise ValueError("該人物全場只能編成一支親衛隊，不能重複指派")
            body_guard = {
                "general_id": target_general_id,
                "owner": player,
                "reduction": float(card.get("assassination_reduction", 0.05)),
                "assigned_turn": int(self.state["turn"]),
                # 同一回合內已經發生的暗殺不受保護，所以從下一回合才算數。
                "active_from_turn": int(self.state["turn"]) + 1,
            }
            guards[target_general_id] = deepcopy(body_guard)
        elif mechanic == "no_effect":
            pass
        else:
            raise ValueError("this function card is not implemented in the playtest rules")
        # 卡片的外交副作用：反共類卡對蘇 -2 對英日 +1、紅軍起義得罪四國，諸如此類。
        # 這一段跑在機制之後，所以機制自己丟出的錯誤會擋掉副作用。
        relation_side_effects = self._apply_relation_effects(player, card)
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
            "railway_effect": railway_effect,
            "unlock_effect": unlock_effect,
            "assassination": assassination,
            "body_guard": body_guard,
            "loan_effect": loan_effect,
            "relation_side_effects": relation_side_effects,
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
            "railway_effect": railway_effect,
            "unlock_effect": unlock_effect,
            "assassination": assassination,
            "body_guard": body_guard,
            "loan_effect": loan_effect,
            "relation_side_effects": relation_side_effects,
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

    def _unit_cost_for(self, player: str, unit_type: str) -> tuple[int, int]:
        """One unit's cost for this player: faction rate first, then card adjustments.

        A card adjustment (汪精衛復出 gives infantry -1 cash) is a flat figure applied
        after the faction's percentage, and can never drive a cost below 1.
        """
        player_state = self._player(player)
        base = RECRUIT_COSTS[unit_type]
        adjustment = player_state.get("recruit_cost_adjustment", {}).get(unit_type, {})
        cash = math.ceil(base["cash"] * player_state.get("recruitment_cost_modifier", 1))
        cash = max(1, cash + int(adjustment.get("cash", 0)))
        factory = max(0, int(base["factory"]) + int(adjustment.get("factory", 0)))
        return cash, factory

    def train_unit(self, player: str, unit_type: str, count: int = 1) -> Dict[str, Any]:
        player_state = self._player(player)
        if unit_type not in RECRUIT_COSTS:
            raise ValueError(f"unknown unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("recruit count must be positive")
        unit_cash, unit_factory = self._unit_cost_for(player, unit_type)
        cash_cost = unit_cash * count
        factory_cost = unit_factory * count
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
        # 專案貸款自帶利率與期限，蓋過該行的常規條件。
        interest = float(card.get("interest_per_turn", terms["interest_per_turn"]))
        term_turns = int(card.get("term_turns", terms["term_turns"])) + int(payload.get("loan_term_bonus", 0))
        loan = {
            "id": f"L{self._next_loan_id(player)}",
            "bank": bank_id,
            "bank_name": LOANS.banks[bank_id]["name"],
            "principal": amount,
            "outstanding": amount,
            "interest_per_turn": interest,
            "term_turns": term_turns,
            "tier": terms["tier"],
            "taken_turn": turn,
            "due_turn": turn + term_turns,
            "overdue": False,
            "source": f"card:{card.get('id')}",
        }
        if card.get("off_quota"):
            loan["off_quota"] = True
        if card.get("default_penalty"):
            penalty = deepcopy(card["default_penalty"])
            penalty["card_name"] = card.get("name", card.get("id"))
            loan["default_penalty"] = penalty
        override = payload.get("loan_interest_override")
        if override is not None:
            loan["interest_per_turn"] = float(override)
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
                "bank_power": LOANS.banks.get(loan["bank"], {}).get("power"),
                "turns_remaining": int(loan["due_turn"]) - turn,
            })
        return rows

    def take_loan(self, player: str, bank_id: str, amount: int) -> Dict[str, Any]:
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        relations = payload.get("foreign_relations", {})
        # Validate before consuming an id so a rejected request leaves no gap.
        LOANS.borrow(list(loans), str(bank_id), int(amount), relations, int(self.state["turn"]), 0)
        # 軍閥公債的後遺症：申貸有機率被拒。擲骰在驗證之後，才不會白白拒絕一筆
        # 本來就不合格的申請。
        success_rate = payload.get("bank_success_rate")
        if success_rate is not None and self.random.random() >= float(success_rate):
            bank_name = LOANS.banks[str(bank_id)]["name"]
            raise ValueError(f"{bank_name}以信用不良為由拒絕本次貸款（成功率 {int(float(success_rate) * 100)}%）")
        loan = LOANS.borrow(
            loans,
            str(bank_id),
            int(amount),
            relations,
            int(self.state["turn"]),
            self._next_loan_id(player),
        )
        self._apply_loan_policy(player, loan)
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

    def _apply_relation_effects(self, player: str, card: Dict[str, Any]) -> list:
        """卡片在自身機制之外造成的外交後果。

        反共類卡對蘇 −2、對英日各 +1；紅軍起義得罪英日美法。這一段跑在機制之後，
        所以機制自己丟出的錯誤會連帶擋掉外交後果。
        """
        effects = card.get("relation_effects") or {}
        if not effects:
            return []
        relations = self._player(player).setdefault("foreign_relations", {})
        changes = []
        for power, amount in effects.items():
            power = str(power)
            if power not in relations:
                continue
            before = int(relations[power])
            after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + int(amount)))
            relations[power] = after
            changes.append({"power": power, "before": before, "after": after, "amount": after - before})
        if changes:
            # 關係一動，友好卡與譴責卡的進出也要跟著重算。
            self._sync_foreign_deck_cards(player)
        return changes

    # ---- 自由中國教育家的免疫 --------------------------------------------

    def _ideology_shield(self, player: str, card_id: str) -> Optional[Dict[str, Any]]:
        for effect in self._player(player).get("timed_effects", []):
            if effect.get("kind") != "ideology_shield" or int(effect.get("remaining_turns", 0)) <= 0:
                continue
            if card_id in (effect.get("shields_cards") or []):
                return effect
        return None

    def _require_no_ideology_shield(self, target_owner: str, card_id: str) -> None:
        shield = self._ideology_shield(target_owner, card_id)
        if shield:
            raise ValueError(
                f"{target_owner} 有「{shield.get('name', '自由中國教育家')}」護持"
                f"（剩餘 {shield['remaining_turns']} 回合），本牌對其無效"
            )

    def _cancel_same_turn_disruptions(self, player: str, card_ids: Iterable[str]) -> list:
        """同回合已經打在自己頭上的紅軍起義／共黨暴動立即失效。"""
        wanted = set(card_ids)
        turn = int(self.state["turn"])
        cancelled = []
        keep = []
        for effect in self.state.get("city_output_effects", []):
            same_target = effect.get("target_owner") == player
            same_turn = int(effect.get("created_turn", -1)) == turn
            if same_target and same_turn and str(effect.get("card_id") or effect.get("id")) in wanted:
                cancelled.append(effect.get("name", effect.get("id")))
                continue
            keep.append(effect)
        if cancelled:
            self.state["city_output_effects"] = keep
            self._refresh_city_income()
        return cancelled

    def _apply_loan_policy(self, player: str, loan: Dict[str, Any]) -> Dict[str, Any]:
        """孔祥熙從政的中央銀行政策，只套用在之後新借的每一筆上。"""
        payload = self._player(player)
        override = payload.get("loan_interest_override")
        if override is not None:
            loan["interest_per_turn"] = float(override)
        bonus = int(payload.get("loan_term_bonus", 0))
        if bonus:
            loan["term_turns"] = int(loan["term_turns"]) + bonus
            loan["due_turn"] = int(loan["due_turn"]) + bonus
        return loan

    # ---- 專案貸款違約條款 ------------------------------------------------

    def _trigger_loan_penalties(self, player: str, newly_overdue: list) -> list:
        """A project loan that just went overdue hands its clause to the power."""
        payload = self._player(player)
        active = payload.setdefault("loan_penalties", [])
        started = []
        for loan in newly_overdue:
            clause = loan.get("default_penalty")
            if not clause or any(entry["loan_id"] == loan["id"] for entry in active):
                continue
            entry = deepcopy(clause)
            entry["loan_id"] = loan["id"]
            entry["started_turn"] = int(self.state["turn"])
            entry["remaining_turns"] = clause.get("duration_turns")
            active.append(entry)
            started.append(entry["loan_id"])
            self._notify(player, f"{clause.get('label', '貸款違約條款')} 生效。")
        return started

    def _penalty_targets(self, player: str, clause: Dict[str, Any]) -> list:
        """The cities a clause bites into, chosen by current output."""
        economy = self._city_economy_for(player)
        if clause.get("scope") == "provinces":
            by_province: Dict[str, list] = {}
            for city in economy:
                by_province.setdefault(city["province"], []).append(city)
            ranked = sorted(
                by_province.items(),
                key=lambda item: (-sum(c["cash"] + c["factory"] for c in item[1]), item[0]),
            )
            return [city for _, cities in ranked[: int(clause.get("count", 1))] for city in cities]
        ranked = sorted(economy, key=lambda city: (-(city["cash"] + city["factory"]), city["id"]))
        return ranked[: int(clause.get("count", 1))]

    def _apply_loan_penalties(self, player: str) -> tuple:
        """This turn's seizure. Returns (cash, factory, log entries)."""
        payload = self._player(player)
        active = payload.setdefault("loan_penalties", [])
        share_default = 1.0
        total_cash = 0
        total_factory = 0
        entries = []
        remaining = []
        for clause in active:
            turns_left = clause.get("remaining_turns")
            if turns_left is not None and int(turns_left) <= 0:
                continue
            share = float(clause.get("share", share_default))
            take = set(clause.get("take") or ["cash", "factory"])
            targets = self._penalty_targets(player, clause)
            cash = int(round(sum(city["cash"] for city in targets) * share)) if "cash" in take else 0
            factory = int(round(sum(city["factory"] for city in targets) * share)) if "factory" in take else 0
            total_cash += cash
            total_factory += factory
            entries.append({
                "loan_id": clause.get("loan_id"),
                "name": clause.get("label", clause.get("card_name", "違約條款")),
                "power": clause.get("power"),
                "cities": [city["name"] for city in targets],
                "cash": cash,
                "factory": factory,
                "remaining_turns": turns_left,
            })
            if turns_left is not None:
                clause["remaining_turns"] = int(turns_left) - 1
                if clause["remaining_turns"] <= 0:
                    continue
            remaining.append(clause)
        payload["loan_penalties"] = remaining
        return total_cash, total_factory, entries

    def active_body_guard(self, general_id: str) -> Optional[Dict[str, Any]]:
        """A guard only shields from the turn after it was raised."""
        guard = self.state.get("body_guards", {}).get(general_id)
        if not guard:
            return None
        if int(self.state["turn"]) < int(guard.get("active_from_turn", 0)):
            return None
        return guard

    def _resolve_assassination(
        self,
        player: str,
        card: Dict[str, Any],
        target_general_id: str,
        target_owner: str,
    ) -> Dict[str, Any]:
        """Roll once. The engine owns no general data, so the caller names the target.

        Success is reported back; applying the death to the general tree is the
        frontend's job, the same way loyalty deltas already work.
        """
        base = float(card.get("success_rate", 0.2))
        guard = self.active_body_guard(target_general_id)
        reduction = float(guard["reduction"]) if guard else 0.0
        chance = max(0.0, base - reduction)
        roll = self.random.random()
        success = roll < chance
        outcome = {
            "card_id": card.get("id"),
            "name": card.get("name", card.get("id")),
            "turn": int(self.state["turn"]),
            "initiator": player,
            "target_general_id": target_general_id,
            "target_owner": target_owner,
            "base_chance": base,
            "guard_reduction": reduction,
            "chance": chance,
            "roll": roll,
            "success": success,
        }
        self.state.setdefault("assassination_log", []).append(deepcopy(outcome))
        if target_owner in self.state["players"]:
            self._notify(target_owner, "遭遇暗殺：得手，該人物身亡。" if success else "遭遇暗殺：未得手。")
        return outcome

    def _notify(self, player: str, text: str) -> None:
        """A short message the affected faction sees on its own screen."""
        payload = self.state["players"].get(player)
        if payload is None:
            return
        payload.setdefault("notifications", []).append({
            "turn": int(self.state["turn"]),
            "text": text,
        })

    def _update_red_army_uprisings(self, city_garrisons: Dict[str, int]) -> None:
        """紅軍起義沒有回合上限：目標每在一座城駐滿一個旅，該城就恢復產出。"""
        active_effects = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") != "red_army_uprising":
                active_effects.append(effect)
                continue
            required = int(effect.get("required_battalions", 5))
            freed = [
                city
                for city in effect.get("cities", [])
                if int(city_garrisons.get(city["id"], 0)) >= required
            ]
            if freed:
                freed_ids = {city["id"] for city in freed}
                effect["cities"] = [city for city in effect.get("cities", []) if city["id"] not in freed_ids]
                effect["city_ids"] = [item for item in effect.get("city_ids", []) if item not in freed_ids]
                self._notify(
                    str(effect.get("target_owner")),
                    f"{effect.get('name', '紅軍起義')}："
                    f"{'、'.join(city['name'] for city in freed)} 駐軍已達 {required} 營，產出恢復。",
                )
            if effect.get("city_ids"):
                active_effects.append(effect)
        self.state["city_output_effects"] = active_effects
        self._refresh_city_income()

    def _tick_railway_effects(self) -> None:
        active = []
        for effect in self.state.get("railway_effects", []):
            remaining = int(effect.get("remaining_turns", 0)) - 1
            if remaining > 0:
                effect["remaining_turns"] = remaining
                active.append(effect)
        self.state["railway_effects"] = active

    def disabled_railways(self) -> list:
        """搶修中的鐵路名稱，前端據此關閉該線的鐵路運輸。"""
        return [
            str(effect.get("railway"))
            for effect in self.state.get("railway_effects", [])
            if int(effect.get("remaining_turns", 0)) > 0
        ]

    def _adjusted_city_output(self, city_id: str, cash: int, factory: int) -> tuple[int, int]:
        adjusted_cash = int(cash)
        adjusted_factory = int(factory)
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") in ("qing_gang_riot", "red_army_uprising"):
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

    @staticmethod
    def _perk_copies(card_id: str) -> int:
        return FOREIGN_PERK_CARD_COPIES_BY_ID.get(card_id, FOREIGN_PERK_CARD_COPIES)

    def _sync_foreign_deck_cards(self, player: str) -> None:
        payload = self._player(player)
        card_ids = {card["id"] for card in self.data["function_cards"]["cards"]}
        relations = payload.get("foreign_relations", {})
        for power, cards in FOREIGN_PERK_CARDS.items():
            friendly = int(relations.get(power, 0)) >= FOREIGN_FRIENDLY_THRESHOLD
            for card_id in cards:
                if card_id not in card_ids:
                    continue
                desired = self._perk_copies(card_id) if friendly else 0
                current = self._card_count_in_player_zones(payload, card_id)
                if current < desired:
                    payload["function_deck"].extend([card_id] * (desired - current))
                    self.random.shuffle(payload["function_deck"])
                elif current > desired:
                    self._remove_undrawn_cards(payload, card_id, current - desired)
        for power, card_id in FOREIGN_CONDEMNATION_CARDS.items():
            if card_id not in card_ids:
                continue
            desired = FOREIGN_CONDEMNATION_COPIES if int(relations.get(power, 0)) <= FOREIGN_HOSTILE_THRESHOLD else 0
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

    def _controlled_provinces(self, player: str, provinces: Iterable[str]) -> list:
        """Provinces the player controls outright — every city in them is his.

        This is the same bar the board uses for 宣告接管全省; holding one city in
        a province is not control.
        """
        wanted = set(provinces)
        cities_by_province: Dict[str, list] = {}
        for city in self.data["strategic_map"]["cities"]:
            province = city.get("province")
            if province in wanted:
                cities_by_province.setdefault(province, []).append(city)
        owned = [
            province
            for province, cities in cities_by_province.items()
            if all(self.state["city_owners"].get(city["id"], city["faction"]) == player for city in cities)
        ]
        return sorted(owned)

    def _city_name(self, city_id: str) -> str:
        city = next((item for item in self.data["strategic_map"]["cities"] if item["id"] == city_id), None)
        return city["name"] if city else city_id

    def _concession_cities(self, player: str, power: str) -> list:
        """Cities the player holds that carry this power's concession."""
        return [
            city
            for city in self.data["strategic_map"]["cities"]
            if power in (city.get("concession") or [])
            and self.state["city_owners"].get(city["id"], city["faction"]) == player
        ]

    def _pro_soviet_players(self) -> list:
        """對蘇關係達友好門檻的勢力。"""
        return [
            code for code, payload in self.state["players"].items()
            if int(payload.get("foreign_relations", {}).get("su", 0)) >= FOREIGN_FRIENDLY_THRESHOLD
        ]

    def _validate_card_use(self, player: str, card: Dict[str, Any]) -> None:
        unlock = card.get("requires_unlock")
        if unlock and unlock not in self._player(player).get("unlocks", []):
            raise ValueError(f"此牌需先觸發「{card.get('requires_unlock_name', unlock)}」才能使用")
        required_provinces = card.get("requires_provinces")
        if required_provinces:
            owned = set(self._controlled_provinces(player, required_provinces))
            missing = [name for name in required_provinces if name not in owned]
            if missing:
                raise ValueError(f"需完全控制 {'、'.join(required_provinces)} 才可使用（尚缺 {'、'.join(missing)}）")
        required_cities = card.get("requires_cities")
        if required_cities:
            missing = [
                self._city_name(city_id) for city_id in required_cities
                if self.state["city_owners"].get(city_id) != player
            ]
            if missing:
                raise ValueError(f"需控制 {'、'.join(missing)} 才可使用")
        relation_max = card.get("requires_relation_max")
        if relation_max:
            power = str(relation_max["power"])
            relation = int(self._player(player).get("foreign_relations", {}).get(power, 0))
            if relation > int(relation_max["value"]):
                raise ValueError(f"對{POWER_NAMES.get(power, power)}關係需在 {relation_max['value']} 以下才可使用")
        concession_power = card.get("concession_power")
        if concession_power and not self._concession_cities(player, concession_power):
            raise ValueError(f"需控制至少一座{POWER_NAMES.get(concession_power, concession_power)}租界城市才可使用")
        allowed = card.get("allowed_players")
        if allowed and player not in allowed:
            raise ValueError("this card is not available to this faction")
        power = card.get("foreign_power_key")
        if power and card.get("requires_relation_min") is not None:
            relation = int(self._player(player).get("foreign_relations", {}).get(power, 0))
            if relation < int(card.get("requires_relation_min")):
                raise ValueError(
                    f"對{POWER_NAMES.get(power, power)}關係需達 {card.get('requires_relation_min')} 才可使用"
                    f"（目前 {relation}）"
                )
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
