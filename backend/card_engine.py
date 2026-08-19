"""In-memory turn and card-pool engine for playtesting."""

from __future__ import annotations

import random
import math
import re
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
FUNCTION_CARD_DRAW_FACTORY_COST = 5
FUNCTION_CARD_DRAW_LIMIT = 2
FOREIGN_RELATION_MIN, FOREIGN_RELATION_MAX = relation_bounds()
WARLORD_CODES = ("F", "W", "S", "N", "Y", "G", "M", "H", "C", "D", "Q")
UNIT_TYPES = ("infantry", "cavalry", "machine_gun", "artillery")
UNIT_FORCE_POINTS = {
    "infantry": 1,
    "cavalry": 1,
    "machine_gun": 2,
    "artillery": 4,
}
ARMY_FORCE_CAP = 100
RECRUIT_COSTS = {
    "infantry": {"cash": 4, "factory": 2},
    "cavalry": {"cash": 7, "factory": 2},
    "machine_gun": {"cash": 10, "factory": 4},
    "artillery": {"cash": 16, "factory": 5},
}
NAVY_RECRUIT_COSTS = {
    "gun_boat": {"cash": 200, "factory": 75},
    "cargo_boat": {"cash": 100, "factory": 50},
}
LOYALTY_FUNCTION_CARD_IDS = ("unit_promotion", "local_autonomy_agitation")
ABSOLUTE_LOYAL_GENERAL_IDS = {
    "zhang_xueliang",
    "jin_yun_e",
    "li_houji",
    "he_yingqin",
}
FUNCTION_CARD_COPIES = {
    "unit_promotion": 10,
    "local_autonomy_agitation": 7,
    "reserve_gift_infantry": 4,
    "reserve_gift_cavalry": 2,
    "reserve_gift_machine_gun": 2,
    "reserve_gift_artillery": 1,
    "city_development": 8,
    "piaohao_network": 3,
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
    "wang_yaqiao_assassination": 3,
    "body_guard_squad": 5,
    "function_軍閥公債": 4,
    "jiangzhe_financiers": 1,
    "affiliation_slot_upgrade": 4,
    "foreign_relation_jp": 5,
    "foreign_relation_su": 5,
    "foreign_relation_uk": 5,
    "foreign_relation_fr": 5,
    "foreign_relation_us": 5,
    "function_在野名將投效": 3,
    "artifact_smuggling": 3,
    "police_precinct": 5,
    "trade_export_jp": 5,
    "trade_export_su": 5,
    "trade_export_uk": 5,
    "trade_export_fr": 5,
    "trade_export_us": 5,
    # 中國人之恥開局 0 張，只靠〈盜賣文物〉塞進牌庫，全場上限 9 張。
    # 德商三張：德國不玩列強政治、只做生意，所以不綁關係，開局就在牌庫裡。
    "siemens_china_expansion": 2,
    "krupp_mauser_return": 1,
    "rheinmetall_arms_export": 1,
    # 三張技術卡的前提事件卡尚未實作，條件永遠不成立，暫時不會進牌庫。
    "government_scholars": 2,
    "penicillin_import": 3,
    "zeppelin_recon": 2,
    "sound_film_studio": 3,
    "state_radio_station": 3,
    "mechanized_division": 2,
    "harbor_demolition": 3,
    "zhou_enlai_underground": 1,
    "national_shame": 0,
}
# 與 foreign_powers/data/foreign_powers.json 同一組切點：友好 >= 6、交惡 <= -4。
# 這兩個常數原本是舊的 0~10 刻度遺留值（7 與 3），在 -10~10 刻度下會讓關係 0~2
# 誤判為交惡。
_RELATION_SCALE = relation_scale()
FOREIGN_FRIENDLY_THRESHOLD = int(_RELATION_SCALE["friendly_at_or_above"])
FOREIGN_HOSTILE_THRESHOLD = int(_RELATION_SCALE["hostile_at_or_below"])
FOREIGN_PERK_CARD_COPIES = 2
# 共黨暴動與紅軍起義比其他 perk 卡多一張
FOREIGN_PERK_CARD_COPIES_BY_ID = {"communist_riot": 3, "red_army_uprising": 3}
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
        "us_socony_oil",
    ],
}
FOREIGN_CONDEMNATION_CARDS = {
    "jp": "jp_condemnation",
    "su": "su_condemnation",
    "uk": "uk_condemnation",
    "fr": "fr_condemnation",
    "us": "us_condemnation",
}
# 在野將領的出山附加費：延攬費 = 身價全額 + 這筆錢。
EXILE_RECRUIT_SURCHARGE = 15
# ── 有陣營層級效果的將領技能 ──────────────────────────────────────────
# 這些技能的效果不在戰場上，而是掛在「持有這名將領的陣營」身上。人走效果就走，
# 所以引擎只記「哪個陣營現在持有這個技能」，由 apply_general_join 在轉投時更新。
#
# 買辦：轉投時該陣營對該國關係上升，且該國的譴責進牌庫時每張有機率被擋下。
COMPRADOR_TRAITS = {
    "japanese_comprador": {"power": "jp", "gain": 2, "immunity": 0.10},   # 張宗昌
    "french_comprador": {"power": "fr", "gain": 3, "immunity": 0.30},     # 唐繼堯
}
# 地方財源：持有者的陣營，該省每座城市每回合現金與工業各 +1。
PROVINCE_OUTPUT_TRAITS = {
    "tianfu_land": {"province": "四川", "cash": 1, "factory": 1},         # 劉湘
    "hunan_governor": {"province": "湖南", "cash": 1, "factory": 1},      # 趙恒惕
}
# 剿共：紅軍起義只要駐滿一回合就恢復產出。
FAST_UPRISING_SUPPRESSION_TRAITS = {
    "anticommunist_vanguard": {"disabled_when": {"power": "su", "min": 6}},  # 何鍵
    "old_cantonese_army": {},                                                # 陳炯明
}
FACTION_LEVEL_TRAITS = (
    set(COMPRADOR_TRAITS) | set(PROVINCE_OUTPUT_TRAITS) | set(FAST_UPRISING_SUPPRESSION_TRAITS)
)
FEATURES = {
    "function_cards": True,
    "function_card_draw_cost": FUNCTION_CARD_DRAW_COST,
    "function_card_draw_factory_cost": FUNCTION_CARD_DRAW_FACTORY_COST,
    "function_card_purchase_limit": FUNCTION_CARD_DRAW_LIMIT,
    "function_card_max_hand_size": MAX_HAND_SIZE,
    "army_force_cap": ARMY_FORCE_CAP,
    "unit_force_points": dict(UNIT_FORCE_POINTS),
    "forced_march": {
        "cash": 10,
        "factory": 10,
        "duration_turns": 3,
        "cooldown_turns": 3,
        "tiles": 2,
    },
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
                    "cash": scaled_city_value(self._with_level(city), "cash"),
                    "factory": scaled_city_value(self._with_level(city), "factory"),
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
            profile["navy_reserves"] = {"gun_boat": 0, "cargo_boat": 0}
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
            # 軍閥公債留下的信用瑕疵；到指定回合前所有列強銀行拒絕新貸。
            profile["loan_ban_until_turn"] = None
            # 孔祥熙從政之後新借款的期限加成。
            profile["loan_term_bonus"] = 0
            profile["loan_penalties"] = []
            # 公費留學生：幾回合後才開始生效的產出加成。
            profile["delayed_output_bonuses"] = []
            # 火燒紅蓮寺這類限時的徵兵折抵。
            profile["timed_recruit_discounts"] = []
            profile["relation_drop_amplifiers"] = []
            profile["loan_rate_overrides"] = []
            profile["province_card_immunities"] = []
            profile["pending_frontend_effects"] = []
            # 中央研究院：holder 表示收編過，disqualified 是永久除名。
            profile["academia_sinica"] = {"holder": False, "disqualified": False}
            profile["loan_interest_grace_until"] = None
            # 進口盤尼西林：配有野戰醫院的將領，效果隨人走。
            profile["field_hospital_generals"] = []
            profile["unlocks"] = []
            # 汪精衛復出這類卡片對單位生產成本的固定加減，單位是現金。
            profile["recruit_cost_adjustment"] = {}
            profile["notifications"] = []
            # 大港開炸：當下付不出來的港口修復費，之後每回合從收入自動扣繳。
            profile["port_repair_due"] = {"cash": 0, "factory": 0}
            # 周恩來與地下黨這類「把某幾張友好卡加到幾張」的加成。
            profile["perk_copy_overrides"] = {}
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
            # 大港開炸癱瘓中的港口。
            "port_effects": [],
            # 政府內閣：五張單一玩家卡各自的持有者。同一張全場只能有一個人在檯面上。
            "cabinet": {},
            # 大帥被俘或陣亡的陣營，由前端隨 next_turn 回報（引擎沒有將領資料）。
            "fallen_marshals": [],
            # 事件卡：抽剩的池子、已發生的歷史、正在等待回應的那一輪。
            "event_pool": [card["id"] for card in (self.data.get("event_cards") or {}).get("cards", [])],
            "event_history": [],
            "pending_events": None,
            # 事件卡造成的暫時性限制。
            # event_locks：被封鎖的事件卡。封鎖 ≠ 移除——卡片仍留在 event_pool 裡，
            # 封鎖期間抽不到；到期後不必洗回，自然又抽得到。
            "event_locks": [],
            "concession_overrides": [],
            # 11.1：省內有部隊「交戰中」時扣產出的規則，以及前端每回合回報的交戰省份。
            # 後端沒有部隊資料，交戰與否由前端算好後隨 next_turn 傳進來
            # （與 riot_garrisons / city_garrisons 同一條通道）。
            "province_combat_penalties": [],
            "contested_provinces": [],
            "bond_underwriting": [],
            # 事件卡對城市等級的永久覆寫（晏陽初辦學鄉村把四省的 2 級城升為 3 級）。
            # strategic_map.json 是靜態資料不動它，覆寫值存在這裡，
            # 所有讀等級的路徑都走 _with_level() 取得生效後的城市。
            "city_level_overrides": {},
            "province_recruit_discounts": [],
            # 學潮（9.3、10.7）造成的城市產出減半走 city_output_effects；
            # 《新月》月刊（9.5）一旦抽出，此後學潮的減幅由 1/2 收斂為 1/4。
            "student_unrest_relief": False,
            "perk_suspensions": [],
            "bank_bans": [],
            "bank_limit_multipliers": [],
            "function_card_overrides": [],
            # function_card_freezes：被釘死的功能卡欄位。禁令生效後才下的改寫一律無效，
            # 禁令之前已經下的照舊（見 10.2 西北科學考查團）。
            "function_card_freezes": [],
            "player_card_overrides": [],
            "scheduled_event_effects": [],
            "loan_surcharges": [],
            "suppression_turn_bonuses": [],
            # 組建親衛隊：general_id -> 一支永久親衛隊。全場每人只能有一支。
            "body_guards": {},
            # 每次暗殺的結果，成敗都留紀錄。
            "assassination_log": [],
            # 在野將領池已被延攬的人：general_id -> 延攬方。全場每人只能被延攬一次。
            "recruited_exiles": {},
            "npc_accounts": {
                code: {
                    "treasury": 60,
                    "unit_reserves": {"infantry": 20, "cavalry": 5, "machine_gun": 3, "artillery": 2},
                }
                for code in WARLORD_CODES
                if code not in DEFAULT_PLAYERS
            },
            "turn_log": [],
            "last_action": None,
            "recurring_effects": [],
            "last_economy_log": {},
            "next_deal_id": 1,
            # 陣營層級技能目前掛在誰身上（開局時只有張宗昌的〈日本買辦〉在奉系）。
            "faction_general_traits": self._initial_faction_general_traits(),
            "condemnation_blocked": {},
        }
        for player in self.state["players"]:
            self._sync_foreign_deck_cards(player)
            # 條件卡開局先全部撤出牌庫，條件成立時才由 _sync_conditional_deck_cards 洗回去。
            self._sync_conditional_deck_cards(player)
            self.random.shuffle(self.state["players"][player]["function_deck"])
        return self.snapshot()

    def snapshot(self) -> Dict[str, Any]:
        state = deepcopy(self.state)
        state["counts"] = {
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

    def restore_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Restore engine state from an `/api/shared-state` engine snapshot."""

        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("players"), dict):
            raise ValueError("invalid engine snapshot")
        restored = deepcopy(snapshot)
        restored.pop("counts", None)
        for profile in restored.get("players", {}).values():
            # Tactical army.units is the sole army-composition authority. Older
            # snapshots kept the same additions here as well, which doubled
            # reinforced battalions after the next browser synchronization.
            profile["army_reinforcements"] = {}
            reserves = profile.setdefault("navy_reserves", {})
            reserves.setdefault("gun_boat", 0)
            reserves.setdefault("cargo_boat", 0)
        self.state = restored
        self._refresh_city_income()
        return self.snapshot()

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
            "generals_in_exile": self.data["generals_in_exile"],
            "navy_system": self.data["navy_system"],
            "strategic_map": self._strategic_map_snapshot(),
            "recruit_costs": RECRUIT_COSTS,
            "navy_recruit_costs": NAVY_RECRUIT_COSTS,
            "features": FEATURES,
            "cards": {
                "function": self.data["function_cards"]["cards"],
                "event": (self.data.get("event_cards") or {}).get("cards", []),
            },
            "event_draw_rules": (self.data.get("event_cards") or {}).get("draw_rules") or {},
        }

    def next_turn(
        self,
        active_player: Optional[str] = None,
        *,
        force: bool = False,
        riot_garrisons: Optional[Dict[str, bool]] = None,
        city_garrisons: Optional[Dict[str, int]] = None,
        contested_provinces: Optional[Iterable[str]] = None,
        fallen_marshals: Optional[Iterable[str]] = None,
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
        if contested_provinces is not None:
            self.set_contested_provinces(contested_provinces)
        if fallen_marshals is not None:
            self.set_fallen_marshals(fallen_marshals)
        self._update_qing_gang_riots(riot_garrisons or {})
        self._update_red_army_uprisings(city_garrisons or {})
        # 事件卡週期：先把本回合唯一一則報紙發出去，等指定勢力回應後才結算經濟。
        if self._start_event_cycle():
            return {
                "turn": {"turn": self.state["turn"], "awaiting_events": True},
                "pending_events": self.state.get("pending_events"),
                "state": self.snapshot(),
            }
        return self._finish_turn(active_player)

    def _finish_turn(self, active_player: Optional[str] = None) -> Dict[str, Any]:
        # 排程中的事件效果要趕在經濟結算之前落地。
        self._fire_scheduled_event_effects()
        # 內閣卡的失效也在結算之前判定：這回合已經失效的人物，不該再發他的加成。
        lapsed_cabinet = self._tick_cabinet()
        economy_log = self._apply_turn_economy()
        self._tick_timed_effects()
        for player, payload in self.state["players"].items():
            payload["function_purchase_count"] = 0
            payload["function_purchase_used"] = False
            self._sync_foreign_deck_cards(player)
            self._sync_conditional_deck_cards(player)
        turn_entry = {
            "turn": self.state["turn"],
            "function_purchase_offer": active_player if FEATURES["function_cards"] else None,
            "economy": economy_log,
            "cabinet_lapsed": lapsed_cabinet,
        }
        self.state["turn_log"].append(turn_entry)
        return {"turn": turn_entry, "state": self.snapshot()}

    def _apply_loan_surcharges(self, player: str) -> None:
        """事件卡造成的貸款加碼利率：到期自動退回原利率。"""
        turn = int(self.state["turn"])
        payload = self._player(player)
        for loan in payload.get("loans", []):
            extra = 0.0
            for entry in self.state.get("loan_surcharges", []):
                if turn >= int(entry.get("until_turn", 0)):
                    continue
                players = entry.get("players")
                if players and player not in players:
                    continue
                banks = entry.get("banks") or []
                if banks and loan.get("bank") not in banks:
                    continue
                extra += float(entry.get("amount", 0))
            base = float(loan.get("base_interest_per_turn", loan["interest_per_turn"]))
            loan.setdefault("base_interest_per_turn", base)
            loan["interest_per_turn"] = round(base + extra, 4)

    def suppression_turn_bonus(self) -> int:
        """火燒紅蓮寺期間，暴動要多鎮壓幾回合。"""
        turn = int(self.state["turn"])
        return sum(int(entry.get("bonus", 0)) for entry in self.state.get("suppression_turn_bonuses", [])
                   if turn < int(entry.get("until_turn", 0)))

    # ── 中央研究院 ────────────────────────────────────────────────────
    # 收編之後：控制江蘇期間每回合工業點 +5、〈盜賣文物〉從你的卡池清空；
    # 一旦丟掉江蘇，加成停掉、〈盜賣文物〉回到卡池。但只要你在離開江蘇期間
    # 打出過〈盜賣文物〉，或任何時候選過〈殷墟第一鏟〉的「售與洋商」，
    # 這張卡就對你永久失效，日後奪回江蘇也不會恢復。
    ACADEMIA_PROVINCE = "江蘇"
    ACADEMIA_FACTORY_BONUS = 5

    def academia_status(self, player: str) -> Dict[str, Any]:
        return self._player(player).setdefault(
            "academia_sinica", {"holder": False, "disqualified": False})

    def academia_founded(self) -> bool:
        """中央研究院是否已經成立（全場限一所，成立與否是全域狀態）。"""
        return bool(self.state.get("academia_sinica", {}).get("founded"))

    def academia_active(self, player: str) -> bool:
        """v4 7.2：研究院一旦成立，**任何**控制江蘇的玩家都吃這個加成。

        舊版要求你自己抽到並回應過（holder 旗標）才算數；v4 把那道門檻拿掉了，
        改成「加成跟著江蘇跑」。失格（賣過殷墟甲骨／離開江蘇期間打過盜賣文物）
        仍然是逐玩家的永久狀態，失格者就算控制江蘇也拿不到。
        """
        if not self.academia_founded():
            return False
        if self.academia_status(player).get("disqualified"):
            return False
        return bool(self._controlled_provinces(player, [self.ACADEMIA_PROVINCE]))

    def disqualify_academia(self, player: str, reason: str) -> Optional[Dict[str, Any]]:
        status = self.academia_status(player)
        if not self.academia_founded() or status.get("disqualified"):
            return None
        status["disqualified"] = True
        status["reason"] = reason
        self._refresh_city_income()
        self._sync_conditional_deck_cards(player)
        return {"kind": "academia_disqualified", "player": player, "reason": reason}

    def _delayed_output_bonus(self, player: str) -> Dict[str, int]:
        """公費留學生這類「幾回合後才開始」的永久產出加成。"""
        turn = int(self.state["turn"])
        total = {"cash": 0, "factory": 0}
        if self.academia_active(player):
            total["factory"] += self.ACADEMIA_FACTORY_BONUS
        for entry in self._player(player).get("delayed_output_bonuses", []):
            if turn < int(entry.get("start_turn", 0)):
                continue
            total["cash"] += int(entry.get("cash", 0))
            total["factory"] += int(entry.get("factory", 0))
        return total

    def _apply_turn_economy(self) -> Dict[str, Any]:
        self._refresh_city_income()
        turn = int(self.state["turn"])
        log: Dict[str, Any] = {}
        for player, payload in self.state["players"].items():
            loans = payload.setdefault("loans", [])
            relations = payload.get("foreign_relations", {})
            debt_before = LOANS.total_outstanding(loans)

            # 3.4 — one turn of interest on every loan, before anything else happens.
            # 每筆貸款各用自己的利率計息，所以先照利率分組記下明細，
            # 介面才不會拿一個寫死的百分比來充當「利息」。
            interest_breakdown: Dict[float, Dict[str, Any]] = {}
            self._apply_loan_surcharges(player)
            # 華爾街的多頭：寬限期內借的新款，第一回合不計息。
            grace_until = payload.get("loan_interest_grace_until")
            graced = []
            if grace_until is not None:
                for loan in loans:
                    borrowed = int(loan.get("taken_turn", 0) or 0)
                    if borrowed and borrowed == turn - 1 and borrowed < int(grace_until):
                        graced.append(loan)
                        loan["_grace_rate"] = float(loan["interest_per_turn"])
                        loan["interest_per_turn"] = 0.0
            for loan in loans:
                rate = float(loan["interest_per_turn"])
                entry = interest_breakdown.setdefault(
                    rate, {"rate": rate, "outstanding": 0, "interest": 0, "loans": 0},
                )
                entry["outstanding"] += int(loan["outstanding"])
                entry["interest"] += int(round(int(loan["outstanding"]) * rate))
                entry["loans"] += 1
            interest = LOANS.accrue_interest(loans)
            for loan in graced:
                loan["interest_per_turn"] = float(loan.pop("_grace_rate"))

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
            port_repair = self._collect_port_repair_due(player)
            payload["debt"] = LOANS.total_outstanding(loans)
            service = {
                "gross_income": gross_income,
                "interest": interest,
                "interest_breakdown": sorted(
                    interest_breakdown.values(), key=lambda entry: -entry["rate"],
                ),
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
                "port_repair": port_repair,
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
                # 無期限旗標（remaining_turns 為 None）永遠留著，不參與倒數。
                if effect.get("permanent") or effect.get("remaining_turns") is None:
                    active_effects.append(effect)
                    continue
                remaining = int(effect.get("remaining_turns", 0)) - 1
                if remaining > 0:
                    effect["remaining_turns"] = remaining
                    active_effects.append(effect)
            payload["timed_effects"] = active_effects
        for player in self.state["players"]:
            self._expire_relation_locked_effects(player)
        self._tick_railway_effects()
        self._tick_port_effects()
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
            # Placement must remain tied to the original scenario map. Current
            # ownership is dynamic and must never make a captured city jump to
            # the nearest tile controlled by its new owner on browser reload.
            city["scenario_faction"] = city["faction"]
            bonus = self.state.get("city_development", {}).get(city["id"], {})
            cash, factory = self._adjusted_city_output(
                city["id"],
                scaled_city_value(self._with_level(city), "cash") + int(bonus.get("cash", 0)),
                scaled_city_value(self._with_level(city), "factory") + int(bonus.get("factory", 0)),
            )
            city["cash"] = cash
            city["factory"] = factory
            # 事件卡升過級的城市，快照要送生效後的等級，前端才畫得對。
            city["level"] = int(self._with_level(city).get("level", city.get("level", 1)))
            city["faction"] = self.state.get("city_owners", {}).get(city["id"], city["scenario_faction"])
        return strategic_map

    def concession_override(self) -> Optional[Dict[str, Any]]:
        """11.2 南洋兄弟與英美煙草：期間內租界加成停發，改成每回合固定值。"""
        turn = int(self.state["turn"])
        for entry in self.state.get("concession_overrides", []):
            if turn < int(entry.get("until_turn", 0)):
                return entry
        return None

    def _concession_bonuses(self) -> Dict[str, Dict[str, Any]]:
        """租界加成，結算週期見 economy/output.py。港口無經濟效果。

        11.2 生效期間走另一套：不再每三回合結算一次原本的加成，
        改成每回合對每座租界城市固定發放（override 裡的 cash／factory）。
        """
        override = self.concession_override()
        if not override and not is_settlement_turn(int(self.state["turn"])):
            return {}
        bonuses: Dict[str, Dict[str, Any]] = {}
        for city in self.data["strategic_map"]["cities"]:
            if override:
                if not city.get("concession"):
                    continue
                cash, factory = int(override.get("cash", 0)), int(override.get("factory", 0))
            else:
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

    def _province_output_bonus(self, player: str) -> Dict[str, Dict[str, int]]:
        """地方財源技能（劉湘的四川、趙恒惕的湖南）帶來的每城每回合加成。"""

        bonus: Dict[str, Dict[str, int]] = {}
        for trait in self.state.get("faction_general_traits", {}).get(player, []):
            rule = PROVINCE_OUTPUT_TRAITS.get(trait)
            if not rule:
                continue
            entry = bonus.setdefault(rule["province"], {"cash": 0, "factory": 0})
            entry["cash"] += int(rule["cash"])
            entry["factory"] += int(rule["factory"])
        return bonus

    # ------------------------------------------------------------------
    # 省份交戰判定（11.1 江浙財團的墊款）
    #
    # 部隊的位置與「交戰中」狀態都住在前端：army.cellKey 決定它在哪一省
    # （provinceForArmy），activeBattles 裡 status 為 pending／ongoing 的那幾場
    # 決定誰在交戰（activeBattleForArmy）。前端把「現在有部隊交戰中的省份」
    # 算成一個清單，隨 next_turn 傳進來，後端只負責據此扣產出。
    # ------------------------------------------------------------------

    def bond_underwriting_for(self, player: str) -> Optional[Dict[str, Any]]:
        """11.1：這位玩家現在有沒有江浙財團的承銷特權。

        紅利跟著省份跑——條件是「完全控制清單上的每一省」且「對指定列強不友好」，
        兩省易主或倒向莫斯科都會立刻失去，奪回則恢復。
        """
        relations = self._player(player).get("foreign_relations", {})
        for entry in self.state.get("bond_underwriting", []):
            provinces = entry.get("provinces") or []
            if provinces and not all(self._controlled_provinces(player, [name])
                                     for name in provinces):
                continue
            if any(int(relations.get(power, 0)) > int(ceiling)
                   for power, ceiling in (entry.get("relation_max") or {}).items()):
                continue
            return entry
        return None

    def set_contested_provinces(self, provinces: Iterable[str]) -> list:
        """前端回報：這些省份現在有部隊處於交戰中。"""
        names = sorted({str(name) for name in (provinces or []) if str(name).strip()})
        self.state["contested_provinces"] = names
        self._refresh_city_income()
        return names

    def province_is_contested(self, province: str) -> bool:
        return str(province) in (self.state.get("contested_provinces") or [])

    def _province_combat_penalty(self, province: str) -> Dict[str, int]:
        """這一省現在因為交戰而要扣多少產出。沒在打就是 0。"""
        total = {"cash": 0, "factory": 0}
        if not self.province_is_contested(province):
            return total
        for rule in self.state.get("province_combat_penalties", []):
            if str(province) not in (rule.get("provinces") or []):
                continue
            total["cash"] += int(rule.get("cash", 0))
            total["factory"] += int(rule.get("factory", 0))
        return total

    def _city_economy_for(self, player: str) -> list[Dict[str, Any]]:
        development = self.state.get("city_development", {})
        province_bonus = self._province_output_bonus(player)
        economy = []
        for city in self.data["strategic_map"]["cities"]:
            if self.state["city_owners"].get(city["id"], city["faction"]) != player:
                continue
            general_bonus = province_bonus.get(city["province"], {"cash": 0, "factory": 0})
            # 11.1：該省正在交戰時，境內每座城市的金錢與工廠各扣一份（商界視戰事為害）。
            war = self._province_combat_penalty(city["province"])
            cash, factory = self._adjusted_city_output(
                city["id"],
                scaled_city_value(self._with_level(city), "cash")
                + int(development.get(city["id"], {}).get("cash", 0))
                + int(general_bonus["cash"]) + war["cash"],
                scaled_city_value(self._with_level(city), "factory")
                + int(development.get(city["id"], {}).get("factory", 0))
                + int(general_bonus["factory"]) + war["factory"],
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
            # 公費留學生那種「幾回合後才開始」的加成，時候到了才算進來。
            delayed = self._delayed_output_bonus(player)
            payload["city_economy"] = city_economy
            payload["income"] = (sum(item["cash"] for item in city_economy)
                                 + int(bonus.get("cash", 0)) + delayed["cash"])
            payload["factory_income"] = (sum(item["factory"] for item in city_economy)
                                         + int(bonus.get("factory", 0)) + delayed["factory"])

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
                    scaled_city_value(self._with_level(city), "cash")
                    + int(self.state.get("city_development", {}).get(city["id"], {}).get("cash", 0)),
                    scaled_city_value(self._with_level(city), "factory")
                    + int(self.state.get("city_development", {}).get(city["id"], {}).get("factory", 0)),
                ))),
            },
            "previous_owner": previous_owner,
            "owner": faction,
            "state": self.snapshot(),
        }

    def recruit_captive_general(self, player: str, traits=None, general_id=None) -> Dict[str, Any]:
        player_state = self._player(player)
        infantry_cost = 5
        if player_state["unit_reserves"].get("infantry", 0) < infantry_cost:
            raise ValueError("recruiting a captive general requires 5 infantry reserves")
        player_state["unit_reserves"]["infantry"] -= infantry_cost
        player_state["unit_reserve"] = sum(player_state["unit_reserves"].values())
        joined = self.apply_general_join(player, traits, general_id)
        return {"infantry": infantry_cost, **joined, "state": self.snapshot()}

    def attempt_defection(self, player: str, loyalty: int) -> Dict[str, Any]:
        return self.attempt_defection_with_force(player, loyalty, 1)

    def attempt_defection_with_force(
        self, player: str, loyalty: int, force: float, traits=None, resistance: float = 0.0,
        general_id=None,
    ) -> Dict[str, Any]:
        player_state = self._player(player)
        loyalty = max(1, min(10, int(loyalty)))
        force = max(1.0, float(force))
        cost = int(math.ceil((10 + force * 3 + loyalty * 2) * 0.5))
        if player_state.get("treasury", 0) < cost:
            raise ValueError(f"defection attempt requires {cost} cash")
        player_state["treasury"] -= cost
        base_chance = 0.45 - loyalty * 0.04 - force * 0.003
        # 目標將領自帶的抗策反（唐生智的〈佛教將軍〉-5%）。
        chance = max(0.03, min(0.60, base_chance * 1.25) - max(0.0, float(resistance or 0.0)))
        roll = self.random.random()
        success = roll < chance
        joined = self.apply_general_join(player, traits, general_id) if success else {}
        return {
            "success": success,
            "cost": cost,
            "chance": chance,
            "roll": roll,
            **joined,
            "state": self.snapshot(),
        }

    def draw_function(self, player: str) -> Dict[str, Any]:
        player_state = self._player(player)
        self._sync_foreign_deck_cards(player)
        self._sync_conditional_deck_cards(player)
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
            raise ValueError(f"抽功能卡需要 {FUNCTION_CARD_DRAW_COST} 現金")
        if int(player_state.get("factory_points", 0)) < FUNCTION_CARD_DRAW_FACTORY_COST:
            raise ValueError(f"抽功能卡需要 {FUNCTION_CARD_DRAW_FACTORY_COST} 工業點")
        player_state["treasury"] -= FUNCTION_CARD_DRAW_COST
        player_state["factory_points"] = int(player_state["factory_points"]) - FUNCTION_CARD_DRAW_FACTORY_COST
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
            "draw_factory_cost": FUNCTION_CARD_DRAW_FACTORY_COST,
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
        target_city_ids: Optional[list] = None,
        target_province: Optional[str] = None,
        target_provinces: Optional[list] = None,
        target_railway: Optional[str] = None,
        target_power: Optional[str] = None,
        exchange_direction: Optional[str] = None,
        exchange_amount: Optional[int] = None,
    ) -> Dict[str, Any]:
        player_state = self._player(player)
        if card_id not in player_state["hand"]:
            raise ValueError(f"{card_id!r} is not in {player}'s hand")
        card = self._card_template(card_id, player)
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
        port_demolition: Optional[Dict[str, Any]] = None
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
        exile_recruit: Optional[Dict[str, Any]] = None
        artifact_sale: Optional[Dict[str, Any]] = None
        piaohao_exchange: Optional[Dict[str, Any]] = None
        riot_shield: Optional[Dict[str, Any]] = None
        loan_effect: Optional[Dict[str, Any]] = None
        affiliation_slot_delta: Optional[Dict[str, Any]] = None
        if mechanic == "loyalty":
            if not target_general_id or not target_owner:
                raise ValueError("a target general is required")
            if target_general_id in ABSOLUTE_LOYAL_GENERAL_IDS:
                raise ValueError("this general has absolute loyalty and cannot be changed by function cards")
            if card_id == "unit_promotion" and target_owner != player:
                raise ValueError("unit promotion must target your own general")
            if card_id == "local_autonomy_agitation" and target_owner == player:
                raise ValueError("local autonomy agitation must target an opposing general")
            # 復興儒學：禮教既立，聯省自治之說難行——目標只要還控制山東就免疫。
            immunity = self.province_card_immunity(str(target_owner), card_id)
            if immunity:
                raise ValueError(
                    f"{immunity.get('label', '事件影響')}：目標仍控制{immunity['province']}，本牌對其無效")
            magnitude = int((player_state.get("radio_station") or {}).get("loyalty_magnitude", 1)) \
                if card_id in ((player_state.get("radio_station") or {}).get("affects_cards") or []) else 1
            loyalty_delta = magnitude if card_id == "unit_promotion" else -magnitude
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
            # 有聲電影製片廠：自己有片廠就多刮幾營，對方有片廠就被他的宣傳擋掉一半。
            studio = player_state.get("propaganda_studio")
            if studio:
                requested += int(studio.get("outgoing_bonus", 0))
            target_studio = target_state.get("propaganda_studio")
            if target_studio:
                requested = int(requested * float(target_studio.get("incoming_multiplier", 0.5)))
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
        elif mechanic == "multi_city_development":
            # 西門子擴產：一次挑兩座城，每座固定 +1 現金、+2 工廠，永久。
            wanted = int(card.get("city_count", 2))
            chosen = [str(item) for item in (target_city_ids or ([target_city_id] if target_city_id else []))]
            if len(chosen) != wanted:
                raise ValueError(f"本卡需要指定 {wanted} 座己方城市")
            if len(set(chosen)) != len(chosen):
                raise ValueError("兩座城市不能重複")
            owned = {item["id"] for item in player_state.get("city_economy", [])}
            missing = [city_id for city_id in chosen if city_id not in owned]
            if missing:
                raise ValueError(f"只能指定己方城市（{'、'.join(self._city_name(item) for item in missing)} 不在你手上）")
            cash = int(card.get("cash", 1))
            factory = int(card.get("factory", 2))
            for city_id in chosen:
                bonus = self.state.setdefault("city_development", {}).setdefault(city_id, {"cash": 0, "factory": 0})
                bonus["cash"] += cash
                bonus["factory"] += factory
                city_developments.append({"city_id": city_id, "cash": cash, "factory": factory})
            self._refresh_city_income()
            city_development = city_developments[0] if city_developments else None
        elif mechanic == "propaganda_studio":
            self._charge_build_cost(player, card)
            player_state["propaganda_studio"] = {
                "card_id": card_id,
                "name": card.get("name", card_id),
                "incoming_multiplier": float(card.get("incoming_multiplier", 0.5)),
                "outgoing_bonus": int(card.get("outgoing_bonus", 2)),
                "built_turn": int(self.state["turn"]),
            }
        elif mechanic == "radio_station":
            self._charge_build_cost(player, card)
            player_state["radio_station"] = {
                "card_id": card_id,
                "name": card.get("name", card_id),
                "loyalty_magnitude": int(card.get("loyalty_magnitude", 2)),
                "affects_cards": [str(item) for item in (card.get("affects_cards") or [])],
                "built_turn": int(self.state["turn"]),
            }
        elif mechanic == "oil_supply":
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "oil_price_immunity",
                "remaining_turns": int(card.get("duration_turns", 10)),
                "owners": [player],
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "delayed_factory_bonus":
            # 公費留學生：先付錢，五回合後才開始每回合多 2 點工廠。
            self._charge_build_cost(player, card)
            entry = {
                "card_id": card_id,
                "name": card.get("name", card_id),
                "start_turn": int(self.state["turn"]) + int(card.get("delay_turns", 5)),
                "cash": int(card.get("cash", 0)),
                "factory": int(card.get("factory", 0)),
            }
            player_state.setdefault("delayed_output_bonuses", []).append(entry)
        elif mechanic == "field_hospital":
            # 進口盤尼西林：指定將領的部隊戰損後可歸隊一個營，效果跟著人走。
            if not target_general_id:
                raise ValueError("進口盤尼西林需要指定一位己方將領")
            if target_owner and target_owner != player:
                raise ValueError("只能指定己方將領")
            roster = player_state.setdefault("field_hospital_generals", [])
            if target_general_id in roster:
                raise ValueError("這位將領的部隊已經配有野戰醫院了")
            self._charge_build_cost(player, card)
            roster.append(str(target_general_id))
        elif mechanic == "aerial_recon":
            # 德國飛艇偵查：一次照三個省，情報局擋不住。
            wanted = int(card.get("province_count", 3))
            provinces = [str(item).strip() for item in (target_provinces or []) if str(item).strip()]
            if len(provinces) != wanted:
                raise ValueError(f"本卡需要指定 {wanted} 個省份")
            if len(set(provinces)) != len(provinces):
                raise ValueError("三個省份不能重複")
            self._charge_build_cost(player, card)
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "aerial_recon",
                "remaining_turns": int(card.get("duration_turns", 1)),
                "owners": [player],
                "target_provinces": provinces,
                "ignores_counter_intelligence": True,
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(timed_effect))
        elif mechanic == "mechanized_division":
            if not target_general_id:
                raise ValueError("成立機械化步兵師需要指定一位己方將領")
            if target_owner and target_owner != player:
                raise ValueError("只能指定己方將領")
            fleet = player_state.setdefault("permanent_forced_march_generals", [])
            if target_general_id in fleet:
                raise ValueError("這位將領的部隊已經是機械化步兵師了")
            self._charge_build_cost(player, card)
            fleet.append(str(target_general_id))
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
            # 列強戰鬥 perk 的效果綁在關係上：關係跌破門檻就立刻失效，不等回合數走完。
            perk_power = card.get("foreign_power_key")
            if perk_power and card.get("expires_below_relation") is not None:
                timed_effect["foreign_power_key"] = str(perk_power)
                timed_effect["expires_below_relation"] = int(card["expires_below_relation"])
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
            amount = int(card.get("loyalty_delta", 0))
            radio = player_state.get("radio_station") or {}
            if card_id in (radio.get("affects_cards") or []) and amount:
                # 廣播電台只放大幅度、不改正負號。
                amount = int(radio.get("loyalty_magnitude", 1)) * (1 if amount > 0 else -1)
            loyalty_delta_all = {"owner": player, "amount": amount}
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
            player_state["loan_interest_override"] = float(card.get("loan_interest_override", 0.03))
            player_state["loan_term_bonus"] = int(player_state.get("loan_term_bonus", 0)) + int(card.get("loan_term_bonus", 0))
            unlock_effect = {
                "owner": player,
                "name": card.get("name", card_id),
                "kind": "central_bank",
                "interest_per_turn": player_state["loan_interest_override"],
                "loan_term_bonus": player_state["loan_term_bonus"],
            }
        elif mechanic in ("project_loan", "warlord_bond"):
            # 專案貸款：卡片自帶利率與到期日，不佔用該行授信額度。
            bond_privilege = None
            cash_delta = int(card.get("cash", 0))
            debt_delta = int(card.get("debt", 0))
            loan = self._record_card_loan(player, card, debt_delta)
            player_state["treasury"] += cash_delta
            if mechanic == "warlord_bond":
                # 發行公債後信用受損，列強銀行在鎖定期內拒絕任何新貸。
                # 但拿到江浙財團承銷特權的人不受這個懲罰（11.1）。
                underwriting = self.bond_underwriting_for(player)
                if underwriting and underwriting.get("no_credit_damage"):
                    bond_privilege = underwriting.get("label")
                else:
                    ban_turns = int(card.get("loan_ban_turns", 5))
                    unlock_turn = int(self.state["turn"]) + max(1, ban_turns)
                    current = player_state.get("loan_ban_until_turn")
                    player_state["loan_ban_until_turn"] = max(int(current or 0), unlock_turn)
            loan_effect = {
                "owner": player,
                "loan_id": loan["id"] if loan else None,
                "cash": cash_delta,
                "debt": debt_delta,
                "interest_per_turn": loan["interest_per_turn"] if loan else None,
                "due_turn": loan["due_turn"] if loan else None,
                "loan_ban_until_turn": player_state.get("loan_ban_until_turn"),
                "bond_privilege": bond_privilege,
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
        elif mechanic == "affiliation_slot":
            if not target_general_id:
                raise ValueError("affiliation slot upgrade requires a target general")
            if target_owner and target_owner != player:
                raise ValueError("affiliation slot upgrade can only target your own general")
            affiliation_slot_delta = {
                "owner": player,
                "general_id": target_general_id,
                "amount": 1,
            }
        elif mechanic == "permanent_player_output":
            bonus = player_state.setdefault("permanent_output_bonus", {"cash": 0, "factory": 0})
            cash = int(card.get("cash", 0))
            factory = int(card.get("factory", 0))
            bonus["cash"] = int(bonus.get("cash", 0)) + cash
            bonus["factory"] = int(bonus.get("factory", 0)) + factory
            self._refresh_city_income()
            permanent_output_delta = {"owner": player, "cash": cash, "factory": factory}
        elif mechanic == "underground_party":
            # 周恩來與地下黨：把指定的友好卡在打出者牌庫裡的份數往上抬。
            overrides = player_state.setdefault("perk_copy_overrides", {})
            for target_id, copies in (card.get("card_copies") or {}).items():
                overrides[str(target_id)] = int(copies)
            self._sync_foreign_deck_cards(player)
            unlock_effect = {
                "owner": player,
                "name": card.get("name", card_id),
                "kind": "underground_party",
                "card_copies": deepcopy(card.get("card_copies") or {}),
            }
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
            if self._gang_riot_shielded(target_owner, province, mechanic):
                raise ValueError(f"{province}有警政單位駐防，不能在此發動黑幫事件")
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
                "required_turns": int(card.get("suppression_turns", 2)),
                "label": str(card.get("disruption_label", "黑幫暴動")),
                "garrison_progress": 0,
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
        elif mechanic == "red_army_uprising":
            # 紅軍起義：兩座隨機城市產出歸零，無期限，直到目標自己派一個旅（5 營）進駐。
            if not target_owner or target_owner == player or target_owner not in self.state["players"]:
                raise ValueError("red army uprising must target another playable faction")
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
                "required_turns": int(card.get("required_turns", 2)),
                "garrison_progress": {},
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
            self._notify(
                target_owner,
                f"{card.get('name', card_id)}：{'、'.join(city['name'] for city in selected)} 產出歸零，"
                f"每城需連續駐紮至少 {required} 營 {int(card.get('required_turns', 2))} 回合才能恢復。",
            )
        elif mechanic == "railway_sabotage":
            # 崩鐵玩家：一條鐵路停運三回合，期間該線不能做鐵路運輸，
            # 沿線地格視為普通地格照常通行；非使用方共同分攤搶修工業點。
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
                # 搶修攤派：除使用者外，每位勢力工業點各 −10。
                "repair_factory_cost": int(card.get("repair_factory_cost", 10)),
                "repair_charges": {},
            }
            charge = railway_effect["repair_factory_cost"]
            for code, payload in self.state["players"].items():
                if code == player:
                    continue
                before = int(payload.get("factory_points", 0))
                payload["factory_points"] = max(0, before - charge)
                railway_effect["repair_charges"][code] = before - payload["factory_points"]
                self._notify(
                    code,
                    f"{railway}遭破壞停運，搶修 {railway_effect['remaining_turns']} 回合，"
                    f"你分攤搶修工業點 −{railway_effect['repair_charges'][code]}。",
                )
            self.state.setdefault("railway_effects", []).append(deepcopy(railway_effect))
        elif mechanic == "port_demolition":
            # 大港開炸：任選兩座敵方港口城市（河港、海港皆可，可同勢力也可分屬兩方），
            # 癱瘓 2 回合；每個被炸到的勢力各出 $10 與工業點 10 修復，
            # 當下付不出來的部分記成欠款，之後每回合從收入自動扣繳。
            wanted = int(card.get("target_city_count", 2))
            chosen_ids = [str(item) for item in (target_city_ids or []) if str(item).strip()]
            if len(set(chosen_ids)) != wanted:
                raise ValueError(f"{card.get('name', card_id)}需要指定 {wanted} 座不同的敵方港口城市")
            ports = {
                city["id"]: city
                for city in self.data["strategic_map"]["cities"]
                if city.get("port")
            }
            downed = set(self.disabled_ports())
            selected = []
            for city_id in chosen_ids:
                city = ports.get(city_id)
                if city is None:
                    raise ValueError(f"{city_id} 不是港口城市")
                owner = self.state["city_owners"].get(city_id, city["faction"])
                if owner == player:
                    raise ValueError(f"{city['name']}是己方港口，不能自己炸")
                if owner not in self.state["players"]:
                    raise ValueError(f"{city['name']}目前不屬於任何可操作勢力")
                if city_id in downed:
                    raise ValueError(f"{city['name']}已經在搶修中")
                selected.append((city, owner))
            duration = int(card.get("duration_turns", 2))
            repair_cash = int(card.get("repair_cash_cost", 10))
            repair_factory = int(card.get("repair_factory_cost", 10))
            port_entries = []
            for city, owner in selected:
                effect = {
                    "id": f"{card_id}:{self.state['turn']}:{player}:{city['id']}",
                    "card_id": card_id,
                    "name": card.get("name", card_id),
                    "initiator": player,
                    "city_id": city["id"],
                    "city_name": city["name"],
                    "port": city.get("port"),
                    "owner": owner,
                    "remaining_turns": duration,
                }
                self.state.setdefault("port_effects", []).append(deepcopy(effect))
                port_entries.append(effect)
            # 修復費按港口算：同一勢力被炸兩座港口就付兩份。
            charges = []
            for city, owner in selected:
                charged = self._charge_port_repair(owner, repair_cash, repair_factory)
                charged["city_id"] = city["id"]
                charged["city_name"] = city["name"]
                charges.append(charged)
                shortfall = charged["due"]["cash"] + charged["due"]["factory"]
                self._notify(
                    owner,
                    f"{card.get('name', card_id)}：{city['name']}港務癱瘓 {duration} 回合，"
                    f"修復支出 ${charged['paid']['cash']}、工業點 {charged['paid']['factory']}。"
                    + (f"累計不足的 ${charged['due']['cash']} 與工業點 {charged['due']['factory']} 由之後回合收入扣繳。"
                       if shortfall else ""),
                )
            port_demolition = {
                "ports": [
                    {"city_id": entry["city_id"], "city_name": entry["city_name"],
                     "owner": entry["owner"], "remaining_turns": entry["remaining_turns"]}
                    for entry in port_entries
                ],
                "charges": charges,
            }
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
        elif mechanic == "exile_recruit":
            # 在野名將投效：自在野將領池指定一名尚未出山者延攬，付其身價全額，
            # 該將領帶著自帶部隊在延攬方大帥的所在地現身。全池每人只能被延攬一次。
            # 引擎不持有將領樹（那是唯讀檔案），這裡只負責扣款、鎖定人選並記錄結果，
            # 實際把人放進將領樹與地圖的是前端。
            pool = self.data["generals_in_exile"]["generals"]
            taken = self.state.setdefault("recruited_exiles", {})
            # 有些人有舊怨，不肯投靠特定陣營（盧永祥不投五省聯軍、陳炯明不投國民革命軍）。
            available = [
                gid for gid in pool
                if gid not in taken and player not in pool[gid].get("forbidden_factions", [])
            ]
            if not available:
                # 池空時本卡改為補充部隊：步兵 ×2、機槍 ×1，
                # 只收該勢力募兵現金的一半（無條件進位），且不收工業點。
                top_up = {"infantry": 2, "machine_gun": 1}
                full_cash = sum(
                    self._unit_cost_for(player, unit_type)[0] * count
                    for unit_type, count in top_up.items()
                )
                price = (full_cash + 1) // 2
                if int(player_state["treasury"]) < price:
                    raise ValueError(f"補充部隊需要 {price} 現金")
                cost += price
                army_unit_delta = {
                    "owner": player,
                    "general_id": "",
                    "unit_reserves": dict(top_up),
                    "requires_active": False,
                    "price": price,
                    "factory_cost": 0,
                    "reason": "在野將領池已空，改為半價補充部隊（不收工業點）",
                }
            else:
                if not target_general_id:
                    raise ValueError("延攬在野名將需要指定人物")
                if target_general_id not in pool:
                    raise ValueError("該人物不在在野將領池中")
                if target_general_id in taken:
                    raise ValueError("該人物已經出山，不在在野將領池中")
                recruit = pool[target_general_id]
                if player in recruit.get("forbidden_factions", []):
                    raise ValueError(f"{recruit['name']}不願投靠此陣營")
                # 延攬費為身價全額，另加出山附加費（請人重新拉隊伍的開辦成本）。
                price = int(recruit.get("recruit_value", 0)) + EXILE_RECRUIT_SURCHARGE
                if int(player_state["treasury"]) < price:
                    raise ValueError(f"延攬{recruit['name']}需要 {price} 現金")
                cost += price
                taken[target_general_id] = player
                exile_recruit = {
                    "owner": player,
                    "general_id": target_general_id,
                    "name": recruit["name"],
                    "price": price,
                    "units": deepcopy(recruit.get("units", {})),
                    "command_cap": recruit.get("command_cap"),
                    "loyalty": recruit.get("loyalty"),
                    "traits": list(recruit.get("traits", [])),
                    "skills": list(recruit.get("skills", [])),
                    "turn": int(self.state["turn"]),
                }
        elif mechanic == "artifact_smuggling":
            # 盜賣文物：向指定列強變賣文物，隨機進帳、關係 +1，
            # 代價是自己的牌庫被塞進三張〈中國人之恥〉（全場上限 9 張）。
            power = str(target_power or "").strip()
            allowed_powers = card.get("powers") or list(POWER_NAMES)
            if not power:
                raise ValueError("盜賣文物需要指定一個列強")
            if power not in allowed_powers:
                raise ValueError(f"盜賣文物只能指定 {'、'.join(POWER_NAMES.get(key, key) for key in allowed_powers)}")
            relations = player_state.setdefault("foreign_relations", {})
            if power not in relations:
                raise ValueError(f"沒有對{POWER_NAMES.get(power, power)}的關係紀錄")
            payout = self.random.randint(int(card.get("payout_min", 20)), int(card.get("payout_max", 40)))
            cash_delta += payout
            player_state["treasury"] += payout
            before = int(relations[power])
            after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + int(card.get("relation_gain", 1))))
            relations[power] = after
            foreign_relation_delta = {
                "power": power, "before": before, "after": after,
                "amount": after - before, "success": True,
            }
            # 離開江蘇期間還去賣文物，中央研究院從此不認這一家。
            academia_lost = self.disqualify_academia(player, "在離開江蘇期間打出〈盜賣文物〉")
            shame_id = str(card.get("shame_card_id", "national_shame"))
            shame_template = self._card_template(shame_id)
            cap = int(shame_template.get("max_copies", 9))
            already = self._card_count_in_player_zones(player_state, shame_id)
            added = max(0, min(int(card.get("shame_copies_per_use", 3)), cap - already))
            if added:
                player_state["function_deck"].extend([shame_id] * added)
                self.random.shuffle(player_state["function_deck"])
            self._sync_foreign_deck_cards(player)
            artifact_sale = {
                "owner": player, "power": power, "payout": payout,
                "shame_cards_added": added, "shame_cards_total": already + added, "shame_cap": cap,
            }
        elif mechanic == "trade_export":
            # 對列強貿易出口：消耗工業點換現金與關係。
            power = str(card.get("foreign_power_key") or "")
            factory_cost = int(card.get("factory_cost", 50))
            if int(player_state.get("factory_points", 0)) < factory_cost:
                raise ValueError(f"貿易出口需要 {factory_cost} 工業點（目前 {int(player_state.get('factory_points', 0))}）")
            player_state["factory_points"] = int(player_state["factory_points"]) - factory_cost
            gain = int(card.get("cash_gain", 20))
            cash_delta += gain
            player_state["treasury"] += gain
            relations = player_state.setdefault("foreign_relations", {})
            before = int(relations.get(power, 0))
            after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + int(card.get("relation_gain", 1))))
            relations[power] = after
            foreign_relation_delta = {
                "power": power, "before": before, "after": after,
                "amount": after - before, "success": True, "factory_cost": factory_cost,
            }
            self._sync_foreign_deck_cards(player)
        elif mechanic == "piaohao_exchange":
            # 票號金融網：工業點與現金雙向互兌，兩邊同一匯率（預設 2 工業點 ↔ $1），
            # 所以來回空轉不賺不賠，只是換個形式擺著。不設數量上限，
            # 上限就是你手上實際有多少；工業點那一邊必須是匯率的整數倍，湊不成整份的不受理。
            rate = max(1, int(card.get("factory_per_cash", 2)))
            direction = str(exchange_direction or "").strip()
            if direction not in ("factory_to_cash", "cash_to_factory"):
                raise ValueError("票號金融網需要指定兌換方向："
                                 "factory_to_cash（賣工廠換錢）或 cash_to_factory（用錢買工廠）")
            try:
                amount = int(exchange_amount)
            except (TypeError, ValueError):
                raise ValueError("票號金融網需要指定兌換數量")
            if amount <= 0:
                raise ValueError("票號金融網的兌換數量必須大於 0")
            factory_before = int(player_state.get("factory_points", 0))
            cash_before = int(player_state["treasury"])
            if direction == "factory_to_cash":
                # amount 是要賣掉的工業點
                if amount % rate:
                    raise ValueError(f"賣工廠須以 {rate} 工業點為一份，{amount} 湊不成整份")
                if factory_before < amount:
                    raise ValueError(f"工業點不足：想賣 {amount}，目前只有 {factory_before}")
                gained = amount // rate
                player_state["factory_points"] = factory_before - amount
                player_state["treasury"] = cash_before + gained
                cash_delta += gained
                factory_spent, cash_spent = amount, 0
                factory_gained, cash_gained = 0, gained
            else:
                # amount 是要花掉的現金
                if cash_before < amount:
                    raise ValueError(f"現金不足：想花 ${amount}，目前只有 ${cash_before}")
                gained = amount * rate
                player_state["treasury"] = cash_before - amount
                player_state["factory_points"] = factory_before + gained
                cash_delta -= amount
                factory_spent, cash_spent = 0, amount
                factory_gained, cash_gained = gained, 0
            piaohao_exchange = {
                "owner": player, "direction": direction, "rate": rate,
                "factory_spent": factory_spent, "factory_gained": factory_gained,
                "cash_spent": cash_spent, "cash_gained": cash_gained,
                "factory_before": factory_before,
                "factory_after": int(player_state["factory_points"]),
                "cash_before": cash_before,
                "cash_after": int(player_state["treasury"]),
            }
        elif mechanic == "gang_riot_shield":
            # 警政單位：指定我方一省，3 回合內免疫黑幫暴動，並立即平息該省現行的暴動。
            province = str(target_province or "").strip()
            if not province:
                raise ValueError("警政單位需要指定一個省份")
            own_cities = [
                city for city in self.data["strategic_map"]["cities"]
                if city.get("province") == province
                and self.state["city_owners"].get(city["id"], city["faction"]) == player
            ]
            if not own_cities:
                raise ValueError(f"你在{province}沒有控制中的城市")
            blocked = list(card.get("blocked_mechanics") or ["qing_gang_riot"])
            quelled = [
                effect for effect in self.state.get("city_output_effects", [])
                if effect.get("kind") in blocked
                and effect.get("target_owner") == player
                and effect.get("province") == province
            ]
            if quelled:
                self.state["city_output_effects"] = [
                    effect for effect in self.state["city_output_effects"] if effect not in quelled
                ]
                self._refresh_city_income()
            shield = {
                "id": f"{card_id}:{self.state['turn']}:{player}:{province}",
                "name": card.get("name", card_id),
                "kind": "gang_riot_shield",
                "owner": player,
                "province": province,
                "blocked_mechanics": blocked,
                "remaining_turns": int(card.get("duration_turns", 3)),
            }
            player_state.setdefault("timed_effects", []).append(deepcopy(shield))
            timed_effect = deepcopy(shield)
            riot_shield = {
                "owner": player, "province": province,
                "quelled": [effect.get("id") for effect in quelled],
                "quelled_count": len(quelled),
                "remaining_turns": shield["remaining_turns"],
            }
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
        cabinet_entry = self._register_cabinet_card(player, card) if card.get("cabinet") else None
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
            "affiliation_slot_delta": affiliation_slot_delta,
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
            "port_demolition": port_demolition,
            "cabinet_entry": cabinet_entry,
            "unlock_effect": unlock_effect,
            "assassination": assassination,
            "body_guard": body_guard,
            "exile_recruit": exile_recruit,
            "artifact_sale": artifact_sale,
            "piaohao_exchange": piaohao_exchange,
            "riot_shield": riot_shield,
            "loan_effect": loan_effect,
            "relation_side_effects": relation_side_effects,
        }
        return {
            "card": card,
            "target_general_id": target_general_id,
            "target_owner": target_owner,
            "loyalty_delta": loyalty_delta,
            "loyalty_delta_all": loyalty_delta_all,
            "loyalty_swings": loyalty_swings,
            "reserve_delta": reserve_delta,
            "reserve_deltas": reserve_deltas,
            "army_unit_delta": army_unit_delta,
            "affiliation_slot_delta": affiliation_slot_delta,
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
            "port_demolition": port_demolition,
            "cabinet_entry": cabinet_entry,
            "unlock_effect": unlock_effect,
            "assassination": assassination,
            "body_guard": body_guard,
            "exile_recruit": exile_recruit,
            "artifact_sale": artifact_sale,
            "piaohao_exchange": piaohao_exchange,
            "riot_shield": riot_shield,
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
        turn = int(self.state["turn"])
        timed = {"cash": 0, "factory": 0}
        for entry in player_state.get("timed_recruit_discounts", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            unit_delta = (entry.get("units") or {}).get(unit_type)
            if not unit_delta:
                continue
            timed["cash"] += int(unit_delta.get("cash", 0))
            timed["factory"] += int(unit_delta.get("factory", 0))
        adjustment = player_state.get("recruit_cost_adjustment", {}).get(unit_type, {})
        # 只在控制指定省份時才成立的折價（晏陽初辦學鄉村：控四省任一者步兵 −$1）。
        province = self._province_recruit_discount(player, unit_type)
        cash = math.ceil(base["cash"] * player_state.get("recruitment_cost_modifier", 1))
        cash = max(1, cash + int(adjustment.get("cash", 0)) + timed["cash"] + province["cash"])
        factory = max(0, int(base["factory"]) + int(adjustment.get("factory", 0))
                     + timed["factory"] + province["factory"])
        return cash, factory

    def _province_recruit_discount(self, player: str, unit_type: str) -> Dict[str, int]:
        """省份綁定的徵兵折價：控制清單裡任一省就生效，全丟光就沒了。"""
        total = {"cash": 0, "factory": 0}
        for entry in self.state.get("province_recruit_discounts", []):
            delta = (entry.get("units") or {}).get(unit_type)
            if not delta:
                continue
            provinces = entry.get("provinces") or []
            if provinces and not any(self._controlled_provinces(player, [name])
                                     for name in provinces):
                continue
            total["cash"] += int(delta.get("cash", 0))
            total["factory"] += int(delta.get("factory", 0))
        return total

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

    def train_navy_unit(self, player: str, unit_type: str, count: int = 1) -> Dict[str, Any]:
        player_state = self._player(player)
        if unit_type not in NAVY_RECRUIT_COSTS:
            raise ValueError(f"unknown navy unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("navy recruit count must be positive")
        unit_cost = NAVY_RECRUIT_COSTS[unit_type]
        cash_cost = int(unit_cost["cash"]) * count
        factory_cost = int(unit_cost["factory"]) * count
        if player_state["treasury"] < cash_cost:
            raise ValueError("insufficient treasury")
        if player_state["factory_points"] < factory_cost:
            raise ValueError("insufficient factory points")
        player_state["treasury"] -= cash_cost
        player_state["factory_points"] -= factory_cost
        reserves = player_state.setdefault("navy_reserves", {"gun_boat": 0, "cargo_boat": 0})
        reserves[unit_type] = int(reserves.get(unit_type, 0)) + count
        return {"state": self.snapshot()}

    def reinforce_navy(self, player: str, city_id: str, unit_type: str, count: int = 1) -> Dict[str, Any]:
        player_state = self._player(player)
        if unit_type not in NAVY_RECRUIT_COSTS:
            raise ValueError(f"unknown navy unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("navy reinforcement count must be positive")
        city = next(
            (item for item in self.data["strategic_map"]["cities"] if item["id"] == city_id),
            None,
        )
        owner = self.state.get("city_owners", {}).get(city_id, city["faction"] if city else None)
        if not city or owner != player or city.get("port") not in {"river", "sea"}:
            raise ValueError("navy reserve transfer requires a controlled harbor")
        reserves = player_state.setdefault("navy_reserves", {"gun_boat": 0, "cargo_boat": 0})
        if int(reserves.get(unit_type, 0)) < count:
            raise ValueError("insufficient navy reserve")
        reserves[unit_type] = int(reserves.get(unit_type, 0)) - count
        return {"state": self.snapshot()}

    def reinforce_army(
        self,
        player: str,
        army_id: str,
        city_id: str,
        unit_type: str,
        count: int = 1,
        current_force: Optional[float] = None,
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
        owner = self.state.get("city_owners", {}).get(city_id, city["faction"] if city else None)
        if not city or owner != player or int(self._with_level(city)["level"]) < 3:
            raise ValueError("reinforcement requires a controlled major city")
        if self.city_in_student_unrest(city_id):
            raise ValueError(f"{city['name']}正值學潮，本地不可補充兵力")
        if current_force is not None:
            next_force = float(current_force) + UNIT_FORCE_POINTS[unit_type] * count
            if next_force > ARMY_FORCE_CAP:
                raise ValueError(
                    f"補充後戰力 {int(next_force)} 會超過單一部隊上限 {ARMY_FORCE_CAP}"
                )
        if player_state["unit_reserves"][unit_type] < count:
            raise ValueError("insufficient unit reserve")
        player_state["unit_reserves"][unit_type] -= count
        player_state["unit_reserve"] = sum(player_state["unit_reserves"].values())
        # Army composition lives in the shared tactical state.  Older builds
        # also accumulated this transfer in ``army_reinforcements``; combat
        # then materialized that ledger into the army and counted it again on
        # the next synchronization.  Return the accepted delta explicitly so
        # the frontend can update the one authoritative army record.
        player_state.setdefault("army_reinforcements", {}).pop(army_id, None)
        return {
            "state": self.snapshot(),
            "army_id": army_id,
            "unit_type": unit_type,
            "count": count,
        }

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
        # 事件卡可以永久改寫某張卡的利率（11.3 不裁兵 → 軍閥公債 12%）。
        for override in payload.get("loan_rate_overrides") or []:
            if str(override.get("card_id")) == str(card.get("id")):
                interest = float(override["interest_per_turn"])
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
        if card.get("domestic_bond"):
            # 公債是自己發的，不欠任何列強銀行。內部仍掛在中立的德華以取得條件欄位，
            # 但對外一律以公債身分顯示，掛自己陣營的旗。
            loan["domestic"] = True
            loan["issuer"] = player
            loan["bank_name"] = card.get("name", "公債")
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

    # ------------------------------------------------------------------
    # 城市等級覆寫
    # ------------------------------------------------------------------

    def _with_level(self, city: Dict[str, Any]) -> Dict[str, Any]:
        """套上事件卡的等級覆寫之後再交出去；沒有覆寫就原物奉還。"""
        # new_game 建初始快照時 self.state 還不存在，那時當然也還沒有任何覆寫。
        state = getattr(self, "state", None) or {}
        override = (state.get("city_level_overrides") or {}).get(city.get("id"))
        if override is None:
            return city
        adjusted = dict(city)
        adjusted["level"] = int(override)
        return adjusted

    def effective_city_level(self, city_id: str) -> int:
        """這座城現在實際上是幾級（含事件卡覆寫）。"""
        city = next((c for c in self.data["strategic_map"]["cities"]
                     if c["id"] == city_id), None)
        if not city:
            return 0
        return int(self._with_level(city).get("level", 1))

    def bank_limit_adjustments(self, player: str) -> Dict[str, Any]:
        """事件卡對這位玩家授信額度的加減，交給 LoanBook 套用。

        `bonus` 永久固定加值（2.1 德意志入盟給德華 +15）；
        `factor` 限時倍率（6.1 佛州地產崩讓花旗打對折、6.4 華爾街多頭全面 ×1.5）。
        """
        turn = int(self.state["turn"])
        bonus = dict(self._player(player).get("bank_limit_bonus") or {})
        factor: Dict[str, float] = {}
        for entry in self.state.get("bank_limit_multipliers", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            banks = entry.get("banks") or ([entry["bank"]] if entry.get("bank") else [])
            for bank_id in banks:
                factor[bank_id] = factor.get(bank_id, 1.0) * float(entry.get("factor", 1))
        return {"bonus": bonus, "factor": factor}

    def loan_offers(self, player: str) -> Dict[str, Any]:
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        turn = int(self.state["turn"])
        ban_until = payload.get("loan_ban_until_turn")
        ban_active = ban_until is not None and turn < int(ban_until)
        offers = LOANS.offers(payload.get("foreign_relations", {}), loans, turn,
                              self.bank_limit_adjustments(player))
        if ban_active:
            for offer in offers:
                if offer.get("bank") is None:
                    continue
                offer["can_borrow"] = False
                offer["loan_ban_until_turn"] = int(ban_until)
                offer["loan_ban_remaining_turns"] = int(ban_until) - turn
                offer["tier_label"] = f"銀行拒貸至第 {int(ban_until)} 回合"
        return {
            "player": player,
            "turn": turn,
            "treasury": int(payload.get("treasury", 0)),
            "debt": LOANS.total_outstanding(loans),
            "loan_ban_until_turn": int(ban_until) if ban_until is not None else None,
            "loan_ban_remaining_turns": int(ban_until) - turn if ban_active else 0,
            "offers": offers,
            "loans": self._loan_rows(player),
        }

    def _loan_rows(self, player: str) -> list:
        payload = self._player(player)
        turn = int(self.state["turn"])
        rows = []
        for loan in payload.get("loans", []):
            rows.append({
                **deepcopy(loan),
                # 公債不掛列強，改由前端用發行陣營的旗幟顯示。
                "bank_power": None if loan.get("domestic") else LOANS.banks.get(loan["bank"], {}).get("power"),
                "turns_remaining": int(loan["due_turn"]) - turn,
            })
        return rows

    def take_loan(self, player: str, bank_id: str, amount: int) -> Dict[str, Any]:
        payload = self._player(player)
        loans = payload.setdefault("loans", [])
        relations = payload.get("foreign_relations", {})
        ban_until = payload.get("loan_ban_until_turn")
        if ban_until is not None and int(self.state["turn"]) < int(ban_until):
            raise ValueError(f"列強銀行因軍閥公債拒絕新貸，需等到第 {int(ban_until)} 回合")
        event_ban = self.bank_banned(player, str(bank_id))
        if event_ban:
            raise ValueError(f"{event_ban.get('label', '事件影響')}，需等到第 {int(event_ban['until_turn'])} 回合")
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

    # 急行軍改成按部隊購買的軍令：$10 + 10 工業點換該支部隊 3 回合的兩格移動，
    # 冷卻與剩餘回合由前端逐軍記錄，引擎只負責收錢。
    FORCED_MARCH_COST_CASH = 10
    FORCED_MARCH_COST_FACTORY = 10
    FORCED_MARCH_DURATION_TURNS = 3
    FORCED_MARCH_COOLDOWN_TURNS = 3
    FORCED_MARCH_TILES = 2

    def pay_forced_march(self, player: str, *, cash: int = FORCED_MARCH_COST_CASH,
                         factory: int = FORCED_MARCH_COST_FACTORY, army_id: str = "") -> Dict[str, Any]:
        player_state = self._player(player)
        cash = max(0, int(cash))
        factory = max(0, int(factory))
        if int(player_state.get("treasury", 0)) < cash:
            raise ValueError(f"急行軍需要 {cash} 現金")
        if int(player_state.get("factory_points", 0)) < factory:
            raise ValueError(f"急行軍需要 {factory} 工業點")
        player_state["treasury"] = int(player_state.get("treasury", 0)) - cash
        player_state["factory_points"] = int(player_state.get("factory_points", 0)) - factory
        self.state["last_action"] = {
            "type": "forced_march_order",
            "player": player,
            "army_id": str(army_id) if army_id else None,
            "cash": cash,
            "factory": factory,
            "duration_turns": self.FORCED_MARCH_DURATION_TURNS,
            "cooldown_turns": self.FORCED_MARCH_COOLDOWN_TURNS,
            "tiles": self.FORCED_MARCH_TILES,
        }
        return {
            "cash": cash,
            "factory": factory,
            "army_id": str(army_id) if army_id else None,
            "duration_turns": self.FORCED_MARCH_DURATION_TURNS,
            "cooldown_turns": self.FORCED_MARCH_COOLDOWN_TURNS,
            "tiles": self.FORCED_MARCH_TILES,
            "state": self.snapshot(),
        }

    def pay_navy_move(self, player: str, *, factory: Optional[int] = None) -> Dict[str, Any]:
        player_state = self._player(player)
        cost = int(factory if factory is not None else self.data["navy_system"]["move"]["factory_cost"])
        if cost < 0:
            raise ValueError("navy movement cost cannot be negative")
        if int(player_state.get("factory_points", 0)) < cost:
            raise ValueError(f"艦隊機動需要 {cost} 工業點")
        player_state["factory_points"] = int(player_state.get("factory_points", 0)) - cost
        self.state["last_action"] = {
            "type": "navy_move_order",
            "player": player,
            "factory": cost,
        }
        return {"factory": cost, "state": self.snapshot()}

    def repair_navy(self, player: str, hp: int) -> Dict[str, Any]:
        player_state = self._player(player)
        hp = max(0, int(hp))
        cost_per_hp = int(self.data["navy_system"]["repair"]["factory_cost_per_hp"])
        cost = hp * cost_per_hp
        if hp <= 0:
            raise ValueError("navy repair must restore positive HP")
        if int(player_state.get("factory_points", 0)) < cost:
            raise ValueError(f"艦艇修理需要 {cost} 工業點")
        player_state["factory_points"] = int(player_state.get("factory_points", 0)) - cost
        self.state["last_action"] = {
            "type": "navy_repair",
            "player": player,
            "hp": hp,
            "factory": cost,
        }
        return {"hp": hp, "factory": cost, "state": self.snapshot()}

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
            scaled_city_value(self._with_level(city), "cash") + int(bonus.get("cash", 0)),
            scaled_city_value(self._with_level(city), "factory") + int(bonus.get("factory", 0)),
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
                "name": effect.get("name", "黑幫暴動"),
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
            if effect["garrison_progress"] < int(effect.get("required_turns", 2)):
                active_effects.append(effect)
        self.state["city_output_effects"] = active_effects
        self._refresh_city_income()

    def _gang_riot_shielded(self, owner: str, province: str, mechanic: str) -> bool:
        """該勢力的這個省是否有警政單位駐防。"""
        for effect in self._player(owner).get("timed_effects", []):
            if effect.get("kind") != "gang_riot_shield":
                continue
            if int(effect.get("remaining_turns", 0)) <= 0:
                continue
            if effect.get("province") != province:
                continue
            if mechanic in (effect.get("blocked_mechanics") or []):
                return True
        return False

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

    def _has_fast_uprising_suppression(self, player: str) -> bool:
        if player not in self.state.get("players", {}):
            return False
        for trait, rule in FAST_UPRISING_SUPPRESSION_TRAITS.items():
            if not self._faction_has_trait(player, trait):
                continue
            if self._trait_relation_disabled(player, rule.get("disabled_when")):
                continue
            return True
        return False

    def _update_red_army_uprisings(self, city_garrisons: Dict[str, int]) -> None:
        """紅軍起義沒有回合上限：一座城要連續駐滿一個旅兩回合才恢復產出。

        中斷就歸零重算，和黑幫暴動的鎮壓計數是同一套邏輯。
        """
        active_effects = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") != "red_army_uprising":
                active_effects.append(effect)
                continue
            required = int(effect.get("required_battalions", 5))
            required_turns = int(effect.get("required_turns", 2))
            # 剿共技能（何鍵、陳炯明）：起義只要駐滿一回合就平定。
            if self._has_fast_uprising_suppression(str(effect.get("target_owner", ""))):
                required_turns = 1
            progress = effect.setdefault("garrison_progress", {})
            freed = []
            for city in effect.get("cities", []):
                if int(city_garrisons.get(city["id"], 0)) >= required:
                    progress[city["id"]] = int(progress.get(city["id"], 0)) + 1
                else:
                    progress[city["id"]] = 0
                if progress[city["id"]] >= required_turns:
                    freed.append(city)
            if freed:
                freed_ids = {city["id"] for city in freed}
                effect["cities"] = [city for city in effect.get("cities", []) if city["id"] not in freed_ids]
                effect["city_ids"] = [item for item in effect.get("city_ids", []) if item not in freed_ids]
                for city_id in freed_ids:
                    progress.pop(city_id, None)
                self._notify(
                    str(effect.get("target_owner")),
                    f"{effect.get('name', '紅軍起義')}："
                    f"{'、'.join(city['name'] for city in freed)} 已連續駐滿 {required} 營 {required_turns} 回合，產出恢復。",
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

    def _charge_port_repair(self, owner: str, cash: int, factory: int) -> Dict[str, Any]:
        """先從手頭扣，扣不完的掛成欠款，之後每回合結算時再扣。"""
        payload = self._player(owner)
        paid_cash = min(int(payload.get("treasury", 0)), int(cash))
        paid_factory = min(int(payload.get("factory_points", 0)), int(factory))
        payload["treasury"] = int(payload.get("treasury", 0)) - paid_cash
        payload["factory_points"] = int(payload.get("factory_points", 0)) - paid_factory
        due = payload.setdefault("port_repair_due", {"cash": 0, "factory": 0})
        due["cash"] = int(due.get("cash", 0)) + int(cash) - paid_cash
        due["factory"] = int(due.get("factory", 0)) + int(factory) - paid_factory
        return {
            "owner": owner,
            "paid": {"cash": paid_cash, "factory": paid_factory},
            "due": {"cash": int(due["cash"]), "factory": int(due["factory"])},
        }

    def _collect_port_repair_due(self, owner: str) -> Dict[str, int]:
        """結算時把積欠的港口修復費從當期收入裡扣掉。"""
        payload = self._player(owner)
        due = payload.setdefault("port_repair_due", {"cash": 0, "factory": 0})
        cash = min(int(payload.get("treasury", 0)), int(due.get("cash", 0)))
        factory = min(int(payload.get("factory_points", 0)), int(due.get("factory", 0)))
        if cash:
            payload["treasury"] = int(payload["treasury"]) - cash
            due["cash"] = int(due["cash"]) - cash
        if factory:
            payload["factory_points"] = int(payload["factory_points"]) - factory
            due["factory"] = int(due["factory"]) - factory
        return {"cash": cash, "factory": factory,
                "remaining_cash": int(due["cash"]), "remaining_factory": int(due["factory"])}

    def _tick_port_effects(self) -> None:
        active = []
        for effect in self.state.get("port_effects", []):
            remaining = int(effect.get("remaining_turns", 0)) - 1
            if remaining > 0:
                effect["remaining_turns"] = remaining
                active.append(effect)
        self.state["port_effects"] = active

    def disabled_ports(self) -> list:
        """遭大港開炸癱瘓的港口城市 id，前端據此關閉停靠、通行與各項港口作業。"""
        return [
            str(effect.get("city_id"))
            for effect in self.state.get("port_effects", [])
            if int(effect.get("remaining_turns", 0)) > 0
        ]

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

    def _perk_copies(self, card_id: str, player: Optional[str] = None) -> int:
        base = FOREIGN_PERK_CARD_COPIES_BY_ID.get(card_id, FOREIGN_PERK_CARD_COPIES)
        if player is None:
            return base
        # 周恩來與地下黨這類卡片會把某幾張友好卡的份數往上抬，只對打出者生效。
        bumped = self._player(player).get("perk_copy_overrides", {}).get(card_id)
        return max(base, int(bumped)) if bumped is not None else base

    # ── 陣營層級的將領技能：買辦、地方財源、剿共 ──────────────────────
    def _initial_faction_general_traits(self) -> Dict[str, list]:
        """開局時各可玩陣營手上有哪些陣營層級技能。"""

        holders: Dict[str, list] = {}
        for faction, tree in self.data.get("playable_general_trees", {}).items():
            owned = sorted({
                trait
                for general in tree.get("generals", {}).values()
                for trait in general.get("traits", [])
                if trait in FACTION_LEVEL_TRAITS
            })
            if owned:
                holders[faction] = owned
        return holders

    def faction_general_traits(self, player: str) -> list:
        return list(self.state.get("faction_general_traits", {}).get(player, []))

    def _faction_has_trait(self, player: str, trait: str) -> bool:
        return trait in self.state.get("faction_general_traits", {}).get(player, [])

    def _trait_relation_disabled(self, player: str, rule: Dict[str, Any]) -> bool:
        """技能因為持有陣營的列強關係而失效（何鍵：自己也親蘇就沒得剿了）。"""

        if not rule:
            return False
        value = int(self._player(player).get("foreign_relations", {}).get(rule["power"], 0))
        if "min" in rule and value >= int(rule["min"]):
            return True
        if "max" in rule and value <= int(rule["max"]):
            return True
        return False

    # 這兩張卡買的是「這位將領的部隊」，人走了效果就沒了，也不隨他過去。
    GENERAL_BOUND_PERK_KEYS = ("permanent_forced_march_generals", "field_hospital_generals")

    def drop_general_bound_perks(self, general_id: str) -> list:
        """將領換東家：把他身上由功能卡買來的永久效果從所有陣營的名單裡拔掉。"""
        dropped = []
        for code, payload in self.state["players"].items():
            for key in self.GENERAL_BOUND_PERK_KEYS:
                roster = payload.get(key) or []
                if general_id in roster:
                    payload[key] = [item for item in roster if item != general_id]
                    dropped.append({"player": code, "effect": key, "general_id": general_id})
        return dropped

    def apply_general_join(self, player: str, traits, general_id: Optional[str] = None) -> Dict[str, Any]:
        """將領轉投某陣營時帶來的非戰鬥效果。技能跟著人走，舊東家同時失去。"""

        traits = [trait for trait in (traits or []) if trait in FACTION_LEVEL_TRAITS]
        result: Dict[str, Any] = {}
        if general_id:
            dropped = self.drop_general_bound_perks(str(general_id))
            if dropped:
                result["dropped_general_perks"] = dropped
        if not traits and result:
            return result
        if not traits:
            return result
        holders = self.state.setdefault("faction_general_traits", {})
        for faction in list(holders):
            remaining = [trait for trait in holders[faction] if trait not in traits]
            if remaining:
                holders[faction] = remaining
            else:
                holders.pop(faction)
        holders[player] = sorted(set(holders.get(player, [])) | set(traits))

        blocked = self.state.setdefault("condemnation_blocked", {})
        compradors = []
        for trait in traits:
            rule = COMPRADOR_TRAITS.get(trait)
            if not rule:
                continue
            power = rule["power"]
            # 換東家就重新擲一次免疫，舊的紀錄作廢。
            for key in [key for key in blocked if key.endswith(f":{power}")]:
                blocked.pop(key, None)
            relations = self._player(player).setdefault("foreign_relations", {})
            before = int(relations.get(power, 0))
            after = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + int(rule["gain"])))
            relations[power] = after
            compradors.append({
                "trait": trait, "owner": player, "power": power,
                "before": before, "after": after, "amount": after - before,
            })
        if compradors:
            for other in self.state["players"]:
                self._sync_foreign_deck_cards(other)
            # 舊欄位名保留給單一買辦的呼叫端，同時提供完整清單。
            result["comprador"] = compradors[0]
            result["compradors"] = compradors
        if any(trait in PROVINCE_OUTPUT_TRAITS for trait in traits):
            self._refresh_city_income()
        result["faction_general_traits"] = self.faction_general_traits(player)
        return result

    # ── 事件卡：每三回合一則共享《民國報》 ────────────────────────────
    EVENT_RESPONSE_ORDER = ("F", "W", "S", "N")

    def _event_rules(self) -> Dict[str, Any]:
        return (self.data.get("event_cards") or {}).get("draw_rules") or {}

    def _event_template(self, card_id: str) -> Dict[str, Any]:
        for card in (self.data.get("event_cards") or {}).get("cards", []):
            if card["id"] == card_id:
                return deepcopy(card)
        raise ValueError(f"unknown event card: {card_id}")

    def _start_event_cycle(self) -> bool:
        """回合數到了就抽事件卡；每則事件隨機指定一個適格玩家承受。"""
        rules = self._event_rules()
        every = int(rules.get("every_turns", 3))
        count = int(rules.get("cards_per_cycle", 4))
        if not every or int(self.state["turn"]) % every != 0:
            return False
        pool = self.state.setdefault("event_pool", [])
        if not pool:
            return False
        order = list(rules.get("response_order") or self.EVENT_RESPONSE_ORDER)
        drawn = []
        already = set()
        for index in range(count):
            # 有進入條件的卡（要控制某省、某城）只有符合的人抽得到；沒人符合就先跳過，
            # 留在池子裡等局勢變了再說。
            # 被 event_locks 封鎖的卡同樣抽不到，但**不會**離開 pool——這是封鎖與移除的差別。
            # already 擋掉同一輪重複抽到同一張（池子裡可以有同名多張，用來加抽中機會）。
            eligible = [
                card_id for card_id in pool
                if card_id not in already
                and not self.event_is_spent(card_id)
                and not self._event_locked(card_id)
                and self._event_eligible_players(self._event_template(card_id))
            ]
            if not eligible:
                break
            card_id = eligible[self.random.randrange(len(eligible))]
            pool.remove(card_id)
            already.add(card_id)
            card = self._event_template(card_id)
            qualified = self._event_eligible_players(card)
            drawer = qualified[self.random.randrange(len(qualified))]
            responders = self._event_responder_queue(card, drawer)
            drawn.append({"card_id": card_id, "drawer": drawer,
                          "responders": responders, "responses": {}})
        self.state["pending_events"] = {"turn": int(self.state["turn"]), "cards": drawn, "index": 0}
        return True

    # ------------------------------------------------------------------
    # 事件卡封鎖（event_locks）
    #
    # 封鎖與移除是兩回事：
    #   封鎖 = 卡片留在 event_pool 裡，封鎖期間抽不到，到期自動又抽得到。
    #   移除 = 從 event_pool 拿掉，不會再回來。
    # 一條封鎖可以指名卡片（cards），也可以指定標籤＋列強（tags/powers），
    # 例如「日本相關的 [軍事] 事件封鎖三回合」就是 tags=["軍事"], powers=["日"]。
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 一次性卡（one-shot）
    #
    # 設計稿裡的事件卡預設都是一次性的：只要已經抽出並結算過，
    # **無論牌庫中還有多少張**都不會再被抽到——日後任何效果再加幾張也一樣。
    # 卡片資料加 `repeatable: true` 才豁免。
    # ------------------------------------------------------------------

    def event_is_repeatable(self, card_id: str) -> bool:
        return bool(self._event_template(card_id).get("repeatable"))

    def event_already_resolved(self, card_id: str) -> bool:
        return any(entry.get("card_id") == card_id
                   for entry in self.state.get("event_history", []))

    def event_is_spent(self, card_id: str) -> bool:
        """這張卡是不是已經用掉了（一次性且抽過）。"""
        return self.event_already_resolved(card_id) and not self.event_is_repeatable(card_id)

    def _event_tags(self, card_id: str) -> list:
        return list(self._event_template(card_id).get("tags") or [])

    def _event_powers(self, card_id: str) -> list:
        """卡片的列強歸屬。power_note 允許寫成「蘇／德」這種複數。"""
        note = str(self._event_template(card_id).get("power_note") or "")
        return [part for part in re.split(r"[／/、,]", note) if part]

    def _event_lock_matches(self, entry: Dict[str, Any], card_id: str) -> bool:
        if card_id in (entry.get("cards") or []):
            return True
        tags = entry.get("tags") or []
        if not tags:
            return False
        if not set(tags) & set(self._event_tags(card_id)):
            return False
        powers = entry.get("powers") or []
        # 沒指定列強 = 該標籤全部封鎖；指定了就只封鎖該國的。
        return not powers or bool(set(powers) & set(self._event_powers(card_id)))

    def _event_locked(self, card_id: str) -> bool:
        turn = int(self.state["turn"])
        for entry in self.state.get("event_locks", []):
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            if self._event_lock_matches(entry, card_id):
                return True
        return False

    def event_lock_entry(self, card_id: str) -> Optional[Dict[str, Any]]:
        """給前端／測試看的：這張卡現在被哪一條封鎖壓著。"""
        turn = int(self.state["turn"])
        for entry in self.state.get("event_locks", []):
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            if self._event_lock_matches(entry, card_id):
                return entry
        return None

    def _event_cards_matching(self, tags: list, powers: list) -> list:
        """資料檔裡符合標籤＋列強的所有事件卡 id（不管現在在不在池子裡）。"""
        out = []
        for card in (self.data.get("event_cards") or {}).get("cards", []):
            card_id = card["id"]
            if tags and not set(tags) & set(self._event_tags(card_id)):
                continue
            if powers and not set(powers) & set(self._event_powers(card_id)):
                continue
            out.append(card_id)
        return out

    # ------------------------------------------------------------------
    # 學潮（student_unrest）
    #
    # 走既有的 city_output_effects：挑該玩家幾座大城，限時把金錢與工廠產出乘上
    # 一個係數。預設減半；《新月》月刊（9.5）抽出後全場改為只減 1/4。
    # 另外學潮期間那幾座城不可補充兵力，由 reinforce_army 擋下。
    # ------------------------------------------------------------------

    STUDENT_UNREST_MULTIPLIER = 0.5
    STUDENT_UNREST_RELIEVED_MULTIPLIER = 0.75

    def student_unrest_multiplier(self) -> float:
        """學潮現在把產出乘上多少。0.5 是減半，0.75 是只減 1/4。"""
        if self.state.get("student_unrest_relief"):
            return self.STUDENT_UNREST_RELIEVED_MULTIPLIER
        return self.STUDENT_UNREST_MULTIPLIER

    def _student_unrest_candidates(self, player: str, min_level: int) -> list:
        """該玩家控制的、等級夠高的城市（9.3／10.7 指定四級或五級大城）。"""
        out = []
        for city in self.data["strategic_map"]["cities"]:
            if self.state["city_owners"].get(city["id"], city["faction"]) != player:
                continue
            if int(self._with_level(city).get("level", 0)) < int(min_level):
                continue
            out.append(city)
        return out

    def city_in_student_unrest(self, city_id: str) -> bool:
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") != "student_unrest":
                continue
            if int(effect.get("remaining_turns", 0)) <= 0:
                continue
            if city_id in (effect.get("city_ids") or []):
                return True
        return False

    def _event_eligible_players(self, card: Dict[str, Any]) -> list:
        """這張事件卡現在有哪些玩家可以抽到。沒有進入條件就是全部。"""
        condition = card.get("entry_condition") or {}
        players = list(self.state["players"])
        if not condition:
            return players
        province = condition.get("controls_province")
        cities = condition.get("controls_cities_any") or []
        relation_min = condition.get("relation_min") or {}
        eligible = []
        for code in players:
            if province and not self._controlled_provinces(code, [province]):
                continue
            if cities and not any(self.state["city_owners"].get(city) == code for city in cities):
                continue
            # 關係門檻（日本承認北京政府要對日 ≥6、蘇聯建交要對蘇 ≥6）。
            relations = self._player(code).get("foreign_relations", {})
            if any(int(relations.get(power, 0)) < int(floor)
                   for power, floor in relation_min.items()):
                continue
            eligible.append(code)
        return eligible

    def event_needs_every_faction(self, card: Dict[str, Any]) -> bool:
        """這張卡是不是「每一家都要各自表態、各自結算」。

        判準：resolution 是 choice 且 scope 為 all_players。
        先前這個值在 pending_event_view 裡被寫死成 False，導致
        〈亞克斯搜查案〉〈非戰公約〉〈全國經濟會議與裁兵之議〉
        全部退化成只有抽到的那一家表態。
        """
        resolution = card.get("resolution") or {}
        return (resolution.get("type") == "choice"
                and resolution.get("scope", "all_players") == "all_players")

    def _event_responder_queue(self, card: Dict[str, Any], drawer: str) -> list:
        """這張卡由誰回應，以及順序。

        全員表態的卡：抽到的那一家排第一，其餘照回應順序接上，
        且只收「現在還在場上、且符合進入條件」的玩家——
        不然佇列裡卡著一個永遠不會回應的人，整張卡就推不動了。
        """
        if not self.event_needs_every_faction(card):
            return [drawer]
        eligible = set(self._event_eligible_players(card)) & set(self.state["players"])
        order = list(self._event_rules().get("response_order") or self.EVENT_RESPONSE_ORDER)
        queue = [drawer] if drawer in eligible else []
        queue += [code for code in order if code in eligible and code not in queue]
        queue += [code for code in eligible if code not in queue]
        return queue or [drawer]

    def pending_event_view(self) -> Optional[Dict[str, Any]]:
        pending = self.state.get("pending_events")
        if not pending:
            return None
        index = int(pending.get("index", 0))
        cards = pending.get("cards") or []
        if index >= len(cards):
            return None
        entry = cards[index]
        answered = entry.get("responses") or {}
        card = self._event_template(entry["card_id"])
        strict = bool(self._event_rules().get("strict_response_order"))
        needs_everyone = self.event_needs_every_faction(card)
        # 防卡死：佇列裡若有已經不存在的玩家，直接跳過，否則 waiting_for 會永遠指著他。
        alive = set(self.state["players"])
        waiting = [code for code in entry["responders"]
                   if code not in answered and code in alive]
        if not strict and not needs_everyone:
            # 寬鬆模式下的單純事件：任何一家點閱就算數，不必等抽到的那一家。
            waiting = [] if answered else list(self.state["players"])
        return {
            "turn": pending["turn"],
            "index": index,
            "total": len(cards),
            "card": card,
            "drawer": entry["drawer"],
            "responders": entry["responders"],
            "responses": answered,
            "waiting_for": waiting[0] if waiting else None,
            "pending_responders": waiting,
            "strict_order": strict,
            "needs_every_faction": needs_everyone,
        }

    def respond_event(
        self, player: str, *, choice: Optional[str] = None, follow_up: Optional[str] = None,
    ) -> Dict[str, Any]:
        view = self.pending_event_view()
        if not view:
            raise ValueError("目前沒有待回應的事件卡")
        card = view["card"]
        resolution = card.get("resolution") or {}
        options = {item["id"]: item for item in (resolution.get("options") or [])}
        pending = self.state["pending_events"]
        entry = pending["cards"][int(pending["index"])]
        if view["strict_order"]:
            # 正式版：嚴格照 奉 → 直 → 五 → 國 的順序，輪不到就不能點。
            if view["waiting_for"] != player:
                raise ValueError(f"現在輪到 {view['waiting_for']} 回應這張事件卡")
        else:
            # 測試版：誰都可以點，但同一家不能重複回應同一張卡。
            if player in entry["responses"]:
                raise ValueError("你已經回應過這張事件卡了")
        if resolution.get("type") == "choice" and choice not in options:
            raise ValueError("本卡需要選擇一個行動")
        option = options.get(choice) if choice else None
        extra_payload: Dict[str, Any] = {}
        if option and option.get("follow_up"):
            spec = option["follow_up"]
            allowed = {item["id"]: item for item in (spec.get("options") or [])}
            if follow_up not in allowed:
                raise ValueError(spec.get("prompt") or "本選項還需要再指定一個對象")
            extra_payload = deepcopy(allowed[follow_up].get("apply") or {})
            entry.setdefault("follow_ups", {})[player] = follow_up
        entry["responses"][player] = choice or "acknowledged"
        applied = []
        if option:
            applied = self._apply_event_payload(option.get("apply") or {}, players=[player], card=card)
            if extra_payload:
                applied += self._apply_event_payload(extra_payload, players=[player], card=card)
        # 誰還沒表態。三種情況都要濾掉已經不在場上的玩家，
        # 否則佇列裡卡著一個永遠不會回應的人，這張卡就結不掉、回合也推不動。
        alive = set(self.state["players"])
        def _left(queue):
            return [code for code in (queue or []) if code not in entry["responses"] and code in alive]

        if view["needs_every_faction"]:
            # 各自表態的卡：名單上每一家都點過才算結束，每家的選擇只作用在自己身上。
            remaining = _left(entry["responders"] or list(self.state["players"]))
        elif resolution.get("scope") == "drawer" or view["strict_order"]:
            remaining = _left(entry["responders"])
        else:
            remaining = []
        card_done = not remaining
        if card_done:
            # 卡片本身的共同效果等所有人回應完才結算；scope 是 drawer 的只發給抽到的那一家。
            scope_players = [entry["drawer"]] if (resolution.get("scope") == "drawer") else None
            applied += self._apply_event_payload(card.get("apply") or {}, players=scope_players, card=card)
            self.state.setdefault("event_history", []).append({
                "turn": int(pending["turn"]), "card_id": card["id"], "name": card["name"],
                "drawer": entry["drawer"], "responses": dict(entry["responses"]),
            })
            pending["index"] = int(pending["index"]) + 1
        finished = int(pending["index"]) >= len(pending["cards"])
        turn_result = None
        if finished:
            self.state["pending_events"] = None
            # 本次共享事件結完，才輪到本回合的金錢、工廠與債務結算。
            turn_result = self._finish_turn()
        return {
            "applied": applied,
            "card_finished": card_done,
            "cycle_finished": finished,
            "pending_events": self.pending_event_view(),
            "turn": (turn_result or {}).get("turn"),
            "state": self.snapshot(),
        }

    def _apply_event_payload(
        self, payload: Dict[str, Any], *, players: Optional[list], card: Dict[str, Any],
    ) -> list:
        """把事件卡上接得住的效果實際寫進狀態，回傳做了哪些事。"""
        if not payload:
            return []
        applied = []
        targets = list(players) if players is not None else list(self.state["players"])
        # 只發給對某國關係達標的玩家（柏林密約只惠及親蘇者）。
        gate = payload.get("relation_gate")
        if gate:
            power, floor = str(gate["power"]), int(gate.get("min", FOREIGN_FRIENDLY_THRESHOLD))
            targets = [code for code in targets
                       if int(self._player(code).get("foreign_relations", {}).get(power, 0)) >= floor]
        # 反向門檻：只發給對某國關係「低於」門檻的玩家（9.3、10.7、10.8 的對蘇 ≤5）。
        gate_max = payload.get("relation_gate_max")
        if gate_max:
            power, ceiling = str(gate_max["power"]), int(gate_max.get("max", 5))
            targets = [code for code in targets
                       if int(self._player(code).get("foreign_relations", {}).get(power, 0)) <= ceiling]
        # 任一達標即可（10.5 庚款興學：對美 ≥3 或對英 ≥3）。
        gate_any = payload.get("relation_gate_any")
        if gate_any:
            def _qualifies(code):
                relations = self._player(code).get("foreign_relations", {})
                return any(int(relations.get(str(rule["power"]), 0)) >= int(rule.get("min", 0))
                           for rule in gate_any)
            targets = [code for code in targets if _qualifies(code)]
        label = card.get("name", card.get("id"))
        turn = int(self.state["turn"])

        for code in targets:
            relations = self._player(code).setdefault("foreign_relations", {})
            deltas = dict(payload.get("relations") or {})
            for rule in payload.get("conditional_relations") or []:
                value = int(relations.get(str(rule["power"]), 0))
                if "min" in rule and value < int(rule["min"]):
                    continue
                if "max" in rule and value > int(rule["max"]):
                    continue
                for key, amount in (rule.get("delta") or {}).items():
                    deltas[key] = deltas.get(key, 0) + int(amount)
            for power, amount in deltas.items():
                if power not in relations:
                    continue
                before = int(relations[power])
                amount = int(amount)
                # 庚款興學：受人之惠，動輒得咎——下一次因你的行動而下降時多降 N 點。
                # 只咬「下降」，加分不受影響；用掉一次就消耗。
                if amount < 0:
                    extra = self._consume_relation_drop_amplifier(code, power)
                    if extra:
                        amount -= extra
                        applied.append({"kind": "relation_drop_amplified", "player": code,
                                        "power": power, "extra": extra})
                relations[power] = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX, before + amount))
                if relations[power] != before:
                    applied.append({"kind": "relation", "player": code, "power": power,
                                    "before": before, "after": relations[power]})
            for unlock in payload.get("unlock") or []:
                unlocks = self._player(code).setdefault("unlocks", [])
                if unlock not in unlocks:
                    unlocks.append(unlock)
                    applied.append({"kind": "unlock", "player": code, "unlock": unlock})
            for card_id, copies in (payload.get("card_copies") or {}).items():
                state_payload = self._player(code)
                state_payload["function_deck"].extend([card_id] * int(copies))
                self.random.shuffle(state_payload["function_deck"])
                applied.append({"kind": "card_copies", "player": code,
                                "card_id": card_id, "copies": int(copies)})
            cash = int(payload.get("cash", 0))
            if cash:
                self._player(code)["treasury"] = int(self._player(code).get("treasury", 0)) + cash
                applied.append({"kind": "cash", "player": code, "amount": cash})
            delayed = payload.get("delayed_output")
            if delayed:
                self._player(code).setdefault("delayed_output_bonuses", []).append({
                    "card_id": card.get("id"),
                    "name": label,
                    "start_turn": turn + int(delayed.get("delay_turns", 0)),
                    "cash": int(delayed.get("cash", 0)),
                    "factory": int(delayed.get("factory", 0)),
                })
                applied.append({"kind": "delayed_output", "player": code, **delayed})
            for bank, bonus in (payload.get("bank_limit_bonus") or {}).items():
                bonuses = self._player(code).setdefault("bank_limit_bonus", {})
                bonuses[bank] = int(bonuses.get(bank, 0)) + int(bonus)
                applied.append({"kind": "bank_limit_bonus", "player": code,
                                "bank": bank, "amount": int(bonus)})

        # 封鎖事件卡：卡片留在 event_pool 裡，封鎖期間抽不到，到期自動解封。
        # 可以指名卡片，也可以用「標籤＋列強」整批封鎖（日本 [軍事] 事件封鎖三回合）。
        for lock in (payload.get("event_lock") or []):
            span = lock.get("turns", 1)
            entry = {
                "cards": list(lock.get("cards") or []),
                "tags": list(lock.get("tags") or []),
                "powers": list(lock.get("powers") or []),
                "until_turn": (turn + int(span)) if span is not None else None,
                "label": lock.get("label", label),
                "source_card": card.get("id"),
            }
            self.state.setdefault("event_locks", []).append(entry)
            # 現在池子裡實際被這條壓住的張數，寫進回報方便前端說明與測試斷言。
            hit = sorted({card_id for card_id in self.state.get("event_pool", [])
                          if self._event_lock_matches(entry, card_id)})
            applied.append({"kind": "event_lock", "matched_in_pool": hit, **entry})

        # 解除封鎖：把指定卡片／標籤的封鎖條提前撤掉（10.7 北京大學共運解掉 10.6 的封鎖）。
        for release in (payload.get("event_unlock") or []):
            kept, removed = [], 0
            for entry in self.state.get("event_locks", []):
                if release.get("labels") and entry.get("label") in release["labels"]:
                    removed += 1
                    continue
                if release.get("cards") and set(release["cards"]) & set(entry.get("cards") or []):
                    removed += 1
                    continue
                kept.append(entry)
            self.state["event_locks"] = kept
            if removed:
                applied.append({"kind": "event_unlock", "released": removed, **release})

        # 增加 N 張卡進池：取代舊的「抽中機率 +X%」寫法。
        # event_pool 允許同一個 id 出現多次，多一張就是多一份被抽中的機會。
        #
        # 語意是「**每一張**符合的卡各加 N 張」，不是從符合的卡裡挑一張加。
        # 所以 tags=["軍事"], powers=["日"], copies=1 的意思是：
        # 資料檔裡每一張日本 [軍事] 事件卡都各多一張進池。
        pool_add = payload.get("event_pool_add")
        if pool_add:
            pool = self.state.setdefault("event_pool", [])
            for spec in pool_add:
                copies = int(spec.get("copies", 1))
                ids = list(spec.get("cards") or [])
                named = spec.get("card_names")
                if not ids and named:
                    # 用卡名比對——目標卡可能還沒建檔（八九式中戰車指名的六張列強懲戒卡）。
                    # 指名了就只認指名的：找不到就是找不到，**不可以**掉回標籤比對，
                    # 否則空的 tags/powers 會匹配到全部卡片。
                    wanted = set(named)
                    ids = [c["id"] for c in (self.data.get("event_cards") or {}).get("cards", [])
                           if c.get("name") in wanted]
                elif not ids and (spec.get("tags") or spec.get("powers")):
                    ids = self._event_cards_matching(spec.get("tags") or [], spec.get("powers") or [])
                if not ids:
                    # 目前資料檔裡沒有符合的卡（例如 [軍事] 類事件卡尚未建檔）。
                    # 誠實記下來，不要假裝加成功了。
                    applied.append({"kind": "event_pool_add", "copies": copies,
                                    "added": [], "note": "no matching event cards in data",
                                    **{k: spec.get(k) for k in ("tags", "powers") if spec.get(k)}})
                    continue
                added, spent = [], []
                for card_id in ids:
                    # 一次性卡抽過就封鎖，再加幾張也抽不到——所以乾脆不加，
                    # 免得牌庫裡堆一疊永遠抽不到的死牌。
                    if self.event_is_spent(card_id):
                        spent.append(card_id)
                        continue
                    pool.extend([card_id] * copies)
                    added.extend([card_id] * copies)
                entry = {"kind": "event_pool_add", "copies": copies,
                         "matched": sorted(set(ids)), "added": added}
                if spent:
                    entry["skipped_already_drawn"] = sorted(set(spent))
                applied.append(entry)

        # ---- 預備隊增減（11.3 裁兵）----------------------------------
        # require_all=True 時整組要嘛全扣、要嘛一個都不扣（兵源不足就整批放棄），
        # 回報 shortfall 讓上層決定要不要改走另一支。
        specs = payload.get("reserve_delta") or []
        if specs:
            require_all = bool(payload.get("reserve_delta_require_all"))
            for code in targets:
                reserves = self._player(code)["unit_reserves"]
                short = [str(spec["unit_type"]) for spec in specs
                         if int(spec.get("amount", 0)) < 0
                         and int(reserves.get(str(spec["unit_type"]), 0)) < abs(int(spec["amount"]))]
                if require_all and short:
                    applied.append({"kind": "reserve_delta_skipped", "player": code,
                                    "shortfall": short})
                    # 兵源不足就自動改走替代方案（11.3：湊不出兵就等於宣告不裁）。
                    fallback = payload.get("on_reserve_shortfall")
                    if fallback:
                        applied += self._apply_event_payload(fallback, players=[code], card=card)
                    continue
                for spec in specs:
                    unit = str(spec["unit_type"]); amount = int(spec.get("amount", 0))
                    before = int(reserves.get(unit, 0))
                    self._add_reserve(code, unit, amount)
                    after = int(self._player(code)["unit_reserves"].get(unit, 0))
                    applied.append({"kind": "reserve_delta", "player": code, "unit_type": unit,
                                    "amount": after - before})

        # ---- 永久改寫功能卡的利率（11.3 不裁兵：軍閥公債利率永久 12%）----
        rate = payload.get("loan_rate_override")
        if rate:
            for code in targets:
                entry = {"card_id": str(rate["card_id"]),
                         "interest_per_turn": float(rate["interest_per_turn"]), "label": label}
                self._player(code).setdefault("loan_rate_overrides", []).append(entry)
                applied.append({"kind": "loan_rate_override", "player": code, **entry})

        # ---- 抽卡時擲一次骰，依結果套用其中一支（11.5 廢兩改元之議）----
        roll_spec = payload.get("random_outcome")
        if roll_spec:
            roll = self.random.random()
            chosen = None
            cumulative = 0.0
            for branch in roll_spec.get("branches") or []:
                cumulative += float(branch.get("chance", 0))
                if roll < cumulative:
                    chosen = branch
                    break
            if chosen is None and roll_spec.get("branches"):
                chosen = roll_spec["branches"][-1]
            if chosen:
                applied.append({"kind": "random_outcome", "roll": round(roll, 4),
                                "chosen": chosen.get("id"),
                                "newspaper_index": chosen.get("newspaper_index", 0)})
                applied += self._apply_event_payload(chosen.get("apply") or {},
                                                     players=targets, card=card)

        # ---- 其他玩家的關係（承認類事件：受惠者 +2，其餘 −1）----------
        others = payload.get("others_relations")
        if others:
            rest = [code for code in self.state["players"] if code not in targets]
            for code in rest:
                relations = self._player(code).setdefault("foreign_relations", {})
                for power, amount in others.items():
                    before = int(relations.get(power, 0))
                    amount = int(amount)
                    if amount < 0:
                        extra = self._consume_relation_drop_amplifier(code, power)
                        if extra:
                            amount -= extra
                    relations[power] = max(FOREIGN_RELATION_MIN,
                                           min(FOREIGN_RELATION_MAX, before + amount))
                    if relations[power] != before:
                        applied.append({"kind": "relation", "player": code, "power": power,
                                        "before": before, "after": relations[power],
                                        "scope": "others"})
                self._sync_foreign_deck_cards(code)

        # ---- 城市等級永久升級（晏陽初辦學鄉村）------------------------
        # 只升不降：指定省份裡等級低於門檻的城市一律拉到門檻。
        # 這是城市本身的屬性，跟誰持有無關，日後易主也帶著走。
        upgrade = payload.get("city_level_upgrade")
        if upgrade:
            provinces = set(upgrade.get("provinces") or [])
            to_level = int(upgrade["to_level"])
            from_level = upgrade.get("from_level")
            overrides = self.state.setdefault("city_level_overrides", {})
            touched = []
            for city in self.data["strategic_map"]["cities"]:
                if provinces and city.get("province") not in provinces:
                    continue
                current = int(self._with_level(city).get("level", 1))
                if from_level is not None and current != int(from_level):
                    continue
                if current >= to_level:
                    continue
                overrides[city["id"]] = to_level
                touched.append({"id": city["id"], "name": city["name"],
                                "province": city["province"],
                                "from": current, "to": to_level})
            if touched:
                self._refresh_city_income()
                applied.append({"kind": "city_level_upgrade", "cities": touched})

        # ---- 控制指定省份才生效的徵兵折價（晏陽初辦學鄉村）--------------
        # 與 permanent_recruit_adjustment 不同：這個是條件式的，
        # 四省全丟光就失效，奪回任一省又回來，所以存條件而不是存結果。
        for spec in (payload.get("province_recruit_discount") or []):
            entry = {"provinces": list(spec.get("provinces") or []),
                     "units": dict(spec.get("units") or {}),
                     "label": label, "source_card": card.get("id")}
            existing = self.state.setdefault("province_recruit_discounts", [])
            if not any(e.get("source_card") == entry["source_card"] for e in existing):
                existing.append(entry)
                applied.append({"kind": "province_recruit_discount", **entry})

        # ---- 交戰扣產出（11.1 江浙財團的墊款）--------------------------
        # 這是全場性的：不管是誰在江浙開打，兩省境內每座城市都吃這個減損。
        war_rule = payload.get("province_combat_penalty")
        if war_rule:
            entry = {"provinces": list(war_rule.get("provinces") or []),
                     "cash": int(war_rule.get("cash", 0)),
                     "factory": int(war_rule.get("factory", 0)),
                     "label": label, "source_card": card.get("id")}
            existing = self.state.setdefault("province_combat_penalties", [])
            if not any(e.get("source_card") == entry["source_card"] for e in existing):
                existing.append(entry)
                self._refresh_city_income()
                applied.append({"kind": "province_combat_penalty", **entry})

        # ---- 公債承銷特權（11.1 的另一半）------------------------------
        # 紅利跟著江浙兩省跑，所以存的是條件而不是結果：每次要用的時候現算。
        bond = payload.get("bond_underwriting")
        if bond:
            entry = {"provinces": list(bond.get("provinces") or []),
                     "relation_max": dict(bond.get("relation_max") or {}),
                     "full_subscription": bool(bond.get("full_subscription")),
                     "no_credit_damage": bool(bond.get("no_credit_damage")),
                     "label": label, "source_card": card.get("id")}
            existing = self.state.setdefault("bond_underwriting", [])
            if not any(e.get("source_card") == entry["source_card"] for e in existing):
                existing.append(entry)
                applied.append({"kind": "bond_underwriting", **entry})

        # ---- 租界城市改發固定值（11.2 南洋兄弟與英美煙草）--------------
        cover = payload.get("concession_override")
        if cover:
            entry = {"cash": int(cover.get("cash", 0)), "factory": int(cover.get("factory", 0)),
                     "until_turn": turn + int(cover.get("turns", 3)),
                     "label": label, "source_card": card.get("id")}
            self.state.setdefault("concession_overrides", []).append(entry)
            self._refresh_city_income()
            applied.append({"kind": "concession_override", **entry})

        # ---- 逐國發放（10.5 庚款興學：一國一筆，兩國都達標就雙倍）----
        grant = payload.get("per_power_grant")
        if grant:
            each = grant.get("each") or {}
            for code in targets:
                relations = self._player(code).get("foreign_relations", {})
                for rule in grant.get("powers") or []:
                    power = str(rule["power"])
                    if int(relations.get(power, 0)) < int(rule.get("min", 0)):
                        continue
                    payload_each = deepcopy(each)
                    amp = payload_each.pop("relation_drop_amplifier", None)
                    if amp:
                        payload_each["relation_drop_amplifier"] = [dict(amp, power=power)]
                    applied.append({"kind": "per_power_grant", "player": code,
                                    "power": power, "label": rule.get("label")})
                    applied += self._apply_event_payload(payload_each, players=[code], card=card)

        # ---- 條件分支：依另一張卡的狀態走不同效果（9.5、10.1、10.3）----
        #
        # 三張卡都是「若目標卡已抽出／生效中，走 A；否則走 B」。
        # 判定依據：event_history 有沒有抽過，以及該卡的效果現在是否還掛在場上。
        branch = payload.get("conditional_branch")
        if branch:
            probe = str(branch["card_id"])
            drawn = any(entry.get("card_id") == probe
                        for entry in self.state.get("event_history", []))
            active = self._event_effect_active(probe)
            # 三種狀態各走各的，**不做任何 fallback**：
            #   未抽出            -> otherwise
            #   已抽出、效果已散    -> if_drawn
            #   已抽出、效果仍生效  -> if_active
            # 先前這裡寫 `branch.get(key) or branch.get("otherwise")`，
            # 只要某張卡沒定義該狀態的分支，就會悄悄改跑「未抽出」那一支——
            # 語意剛好顛倒，而且不會有任何跡象。現在沒定義就是沒效果，並如實回報。
            key = "if_active" if (drawn and active) else ("if_drawn" if drawn else "otherwise")
            chosen = branch.get(key)
            applied.append({"kind": "conditional_branch", "probe": probe,
                            "drawn": drawn, "active": active, "chosen": key,
                            "has_branch": chosen is not None})
            if chosen:
                applied += self._apply_event_payload(chosen, players=players, card=card)

        # ---- 延長某張事件卡已經掛著的效果（9.5 延長自由中國教育家）----
        extend = payload.get("extend_effect")
        if extend:
            span = int(extend.get("turns", 5))
            probe = str(extend["card_id"])
            touched = 0
            for entry in self.state.get("perk_suspensions", []):
                if entry.get("source_card") != probe:
                    continue
                if entry.get("until_turn") is not None:
                    entry["until_turn"] = int(entry["until_turn"]) + span
                    touched += 1
            for entry in self.state.get("event_locks", []):
                if entry.get("source_card") != probe:
                    continue
                if entry.get("until_turn") is not None:
                    entry["until_turn"] = int(entry["until_turn"]) + span
                    touched += 1
            applied.append({"kind": "extend_effect", "card_id": probe,
                            "turns": span, "entries": touched})

        # ---- 擴大省份綁定免疫的適用範圍（10.1 把復興儒學擴到山東＋直隸）----
        widen = payload.get("widen_province_immunity")
        if widen:
            extra = list(widen.get("add_provinces") or [])
            probe = str(widen.get("source_card", ""))
            touched = 0
            for code in list(self.state["players"]):
                for entry in self._player(code).get("province_card_immunities") or []:
                    if probe and entry.get("source_card") != probe:
                        continue
                    provinces = entry.setdefault("provinces", [entry["province"]])
                    for name in extra:
                        if name not in provinces:
                            provinces.append(name)
                            touched += 1
            applied.append({"kind": "widen_province_immunity",
                            "add_provinces": extra, "entries": touched})

        # ---- 讓省份綁定免疫暫時失效（10.3 古史辨打掉復興儒學的護持）----
        pierce = payload.get("suspend_province_immunity")
        if pierce:
            probe = str(pierce.get("source_card", ""))
            until = turn + int(pierce.get("turns", 10))
            touched = 0
            for code in list(self.state["players"]):
                for entry in self._player(code).get("province_card_immunities") or []:
                    if probe and entry.get("source_card") != probe:
                        continue
                    entry["suspended_until_turn"] = until
                    touched += 1
            applied.append({"kind": "suspend_province_immunity",
                            "until_turn": until, "entries": touched})

        # ---- 學潮（9.3、10.7）----------------------------------------
        unrest = payload.get("student_unrest")
        if unrest:
            multiplier = self.student_unrest_multiplier()
            span = int(unrest.get("turns", 3))
            want = int(unrest.get("cities", 2))
            min_level = int(unrest.get("min_level", 4))
            for code in targets:
                pool_cities = self._student_unrest_candidates(code, min_level)
                if not pool_cities:
                    applied.append({"kind": "student_unrest", "player": code, "cities": [],
                                    "note": "no city of the required level under this player"})
                    continue
                picked = self.random.sample(pool_cities, k=min(want, len(pool_cities)))
                entry = {
                    "id": f"student_unrest:{card.get('id')}:{code}",
                    "kind": "student_unrest",
                    "card_id": card.get("id"),
                    "name": label,
                    "target_owner": code,
                    "created_turn": turn,
                    "remaining_turns": span,
                    "city_ids": [c["id"] for c in picked],
                    "cities": [{"id": c["id"], "name": c["name"]} for c in picked],
                    "cash_multiplier": multiplier,
                    "factory_multiplier": multiplier,
                    "blocks_reinforcement": True,
                }
                self.state.setdefault("city_output_effects", []).append(deepcopy(entry))
                applied.append({"kind": "student_unrest", "player": code,
                                "cities": entry["cities"], "turns": span,
                                "multiplier": multiplier})
            self._refresh_city_income()

        # ---- 《新月》月刊：此後學潮只減 1/4（9.5）---------------------
        if payload.get("student_unrest_relief"):
            if not self.state.get("student_unrest_relief"):
                self.state["student_unrest_relief"] = True
                applied.append({"kind": "student_unrest_relief",
                                "multiplier": self.STUDENT_UNREST_RELIEVED_MULTIPLIER})

        # ---- 關係下降放大器（10.5 庚款興學）---------------------------
        # 「下一次與該國關係因你的行動下降時，多降 1 點」——用完就消耗掉。
        for amp in (payload.get("relation_drop_amplifier") or []):
            for code in targets:
                entry = {"power": str(amp["power"]), "extra": int(amp.get("extra", 1)),
                         "uses": amp.get("uses", 1), "label": label}
                self._player(code).setdefault("relation_drop_amplifiers", []).append(entry)
                applied.append({"kind": "relation_drop_amplifier", "player": code, **entry})

        # ---- 租界國關係（11.2 南洋兄弟與英美煙草）----------------------
        # 一座城可能有多國租界；同一國在同一位玩家身上只扣一次。
        conc = payload.get("concession_relations")
        if conc:
            delta = int(conc.get("delta", -1))
            for code in targets:
                powers = set()
                for city in self.data["strategic_map"]["cities"]:
                    if self.state["city_owners"].get(city["id"], city["faction"]) != code:
                        continue
                    powers.update(city.get("concession") or [])
                if not powers:
                    continue
                relations = self._player(code).setdefault("foreign_relations", {})
                for power in sorted(powers):
                    relations[power] = max(FOREIGN_RELATION_MIN, min(FOREIGN_RELATION_MAX,
                                                 int(relations.get(power, 0)) + delta))
                applied.append({"kind": "concession_relations", "player": code,
                                "powers": sorted(powers), "delta": delta})

        # ---- 永久徵兵成本調整（11.4 中華國貨展覽會）-------------------
        perm = payload.get("permanent_recruit_adjustment")
        if perm:
            for code in targets:
                adjust = self._player(code).setdefault("recruit_cost_adjustment", {})
                for unit, delta in (perm.get("units") or {}).items():
                    slot = adjust.setdefault(unit, {})
                    for field, amount in delta.items():
                        slot[field] = int(slot.get(field, 0)) + int(amount)
                applied.append({"kind": "permanent_recruit_adjustment", "player": code,
                                "units": perm.get("units")})

        # ---- 給前端執行的效果（忠誠等住在將領樹上的東西）--------------
        for effect in (payload.get("frontend_effects") or []):
            for code in targets:
                entry = {"kind": effect["kind"], "label": label,
                         **{k: v for k, v in effect.items() if k != "kind"}}
                # 廣播電台放大忠誠幅度：卡片改制成事件卡之後，這條加成照樣要吃得到。
                # 只放大幅度、不改正負號，與功能卡路徑同一套規則。
                radio = self._player(code).get("radio_station") or {}
                source = str(effect.get("card_id") or card.get("id") or "")
                if entry.get("amount") and source in (radio.get("affects_cards") or []):
                    magnitude = int(radio.get("loyalty_magnitude", 1))
                    entry["amount"] = magnitude * (1 if int(entry["amount"]) > 0 else -1)
                    entry["amplified_by"] = "radio_station"
                self._player(code).setdefault("pending_frontend_effects", []).append(entry)
                applied.append({"kind": "frontend_effect", "player": code,
                                "effect": effect["kind"], "amount": entry.get("amount")})

        # ---- 省份綁定的功能卡免疫（10.8 復興儒學）---------------------
        for imm in (payload.get("province_card_immunity") or []):
            for code in targets:
                entry = {"province": str(imm["province"]),
                         "provinces": [str(imm["province"])],
                         "cards": list(imm.get("cards") or []),
                         "label": label, "source_card": card.get("id")}
                self._player(code).setdefault("province_card_immunities", []).append(entry)
                applied.append({"kind": "province_card_immunity", "player": code, **entry})

        suspension = payload.get("perk_suspension")
        if suspension:
            # turns 為 null 代表無期限（中央研究院把〈盜賣文物〉永久收走）。
            span = suspension.get("turns", 1)
            entry = {"cards": list(suspension.get("cards") or []),
                     "until_turn": (turn + int(span)) if span is not None else None,
                     "players": targets if (suspension.get("self_only") or players is not None) else None,
                     "label": suspension.get("label", label),
                     "source_card": card.get("id")}
            self.state.setdefault("perk_suspensions", []).append(entry)
            # 被按住的卡立刻從還沒抽到的地方收走（手上那幾張留著，但打不出來）；
            # 若卡片註明 clear_active，連已經生效中的效果也一起撤掉。
            for code in (entry["players"] or list(self.state["players"])):
                state_payload = self._player(code)
                if suspension.get("clear_active"):
                    kept = [effect for effect in state_payload.get("timed_effects", [])
                            if effect.get("id") not in entry["cards"]]
                    if len(kept) != len(state_payload.get("timed_effects", [])):
                        applied.append({"kind": "cleared_active_effects", "player": code,
                                        "count": len(state_payload["timed_effects"]) - len(kept)})
                        state_payload["timed_effects"] = kept
                for card_id in entry["cards"]:
                    current = self._card_count_in_player_zones(state_payload, card_id)
                    if current:
                        self._remove_undrawn_cards(state_payload, card_id, current)
            applied.append(dict(kind="perk_suspension", **entry))
        ban = payload.get("bank_ban")
        if ban:
            entry = {"bank": ban["bank"], "until_turn": turn + int(ban.get("turns", 1)),
                     "players": targets if (ban.get("self_only") or players is not None) else None,
                     "label": ban.get("label", label)}
            self.state.setdefault("bank_bans", []).append(entry)
            applied.append(dict(kind="bank_ban", **entry))
        multiplier = payload.get("bank_limit_multiplier")
        if multiplier:
            banks = list(multiplier.get("banks") or ([multiplier["bank"]] if multiplier.get("bank") else []))
            entry = {"banks": banks, "factor": float(multiplier.get("factor", 1.0)),
                     "until_turn": turn + int(multiplier.get("turns", 1)), "label": label}
            self.state.setdefault("bank_limit_multipliers", []).append(entry)
            applied.append(dict(kind="bank_limit_multiplier", **entry))
        for override in payload.get("card_overrides") or []:
            # `fields` 是絕對值改寫（後蓋前），`field_deltas` 是增量（會累加）。
            # 增量的用意：兩張卡都影響同一個數字時，兩份加成應該疊起來，
            # 而不是後抽到的那張把前一張的效果整個蓋掉、變成寫死的上限。
            entry = {"card_id": override["card_id"], "fields": dict(override.get("fields") or {}),
                     "field_deltas": {k: int(v) for k, v in (override.get("field_deltas") or {}).items()},
                     "until_turn": (turn + int(override["duration_turns"])) if override.get("duration_turns") else None,
                     "label": label}
            self.state.setdefault("function_card_overrides", []).append(entry)
            applied.append(dict(kind="card_override", **entry))

        # 凍結某張功能卡的某幾個欄位：此後**再有卡想改寫這些欄位一律無效**。
        # 10.2 西北科學考查團用這個把〈盜賣文物〉的收益釘死——學術主權立起來之後，
        # 別的卡就不該再把文物價格炒回去。刻意放在 card_overrides 之後處理，
        # 好讓下這道禁令的卡自己那份改寫先落地、再開始擋後來的。
        for freeze in payload.get("override_freeze") or []:
            entry = {"card_id": freeze["card_id"], "fields": list(freeze.get("fields") or []),
                     "from_index": len(self.state.get("function_card_overrides", [])),
                     "label": freeze.get("label", label), "source_card": card.get("id")}
            self.state.setdefault("function_card_freezes", []).append(entry)
            applied.append(dict(kind="override_freeze", **entry))

        city_output = payload.get("city_output")
        if city_output:
            for city_id in city_output.get("cities") or []:
                bonus = self.state.setdefault("city_development", {}).setdefault(city_id, {"cash": 0, "factory": 0})
                bonus["cash"] += int(city_output.get("cash", 0))
                bonus["factory"] += int(city_output.get("factory", 0))
                applied.append({"kind": "city_output", "city_id": city_id,
                                "cash": int(city_output.get("cash", 0)),
                                "factory": int(city_output.get("factory", 0))})
            self._refresh_city_income()
        # 把某張功能卡從指定玩家的手牌／牌庫／棄牌堆整個清掉（中央研究院清〈中國人之恥〉）。
        for card_id in payload.get("clear_cards") or []:
            for code in targets:
                state_payload = self._player(code)
                removed = 0
                for zone in ("function_deck", "hand", "discard"):
                    before = len(state_payload.get(zone) or [])
                    state_payload[zone] = [item for item in state_payload.get(zone, []) if item != card_id]
                    removed += before - len(state_payload[zone])
                if state_payload.get("pending_draw") == card_id:
                    state_payload["pending_draw"] = None
                    removed += 1
                if removed:
                    applied.append({"kind": "clear_cards", "player": code,
                                    "card_id": card_id, "removed": removed})
        # 中央研究院的收編與除名。
        if payload.get("academia_grant"):
            # v4 7.2：研究院成立是全場一次性的事件。成立之後：
            #   1. 加成跟著江蘇跑，任何控制江蘇且未失格的玩家都吃得到；
            #   2. 〈盜賣文物〉從所有人的功能卡池「完全移除」（不是暫時封鎖，不會回來）；
            #   3. 已洗入牌庫的〈中國人之恥〉一次清空。
            founded = self.state.setdefault("academia_sinica", {})
            if not founded.get("founded"):
                founded["founded"] = True
                founded["founded_turn"] = turn
                applied.append({"kind": "academia_founded", "turn": turn})
                # 〈盜賣文物〉不 purge——它改為「逐玩家封鎖」，見 academia_active()。
                # 這裡只把〈中國人之恥〉一次清空（v4 7.2）。
                for code in list(self.state["players"]):
                    state_payload = self._player(code)
                    for card_id in ("national_shame",):
                        removed = 0
                        for zone in ("function_deck", "hand", "discard"):
                            before = len(state_payload.get(zone) or [])
                            state_payload[zone] = [item for item in state_payload.get(zone, [])
                                                   if item != card_id]
                            removed += before - len(state_payload[zone])
                        if state_payload.get("pending_draw") == card_id:
                            state_payload["pending_draw"] = None
                            removed += 1
                        if removed:
                            applied.append({"kind": "academia_purge", "player": code,
                                            "card_id": card_id, "removed": removed})
            for code in targets:
                status = self.academia_status(code)
                if not status.get("disqualified"):
                    status["holder"] = True   # 保留：記錄是誰抽到的，不再是吃加成的門檻
                    applied.append({"kind": "academia_grant", "player": code})
            self._refresh_city_income()
        if payload.get("academia_disqualify"):
            for code in targets:
                lost = self.disqualify_academia(code, str(payload["academia_disqualify"]))
                if lost:
                    applied.append(lost)
                else:
                    # 還沒收編就先失格，之後抽到中央研究院也不會生效。
                    self.academia_status(code)["disqualified"] = True
                    applied.append({"kind": "academia_barred", "player": code})
        # 生效中的暴動全部平息（一黨之國）。
        if payload.get("clear_riots"):
            kinds = list(payload["clear_riots"]) if isinstance(payload["clear_riots"], list) \
                else ["qing_gang_riot", "communist_riot", "red_army_uprising"]
            before = list(self.state.get("city_output_effects", []))
            self.state["city_output_effects"] = [
                effect for effect in before if effect.get("kind") not in kinds
            ]
            cleared = len(before) - len(self.state["city_output_effects"])
            if cleared:
                self._refresh_city_income()
                applied.append({"kind": "clear_riots", "count": cleared, "kinds": kinds})
        # 幾回合後才發生的事（昭和改元的態度轉硬、非戰公約的停戰紅利）。
        for scheduled in payload.get("scheduled") or []:
            entry = {
                "fire_turn": turn + int(scheduled.get("after_turns", 1)),
                "card_id": card.get("id"),
                "name": scheduled.get("label", label),
                "players": list(targets) if scheduled.get("keep_targets") else None,
                "payload": deepcopy(scheduled.get("apply") or {}),
            }
            self.state.setdefault("scheduled_event_effects", []).append(entry)
            applied.append({"kind": "scheduled", "fire_turn": entry["fire_turn"], "name": entry["name"]})
        # 逐玩家的功能卡改寫（跨洋長途電話的交涉成功率）。
        for override in payload.get("player_card_overrides") or []:
            for code in targets:
                entry = {
                    "player": code,
                    "card_id": override["card_id"],
                    "fields": dict(override.get("fields") or {}),
                    "until_turn": (turn + int(override["duration_turns"])) if override.get("duration_turns") else None,
                    "requires_cities_any": list(override.get("requires_cities_any") or []),
                    "label": label,
                }
                self.state.setdefault("player_card_overrides", []).append(entry)
                applied.append(dict(kind="player_card_override", **entry))
        # 借款相關：既有貸款加碼利率、新借款首回合免息。
        surcharge = payload.get("loan_surcharge")
        if surcharge:
            entry = {
                "banks": list(surcharge.get("banks") or []),
                "amount": float(surcharge.get("amount", 0.02)),
                "until_turn": turn + int(surcharge.get("turns", 1)),
                "players": list(targets) if surcharge.get("self_only") else None,
                "label": label,
            }
            self.state.setdefault("loan_surcharges", []).append(entry)
            applied.append(dict(kind="loan_surcharge", **entry))
        grace = payload.get("loan_interest_grace")
        if grace:
            for code in targets:
                self._player(code)["loan_interest_grace_until"] = turn + int(grace.get("turns", 1))
                applied.append({"kind": "loan_interest_grace", "player": code,
                                "until_turn": turn + int(grace.get("turns", 1))})
        # 直接掛在玩家身上的限時旗標（停戰、戰後傷兵歸隊⋯），由前端讀取執行。
        for flag in payload.get("timed_flags") or []:
            for code in targets:
                entry = {
                    "id": card.get("id"),
                    "name": flag.get("label", label),
                    "kind": flag["kind"],
                    # turns 為 null 代表無期限（廢兩改元成功後的永久免疫）。
                    "remaining_turns": (int(flag["turns"]) if flag.get("turns") is not None
                                        else None),
                    "permanent": flag.get("turns") is None,
                    "owners": [code],
                }
                entry.update({key: value for key, value in flag.items()
                              if key not in ("kind", "turns", "label")})
                self._player(code).setdefault("timed_effects", []).append(deepcopy(entry))
                applied.append({"kind": "timed_flag", "player": code, "flag": flag["kind"]})
        # 限時的徵兵成本折抵（火燒紅蓮寺）。
        discount = payload.get("recruit_discount")
        if discount:
            for code in targets:
                entry = {
                    "units": dict(discount.get("units") or {}),
                    "until_turn": turn + int(discount.get("turns", 1)),
                    "label": label,
                }
                self._player(code).setdefault("timed_recruit_discounts", []).append(entry)
                applied.append({"kind": "recruit_discount", "player": code, **entry})
        # 暴動鎮壓所需回合數加碼（火燒紅蓮寺）。
        if payload.get("suppression_turns_bonus"):
            entry = {
                "bonus": int(payload["suppression_turns_bonus"].get("amount", 1)),
                "until_turn": turn + int(payload["suppression_turns_bonus"].get("turns", 1)),
                "label": label,
            }
            self.state.setdefault("suppression_turn_bonuses", []).append(entry)
            applied.append(dict(kind="suppression_turns_bonus", **entry))
        for code in targets:
            self._sync_foreign_deck_cards(code)
            self._sync_conditional_deck_cards(code)
        return applied

    def _fire_scheduled_event_effects(self) -> list:
        """回合推進時把到期的排程效果放出來。"""
        turn = int(self.state["turn"])
        pending, fired = [], []
        for entry in self.state.get("scheduled_event_effects", []):
            if turn < int(entry.get("fire_turn", 0)):
                pending.append(entry)
                continue
            card = {"id": entry.get("card_id"), "name": entry.get("name")}
            fired += self._apply_event_payload(entry.get("payload") or {},
                                               players=entry.get("players"), card=card)
        self.state["scheduled_event_effects"] = pending
        return fired

    def suspended_card_entry(self, player: str, card_id: str) -> Optional[Dict[str, Any]]:
        """這張功能卡現在是不是被事件卡按住了（不限列強 perk）。"""
        if card_id == "artifact_smuggling" and self.academia_active(player):
            return {"label": "中央研究院收編文物", "cards": [card_id], "until_turn": None,
                    "note": "控制江蘇期間文物收歸國有，〈盜賣文物〉封鎖中；離開江蘇即解封"}
        turn = int(self.state["turn"])
        for entry in self.state.get("perk_suspensions", []):
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            if card_id not in (entry.get("cards") or []):
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            return entry
        return None

    def _perk_suspended(self, player: str, card_id: str) -> bool:
        if card_id == "artifact_smuggling" and self.academia_active(player):
            return True
        return self.suspended_card_entry(player, card_id) is not None

    def bank_banned(self, player: str, bank_id: str) -> Optional[Dict[str, Any]]:
        turn = int(self.state["turn"])
        for entry in self.state.get("bank_bans", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            if entry.get("bank") != bank_id:
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            return entry
        return None

    def _expire_relation_locked_effects(self, player: str) -> list:
        """關係跌破門檻的列強戰鬥 perk 立即失效。

        每個會動到外交關係的路徑都會呼叫 _sync_foreign_deck_cards，所以掛在那裡就等於
        「關係一變就重算」；回合推進時也會再掃一次做保險。
        """
        payload = self._player(player)
        relations = payload.get("foreign_relations", {})
        kept, expired = [], []
        for effect in payload.get("timed_effects", []):
            floor = effect.get("expires_below_relation")
            power = effect.get("foreign_power_key")
            if floor is not None and power and int(relations.get(str(power), 0)) < int(floor):
                expired.append({
                    "id": effect.get("id"),
                    "name": effect.get("name"),
                    "power": str(power),
                    "relation": int(relations.get(str(power), 0)),
                    "floor": int(floor),
                })
                continue
            kept.append(effect)
        if expired:
            payload["timed_effects"] = kept
        return expired

    def _sync_foreign_deck_cards(self, player: str) -> None:
        payload = self._player(player)
        self._expire_relation_locked_effects(player)
        card_ids = {card["id"] for card in self.data["function_cards"]["cards"]}
        relations = payload.get("foreign_relations", {})
        for power, cards in FOREIGN_PERK_CARDS.items():
            friendly = int(relations.get(power, 0)) >= FOREIGN_FRIENDLY_THRESHOLD
            for card_id in cards:
                if card_id not in card_ids:
                    continue
                desired = self._perk_copies(card_id, player) if friendly else 0
                if desired and self._perk_suspended(player, card_id):
                    desired = 0   # 事件卡把這張暫時抽離卡池
                current = self._card_count_in_player_zones(payload, card_id)
                if current < desired:
                    payload["function_deck"].extend([card_id] * (desired - current))
                    self.random.shuffle(payload["function_deck"])
                elif current > desired:
                    self._remove_undrawn_cards(payload, card_id, current - desired)
        blocked_map = self.state.setdefault("condemnation_blocked", {})
        immunity_by_power = {
            rule["power"]: float(rule["immunity"])
            for trait, rule in COMPRADOR_TRAITS.items()
            if self._faction_has_trait(player, trait)
        }
        for power, card_id in FOREIGN_CONDEMNATION_CARDS.items():
            if card_id not in card_ids:
                continue
            desired = FOREIGN_CONDEMNATION_COPIES if int(relations.get(power, 0)) <= FOREIGN_HOSTILE_THRESHOLD else 0
            # 買辦技能：該國的譴責進牌庫時每張有機率被私下擺平（日 10%、法 30%）。
            # 只在關係惡化的那一刻擲一次並記住結果，之後每回合同步時不再重擲。
            block_key = f"{player}:{power}"
            if desired <= 0:
                blocked_map.pop(block_key, None)
            else:
                if block_key not in blocked_map:
                    immunity = immunity_by_power.get(power, 0.0)
                    blocked_map[block_key] = sum(
                        1 for _ in range(desired) if immunity and self.random.random() < immunity
                    )
                desired = max(0, desired - int(blocked_map[block_key]))
            current = self._card_count_in_player_zones(payload, card_id)
            if current < desired:
                payload["function_deck"].extend([card_id] * (desired - current))
                self.random.shuffle(payload["function_deck"])
            elif current > desired:
                self._remove_undrawn_cards(payload, card_id, current - desired)

    # ── 條件卡：條件沒達成就不該出現在牌庫裡 ────────────────────────────
    # 玩家不該抽到一張打不出來的牌。條件成立時才把它洗進牌庫，條件消失時把還沒
    # 抽到的那幾張抽走。已經在手上的不動——那是抽牌當下條件成立才拿到的，之後
    # 條件沒了仍然留在手上，只是 _validate_card_use 會擋住不讓打。
    CONDITION_KEYS = (
        "requires_unlock", "requires_provinces", "requires_any_province",
        "requires_cities", "requires_relation_max", "requires_relation_min",
        "concession_power", "requires_peace_with", "requires_city_level_min",
        # 內閣卡：別人打出來之後，其餘玩家的卡池就要封鎖這張。
        "cabinet",
    )

    def _conditional_card_ids(self) -> list:
        return [
            card["id"]
            for card in self.data["function_cards"]["cards"]
            if any(card.get(key) for key in self.CONDITION_KEYS)
        ]

    def _card_conditions_met(self, player: str, card_id: str) -> bool:
        try:
            self._validate_card_use(player, self._card_template(card_id))
        except ValueError:
            return False
        return True

    def _sync_suspendable_cards(self, player: str) -> None:
        """被事件卡按住過的一般功能卡：按住時從卡池清空，解除時洗回原本的張數。

        只碰「曾經被按住過」的卡，免得動到〈中國人之恥〉這種靠卡片動態塞入的張數。
        """
        payload = self._player(player)
        watched = set()
        for entry in self.state.get("perk_suspensions", []):
            watched.update(entry.get("cards") or [])
        if self.academia_founded():
            # 研究院成立後這張卡就是「封鎖／解封」在跑：控制江蘇時鎖住（desired=0），
            # 離開江蘇就洗回原本張數，所以不管現在鎖沒鎖都要納入同步。
            watched.add("artifact_smuggling")
        card_ids = {card["id"] for card in self.data["function_cards"]["cards"]}
        for card_id in watched:
            if card_id not in FUNCTION_CARD_COPIES or card_id not in card_ids:
                continue
            desired = 0 if self._perk_suspended(player, card_id) else int(FUNCTION_CARD_COPIES[card_id])
            current = self._card_count_in_player_zones(payload, card_id)
            if current < desired:
                payload["function_deck"].extend([card_id] * (desired - current))
                self.random.shuffle(payload["function_deck"])
            elif current > desired:
                self._remove_undrawn_cards(payload, card_id, current - desired)

    def _sync_conditional_deck_cards(self, player: str) -> None:
        payload = self._player(player)
        self._sync_suspendable_cards(player)
        for card_id in self._conditional_card_ids():
            if not self._card_allowed_for_player(card_id, player):
                continue
            # 手上那幾張不算在額度裡，也不會被抽走。
            in_hand = payload.get("hand", []).count(card_id)
            if payload.get("pending_draw") == card_id:
                in_hand += 1
            current = self._card_count_in_player_zones(payload, card_id) - in_hand
            if not self._card_conditions_met(player, card_id) or self._perk_suspended(player, card_id):
                desired = 0
            elif card_id in FUNCTION_CARD_COPIES:
                desired = int(FUNCTION_CARD_COPIES[card_id])
            else:
                # 解鎖類卡片由它自己的機制發牌。解鎖已經生效的，條件回來時要洗回去
                # （例如國共合作：汪精衛復出過了，但對蘇關係一度跌破門檻）。
                granted = self._unlocked_card_copies(player, card_id)
                desired = current if granted is None else granted
            if current < desired:
                payload["function_deck"].extend([card_id] * (desired - current))
                self.random.shuffle(payload["function_deck"])
            elif current > desired:
                self._remove_undrawn_cards(payload, card_id, current - desired)

    def _unlocked_card_copies(self, player: str, card_id: str) -> Optional[int]:
        """靠解鎖卡發下來的卡片，在解鎖已經生效時該有幾張；沒解鎖就回 None。"""
        unlocks = self._player(player).get("unlocks", [])
        for card in self.data["function_cards"]["cards"]:
            if str(card.get("unlock_key") or card["id"]) not in unlocks:
                continue
            for entry in card.get("unlocks_cards", []):
                if str(entry.get("id")) == card_id:
                    return int(entry.get("copies", 1))
        return None

    # ── 政府內閣：五張單一玩家卡 ──────────────────────────────────────
    # 同一張全場只能有一個人在檯面上；別人的卡池會被封鎖，手上那張也打不出來。
    # 失效條件寫在卡片資料的 cabinet.lapse 裡，每回合結算前檢查一次。
    def cabinet_card_ids(self) -> list:
        return [
            card["id"] for card in self.data["function_cards"]["cards"]
            if card.get("cabinet")
        ]

    def cabinet_holder(self, card_id: str) -> Optional[str]:
        entry = self.state.get("cabinet", {}).get(card_id)
        return entry.get("owner") if entry else None

    def _register_cabinet_card(self, player: str, card: Dict[str, Any]) -> Dict[str, Any]:
        spec = card.get("cabinet") or {}
        entry = {
            "card_id": card["id"],
            "card_name": card.get("name", card["id"]),
            "owner": player,
            "person": spec.get("person", card.get("name", card["id"])),
            "skill": spec.get("skill", ""),
            "portrait": spec.get("portrait") or spec.get("person"),
            "effect": card.get("effect", ""),
            "lapse_text": spec.get("lapse_text", ""),
            "since_turn": int(self.state["turn"]),
        }
        self.state.setdefault("cabinet", {})[card["id"]] = entry
        for code in self.state["players"]:
            if code != player:
                self._sync_conditional_deck_cards(code)
        return deepcopy(entry)

    def _cabinet_card_lapsed(self, card_id: str, entry: Dict[str, Any]) -> bool:
        card = self._card_template(card_id)
        lapse = (card.get("cabinet") or {}).get("lapse") or {}
        owner = entry.get("owner")
        if owner not in self.state["players"]:
            return True
        if lapse.get("marshal_lost") and owner in (self.state.get("fallen_marshals") or []):
            return True
        city_id = lapse.get("lose_city")
        if city_id and self.state["city_owners"].get(city_id) != owner:
            return True
        relation = lapse.get("relation") or {}
        if relation:
            power = str(relation.get("power"))
            current = int(self._player(owner).get("foreign_relations", {}).get(power, 0))
            if relation.get("at_or_above") is not None and current >= int(relation["at_or_above"]):
                return True
            if relation.get("below") is not None and current < int(relation["below"]):
                return True
        return False

    def _revoke_cabinet_card(self, card_id: str, entry: Dict[str, Any]) -> None:
        """卡片失效：撤掉它帶來的持續效果，人物離開該陣營，卡片重新開放給所有人。"""
        owner = entry.get("owner")
        card = self._card_template(card_id)
        payload = self.state["players"].get(owner)
        mechanic = card.get("mechanic")
        if payload is not None:
            if mechanic == "soong_patronage":
                payload.pop("soong_patronage", None)
            elif mechanic == "central_bank":
                payload["loan_interest_override"] = None
                payload["loan_term_bonus"] = max(
                    0, int(payload.get("loan_term_bonus", 0)) - int(card.get("loan_term_bonus", 0)))
            elif mechanic == "permanent_player_output":
                bonus = payload.setdefault("permanent_output_bonus", {"cash": 0, "factory": 0})
                bonus["cash"] = int(bonus.get("cash", 0)) - int(card.get("cash", 0))
                bonus["factory"] = int(bonus.get("factory", 0)) - int(card.get("factory", 0))
            elif mechanic == "underground_party":
                overrides = payload.setdefault("perk_copy_overrides", {})
                for target_id in (card.get("card_copies") or {}):
                    overrides.pop(str(target_id), None)
                self._sync_foreign_deck_cards(owner)
            elif mechanic == "faction_unlock":
                unlock_key = str(card.get("unlock_key") or card_id)
                payload["unlocks"] = [key for key in payload.get("unlocks", []) if key != unlock_key]
                bonus = payload.setdefault("permanent_output_bonus", {"cash": 0, "factory": 0})
                bonus["cash"] = int(bonus.get("cash", 0)) - int(card.get("cash", 0))
                bonus["factory"] = int(bonus.get("factory", 0)) - int(card.get("factory", 0))
                adjustments = payload.setdefault("recruit_cost_adjustment", {})
                for unit_type, delta in (card.get("recruit_cost_adjustment") or {}).items():
                    item = adjustments.get(str(unit_type))
                    if not item:
                        continue
                    item["cash"] = int(item.get("cash", 0)) - int(delta.get("cash", 0))
                    item["factory"] = int(item.get("factory", 0)) - int(delta.get("factory", 0))
        self.state.get("cabinet", {}).pop(card_id, None)
        if payload is not None:
            self._notify(owner, f"{entry.get('person', card.get('name', card_id))}已離開你的陣營："
                                f"「{card.get('name', card_id)}」失效。")
        self._refresh_city_income()
        for code in self.state["players"]:
            self._sync_conditional_deck_cards(code)

    def _tick_cabinet(self) -> list:
        lapsed = []
        for card_id, entry in list(self.state.get("cabinet", {}).items()):
            if not self._cabinet_card_lapsed(card_id, entry):
                continue
            lapsed.append(deepcopy(entry))
            self._revoke_cabinet_card(card_id, entry)
        return lapsed

    def set_fallen_marshals(self, factions: Iterable[str]) -> None:
        """前端回報哪些陣營的大帥已被俘或陣亡（引擎沒有將領資料）。"""
        self.state["fallen_marshals"] = sorted(
            {str(code) for code in (factions or []) if str(code) in self.state["players"]}
        )

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

    def _charge_build_cost(self, player: str, card: Dict[str, Any]) -> None:
        """技術類卡片打出時要先付現金與工業點，付不起就打不出來。"""
        payload = self._player(player)
        cash = int(card.get("cost", 0))
        factory = int(card.get("factory_cost", 0))
        if cash and int(payload.get("treasury", 0)) < cash:
            raise ValueError(f"{card.get('name', card['id'])}需要 ${cash}（目前 ${int(payload.get('treasury', 0))}）")
        if factory and int(payload.get("factory_points", 0)) < factory:
            raise ValueError(
                f"{card.get('name', card['id'])}需要 {factory} 工業點"
                f"（目前 {int(payload.get('factory_points', 0))}）"
            )
        if cash:
            payload["treasury"] = int(payload["treasury"]) - cash
        if factory:
            payload["factory_points"] = int(payload["factory_points"]) - factory

    def _controls_city_of_level(self, player: str, level_min: int) -> bool:
        """有沒有一座夠大的城市——技術類卡片要靠大城的工業與人力才辦得起來。"""
        for city in self.data["strategic_map"]["cities"]:
            if int(self._with_level(city).get("level", 0)) < level_min:
                continue
            if self.state["city_owners"].get(city["id"], city["faction"]) == player:
                return True
        return False

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

    def _consume_relation_drop_amplifier(self, player: str, power: str) -> int:
        """取出並消耗一次「關係下降加碼」。回傳要額外扣的點數（0 表示沒有）。"""
        entries = self._player(player).get("relation_drop_amplifiers") or []
        for entry in entries:
            if str(entry.get("power")) != str(power):
                continue
            extra = int(entry.get("extra", 1))
            uses = entry.get("uses")
            if uses is not None:
                entry["uses"] = int(uses) - 1
                if entry["uses"] <= 0:
                    entries.remove(entry)
            return extra
        return 0

    def province_card_immunity(self, player: str, card_id: str) -> Optional[Dict[str, Any]]:
        """復興儒學那種「只要還控制某省，這張卡對你無效」的免疫。

        免疫跟著省份跑：丟掉該省立刻失效，奪回就恢復。
        10.1 昆明湖可以把適用省份擴大（provinces 多一個直隸），
        10.3《古史辨》可以把它暫時按掉（suspended_until_turn）。
        """
        turn = int(self.state["turn"])
        for entry in self._player(player).get("province_card_immunities") or []:
            if card_id not in (entry.get("cards") or []):
                continue
            suspended = entry.get("suspended_until_turn")
            if suspended is not None and turn < int(suspended):
                continue
            provinces = entry.get("provinces") or [entry["province"]]
            if not any(self._controlled_provinces(player, [name]) for name in provinces):
                continue
            return entry
        return None

    def _event_effect_active(self, card_id: str) -> bool:
        """這張事件卡掛出去的效果現在還在場上嗎（供 9.5／10.1／10.3 的分支判定）。"""
        turn = int(self.state["turn"])
        for entry in self.state.get("perk_suspensions", []):
            if entry.get("source_card") != card_id:
                continue
            until = entry.get("until_turn")
            if until is None or turn < int(until):
                return True
        for entry in self.state.get("event_locks", []):
            if entry.get("source_card") != card_id:
                continue
            until = entry.get("until_turn")
            if until is None or turn < int(until):
                return True
        for code in self.state["players"]:
            for entry in self._player(code).get("province_card_immunities") or []:
                if entry.get("source_card") == card_id:
                    return True
        return False

    def _validate_card_use(self, player: str, card: Dict[str, Any]) -> None:
        suspended = self.suspended_card_entry(player, str(card.get("id", "")))
        if suspended:
            until = suspended.get("until_turn")
            window = f"，需等到第 {int(until)} 回合" if until is not None else "（無期限）"
            raise ValueError(f"{suspended.get('label', '事件影響')}，本牌暫時打不出來{window}")
        unlock = card.get("requires_unlock")
        if unlock and unlock not in self._player(player).get("unlocks", []):
            raise ValueError(f"此牌需先觸發「{card.get('requires_unlock_name', unlock)}」才能使用")
        required_provinces = card.get("requires_provinces")
        if required_provinces:
            owned = set(self._controlled_provinces(player, required_provinces))
            missing = [name for name in required_provinces if name not in owned]
            if missing:
                raise ValueError(f"需完全控制 {'、'.join(required_provinces)} 才可使用（尚缺 {'、'.join(missing)}）")
        # 「任一省」與 requires_provinces 的「每一省」不同：僑胞匯款只要廣東、福建
        # 其中一省全控就成立。
        any_provinces = card.get("requires_any_province")
        if any_provinces and not self._controlled_provinces(player, any_provinces):
            raise ValueError(f"需完全控制 {'、'.join(any_provinces)} 其中至少一省才可使用")
        required_cities = card.get("requires_cities")
        if required_cities:
            missing = [
                self._city_name(city_id) for city_id in required_cities
                if self.state["city_owners"].get(city_id) != player
            ]
            if missing:
                raise ValueError(f"需控制 {'、'.join(missing)} 才可使用")
        level_min = card.get("requires_city_level_min")
        if level_min is not None and not self._controls_city_of_level(player, int(level_min)):
            raise ValueError(f"需控制至少一座 {level_min} 級以上的城市才可使用")
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
        if card.get("cabinet"):
            holder = self.cabinet_holder(card["id"])
            if holder is not None and holder != player:
                raise ValueError(
                    f"「{card.get('name', card['id'])}」已由{holder}打出並生效，全場只能有一位持有者"
                )
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

    def _card_template(self, card_id: str, player: Optional[str] = None) -> Dict[str, Any]:
        indexes = self.data["indexes"]
        if card_id not in indexes["function_cards"]:
            raise ValueError(f"unknown card id: {card_id}")
        card = deepcopy(indexes["function_cards"][card_id])
        # 事件卡可以改寫功能卡的數字（〈飛鳥非鳥案〉《杜蘭朵》等），有期限的到期就失效。
        # 兩種寫法：`fields` 絕對值改寫（後蓋前），`field_deltas` 增量（多張卡累加）。
        # 增量一律以卡片原始數字為基準逐一加上去，所以生效順序不影響結果。
        turn = int(self.state["turn"]) if getattr(self, "state", None) else 0
        deltas: Dict[str, int] = {}
        overrides = (self.state or {}).get("function_card_overrides", []) if getattr(self, "state", None) else []
        freezes = [f for f in ((self.state or {}).get("function_card_freezes", [])
                               if getattr(self, "state", None) else [])
                   if f.get("card_id") == card_id]
        for index, override in enumerate(overrides):
            if override.get("card_id") != card_id:
                continue
            until = override.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            # 被凍結的欄位：這條改寫排在禁令之後才下的，就整個欄位跳過。
            blocked = {field for f in freezes if index >= int(f.get("from_index", 0))
                       for field in f.get("fields") or []}
            card.update({k: v for k, v in (override.get("fields") or {}).items() if k not in blocked})
            for field, amount in (override.get("field_deltas") or {}).items():
                if field in blocked:
                    continue
                deltas[field] = deltas.get(field, 0) + int(amount)
        for field, amount in deltas.items():
            card[field] = int(card.get(field, 0)) + amount
        if player:
            for override in (self.state or {}).get("player_card_overrides", []):
                if override.get("player") != player or override.get("card_id") != card_id:
                    continue
                until = override.get("until_turn")
                if until is not None and turn >= int(until):
                    continue
                # 綁在城市上的效果（跨洋長途電話綁上海）：城丟了就不算。
                cities = override.get("requires_cities_any") or []
                if cities and not any(self.state["city_owners"].get(city) == player for city in cities):
                    continue
                card.update(override.get("fields") or {})
        return card
