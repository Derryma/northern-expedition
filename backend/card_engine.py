"""In-memory turn and card-pool engine for playtesting."""

from __future__ import annotations

import random
import math
import re
from copy import deepcopy
from typing import Any, Dict, Iterable, Optional

from .data_store import load_game_data
from .foreign_punishment import (PunishmentBook, POWER_TERRITORY_COLORS,
                                 waters_for_city, HOSTILE_AT_OR_BELOW)
from .foreign_pressure import UltimatumBook, ConcessionControlBook, ULTIMATUM_CITIES

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
# 戰力點的唯一真源是 comabt_system/data/unit_stats.json（戰鬥解算器也讀同一份）。
# 先前這裡是第三份寫死的副本：資料檔一份、combat.py 一份、這裡一份，
# 三份剛好相同，但沒有任何東西保證它們會一直相同。
UNIT_FORCE_POINTS = {
    unit: int(stats["force_points"])
    for unit, stats in load_game_data()["unit_stats"]["units"].items()
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
    # 卡片 id 仍是 police_system（存檔與卡片資料都用它）；
    # 改名的是 mechanic 與 timed_effect 的 kind：counter_intel。
    # 「警政單位」是另一張卡（police_precinct，擋黑幫暴動），兩者無關。
    "police_system": 4,
    "du_yuesheng_gamble": 2,
    "hongmen_uprising": 2,
    "red_spear_uprising": 2,
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
    # 投降門檻。真正的判定在 backend/combat_adapter.surrender_verdict，
    # 這裡送給前端只為了「開戰當下對方就已經太弱」那一個前置檢查與按鈕文字。
    "surrender": {
        "force_threshold": 5,
        "overrun_force": 8,
        "overrun_ratio": 2.5,
    },
}
NORTHEAST_PROVINCES = {"奉天", "吉林", "黑龍江"}
POWER_NAMES = {"jp": "日", "su": "蘇", "uk": "英", "fr": "法", "us": "美", "de": "德"}
# 地方官貪腐選「放任」的代價：每回合 $−2，每放任一次疊一層。
GRAFT_NEGLECT_PENALTY = 2
# power_note 寫的是中文（「日」「法」），程式裡用的是代碼。買辦比對要用得到。
POWER_BY_NAME = {name: code for code, name in POWER_NAMES.items()}
# 通知訊息要給人看，不能印 machine_gun。
UNIT_NAMES = {"infantry": "步兵", "cavalry": "騎兵",
              "machine_gun": "機槍", "artillery": "砲兵",
              "gun_boat": "砲艇", "cargo_boat": "運輸船"}


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
        # 懲戒帳本只是 state 的操作介面，本身不存狀態，所以可以在 new_game 之前建。
        self.punishments = PunishmentBook(self)
        self.ultimatums = UltimatumBook(self)
        self.concession_controls = ConcessionControlBook(self)
        # 抽卡時要判「閻錫山還在不在晉系」，而將領與編制住在 SHARED_TACTICAL_STATE。
        # 伺服器在 next_turn 時把快照交進來；沒有快照時 NPC 條件一律判為不成立
        # （見 _npc_requires_met），寧可卡不出現，也不要發一張人早就不在的報紙。
        self._tactical: Optional[Dict[str, Any]] = None
        self._city_garrisons: Dict[str, Dict[str, int]] = {}
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
            # 軍令扣款帳本：撤銷軍令時憑 charge_id 退款，退多少由這裡決定。
            profile["charges"] = {}
            profile["next_charge_id"] = 1
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
            # NPC 陣營的限時戰鬥修正。玩家的掛在 player["timed_effects"]，
            # 但 NPC 不在 state["players"] 裡，所以另設一份全域清單。
            "npc_combat_effects": [],
            # 已經退出地圖的 NPC 陣營（被併吞或整批歸附）。退出之後它的將領
            # 一律視為不在場，點名它的卡片就再也不會出現。
            "retired_npc_factions": [],
            # 大港開炸癱瘓中的港口。
            "port_effects": [],
            # 政府內閣：五張單一玩家卡各自的持有者。同一張全場只能有一個人在檯面上。
            "cabinet": {},
            # 大帥被俘或陣亡的陣營，由前端隨 next_turn 回報（引擎沒有將領資料）。
            "fallen_marshals": [],
            # marshal_ids：各陣營大帥的 general_id，由前端隨回合回報。
            "marshal_ids": {},
            # 事件卡：抽剩的池子、已發生的歷史、正在等待回應的那一輪。
            # pool_copies：同一張卡在池子裡放幾份（最後通牒每國 10 張）。
            # never_drawn：不進池子，只由機制直接插進 pending（日蘇戰況報導）。
            # not_in_pool：卡與報導已建檔，但效果的後端機制還沒補齊（NPC 行動那一批）。
            #   與 never_drawn 不同——那批是「永遠不抽，也沒有效果」；這批是
            #   「效果寫好了但引擎還接不上」，所以先擋在池外，補齊之後把旗標拿掉即可。
            #   擋在池外是刻意的：抽得到卻什麼都不發生，比抽不到更糟。
            "event_pool": [card["id"]
                           for card in (self.data.get("event_cards") or {}).get("cards", [])
                           if not card.get("never_drawn") and not card.get("not_in_pool")
                           for _ in range(max(1, int(card.get("pool_copies", 1))))],
            "event_history": [],
            # 已經抽出去的第幾張事件卡（不含被買辦壓下的重抽）。抽卡順序
            # （NPC 優先那個 3:1 的節奏）就是照這個序號算的。
            "event_draw_index": 0,
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
            # perk_copy_bonuses：有時效的列強 perk 加張（2.2 柏林密約）。
            "perk_copy_bonuses": [],
            # action_bans：被事件禁掉的行動（13.25 軍餉短缺不可訓練／造船／補兵）。
            "action_bans": [],
            "bank_bans": [],
            "bank_limit_multipliers": [],
            # foreign_punishments：生效中的列強懲戒（佔領／封鎖／轟炸）。
            # 一筆對一位玩家，同一張卡可以同時對不同玩家各開一筆。
            "foreign_punishments": [],
            # power_wars：日蘇重疊區打過的仗，一省一筆（報紙要照著刊）。
            "power_wars": [],
            # ultimatums：最後通牒。沒做到 → 該國 [地面部隊] 懲戒對你解封。
            "ultimatums": [],
            # concession_controls：租界管制。一國一位玩家一筆。
            "concession_controls": [],
            # city_rebuilding：轟炸解除後還在停工的城市 → 還要幾回合。
            "city_rebuilding": {},
            "ownerless_cities": [],
            # event_duration_bonuses：依標籤替事件卡的持續時間加碼
            # （火燒紅蓮寺讓 [幫會] 卡多撐 1 回合）。
            "event_duration_bonuses": [],
            "function_card_overrides": [],
            # function_card_freezes：被釘死的功能卡欄位。禁令生效後才下的改寫一律無效，
            # 禁令之前已經下的照舊（見 10.2 西北科學考查團）。
            "function_card_freezes": [],
            "player_card_overrides": [],
            # production_cost_multipliers：事件卡造成的生產成本倍率。
            "production_cost_multipliers": [],
            # railway_bans：交涉破裂造成的路權封鎖，只對特定玩家生效。
            "railway_bans": [],
            # concession_bonus_forfeits：永久放棄租界加成的城市。
            "concession_bonus_forfeits": [],
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
            "next_deal_id": 1,
            # 陣營層級技能目前掛在誰身上（開局時只有張宗昌的〈日本買辦〉在奉系）。
            "faction_general_traits": self._initial_faction_general_traits(),
            # comprador_deflections：買辦擋下懲戒的紀錄（靜默重抽，只供查帳／測試）。
            "comprador_deflections": [],
            # 擋滿上限而被迫放行的紀錄，與上面那份分開記，免得同一張卡兩邊都有。
            "comprador_deflection_overrides": [],
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
        # 可以花錢平息的事件：前端要據此畫按鈕。放進 snapshot 而不是讓前端自己
        # 從 city_output_effects 掃——前端自建視圖正是這個專案反覆掉欄位的地方。
        state["quellable_unrest"] = {player: self.quellable_unrest(player)
                                     for player in state["players"]}
        # 地格資訊欄的癱瘓標籤：哪一種、進度多少，後端算好，前端只排版。
        state["city_disruptions"] = self.city_disruption_report()
        # 偵查：哪些省被揭露、誰有反情報。規則在後端，前端只負責「這支部隊在哪一省」。
        state["intel"] = {player: self.intel_report(player) for player in state["players"]}
        # 已解算的徵募價格。募兵面板先前自己用
        # `bootstrap.recruit_costs × 陣營費率 + 固定加減` 重算一次，
        # 完全漏掉生產成本倍率（油價上漲、軍火禁運、香港軍火交易）與限時折抵
        # （火燒紅蓮寺）——面板寫 $5，後端實收 $6。價格只能有一份來源。
        for player, payload in state["players"].items():
            payload["resolved_recruit_costs"] = {
                unit: {"cash": cash, "factory": factory}
                for unit in RECRUIT_COSTS
                for cash, factory in [self._unit_cost_for(player, unit)]
            }
            # 技能因列強關係失效的名單。判準在後端，畫面只讀結果。
            payload["disabled_traits"] = self.disabled_traits(player)
            payload["resolved_navy_costs"] = {
                unit: {"cash": cash, "factory": factory}
                for unit in NAVY_RECRUIT_COSTS
                for cash, factory in [self._navy_unit_cost_for(player, unit)]
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
            # 工事的成本與工期是規則，前端只拿來顯示按鈕上的數字。
            "engineering": self.engineering_rules(),
            # 出山附加費同理：前端要在名冊上印延攬費，但那個數字是規則，
            # 只能有一份。前端自己抄一份的話，改了這裡而畫面照舊，玩家看到的價目
            # 就會與實際扣款不符。
            "exile_recruit": {
                "surcharge": EXILE_RECRUIT_SURCHARGE,
                "prices": {gid: int(g.get("recruit_value", 0)) + EXILE_RECRUIT_SURCHARGE
                           for gid, g in self.data["generals_in_exile"]["generals"].items()},
            },
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
        ultimatum_garrisons: Optional[Dict[str, list]] = None,
        city_garrison_report: Optional[Dict[str, Dict[str, int]]] = None,
        marshal_ids: Optional[Dict[str, str]] = None,
        faction_trait_holders: Optional[Dict[str, Iterable[str]]] = None,
        tactical: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 這一輪的抽卡要用它判 NPC 條件。傳 None 就是「這一輪沒有快照」，
        # 於是所有帶 NPC 條件的卡都抽不到——這是刻意的保守作法。
        self._tactical = tactical if isinstance(tactical, dict) else None
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
        # 最後通牒：前端回報「哪些指定城市的周邊一格有我方部隊」，這裡結案。
        self.ultimatums.report_garrisons(ultimatum_garrisons or {})
        self._city_garrisons = dict(city_garrison_report or {})
        # 引擎不持有將領資料，大帥是誰只有前端知道；暗殺類事件要靠這份名單擲骰。
        if marshal_ids:
            self.state["marshal_ids"] = {str(k): str(v) for k, v in marshal_ids.items() if v}
        # 陣營層級技能的對帳（買辦、地方財源、剿共）。
        if faction_trait_holders is not None:
            self.set_faction_trait_holders(faction_trait_holders)
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
        # 列強懲戒：關係修好的解除、轟炸目標重挑、被炸城市的重建倒數。
        punishment_log = self.punishments.tick()
        # 最後通牒過期判定與租界管制的解除，都排在經濟結算之前。
        ultimatum_log = self.ultimatums.tick()
        concession_log = self.concession_controls.tick()
        economy_log = self._apply_turn_economy()
        self._tick_timed_effects()
        for player, payload in self.state["players"].items():
            payload["function_purchase_count"] = 0
            payload["function_purchase_used"] = False
            self._sync_foreign_deck_cards(player)
            self._sync_conditional_deck_cards(player)
        turn_entry = {
            "turn": self.state["turn"],
            # 回合結束時各家手上的現金。13.25 軍餉短缺的進入條件要看這個——
            # 事件在本回合收入入帳前結算，拿現值判會判到錯的人。
            "treasury_after": {code: int(payload.get("treasury", 0))
                               for code, payload in self.state["players"].items()},
            "function_purchase_offer": active_player if FEATURES["function_cards"] else None,
            "economy": economy_log,
            "cabinet_lapsed": lapsed_cabinet,
            "foreign_punishments": punishment_log,
            "ultimatums": ultimatum_log,
            "concession_controls": concession_log,
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
            # until_turn 為 None＝永久（公費留學生）；有數字就會自己到期
            # （14.9 地方官貪腐選整頓的 5 回合 $+3）。
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            total["cash"] += int(entry.get("cash", 0))
            total["factory"] += int(entry.get("factory", 0))
        # 地方官貪腐選了「放任」：每回合 $−2，沒有期限，放任幾次就疊幾層，
        # 直到下次抽到那張卡並選「整頓」才一次清光。
        total["cash"] -= GRAFT_NEGLECT_PENALTY * int(
            self._player(player).get("graft_neglect", 0))
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
        return log

    def _tick_timed_effects(self) -> None:
        for payload in self.state["players"].values():
            active_effects = []
            for effect in payload.get("timed_effects", []):
                # 無期限旗標（remaining_turns 為 None）永遠留著，不參與倒數。
                if effect.get("permanent") or effect.get("remaining_turns") is None:
                    active_effects.append(effect)
                    continue
                # 這一回合才掛上去的效果不在這次倒數——事件卡是在回合結算「之前」
                # 才結算完的，若照扣，一張寫「3 回合」的卡玩家實際只吃得到 2 回合。
                if effect.pop("granted_this_turn", None):
                    active_effects.append(effect)
                    continue
                remaining = int(effect.get("remaining_turns", 0)) - 1
                if remaining > 0:
                    effect["remaining_turns"] = remaining
                    active_effects.append(effect)
            payload["timed_effects"] = active_effects
        for player in self.state["players"]:
            self._expire_relation_locked_effects(player)
        self._tick_npc_combat_effects()
        self._tick_railway_effects()
        self._tick_port_effects()
        active_city_effects = []
        for effect in self.state.get("city_output_effects", []):
            # 這兩種暴動沒有回合上限，解除條件是駐軍而不是時間。
            if effect.get("kind") in ("qing_gang_riot", "red_army_uprising"):
                active_city_effects.append(effect)
                continue
            # remaining_turns 為 None 也是無限期，解除條件是花錢
            # （米騷動：不賑濟就無限期停產）。不能拿去 int() 減一。
            if effect.get("remaining_turns") is None:
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
            # 租界管制：加成綁的是城市的「租界」狀態，所以只有該城**所有**租界國
            # 都對你管制時才會消失；只被其中一國管制，加成照領。
            if self.concession_controls.bonus_suspended(city, owner):
                continue
            # 門戶開放照會那一類：這座城的租界加成被永久放棄，與關係無關。
            if city["id"] in (self.state.get("concession_bonus_forfeits") or []):
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
            # 被列強佔領／封鎖／轟炸／還在重建的城市一律沒有產出。
            if self.punishments.city_output_is_zero(city["id"], player):
                economy.append({"id": city["id"], "name": city["name"],
                                "province": city["province"], "cash": 0, "factory": 0,
                                "suppressed_by": self.punishments.city_status(city["id"])
                                or {"status": "occupied"}})
                continue
            general_bonus = province_bonus.get(city["province"], {"cash": 0, "factory": 0})
            # 租界管制：該國租界城市每回合 $−3、工廠 −3，多國可疊加至歸零為止。
            control = self.concession_controls.penalty_for_city(city, player)
            # 11.1：該省正在交戰時，境內每座城市的金錢與工廠各扣一份（商界視戰事為害）。
            war = self._province_combat_penalty(city["province"])
            cash, factory = self._adjusted_city_output(
                city["id"],
                scaled_city_value(self._with_level(city), "cash")
                + int(development.get(city["id"], {}).get("cash", 0))
                + int(general_bonus["cash"]) + war["cash"] - control,
                scaled_city_value(self._with_level(city), "factory")
                + int(development.get(city["id"], {}).get("factory", 0))
                + int(general_bonus["factory"]) + war["factory"] - control,
            )
            row = {
                "id": city["id"],
                "name": city["name"],
                "province": city["province"],
                "cash": cash,
                "factory": factory,
            }
            # 前端的「每回合結算明細」要說得出這座城為什麼少了錢，所以把
            # 租界管制的細目一起送出去：哪幾國在管制、扣了多少、加成有沒有停。
            if control:
                controlling = sorted(set(city.get("concession") or [])
                                     & self.concession_controls.controlled_powers(player))
                row["concession_control"] = {
                    "powers": controlling,
                    "penalty": control,
                    "bonus_suspended": self.concession_controls.bonus_suspended(city, player),
                    "concession": sorted(city.get("concession") or []),
                }
            economy.append(row)
        return economy

    def _city_by_id(self, city_id: str) -> Optional[Dict[str, Any]]:
        for city in self.data["strategic_map"]["cities"]:
            if city["id"] == city_id:
                return city
        return None

    def _refresh_city_income(self) -> None:
        for player, payload in self.state["players"].items():
            city_economy = self._city_economy_for(player)
            bonus = payload.get("permanent_output_bonus", {})
            # 公費留學生那種「幾回合後才開始」的加成，時候到了才算進來。
            delayed = self._delayed_output_bonus(player)
            payload["city_economy"] = city_economy
            income = (sum(item["cash"] for item in city_economy)
                      + int(bonus.get("cash", 0)) + delayed["cash"])
            factory_income = (sum(item["factory"] for item in city_economy)
                              + int(bonus.get("factory", 0)) + delayed["factory"])
            # 玩家層級的產出乘數（13.24 軍工訂單暴增：工廠 ×1.5）。設計稿寫
            # 「無條件進位」，所以用 ceil 不是 round——×1.5 之後的 0.5 歸玩家。
            multiplier = self._output_multiplier(player)
            payload["income"] = int(math.ceil(income * multiplier["cash"]))
            payload["factory_income"] = int(math.ceil(factory_income * multiplier["factory"]))

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

    # ── 將領忠誠 ────────────────────────────────────────────────────────
    # 規則住在後端，前端只送「它自己擁有的事實」（部隊編制、忠誠覆寫、誰在誰手上），
    # 不送算好的數字。先前整套算式只在 app.js 裡，而後端卻拿前端算出來的忠誠去
    # 扣錢擲骰策反——規則與判定分居兩處，任何一邊改動都不會有人叫。
    LOYALTY_NO_ARMY_CAP = 2          # 沒有直屬部隊：忠誠最多 2
    LOYALTY_RELATIVE_POWER_CAP = 2   # 相對實力修正的上下限
    LOYALTY_BATTLE_LOSS_CAP = 4      # 戰損修正的下限

    def compute_loyalty(
        self,
        *,
        base: Optional[float],
        absolute: bool = False,
        override: Optional[float] = None,
        in_exile: bool = False,
        has_army: bool = True,
        jailed: bool = False,
        recruited: bool = False,
        current_force: float = 0.0,
        average_friendly_force: float = 0.0,
        baseline_force: float = 0.0,
        relation_penalty: float = 0.0,
    ) -> Dict[str, Any]:
        """算一位將領此刻的忠誠，連同拆帳明細。

        回傳 breakdown 是為了讓面板能照著顯示，而不是自己再推一次。
        """
        if base is None:
            return {"value": None, "breakdown": {}}
        if absolute:
            return {"value": 10, "breakdown": {"absolute": True}}
        source = float(base if override is None else override)
        base_loyalty = max(0.0, min(10.0, source + float(relation_penalty)))
        breakdown = {"base": int(base_loyalty), "relation_penalty": float(relation_penalty),
                     "override": override is not None}
        if in_exile:
            return {"value": int(base_loyalty),
                    "breakdown": {**breakdown, "in_exile": True}}
        if not has_army or jailed or recruited:
            value = min(int(base_loyalty), self.LOYALTY_NO_ARMY_CAP)
            return {"value": value,
                    "breakdown": {**breakdown, "no_army": int(base_loyalty) - value}}
        average = max(1.0, float(average_friendly_force))
        relative = max(-self.LOYALTY_RELATIVE_POWER_CAP,
                       min(self.LOYALTY_RELATIVE_POWER_CAP,
                           round((float(current_force) / average - 1) * 3)))
        initial = max(1.0, float(baseline_force))
        loss_rate = max(0.0, (initial - float(current_force)) / initial)
        battle_loss = -min(self.LOYALTY_BATTLE_LOSS_CAP, math.floor(loss_rate * 5))
        value = int(max(0, min(10, base_loyalty + relative + battle_loss)))
        return {"value": value,
                "breakdown": {**breakdown, "relative_power": int(relative),
                              "battle_loss": int(battle_loss),
                              "current_force": round(float(current_force), 2),
                              "baseline_force": round(initial, 2)}}

    LOYALTY_OVERRIDE_MIN, LOYALTY_OVERRIDE_MAX = 1, 10

    def mutable_loyalty_generals(self, owner: str,
                                 tactical: Optional[Dict[str, Any]] = None) -> list:
        """這位陣營底下「忠誠可變」的將領。

        排除：忠誠為 null 的（派系核心）、絕對忠誠的、以及 loyalty_exempt 的。
        判準跟 compute_loyalty 用的是同一組欄位，所以卡面說「全體可變忠誠將領」時
        前後端指的是同一批人。
        """
        snapshot = tactical if isinstance(tactical, dict) else (self._tactical or {})
        trees = snapshot.get("generalTrees") or {}
        owners = snapshot.get("generalOwners") or {}
        overrides = snapshot.get("loyaltyOverrides") or {}
        out = []
        for faction, tree in trees.items():
            for general_id, general in (tree.get("generals") or {}).items():
                if owners.get(general_id, faction) != owner:
                    continue
                if general.get("loyalty") is None or general.get("loyalty_exempt"):
                    continue
                absolute = bool(general.get("absolute_loyalty")) and not (
                    general_id in overrides
                    and float(overrides[general_id]) <= self.LOYALTY_OVERRIDE_MIN)
                if absolute:
                    continue
                out.append(general_id)
        return sorted(out)

    def apply_loyalty_deltas(self, deltas, tactical: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        """把卡片的忠誠加減算成新的 loyaltyOverrides，回傳「將領 → 新的基礎值」。

        **加減的是基礎值，不是畫面上顯示的那個數字。** 先前這一段在前端，
        而且拿顯示值去加——顯示值已經含了相對實力與戰損的修正，後端再套一次，
        於是「忠誠 +2」在強軍身上縮成 +1、在弱軍身上直接變成 **+0**（卡等於沒效果）。

        deltas 是 [{"general_id": ..., "amount": n}] 或 [{"owner": ..., "amount": n}]；
        指定 owner 就是「該陣營全體可變忠誠將領」。
        """
        snapshot = tactical if isinstance(tactical, dict) else (self._tactical or {})
        trees = snapshot.get("generalTrees") or {}
        overrides = dict(snapshot.get("loyaltyOverrides") or {})
        base_of = {}
        for tree in trees.values():
            for general_id, general in (tree.get("generals") or {}).items():
                base_of[general_id] = general.get("loyalty")
        changed: Dict[str, int] = {}

        def bump(general_id: str, amount: int) -> None:
            if general_id not in base_of or base_of[general_id] is None:
                return
            current = overrides.get(general_id, base_of[general_id])
            value = int(max(self.LOYALTY_OVERRIDE_MIN,
                            min(self.LOYALTY_OVERRIDE_MAX, float(current) + float(amount))))
            overrides[general_id] = value
            changed[general_id] = value

        for delta in deltas or []:
            amount = int(delta.get("amount") or 0)
            if not amount:
                continue
            if delta.get("general_id"):
                targets = [str(delta["general_id"])]
            elif delta.get("owner"):
                targets = self.mutable_loyalty_generals(str(delta["owner"]), snapshot)
            else:
                targets = []
            for general_id in targets:
                bump(general_id, amount)
        return changed

    def resolve_loyalty_effect(self, kind: str, faction: str, effect: Dict[str, Any],
                               tactical: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """事件卡交辦的忠誠加減：挑對象、算新的 loyaltyOverrides，全在後端。

        `loyalty_all` 是全體可變忠誠將領；`loyalty_random` 是隨機幾位——
        **抽籤也在後端**，用引擎自己的亂數，所以同一顆種子重播結果一致。
        先前抽籤與加減都在前端，而且加在畫面顯示值上（見 apply_loyalty_deltas）。
        """
        snapshot = tactical if isinstance(tactical, dict) else (self._tactical or {})
        amount = int(effect.get("amount") or 0)
        pool = self.mutable_loyalty_generals(str(faction), snapshot)
        if not amount or not pool:
            return {"picked": [], "overrides": {}, "amount": amount}
        if kind == "loyalty_random":
            want = min(int(effect.get("count") or 0), len(pool))
            picked = [pool[i] for i in self.random.sample(range(len(pool)), want)] if want else []
        else:
            picked = list(pool)
        overrides = self.apply_loyalty_deltas(
            [{"general_id": general_id, "amount": amount} for general_id in picked], snapshot)
        return {"picked": picked, "overrides": overrides, "amount": amount}

    def loyalty_report(self, tactical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """從伺服器手上的戰術狀態，算出每一位將領的忠誠。

        伺服器本來就存著 `SHARED_TACTICAL_STATE`（部隊編制、將領樹、忠誠覆寫、
        誰在誰手上），所以後端有足夠的事實自己算——不必反過來相信前端算的數字。
        """
        if not isinstance(tactical, dict):
            return {}
        armies = tactical.get("armies") or {}
        trees = tactical.get("generalTrees") or {}
        owners = tactical.get("generalOwners") or {}
        overrides = tactical.get("loyaltyOverrides") or {}
        baselines = tactical.get("loyaltyBaselineArmyUnits") or {}
        army_by_general = {}
        for army_id, army in armies.items():
            if army.get("generalId"):
                army_by_general[army["generalId"]] = {"id": army_id, **army}
        force = lambda units: sum(max(0, int(units.get(u, 0) or 0)) * points
                                  for u, points in UNIT_FORCE_POINTS.items())
        by_faction: Dict[str, list] = {}
        for army_id, army in armies.items():
            if army.get("status") == "jailed":
                continue
            by_faction.setdefault(str(army.get("faction")), []).append(
                force(army.get("units") or {}))
        out: Dict[str, Any] = {}
        for faction, tree in trees.items():
            for general_id, general in (tree.get("generals") or {}).items():
                army = army_by_general.get(general_id)
                units = (army or {}).get("units") or {}
                owner = owners.get(general_id, faction)
                peers = by_faction.get(str(owner)) or []
                out[general_id] = self.compute_loyalty(
                    base=general.get("loyalty"),
                    absolute=bool(general.get("absolute_loyalty"))
                    and not (general_id in overrides and float(overrides[general_id]) <= 1),
                    override=overrides.get(general_id),
                    in_exile=general.get("status") == "in_exile",
                    has_army=bool(army),
                    jailed=(army or {}).get("status") == "jailed",
                    recruited=general.get("status") == "recruited",
                    current_force=force(units),
                    average_friendly_force=(sum(peers) / len(peers)) if peers else 0.0,
                    baseline_force=force(baselines.get((army or {}).get("id")) or units),
                )
        return out

    def army_force_from_tactical(self, tactical: Optional[Dict[str, Any]],
                                 army_id: str) -> Optional[float]:
        """從伺服器手上的戰術狀態算某支部隊的戰力點。

        補兵的上限檢查要拿這個當基準，而不是前端自己報的 current_force。
        """
        if not isinstance(tactical, dict):
            return None
        army = (tactical.get("armies") or {}).get(str(army_id))
        if not isinstance(army, dict):
            return None
        units = army.get("units") or {}
        return float(sum(max(0, int(units.get(unit) or 0)) * points
                         for unit, points in UNIT_FORCE_POINTS.items()))

    # ── 回合結束時的自動補兵 ────────────────────────────────────────────
    #
    # NPC 增援與野戰醫院原本整套住在 app.js：節奏常數、資格判定、抽兵種，
    # 全在前端，而且**用沒有種子的 Math.random()**——多人連線時每個 client 算出來
    # 的 NPC 兵力可能不一樣，誰先 publishSharedState 誰說了算。
    # 伺服器手上有 SHARED_TACTICAL_STATE（編制、狀態、將領樹、將領歸屬），資料是齊的。

    NPC_FACTIONS = ("Y", "G", "M", "H", "C", "D", "Q")
    NPC_GROWTH_INFANTRY_EVERY_TURNS = 3
    NPC_GROWTH_HEAVY_EVERY_TURNS = 5
    NPC_GROWTH_HEAVY_UNITS = ("machine_gun", "cavalry", "artillery")
    DEAD_ARMY_STATUSES = ("jailed", "killed", "destroyed", "surrendered")

    @staticmethod
    def _force_of(units: Optional[Dict[str, Any]]) -> int:
        return sum(max(0, int((units or {}).get(unit) or 0)) * points
                   for unit, points in UNIT_FORCE_POINTS.items())

    @classmethod
    def _trim_to_force(cls, units: Dict[str, Any], cap: int) -> Dict[str, int]:
        """裁到戰力點不超過 cap，**從最貴的兵種開始裁**。

        「最貴的先裁」是既有規則（前端 `clampUnitsToForceCap()` 一直是這樣做的，
        12.x 列強行動那批的「部隊戰力一次性 −40%」就走這條），這裡只是把它搬到後端。
        """
        out = {unit: max(0, int(units.get(unit) or 0)) for unit in UNIT_FORCE_POINTS}
        order = sorted(UNIT_FORCE_POINTS, key=lambda unit: -UNIT_FORCE_POINTS[unit])
        while cls._force_of(out) > max(0, int(cap)):
            unit = next((u for u in order if out[u] > 0), None)
            if unit is None:
                break
            out[unit] -= 1
        return out

    @classmethod
    def _clamp_to_force_cap(cls, units: Dict[str, Any]) -> Dict[str, int]:
        """超過單一部隊上限就從最貴的兵種開始裁，直到回到上限以內。"""
        return cls._trim_to_force(units, ARMY_FORCE_CAP)

    @classmethod
    def _cut_down_to_force(cls, units: Dict[str, Any], target: int) -> Dict[str, int]:
        """裁到戰力點**剛好等於** target，一樣從最貴的兵種先裁。

        和 `_trim_to_force` 的差別是「不裁過頭」。那個函式的工作是把超編的部隊
        壓回上限以內，裁多了無所謂；這裡的工作是命中一個指定的戰力值——
        楊森 13 點打九折是 11 點，先砍掉那一營砲兵會直接掉到 9 點，
        「戰力 −10%」實際變成 −31%。所以每一步只裁「裁下去還不會低於 target」的
        最貴兵種；沒有這種兵種時就停手（剩下的都太貴，再裁就過頭了）。
        """
        out = {unit: max(0, int(units.get(unit) or 0)) for unit in UNIT_FORCE_POINTS}
        order = sorted(UNIT_FORCE_POINTS, key=lambda unit: -UNIT_FORCE_POINTS[unit])
        target = max(0, int(target))
        while cls._force_of(out) > target:
            unit = next((u for u in order
                         if out[u] > 0
                         and cls._force_of(out) - UNIT_FORCE_POINTS[u] >= target), None)
            if unit is None:
                break
            out[unit] -= 1
        return out

    @staticmethod
    def _home_faction(army_id: str) -> str:
        return str(army_id).split("-")[0]

    def _npc_defected(self, army_id: str, army: Dict[str, Any],
                      owners: Dict[str, Any]) -> bool:
        """跳槽過的部隊永久除名：將領歸屬換人（招降）或部隊改掛別家旗（策反）。"""
        home = self._home_faction(army_id)
        owner = owners.get(army.get("generalId"))
        if owner and owner != home:
            return True
        return bool(army.get("faction")) and army["faction"] != home

    def npc_reinforcements(self, tactical: Optional[Dict[str, Any]],
                           turn: Optional[int] = None) -> Dict[str, Any]:
        """NPC 勢力的自動增兵。回傳每支部隊補完之後的編制，前端照著寫回去。"""
        if not isinstance(tactical, dict):
            return {"grown": [], "ended_growth": []}
        turn = int(self.state["turn"] if turn is None else turn)
        armies = tactical.get("armies") or {}
        trees = tactical.get("generalTrees") or {}
        owners = tactical.get("generalOwners") or {}
        marshal_army_ids = set()
        for faction in self.NPC_FACTIONS:
            marshal_id = (trees.get(faction) or {}).get("great_general_id")
            if not marshal_id:
                continue
            for army_id, army in armies.items():
                if (self._home_faction(army_id) == faction
                        and army.get("generalId") == marshal_id):
                    marshal_army_ids.add(army_id)

        retired = self.retired_npc_factions()
        ended: list = []
        for army_id, army in armies.items():
            if self._home_faction(army_id) not in self.NPC_FACTIONS:
                continue
            if army.get("npcGrowthEnded"):
                continue
            if self._npc_defected(army_id, army, owners):
                ended.append(army_id)

        grown: list = []
        if turn <= 0:
            return {"grown": grown, "ended_growth": ended}
        infantry_turn = turn % self.NPC_GROWTH_INFANTRY_EVERY_TURNS == 0
        heavy_turn = turn % self.NPC_GROWTH_HEAVY_EVERY_TURNS == 0
        if not infantry_turn and not heavy_turn:
            return {"grown": grown, "ended_growth": ended}

        for army_id in sorted(armies):
            army = armies[army_id]
            if self._home_faction(army_id) not in self.NPC_FACTIONS:
                continue
            # 已經退出地圖的陣營不再補兵。少了這一條，被併吞的黔軍會在
            # 三回合後自己長出一營步兵，然後一路長回來。
            if self._home_faction(army_id) in retired:
                continue
            if army.get("npcGrowthEnded") or army_id in ended:
                continue
            if army.get("status") in self.DEAD_ARMY_STATUSES:
                continue
            units = {unit: max(0, int((army.get("units") or {}).get(unit) or 0))
                     for unit in UNIT_FORCE_POINTS}
            if self._force_of(units) >= ARMY_FORCE_CAP:
                continue
            gains: list = []
            if infantry_turn and self._force_of(units) + UNIT_FORCE_POINTS["infantry"] <= ARMY_FORCE_CAP:
                units["infantry"] += 1
                gains.append("infantry")
            if heavy_turn and army_id in marshal_army_ids:
                room = ARMY_FORCE_CAP - self._force_of(units)
                choices = [unit for unit in self.NPC_GROWTH_HEAVY_UNITS
                           if UNIT_FORCE_POINTS[unit] <= room]
                if choices:
                    pick = choices[self.random.randrange(len(choices))]
                    units[pick] += 1
                    gains.append(pick)
            if not gains:
                continue
            grown.append({"armyId": army_id, "faction": self._home_faction(army_id),
                          "gains": gains, "units": self._clamp_to_force_cap(units)})
        return {"grown": grown, "ended_growth": ended}

    # 〈泳渡海峽的女子〉開的全軍野戰醫院沒有卡片欄位可讀，用這個當基準。
    DEFAULT_FIELD_HOSPITAL_BATTALIONS = 1

    def _field_hospital_battalions(self, faction: str, general_id: Optional[str]) -> int:
        """這支部隊一次能歸隊幾個營。數字的唯一來源是功能卡上的 recover_battalions。

        名單上的將領吃卡片上的數字；沒進名單、靠事件卡開的全軍醫院吃預設值。
        資料檔目前只有一張 field_hospital 卡；真要出現第二張、而且數字不一樣時
        這裡會直接擋下來，不會偷偷挑第一張（FieldHospitalSourceTests 也守著）。
        """
        roster = self._player(faction).get("field_hospital_generals") or []
        if general_id not in roster:
            return self.DEFAULT_FIELD_HOSPITAL_BATTALIONS
        values = {max(1, int(card.get("recover_battalions",
                                      self.DEFAULT_FIELD_HOSPITAL_BATTALIONS)))
                  for card in self.data["function_cards"]["cards"]
                  if card.get("mechanic") == "field_hospital"}
        if len(values) > 1:
            raise ValueError(f"field_hospital 卡的 recover_battalions 不只一種：{sorted(values)}")
        return values.pop() if values else self.DEFAULT_FIELD_HOSPITAL_BATTALIONS

    def field_hospital_recovery(self, tactical: Optional[Dict[str, Any]],
                                turn: Optional[int] = None) -> Dict[str, Any]:
        """野戰醫院：上一戰的損失裡隨機挑一個兵種免費歸隊一營。

        「有沒有野戰醫院」看 field_hospital_generals 名單，或〈泳渡海峽的女子〉
        開的 field_hospital_window（全軍適用）。兩份資料都在後端。
        """
        if not isinstance(tactical, dict):
            return {"healed": [], "cleared": []}
        turn = int(self.state["turn"] if turn is None else turn)
        armies = tactical.get("armies") or {}
        healed: list = []
        cleared: list = []
        for army_id in sorted(armies):
            army = armies[army_id]
            pending = army.get("fieldHospitalPending") or None
            if not pending or not (pending.get("units") or []):
                continue
            if army.get("status") in self.DEAD_ARMY_STATUSES or army.get("embarkedOn"):
                continue
            if turn <= int(pending.get("turn") or 0):
                continue                       # 要等到「下一回合」
            faction = army.get("faction") or self._home_faction(army_id)
            general_id = army.get("generalId")
            covered = (self.has_timed_flag(faction, "field_hospital_window")
                       or general_id in (self._player(faction).get("field_hospital_generals") or []))
            if not covered:
                cleared.append(army_id)        # 醫院沒了，待辦也清掉
                continue
            candidates = [unit for unit in pending["units"] if unit in UNIT_FORCE_POINTS]
            if not candidates:
                cleared.append(army_id)
                continue
            # 歸隊幾個營由卡片決定（〈進口盤尼西林〉的 recover_battalions）。
            # 先前這裡寫死 +1，卡片上那個欄位沒有任何讀取者——同一條規則
            # 存在兩份，改資料完全不會生效。
            battalions = self._field_hospital_battalions(faction, general_id)
            units = {unit: max(0, int((army.get("units") or {}).get(unit) or 0))
                     for unit in UNIT_FORCE_POINTS}
            picked = []
            for _ in range(battalions):
                pick = candidates[self.random.randrange(len(candidates))]
                units[pick] += 1
                picked.append(pick)
            pick = picked[0]
            healed.append({"armyId": army_id, "unit": pick,
                           "units": self._clamp_to_force_cap(units)})
        return {"healed": healed, "cleared": cleared}

    def turn_reinforcements(self, tactical: Optional[Dict[str, Any]],
                            turn: Optional[int] = None) -> Dict[str, Any]:
        return {"npc": self.npc_reinforcements(tactical, turn),
                "field_hospital": self.field_hospital_recovery(tactical, turn)}

    def navy_outlook(self, tactical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """每支艦隊「還能撐幾輪」的預估，由後端算好給前端顯示。

        前端 navyContactEstimate() 原本自己重跑一次退卻線與火力公式。畫面上的
        數字必須和真正結算用的規則同源，不然玩家看到「還能撐 3 輪」卻一輪就被打退。
        伺服器手上有 SHARED_TACTICAL_STATE（艦隊、部隊、位置）與宣戰關係，資料是齊的。
        """
        from navy_system.navy import contact_outlook
        if not isinstance(tactical, dict):
            return {}
        rules = self.data["navy_system"]
        navies = tactical.get("navyDivisions") or []
        armies = (tactical.get("armies") or {}).values()
        out: Dict[str, Any] = {}
        for navy in navies:
            faction = navy.get("faction") or str(navy.get("id", "")).split("-")[0]
            cell = navy.get("cellKey")
            enemy_navy = next(
                (other for other in navies
                 if other.get("id") != navy.get("id") and other.get("cellKey") == cell
                 and self._at_war(faction, other.get("faction")
                                  or str(other.get("id", "")).split("-")[0])),
                None)
            enemy_artillery = 0
            for army in armies:
                if army.get("cellKey") != cell or army.get("embarkedOn"):
                    continue
                if army.get("status") in ("killed", "destroyed", "jailed"):
                    continue
                if not self._at_war(faction, army.get("faction")):
                    continue
                enemy_artillery += max(0, int((army.get("units") or {}).get("artillery") or 0))
            out[str(navy.get("id"))] = contact_outlook(navy, enemy_navy, enemy_artillery, rules)
        return out

    def _at_war(self, first: Optional[str], second: Optional[str]) -> bool:
        if not first or not second or first == second:
            return False
        players = self.state.get("players", {})
        for a, b in ((first, second), (second, first)):
            relation = (players.get(a, {}).get("warlord_relations") or {}).get(b) or {}
            if relation.get("status") == "war":
                return True
        return False

    # 目標將領自帶的抗策反：唐生智的〈佛教將軍〉−5%。
    # 這張表先前**只存在於前端**，後端是從請求裡收 resistance 這個數字——
    # 等於成功率的一部分由客戶端說了算。現在表在後端，前端不再送這個欄位。
    DEFECTION_RESISTANCE_TRAITS = {"buddhist_general": 0.05}

    def _defection_resistance(self, traits) -> float:
        return sum(self.DEFECTION_RESISTANCE_TRAITS.get(str(t), 0.0)
                   for t in (traits or []))

    def _defection_inputs(self, general_id: str,
                          tactical: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """從伺服器手上的戰術快照湊出這一次策反的三個輸入：忠誠、戰力、抗性。

        先前這三個都由前端算好送上來（連成功率的公式前端也自備一份）。
        伺服器本來就存著 SHARED_TACTICAL_STATE，自己算得出來。
        """
        snapshot = tactical if isinstance(tactical, dict) else (self._tactical or {})
        armies = snapshot.get("armies") or {}
        trees = snapshot.get("generalTrees") or {}
        general = None
        for tree in trees.values():
            found = (tree.get("generals") or {}).get(general_id)
            if found:
                general = found
                break
        army = next((a for a in armies.values() if a.get("generalId") == general_id), None)
        units = (army or {}).get("units") or {}
        force = sum(max(0, int(units.get(unit, 0) or 0)) * points
                    for unit, points in UNIT_FORCE_POINTS.items())
        report = self.loyalty_report(snapshot).get(general_id) or {}
        return {
            "loyalty": report.get("value"),
            "force": force,
            "resistance": self._defection_resistance((general or {}).get("traits")),
            "traits": list((general or {}).get("traits") or []),
            "known": bool(general),
        }

    def defection_quote(self, general_id: str,
                        tactical: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """報價：策反這位將領要花多少、成功率多少。畫面上那兩個數字的唯一來源。"""
        inputs = self._defection_inputs(general_id, tactical)
        loyalty = max(1, min(10, int(inputs["loyalty"] or 1)))
        force = max(1.0, float(inputs["force"]))
        cost = int(math.ceil((10 + force * 3 + loyalty * 2) * 0.5))
        base_chance = 0.45 - loyalty * 0.04 - force * 0.003
        chance = max(0.03, min(0.60, base_chance * 1.25) - max(0.0, float(inputs["resistance"])))
        return {
            "general_id": general_id, "cost": cost, "chance": chance,
            "loyalty": loyalty, "force": force, "resistance": inputs["resistance"],
            "known": inputs["known"],
        }

    def attempt_defection(self, player: str, loyalty: int) -> Dict[str, Any]:
        return self.attempt_defection_with_force(player, loyalty, 1)

    def attempt_defection_with_force(
        self, player: str, loyalty: int = 0, force: float = 0, traits=None,
        resistance: float = 0.0, general_id=None,
        tactical: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """成本與成功率一律由後端從戰術快照算。

        指定 general_id 時，loyalty／force／resistance 三個參數一概忽略——
        客戶端說的不算。舊的呼叫端（沒有 general_id 的測試夾具）才走傳進來的數字。
        """
        player_state = self._player(player)
        if general_id:
            quote = self.defection_quote(str(general_id), tactical)
            loyalty, force = quote["loyalty"], quote["force"]
            cost, chance = quote["cost"], quote["chance"]
            traits = traits if traits is not None else \
                self._defection_inputs(str(general_id), tactical)["traits"]
        else:
            loyalty = max(1, min(10, int(loyalty)))
            force = max(1.0, float(force))
            cost = int(math.ceil((10 + force * 3 + loyalty * 2) * 0.5))
            base_chance = 0.45 - loyalty * 0.04 - force * 0.003
            chance = max(0.03, min(0.60, base_chance * 1.25) - max(0.0, float(resistance or 0.0)))
        if player_state.get("treasury", 0) < cost:
            raise ValueError(f"defection attempt requires {cost} cash")
        player_state["treasury"] -= cost
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
            # 免疫哪張卡寫在卡片資料的 immune_cards 裡，不寫死在引擎——
            # 引擎只負責「持有這個效果的人，那幾張卡的生產加價不算在他頭上」。
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "oil_price_immunity",
                "remaining_turns": int(card.get("duration_turns", 10)),
                "owners": [player],
                "immune_cards": [str(x) for x in (card.get("immune_cards") or [])],
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
        elif mechanic == "counter_intel":
            duration = int(card.get("duration_turns", 3))
            timed_effect = {
                "id": card_id,
                "name": card.get("name", card_id),
                "kind": "counter_intel",
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
                # 先前這一筆沒有 kind——地格資訊欄認不出它是哪一種癱瘓。
                "kind": "communist_riot",
                "name": card.get("name", card_id),
                "label": str(card.get("disruption_label", card.get("name", card_id))),
                "target_owner": target_owner,
                "remaining_turns": int(card.get("duration_turns", 3)),
                "total_turns": int(card.get("duration_turns", 3)),
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
            # 同一個省已經在暴動就不能再發動一次。產出只會歸零一次，但分潤是
            # **逐筆**結算的——疊第二筆會讓兩個發動者各拿一份「被截斷的一半」，
            # 目標少 11、兩人合拿 24，憑空生錢。
            # 這與鐵路「已經在搶修中」不准重複爆破是同一條道理。
            if any(effect.get("kind") == mechanic
                   and effect.get("target_owner") == target_owner
                   and effect.get("province") == province
                   for effect in self.state.get("city_output_effects", [])):
                raise ValueError(f"{province}已經在暴動中，不能重複發動")
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
                # 治安惡化期（火燒紅蓮寺、鴉片與釐金稅收）發動的暴動要多鎮壓幾回合。
                # 加碼只在**發動當下**結算一次，之後這條暴動的門檻就固定了。
                "required_turns": int(card.get("suppression_turns", 2)) + self.suppression_turn_bonus(),
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
            required_turns = int(card.get("required_turns", 2)) + self.suppression_turn_bonus()
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
                "required_turns": required_turns,
                "garrison_progress": {},
            }
            self.state.setdefault("city_output_effects", []).append(deepcopy(city_disruption))
            self._refresh_city_income()
            self._notify(
                target_owner,
                f"{card.get('name', card_id)}：{'、'.join(city['name'] for city in selected)} 產出歸零，"
                f"每城需連續駐紮至少 {required} 營 {required_turns} 回合才能恢復。",
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
        # 忠誠加減：算出新的 loyaltyOverrides（加在**基礎值**上），前端照抄就好。
        # 先前這一段在前端，而且拿畫面上的顯示值去加——顯示值含相對實力與戰損的
        # 修正，後端再套一次，於是「+2」在弱軍身上會縮成 +0，卡等於沒效果。
        loyalty_overrides = self.apply_loyalty_deltas(
            ([{"general_id": target_general_id, "amount": loyalty_delta}]
             if target_general_id and loyalty_delta else [])
            + ([dict(loyalty_delta_all)] if loyalty_delta_all else [])
            + [dict(swing) for swing in loyalty_swings])
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
            "loyalty_overrides": loyalty_overrides,
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
            "loyalty_overrides": loyalty_overrides,
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
        # 〈非戰公約〉通電支持者：停戰期內不得宣戰。旗標上的 blocks_declaration
        # 先前沒有任何讀取者，於是「不得宣戰」變成玩家自主遵守——這裡把它擋住。
        if status == "war":
            peace = self.active_timed_flag(player, "forced_peace") or {}
            if peace.get("blocks_declaration"):
                raise ValueError(f'{peace.get("name") or "強制和平"}：停戰期內不得宣戰'
                                 f'（尚餘 {int(peace.get("remaining_turns") or 0)} 回合）')
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

    def _oil_price_immune_cards(self, player: str) -> set:
        """這位玩家目前免疫哪幾張卡的生產加價。

        來源是 `oil_price_immunity` 這種限時效果（美孚石油供應）。
        效果本身只是個旗標——先前寫了旗標卻**沒有任何地方讀它**，
        於是那張卡打出去等於什麼都沒發生。
        """
        if player not in self.state["players"]:
            return set()
        out: set = set()
        for effect in self._player(player).get("timed_effects", []):
            if effect.get("kind") != "oil_price_immunity":
                continue
            remaining = effect.get("remaining_turns")
            if remaining is not None and int(remaining) <= 0:
                continue
            out |= {str(x) for x in (effect.get("immune_cards") or [])}
        return out

    def _production_multiplier(self, player: str, arm: str) -> Dict[str, float]:
        """生產成本乘數（英國軍火出口管制 +30%、美國禁運案 +50%、香港軍火交易 −30%）。

        多張同時生效就連乘。arm 是 "ground"（陸軍兵種）或 "navy"（砲艇／運輸船）。
        players 為 None 代表全場適用。
        """
        turn = int(self.state["turn"])
        cash, factory = 1.0, 1.0
        immune = self._oil_price_immune_cards(player)
        for entry in self.state.get("production_cost_multipliers", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            if arm not in (entry.get("arms") or ["ground", "navy"]):
                continue
            # 美孚石油供應：拿到穩定油源的人不吃〈國際油價上漲〉的加價。
            # 只擋加價（>1），不擋降價——免疫不該把便宜也一起免掉。
            if entry.get("card_id") in immune and (
                    float(entry.get("cash", 1)) > 1 or float(entry.get("factory", 1)) > 1):
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            cash *= float(entry.get("cash", 1))
            factory *= float(entry.get("factory", 1))
        return {"cash": cash, "factory": factory}

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
        # 「降為 N 元」是寫死的價格，不是折抵——一律蓋過其他加減。
        override = None
        for entry in player_state.get("timed_recruit_discounts", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            fixed = (entry.get("cash_override") or {}).get(unit_type)
            if fixed is not None:
                override = int(fixed) if override is None else min(override, int(fixed))
        adjustment = player_state.get("recruit_cost_adjustment", {}).get(unit_type, {})
        # 只在控制指定省份時才成立的折價（晏陽初辦學鄉村：控四省任一者步兵 −$1）。
        province = self._province_recruit_discount(player, unit_type)
        # 事件卡的成本乘數先乘在底價上，之後才加各種定額增減。
        multiplier = self._production_multiplier(player, "ground")
        cash = math.ceil(base["cash"] * player_state.get("recruitment_cost_modifier", 1)
                         * multiplier["cash"])
        cash = max(1, cash + int(adjustment.get("cash", 0)) + timed["cash"] + province["cash"])
        factory = max(0, math.ceil(int(base["factory"]) * multiplier["factory"])
                     + int(adjustment.get("factory", 0))
                     + timed["factory"] + province["factory"])
        if override is not None:
            cash = max(0, override)
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
        self._require_action(player, "train_unit")
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

    def _navy_unit_cost_for(self, player: str, unit_type: str) -> tuple[int, int]:
        """一艘船對這位玩家現在要多少錢。

        抽成函式是為了讓「實際扣款」與「面板顯示」讀同一份計算——
        先前這段內嵌在 train_navy_unit 裡，面板只好自己再算一次，
        於是生產成本倍率生效時兩邊就對不上了。
        """
        unit_cost = NAVY_RECRUIT_COSTS[unit_type]
        multiplier = self._production_multiplier(player, "navy")
        return (math.ceil(int(unit_cost["cash"]) * multiplier["cash"]),
                math.ceil(int(unit_cost["factory"]) * multiplier["factory"]))

    def train_navy_unit(self, player: str, unit_type: str, count: int = 1) -> Dict[str, Any]:
        self._require_action(player, "train_navy_unit")
        player_state = self._player(player)
        if unit_type not in NAVY_RECRUIT_COSTS:
            raise ValueError(f"unknown navy unit type: {unit_type!r}")
        count = int(count)
        if count < 1:
            raise ValueError("navy recruit count must be positive")
        unit_cash, unit_factory = self._navy_unit_cost_for(player, unit_type)
        cash_cost = unit_cash * count
        factory_cost = unit_factory * count
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
        self._require_action(player, "reinforce_navy")
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
        self._require_action(player, "reinforce_army")
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
        block = self._reinforce_block(player, city.get("province"))
        if block:
            raise ValueError(f"{block.get('label') or '事件'}：{city['province']}"
                             f"境內 {block['remaining_turns']} 回合內不可補充兵力")
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

    # ── 軍令收費帳本 ──────────────────────────────────────────────────
    #
    # 每一筆軍令扣款都在伺服器這邊記一筆，回傳 charge_id。撤銷軍令時前端只送
    # charge_id，退多少由帳本決定。先前是前端自己把 `factory_points` 加回去
    # （app.js 的 undo 路徑），金額還是前端當初自己算的那個數字——
    # 那是一條可以重複觸發的無限工業點路徑。

    def _next_charge_id(self, player: str) -> str:
        player_state = self._player(player)
        serial = int(player_state.get("next_charge_id", 1))
        player_state["next_charge_id"] = serial + 1
        return f"{player}-CHG{serial}"

    def _record_charge(self, player: str, kind: str, *, cash: int = 0, factory: int = 0,
                       ref: Optional[str] = None) -> str:
        player_state = self._player(player)
        charge_id = self._next_charge_id(player)
        player_state.setdefault("charges", {})[charge_id] = {
            "kind": kind, "cash": int(cash), "factory": int(factory), "ref": ref,
        }
        return charge_id

    def refund_charge(self, player: str, charge_id: str) -> Dict[str, Any]:
        """憑 charge_id 退款。退多少看帳本，不看前端說了什麼；同一筆只退得掉一次。"""
        player_state = self._player(player)
        charges = player_state.setdefault("charges", {})
        charge = charges.pop(str(charge_id), None)
        if charge is None:
            raise ValueError(f"找不到這筆軍令扣款（或已經退過）：{charge_id}")
        player_state["treasury"] = int(player_state.get("treasury", 0)) + int(charge["cash"])
        player_state["factory_points"] = (
            int(player_state.get("factory_points", 0)) + int(charge["factory"]))
        return {"charge_id": str(charge_id), "kind": charge["kind"],
                "cash": int(charge["cash"]), "factory": int(charge["factory"]),
                "state": self.snapshot()}

    def _charge(self, player: str, kind: str, *, cash: int = 0, factory: int = 0,
                ref: Optional[str] = None, cash_note: str = "", factory_note: str = "") -> str:
        player_state = self._player(player)
        cash, factory = max(0, int(cash)), max(0, int(factory))
        if int(player_state.get("treasury", 0)) < cash:
            raise ValueError(cash_note or f"{kind}需要 {cash} 現金")
        if int(player_state.get("factory_points", 0)) < factory:
            raise ValueError(factory_note or f"{kind}需要 {factory} 工業點")
        player_state["treasury"] = int(player_state.get("treasury", 0)) - cash
        player_state["factory_points"] = int(player_state.get("factory_points", 0)) - factory
        return self._record_charge(player, kind, cash=cash, factory=factory, ref=ref)

    # 急行軍改成按部隊購買的軍令：$10 + 10 工業點換該支部隊 3 回合的兩格移動。
    FORCED_MARCH_COST_CASH = 10
    FORCED_MARCH_COST_FACTORY = 10
    FORCED_MARCH_DURATION_TURNS = 3
    FORCED_MARCH_COOLDOWN_TURNS = 3
    FORCED_MARCH_TILES = 2

    def pay_forced_march(self, player: str, army_id: str = "") -> Dict[str, Any]:
        """急行軍收費。金額是這邊的常數，不收前端送來的數字。"""
        cash = int(self.FORCED_MARCH_COST_CASH)
        factory = int(self.FORCED_MARCH_COST_FACTORY)
        charge_id = self._charge(
            player, "forced_march", cash=cash, factory=factory, ref=str(army_id) or None,
            cash_note=f"急行軍需要 {cash} 現金", factory_note=f"急行軍需要 {factory} 工業點")
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
            "charge_id": charge_id,
            "army_id": str(army_id) if army_id else None,
            "duration_turns": self.FORCED_MARCH_DURATION_TURNS,
            "cooldown_turns": self.FORCED_MARCH_COOLDOWN_TURNS,
            "tiles": self.FORCED_MARCH_TILES,
            "state": self.snapshot(),
        }

    def navy_move_cost(self, navy: Optional[Dict[str, Any]] = None) -> int:
        """艦隊機動的工業點成本：每艘現存砲艇一份。

        先前是前端乘好再送上來，伺服器照單全收——而且兩邊規則根本不同：
        後端預設讀的是 move.factory_cost（一筆固定價），前端算的是每艘砲艇。
        規則只留這一份。
        """
        from navy_system.navy import normalize_division
        move_rules = self.data["navy_system"].get("move", {})
        per_gun_boat = move_rules.get("factory_cost_per_gun_boat")
        if per_gun_boat is None:
            return max(0, int(move_rules.get("factory_cost", 0)))
        if not navy:
            # 按砲艇計價卻沒送艦隊現況，就算不出成本。回 0 等於免費機動——
            # 少送一個欄位就白嫖的洞，寧可擋下來。
            raise ValueError("艦隊機動需要艦隊現況才能計算成本")
        normalize_division(navy, self.data["navy_system"])
        return max(0, len(navy.get("gunBoats") or []) * int(per_gun_boat))

    def pay_navy_move(self, player: str, *, navy: Optional[Dict[str, Any]] = None,
                      navy_id: Optional[str] = None) -> Dict[str, Any]:
        cost = self.navy_move_cost(navy)
        charge_id = self._charge(player, "navy_move", factory=cost, ref=navy_id,
                                 factory_note=f"艦隊機動需要 {cost} 工業點")
        self.state["last_action"] = {
            "type": "navy_move_order",
            "player": player,
            "factory": cost,
        }
        return {"factory": cost, "charge_id": charge_id, "state": self.snapshot()}

    # ── 工事：架設浮橋與構築要塞 ───────────────────────────────────────
    #
    # 成本與工期原本只存在前端（ENGINEERING_OPERATIONS），而且扣款完全在前端做，
    # **沒有任何 API 呼叫**——改一行 JS 就能把要塞變免費。規則搬到這裡。
    ENGINEERING_OPERATIONS = {
        "pontoon_bridge": {"label": "架設浮橋", "turns": 2, "factory_cost": 10},
        "fortress_builder": {"label": "構築要塞", "turns": 3, "factory_cost": 10},
    }

    def engineering_rules(self) -> Dict[str, Any]:
        return {key: dict(value) for key, value in self.ENGINEERING_OPERATIONS.items()}

    def pay_engineering(self, player: str, operation: str,
                        cell_key: Optional[str] = None) -> Dict[str, Any]:
        rule = self.ENGINEERING_OPERATIONS.get(str(operation))
        if not rule:
            raise ValueError(f"unknown engineering operation: {operation!r}")
        cost = int(rule["factory_cost"])
        charge_id = self._charge(
            player, f"engineering:{operation}", factory=cost, ref=cell_key,
            factory_note=f"{rule['label']}需要工業點 {cost}")
        self.state["last_action"] = {
            "type": "engineering_order",
            "player": player,
            "operation": str(operation),
            "cell_key": cell_key,
            "factory": cost,
        }
        return {"operation": str(operation), "label": rule["label"],
                "factory": cost, "turns": int(rule["turns"]),
                "charge_id": charge_id, "state": self.snapshot()}

    # ── 海戰：規則的單一來源 ────────────────────────────────────────────
    # 原本整套住在 frontend/navy.js，後端只收結果。現在由這裡結算，
    # 前端負責接收玩家指令、把結果畫出來、處理地圖上的位置與撤退格。

    def authorize_embark(self, navy: Dict[str, Any],
                         army_units: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """陸軍要上船，先問伺服器裝不裝得下。

        容量門檻原本只在前端擋（handleNavyOperation 裡的 forcePoints > navyCapacity），
        **沒有任何端點複驗**——海戰其他部分都搬走了，這條裝載門檻是漏網的。
        """
        from navy_system.navy import force_points, navy_capacity
        rules = self.data["navy_system"]
        capacity = navy_capacity(navy or {}, rules)
        force = force_points(army_units or {}, UNIT_FORCE_POINTS)
        if force <= 0:
            raise ValueError("這支部隊沒有可搭載的兵力")
        if force > capacity:
            raise ValueError(f"運輸船容量不足：目前容量 {capacity} 戰力點，"
                             f"這支部隊有 {force} 戰力點")
        return {"allowed": True, "capacity": capacity, "force": force, "navy": navy}

    def settle_navy_carried_army(self, navy: Dict[str, Any]) -> Dict[str, Any]:
        """海戰後船上陸軍的下場——裁兵或隨船覆沒——由這裡決定，不再由前端算。

        ``navy["carried"]`` 是前端送上來的載運現況 {armyId, generalId, units}。
        """
        from navy_system.navy import settle_carried_army as _settle
        return _settle(navy, (navy or {}).get("carried"), self.data["navy_system"],
                       self.random, UNIT_FORCE_POINTS)

    def resolve_navy_duel(self, attacker: Dict[str, Any],
                          defender: Dict[str, Any]) -> Dict[str, Any]:
        from navy_system.navy import resolve_navy_duel as _duel
        rules = self.data["navy_system"]
        result = _duel(attacker, defender, rules)
        return {"result": result, "attacker": attacker, "defender": defender,
                "attackerCarried": self.settle_navy_carried_army(attacker),
                "defenderCarried": self.settle_navy_carried_army(defender)}

    def resolve_army_navy_contact(self, army_units: Dict[str, Any],
                                  navy: Dict[str, Any]) -> Dict[str, Any]:
        from navy_system.navy import resolve_army_navy_contact as _contact
        rules = self.data["navy_system"]
        result = _contact(army_units, navy, rules)
        return {"result": result, "navy": navy,
                "carried": self.settle_navy_carried_army(navy)}

    def _navy_repair_port(self, city_id: Optional[str]) -> Dict[str, Any]:
        """艦艇能不能在這裡修。三道關全在後端，前端只是先擋一次給即時回饋。

        先前這三條只寫在 app.js（`harbor_only` 這個欄位甚至沒有任何讀取者），
        伺服器照單全收——直接打 /api/repair-navy 就能在任何地方免費修好。
        """
        rules = self.data["navy_system"].get("repair", {})
        if not rules.get("harbor_only"):
            return {}
        if not city_id:
            raise ValueError("艦艇只能在港口修理：請指明艦隊所在的城市")
        city = self._city_by_id(str(city_id))
        if not city or not city.get("port"):
            raise ValueError("艦艇只能在港口修理。")
        if any(effect.get("city_id") == str(city_id)
               for effect in self.state.get("port_effects", [])
               if int(effect.get("remaining_turns", 0)) > 0):
            raise ValueError(f'{city.get("name", city_id)}港務癱瘓中，不能修理艦艇。')
        floor = int(rules.get("min_port_level", 3))
        level = int(self._with_level(city).get("level", 0))
        if level < floor:
            raise ValueError(f'{city.get("name", city_id)}是 {level} 級小港，'
                             f'修理與編補艦隊要到 {floor} 級以上的港口。')
        return {"city_id": str(city_id), "level": level}

    def repair_navy(self, player: str, hp: int = 0, navy: Optional[Dict[str, Any]] = None,
                    target_hp: Optional[int] = None,
                    city_id: Optional[str] = None) -> Dict[str, Any]:
        """修理艦隊並收工業點。

        送 ``navy`` + ``target_hp`` 時，補了幾點由後端從艦隊現況算出來，並把修好的
        艦隊一起回傳。先前只收前端算好的 ``hp``：伺服器不知道艦隊長什麼樣，
        送 0 就是免費修，送大數就是花錢買不存在的血。
        """
        from navy_system.navy import restore_hp_to_floor
        player_state = self._player(player)
        self._navy_repair_port(city_id)
        repaired = None
        if navy is not None:
            if target_hp is None:
                raise ValueError("navy repair requires a target hp")
            hp = restore_hp_to_floor(navy, target_hp, self.data["navy_system"])
            repaired = navy
        hp = max(0, int(hp))
        cost_per_hp = int(self.data["navy_system"]["repair"]["factory_cost_per_hp"])
        cost = hp * cost_per_hp
        if hp <= 0:
            raise ValueError("所有現存艦艇都已達到該 HP，沒有需要修理的地方。")
        if int(player_state.get("factory_points", 0)) < cost:
            raise ValueError(f"艦艇修理需要 {cost} 工業點")
        player_state["factory_points"] = int(player_state.get("factory_points", 0)) - cost
        self.state["last_action"] = {
            "type": "navy_repair",
            "player": player,
            "hp": hp,
            "factory": cost,
        }
        return {"hp": hp, "factory": cost, "navy": repaired, "state": self.snapshot()}

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

    def police_shielded_provinces(self, owner: str, mechanic: str = "qing_gang_riot") -> set:
        """這位玩家有警政單位駐防、因此免疫黑幫事件的省份。"""
        out = set()
        for effect in self._player(owner).get("timed_effects", []):
            if effect.get("kind") != "gang_riot_shield":
                continue
            if int(effect.get("remaining_turns", 0)) <= 0:
                continue
            if mechanic not in (effect.get("blocked_mechanics") or []):
                continue
            if effect.get("province"):
                out.add(effect["province"])
        return out

    def _drop_police_shielded(self, owner: str, city_ids: Iterable[str]) -> list:
        """把有警政單位駐防的省份裡的城市剔掉。

        設計稿的「有警政單位保護者免疫」是逐省的——不是整個玩家免疫，
        也不是完全沒作用。這一條讓 14.2／14.5 真的吃得到那道護盾。
        """
        shielded = self.police_shielded_provinces(owner)
        if not shielded:
            return list(city_ids)
        return [cid for cid in city_ids
                if (self._city_by_id(cid) or {}).get("province") not in shielded]

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
        notify: bool = True,
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
        # 事件卡的暗殺是在**抽出當下**擲的，那時報紙還沒送到玩家眼前。
        # 這裡若照舊發通知，玩家會在讀報之前就從側欄知道結果，等於劇透。
        if notify and target_owner in self.state["players"]:
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

    def _tick_npc_combat_effects(self) -> None:
        """NPC 戰鬥修正的到期清理。

        兩種效期：
          * `remaining_turns` 走完（15.20／15.22／15.23 各 5 回合）；
          * `until_general_leaves`——沒有回合上限，掛到那位將領離場為止（15.2）。

        「離場」的判準用 `npc_situation()`，也就是**戰術快照**上的現況：
        陣亡、被殲、被俘、跳槽都算。將領樹是唯讀的靜態資料檔，裡面的 status
        永遠不會變，拿它來判離場等於這條效期永遠不會到期。
        """
        effects = self.state.get("npc_combat_effects") or []
        if not effects:
            return
        situation = self.npc_situation(self._tactical) if self._tactical else None
        alive: list = []
        for effect in effects:
            if effect.get("until_general_leaves"):
                general_id = effect.get("general_id")
                faction = effect.get("faction")
                # 沒有快照就無從判斷，這一輪先留著——寧可多留一回合，
                # 也不要因為前端還沒送狀態就把效果誤刪。
                if situation and situation.get("available") and general_id and faction:
                    here = (situation["factions"].get(faction) or {}).get("generals") or []
                    if general_id not in here:
                        continue
            if effect.get("remaining_turns") is not None:
                # 抽到的那一回合不倒數，否則 5 回合的效果只會活 4 回合。
                if effect.pop("granted_this_turn", None):
                    alive.append(effect)
                    continue
                remaining = int(effect["remaining_turns"]) - 1
                if remaining <= 0:
                    continue
                effect["remaining_turns"] = remaining
            else:
                effect.pop("granted_this_turn", None)
            alive.append(effect)
        self.state["npc_combat_effects"] = alive

    @staticmethod
    def _railway_effect_active(effect: Dict[str, Any]) -> bool:
        """這條封路現在還算不算數。

        `remaining_turns` 是 None 代表**無限期**（15.1 閻錫山封鎖窄軌鐵路：
        沒有回合上限，也修不好，解除條件是他本人被俘）。不能拿 None 去 int()。
        """
        remaining = effect.get("remaining_turns")
        if remaining is None:
            return True
        return int(remaining) > 0

    def _tick_railway_effects(self) -> None:
        active = []
        for effect in self.state.get("railway_effects", []):
            if effect.get("permanent"):
                # 無限期封路。解除條件不是時間，是指定將領離場。
                gate = effect.get("until_general_leaves") or {}
                if gate and not self._npc_general_still_here(
                        gate.get("general"), gate.get("faction")):
                    self._notify_all(f'{effect.get("name")}：{gate.get("general")}已不在場，'
                                     f'{effect.get("railway")}恢復通行。')
                    continue
                active.append(effect)
                continue
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

    def banned_railways(self, player: str) -> list:
        """這位玩家目前不得使用的鐵路（交涉破裂的路權封鎖）。

        與 disabled_railways() 不同：那是全場停運（崩鐵／爆破），
        這裡是只罰一家的路權封鎖，別人照走。
        """
        turn = int(self.state["turn"])
        return sorted({entry["railway"] for entry in self.state.get("railway_bans", [])
                       if entry.get("player") == player
                       and turn < int(entry.get("until_turn", 0))})

    def disabled_railways(self) -> list:
        """搶修中的鐵路名稱，前端據此關閉該線的鐵路運輸。"""
        return [
            str(effect.get("railway"))
            for effect in self.state.get("railway_effects", [])
            if self._railway_effect_active(effect)
        ]

    def foreign_railways(self) -> Dict[str, str]:
        """列強鐵路 → 該國的關係鍵。

        資料出自 scenario/data/strategic_map.json：標了 foreign 的線必須同時
        寫明 power。這裡不在程式碼裡另寫一份對照表——寫了就是第二份真源，
        遲早跟地圖對不上。
        """
        out: Dict[str, str] = {}
        for line in self.data["strategic_map"].get("railroads", []):
            if not line.get("foreign"):
                continue
            name = str(line.get("name") or "").strip()
            power = str(line.get("power") or "").strip()
            if not name:
                raise ValueError("strategic_map 裡有一條沒有名字的鐵路")
            if not power:
                raise ValueError(f"{name} 標了 foreign 卻沒有寫 power")
            if power not in RELATION_KEYS:
                raise ValueError(f"{name} 的 power「{power}」不是有效的關係鍵")
            out[name] = power
        return out

    def locked_foreign_railways(self, player: str) -> list:
        """關係沒到友好門檻，人家就不讓你用他的線調兵。

        門檻是 FOREIGN_FRIENDLY_THRESHOLD，與 perk 卡、優惠借貸同一個切點，
        全都由 foreign_powers.json 的 friendly_at_or_above 導出。
        """
        profile = self.state.get("players", {}).get(player) or {}
        relations = profile.get("foreign_relations") or {}
        return sorted(
            name for name, power in self.foreign_railways().items()
            if int(relations.get(power, 0)) < FOREIGN_FRIENDLY_THRESHOLD
        )

    def unusable_railways(self, player: str) -> list:
        """這位玩家現在做不了鐵路運輸的線：搶修中 ∪ 路權被封 ∪ 關係不到。

        沿線地格仍可當普通地格走過去——不能走的是「一次三格」的鐵路運輸。
        """
        return sorted(set(self.disabled_railways())
                      | set(self.banned_railways(player))
                      | set(self.locked_foreign_railways(player)))

    def railway_access(self) -> Dict[str, Any]:
        """鐵路可用性的完整判定結果，前端照著畫就好，不必自己算門檻。"""
        foreign = self.foreign_railways()
        disabled = sorted(set(self.disabled_railways()))
        by_player: Dict[str, Any] = {}
        for code, profile in (self.state.get("players") or {}).items():
            relations = (profile or {}).get("foreign_relations") or {}
            locked = self.locked_foreign_railways(code)
            by_player[code] = {
                "locked": locked,
                "banned": self.banned_railways(code),
                "unusable": self.unusable_railways(code),
                "relations": {name: int(relations.get(power, 0))
                              for name, power in foreign.items()},
            }
        return {
            "friendly_threshold": FOREIGN_FRIENDLY_THRESHOLD,
            "hostile_threshold": FOREIGN_HOSTILE_THRESHOLD,
            "foreign_railways": foreign,
            "disabled": disabled,
            "by_player": by_player,
        }

    # 可以被 action_ban 禁掉的行動。寫死成清單是刻意的——卡片打錯字會當場報錯，
    # 而不是安靜地禁了一個不存在的行動（那就等於沒禁）。
    BANNABLE_ACTIONS = {"train_unit", "train_navy_unit", "reinforce_army", "reinforce_navy"}

    def action_banned(self, player: str, action: str) -> Optional[Dict[str, Any]]:
        """這位玩家現在能不能做這件事；回傳擋下它的那一筆，沒有就是 None。"""
        turn = int(self.state["turn"])
        for entry in self.state.get("action_bans", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            if action not in (entry.get("actions") or []):
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            return entry
        return None

    def _require_action(self, player: str, action: str) -> None:
        entry = self.action_banned(player, action)
        if entry:
            raise ValueError(f'{entry.get("label") or "事件效果"}：本回合不可'
                             f'{self.ACTION_NAMES.get(action, action)}，'
                             f'需等到第 {int(entry["until_turn"])} 回合')

    ACTION_NAMES = {"train_unit": "訓練部隊", "train_navy_unit": "造船",
                    "reinforce_army": "補充兵力", "reinforce_navy": "補充艦隊"}

    def active_timed_flag(self, player: str, kind: str) -> Optional[Dict[str, Any]]:
        """回傳這位玩家身上還生效中的該類旗標本身（沒有就回 None）。

        `has_timed_flag` 只答有沒有；但像〈非戰公約〉的強制和平，旗標上還帶著
        `blocks_declaration` 這種**參數**，判斷的人得拿得到旗標本體才讀得到。
        """
        for effect in self._player(player).get("timed_effects", []):
            if effect.get("kind") != kind:
                continue
            if effect.get("permanent") or effect.get("remaining_turns") is None:
                return effect
            if int(effect.get("remaining_turns", 0)) > 0:
                return effect
        return None

    def has_timed_flag(self, player: str, kind: str) -> bool:
        """這位玩家身上有沒有某個還生效中的旗標（permanent 的永遠算數）。"""
        turn = int(self.state["turn"])
        for effect in self._player(player).get("timed_effects", []):
            if effect.get("kind") != kind:
                continue
            if effect.get("permanent") or effect.get("remaining_turns") is None:
                return True
            if int(effect.get("remaining_turns", 0)) > 0:
                return True
        return False

    def _treasury_at_last_turn_end(self, player: str) -> int:
        """上一回合結算完之後，這位玩家手上有多少現金。

        turn_log 每回合結束時記一筆；還沒有任何一筆（第一回合）就退回現值。
        """
        for entry in reversed(self.state.get("turn_log") or []):
            snapshot = (entry.get("treasury_after") or {})
            if player in snapshot:
                return int(snapshot[player])
        return int(self._player(player).get("treasury", 0))

    def _output_multiplier(self, player: str) -> Dict[str, float]:
        """這位玩家這回合的產出乘數，多張同時生效就連乘。"""
        turn = int(self.state["turn"])
        cash, factory = 1.0, 1.0
        for entry in self._player(player).get("output_multipliers", []):
            if turn >= int(entry.get("until_turn", 0)):
                continue
            cash *= float(entry.get("cash", 1))
            factory *= float(entry.get("factory", 1))
        return {"cash": cash, "factory": factory}

    def _adjusted_city_output(self, city_id: str, cash: int, factory: int) -> tuple[int, int]:
        adjusted_cash = int(cash)
        adjusted_factory = int(factory)
        for effect in self.state.get("city_output_effects", []):
            if effect.get("kind") in ("qing_gang_riot", "red_army_uprising"):
                if city_id in effect.get("city_ids", []):
                    adjusted_cash = 0
                    adjusted_factory = 0
                continue
            if city_id not in effect.get("city_ids", []):
                continue
            # None＝無限期，仍在生效；有數字才看剩幾回合。
            if effect.get("remaining_turns") is not None \
                    and int(effect["remaining_turns"]) <= 0:
                continue
            adjusted_cash = int(round(adjusted_cash * float(effect.get("cash_multiplier", 1))))
            adjusted_factory = int(round(adjusted_factory * float(effect.get("factory_multiplier", 1))))
            # 定額增減（煤礦短缺的工廠 −2）排在乘數之後：先打折再扣固定值。
            adjusted_cash += int(effect.get("cash_delta", 0))
            adjusted_factory += int(effect.get("factory_delta", 0))
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

    # 買辦擋懲戒：連續被擋這麼多次就直接實施，防止死循環。
    # 實務上碰不到（連 10 次 30% 全中約萬分之一），但卡住回合是絕對不能接受的。
    COMPRADOR_MAX_REDRAWS = 10

    def comprador_immunity(self, player: str, power: str) -> float:
        """這位玩家對這一國的懲戒有多少機率免疫（沒有買辦就是 0）。"""
        for trait, rule in COMPRADOR_TRAITS.items():
            if rule["power"] != power:
                continue
            if self._faction_has_trait(player, trait):
                return float(rule.get("immunity", 0))
        return 0.0

    def _comprador_deflects(self, card: Dict[str, Any], drawer: str) -> bool:
        """這張卡是不是被買辦擋下了。

        只對「該國的 [懲戒] 事件卡」生效——不是所有事件卡，也不是功能卡。
        判準是卡片自己的 tags 與 power_note，所以日後任何一張新的 [懲戒] 卡
        都自動吃得到，不必回頭改這裡。
        """
        if "懲戒" not in (card.get("tags") or []):
            return False
        # power_note 允許寫成「蘇／德」這種複數（既有的 _event_powers 就這樣解）。
        # 先前直接拿整串去查表，複合寫法一律查不到 → 永遠擋不下來。
        notes = [part.strip() for part in
                 re.split(r"[／/、,]", str(card.get("power_note") or "")) if part.strip()]
        chance = max((self.comprador_immunity(drawer, POWER_BY_NAME[note])
                      for note in notes if note in POWER_BY_NAME), default=0.0)
        return bool(chance) and self.random.random() < chance

    def _perk_copies(self, card_id: str, player: Optional[str] = None) -> int:
        base = FOREIGN_PERK_CARD_COPIES_BY_ID.get(card_id, FOREIGN_PERK_CARD_COPIES)
        if player is None:
            return base
        # 周恩來與地下黨這類卡片會把某幾張友好卡的份數往上抬，只對打出者生效。
        bumped = self._player(player).get("perk_copy_overrides", {}).get(card_id)
        total = max(base, int(bumped)) if bumped is not None else base
        # 事件卡給的**有時效**加張（2.2 柏林密約：10 回合內蘇聯 perk 卡各 +2）。
        # 這必須算在 desired 裡，不能像 card_copies 那樣直接往牌庫塞——
        # _sync_foreign_deck_cards 每次都會把份數修回 desired，塞進去的當場就被收走。
        return total + self._perk_copy_bonus(card_id, player)

    def _perk_copy_bonus(self, card_id: str, player: str) -> int:
        turn = int(self.state["turn"])
        bonus = 0
        for entry in self.state.get("perk_copy_bonuses", []):
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            players = entry.get("players")
            if players and player not in players:
                continue
            if card_id not in (entry.get("cards") or []):
                continue
            bonus += int(entry.get("copies", 0))
        return bonus

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

    def disabled_traits(self, player: str) -> list:
        """這位玩家名下有哪些技能因為列強關係而失效。

        判準表在 backend/combat_modifiers.RELATION_DISABLED_TRAITS，只有一份。
        先前前端另外抄了一份表、自己拿關係去比——畫面說失效、戰鬥算沒失效
        （或反過來）都不會有任何東西叫。現在畫面讀這一份。
        """
        from .combat_modifiers import RELATION_DISABLED_TRAITS
        return sorted(trait for trait, rule in RELATION_DISABLED_TRAITS.items()
                      if self._trait_relation_disabled(player, rule))

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

    # 「買的是這位將領的部隊」的卡：人走了效果就沒了，也不隨他過去。
    # 哪些卡算數由卡片自己的 lost_on_defection 決定（先前是寫死一個 tuple，
    # 於是卡片上那個欄位沒有任何讀取者——第三張同類卡只加欄位就會靜靜失效）。
    # 這張表只負責「這個 mechanic 把將領記在哪個名單上」。
    PERK_ROSTER_BY_MECHANIC = {
        "mechanized_division": "permanent_forced_march_generals",
        "field_hospital": "field_hospital_generals",
    }

    @property
    def GENERAL_BOUND_PERK_KEYS(self) -> tuple:
        keys = []
        for card in self.data["function_cards"]["cards"]:
            if not card.get("lost_on_defection"):
                continue
            roster = self.PERK_ROSTER_BY_MECHANIC.get(card.get("mechanic"))
            if roster is None:
                raise ValueError(
                    f'{card.get("id")} 標了 lost_on_defection，'
                    f'但 PERK_ROSTER_BY_MECHANIC 沒有 {card.get("mechanic")} 的名單')
            if roster not in keys:
                keys.append(roster)
        return tuple(keys)

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

        compradors = []
        for trait in traits:
            rule = COMPRADOR_TRAITS.get(trait)
            if not rule:
                continue
            power = rule["power"]
            # 免疫不再預先擲、也不再記帳——改成每次抽到該國 [懲戒] 時當場擲，
            # 所以換東家不必清任何紀錄，技能跟著將領走就是了。
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

    def _priority_group_rule(self) -> Dict[str, Any]:
        """NPC 卡優先的抽卡節奏。節奏本身寫在資料檔，不寫死在這裡。"""
        rule = (self._event_rules().get("priority_group") or {})
        if not rule.get("ref_prefix"):
            return {}
        return rule

    def is_priority_event(self, card_id: str) -> bool:
        """這張卡屬不屬於優先抽的那一組（第 15 區塊的 NPC 行動卡）。"""
        rule = self._priority_group_rule()
        if not rule:
            return False
        ref = str((self._event_template(card_id) or {}).get("ref") or "")
        return ref.startswith(str(rule["ref_prefix"]))

    def _priority_slot(self, draw_index: int) -> bool:
        """第 draw_index 張（從 0 起算）該不該優先抽 NPC 卡。

        節奏是「draws 張優先 + then_ordinary 張一般」循環：預設 3 NPC → 1 一般。
        序號照抽出的張數走，所以就算某一次因為沒有合格的 NPC 卡而退回抽一般卡，
        之後的順序也不會錯位。
        """
        rule = self._priority_group_rule()
        if not rule:
            return False
        priority = max(0, int(rule.get("draws", 0)))
        ordinary = max(0, int(rule.get("then_ordinary", 0)))
        period = priority + ordinary
        if priority <= 0 or period <= 0:
            return False
        return (int(draw_index) % period) < priority

    def _pick_by_priority(self, eligible: list, draw_index: int) -> list:
        """把合格清單依這一格該抽的組別排序：想要的那一組排前面。

        兩組都空不會發生（呼叫端已經確認 eligible 非空）；想要的那一組空了就
        退回另一組，寧可抽一張一般卡，也不要讓事件週期停擺。
        """
        if not self._priority_group_rule():
            return eligible
        want_priority = self._priority_slot(draw_index)
        wanted = [cid for cid in eligible if self.is_priority_event(cid) == want_priority]
        return wanted or eligible

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
        deflected = 0
        # 重抽不佔用「本輪要抽幾張」的額度，但總次數有上限（見 COMPRADOR_MAX_REDRAWS）。
        for index in range(count + self.COMPRADOR_MAX_REDRAWS):
            if len(drawn) >= count:
                break
            # 有進入條件的卡（要控制某省、某城）只有符合的人抽得到；沒人符合就先跳過，
            # 留在池子裡等局勢變了再說。
            # 被 event_locks 封鎖的卡同樣抽不到，但**不會**離開 pool——這是封鎖與移除的差別。
            # already 擋掉同一輪重複抽到同一張（池子裡可以有同名多張，用來加抽中機會）。
            eligible = [
                card_id for card_id in pool
                if card_id not in already
                # never_drawn 只在開局配池時擋過一次。任何把卡塞進 event_pool 的
                # 路徑（2.4 東方會議的標籤加張）都能繞過那道防線，所以這裡再擋一次：
                # 這種卡只能由機制直接插進 pending，永遠不該被抽出來。
                and not (self._event_template(card_id) or {}).get("never_drawn")
                # not_in_pool 同理：機制還沒補齊的卡就算被塞進池子也不准抽出來，
                # 否則玩家會收到一張什麼都不會發生的報紙。
                and not (self._event_template(card_id) or {}).get("not_in_pool")
                and not self.event_is_spent(card_id)
                and not self._event_locked(card_id)
                and self._event_eligible_players(self._event_template(card_id))
            ]
            if not eligible:
                break
            # NPC 卡優先：第 N 張該抽哪一組由 _priority_slot 決定，
            # 序號是「已經抽出去幾張」，不是這一輪的第幾次嘗試——
            # 被買辦壓下的重抽不佔序號，否則節奏會被躲掉的卡帶偏。
            eligible = self._pick_by_priority(
                eligible, int(self.state.get("event_draw_index", 0)))
            card_id = eligible[self.random.randrange(len(eligible))]
            card = self._event_template(card_id)
            qualified = self._event_eligible_players(card)
            drawer = qualified[self.random.randrange(len(qualified))]
            # 買辦技能：唐繼堯（法 30%）、張宗昌（日 10%）在自家挨上該國的
            # [懲戒] 時有機率把它壓下來。壓下來就**靜默重抽**——玩家不會知道
            # 剛剛躲過什麼。被壓下的卡留在池子裡（不是永久免疫，下回合還會來），
            # 只在這一輪加進 already，免得同一輪對同一張反覆擲骰。
            if self._comprador_deflects(card, drawer):
                # 這一次不算數，但也不能無止盡重抽——連續被擋滿 N 次就直接實施。
                deflected += 1
                if deflected < self.COMPRADOR_MAX_REDRAWS:
                    already.add(card_id)
                    self.state.setdefault("comprador_deflections", []).append({
                        "turn": int(self.state["turn"]), "card_id": card_id,
                        "owner": drawer, "power": str(card.get("power_note") or ""),
                    })
                    continue
                # 擋滿上限：這張照樣降臨，所以**不能**記成被擋下——
                # 先前記了，查帳時會看到一張「既被擋下又降臨」的卡。
                self.state.setdefault("comprador_deflection_overrides", []).append({
                    "turn": int(self.state["turn"]), "card_id": card_id, "owner": drawer,
                    "note": "連續擋滿上限，本張直接實施",
                })
            pool.remove(card_id)
            already.add(card_id)
            responders = self._event_responder_queue(card, drawer)
            entry = {"card_id": card_id, "drawer": drawer,
                     "responders": responders, "responses": {}}
            # 有 random_outcome 的卡（11.5 廢兩改元）在**抽出當下**就擲骰，
            # 結果存在 pending 上：報紙要刊的是「已經發生的事」，
            # 不能等玩家讀完才決定成或不成。結算時直接沿用這一次的結果，不再擲第二次。
            pre = self._preroll_random_outcome(card)
            if pre is not None:
                entry["random_outcome"] = pre
            # 暗殺同理：報紙上要寫這一次得手沒有，所以骰子必須在抽出當下就擲。
            shot = self._preroll_assassination(card, drawer)
            if shot is not None:
                entry["assassination"] = shot
            drawn.append(entry)
            self.state["event_draw_index"] = int(self.state.get("event_draw_index", 0)) + 1
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

    @staticmethod
    def _pick_random_branch(roll_spec: Dict[str, Any], roll: float):
        """依累積機率挑一支；掉出範圍就取最後一支（機率沒加滿到 1 時的保底）。"""
        cumulative = 0.0
        for branch in roll_spec.get("branches") or []:
            cumulative += float(branch.get("chance", 0))
            if roll < cumulative:
                return branch
        branches = roll_spec.get("branches") or []
        return branches[-1] if branches else None

    def _preroll_random_outcome(self, card: Dict[str, Any]):
        """抽出當下先擲骰，好讓報紙刊出對應的那一版。沒有 random_outcome 就回 None。"""
        spec = (card.get("apply") or {}).get("random_outcome")
        if not spec:
            return None
        roll = self.random.random()
        chosen = self._pick_random_branch(spec, roll)
        if not chosen:
            return None
        return {"roll": round(roll, 4), "chosen": chosen.get("id"),
                "newspaper_index": int(chosen.get("newspaper_index", 0)),
                # 報紙的效果欄要把擲出的那一支標紅，靠這個字串比對。
                "effect_marker": chosen.get("effect_marker")}

    def _reinforce_block(self, player: str, province) -> Optional[Dict[str, Any]]:
        """這位玩家在這一省是不是被禁止補充兵力（法國教案抗議那一類）。"""
        for entry in self._player(player).get("timed_effects", []):
            if entry.get("kind") != "reinforce_block":
                continue
            if int(entry.get("remaining_turns") or 0) <= 0:
                continue
            provinces = entry.get("provinces") or []
            if not provinces or province in provinces:
                return entry
        return None

    def _infantry_levy_cost(self, player: str, count: int) -> Dict[str, int]:
        """按「每個租界一個步兵營」計價的一次性軍費。"""
        cash, factory = self._unit_cost_for(player, "infantry")
        return {"cash": cash * count, "factory": factory * count}

    def _select_cities(self, select, players) -> list:
        """依條件挑城市。給 city_output／city_output_once 共用。

        支援：port（所有港市）、port_types（限河港或海港）、min_level（城市等級
        下限）、waters（貼著哪片水系，與封鎖引擎同一份名單）、concession（所有租界
        城市）、concession_of（指定列強的租界）、provinces（指定省份）、
        owned_by_target（只算 targets 手上的）。
        沒給條件就回空清單；只給 owned_by_target 就是「那位玩家的所有城市」。

        未知的鍵一律**不**當成篩選條件——寫錯鍵名會讓範圍變大而不是變小，
        所以下面把認得的鍵列出來，遇到不認得的就直接拋錯，別讓它默默放行。
        """
        known = {"port", "port_types", "min_level", "max_level", "concession",
                 "concession_of", "concession_of_any", "provinces",
                 "owned_by_target", "waters", "largest", "random"}
        unknown = set(select or {}) - known
        if unknown:
            raise ValueError(f"_select_cities 不認得的條件：{sorted(unknown)}")
        if not select:
            return []
        out = []
        owners = set(players or [])
        for city in self.data["strategic_map"]["cities"]:
            if select.get("port") and not city.get("port"):
                continue
            # port_types：["river"] 只要河港、["sea"] 只要海港；不給就河海通吃。
            port_types = select.get("port_types")
            if port_types and city.get("port") not in port_types:
                continue
            # min_level／max_level：城市等級上下限（13.11 的「三級以上」、
            # 14.11 瘟疫流行的「四級與五級」）。
            if select.get("min_level") is not None \
                    and int(city.get("level", 0)) < int(select["min_level"]):
                continue
            if select.get("max_level") is not None \
                    and int(city.get("level", 0)) > int(select["max_level"]):
                continue
            if select.get("concession") and not city.get("concession"):
                continue
            power = select.get("concession_of")
            if power and power not in (city.get("concession") or []):
                continue
            # 「含英租界**或**日租界」：任一命中即可。
            any_powers = select.get("concession_of_any") or []
            if any_powers and not (set(any_powers) & set(city.get("concession") or [])):
                continue
            # waters：貼著哪片水系（長江／黃河／珠江）。名單與封鎖引擎共用一份，
            # 免得「長江河港」在兩個機制裡是兩種定義。
            waters = select.get("waters")
            if waters and not (set(waters_for_city(city)) & set(waters)):
                continue
            provinces = select.get("provinces")
            if provinces and city.get("province") not in provinces:
                continue
            if select.get("owned_by_target"):
                owner = self.state["city_owners"].get(city["id"], city["faction"])
                if owner not in owners:
                    continue
            out.append(city["id"])
        # largest：規模最大（$ ＋ 工廠）的前 N 座。規模用**目前**的產出算，
        # 不是卡面基準值——被暴動壓著的城不該還算成大城。平手時隨機挑，
        # 所以排序的 key 帶一個亂數位；同一個 seed 可重現。
        largest = select.get("largest")
        if largest is not None:
            scored = []
            for city_id in out:
                cash, factory = self._current_city_output(city_id)
                scored.append((-(cash + factory), self.random.random(), city_id))
            scored.sort()
            out = [city_id for _, _, city_id in scored[:int(largest)]]
        # random：從符合條件的城裡隨機抽 N 座。
        count = select.get("random")
        if count is not None:
            count = min(int(count), len(out))
            picks = self.random.sample(range(len(out)), count) if count else []
            out = [out[i] for i in sorted(picks)]
        return out

    # 地格資訊欄要顯示的城市癱瘓標籤。哪一種、進度多少全由後端算，
    # 前端只負責排版——先前前端根本沒有這一欄，玩家看不出這座城為什麼沒有產出。
    DISRUPTION_LABELS = {
        "qing_gang_riot": "黑幫暴動",
        "red_army_uprising": "紅軍起義",
        "communist_riot": "共黨暴動",
        "city_halt": "產出受阻",
        "city_output_timed": "產出受阻",
    }

    def intel_report(self, observer: str) -> Dict[str, Any]:
        """偵查規則：這位觀察者這回合看得到哪些省、誰擋得住。

        三條規則的優先序全在這裡：
          1. 空中偵查（德國飛艇）照相片，情報局擋不住；
          2. 情報局（counter_intel）擋得住一般情報網；
          3. 情報網（intel_network）揭露指定的省。
        「這支部隊在哪一省」是地圖的事，留在前端；規則不留第二份。
        """
        return {
            "aerial_provinces": sorted({
                str(province)
                for effect in self._player(observer).get("timed_effects", [])
                if effect.get("kind") == "aerial_recon"
                and int(effect.get("remaining_turns", 0)) > 0
                for province in (effect.get("target_provinces") or [])
            }),
            "intel_provinces": sorted({
                str(effect.get("target_province"))
                for effect in self._player(observer).get("timed_effects", [])
                if effect.get("kind") == "intel_network"
                and int(effect.get("remaining_turns", 0)) > 0
                and effect.get("target_province")
            }),
            "counter_intel_factions": sorted({
                code for code in self.state["players"]
                if self.has_timed_flag(code, "counter_intel")
            }),
        }

    def city_disruption_report(self) -> Dict[str, list]:
        """城市 id → 目前壓在它頭上的癱瘓效果清單（含進度）。

        兩種進度：
          garrison —— 要駐軍才平息（黑幫暴動、紅軍起義），回報 progress/required。
          timed    —— 到期自動解除（共黨暴動、各種停產），回報 elapsed/total。
        """
        report: Dict[str, list] = {}
        for effect in self.state.get("city_output_effects", []):
            kind = str(effect.get("kind") or "city_halt")
            label = str(effect.get("label") or self.DISRUPTION_LABELS.get(kind)
                        or effect.get("name") or "產出受阻")
            required_turns = effect.get("required_turns")
            for city_id in (effect.get("city_ids") or []):
                entry = {
                    "id": effect.get("id"),
                    "kind": kind,
                    "label": label,
                    "name": effect.get("name"),
                    "cash_multiplier": float(effect.get("cash_multiplier", 0)),
                    "factory_multiplier": float(effect.get("factory_multiplier", 0)),
                }
                if required_turns is not None:
                    progress = effect.get("garrison_progress")
                    # 黑幫暴動整省一個計數；紅軍起義是逐城計數。
                    if isinstance(progress, dict):
                        progress = progress.get(city_id, 0)
                    entry.update({
                        "mode": "garrison",
                        "progress": int(progress or 0),
                        "required_turns": int(required_turns),
                        "required_force": effect.get("required_force"),
                        "required_battalions": effect.get("required_battalions"),
                    })
                else:
                    remaining = effect.get("remaining_turns")
                    total = effect.get("total_turns")
                    entry.update({
                        "mode": "timed",
                        "remaining_turns": None if remaining is None else int(remaining),
                        "total_turns": None if total is None else int(total),
                        "elapsed_turns": (None if remaining is None or total is None
                                          else max(0, int(total) - int(remaining))),
                    })
                report.setdefault(str(city_id), []).append(entry)
        return report

    def quellable_unrest(self, player: str) -> list:
        """這位玩家現在可以花錢平息的事件（前端要據此畫按鈕）。"""
        out = []
        for effect in self.state.get("city_output_effects", []):
            if effect.get("owner") != player or effect.get("quell_cost") is None:
                continue
            # 沒有 id 的效果沒辦法被鎮壓（quell_unrest 是靠 id 找的），直接跳過。
            # 先前這裡是 effect["id"]，一筆缺欄位的效果就會讓 snapshot() 整個拋
            # KeyError——而 snapshot() 幾乎每個 API 都會呼叫，等於整台伺服器停擺。
            if not effect.get("id"):
                continue
            out.append({
                "id": effect["id"],
                "name": effect.get("name"),
                "cost": int(effect["quell_cost"]),
                "cities": [(self._city_by_id(cid) or {}).get("name", cid)
                           for cid in effect.get("city_ids", [])],
                "city_ids": list(effect.get("city_ids", [])),
                "remaining_turns": effect.get("remaining_turns"),
                "affordable": int(self._player(player).get("treasury", 0)) >= int(effect["quell_cost"]),
            })
        return out

    def quell_unrest(self, player: str, effect_id: str) -> Dict[str, Any]:
        """付錢提前平息一起可平息的事件。

        錢不夠就擋下來——這是規則，不是提示；不能讓前端「先扣了再說」。
        """
        target = None
        for effect in self.state.get("city_output_effects", []):
            if effect.get("id") == effect_id and effect.get("owner") == player:
                target = effect
                break
        if target is None:
            raise ValueError("找不到這一起可平息的事件")
        if target.get("quell_cost") is None:
            raise ValueError(f'{target.get("name")} 不能用錢平息')
        cost = int(target["quell_cost"])
        profile = self._player(player)
        if int(profile.get("treasury", 0)) < cost:
            raise ValueError(f'平息{target.get("name")}要 ${cost}，你只有 ${int(profile.get("treasury", 0))}')
        profile["treasury"] = int(profile["treasury"]) - cost
        self.state["city_output_effects"] = [
            e for e in self.state.get("city_output_effects", []) if e is not target]
        self._refresh_city_income()
        cities = [(self._city_by_id(cid) or {}).get("name", cid)
                  for cid in target.get("city_ids", [])]
        self._notify(player, f'已支付 ${cost} 平息{target.get("name")}，'
                             f'{"、".join(cities)} 恢復產出。')
        return {"quelled": {"id": effect_id, "name": target.get("name"),
                            "cost": cost, "cities": cities},
                "state": self.snapshot()}

    def _current_city_output(self, city_id: str) -> tuple[int, int]:
        """這座城此刻的 ($ , 工廠)——含開發加成與生效中的減產／停產。"""
        city = self._city_by_id(city_id) or {}
        if not city:
            return (0, 0)
        development = (self.state.get("city_development", {}) or {}).get(city_id, {})
        return self._adjusted_city_output(
            city_id,
            scaled_city_value(self._with_level(city), "cash") + int(development.get("cash", 0)),
            scaled_city_value(self._with_level(city), "factory") + int(development.get("factory", 0)),
        )

    def _open_event_riot(self, owner: str, spec, card) -> Dict[str, Any]:
        """事件卡引發的暴動：挑幾座該玩家的城市停產，直到派兵平息。

        走的是與功能卡完全相同的 city_output_effects 結構，差別只在
        「誰引發的」——這裡沒有發動者，是列強／共產國際。
        """
        owned = [row["id"] for row in self._player(owner).get("city_economy", [])]
        # 「有警政單位保護者免疫」是逐省的（14.2 黑幫動亂）——先把有護盾的
        # 省份剔掉再抽，不然抽中了才發現免疫，等於這張卡對他少了一次機會。
        spared = []
        if spec.get("respect_police"):
            kept = self._drop_police_shielded(owner, owned)
            spared = sorted(set(owned) - set(kept))
            owned = kept
            if not owned:
                return {"skipped": "police_shielded", "spared": spared}
        if spec.get("scope") == "all_provinces":
            picks = owned
        else:
            count = min(int(spec.get("cities", 2)), len(owned))
            picks = [owned[i] for i in self.random.sample(range(len(owned)), count)] if count else []
        if not picks:
            return {"skipped": "no_cities", "spared": spared}
        effect = {
            "id": f"{card.get('id')}:{self.state['turn']}:{owner}",
            "card_id": card.get("id"),
            "name": card.get("name", card.get("id")),
            "kind": str(spec.get("kind", "red_army_uprising")),
            "owner": owner,
            "city_ids": list(picks),
            "required_battalions": int(spec.get("required_battalions", 5)),
            "required_force": int(spec.get("required_force", 15)),
            # 平息門檻的欄位名只能有一個。先前這裡寫的是 suppression_turns，
            # 而判平息的兩處（_update_qing_gang_riots、紅軍起義的駐紮結算）
            # 讀的都是 required_turns——於是〈黑幫動亂〉卡上的 required_turns
            # 從來沒被讀過，一律吃預設值。
            "required_turns": int(self._extended_duration(
                card, spec.get("required_turns", spec.get("suppression_turns")), 2)),
            "remaining_turns": None,
        }
        self.state.setdefault("city_output_effects", []).append(deepcopy(effect))
        self._refresh_city_income()
        self._notify(owner, f"{card.get('name')}：{len(picks)} 座城市發生暴動，產出歸零，需派兵平息。")
        if spared:
            # 部分免疫也要講出來。全省被護住時回的是 skipped=police_shielded，
            # 但只護住其中幾座時原本什麼都不回報，玩家看不出警政單位有作用。
            self._notify(owner,
                         f"{card.get('name')}：警政單位駐防的省份免疫，"
                         f"{len(spared)} 座城市未受波及。")
        return {"cities": list(picks), "riot_kind": effect["kind"], "spared": spared}

    def _sabotage_railway_as_punishment(self, owner: str, spec: Dict[str, Any],
                                        card: Dict[str, Any]) -> Dict[str, Any]:
        """挑一條被懲戒方境內、還沒在搶修的鐵路癱瘓掉。

        全額由被懲戒方支付（設計稿：一條鐵路消耗 30 工業點），付不出來的部分
        就扣到 0 為止並如實回報，不記成欠款——設計稿沒有寫欠款這件事。
        """
        allowed = list(spec.get("railways") or [])
        known = [line["name"] for line in self.data["strategic_map"].get("railroads", [])]
        busy = {e.get("railway") for e in self.state.get("railway_effects", [])
                if self._railway_effect_active(e)}
        pool = [name for name in (allowed or known) if name in known and name not in busy]
        if not pool:
            return {"skipped": "no_railway_available"}
        railway = pool[self.random.randrange(len(pool))]
        cost = int(spec.get("factory_cost", 30))
        profile = self._player(owner)
        before = int(profile.get("factory_points", 0))
        profile["factory_points"] = max(0, before - cost)
        paid = before - profile["factory_points"]
        effect = {
            "id": f"{card.get('id')}:{self.state['turn']}:{owner}:{railway}",
            "card_id": card.get("id"),
            "name": card.get("name", card.get("id")),
            "railway": railway,
            "initiator": str(spec.get("power", "")),
            "remaining_turns": int(spec.get("duration_turns", 3)),
            "repair_factory_cost": cost,
            # 只有被懲戒方付錢，這是與〈崩鐵玩家〉唯一的差別。
            "repair_charges": {owner: paid},
            "punishment": True,
        }
        self.state.setdefault("railway_effects", []).append(deepcopy(effect))
        self._notify(owner, f"{railway}遭破壞停運，搶修 {effect['remaining_turns']} 回合，"
                            f"修復工業點 −{paid}（全額由你負擔）。")
        return {"railway": railway, "paid": paid, "shortfall": max(0, cost - paid),
                "remaining_turns": effect["remaining_turns"]}

    def _preroll_assassination(self, card: Dict[str, Any], drawer: str):
        """列強派來的刺客：抽出當下就擲一次骰，成敗寫進 pending，供報紙照實刊登。

        引擎不持有將領資料，大帥是誰由前端隨回合回報（state.marshal_ids）。
        名單上沒有那一家就不擲——寧可不發生，也不要憑空殺一個不存在的人。
        """
        specs = (card.get("apply") or {}).get("assassinate_marshal") or []
        if not specs:
            return None
        spec = specs[0]
        marshal_id = (self.state.get("marshal_ids") or {}).get(drawer)
        if not marshal_id:
            return None
        outcome = self._resolve_assassination(
            str(spec.get("power", "")),
            {"id": card.get("id"), "name": card.get("name"),
             "success_rate": float(spec.get("success_rate", 0.2))},
            marshal_id, drawer, notify=False,
        )
        outcome["power"] = spec.get("power")
        return outcome

    def _event_duration_bonus(self, card: Dict[str, Any]) -> int:
        """這張事件卡的持續時間要不要加碼（火燒紅蓮寺對 [幫會] 卡 +1 回合）。

        比對的是卡片自己的 tags，所以日後任何一張卡掛上 [幫會] 就自動吃到，
        不必回頭改這裡。沒有相符的加碼條目就回 0。
        """
        # 標籤優先讀卡片本體：payload 一路傳下來的就是卡片自己，不必再回資料檔
        # 查一次（合成／測試用的卡片查不到會炸）。本體沒帶 tags 才回頭查資料檔。
        tags = set(card.get("tags") or [])
        card_id = card.get("id")
        if not tags and card_id:
            try:
                tags = set(self._event_tags(card_id))
            except ValueError:
                tags = set()
        if not tags:
            return 0
        turn = int(self.state["turn"])
        bonus = 0
        for entry in self.state.get("event_duration_bonuses", []):
            until = entry.get("until_turn")
            if until is not None and turn >= int(until):
                continue
            if tags & set(entry.get("tags") or []):
                bonus += int(entry.get("bonus", 0))
        return bonus

    def _extended_duration(self, card: Dict[str, Any], turns: Any, default: Any = None) -> Any:
        """把 [幫會]／[學潮] 的持續時間加碼套到一個「回合數」欄位上。

        先前這個加碼只接到 timed_flags，而 9 張帶標籤的卡沒有一張用 timed_flags，
        於是〈火燒紅蓮寺〉〈鴉片與釐金稅收〉〈萬縣慘案〉〈南京事件〉
        〈學潮與反帝遊行〉的「+1 回合」全部空轉。凡是這些卡開得出來的
        限時效果（city_halt、action_ban、student_unrest、city_riot 的鎮壓回合）
        都要走這裡，一份規則一個入口。

        turns 為 None（無期限）時原樣回傳——無期限再加一回合沒有意義。
        """
        span = turns if turns is not None else default
        if span is None:
            return None
        return int(span) + self._event_duration_bonus(card)

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
        """該玩家控制的、等級夠高的城市（9.3／10.7 指定四級或五級大城）。

        受〈殷墟第一鏟〉「科學發掘」那類治安事件免疫保護的省份要整省排除——
        免疫的意思是那些城市根本不會被挑中，而不是挑中之後再免疫。
        """
        out = []
        for city in self.data["strategic_map"]["cities"]:
            if self.state["city_owners"].get(city["id"], city["faction"]) != player:
                continue
            if int(self._with_level(city).get("level", 0)) < int(min_level):
                continue
            if self._gang_riot_shielded(player, city.get("province"), "security_event"):
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

    def _eligible_region_count(self, card: Dict[str, Any], player: str) -> int:
        """這位玩家控制了幾個「這張卡點名的地區」。

        「控制 a、b 或 c 者本回合獲得 $xx」的收益是**一個地區發一次、可疊加**，
        所以要數的是數量而不是有無。地區清單一律讀卡片 entry_condition 上的那一份
        （controls_provinces_any／controls_cities_any），不在別處再抄一次。
        """
        condition = card.get("entry_condition") or {}
        provinces = condition.get("controls_provinces_any") or []
        cities = condition.get("controls_cities_any") or []
        count = 0
        for province in provinces:
            if any(self.state["city_owners"].get(city["id"], city["faction"]) == player
                   for city in self.data["strategic_map"]["cities"]
                   if city.get("province") == province):
                count += 1
        for city_id in cities:
            city = next((c for c in self.data["strategic_map"]["cities"]
                         if c["id"] == city_id), None)
            if city is None:
                raise ValueError(f"{card.get('id')} 點名了不存在的城市：{city_id}")
            if self.state["city_owners"].get(city_id, city["faction"]) == player:
                count += 1
        return count

    # ── NPC 事件卡的觸發條件 ────────────────────────────────────────────
    #
    # 十五、NPC 行動那 33 張的進入條件講的是 NPC 勢力的現況：
    # 「閻錫山仍屬晉系」「黔軍至少還有 1 營兵力」「張家口仍歸西北軍佔領」。
    # 這些判定要在後端做——前端算的話，一句 JS 就能讓馮玉祥「復活」。
    #
    # 資料來源分兩處，各有各的道理：
    #   * 城市歸屬看 `state["city_owners"]`，那本來就是引擎自己的帳。
    #   * 將領與兵力看 SHARED_TACTICAL_STATE——編制、將領樹、將領歸屬都在那裡。
    #     引擎不持有將領樹（那是唯讀檔案），所以由伺服器把快照傳進來。
    #
    # **沒有快照時一律判為不合格**（fail closed）。寧可這張卡不出現，
    # 也不要發一張「馮玉祥誓師」而馮玉祥早就陣亡的報紙。

    def _npc_general_index(self) -> Dict[str, list]:
        """將領姓名 → [(陣營代號, 將領代號), ...]。名字是卡片上寫的，代號是資料檔的。"""
        index: Dict[str, list] = {}
        for faction in self.NPC_FACTIONS:
            tree = self.data.get("npc_general_trees", {}).get(faction) or {}
            for general_id, general in (tree.get("generals") or {}).items():
                index.setdefault(str(general.get("name") or ""), []).append(
                    (faction, general_id))
        return index

    def npc_situation(self, tactical: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """從戰術快照導出各 NPC 陣營的現況：還在的將領、還剩幾營。

        「還在」的定義：部隊沒有陣亡／被俘／被殲，且將領沒有跳槽
        （`generalOwners` 指向別家，或部隊自己改掛了別家的旗）。
        """
        out: Dict[str, Any] = {"available": isinstance(tactical, dict),
                               "factions": {}, "general_faction": {}}
        armies = (tactical or {}).get("armies") or {}
        owners = (tactical or {}).get("generalOwners") or {}
        jailed = set((tactical or {}).get("jailedGenerals") or [])
        index = self._npc_general_index()
        id_to_name = {gid: name for name, pairs in index.items() for _, gid in pairs}

        retired = self.retired_npc_factions()
        for faction in self.NPC_FACTIONS:
            generals: list = []
            battalions = 0
            # 已經退出地圖的陣營（被併吞或整批歸附）一律當成空的，
            # 點名它的卡片就再也不會出現。
            if faction in retired:
                out["factions"][faction] = {"generals": [], "battalions": 0}
                continue
            for army_id, army in armies.items():
                if self._home_faction(army_id) != faction:
                    continue
                if army.get("status") in self.DEAD_ARMY_STATUSES:
                    continue
                if self._npc_defected(army_id, army, owners):
                    continue
                general_id = army.get("generalId")
                if general_id and general_id not in jailed:
                    generals.append(general_id)
                    name = id_to_name.get(general_id)
                    if name:
                        out["general_faction"][name] = faction
                battalions += sum(max(0, int((army.get("units") or {}).get(unit) or 0))
                                  for unit in UNIT_FORCE_POINTS)
            out["factions"][faction] = {"generals": sorted(set(generals)),
                                        "battalions": battalions}
        return out

    def _living_npc_armies(self, tactical: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """還在場上、還算自家人的 NPC 部隊。判準與 npc_reinforcements 同一套。"""
        armies = (tactical or {}).get("armies") or {}
        owners = (tactical or {}).get("generalOwners") or {}
        jailed = set((tactical or {}).get("jailedGenerals") or [])
        out: Dict[str, Dict[str, Any]] = {}
        retired = self.retired_npc_factions()
        for army_id, army in armies.items():
            if self._home_faction(army_id) not in self.NPC_FACTIONS:
                continue
            if self._home_faction(army_id) in retired:
                continue
            if army.get("status") in self.DEAD_ARMY_STATUSES:
                continue
            if self._npc_defected(army_id, army, owners):
                continue
            if army.get("generalId") in jailed:
                continue
            out[army_id] = army
        return out

    def _npc_delta_targets(self, spec: Dict[str, Any], armies: Dict[str, Dict[str, Any]],
                           card: Dict[str, Any]) -> list:
        """一條 npc_unit_delta 規則點到哪些部隊。

        三種點名方式（可組合）：
          general / generals —— 指名將領，他的部隊。
          faction            —— 整個 NPC 陣營的所有部隊。
          except_generals    —— 從上面選出來的名單裡再剔除這些人（15.17 除馮玉祥外）。
        點名了查無此人的將領、不存在的陣營代號，一律拋錯——這種錯誤靜默略過的話，
        卡片會「生效了但什麼都沒發生」，比直接壞掉更難查。
        """
        index = self._npc_general_index()
        card_id = card.get("id")

        def ids_for(names: Any) -> set:
            out: set = set()
            for name in (names if isinstance(names, (list, tuple)) else [names]):
                pairs = index.get(str(name))
                if not pairs:
                    raise ValueError(f"{card_id} 的 npc_unit_delta 點名了查無此人的將領：{name}")
                out |= {gid for _, gid in pairs}
            return out

        picked: set = set()
        named = spec.get("generals") if spec.get("generals") is not None else spec.get("general")
        if named is not None:
            wanted = ids_for(named)
            picked |= {army_id for army_id, army in armies.items()
                       if army.get("generalId") in wanted}
        faction = spec.get("faction")
        if faction is not None:
            if str(faction) not in self.NPC_FACTIONS:
                raise ValueError(f"{card_id} 的 npc_unit_delta 用了不是 NPC 陣營的代號：{faction}")
            picked |= {army_id for army_id in armies
                       if self._home_faction(army_id) == str(faction)}
        if named is None and faction is None:
            raise ValueError(f"{card_id} 的 npc_unit_delta 沒有指定 general 或 faction：{spec}")
        excluded = spec.get("except_generals")
        if excluded:
            skip = ids_for(excluded)
            picked = {army_id for army_id in picked
                      if armies[army_id].get("generalId") not in skip}
        return sorted(picked)

    def npc_unit_delta_patch(self, specs: list, card: Dict[str, Any],
                             tactical: Optional[Dict[str, Any]]) -> list:
        """算出每支被點到的 NPC 部隊「加減完之後」的絕對編制。

        規則有好幾條時（15.3：馮玉祥一條、其餘西北軍一條）先把同一支部隊的增減
        全部累加起來，最後才寫一次——否則同一支部隊會出現兩筆互相覆蓋的補丁。
        戰力一律受 ARMY_FORCE_CAP 箝制，兵種數量不會低於 0。
        """
        armies = self._living_npc_armies(tactical)
        totals: Dict[str, Dict[str, int]] = {}
        order: list = []
        for spec in specs:
            deltas = spec.get("units") or {}
            if not deltas:
                raise ValueError(f"{card.get('id')} 的 npc_unit_delta 少了 units：{spec}")
            unknown = set(deltas) - set(UNIT_FORCE_POINTS)
            if unknown:
                raise ValueError(
                    f"{card.get('id')} 的 npc_unit_delta 用了不認得的兵種：{sorted(unknown)}")
            for army_id in self._npc_delta_targets(spec, armies, card):
                if army_id not in totals:
                    totals[army_id] = {}
                    order.append(army_id)
                for unit, amount in deltas.items():
                    totals[army_id][unit] = totals[army_id].get(unit, 0) + int(amount)

        patch: list = []
        for army_id in order:
            army = armies[army_id]
            before = {unit: max(0, int((army.get("units") or {}).get(unit) or 0))
                      for unit in UNIT_FORCE_POINTS}
            after = dict(before)
            # 先扣後補。減損一律生效（最低 0）；增援只補得進去的那部分——
            # 部隊已經滿編時不該為了塞進新兵而把原來的老兵裁掉，那是「擴軍」
            # 反而讓兵變少。補不完就補不完，下面 changed 會誠實報實際的數。
            for unit, amount in totals[army_id].items():
                if int(amount) < 0:
                    after[unit] = max(0, after[unit] + int(amount))
            for unit, amount in totals[army_id].items():
                for _ in range(max(0, int(amount))):
                    if self._force_of(after) + UNIT_FORCE_POINTS[unit] > ARMY_FORCE_CAP:
                        break
                    after[unit] += 1
            gained = {unit: after[unit] - before[unit]
                      for unit in UNIT_FORCE_POINTS if after[unit] != before[unit]}
            if not gained:
                continue
            patch.append({"armyId": army_id, "faction": self._home_faction(army_id),
                          "generalId": army.get("generalId"),
                          "units": after, "changed": gained})
        return patch

    def npc_force_scale_patch(self, specs: list, card: Dict[str, Any],
                              tactical: Optional[Dict[str, Any]]) -> list:
        """按比例增減 NPC 部隊的**戰力**，回傳每支部隊調整後的絕對編制。

        規則書裡「戰力」就是那個 100 點上限的兵力值（步兵／騎兵每營 1 點、
        機槍 2 點、砲兵 4 點），所以「唐生智戰力 −50%」是**真的裁兵**，
        不是打折的戰鬥乘數。這與 12.x 列強行動那批「部隊戰力一次性 −40%」同一套。

        目標戰力點 = floor(現值 × 倍率)，上限仍是 ARMY_FORCE_CAP。
          減損 → 從最貴的兵種裁起（既有規則）。
          增益 → 補步兵，每營 1 點，補得最精準，也和 NPC 例行補兵一致。
        一次性、不會自己回復。
        """
        armies = self._living_npc_armies(tactical)
        factors: Dict[str, float] = {}
        order: list = []
        for spec in specs:
            if "multiplier" not in spec:
                raise ValueError(f"{card.get('id')} 的 npc_force_scale 少了 multiplier：{spec}")
            multiplier = float(spec["multiplier"])
            if multiplier < 0:
                raise ValueError(f"{card.get('id')} 的 npc_force_scale 倍率不能是負的：{multiplier}")
            for army_id in self._npc_delta_targets(spec, armies, card):
                if army_id not in factors:
                    factors[army_id] = 1.0
                    order.append(army_id)
                # 同一支部隊被多條規則點到時倍率相乘——先 −15% 再 −10%
                # 是在剩下的兵上再砍一成，不是一口氣砍兩成五。
                factors[army_id] *= multiplier

        patch: list = []
        for army_id in order:
            army = armies[army_id]
            before = {unit: max(0, int((army.get("units") or {}).get(unit) or 0))
                      for unit in UNIT_FORCE_POINTS}
            current = self._force_of(before)
            # 四捨五入，不是無條件捨去。NPC 部隊普遍小，捨去小數的損失占比很重：
            # 一張寫 −15% 的卡打在 7 點的部隊上，捨去會變成實際 −29%。
            # 用 floor(x+0.5) 而不是 Python 的 round()——後者是銀行家捨入
            # （.5 進到偶數），同樣的 .5 會依前一位數字給出不同答案。
            target = min(ARMY_FORCE_CAP,
                         int(math.floor(current * factors[army_id] + 0.5)))
            if target < current:
                after = self._cut_down_to_force(before, target)
            else:
                after = dict(before)
                while self._force_of(after) + UNIT_FORCE_POINTS["infantry"] <= target:
                    after["infantry"] += 1
            changed = {unit: after[unit] - before[unit]
                       for unit in UNIT_FORCE_POINTS if after[unit] != before[unit]}
            if not changed:
                continue
            patch.append({"armyId": army_id, "faction": self._home_faction(army_id),
                          "generalId": army.get("generalId"), "units": after,
                          "changed": changed, "force_before": current,
                          "force_after": self._force_of(after)})
        return patch

    def _land_npc_army_patch(self, kind: str, builder, specs: list,
                             card: Dict[str, Any], label: str) -> list:
        """把一份 NPC 部隊編制補丁落地：改後端那份，再掛一筆給前端。

        `npc_unit_delta`（絕對增減）與 `npc_force_scale`（按比例）算法不同，
        但算完之後要做的事一模一樣，所以共用這一段。
        """
        if not isinstance(self._tactical, dict):
            # 走不到這裡：這批卡都有 npc_requires，沒有戰術快照時整張卡就不會出現。
            # 真的走到了也不要靜默——記一筆，讓重播與測試看得見。
            return [{"kind": f"{kind}_skipped", "reason": "no_tactical"}]
        patch = builder(specs, card, self._tactical)
        # 伺服器手上這份先改掉：同一個事件卡週期裡後面幾張卡的 npc_requires
        # 要看的是改完之後的現況。
        for entry in patch:
            army = (self._tactical.get("armies") or {}).get(entry["armyId"])
            if army is not None:
                army["units"] = dict(entry["units"])
        if patch:
            # 前端那份是各 client 自己的副本，靠 pending_frontend_effects 補回去。
            # 只掛在一位玩家的佇列上：這件事是全場共通的，掛給每個人會被套用多次。
            # 內容是絕對編制，重複套用結果相同，但提示會重複，所以還是只掛一次。
            holder = sorted(self.state["players"])[0]
            self._player(holder).setdefault("pending_frontend_effects", []).append({
                "kind": "npc_army_units", "label": label, "armies": patch})
        return [{"kind": kind, "armies": patch}]

    # ── 批次四：陣營級結構變動的共用零件 ────────────────────────────────

    def _notify_all(self, text: str) -> None:
        for code in self.state["players"]:
            self._notify(code, text)

    def retired_npc_factions(self) -> set:
        return {str(code) for code in (self.state.get("retired_npc_factions") or [])}

    def _npc_general_still_here(self, name: Optional[str],
                               faction: Optional[str]) -> bool:
        """這位 NPC 將領現在還在他原本的陣營裡嗎。

        沒有戰術快照時回報「還在」——寧可效果多留一回合，也不要因為前端還沒送
        狀態就把封路誤解除。這與 npc_combat_effects 的離場判定同一個道理。
        """
        if not name or not faction:
            return True
        if faction in self.retired_npc_factions():
            return False
        if not isinstance(self._tactical, dict):
            return True
        situation = self.npc_situation(self._tactical)
        if not situation.get("available"):
            return True
        return situation["general_faction"].get(str(name)) == str(faction)

    def _npc_faction_cities(self, faction: str) -> list:
        """這個陣營現在握著哪些城市。以 city_owners 為準，沒有紀錄就看地圖的初始歸屬。"""
        owners = self.state.get("city_owners") or {}
        return [city["id"] for city in self.data["strategic_map"]["cities"]
                if owners.get(city["id"], city["faction"]) == str(faction)]

    def _retire_npc_faction(self, faction: str) -> None:
        retired = self.state.setdefault("retired_npc_factions", [])
        if str(faction) not in retired:
            retired.append(str(faction))

    def _hand_over_npc_armies(self, faction: str, new_owner: str) -> list:
        """把一個 NPC 陣營的部隊整批換旗，回傳搬了哪些。

        改的是伺服器手上那份戰術快照；前端那份靠 pending_frontend_effects 補。
        """
        moved: list = []
        for army_id, army in sorted(self._living_npc_armies(self._tactical).items()):
            if self._home_faction(army_id) != str(faction):
                continue
            army["faction"] = str(new_owner)
            general_id = army.get("generalId")
            if general_id and isinstance(self._tactical, dict):
                self._tactical.setdefault("generalOwners", {})[general_id] = str(new_owner)
            moved.append({"armyId": army_id, "generalId": general_id,
                          "units": dict(army.get("units") or {})})
        return moved

    def player_force_ranking(self) -> list:
        """各玩家的總戰力，由高到低。戰力就是那個 100 點上限用的兵力點。

        資料來自戰術快照——部隊編制住在那裡。沒有快照就回空的，
        呼叫端要自己決定怎麼辦（15.13 的作法是不發這張卡）。
        """
        if not isinstance(self._tactical, dict):
            return []
        totals = {code: 0 for code in self.state["players"]}
        owners = (self._tactical.get("generalOwners") or {})
        for army_id, army in (self._tactical.get("armies") or {}).items():
            if army.get("status") in self.DEAD_ARMY_STATUSES:
                continue
            faction = (army.get("faction")
                       or owners.get(army.get("generalId"))
                       or self._home_faction(army_id))
            if faction not in totals:
                continue
            totals[faction] += self._force_of(army.get("units"))
        return sorted(totals.items(), key=lambda item: (-item[1], item[0]))

    def _top_force_player(self) -> Optional[str]:
        """總戰力最高的玩家。並列最高就隨機擇一（用有種子的亂數，可重播）。"""
        ranking = self.player_force_ranking()
        if not ranking:
            return None
        best = ranking[0][1]
        tied = [code for code, force in ranking if force == best]
        if len(tied) == 1:
            return tied[0]
        return tied[self.random.randrange(len(tied))]

    def _npc_requires_met(self, card: Dict[str, Any],
                          tactical: Optional[Dict[str, Any]]) -> bool:
        """卡片的 `entry_condition.npc_requires` 是否全部成立。"""
        rules = (card.get("entry_condition") or {}).get("npc_requires") or []
        if not rules:
            return True
        situation = self.npc_situation(tactical)
        index = self._npc_general_index()
        named_ids: set = set()
        # 先把本卡點名的將領收齊，`at_least_one_other_general` 的「其他」指的就是他們以外。
        for rule in rules:
            name = rule.get("general")
            if name:
                named_ids |= {gid for _, gid in index.get(name, [])}

        for rule in rules:
            if rule.get("general"):
                name = str(rule["general"])
                faction = str(rule["still_with"])
                candidates = index.get(name) or []
                if not candidates:
                    raise ValueError(
                        f"{card.get('id')} 點名了查無此人的將領：{name}")
                if all(code != faction for code, _ in candidates):
                    raise ValueError(
                        f"{card.get('id')}：{name}不屬於 {faction}，"
                        f"資料檔裡他在 {sorted({code for code, _ in candidates})}")
                if not situation["available"]:
                    return False
                if situation["general_faction"].get(name) != faction:
                    return False
            elif rule.get("at_least_one_general"):
                if not situation["available"]:
                    return False
                if not situation["factions"].get(str(rule["faction"]), {}).get("generals"):
                    return False
            elif rule.get("at_least_one_other_general"):
                if not situation["available"]:
                    return False
                alive = set(situation["factions"]
                            .get(str(rule["faction"]), {}).get("generals") or [])
                if not (alive - named_ids):
                    return False
            elif rule.get("min_battalions") is not None:
                if not situation["available"]:
                    return False
                have = situation["factions"].get(str(rule["faction"]), {}).get("battalions", 0)
                if int(have) < int(rule["min_battalions"]):
                    return False
            elif rule.get("city"):
                # 城市歸屬是引擎自己的帳，不必等戰術快照。
                city_id = str(rule["city"])
                city = next((c for c in self.data["strategic_map"]["cities"]
                             if c["id"] == city_id), None)
                if city is None:
                    raise ValueError(f"{card.get('id')} 點名了不存在的城市：{city_id}")
                if self.state["city_owners"].get(city_id, city["faction"]) \
                        != str(rule["held_by_faction"]):
                    return False
            else:
                raise ValueError(f"{card.get('id')} 有一條看不懂的 NPC 條件：{rule}")
        return True

    def _event_eligible_players(self, card: Dict[str, Any]) -> list:
        """這張事件卡現在有哪些玩家可以抽到。沒有進入條件就是全部。"""
        condition = card.get("entry_condition") or {}
        # NPC 條件是**整張卡**的閘門，不是逐玩家的：閻錫山不在了，
        # 這張卡對誰都不該出現。不成立就直接回空的名單。
        if condition.get("npc_requires") and not self._npc_requires_met(card, self._tactical):
            return []
        # 15.16 南京事件：南京得真的有軍隊駐守。駐軍位置住在地圖層（前端），
        # 所以前端每回合把「哪座城有誰的幾營」這個**事實**報上來，規則在這裡判。
        # 沒收到報告就一律不發（fail closed）——與 npc_requires 同一個道理。
        # 15.13 馬家軍歸附：卡片本身要求「當前總戰力最高的玩家」存在才有意義。
        # 排名要靠戰術快照，沒有快照就不發（fail closed）。
        rank_rule = condition.get("player_rank")
        if rank_rule:
            metric = str(rank_rule.get("metric") or "total_force")
            if metric != "total_force":
                raise ValueError(f"{card.get('id')} 的 player_rank 用了不認得的 metric：{metric}")
            position = str(rank_rule.get("position") or "highest")
            if position != "highest":
                raise ValueError(f"{card.get('id')} 的 player_rank 只支援 highest：{position}")
            ranking = self.player_force_ranking()
            if not ranking or ranking[0][1] <= 0:
                return []

        garrison_city = condition.get("requires_garrison_in_city")
        if garrison_city:
            city_id = str(garrison_city)
            if not any(c["id"] == city_id for c in self.data["strategic_map"]["cities"]):
                raise ValueError(f"{card.get('id')} 的 requires_garrison_in_city 指向不存在的城市：{city_id}")
            here = (self._city_garrisons or {}).get(city_id) or {}
            if not any(int(n) > 0 for n in here.values()):
                return []
        players = list(self.state["players"])
        # [懲戒] 卡：對某人還生效中就不該再降臨同一個人，但**別人照樣抽得到**——
        # 兩個對日交惡的玩家可以同時挨日軍航空隊的轟炸。所以這是逐玩家的封鎖，
        # 不是整張卡的封鎖。
        card_id = str(card.get("id") or "")
        players = [code for code in players
                   if not self.punishments.active_card_for(card_id, code)]
        # 最後通牒與租界管制走同一個「對同一人生效中就不重複降臨」的規則。
        for spec in (card.get("apply") or {}).get("ultimatum") or []:
            players = [code for code in players
                       if not self.ultimatums.active_for(str(spec["power"]), code)]
        for spec in (card.get("apply") or {}).get("concession_control") or []:
            players = [code for code in players
                       if not self.concession_controls.active_for(str(spec["power"]), code)]
        # 關係門檻的另一半：`relation_max`（懲戒卡都是「對某國關係 ≤ −4」才降臨）。
        relation_max = condition.get("relation_max") or {}
        if relation_max:
            players = [code for code in players
                       if all(int(self._player(code).get("foreign_relations", {})
                                  .get(power, 0)) <= int(ceiling)
                              for power, ceiling in relation_max.items())]
        if not condition:
            return players
        province = condition.get("controls_province")
        cities = condition.get("controls_cities_any") or []
        cities_all = condition.get("controls_cities_all") or []
        relation_min = condition.get("relation_min") or {}
        relation_min_any = condition.get("relation_min_any") or {}
        provinces_any = condition.get("controls_provinces_any") or []
        # [地面部隊] 懲戒：唯有該國的最後通牒被無視之後才對那位玩家解封。
        ignored_ultimatum = condition.get("requires_failed_ultimatum")
        # 租界管制：手上得真的有那一國的租界城市。
        concession_of = condition.get("requires_concession_of")
        # 封鎖類：手上得真的有夠多座貼著那片水域的港市
        # （「控制至少三座長江河港城市」「三座珠江河港或南海沿岸海港」）。
        ports_rule = condition.get("controls_ports_in_waters_min") or {}
        # 13.11 關餘與鹽稅盈餘：「控制至少一個三級以上河港或海港城市」。
        port_level_rule = condition.get("controls_port_level_min") or {}
        # 13.17 外資設廠：「控制至少一個租界城市」——不指定是哪一國的租界。
        concession_any = bool(condition.get("requires_concession_any"))
        # 13.25 軍餉短缺：「上回合結束時現金 < 10」。看的是**上回合結束後**的數字，
        # 不是此刻的——事件在本回合收入入帳前結算，拿現值判會判錯人。
        treasury_below = condition.get("treasury_below_last_turn")
        # 14.4 碼頭工潮：「控制至少兩個港口城市（河港海港皆可）」。
        port_count = condition.get("controls_port_count_min")
        # 條件鍵寫錯會讓卡片對所有人生效（漏放行比誤放行安全），所以先擋。
        known_conditions = {
            "relation_max", "controls_province", "controls_cities_any", "controls_cities_all",
            "relation_min", "relation_min_any", "controls_provinces_any",
            "requires_failed_ultimatum", "requires_concession_of",
            "controls_ports_in_waters_min", "controls_port_level_min",
            "requires_concession_any", "treasury_below_last_turn",
            "controls_port_count_min",
            # 十五、NPC 行動。npc_requires 與 requires_garrison_in_city 是**整張卡**
            # 的閘門（在上面判）；at_war_with 與 player_rank 是逐玩家的。
            "npc_requires", "at_war_with", "requires_garrison_in_city", "player_rank",
        }
        unknown = set(condition) - known_conditions
        if unknown:
            raise ValueError(f"entry_condition 不認得的條件：{sorted(unknown)}")
        # 15.18 劉湘通電討直：「當下正對直系宣戰的玩家」才抽得到。逐玩家判。
        at_war_with = condition.get("at_war_with")
        eligible = []
        for code in players:
            if at_war_with and not self._at_war(code, str(at_war_with)):
                continue
            if ignored_ultimatum and str(ignored_ultimatum) not in self.ultimatums.failed_powers(code):
                continue
            if port_level_rule and not self._select_cities(
                    {"port": True, "owned_by_target": True,
                     "min_level": int(port_level_rule.get("level", 3)),
                     **({"port_types": port_level_rule["port_types"]}
                        if port_level_rule.get("port_types") else {})}, [code]):
                continue
            if concession_any and not self._select_cities(
                    {"concession": True, "owned_by_target": True}, [code]):
                continue
            if treasury_below is not None \
                    and self._treasury_at_last_turn_end(code) >= int(treasury_below):
                continue
            if port_count is not None and len(self._select_cities(
                    {"port": True, "owned_by_target": True}, [code])) < int(port_count):
                continue
            if concession_of and not self._concession_cities(code, str(concession_of)):
                continue
            if ports_rule and self._ports_in_waters(code, ports_rule.get("waters") or []) \
                    < int(ports_rule.get("count", 1)):
                continue
            if provinces_any and not any(self._controlled_provinces(code, [p])
                                         for p in provinces_any):
                continue
            if province and not self._controlled_provinces(code, [province]):
                continue
            if cities and not any(self.state["city_owners"].get(city) == code for city in cities):
                continue
            # 「周邊一圈兩格內所有城市」這種條件是**全部**要控制，不是任一。
            if cities_all and not all(self.state["city_owners"].get(city) == code
                                      for city in cities_all):
                continue
            # 關係門檻（日本承認北京政府要對日 ≥6、蘇聯建交要對蘇 ≥6）。
            relations = self._player(code).get("foreign_relations", {})
            if any(int(relations.get(power, 0)) < int(floor)
                   for power, floor in relation_min.items()):
                continue
            # 「對英 ≥6 **或** 對美 ≥6」：任一達標即可，與 relation_min 的全部達標不同。
            if relation_min_any and not any(int(relations.get(power, 0)) >= int(floor)
                                            for power, floor in relation_min_any.items()):
                continue
            eligible.append(code)
        return eligible

    # 「每一家都要各自表態」的兩種範圍：
    #   all_players      —— 全場都問（〈非戰公約〉）。
    #   eligible_players —— 只問符合 entry_condition 的那幾家（付費招募 NPC 的四張卡、
    #                       〈南京事件〉）。責任分工在 _event_responder_queue：
    #                       名單本來就是照 _event_eligible_players 篩的。
    # eligible_players 先前不在這個集合裡，於是佇列塌成 [drawer]，第一個人回應完
    # 整張卡就結案——多方競標（所有出價者各付 $25、成功率 1/n）實戰永遠跑不到，
    # 而〈南京事件〉也只會問到抽卡的那一家。
    EVERY_FACTION_SCOPES = ("all_players", "eligible_players")

    def event_needs_every_faction(self, card: Dict[str, Any]) -> bool:
        """這張卡是不是「每一家都要各自表態、各自結算」。

        判準：resolution 是 choice，且 scope 在 EVERY_FACTION_SCOPES 裡。
        先前這個值在 pending_event_view 裡被寫死成 False，導致
        〈亞克斯搜查案〉〈非戰公約〉〈全國經濟會議與裁兵之議〉
        全部退化成只有抽到的那一家表態。
        """
        resolution = card.get("resolution") or {}
        return (resolution.get("type") == "choice"
                and resolution.get("scope", "all_players") in self.EVERY_FACTION_SCOPES)

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
            # 已擲骰的卡（11.5）：告訴前端該刊哪一版報紙。沒擲過就是 None。
            "newspaper_index": (entry.get("random_outcome") or {}).get("newspaper_index"),
            # 暗殺類事件：報紙的「效果」欄要照實寫出這一次得手沒有。
            "assassination": entry.get("assassination"),
        }

    # 日蘇戰爭的四份戰況報導：兩個可能的衝突省 × 勝負兩種結果。
    POWER_WAR_REPORTS = {
        ("黑龍江", "su"): "jp_su_war_heilongjiang_soviet_win",
        ("黑龍江", "jp"): "jp_su_war_heilongjiang_japan_win",
        ("吉林", "su"): "jp_su_war_jilin_soviet_win",
        ("吉林", "jp"): "jp_su_war_jilin_japan_win",
    }

    def _queue_power_war_reports(self, applied: list, pending: Dict[str, Any],
                                 drawer: str) -> int:
        """把戰況報導插進本回合的報紙佇列，排在觸發懲戒的那一張後面。"""
        inserted = 0
        for item in applied:
            if item.get("kind") != "foreign_punishment":
                continue
            for war in (item.get("punishment") or {}).get("wars") or []:
                card_id = self.POWER_WAR_REPORTS.get((war["province"], war["winner"]))
                if not card_id:
                    # 原本是 `continue`：仗照打、地照易手、傷害照扣，就是不出報紙。
                    # 玩家會看到領土無故換手卻沒有任何說明——最難查的那種靜默失敗。
                    # 目前資料檔的日蘇重疊只落在吉林／黑龍江（兩者都有戰報卡），
                    # 但只要新增一張讓重疊跑到別省的懲戒卡就會踩到。吵出來。
                    raise ValueError(
                        f'{war["province"]} 的日蘇開戰（{war["winner"]} 方獲勝）'
                        f"沒有對應的戰況報導卡，請補進 POWER_WAR_REPORTS")
                pending["cards"].insert(int(pending["index"]) + inserted, {
                    "card_id": card_id, "drawer": drawer,
                    "responders": [drawer], "responses": {}, "power_war": war,
                })
                inserted += 1
        return inserted

    def consume_frontend_effects(self, player: str, kind: Optional[str] = None) -> Dict[str, Any]:
        """把某位玩家的前端待辦清單取出並清掉。

        部隊戰力、艦隊生命、駐軍位置都住在 app.js，後端只能把要做的事記在
        pending_frontend_effects 上。前端做完之後回來銷帳——不銷的話下一次
        讀狀態又會看到同一筆，同一份傷害會重複扣。
        """
        profile = self._player(player)
        queue = list(profile.get("pending_frontend_effects") or [])
        if kind is None:
            taken, left = queue, []
        else:
            taken = [entry for entry in queue if entry.get("kind") == kind]
            left = [entry for entry in queue if entry.get("kind") != kind]
        profile["pending_frontend_effects"] = left
        return {"consumed": taken, "state": self.snapshot()}

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
            # 日蘇重疊區開戰：懲戒本身結完之後，同一回合再補刊戰況報導，一省一則。
            # 衝突兩省玩家就會看到三則（懲戒 ＋ 兩省戰況），與設計稿一致。
            self._queue_power_war_reports(applied, pending, entry["drawer"])
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

    def _event_responses(self, card: Dict[str, Any]) -> Dict[str, str]:
        """這張卡目前收到的表態：{玩家代號: 選項 id}。

        卡片層級的 `apply` 是在**所有人都回應完**之後才跑一次的（見 respond_event
        的 card_done 分支），所以競標類的效果只能寫在那裡——寫在選項的 apply 裡
        會在每個人各自回應的當下就結算，那時候只看得到他一個人的選擇。
        """
        pending = self.state.get("pending_events") or {}
        cards = pending.get("cards") or []
        index = int(pending.get("index") or 0)
        if not (0 <= index < len(cards)):
            return {}
        entry = cards[index]
        if str(entry.get("card_id") or "") != str(card.get("id") or ""):
            return {}
        return dict(entry.get("responses") or {})

    def _purge_card_everywhere(self, player: str, card_id: str) -> int:
        """把一張功能卡從這位玩家的牌庫／手牌／棄牌堆／待抽整個清掉，回傳清了幾張。

        中央研究院的〈中國人之恥〉與通用的 clear_cards 走同一份實作——
        先前是兩份，通用那份因此沒有任何卡片走得到。
        """
        payload = self._player(player)
        removed = 0
        for zone in ("function_deck", "hand", "discard"):
            before = len(payload.get(zone) or [])
            payload[zone] = [item for item in payload.get(zone, []) if item != card_id]
            removed += before - len(payload[zone])
        if payload.get("pending_draw") == card_id:
            payload["pending_draw"] = None
            removed += 1
        return removed

    def _apply_event_payload(
        self, payload: Dict[str, Any], *, players: Optional[list], card: Dict[str, Any],
    ) -> list:
        """把事件卡上接得住的效果實際寫進狀態，回傳做了哪些事。"""
        if not payload:
            return []
        applied = []
        targets = list(players) if players is not None else list(self.state["players"])
        # ---- 「僅適用符合條件的玩家」----
        # entry_condition 只決定「這張卡抽不抽得到、誰當抽卡人」，卡片層級的 apply
        # 預設是**全場**生效。設計稿標「僅適用符合條件的玩家」而效果又不會自己
        # 限縮範圍的（例如直接發錢的 grant），得靠這個旗標把 targets 收回來，
        # 否則沒控制江浙的玩家也會跟著領到那 $+8。
        if payload.get("eligible_only"):
            qualified = set(self._event_eligible_players(card))
            targets = [code for code in targets if code in qualified]
        # ---- 免疫旗標（11.5 廢兩改元成功者不再受銀價／外流／擠兌影響）----
        # 旗標掛在玩家的 timed_effects 上，這裡直接把持有者從 targets 裡剔除。
        immune = payload.get("immune_flag")
        if immune:
            targets = [code for code in targets if not self.has_timed_flag(code, str(immune))]
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
                start = turn + int(delayed.get("delay_turns", 0))
                span = delayed.get("turns")
                self._player(code).setdefault("delayed_output_bonuses", []).append({
                    "card_id": card.get("id"),
                    "name": label,
                    "start_turn": start,
                    # turns 不寫＝永久；寫了就會自己到期。
                    "until_turn": (start + int(span)) if span is not None else None,
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
            # 「封鎖」有兩種來源：事件卡池的 event_locks，以及功能卡的 perk_suspensions。
            # 10.7 北京大學共運要解除的〈紅軍起義〉〈共黨暴動〉封鎖是後者（10.6 自由中國
            # 教育家下的 perk_suspension），先前只清前者，等於這張卡的解封是空的。
            suspensions_kept, suspensions_removed = [], 0
            for entry in self.state.get("perk_suspensions", []):
                if release.get("labels") and entry.get("label") in release["labels"]:
                    suspensions_removed += 1
                    continue
                if release.get("cards") and set(release["cards"]) & set(entry.get("cards") or []):
                    suspensions_removed += 1
                    continue
                if release.get("source_cards") and entry.get("source_card") in release["source_cards"]:
                    suspensions_removed += 1
                    continue
                suspensions_kept.append(entry)
            self.state["perk_suspensions"] = suspensions_kept
            for code in self.state["players"]:
                self._sync_foreign_deck_cards(code)
                self._sync_conditional_deck_cards(code)
            if removed or suspensions_removed:
                applied.append({"kind": "event_unlock", "released": removed,
                                "perk_suspensions_released": suspensions_removed,
                                **release})

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
                # never_drawn 的卡不進池子——它們只由機制直接插進 pending（日蘇戰況
                # 報導）。2.4 東方會議是用「日本 [軍事]」標籤整批加張的，而
                # 12.20／12.22 兩張日軍獲勝的戰況報導剛好也掛著 [軍事]＋日，
                # 於是被一起塞進池子，之後真的抽得到——變成一則從沒打過的仗的戰報。
                ids = [cid for cid in ids
                       if not (self._event_template(cid) or {}).get("never_drawn")
                       and not (self._event_template(cid) or {}).get("not_in_pool")]
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

        # ---- NPC 部隊增減兵（15.3、15.6、15.8、15.12、15.19、15.25、15.26）----
        # 這是 NPC 的兵，不是玩家的預備隊，所以不走 reserve_delta：NPC 沒有預備隊，
        # 兵直接加在場上的部隊編制裡。編制住在 SHARED_TACTICAL_STATE，伺服器手上就有，
        # 因此**加減與上限箝制全在後端算完**，前端拿到的是絕對編制，照抄即可。
        npc_specs = payload.get("npc_unit_delta") or []
        if npc_specs:
            applied += self._land_npc_army_patch(
                "npc_unit_delta", self.npc_unit_delta_patch, npc_specs, card, label)

        # ---- NPC 部隊按比例增減戰力（15.4、15.7、15.9、15.11、15.15、15.17、15.24）----
        # 規則書裡「戰力」就是那個 100 點上限的兵力值，所以這是真的裁兵／補兵，
        # 不是戰鬥時打折。落地方式與上面那條完全相同。
        scale_specs = payload.get("npc_force_scale") or []
        if scale_specs:
            applied += self._land_npc_army_patch(
                "npc_force_scale", self.npc_force_scale_patch, scale_specs, card, label)

        # ---- NPC 戰鬥修正（15.2、15.20、15.22、15.23）----
        # 「生命」是 hp、「攻擊」是 attack；「戰力」是第三個詞，指兵力，走 npc_force_scale。
        for spec in (payload.get("npc_combat_modifier") or []):
            faction = spec.get("faction")
            general_name = spec.get("general")
            general_id = None
            if general_name:
                pairs = self._npc_general_index().get(str(general_name))
                if not pairs:
                    raise ValueError(
                        f"{card.get('id')} 的 npc_combat_modifier 點名了查無此人的將領：{general_name}")
                faction_from_name, general_id = pairs[0]
                if faction and faction != faction_from_name:
                    raise ValueError(
                        f"{card.get('id')}：{general_name} 不屬於 {faction}，"
                        f"資料檔裡他在 {faction_from_name}")
                faction = faction_from_name
            if not faction:
                raise ValueError(
                    f"{card.get('id')} 的 npc_combat_modifier 沒有指定 faction 或 general：{spec}")
            if faction not in self.NPC_FACTIONS:
                raise ValueError(
                    f"{card.get('id')} 的 npc_combat_modifier 用了不是 NPC 陣營的代號：{faction}")
            modifiers = list(spec.get("modifiers") or [])
            if not modifiers:
                raise ValueError(f"{card.get('id')} 的 npc_combat_modifier 少了 modifiers：{spec}")
            unknown = {str(m.get("stat")) for m in modifiers} - {"hp", "attack", "harm_taken"}
            if unknown:
                raise ValueError(
                    f"{card.get('id')} 的 npc_combat_modifier 用了不認得的 stat：{sorted(unknown)}")
            turns = spec.get("turns")
            until_leaves = bool(spec.get("until_general_leaves"))
            if turns is None and not until_leaves:
                raise ValueError(
                    f"{card.get('id')} 的 npc_combat_modifier 既沒有 turns 也沒有 "
                    f"until_general_leaves——效期不明的效果會永遠掛著：{spec}")
            if until_leaves and not general_id:
                raise ValueError(
                    f"{card.get('id')} 的 until_general_leaves 沒有指定將領，無從判斷離場：{spec}")
            entry = {"name": label, "card_id": str(card.get("id") or ""),
                     "faction": faction, "general_id": general_id,
                     "modifiers": deepcopy(modifiers),
                     "remaining_turns": None if turns is None else int(turns),
                     "until_general_leaves": until_leaves,
                     # 抽到的這一回合不倒數，否則 5 回合的效果只會活 4 回合。
                     "granted_this_turn": True}
            self.state.setdefault("npc_combat_effects", []).append(entry)
            applied.append({"kind": "npc_combat_modifier", "faction": faction,
                            "general_id": general_id, "general": general_name,
                            "modifiers": entry["modifiers"], "turns": entry["remaining_turns"],
                            "until_general_leaves": until_leaves})

        # ---- NPC 付費招募（15.7、15.10、15.18、15.21）----
        # 「多方都想招募，則所有要招募者都要付 $25，且成功率由所有參與招募的玩家平分」。
        # 付錢的一律扣款——競標輸了錢也不退，這是卡片寫的。抽籤用 self.random（有種子，
        # 可重播），不是 Python 的全域亂數。
        recruit = payload.get("contested_npc_recruit")
        if recruit:
            general_name = str(recruit.get("general") or "")
            pairs = self._npc_general_index().get(general_name)
            if not pairs:
                raise ValueError(
                    f"{card.get('id')} 的 contested_npc_recruit 點名了查無此人的將領：{general_name}")
            home_faction, general_id = pairs[0]
            cost = int(recruit.get("cost", 25))
            option_id = str(recruit.get("option_id") or "recruit")

            # 誰表態要招募：看這張卡的回應。表態了但錢不夠的算棄權——
            # 事件卡不該讓人負債，也不該無聲把他算進分母稀釋別人的機率。
            bidders, broke = [], []
            for code in sorted(self._event_responses(card)):
                if self._event_responses(card).get(code) != option_id:
                    continue
                if int(self._player(code).get("treasury", 0)) < cost:
                    broke.append(code)
                    continue
                bidders.append(code)

            entry = {"kind": "contested_npc_recruit", "general": general_name,
                     "general_id": general_id, "from_faction": home_faction,
                     "cost": cost, "bidders": bidders, "winner": None}
            if broke:
                entry["skipped_no_funds"] = broke

            if bidders:
                for code in bidders:
                    self._player(code)["treasury"] = int(self._player(code)["treasury"]) - cost
                # 成功率平分：n 個人各 1/n，所以必定有人成功——卡片沒有寫「可能全部失敗」。
                winner = bidders[self.random.randrange(len(bidders))]
                entry["winner"] = winner
                entry["odds"] = f"1/{len(bidders)}"
                # 連人帶部隊整體歸附。將領樹與地圖住在前端，所以照既有的通道
                # 掛一筆交辦事項；後端這邊先把伺服器手上的快照改掉。
                moved = []
                for army_id, army in sorted(self._living_npc_armies(self._tactical).items()):
                    if army.get("generalId") != general_id:
                        continue
                    army["faction"] = winner
                    moved.append({"armyId": army_id, "units": dict(army.get("units") or {})})
                if isinstance(self._tactical, dict):
                    self._tactical.setdefault("generalOwners", {})[general_id] = winner
                entry["armies"] = moved
                holder = sorted(self.state["players"])[0]
                self._player(holder).setdefault("pending_frontend_effects", []).append({
                    "kind": "npc_general_recruited", "label": label,
                    "general_id": general_id, "general": general_name,
                    "from_faction": home_faction, "owner": winner, "armies": moved})
                for code in bidders:
                    self._notify(code, f"{label}：付了 ${cost}，"
                                       + (f"{general_name}率部歸附。" if code == winner
                                          else f"{general_name}投了別家，錢沒退。"))
            applied.append(entry)

        # ---- 無限期封路（15.1 閻錫山封鎖窄軌鐵路）----
        # 效果與〈崩鐵玩家〉同一份 railway_effects，差別有二：沒有回合上限、
        # 也沒有搶修攤派（修不好），解除條件是指定將領被俘或離場。
        block = payload.get("railway_permanent_block")
        if block:
            known = {line["name"] for line in self.data["strategic_map"].get("railroads", [])}
            wanted = [str(name) for name in (block.get("railways") or [])]
            if not wanted:
                raise ValueError(f"{card.get('id')} 的 railway_permanent_block 沒有指定鐵路")
            missing = [name for name in wanted if name not in known]
            if missing:
                raise ValueError(f"{card.get('id')} 點名了地圖上沒有的鐵路：{missing}")
            gate = block.get("until_general_leaves") or {}
            if gate:
                name = str(gate.get("general") or "")
                pairs = self._npc_general_index().get(name)
                if not pairs:
                    raise ValueError(
                        f"{card.get('id')} 的 until_general_leaves 點名了查無此人的將領：{name}")
                gate = {"general": name, "faction": pairs[0][0]}
            blocked = []
            for railway in wanted:
                if any(e.get("railway") == railway and self._railway_effect_active(e)
                       for e in self.state.get("railway_effects", [])):
                    continue          # 這條線已經停運了，不重複掛
                entry = {"id": f"{card.get('id')}:{self.state['turn']}:{railway}",
                         "card_id": card.get("id"), "name": label, "railway": railway,
                         "initiator": str(block.get("initiator") or ""),
                         "remaining_turns": None, "permanent": True,
                         # 修不好，所以沒有搶修費用可以攤派——不要留一個 0 元的空帳。
                         "no_repair": True, "repair_charges": {},
                         "until_general_leaves": gate or None}
                self.state.setdefault("railway_effects", []).append(entry)
                blocked.append(railway)
            if blocked:
                self._notify_all(f'{label}：' + "、".join(blocked)
                                 + "全線停擺，且無法搶修。")
            applied.append({"kind": "railway_permanent_block", "railways": blocked,
                            "until_general_leaves": gate or None})

        # ---- NPC 將領換陣營（15.5 馬福祥加入西北軍）----
        transfer = payload.get("npc_general_transfer")
        if transfer:
            name = str(transfer.get("general") or "")
            pairs = self._npc_general_index().get(name)
            if not pairs:
                raise ValueError(
                    f"{card.get('id')} 的 npc_general_transfer 點名了查無此人的將領：{name}")
            home_faction, general_id = pairs[0]
            to_faction = str(transfer.get("to_faction") or "")
            if to_faction not in self.NPC_FACTIONS:
                raise ValueError(
                    f"{card.get('id')} 的 npc_general_transfer 目標不是 NPC 陣營：{to_faction}")
            if to_faction == home_faction:
                raise ValueError(f"{card.get('id')}：{name} 本來就在 {to_faction}")
            moved = []
            for army_id, army in sorted(self._living_npc_armies(self._tactical).items()):
                if army.get("generalId") != general_id:
                    continue
                army["faction"] = to_faction
                moved.append({"armyId": army_id, "units": dict(army.get("units") or {})})
            if moved and isinstance(self._tactical, dict):
                self._tactical.setdefault("generalOwners", {})[general_id] = to_faction
            entry = {"kind": "npc_general_transfer", "general": name,
                     "general_id": general_id, "from_faction": home_faction,
                     "to_faction": to_faction, "armies": moved}

            # 移防：後端沒有座標，所以只說「搬到哪座城周邊幾格」，
            # 由前端挑格子——和列強砲擊把駐軍趕出城（evictArmyFromCity）同一個分工。
            relocate = payload.get("npc_army_relocate")
            if relocate:
                city_id = str(relocate.get("near_city") or "")
                if not any(c["id"] == city_id for c in self.data["strategic_map"]["cities"]):
                    raise ValueError(
                        f"{card.get('id')} 的 npc_army_relocate 指向不存在的城市：{city_id}")
                entry["relocate"] = {"near_city": city_id,
                                     "within": int(relocate.get("within", 1))}
            if moved:
                holder = sorted(self.state["players"])[0]
                self._player(holder).setdefault("pending_frontend_effects", []).append({
                    "kind": "npc_general_transferred", "label": label,
                    "general": name, "general_id": general_id,
                    "from_faction": home_faction, "to_faction": to_faction,
                    "armies": moved, "relocate": entry.get("relocate")})
            applied.append(entry)

        # ---- 整個 NPC 陣營歸附玩家（15.13 馬家軍歸附）----
        absorb = payload.get("npc_faction_absorb")
        if absorb:
            faction = str(absorb.get("faction") or "")
            if faction not in self.NPC_FACTIONS:
                raise ValueError(
                    f"{card.get('id')} 的 npc_faction_absorb 不是 NPC 陣營：{faction}")
            rule = str(absorb.get("to") or "highest_total_force")
            if rule != "highest_total_force":
                raise ValueError(
                    f"{card.get('id')} 的 npc_faction_absorb 用了不認得的歸屬規則：{rule}")
            winner = self._top_force_player()
            if not winner:
                applied.append({"kind": "npc_faction_absorb_skipped",
                                "reason": "no_tactical_or_no_force"})
            else:
                armies = self._hand_over_npc_armies(faction, winner)
                cities = self._npc_faction_cities(faction)
                for city_id in cities:
                    self.state["city_owners"][city_id] = winner
                self._retire_npc_faction(faction)
                self._refresh_city_income()
                holder = sorted(self.state["players"])[0]
                self._player(holder).setdefault("pending_frontend_effects", []).append({
                    "kind": "npc_faction_absorbed", "label": label,
                    "faction": faction, "owner": winner,
                    "armies": armies, "cities": cities})
                self._notify_all(f'{label}：{faction} 全軍歸附 {winner}，'
                                 f'地盤 {len(cities)} 座城一併轉屬。')
                applied.append({"kind": "npc_faction_absorb", "faction": faction,
                                "owner": winner, "armies": armies, "cities": cities,
                                "ranking": self.player_force_ranking()})

        # ---- NPC 併 NPC（15.14／15.27 黔軍遭吞併）----
        merge = payload.get("npc_faction_merge")
        if merge:
            source = str(merge.get("from_faction") or "")
            if source not in self.NPC_FACTIONS:
                raise ValueError(
                    f"{card.get('id')} 的 npc_faction_merge 來源不是 NPC 陣營：{source}")
            name = str(merge.get("into_general") or "")
            pairs = self._npc_general_index().get(name)
            if not pairs:
                raise ValueError(
                    f"{card.get('id')} 的 npc_faction_merge 點名了查無此人的將領：{name}")
            winner_faction, winner_general = pairs[0]
            if winner_faction == source:
                raise ValueError(f"{card.get('id')}：{name} 就在 {source}，併不了自己")
            living = self._living_npc_armies(self._tactical)
            target_id = next((aid for aid, army in sorted(living.items())
                              if army.get("generalId") == winner_general), None)
            absorbed, overflow = [], {}
            if target_id is None:
                applied.append({"kind": "npc_faction_merge_skipped",
                                "reason": "no_target_army", "into_general": name})
            else:
                target = living[target_id]
                units = {unit: max(0, int((target.get("units") or {}).get(unit) or 0))
                         for unit in UNIT_FORCE_POINTS}
                for army_id, army in sorted(living.items()):
                    if self._home_faction(army_id) != source:
                        continue
                    absorbed.append({"armyId": army_id,
                                     "units": dict(army.get("units") or {})})
                    for unit in UNIT_FORCE_POINTS:
                        # 併進來的兵一營一營塞，塞不下的如實記在 overflow——
                        # 單一部隊的戰力上限不因為併吞而放寬。
                        for _ in range(max(0, int((army.get("units") or {}).get(unit) or 0))):
                            if self._force_of(units) + UNIT_FORCE_POINTS[unit] > ARMY_FORCE_CAP:
                                overflow[unit] = overflow.get(unit, 0) + 1
                                continue
                            units[unit] += 1
                    army["units"] = {unit: 0 for unit in UNIT_FORCE_POINTS}
                    # 被併掉的部隊要用大家都認得的退場狀態。先前用的那個字串
                    # 前後端都沒有任何一處讀，於是黔軍的空殼部隊
                    # 頂著 0 兵繼續留在地圖上——看起來就像吞併「沒有生效」。
                    army["status"] = "destroyed"
                target["units"] = units
                cities = self._npc_faction_cities(source)
                for city_id in cities:
                    self.state["city_owners"][city_id] = winner_faction
                self._retire_npc_faction(source)
                self._refresh_city_income()
                holder = sorted(self.state["players"])[0]
                self._player(holder).setdefault("pending_frontend_effects", []).append({
                    "kind": "npc_faction_merged", "label": label,
                    "from_faction": source, "into_faction": winner_faction,
                    "into_general_id": winner_general, "into_army_id": target_id,
                    "units": dict(units), "absorbed": absorbed, "cities": cities})
                self._notify_all(f'{label}：{source} 全軍併入{name}部，'
                                 f'地盤 {len(cities)} 座城轉屬 {winner_faction}。')
                applied.append({"kind": "npc_faction_merge", "from_faction": source,
                                "into_general": name, "into_general_id": winner_general,
                                "into_army_id": target_id, "units": dict(units),
                                "absorbed": absorbed, "cities": cities,
                                "overflow": overflow})

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
            # 抽出當下已經擲過的話就沿用，否則現在擲。沿用是必要的：
            # 報紙在抽出時就依結果刊了，結算時再擲一次會和報紙說的不一樣。
            pre = ((self.state.get("pending_events") or {}).get("cards") or [{}])
            pre = next((c.get("random_outcome") for c in pre
                        if c.get("card_id") == card.get("id") and c.get("random_outcome")), None)
            if pre:
                roll = float(pre["roll"])
                chosen = next((b for b in roll_spec.get("branches") or []
                               if b.get("id") == pre["chosen"]), None)
            else:
                roll = self.random.random()
                chosen = self._pick_random_branch(roll_spec, roll)
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
            # 兩種寫法：
            #   絕對——`to_level` 指定升到第幾級（晏陽初辦學鄉村：二級升三級）。
            #   相對——`delta` 指定加幾級（NPC 那批「某某城市等級 +1」）。
            #          相對的寫法可以只點名城市（`cities`），不必整省一起動。
            provinces = set(upgrade.get("provinces") or [])
            named = [str(cid) for cid in (upgrade.get("cities") or [])]
            delta = upgrade.get("delta")
            to_level = upgrade.get("to_level")
            if delta is None and to_level is None:
                raise ValueError("city_level_upgrade 要嘛給 to_level，要嘛給 delta")
            from_level = upgrade.get("from_level")
            max_level = int(upgrade.get("max_level", 5))
            if named:
                known = {c["id"] for c in self.data["strategic_map"]["cities"]}
                unknown = [cid for cid in named if cid not in known]
                if unknown:
                    raise ValueError(f"city_level_upgrade 點名了不存在的城市：{unknown}")
            overrides = self.state.setdefault("city_level_overrides", {})
            touched = []
            for city in self.data["strategic_map"]["cities"]:
                if named and city["id"] not in named:
                    continue
                if provinces and city.get("province") not in provinces:
                    continue
                current = int(self._with_level(city).get("level", 1))
                if from_level is not None and current != int(from_level):
                    continue
                target = (min(current + int(delta), max_level)
                          if delta is not None else int(to_level))
                if current >= target:
                    continue
                overrides[city["id"]] = target
                touched.append({"id": city["id"], "name": city["name"],
                                "province": city["province"],
                                "from": current, "to": target})
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
            span = int(self._extended_duration(card, unrest.get("turns", 3), 3))
            want = int(unrest.get("cities", 2))
            min_level = int(unrest.get("min_level", 4))
            for code in targets:
                pool_cities = self._student_unrest_candidates(code, min_level)
                if not pool_cities:
                    shielded = sorted({
                        city.get("province")
                        for city in self.data["strategic_map"]["cities"]
                        if self.state["city_owners"].get(city["id"], city["faction"]) == code
                        and int(self._with_level(city).get("level", 0)) >= int(min_level)
                        and self._gang_riot_shielded(code, city.get("province"), "security_event")
                    })
                    applied.append({"kind": "student_unrest", "player": code, "cities": [],
                                    "shielded_provinces": shielded,
                                    "note": ("all qualifying cities are shielded from security events"
                                             if shielded else
                                             "no city of the required level under this player")})
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
        # ---- 有時效的 perk 加張（2.2 柏林密約）----
        # 與 card_copies 的差別：那是「往牌庫塞幾張」的一次性動作，對列強 perk 卡
        # 無效（下一次同步就被修回去）；這裡改成抬高該卡的 desired 份數，
        # 同步時就會自己補進來，到期後也會自己收回去。
        bonus_spec = payload.get("perk_copy_bonus")
        if bonus_spec:
            span = bonus_spec.get("turns", 1)
            entry = {"cards": list(bonus_spec.get("cards") or []),
                     "copies": int(bonus_spec.get("copies", 1)),
                     "until_turn": (turn + int(span)) if span is not None else None,
                     "players": list(targets) if players is not None else None,
                     "label": bonus_spec.get("label", label),
                     "source_card": card.get("id")}
            self.state.setdefault("perk_copy_bonuses", []).append(entry)
            for code in (entry["players"] or list(self.state["players"])):
                self._sync_foreign_deck_cards(code)
            applied.append(dict(kind="perk_copy_bonus", **entry))
        ban = payload.get("bank_ban")
        if ban:
            # bank：單一銀行；banks：指定幾家；all_banks：全部（13.20 洋行倒閉
            # 「所有銀行停止發出新借款」）。三者擇一，別讓漏填變成「一家都沒封」。
            if ban.get("all_banks"):
                banks = sorted(LOANS.banks)
            else:
                banks = list(ban.get("banks") or ([ban["bank"]] if ban.get("bank") else []))
            if not banks:
                raise ValueError("bank_ban 要指定 bank／banks／all_banks 其中之一")
            entry = {"bank": banks[0] if len(banks) == 1 else None, "banks": banks,
                     "until_turn": turn + int(ban.get("turns", 1)),
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
            for city_id in (city_output.get("cities") or []) + self._select_cities(
                    city_output.get("select"), targets):
                bonus = self.state.setdefault("city_development", {}).setdefault(city_id, {"cash": 0, "factory": 0})
                bonus["cash"] += int(city_output.get("cash", 0))
                bonus["factory"] += int(city_output.get("factory", 0))
                applied.append({"kind": "city_output", "city_id": city_id,
                                "cash": int(city_output.get("cash", 0)),
                                "factory": int(city_output.get("factory", 0))})
            self._refresh_city_income()
        # ---- 一次性的城市進帳／扣帳（「本回合所有租界城市金錢 +3」那一類）----
        # 與 city_output 的差別：那是每回合的永久加成，這裡是**只發生一次**。
        once = payload.get("city_output_once")
        if once:
            for code in targets:
                city_ids = self._select_cities(once.get("select"), [code]) \
                    + list(once.get("cities") or [])
                # 「我控制的城」＝ city_owners 上的現任持有者；沒被登記過的城才回退
                # 到初始陣營。原本是 `owners.get(cid) == code 或 faction == code`，
                # 城被別人打下來之後仍會算成原陣營的，改成單一判準。
                mine = [cid for cid in set(city_ids)
                        if self.state["city_owners"].get(
                            cid, (self._city_by_id(cid) or {}).get("faction")) == code]
                if not mine:
                    continue
                cash = int(once.get("cash", 0)) * len(mine)
                factory = int(once.get("factory", 0)) * len(mine)
                profile = self._player(code)
                # 玩家的錢在 treasury，不是 cash——原本寫進 profile["cash"]，
                # 而整個 engine 沒有任何地方讀那個欄位，等於這條效果一直在空轉。
                profile["treasury"] = max(0, int(profile.get("treasury", 0)) + cash)
                profile["factory_points"] = max(0, int(profile.get("factory_points", 0)) + factory)
                applied.append({"kind": "city_output_once", "player": code,
                                "cities": sorted(mine), "cash": cash, "factory": factory})

        # ---- 對「與你交惡的每一個列強」各動一次關係（列強對華聯合譴責）----
        hostile = payload.get("hostile_relations_delta")
        if hostile is not None:
            for code in targets:
                relations = self._player(code).setdefault("foreign_relations", {})
                touched = {}
                for power, value in list(relations.items()):
                    if int(value) > HOSTILE_AT_OR_BELOW:
                        continue
                    relations[power] = int(value) + int(hostile)
                    touched[power] = relations[power]
                if touched:
                    applied.append({"kind": "hostile_relations_delta", "player": code,
                                    "amount": int(hostile), "powers": touched})

        # ---- 一次性入帳（交涉卡的「一次性金錢 +10」「一次性工廠 +10」）----
        #
        # `per: "eligible_regions"` 是「控制 a、b 或 c 者獲得 $xx」那一類卡的疊加規則：
        # 收益以**每控制一個地區發一次**計算，控制三個地區就是三倍。地區清單不在
        # 這裡再抄一份——直接讀卡片 entry_condition 上那一份，永遠只有一個來源。
        grant_once = payload.get("grant")
        if grant_once:
            per_region = str(grant_once.get("per") or "") == "eligible_regions"
            for code in targets:
                profile = self._player(code)
                times = self._eligible_region_count(card, code) if per_region else 1
                cash = int(grant_once.get("cash", 0)) * times
                factory = int(grant_once.get("factory", 0)) * times
                if cash:
                    profile["treasury"] = max(0, int(profile.get("treasury", 0)) + cash)
                if factory:
                    profile["factory_points"] = max(
                        0, int(profile.get("factory_points", 0)) + factory)
                applied.append({"kind": "grant", "player": code,
                                "cash": cash, "factory": factory, "regions": times})

        # ---- 每回合的永久增減（日商設廠：工廠 +2、金錢 −2）----
        for spec in payload.get("player_output_bonus") or []:
            for code in targets:
                bonus = self._player(code).setdefault(
                    "permanent_output_bonus", {"cash": 0, "factory": 0})
                bonus["cash"] = int(bonus.get("cash", 0)) + int(spec.get("cash", 0))
                bonus["factory"] = int(bonus.get("factory", 0)) + int(spec.get("factory", 0))
                applied.append({"kind": "player_output_bonus", "player": code,
                                "cash": int(spec.get("cash", 0)),
                                "factory": int(spec.get("factory", 0))})
            self._refresh_city_income()

        # ---- 路權封鎖：拒絕交涉的代價，只罰拒絕的那一家 ----
        # 與〈崩鐵玩家〉的差別：那是全場停運，這是**只有你**不得使用該線。
        for spec in payload.get("railway_ban") or []:
            for code in targets:
                entry = {
                    "id": f"{card.get('id')}:{turn}:{code}",
                    "card_id": card.get("id"),
                    "label": spec.get("label") or label,
                    "railway": str(spec["railway"]),
                    "player": code,
                    "until_turn": turn + int(spec.get("turns", 10)),
                }
                self.state.setdefault("railway_bans", []).append(entry)
                self._notify(code, f"{entry['railway']}路權遭封鎖，"
                                   f"{int(spec.get('turns', 10))} 回合內不得使用該線運輸。")
                applied.append(dict(kind="railway_ban", **entry))

        # ---- 依租界數量攤派的一次性軍費（法國教會保護、美國護僑）----
        for spec in payload.get("levy_per_concession") or []:
            power = str(spec["power"])
            for code in targets:
                count = len(self._concession_cities(code, power))
                if not count:
                    continue
                cost = self._infantry_levy_cost(code, count)
                profile = self._player(code)
                profile["treasury"] = max(0, int(profile.get("treasury", 0)) - cost["cash"])
                profile["factory_points"] = max(
                    0, int(profile.get("factory_points", 0)) - cost["factory"])
                applied.append({"kind": "levy_per_concession", "player": code,
                                "power": power, "concessions": count, **cost})

        # ---- 永久放棄某些城市的租界加成（門戶開放照會）----
        forfeit = payload.get("concession_bonus_forfeit")
        if forfeit:
            picked = []
            for code in targets:
                picked += self._select_cities(forfeit.get("select"), [code])
            store = self.state.setdefault("concession_bonus_forfeits", [])
            for city_id in picked:
                if city_id not in store:
                    store.append(city_id)
            if picked:
                self._refresh_city_income()
                applied.append({"kind": "concession_bonus_forfeit",
                                "cities": sorted(set(picked))})

        # ---- 本回合停產（英日要求清剿工運）----
        # ---- 現金儲備按百分比損失（13.21 世界銀價波動 20%、13.22 白銀外流 10%）----
        # 與 grant 的差別：那是定額，這是比例——有錢的人賠得多，才是通膨的樣子。
        # 無條件進位：損失算給銀行，零頭不會被玩家賺走。
        loss = payload.get("treasury_percent_loss")
        if loss is not None:
            percent = float(loss.get("percent", 0)) if isinstance(loss, dict) else float(loss)
            for code in targets:
                profile = self._player(code)
                before = int(profile.get("treasury", 0))
                taken = int(math.ceil(before * percent / 100.0))
                profile["treasury"] = max(0, before - taken)
                applied.append({"kind": "treasury_percent_loss", "player": code,
                                "percent": percent, "before": before, "amount": taken})

        # ---- 有無負債走兩條路（13.23 錢莊擠兌）----
        # 「負債者債務 +10；無負債者現金 −8」——同一張卡對兩種人做不同的事，
        # 而且是逐玩家各自判定，不是全場二選一。
        debt_branch = payload.get("debt_branch")
        if debt_branch:
            for code in targets:
                profile = self._player(code)
                in_debt = bool(profile.get("loans"))
                arm = debt_branch.get("in_debt" if in_debt else "debt_free") or {}
                extra = int(arm.get("debt", 0))
                if extra and profile.get("loans"):
                    # 平均攤到每一筆未清償的借款上，湊不整除的餘數丟給第一筆。
                    per, rest = divmod(extra, len(profile["loans"]))
                    for index, item in enumerate(profile["loans"]):
                        item["principal"] = int(item.get("principal", 0)) + per + (rest if index == 0 else 0)
                cash = int(arm.get("cash", 0))
                if cash:
                    profile["treasury"] = max(0, int(profile.get("treasury", 0)) + cash)
                applied.append({"kind": "debt_branch", "player": code,
                                "in_debt": in_debt, "debt": extra, "cash": cash})

        # ---- 有時效的城市產出加減（13.26 煤礦短缺：所有城市工廠 −2，2 回合）----
        # 與 city_output 的差別：那是永久寫進 city_development 的，這一條會自己到期。
        # 掛在 city_output_effects 上跟停產／暴動共用同一套倒數。
        timed_output = payload.get("city_output_timed")
        if timed_output:
            city_ids = list(timed_output.get("cities") or []) + self._select_cities(
                timed_output.get("select"), targets)
            if not city_ids:
                # 全場所有城市：不寫 select 就是「每一座城」，別讓它安靜地什麼都沒選到。
                city_ids = [c["id"] for c in self.data["strategic_map"]["cities"]]
            self.state.setdefault("city_output_effects", []).append({
                "id": f"{card.get('id')}:{turn}",
                "card_id": card.get("id"), "name": label, "kind": "city_output_timed",
                "city_ids": sorted(set(city_ids)),
                "cash_multiplier": 1, "factory_multiplier": 1,
                "cash_delta": int(timed_output.get("cash", 0)),
                "factory_delta": int(timed_output.get("factory", 0)),
                # 事件在回合結算之前結完，本回合的 tick 還在後面，所以 +1。
                "remaining_turns": int(timed_output.get("turns", 1)) + 1,
            })
            applied.append({"kind": "city_output_timed", "cities": sorted(set(city_ids)),
                            "cash": int(timed_output.get("cash", 0)),
                            "factory": int(timed_output.get("factory", 0)),
                            "turns": int(timed_output.get("turns", 1))})
            self._refresh_city_income()

        # ---- 玩家層級的產出乘數（13.24 軍工訂單暴增：工廠產出 ×1.5，無條件進位）----
        for spec in payload.get("player_output_multiplier") or []:
            for code in targets:
                self._player(code).setdefault("output_multipliers", []).append({
                    "cash": float(spec.get("cash", 1)),
                    "factory": float(spec.get("factory", 1)),
                    "until_turn": turn + int(spec.get("turns", 1)),
                    "label": spec.get("label", label),
                })
                applied.append({"kind": "player_output_multiplier", "player": code,
                                "cash": float(spec.get("cash", 1)),
                                "factory": float(spec.get("factory", 1)),
                                "turns": int(spec.get("turns", 1))})
            self._refresh_city_income()

        # ---- 禁止特定行動（13.25 軍餉短缺：不可訓練／造船／補兵）----
        # 做成通用的：治安事件〈土匪劫道〉的「2 回合不可徵兵與造船」可以直接沿用。
        for spec in payload.get("action_ban") or []:
            entry = {
                "id": f"{card.get('id')}:{turn}",
                "card_id": card.get("id"),
                "actions": list(spec.get("actions") or []),
                "until_turn": turn + int(self._extended_duration(card, spec.get("turns", 1), 1)),
                # 一律照 targets 走。targets 本來就是「這張卡這一次的作用對象」——
                # 沒有任何門檻時它就是全場，有 eligible_only 之類的門檻時它已經
                # 縮好了。先前寫成 `players is not None`，卡片層級的 apply 一律
                # 傳 None，於是 13.25 只該罰欠餉那一家，卻把四家都禁了。
                "players": list(targets),
                "label": spec.get("label", label),
            }
            if not entry["actions"]:
                raise ValueError("action_ban 要指定 actions")
            unknown = set(entry["actions"]) - self.BANNABLE_ACTIONS
            if unknown:
                raise ValueError(f"action_ban 不認得的行動：{sorted(unknown)}")
            self.state.setdefault("action_bans", []).append(entry)
            applied.append(dict(kind="action_ban", **entry))

        # ---- 部隊嘩變（14.8 兵變）----
        # 「隨機抽選兩位玩家的隨機 2 個營預備隊脫離陣營」。抽人、抽兵種都靠亂數，
        # 而且只從**真的有兵**的兵種裡抽——照著空兵種抽會變成「嘩變了 0 個營」。
        mutiny = payload.get("reserve_mutiny")
        if mutiny:
            pool = [code for code in targets
                    if sum(int(v) for v in self._player(code)["unit_reserves"].values()) > 0]
            picks = int(mutiny.get("players", len(pool)))
            if pool and picks < len(pool):
                chosen = [pool[i] for i in sorted(self.random.sample(range(len(pool)), picks))]
            else:
                chosen = pool
            for code in chosen:
                reserves = self._player(code)["unit_reserves"]
                lost = {}
                for _ in range(int(mutiny.get("battalions", 1))):
                    available = [u for u, n in reserves.items() if int(n) > 0]
                    if not available:
                        break
                    unit = available[self.random.randrange(len(available))]
                    reserves[unit] = int(reserves[unit]) - 1
                    lost[unit] = lost.get(unit, 0) + 1
                self._player(code)["unit_reserve"] = sum(int(v) for v in reserves.values())
                applied.append({"kind": "reserve_mutiny", "player": code, "lost": lost})
                if lost:
                    self._notify(code, f'{label}：預備隊'
                                       + "、".join(f"{UNIT_NAMES.get(u, u)} {n} 營"
                                                  for u, n in sorted(lost.items()))
                                       + "脫離陣營。")

        # ---- 地方官貪腐的「放任」狀態（14.9）----
        # 沒有期限，直到下次抽到這張卡並選「整頓」才解除；放任多次會疊加。
        graft = payload.get("graft_state")
        if graft:
            for code in targets:
                profile = self._player(code)
                level = int(profile.get("graft_neglect", 0))
                if graft.get("action") == "clear":
                    profile["graft_neglect"] = 0
                    applied.append({"kind": "graft_state", "player": code,
                                    "action": "clear", "cleared_levels": level})
                else:
                    profile["graft_neglect"] = level + 1
                    applied.append({"kind": "graft_state", "player": code,
                                    "action": "neglect", "level": level + 1})
            self._refresh_city_income()

        # ---- 鐵路工人罷工（14.15）：全線停運，全場適用 ----
        # 與〈崩鐵玩家〉的差別：那是玩家指定一條線並攤派搶修費，這是罷工，
        # 由系統隨機擇一，也沒有人要付搶修費。共用同一套 railway_effects，
        # 所以「該線不能做鐵路運輸、沿線退回一般一格」那一整套不必重寫。
        strike = payload.get("railway_strike")
        if strike:
            options = list(strike.get("railways") or [])
            known = {line["name"] for line in self.data["strategic_map"].get("railroads", [])}
            unknown = [name for name in options if name not in known]
            if unknown:
                raise ValueError(f"地圖上沒有這些鐵路：{unknown}")
            busy = {e.get("railway") for e in self.state.get("railway_effects", [])}
            free = [name for name in options if name not in busy]
            if free:
                railway = free[self.random.randrange(len(free))]
                self.state.setdefault("railway_effects", []).append({
                    "id": f"{card.get('id')}:{turn}:{railway}",
                    "card_id": card.get("id"), "name": label, "railway": railway,
                    "initiator": None,
                    "remaining_turns": int(strike.get("turns", 2)) + 1,
                    "repair_factory_cost": 0, "repair_charges": {},
                })
                applied.append({"kind": "railway_strike", "railway": railway,
                                "turns": int(strike.get("turns", 2))})
            else:
                applied.append({"kind": "railway_strike", "railway": None,
                                "note": "候選路線都已經在停運中"})

        halt = payload.get("city_halt")
        if halt:
            for code in targets:
                city_ids = list(halt.get("cities") or []) \
                    + self._select_cities(halt.get("select"), [code])
                city_ids = [cid for cid in dict.fromkeys(city_ids)]
                # 「有警政單位保護者免疫」（14.2 黑幫動亂、14.5 會黨滋事）。
                if halt.get("respect_police"):
                    kept = self._drop_police_shielded(code, city_ids)
                    if len(kept) != len(city_ids):
                        applied.append({"kind": "police_immunity", "player": code,
                                        "spared": sorted(set(city_ids) - set(kept))})
                    city_ids = kept
                if not city_ids:
                    continue
                span = self._extended_duration(card, halt.get("turns", 1))
                entry = {
                    "id": f"{card.get('id')}:{turn}:{code}",
                    "card_id": card.get("id"), "name": label,
                    "kind": str(halt.get("kind", "city_halt")), "owner": code,
                    "city_ids": sorted(set(city_ids)),
                    "cash_multiplier": float(halt.get("cash_multiplier", 0)),
                    "factory_multiplier": float(halt.get("factory_multiplier", 0)),
                    # 效果在事件結算時建立，而本回合的 tick 還在後面；
                    # 不 +1 的話「本回合停產」會在生效前就被扣光。
                    # turns 為 null＝無限期（米騷動：不花錢賑濟就一直停產）。
                    "remaining_turns": (int(span) + 1) if span is not None else None,
                    "total_turns": (int(span) + 1) if span is not None else None,
                }
                # 可以花錢提前平息的，把價碼記在效果上——玩家要看得到、按得到，
                # 而不是自己記得「這張卡好像可以付 $10」。
                if halt.get("quell_cost") is not None:
                    entry["quell_cost"] = int(halt["quell_cost"])
                    entry["quell_label"] = halt.get("quell_label", label)
                self.state.setdefault("city_output_effects", []).append(entry)
                applied.append({"kind": "city_halt", "player": code,
                                "cities": sorted(set(city_ids)),
                                "quell_cost": entry.get("quell_cost"),
                                "turns": span})
            self._refresh_city_income()

        # ---- 內閣去職（四國反共聯合聲明：汪精衛與周恩來立刻離職）----
        for card_id in payload.get("dismiss_cabinet") or []:
            entry = (self.state.get("cabinet") or {}).get(card_id)
            if not entry:
                continue
            self._revoke_cabinet_card(card_id, entry)
            self.state["cabinet"].pop(card_id, None)
            applied.append({"kind": "dismiss_cabinet", "card_id": card_id})

        # ---- 清掉限時的徵兵優惠（四國反共：工農動員類加成立即失效）----
        for label_key in payload.get("clear_recruit_discounts") or []:
            for code in targets:
                profile = self._player(code)
                before = len(profile.get("timed_recruit_discounts") or [])
                profile["timed_recruit_discounts"] = [
                    e for e in profile.get("timed_recruit_discounts", [])
                    if label_key not in str(e.get("label", ""))]
                removed = before - len(profile["timed_recruit_discounts"])
                if removed:
                    applied.append({"kind": "clear_recruit_discounts", "player": code,
                                    "removed": removed})

        # ---- 生產成本乘數（軍火管制、禁運案、香港軍火交易）----
        for spec in payload.get("production_cost_multiplier") or []:
            entry = {
                "id": f"{card.get('id')}:{turn}",
                # 來源卡號：免疫（美孚石油供應）要靠它認出「這筆加價是哪張卡造成的」。
                # 從 id 反解字串也做得到，但那是把格式當資料用，改個分隔符就壞了。
                "card_id": str(card.get("id") or ""),
                "label": spec.get("label") or label,
                "arms": list(spec.get("arms") or ["ground"]),
                "cash": float(spec.get("cash", 1)),
                "factory": float(spec.get("factory", 1)),
                "until_turn": turn + int(spec.get("turns", 3)),
                # scope=self 只罰打出／抽到的那幾家；不寫就是全場適用。
                "players": list(targets) if spec.get("scope") == "self" else None,
            }
            self.state.setdefault("production_cost_multipliers", []).append(entry)
            applied.append(dict(kind="production_cost_multiplier", **entry))

        # ---- 事件驅動的城市暴動（共產國際大革命、赤色工運滲透）----
        # 與功能卡〈紅軍起義〉〈洪門起義〉共用 city_output_effects，
        # 所以平息條件、產出歸零、前端回報駐軍那一整套都不必重寫。
        for spec in payload.get("city_riot") or []:
            for code in targets:
                applied.append({"kind": "city_riot", "player": code,
                                **self._open_event_riot(code, spec, card)})

        # 把某張功能卡從指定玩家的手牌／牌庫／棄牌堆整個清掉。
        # 用得到它的只有中央研究院清〈中國人之恥〉，而那段自己寫了一份清除迴圈，
        # 於是這條通用路徑沒有任何卡片走得到。現在改成共用同一份實作：
        # academia_grant 那段呼叫 _purge_card_everywhere，這裡也是。
        for card_id in payload.get("clear_cards") or []:
            for code in targets:
                removed = self._purge_card_everywhere(code, card_id)
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
                    for card_id in ("national_shame",):
                        removed = self._purge_card_everywhere(code, card_id)
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
                    "field_deltas": dict(override.get("field_deltas") or {}),
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
                    "remaining_turns": (int(flag["turns"]) + self._event_duration_bonus(card)
                                        if flag.get("turns") is not None else None),
                    "permanent": flag.get("turns") is None,
                    "owners": [code],
                }
                entry.update({key: value for key, value in flag.items()
                              if key not in ("kind", "turns", "label", "select")})
                # select：讓凍結範圍與同一張卡的停產範圍**由同一個條件算出來**。
                # 水患卡若把城市名單抄第二份，兩份總有一天會對不上——
                # 停產 11 座、凍結 10 座，而且沒有任何東西會叫。
                if flag.get("select"):
                    entry["cities"] = sorted(self._select_cities(flag["select"], [code]))
                # random_provinces：從這位玩家實際有城的省份裡隨機挑幾省
                # （14.14 地方自治運動：各有隨機一省 2 回合不可補充兵力）。
                # 挑不到就不掛旗標，而不是掛一個空的（空的 provinces 代表全境）。
                if flag.get("random_provinces"):
                    owned = sorted({
                        city["province"] for city in self.data["strategic_map"]["cities"]
                        if self.state["city_owners"].get(city["id"], city["faction"]) == code})
                    want = min(int(flag["random_provinces"]), len(owned))
                    if not want:
                        continue
                    entry["provinces"] = [owned[i] for i in sorted(
                        self.random.sample(range(len(owned)), want))]
                entry["granted_this_turn"] = True
                self._player(code).setdefault("timed_effects", []).append(deepcopy(entry))
                applied.append({"kind": "timed_flag", "player": code, "flag": flag["kind"]})
        # 限時的徵兵成本折抵（火燒紅蓮寺）。
        discount = payload.get("recruit_discount")
        if discount:
            for code in targets:
                entry = {
                    "units": dict(discount.get("units") or {}),
                    "cash_override": dict(discount.get("cash_override") or {}),
                    "until_turn": turn + int(discount.get("turns", 1)),
                    # 卡片可以自己指定標籤，好讓別張卡（四國反共）點名清掉它。
                    "label": discount.get("label") or label,
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

        # ---- 列強懲戒（佔領／封鎖／轟炸）與演習 ----------------------------
        # 卡片只宣告「哪一國、哪一類、範圍」，佔領、解除、傷害、復工全在
        # foreign_punishment.PunishmentBook 裡，三類共用同一套骨架。
        for spec in payload.get("foreign_punishment") or []:
            for code in targets:
                entry = self.punishments.open(
                    card_id=str(card.get("id")),
                    power=str(spec["power"]),
                    kind=str(spec["kind"]),
                    owner=code,
                    provinces=spec.get("provinces") or [],
                    waters=spec.get("waters") or [],
                    city_count=int(spec.get("cities", 5)),
                    drill_turns=spec.get("drill_turns"),
                    label=spec.get("label") or label,
                )
                applied.append({"kind": "foreign_punishment", "player": code,
                                "punishment": entry})

        # ---- 列強派來的刺客：對被懲戒方的大帥動手 --------------------------
        # 骰子在抽出當下就擲過了（報紙照那個結果刊），這裡沿用同一個結果；
        # 真正把人從將領樹上抹掉是前端的事，所以掛進 pending_frontend_effects。
        for spec in payload.get("assassinate_marshal") or []:
            for code in targets:
                outcome = None
                for pending in ((self.state.get("pending_events") or {}).get("cards") or []):
                    if pending.get("card_id") == card.get("id") and pending.get("assassination"):
                        outcome = pending["assassination"]
                        break
                if outcome is None:
                    marshal_id = (self.state.get("marshal_ids") or {}).get(code)
                    if not marshal_id:
                        applied.append({"kind": "assassinate_marshal", "player": code,
                                        "skipped": "no_marshal_reported"})
                        continue
                    outcome = self._resolve_assassination(
                        str(spec.get("power", "")),
                        {"id": card.get("id"), "name": card.get("name"),
                         "success_rate": float(spec.get("success_rate", 0.2))},
                        marshal_id, code)
                    outcome["power"] = spec.get("power")
                self._notify(code, "遭遇暗殺：得手，該人物身亡。"
                             if outcome.get("success") else "遭遇暗殺：未得手。")
                if outcome.get("success"):
                    self._player(code).setdefault("pending_frontend_effects", []).append({
                        "kind": "general_death", "label": label,
                        "general_id": outcome["target_general_id"], "owner": code,
                        "marshal": True, "power": spec.get("power"),
                    })
                applied.append({"kind": "assassinate_marshal", "player": code,
                                "assassination": outcome})

        # ---- 爆破鐵路 ------------------------------------------------------
        # 效果與功能卡〈崩鐵玩家〉相同（同一份 railway_effects），差別在搶修攤派：
        # 這是懲戒，所以工業點由**被懲戒方全額支付**，其他玩家一毛不出。
        for spec in payload.get("railway_sabotage") or []:
            for code in targets:
                applied.append({"kind": "railway_sabotage", "player": code,
                                **self._sabotage_railway_as_punishment(code, spec, card)})

        # ---- 最後通牒 ----------------------------------------------------
        # 抽出後 5 回合內要派部隊到指定城市周邊一格駐紮至少 1 回合。
        # 卡上沒寫城市名單就用該國的預設名單（foreign_pressure.ULTIMATUM_CITIES）。
        for spec in payload.get("ultimatum") or []:
            for code in targets:
                entry = self.ultimatums.open(
                    card_id=str(card.get("id")),
                    power=str(spec["power"]),
                    owner=code,
                    cities=spec.get("cities"),
                    turns=int(spec.get("turns", 5)),
                )
                applied.append({"kind": "ultimatum", "player": code, "ultimatum": entry})

        # ---- 租界管制 ----------------------------------------------------
        for spec in payload.get("concession_control") or []:
            for code in targets:
                entry = self.concession_controls.open(
                    card_id=str(card.get("id")), power=str(spec["power"]), owner=code)
                applied.append({"kind": "concession_control", "player": code,
                                "control": entry})
        if payload.get("concession_control"):
            self._refresh_city_income()

        # 事件卡持續時間加碼（火燒紅蓮寺：期間抽到的 [幫會] 事件卡多撐 1 回合）。
        # 標籤比對走 _event_tags()，所以日後只要有卡掛上 [幫會] 就自動生效，
        # 這裡不必再改。目前資料檔還沒有 [幫會] 卡，機制先備著。
        duration = payload.get("event_duration_bonus")
        if duration:
            entry = {
                "tags": list(duration.get("tags") or []),
                "bonus": int(duration.get("amount", 1)),
                "until_turn": turn + int(duration["turns"]) if duration.get("turns") else None,
                "label": label,
            }
            self.state.setdefault("event_duration_bonuses", []).append(entry)
            applied.append(dict(kind="event_duration_bonus", **entry))

        # 省份免疫暴動類功能卡（殷墟第一鏟的「科學發掘」：民心所繫，該省三回合不生亂）。
        # 沿用〈警政單位〉那一套 gang_riot_shield，差別只在這裡是事件卡發的、
        # 而且封鎖的機制清單比較寬。
        for shield in payload.get("province_riot_shield") or []:
            province = str(shield.get("province") or "").strip()
            blocked = list(shield.get("blocked_mechanics")
                           or ["qing_gang_riot", "communist_riot", "red_army_uprising"])
            span = int(shield.get("turns", 3))
            for code in targets:
                quelled = [effect for effect in self.state.get("city_output_effects", [])
                           if effect.get("kind") in blocked
                           and effect.get("target_owner") == code
                           and effect.get("province") == province]
                if quelled:
                    self.state["city_output_effects"] = [
                        e for e in self.state["city_output_effects"] if e not in quelled]
                    self._refresh_city_income()
                entry = {
                    "id": f"{card.get('id')}:{turn}:{code}:{province}",
                    "name": shield.get("label") or label,
                    "kind": "gang_riot_shield",
                    "owner": code,
                    "province": province,
                    "blocked_mechanics": blocked,
                    "remaining_turns": span,
                }
                entry["granted_this_turn"] = True
                self._player(code).setdefault("timed_effects", []).append(deepcopy(entry))
                applied.append({"kind": "province_riot_shield", "player": code,
                                "province": province, "turns": span,
                                "blocked_mechanics": blocked,
                                "quelled_count": len(quelled)})

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
            # 舊格式只有 bank（單一），新格式是 banks（清單，可為全部銀行）。
            banks = entry.get("banks") or ([entry["bank"]] if entry.get("bank") else [])
            if bank_id not in banks:
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
        # 譴責卡照關係好壞進出牌庫，不再受買辦影響。
        # 買辦的免疫已經改成作用在**事件卡的 [懲戒]** 上（見 _comprador_deflects），
        # 原本「少抽幾張譴責」那一套整個拿掉了——同一個技能不該有兩處作用。
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

    def set_faction_trait_holders(self, holders: Dict[str, Iterable[str]]) -> Dict[str, Any]:
        """前端每回合回報「哪些陣營層級技能還有活著的持有者」，這裡對帳。

        為什麼要對帳而不是等一則「某某陣亡」的事件：將領的生死與歸屬只有前端
        知道（將領樹是前端的資料），而後端的 faction_general_traits 原本只在
        apply_general_join 時被動更新——**將領陣亡它完全收不到消息**。
        於是張宗昌被暗殺身亡之後，奉系照樣享有 10% 的日本懲戒免疫；
        劉湘死了，四川每座城照樣每回合 +1；何鍵死了，剿共照樣生效。

        改成每回合整份對帳，漏送一次下回合也自己修得回來。只認得 FACTION_LEVEL_TRAITS
        裡的技能——前端送來別的東西一律忽略，免得把戰場技能誤記成陣營技能。
        """
        clean: Dict[str, list] = {}
        for faction, traits in (holders or {}).items():
            if faction not in self.state.get("players", {}):
                continue
            kept = sorted({str(t) for t in (traits or []) if str(t) in FACTION_LEVEL_TRAITS})
            if kept:
                clean[faction] = kept
        before = deepcopy(self.state.get("faction_general_traits", {}))
        self.state["faction_general_traits"] = clean
        lost = {faction: sorted(set(traits) - set(clean.get(faction, [])))
                for faction, traits in before.items()
                if set(traits) - set(clean.get(faction, []))}
        if lost:
            self._refresh_city_income()      # 地方財源沒了，收入要跟著掉
        return {"holders": clean, "lost": lost}

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

    def _ports_in_waters(self, player: str, waters: Iterable[str]) -> int:
        """這位玩家控制幾座貼著這些水域的港市。水域歸屬與懲戒引擎同一套。"""
        wanted = set(waters)
        if not wanted:
            return 0
        total = 0
        for city in self.data["strategic_map"]["cities"]:
            if self.state["city_owners"].get(city["id"], city["faction"]) != player:
                continue
            if set(waters_for_city(city)) & wanted:
                total += 1
        return total

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
                # 增量式改寫（商約的「每次貿易 +15」）：可以與別張卡的加成疊加，
                # 不像 fields 是後寫的蓋掉先寫的。
                for field, amount in (override.get("field_deltas") or {}).items():
                    card[field] = int(card.get(field, 0)) + int(amount)
        return card
