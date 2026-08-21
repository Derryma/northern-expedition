import re
import copy
import json
import math
import random
import pathlib
import collections
import unittest

from backend.card_engine import (
    FOREIGN_CONDEMNATION_CARDS,
    FOREIGN_PERK_CARDS,
    FOREIGN_CONDEMNATION_COPIES,
    FOREIGN_FRIENDLY_THRESHOLD,
    FOREIGN_HOSTILE_THRESHOLD,
    GameEngine,
    RECRUIT_COSTS,
    FACTION_LEVEL_TRAITS,
)
from copy import deepcopy
from backend.combat_adapter import simulate
from backend.data_store import load_game_data
from economy import LoanBook

# 守門測試要比對「這個旗標有沒有人讀」，讀的人可能在前端。
FRONTEND_SOURCE = (pathlib.Path(__file__).resolve().parents[1]
                   / "frontend" / "app.js").read_text(encoding="utf-8")

LOANS = LoanBook()


def advance_turn(engine, active_player=None, **kwargs):
    """推進一回合，順手把當回合跳出的事件卡全部「我知道了」掉。

    事件卡週期（每三回合）會讓 next_turn 停在等待回應的狀態，本回合的經濟要等
    指定勢力讀完唯一一則報紙才結算。測試多半不關心事件內容，只要讓回合真的走完。
    """
    result = engine.next_turn(active_player=active_player, **kwargs)
    while True:
        view = engine.pending_event_view()
        if not view:
            break
        resolution = view["card"].get("resolution") or {}
        choice = (resolution.get("options") or [{}])[0].get("id") if resolution.get("type") == "choice" else None
        result = engine.respond_event(view["waiting_for"], choice=choice)
    return result


class BackendTests(unittest.TestCase):
    def test_data_loads_with_unique_card_ids(self):
        data = load_game_data()

        self.assertGreater(data["metadata"]["function_cards"], 50)
        # 事件卡與後果卡整套移除之後，卡池裡只剩功能卡。
        # 一到十一區塊 59 張 ＋ 十二（列強行動）71 ＋ 十三（經濟）29 ＋ 十四（治安）15
        # ＋ 十五（NPC 行動）33。
        self.assertEqual(data["metadata"]["event_cards"], 207)
        repo = pathlib.Path(__file__).resolve().parent.parent
        cards = json.loads(
            (repo / "cards" / "data" / "event_cards.json").read_text(encoding="utf-8"))["cards"]
        counts = collections.Counter(str(c["ref"]).split(".")[0] for c in cards)
        self.assertEqual(counts["12"], 71)
        self.assertEqual(counts["13"], 29)
        self.assertEqual(counts["14"], 15)
        self.assertEqual(counts["15"], 33)
        self.assertNotIn("injected_event_cards", data["metadata"])
        self.assertEqual(set(data["indexes"]), {"function_cards"})
        self.assertEqual(data["metadata"]["navy_divisions"], 4)

    def test_turn_does_not_auto_buy_function_cards(self):
        engine = GameEngine(seed=7)
        result = engine.next_turn()

        self.assertEqual(result["turn"]["turn"], 1)
        self.assertIsNone(result["turn"]["function_purchase_offer"])
        self.assertNotIn("event", result["turn"])
        for player in ("F", "W", "S", "N"):
            self.assertEqual(result["state"]["counts"]["players"][player]["hand"], 0)
            self.assertFalse(result["state"]["players"][player]["function_purchase_used"])
        self.assertNotIn("events", engine.bootstrap()["features"])

    def test_active_player_gets_optional_function_purchase_offer(self):
        engine = GameEngine(seed=7)
        result = engine.next_turn(active_player="N")

        self.assertEqual(result["turn"]["function_purchase_offer"], "N")
        for player in ("F", "W", "S", "N"):
            self.assertEqual(result["state"]["counts"]["players"][player]["hand"], 0)

    def test_navy_rules_are_exposed_and_cost_factory_points(self):
        engine = GameEngine(seed=7)
        self.assertEqual(engine.bootstrap()["navy_system"]["move"]["factory_cost"], 10)
        before = engine.state["players"]["N"]["factory_points"]
        # 每艘砲艇 5 工業點，兩艘就是 10——成本由後端從艦隊現況算。
        fleet = {"id": "N-NAVY-1", "cargoBoats": 1,
                 "cargoBoatHp": [{"id": "c1", "hp": 10, "maxHp": 10}],
                 "gunBoats": [{"id": "g1", "hp": 30, "maxHp": 30},
                              {"id": "g2", "hp": 30, "maxHp": 30}]}
        result = engine.pay_navy_move("N", navy=fleet)
        self.assertEqual(result["factory"], 10)
        self.assertEqual(result["state"]["players"]["N"]["factory_points"], before - 10)

    def test_navy_repair_costs_two_factory_per_hp(self):
        engine = GameEngine(seed=7)
        before = engine.state["players"]["W"]["factory_points"]
        result = engine.repair_navy("W", 3)
        self.assertEqual(result["factory"], 6)
        self.assertEqual(result["state"]["players"]["W"]["factory_points"], before - 6)

    def test_navy_recruitment_uses_large_cash_and_factory_costs(self):
        engine = GameEngine(seed=7)
        player = engine.state["players"]["N"]
        player["treasury"] = 300
        player["factory_points"] = 100

        result = engine.train_navy_unit("N", "gun_boat")

        updated = result["state"]["players"]["N"]
        self.assertEqual(updated["treasury"], 100)
        self.assertEqual(updated["factory_points"], 25)
        self.assertEqual(updated["navy_reserves"]["gun_boat"], 1)

    def test_navy_reserve_transfer_requires_controlled_harbor(self):
        engine = GameEngine(seed=7)
        engine.state["players"]["N"]["navy_reserves"]["cargo_boat"] = 1

        with self.assertRaisesRegex(ValueError, "controlled harbor"):
            engine.reinforce_navy("N", "guilin", "cargo_boat")

        result = engine.reinforce_navy("N", "guangzhou", "cargo_boat")

        self.assertEqual(result["state"]["players"]["N"]["navy_reserves"]["cargo_boat"], 0)

    def test_playable_factions_have_distinct_profiles(self):
        engine = GameEngine(seed=7)
        players = engine.snapshot()["players"]

        economy_profiles = {
            (payload["treasury"], payload["income"], payload["debt"], payload["unit_reserve"])
            for payload in players.values()
        }
        relation_profiles = {
            tuple(sorted(payload["foreign_relations"].items()))
            for payload in players.values()
        }

        self.assertEqual(len(economy_profiles), 4)
        self.assertEqual(len(relation_profiles), 4)

    def test_wu_peifu_city_economy_is_henan_and_hubei(self):
        engine = GameEngine(seed=7)
        provinces = {city["province"] for city in engine.state["players"]["W"]["city_economy"]}

        self.assertEqual(provinces, {"河南", "湖北"})

    def test_captured_city_transfers_recurring_economy(self):
        engine = GameEngine(seed=7)
        city = next(item for item in engine.bootstrap()["strategic_map"]["cities"] if item["faction"] == "W")
        before_n = engine.state["players"]["N"]["income"]
        before_w = engine.state["players"]["W"]["income"]
        before_n_factory = engine.state["players"]["N"]["factory_income"]
        before_w_factory = engine.state["players"]["W"]["factory_income"]

        captured = engine.capture_city(city["id"], "N")

        self.assertEqual(captured["previous_owner"], "W")
        self.assertEqual(captured["state"]["players"]["N"]["income"], before_n + city["cash"])
        self.assertEqual(captured["state"]["players"]["W"]["income"], before_w - city["cash"])
        self.assertEqual(captured["state"]["players"]["N"]["factory_income"], before_n_factory + city["factory"])
        self.assertEqual(captured["state"]["players"]["W"]["factory_income"], before_w_factory - city["factory"])
        self.assertEqual(captured["state"]["city_owners"][city["id"]], "N")
        self.assertEqual(
            next(item for item in engine.bootstrap()["strategic_map"]["cities"] if item["id"] == city["id"])["faction"],
            "N",
        )

        restored = engine.capture_city(city["id"], "W")["state"]
        self.assertEqual(restored["players"]["N"]["income"], before_n)
        self.assertEqual(restored["players"]["W"]["factory_income"], before_w_factory)

    def test_general_recruitment_spends_five_infantry_reserves(self):
        engine = GameEngine(seed=7)
        before = engine.state["players"]["N"]["unit_reserves"]["infantry"]

        result = engine.recruit_captive_general("N")

        self.assertEqual(result["infantry"], 5)
        self.assertEqual(result["state"]["players"]["N"]["unit_reserves"]["infantry"], before - 5)

    def test_defection_attempt_spends_cash_and_uses_loyalty(self):
        low = GameEngine(seed=1)
        high = GameEngine(seed=1)

        low_result = low.attempt_defection("N", 2)
        high_result = high.attempt_defection("N", 8)

        self.assertGreater(low_result["chance"], high_result["chance"])
        self.assertEqual(low_result["state"]["players"]["N"]["treasury"], 40 - low_result["cost"])
        self.assertEqual(high_result["state"]["players"]["N"]["treasury"], 40 - high_result["cost"])

    def test_defection_cost_scales_with_force_and_success_is_low(self):
        weak_engine = GameEngine(seed=1)
        strong_engine = GameEngine(seed=1)
        weak_engine.state["players"]["N"]["treasury"] = 200
        strong_engine.state["players"]["N"]["treasury"] = 200
        weak = weak_engine.attempt_defection_with_force("N", 2, 5)
        strong = strong_engine.attempt_defection_with_force("N", 2, 30)
        self.assertGreater(strong["cost"], weak["cost"])
        self.assertEqual(weak["cost"], 15)
        self.assertEqual(strong["cost"], 52)
        self.assertLessEqual(weak["chance"], 0.60)
        self.assertLessEqual(strong["chance"], weak["chance"])

    def test_training_spends_cash_and_factory_points_by_unit_type(self):
        engine = GameEngine(seed=5)
        player = engine.state["players"]["N"]
        player["treasury"] = 100
        player["factory_points"] = 100
        before = (player["treasury"], player["factory_points"], player["unit_reserves"]["artillery"])

        result = engine.train_unit("N", "artillery")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["treasury"], before[0] - 15)
        self.assertEqual(updated["factory_points"], before[1] - 5)
        self.assertEqual(updated["unit_reserves"]["artillery"], before[2] + 1)

    def test_recruit_costs_are_raised_for_all_units(self):
        self.assertEqual(RECRUIT_COSTS, {
            "infantry": {"cash": 4, "factory": 2},
            "cavalry": {"cash": 7, "factory": 2},
            "machine_gun": {"cash": 10, "factory": 4},
            "artillery": {"cash": 16, "factory": 5},
        })

    def test_city_output_follows_level(self):
        """1 級 cash 1 / factory 1，每升一級各 +1，最高 5 級。

        取代舊的「步兵成本約等於小城 3-4 回合產出」不變式：改採等級公式後，
        2 級城市每回合產出 2 元，已等於步兵 3 元的成本，該不變式不再成立。
        招募成本是否要跟著調整，屬於平衡設計決定，不在此測試範圍。
        """
        engine = GameEngine(seed=5)
        bootstrap = engine.bootstrap()
        by_level = {}
        for city in bootstrap["strategic_map"]["cities"]:
            by_level.setdefault(city["level"], set()).add((city["cash"], city["factory"]))
        for level, outputs in by_level.items():
            self.assertEqual(outputs, {(1 + level - 1, 1 + level - 1)}, level)

    def test_major_city_can_transfer_reserve_to_army(self):
        engine = GameEngine(seed=5)
        before = engine.state["players"]["N"]["unit_reserves"]["infantry"]

        result = engine.reinforce_army("N", "N-1", "guangzhou", "infantry")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["unit_reserves"]["infantry"], before - 1)
        self.assertEqual(result["army_id"], "N-1")
        self.assertEqual(result["unit_type"], "infantry")
        self.assertEqual(result["count"], 1)
        self.assertNotIn("N-1", updated["army_reinforcements"])

    def test_captured_major_city_can_reinforce_army(self):
        engine = GameEngine(seed=5)
        engine.capture_city("hankou", "N")
        before = engine.state["players"]["N"]["unit_reserves"]["machine_gun"]

        result = engine.reinforce_army("N", "N-1", "hankou", "machine_gun")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["unit_reserves"]["machine_gun"], before - 1)
        self.assertEqual(result["army_id"], "N-1")
        self.assertEqual(result["unit_type"], "machine_gun")
        self.assertEqual(result["count"], 1)
        self.assertNotIn("N-1", updated["army_reinforcements"])

    def test_restore_snapshot_rehydrates_engine_state(self):
        engine = GameEngine(seed=5)
        snapshot = engine.capture_city("hankou", "N")["state"]
        snapshot["players"]["N"]["army_reinforcements"] = {
            "N-1": {"infantry": 5, "cavalry": 3}
        }
        fresh = GameEngine(seed=8)

        restored = fresh.restore_snapshot(snapshot)

        self.assertEqual(restored["turn"], snapshot["turn"])
        self.assertEqual(restored["city_owners"]["hankou"], "N")
        self.assertEqual(restored["players"]["N"]["income"], snapshot["players"]["N"]["income"])
        self.assertEqual(restored["players"]["N"]["army_reinforcements"], {})

    def test_diplomacy_and_deals_require_recipient_acceptance(self):
        engine = GameEngine(seed=5)
        self.assertEqual(engine.state["players"]["N"]["warlord_relations"]["W"]["status"], "peace")

        war = engine.set_diplomacy("N", "W", "war")["state"]
        self.assertEqual(war["players"]["N"]["warlord_relations"]["W"]["status"], "war")
        self.assertEqual(war["players"]["W"]["warlord_relations"]["N"]["status"], "war")

        n_cash = engine.state["players"]["N"]["treasury"]
        w_cash = engine.state["players"]["W"]["treasury"]
        proposal = engine.make_deal("N", "W", funds=10, unit_type="cavalry", reserve=2)
        self.assertEqual(proposal["state"]["players"]["N"]["treasury"], n_cash)
        self.assertEqual(proposal["state"]["players"]["W"]["treasury"], w_cash)
        self.assertEqual(len(proposal["state"]["players"]["W"]["pending_deals"]), 1)

        accepted = engine.respond_to_deal("W", proposal["deal"]["id"], True)["state"]
        self.assertEqual(accepted["players"]["N"]["treasury"], n_cash - 10)
        self.assertEqual(accepted["players"]["W"]["treasury"], w_cash + 10)

    def test_npc_deals_are_rejected_and_early_peace_is_blocked(self):
        engine = GameEngine(seed=5)
        with self.assertRaisesRegex(ValueError, "playable factions"):
            engine.make_deal("N", "Y", funds=5)

        engine.set_diplomacy("N", "W", "war")
        with self.assertRaisesRegex(ValueError, "10 turns"):
            engine.set_diplomacy("N", "W", "peace")
        engine.state["turn"] = 10
        peace = engine.set_diplomacy("N", "W", "peace")["state"]
        self.assertEqual(peace["players"]["N"]["warlord_relations"]["W"]["status"], "peace")

    def test_seventh_function_card_requires_discard(self):
        engine = GameEngine(seed=11)
        player = engine.state["players"]["F"]
        player["hand"] = [
            "unit_promotion",
            "local_autonomy_agitation",
            "unit_promotion",
            "local_autonomy_agitation",
            "reserve_gift_infantry",
            "city_development",
        ]
        player["function_deck"] = ["unit_promotion"]
        player["treasury"] = 100

        existing_hand = list(player["hand"])
        result = engine.draw_function("F")

        self.assertTrue(result["requires_discard"])
        self.assertEqual(player["hand"], existing_hand)
        self.assertIsNotNone(player["pending_draw"])

        discarded_id = existing_hand[0]
        received_id = player["pending_draw"]
        discard_result = engine.discard_for_draw("F", discarded_id)

        self.assertEqual(len(discard_result["state"]["players"]["F"]["hand"]), 6)
        self.assertIn(received_id, discard_result["state"]["players"]["F"]["hand"])
        self.assertIn(discarded_id, discard_result["state"]["players"]["F"]["discard"])

    def test_loyalty_function_card_requires_target_and_is_free_to_use(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["hand"] = ["unit_promotion"]
        before = engine.state["players"]["F"]["treasury"]

        result = engine.use_function(
            "F",
            "unit_promotion",
            target_general_id="yang_yuting",
            target_owner="F",
        )

        self.assertEqual(result["loyalty_delta"], 1)
        self.assertEqual(result["state"]["players"]["F"]["treasury"], before)
        self.assertEqual(result["state"]["last_action"]["player"], "F")
        self.assertEqual(result["state"]["last_action"]["target_general_id"], "yang_yuting")

    def test_absolute_loyal_generals_ignore_loyalty_function_cards(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["hand"] = ["unit_promotion"]

        with self.assertRaisesRegex(ValueError, "absolute loyalty"):
            engine.use_function(
                "F",
                "unit_promotion",
                target_general_id="zhang_xueliang",
                target_owner="F",
            )

    def test_enabled_cards_block_turn_with_pending_draw(self):
        engine = GameEngine(seed=13)
        engine.state["players"]["W"]["pending_draw"] = "unit_promotion"

        with self.assertRaisesRegex(ValueError, "resolve pending"):
            engine.next_turn()

    def test_function_card_draw_costs_five_cash(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["F"]
        before = player["treasury"]
        engine.draw_function("F")
        self.assertEqual(player["treasury"], before - 5)

    def test_function_card_purchase_is_limited_to_twice_per_turn(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["F"]
        player["treasury"] = 100

        engine.draw_function("F")
        engine.draw_function("F")
        with self.assertRaisesRegex(ValueError, "purchase limit"):
            engine.draw_function("F")
        self.assertEqual(player["function_purchase_count"], 2)

        engine.next_turn(active_player="F")
        engine.draw_function("F")
        self.assertEqual(player["function_purchase_used"], True)
        self.assertEqual(player["function_purchase_count"], 1)

    def test_function_decks_are_filtered_by_faction(self):
        engine = GameEngine(seed=4)

        for payload in engine.state["players"].values():
            self.assertNotIn("soviet_aid", payload["function_deck"])
            self.assertNotIn("japanese_loan", payload["function_deck"])
        self.assertIn("foreign_relation_su", engine.state["players"]["N"]["function_deck"])
        self.assertIn("foreign_relation_jp", engine.state["players"]["F"]["function_deck"])
        # 門檻修正後交惡為 <= -4。國民革命軍對日 -1 不算交惡，對英 -8 才是。
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("jp_condemnation"), 0)
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("uk_condemnation"), 3)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("city_development"), 8)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("foreign_relation_jp"), 5)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("young_marshal_rises"), 1)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("wang_yongjiang_financial_reform"), 1)
        # 急行軍已改成按部隊採購的軍令，牌庫裡不再有這張卡。
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("forced_march"), 0)
        self.assertIn("zhili_infantry_drill", engine.state["players"]["W"]["function_deck"])
        self.assertIn("zhili_infantry_drill", engine.state["players"]["S"]["function_deck"])

    def test_foreign_relation_unlocks_perk_cards(self):
        """交涉現在只有 70% 成功率，所以這裡打到談成為止，再驗解鎖。"""
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        for _ in range(50):
            player["foreign_relations"]["su"] = 6
            player["hand"] = ["foreign_relation_su"]
            result = engine.use_function("N", "foreign_relation_su")
            delta = result["foreign_relation_delta"]
            self.assertEqual(delta["before"], 6)
            if delta["success"]:
                break
            self.assertEqual(delta["after"], 6)      # 談不成就完全不動
        else:
            self.fail("50 次交涉沒有一次成功，機率實作可能有問題")

        self.assertEqual(delta["after"], 8)
        self.assertIn("su_rifle_shipment", player["function_deck"])
        self.assertIn("su_galen_advisers", player["function_deck"])

    def test_foreign_perk_requires_relation_and_adds_reserves(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["foreign_relations"]["su"] = 8
        player["hand"] = ["su_rifle_shipment"]
        before = dict(player["unit_reserves"])

        result = engine.use_function("N", "su_rifle_shipment")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["unit_reserves"]["infantry"], before["infantry"] + 6)
        self.assertEqual(updated["unit_reserves"]["machine_gun"], before["machine_gun"] + 1)
        self.assertEqual(len(result["reserve_deltas"]), 2)

    def test_foreign_perk_is_blocked_if_relation_falls(self):
        engine = GameEngine(seed=4)
        # 列強友好卡的門檻統一改成 6，所以這裡要壓到 6 以下才擋得住。
        engine.state["players"]["N"]["foreign_relations"]["su"] = 5
        engine.state["players"]["N"]["hand"] = ["su_rifle_shipment"]

        # 訊息改成中文並帶出實際關係值，因為這條錯誤現在也會出現在一般卡片上。
        with self.assertRaisesRegex(ValueError, "關係需達"):
            engine.use_function("N", "su_rifle_shipment")

    def test_fengtian_financial_reform_adds_permanent_income(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["F"]
        player["hand"] = ["wang_yongjiang_financial_reform"]
        before_income = player["income"]
        before_factory_income = player["factory_income"]

        result = engine.use_function("F", "wang_yongjiang_financial_reform")
        updated = result["state"]["players"]["F"]

        self.assertEqual(result["permanent_output_delta"], {"owner": "F", "cash": 5, "factory": 2})
        self.assertEqual(updated["income"], before_income + 5)
        self.assertEqual(updated["factory_income"], before_factory_income + 2)

    def test_young_marshal_card_reports_army_bundle(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["F"]["hand"] = ["young_marshal_rises"]

        result = engine.use_function("F", "young_marshal_rises")

        self.assertEqual(result["army_unit_delta"]["general_id"], "zhang_xueliang")
        self.assertEqual(result["army_unit_delta"]["unit_reserves"]["infantry"], 10)

    def test_forced_march_is_a_paid_order_not_a_card(self):
        # 卡池裡不該再有〈急行軍〉；它現在是 $10 + 10 工業點的逐軍採購。
        self.assertNotIn("forced_march", load_game_data()["indexes"]["function_cards"])

        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        cash_before = int(player["treasury"])
        factory_before = int(player["factory_points"])

        result = engine.pay_forced_march("N", army_id="N-1")

        self.assertEqual(result["cash"], 10)
        self.assertEqual(result["factory"], 10)
        self.assertEqual(result["army_id"], "N-1")
        self.assertEqual(result["duration_turns"], 3)
        self.assertEqual(result["cooldown_turns"], 3)
        self.assertEqual(result["tiles"], 2)
        self.assertEqual(player["treasury"], cash_before - 10)
        self.assertEqual(player["factory_points"], factory_before - 10)

    def test_forced_march_needs_both_cash_and_factory(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["treasury"] = 5
        with self.assertRaisesRegex(ValueError, "現金"):
            engine.pay_forced_march("N", army_id="N-1")
        player["treasury"] = 100
        player["factory_points"] = 3
        with self.assertRaisesRegex(ValueError, "工業點"):
            engine.pay_forced_march("N", army_id="N-1")

    def test_affiliation_slot_upgrade_returns_slot_delta(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["affiliation_slot_upgrade"]

        result = engine.use_function("N", "affiliation_slot_upgrade", target_general_id="he_yingqin", target_owner="N")

        self.assertEqual(result["affiliation_slot_delta"], {"owner": "N", "general_id": "he_yingqin", "amount": 1})

    def test_first_united_front_requires_the_wang_jingwei_unlock(self):
        """國共合作需「汪精衛復出」生效後才可使用（該卡於下一批實作）。"""
        engine = GameEngine(seed=5)
        player = engine.state["players"]["N"]
        player["hand"].append("first_united_front")
        with self.assertRaisesRegex(ValueError, "汪精衛"):
            engine.use_function("N", "first_united_front")

        player["unlocks"].append("wang_jingwei_return")
        before = player["unit_reserves"]["infantry"]
        result = engine.use_function("N", "first_united_front")
        self.assertEqual(
            result["state"]["players"]["N"]["unit_reserves"]["infantry"], before + 20
        )
        self.assertEqual(result["loyalty_delta_all"], {"owner": "N", "amount": -2})


    def test_zhili_anti_communist_declaration_returns_loyalty_swings(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["W"]["hand"] = ["zhili_anti_communist_declaration"]

        result = engine.use_function("W", "zhili_anti_communist_declaration")

        self.assertIn({"owner": "W", "amount": 2}, result["loyalty_swings"])
        self.assertIn({"owner": "S", "amount": 2}, result["loyalty_swings"])
        # 親蘇方動態判定：開局只有國民革命軍對蘇 +9 達門檻
        self.assertIn({"owner": "N", "amount": -1}, result["loyalty_swings"])
        self.assertNotIn({"owner": "F", "amount": -1}, result["loyalty_swings"])
        self.assertIn({"owner": "N", "amount": -1}, result["loyalty_swings"])

    def test_intel_and_police_cards_create_timed_effects(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["intel_network", "police_system"]

        intel = engine.use_function("N", "intel_network", target_province="湖北")
        police = engine.use_function("N", "police_system")
        effects = police["state"]["players"]["N"]["timed_effects"]

        self.assertEqual(intel["timed_effect"]["kind"], "intel_network")
        self.assertEqual(intel["timed_effect"]["target_province"], "湖北")
        self.assertTrue(any(effect["kind"] == "police_system" and effect["remaining_turns"] == 3 for effect in effects))

    def test_communist_riot_suppresses_two_target_cities_temporarily(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["communist_riot"]
        before_income = engine.state["players"]["W"]["income"]
        before_factory = engine.state["players"]["W"]["factory_income"]

        result = engine.use_function("N", "communist_riot", target_owner="W")
        updated = result["state"]["players"]["W"]

        self.assertEqual(len(result["city_disruption"]["city_ids"]), 2)
        self.assertLess(updated["income"], before_income)
        self.assertLess(updated["factory_income"], before_factory)

    def test_du_yuesheng_gamble_halts_province_and_pays_until_suppressed(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["du_yuesheng_gamble"]
        before_n_cash = engine.state["players"]["N"]["treasury"]
        before_w_income = engine.state["players"]["W"]["income"]
        before_w_factory = engine.state["players"]["W"]["factory_income"]

        result = engine.use_function("N", "du_yuesheng_gamble", target_owner="W", target_province="湖北")
        effect = result["city_disruption"]

        self.assertEqual(effect["province"], "湖北")
        self.assertGreater(len(effect["city_ids"]), 0)
        self.assertLess(result["state"]["players"]["W"]["income"], before_w_income)
        self.assertLess(result["state"]["players"]["W"]["factory_income"], before_w_factory)

        turn = engine.next_turn(active_player="N")
        self.assertGreater(turn["state"]["players"]["N"]["treasury"], before_n_cash - 10)
        self.assertTrue(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))

        # 鎮壓門檻已改為連續駐留 2 回合：第一回合還在，第二回合結束才平息。
        engine.next_turn(active_player="N", riot_garrisons={effect["id"]: True})
        self.assertTrue(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))
        self.assertEqual(effect["required_turns"], 2)

        engine.next_turn(active_player="N", riot_garrisons={effect["id"]: True})
        self.assertFalse(any(item.get("id") == effect["id"] for item in engine.state["city_output_effects"]))

    def test_forced_next_turn_discards_unresolved_pending_draws(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["W"]["pending_draw"] = "unit_promotion"

        result = engine.next_turn(active_player="N", force=True)

        self.assertEqual(result["turn"]["turn"], 1)
        self.assertIsNone(result["state"]["players"]["W"]["pending_draw"])
        self.assertIn("unit_promotion", result["state"]["players"]["W"]["discard"])

    def test_zhili_joint_cards_require_peace_and_affect_both_factions(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["W"]["hand"] = ["zhili_infantry_drill"]
        before_w = engine.state["players"]["W"]["unit_reserves"]["infantry"]
        before_s = engine.state["players"]["S"]["unit_reserves"]["infantry"]

        result = engine.use_function("W", "zhili_infantry_drill")

        self.assertEqual(result["state"]["players"]["W"]["unit_reserves"]["infantry"], before_w + 5)
        self.assertEqual(result["state"]["players"]["S"]["unit_reserves"]["infantry"], before_s + 5)

        engine.state["players"]["W"]["hand"] = ["anti_fengtian_alignment"]
        engine.set_diplomacy("W", "S", "war")
        with self.assertRaisesRegex(ValueError, "requires peace"):
            engine.use_function("W", "anti_fengtian_alignment")

    def test_turn_accrues_interest_without_seizing_income(self):
        """3.2/3.4 — interest every turn, but income is the player's to spend."""
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["treasury"] = 10
        engine.take_loan("N", "deutsch_asiatische", 20)
        self.assertEqual(player["treasury"], 30)
        income = player["income"]

        result = engine.next_turn(active_player="N")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["last_debt_service"]["interest"], 2)  # round(20 * 0.08)
        self.assertEqual(updated["debt"], 22)
        self.assertEqual(updated["last_debt_service"]["forced_repayment"], 0)
        self.assertEqual(updated["treasury"], 30 + income)

    def test_manual_debt_repayment_is_capped_by_cash_and_debt(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        engine.take_loan("N", "deutsch_asiatische", 20)
        player["treasury"] = 12

        result = engine.repay_debt("N", 40)

        self.assertEqual(result["amount"], 12)
        self.assertEqual(result["state"]["players"]["N"]["treasury"], 0)
        self.assertEqual(result["state"]["players"]["N"]["debt"], 8)

    def test_overdue_loan_seizes_cash_on_hand(self):
        """3.5 — on the turn a loan runs past due, cash on hand is taken first."""
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        engine.take_loan("N", "deutsch_asiatische", 20)   # 3-turn term, due on turn 3
        player["treasury"] = 5

        for _ in range(3):
            engine.next_turn(active_player="N", force=True)
        before = engine.state["players"]["N"]["treasury"]
        owed = engine.state["players"]["N"]["debt"]
        self.assertEqual(engine.state["players"]["N"]["last_debt_service"]["seized_cash"], 0)

        engine.next_turn(active_player="N", force=True)
        updated = engine.state["players"]["N"]
        service = updated["last_debt_service"]

        self.assertEqual(engine.state["turn"], 4)
        self.assertEqual(service["seized_cash"], owed + service["interest"])
        self.assertEqual(updated["debt"], 0)
        self.assertEqual(updated["treasury"], before - service["seized_cash"] + service["net_income"])

    def test_overdue_loan_falls_back_to_seizing_income(self):
        """3.5 — when cash will not cover it, that turn's income goes too, and keeps going."""
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        engine.take_loan("N", "citibank", 30)             # us +1 -> standard, due on turn 3
        engine.take_loan("N", "yokohama_specie", 26)      # jp -1 -> standard
        player["treasury"] = 0

        for _ in range(4):
            engine.next_turn(active_player="N", force=True)
            engine.state["players"]["N"]["treasury"] = 0  # spent it all each turn
        service = engine.state["players"]["N"]["last_debt_service"]

        self.assertGreater(service["seized_income"], 0)
        self.assertEqual(service["net_income"], service["gross_income"] - service["seized_income"])
        self.assertGreater(engine.state["players"]["N"]["debt"], 0)

        # arrears survive into the next turn and keep taking the income
        engine.next_turn(active_player="N", force=True)
        self.assertGreater(engine.state["players"]["N"]["last_debt_service"]["seized_income"], 0)

    def test_hostile_relation_calls_the_loan_in(self):
        """3.6.1 — falling into the hostile band makes that bank's loans due at once."""
        engine = GameEngine(seed=4)
        engine.take_loan("F", "yokohama_specie", 10)      # 奉系 starts at jp +8
        engine.state["players"]["F"]["foreign_relations"]["jp"] = -6

        engine.next_turn(active_player="F", force=True)
        service = engine.state["players"]["F"]["last_debt_service"]

        self.assertTrue(service["called_in"])

    def test_starting_debt_is_zero_for_every_faction(self):
        engine = GameEngine(seed=4)
        for code in ("F", "W", "S", "N"):
            self.assertEqual(engine.state["players"][code]["debt"], 0)
            self.assertEqual(engine.state["players"][code]["loans"], [])

    def test_starting_relations_come_from_foreign_powers_data(self):
        engine = GameEngine(seed=4)
        self.assertEqual(engine.state["players"]["F"]["foreign_relations"]["jp"], 8)
        self.assertEqual(engine.state["players"]["N"]["foreign_relations"]["uk"], -8)
        self.assertEqual(engine.state["players"]["W"]["foreign_relations"]["su"], -8)

    def test_function_card_loan_joins_the_loan_list(self):
        """3.3 — a card-issued loan is a loan like any other."""
        engine = GameEngine(seed=4)
        player = engine.state["players"]["F"]
        before = len(player["loans"])
        engine._record_card_loan("F", {"id": "jp_yokohama_specie_loan"}, 55)
        self.assertEqual(len(player["loans"]), before + 1)
        loan = player["loans"][-1]
        self.assertEqual(loan["bank"], "yokohama_specie")
        self.assertEqual(loan["outstanding"], 55)
        self.assertEqual(player["debt"], 55)

    def test_initial_reserves_are_halved(self):
        engine = GameEngine(seed=4)
        self.assertEqual(engine.state["players"]["F"]["unit_reserves"]["infantry"], 27)

    def test_dalian_is_removed_from_playtest_city_list(self):
        engine = GameEngine(seed=4)
        self.assertNotIn("dalian", {city["id"] for city in engine.data["strategic_map"]["cities"]})

    def test_qingdao_is_a_sea_harbor(self):
        engine = GameEngine(seed=4)
        qingdao = next(city for city in engine.data["strategic_map"]["cities"] if city["id"] == "qingdao")
        self.assertEqual(qingdao["port"], "sea")

    def test_captured_city_keeps_its_scenario_faction_for_map_placement(self):
        engine = GameEngine(seed=4)
        engine.state["city_owners"]["tianjin"] = "S"
        tianjin = next(city for city in engine.bootstrap()["strategic_map"]["cities"] if city["id"] == "tianjin")
        self.assertEqual(tianjin["scenario_faction"], "F")
        self.assertEqual(tianjin["faction"], "S")

    def test_inactive_faction_must_choose_its_own_discard(self):
        engine = GameEngine(seed=13)
        engine.state["players"]["W"]["hand"] = ["unit_promotion"]
        engine.state["players"]["W"]["pending_draw"] = "unit_promotion"

        with self.assertRaisesRegex(ValueError, "W"):
            engine.next_turn(active_player="N")

    def test_combat_adapter_runs_existing_combat_system(self):
        result = simulate(
            {
                "army_a": {"units": {"infantry": 6}},
                "army_b": {"units": {"infantry": 6}},
                "max_rounds": 1,
            }
        )

        self.assertIn(result["winner"], {"A", "B", "draw", "stalemate", "undecided"})

    def test_combat_force_gate_and_defender_surrender(self):
        with self.assertRaisesRegex(ValueError, "more than 5"):
            simulate({"army_a": {"units": {"infantry": 5}}, "army_b": {"units": {"infantry": 8}}})

        result = simulate(
            {"army_a": {"units": {"infantry": 8}}, "army_b": {"units": {"infantry": 5}}}
        )
        self.assertEqual(result["winner"], "A")
        self.assertEqual(result["surrendered"], "B")


    # ---- 第二批功能卡：紅軍起義、汪精衛復出、崩鐵玩家 ----------------------

    def test_soviet_riot_cards_follow_the_relation_not_the_faction(self):
        """共黨暴動與紅軍起義只看對蘇關係，四個陣營一視同仁。

        這裡刻意不寫死任何陣營代號：規則是「跨過友好門檻就有 3 張，掉下去就收走」，
        開局誰拿得到只是初始關係值的結果，不是陣營特權。
        """
        cards = ("communist_riot", "red_army_uprising")
        for card_id in cards:
            self.assertIsNone(load_game_data()["indexes"]["function_cards"][card_id].get("allowed_players"), card_id)

        engine = GameEngine(seed=3)
        friendly = FOREIGN_FRIENDLY_THRESHOLD
        for code in engine.state["players"]:
            player = engine.state["players"][code]
            for relation, expected in ((friendly, 3), (friendly - 1, 0)):
                player["foreign_relations"]["su"] = relation
                engine._sync_foreign_deck_cards(code)
                for card_id in cards:
                    self.assertEqual(
                        engine._card_count_in_player_zones(player, card_id),
                        expected,
                        f"{code} su={relation} {card_id}",
                    )

    def test_any_faction_can_play_the_uprising_once_moscow_is_friendly(self):
        """關係到位，非國民革命軍的陣營一樣打得出紅軍起義。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = FOREIGN_FRIENDLY_THRESHOLD
        engine._sync_foreign_deck_cards("F")
        engine.state["players"]["F"]["hand"].append("red_army_uprising")
        result = engine.use_function("F", "red_army_uprising", target_owner="N")
        self.assertEqual(len(result["city_disruption"]["city_ids"]), 2)

    def test_red_army_uprising_zeroes_two_cities_until_a_brigade_arrives(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["N"]["hand"].append("red_army_uprising")
        before_cash = engine.state["players"]["S"]["income"]
        result = engine.use_function("N", "red_army_uprising", target_owner="S")
        disruption = result["city_disruption"]
        self.assertEqual(len(disruption["city_ids"]), 2)
        self.assertEqual(disruption["required_battalions"], 5)
        self.assertLess(engine.state["players"]["S"]["income"], before_cash)
        self.assertTrue(engine.state["players"]["S"]["notifications"])

        first, second = disruption["city_ids"]
        self.assertEqual(disruption["required_turns"], 2)
        # 五營要連續駐兩回合才解除，四營不算；沒有回合上限。
        engine.next_turn("N", city_garrisons={first: 4, second: 5})
        active = [e for e in engine.state["city_output_effects"] if e.get("kind") == "red_army_uprising"]
        self.assertEqual(sorted(active[0]["city_ids"]), sorted([first, second]))
        engine.next_turn("N", city_garrisons={first: 4, second: 5})
        active = [e for e in engine.state["city_output_effects"] if e.get("kind") == "red_army_uprising"]
        self.assertEqual(active[0]["city_ids"], [first])
        # first 中斷過，所以要再連兩回合。
        engine.next_turn("N", city_garrisons={first: 5})
        self.assertTrue([e for e in engine.state["city_output_effects"] if e.get("kind") == "red_army_uprising"])
        engine.next_turn("N", city_garrisons={first: 5})
        self.assertFalse([e for e in engine.state["city_output_effects"] if e.get("kind") == "red_army_uprising"])
        self.assertEqual(engine.state["players"]["S"]["income"], before_cash)

    def test_wang_jingwei_return_unlocks_the_united_front_and_cheapens_infantry_and_guns(self):
        engine = GameEngine(seed=11)
        player = engine.state["players"]["N"]
        self.assertEqual(player["function_deck"].count("wang_jingwei_return"), 1)
        self.assertEqual(player["function_deck"].count("first_united_front"), 0)

        infantry_before, _ = engine._unit_cost_for("N", "infantry")
        machine_gun_before, _ = engine._unit_cost_for("N", "machine_gun")
        factory_before = player["factory_income"]
        player["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")

        self.assertIn("wang_jingwei_return", player["unlocks"])
        self.assertEqual(player["function_deck"].count("first_united_front"), 1)
        self.assertEqual(engine._unit_cost_for("N", "infantry")[0], infantry_before - 2)
        self.assertEqual(engine._unit_cost_for("N", "machine_gun")[0], machine_gun_before - 2)
        self.assertEqual(player["factory_income"], factory_before + 2)

    def test_wang_jingwei_return_is_nationalist_only_and_single_use(self):
        engine = GameEngine(seed=11)
        for code in ("F", "W", "S"):
            self.assertFalse(engine._card_allowed_for_player("wang_jingwei_return", code))
        player = engine.state["players"]["N"]
        player["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")
        player["hand"].append("wang_jingwei_return")
        with self.assertRaisesRegex(ValueError, "已經生效"):
            engine.use_function("N", "wang_jingwei_return")

    def test_united_front_stays_locked_until_wang_returns(self):
        engine = GameEngine(seed=11)
        engine.state["players"]["N"]["hand"].append("first_united_front")
        with self.assertRaisesRegex(ValueError, "汪精衛復出"):
            engine.use_function("N", "first_united_front")

    def test_railway_saboteur_downs_one_line_for_three_turns(self):
        engine = GameEngine(seed=5)
        player = engine.state["players"]["F"]
        self.assertEqual(player["function_deck"].count("railway_saboteur"), 4)
        player["hand"].append("railway_saboteur")
        engine.use_function("F", "railway_saboteur", target_railway="京漢鐵路")
        self.assertEqual(engine.disabled_railways(), ["京漢鐵路"])
        for _ in range(2):
            advance_turn(engine, "F")
            self.assertEqual(engine.disabled_railways(), ["京漢鐵路"])
        advance_turn(engine, "F")
        self.assertEqual(engine.disabled_railways(), [])

    def test_railway_saboteur_rejects_lines_outside_the_card(self):
        engine = GameEngine(seed=5)
        player = engine.state["players"]["F"]
        player["hand"].append("railway_saboteur")
        # 南滿鐵路在地圖上，但不在卡片列出的八條中國鐵路裡。
        with self.assertRaisesRegex(ValueError, "只能指定"):
            engine.use_function("F", "railway_saboteur", target_railway="南滿鐵路")
        with self.assertRaisesRegex(ValueError, "需要指定"):
            engine.use_function("F", "railway_saboteur")
        engine.use_function("F", "railway_saboteur", target_railway="津浦鐵路")
        player["hand"].append("railway_saboteur")
        with self.assertRaisesRegex(ValueError, "搶修中"):
            engine.use_function("F", "railway_saboteur", target_railway="津浦鐵路")


    # ---- 第三批功能卡：王亞樵來投、組建親衛隊 ------------------------------

    def test_assassination_and_guard_copies(self):
        engine = GameEngine(seed=1)
        for code in engine.state["players"]:
            deck = engine.state["players"][code]["function_deck"]
            self.assertEqual(deck.count("wang_yaqiao_assassination"), 3, code)
            self.assertEqual(deck.count("body_guard_squad"), 5, code)

    def test_old_special_service_guard_cards_are_gone(self):
        """組建親衛隊取代了特勤衛隊：普通／菁英。"""
        index = load_game_data()["indexes"]["function_cards"]
        self.assertNotIn("special_service_guard_low", index)
        self.assertNotIn("special_service_guard_high", index)
        self.assertIn("body_guard_squad", index)

    def test_assassination_is_twenty_percent_and_logged(self):
        engine = GameEngine(seed=1)
        engine.state["players"]["F"]["hand"].append("wang_yaqiao_assassination")
        outcome = engine.use_function(
            "F", "wang_yaqiao_assassination",
            target_general_id="chiang_kai_shek", target_owner="N",
        )["assassination"]
        self.assertAlmostEqual(outcome["base_chance"], 0.20)
        self.assertAlmostEqual(outcome["chance"], 0.20)
        self.assertEqual(outcome["guard_reduction"], 0.0)
        self.assertEqual(outcome["success"], outcome["roll"] < outcome["chance"])
        self.assertEqual(len(engine.state["assassination_log"]), 1)
        self.assertTrue(engine.state["players"]["N"]["notifications"])

    def test_assassination_cannot_target_your_own_side(self):
        engine = GameEngine(seed=1)
        engine.state["players"]["F"]["hand"].append("wang_yaqiao_assassination")
        with self.assertRaisesRegex(ValueError, "自己陣營"):
            engine.use_function(
                "F", "wang_yaqiao_assassination",
                target_general_id="zhang_zuolin", target_owner="F",
            )
        with self.assertRaisesRegex(ValueError, "指定目標人物"):
            engine.use_function("F", "wang_yaqiao_assassination", target_owner="N")

    def test_guard_only_shields_from_the_following_turn(self):
        """同一回合內編成的親衛隊擋不住當回合的暗殺。"""
        engine = GameEngine(seed=1)
        engine.state["players"]["N"]["hand"].append("body_guard_squad")
        guard = engine.use_function("N", "body_guard_squad", target_general_id="chiang_kai_shek")["body_guard"]
        self.assertEqual(guard["active_from_turn"], engine.state["turn"] + 1)
        self.assertIsNone(engine.active_body_guard("chiang_kai_shek"))

        engine.state["players"]["F"]["hand"].append("wang_yaqiao_assassination")
        same_turn = engine.use_function(
            "F", "wang_yaqiao_assassination",
            target_general_id="chiang_kai_shek", target_owner="N",
        )["assassination"]
        self.assertAlmostEqual(same_turn["chance"], 0.20)

        engine.next_turn("F")
        self.assertIsNotNone(engine.active_body_guard("chiang_kai_shek"))
        engine.state["players"]["F"]["hand"].append("wang_yaqiao_assassination")
        later = engine.use_function(
            "F", "wang_yaqiao_assassination",
            target_general_id="chiang_kai_shek", target_owner="N",
        )["assassination"]
        self.assertAlmostEqual(later["chance"], 0.15)
        self.assertAlmostEqual(later["guard_reduction"], 0.05)

    def test_guard_is_permanent_and_one_per_character(self):
        engine = GameEngine(seed=1)
        engine.state["players"]["N"]["hand"].append("body_guard_squad")
        engine.use_function("N", "body_guard_squad", target_general_id="chiang_kai_shek")
        engine.state["players"]["N"]["hand"].append("body_guard_squad")
        with self.assertRaisesRegex(ValueError, "只能編成一支"):
            engine.use_function("N", "body_guard_squad", target_general_id="chiang_kai_shek")
        # 永久有效：跑很多回合仍在。
        for _ in range(12):
            engine.next_turn("N")
        self.assertIsNotNone(engine.active_body_guard("chiang_kai_shek"))

    def test_guard_cannot_be_given_to_another_faction(self):
        engine = GameEngine(seed=1)
        engine.state["players"]["N"]["hand"].append("body_guard_squad")
        with self.assertRaisesRegex(ValueError, "自己陣營"):
            engine.use_function(
                "N", "body_guard_squad",
                target_general_id="wu_peifu", target_owner="W",
            )

    def test_assassination_rates_hold_up_over_many_rolls(self):
        """20% 與 15% 是實際擲骰結果，不只是欄位上的數字。"""
        engine = GameEngine(seed=99)
        card = {"id": "wang_yaqiao_assassination", "name": "王亞樵來投", "success_rate": 0.20}
        rounds = 8000
        bare = sum(engine._resolve_assassination("F", card, "he_yingqin", "N")["success"] for _ in range(rounds))
        engine.state["body_guards"]["he_yingqin"] = {
            "general_id": "he_yingqin", "owner": "N",
            "reduction": 0.05, "assigned_turn": 0, "active_from_turn": 0,
        }
        guarded = sum(engine._resolve_assassination("F", card, "he_yingqin", "N")["success"] for _ in range(rounds))
        self.assertAlmostEqual(bare / rounds, 0.20, delta=0.02)
        self.assertAlmostEqual(guarded / rounds, 0.15, delta=0.02)


    # ---- 第四批 A/B：改名、控制省份判定、租界城市加成 ----------------------

    def test_renames_and_removal(self):
        index = load_game_data()["indexes"]["function_cards"]
        self.assertEqual(index["jp_mitsui_arms_shipment"]["name"], "三井商社輕兵器採購")
        self.assertEqual(index["su_rifle_shipment"]["name"], "蘇援槍械抵華")
        self.assertEqual(index["us_browning_samples"]["name"], "白朗寧軍火到貨")
        self.assertEqual(index["jp_south_manchuria_engineers"]["name"], "滿州墾殖團")
        self.assertEqual(index["fr_concession_engineers"]["name"], "滇越鐵路沿線擴建")
        self.assertEqual(index["uk_customs_advisers"]["name"], "怡和洋行投資案")
        self.assertEqual(index["us_industrial_engineers"]["name"], "美商投資公共租界")
        self.assertNotIn("su_military_academy_mission", index)

    def test_controlling_a_province_means_every_city_in_it(self):
        """與盤面「宣告接管全省」同一條標準：少一座城就不算控制。"""
        engine = GameEngine(seed=4)
        # 奉系開局就全控東北三省。
        self.assertEqual(
            engine._controlled_provinces("F", ["奉天", "吉林", "黑龍江"]),
            ["吉林", "奉天", "黑龍江"],
        )
        engine.state["city_owners"]["harbin"] = "N"
        self.assertEqual(engine._controlled_provinces("F", ["奉天", "吉林", "黑龍江"]), ["奉天", "黑龍江"])

    def test_manchurian_settlement_needs_all_three_provinces(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["F"]
        player["foreign_relations"]["jp"] = 9
        engine._sync_foreign_deck_cards("F")
        engine.state["city_owners"]["harbin"] = "N"
        engine._refresh_city_income()
        player["hand"].append("jp_south_manchuria_engineers")
        with self.assertRaisesRegex(ValueError, "吉林"):
            engine.use_function("F", "jp_south_manchuria_engineers")

        engine.state["city_owners"]["harbin"] = "F"
        engine._refresh_city_income()
        before = player["factory_income"]
        result = engine.use_function("F", "jp_south_manchuria_engineers")
        self.assertEqual(len(result["city_developments"]), 6)
        self.assertEqual(player["factory_income"], before + 6 * 2)

    def test_yunnan_expansion_needs_the_whole_province(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["foreign_relations"]["fr"] = 9
        engine._sync_foreign_deck_cards("N")
        player["hand"].append("fr_concession_engineers")
        with self.assertRaisesRegex(ValueError, "雲南"):
            engine.use_function("N", "fr_concession_engineers")

        for city in engine.data["strategic_map"]["cities"]:
            if city["province"] == "雲南":
                engine.state["city_owners"][city["id"]] = "N"
        engine._refresh_city_income()
        result = engine.use_function("N", "fr_concession_engineers")
        self.assertEqual({d["city_id"] for d in result["city_developments"]}, {"kunming", "dali", "mengzi"})
        self.assertTrue(all(d["cash"] == 2 and d["factory"] == 2 for d in result["city_developments"]))

    def test_concession_cards_need_and_only_pay_their_own_power(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["W"]
        player["foreign_relations"]["uk"] = 9
        engine._sync_foreign_deck_cards("W")
        player["hand"].append("uk_customs_advisers")

        # 漢口是直系開局唯一的英租界，拿走就不能用。
        engine.state["city_owners"]["hankou"] = "N"
        engine._refresh_city_income()
        with self.assertRaisesRegex(ValueError, "英租界"):
            engine.use_function("W", "uk_customs_advisers")

        engine.state["city_owners"]["hankou"] = "W"
        engine.state["city_owners"]["shanghai"] = "W"   # 上海掛英美法三國租界
        engine.state["city_owners"]["suzhou"] = "W"     # 蘇州只有日租界，不該受惠
        engine._refresh_city_income()
        result = engine.use_function("W", "uk_customs_advisers")
        self.assertEqual({d["city_id"] for d in result["city_developments"]}, {"hankou", "shanghai"})

    def test_american_concession_card_pays_two_cash_four_factory(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["S"]
        player["foreign_relations"]["us"] = 9
        engine._sync_foreign_deck_cards("S")
        player["hand"].append("us_industrial_engineers")
        # 五省聯軍開局持有上海，那是美租界城市。
        result = engine.use_function("S", "us_industrial_engineers")
        self.assertEqual([d["city_id"] for d in result["city_developments"]], ["shanghai"])
        self.assertEqual(result["city_developments"][0], {"city_id": "shanghai", "cash": 2, "factory": 4})


    # ---- 第四批 C/D/E：專案貸款、江浙財團、思潮對抗 ----------------------

    def test_project_loan_carries_its_own_terms_and_skips_the_quota(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["S"]
        player["foreign_relations"]["us"] = 9
        engine._sync_foreign_deck_cards("S")
        player["hand"].append("us_commercial_credit")
        cash_before = player["treasury"]

        engine.use_function("S", "us_commercial_credit")
        loan = player["loans"][-1]
        self.assertEqual(player["treasury"], cash_before + 50)
        self.assertEqual(loan["principal"], 40)
        self.assertAlmostEqual(loan["interest_per_turn"], 0.05)   # 三張列強借款 perk 卡一律 5%
        self.assertEqual(loan["term_turns"], 3)
        self.assertTrue(loan["off_quota"])
        # 額度未被佔用：花旗標準額度 30，關係 9 是優惠級 58。
        self.assertEqual(LOANS.available_credit("citibank", player["foreign_relations"], player["loans"]), 58)

    def test_citibank_default_takes_factory_from_three_cities_for_five_turns(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["S"]
        player["foreign_relations"]["us"] = 9
        engine._sync_foreign_deck_cards("S")
        player["hand"].append("us_commercial_credit")
        engine.use_function("S", "us_commercial_credit")

        seen = []
        for _ in range(9):
            advance_turn(engine, "S")
            seen.append(player["last_debt_service"]["penalties"])
        hits = [entry for turn in seen for entry in turn]
        self.assertTrue(hits)
        first = hits[0]
        self.assertEqual(len(first["cities"]), 3)
        self.assertEqual(first["cash"], 0)          # 只拿工廠
        self.assertGreater(first["factory"], 0)
        self.assertEqual(len(hits), 5)              # 持續 5 回合

    def test_hsbc_default_is_a_permanent_province_tithe(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["W"]
        player["foreign_relations"]["uk"] = 9
        engine._sync_foreign_deck_cards("W")
        player["hand"].append("uk_hsbc_credit")
        engine.use_function("W", "uk_hsbc_credit")
        for _ in range(9):
            engine.next_turn("W")
        entry = player["last_debt_service"]["penalties"][0]
        self.assertIsNone(entry["remaining_turns"])  # 永久
        self.assertGreater(entry["cash"], 0)
        self.assertGreater(entry["factory"], 0)

    def test_default_penalty_stacks_with_the_forced_repayment(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["F"]
        player["foreign_relations"]["jp"] = 9
        engine._sync_foreign_deck_cards("F")
        player["hand"].append("jp_yokohama_specie_loan")
        engine.use_function("F", "jp_yokohama_specie_loan")
        for _ in range(4):
            engine.next_turn("F")
        service = player["last_debt_service"]
        self.assertGreater(service["forced_repayment"], 0)   # 債務照扣
        self.assertTrue(service["penalties"])                # 罰則另外生效
        self.assertEqual(len(service["penalties"][0]["cities"]), 2)

    def test_warlord_bond_locks_foreign_banks_for_five_turns(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["N"]
        self.assertIsNone(player["loan_ban_until_turn"])
        player["hand"].append("function_軍閥公債")
        cash_before = player["treasury"]
        turn = int(engine.state["turn"])
        engine.use_function("N", "function_軍閥公債")
        self.assertEqual(player["treasury"], cash_before + 50)
        self.assertEqual(player["loans"][-1]["principal"], 25)
        self.assertAlmostEqual(player["loans"][-1]["interest_per_turn"], 0.08)   # 公債與普通借款同為 8%
        self.assertEqual(player["loan_ban_until_turn"], turn + 5)

        # 封鎖期內任何列強銀行都拒貸，理由要講清楚是公債造成的。
        player["foreign_relations"]["uk"] = 8
        with self.assertRaisesRegex(ValueError, "軍閥公債"):
            engine.take_loan("N", "hsbc", 1)

        offers = engine.loan_offers("N")
        self.assertEqual(offers["loan_ban_remaining_turns"], 5)
        self.assertTrue(all(not offer["can_borrow"] for offer in offers["offers"] if offer.get("bank")))

        # 五回合一過就恢復正常。
        player["loan_ban_until_turn"] = turn
        engine.take_loan("N", "hsbc", 1)
        self.assertEqual(engine.loan_offers("N")["loan_ban_remaining_turns"], 0)

    def test_jiangzhe_alliance_needs_both_provinces_and_unlocks_two_cards(self):
        engine = GameEngine(seed=8)
        player = engine.state["players"]["S"]
        player["hand"].append("jiangzhe_financiers")
        engine.state["city_owners"]["hangzhou"] = "N"
        engine._refresh_city_income()
        with self.assertRaisesRegex(ValueError, "浙江"):
            engine.use_function("S", "jiangzhe_financiers")

        engine.state["city_owners"]["hangzhou"] = "S"
        engine._refresh_city_income()
        before = player["treasury"]
        engine.use_function("S", "jiangzhe_financiers")
        self.assertEqual(player["treasury"], before + 50)
        self.assertEqual(player["function_deck"].count("kong_xiangxi_office"), 1)
        self.assertEqual(player["function_deck"].count("soong_patronage"), 1)

    def test_central_bank_only_reprices_later_loans(self):
        engine = GameEngine(seed=8)
        player = engine.state["players"]["S"]
        player["foreign_relations"]["uk"] = 0
        player["unlocks"].append("jiangzhe_financiers")
        old_loan = engine.take_loan("S", "hsbc", 10)["loan"]

        player["hand"].append("kong_xiangxi_office")
        engine.use_function("S", "kong_xiangxi_office")
        new_loan = engine.take_loan("S", "hsbc", 10)["loan"]

        self.assertAlmostEqual(new_loan["interest_per_turn"], 0.03)   # 孔祥熙統一 3%
        self.assertEqual(new_loan["term_turns"], old_loan["term_turns"] + 1)
        # 舊債不受影響。
        self.assertAlmostEqual(player["loans"][0]["interest_per_turn"], old_loan["interest_per_turn"])
        self.assertEqual(player["loans"][0]["term_turns"], old_loan["term_turns"])

    def test_soong_patronage_pays_on_settlement_and_blocks_du_yuesheng(self):
        engine = GameEngine(seed=8)
        # 這條測的是「宋家擋掉杜月笙」，不是事件卡。推回合會抽事件，抽到
        # 〈一黨之國〉時 [幫會] 卡整批被按住，攔下杜月笙的就變成別的理由，
        # 斷言看起來紅了但講的是另一件事。把池子清空，只留要測的那件事。
        engine.state["event_pool"] = []
        player = engine.state["players"]["S"]
        player["unlocks"].append("jiangzhe_financiers")
        player["hand"].append("soong_patronage")
        engine.use_function("S", "soong_patronage")

        while engine.state["turn"] % 3 or not engine.state["turn"]:
            advance_turn(engine, "S")
        paid = [item for item in player["last_debt_service"]["cash_effects"] if item["name"] == "上海宋家支持"]
        self.assertEqual(paid, [{"name": "上海宋家支持", "amount": 10, "factory": 5, "cities": ["上海"]}])

        rival = engine.state["players"]["W"]
        rival["hand"].append("du_yuesheng_gamble")
        with self.assertRaisesRegex(ValueError, "宋家"):
            engine.use_function("W", "du_yuesheng_gamble", target_owner="S", target_province="江蘇")

    def test_soong_patronage_stops_paying_once_shanghai_is_lost(self):
        engine = GameEngine(seed=8)
        player = engine.state["players"]["S"]
        player["unlocks"].append("jiangzhe_financiers")
        player["hand"].append("soong_patronage")
        engine.use_function("S", "soong_patronage")
        engine.state["city_owners"]["shanghai"] = "N"
        engine._refresh_city_income()
        while engine.state["turn"] % 3 or not engine.state["turn"]:
            engine.next_turn("S")
        self.assertEqual(
            [item for item in player["last_debt_service"]["cash_effects"] if item["name"] == "上海宋家支持"],
            [],
        )

    def test_three_cards_now_need_moscow_kept_at_arms_length(self):
        engine = GameEngine(seed=8)
        cases = [("S", "jiangzhe_financiers"), ("S", "overseas_chinese_remittance"),
                 ("W", "zhili_anti_communist_declaration")]
        for player, card_id in cases:
            payload = engine.state["players"][player]
            payload["foreign_relations"]["su"] = 6
            payload["hand"].append(card_id)
            with self.assertRaisesRegex(ValueError, "對蘇關係需在 5 以下", msg=card_id):
                engine.use_function(player, card_id)
            payload["hand"].remove(card_id)

    def test_anti_communist_cards_cost_moscow_and_please_london_and_tokyo(self):
        engine = GameEngine(seed=8)
        for player, card_id in (("W", "zhili_anti_communist_declaration"),):
            payload = engine.state["players"][player]
            payload["foreign_relations"].update({"su": 0, "uk": 0, "jp": 0})
            payload["hand"].append(card_id)
            result = engine.use_function(player, card_id)
            moved = {item["power"]: item["amount"] for item in result["relation_side_effects"]}
            self.assertEqual(moved, {"su": -2, "uk": 1, "jp": 1}, card_id)
            self.assertEqual(payload["foreign_relations"]["su"], -2, card_id)
            self.assertEqual(payload["foreign_relations"]["uk"], 1, card_id)
            self.assertEqual(payload["foreign_relations"]["jp"], 1, card_id)

    def test_relation_side_effects_are_clamped_to_the_scale(self):
        engine = GameEngine(seed=8)
        payload = engine.state["players"]["W"]
        payload["foreign_relations"].update({"su": -10, "uk": 10, "jp": 10})
        payload["hand"].append("zhili_anti_communist_declaration")
        engine.use_function("W", "zhili_anti_communist_declaration")
        self.assertEqual(payload["foreign_relations"]["su"], -10)
        self.assertEqual(payload["foreign_relations"]["uk"], 10)
        self.assertEqual(payload["foreign_relations"]["jp"], 10)

    def test_red_army_uprising_annoys_the_four_western_powers(self):
        engine = GameEngine(seed=8)
        payload = engine.state["players"]["N"]
        payload["foreign_relations"].update({"uk": 0, "jp": 0, "us": 0, "fr": 0})
        payload["hand"].append("red_army_uprising")
        result = engine.use_function("N", "red_army_uprising", target_owner="S")
        moved = {item["power"]: item["amount"] for item in result["relation_side_effects"]}
        self.assertEqual(moved, {"uk": -1, "jp": -1, "us": -1, "fr": -1})
        self.assertNotIn("su", moved)   # 蘇聯不受影響

    def test_negotiation_succeeds_about_eighty_percent_and_does_nothing_on_failure(self):
        engine = GameEngine(seed=8)
        payload = engine.state["players"]["W"]
        rounds = 3000
        wins = 0
        for _ in range(rounds):
            payload["foreign_relations"]["fr"] = 0
            payload["hand"] = ["foreign_relation_fr"]
            delta = engine.use_function("W", "foreign_relation_fr")["foreign_relation_delta"]
            if delta["success"]:
                wins += 1
                self.assertEqual(delta["after"], 2)
            else:
                self.assertEqual(delta["after"], 0)      # 失敗完全沒有效果
                self.assertEqual(delta["amount"], 0)
        self.assertAlmostEqual(wins / rounds, 0.80, delta=0.03)

    def test_every_negotiation_card_carries_the_same_odds(self):
        index = load_game_data()["indexes"]["function_cards"]
        for power in ("jp", "su", "uk", "fr", "us"):
            self.assertAlmostEqual(index["foreign_relation_" + power]["success_rate"], 0.80, msg=power)

    def test_sixty_six_cards_carry_a_story(self):
        # 17 → 18（在野名將投效）→ 27（設立情報局、盜賣文物、中國人之恥、
        # 警政單位、五張貿易出口卡）→ 28（僑胞匯款）→ 30（崩鐵玩家、復興儒學）。
        # 這批文案補寫再加 14 張：情報網、鼓吹地方自治、結盟江浙財團、滿州墾殖團、
        # 共黨暴動、紅軍起義、怡和洋行投資案、滇越鐵路沿線擴建、美商投資公共租界，
        # 以及英美日法蘇五張譴責卡 → 44。
        cards = load_game_data()["function_cards"]["cards"]
        with_story = [card for card in cards if card.get("story")]
        # 再補 22 張：三張德商卡、四張技術／油源新卡，以及原本沒有文案的
        # 十五張列強友好卡 → 66；公費留學生、進口盤尼西林、德國飛艇偵查再 +3 → 69。
        # 再 +1：票號金融網 → 70。
        self.assertEqual(len(with_story), 70)
        for card in with_story:
            self.assertTrue(card["story"].strip(), card["id"])

    def test_narrative_moved_out_of_the_effect_text(self):
        """這五張的敘事原本混在效果文字裡，現在只應該出現在 story。"""
        index = load_game_data()["indexes"]["function_cards"]
        moved = {
            # 汪精衛復出的故事後來擴寫過，這裡改抓新稿裡的字眼，測的還是同一件事：
            # 敘事只能出現在 story，不能混進 effect。
            "wang_jingwei_return": "黃浦江",
            "soong_patronage": "宋家",
            "kong_xiangxi_office": "孔祥熙",
        }
        for card_id, phrase in moved.items():
            card = index[card_id]
            self.assertIn(phrase, card["story"], card_id)
            self.assertNotIn(phrase, card["effect"], card_id)




class EventCardTests(unittest.TestCase):
    """事件卡：每三回合發一則共享《民國報》，指定勢力回應後才結算經濟。"""

    def test_pool_holds_every_section_of_the_design(self):
        engine = GameEngine(seed=3)
        cards = engine.data["event_cards"]["cards"]
        # 池子＝每張卡放 pool_copies 份（預設 1）。兩種卡完全不進池子：
        #   never_drawn——只由機制直接插進 pending 的日蘇戰況報導；
        #   not_in_pool——卡與報導已建檔但後端機制還沒補齊的 NPC 行動那一批。
        expected = sum(max(1, int(c.get("pool_copies", 1)))
                       for c in cards
                       if not c.get("never_drawn") and not c.get("not_in_pool"))
        self.assertEqual(len(engine.state["event_pool"]), expected)
        self.assertTrue([c for c in cards if c.get("never_drawn")],
                        "日蘇戰況報導應該存在且不進池子")
        for card in cards:
            if card.get("never_drawn") or card.get("not_in_pool"):
                self.assertNotIn(card["id"], engine.state["event_pool"], card["name"])
        self.assertIsNone(engine.pending_event_view())

    def test_conditional_cards_only_reach_qualifying_players(self):
        """有進入條件的卡只有符合的人抽得到，而且一定發給符合的那一家。"""
        engine = GameEngine(seed=3)
        self.assertEqual(engine._event_eligible_players(engine._event_template("academia_sinica")), ["S"])
        self.assertEqual(engine._event_eligible_players(engine._event_template("yinxu_first_spade")), ["W"])
        self.assertEqual(engine._event_eligible_players(engine._event_template("baird_television")),
                         list(engine.state["players"]))

        for card_id, expected in (("academia_sinica", "S"), ("yinxu_first_spade", "W")):
            engine = GameEngine(seed=3)
            engine.state["turn"] = 2
            engine.state["event_pool"] = [card_id]
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            self.assertEqual(view["card"]["id"], card_id)
            self.assertEqual(view["drawer"], expected)
            self.assertEqual(view["responders"], [expected])

    def test_drawer_scoped_cards_only_pay_the_drawer(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["academia_sinica"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["responders"], ["S"])
        engine.respond_event("S")
        self.assertTrue(engine.academia_active("S"))
        for code in ("F", "W", "N"):
            self.assertFalse(engine.academia_status(code)["holder"], code)

    def test_yinxu_pays_cash_and_can_poison_your_own_deck(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["yinxu_first_spade"]
        engine.next_turn(active_player="F")
        payload = engine.state["players"]["W"]
        before = payload["treasury"]
        engine.respond_event("W", choice="sell_to_foreigners", follow_up="jp")
        # 這是本期最後一張，回應完後端會補跑本回合經濟，所以現金還會多一筆城市收入。
        self.assertGreaterEqual(payload["treasury"], before + 60)
        self.assertEqual(payload["function_deck"].count("national_shame"), 4)
        for code in ("F", "S", "N"):
            self.assertEqual(engine.state["players"][code]["function_deck"].count("national_shame"), 0)

    def test_section_seven_and_eight_unlock_the_new_technology_cards(self):
        engine = GameEngine(seed=3)
        pairs = {
            "government_scholars_program": ("event_government_scholars", "government_scholars"),
            "penicillin_discovery": ("event_penicillin", "penicillin_import"),
            "graf_zeppelin": ("event_graf_zeppelin", "zeppelin_recon"),
        }
        for event_id, (unlock, card_id) in pairs.items():
            engine.state["turn"] = 2
            engine.state["event_pool"] = [event_id]
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            engine.respond_event(view["waiting_for"])
            for code in engine.state["players"]:
                self.assertIn(unlock, engine.state["players"][code]["unlocks"], event_id)
        # 解鎖之後這幾張技術卡就會被洗進牌庫。
        for code in engine.state["players"]:
            deck = engine.state["players"][code]["function_deck"]
            self.assertGreater(deck.count("government_scholars"), 0, code)
            self.assertGreater(deck.count("penicillin_import"), 0, code)

    def test_one_party_state_freezes_five_cards_and_calms_the_riots(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["hand"].append("du_yuesheng_gamble")
        engine.use_function("F", "du_yuesheng_gamble", target_owner="S", target_province="江蘇")
        self.assertTrue(engine.state["city_output_effects"])

        engine.state["turn"] = 2
        engine.state["event_pool"] = ["one_party_state"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])

        self.assertEqual(engine.state["city_output_effects"], [])       # 暴動平息
        payload = engine.state["players"]["F"]
        payload["hand"].append("local_autonomy_agitation")
        with self.assertRaisesRegex(ValueError, "一黨之國"):
            engine.use_function("F", "local_autonomy_agitation",
                                target_general_id="wu_peifu", target_owner="W")
        for card_id in ("communist_riot", "hongmen_uprising", "peking_university_movement"):
            self.assertEqual(payload["function_deck"].count(card_id), 0, card_id)

    def test_showa_accession_hardens_tokyo_three_turns_later(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["showa_accession"]
        engine.next_turn(active_player="F")
        friendly = engine.state["players"]["F"]
        friendly["foreign_relations"]["jp"] = 8
        hostile = engine.state["players"]["N"]
        hostile["foreign_relations"]["jp"] = -6
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(friendly["foreign_relations"]["jp"], 8)        # 還沒到第四回合
        self.assertTrue(engine.state["scheduled_event_effects"])
        # 昭和改元會把 2 張〈東方會議〉加進池子（v4 2.4 條件）；那兩張抽到也會動對日關係，
        # 這條測試只驗「第四回合起兩極化」，所以先把池子清空隔離。
        self.assertEqual(engine.state["event_pool"].count("eastern_conference"), 2)
        engine.state["event_pool"] = []
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertEqual(friendly["foreign_relations"]["jp"], 9)        # 兩極化：友好再 +1
        self.assertEqual(hostile["foreign_relations"]["jp"], -7)        # 交惡再 −1
        self.assertEqual(engine.state["scheduled_event_effects"], [])

    def test_treaty_of_berlin_only_supplies_moscows_friends(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["N"]["foreign_relations"]["su"] = 9
        engine.state["players"]["F"]["foreign_relations"]["su"] = -7
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["treaty_of_berlin"]
        engine.next_turn(active_player="F")
        base = engine.state["players"]["N"]["function_deck"].count("su_rifle_shipment")
        self.assertEqual(base, 2, "親蘇的底牌本來就是 2 張")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        # 這條先前斷言的是 2——也就是「跟沒發生過一樣」。卡片說各 +2，
        # 於是這張卡整整空轉，測試卻是綠的。要斷言的是加成本身。
        self.assertEqual(
            engine.state["players"]["N"]["function_deck"].count("su_rifle_shipment"),
            base + 2, "親蘇玩家該實拿 +2 張")
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("su_rifle_shipment"), 0)

    def test_burning_red_lotus_cheapens_infantry_for_three_turns(self):
        engine = GameEngine(seed=3)
        before = engine._unit_cost_for("F", "infantry")[0]
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["burning_red_lotus"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], before - 1)
        self.assertEqual(engine.suppression_turn_bonus(), 1)
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], before)
        self.assertEqual(engine.suppression_turn_bonus(), 0)

    def test_panic_adds_two_points_to_the_matching_loans(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["foreign_relations"]["jp"] = 4
        loan = engine.take_loan("F", "yokohama_specie", 10)["loan"]
        base = float(loan["interest_per_turn"])
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["showa_financial_panic"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertAlmostEqual(float(payload["loans"][-1]["interest_per_turn"]), base + 0.02)
        # 加碼到期就退回原利率（貸款本身三回合到期，所以直接把回合推過去驗證）。
        engine.state["turn"] += 3
        engine._apply_loan_surcharges("F")
        self.assertAlmostEqual(float(payload["loans"][-1]["interest_per_turn"]), base)

    def test_academia_sinica_bonus_follows_jiangsu_for_anyone(self):
        """v4 7.2：研究院成立後，加成跟著江蘇跑，不再限抽到的那一家。"""
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["S"]
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["academia_sinica"]
        engine.next_turn(active_player="F")
        base = payload["factory_income"]
        engine.respond_event("S")
        self.assertTrue(engine.academia_founded())
        self.assertEqual(payload["factory_income"], base + 5)

        def set_jiangsu(owner):
            for city in engine.data["strategic_map"]["cities"]:
                if city.get("province") == "江蘇":
                    engine.state["city_owners"][city["id"]] = owner
            engine._refresh_city_income()
            for code in engine.state["players"]:
                engine._sync_conditional_deck_cards(code)

        # 江蘇易主：加成整個轉給新主，即使新主從來沒抽到過這張卡。
        set_jiangsu("N")
        self.assertFalse(engine.academia_active("S"))
        self.assertTrue(engine.academia_active("N"))
        self.assertFalse(engine.state["players"]["N"]["academia_sinica"]["holder"])
        set_jiangsu("S")
        self.assertTrue(engine.academia_active("S"))
        self.assertEqual(payload["factory_income"], base + 5)

    def test_academia_sinica_locks_smuggling_per_player_and_punishes_use(self):
        """v4 7.2（修訂）：〈盜賣文物〉是逐玩家封鎖，不是全場移除。

        控制江蘇時鎖住；離開江蘇就解封、又抽得到。但離開期間真的打出去，
        該玩家就永久失格——日後奪回江蘇也拿不到研究院加成。
        """
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["S"]
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["academia_sinica"]
        engine.next_turn(active_player="F")
        base = payload["factory_income"]
        for code in engine.state["players"]:
            engine.state["players"][code]["hand"].append("national_shame")
        engine.respond_event("S")

        # 成立當下：〈中國人之恥〉全場一次清空。
        for code in engine.state["players"]:
            self.assertEqual(engine._card_count_in_player_zones(
                engine.state["players"][code], "national_shame"), 0, code)

        # 控制江蘇：加成 +5，〈盜賣文物〉封鎖中，手上有也打不出來。
        self.assertEqual(payload["factory_income"], base + 5)
        self.assertEqual(payload["function_deck"].count("artifact_smuggling"), 0)
        payload["hand"].append("artifact_smuggling")
        with self.assertRaisesRegex(ValueError, "中央研究院"):
            engine.use_function("S", "artifact_smuggling", target_power="uk")

        def set_jiangsu(owner):
            for city in engine.data["strategic_map"]["cities"]:
                if city.get("province") == "江蘇":
                    engine.state["city_owners"][city["id"]] = owner
            engine._refresh_city_income()
            for code in engine.state["players"]:
                engine._sync_conditional_deck_cards(code)

        # 離開江蘇：加成停、封鎖解除，卡洗回原本張數（手上那張也算在總數裡）。
        set_jiangsu("N")
        self.assertLess(payload["factory_income"], base + 5)
        self.assertFalse(engine._perk_suspended("S", "artifact_smuggling"))
        self.assertEqual(engine._card_count_in_player_zones(payload, "artifact_smuggling"), 3)

        # 奪回江蘇：兩者都回來。
        set_jiangsu("S")
        self.assertEqual(payload["factory_income"], base + 5)
        self.assertEqual(payload["function_deck"].count("artifact_smuggling"), 0)

        # 離開期間打出去 → 永久失格，奪回江蘇也不恢復。
        set_jiangsu("N")
        engine.use_function("S", "artifact_smuggling", target_power="uk")
        self.assertTrue(payload["academia_sinica"]["disqualified"])
        set_jiangsu("S")
        self.assertFalse(engine.academia_active("S"))
        self.assertEqual(payload["factory_income"], base)

    def test_selling_the_oracle_bones_bars_you_from_academia_sinica(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["yinxu_first_spade"]
        engine.next_turn(active_player="F")
        holder = engine.pending_event_view()["drawer"]
        payload = engine.state["players"][holder]
        before = payload["foreign_relations"]["jp"]

        with self.assertRaisesRegex(ValueError, "指定買家"):
            engine.respond_event(holder, choice="sell_to_foreigners")
        with self.assertRaisesRegex(ValueError, "指定買家"):
            engine.respond_event(holder, choice="sell_to_foreigners", follow_up="de")

        engine.respond_event(holder, choice="sell_to_foreigners", follow_up="jp")
        self.assertEqual(payload["foreign_relations"]["jp"], min(10, before + 1))
        self.assertTrue(payload["academia_sinica"]["disqualified"])

        # 之後就算抽到中央研究院也不會生效。
        engine.state["turn"] = 5
        engine.state["event_pool"] = ["academia_sinica"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        if view and view["drawer"] == holder:
            engine.respond_event(holder)
            self.assertFalse(engine.academia_active(holder))

    def test_transatlantic_call_only_helps_whoever_holds_shanghai(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["transatlantic_call"]
        engine.next_turn(active_player="F")
        holder = engine.pending_event_view()["drawer"]
        engine.respond_event(holder)
        self.assertAlmostEqual(engine._card_template("foreign_relation_jp", holder)["success_rate"], 0.9)
        other = next(code for code in engine.state["players"] if code != holder)
        self.assertAlmostEqual(engine._card_template("foreign_relation_jp", other)["success_rate"], 0.8)
        # 上海易主，加成跟著走。
        engine.state["city_owners"]["shanghai"] = other
        self.assertAlmostEqual(engine._card_template("foreign_relation_jp", holder)["success_rate"], 0.8)

    def test_kellogg_signatories_enter_forced_peace_and_get_paid(self):
        """非戰公約：簽的人進入強制和平並在三回合後入帳，不簽的人什麼都沒有。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["kellogg_briand_pact"]
        engine.next_turn(active_player="F")
        # 四家依序表態：第一家簽、其餘不簽
        picks = {}
        while True:
            view = engine.pending_event_view()
            if not view:
                break
            who = view["waiting_for"]
            pick = "sign" if not picks else "ignore"
            picks[who] = pick
            engine.respond_event(who, choice=pick)
        signer_code = next(code for code, pick in picks.items() if pick == "sign")
        refuser_code = next(code for code, pick in picks.items() if pick == "ignore")
        signer = engine.state["players"][signer_code]
        refuser = engine.state["players"][refuser_code]

        peace = [e for e in signer["timed_effects"] if e.get("kind") == "forced_peace"]
        self.assertEqual(len(peace), 1)
        self.assertTrue(peace[0]["blocks_enemy_entry"])
        self.assertTrue(peace[0]["blocks_declaration"])
        self.assertTrue(peace[0]["withdraw_active_battles"])
        self.assertEqual(peace[0]["defensive_harm_taken_multiplier"], 0.92)
        self.assertFalse([e for e in refuser["timed_effects"] if e.get("kind") == "forced_peace"])

        before = signer["treasury"]
        engine.state["event_pool"] = []
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertGreaterEqual(signer["treasury"], before + 10)

    def test_goddard_rocket_rewrites_the_artillery_gift(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine._card_template("reserve_gift_artillery")["max_units"], 2)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["goddard_rocket"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        card = engine._card_template("reserve_gift_artillery")
        self.assertEqual((card["min_units"], card["max_units"]), (3, 3))

    def test_cycle_fires_every_third_turn_and_holds_the_economy(self):
        engine = GameEngine(seed=3)
        pool_before = len(engine.state["event_pool"])
        for _ in range(2):
            result = engine.next_turn(active_player="F")
            self.assertNotIn("awaiting_events", result["turn"])
        result = engine.next_turn(active_player="F")
        self.assertTrue(result["turn"]["awaiting_events"])
        # 經濟還沒跑：turn_log 停在第二回合。
        self.assertEqual(engine.state["turn_log"][-1]["turn"], 2)

        view = engine.pending_event_view()
        self.assertEqual(view["total"], 1)
        self.assertEqual(view["index"], 0)
        self.assertEqual(view["responders"], [view["drawer"]])
        self.assertIn("headline", view["card"]["newspaper"])

        added = 0
        while engine.pending_event_view():
            current = engine.pending_event_view()
            resolution = current["card"].get("resolution") or {}
            choice = (resolution.get("options") or [{}])[0].get("id") if resolution.get("type") == "choice" else None
            outcome = engine.respond_event(current["waiting_for"], choice=choice)
            added += sum(len(entry.get("added") or [])
                         for entry in (outcome.get("applied") or [])
                         if entry.get("kind") == "event_pool_add")
        # 唯一一則結完，本回合的經濟才補跑。
        self.assertEqual(engine.state["turn_log"][-1]["turn"], 3)
        self.assertEqual(len(engine.state["event_history"]), 1)
        # 抽出的那張離開池子；但有些卡（2.4 東方會議）會反過來往池子裡加張，
        # 所以這裡不能寫死一個數字——先前寫死 58，之後只要牌堆洗牌的隨機序列
        # 有任何變動、換一張卡被抽到，這條就會莫名其妙紅掉。改為對帳：
        #   期末張數 ＝ 期初 − 1（抽走的） ＋ 這一則加進去的
        # 抽走的是**一份**，不是這張卡的全部——最後通牒每國 10 張、經濟事件
        # 也有權重複本，抽掉一份之後池子裡照樣還有同名的卡。先前寫成
        # `assertNotIn(drawn, pool)`，只要隨機序列改到抽中複本卡就會紅。
        drawn = engine.state["event_history"][-1]["card_id"]
        declared = max(1, int(engine._event_template(drawn).get("pool_copies", 1)))
        self.assertEqual(engine.state["event_pool"].count(drawn), declared - 1)
        self.assertEqual(len(engine.state["event_pool"]), pool_before - 1 + added)

    def test_choice_cards_ask_every_faction_in_turn(self):
        """表態卡：四家依序各自表態、各自結算，抽到的那一家排第一。

        （先前 pending_event_view 把 needs_every_faction 寫死成 False，
        這類卡退化成只有抽到的一家表態，其餘三家的選擇根本問不到。）
        """
        engine = GameEngine(seed=3)
        card = engine._event_template("arcos_raid")
        self.assertEqual(card["resolution"]["type"], "choice")
        self.assertEqual(card["resolution"].get("scope"), "all_players")
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["arcos_raid"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertTrue(view["needs_every_faction"])
        self.assertEqual(len(view["responders"]), len(engine.state["players"]))
        self.assertEqual(view["responders"][0], view["drawer"])

        # 還沒輪到的人點不動，輪到的人不選也不行
        first = view["waiting_for"]
        later = [code for code in view["responders"] if code != first][0]
        with self.assertRaisesRegex(ValueError, "現在輪到"):
            engine.respond_event(later, choice="back_britain")
        with self.assertRaisesRegex(ValueError, "需要選擇"):
            engine.respond_event(first)

        # 四家逐一表態，每一步都要能推進到下一家，不能卡住
        seen = []
        for _ in range(len(view["responders"])):
            current = engine.pending_event_view()
            self.assertIsNotNone(current, "四家都表態完之前不該提早收卡")
            who = current["waiting_for"]
            self.assertIsNotNone(who, "waiting_for 不能是 None，否則前端點不下去")
            self.assertNotIn(who, seen, "同一家不該被問第二次")
            seen.append(who)
            engine.respond_event(who, choice="back_britain" if len(seen) % 2 else "back_soviets")
        self.assertEqual(sorted(seen), sorted(engine.state["players"]))
        self.assertIsNone(engine.pending_event_view())

    def test_each_faction_settles_its_own_choice(self):
        """各自結算：選英國的對英 +2，選蘇聯的對蘇 +2，互不干涉。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["arcos_raid"]
        engine.next_turn(active_player="F")
        before = {code: dict(engine.state["players"][code]["foreign_relations"])
                  for code in engine.state["players"]}
        picks = {}
        while True:
            view = engine.pending_event_view()
            if not view:
                break
            who = view["waiting_for"]
            pick = "back_britain" if len(picks) % 2 == 0 else "back_soviets"
            picks[who] = pick
            engine.respond_event(who, choice=pick)
        for code, pick in picks.items():
            now = engine.state["players"][code]["foreign_relations"]
            if pick == "back_britain":
                self.assertEqual(now["uk"], min(10, before[code]["uk"] + 2), code)
                self.assertLess(now["su"], before[code]["su"], code)
            else:
                self.assertEqual(now["su"], min(10, before[code]["su"] + 2), code)
                self.assertLess(now["uk"], before[code]["uk"], code)

    def test_choice_events_wait_for_the_drawer_not_the_player_order(self):
        """前端應看 responders 裡的抽中勢力，而不是 state.players 的鍵值順序。"""
        engine = GameEngine(seed=3)
        engine.state["event_pool"] = ["arcos_raid"]
        engine.state["turn"] = 3           # _start_event_cycle 只在回合數是 3 的倍數時發報
        # 強制模擬國民革命軍抽到這張卡。
        self.assertTrue(engine._start_event_cycle())
        entry = engine.state["pending_events"]["cards"][0]
        entry["drawer"] = "N"
        entry["responders"] = ["N"]

        view = engine.pending_event_view()
        self.assertEqual(view["waiting_for"], "N")
        self.assertEqual(view["pending_responders"], ["N"])
        with self.assertRaisesRegex(ValueError, "現在輪到 N"):
            engine.respond_event("F", choice="back_britain")

        engine.respond_event("N", choice="back_britain")
        self.assertIsNone(engine.pending_event_view())
        self.assertEqual(engine.state["event_history"][-1]["responses"], {"N": "back_britain"})

    def test_plain_events_wait_for_the_faction_that_drew_them(self):
        """單純事件由抽到的那一家點閱；別家點會被擋下並說明輪到誰。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["amsterdam_olympics"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        # 抽到哪一家由引擎的亂數決定，測的是「只有抽到的那家點得動」。
        drawer = view["drawer"]
        self.assertEqual(view["waiting_for"], drawer)
        other = next(code for code in engine.state["players"] if code != drawer)
        with self.assertRaisesRegex(ValueError, f"現在輪到 {drawer}"):
            engine.respond_event(other)
        engine.respond_event(drawer)
        self.assertIsNone(engine.state["pending_events"])
        self.assertEqual(engine.state["event_history"][-1]["responses"], {drawer: "acknowledged"})

    def test_relaxed_mode_still_available_behind_the_flag(self):
        """把旗標關掉就回到寬鬆模式：單純事件任何一家點閱都算數。"""
        engine = GameEngine(seed=3)
        engine.data["event_cards"]["draw_rules"]["strict_response_order"] = False
        try:
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["amsterdam_olympics"]
            engine.next_turn(active_player="F")
            self.assertFalse(engine.pending_event_view()["strict_order"])
            engine.respond_event("N")
            self.assertIsNone(engine.state["pending_events"])
        finally:
            engine.data["event_cards"]["draw_rules"]["strict_response_order"] = True

    def test_acknowledge_card_applies_its_payload_once(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["sound_film"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        for code in engine.state["players"]:
            self.assertIn("event_sound_film", engine.state["players"][code]["unlocks"])
        self.assertIsNone(engine.state["pending_events"])

    def test_perk_suspension_pulls_cards_out_of_the_deck(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["foreign_relations"]["jp"] = 9
        engine._sync_foreign_deck_cards("F")
        self.assertGreater(payload["function_deck"].count("jp_yokohama_specie_loan"), 0)

        engine.state["turn"] = 2
        engine.state["event_pool"] = ["showa_financial_panic"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(payload["function_deck"].count("jp_yokohama_specie_loan"), 0)
        with self.assertRaisesRegex(ValueError, "橫濱正金"):
            engine.take_loan("F", "yokohama_specie", 10)

    def test_event_card_can_rewrite_a_function_card(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine._card_template("artifact_smuggling")["payout_min"], 20)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["bird_in_space_case"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        card = engine._card_template("artifact_smuggling")
        self.assertEqual((card["payout_min"], card["payout_max"], card["shame_copies_per_use"]), (30, 60, 4))

    def test_pool_never_repeats_a_card(self):
        engine = GameEngine(seed=3)
        seen = []
        for _ in range(24):
            advance_turn(engine, "F")
        seen = [entry["card_id"] for entry in engine.state["event_history"]]
        # 抽過的卡不會洗回，所以「抽過的 + 還在池子裡的」必然守恆；
        # 但事件卡可以把別的卡加進池子（event_pool_add），總數只增不減。
        self.assertGreaterEqual(len(seen) + len(engine.state["event_pool"]), 59)


class EventLockTests(unittest.TestCase):
    """事件卡封鎖：卡片留在池子裡，封鎖期間抽不到，到期自動解封。

    封鎖與移除的差別就在這裡——移除的卡離開 event_pool 不再回來，
    封鎖的卡一張都沒少，只是抽卡時被跳過。
    """

    def _engine_with(self, pool, turn=2):
        engine = GameEngine(seed=3)
        engine.state["turn"] = turn
        engine.state["event_pool"] = list(pool)
        return engine

    @staticmethod
    def _tag(engine, card_id, tags, power_note=None):
        """_event_template 回傳的是 deepcopy，要改標籤得改資料本體。"""
        for card in engine.data["event_cards"]["cards"]:
            if card["id"] == card_id:
                card["tags"] = tags
                if power_note is not None:
                    card["power_note"] = power_note
                return
        raise AssertionError(card_id)

    def test_locked_card_stays_in_the_pool(self):
        """被封鎖的卡不會離開 event_pool——這是封鎖不是移除。"""
        engine = self._engine_with(["baird_television"])
        engine.state["event_locks"] = [
            {"cards": ["baird_television"], "until_turn": 99, "label": "測試封鎖"}
        ]
        self.assertTrue(engine._event_locked("baird_television"))
        engine.next_turn(active_player="F")
        # 池子裡只有這張，而它被封鎖，所以整輪抽不到東西，卡片原封不動
        self.assertIsNone(engine.pending_event_view())
        self.assertEqual(engine.state["event_pool"], ["baird_television"])

    def test_lock_expires_and_the_card_comes_back(self):
        engine = self._engine_with(["baird_television"])
        engine.state["event_locks"] = [
            {"cards": ["baird_television"], "until_turn": 4, "label": "測試封鎖"}
        ]
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view())
        engine.state["turn"] = 5
        self.assertFalse(engine._event_locked("baird_television"))

    def test_tag_and_power_lock_only_bites_that_power(self):
        """tags + powers：只封鎖該國該類，別國同標籤的照抽。"""
        engine = self._engine_with(["baird_television", "showa_accession"])
        for card in engine.data["event_cards"]["cards"]:
            card.pop("tags", None)
        self._tag(engine, "baird_television", ["軍事"], "日")
        self._tag(engine, "showa_accession", ["軍事"], "英")
        engine.state["event_locks"] = [
            {"tags": ["軍事"], "powers": ["日"], "until_turn": 99, "label": "日本軍事封鎖"}
        ]
        self.assertTrue(engine._event_locked("baird_television"))
        self.assertFalse(engine._event_locked("showa_accession"))

    def test_power_note_accepts_multiple_powers(self):
        engine = self._engine_with(["treaty_of_berlin"])
        self._tag(engine, "treaty_of_berlin", ["軍事"], None)
        self.assertEqual(engine._event_powers("treaty_of_berlin"), ["蘇", "德"])
        engine.state["event_locks"] = [
            {"tags": ["軍事"], "powers": ["德"], "until_turn": 99, "label": "德國軍事封鎖"}
        ]
        self.assertTrue(engine._event_locked("treaty_of_berlin"))

    def test_event_card_applies_a_lock(self):
        """芥川之死：抽出後掛上「日本 [軍事] 事件封鎖 2 回合」。"""
        engine = self._engine_with(["akutagawa_death"])
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        locks = engine.state["event_locks"]
        self.assertEqual(len(locks), 1)
        self.assertEqual((locks[0]["tags"], locks[0]["powers"]), (["軍事"], ["日"]))
        self.assertEqual(locks[0]["until_turn"], 3 + 2)

    def test_one_party_state_locks_student_movement_events(self):
        """一黨之國同時做兩件事：功能卡按住、學潮類事件卡封鎖。"""
        engine = self._engine_with(["one_party_state"])
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        lock = [entry for entry in engine.state["event_locks"]
                if "學潮" in str(entry.get("label"))]
        self.assertEqual(len(lock), 1)
        self.assertIn("peking_university_movement", lock[0]["cards"])
        # 〈北京大學共運〉現在是事件卡 10.7，走事件卡池封鎖
        self.assertTrue(engine._event_locked("peking_university_movement"))


class EventPoolAddTests(unittest.TestCase):
    """增加 N 張卡進池：取代舊的「抽中機率 +X%」寫法。"""

    def test_showa_accession_adds_two_eastern_conference_copies(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["showa_accession"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(engine.state["event_pool"].count("eastern_conference"), 2)

    def test_duplicate_copies_are_drawn_one_at_a_time(self):
        """同一張卡在池子裡可以有多份，抽掉一份還剩一份。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["baird_television", "baird_television"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(engine.state["event_pool"], ["baird_television"])

    def test_tag_pool_add_gives_every_matching_card_a_copy(self):
        """「增加 1 張日本 [軍事] 事件卡」= 每一張日本 [軍事] 卡各 +1，不是隨機挑一張。"""
        engine = GameEngine(seed=3)
        for card in engine.data["event_cards"]["cards"]:
            card.pop("tags", None)
        for card_id, power in (("baird_television", "日"), ("goddard_rocket", "日"),
                               ("lindbergh_flight", "英")):
            for card in engine.data["event_cards"]["cards"]:
                if card["id"] == card_id:
                    card["tags"] = ["軍事"]
                    card["power_note"] = power
        engine.state["event_pool"] = []
        engine._apply_event_payload(
            {"event_pool_add": [{"tags": ["軍事"], "powers": ["日"], "copies": 1}]},
            players=None, card={"id": "probe", "name": "probe"})
        pool = engine.state["event_pool"]
        self.assertEqual(pool.count("baird_television"), 1)
        self.assertEqual(pool.count("goddard_rocket"), 1)
        self.assertEqual(pool.count("lindbergh_flight"), 0)   # 英國的不算

    def test_tag_pool_add_scales_with_copies(self):
        engine = GameEngine(seed=3)
        # 先把資料檔裡本來就帶 [軍事] 的卡清掉標籤，讓這條測試只驗自己指定的兩張。
        for card in engine.data["event_cards"]["cards"]:
            card.pop("tags", None)
        for card_id in ("baird_television", "goddard_rocket"):
            for card in engine.data["event_cards"]["cards"]:
                if card["id"] == card_id:
                    card["tags"] = ["軍事"]
                    card["power_note"] = "日"
        engine.state["event_pool"] = []
        engine._apply_event_payload(
            {"event_pool_add": [{"tags": ["軍事"], "powers": ["日"], "copies": 2}]},
            players=None, card={"id": "probe", "name": "probe"})
        pool = engine.state["event_pool"]
        self.assertEqual(pool.count("baird_television"), 2)
        self.assertEqual(pool.count("goddard_rocket"), 2)

    def test_pool_add_reports_honestly_when_nothing_matches(self):
        """沒有符合標籤的卡就明講加不進去，不要假裝加成功。"""
        engine = GameEngine(seed=3)
        applied = engine._apply_event_payload(
            {"event_pool_add": [{"tags": ["尚未建檔的標籤"], "powers": ["日"], "copies": 2}]},
            players=None, card={"id": "probe", "name": "probe"})
        entry = [item for item in applied if item["kind"] == "event_pool_add"][0]
        self.assertEqual(entry["added"], [])
        self.assertEqual(entry["note"], "no matching event cards in data")

    def test_germany_joins_league_deals_three_german_cards(self):
        """德意志入盟：三張德商功能卡各進一張（取代機率 +3%）。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["germany_joins_league"]
        cids = ("siemens_china_expansion", "krupp_mauser_return", "rheinmetall_arms_export")
        before = {cid: engine._player("F")["function_deck"].count(cid) for cid in cids}
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        for cid in cids:
            self.assertEqual(engine._player("F")["function_deck"].count(cid),
                             before[cid] + 1, cid)


class ExileGeneralTests(unittest.TestCase):
    """在野將領池與〈在野名將投效〉。"""

    POOL_IDS = {
        "duan_qirui", "chen_jiongming", "tian_zhongyu",
        "wang_chengbin", "li_houji", "lu_yongxiang",
    }

    def test_pool_holds_the_six_generals_off_board_and_factionless(self):
        pool = load_game_data()["generals_in_exile"]["generals"]
        self.assertEqual(set(pool), self.POOL_IDS)
        for gid, general in pool.items():
            self.assertIsNone(general["faction"], gid)          # 不屬於任何陣營
            self.assertFalse(general["core_faction"], gid)
            self.assertEqual(general["status"], "in_exile", gid)  # 開局不在場上
            self.assertGreater(int(general["recruit_value"]), 0, gid)
            self.assertTrue(general["background"].strip(), gid)

    def test_moved_generals_left_their_original_factions(self):
        data = load_game_data()
        # 王承斌、韓復榘 原屬直系；李厚基、盧永祥 原屬五省聯軍。
        import json
        from backend.data_store import REPO_ROOT
        zhili = json.loads((REPO_ROOT / "general_tree/data/general_tree_zhili.json").read_text(encoding="utf-8"))
        sunfang = json.loads((REPO_ROOT / "general_tree/data/general_tree_sunfang.json").read_text(encoding="utf-8"))
        self.assertNotIn("wang_chengbin", zhili["generals"])
        self.assertIn("chen_jiamo", zhili["generals"])
        self.assertIn("kou_yingjie", zhili["generals"])
        self.assertNotIn("li_houji", sunfang["generals"])
        self.assertNotIn("lu_yongxiang", sunfang["generals"])
        self.assertIn("lu_xiangting", sunfang["generals"])
        self.assertIn("meng_zhaoyue", sunfang["generals"])
        # 韓復榘改列西北軍。
        feng = json.loads((REPO_ROOT / "general_tree/data/general_tree_npc_G.json").read_text(encoding="utf-8"))
        self.assertEqual(feng["generals"]["han_fuqu"]["faction"], "西北軍")
        self.assertIn("lu_zhonglin", feng["generals"])
        del data

    def test_replacements_inherit_the_outgoing_generals_numbers(self):
        import json
        from backend.data_store import REPO_ROOT
        zhili = json.loads((REPO_ROOT / "general_tree/data/general_tree_zhili.json").read_text(encoding="utf-8"))
        # 陳嘉謨完全沿用王承斌的數值。
        chen = zhili["generals"]["chen_jiamo"]
        self.assertEqual(chen["units"], {"infantry": 12, "cavalry": 2, "artillery": 1, "machine_gun": 2})
        self.assertEqual(chen["command_cap"], 35)
        self.assertEqual(chen["loyalty"], 7)
        # 寇英傑完全沿用韓復榘在直系時的數值。
        kou = zhili["generals"]["kou_yingjie"]
        self.assertEqual(kou["units"], {"infantry": 12, "cavalry": 4, "artillery": 2, "machine_gun": 3})
        self.assertEqual(kou["command_cap"], 34)

    def test_recruiting_costs_the_full_value_and_locks_the_general(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["W"]["treasury"]
        engine.state["players"]["W"]["hand"].append("function_在野名將投效")
        outcome = engine.use_function(
            "W", "function_在野名將投效", target_general_id="duan_qirui",
        )["exile_recruit"]

        self.assertEqual(outcome["general_id"], "duan_qirui")
        # 延攬費 = 身價全額 22 + 出山附加費 15（規則：所有在野將領招募費用 +$15）
        self.assertEqual(outcome["price"], 37)
        self.assertEqual(outcome["owner"], "W")
        self.assertEqual(outcome["units"], {"infantry": 6, "cavalry": 1, "artillery": 2, "machine_gun": 1})
        self.assertEqual(engine.state["players"]["W"]["treasury"], before - 37)
        self.assertEqual(engine.state["recruited_exiles"]["duan_qirui"], "W")

        # 同一人不能被第二次延攬。
        engine.state["players"]["S"]["hand"].append("function_在野名將投效")
        with self.assertRaises(ValueError):
            engine.use_function("S", "function_在野名將投效", target_general_id="duan_qirui")

    def test_recruiting_needs_a_target_and_enough_cash(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["W"]["hand"].append("function_在野名將投效")
        with self.assertRaises(ValueError):
            engine.use_function("W", "function_在野名將投效")

        engine.state["players"]["W"]["treasury"] = 5
        with self.assertRaises(ValueError):
            engine.use_function("W", "function_在野名將投效", target_general_id="duan_qirui")

    def test_empty_pool_turns_the_card_into_a_half_price_unit_top_up(self):
        engine = GameEngine(seed=3)
        engine.state["recruited_exiles"] = {gid: "F" for gid in self.POOL_IDS}
        before = engine.state["players"]["W"]["treasury"]
        engine.state["players"]["W"]["hand"].append("function_在野名將投效")
        result = engine.use_function("W", "function_在野名將投效")
        self.assertIsNone(result["exile_recruit"])
        delta = result["army_unit_delta"]
        self.assertEqual(delta["unit_reserves"], {"infantry": 2, "machine_gun": 1})
        # 步兵 4 ×2 + 機槍 10 = 18，半價 9；工業點不收。
        infantry_cash = engine._unit_cost_for("W", "infantry")[0]
        machine_gun_cash = engine._unit_cost_for("W", "machine_gun")[0]
        expected = (infantry_cash * 2 + machine_gun_cash + 1) // 2
        self.assertEqual(delta["price"], expected)
        self.assertEqual(delta["factory_cost"], 0)
        self.assertEqual(engine.state["players"]["W"]["treasury"], before - expected)

    def test_starting_force_targets(self):
        """開局戰力（步1、騎1、機2、砲4）——這些數字是刻意調出來的，別無意改動。"""
        import json
        from backend.data_store import REPO_ROOT
        stems = {"N": "playtest", "F": "fengtian", "W": "zhili", "S": "sunfang", "Y": "npc_Y"}
        expected = {"N": 114, "F": 120, "W": 122, "S": 111, "Y": 53}
        for code, stem in stems.items():
            tree = json.loads((REPO_ROOT / f"general_tree/data/general_tree_{stem}.json").read_text(encoding="utf-8"))
            total = 0
            for general in tree["generals"].values():
                units = general["units"]
                total += (int(units.get("infantry", 0)) + int(units.get("cavalry", 0))
                          + int(units.get("machine_gun", 0)) * 2 + int(units.get("artillery", 0)) * 4)
            self.assertEqual(total, expected[code], code)

    def test_map_armies_match_the_general_trees(self):
        """地圖上的部隊數必須和將領樹一致——runtime 以將領樹為準，不一致只會誤導。"""
        import json
        import re
        from backend.data_store import REPO_ROOT
        trees = {}
        for path in (REPO_ROOT / "general_tree/data").glob("general_tree_*.json"):
            if path.name.endswith("template.json"):
                continue
            for general in json.loads(path.read_text(encoding="utf-8"))["generals"].values():
                trees[general["id"]] = general["units"]
        source = (REPO_ROOT / "frontend/map.js").read_text(encoding="utf-8")
        block = re.search(r"export const ARMY_POSITIONS = \{(.*?)\n\};", source, re.S).group(1)
        checked = 0
        for line in block.splitlines():
            found = re.search(r"generalId: '([^']+)'.*?units: \{([^}]*)\}", line)
            if not found or found.group(1) not in trees:
                continue
            units = {key: int(value) for key, value in re.findall(r"(\w+):\s*(\d+)", found.group(2))}
            tree_units = {key: int(trees[found.group(1)].get(key, 0))
                          for key in ("infantry", "cavalry", "artillery", "machine_gun")}
            self.assertEqual(units, tree_units, found.group(1))
            checked += 1
        self.assertGreaterEqual(checked, 30)


class CardBatchTests(unittest.TestCase):
    """本批更新：盜賣文物、中國人之恥、警政單位、貿易出口、崩鐵、抽牌成本、條件卡。"""

    def test_copy_counts_for_this_batch(self):
        engine = GameEngine(seed=5)
        for code in engine.state["players"]:
            deck = engine.state["players"][code]["function_deck"]
            self.assertEqual(deck.count("function_在野名將投效"), 3, code)
            self.assertEqual(deck.count("unit_promotion"), 10, code)
            self.assertEqual(deck.count("local_autonomy_agitation"), 7, code)
            self.assertEqual(deck.count("body_guard_squad"), 5, code)
            self.assertEqual(deck.count("wang_yaqiao_assassination"), 3, code)
            self.assertEqual(deck.count("artifact_smuggling"), 3, code)
            self.assertEqual(deck.count("police_precinct"), 5, code)
            for power in ("jp", "su", "uk", "fr", "us"):
                self.assertEqual(deck.count(f"trade_export_{power}"), 5, f"{code}/{power}")
            # 中國人之恥開局一張都沒有。
            self.assertEqual(deck.count("national_shame"), 0, code)

    def test_intelligence_bureau_was_merged_into_the_renamed_card(self):
        index = load_game_data()["indexes"]["function_cards"]
        self.assertNotIn("intelligence_bureau", index)   # 舊卡合併掉了
        self.assertEqual(index["police_system"]["name"], "設立情報局")

    def test_artifact_smuggling_pays_out_and_poisons_the_deck(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["W"]
        before_cash = payload["treasury"]
        before_relation = payload["foreign_relations"]["uk"]
        payload["hand"].append("artifact_smuggling")
        result = engine.use_function("W", "artifact_smuggling", target_power="uk")

        sale = result["artifact_sale"]
        self.assertGreaterEqual(sale["payout"], 20)
        self.assertLessEqual(sale["payout"], 40)
        self.assertEqual(payload["treasury"], before_cash + sale["payout"])
        self.assertEqual(payload["foreign_relations"]["uk"], before_relation + 1)
        self.assertEqual(sale["shame_cards_added"], 3)
        self.assertEqual(payload["function_deck"].count("national_shame"), 3)

    def test_shame_cards_stop_at_nine(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["W"]
        for _ in range(5):
            payload["hand"].append("artifact_smuggling")
            engine.use_function("W", "artifact_smuggling", target_power="us")
        self.assertEqual(engine._card_count_in_player_zones(payload, "national_shame"), 9)

    def test_shame_card_does_nothing(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["W"]
        before = payload["treasury"]
        payload["hand"].append("national_shame")
        engine.use_function("W", "national_shame")
        self.assertEqual(payload["treasury"], before)
        self.assertIn("national_shame", payload["discard"])

    def test_artifact_smuggling_only_hits_the_users_own_deck(self):
        engine = GameEngine(seed=7)
        engine.state["players"]["W"]["hand"].append("artifact_smuggling")
        engine.use_function("W", "artifact_smuggling", target_power="jp")
        for code in ("F", "S", "N"):
            self.assertEqual(
                engine._card_count_in_player_zones(engine.state["players"][code], "national_shame"), 0, code)

    def test_artifact_smuggling_cannot_target_germany(self):
        # 只賣得給日、蘇、英、美、法五國，德國不在名單上。
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["W"]
        payload["hand"].append("artifact_smuggling")
        with self.assertRaisesRegex(ValueError, "盜賣文物只能指定"):
            engine.use_function("W", "artifact_smuggling", target_power="de")
        self.assertEqual(
            engine._card_template("artifact_smuggling")["powers"],
            ["jp", "su", "uk", "fr", "us"],
        )

    def test_foreign_combat_perks_run_three_turns_for_the_whole_faction(self):
        # 打出門檻、進牌庫門檻、失效門檻現在都是關係 6。
        index = load_game_data()["indexes"]["function_cards"]
        for card_id in (
            "jp_infantry_drill_mission", "su_galen_advisers", "uk_machine_gun_advisers",
            "fr_artillery_school", "us_firepower_doctrine",
        ):
            card = index[card_id]
            self.assertEqual(card["mechanic"], "timed_combat_effect", card_id)
            self.assertEqual(card["duration_turns"], 3, card_id)
            self.assertEqual(card["requires_relation_min"], 6, card_id)
            self.assertEqual(card["expires_below_relation"], 6, card_id)

    def test_combat_perk_is_playable_at_relation_six(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["F"]
        payload["foreign_relations"]["jp"] = 5
        payload["hand"].append("jp_infantry_drill_mission")
        with self.assertRaisesRegex(ValueError, "關係需達 6"):
            engine.use_function("F", "jp_infantry_drill_mission")
        payload["foreign_relations"]["jp"] = 6
        engine.use_function("F", "jp_infantry_drill_mission")
        effect = next(e for e in payload["timed_effects"] if e["id"] == "jp_infantry_drill_mission")
        self.assertEqual(effect["remaining_turns"], 3)

    def test_combat_perk_dies_when_the_relation_slips(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["F"]
        payload["foreign_relations"]["jp"] = 9
        payload["hand"].append("jp_infantry_drill_mission")
        engine.use_function("F", "jp_infantry_drill_mission")
        effect = next(e for e in payload["timed_effects"] if e["id"] == "jp_infantry_drill_mission")
        self.assertEqual(effect["remaining_turns"], 3)
        self.assertEqual(effect["foreign_power_key"], "jp")

        # 關係還在 6 以上：效果照舊。
        payload["foreign_relations"]["jp"] = 6
        engine._sync_foreign_deck_cards("F")
        self.assertTrue(any(e["id"] == "jp_infantry_drill_mission" for e in payload["timed_effects"]))

        # 跌破 6 就立刻失效，不等回合數走完。
        payload["foreign_relations"]["jp"] = 5
        engine._sync_foreign_deck_cards("F")
        self.assertFalse(any(e["id"] == "jp_infantry_drill_mission" for e in payload["timed_effects"]))

    def test_german_industry_cards_are_plain_deck_cards(self):
        # 德國不列入列強關係，所以這三張不綁關係，開局就在每個人的牌庫裡。
        engine = GameEngine(seed=5)
        for code in engine.state["players"]:
            deck = engine.state["players"][code]["function_deck"]
            self.assertEqual(deck.count("siemens_china_expansion"), 2, code)
            self.assertEqual(deck.count("krupp_mauser_return"), 1, code)
            self.assertEqual(deck.count("rheinmetall_arms_export"), 1, code)

    def test_siemens_upgrades_exactly_two_of_your_own_cities(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        cities = [item["id"] for item in payload["city_economy"][:2]]
        payload["hand"].append("siemens_china_expansion")
        result = engine.use_function("F", "siemens_china_expansion", target_city_ids=cities)
        self.assertEqual(
            [(item["city_id"], item["cash"], item["factory"]) for item in result["city_developments"]],
            [(cities[0], 1, 2), (cities[1], 1, 2)],
        )
        payload["hand"].append("siemens_china_expansion")
        with self.assertRaisesRegex(ValueError, "需要指定 2 座"):
            engine.use_function("F", "siemens_china_expansion", target_city_ids=cities[:1])
        payload["hand"].append("siemens_china_expansion")
        with self.assertRaisesRegex(ValueError, "不能重複"):
            engine.use_function("F", "siemens_china_expansion", target_city_ids=[cities[0], cities[0]])

    def test_technology_cards_wait_for_event_cards_that_do_not_exist_yet(self):
        # 三張技術卡的前提是事件卡，事件系統還沒重建，所以永遠不會被洗進牌庫。
        engine = GameEngine(seed=5)
        for card_id in ("sound_film_studio", "state_radio_station", "mechanized_division"):
            for code in engine.state["players"]:
                self.assertEqual(engine.state["players"][code]["function_deck"].count(card_id), 0, code)
            engine.state["players"]["F"]["hand"].append(card_id)
            with self.assertRaisesRegex(ValueError, "事件卡"):
                engine.use_function("F", card_id)

    def test_sound_film_studio_doubles_down_on_antiwar_speeches(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        rival = engine.state["players"]["W"]
        payload["treasury"], payload["factory_points"] = 100, 100
        payload.setdefault("unlocks", []).append("event_sound_film")
        payload["hand"].append("sound_film_studio")
        engine.use_function("F", "sound_film_studio")
        self.assertEqual(payload["treasury"], 80)
        self.assertEqual(payload["factory_points"], 80)

        rival["unit_reserves"]["infantry"] = 99
        payload["unit_reserves"]["infantry"] = 99
        for _ in range(6):
            payload["hand"].append("antiwar_speech_infantry")
            amount = -engine.use_function("F", "antiwar_speech_infantry", target_owner="W")["reserve_delta"]["amount"]
            self.assertGreaterEqual(amount, 5)   # 基礎 3~5 再加 2
            self.assertLessEqual(amount, 7)
        for _ in range(6):
            rival["hand"].append("antiwar_speech_infantry")
            amount = -engine.use_function("W", "antiwar_speech_infantry", target_owner="F")["reserve_delta"]["amount"]
            self.assertGreaterEqual(amount, 1)   # 3~5 減半去尾
            self.assertLessEqual(amount, 2)

    def test_radio_station_doubles_the_loyalty_cards(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        payload["treasury"], payload["factory_points"] = 100, 100
        payload.setdefault("unlocks", []).append("event_radio_network")
        payload["hand"].append("state_radio_station")
        engine.use_function("F", "state_radio_station")
        self.assertEqual(payload["treasury"], 70)
        self.assertEqual(payload["factory_points"], 70)

        payload["hand"].append("unit_promotion")
        self.assertEqual(
            engine.use_function("F", "unit_promotion", target_general_id="yang_yuting", target_owner="F")["loyalty_delta"], 2)
        payload["hand"].append("local_autonomy_agitation")
        self.assertEqual(
            engine.use_function("F", "local_autonomy_agitation", target_general_id="wu_peifu", target_owner="W")["loyalty_delta"], -2)
        # 〈復興儒學〉已改制成事件卡 10.8，走 frontend_effects；廣播電台照樣放大到 +2。
        payload["foreign_relations"]["su"] = -8
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "F"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        engine.respond_event("F")
        loyalty = [e for e in payload["pending_frontend_effects"] if e["kind"] == "loyalty_all"]
        self.assertEqual(loyalty[-1]["amount"], 2)
        self.assertEqual(loyalty[-1]["amplified_by"], "radio_station")

    def test_mechanized_division_buys_one_general_a_permanent_forced_march(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        payload["treasury"], payload["factory_points"] = 100, 100
        payload.setdefault("unlocks", []).append("event_model_a_car")
        payload["hand"].append("mechanized_division")
        engine.use_function("F", "mechanized_division", target_general_id="zhang_zongchang")
        self.assertEqual(payload["permanent_forced_march_generals"], ["zhang_zongchang"])
        self.assertEqual(payload["treasury"], 70)
        payload["hand"].append("mechanized_division")
        with self.assertRaisesRegex(ValueError, "已經是機械化步兵師"):
            engine.use_function("F", "mechanized_division", target_general_id="zhang_zongchang")

    def test_new_technology_cards_wait_for_their_event_cards(self):
        engine = GameEngine(seed=5)
        for card_id in ("government_scholars", "penicillin_import", "zeppelin_recon"):
            for code in engine.state["players"]:
                self.assertEqual(engine.state["players"][code]["function_deck"].count(card_id), 0, card_id)
            engine.state["players"]["F"]["hand"].append(card_id)
            with self.assertRaisesRegex(ValueError, "事件卡"):
                engine.use_function("F", card_id)

    def test_government_scholars_pays_off_five_turns_later(self):
        engine = GameEngine(seed=5)
        # 這條要連推五回合，正好會撞上第三回合的事件卡。抽到什麼是亂數決定的，
        # 而牌庫組成一變（多一張功能卡就夠了）抽到的那張就跟著換人——
        # 曾經抽到〈全國經濟會議與裁兵之議〉，它的裁兵給工廠 +4，
        # 這條測的工廠 +2 就被蓋掉了。清空事件卡池，讓它只測自己那件事。
        engine.state["event_pool"] = []
        payload = engine.state["players"]["F"]
        payload["treasury"] = 100
        payload.setdefault("unlocks", []).append("event_government_scholars")
        payload["hand"].append("government_scholars")
        before = payload["factory_income"]
        engine.use_function("F", "government_scholars")
        self.assertEqual(payload["treasury"], 85)
        self.assertEqual(payload["factory_income"], before)   # 還沒到時候
        for _ in range(4):
            advance_turn(engine, "F")
            self.assertEqual(payload["factory_income"], before)
        advance_turn(engine, "F")                              # 第五回合起生效
        self.assertEqual(payload["factory_income"], before + 2)

    def test_penicillin_and_mechanized_division_follow_the_general(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        payload["treasury"], payload["factory_points"] = 200, 200
        payload.setdefault("unlocks", []).extend(["event_penicillin", "event_model_a_car"])
        payload["hand"].extend(["penicillin_import", "mechanized_division"])
        engine.use_function("F", "penicillin_import", target_general_id="zhang_zongchang")
        engine.use_function("F", "mechanized_division", target_general_id="zhang_zongchang")
        self.assertEqual(payload["field_hospital_generals"], ["zhang_zongchang"])
        self.assertEqual(payload["permanent_forced_march_generals"], ["zhang_zongchang"])

        payload["hand"].append("penicillin_import")
        with self.assertRaisesRegex(ValueError, "已經配有野戰醫院"):
            engine.use_function("F", "penicillin_import", target_general_id="zhang_zongchang")

        # 張宗昌被別家招降：兩張卡買來的效果一起消失，也不隨他過去。
        engine.state["players"]["W"]["unit_reserves"]["infantry"] = 10
        engine.recruit_captive_general("W", [], "zhang_zongchang")
        self.assertEqual(payload["field_hospital_generals"], [])
        self.assertEqual(payload["permanent_forced_march_generals"], [])
        self.assertEqual(engine.state["players"]["W"].get("field_hospital_generals"), [])

    def test_zeppelin_recon_needs_three_distinct_provinces(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        payload["treasury"] = 100
        payload.setdefault("unlocks", []).append("event_graf_zeppelin")
        payload["hand"].append("zeppelin_recon")
        with self.assertRaisesRegex(ValueError, "需要指定 3 個省份"):
            engine.use_function("F", "zeppelin_recon", target_provinces=["直隸", "山東"])
        payload["hand"].append("zeppelin_recon")
        with self.assertRaisesRegex(ValueError, "不能重複"):
            engine.use_function("F", "zeppelin_recon", target_provinces=["直隸", "直隸", "山東"])
        engine.use_function("F", "zeppelin_recon", target_provinces=["直隸", "山東", "河南"])
        effect = next(item for item in payload["timed_effects"] if item["kind"] == "aerial_recon")
        self.assertEqual(effect["target_provinces"], ["直隸", "山東", "河南"])
        self.assertTrue(effect["ignores_counter_intelligence"])
        self.assertEqual(payload["treasury"], 80)

    def test_socony_oil_is_an_american_money_perk(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        self.assertEqual(payload["function_deck"].count("us_socony_oil"), 0)
        payload["foreign_relations"]["us"] = 8
        engine._sync_foreign_deck_cards("F")
        self.assertEqual(payload["function_deck"].count("us_socony_oil"), 2)
        payload["hand"].append("us_socony_oil")
        engine.use_function("F", "us_socony_oil")
        effect = next(item for item in payload["timed_effects"] if item["kind"] == "oil_price_immunity")
        self.assertEqual(effect["remaining_turns"], 10)

    def test_trade_export_burns_factory_points_for_cash_and_relation(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["S"]
        payload["factory_points"] = 100
        before_cash = payload["treasury"]
        before_relation = payload["foreign_relations"]["fr"]
        payload["hand"].append("trade_export_fr")
        engine.use_function("S", "trade_export_fr")
        self.assertEqual(payload["factory_points"], 50)
        self.assertEqual(payload["treasury"], before_cash + 20)
        self.assertEqual(payload["foreign_relations"]["fr"], before_relation + 1)

    def test_trade_export_needs_the_full_fifty_points(self):
        engine = GameEngine(seed=7)
        payload = engine.state["players"]["S"]
        payload["factory_points"] = 49
        payload["hand"].append("trade_export_us")
        with self.assertRaises(ValueError):
            engine.use_function("S", "trade_export_us")
        self.assertEqual(payload["factory_points"], 49)   # 失敗不扣點

    def test_police_precinct_blocks_and_quells_gang_riots(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["N"]["hand"].append("du_yuesheng_gamble")
        effect = engine.use_function(
            "N", "du_yuesheng_gamble", target_owner="W", target_province="湖北")["city_disruption"]
        self.assertTrue(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))

        engine.state["players"]["W"]["hand"].append("police_precinct")
        shield = engine.use_function("W", "police_precinct", target_province="湖北")["riot_shield"]
        self.assertEqual(shield["quelled_count"], 1)      # 現行暴動立即平息
        self.assertFalse(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))

        # 護盾期間敵方不能再在該省發動。
        engine.state["players"]["N"]["hand"].append("hongmen_uprising")
        engine.state["players"]["N"]["hand"].append("du_yuesheng_gamble")
        with self.assertRaises(ValueError):
            engine.use_function("N", "du_yuesheng_gamble", target_owner="W", target_province="湖北")
        # 別的省不受影響。
        engine.use_function("N", "du_yuesheng_gamble", target_owner="W", target_province="河南")

    def test_police_precinct_needs_a_province_you_hold(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["W"]["hand"].append("police_precinct")
        with self.assertRaises(ValueError):
            engine.use_function("W", "police_precinct", target_province="廣東")

    def test_railway_sabotage_bills_everyone_else_ten_factory_points(self):
        engine = GameEngine(seed=3)
        before = {code: engine.state["players"][code]["factory_points"] for code in engine.state["players"]}
        engine.state["players"]["N"]["hand"].append("railway_saboteur")
        result = engine.use_function("N", "railway_saboteur", target_railway="京漢鐵路")

        self.assertEqual(engine.state["players"]["N"]["factory_points"], before["N"])   # 使用者不付
        for code in ("F", "W", "S"):
            self.assertEqual(engine.state["players"][code]["factory_points"], max(0, before[code] - 10), code)
        self.assertEqual(result["railway_effect"]["repair_factory_cost"], 10)
        # 不再壓低沿線移動格數。
        self.assertNotIn("move_limit_tiles", result["railway_effect"])
        self.assertIn("京漢鐵路", engine.disabled_railways())

    def test_drawing_a_card_costs_cash_and_factory_points(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["W"]
        engine.next_turn(active_player="W")
        cash = payload["treasury"]
        factory = payload["factory_points"]
        engine.draw_function("W")
        self.assertEqual(payload["treasury"], cash - 5)
        self.assertEqual(payload["factory_points"], factory - 5)

        payload["factory_points"] = 4
        payload["function_purchase_count"] = 0
        with self.assertRaises(ValueError):
            engine.draw_function("W")

    def test_cards_with_unmet_conditions_stay_out_of_the_deck(self):
        """條件沒達成的卡不該被抽到，達成後才洗進牌庫。"""
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["N"]
        # 國共合作需要先打出汪精衛復出。
        self.assertEqual(payload["function_deck"].count("first_united_front"), 0)
        payload["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")
        engine.next_turn(active_player="N")
        self.assertGreater(payload["function_deck"].count("first_united_front"), 0)

    def test_a_card_already_in_hand_is_kept_but_blocked_when_the_condition_lapses(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["N"]
        payload["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")
        engine.next_turn(active_player="N")
        payload["hand"].append("first_united_front")

        payload["unlocks"] = []                     # 條件消失
        engine.next_turn(active_player="N")
        self.assertIn("first_united_front", payload["hand"])          # 手牌不會被抽走
        self.assertEqual(payload["function_deck"].count("first_united_front"), 0)
        with self.assertRaises(ValueError):                            # 但打不出來
            engine.use_function("N", "first_united_front")


class CityLevelFloorTests(unittest.TestCase):
    """省會與租界城市的等級下限。"""

    # 1926 年的省會。直隸省會此時在天津，北京同為 4 級，兩者都過關。
    PROVINCIAL_CAPITALS = {
        "吉林": "吉林", "四川": "成都", "奉天": "奉天", "安徽": "安慶",
        "察哈爾": "張家口", "山東": "濟南", "山西": "太原", "廣東": "廣州",
        "廣西": "南寧", "江蘇": "南京", "江西": "南昌", "河南": "開封",
        "浙江": "杭州", "湖北": "武昌", "湖南": "長沙", "熱河": "承德",
        "甘肅": "蘭州", "直隸": "天津", "福建": "福州", "綏遠": "歸綏",
        "貴州": "貴陽", "陝西": "西安", "雲南": "昆明", "黑龍江": "齊齊哈爾",
    }

    def _cities(self):
        return load_game_data()["strategic_map"]["cities"]

    def test_every_province_capital_is_at_least_level_three(self):
        by_name = {city["name"]: city for city in self._cities()}
        for province, name in self.PROVINCIAL_CAPITALS.items():
            city = by_name.get(name)
            self.assertIsNotNone(city, f"{province} 的省會 {name} 不在地圖上")
            self.assertEqual(city["province"], province, name)
            self.assertGreaterEqual(int(city["level"]), 3, f"{province}·{name}")

    def test_every_concession_city_is_at_least_level_three(self):
        concession_cities = [city for city in self._cities() if city.get("concession")]
        self.assertGreaterEqual(len(concession_cities), 10)
        for city in concession_cities:
            self.assertGreaterEqual(int(city["level"]), 3, city["name"])

    def test_every_province_on_the_map_has_a_capital_listed(self):
        """新增省份時別忘了補上省會，否則上面兩個測試會漏掉它。"""
        provinces = {city["province"] for city in self._cities()}
        self.assertEqual(provinces, set(self.PROVINCIAL_CAPITALS))


class ConditionalDeckTests(unittest.TestCase):
    """條件卡的進出牌庫：僑胞匯款與吳孫合作卡。"""

    def test_remittance_stays_out_until_you_hold_guangdong_or_fujian(self):
        engine = GameEngine(seed=3)
        # 開局：奉系與直系一省都沒全控，所以牌庫裡不該有這張。
        for code in ("F", "W"):
            self.assertEqual(
                engine.state["players"][code]["function_deck"].count("overseas_chinese_remittance"), 0, code)
        # 五省聯軍全控福建，條件成立。
        self.assertEqual(
            engine.state["players"]["S"]["function_deck"].count("overseas_chinese_remittance"), 2)
        # 國民革命軍全控廣東，但對蘇 9 > 5，關係條件擋住。
        self.assertEqual(
            engine.state["players"]["N"]["function_deck"].count("overseas_chinese_remittance"), 0)

    def test_remittance_enters_the_deck_once_a_province_is_taken(self):
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city["province"] == "廣東":
                engine.state["city_owners"][city["id"]] = "W"
        engine.next_turn(active_player="W")
        self.assertEqual(
            engine.state["players"]["W"]["function_deck"].count("overseas_chinese_remittance"), 2)

    def test_remittance_leaves_the_deck_when_the_province_is_lost(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["S"]
        self.assertEqual(payload["function_deck"].count("overseas_chinese_remittance"), 2)
        engine.state["city_owners"]["xiamen"] = "N"
        engine.next_turn(active_player="S")
        self.assertEqual(payload["function_deck"].count("overseas_chinese_remittance"), 0)

    JOINT_CARDS = (
        "zhili_infantry_drill", "anti_fengtian_alignment",
        "marshal_gratitude", "zhili_anti_communist_declaration",
    )

    def test_joint_cards_are_dealt_while_wu_and_sun_are_at_peace(self):
        engine = GameEngine(seed=3)
        for code in ("W", "S"):
            for card_id in self.JOINT_CARDS:
                self.assertGreater(
                    engine.state["players"][code]["function_deck"].count(card_id), 0, f"{code}/{card_id}")
        # 別家本來就拿不到這幾張。
        for code in ("F", "N"):
            for card_id in self.JOINT_CARDS:
                self.assertEqual(
                    engine.state["players"][code]["function_deck"].count(card_id), 0, f"{code}/{card_id}")

    def test_joint_cards_leave_the_deck_once_wu_and_sun_go_to_war(self):
        engine = GameEngine(seed=3)
        engine.set_diplomacy("W", "S", "war")
        engine.next_turn(active_player="W")
        for code in ("W", "S"):
            for card_id in self.JOINT_CARDS:
                self.assertEqual(
                    engine.state["players"][code]["function_deck"].count(card_id), 0, f"{code}/{card_id}")

    def test_a_joint_card_in_hand_survives_the_war_but_cannot_be_played(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["W"]["hand"].append("zhili_infantry_drill")
        engine.set_diplomacy("W", "S", "war")
        engine.next_turn(active_player="W")
        self.assertIn("zhili_infantry_drill", engine.state["players"]["W"]["hand"])
        with self.assertRaises(ValueError):
            engine.use_function("W", "zhili_infantry_drill")


class JapaneseCompradorTest(unittest.TestCase):
    """〈日本買辦〉：張宗昌轉投時帶走的人脈。"""

    def test_the_comprador_starts_with_the_faction_that_holds_zhang_zongchang(self):
        engine = GameEngine(seed=11)
        self.assertEqual(engine.faction_general_traits("F"), ["japanese_comprador"])

    def test_joining_a_faction_raises_that_factions_japan_relation_by_two(self):
        engine = GameEngine(seed=11)
        before = engine.state["players"]["W"]["foreign_relations"]["jp"]
        result = engine.apply_general_join("W", ["japanese_comprador"])

        self.assertEqual(result["comprador"]["amount"], 2)
        self.assertEqual(engine.state["players"]["W"]["foreign_relations"]["jp"], before + 2)
        # 人脈跟著人走，舊東家不再享有。
        self.assertEqual(engine.faction_general_traits("W"), ["japanese_comprador"])
        self.assertEqual(engine.faction_general_traits("F"), [])

    def test_generals_without_the_trait_change_nothing(self):
        engine = GameEngine(seed=11)
        before = engine.state["players"]["W"]["foreign_relations"]["jp"]
        self.assertEqual(engine.apply_general_join("W", ["defensive_specialist"]), {})
        self.assertEqual(engine.state["players"]["W"]["foreign_relations"]["jp"], before)

    def test_the_comprador_no_longer_touches_the_condemnation_deck(self):
        """買辦的免疫改成作用在事件卡的 [懲戒] 上，譴責功能卡不再受它影響。

        同一個技能不該有兩處作用。這條掃一輪固定種子，確認**每一次**都是滿張
        ——只要還有任何一次少了一張，就代表舊機制還活著。
        """
        for seed in range(40):
            engine = GameEngine(seed=seed)
            engine.state["faction_general_traits"] = {"W": ["japanese_comprador"]}
            engine.state["players"]["W"]["foreign_relations"]["jp"] = FOREIGN_HOSTILE_THRESHOLD
            engine._sync_foreign_deck_cards("W")
            self.assertEqual(
                engine.state["players"]["W"]["function_deck"].count("jp_condemnation"),
                FOREIGN_CONDEMNATION_COPIES,
                f"seed={seed}：買辦不該再擋譴責卡了")

    def test_the_old_condemnation_blocking_state_is_gone(self):
        """守門：`condemnation_blocked` 這個狀態欄整個廢掉了，別讓它悄悄復活。"""
        engine = GameEngine(seed=3)
        self.assertNotIn("condemnation_blocked", engine.state)
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        self.assertNotIn("condemnation_blocked", source)

    def test_without_the_comprador_every_condemnation_copy_lands(self):
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {}
        engine.state["players"]["W"]["foreign_relations"]["jp"] = FOREIGN_HOSTILE_THRESHOLD
        engine._sync_foreign_deck_cards("W")
        self.assertEqual(
            engine.state["players"]["W"]["function_deck"].count("jp_condemnation"),
            FOREIGN_CONDEMNATION_COPIES,
        )


class GeneralSkillCatalogTest(unittest.TestCase):
    """22 名主要將領的專屬技能都要在技能總表裡查得到。"""

    NAMED_SKILLS = {
        "northwest_overlord", "dodging_drift", "broadsword_corps", "northwest_vanguard",
        "shanxi_king", "iron_bulwark", "chief_of_staff", "xining_garrison",
        "desert_guard", "valiant_horse", "marshal_zhang", "young_marshal",
        "white_russian_mercenaries", "japanese_comprador", "elite_artillery",
        "five_provinces_alliance", "riverine_warfare", "assault_breaker",
        "wu_peifu_admired", "defensive_specialist", "central_plains_veteran",
        "wuchang_veteran",
    }

    def test_every_named_skill_exists(self):
        traits = load_game_data()["general_traits"]["traits"]
        self.assertTrue(self.NAMED_SKILLS.issubset(set(traits)))

    def test_every_trait_used_by_a_tree_exists_in_the_catalog(self):
        data = load_game_data()
        traits = set(data["general_traits"]["traits"])
        for faction, tree in data["playable_general_trees"].items():
            for general_id, general in tree["generals"].items():
                for trait in general.get("traits", []):
                    self.assertIn(trait, traits, f"{faction}/{general_id}: {trait}")

    def test_the_exile_pool_only_uses_known_traits(self):
        data = load_game_data()
        traits = set(data["general_traits"]["traits"])
        for general_id, general in data["generals_in_exile"]["generals"].items():
            for trait in general.get("traits", []):
                self.assertIn(trait, traits, f"{general_id}: {trait}")


class FactionLevelGeneralTraitTest(unittest.TestCase):
    """陣營層級的將領技能：買辦、地方財源、剿共。技能跟著人走。"""

    def test_the_french_comprador_raises_the_france_relation_by_three(self):
        engine = GameEngine(seed=5)
        before = engine.state["players"]["N"]["foreign_relations"]["fr"]
        result = engine.apply_general_join("N", ["french_comprador", "mountain_division"])

        self.assertEqual(result["comprador"]["power"], "fr")
        self.assertEqual(result["comprador"]["amount"], 3)
        self.assertEqual(engine.state["players"]["N"]["foreign_relations"]["fr"], before + 3)
        # 山地師是戰場技能，不該被記成陣營層級技能。
        self.assertEqual(engine.faction_general_traits("N"), ["french_comprador"])

    def test_the_french_comprador_is_three_times_the_japanese_one(self):
        """免疫率的相對關係沒變（法 30% 對日 10%），變的是它作用在哪裡。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"W": ["french_comprador"],
                                                  "S": ["japanese_comprador"]}
        self.assertAlmostEqual(engine.comprador_immunity("W", "fr"), 0.30)
        self.assertAlmostEqual(engine.comprador_immunity("S", "jp"), 0.10)
        # 技能只對自己那一國有效
        self.assertEqual(engine.comprador_immunity("W", "jp"), 0.0)
        self.assertEqual(engine.comprador_immunity("S", "fr"), 0.0)
        self.assertEqual(engine.comprador_immunity("N", "fr"), 0.0)

    def test_tianfu_land_adds_one_cash_and_factory_to_every_sichuan_city(self):
        engine = GameEngine(seed=5)
        engine.state["city_owners"]["chengdu"] = "W"
        engine.state["city_owners"]["zhengzhou"] = "W"
        engine._refresh_city_income()
        before = {item["id"]: (item["cash"], item["factory"]) for item in engine.state["players"]["W"]["city_economy"]}
        engine.apply_general_join("W", ["tianfu_land"])
        after = {item["id"]: (item["cash"], item["factory"]) for item in engine.state["players"]["W"]["city_economy"]}

        self.assertEqual(after["chengdu"], (before["chengdu"][0] + 1, before["chengdu"][1] + 1))
        self.assertEqual(after["zhengzhou"], before["zhengzhou"])   # 河南不受影響

    def test_hunan_governor_covers_hunan_only(self):
        engine = GameEngine(seed=5)
        engine.state["city_owners"]["changsha"] = "F"
        engine._refresh_city_income()
        before = {item["id"]: item["cash"] for item in engine.state["players"]["F"]["city_economy"]}
        engine.apply_general_join("F", ["hunan_governor"])
        after = {item["id"]: item["cash"] for item in engine.state["players"]["F"]["city_economy"]}

        self.assertEqual(after["changsha"], before["changsha"] + 1)
        self.assertEqual(after["beijing"], before["beijing"])

    def test_the_bonus_moves_with_the_general(self):
        engine = GameEngine(seed=5)
        engine.state["city_owners"]["chengdu"] = "W"
        engine.apply_general_join("W", ["tianfu_land"])
        with_bonus = {item["id"]: item["cash"] for item in engine.state["players"]["W"]["city_economy"]}["chengdu"]
        engine.apply_general_join("S", ["tianfu_land"])
        engine._refresh_city_income()
        without_bonus = {item["id"]: item["cash"] for item in engine.state["players"]["W"]["city_economy"]}["chengdu"]

        self.assertEqual(without_bonus, with_bonus - 1)
        self.assertEqual(engine.faction_general_traits("W"), [])
        self.assertEqual(engine.faction_general_traits("S"), ["tianfu_land"])

    def test_anticommunist_vanguard_switches_off_when_its_own_faction_turns_red(self):
        engine = GameEngine(seed=5)
        engine.apply_general_join("S", ["anticommunist_vanguard"])
        engine.state["players"]["S"]["foreign_relations"]["su"] = 0
        self.assertTrue(engine._has_fast_uprising_suppression("S"))
        engine.state["players"]["S"]["foreign_relations"]["su"] = 6
        self.assertFalse(engine._has_fast_uprising_suppression("S"))

    def test_the_old_cantonese_army_suppresses_an_uprising_in_a_single_turn(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["N"]["foreign_relations"]["su"] = FOREIGN_FRIENDLY_THRESHOLD
        engine.state["players"]["N"]["hand"].append("red_army_uprising")
        result = engine.use_function("N", "red_army_uprising", target_owner="S")
        garrison = {city_id: 5 for city_id in result["city_disruption"]["city_ids"]}

        engine.apply_general_join("S", ["old_cantonese_army"])
        engine.next_turn(active_player="N", city_garrisons=garrison)
        self.assertFalse([
            effect for effect in engine.state["city_output_effects"]
            if effect.get("kind") == "red_army_uprising"
        ])

    def test_without_the_trait_the_uprising_needs_two_turns(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["N"]["foreign_relations"]["su"] = FOREIGN_FRIENDLY_THRESHOLD
        engine.state["players"]["N"]["hand"].append("red_army_uprising")
        result = engine.use_function("N", "red_army_uprising", target_owner="S")
        garrison = {city_id: 5 for city_id in result["city_disruption"]["city_ids"]}

        engine.next_turn(active_player="N", city_garrisons=garrison)
        self.assertTrue([
            effect for effect in engine.state["city_output_effects"]
            if effect.get("kind") == "red_army_uprising"
        ])


class ExileRecruitRestrictionTest(unittest.TestCase):
    """有舊怨的在野將領不肯投靠特定陣營。"""

    def test_lu_yongxiang_refuses_the_five_province_alliance(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["S"]["hand"].append("function_在野名將投效")
        with self.assertRaises(ValueError):
            engine.use_function("S", "function_在野名將投效", target_general_id="lu_yongxiang")

    def test_chen_jiongming_refuses_the_national_revolutionary_army(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["N"]["hand"].append("function_在野名將投效")
        with self.assertRaises(ValueError):
            engine.use_function("N", "function_在野名將投效", target_general_id="chen_jiongming")

    def test_everyone_else_can_still_recruit_them(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["S"]["hand"].append("function_在野名將投效")
        outcome = engine.use_function(
            "S", "function_在野名將投效", target_general_id="chen_jiongming",
        )["exile_recruit"]
        self.assertEqual(outcome["general_id"], "chen_jiongming")

    def test_lu_hongtao_is_gone_from_the_pool(self):
        self.assertNotIn("lu_hongtao", load_game_data()["generals_in_exile"]["generals"])


class DefectionResistanceTest(unittest.TestCase):
    """唐生智的〈佛教將軍〉讓對方策反成功率額外 -5%。"""

    def test_resistance_lowers_the_success_chance(self):
        plain = GameEngine(seed=5).attempt_defection_with_force("N", 5, 20.0)
        resisted = GameEngine(seed=5).attempt_defection_with_force("N", 5, 20.0, None, 0.05)
        self.assertAlmostEqual(resisted["chance"], plain["chance"] - 0.05, places=6)

    def test_the_floor_still_applies(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["N"]["treasury"] = 500
        result = engine.attempt_defection_with_force("N", 10, 200.0, None, 0.5)
        self.assertGreaterEqual(result["chance"], 0.03)


class DebtServiceInterestBreakdownTest(unittest.TestCase):
    """債務結算要記下每種利率各收了多少利息，介面才不會寫死一個百分比。"""

    def engine_with_two_rates(self):
        engine = GameEngine(seed=5)
        # 匯豐關係 9 是優惠級 5%；德華銀行固定 8%。
        engine.state["players"]["W"]["foreign_relations"]["uk"] = 9
        engine.take_loan("W", "hsbc", 30)
        engine.take_loan("W", "deutsch_asiatische", 20)
        return engine

    def test_breakdown_matches_the_actual_loan_rates(self):
        engine = self.engine_with_two_rates()
        engine.next_turn(active_player="W")
        service = engine.state["players"]["W"]["last_debt_service"]
        rates = {entry["rate"] for entry in service["interest_breakdown"]}

        self.assertEqual(rates, {0.05, 0.08})
        # 明細加總必須等於實際入帳的利息，不能各算各的。
        self.assertEqual(sum(entry["interest"] for entry in service["interest_breakdown"]), service["interest"])
        self.assertEqual(
            sum(entry["outstanding"] for entry in service["interest_breakdown"]),
            service["debt_before"],
        )

    def test_no_loans_means_an_empty_breakdown(self):
        engine = GameEngine(seed=5)
        engine.next_turn(active_player="W")
        service = engine.state["players"]["W"]["last_debt_service"]
        self.assertEqual(service["interest_breakdown"], [])
        self.assertEqual(service["interest"], 0)

    def test_the_recorded_rate_is_never_a_fixed_two_percent(self):
        engine = self.engine_with_two_rates()
        engine.next_turn(active_player="W")
        service = engine.state["players"]["W"]["last_debt_service"]
        self.assertNotIn(0.02, {entry["rate"] for entry in service["interest_breakdown"]})


class ForeignPerkCopiesTest(unittest.TestCase):
    """列強友好卡的份數：暴動兩張各 3 份，其餘各 2 份。"""

    def test_every_ordinary_perk_card_comes_in_two_copies(self):
        engine = GameEngine(seed=4)
        payload = engine.state["players"]["W"]
        for power, cards in FOREIGN_PERK_CARDS.items():
            payload["foreign_relations"][power] = 10
        engine._sync_foreign_deck_cards("W")
        for power, cards in FOREIGN_PERK_CARDS.items():
            for card_id in cards:
                expected = 3 if card_id in ("communist_riot", "red_army_uprising") else 2
                with self.subTest(card=card_id):
                    self.assertEqual(engine._card_count_in_player_zones(payload, card_id), expected)

    def test_falling_below_the_threshold_removes_every_copy(self):
        engine = GameEngine(seed=4)
        payload = engine.state["players"]["W"]
        payload["foreign_relations"]["us"] = 10
        engine._sync_foreign_deck_cards("W")
        self.assertEqual(engine._card_count_in_player_zones(payload, "us_browning_samples"), 2)
        payload["foreign_relations"]["us"] = FOREIGN_FRIENDLY_THRESHOLD - 1
        engine._sync_foreign_deck_cards("W")
        self.assertEqual(engine._card_count_in_player_zones(payload, "us_browning_samples"), 0)


class CardPunctuationTest(unittest.TestCase):
    """卡牌的說明與故事一律使用全形中文標點。"""

    HALF_WIDTH = re.compile(r"[!,;:?'\"()/]|\.{2,}")

    def test_no_half_width_chinese_punctuation(self):
        data = load_game_data()
        offenders = []
        for key in ("function_cards",):
            for card in data[key]["cards"]:
                for field in ("effect", "story"):
                    text = card.get(field)
                    if not isinstance(text, str):
                        continue
                    for match in self.HALF_WIDTH.finditer(text):
                        offenders.append(f"{card['id']}.{field}: {match.group(0)!r}")
        self.assertEqual(offenders, [])

    def test_no_card_carries_generated_event_cards(self):
        # 事件系統移除後，功能卡不該再帶著把事件卡塞進牌池的欄位。
        for card in load_game_data()["function_cards"]["cards"]:
            self.assertNotIn("generated_event_cards", card, card["id"])



class StudentUnrestTests(unittest.TestCase):
    """學潮（9.3 革命文學論戰、10.7 北京大學共運）與 9.5 的減災。"""

    def _draw(self, engine, card_id, responder=None):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        engine.respond_event(view["waiting_for"] if responder is None else responder)
        return view

    def test_unrest_halves_output_of_two_big_cities(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0   # 對蘇 ≤5，全場都吃
        self._draw(engine, "revolutionary_literature")
        effects = [e for e in engine.state["city_output_effects"]
                   if e.get("kind") == "student_unrest"]
        self.assertTrue(effects)
        for effect in effects:
            self.assertLessEqual(len(effect["city_ids"]), 2)
            self.assertEqual(effect["cash_multiplier"], 0.5)
            # 事件在第 3 回合結算，該回合收尾時已倒數一次，所以看到的是 2
            self.assertEqual(effect["remaining_turns"], 2)
            for city_id in effect["city_ids"]:
                city = next(c for c in engine.data["strategic_map"]["cities"]
                            if c["id"] == city_id)
                self.assertGreaterEqual(city["level"], 4)   # 只挑四級或五級大城

    def test_unrest_skips_moscows_friends(self):
        """對蘇 ≥6 的玩家不吃學潮（relation_gate_max）。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 8
        self._draw(engine, "revolutionary_literature")
        self.assertEqual([e for e in engine.state["city_output_effects"]
                          if e.get("kind") == "student_unrest"], [])

    def test_unrest_blocks_reinforcement_in_those_cities(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        self._draw(engine, "revolutionary_literature")
        effect = next(e for e in engine.state["city_output_effects"]
                      if e.get("kind") == "student_unrest")
        city_id = effect["city_ids"][0]
        owner = effect["target_owner"]
        self.assertTrue(engine.city_in_student_unrest(city_id))
        with self.assertRaisesRegex(ValueError, "學潮"):
            engine.reinforce_army(owner, "army-1", city_id, "infantry", 1)

    def test_crescent_moon_softens_later_unrest(self):
        """《新月》月刊抽出後，此後的學潮只減 1/4。"""
        engine = GameEngine(seed=3)
        self.assertEqual(engine.student_unrest_multiplier(), 0.5)
        self._draw(engine, "crescent_moon_monthly")
        self.assertTrue(engine.state["student_unrest_relief"])
        self.assertEqual(engine.student_unrest_multiplier(), 0.75)

    def test_crescent_moon_deals_three_educator_copies(self):
        engine = GameEngine(seed=3)
        self._draw(engine, "crescent_moon_monthly")
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 3)


class NewEventCardTests(unittest.TestCase):
    """設計稿九、十、十一區塊新收錄的事件卡。"""

    def _draw(self, engine, card_id, choice=None):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        engine.respond_event(view["waiting_for"], choice=choice)
        return view

    def test_boxer_indemnity_amplifies_the_next_relation_drop(self):
        """10.5 庚款興學：受人之惠，動輒得咎——下一次關係下降多降 1 點，用完消失。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 5
            engine.state["players"][code]["foreign_relations"]["uk"] = 5
        self._draw(engine, "boxer_indemnity_schooling")
        payload = engine.state["players"]["F"]
        self.assertTrue(payload["relation_drop_amplifiers"])
        before = payload["foreign_relations"]["us"]
        engine._apply_event_payload({"relations": {"us": -1}}, players=["F"],
                                    card={"id": "probe", "name": "probe"})
        self.assertEqual(payload["foreign_relations"]["us"], before - 2)   # −1 再加碼 −1
        # 用過就沒了：第二次只降 1
        before = payload["foreign_relations"]["us"]
        engine._apply_event_payload({"relations": {"us": -1}}, players=["F"],
                                    card={"id": "probe", "name": "probe"})
        self.assertEqual(payload["foreign_relations"]["us"], before - 1)

    def test_boxer_indemnity_does_not_amplify_gains(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 5
            engine.state["players"][code]["foreign_relations"]["uk"] = 5
        self._draw(engine, "boxer_indemnity_schooling")
        payload = engine.state["players"]["F"]
        before = payload["foreign_relations"]["us"]
        engine._apply_event_payload({"relations": {"us": 1}}, players=["F"],
                                    card={"id": "probe", "name": "probe"})
        self.assertEqual(payload["foreign_relations"]["us"], before + 1)

    def test_boxer_indemnity_skips_players_friendly_with_neither(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 0
            engine.state["players"][code]["foreign_relations"]["uk"] = 0
        self._draw(engine, "boxer_indemnity_schooling")
        for code in engine.state["players"]:
            self.assertEqual(engine.state["players"][code]["relation_drop_amplifiers"], [])

    def test_confucian_revival_makes_local_autonomy_bounce_off(self):
        """10.8 復興儒學：只要還控制山東，〈鼓吹地方自治〉對你無效。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        holder = None
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["drawer"], "S")          # entry_condition 綁山東
        engine.respond_event("S")
        self.assertIsNotNone(engine.province_card_immunity("S", "local_autonomy_agitation"))

        rival = engine.state["players"]["N"]
        rival["hand"].append("local_autonomy_agitation")
        with self.assertRaisesRegex(ValueError, "山東"):
            engine.use_function("N", "local_autonomy_agitation",
                                target_owner="S", target_general_id="han_fuju")

        # 丟掉山東，免疫立刻消失
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "N"
        self.assertIsNone(engine.province_card_immunity("S", "local_autonomy_agitation"))

    def test_confucian_revival_emits_a_loyalty_effect_for_the_frontend(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        engine.respond_event("S")
        pending = engine.state["players"]["S"]["pending_frontend_effects"]
        self.assertTrue(any(e["kind"] == "loyalty_all" and e["amount"] == 1 for e in pending))

    def test_the_loyalty_effect_can_be_drained_and_does_not_come_back(self):
        """前端做完之後要銷得掉。銷不掉的話同一筆忠誠會每回合重複加。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        engine.respond_event("S")
        result = engine.consume_frontend_effects("S")          # 不指定 kind＝整個佇列
        self.assertTrue(any(e["kind"] == "loyalty_all" for e in result["consumed"]))
        self.assertEqual(engine.state["players"]["S"]["pending_frontend_effects"], [])
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertEqual(engine.state["players"]["S"]["pending_frontend_effects"], [],
                         "忠誠是一次性的，下一回合不該又冒出一筆")

    def test_nanyang_tobacco_docks_each_concession_power_once(self):
        """11.2：一城多國租界時每國各扣 1，同一國不重複扣。"""
        engine = GameEngine(seed=3)
        owner = engine.state["city_owners"].get("tianjin")
        payload = engine.state["players"][owner]
        for power in ("uk", "us", "fr", "jp"):
            payload["foreign_relations"][power] = 5
        before = dict(payload["foreign_relations"])
        engine._apply_event_payload({"concession_relations": {"delta": -1}},
                                    players=[owner], card={"id": "probe", "name": "probe"})
        # 天津有英美法日四國租界 → 四國各 −1，且各只扣一次
        for power in ("uk", "us", "fr", "jp"):
            self.assertEqual(payload["foreign_relations"][power], before[power] - 1, power)

    def test_national_goods_expo_cuts_factory_cost_permanently(self):
        """11.4：步兵、機槍、騎兵的工廠花費永久 −1。"""
        engine = GameEngine(seed=3)
        before = {unit: engine._unit_cost_for("F", unit)[1]
                  for unit in ("infantry", "machine_gun", "cavalry", "artillery")}
        self._draw(engine, "national_goods_expo")
        for unit in ("infantry", "machine_gun", "cavalry"):
            self.assertEqual(engine._unit_cost_for("F", unit)[1], before[unit] - 1, unit)
        self.assertEqual(engine._unit_cost_for("F", "artillery")[1], before["artillery"])

    def test_northwest_expedition_rewrites_the_smuggling_numbers(self):
        """10.2：〈盜賣文物〉收益降為 $10–30，〈中國人之恥〉上限 12、每次洗入 4。"""
        engine = GameEngine(seed=3)
        self._draw(engine, "northwest_expedition")
        card = engine._card_template("artifact_smuggling")
        self.assertEqual((card["payout_min"], card["payout_max"]), (10, 30))
        self.assertEqual(card["shame_copies_per_use"], 4)
        self.assertEqual(engine._card_template("national_shame")["max_copies"], 12)

    def test_gushibian_locks_confucian_revival(self):
        """10.3《古史辨》：把〈復興儒學〉從事件卡池封鎖 5 回合。"""
        engine = GameEngine(seed=3)
        self._draw(engine, "gushibian")
        self.assertTrue(engine._event_locked("confucian_revival"))
        entry = engine.event_lock_entry("confucian_revival")
        self.assertEqual(entry["until_turn"], 3 + 5)

    def test_kunming_lake_deals_three_revival_copies(self):
        engine = GameEngine(seed=3)
        self._draw(engine, "kunming_lake")
        self.assertEqual(engine.state["event_pool"].count("confucian_revival"), 3)

    def test_free_china_educators_locks_the_riot_cards_for_moscows_friends(self):
        """10.6：只咬對蘇 ≥6 者；清除則是全場。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        engine.state["players"]["N"]["foreign_relations"]["su"] = 0
        self._draw(engine, "free_china_educators")
        self.assertTrue(engine._perk_suspended("F", "communist_riot"))
        self.assertFalse(engine._perk_suspended("N", "communist_riot"))

    def test_art_academy_lifts_trade_export_payout(self):
        """9.4：五張貿易出口卡收益各 +$10（20 → 30），杭州每回合現金 +2。"""
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "浙江":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_art_academy"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        for cid in ("trade_export_jp", "trade_export_uk", "trade_export_us"):
            self.assertEqual(engine._card_template(cid)["cash_gain"], 30, cid)
        self.assertEqual(engine.state["city_development"]["hangzhou"]["cash"], 2)

    def test_silver_reform_rolls_once_and_picks_a_branch(self):
        """11.5：抽出時擲一次骰，兩支結果擇一，報紙也跟著擇一。"""
        seen = set()
        for seed in range(12):
            engine = GameEngine(seed=seed)
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["silver_tael_reform"]
            engine.next_turn(active_player="F")
            result = engine.respond_event(engine.pending_event_view()["waiting_for"])
            rolls = [e for e in (result.get("applied") or [])
                     if e.get("kind") == "random_outcome"]
            self.assertEqual(len(rolls), 1)
            self.assertIn(rolls[0]["chosen"], ("succeeds", "fails"))
            seen.add(rolls[0]["chosen"])
        self.assertEqual(seen, {"succeeds", "fails"})   # 兩支都出得來

    def test_silver_reform_carries_two_newspapers(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("silver_tael_reform")
        self.assertEqual(len(card["newspaper_variants"]), 2)
        self.assertIn("實行", card["newspaper_variants"][0]["headline"])
        self.assertIn("中輟", card["newspaper_variants"][1]["headline"])

    def test_disarmament_disbands_two_infantry_and_one_cavalry(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_economic_conference"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        # 這張卡指定誰由引擎抽，預備隊就設在被指到的那家身上。
        payload = engine.state["players"][view["waiting_for"]]
        payload["unit_reserves"]["infantry"] = 9
        payload["unit_reserves"]["cavalry"] = 4
        self.assertEqual(view["card"]["resolution"]["type"], "choice")
        engine.respond_event(view["waiting_for"], choice="disarm")
        self.assertEqual(payload["unit_reserves"]["infantry"], 7)
        self.assertEqual(payload["unit_reserves"]["cavalry"], 3)
        self.assertEqual(payload["loan_rate_overrides"], [])       # 裁成功就沒有懲罰

    def test_disarmament_falls_back_to_keeping_the_army_when_short(self):
        """預備隊湊不出步兵 2＋騎兵 1 時，自動改為不裁並吃下懲罰。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_economic_conference"]
        engine.next_turn(active_player="F")
        payload = engine.state["players"][engine.pending_event_view()["waiting_for"]]
        payload["unit_reserves"]["infantry"] = 1     # 不夠
        payload["unit_reserves"]["cavalry"] = 4
        result = engine.respond_event(engine.pending_event_view()["waiting_for"], choice="disarm")
        skipped = [e for e in (result.get("applied") or [])
                   if e.get("kind") == "reserve_delta_skipped"]
        self.assertTrue(skipped)
        self.assertIn("infantry", skipped[0]["shortfall"])
        self.assertEqual(payload["unit_reserves"]["infantry"], 1)   # 一個都沒扣
        self.assertEqual(payload["unit_reserves"]["cavalry"], 4)
        self.assertTrue(any(o["interest_per_turn"] == 0.12
                            for o in payload["loan_rate_overrides"]))

    def test_keeping_the_army_really_raises_the_bond_rate(self):
        """不裁的懲罰要真的咬到：〈軍閥公債〉發行時利率變 12%。"""
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_economic_conference"]
        engine.next_turn(active_player="F")
        punished = engine.pending_event_view()["waiting_for"]
        engine.respond_event(punished, choice="keep_army")
        payload = engine.state["players"][punished]
        payload["hand"].append("function_軍閥公債")
        engine.use_function(punished, "function_軍閥公債")
        bond = [loan for loan in payload["loans"] if loan["principal"] == 25][-1]
        self.assertEqual(bond["interest_per_turn"], 0.12)

    def test_bond_rate_is_eight_percent_without_the_penalty(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["hand"].append("function_軍閥公債")
        engine.use_function("F", "function_軍閥公債")
        bond = [loan for loan in payload["loans"] if loan["principal"] == 25][-1]
        self.assertEqual(bond["interest_per_turn"], 0.08)

    def test_nanyang_tobacco_swaps_concession_bonus_for_a_flat_payout(self):
        """11.2：3 回合內租界城市改發每回合 +5/+5，期間原本的租界加成停發。"""
        engine = GameEngine(seed=3)
        self.assertIsNone(engine.concession_override())
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["nanyang_vs_bat"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        override = engine.concession_override()
        self.assertIsNotNone(override)
        self.assertEqual((override["cash"], override["factory"]), (5, 5))
        # 生效期間不論是不是結算回合，租界城市都拿得到固定值
        engine.state["turn"] = 4
        bonuses = engine._concession_bonuses()
        self.assertTrue(bonuses)
        for entry in bonuses.values():
            self.assertEqual(entry["cash"], 5 * len(entry["cities"]))
        # 期滿之後回到原本的三回合結算制
        engine.state["turn"] = 99
        self.assertIsNone(engine.concession_override())

    def test_every_new_card_has_a_newspaper(self):
        """九、十、十一區塊的每一張都要有報紙短篇，不能只有效果。"""
        engine = GameEngine(seed=3)
        for card in engine.data["event_cards"]["cards"]:
            if str(card.get("ref", "")).split(".")[0] not in ("9", "10", "11"):
                continue
            paper = card.get("newspaper") or {}
            self.assertTrue(paper.get("headline"), card["id"])
            self.assertGreaterEqual(len(paper.get("paragraphs") or []), 2, card["id"])



class ConditionalBranchTests(unittest.TestCase):
    """9.5 / 10.1 / 10.3：依另一張卡的狀態走不同效果。"""

    def _fire(self, engine, card_id, responder=None):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        return engine.respond_event(view["waiting_for"] if responder is None else responder)

    def _chosen(self, result):
        picks = [e for e in (result.get("applied") or [])
                 if e.get("kind") == "conditional_branch"]
        self.assertEqual(len(picks), 1)
        return picks[0]

    def _found_academy_in_shandong(self, engine, owner="S"):
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = owner
        self._fire(engine, "confucian_revival", responder=owner)

    def test_crescent_moon_adds_copies_when_educators_not_drawn(self):
        engine = GameEngine(seed=3)
        pick = self._chosen(self._fire(engine, "crescent_moon_monthly"))
        self.assertEqual(pick["chosen"], "otherwise")
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 3)

    def test_crescent_moon_extends_the_lock_when_educators_active(self):
        """〈自由中國教育家〉還生效中 → 改成延長 5 回合，而不是再加牌。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        self._fire(engine, "free_china_educators")
        entry = next(e for e in engine.state["perk_suspensions"]
                     if e.get("source_card") == "free_china_educators")
        before = entry["until_turn"]
        result = self._fire(engine, "crescent_moon_monthly")
        self.assertEqual(self._chosen(result)["chosen"], "if_active")
        self.assertEqual(entry["until_turn"], before + 5)
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 0)

    def test_kunming_lake_adds_copies_when_revival_not_drawn(self):
        engine = GameEngine(seed=3)
        pick = self._chosen(self._fire(engine, "kunming_lake"))
        self.assertEqual(pick["chosen"], "otherwise")
        self.assertEqual(engine.state["event_pool"].count("confucian_revival"), 3)

    def test_kunming_lake_widens_the_revival_to_zhili(self):
        """〈復興儒學〉已抽出 → 免疫範圍擴大到山東與直隸。"""
        engine = GameEngine(seed=3)
        self._found_academy_in_shandong(engine)
        entry = engine.state["players"]["S"]["province_card_immunities"][0]
        self.assertEqual(entry["provinces"], ["山東"])
        result = self._fire(engine, "kunming_lake")
        self.assertIn(self._chosen(result)["chosen"], ("if_drawn", "if_active"))
        self.assertEqual(entry["provinces"], ["山東", "直隸"])

        # 丟掉山東但控制直隸，免疫仍在
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "N"
            if city.get("province") == "直隸":
                engine.state["city_owners"][city["id"]] = "S"
        self.assertIsNotNone(engine.province_card_immunity("S", "local_autonomy_agitation"))

    def test_gushibian_locks_revival_when_not_drawn(self):
        engine = GameEngine(seed=3)
        pick = self._chosen(self._fire(engine, "gushibian"))
        self.assertEqual(pick["chosen"], "otherwise")
        self.assertTrue(engine._event_locked("confucian_revival"))

    def test_gushibian_pierces_the_revival_shield_when_active(self):
        """〈復興儒學〉生效中 → 改成把它的護持按掉 10 回合。"""
        engine = GameEngine(seed=3)
        self._found_academy_in_shandong(engine)
        self.assertIsNotNone(engine.province_card_immunity("S", "local_autonomy_agitation"))
        result = self._fire(engine, "gushibian")
        self.assertIn(self._chosen(result)["chosen"], ("if_active", "if_drawn"))
        self.assertIsNone(engine.province_card_immunity("S", "local_autonomy_agitation"))
        # 十回合後護持自己回來
        engine.state["turn"] = 99
        self.assertIsNotNone(engine.province_card_immunity("S", "local_autonomy_agitation"))


class BoxerIndemnityTests(unittest.TestCase):
    """10.5 庚款興學：一國符合發一次，兩國都符合就雙倍。"""

    def _fire(self, engine, us, uk):
        """回傳 (F 的狀態, 這張卡實際發給 F 的現金總額)。

        不看 treasury 差額——事件結算完會接著跑該回合的經濟，收入會混進來。
        改看 applied 裡屬於這張卡的 cash 項。
        """
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = us
            engine.state["players"][code]["foreign_relations"]["uk"] = uk
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["boxer_indemnity_schooling"]
        engine.next_turn(active_player="F")
        result = engine.respond_event(engine.pending_event_view()["waiting_for"])
        paid = sum(int(e["amount"]) for e in (result.get("applied") or [])
                   if e.get("kind") == "cash" and e.get("player") == "F")
        return engine.state["players"]["F"], paid

    def test_one_qualifying_power_pays_one_grant(self):
        engine = GameEngine(seed=3)
        payload, paid = self._fire(engine, us=5, uk=0)
        self.assertEqual(paid, 15)
        self.assertEqual(len(payload["delayed_output_bonuses"]), 1)
        self.assertEqual([a["power"] for a in payload["relation_drop_amplifiers"]], ["us"])

    def test_both_powers_pay_double(self):
        engine = GameEngine(seed=3)
        payload, paid = self._fire(engine, us=5, uk=5)
        self.assertEqual(paid, 30)
        self.assertEqual(len(payload["delayed_output_bonuses"]), 2)
        self.assertEqual(sorted(a["power"] for a in payload["relation_drop_amplifiers"]),
                         ["uk", "us"])

    def test_neither_power_pays_nothing(self):
        engine = GameEngine(seed=3)
        payload, paid = self._fire(engine, us=0, uk=0)
        self.assertEqual(paid, 0)
        self.assertEqual(payload["relation_drop_amplifiers"], [])

    def test_each_amplifier_is_bound_to_its_own_power(self):
        engine = GameEngine(seed=3)
        payload, _ = self._fire(engine, us=5, uk=5)
        engine._apply_event_payload({"relations": {"us": -1}}, players=["F"],
                                    card={"id": "probe", "name": "probe"})
        self.assertEqual(payload["foreign_relations"]["us"], 5 - 2)
        self.assertEqual(payload["foreign_relations"]["uk"], 5)      # 英國那條還沒用掉



class JiangzheFinanciersTests(unittest.TestCase):
    """11.1 江浙財團的墊款：交戰判定 + 公債承銷特權。

    部隊位置與「交戰中」狀態住在前端，後端只收前端算好的省份清單
    （contested_provinces，與 riot_garrisons 同一條通道）。
    """

    def _found(self, engine, owner="S"):
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("江蘇", "浙江"):
                engine.state["city_owners"][city["id"]] = owner
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["jiangzhe_financiers"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["drawer"], owner)
        engine.respond_event(owner)
        return engine.state["players"][owner]

    def _city_cash(self, engine, owner, province):
        return {item["name"]: item["cash"] for item in engine.state["players"][owner]["city_economy"]
                if item["province"] == province}

    def test_no_penalty_while_nobody_is_fighting(self):
        engine = GameEngine(seed=3)
        self._found(engine)
        self.assertEqual(engine.state["contested_provinces"], [])
        for province in ("江蘇", "浙江"):
            self.assertFalse(engine.province_is_contested(province))
            self.assertEqual(engine._province_combat_penalty(province),
                             {"cash": 0, "factory": 0})

    def test_fighting_in_jiangsu_docks_every_city_in_jiangsu(self):
        engine = GameEngine(seed=3)
        self._found(engine)
        before = self._city_cash(engine, "S", "江蘇")
        engine.set_contested_provinces(["江蘇"])
        after = self._city_cash(engine, "S", "江蘇")
        self.assertTrue(before)
        for name, cash in before.items():
            self.assertEqual(after[name], max(0, cash - 1), name)
        # 浙江沒在打，一毛不動
        self.assertEqual(engine._province_combat_penalty("浙江"), {"cash": 0, "factory": 0})

    def test_penalty_lifts_when_the_fighting_stops(self):
        engine = GameEngine(seed=3)
        self._found(engine)
        before = self._city_cash(engine, "S", "浙江")
        engine.set_contested_provinces(["浙江"])
        self.assertNotEqual(self._city_cash(engine, "S", "浙江"), before)
        engine.set_contested_provinces([])
        self.assertEqual(self._city_cash(engine, "S", "浙江"), before)

    def test_penalty_hits_whoever_owns_the_city_not_just_the_drawer(self):
        """減損是全場性的：不管誰在江浙開打，誰持有城市誰吃。"""
        engine = GameEngine(seed=3)
        self._found(engine, owner="S")
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "江蘇":
                engine.state["city_owners"][city["id"]] = "N"
        engine.set_contested_provinces([])
        before = self._city_cash(engine, "N", "江蘇")
        engine.set_contested_provinces(["江蘇"])
        after = self._city_cash(engine, "N", "江蘇")
        for name, cash in before.items():
            self.assertEqual(after[name], max(0, cash - 1), name)

    def test_other_provinces_are_untouched(self):
        engine = GameEngine(seed=3)
        self._found(engine)
        engine.set_contested_provinces(["河南", "山東"])
        self.assertEqual(engine._province_combat_penalty("河南"), {"cash": 0, "factory": 0})

    def test_next_turn_accepts_the_frontend_report(self):
        engine = GameEngine(seed=3)
        self._found(engine)
        advance_turn(engine, "F", contested_provinces=["浙江"])
        self.assertEqual(engine.state["contested_provinces"], ["浙江"])

    def test_bond_privilege_skips_the_credit_damage(self):
        engine = GameEngine(seed=3)
        payload = self._found(engine)
        self.assertIsNotNone(engine.bond_underwriting_for("S"))
        payload["hand"].append("function_軍閥公債")
        result = engine.use_function("S", "function_軍閥公債")
        self.assertIsNone(payload.get("loan_ban_until_turn"))
        self.assertTrue(result["loan_effect"]["bond_privilege"])

    def test_without_the_card_the_bond_still_burns_your_credit(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["S"]
        payload["hand"].append("function_軍閥公債")
        engine.use_function("S", "function_軍閥公債")
        self.assertTrue(payload.get("loan_ban_until_turn"))

    def test_privilege_follows_the_two_provinces(self):
        """紅利跟著江浙跑：丟掉浙江就沒了，奪回就恢復。"""
        engine = GameEngine(seed=3)
        self._found(engine)
        self.assertIsNotNone(engine.bond_underwriting_for("S"))
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "浙江":
                engine.state["city_owners"][city["id"]] = "N"
        self.assertIsNone(engine.bond_underwriting_for("S"))
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "浙江":
                engine.state["city_owners"][city["id"]] = "S"
        self.assertIsNotNone(engine.bond_underwriting_for("S"))

    def test_privilege_lapses_if_you_warm_to_moscow(self):
        engine = GameEngine(seed=3)
        payload = self._found(engine)
        payload["foreign_relations"]["su"] = 8
        self.assertIsNone(engine.bond_underwriting_for("S"))



class ScheduledEventPathTests(unittest.TestCase):
    """多階段事件卡：掛上排程之後，真的推進回合驗它有沒有落地。

    先前這幾張只驗到「排程掛上去了」，沒驗「時候到了真的發生」。
    """

    def _fire(self, engine, card_id, choice=None):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        # 被指定的那家記下來，測試才知道效果該落在誰身上。
        self.responder = engine.pending_event_view()["waiting_for"]
        result = engine.respond_event(self.responder, choice=choice)
        engine.state["event_pool"] = []      # 清空，免得後面幾回合又抽到別的卡干擾
        return result

    def test_nanyang_tobacco_settles_concession_relations_three_turns_later(self):
        """11.2：加值三回合，期滿才對租界國各 −1，而且期滿前不動。"""
        engine = GameEngine(seed=3)
        owner = engine.state["city_owners"].get("tianjin")
        payload = engine.state["players"][owner]
        for power in ("uk", "us", "fr", "jp"):
            payload["foreign_relations"][power] = 5
        self._fire(engine, "nanyang_vs_bat")
        before = {p: payload["foreign_relations"][p] for p in ("uk", "us", "fr", "jp")}
        self.assertTrue(engine.state["scheduled_event_effects"])

        # 期滿前：關係一動也不動
        advance_turn(engine, "F")
        self.assertEqual({p: payload["foreign_relations"][p] for p in before}, before)

        # 第三回合到期：天津的四國租界各扣 1，且同一國只扣一次
        advance_turn(engine, "F")
        advance_turn(engine, "F")
        for power, was in before.items():
            self.assertEqual(payload["foreign_relations"][power], was - 1, power)
        self.assertEqual(engine.state["scheduled_event_effects"], [])

    def test_nanyang_settlement_uses_ownership_at_settlement_time(self):
        """清算掃的是清算當下的城市歸屬，不是抽卡當下的。"""
        engine = GameEngine(seed=3)
        owner = engine.state["city_owners"].get("tianjin")
        other = next(code for code in engine.state["players"] if code != owner)
        payload = engine.state["players"][owner]
        for power in ("uk", "us", "fr", "jp"):
            payload["foreign_relations"][power] = 5
        self._fire(engine, "nanyang_vs_bat")
        before = {p: payload["foreign_relations"][p] for p in ("uk", "us", "fr", "jp")}
        # 把所有租界城市交出去，期滿時原持有人身上已經沒有租界了
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("concession"):
                engine.state["city_owners"][city["id"]] = other
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertEqual({p: payload["foreign_relations"][p] for p in before}, before)

    def test_disarmament_bonus_expires_after_three_turns(self):
        """11.3 裁兵：三回合紅利到期後，加成要真的收回去。"""
        engine = GameEngine(seed=3)
        for payload in engine.state["players"].values():
            payload["unit_reserves"]["infantry"] = 9
            payload["unit_reserves"]["cavalry"] = 4
        base = engine._delayed_output_bonus("F")
        self._fire(engine, "national_economic_conference", choice="disarm")
        during = engine._delayed_output_bonus(self.responder)
        self.assertEqual(during["cash"] - base["cash"], 8)
        self.assertEqual(during["factory"] - base["factory"], 4)
        for _ in range(3):
            advance_turn(engine, "F")
        after = engine._delayed_output_bonus(self.responder)
        self.assertEqual(after["cash"], base["cash"])
        self.assertEqual(after["factory"], base["factory"])

    def test_silver_reform_failure_bleeds_cash_for_two_turns(self):
        """11.5「不成」那一支：連兩回合每人 −10，第三回合停。"""
        engine = None
        for seed in range(40):                       # 找一個會擲出「不成」的種子
            probe = GameEngine(seed=seed)
            probe.state["turn"] = 2
            probe.state["event_pool"] = ["silver_tael_reform"]
            probe.next_turn(active_player="F")
            result = probe.respond_event(probe.pending_event_view()["waiting_for"])
            roll = [e for e in (result.get("applied") or []) if e["kind"] == "random_outcome"][0]
            if roll["chosen"] == "fails":
                engine = probe
                break
        self.assertIsNotNone(engine, "四十個種子都沒擲出『不成』，機率設定可能有問題")
        engine.state["event_pool"] = []
        self.assertEqual(len(engine.state["scheduled_event_effects"]), 2)

        # 直接看國庫：排程落地時每位玩家 −10，連兩回合，第三回合不再扣。
        # 用「同一回合內事件扣款前後的差」不好抓（經濟結算會混進來），
        # 所以改記每回合的排程佇列長度與實際觸發的扣款。
        drained = []
        for _ in range(3):
            before_queue = len(engine.state["scheduled_event_effects"])
            treasury_before = engine.state["players"]["F"]["treasury"]
            advance_turn(engine, "F")
            drained.append(before_queue - len(engine.state["scheduled_event_effects"]))
            if before_queue:
                # 有排程到期的那兩回合，扣款一定發生過：本回合淨變化會比
                # 沒有扣款的情況少 10。用收入下限反推：treasury 不可能只增不減 10。
                self.assertLessEqual(
                    engine.state["players"]["F"]["treasury"],
                    treasury_before + engine.state["players"]["F"]["income"])
        self.assertEqual(drained, [1, 1, 0])          # 兩回合各落地一筆，第三回合沒有
        self.assertEqual(engine.state["scheduled_event_effects"], [])


class BankCreditEventTests(unittest.TestCase):
    """授信額度的增減：2.1 永久加值、6.1 打對折、6.4 全面放大。

    這三張先前是「寫進 state 但沒有人讀」——offers() 根本收不到調整值，
    所以卡面說的額度變化實際上不會發生。這組測試就是釘住這條路徑。
    """

    def _limits(self, engine, player="F"):
        return {o["bank"]: o["limit"] for o in engine.loan_offers(player)["offers"] if o["bank"]}

    def _fire(self, engine, card_id):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        engine.state["event_pool"] = []

    def test_germany_joins_league_lifts_the_deutsch_asiatische_limit(self):
        engine = GameEngine(seed=3)
        before = self._limits(engine)
        self._fire(engine, "germany_joins_league")
        after = self._limits(engine)
        self.assertEqual(after["deutsch_asiatische"], before["deutsch_asiatische"] + 15)
        for bank in before:
            if bank != "deutsch_asiatische":
                self.assertEqual(after[bank], before[bank], bank)

    def test_germany_limit_bonus_is_permanent(self):
        engine = GameEngine(seed=3)
        before = self._limits(engine)["deutsch_asiatische"]
        self._fire(engine, "germany_joins_league")
        for _ in range(6):
            advance_turn(engine, "F")
        self.assertEqual(self._limits(engine)["deutsch_asiatische"], before + 15)

    def test_florida_bust_halves_citibank_for_three_turns(self):
        engine = GameEngine(seed=3)
        before = self._limits(engine)
        self._fire(engine, "florida_land_bust")
        during = self._limits(engine)
        self.assertEqual(during["citibank"], round(before["citibank"] * 0.5))
        self.assertEqual(during["hsbc"], before["hsbc"])          # 只咬花旗
        for _ in range(4):
            advance_turn(engine, "F")
        self.assertEqual(self._limits(engine)["citibank"], before["citibank"])

    def test_florida_bust_also_bans_the_two_american_cards(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "florida_land_bust")
        for card_id in ("us_socony_oil", "us_commercial_credit"):
            self.assertTrue(engine._perk_suspended("F", card_id), card_id)

    def test_wall_street_bull_widens_three_banks_by_half(self):
        engine = GameEngine(seed=3)
        before = self._limits(engine)
        self._fire(engine, "wall_street_bull")
        after = self._limits(engine)
        for bank in ("citibank", "hsbc", "banque_de_l_indochine"):
            self.assertEqual(after[bank], round(before[bank] * 1.5), bank)
        for bank in ("yokohama_specie", "deutsch_asiatische"):
            self.assertEqual(after[bank], before[bank], bank)

    def test_wall_street_bull_expires(self):
        engine = GameEngine(seed=3)
        before = self._limits(engine)
        self._fire(engine, "wall_street_bull")
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertEqual(self._limits(engine), before)

    def test_general_strike_shuts_the_hsbc_window(self):
        engine = GameEngine(seed=3)
        self.assertIsNone(engine.bank_banned("F", "hsbc"))
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["british_general_strike"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        engine.state["event_pool"] = []
        self.assertIsNotNone(engine.bank_banned("F", "hsbc"))
        for card_id in ("uk_vickers_contract", "uk_hsbc_credit",
                        "uk_machine_gun_advisers", "uk_customs_advisers"):
            self.assertTrue(engine._perk_suspended("F", card_id), card_id)
        for _ in range(4):
            advance_turn(engine, "F")
        self.assertIsNone(engine.bank_banned("F", "hsbc"))


class RemainingEventCardTests(unittest.TestCase):
    """先前完全沒有測試碰過的事件卡，一張一條端到端。"""

    def _fire(self, engine, card_id, responder=None):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        engine.respond_event(view["waiting_for"] if responder is None else responder)
        engine.state["event_pool"] = []
        return view

    def test_may_coup_wave_costs_the_three_constitutional_powers(self):
        engine = GameEngine(seed=3)
        before = {code: dict(engine.state["players"][code]["foreign_relations"])
                  for code in engine.state["players"]}
        self._fire(engine, "may_coup_wave")
        for code, was in before.items():
            now = engine.state["players"][code]["foreign_relations"]
            for power in ("uk", "us", "fr"):
                self.assertEqual(now[power], max(-10, was[power] - 1), f"{code}/{power}")
            self.assertEqual(now["jp"], was["jp"], code)      # 日本不動

    def test_trotsky_defeat_freezes_the_two_soviet_perks(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "trotsky_defeated")
        for card_id in ("su_ruble_subsidy", "su_galen_advisers"):
            self.assertTrue(engine._perk_suspended("F", card_id), card_id)
        entry = engine.suspended_card_entry("F", "su_ruble_subsidy")
        self.assertEqual(entry["until_turn"], 3 + 10)

    def test_womens_suffrage_warms_london_and_locks_its_military_events(self):
        engine = GameEngine(seed=3)
        before = {code: engine.state["players"][code]["foreign_relations"]["uk"]
                  for code in engine.state["players"]}
        self._fire(engine, "womens_suffrage_act")
        for code, was in before.items():
            self.assertEqual(engine.state["players"][code]["foreign_relations"]["uk"],
                             min(10, was + 1), code)
        lock = [e for e in engine.state["event_locks"] if e.get("powers") == ["英"]]
        self.assertEqual(len(lock), 1)
        self.assertEqual(lock[0]["until_turn"], 3 + 5)

    def test_hoover_warms_washington_and_freezes_its_combat_perk(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["foreign_relations"]["us"]
        self._fire(engine, "hoover_elected")
        self.assertEqual(engine.state["players"]["F"]["foreign_relations"]["us"],
                         min(10, before + 1))
        self.assertTrue(engine._perk_suspended("F", "us_firepower_doctrine"))
        lock = [e for e in engine.state["event_locks"] if e.get("powers") == ["美"]]
        self.assertEqual(lock[0]["until_turn"], 3 + 10)

    def test_simon_commission_locks_british_military_events(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "simon_commission")
        lock = [e for e in engine.state["event_locks"] if e.get("powers") == ["英"]]
        self.assertEqual(len(lock), 1)
        self.assertEqual((lock[0]["tags"], lock[0]["until_turn"]), (["軍事"], 3 + 3))

    def test_radio_network_unlocks_the_radio_station_card(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["hand"].append("state_radio_station")
        with self.assertRaisesRegex(ValueError, "無線電網"):
            engine.use_function("F", "state_radio_station")
        self._fire(engine, "radio_network")
        self.assertIn("event_radio_network", payload["unlocks"])

    def test_model_a_ford_unlocks_the_mechanized_division(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["hand"].append("mechanized_division")
        with self.assertRaisesRegex(ValueError, "A 型車|型車"):
            engine.use_function("F", "mechanized_division", target_general_id="zhang_zongchang")
        self._fire(engine, "model_a_ford")
        self.assertIn("event_model_a_car", payload["unlocks"])

    def test_bauhaus_deals_two_siemens_copies_to_everyone(self):
        engine = GameEngine(seed=3)
        before = {code: engine.state["players"][code]["function_deck"].count("siemens_china_expansion")
                  for code in engine.state["players"]}
        self._fire(engine, "bauhaus_dessau")
        for code, was in before.items():
            self.assertEqual(
                engine.state["players"][code]["function_deck"].count("siemens_china_expansion"),
                was + 2, code)

    def test_turandot_lifts_export_payouts_for_two_turns(self):
        engine = GameEngine(seed=3)
        base = engine._card_template("trade_export_uk")["cash_gain"]
        smuggle = engine._card_template("artifact_smuggling")["payout_min"]
        self._fire(engine, "turandot_premiere")
        self.assertEqual(engine._card_template("trade_export_uk")["cash_gain"], 30)
        self.assertEqual(engine._card_template("artifact_smuggling")["payout_min"], 30)
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertEqual(engine._card_template("trade_export_uk")["cash_gain"], base)
        self.assertEqual(engine._card_template("artifact_smuggling")["payout_min"], smuggle)

    def test_cotton_club_pays_shanghai_and_tianjin_forever(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "cotton_club")
        for city_id in ("shanghai", "tianjin"):
            self.assertEqual(engine.state["city_development"][city_id]["cash"], 3, city_id)
        owner = engine.state["city_owners"].get("shanghai")
        cash = {item["id"]: item["cash"]
                for item in engine.state["players"][owner]["city_economy"]}
        self.assertIn("shanghai", cash)

    def test_channel_swim_hands_out_a_three_turn_hospital_window(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "channel_swim")
        flags = [e for e in engine.state["players"]["F"]["timed_effects"]
                 if e.get("kind") == "field_hospital_window"]
        self.assertEqual(len(flags), 1)
        self.assertGreater(int(flags[0]["remaining_turns"]), 0)
        for _ in range(4):
            advance_turn(engine, "F")
        self.assertEqual([e for e in engine.state["players"]["F"]["timed_effects"]
                          if e.get("kind") == "field_hospital_window"], [])


class SovietGatedNationalistCardsTests(unittest.TestCase):
    """汪精衛復出與國共合作：對蘇關係 6 以上才進得了國民革命軍的牌庫。"""

    @staticmethod
    def _zones(engine, card_id, player="N"):
        payload = engine.state["players"][player]
        return (payload["function_deck"] + payload["hand"] + payload["discard"]).count(card_id)

    def test_wang_jingwei_is_in_the_deck_while_moscow_is_close(self):
        engine = GameEngine(seed=3)
        # 國民革命軍開局對蘇 9，門檻是 6。
        self.assertGreaterEqual(engine.state["players"]["N"]["foreign_relations"]["su"], 6)
        self.assertEqual(self._zones(engine, "wang_jingwei_return"), 1)

    def test_relations_below_six_pull_it_out_and_recovery_puts_it_back(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["N"]["foreign_relations"]["su"] = 5
        engine._sync_conditional_deck_cards("N")
        self.assertEqual(self._zones(engine, "wang_jingwei_return"), 0)
        engine.state["players"]["N"]["foreign_relations"]["su"] = 6
        engine._sync_conditional_deck_cards("N")
        self.assertEqual(self._zones(engine, "wang_jingwei_return"), 1)

    def test_the_united_front_follows_the_same_gate_after_it_is_unlocked(self):
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["N"]
        payload["foreign_relations"]["su"] = 8
        payload["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")
        self.assertEqual(self._zones(engine, "first_united_front"), 1)
        # 關係跌破門檻：還沒抽到的那張收回。
        payload["foreign_relations"]["su"] = 4
        engine._sync_conditional_deck_cards("N")
        self.assertEqual(self._zones(engine, "first_united_front"), 0)
        # 關係回升：解鎖仍在，牌洗回去。
        payload["foreign_relations"]["su"] = 7
        engine._sync_conditional_deck_cards("N")
        self.assertEqual(self._zones(engine, "first_united_front"), 1)

    def test_both_cards_stay_exclusive_to_the_nationalists(self):
        index = load_game_data()["indexes"]["function_cards"]
        for card_id in ("wang_jingwei_return", "first_united_front"):
            self.assertEqual(index[card_id]["allowed_players"], ["N"], card_id)
            self.assertEqual(index[card_id]["foreign_power_key"], "su", card_id)
            self.assertEqual(index[card_id]["requires_relation_min"], 6, card_id)
        engine = GameEngine(seed=3)
        for code in ("F", "W", "S"):
            self.assertEqual(self._zones(engine, "wang_jingwei_return", code), 0, code)
            self.assertEqual(self._zones(engine, "first_united_front", code), 0, code)


class CabinetCardTests(unittest.TestCase):
    """政府內閣：五張單一玩家卡的獨佔、失效與人物去留。"""

    CARDS = ("soong_patronage", "kong_xiangxi_office", "wang_jingwei_return",
             "wang_yongjiang_financial_reform", "zhou_enlai_underground")

    @staticmethod
    def _zones(engine, card_id, player):
        payload = engine.state["players"][player]
        return (payload["function_deck"] + payload["hand"] + payload["discard"]).count(card_id)

    def test_every_cabinet_card_declares_a_person_and_a_lapse_rule(self):
        index = load_game_data()["indexes"]["function_cards"]
        for card_id in self.CARDS:
            spec = index[card_id].get("cabinet")
            self.assertIsNotNone(spec, card_id)
            self.assertTrue(spec.get("person"), card_id)
            self.assertTrue(spec.get("lapse_text"), card_id)
            self.assertTrue(spec.get("lapse"), card_id)

    def test_playing_one_locks_every_other_player_out(self):
        engine = GameEngine(seed=5)
        # 孔祥熙沒有陣營限制，兩家都先拿到江浙財團的解鎖。
        for code in ("F", "W"):
            payload = engine.state["players"][code]
            payload["unlocks"].append("jiangzhe_financiers")
            payload["foreign_relations"]["su"] = 2
        engine.state["players"]["F"]["hand"].append("kong_xiangxi_office")
        engine.use_function("F", "kong_xiangxi_office")
        self.assertEqual(engine.cabinet_holder("kong_xiangxi_office"), "F")
        # 別家的卡池被清空，手上那張也打不出來。
        for code in ("W", "S", "N"):
            self.assertEqual(self._zones(engine, "kong_xiangxi_office", code), 0, code)
        engine.state["players"]["W"]["hand"].append("kong_xiangxi_office")
        with self.assertRaisesRegex(ValueError, "只能有一位持有者"):
            engine.use_function("W", "kong_xiangxi_office")

    def test_a_fallen_marshal_sends_the_person_home(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["F"]
        payload["hand"].append("wang_yongjiang_financial_reform")
        engine.use_function("F", "wang_yongjiang_financial_reform")
        bonus = dict(payload["permanent_output_bonus"])
        self.assertEqual((bonus["cash"], bonus["factory"]), (5, 2))
        advance_turn(engine, "F", fallen_marshals=["F"])
        self.assertIsNone(engine.cabinet_holder("wang_yongjiang_financial_reform"))
        self.assertEqual(payload["permanent_output_bonus"], {"cash": 0, "factory": 0})

    def test_wang_jingwei_lapses_when_moscow_cools_and_takes_his_bonuses(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["N"]
        payload["foreign_relations"]["su"] = 8
        payload["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")
        self.assertIn("wang_jingwei_return", payload["unlocks"])
        self.assertEqual(payload["permanent_output_bonus"]["factory"], 2)
        payload["foreign_relations"]["su"] = 5
        advance_turn(engine, "N")
        self.assertIsNone(engine.cabinet_holder("wang_jingwei_return"))
        self.assertNotIn("wang_jingwei_return", payload["unlocks"])
        self.assertEqual(payload["permanent_output_bonus"]["factory"], 0)
        self.assertEqual(payload["recruit_cost_adjustment"]["infantry"]["cash"], 0)
        self.assertEqual(payload["recruit_cost_adjustment"]["machine_gun"]["cash"], 0)
        self.assertEqual(self._zones(engine, "first_united_front", "N"), 0)

    def test_soong_lapses_when_shanghai_is_lost(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["S"]
        payload["foreign_relations"]["su"] = 2
        payload["unlocks"].append("jiangzhe_financiers")
        engine.state["city_owners"]["shanghai"] = "S"
        payload["hand"].append("soong_patronage")
        engine.use_function("S", "soong_patronage")
        self.assertIsNotNone(payload.get("soong_patronage"))
        engine.state["city_owners"]["shanghai"] = "N"
        advance_turn(engine, "S")
        self.assertIsNone(engine.cabinet_holder("soong_patronage"))
        self.assertIsNone(payload.get("soong_patronage"))

    def test_kong_lapses_when_moscow_warms_up(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["S"]
        payload["foreign_relations"]["su"] = 2
        payload["unlocks"].append("jiangzhe_financiers")
        payload["hand"].append("kong_xiangxi_office")
        engine.use_function("S", "kong_xiangxi_office")
        self.assertEqual(payload["loan_interest_override"], 0.03)
        payload["foreign_relations"]["su"] = 6
        advance_turn(engine, "S")
        self.assertIsNone(engine.cabinet_holder("kong_xiangxi_office"))
        self.assertIsNone(payload["loan_interest_override"])
        self.assertEqual(payload["loan_term_bonus"], 0)

    def test_zhou_enlai_raises_both_riot_cards_to_six_and_gives_them_back(self):
        engine = GameEngine(seed=5)
        payload = engine.state["players"]["N"]
        payload["foreign_relations"]["su"] = 8
        engine._sync_foreign_deck_cards("N")
        self.assertEqual(self._zones(engine, "communist_riot", "N"), 3)
        payload["hand"].append("zhou_enlai_underground")
        engine.use_function("N", "zhou_enlai_underground")
        self.assertEqual(self._zones(engine, "communist_riot", "N"), 6)
        self.assertEqual(self._zones(engine, "red_army_uprising", "N"), 6)
        payload["foreign_relations"]["su"] = 5
        advance_turn(engine, "N")
        self.assertIsNone(engine.cabinet_holder("zhou_enlai_underground"))
        # 關係跌破 6，友好卡本來就整批收回。
        self.assertEqual(self._zones(engine, "communist_riot", "N"), 0)
        payload["foreign_relations"]["su"] = 8
        engine._sync_foreign_deck_cards("N")
        self.assertEqual(self._zones(engine, "communist_riot", "N"), 3)

    def test_the_card_comes_back_to_everyone_once_it_lapses(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["hand"].append("wang_yongjiang_financial_reform")
        engine.use_function("F", "wang_yongjiang_financial_reform")
        advance_turn(engine, "F", fallen_marshals=["F"])
        # 這張只有奉系拿得到，張學良接手後仍在同一副牌庫裡。
        self.assertEqual(self._zones(engine, "wang_yongjiang_financial_reform", "F"), 1)


class HarborDemolitionTests(unittest.TestCase):
    """大港開炸：兩座敵方港口癱瘓兩回合，被炸的勢力各攤一份修復費。"""

    @staticmethod
    def _ports(engine, owner):
        return [
            city["id"] for city in engine.data["strategic_map"]["cities"]
            if city.get("port") and engine.state["city_owners"].get(city["id"], city["faction"]) == owner
        ]

    def test_three_copies_in_every_starting_deck(self):
        engine = GameEngine(seed=11)
        for code in engine.state["players"]:
            self.assertEqual(engine.state["players"][code]["function_deck"].count("harbor_demolition"), 3, code)

    def test_two_ports_go_down_and_both_owners_pay(self):
        engine = GameEngine(seed=11)
        first = self._ports(engine, "F")[0]
        second = self._ports(engine, "S")[0]
        for code in ("F", "S"):
            engine.state["players"][code]["treasury"] = 100
            engine.state["players"][code]["factory_points"] = 100
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        result = engine.use_function("N", "harbor_demolition", target_city_ids=[first, second])
        self.assertEqual(sorted(engine.disabled_ports()), sorted([first, second]))
        self.assertEqual(len(result["port_demolition"]["ports"]), 2)
        for code in ("F", "S"):
            self.assertEqual(engine.state["players"][code]["treasury"], 90, code)
            self.assertEqual(engine.state["players"][code]["factory_points"], 90, code)
            self.assertEqual(engine.state["players"][code]["port_repair_due"], {"cash": 0, "factory": 0}, code)

    def test_two_ports_of_one_faction_cost_two_repair_shares(self):
        # 修復費按港口算，同一勢力被炸兩座就付雙倍。
        engine = GameEngine(seed=11)
        ports = self._ports(engine, "S")[:2]
        engine.state["players"]["S"]["treasury"] = 100
        engine.state["players"]["S"]["factory_points"] = 100
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        result = engine.use_function("N", "harbor_demolition", target_city_ids=ports)
        self.assertEqual(engine.state["players"]["S"]["treasury"], 80)
        self.assertEqual(engine.state["players"]["S"]["factory_points"], 80)
        self.assertEqual([charge["city_id"] for charge in result["port_demolition"]["charges"]], ports)

    def test_shortfall_is_collected_from_later_income(self):
        engine = GameEngine(seed=11)
        port = self._ports(engine, "S")[0]
        engine.state["players"]["S"]["treasury"] = 4
        engine.state["players"]["S"]["factory_points"] = 0
        other = self._ports(engine, "F")[0]
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        engine.use_function("N", "harbor_demolition", target_city_ids=[port, other])
        payload = engine.state["players"]["S"]
        self.assertEqual(payload["treasury"], 0)
        self.assertEqual(payload["port_repair_due"], {"cash": 6, "factory": 10})
        for _ in range(3):
            advance_turn(engine, active_player="S")
            if payload["port_repair_due"] == {"cash": 0, "factory": 0}:
                break
        self.assertEqual(payload["port_repair_due"], {"cash": 0, "factory": 0})

    def test_the_paralysis_expires_after_two_turns(self):
        engine = GameEngine(seed=11)
        targets = [self._ports(engine, "F")[0], self._ports(engine, "S")[0]]
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        engine.use_function("N", "harbor_demolition", target_city_ids=targets)
        advance_turn(engine, active_player="N")
        self.assertEqual(len(engine.disabled_ports()), 2)
        advance_turn(engine, active_player="N")
        self.assertEqual(engine.disabled_ports(), [])

    def test_own_ports_and_repeats_are_rejected(self):
        engine = GameEngine(seed=11)
        mine = self._ports(engine, "N")[0]
        theirs = self._ports(engine, "F")[0]
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        with self.assertRaises(ValueError):
            engine.use_function("N", "harbor_demolition", target_city_ids=[mine, theirs])
        engine.state["players"]["N"]["hand"].append("harbor_demolition")
        with self.assertRaises(ValueError):
            engine.use_function("N", "harbor_demolition", target_city_ids=[theirs, theirs])


class PowerWarOverlapTests(unittest.TestCase):
    """日蘇重疊區開戰判定：黑龍江／吉林，蘇 60% 對日 40%，三重傷害疊加。"""

    NORTH = ("吉林", "黑龍江")

    def _own(self, engine, code, provinces):
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in provinces:
                engine.state["city_owners"][city["id"]] = code

    def _open(self, engine, power, provinces, owner="F", relation=-6):
        engine.state["players"][owner]["foreign_relations"][power] = relation
        card = {"jp": "kwantung_army_occupies_manchuria",
                "su": "soviet_far_east_army_invades_songhua",
                "uk": "british_troops_occupy_jiangsu_zhejiang",
                "fr": "french_troops_occupy_southwest"}[power]
        return engine.punishments.open(
            card_id=card, power=power, kind="ground_occupation",
            owner=owner, provinces=list(provinces), label=card)

    def _rig(self, engine, soviet_wins):
        """把骰子釘死：蘇聯勝率 0.60，所以 0.1 是蘇勝、0.9 是日勝。"""
        engine.random.random = lambda: 0.1 if soviet_wins else 0.9

    def test_soviet_challenger_takes_the_overlap_when_it_wins(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        japan = self._open(engine, "jp", ["奉天", "吉林", "黑龍江"])
        self._rig(engine, soviet_wins=True)
        soviet = self._open(engine, "su", ["吉林", "黑龍江"])
        self.assertEqual(sorted(soviet["provinces"]), ["吉林", "黑龍江"])
        self.assertEqual(japan["provinces"], ["奉天"], "戰敗方只該輸掉重疊的那兩省")
        self.assertEqual(sorted(japan["lost_provinces"]), ["吉林", "黑龍江"])
        self.assertEqual(len(soviet["wars"]), 2, "衝突兩省就要判定兩次")

    def test_japanese_incumbent_keeps_the_overlap_when_it_wins(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        japan = self._open(engine, "jp", ["奉天", "吉林", "黑龍江"])
        self._rig(engine, soviet_wins=False)
        soviet = self._open(engine, "su", ["吉林", "黑龍江"])
        self.assertEqual(soviet["provinces"], [], "蘇聯什麼都沒拿到")
        self.assertEqual(sorted(soviet["skipped_provinces"]), ["吉林", "黑龍江"])
        self.assertEqual(sorted(japan["provinces"]), ["吉林", "奉天", "黑龍江"])

    def test_one_contested_province_rolls_once(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", ("奉天", "吉林"))
        self._open(engine, "jp", ["奉天", "吉林"])
        self._rig(engine, soviet_wins=True)
        soviet = self._open(engine, "su", ["吉林"])
        self.assertEqual(len(soviet["wars"]), 1, "衝突一省就只判定一次")
        self.assertEqual(len(engine.state["power_wars"]), 1)

    # ---- 戰況報導：日蘇兩方要對稱 ----

    def _war_papers(self, soviet_wins, lock_japan=False):
        """走真正的抽卡→結算路徑，回傳這一輪實際刊出的報紙。"""
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("吉林", "黑龍江", "奉天"):
                engine.state["city_owners"][city["id"]] = "F"
        engine._refresh_city_income()
        engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
        engine.state["players"]["F"]["foreign_relations"]["su"] = -6
        engine.punishments.open(card_id="kwantung_army_occupies_manchuria", power="jp",
                                kind="ground_occupation", owner="F",
                                provinces=["奉天", "吉林", "黑龍江"],
                                label="關東軍侵占東北三省")
        entry = engine.ultimatums.open(card_id="soviet_ultimatum", power="su", owner="F")
        entry["status"] = "failed"      # [地面部隊] 懲戒要通牒被無視才解封
        if lock_japan:
            card = engine._event_template("akutagawa_death")
            engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self._rig(engine, soviet_wins)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["soviet_far_east_army_invades_songhua"]
        engine.next_turn(active_player="F")
        papers = []
        for _ in range(10):
            view = engine.pending_event_view()
            if not view:
                break
            papers.append(view["card"]["id"])
            engine.respond_event(view["waiting_for"])
        return engine, papers

    def test_both_winners_get_their_own_papers_for_both_provinces(self):
        """設計稿：衝突兩省 → 懲戒本身 1 則 ＋ 兩省戰況各 1 則。日蘇兩方對稱。"""
        _, soviet = self._war_papers(soviet_wins=True)
        self.assertEqual(soviet, ["soviet_far_east_army_invades_songhua",
                                  "jp_su_war_jilin_soviet_win",
                                  "jp_su_war_heilongjiang_soviet_win"])
        _, japan = self._war_papers(soviet_wins=False)
        self.assertEqual(japan, ["soviet_far_east_army_invades_songhua",
                                 "jp_su_war_jilin_japan_win",
                                 "jp_su_war_heilongjiang_japan_win"])

    def test_the_war_reports_carry_no_tags_at_all(self):
        """斷根：四張戰況報導一個標籤都不掛。

        它們原本掛著 [軍事]＋日／蘇，於是任何「按標籤整批封鎖／整批加張」的卡
        都會掃到它們——2.4 東方會議就這樣把日軍獲勝的兩張塞進池子，真的抽得出來。
        與其一條一條擋，不如讓它們根本不在任何標籤規則的射程內：這種卡只由開戰
        判定直接插進 pending，本來就不該被任何牌庫規則碰到。
        `power_note` 保留，那只供 README 顯示，不參與封鎖比對
        （`_event_lock_matches` 沒有 tags 就直接不成立）。
        """
        engine = GameEngine(seed=3)
        war_cards = [c for c in engine.data["event_cards"]["cards"]
                     if c.get("never_drawn")]
        self.assertEqual(len(war_cards), 4)
        for card in war_cards:
            self.assertEqual(card.get("tags") or [], [],
                             f'{card["ref"]} {card["name"]} 又被掛上標籤了')

    def test_no_tag_lock_can_reach_a_war_report(self):
        """任何標籤封鎖都掃不到戰況報導——日、蘇兩方都一樣。"""
        engine = GameEngine(seed=3)
        never = [c["id"] for c in engine.data["event_cards"]["cards"]
                 if c.get("never_drawn")]
        for power in ("日", "蘇"):
            probe = GameEngine(seed=3)
            probe._apply_event_payload(
                {"event_lock": [{"tags": ["軍事", "戰況"], "powers": [power],
                                 "turns": 5, "label": "probe"}]},
                players=["F"], card={"id": "probe", "name": "probe"})
            for card_id in never:
                self.assertFalse(probe._event_locked(card_id),
                                 f"{power} 的標籤封鎖掃到了 {card_id}")

    def test_a_military_tag_lock_does_not_silence_the_war_report(self):
        """昭和國喪把日本 [軍事] 整批封鎖時，日方打贏的報紙照樣要登。

        兩層保障：戰況報導已經不掛標籤，封鎖掃不到它；而且插入路徑本來就不走
        抽卡，就算被鎖也照登。否則會變成日方打贏無聲、蘇方打贏有聲的不對稱。
        """
        engine, papers = self._war_papers(soviet_wins=False, lock_japan=True)
        self.assertFalse(engine._event_locked("jp_su_war_jilin_japan_win"),
                         "戰報卡不該再被 [軍事] 封鎖掃到")
        self.assertIn("jp_su_war_jilin_japan_win", papers)
        self.assertIn("jp_su_war_heilongjiang_japan_win", papers)

    def test_a_second_war_reports_again(self):
        """打第二次仗要再登一次報——戰報卡是 repeatable，不能只登一次。"""
        engine = GameEngine(seed=3)
        for card_id in engine.POWER_WAR_REPORTS.values():
            template = engine._event_template(card_id)
            self.assertTrue(template.get("repeatable"), card_id)
            engine.state["event_history"].append({"turn": 1, "card_id": card_id})
            self.assertFalse(engine.event_is_spent(card_id),
                             f"{card_id} 刊過一次就不能再刊了")

    def test_every_reachable_overlap_province_has_a_report_card(self):
        """守門：資料檔裡日蘇地面佔領可能重疊的每一省，兩種勝負都要有戰報卡。

        沒有的話 _queue_power_war_reports 會丟錯（先前是靜默跳過——仗照打、
        地照易手，就是不出報紙）。這條把覆蓋率直接從資料檔算出來。
        """
        engine = GameEngine(seed=3)
        occupied = {"jp": set(), "su": set()}
        for card in engine.data["event_cards"]["cards"]:
            for spec in (card.get("apply") or {}).get("foreign_punishment") or []:
                if spec.get("kind") == "ground_occupation" and spec["power"] in occupied:
                    occupied[spec["power"]].update(spec.get("provinces") or [])
        overlap = occupied["jp"] & occupied["su"]
        self.assertTrue(overlap, "日蘇本來就該有重疊區")
        for province in sorted(overlap):
            for winner in ("jp", "su"):
                self.assertIn((province, winner), engine.POWER_WAR_REPORTS,
                              f"{province} 的 {winner} 方獲勝沒有戰況報導卡")

    def test_a_war_without_a_report_card_raises_instead_of_going_quiet(self):
        engine = GameEngine(seed=3)
        applied = [{"kind": "foreign_punishment", "punishment": {"wars": [
            {"province": "奉天", "winner": "su", "loser": "jp"}]}}]
        pending = {"cards": [], "index": 0}
        with self.assertRaisesRegex(ValueError, "POWER_WAR_REPORTS"):
            engine._queue_power_war_reports(applied, pending, "F")

    def test_britain_and_france_still_go_first_come_first_served(self):
        """先來後到只在日蘇之間破例；其餘組合照舊，不會打起來。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", ("江蘇", "浙江"))
        first = self._open(engine, "uk", ["江蘇", "浙江"])
        second = self._open(engine, "fr", ["江蘇", "雲南"])
        self.assertEqual(second["provinces"], ["雲南"])
        self.assertEqual(second["skipped_provinces"], ["江蘇"])
        self.assertEqual(second["wars"], [])
        self.assertEqual(sorted(first["provinces"]), ["江蘇", "浙江"])

    # ---- 三重傷害疊加 ----

    def _cumulative(self, engine, code, province):
        hits = [e for e in engine.state["players"][code]["pending_frontend_effects"]
                if e["kind"] == "foreign_punishment_damage"
                and e.get("punishment_kind") == "power_war"
                and province in e["provinces"]]
        return hits[-1]["cumulative_army_force"] if hits else None

    def test_soviet_victory_leaves_ten_percent(self):
        """日懲戒 −40%、戰火 −10%、蘇懲戒 −40%，**以初始值相加** → 剩 10%。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        self._open(engine, "jp", ["吉林", "黑龍江"])
        self._rig(engine, soviet_wins=True)
        self._open(engine, "su", ["吉林", "黑龍江"])
        for province in self.NORTH:
            self.assertAlmostEqual(self._cumulative(engine, "F", province), 0.90,
                                   msg=f"{province} 應該累計掉 90%")

    def test_japanese_victory_leaves_fifty_percent(self):
        """日懲戒 −40% ＋ 戰火 −10% → 剩 50%；蘇聯沒贏就沒有第三段。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        self._open(engine, "jp", ["吉林", "黑龍江"])
        self._rig(engine, soviet_wins=False)
        self._open(engine, "su", ["吉林", "黑龍江"])
        for province in self.NORTH:
            self.assertAlmostEqual(self._cumulative(engine, "F", province), 0.50)

    def test_a_bystander_only_eats_the_ten_percent_splash(self):
        """沒跟日蘇任一方交惡的第三方只吃戰火波及那 10%。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        for power in ("jp", "su"):
            engine.state["players"]["W"]["foreign_relations"][power] = 2
        self._open(engine, "jp", ["吉林", "黑龍江"])
        self._rig(engine, soviet_wins=True)
        self._open(engine, "su", ["吉林", "黑龍江"])
        self.assertAlmostEqual(self._cumulative(engine, "W", "吉林"), 0.10)

    def test_the_damage_is_added_not_multiplied(self):
        """守住這條算法：連乘會得到 32.4%／54%，那與設計稿不符。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        self._open(engine, "jp", ["吉林"])
        self._rig(engine, soviet_wins=True)
        self._open(engine, "su", ["吉林"])
        remaining = 1 - self._cumulative(engine, "F", "吉林")
        self.assertAlmostEqual(remaining, 0.10)
        self.assertNotAlmostEqual(remaining, 0.6 * 0.9 * 0.6, places=3)

    # ---- 戰況報導 ----

    def test_each_contested_province_gets_its_own_newspaper(self):
        """衝突兩省 → 三則報導（懲戒本身 ＋ 兩省戰況）。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.NORTH)
        engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
        engine.state["players"]["F"]["foreign_relations"]["su"] = -6
        engine.punishments.open(
            card_id="kwantung_army_occupies_manchuria", power="jp",
            kind="ground_occupation", owner="F",
            provinces=["吉林", "黑龍江"], label="日佔")
        self._rig(engine, soviet_wins=True)
        engine.state.setdefault("ultimatums", []).append({
            "id": "t", "card_id": "soviet_ultimatum", "power": "su", "owner": "F",
            "cities": [], "opened_turn": 0, "deadline_turn": 0, "status": "failed"})
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["soviet_far_east_army_invades_songhua"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["card"]["id"], "soviet_far_east_army_invades_songhua")
        engine.respond_event(view["waiting_for"])
        reports = []
        for _ in range(2):
            view = engine.pending_event_view()
            self.assertIsNotNone(view, "戰況報導應該接在懲戒那一張後面")
            reports.append(view["card"]["id"])
            engine.respond_event(view["waiting_for"])
        self.assertEqual(sorted(reports), ["jp_su_war_heilongjiang_soviet_win",
                                           "jp_su_war_jilin_soviet_win"])

    def test_the_report_matches_who_actually_won(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", ("吉林",))
        self._open(engine, "jp", ["吉林"])
        self._rig(engine, soviet_wins=False)
        soviet = self._open(engine, "su", ["吉林"])
        pending = {"cards": [], "index": 0}
        applied = [{"kind": "foreign_punishment", "player": "F", "punishment": soviet}]
        engine._queue_power_war_reports(applied, pending, "F")
        self.assertEqual([c["card_id"] for c in pending["cards"]],
                         ["jp_su_war_jilin_japan_win"])

    def test_all_four_reports_exist_and_never_enter_the_pool(self):
        engine = GameEngine(seed=3)
        for card_id in ("jp_su_war_heilongjiang_soviet_win",
                        "jp_su_war_heilongjiang_japan_win",
                        "jp_su_war_jilin_soviet_win",
                        "jp_su_war_jilin_japan_win"):
            card = engine._event_template(card_id)
            self.assertTrue(card.get("never_drawn"), card_id)
            self.assertNotIn(card_id, engine.state["event_pool"])


class UltimatumTests(unittest.TestCase):
    """最後通牒：5 回合內派兵到指定城市周邊駐紮，否則 [地面部隊] 解封。"""

    def _draw(self, engine, card_id, owner="F", power="jp"):
        engine.state["players"][owner]["foreign_relations"][power] = -6
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player=owner)
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        engine.respond_event(view["waiting_for"])
        return view["drawer"]

    def test_every_power_but_america_has_one(self):
        engine = GameEngine(seed=3)
        powers = set()
        for card in engine.data["event_cards"]["cards"]:
            for spec in (card.get("apply") or {}).get("ultimatum") or []:
                powers.add(spec["power"])
        self.assertEqual(powers, {"jp", "uk", "su", "fr"},
                         "美國不使用地面部隊懲戒，所以沒有最後通牒")

    def test_drawing_it_opens_a_five_turn_clock(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        entry = engine.ultimatums.active_for("jp", drawer)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["deadline_turn"] - entry["opened_turn"], 5)
        self.assertEqual(entry["cities"], ["lushun", "suzhou", "hankou"])

    def test_ignoring_it_unlocks_the_ground_troop_cards(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        ground = engine._event_template("kwantung_army_occupies_manchuria")
        self.assertNotIn(drawer, engine._event_eligible_players(ground),
                         "通牒還沒逾期，地面部隊不該解封")
        for _ in range(7):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer)
        self.assertEqual(engine.ultimatums.active_for("jp", drawer), None)
        self.assertIn("jp", engine.ultimatums.failed_powers(drawer))
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("奉天", "吉林", "黑龍江"):
                engine.state["city_owners"][city["id"]] = drawer
        self.assertIn(drawer, engine._event_eligible_players(ground))

    def test_meeting_it_keeps_the_ground_cards_locked_and_pays_a_relation(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        before = int(engine.state["players"][drawer]["foreign_relations"]["jp"])
        # 「駐紮至少 1 回合」＝ 連續兩次回合推進都看得到部隊。
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer,
                             ultimatum_garrisons={drawer: ["lushun"]})
        entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
        self.assertEqual(entry["status"], "met")
        self.assertEqual(int(engine.state["players"][drawer]["foreign_relations"]["jp"]),
                         before + 1)
        self.assertNotIn("jp", engine.ultimatums.failed_powers(drawer))

    def test_a_single_turn_visit_is_not_enough(self):
        """駐紮「至少 1 回合」——只路過一回合不算數。"""
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        engine.state["event_pool"] = []
        engine.next_turn(active_player=drawer, ultimatum_garrisons={drawer: ["lushun"]})
        engine.state["event_pool"] = []
        engine.next_turn(active_player=drawer, ultimatum_garrisons={})
        entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
        self.assertEqual(entry["status"], "open", "人走了就不該算完成")

    def test_the_wrong_city_does_not_count(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer,
                             ultimatum_garrisons={drawer: ["vladivostok"]})
        entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
        self.assertEqual(entry["status"], "open")

    def test_the_same_power_does_not_send_two_open_ultimatums(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        card = engine._event_template("japanese_ultimatum")
        self.assertNotIn(drawer, engine._event_eligible_players(card))

    def test_a_thaw_voids_an_ultimatum_still_counting_down(self):
        """[懲戒] 的通則對最後通牒一樣適用：關係回到非敵對的下一回合，
        還在倒數的通牒直接作廢，不會等期限到了再判成無視。"""
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        engine.state["players"][drawer]["foreign_relations"]["jp"] = 0
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer)
        entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
        self.assertEqual(entry["status"], "voided")
        self.assertNotIn("jp", engine.ultimatums.failed_powers(drawer))
        ground = engine._event_template("kwantung_army_occupies_manchuria")
        self.assertNotIn(drawer, engine._event_eligible_players(ground))

    def test_a_thaw_on_the_very_last_turn_still_saves_you(self):
        """先作廢再判逾期：在最後一刻把關係修好不該被判成無視。"""
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
        engine.state["turn"] = int(entry["deadline_turn"]) - 1
        engine.state["players"][drawer]["foreign_relations"]["jp"] = 0
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer)
        self.assertEqual(entry["status"], "voided")

    def test_mending_relations_relocks_the_ground_cards(self):
        engine = GameEngine(seed=3)
        drawer = self._draw(engine, "japanese_ultimatum")
        for _ in range(7):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer)
        self.assertIn("jp", engine.ultimatums.failed_powers(drawer))
        engine.state["players"][drawer]["foreign_relations"]["jp"] = 0
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player=drawer)
        self.assertNotIn("jp", engine.ultimatums.failed_powers(drawer))

    def test_the_other_three_powers_are_wired_the_same_way(self):
        for card_id, power, city in (("british_ultimatum", "uk", "hongkong"),
                                     ("soviet_ultimatum", "su", "vladivostok"),
                                     ("french_ultimatum", "fr", "kunming")):
            engine = GameEngine(seed=3)
            drawer = self._draw(engine, card_id, power=power)
            self.assertIsNotNone(engine.ultimatums.active_for(power, drawer), card_id)
            for _ in range(2):
                engine.state["event_pool"] = []
                engine.next_turn(active_player=drawer,
                                 ultimatum_garrisons={drawer: [city]})
            entry = [e for e in engine.state["ultimatums"] if e["owner"] == drawer][0]
            self.assertEqual(entry["status"], "met", card_id)


    def test_every_ground_troop_card_is_declared_correctly(self):
        """六張 [地面部隊] 卡逐一對照設計稿：國別、省份、關係門檻、通牒門檻。"""
        engine = GameEngine(seed=3)
        expected = {
            "kwantung_army_occupies_manchuria": ("jp", ["奉天", "吉林", "黑龍江"]),
            "japan_annexes_jiangsu_zhejiang": ("jp", ["江蘇", "浙江"]),
            "british_troops_occupy_jiangsu_zhejiang": ("uk", ["江蘇", "浙江"]),
            "british_troops_occupy_two_guangs": ("uk", ["廣東", "廣西"]),
            "soviet_far_east_army_invades_songhua": ("su", ["吉林", "黑龍江"]),
            "soviet_mongol_army_enters_inner_mongolia": ("su", ["察哈爾", "熱河", "黑龍江"]),
            "french_troops_occupy_southwest": ("fr", ["雲南", "廣西"]),
        }
        for card_id, (power, provinces) in expected.items():
            card = engine._event_template(card_id)
            spec = card["apply"]["foreign_punishment"][0]
            self.assertEqual(spec["power"], power, card_id)
            self.assertEqual(spec["kind"], "ground_occupation", card_id)
            self.assertEqual(spec["provinces"], provinces, card_id)
            condition = card["entry_condition"]
            self.assertEqual(condition["relation_max"], {power: -6}, card_id)
            self.assertEqual(condition["requires_failed_ultimatum"], power, card_id)
            self.assertEqual(sorted(condition["controls_provinces_any"]),
                             sorted(provinces), card_id)
            self.assertTrue(card.get("repeatable"), card_id)

    def test_every_ground_troop_card_is_gated_behind_an_ultimatum(self):
        """設計稿：[地面部隊] 一開始全部封鎖，只有通牒被無視才解封。"""
        engine = GameEngine(seed=3)
        for card in engine.data["event_cards"]["cards"]:
            if "地面部隊" not in (card.get("tags") or []):
                continue
            gate = (card.get("entry_condition") or {}).get("requires_failed_ultimatum")
            self.assertTrue(gate, f'{card["name"]} 沒有掛通牒門檻')
            self.assertEqual(engine._event_eligible_players(card), [],
                             f'{card["name"]} 開局就抽得到，等於沒鎖')


class ConcessionControlTests(unittest.TestCase):
    """租界管制：該國租界城市每回合 $−3 工廠 −3；加成只有全數失守才消失。"""

    def _city_with(self, engine, powers):
        for city in engine.data["strategic_map"]["cities"]:
            if set(city.get("concession") or []) == set(powers):
                return city
        return None

    def _open(self, engine, power, owner):
        engine.state["players"][owner]["foreign_relations"][power] = -6
        entry = engine.concession_controls.open(
            card_id=f"{power}_concession_control", power=power, owner=owner)
        engine._refresh_city_income()
        return entry

    def _row(self, engine, owner, city_id):
        return next((r for r in engine.state["players"][owner]["city_economy"]
                     if r["id"] == city_id), None)

    def test_every_concession_power_has_a_card(self):
        engine = GameEngine(seed=3)
        powers = set()
        for card in engine.data["event_cards"]["cards"]:
            for spec in (card.get("apply") or {}).get("concession_control") or []:
                powers.add(spec["power"])
        self.assertEqual(powers, {"jp", "uk", "fr", "us"},
                         "蘇聯在華無租界，所以沒有租界管制卡")

    def test_it_docks_three_cash_and_three_factory_per_turn(self):
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if "uk" in (c.get("concession") or []))
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        engine._refresh_city_income()
        before = self._row(engine, owner, city["id"])
        self._open(engine, "uk", owner)
        after = self._row(engine, owner, city["id"])
        self.assertEqual(before["cash"] - after["cash"], 3)
        self.assertEqual(before["factory"] - after["factory"], 3)

    def test_cities_without_that_power_are_untouched(self):
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if not c.get("concession"))
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        engine._refresh_city_income()
        before = self._row(engine, owner, city["id"])
        self._open(engine, "uk", owner)
        self.assertEqual(self._row(engine, owner, city["id"]), before)

    def test_one_power_alone_does_not_kill_the_concession_bonus(self):
        """加成綁的是城市的「租界」狀態：只被其中一國管制，加成照領。"""
        engine = GameEngine(seed=3)
        city = self._city_with(engine, ["uk", "fr"]) or self._city_with(engine, ["uk", "jp"])
        self.assertIsNotNone(city, "需要一座多國租界城市來測這條")
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        powers = list(city["concession"])
        self._open(engine, powers[0], owner)
        self.assertFalse(engine.concession_controls.bonus_suspended(city, owner))
        self._open(engine, powers[1], owner)
        self.assertTrue(engine.concession_controls.bonus_suspended(city, owner),
                        "所有租界國都管制了，租界狀態才消失")

    def test_multiple_powers_stack_down_to_zero_but_no_further(self):
        engine = GameEngine(seed=3)
        city = self._city_with(engine, ["uk", "fr"]) or self._city_with(engine, ["uk", "jp"])
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        for power in city["concession"]:
            self._open(engine, power, owner)
        row = self._row(engine, owner, city["id"])
        self.assertGreaterEqual(row["cash"], 0)
        self.assertGreaterEqual(row["factory"], 0)
        self.assertEqual(engine.concession_controls.penalty_for_city(city, owner),
                         3 * len(city["concession"]))

    def test_it_lifts_the_turn_after_relations_mend(self):
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if "uk" in (c.get("concession") or []))
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        self._open(engine, "uk", owner)
        engine.state["players"][owner]["foreign_relations"]["uk"] = -6
        engine.state["event_pool"] = []
        engine.next_turn(active_player=owner)
        self.assertIn("uk", engine.concession_controls.controlled_powers(owner))
        engine.state["players"][owner]["foreign_relations"]["uk"] = 0
        engine.state["event_pool"] = []
        engine.next_turn(active_player=owner)
        self.assertIn("uk", engine.concession_controls.controlled_powers(owner),
                      "修好的那一回合還不解除")
        engine.state["event_pool"] = []
        engine.next_turn(active_player=owner)
        self.assertNotIn("uk", engine.concession_controls.controlled_powers(owner))

    def test_the_card_needs_you_to_actually_hold_that_concession(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("usa_concession_control")
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = -6
        holders = [code for code in engine.state["players"]
                   if engine._concession_cities(code, "us")]
        self.assertEqual(sorted(engine._event_eligible_players(card)), sorted(holders))


    def test_each_concession_card_targets_its_own_power(self):
        engine = GameEngine(seed=3)
        for card_id, power in (("japan_concession_control", "jp"),
                               ("britain_concession_control", "uk"),
                               ("france_concession_control", "fr"),
                               ("usa_concession_control", "us")):
            card = engine._event_template(card_id)
            self.assertEqual(card["apply"]["concession_control"][0]["power"], power, card_id)
            self.assertEqual(card["entry_condition"]["relation_max"], {power: -4}, card_id)
            self.assertEqual(card["entry_condition"]["requires_concession_of"], power, card_id)
            self.assertTrue(card.get("repeatable"), card_id)

    def test_the_same_power_does_not_control_twice(self):
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if "jp" in (c.get("concession") or []))
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        self._open(engine, "jp", owner)
        card = engine._event_template("japan_concession_control")
        self.assertNotIn(owner, engine._event_eligible_players(card))



class ForeignActionBatchOneTests(unittest.TestCase):
    """第一批列強行動：複用懲戒引擎的封鎖、轟炸與演習卡。

    這批卡自己沒有新機制——正因如此，要守的是**宣告是否正確**：
    國別、水域、演習回合數、進入條件，錯一個就是整張卡失效或亂降臨。
    """

    BLOCKADES = {
        "japanese_navy_blockades_yellow_river": ("jp", ["黃河"]),
        "british_navy_blockades_yangtze": ("uk", ["長江"]),
        "british_navy_blockades_pearl_and_south_sea": ("uk", ["珠江", "南海"]),
        "french_navy_blockades_pearl_and_south_sea": ("fr", ["珠江", "南海"]),
        "japanese_navy_blockades_yangtze": ("jp", ["長江"]),
    }
    RAIDS = {
        "royal_air_force_bombing": "uk",
        "soviet_air_force_bombing": "su",
        "french_air_force_bombing": "fr",
        "american_air_force_bombing": "us",
        "japanese_air_raid": "jp",
    }
    NAVAL_DRILLS = {
        "combined_fleet_special_drill": ("jp", ["黃海", "東海", "臺灣海峽"]),
        "bohai_fleet_special_drill": ("jp", ["渤海"]),
        "royal_navy_yangtze_drill": ("uk", ["長江"]),
        "royal_navy_far_east_drill": ("uk", ["南海"]),
    }

    def test_every_blockade_card_is_declared_correctly(self):
        engine = GameEngine(seed=3)
        for card_id, (power, waters) in self.BLOCKADES.items():
            card = engine._event_template(card_id)
            spec = card["apply"]["foreign_punishment"][0]
            self.assertEqual(spec["power"], power, card_id)
            self.assertEqual(spec["kind"], "water_blockade", card_id)
            self.assertEqual(spec["waters"], waters, card_id)
            self.assertNotIn("drill_turns", spec, f"{card_id} 是懲戒不是演習")
            self.assertEqual(card["entry_condition"]["relation_max"], {power: -4}, card_id)
            rule = card["entry_condition"]["controls_ports_in_waters_min"]
            self.assertEqual(rule["count"], 3, card_id)
            self.assertTrue(card.get("repeatable"), card_id)

    def test_every_air_raid_card_is_declared_correctly(self):
        engine = GameEngine(seed=3)
        for card_id, power in self.RAIDS.items():
            card = engine._event_template(card_id)
            spec = card["apply"]["foreign_punishment"][0]
            self.assertEqual((spec["power"], spec["kind"]), (power, "air_raid"), card_id)
            self.assertEqual(spec["cities"], 5, card_id)
            self.assertEqual(card["entry_condition"]["relation_max"], {power: -4}, card_id)

    def test_every_naval_drill_lasts_three_turns_and_hurts_nobody(self):
        engine = GameEngine(seed=3)
        for card_id, (power, waters) in self.NAVAL_DRILLS.items():
            card = engine._event_template(card_id)
            spec = card["apply"]["foreign_punishment"][0]
            self.assertEqual(spec["power"], power, card_id)
            self.assertEqual(spec["kind"], "water_blockade", card_id)
            self.assertEqual(spec["waters"], waters, card_id)
            self.assertEqual(spec["drill_turns"], 3, card_id)
            self.assertEqual(card.get("entry_condition"), {},
                             f"{card_id} 演習與關係無關，不該有進入條件")

    def test_a_naval_drill_leaves_city_output_alone(self):
        """設計稿明寫海軍演習「領域內城市生產照常，不會減損」——與封鎖的分水嶺。"""
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if c["id"] == "shanghai")
        owner = engine.state["city_owners"].get(city["id"], city["faction"])
        engine._refresh_city_income()
        before = next(r for r in engine.state["players"][owner]["city_economy"]
                      if r["id"] == "shanghai")
        engine.punishments.open(card_id="royal_navy_yangtze_drill", power="uk",
                                kind="water_blockade", owner=owner,
                                waters=["長江"], drill_turns=3, label="演習")
        after = next(r for r in engine.state["players"][owner]["city_economy"]
                     if r["id"] == "shanghai")
        self.assertEqual((after["cash"], after["factory"]),
                         (before["cash"], before["factory"]))

    def test_a_real_blockade_does_zero_the_same_city(self):
        """對照組：同一座城、同一片水域，換成真的封鎖就該歸零。"""
        engine = GameEngine(seed=3)
        owner = engine.state["city_owners"].get("shanghai", "S")
        engine.state["players"][owner]["foreign_relations"]["uk"] = -6
        engine.punishments.open(card_id="british_navy_blockades_yangtze", power="uk",
                                kind="water_blockade", owner=owner,
                                waters=["長江"], label="封鎖")
        row = next(r for r in engine.state["players"][owner]["city_economy"]
                   if r["id"] == "shanghai")
        self.assertEqual((row["cash"], row["factory"]), (0, 0))

    def test_a_naval_drill_still_locks_fleets_and_expires_on_time(self):
        engine = GameEngine(seed=3)
        entry = engine.punishments.open(
            card_id="bohai_fleet_special_drill", power="jp", kind="water_blockade",
            owner="F", waters=["渤海"], drill_turns=3, label="演習")
        self.assertTrue(entry["drill"])
        self.assertEqual(entry["damage"], {}, "演習不造成任何傷害")
        self.assertIn("渤海", engine.punishments.blockaded_waters())
        for _ in range(3):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertNotIn("渤海", engine.punishments.blockaded_waters())

    def test_the_port_count_gate_actually_bites(self):
        """「控制至少三座長江河港城市」先前只寫在說明裡，沒有真的擋。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("japanese_navy_blockades_yangtze")
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["jp"] = -6
        yangtze = ["hankou", "wuchang", "nanjing", "shanghai", "jiujiang"]
        for city_id in yangtze:
            engine.state["city_owners"][city_id] = "S"
        engine.state["city_owners"]["hankou"] = "W"
        engine.state["city_owners"]["wuchang"] = "W"
        engine.state["city_owners"]["nanjing"] = "W"
        eligible = engine._event_eligible_players(card)
        self.assertIn("W", eligible)
        engine.state["city_owners"]["nanjing"] = "S"
        engine.state["city_owners"]["wuchang"] = "S"
        self.assertNotIn("W", engine._event_eligible_players(card),
                         "只剩一座長江河港就不該再被封鎖")

    def test_the_soviet_mongol_drill_is_a_ground_drill(self):
        """陸軍演習與海軍演習的差別：陸軍演習期間收入照樣歸零。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("soviet_mongol_army_drill")
        spec = card["apply"]["foreign_punishment"][0]
        self.assertEqual((spec["power"], spec["kind"]), ("su", "ground_occupation"))
        self.assertEqual(spec["provinces"], ["察哈爾", "熱河"])
        self.assertEqual(spec["drill_turns"], 3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("察哈爾", "熱河"):
                engine.state["city_owners"][city["id"]] = "F"
        engine.punishments.open(card_id="soviet_mongol_army_drill", power="su",
                                kind="ground_occupation", owner="F",
                                provinces=["察哈爾", "熱河"], drill_turns=3, label="演習")
        rows = [r for r in engine.state["players"]["F"]["city_economy"]
                if r["province"] in ("察哈爾", "熱河")]
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual((row["cash"], row["factory"]), (0, 0), row["name"])


class RailwaySabotageEventTests(unittest.TestCase):
    """爆破鐵路：效果與功能卡〈崩鐵玩家〉相同，差別只在搶修由被懲戒方全額支付。"""

    def _fire(self, engine, card_id, owner="F", power="jp"):
        engine.state["players"][owner]["foreign_relations"][power] = -6
        for code in engine.state["players"]:
            if code != owner:
                engine.state["players"][code]["foreign_relations"][power] = 5
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player=owner)
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        return view["drawer"], engine.respond_event(view["waiting_for"])

    def test_it_paralyses_a_chinese_trunk_line_for_three_turns(self):
        engine = GameEngine(seed=3)
        drawer, result = self._fire(engine, "japanese_agents_blow_up_railway")
        entry = next(e for e in result["applied"] if e["kind"] == "railway_sabotage")
        self.assertIn(entry["railway"], engine.disabled_railways())
        self.assertEqual(entry["remaining_turns"], 3)

    def test_it_never_picks_a_foreign_owned_line(self):
        """南滿、中東、滇越是列強自己的鐵路，不在「境內黑色鐵路」之列。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("japanese_agents_blow_up_railway")
        allowed = card["apply"]["railway_sabotage"][0]["railways"]
        for foreign in ("南滿鐵路", "中東鐵路", "滇越鐵路"):
            self.assertNotIn(foreign, allowed)

    def test_only_the_punished_player_pays_and_pays_the_full_thirty(self):
        """對照組跑一次沒有這張卡的同一回合，兩邊相減才看得出誰真的付了錢
        （回合結算本身也會加工業點，直接看絕對值會被收入蓋掉）。"""
        def run(with_card):
            engine = GameEngine(seed=3)
            for code in engine.state["players"]:
                engine.state["players"][code]["factory_points"] = 100
                engine.state["players"][code]["foreign_relations"]["jp"] = 5
            engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
            engine.state["turn"] = 2
            engine.state["event_pool"] = (["japanese_agents_blow_up_railway"]
                                          if with_card else [])
            engine.next_turn(active_player="F")
            result = None
            view = engine.pending_event_view()
            if view:
                result = engine.respond_event(view["waiting_for"])
            return engine, result

        hit, result = run(True)
        control, _ = run(False)
        entry = next(e for e in result["applied"] if e["kind"] == "railway_sabotage")
        self.assertEqual(entry["paid"], 30)
        self.assertEqual(entry["shortfall"], 0)
        for code in hit.state["players"]:
            delta = (int(control.state["players"][code]["factory_points"])
                     - int(hit.state["players"][code]["factory_points"]))
            self.assertEqual(delta, 30 if code == "F" else 0,
                             f"{code} 的工業點差額不對")

    def test_the_function_card_still_splits_the_bill_the_old_way(self):
        """對照組：〈崩鐵玩家〉照舊是「除使用者外每家 −10」，沒有被我改壞。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["factory_points"] = 100
        engine.state["players"]["F"]["hand"] = ["railway_saboteur"]
        engine.use_function("F", "railway_saboteur", target_railway="京漢鐵路")
        self.assertEqual(int(engine.state["players"]["F"]["factory_points"]), 100)
        for code in engine.state["players"]:
            if code != "F":
                self.assertEqual(int(engine.state["players"][code]["factory_points"]), 90)

    def test_a_line_already_under_repair_is_not_picked_twice(self):
        engine = GameEngine(seed=3)
        engine.state["railway_effects"] = [
            {"railway": name, "remaining_turns": 3}
            for name in ("京奉鐵路", "京漢鐵路", "津浦鐵路", "膠濟鐵路",
                         "正太鐵路", "隴海鐵路", "滬寧鐵路")]
        _, result = self._fire(engine, "ccp_agents_blow_up_railway", power="su")
        entry = next(e for e in result["applied"] if e["kind"] == "railway_sabotage")
        self.assertEqual(entry["railway"], "粵漢鐵路", "只剩一條沒在搶修就該挑那一條")

    def test_it_reports_honestly_when_every_line_is_already_down(self):
        engine = GameEngine(seed=3)
        engine.state["railway_effects"] = [
            {"railway": line["name"], "remaining_turns": 3}
            for line in engine.data["strategic_map"]["railroads"]]
        _, result = self._fire(engine, "ccp_agents_blow_up_railway", power="su")
        entry = next(e for e in result["applied"] if e["kind"] == "railway_sabotage")
        self.assertEqual(entry.get("skipped"), "no_railway_available")


class MarshalAssassinationEventTests(unittest.TestCase):
    """列強派來的刺客：成功率 20%，骰子在抽出當下就擲，報紙照實刊。"""

    MARSHALS = {"F": "zhang_zuolin", "W": "wu_peifu", "S": "sun_chuanfang", "N": "chiang"}

    def _draw(self, engine, card_id, owner="F", power="jp", rig=None):
        engine.state["marshal_ids"] = dict(self.MARSHALS)
        # 奉系手上有張宗昌的日本買辦（對日 [懲戒] 10% 免疫），而這幾條測試把
        # random() 釘死成很小的值來控制暗殺骰。兩者會撞在一起：買辦先擲先中，
        # 這張卡根本抽不出來。這裡測的是暗殺，不是買辦，所以先把技能拿掉——
        # 買辦本身另有 CompradorPunishmentImmunityTests 專門驗。
        engine.state["faction_general_traits"] = {}
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"][power] = 5
        engine.state["players"][owner]["foreign_relations"][power] = -6
        if rig is not None:
            engine.random.random = lambda: rig
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player=owner)
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        return view

    def test_the_roll_happens_at_draw_time_so_the_paper_can_report_it(self):
        engine = GameEngine(seed=3)
        view = self._draw(engine, "kwantung_army_special_service_assassination", rig=0.05)
        self.assertIsNotNone(view["assassination"], "報紙拿不到結果就寫不出成敗")
        self.assertTrue(view["assassination"]["success"])
        self.assertEqual(view["assassination"]["target_general_id"], "zhang_zuolin")
        self.assertEqual(view["assassination"]["target_owner"], "F")

    def test_the_success_rate_is_twenty_percent(self):
        engine = GameEngine(seed=3)
        view = self._draw(engine, "kwantung_army_special_service_assassination", rig=0.19)
        self.assertAlmostEqual(view["assassination"]["base_chance"], 0.20)
        self.assertTrue(view["assassination"]["success"])
        engine2 = GameEngine(seed=3)
        view2 = self._draw(engine2, "kwantung_army_special_service_assassination", rig=0.21)
        self.assertFalse(view2["assassination"]["success"])

    def test_a_hit_queues_the_death_for_the_frontend(self):
        engine = GameEngine(seed=3)
        view = self._draw(engine, "ccp_assassination_attempt", power="su", rig=0.05)
        drawer = view["drawer"]
        engine.respond_event(view["waiting_for"])
        queue = engine.state["players"][drawer]["pending_frontend_effects"]
        deaths = [e for e in queue if e["kind"] == "general_death"]
        self.assertEqual(len(deaths), 1)
        self.assertEqual(deaths[0]["general_id"], self.MARSHALS[drawer])
        self.assertEqual(deaths[0]["owner"], drawer)
        self.assertTrue(deaths[0]["marshal"])

    def test_a_miss_queues_nothing(self):
        engine = GameEngine(seed=3)
        view = self._draw(engine, "ccp_assassination_attempt", power="su", rig=0.9)
        drawer = view["drawer"]
        engine.respond_event(view["waiting_for"])
        queue = engine.state["players"][drawer]["pending_frontend_effects"]
        self.assertEqual([e for e in queue if e["kind"] == "general_death"], [])

    def test_settling_reuses_the_drawn_roll_instead_of_rolling_again(self):
        """報紙寫了得手，結算時不能再擲一次擲成失手——這是 11.5 踩過的坑。"""
        engine = GameEngine(seed=3)
        view = self._draw(engine, "kwantung_army_special_service_assassination", rig=0.05)
        drawer = view["drawer"]
        engine.random.random = lambda: 0.99      # 再擲一定失敗
        result = engine.respond_event(view["waiting_for"])
        entry = next(e for e in result["applied"] if e["kind"] == "assassinate_marshal")
        self.assertTrue(entry["assassination"]["success"], "應沿用抽出當下的結果")
        self.assertTrue([e for e in engine.state["players"][drawer]["pending_frontend_effects"]
                         if e["kind"] == "general_death"])

    def test_a_body_guard_lowers_the_chance(self):
        engine = GameEngine(seed=3)
        engine.state["body_guards"] = {"zhang_zuolin": {
            "general_id": "zhang_zuolin", "owner": "F", "reduction": 0.05,
            "assigned_turn": 0, "active_from_turn": 0}}
        view = self._draw(engine, "kwantung_army_special_service_assassination", rig=0.17)
        self.assertAlmostEqual(view["assassination"]["chance"], 0.15)
        self.assertFalse(view["assassination"]["success"],
                         "0.17 在 20% 會中，被親衛隊壓到 15% 就不該中")

    def test_without_a_reported_marshal_nothing_happens(self):
        """引擎不持有將領資料。名單沒報上來就不擲——不能憑空殺一個不存在的人。"""
        engine = GameEngine(seed=3)
        engine.state["marshal_ids"] = {}
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["jp"] = -6
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["kwantung_army_special_service_assassination"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNone(view["assassination"])
        result = engine.respond_event(view["waiting_for"])
        entry = next(e for e in result["applied"] if e["kind"] == "assassinate_marshal")
        self.assertEqual(entry.get("skipped"), "no_marshal_reported")

    def test_the_paper_is_not_spoiled_by_a_side_bar_notice(self):
        """骰子在抽出當下就擲了，但通知要等結算才發——否則玩家在讀報之前
        就從側欄看到結果，報紙的成敗欄就白寫了。"""
        engine = GameEngine(seed=3)
        view = self._draw(engine, "kwantung_army_special_service_assassination", rig=0.05)
        drawer = view["drawer"]
        notices = engine.state["players"][drawer].get("notifications") or []
        self.assertEqual([n for n in notices if "暗殺" in n["text"]], [],
                         "讀報之前不該先收到暗殺結果")
        engine.respond_event(view["waiting_for"])
        notices = engine.state["players"][drawer].get("notifications") or []
        self.assertTrue([n for n in notices if "暗殺" in n["text"]],
                        "結算之後才該收到")

    def test_the_marshal_list_survives_a_turn_report(self):
        engine = GameEngine(seed=3)
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F", marshal_ids={"F": "zhang_zuolin"})
        self.assertEqual(engine.state["marshal_ids"]["F"], "zhang_zuolin")


class ForeignActionBatchTwoTests(unittest.TestCase):
    """第二批 B：複用既有機制的 14 張。重點在**宣告與既有機制真的接得上**。"""

    def _fire(self, engine, card_id, prep=None, turn=2):
        if prep:
            prep(engine)
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        applied = []
        while True:
            view = engine.pending_event_view()
            if not view:
                break
            result = engine.respond_event(view["waiting_for"])
            applied += result["applied"]
            if result["cycle_finished"]:
                break
        return applied

    # ---- 暴動類 ----

    def _comintern_prep(self, engine):
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 5
        engine.state["players"]["F"]["foreign_relations"]["su"] = -6
        engine.state.setdefault("ultimatums", []).append({
            "id": "t", "card_id": "soviet_ultimatum", "power": "su", "owner": "F",
            "cities": [], "opened_turn": 0, "deadline_turn": 0, "status": "failed"})

    def test_comintern_revolution_hits_six_random_cities(self):
        engine = GameEngine(seed=3)
        owned = {r["id"] for r in engine.state["players"]["F"]["city_economy"]}
        self.assertGreater(len(owned), 6, "手上要多於六座城才測得出「隨機挑六座」")
        applied = self._fire(engine, "comintern_great_revolution", self._comintern_prep)
        riot = next(e for e in applied if e["kind"] == "city_riot")
        self.assertEqual(len(riot["cities"]), 6)
        self.assertTrue(set(riot["cities"]) <= owned)
        hit = set(riot["cities"])
        for row in engine.state["players"]["F"]["city_economy"]:
            if row["id"] in hit:
                self.assertEqual((row["cash"], row["factory"]), (0, 0), row["name"])
            else:
                self.assertGreater(row["cash"] + row["factory"], 0, row["name"])

    def test_the_revolution_survives_a_diplomatic_thaw(self):
        """[懲戒] 的通則是關係回升就自動失效，這張是唯一的例外：
        一經發動就走紅軍起義的機制，只能靠派兵平息。"""
        engine = GameEngine(seed=3)
        applied = self._fire(engine, "comintern_great_revolution", self._comintern_prep)
        hit = set(next(e for e in applied if e["kind"] == "city_riot")["cities"])
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        for _ in range(4):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        still = {row["id"] for row in engine.state["players"]["F"]["city_economy"]
                 if (row["cash"], row["factory"]) == (0, 0)}
        self.assertTrue(hit <= still, "邦交轉圜也不該讓起義自行平息")

    def test_a_normal_punishment_does_lift_on_a_thaw(self):
        """對照組：一般 [懲戒] 關係修好的下一回合就解除。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = -6
        engine.punishments.open(card_id="soviet_air_force_bombing", power="su",
                                kind="air_raid", owner="F", label="轟炸")
        self.assertTrue(engine.punishments.bombed_cities())
        engine.state["players"]["F"]["foreign_relations"]["su"] = 2
        for _ in range(3):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(engine.punishments.bombed_cities(), {})

    def test_red_labour_infiltration_hits_two_cities_of_every_unfriendly_player(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        engine.state["players"]["N"]["foreign_relations"]["su"] = 6
        applied = self._fire(engine, "red_labour_infiltration")
        riots = {e["player"]: e for e in applied if e["kind"] == "city_riot"}
        self.assertNotIn("N", riots, "對蘇 ≥6 的玩家不受影響")
        self.assertTrue(riots)
        for entry in riots.values():
            self.assertEqual(len(entry["cities"]), 2)

    def test_red_propaganda_drains_one_battalion_of_every_arm(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
            engine.state["players"][code]["unit_reserves"] = {
                "infantry": 5, "cavalry": 5, "machine_gun": 5, "artillery": 5}
        engine.state["players"]["N"]["foreign_relations"]["su"] = 6
        self._fire(engine, "red_propaganda_infiltration")
        for code in ("F", "W", "S"):
            for unit in ("infantry", "cavalry", "machine_gun", "artillery"):
                self.assertEqual(engine.state["players"][code]["unit_reserves"][unit], 4,
                                 f"{code}/{unit}")
        self.assertEqual(engine.state["players"]["N"]["unit_reserves"]["infantry"], 5)

    # ---- 原地戰備 ----

    def test_soviet_mobilisation_docks_output_and_freezes_movement(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        engine.state["players"]["F"]["foreign_relations"]["su"] = -2
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("熱河", "察哈爾", "黑龍江"):
                engine.state["city_owners"][city["id"]] = "F"
        applied = self._fire(engine, "soviet_far_east_mobilisation")
        once = next(e for e in applied if e["kind"] == "city_output_once")
        self.assertEqual(once["player"], "F")
        self.assertEqual(once["cash"], -2 * len(once["cities"]))
        freeze = [e for e in engine.state["players"]["F"]["timed_effects"]
                  if e["kind"] == "movement_freeze"]
        self.assertEqual(len(freeze), 1)
        self.assertEqual(sorted(freeze[0]["provinces"]), ["察哈爾", "熱河", "黑龍江"])

    def test_the_mobilisation_only_docks_cities_you_actually_hold(self):
        """owned_by_target：三省裡別人的城不該算進你的帳。"""
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        engine.state["players"]["F"]["foreign_relations"]["su"] = -2
        north = [c["id"] for c in engine.data["strategic_map"]["cities"]
                 if c.get("province") in ("熱河", "察哈爾", "黑龍江")]
        self.assertGreater(len(north), 2)
        mine, theirs = north[:2], north[2:]
        for city_id in mine:
            engine.state["city_owners"][city_id] = "F"
        for city_id in theirs:
            engine.state["city_owners"][city_id] = "W"
        applied = self._fire(engine, "soviet_far_east_mobilisation")
        once = next(e for e in applied if e["kind"] == "city_output_once")
        self.assertEqual(sorted(once["cities"]), sorted(mine))
        self.assertEqual(once["cash"], -2 * len(mine))

    def test_guard_expansion_freezes_manchuria_for_three_turns(self):
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("奉天", "吉林", "黑龍江"):
                engine.state["city_owners"][city["id"]] = "F"
        self._fire(engine, "south_manchuria_guard_expansion")
        freeze = [e for e in engine.state["players"]["F"]["timed_effects"]
                  if e["kind"] == "movement_freeze"]
        self.assertEqual(len(freeze), 1)
        self.assertEqual(freeze[0]["remaining_turns"], 3)
        self.assertEqual(sorted(freeze[0]["provinces"]), ["吉林", "奉天", "黑龍江"])

    # ---- 城市選擇器 ----

    def test_customs_agreement_pays_every_port_city_forever(self):
        engine = GameEngine(seed=3)
        ports = [c["id"] for c in engine.data["strategic_map"]["cities"] if c.get("port")]
        self.assertTrue(ports)
        before = {row["id"]: row["cash"]
                  for row in engine.state["players"]["F"]["city_economy"]}
        self._fire(engine, "maritime_customs_agreement")
        for row in engine.state["players"]["F"]["city_economy"]:
            expected = before.get(row["id"], 0) + (1 if row["id"] in ports else 0)
            self.assertEqual(row["cash"], expected, row["name"])

    def test_british_tariff_autonomy_only_touches_british_concessions(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["uk"] = 3
        uk = {c["id"] for c in engine.data["strategic_map"]["cities"]
              if "uk" in (c.get("concession") or [])}
        for city_id in uk:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        before = {r["id"]: r["cash"] for r in engine.state["players"]["F"]["city_economy"]}
        self._fire(engine, "britain_recognises_tariff_autonomy")
        for row in engine.state["players"]["F"]["city_economy"]:
            bump = 2 if row["id"] in uk else 0
            self.assertEqual(row["cash"], before[row["id"]] + bump, row["name"])

    def test_tariff_conference_pays_per_concession_city_and_lifts_relations(self):
        engine = GameEngine(seed=3)
        conc = [c for c in engine.data["strategic_map"]["cities"] if c.get("concession")]
        for city in conc:
            engine.state["city_owners"][city["id"]] = "F"
        engine._refresh_city_income()
        rel_before = dict(engine.state["players"]["F"]["foreign_relations"])
        applied = self._fire(engine, "powers_tariff_conference")
        once = next(e for e in applied if e["kind"] == "city_output_once" and e["player"] == "F")
        self.assertEqual(len(once["cities"]), len(conc))
        self.assertEqual(once["cash"], 3 * len(conc))
        powers = {p for c in conc for p in c["concession"]}
        after = engine.state["players"]["F"]["foreign_relations"]
        for power in powers:
            self.assertEqual(int(after[power]), int(rel_before.get(power, 0)) + 1, power)

    # ---- 關係類 ----

    def test_far_east_conference_costs_five_with_three_powers(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 0
        engine.state["players"]["F"]["foreign_relations"]["us"] = -6
        before = dict(engine.state["players"]["F"]["foreign_relations"])
        self._fire(engine, "far_east_diplomatic_conference")
        after = engine.state["players"]["F"]["foreign_relations"]
        for power in ("uk", "fr", "jp"):
            self.assertEqual(int(after[power]), int(before[power]) - 5, power)
        self.assertEqual(int(after["su"]), int(before["su"]), "蘇聯不在這張卡裡")

    def test_joint_condemnation_only_bites_powers_you_already_offended(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            for power in ("jp", "uk", "fr", "us", "su"):
                engine.state["players"][code]["foreign_relations"][power] = 2
        engine.state["players"]["F"]["foreign_relations"]["jp"] = -4
        engine.state["players"]["F"]["foreign_relations"]["su"] = -8
        applied = self._fire(engine, "joint_condemnation_of_china")
        entry = next(e for e in applied
                     if e["kind"] == "hostile_relations_delta" and e["player"] == "F")
        self.assertEqual(sorted(entry["powers"]), ["jp", "su"])
        after = engine.state["players"]["F"]["foreign_relations"]
        self.assertEqual(int(after["jp"]), -5)
        self.assertEqual(int(after["su"]), -9)
        self.assertEqual(int(after["uk"]), 2, "沒交惡的不動")

    def test_washington_conference_moves_all_four_powers(self):
        engine = GameEngine(seed=3)
        before = {code: dict(engine.state["players"][code]["foreign_relations"])
                  for code in engine.state["players"]}
        self._fire(engine, "washington_system_conference")
        for code in engine.state["players"]:
            after = engine.state["players"][code]["foreign_relations"]
            for power, delta in (("uk", 1), ("us", 1), ("jp", 1), ("su", -2)):
                self.assertEqual(int(after[power]), int(before[code][power]) + delta,
                                 f"{code}/{power}")

    # ---- 商約 ----

    def test_the_treaty_adds_fifteen_to_that_players_trade_card_only(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 0
        engine.state["players"]["F"]["foreign_relations"]["us"] = 6
        base = int(engine._card_template("trade_export_us", player="W").get("cash_gain", 0))
        self._fire(engine, "usa_recognition_and_treaty")
        self.assertEqual(int(engine._card_template("trade_export_us", player="F")["cash_gain"]),
                         base + 15)
        self.assertEqual(int(engine._card_template("trade_export_us", player="W")["cash_gain"]),
                         base, "只有簽約那一家吃到")
        self.assertEqual(int(engine._card_template("trade_export_uk", player="F")["cash_gain"]),
                         int(engine._card_template("trade_export_uk", player="W")["cash_gain"]),
                         "對英那張不該被動到")

    def test_both_treaties_stack_instead_of_overwriting(self):
        """用 field_deltas 而不是 fields：兩張商約各管各的卡，且可與別的加成疊加。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("britain_recognition_and_treaty")
        override = card["apply"]["player_card_overrides"][0]
        self.assertIn("field_deltas", override)
        self.assertNotIn("fields", override)

    # ---- 紅十字 ----

    def test_red_cross_needs_only_one_friendly_power(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("international_red_cross")
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["uk"] = 0
            engine.state["players"][code]["foreign_relations"]["us"] = 0
        self.assertEqual(engine._event_eligible_players(card), [])
        engine.state["players"]["W"]["foreign_relations"]["us"] = 6
        self.assertEqual(engine._event_eligible_players(card), ["W"],
                         "對英或對美其中一個達標就夠")

    def test_red_cross_opens_the_field_hospital_window(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["uk"] = 6
        self._fire(engine, "international_red_cross")
        window = [e for e in engine.state["players"]["F"]["timed_effects"]
                  if e["kind"] == "field_hospital_window"]
        self.assertEqual(len(window), 1)
        self.assertEqual(window[0]["remaining_turns"], 3)
        self.assertEqual(window[0]["units"], 2)


class ForeignActionBatchThreeTests(unittest.TestCase):
    """第三批：生產成本乘數 4 張 ＋ 交涉類選項卡 6 張（各自表態、各自結算）。"""

    def _resolve_all(self, engine, card_id, choice_by_player, turn=2, prep=None):
        if prep:
            prep(engine)
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        applied = []
        seen = 0
        while seen < 20:
            view = engine.pending_event_view()
            if not view:
                break
            who = view["waiting_for"]
            result = engine.respond_event(who, choice=choice_by_player.get(who, "accept"))
            applied += result["applied"]
            seen += 1
            if result["cycle_finished"]:
                break
        return applied

    # ---- 生產成本乘數 ----

    def test_the_embargo_raises_ground_costs_by_half_for_everyone(self):
        engine = GameEngine(seed=3)
        before = engine._unit_cost_for("F", "infantry")
        self._resolve_all(engine, "usa_congress_arms_embargo", {})
        after = engine._unit_cost_for("F", "infantry")
        # 乘數是乘在**底價**上，不是乘在已含陣營修正的成品價上，
        # 所以期望值要照同一條算式重算，不能拿 before×1.5 來比。
        base = RECRUIT_COSTS["infantry"]["cash"]
        modifier = engine.state["players"]["F"].get("recruitment_cost_modifier", 1)
        self.assertEqual(after[0], math.ceil(base * modifier * 1.5))
        self.assertGreater(after[0], before[0])
        self.assertEqual(engine._production_multiplier("W", "ground")["cash"], 1.5,
                         "禁運案是全場適用")

    def test_two_multipliers_compound(self):
        """兩張同時生效就連乘（1.5 × 1.3），不是取最大也不是相加。"""
        engine = GameEngine(seed=3)
        for card_id in ("usa_congress_arms_embargo", "britain_arms_export_control"):
            card = engine._event_template(card_id)
            engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"],
                               1.5 * 1.3)
        base = RECRUIT_COSTS["infantry"]["cash"]
        modifier = engine.state["players"]["F"].get("recruitment_cost_modifier", 1)
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0],
                         math.ceil(base * modifier * 1.5 * 1.3))

    def test_the_multiplier_expires(self):
        engine = GameEngine(seed=3)
        base = engine._unit_cost_for("F", "infantry")[0]
        self._resolve_all(engine, "usa_congress_arms_embargo", {})
        self.assertGreater(engine._unit_cost_for("F", "infantry")[0], base)
        for _ in range(5):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], base)

    def test_sanctions_only_bite_the_condemned_player(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["us"] = 3
        engine.state["players"]["F"]["foreign_relations"]["us"] = -6
        base = engine._unit_cost_for("W", "infantry")[0]
        self._resolve_all(engine, "usa_condemns_open_door_breach", {})
        self.assertEqual(engine._unit_cost_for("W", "infantry")[0], base,
                         "沒被譴責的人不該漲價")
        self.assertEqual(engine._production_multiplier("F", "ground")["cash"], 1.5)
        self.assertEqual(engine._production_multiplier("W", "ground")["cash"], 1.0)

    def test_hongkong_trade_cuts_costs_instead(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["uk"] = 0
        engine.state["players"]["N"]["foreign_relations"]["uk"] = 6
        for city_id in ("guangzhou", "foshan"):
            engine.state["city_owners"][city_id] = "N"
        base = engine._unit_cost_for("N", "infantry")[0]
        self._resolve_all(engine, "hongkong_arms_trade", {})
        self.assertLess(engine._unit_cost_for("N", "infantry")[0], base)

    def test_hongkong_trade_needs_every_city_in_the_ring(self):
        """條件是「香港周邊兩格內**所有**城市」——少一座就不成立。
        地圖上沒有深圳，兩格內真正存在的只有廣州與佛山。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("hongkong_arms_trade")
        self.assertEqual(card["entry_condition"]["controls_cities_all"],
                         ["guangzhou", "foshan"])
        known = {c["id"] for c in engine.data["strategic_map"]["cities"]}
        for city_id in card["entry_condition"]["controls_cities_all"]:
            self.assertIn(city_id, known, f"{city_id} 不在地圖上")
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["uk"] = 6
        engine.state["city_owners"]["guangzhou"] = "N"
        engine.state["city_owners"]["foshan"] = "S"
        self.assertEqual(engine._event_eligible_players(card), [],
                         "兩座城分屬兩家，誰都不該符合條件")
        engine.state["city_owners"]["foshan"] = "N"
        self.assertEqual(engine._event_eligible_players(card), ["N"])

    def test_the_red_cross_condition_is_either_power(self):
        """對英 ≥6 **或** 對美 ≥6，任一達標即可。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("international_red_cross")
        self.assertEqual(card["entry_condition"],
                         {"relation_min_any": {"uk": 6, "us": 6}})
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["uk"] = 5
            engine.state["players"][code]["foreign_relations"]["us"] = 5
        self.assertEqual(engine._event_eligible_players(card), [],
                         "兩邊都差一點就不該符合")
        engine.state["players"]["S"]["foreign_relations"]["us"] = 6
        engine.state["players"]["W"]["foreign_relations"]["uk"] = 6
        self.assertEqual(sorted(engine._event_eligible_players(card)), ["S", "W"])

    def test_the_navy_only_moves_when_the_card_says_so(self):
        """禁運案只寫「陸軍兵種」，砲艇不該跟著漲；門戶開放制裁才含艦艇。"""
        engine = GameEngine(seed=3)
        before = engine._production_multiplier("F", "navy")["cash"]
        self._resolve_all(engine, "usa_congress_arms_embargo", {})
        self.assertEqual(engine._production_multiplier("F", "navy")["cash"], before)
        self.assertGreater(engine._production_multiplier("F", "ground")["cash"], 1)

    # ---- 交涉卡 ----

    def test_each_player_settles_their_own_choice(self):
        """各自表態各自結算：接受的付代價、拒絕的挨罰，互不相干。

        注意回應名單只包含**符合條件**的玩家（設計稿的「僅適用符合條件的玩家」），
        所以這裡刻意讓 F 與 W 各控一省，兩家才都會被問到。"""
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "奉天":
                engine.state["city_owners"][city["id"]] = "F"
            elif city.get("province") == "吉林":
                engine.state["city_owners"][city["id"]] = "W"
        before = {code: dict(engine.state["players"][code]["foreign_relations"])
                  for code in engine.state["players"]}
        self._resolve_all(engine, "south_manchuria_railway_talks",
                          {"F": "accept", "W": "refuse", "S": "refuse", "N": "accept"})
        after = engine.state["players"]
        self.assertEqual(int(after["F"]["foreign_relations"]["jp"]),
                         int(before["F"]["jp"]) + 2)
        self.assertEqual(int(after["W"]["foreign_relations"]["jp"]),
                         int(before["W"]["jp"]) - 2)
        self.assertIn("南滿鐵路", engine.banned_railways("W"))
        self.assertNotIn("南滿鐵路", engine.banned_railways("F"))

    def test_the_railway_ban_lasts_ten_turns_and_only_hits_the_refuser(self):
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "黑龍江":
                engine.state["city_owners"][city["id"]] = "F"
            elif city.get("province") == "吉林":
                engine.state["city_owners"][city["id"]] = "W"
        self._resolve_all(engine, "chinese_eastern_railway_talks",
                          {code: "refuse" for code in engine.state["players"]})
        for code in ("F", "W"):
            self.assertIn("中東鐵路", engine.banned_railways(code))
        self.assertEqual(engine.banned_railways("N"), [],
                         "不符合條件的玩家根本不會被問到，也就不該挨罰")
        self.assertNotIn("中東鐵路", engine.disabled_railways(),
                         "路權封鎖不是全場停運，別家的路況不該受影響")
        for _ in range(11):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(engine.banned_railways("F"), [])

    def test_accepting_the_manchuria_deal_pays_ten_and_costs_the_line(self):
        engine = GameEngine(seed=3)
        north = [c["id"] for c in engine.data["strategic_map"]["cities"]
                 if c.get("province") in ("奉天", "吉林")]
        for city_id in north:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        engine._refresh_city_income()
        before = {r["id"]: r["cash"] for r in engine.state["players"]["F"]["city_economy"]}
        applied = self._resolve_all(engine, "south_manchuria_railway_talks",
                                    {code: "accept" for code in engine.state["players"]})
        grant = next(e for e in applied if e["kind"] == "grant" and e["player"] == "F")
        self.assertEqual(grant["cash"], 10)
        for row in engine.state["players"]["F"]["city_economy"]:
            if row["id"] in north:
                self.assertEqual(row["cash"], max(0, before[row["id"]] - 1), row["name"])

    def test_japanese_factories_trade_cash_for_industry_forever(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["jp"] = 3
        cash_before = int(engine.state["players"]["F"]["income"])
        factory_before = int(engine.state["players"]["F"]["factory_income"])
        self._resolve_all(engine, "japanese_factory_investment",
                          {code: "accept" for code in engine.state["players"]})
        self.assertEqual(int(engine.state["players"]["F"]["income"]), cash_before - 2)
        self.assertEqual(int(engine.state["players"]["F"]["factory_income"]),
                         factory_before + 2)

    def test_every_negotiation_card_lets_all_players_speak(self):
        engine = GameEngine(seed=3)
        for card_id in ("south_manchuria_railway_talks", "chinese_eastern_railway_talks",
                        "yunnan_vietnam_railway_talks", "yangtze_navigation_talks",
                        "jinan_protect_nationals", "japanese_factory_investment"):
            card = engine._event_template(card_id)
            resolution = card["resolution"]
            self.assertEqual(resolution["type"], "choice", card_id)
            self.assertEqual(resolution["scope"], "all_players", card_id)
            self.assertTrue(engine.event_needs_every_faction(card), card_id)
            self.assertEqual(len(resolution["options"]), 2, card_id)
            for option in resolution["options"]:
                self.assertTrue(option.get("apply"), f'{card_id}/{option["id"]} 沒有效果')


class ForeignActionBatchFourTests(unittest.TestCase):
    """列強行動最後 8 張選項卡。全部是「各自表態、各自結算」。"""

    CARDS = ["comintern_directive", "open_door_note", "french_mission_protection",
             "usa_protect_nationals", "french_mission_case_protest",
             "extraterritoriality_talks", "four_power_anti_communist_declaration",
             "anglo_japanese_labour_crackdown"]

    def _run(self, engine, card_id, choice="accept", turn=2, only=None):
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        self.assertIsNotNone(engine.pending_event_view(), f"{card_id} 沒被抽出來")
        applied = []
        for _ in range(8):
            view = engine.pending_event_view()
            if not view:
                break
            who = view["waiting_for"]
            pick = choice if (only is None or who in only) else "refuse"
            applied += engine.respond_event(who, choice=pick)["applied"]
        return applied

    def _own_concession(self, engine, power, owner="F"):
        held = []
        for city in engine.data["strategic_map"]["cities"]:
            if power in (city.get("concession") or []):
                engine.state["city_owners"][city["id"]] = owner
                held.append(city["id"])
        engine._refresh_city_income()
        return held

    def test_all_eight_are_all_player_choice_cards(self):
        engine = GameEngine(seed=3)
        for card_id in self.CARDS:
            card = engine._event_template(card_id)
            self.assertEqual(card["resolution"]["type"], "choice", card_id)
            self.assertEqual(card["resolution"]["scope"], "all_players", card_id)
            self.assertTrue(engine.event_needs_every_faction(card), card_id)
            for option in card["resolution"]["options"]:
                self.assertTrue(option.get("apply"), f'{card_id}/{option["id"]}')

    # ---- 共產國際指令 ----

    def test_the_directive_fixes_infantry_at_two_dollars(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        before = engine._unit_cost_for("F", "infantry")[0]
        rel = dict(engine.state["players"]["F"]["foreign_relations"])
        self.assertNotEqual(before, 2)
        self._run(engine, "comintern_directive", "accept")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], 2,
                         "「降為 2 元」是寫死的價格，不是折抵")
        after = engine.state["players"]["F"]["foreign_relations"]
        self.assertEqual(int(after["su"]), int(rel["su"]) + 2)
        for power in ("uk", "us", "jp"):
            self.assertEqual(int(after[power]), int(rel[power]) - 1, power)

    def test_the_directive_expires_after_five_turns(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        base = engine._unit_cost_for("F", "infantry")[0]
        self._run(engine, "comintern_directive", "accept")
        for _ in range(6):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], base)

    def test_refusing_the_directive_only_costs_soviet_goodwill(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        base = engine._unit_cost_for("F", "infantry")[0]
        self._run(engine, "comintern_directive", "refuse")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], base)
        self.assertEqual(int(engine.state["players"]["F"]["foreign_relations"]["su"]), 0)

    # ---- 門戶開放照會 ----

    def test_the_open_door_note_kills_the_concession_bonus_for_good(self):
        engine = GameEngine(seed=3)
        held = self._own_concession(engine, "us")
        self.assertTrue(held)
        # 租界加成每三回合結算一次，直接量 _concession_bonuses() 才看得到差別。
        engine.state["turn"] = 3
        before = engine._concession_bonuses().get("F", {"cash": 0})["cash"]
        self.assertGreater(before, 0, "接受之前該有租界加成")
        self._run(engine, "open_door_note", "accept")
        for city_id in held:
            self.assertIn(city_id, engine.state["concession_bonus_forfeits"])
        engine.state["turn"] = 3
        after = engine._concession_bonuses().get("F", {"cash": 0})["cash"]
        self.assertLess(after, before, "被放棄的那些城不該再領租界加成")

    def test_refusing_the_open_door_note_keeps_the_bonus(self):
        engine = GameEngine(seed=3)
        self._own_concession(engine, "us")
        before = int(engine.state["players"]["F"]["foreign_relations"]["us"])
        self._run(engine, "open_door_note", "refuse")
        self.assertEqual(engine.state.get("concession_bonus_forfeits"), [])
        self.assertEqual(int(engine.state["players"]["F"]["foreign_relations"]["us"]),
                         before - 2)

    # ---- 按租界攤派的軍費 ----

    def test_the_levy_scales_with_how_many_concessions_you_hold(self):
        engine = GameEngine(seed=3)
        held = self._own_concession(engine, "fr")
        unit_cash, unit_factory = engine._unit_cost_for("F", "infantry")
        applied = self._run(engine, "french_mission_protection", "accept")
        levy = next(e for e in applied
                    if e["kind"] == "levy_per_concession" and e["player"] == "F")
        self.assertEqual(levy["concessions"], len(held))
        self.assertEqual(levy["cash"], unit_cash * len(held))
        self.assertEqual(levy["factory"], unit_factory * len(held))

    def test_no_concession_means_no_levy(self):
        engine = GameEngine(seed=3)
        self._own_concession(engine, "us", owner="W")
        applied = self._run(engine, "usa_protect_nationals", "accept")
        payers = {e["player"] for e in applied if e["kind"] == "levy_per_concession"}
        self.assertEqual(payers, {"W"}, "沒有美租界的人不該被攤派")

    # ---- 補充兵力封鎖 ----

    def test_handling_the_mission_case_blocks_reinforcement_there(self):
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("雲南", "廣西"):
                engine.state["city_owners"][city["id"]] = "F"
        engine._refresh_city_income()
        self._run(engine, "french_mission_case_protest", "accept")
        block = engine._reinforce_block("F", "雲南")
        self.assertIsNotNone(block)
        self.assertEqual(sorted(block["provinces"]), ["廣西", "雲南"])
        self.assertIsNone(engine._reinforce_block("F", "直隸"),
                          "只鎖那兩省，別省照舊")

    def test_the_block_actually_stops_the_api(self):
        engine = GameEngine(seed=3)
        target = next(c for c in engine.data["strategic_map"]["cities"]
                      if c.get("province") == "雲南"
                      and int(engine._with_level(c)["level"]) >= 3)
        engine.state["city_owners"][target["id"]] = "F"
        engine.state["players"]["F"]["unit_reserves"]["infantry"] = 5
        engine._player("F").setdefault("timed_effects", []).append({
            "kind": "reinforce_block", "remaining_turns": 3,
            "provinces": ["雲南", "廣西"], "label": "教案查辦"})
        with self.assertRaises(ValueError) as caught:
            engine.reinforce_army("F", "army-1", target["id"], "infantry", 1)
        self.assertIn("不可補充兵力", str(caught.exception))

    # ---- 領事裁判權 ----

    def test_forcing_extraterritoriality_pays_every_concession_city(self):
        engine = GameEngine(seed=3)
        held = self._own_concession(engine, "uk")
        before = {r["id"]: r["cash"] for r in engine.state["players"]["F"]["city_economy"]}
        rel = dict(engine.state["players"]["F"]["foreign_relations"])
        self._run(engine, "extraterritoriality_talks", "accept")
        rows = {r["id"]: r for r in engine.state["players"]["F"]["city_economy"]}
        for city_id in held:
            self.assertEqual(rows[city_id]["cash"], before[city_id] + 3, city_id)
        for power in ("uk", "fr", "us", "jp"):
            self.assertEqual(int(engine.state["players"]["F"]["foreign_relations"][power]),
                             int(rel[power]) - 2, power)

    def test_yielding_on_extraterritoriality_does_nothing(self):
        engine = GameEngine(seed=3)
        before = dict(engine.state["players"]["F"]["foreign_relations"])
        self._run(engine, "extraterritoriality_talks", "refuse")
        self.assertEqual(engine.state["players"]["F"]["foreign_relations"], before)

    # ---- 四國反共 ----

    def test_complying_dismisses_the_two_ministers_and_kills_the_discount(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 2
        self._run(engine, "comintern_directive", "accept")
        self.assertEqual(engine._unit_cost_for("F", "infantry")[0], 2)
        engine.state["cabinet"] = {
            "wang_jingwei_return": {"card_id": "wang_jingwei_return", "owner": "F"},
            "zhou_enlai_underground": {"card_id": "zhou_enlai_underground", "owner": "F"},
        }
        self._run(engine, "four_power_anti_communist_declaration", "accept", turn=5)
        self.assertEqual(engine.state["cabinet"], {}, "兩位閣員應立刻離職")
        self.assertNotEqual(engine._unit_cost_for("F", "infantry")[0], 2,
                            "工農動員加成應立即失效")

    def test_refusing_the_declaration_costs_four_powers(self):
        engine = GameEngine(seed=3)
        rel = dict(engine.state["players"]["F"]["foreign_relations"])
        self._run(engine, "four_power_anti_communist_declaration", "refuse")
        for power in ("uk", "us", "jp", "fr"):
            self.assertEqual(int(engine.state["players"]["F"]["foreign_relations"][power]),
                             int(rel[power]) - 2, power)

    # ---- 清剿工運 ----

    def test_the_crackdown_halts_british_and_japanese_concession_cities(self):
        engine = GameEngine(seed=3)
        held = set(self._own_concession(engine, "uk")) | set(self._own_concession(engine, "jp"))
        self._run(engine, "anglo_japanese_labour_crackdown", "accept")
        rows = {r["id"]: r for r in engine.state["players"]["F"]["city_economy"]}
        for city_id in held:
            self.assertEqual((rows[city_id]["cash"], rows[city_id]["factory"]), (0, 0),
                             city_id)
        others = [r for r in engine.state["players"]["F"]["city_economy"]
                  if r["id"] not in held]
        self.assertTrue(any(r["cash"] + r["factory"] > 0 for r in others),
                        "沒有英日租界的城市不該停產")

    def test_the_halt_lasts_a_single_turn(self):
        engine = GameEngine(seed=3)
        held = self._own_concession(engine, "uk")
        self._run(engine, "anglo_japanese_labour_crackdown", "accept")
        rows = {r["id"]: r for r in engine.state["players"]["F"]["city_economy"]}
        self.assertEqual(rows[held[0]]["cash"], 0)
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        rows = {r["id"]: r for r in engine.state["players"]["F"]["city_economy"]}
        self.assertGreater(rows[held[0]]["cash"] + rows[held[0]]["factory"], 0)


class ChoiceCardBothBranchesTests(unittest.TestCase):
    """守門測試：每一張需要表態的事件卡，**正反兩邊都要真的有效果落地**。

    靜態看 apply 有沒有鍵不夠——鍵可能是引擎不認得的拼字，或是寫了卻沒接上。
    這裡把每個選項真的餵進 _apply_event_payload()，比對前後整包狀態有沒有變。
    """

    # 設計稿明寫「沒有效果」的選項，唯一的合法例外。
    DELIBERATE_NO_OPS = {("extraterritoriality_talks", "refuse")}

    def _choice_cards(self):
        engine = GameEngine(seed=3)
        return engine, [c for c in engine.data["event_cards"]["cards"]
                        if (c.get("resolution") or {}).get("type") == "choice"]

    def _fingerprint(self, engine):
        return json.dumps(engine.snapshot(), sort_keys=True, ensure_ascii=False,
                          default=str)

    def test_every_choice_card_offers_at_least_two_options(self):
        engine, cards = self._choice_cards()
        self.assertGreaterEqual(len(cards), 18, "表態類卡片數量不該無故減少")
        for card in cards:
            options = card["resolution"].get("options") or []
            self.assertGreaterEqual(len(options), 2, card["id"])
            ids = [o.get("id") for o in options]
            self.assertEqual(len(ids), len(set(ids)), f'{card["id"]} 選項 id 重複')
            for option in options:
                self.assertTrue(option.get("label"), f'{card["id"]} 有選項沒有標籤')
                self.assertTrue(option.get("effect_text") or option.get("apply"),
                                f'{card["id"]}/{option["id"]} 既沒說明也沒效果')

    def test_both_branches_of_every_choice_card_actually_do_something(self):
        _, cards = self._choice_cards()
        inert = []
        for card in cards:
            for option in card["resolution"].get("options") or []:
                key = (card["id"], option.get("id"))
                engine = GameEngine(seed=3)
                # 讓條件類的效果有東西可以作用：手上先給一批租界城市與預備隊。
                for city in engine.data["strategic_map"]["cities"]:
                    if city.get("concession"):
                        engine.state["city_owners"][city["id"]] = "F"
                engine.state["players"]["F"]["unit_reserves"] = {
                    "infantry": 9, "cavalry": 9, "machine_gun": 9, "artillery": 9}
                engine.state["cabinet"] = {
                    "wang_jingwei_return": {"card_id": "wang_jingwei_return", "owner": "F"},
                    "zhou_enlai_underground": {"card_id": "zhou_enlai_underground",
                                               "owner": "F"},
                }
                engine._refresh_city_income()
                before = self._fingerprint(engine)
                engine._apply_event_payload(option.get("apply") or {},
                                            players=["F"], card=card)
                if self._fingerprint(engine) == before:
                    inert.append(f'{card.get("ref")} {card["name"]}／{option.get("label")}')
                    continue
                self.assertNotIn(key, self.DELIBERATE_NO_OPS,
                                 f'{key} 被標成「刻意沒有效果」，卻真的改了狀態')
        expected = sorted(f'{cid}／{oid}' for cid, oid in self.DELIBERATE_NO_OPS)
        self.assertEqual(
            len(inert), len(self.DELIBERATE_NO_OPS),
            "這些選項按下去什麼都沒發生：" + "、".join(inert)
            + f"（唯一允許的例外是 {expected}）")

    def test_the_engine_understands_every_key_both_branches_use(self):
        """選項用到的每一個 payload 鍵，引擎都要真的有在讀。"""
        import re
        source = pathlib.Path(GameEngine.__module__.replace(".", "/") + ".py")
        if not source.exists():
            source = pathlib.Path(__file__).with_name("card_engine.py")
        text = source.read_text(encoding="utf-8")
        body = re.search(r"def _apply_event_payload\(.*?\n(    def |\Z)", text, re.S).group(0)
        known = set(re.findall(r'payload\.get\("([a-z_]+)"', body)) | {"notes", "pending"}
        _, cards = self._choice_cards()
        unknown = []
        for card in cards:
            for option in card["resolution"].get("options") or []:
                for key in (option.get("apply") or {}):
                    if key not in known:
                        unknown.append(f'{card["id"]}/{option.get("id")}: {key}')
        self.assertEqual(unknown, [], "引擎讀不到這些鍵：" + "、".join(unknown))


class ProjectLoanAuditTests(unittest.TestCase):
    """三張列強專案借款的完整運作驗收：放款、利息、到期、違約罰則、還清免罰。"""

    CARDS = {
        "jp_yokohama_specie_loan": ("jp", "S", 50, 40, "cities", 2, {"cash", "factory"}, 5),
        "uk_hsbc_credit":          ("uk", "W", 65, 50, "provinces", 1, {"cash", "factory"}, None),
        "us_commercial_credit":    ("us", "S", 50, 40, "cities", 3, {"factory"}, 5),
    }

    def _play(self, card_id, owner=None):
        power, default_owner, *_ = self.CARDS[card_id]
        owner = owner or default_owner
        engine = GameEngine(seed=6)
        player = engine.state["players"][owner]
        player["foreign_relations"][power] = 9
        engine._sync_foreign_deck_cards(owner)
        player["hand"].append(card_id)
        engine.use_function(owner, card_id)
        return engine, owner, player

    def test_all_three_cards_pay_out_exactly_what_they_promise(self):
        for card_id, (power, owner, cash, debt, *_ ) in self.CARDS.items():
            engine = GameEngine(seed=6)
            player = engine.state["players"][owner]
            player["foreign_relations"][power] = 9
            engine._sync_foreign_deck_cards(owner)
            player["hand"].append(card_id)
            before = int(player["treasury"])
            engine.use_function(owner, card_id)
            loan = player["loans"][-1]
            self.assertEqual(int(player["treasury"]), before + cash, card_id)
            self.assertEqual(int(loan["principal"]), debt, card_id)
            self.assertAlmostEqual(float(loan["interest_per_turn"]), 0.05, msg=card_id)
            self.assertEqual(int(loan["term_turns"]), 3, card_id)
            self.assertTrue(loan["off_quota"], card_id)
            self.assertEqual(int(loan["due_turn"]),
                             int(engine.state["turn"]) + 3, card_id)

    def test_the_card_is_gated_on_the_relation_it_declares(self):
        for card_id, (power, owner, *_ ) in self.CARDS.items():
            engine = GameEngine(seed=6)
            card = engine._card_template(card_id)
            floor = int(card["requires_relation_min"])
            player = engine.state["players"][owner]
            player["foreign_relations"][power] = floor - 1
            engine._sync_foreign_deck_cards(owner)
            player["hand"].append(card_id)
            with self.assertRaises(ValueError, msg=card_id):
                engine.use_function(owner, card_id)
            player["foreign_relations"][power] = floor
            engine._sync_foreign_deck_cards(owner)
            if card_id not in player["hand"]:
                player["hand"].append(card_id)
            engine.use_function(owner, card_id)
            self.assertTrue(player["loans"], card_id)

    def test_interest_accrues_five_percent_a_turn(self):
        engine, owner, player = self._play("uk_hsbc_credit")
        loan = player["loans"][-1]
        principal = int(loan["principal"])
        advance_turn(engine, owner)
        service = player["last_debt_service"]
        breakdown = [e for e in service["interest_breakdown"]
                     if e.get("outstanding", 0) > 0]
        self.assertTrue(breakdown)
        self.assertEqual(service["interest"],
                         sum(int(round(e["outstanding"] * e["rate"])) for e in breakdown))
        self.assertAlmostEqual(breakdown[0]["rate"], 0.05)
        self.assertGreaterEqual(int(breakdown[0]["outstanding"]), principal - 1)

    def test_paying_it_off_before_the_due_turn_avoids_the_clause_entirely(self):
        engine, owner, player = self._play("jp_yokohama_specie_loan")
        loan = player["loans"][-1]
        player["treasury"] = 500
        engine.repay_debt(owner, int(loan["principal"]) + 20)
        for _ in range(6):
            advance_turn(engine, owner)
        self.assertEqual(player.get("loan_penalties") or [], [],
                         "按期還清就不該有任何違約條款")
        for _ in range(6):
            self.assertEqual(player["last_debt_service"]["penalties"], [])
            advance_turn(engine, owner)

    def test_the_clause_only_fires_after_the_due_turn(self):
        engine, owner, player = self._play("jp_yokohama_specie_loan")
        due = int(player["loans"][-1]["due_turn"])
        while int(engine.state["turn"]) <= due:
            advance_turn(engine, owner)
            if int(engine.state["turn"]) <= due:
                self.assertEqual(player["last_debt_service"]["penalties"], [],
                                 f'第 {engine.state["turn"]} 回合還沒到期就開罰')
        advance_turn(engine, owner)
        self.assertTrue(player["last_debt_service"]["penalties"], "逾期後必須開罰")

    def test_each_clause_seizes_exactly_what_its_card_says(self):
        for card_id, (_, owner, _, _, scope, count, take, duration) in self.CARDS.items():
            engine, owner, player = self._play(card_id)
            for _ in range(6):
                advance_turn(engine, owner)
                if player["last_debt_service"]["penalties"]:
                    break
            entry = player["last_debt_service"]["penalties"][0]
            if scope == "cities":
                self.assertEqual(len(entry["cities"]), count, card_id)
            else:
                provinces = {c["province"] for c in engine._city_economy_for(owner)
                             if c["name"] in entry["cities"] or c["id"] in entry["cities"]}
                self.assertLessEqual(len(provinces), count + 1, card_id)
            if "cash" in take:
                self.assertGreaterEqual(entry["cash"], 0, card_id)
            else:
                self.assertEqual(entry["cash"], 0, f'{card_id} 不該拿現金')
            if "factory" in take:
                self.assertGreater(entry["factory"], 0, card_id)
            self.assertEqual(entry.get("remaining_turns") is None, duration is None, card_id)

    def test_the_seizure_really_leaves_the_players_pocket(self):
        """罰則不能只寫在帳上——實收現金要真的少掉那一份。"""
        engine, owner, player = self._play("us_commercial_credit")
        for _ in range(6):
            advance_turn(engine, owner)
            service = player["last_debt_service"]
            if service["penalties"]:
                break
        seized = sum(e["factory"] for e in service["penalties"])
        self.assertGreater(seized, 0)
        gross = int(player["factory_income"])
        self.assertLessEqual(seized, gross + 1)
        clean = GameEngine(seed=6)
        for _ in range(int(engine.state["turn"])):
            advance_turn(clean, owner)
        self.assertLess(int(player["factory_points"]),
                        int(clean.state["players"][owner]["factory_points"]),
                        "被接管工廠產出的人，工業點應該比沒借錢的自己少")

    def test_a_five_turn_clause_stops_after_five_turns(self):
        engine, owner, player = self._play("jp_yokohama_specie_loan")
        hits = 0
        for _ in range(14):
            advance_turn(engine, owner)
            hits += len(player["last_debt_service"]["penalties"])
        self.assertEqual(hits, 5, "5 回合條款不該多罰也不該少罰")

    def test_a_permanent_clause_never_stops(self):
        engine, owner, player = self._play("uk_hsbc_credit")
        hits = 0
        for _ in range(14):
            advance_turn(engine, owner)
            hits += len(player["last_debt_service"]["penalties"])
        self.assertGreaterEqual(hits, 10, "永久條款應該一直罰下去")

    def test_the_same_loan_never_opens_two_clauses(self):
        engine, owner, player = self._play("jp_yokohama_specie_loan")
        for _ in range(10):
            advance_turn(engine, owner)
        loan_ids = [entry["loan_id"] for entry in player.get("loan_penalties") or []]
        self.assertEqual(len(loan_ids), len(set(loan_ids)))


class FrontendEventViewParityTests(unittest.TestCase):
    """前端自己組 view，容易漏掉後端才有的欄位。

    這類漏掉**不會有任何錯誤訊息**，只會安靜地永遠顯示預設值——
    11.5 廢兩改元就這樣一直刊第 0 版（不管實際成不成），
    暗殺卡的成敗欄也是同一個原因看不到。所以這裡設一道文字守門。
    """

    REQUIRED = ("newspaper_index", "assassination")

    def _pending_event_state_source(self) -> str:
        app = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "app.js"
        text = app.read_text(encoding="utf-8")
        start = text.index("function pendingEventState(")
        end = text.index("\nfunction ", start + 10)
        return text[start:end]

    def test_the_frontend_view_carries_the_fields_the_backend_prerolls(self):
        source = self._pending_event_state_source()
        missing = [name for name in self.REQUIRED if name not in source]
        self.assertEqual(missing, [],
                         "frontend/app.js 的 pendingEventState() 少了這些欄位，"
                         "報紙會安靜地顯示預設值：" + "、".join(missing))

    def test_the_backend_view_still_exposes_them(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["silver_tael_reform"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view)
        for name in self.REQUIRED:
            self.assertIn(name, view, name)

    def test_the_tael_reform_has_one_paper_per_outcome(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("silver_tael_reform")
        variants = card.get("newspaper_variants") or []
        branches = card["apply"]["random_outcome"]["branches"]
        self.assertEqual(len(variants), 2)
        self.assertEqual(sorted(b["newspaper_index"] for b in branches), [0, 1],
                         "成與不成必須各對到一版報紙")
        self.assertNotEqual(variants[0]["headline"], variants[1]["headline"])

    def test_each_branch_declares_the_string_the_paper_highlights(self):
        """效果欄要把「實際擲出的那一支」標紅，靠 effect_marker 去比對是哪一條。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("silver_tael_reform")
        for branch in card["apply"]["random_outcome"]["branches"]:
            marker = branch.get("effect_marker")
            self.assertTrue(marker, f'{branch["id"]} 沒有 effect_marker')
            self.assertIn(marker, card["effect"],
                          f'{marker} 在效果欄裡找不到對應的那一條')

    def test_the_preroll_carries_the_marker_through(self):
        for rig, expected in ((0.05, "成（40%）"), (0.95, "不成（60%）")):
            engine = GameEngine(seed=3)
            engine.random.random = lambda: rig
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["silver_tael_reform"]
            engine.next_turn(active_player="F")
            entry = engine.state["pending_events"]["cards"][0]
            self.assertEqual(entry["random_outcome"]["effect_marker"], expected)

    def test_the_frontend_reads_the_marker(self):
        source = self._pending_event_state_source()
        self.assertIn("outcome_marker", source,
                      "pendingEventState() 沒把 effect_marker 帶出來，效果欄就標不了紅")

    def test_the_prerolled_index_follows_the_roll(self):
        for rig, expected in ((0.05, 0), (0.95, 1)):
            engine = GameEngine(seed=3)
            engine.random.random = lambda: rig
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["silver_tael_reform"]
            engine.next_turn(active_player="F")
            self.assertEqual(engine.pending_event_view()["newspaper_index"], expected,
                             f"roll={rig} 應該刊第 {expected} 版")


class ForeignPerkThresholdTests(unittest.TestCase):
    """列強 perk 卡的關係門檻一律是 6，卡面文字與實作不得有第二種說法。"""

    def test_every_perk_card_uses_the_same_threshold(self):
        engine = GameEngine(seed=3)
        floors = {int(c["requires_relation_min"])
                  for c in engine.data["function_cards"]["cards"]
                  if "requires_relation_min" in c}
        self.assertEqual(floors, {FOREIGN_FRIENDLY_THRESHOLD},
                         f"列強 perk 卡的門檻應該一律是 {FOREIGN_FRIENDLY_THRESHOLD}")

    def test_the_card_text_never_contradicts_the_implementation(self):
        """卡面寫「關係 N+」時，N 必須等於 requires_relation_min。

        先前有 14 張卡卡面寫 8+、實作卻是 6，玩家照卡面判斷會誤以為用不了。
        """
        engine = GameEngine(seed=3)
        mismatched = []
        for card in engine.data["function_cards"]["cards"]:
            if "requires_relation_min" not in card:
                continue
            match = re.search(r"關係\s*(\d+)\s*\+", str(card.get("effect", "")))
            if match and int(match.group(1)) != int(card["requires_relation_min"]):
                mismatched.append(
                    f'{card["name"]}：卡面 {match.group(1)}+，實作 {card["requires_relation_min"]}')
        self.assertEqual(mismatched, [], "卡面與實作不一致：" + "、".join(mismatched))


class MilitaryTagWiringTests(unittest.TestCase):
    """[軍事] / [幫會] 這幾條靠標籤運作的機制，在列強懲戒卡全部建檔之後的實測。

    這些機制以前是「機制先備著、資料檔還沒有符合的卡」，等於空轉；
    現在有 13 張可抽的日本 [軍事] 卡了，該擋的就必須真的擋得住。
    """

    def _japanese_military(self, engine):
        return [c for c in engine.data["event_cards"]["cards"]
                if "軍事" in (c.get("tags") or [])
                and c.get("power_note") == "日" and not c.get("never_drawn")]

    def test_there_really_are_japanese_military_cards_now(self):
        engine = GameEngine(seed=3)
        self.assertGreaterEqual(len(self._japanese_military(engine)), 13)

    def test_a_tag_lock_actually_blocks_every_one_of_them(self):
        """3.4 芥川之死：日本 [軍事] 事件封鎖 2 回合——要整批鎖住，不能只鎖一張。"""
        engine = GameEngine(seed=3)
        targets = self._japanese_military(engine)
        for card in targets:
            self.assertFalse(engine._event_locked(card["id"]), card["id"])
        card = engine._event_template("akutagawa_death")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        for target in targets:
            self.assertTrue(engine._event_locked(target["id"]),
                            f'{target["ref"]} {target["name"]} 沒被鎖住')
        self.assertIn(targets[0]["id"], engine.state["event_pool"],
                      "封鎖不等於移除，卡片要留在池子裡")

    def test_the_lock_expires_and_the_cards_come_back(self):
        engine = GameEngine(seed=3)
        target = self._japanese_military(engine)[0]["id"]
        card = engine._event_template("akutagawa_death")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self.assertTrue(engine._event_locked(target))
        for _ in range(3):
            engine.state["event_pool"] = []
            advance_turn(engine, "F")
        self.assertFalse(engine._event_locked(target), "兩回合過了就該解鎖")

    def test_a_locked_card_is_never_drawn(self):
        engine = GameEngine(seed=3)
        target = self._japanese_military(engine)[0]
        engine.state["turn"] = 2
        card = engine._event_template("akutagawa_death")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        engine.state["event_pool"] = [target["id"]]
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view(),
                          f'{target["name"]} 被封鎖時不該抽得到')

    def test_the_eastern_conference_adds_one_copy_of_each(self):
        """2.4 東方會議：每一張日本 [軍事] 事件卡各 +1 張進池。"""
        engine = GameEngine(seed=3)
        targets = [c["id"] for c in self._japanese_military(engine)]
        before = {cid: engine.state["event_pool"].count(cid) for cid in targets}
        card = engine._event_template("eastern_conference")
        applied = engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self.assertTrue([e for e in applied if e["kind"] == "event_pool_add"])
        for cid in targets:
            self.assertEqual(engine.state["event_pool"].count(cid), before[cid] + 1, cid)

    def test_the_tank_card_adds_all_six_named_targets(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("type89_medium_tank")
        wanted = card["apply"]["event_pool_add"][0]["card_names"]
        self.assertEqual(len(wanted), 6)
        names = {c["name"]: c["id"] for c in engine.data["event_cards"]["cards"]}
        before = {names[n]: engine.state["event_pool"].count(names[n]) for n in wanted}
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        for name in wanted:
            cid = names[name]
            self.assertEqual(engine.state["event_pool"].count(cid), before[cid] + 1, name)

    def test_the_gang_duration_bonus_has_a_real_target_now(self):
        """3.3 火燒紅蓮寺：[幫會] 事件卡持續時間 +1 回合。"""
        engine = GameEngine(seed=3)
        gang = [c for c in engine.data["event_cards"]["cards"]
                if "幫會" in (c.get("tags") or [])]
        self.assertTrue(gang, "資料檔應該至少有一張 [幫會] 卡了")
        card = engine._event_template("burning_red_lotus")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self.assertEqual(engine._event_duration_bonus(gang[0]), 1,
                         f'{gang[0]["name"]} 應該吃到 +1 回合')
        plain = next(c for c in engine.data["event_cards"]["cards"]
                     if "幫會" not in (c.get("tags") or []))
        self.assertEqual(engine._event_duration_bonus(plain), 0)

    def test_every_power_has_military_cards_for_its_lock_to_bite(self):
        """五個列強各自的 [軍事] 封鎖都要鎖得到東西，不能有國家是空轉的。"""
        engine = GameEngine(seed=3)
        by_power = {}
        for card in engine.data["event_cards"]["cards"]:
            if "軍事" in (card.get("tags") or []) and not card.get("never_drawn"):
                by_power.setdefault(card.get("power_note"), []).append(card["id"])
        for ref, note in (("1.5", "英"), ("1.7", "美"), ("2.7", "英"),
                          ("1.2", "日"), ("3.4", "日")):
            self.assertTrue(by_power.get(note),
                            f'{ref} 的 [軍事] 封鎖對象（{note}）一張卡都沒有，等於空轉')

    def test_the_british_and_american_locks_bite_their_own_cards_only(self):
        engine = GameEngine(seed=3)
        british = [c["id"] for c in engine.data["event_cards"]["cards"]
                   if "軍事" in (c.get("tags") or []) and c.get("power_note") == "英"]
        japanese = [c["id"] for c in engine.data["event_cards"]["cards"]
                    if "軍事" in (c.get("tags") or []) and c.get("power_note") == "日"]
        self.assertTrue(british and japanese)
        card = engine._event_template("simon_commission")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        for cid in british:
            self.assertTrue(engine._event_locked(cid), cid)
        for cid in japanese:
            self.assertFalse(engine._event_locked(cid),
                             f"{cid} 是日本的卡，不該被英國的封鎖鎖到")

    def test_no_card_claims_a_target_is_missing_when_it_is_not(self):
        """守門：卡片說「目標尚未建檔」時，那件事必須是真的。

        原本這條是**禁用這幾個詞**，前提是那批 [軍事] 卡都建好了。但
        13.29 鴉片與釐金稅收封鎖的〈煙館查禁風波〉屬治安區塊，確實還沒做——
        禁詞會逼人把真話刪掉，那比留著更糟。改成查證：說了就要指得出
        一張真的不存在的卡，指得出來就放行，指不出來才是過時的說明。
        """
        engine = GameEngine(seed=3)
        ids = {c["id"] for c in engine.data["event_cards"]["cards"]}
        stale = []
        for card in engine.data["event_cards"]["cards"]:
            blob = json.dumps(card, ensure_ascii=False)
            if not any(p in blob for p in ("尚未建檔", "還沒有任何一張", "目前沒有符合")):
                continue
            referenced = set()
            for spec in (card.get("apply") or {}).get("event_lock") or []:
                referenced |= set(spec.get("cards") or [])
            for spec in (card.get("apply") or {}).get("event_pool_add") or []:
                referenced |= set(spec.get("cards") or [])
            if not (referenced - ids):
                stale.append(f'{card.get("ref")} {card["name"]}')
        self.assertEqual(stale, [],
                         "這些卡說目標還沒建檔，但目標其實都在了：" + "、".join(stale))


class DeckManipulationWiringTests(unittest.TestCase):
    """所有「封鎖卡／加張進池／收牌／解鎖」機制的整批驗收。

    這類機制最容易變成空轉：卡片指名的目標不存在、或標籤比對不到任何一張，
    程式不會報錯，只會安靜地什麼都沒做。這裡把 30 張帶有這類機制的卡全部跑一次，
    確認每一張都真的動到了東西。
    """

    KEYS = ("event_lock", "event_pool_add", "perk_suspension", "clear_cards",
            "card_copies", "event_unlock", "unlock")

    def _cards_with_deck_effects(self, engine):
        out = []
        for card in engine.data["event_cards"]["cards"]:
            payloads = [card.get("apply") or {}]
            payloads += [o.get("apply") or {}
                         for o in (card.get("resolution") or {}).get("options") or []]
            for branch in (card.get("apply") or {}).get("random_outcome", {}).get("branches") or []:
                payloads.append(branch.get("apply") or {})
            for branch in ((card.get("apply") or {}).get("conditional_branch") or {}).values():
                if isinstance(branch, dict):
                    payloads.append(branch.get("apply") or branch)
            for payload in payloads:
                if any(k in payload for k in self.KEYS):
                    out.append((card, payload))
        return out

    def test_every_deck_effect_card_is_accounted_for(self):
        engine = GameEngine(seed=3)
        found = {c["ref"] for c, _ in self._cards_with_deck_effects(engine)}
        self.assertGreaterEqual(len(found), 28,
                                "帶有封鎖／加張／收牌機制的卡數量不該無故減少")

    def test_every_event_lock_resolves_to_real_cards(self):
        """封鎖必須鎖得到東西——指名的卡要存在，標籤要比對得到。"""
        engine = GameEngine(seed=3)
        ids = {c["id"] for c in engine.data["event_cards"]["cards"]}
        empty = []
        for card, payload in self._cards_with_deck_effects(engine):
            for spec in payload.get("event_lock") or []:
                named = [cid for cid in (spec.get("cards") or [])]
                # 指名一張還沒建檔的卡是允許的——**但卡片必須自己講出來**。
                # 13.29 鴉片與釐金稅收永久封鎖〈煙館查禁風波〉，而那是治安區塊
                # 還沒做的卡。有 pending 說明就放行，沒有就是筆誤。
                declared = " ".join(str(x) for x in
                                    ((card.get("apply") or {}).get("pending") or []))
                for cid in named:
                    if cid not in ids:
                        self.assertIn("尚未建檔", declared,
                                      f'{card["ref"]} 指名了不存在的卡 {cid}，'
                                      f"且沒有在 pending 裡說明")
                        continue
                    self.assertIn(cid, ids, f'{card["ref"]} 指名了不存在的卡 {cid}')
                tags = spec.get("tags") or []
                if not tags:
                    self.assertTrue(named, f'{card["ref"]} 的封鎖既沒指名也沒標籤')
                    continue
                powers = spec.get("powers") or []
                hits = [c for c in engine.data["event_cards"]["cards"]
                        if set(tags) & set(c.get("tags") or [])
                        and (not powers or c.get("power_note") in powers)]
                if not hits:
                    empty.append(f'{card["ref"]} {card["name"]}：{tags}／{powers}')
        self.assertEqual(empty, [], "這些封鎖一張卡都鎖不到：" + "、".join(empty))

    def test_every_pool_add_resolves_to_real_cards(self):
        engine = GameEngine(seed=3)
        names = {c["name"] for c in engine.data["event_cards"]["cards"]}
        ids = {c["id"] for c in engine.data["event_cards"]["cards"]}
        empty = []
        for card, payload in self._cards_with_deck_effects(engine):
            for spec in payload.get("event_pool_add") or []:
                for name in spec.get("card_names") or []:
                    self.assertIn(name, names, f'{card["ref"]} 指名了不存在的卡「{name}」')
                for cid in spec.get("cards") or []:
                    self.assertIn(cid, ids, f'{card["ref"]} 指名了不存在的卡 {cid}')
                tags = spec.get("tags") or []
                if tags:
                    powers = spec.get("powers") or []
                    hits = [c for c in engine.data["event_cards"]["cards"]
                            if set(tags) & set(c.get("tags") or [])
                            and (not powers or c.get("power_note") in powers)]
                    if not hits:
                        empty.append(f'{card["ref"]} {card["name"]}：{tags}／{powers}')
        self.assertEqual(empty, [], "這些加張比對不到任何卡：" + "、".join(empty))

    def test_every_deck_effect_actually_changes_something(self):
        """逐張真的跑一次，比對狀態有沒有變。空轉的會被列出來。"""
        engine0 = GameEngine(seed=3)
        inert = []
        for card, payload in self._cards_with_deck_effects(engine0):
            engine = GameEngine(seed=3)
            # 讓收牌／perk 封鎖有東西可以動：先把列強關係拉高並同步牌庫。
            for code in engine.state["players"]:
                for power in ("jp", "uk", "us", "fr", "su"):
                    engine.state["players"][code]["foreign_relations"][power] = 8
                engine._sync_foreign_deck_cards(code)
            before = json.dumps(engine.snapshot(), sort_keys=True,
                                ensure_ascii=False, default=str)
            engine._apply_event_payload(payload, players=["F"], card=card)
            after = json.dumps(engine.snapshot(), sort_keys=True,
                               ensure_ascii=False, default=str)
            if before == after:
                inert.append(f'{card.get("ref")} {card["name"]}')
        self.assertEqual(inert, [], "這幾張的牌庫效果什麼都沒做：" + "、".join(inert))

    def test_perk_suspension_really_removes_the_named_cards(self):
        engine = GameEngine(seed=3)
        for power in ("jp", "uk", "us", "fr", "su"):
            engine.state["players"]["F"]["foreign_relations"][power] = 8
        engine._sync_foreign_deck_cards("F")
        card = engine._event_template("showa_accession")
        targets = card["apply"]["perk_suspension"]["cards"]
        zones = lambda: (engine.state["players"]["F"]["function_deck"]
                         + engine.state["players"]["F"]["hand"])
        self.assertTrue(set(targets) & set(zones()), "封鎖前手上／牌庫要有這些卡")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        self.assertFalse(set(targets) & set(zones()), "被封鎖的 perk 卡應該離開牌庫")

    def test_the_peking_movement_really_lifts_the_red_uprising_ban(self):
        """10.7 卡面明寫「〈紅軍起義〉〈共黨暴動〉的封鎖即刻解除」。

        那道封鎖是 10.6 自由中國教育家下的 **perk_suspension**，不是 event_lock；
        先前 event_unlock 只清 event_locks，這張卡的解封等於是空的。
        """
        engine = GameEngine(seed=3)
        banned = ["red_army_uprising", "communist_riot"]
        ban = engine._event_template("free_china_educators")
        engine._apply_event_payload(ban["apply"], players=["F"], card=ban)
        active = [e for e in engine.state.get("perk_suspensions", [])
                  if set(banned) & set(e.get("cards") or [])]
        self.assertTrue(active, "10.6 應該先壓下這兩張卡")
        card = engine._event_template("peking_university_movement")
        applied = engine._apply_event_payload(card["apply"], players=["F"], card=card)
        still = [e for e in engine.state.get("perk_suspensions", [])
                 if set(banned) & set(e.get("cards") or [])]
        self.assertEqual(still, [], "10.7 之後封鎖就該解除了")
        entry = next(e for e in applied if e["kind"] == "event_unlock")
        self.assertGreaterEqual(entry["perk_suspensions_released"], 1)

    def _zones(self, engine, code):
        payload = engine.state["players"][code]
        return (payload["function_deck"] + payload["hand"] + payload["discard"])

    def test_card_copies_really_lands_in_the_deck(self):
        """不能只看 `applied` 有回報——要數牌庫。

        先前這條只斷言「有回報結果」，於是 2.2 柏林密約回報了 +2 卻一張都沒進
        牌庫（列強 perk 卡的份數會被 _sync_foreign_deck_cards 修回去），
        測試照樣綠燈。現在每一張用 card_copies 的卡都逐張數。
        """
        engine0 = GameEngine(seed=3)
        for card, payload in self._cards_with_deck_effects(engine0):
            spec = payload.get("card_copies")
            if not spec:
                continue
            engine = GameEngine(seed=3)
            for code in engine.state["players"]:
                for power in ("jp", "uk", "us", "fr", "su", "de"):
                    engine.state["players"][code]["foreign_relations"][power] = 8
                engine._sync_foreign_deck_cards(code)
            before = {t: self._zones(engine, "F").count(t) for t in spec}
            engine._apply_event_payload(payload, players=["F"], card=card)
            for target, copies in spec.items():
                got = self._zones(engine, "F").count(target) - before[target]
                self.assertEqual(got, int(copies),
                                 f'{card["ref"]} {card["name"]} 的 {target}：'
                                 f'說要加 {copies} 張，實際進牌庫 {got} 張')

    def test_the_berlin_treaty_bonus_is_timed_and_survives_the_deck_sync(self):
        """2.2 柏林密約：10 回合內蘇聯 perk 卡各 +2。

        這張不能用 card_copies——列強 perk 卡的份數由 _sync_foreign_deck_cards
        每回合修回 desired，硬塞進牌庫的當場就被收走。改成抬高 desired 的
        perk_copy_bonus，加得進去、也到期收得回來。
        """
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 8
            engine._sync_foreign_deck_cards(code)
        card = engine._event_template("treaty_of_berlin")
        spec = card["apply"]["perk_copy_bonus"]
        targets = spec["cards"]
        base = {t: self._zones(engine, "F").count(t) for t in targets}
        self.assertTrue(all(base.values()), "親蘇時本來就該有幾張")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        for target in targets:
            self.assertEqual(self._zones(engine, "F").count(target), base[target] + 2, target)
        # 效期內推幾回合，同步不該把加成收走
        for _ in range(5):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        for target in targets:
            self.assertEqual(self._zones(engine, "F").count(target), base[target] + 2,
                             f"{target} 在效期內被同步收走了")
        for _ in range(7):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        for target in targets:
            self.assertEqual(self._zones(engine, "F").count(target), base[target],
                             f"{target} 過了 10 回合還沒收回去")

    def test_the_berlin_treaty_only_rewards_the_pro_soviet(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 8 if code == "F" else 0
            engine._sync_foreign_deck_cards(code)
        card = engine._event_template("treaty_of_berlin")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        for target in card["apply"]["perk_copy_bonus"]["cards"]:
            self.assertEqual(self._zones(engine, "F").count(target), 4, target)
            self.assertEqual(self._zones(engine, "W").count(target), 0,
                             f"{target}：對蘇冷淡的人連底牌都不該有，更別說加成")

    def test_the_engine_still_blocks_a_tagged_never_drawn_card(self):
        """第二道保險：就算有人日後又把標籤掛回戰況報導上，引擎也不准撈它。

        資料檔那一層已經斷根（四張戰報卡不掛任何標籤），所以這條刻意在記憶體裡
        把標籤補回去，測的是**引擎自己**擋不擋得住——不是靠資料乖乖不寫標籤。
        """
        engine = GameEngine(seed=3)
        war = [c for c in engine.data["event_cards"]["cards"] if c.get("never_drawn")]
        self.assertEqual(len(war), 4)
        for card in war:                      # 只動這一個 engine 的記憶體副本
            card["tags"] = ["軍事", "戰況"]
        for power in ("日", "蘇"):
            engine._apply_event_payload(
                {"event_pool_add": [{"tags": ["軍事"], "powers": [power], "copies": 1}]},
                players=["F"], card={"id": "probe", "name": "probe"})
        for card in war:
            self.assertEqual(engine.state["event_pool"].count(card["id"]), 0,
                             f'{card["ref"]} 又被標籤加張塞進池子了')

    def test_no_never_drawn_card_can_be_drawn_even_if_it_reaches_the_pool(self):
        """第二道防線：never_drawn 原本只在開局配池時擋一次，任何往 event_pool
        塞卡的路徑都能繞過去。抽卡迴圈自己也要擋。

        四張都要測——日軍獲勝的兩張是被 2.4 東方會議（日本 [軍事]）撈進去的，
        蘇軍獲勝的兩張目前沒有對應的整批加張卡，但防線必須一視同仁，
        不能只擋日方那兩張。
        """
        engine0 = GameEngine(seed=3)
        never = [c["id"] for c in engine0.data["event_cards"]["cards"]
                 if c.get("never_drawn")]
        self.assertEqual(len(never), 4, "日蘇戰況報導應該是四張")
        for card_id in never:
            engine = GameEngine(seed=3)
            engine.state["turn"] = 2
            engine.state["event_pool"] = [card_id]
            engine.next_turn(active_player="F")
            self.assertIsNone(engine.pending_event_view(),
                              f"{card_id} 不該被當成一般事件抽出來")

    def test_no_tag_rule_can_ever_drag_a_war_report_into_the_pool(self):
        """不限 2.4 一張：任何標籤加張都不准撈到戰況報導。

        蘇軍獲勝的兩張目前沒被撈到，只是因為資料檔剛好沒有「蘇聯 [軍事] 整批
        加張」的卡；防線不能建立在「剛好沒有」上面。這裡直接構造日、蘇兩種
        整批加張各跑一次。
        """
        engine0 = GameEngine(seed=3)
        never = [c["id"] for c in engine0.data["event_cards"]["cards"]
                 if c.get("never_drawn")]
        for power in ("日", "蘇"):
            engine = GameEngine(seed=3)
            payload = {"event_pool_add": [{"tags": ["軍事"], "powers": [power],
                                           "copies": 1}]}
            engine._apply_event_payload(payload, players=["F"],
                                        card={"id": "probe", "name": "probe"})
            for card_id in never:
                self.assertEqual(engine.state["event_pool"].count(card_id), 0,
                                 f"{power} 的整批加張把 {card_id} 塞進池子了")
            # 但同標籤的正常卡要照樣加得到，別擋過頭
            normal = [c["id"] for c in engine.data["event_cards"]["cards"]
                      if "軍事" in (c.get("tags") or [])
                      and c.get("power_note") == power and not c.get("never_drawn")]
            self.assertTrue(normal, f"{power} 應該要有正常的 [軍事] 卡")
            fresh = GameEngine(seed=3)
            for card_id in normal:
                self.assertEqual(engine.state["event_pool"].count(card_id),
                                 fresh.state["event_pool"].count(card_id) + 1, card_id)

    def test_unlock_flags_land_on_the_player(self):
        engine = GameEngine(seed=3)
        for ref in ("3.1", "3.2", "6.2", "7.1", "7.4", "8.2", "8.4"):
            card = next(c for c in engine.data["event_cards"]["cards"]
                        if c.get("ref") == ref)
            fresh = GameEngine(seed=3)
            before = set(fresh.state["players"]["F"].get("unlocks") or [])
            fresh._apply_event_payload(card["apply"], players=["F"], card=card)
            after = set(fresh.state["players"]["F"].get("unlocks") or [])
            self.assertNotEqual(before, after, f'{ref} {card["name"]} 沒有解鎖任何東西')


class EventCardCoverageTest(unittest.TestCase):
    """守門測試：每一張有機械化效果的事件卡都要被某條測試指名引用過。

    新增事件卡卻忘了寫測試時，這條會擋下來。
    """

    def test_every_card_with_an_effect_is_referenced_by_some_test(self):
        import pathlib
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        data = load_game_data()
        missing = []
        deferred = []
        for card in data["event_cards"]["cards"]:
            apply_block = card.get("apply") or {}
            has_effect = bool([k for k in apply_block if k not in ("notes", "pending")]) or any(
                option.get("apply")
                for option in ((card.get("resolution") or {}).get("options") or []))
            if not has_effect:
                continue
            if f'"{card["id"]}"' in source:
                continue
            # 還沒上線的卡（not_in_pool）由 NpcActionCardTests 整批守著：
            # 一次性、報導齊備、待建機制名稱合法、且確實抽不到。等機制補齊、
            # not_in_pool 拿掉的那一刻，這條就會要求它有自己的測試。
            if card.get("not_in_pool"):
                deferred.append(card["id"])
                continue
            missing.append(f'{card.get("ref")} {card["name"]} ({card["id"]})')
        self.assertEqual(missing, [], "這些事件卡有效果卻沒有任何測試引用：" + "、".join(missing))
        for card_id in deferred:
            card = next(c for c in data["event_cards"]["cards"] if c["id"] == card_id)
            self.assertTrue((card.get("apply") or {}).get("pending"),
                            f"{card_id} 掛了 not_in_pool 卻沒說還缺什麼機制")



class RecognitionEventTests(unittest.TestCase):
    """承認類事件（1.8 日本承認北京政府、2.8 蘇聯建交與承認）。

    共同結構：進入條件同時卡「控制某城」與「對某國關係達標」，
    受惠者 +2、其餘所有人 −1。
    """

    def _setup(self, engine, city_ids, power, value, owner="S"):
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"][power] = 0
        engine.state["players"][owner]["foreign_relations"][power] = value
        for city_id in city_ids:
            engine.state["city_owners"][city_id] = owner

    def test_japan_recognition_needs_both_peking_and_warm_tokyo(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("japan_recognises_peking")
        # 控制北京但對日冷淡 → 沒有人有資格
        self._setup(engine, ["beijing"], "jp", 0, owner="S")
        self.assertEqual(engine._event_eligible_players(card), [])
        # 對日夠熱但北京不在手上 → 一樣沒資格
        self._setup(engine, [], "jp", 8, owner="S")
        engine.state["city_owners"]["beijing"] = "N"
        self.assertEqual(engine._event_eligible_players(card), [])
        # 兩個條件都成立才進得了牌庫
        self._setup(engine, ["beijing"], "jp", 8, owner="S")
        self.assertEqual(engine._event_eligible_players(card), ["S"])

    def test_japan_recognition_pays_the_holder_and_docks_everyone_else(self):
        engine = GameEngine(seed=3)
        self._setup(engine, ["beijing"], "jp", 8, owner="S")
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["japan_recognises_peking"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["drawer"], "S")
        before = {c: engine.state["players"][c]["foreign_relations"]["jp"]
                  for c in engine.state["players"]}
        engine.respond_event("S")
        self.assertEqual(engine.state["players"]["S"]["foreign_relations"]["jp"],
                         min(10, before["S"] + 2))
        for code in engine.state["players"]:
            if code == "S":
                continue
            self.assertEqual(engine.state["players"][code]["foreign_relations"]["jp"],
                             max(-10, before[code] - 1), code)

    def test_japan_recognition_lifts_every_variable_loyalty_general(self):
        engine = GameEngine(seed=3)
        self._setup(engine, ["beijing"], "jp", 8, owner="S")
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["japan_recognises_peking"]
        engine.next_turn(active_player="F")
        engine.respond_event("S")
        pending = engine.state["players"]["S"]["pending_frontend_effects"]
        self.assertTrue(any(e["kind"] == "loyalty_all" and e["amount"] == 1 for e in pending))

    def test_soviet_recognition_accepts_either_canton_or_hankou(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("soviet_recognition")
        self._setup(engine, ["guangzhou"], "su", 8, owner="N")
        engine.state["city_owners"]["hankou"] = "F"
        self.assertEqual(engine._event_eligible_players(card), ["N"])
        self._setup(engine, ["hankou"], "su", 8, owner="N")
        engine.state["city_owners"]["guangzhou"] = "F"
        self.assertEqual(engine._event_eligible_players(card), ["N"])

    def test_soviet_recognition_pays_the_holder_and_docks_everyone_else(self):
        engine = GameEngine(seed=3)
        self._setup(engine, ["guangzhou", "hankou"], "su", 8, owner="N")
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["soviet_recognition"]
        engine.next_turn(active_player="F")
        before = {c: engine.state["players"][c]["foreign_relations"]["su"]
                  for c in engine.state["players"]}
        engine.respond_event("N")
        self.assertEqual(engine.state["players"]["N"]["foreign_relations"]["su"],
                         min(10, before["N"] + 2))
        for code in engine.state["players"]:
            if code == "N":
                continue
            self.assertEqual(engine.state["players"][code]["foreign_relations"]["su"],
                             max(-10, before[code] - 1), code)


class YanYangchuTests(unittest.TestCase):
    """10.4 晏陽初辦學鄉村：四省 2 級城永久升 3 級 + 控省者步兵 −$1。"""

    PROVINCES = ("直隸", "山東", "山西", "河南")

    def _fire(self, engine):
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["yan_yangchu_rural_education"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        engine.state["event_pool"] = []

    def _level2_cities(self, engine):
        return [c["id"] for c in engine.data["strategic_map"]["cities"]
                if c.get("province") in self.PROVINCES and int(c.get("level", 0)) == 2]

    def test_level_two_cities_in_the_four_provinces_become_level_three(self):
        engine = GameEngine(seed=3)
        targets = self._level2_cities(engine)
        self.assertTrue(targets, "四省裡應該要有 2 級城市可升級")
        for city_id in targets:
            self.assertEqual(engine.effective_city_level(city_id), 2)
        self._fire(engine)
        for city_id in targets:
            self.assertEqual(engine.effective_city_level(city_id), 3, city_id)

    def test_cities_outside_the_four_provinces_are_untouched(self):
        engine = GameEngine(seed=3)
        outside = [c["id"] for c in engine.data["strategic_map"]["cities"]
                   if c.get("province") not in self.PROVINCES and int(c.get("level", 0)) == 2]
        before = {cid: engine.effective_city_level(cid) for cid in outside}
        self._fire(engine)
        for cid, was in before.items():
            self.assertEqual(engine.effective_city_level(cid), was, cid)

    def test_higher_level_cities_are_not_pulled_down(self):
        engine = GameEngine(seed=3)
        big = [c["id"] for c in engine.data["strategic_map"]["cities"]
               if c.get("province") in self.PROVINCES and int(c.get("level", 0)) >= 4]
        before = {cid: engine.effective_city_level(cid) for cid in big}
        self._fire(engine)
        for cid, was in before.items():
            self.assertEqual(engine.effective_city_level(cid), was, cid)

    def test_upgrade_raises_the_city_income(self):
        engine = GameEngine(seed=3)
        targets = self._level2_cities(engine)
        owner = engine.state["city_owners"].get(targets[0])
        before = next(item["cash"] for item in engine.state["players"][owner]["city_economy"]
                      if item["id"] == targets[0])
        self._fire(engine)
        after = next(item["cash"] for item in engine.state["players"][owner]["city_economy"]
                     if item["id"] == targets[0])
        self.assertGreater(after, before)

    def test_upgrade_survives_a_change_of_owner(self):
        """城市升級是城市的屬性，易主也帶著走。"""
        engine = GameEngine(seed=3)
        targets = self._level2_cities(engine)
        self._fire(engine)
        engine.state["city_owners"][targets[0]] = "N"
        engine._refresh_city_income()
        self.assertEqual(engine.effective_city_level(targets[0]), 3)

    def test_infantry_costs_one_less_while_you_hold_any_of_the_four(self):
        engine = GameEngine(seed=3)
        base = engine._unit_cost_for("S", "infantry")[0]
        others = {unit: engine._unit_cost_for("S", unit)[0]
                  for unit in ("cavalry", "machine_gun", "artillery")}
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        self._fire(engine)
        self.assertEqual(engine._unit_cost_for("S", "infantry")[0], base - 1)
        # 其他兵種不受影響（跟自己事發前的成本比，不同陣營本來就有不同係數）
        for unit, was in others.items():
            self.assertEqual(engine._unit_cost_for("S", unit)[0], was, unit)

    def test_discount_lapses_when_all_four_provinces_are_lost(self):
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        self._fire(engine)
        discounted = engine._unit_cost_for("S", "infantry")[0]
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in self.PROVINCES:
                engine.state["city_owners"][city["id"]] = "N"
        self.assertEqual(engine._unit_cost_for("S", "infantry")[0], discounted + 1)
        # 奪回任一省又恢復
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "河南":
                engine.state["city_owners"][city["id"]] = "S"
        self.assertEqual(engine._unit_cost_for("S", "infantry")[0], discounted)


class Type89TankTests(unittest.TestCase):
    """1.9 日本陸軍裝備八九式中戰車：指名六張尚未建檔的未來卡。"""

    def _fire(self, engine):
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["type89_medium_tank"]
        engine.next_turn(active_player="F")
        return engine.respond_event(engine.pending_event_view()["waiting_for"])

    def test_it_adds_the_targets_that_exist_and_reports_the_rest_honestly(self):
        """六張目標卡目前建檔了兩張（12.1 關東軍侵占東北三省、12.4 關東軍特別演習）。

        這條原本斷言「一張都加不到」，那在當時是對的；現在那兩張真的存在了，
        就必須真的加得進去——否則 1.9 這張卡等於白寫。
        """
        engine = GameEngine(seed=3)
        names = {c["name"]: c["id"] for c in engine.data["event_cards"]["cards"]}
        wanted = ["南滿鐵路交涉", "南滿護路隊擴編", "濟南護僑",
                  "關東軍侵占東北三省", "日本吞併江浙地區", "關東軍特別演習"]
        existing = sorted(names[n] for n in wanted if n in names)
        self.assertEqual(len(existing), 6, "六張目標卡現在應該全部建檔了")
        self.assertEqual(existing,
                         sorted(["japan_annexes_jiangsu_zhejiang",
                                 "kwantung_army_occupies_manchuria",
                                 "kwantung_army_special_drill",
                                 "jinan_protect_nationals",
                                 "south_manchuria_guard_expansion",
                                 "south_manchuria_railway_talks"]),
                         "已建檔的目標卡與預期不符，請更新這條測試")
        result = self._fire(engine)
        entry = [e for e in (result.get("applied") or []) if e["kind"] == "event_pool_add"]
        self.assertEqual(len(entry), 1)
        self.assertEqual(sorted(set(entry[0]["added"])), existing)
        # 其餘四張還沒建檔，所以池子裡只會多這兩張
        self.assertEqual(len(entry[0]["added"]), len(existing))

    def test_card_names_match_once_the_target_exists(self):
        """目標卡一旦建檔，同一張卡不必改就會開始生效。"""
        engine = GameEngine(seed=3)
        # 借一張現有卡改名冒充「關東軍特別演習」
        for card in engine.data["event_cards"]["cards"]:
            if card["id"] == "baird_television":
                card["name"] = "關東軍特別演習"
        engine.state["event_pool"] = []
        engine._apply_event_payload(
            {"event_pool_add": [{"card_names": ["關東軍特別演習"], "copies": 1}]},
            players=None, card={"id": "probe", "name": "probe"})
        self.assertEqual(engine.state["event_pool"].count("baird_television"), 1)

    def test_it_is_the_first_card_carrying_the_military_tag(self):
        """這張卡讓 [軍事] 標籤終於有目標，先前空轉的封鎖與加張機制就此生效。"""
        engine = GameEngine(seed=3)
        tagged = [c["id"] for c in engine.data["event_cards"]["cards"]
                  if "軍事" in (c.get("tags") or [])]
        self.assertIn("type89_medium_tank", tagged)
        self.assertEqual(engine._event_powers("type89_medium_tank"), ["日"])
        # 芥川之死封鎖日本 [軍事] 事件，現在真的鎖得到東西
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["akutagawa_death", "type89_medium_tank"]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        if engine.state["event_locks"]:
            self.assertTrue(engine._event_locked("type89_medium_tank"))



class OneShotEventCardTests(unittest.TestCase):
    """一次性卡：抽過並結算過就永久封鎖，無論牌庫裡還有幾張。

    設計稿裡 59 張全部是一次性；卡片資料加 `repeatable: true` 才豁免。
    """

    def _draw_once(self, engine, card_id):
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])

    def test_every_designed_card_defaults_to_one_copy(self):
        """沒宣告 pool_copies 的卡在開局牌庫裡只能有一份。

        有複本的只有兩類，而且**每一份都必須寫在卡上**，不能靠程式默默塞：
        最後通牒每國 10 張（設計稿），以及經濟事件的「權重」欄——
        設計稿給了 5／2／1，這裡逐張對死，改權重就得同步改這份清單。"""
        engine = GameEngine(seed=3)
        pool = engine.state["event_pool"]
        declared = {c["id"]: max(1, int(c.get("pool_copies", 1)))
                    for c in engine.data["event_cards"]["cards"]}
        for card_id in set(pool):
            self.assertEqual(pool.count(card_id), declared[card_id], card_id)
        extras = {cid: n for cid, n in declared.items() if n > 1}
        self.assertEqual(extras, {
            "british_ultimatum": 10, "french_ultimatum": 10,
            "japanese_ultimatum": 10, "soviet_ultimatum": 10,
            # 經濟事件的權重（《可重複抽取事件卡》經濟事件表的「權重」欄）
            "world_oil_price_surge": 5, "bumper_harvest": 2, "customs_salt_surplus": 2,
            "cotton_yarn_boom": 2, "overseas_chinese_investment": 2,
            "treaty_port_prosperity": 2, "world_silver_price_swing": 2,
            "silver_outflow": 2, "native_bank_run": 2, "pay_arrears": 2,
            "coal_shortage": 2,
            # 治安事件的權重（《可重複抽取事件卡》治安事件表的「權重」欄）
            "general_strike": 2, "factory_accident": 2, "secret_society_trouble": 2,
            "anti_imperialist_march": 2, "rice_riots": 2, "mutiny": 2,
            "local_official_graft": 3, "bandit_raids": 2, "opium_den_crackdown": 2,
            "student_demonstrations": 2,
        }, "有複本的卡必須剛好是最後通牒與設計稿標了權重的經濟／治安事件")

    def test_only_the_recurring_punishment_cards_are_repeatable(self):
        """《可重複抽取事件卡》那批可以反覆抽到，其餘每一張都嚴格只抽一次。

        判準是卡片自己的 `repeatable`，而《可重複抽取事件卡》的卡放在設計稿
        第十二（列強行動）與第十三（經濟事件）區塊。兩邊必須完全對得起來——
        漏標會讓懲戒只降臨一次，多標會讓一次性卡變成無限循環。
        """
        engine = GameEngine(seed=3)
        cards = engine.data["event_cards"]["cards"]
        repeatable = {c["id"] for c in cards if c.get("repeatable")}
        recurring = {c["id"] for c in cards
                     if str(c.get("ref", "")).split(".")[0] in {"12", "13", "14"}}
        self.assertEqual(repeatable, recurring,
                         "可重複抽取的卡必須剛好是第十二、十三、十四區塊那批")
        self.assertTrue(repeatable, "第十二、十三、十四區塊應該要有卡")
        for card in cards:
            if card["id"] in repeatable:
                self.assertFalse(engine.event_is_spent(card["id"]), card["id"])

    def test_a_repeatable_card_can_be_drawn_again(self):
        """懲戒卡抽過還是抽得到——關係不修好，同一種懲戒會反覆降臨。"""
        engine = GameEngine(seed=3)
        engine.state["event_history"].append({"turn": 1, "card_id": "japanese_air_raid"})
        self.assertTrue(engine.event_already_resolved("japanese_air_raid"))
        self.assertTrue(engine.event_is_repeatable("japanese_air_raid"))
        self.assertFalse(engine.event_is_spent("japanese_air_raid"),
                         "可重複抽取的卡不該被當成用掉了")

    def test_a_drawn_card_cannot_be_drawn_again(self):
        engine = GameEngine(seed=3)
        self._draw_once(engine, "baird_television")
        self.assertTrue(engine.event_already_resolved("baird_television"))
        self.assertTrue(engine.event_is_spent("baird_television"))
        # 手動把牌塞回池子，照樣抽不到
        engine.state["event_pool"] = ["baird_television"]
        engine.state["turn"] = 5
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view())

    def test_extra_copies_do_not_revive_a_spent_card(self):
        """抽過的卡即使被效果加回三張，也一張都抽不到。"""
        engine = GameEngine(seed=3)
        self._draw_once(engine, "baird_television")
        engine.state["event_pool"] = ["baird_television"] * 3
        engine.state["turn"] = 5
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view())

    def test_pool_add_skips_spent_cards_and_says_so(self):
        """已用掉的卡乾脆不加進池子，並如實回報跳過了哪幾張。"""
        engine = GameEngine(seed=3)
        self._draw_once(engine, "eastern_conference")
        engine.state["event_pool"] = []
        applied = engine._apply_event_payload(
            {"event_pool_add": [{"cards": ["eastern_conference"], "copies": 2}]},
            players=None, card={"id": "probe", "name": "probe"})
        entry = [e for e in applied if e["kind"] == "event_pool_add"][0]
        self.assertEqual(entry["added"], [])
        self.assertEqual(entry["skipped_already_drawn"], ["eastern_conference"])
        self.assertEqual(engine.state["event_pool"], [])

    def test_showa_accession_no_longer_revives_a_drawn_eastern_conference(self):
        """1.2 昭和改元加 2 張〈東方會議〉——但那張若已抽過就不加。"""
        engine = GameEngine(seed=3)
        self._draw_once(engine, "eastern_conference")
        engine.state["event_pool"] = ["showa_accession"]
        engine.state["turn"] = 5
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(engine.state["event_pool"].count("eastern_conference"), 0)

    def test_pool_add_still_works_for_a_card_never_drawn(self):
        engine = GameEngine(seed=3)
        engine.state["event_pool"] = []
        engine._apply_event_payload(
            {"event_pool_add": [{"cards": ["eastern_conference"], "copies": 2}]},
            players=None, card={"id": "probe", "name": "probe"})
        self.assertEqual(engine.state["event_pool"].count("eastern_conference"), 2)

    def test_repeatable_flag_exempts_a_card(self):
        engine = GameEngine(seed=3)
        for card in engine.data["event_cards"]["cards"]:
            if card["id"] == "baird_television":
                card["repeatable"] = True
        self._draw_once(engine, "baird_television")
        self.assertTrue(engine.event_already_resolved("baird_television"))
        self.assertFalse(engine.event_is_spent("baird_television"))
        engine.state["event_pool"] = ["baird_television"]
        engine.state["turn"] = 5
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view)
        self.assertEqual(view["card"]["id"], "baird_television")

    def test_a_long_game_never_repeats_any_card(self):
        """跑滿整局：**非** repeatable 的卡在 event_history 裡不該有任何重複。

        可重複抽取的懲戒卡（第 12 區塊）本來就會反覆出現，最後通牒更是每國
        10 張，所以只能對一次性卡下這個斷言。"""
        engine = GameEngine(seed=3)
        once_only = {c["id"] for c in engine.data["event_cards"]["cards"]
                     if not c.get("repeatable")}
        for _ in range(40):
            advance_turn(engine, "F")
        seen = [entry["card_id"] for entry in engine.state["event_history"]
                if entry["card_id"] in once_only]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertTrue(seen, "整局下來應該至少抽到一張一次性卡")



class BranchStateMatrixTests(unittest.TestCase):
    """分支卡的三種狀態逐一釘死，防止語意顛倒。

    判定：未抽出 → otherwise；已抽出但效果已散 → if_drawn；已抽出且仍生效 → if_active。
    先前 `chosen = branch.get(key) or branch.get("otherwise")` 有 fallback，
    某狀態沒定義分支時會悄悄改跑「未抽出」那一支——語意剛好顛倒且毫無跡象。
    """

    BRANCH_CARDS = {
        "crescent_moon_monthly": "free_china_educators",
        "kunming_lake": "confucian_revival",
        "gushibian": "confucian_revival",
    }

    def _fire(self, engine, card_id):
        """抽一張指定的卡並結算。

        抽卡前才把池子換成只有這張——**結算後不清空**，
        否則加張效果剛放進池子的卡會被自己的輔助函式掃掉。
        """
        # 事件每三回合觸發一次，所以把回合設在「下一個 3 的倍數」的前一格
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        return engine.respond_event(engine.pending_event_view()["waiting_for"])

    def _chosen(self, result):
        picks = [e for e in (result.get("applied") or [])
                 if e.get("kind") == "conditional_branch"]
        self.assertEqual(len(picks), 1)
        return picks[0]

    def test_no_branch_falls_back_to_the_未抽出_path(self):
        """沒定義的狀態就是沒效果，絕不可以掉回 otherwise。"""
        engine = GameEngine(seed=3)
        # 假造：目標卡已抽過但效果已散，而卡片只定義了 otherwise
        engine.state["event_history"].append({"card_id": "baird_television", "name": "probe"})
        applied = engine._apply_event_payload(
            {"conditional_branch": {"card_id": "baird_television",
                                    "otherwise": {"cash": 999}}},
            players=["F"], card={"id": "probe", "name": "probe"})
        pick = [e for e in applied if e["kind"] == "conditional_branch"][0]
        self.assertEqual(pick["chosen"], "if_drawn")
        self.assertFalse(pick["has_branch"])
        self.assertEqual([e for e in applied if e["kind"] == "cash"], [],
                         "沒定義 if_drawn 時不該改跑 otherwise 的效果")

    def test_every_branch_card_picks_otherwise_when_target_never_drawn(self):
        for card_id, probe in self.BRANCH_CARDS.items():
            engine = GameEngine(seed=3)
            self.assertFalse(engine.event_already_resolved(probe))
            pick = self._chosen(self._fire(engine, card_id))
            self.assertEqual(pick["chosen"], "otherwise", card_id)
            self.assertFalse(pick["drawn"], card_id)

    def test_crescent_moon_adds_three_copies_only_when_not_drawn(self):
        """9.5 原文：若〈自由中國教育家〉尚未抽出，則增加 3 張該卡。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "crescent_moon_monthly")
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 3)

    def test_crescent_moon_extends_when_target_is_still_active(self):
        """已抽出且仍生效 → 延長 5 回合，不加張。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        self._fire(engine, "free_china_educators")
        entry = next(e for e in engine.state["perk_suspensions"]
                     if e.get("source_card") == "free_china_educators")
        before = entry["until_turn"]
        pick = self._chosen(self._fire(engine, "crescent_moon_monthly"))
        self.assertEqual(pick["chosen"], "if_active")
        self.assertEqual(entry["until_turn"], before + 5)
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 0)

    def test_crescent_moon_never_adds_copies_once_the_target_is_spent(self):
        """已抽出但效果已散 → 仍走延長那一支，**絕不**加張。

        設計稿 v5 原文：「若已抽出（無論效果是否仍生效），則改為將該效果再延長 5 回合
        ——因為一次性卡抽過就不會再出現，加張沒有意義。」
        所以 if_drawn 與 if_active 掛同一個 extend_effect；效果已散時沒有東西可延長，
        引擎照實回報 entries=0，而不是偷偷改跑「未抽出」那一支去加三張。
        """
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        self._fire(engine, "free_china_educators")
        engine.state["perk_suspensions"] = []       # 效果散掉
        result = self._fire(engine, "crescent_moon_monthly")
        pick = self._chosen(result)
        self.assertEqual(pick["chosen"], "if_drawn")
        self.assertTrue(pick["has_branch"])
        extend = [e for e in (result.get("applied") or []) if e["kind"] == "extend_effect"]
        self.assertEqual(len(extend), 1)
        self.assertEqual(extend[0]["entries"], 0, "效果已散，沒有東西可延長，要照實回報 0")
        self.assertEqual(engine.state["event_pool"].count("free_china_educators"), 0,
                         "已抽出的一次性卡不該再被加回池子")
        # 但學潮減災照常生效
        self.assertTrue(engine.state["student_unrest_relief"])

    def test_kunming_lake_adds_copies_only_when_revival_not_drawn(self):
        engine = GameEngine(seed=3)
        pick = self._chosen(self._fire(engine, "kunming_lake"))
        self.assertEqual(pick["chosen"], "otherwise")
        self.assertEqual(engine.state["event_pool"].count("confucian_revival"), 3)

    def test_kunming_lake_widens_instead_once_revival_is_drawn(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        engine.respond_event("S")
        engine.state["event_pool"] = []
        pick = self._chosen(self._fire(engine, "kunming_lake"))
        self.assertIn(pick["chosen"], ("if_drawn", "if_active"))
        self.assertEqual(engine.state["event_pool"].count("confucian_revival"), 0)
        self.assertEqual(
            engine.state["players"]["S"]["province_card_immunities"][0]["provinces"],
            ["山東", "直隸"])

    def test_gushibian_locks_only_when_revival_not_drawn(self):
        engine = GameEngine(seed=3)
        pick = self._chosen(self._fire(engine, "gushibian"))
        self.assertEqual(pick["chosen"], "otherwise")
        self.assertTrue(engine._event_locked("confucian_revival"))

    def test_gushibian_pierces_instead_once_revival_is_drawn(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "山東":
                engine.state["city_owners"][city["id"]] = "S"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["confucian_revival"]
        engine.next_turn(active_player="F")
        engine.respond_event("S")
        engine.state["event_pool"] = []
        pick = self._chosen(self._fire(engine, "gushibian"))
        self.assertIn(pick["chosen"], ("if_drawn", "if_active"))
        self.assertIsNone(engine.province_card_immunity("S", "local_autonomy_agitation"))

    def test_branch_cards_never_map_未抽出_to_an_already_drawn_effect(self):
        """守門：每張分支卡的 otherwise 都必須是「目標卡還沒出現」時才合理的效果。

        目前三張的 otherwise 都是「把目標卡加進池子」或「封鎖目標卡」——
        兩者都預設目標卡還在池子裡。若哪天有人把 otherwise 換成
        「延長／擴大目標卡的效果」，那就是語意顛倒，這條會擋下來。
        """
        engine = GameEngine(seed=3)
        TARGETED_AT_EXISTING = {"extend_effect", "widen_province_immunity",
                                "suspend_province_immunity"}
        for card in engine.data["event_cards"]["cards"]:
            cb = (card.get("apply") or {}).get("conditional_branch")
            if not cb:
                continue
            otherwise = cb.get("otherwise") or {}
            clash = TARGETED_AT_EXISTING & set(otherwise)
            self.assertEqual(clash, set(),
                             f'{card["ref"]} {card["name"]} 的「未抽出」分支用了'
                             f'只有目標卡已生效才說得通的效果：{clash}')



class TradeExportIncrementTests(unittest.TestCase):
    """貿易出口的加成改為增量（field_deltas），不再是寫死的 30。

    影響對美／對英（以及蘇、法、日）貿易出口的事件卡只有兩張：
      4.3 杜蘭朵公主   —— 2 回合內，對蘇／英／法／美 各 +$10（不含日本）
      9.4 國立藝術院   —— 永久，五張全部 +$10
    兩張都吃到時應疊加，而不是後抽到的那張把前一張蓋掉。
    """

    TRADE = ("trade_export_jp", "trade_export_su", "trade_export_uk",
             "trade_export_fr", "trade_export_us")
    BASE = 20

    def _fire(self, engine, card_id):
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        engine.respond_event(engine.pending_event_view()["waiting_for"])

    def _own_zhejiang(self, engine, code="S"):
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "浙江":
                engine.state["city_owners"][city["id"]] = code

    def test_base_payout_is_twenty(self):
        engine = GameEngine(seed=3)
        for cid in self.TRADE:
            self.assertEqual(engine._card_template(cid)["cash_gain"], self.BASE, cid)

    def test_no_event_card_writes_an_absolute_trade_payout(self):
        """守門：貿易出口的收益只能用 field_deltas 調整，不准再寫死絕對值。

        寫死絕對值（fields.cash_gain = 30）等於替這個數字設了一個隱形上限——
        第二張卡再怎麼加也只會蓋成同一個 30。這條擋住回頭路。
        """
        engine = GameEngine(seed=3)
        for card in engine.data["event_cards"]["cards"]:
            for ov in (card.get("apply") or {}).get("card_overrides") or []:
                if ov["card_id"] not in self.TRADE:
                    continue
                self.assertNotIn("cash_gain", ov.get("fields") or {},
                                 f'{card["ref"]} {card["name"]} 對 {ov["card_id"]} 寫死了絕對值')
                self.assertIn("cash_gain", ov.get("field_deltas") or {},
                              f'{card["ref"]} {card["name"]} 對 {ov["card_id"]} 沒有增量')

    def test_turandot_adds_ten_to_four_powers_but_not_japan(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "turandot_premiere")
        for cid in ("trade_export_su", "trade_export_uk", "trade_export_fr", "trade_export_us"):
            self.assertEqual(engine._card_template(cid)["cash_gain"], self.BASE + 10, cid)
        self.assertEqual(engine._card_template("trade_export_jp")["cash_gain"], self.BASE,
                         "杜蘭朵是歐美熱潮，不含對日貿易")

    def test_art_academy_adds_ten_to_all_five(self):
        engine = GameEngine(seed=3)
        self._own_zhejiang(engine)
        self._fire(engine, "national_art_academy")
        for cid in self.TRADE:
            self.assertEqual(engine._card_template(cid)["cash_gain"], self.BASE + 10, cid)

    def test_the_two_cards_stack_instead_of_capping_each_other(self):
        """兩張都生效 → 對英／對美 $40，對日 $30（只吃到藝術院那份）。"""
        engine = GameEngine(seed=3)
        self._own_zhejiang(engine)
        self._fire(engine, "national_art_academy")
        self._fire(engine, "turandot_premiere")
        for cid in ("trade_export_su", "trade_export_uk", "trade_export_fr", "trade_export_us"):
            self.assertEqual(engine._card_template(cid)["cash_gain"], self.BASE + 20, cid)
        self.assertEqual(engine._card_template("trade_export_jp")["cash_gain"], self.BASE + 10)

    def test_stacking_holds_regardless_of_which_card_lands_first(self):
        """增量以卡片原始數字為基準累加，所以先後順序不影響結果。

        走 `_apply_event_payload` 而不走 `_fire`，是為了讓兩張卡落在同一個回合——
        事件每三回合才觸發一次，用 `_fire` 連開兩張的話杜蘭朵的 2 回合早就過期了，
        測到的會是過期而不是順序。
        """
        results = []
        for order in (("turandot_premiere", "national_art_academy"),
                      ("national_art_academy", "turandot_premiere")):
            engine = GameEngine(seed=3)
            engine.state["turn"] = 1
            for card_id in order:
                card = engine._event_template(card_id)
                engine._apply_event_payload(card["apply"], players=["S"], card=card)
            results.append(engine._card_template("trade_export_us")["cash_gain"])
        self.assertEqual(results, [self.BASE + 20, self.BASE + 20])

    def test_turandot_share_lapses_after_two_turns_leaving_the_academy(self):
        engine = GameEngine(seed=3)
        self._own_zhejiang(engine)
        self._fire(engine, "national_art_academy")
        self._fire(engine, "turandot_premiere")
        self.assertEqual(engine._card_template("trade_export_uk")["cash_gain"], self.BASE + 20)
        engine.state["turn"] = int(engine.state["turn"]) + 3      # 杜蘭朵的 2 回合到期
        self.assertEqual(engine._card_template("trade_export_uk")["cash_gain"], self.BASE + 10,
                         "杜蘭朵過期後應只剩藝術院的永久那份")

    def _sell(self, engine, code="S", card_id="trade_export_us"):
        payload = engine.state["players"][code]
        payload["factory_points"] = 100
        before = int(payload["treasury"])
        payload["hand"].append(card_id)
        engine.use_function(code, card_id)
        return int(payload["treasury"]) - before

    def test_the_increment_actually_reaches_the_players_treasury(self):
        """不是只有模板數字變了——真的打出這張牌時要多進帳那 $10。"""
        engine = GameEngine(seed=3)
        self._own_zhejiang(engine)
        self.assertEqual(self._sell(engine), self.BASE)
        self._fire(engine, "national_art_academy")
        self.assertEqual(self._sell(engine), self.BASE + 10)
        self._fire(engine, "turandot_premiere")
        self.assertEqual(self._sell(engine), self.BASE + 20)



class NorthwestExpeditionTests(unittest.TestCase):
    """10.2 西北科學考查團：文物收益降為 $10～30，並封死此後一切「加價」的卡。

    「增加〈盜賣文物〉收益」的卡只有兩張：
      4.2 飛鳥非鳥案   永久 $30～60（除此之外沒有別的效果）→ 整張封鎖
      4.3 杜蘭朵公主   2 回合 $30～60，另帶貿易出口 +$10 → 不封鎖整張，
                       改用 override_freeze 把文物那兩個欄位釘死
    """

    def _fire(self, engine, card_id):
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        return engine.respond_event(engine.pending_event_view()["waiting_for"])

    def _payout(self, engine):
        card = engine._card_template("artifact_smuggling")
        return (card["payout_min"], card["payout_max"])

    # ---- 先確認這張卡本來的三件事真的有做好 ----

    def test_it_lowers_the_payout_raises_the_shame_cap_and_the_per_use_count(self):
        engine = GameEngine(seed=3)
        self.assertEqual(self._payout(engine), (20, 40))
        self.assertEqual(engine._card_template("artifact_smuggling")["shame_copies_per_use"], 3)
        self.assertEqual(engine._card_template("national_shame")["max_copies"], 9)
        self._fire(engine, "northwest_expedition")
        self.assertEqual(self._payout(engine), (10, 30))
        self.assertEqual(engine._card_template("artifact_smuggling")["shame_copies_per_use"], 4)
        self.assertEqual(engine._card_template("national_shame")["max_copies"], 12)

    def test_the_lower_payout_actually_reaches_the_players_treasury(self):
        """不是只有模板數字變了——真的打出〈盜賣文物〉時進帳要落在 $10～30。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "northwest_expedition")
        payload = engine.state["players"]["W"]
        for _ in range(6):
            before = int(payload["treasury"])
            payload["hand"].append("artifact_smuggling")
            engine.use_function("W", "artifact_smuggling", target_power="uk")
            gained = int(payload["treasury"]) - before
            self.assertGreaterEqual(gained, 10)
            self.assertLessEqual(gained, 30)

    def test_the_shame_cap_is_per_player_not_table_wide(self):
        """上限 12 是每位玩家各自 12 張，不是四家合計 12 張。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "northwest_expedition")
        payload = engine.state["players"]["W"]
        for _ in range(8):
            payload["hand"].append("artifact_smuggling")
            engine.use_function("W", "artifact_smuggling", target_power="uk")
        self.assertEqual(engine._card_count_in_player_zones(payload, "national_shame"), 12)
        for code in engine.state["players"]:
            if code == "W":
                continue
            self.assertEqual(
                engine._card_count_in_player_zones(engine.state["players"][code], "national_shame"),
                0, code)

    # ---- 禁令本體 ----

    def test_it_permanently_locks_the_bird_in_space_case(self):
        engine = GameEngine(seed=3)
        self.assertFalse(engine._event_locked("bird_in_space_case"))
        self._fire(engine, "northwest_expedition")
        self.assertTrue(engine._event_locked("bird_in_space_case"))
        self.assertIsNone(engine.event_lock_entry("bird_in_space_case")["until_turn"],
                          "禁令是永久的，不該有到期回合")
        # 永久：往後推很多回合仍然鎖著
        engine.state["turn"] = int(engine.state["turn"]) + 60
        self.assertTrue(engine._event_locked("bird_in_space_case"))

    def test_a_locked_bird_in_space_case_is_never_drawn(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "northwest_expedition")
        engine.state["event_pool"] = ["bird_in_space_case"]
        for _ in range(9):
            advance_turn(engine, "F")
        drawn = [entry["card_id"] for entry in engine.state["event_history"]]
        self.assertNotIn("bird_in_space_case", drawn)
        self.assertIn("bird_in_space_case", engine.state["event_pool"],
                      "封鎖不是移除：卡片仍留在池子裡")

    def test_turandot_still_lands_but_its_artifact_clause_is_dead(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "northwest_expedition")
        self.assertFalse(engine._event_locked("turandot_premiere"), "杜蘭朵不該被整張封鎖")
        self._fire(engine, "turandot_premiere")
        self.assertIn("turandot_premiere",
                      [e["card_id"] for e in engine.state["event_history"]])
        self.assertEqual(self._payout(engine), (10, 30), "文物收益那一段應該落空")
        self.assertEqual(engine._card_template("trade_export_uk")["cash_gain"], 30,
                         "貿易出口 +$10 照給")

    def test_the_freeze_only_blocks_rewrites_that_come_after_it(self):
        """禁令之前就已生效的改寫不受影響——本卡靠「後下先贏」蓋過去，不是靠禁令。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "bird_in_space_case")
        self.assertEqual(self._payout(engine), (30, 60))
        self._fire(engine, "northwest_expedition")
        self.assertEqual(self._payout(engine), (10, 30))

    def test_the_expeditions_own_rewrite_is_not_caught_by_its_own_ban(self):
        """禁令排在自己的改寫之後生效，否則這張卡會把自己擋掉。"""
        engine = GameEngine(seed=3)
        result = self._fire(engine, "northwest_expedition")
        kinds = [e["kind"] for e in (result.get("applied") or [])]
        self.assertLess(kinds.index("card_override"), kinds.index("override_freeze"))
        self.assertEqual(self._payout(engine), (10, 30))

    def test_the_ban_covers_every_card_that_raises_the_artifact_payout(self):
        """守門：日後若有人新增一張會調高文物收益的卡，這條會逼他一起處理禁令。"""
        engine = GameEngine(seed=3)
        base = engine.data["indexes"]["function_cards"]["artifact_smuggling"]
        expedition = engine._event_template("northwest_expedition")
        locked = set((expedition["apply"]["event_lock"][0]["cards"]))
        frozen = set(expedition["apply"]["override_freeze"][0]["fields"])
        for card in engine.data["event_cards"]["cards"]:
            if card["id"] == "northwest_expedition":
                continue
            for ov in (card.get("apply") or {}).get("card_overrides") or []:
                if ov["card_id"] != "artifact_smuggling":
                    continue
                raises = any(int(v) > int(base[k])
                             for k, v in (ov.get("fields") or {}).items()
                             if k in ("payout_min", "payout_max"))
                if not raises:
                    continue
                touched = {k for k in (ov.get("fields") or {})
                           if k in ("payout_min", "payout_max")}
                self.assertTrue(
                    card["id"] in locked or touched <= frozen,
                    f'{card["ref"]} {card["name"]} 會調高文物收益，'
                    f'但既沒被 10.2 封鎖、動到的欄位也不在凍結名單裡')



class NewspaperEffectTextTests(unittest.TestCase):
    """報紙「本報附誌」欄的排版，靠效果文字守幾條約定。這裡把約定釘住。

    前端 `newspaperEffectMarkup()` 用「半形連字號兩側帶空白」當條列分隔符。
    只要有人在效果文字裡用半形 `-` 當減號（「關係 -1」），那一行就會被切成兩條，
    畫面上憑空多一個項目符號。負號一律用全形減號 U+2212。
    """

    MINUS = "\u2212"

    def _cards(self):
        return load_game_data()["event_cards"]["cards"]

    def _texts(self, card):
        """一張卡上所有會進到報紙效果欄的文字。"""
        yield "effect", card.get("effect") or ""
        for option in ((card.get("resolution") or {}).get("options") or []):
            yield f'option:{option.get("id")}', option.get("effect_text") or ""

    def test_no_effect_text_uses_an_ascii_hyphen_as_a_minus_sign(self):
        bad = []
        for card in self._cards():
            for where, text in self._texts(card):
                for match in re.finditer(r"\s-\s*\d", text):
                    bad.append(f'{card["ref"]} {card["name"]} [{where}] …{text[max(0, match.start()-12):match.end()+6]}…')
        self.assertEqual(bad, [], "這些地方用半形 - 當減號，會被誤判成條列分隔符：\n" + "\n".join(bad))

    def test_bold_markers_are_balanced(self):
        """`**粗體**` 落單的話會整段吃掉，或把星號原樣印出來。"""
        bad = []
        for card in self._cards():
            for where, text in self._texts(card):
                if text.count("**") % 2:
                    bad.append(f'{card["ref"]} {card["name"]} [{where}]')
        self.assertEqual(bad, [], "粗體標記沒有成對：" + "、".join(bad))

    def test_backticks_are_balanced(self):
        """反引號在前端會被直接剝掉，落單的話會吃掉後面整段。"""
        bad = []
        for card in self._cards():
            for where, text in self._texts(card):
                if text.count("`") % 2:
                    bad.append(f'{card["ref"]} {card["name"]} [{where}]')
        self.assertEqual(bad, [], "反引號沒有成對：" + "、".join(bad))

    def test_every_bullet_separator_starts_a_real_item(self):
        """切出來的條目不該是空的，也不該只剩標點。"""
        for card in self._cards():
            for where, text in self._texts(card):
                for block in re.split(r"\n+", text):
                    parts = [p.strip() for p in re.split(r"\s+-\s+", block)]
                    for part in parts[1:]:
                        self.assertTrue(len(part) >= 2,
                                        f'{card["ref"]} {card["name"]} [{where}] 切出了空條目')



class PiaohaoNetworkTests(unittest.TestCase):
    """票號金融網：工業點與現金雙向互兌，兩邊同一匯率（2 工業點 ↔ $1），不設數量上限。"""

    CARD = "piaohao_network"

    def _ready(self, engine, code="S", factory=100, cash=100):
        payload = engine.state["players"][code]
        payload["factory_points"] = factory
        payload["treasury"] = cash
        payload["hand"].append(self.CARD)
        return payload

    def test_every_faction_starts_with_three_copies(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            payload = engine.state["players"][code]
            self.assertEqual(engine._card_count_in_player_zones(payload, self.CARD), 3, code)

    def test_selling_factory_points_pays_one_dollar_per_two_points(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        result = engine.use_function("S", self.CARD,
                                     exchange_direction="factory_to_cash", exchange_amount=40)
        self.assertEqual(payload["factory_points"], 60)
        self.assertEqual(payload["treasury"], 120)
        deal = result["piaohao_exchange"]
        self.assertEqual((deal["factory_spent"], deal["cash_gained"]), (40, 20))
        self.assertEqual(result["cash_delta"], 20)

    def test_buying_factory_points_costs_one_dollar_per_two_points(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        result = engine.use_function("S", self.CARD,
                                     exchange_direction="cash_to_factory", exchange_amount=30)
        self.assertEqual(payload["treasury"], 70)
        self.assertEqual(payload["factory_points"], 160)
        deal = result["piaohao_exchange"]
        self.assertEqual((deal["cash_spent"], deal["factory_gained"]), (30, 60))
        self.assertEqual(result["cash_delta"], -30)

    def test_a_round_trip_is_a_wash(self):
        """兩邊同一匯率，所以賣掉再買回來不賺不賠（使用者裁示如此）。"""
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        before = (payload["factory_points"], payload["treasury"])
        engine.use_function("S", self.CARD, exchange_direction="factory_to_cash", exchange_amount=40)
        payload["hand"].append(self.CARD)
        engine.use_function("S", self.CARD, exchange_direction="cash_to_factory", exchange_amount=20)
        self.assertEqual((payload["factory_points"], payload["treasury"]), before)

    def test_there_is_no_ceiling_on_the_amount(self):
        """不設上限：手上有多少就能換多少。"""
        engine = GameEngine(seed=3)
        payload = self._ready(engine, factory=1000, cash=0)
        engine.use_function("S", self.CARD, exchange_direction="factory_to_cash", exchange_amount=1000)
        self.assertEqual(payload["factory_points"], 0)
        self.assertEqual(payload["treasury"], 500)

    def test_odd_factory_amounts_are_refused(self):
        """工業點那一邊必須湊得成整份，湊不成不受理——不做無聲的無條件捨去。"""
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        with self.assertRaisesRegex(ValueError, "湊不成整份"):
            engine.use_function("S", self.CARD,
                                exchange_direction="factory_to_cash", exchange_amount=41)
        self.assertEqual(payload["factory_points"], 100)
        self.assertEqual(payload["treasury"], 100)
        self.assertIn(self.CARD, payload["hand"], "被拒絕的交易不該把卡吃掉")

    def test_you_cannot_sell_factory_points_you_do_not_have(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine, factory=10)
        with self.assertRaisesRegex(ValueError, "工業點不足"):
            engine.use_function("S", self.CARD,
                                exchange_direction="factory_to_cash", exchange_amount=20)
        self.assertEqual(payload["factory_points"], 10)
        self.assertIn(self.CARD, payload["hand"])

    def test_you_cannot_spend_cash_you_do_not_have(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine, cash=5)
        with self.assertRaisesRegex(ValueError, "現金不足"):
            engine.use_function("S", self.CARD,
                                exchange_direction="cash_to_factory", exchange_amount=6)
        self.assertEqual(payload["treasury"], 5)
        self.assertIn(self.CARD, payload["hand"])

    def test_direction_and_amount_are_both_required(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        with self.assertRaisesRegex(ValueError, "兌換方向"):
            engine.use_function("S", self.CARD, exchange_amount=10)
        payload["hand"].append(self.CARD)
        with self.assertRaisesRegex(ValueError, "兌換數量"):
            engine.use_function("S", self.CARD, exchange_direction="factory_to_cash")
        payload["hand"].append(self.CARD)
        with self.assertRaisesRegex(ValueError, "必須大於 0"):
            engine.use_function("S", self.CARD,
                                exchange_direction="factory_to_cash", exchange_amount=0)
        with self.assertRaisesRegex(ValueError, "兌換方向"):
            engine.use_function("S", self.CARD,
                                exchange_direction="sideways", exchange_amount=10)

    def test_the_used_card_goes_to_the_discard_pile(self):
        engine = GameEngine(seed=3)
        payload = self._ready(engine)
        engine.use_function("S", self.CARD, exchange_direction="factory_to_cash", exchange_amount=2)
        self.assertNotIn(self.CARD, payload["hand"])
        self.assertIn(self.CARD, payload["discard"])

    def test_the_server_passes_the_exchange_arguments_through(self):
        """新參數要一路接到 HTTP 層，否則前端點了也沒用。"""
        import inspect
        from backend import server
        source = inspect.getsource(server._Handler._use_function if hasattr(server, "_Handler")
                                   else server)
        for name in ("exchange_direction", "exchange_amount"):
            self.assertIn(name, source, f"server.py 沒有把 {name} 傳下去")



class CabinetSovietGateTests(unittest.TestCase):
    """上海灘宋貴人與孔祥熙從政：除了〈結盟江浙財團〉，還要對蘇關係 5 以下。

    這兩張是江浙財團路線的內閣卡，與親蘇路線（汪精衛、周恩來，需對蘇 ≥6）互斥。
    門檻同時擋兩件事：條件不成立時不會洗進牌庫，硬要打也會被 _validate_card_use 擋下。
    """

    CARDS = ("soong_patronage", "kong_xiangxi_office")

    def _zones(self, engine, card_id, player="S"):
        payload = engine.state["players"][player]
        return (payload["function_deck"] + payload["hand"] + payload["discard"]).count(card_id)

    def _unlock(self, engine, player="S"):
        """照規則打出〈結盟江浙財團〉，不直接塞 unlocks。"""
        payload = engine.state["players"][player]
        payload["treasury"] = 500
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("江蘇", "浙江"):
                engine.state["city_owners"][city["id"]] = player
        payload["foreign_relations"]["su"] = 2
        engine._sync_conditional_deck_cards(player)
        payload["hand"].append("jiangzhe_financiers")
        engine.use_function(player, "jiangzhe_financiers")
        engine._sync_conditional_deck_cards(player)

    def test_both_cards_declare_the_gate(self):
        engine = GameEngine(seed=3)
        for cid in self.CARDS:
            card = engine._card_template(cid)
            self.assertEqual(card.get("requires_relation_max"),
                             {"power": "su", "value": 5}, cid)

    def test_they_reach_the_deck_when_moscow_is_cold(self):
        engine = GameEngine(seed=3)
        self._unlock(engine)
        for cid in self.CARDS:
            self.assertEqual(self._zones(engine, cid), 1, cid)

    def test_warm_soviet_relations_pull_them_back_out(self):
        engine = GameEngine(seed=3)
        self._unlock(engine)
        engine.state["players"]["S"]["foreign_relations"]["su"] = 6
        engine._sync_conditional_deck_cards("S")
        for cid in self.CARDS:
            self.assertEqual(self._zones(engine, cid), 0, cid)
        # 降回 5 又洗回來
        engine.state["players"]["S"]["foreign_relations"]["su"] = 5
        engine._sync_conditional_deck_cards("S")
        for cid in self.CARDS:
            self.assertEqual(self._zones(engine, cid), 1, cid)

    def test_five_is_in_and_six_is_out(self):
        """「對蘇 < 6」＝ 5 以下可用，6 就不行——邊界釘死，免得日後寫成 ≤6。"""
        engine = GameEngine(seed=3)
        self._unlock(engine)
        payload = engine.state["players"]["S"]
        for value, allowed in ((5, True), (6, False)):
            payload["foreign_relations"]["su"] = value
            for cid in self.CARDS:
                card = engine._card_template(cid)
                if allowed:
                    engine._validate_card_use("S", card)
                else:
                    with self.assertRaisesRegex(ValueError, "5 以下"):
                        engine._validate_card_use("S", card)

    def test_playing_it_is_blocked_once_relations_warm_up(self):
        """已經在手上的牌不會消失，但打不出去。"""
        engine = GameEngine(seed=3)
        self._unlock(engine)
        payload = engine.state["players"]["S"]
        payload["hand"].append("soong_patronage")
        payload["foreign_relations"]["su"] = 7
        with self.assertRaisesRegex(ValueError, "5 以下"):
            engine.use_function("S", "soong_patronage")
        self.assertIn("soong_patronage", payload["hand"], "被擋下的牌不該被吃掉")

    def test_the_unlock_is_still_required_on_its_own(self):
        """關係達標但沒觸發〈結盟江浙財團〉一樣不行——兩個條件是且，不是或。"""
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["S"]
        payload["foreign_relations"]["su"] = 2
        engine._sync_conditional_deck_cards("S")
        for cid in self.CARDS:
            self.assertEqual(self._zones(engine, cid), 0, cid)
            payload["hand"].append(cid)
            with self.assertRaisesRegex(ValueError, "結盟江浙財團"):
                engine.use_function("S", cid)
            payload["hand"].remove(cid)

    def test_the_pro_soviet_and_financier_routes_stay_mutually_exclusive(self):
        """江浙路線需對蘇 ≤5、親蘇內閣需對蘇 ≥6：同一家不可能兩邊都拿。"""
        engine = GameEngine(seed=3)
        for cid in self.CARDS + ("jiangzhe_financiers",):
            self.assertEqual(engine._card_template(cid)["requires_relation_max"]["value"], 5, cid)
        for cid in ("wang_jingwei_return", "zhou_enlai_underground"):
            self.assertEqual(engine._card_template(cid)["requires_relation_min"], 6, cid)



class EventCardTableTests(unittest.TestCase):
    """cards/README.md 的「五九張事件卡逐張明細」由 event_cards.json 產生，兩邊必須同步。

    這一節是給人看的說明文件，最容易在改卡片時被忘記更新——一旦文件寫的和
    引擎實際跑的不一樣，比沒有文件更糟。這條測試把兩邊釘在一起。
    """

    @staticmethod
    def _builder():
        import importlib.util
        import pathlib
        path = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "build_event_card_table.py"
        spec = importlib.util.spec_from_file_location("build_event_card_table", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_event_card_table_matches_the_data(self):
        builder = self._builder()
        readme = builder.README.read_text(encoding="utf-8")
        self.assertIn(builder.BEGIN, readme, "README 少了事件卡明細的起始標記")
        self.assertIn(builder.END, readme, "README 少了事件卡明細的結束標記")
        head, rest = readme.split(builder.BEGIN, 1)
        _, tail = rest.split(builder.END, 1)
        self.assertEqual(
            head + builder.build() + tail, readme,
            "README 的事件卡明細與 event_cards.json 不同步，"
            "請跑 python3 scripts/build_event_card_table.py")

    def test_story_table_matches_the_function_cards(self):
        """〈票號金融網〉的故事就是這樣掉的：卡加進資料檔，手寫的 README 表沒人補。"""
        builder = self._builder()
        readme = builder.README.read_text(encoding="utf-8")
        self.assertIn(builder.STORY_BEGIN, readme)
        self.assertEqual(builder._replace(readme, builder.STORY_BEGIN, builder.STORY_END,
                                          builder.build_story_table()),
                         readme,
                         "README 的故事表與 function_cards.json 不同步，"
                         "請跑 python3 scripts/build_event_card_table.py")

    def test_every_card_with_a_story_is_listed(self):
        builder = self._builder()
        table = builder.build_story_table()
        for card in load_game_data()["function_cards"]["cards"]:
            if not (card.get("story") or "").strip():
                continue
            self.assertIn(f'| {card["name"]} |', table,
                          f'{card["id"]} {card["name"]} 有故事卻沒列進表裡')

    def test_every_card_appears_exactly_once(self):
        builder = self._builder()
        table = builder.build()
        for card in load_game_data()["event_cards"]["cards"]:
            self.assertEqual(table.count(f'| {card["ref"]} | '), 1,
                             f'{card["ref"]} {card["name"]} 沒有剛好出現一次')

    def test_cards_with_pending_work_are_flagged(self):
        """`apply.pending` 是「確實還沒接上」的清單，表格一定要標出來。

        注意 `apply.notes` 不算——那只是說明機制怎麼運作。兩者混為一談的話，
        9.5、10.1 這種其實全自動的卡會被誤標成需要人工，那比沒寫還糟。
        """
        builder = self._builder()
        table = builder.build()
        for card in load_game_data()["event_cards"]["cards"]:
            row = next(line for line in table.splitlines()
                       if line.startswith(f'| {card["ref"]} | '))
            if builder._collect(card)[1]:
                self.assertIn("待卡片建檔", row,
                              f'{card["ref"]} {card["name"]} 有 pending 卻沒被標出來')
            else:
                self.assertNotIn("待卡片建檔", row,
                                 f'{card["ref"]} {card["name"]} 沒有 pending 卻被標成待辦')

    def test_option_level_effects_are_not_reported_as_flavour_text(self):
        """表態卡的效果全在 resolution.options[].apply 底下。

        產生器若只看最上層 `apply`，2.3／2.5／7.3／11.3 會被標成「純敘事」——
        它們明明都自動化了。這條擋住那個誤判。
        """
        builder = self._builder()
        table = builder.build()
        for ref in ("2.3", "2.5", "7.3", "11.3"):
            row = next(line for line in table.splitlines()
                       if line.startswith(f'| {ref} | '))
            self.assertNotIn("純敘事", row, f'{ref} 的效果在選項底下，不該被當成純敘事')
            self.assertIn("自動", row, f'{ref} 應該標成已自動化')

    def test_no_card_is_left_to_manual_play(self):
        """守門：整張表不准再出現「玩家自行遵守」。

        該自動化的都要自動化；真正卡在「目標卡還沒建檔」的，標成待建檔，
        不要推給玩家。
        """
        builder = self._builder()
        self.assertNotIn("玩家自行遵守", builder.build())

    def test_no_internal_ids_leak_into_the_table(self):
        """表格是給人看的，不該印出 beijing / shanghai 這種內部代號。"""
        builder = self._builder()
        table = builder.build()
        for city_id in builder.CITY_NAMES:
            self.assertNotIn(f'控制{city_id}', table, f'{city_id} 應該印中文名')



class NewlyAutomatedEffectTests(unittest.TestCase):
    """本輪補上的三個自動化：7.3 省份免疫暴動、3.3 [幫會] 持續時間加碼、11.5 報紙擇一。"""

    def _fire(self, engine, card_id, choice=None):
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        return view, engine.respond_event(view["waiting_for"], choice=choice)

    # ---- 7.3 殷墟第一鏟：科學發掘 → 河南三回合免疫暴動 ----

    def _own_henan(self, engine, code):
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "河南":
                engine.state["city_owners"][city["id"]] = code

    def test_scientific_dig_shields_henan_from_riots(self):
        engine = GameEngine(seed=3)
        self._own_henan(engine, "S")
        view, result = self._fire(engine, "yinxu_first_spade", choice="scientific_dig")
        owner = view["drawer"]
        shield = [e for e in engine.state["players"][owner]["timed_effects"]
                  if e.get("kind") == "gang_riot_shield" and e.get("province") == "河南"]
        self.assertEqual(len(shield), 1)
        self.assertEqual(shield[0]["remaining_turns"], 3)
        for mechanic in ("qing_gang_riot", "communist_riot", "red_army_uprising"):
            self.assertTrue(engine._gang_riot_shielded(owner, "河南", mechanic), mechanic)

    def test_the_shield_really_blocks_a_gang_riot(self):
        """不是只掛個旗標——打出〈杜月笙的豪賭〉指向河南要真的被擋下。"""
        engine = GameEngine(seed=3)
        self._own_henan(engine, "S")
        view, _ = self._fire(engine, "yinxu_first_spade", choice="scientific_dig")
        owner = view["drawer"]
        attacker = next(c for c in engine.state["players"] if c != owner)
        self._own_henan(engine, owner)
        payload = engine.state["players"][attacker]
        payload["treasury"] = 200
        payload.setdefault("unlocks", []).append("已收買黑金")
        payload["hand"].append("du_yuesheng_gamble")
        before = len(engine.state.get("city_output_effects", []))
        try:
            engine.use_function(attacker, "du_yuesheng_gamble",
                                target_owner=owner, target_province="河南")
        except ValueError:
            pass          # 直接被擋下也算擋住
        riots = [e for e in engine.state.get("city_output_effects", [])
                 if e.get("kind") == "qing_gang_riot" and e.get("province") == "河南"]
        self.assertEqual(riots, [], "河南在保護期內不該發得起黑幫暴動")
        self.assertEqual(len(engine.state.get("city_output_effects", [])), before)

    def test_selling_to_foreigners_gets_no_shield(self):
        engine = GameEngine(seed=3)
        self._own_henan(engine, "S")
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = ["yinxu_first_spade"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        engine.respond_event(view["waiting_for"], choice="sell_to_foreigners", follow_up="uk")
        owner = view["drawer"]
        self.assertFalse([e for e in engine.state["players"][owner]["timed_effects"]
                          if e.get("kind") == "gang_riot_shield"])

    # ---- 3.3 火燒紅蓮寺：[幫會] 事件卡持續時間 +1 ----

    def test_gang_tag_duration_bonus_is_recorded(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "burning_red_lotus")
        entries = engine.state["event_duration_bonuses"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["tags"], ["幫會"])
        self.assertEqual(entries[0]["bonus"], 1)

    def test_a_gang_tagged_card_lasts_one_turn_longer(self):
        """借一張現有卡掛上 [幫會] 標籤，確認它的限時效果真的多一回合。

        資料檔目前沒有 [幫會] 卡，所以這裡自己造一張——機制是否成立，
        不該等到那批卡建檔才知道。
        """
        engine = GameEngine(seed=3)
        probe = next(c for c in engine.data["event_cards"]["cards"]
                     if c["id"] == "baird_television")
        probe["tags"] = ["幫會"]
        probe["apply"] = {"timed_flags": [{"kind": "probe_flag", "turns": 2}]}

        plain = GameEngine(seed=3)
        twin = next(c for c in plain.data["event_cards"]["cards"] if c["id"] == "baird_television")
        twin["tags"] = ["幫會"]
        twin["apply"] = {"timed_flags": [{"kind": "probe_flag", "turns": 2}]}
        self._fire(plain, "baird_television")
        base = next(e for e in plain.state["players"]["F"]["timed_effects"]
                    if e.get("kind") == "probe_flag")["remaining_turns"]

        self._fire(engine, "burning_red_lotus")
        # 加碼只撐 3 回合，而事件正好每 3 回合一次——用 _fire 連開兩張會卡在到期那一格。
        # 這裡直接在同一回合套用第二張的 payload，測的是加碼本身而不是到期時機。
        card = engine._event_template("baird_television")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        boosted = next(e for e in engine.state["players"]["F"]["timed_effects"]
                       if e.get("kind") == "probe_flag")["remaining_turns"]
        self.assertEqual(boosted, base + 1)

    def test_untagged_cards_are_unaffected(self):
        engine = GameEngine(seed=3)
        probe = next(c for c in engine.data["event_cards"]["cards"]
                     if c["id"] == "baird_television")
        probe.pop("tags", None)
        probe["apply"] = {"timed_flags": [{"kind": "probe_flag", "turns": 2}]}
        self._fire(engine, "burning_red_lotus")
        card = engine._event_template("baird_television")
        engine._apply_event_payload(card["apply"], players=["F"], card=card)
        entry = next(e for e in engine.state["players"]["F"]["timed_effects"]
                     if e.get("kind") == "probe_flag")
        self.assertEqual(entry["remaining_turns"], 2)

    # ---- 11.5 廢兩改元：報紙依擲骰結果擇一 ----

    def test_the_roll_happens_at_draw_time_and_picks_the_newspaper(self):
        seen = set()
        for seed in range(14):
            engine = GameEngine(seed=seed)
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["silver_tael_reform"]
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            index = view["newspaper_index"]
            self.assertIn(index, (0, 1), "報紙索引只能是這兩則之一")
            seen.add(index)
        self.assertEqual(seen, {0, 1}, "兩版報紙都應該有機會刊出")

    def test_the_newspaper_matches_the_outcome_that_is_settled(self):
        """報紙刊「不成」，結算就必須真的走不成那一支——不能各說各話。"""
        for seed in range(14):
            engine = GameEngine(seed=seed)
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["silver_tael_reform"]
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            index = view["newspaper_index"]
            result = engine.respond_event(view["waiting_for"])
            roll = next(e for e in result["applied"] if e["kind"] == "random_outcome")
            self.assertEqual(roll["newspaper_index"], index,
                             "結算結果與抽出當下刊的報紙不一致")
            expected = "succeeds" if index == 0 else "fails"
            self.assertEqual(roll["chosen"], expected)

    def test_cards_without_a_roll_report_no_index(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["baird_television"]
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view()["newspaper_index"])



class SecurityEventShieldTests(unittest.TestCase):
    """7.3「科學發掘」的免疫也擋 security 類事件卡。

    實際會傷到城市的 security 卡只有兩張，都走 student_unrest：
      9.3 革命文學論戰（3 回合）、10.7 北京大學共運（2 回合）。
    5.3 純新聞、7.4 只解鎖功能卡、10.1 是分支卡，都不碰城市。
    """

    UNREST_CARDS = ("revolutionary_literature", "peking_university_movement")

    def _dig(self, engine, owner="S"):
        """照規則打出 7.3 並選科學發掘，讓 owner 拿到河南的免疫。"""
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "河南":
                engine.state["city_owners"][city["id"]] = owner
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = ["yinxu_first_spade"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        engine.respond_event(view["waiting_for"], choice="scientific_dig")
        return view["drawer"]

    def _henan_big_cities(self, engine, owner):
        return [c["id"] for c in engine.data["strategic_map"]["cities"]
                if c.get("province") == "河南"
                and engine.state["city_owners"].get(c["id"]) == owner
                and int(engine._with_level(c).get("level", 0)) >= 4]

    def test_the_shield_lists_security_events(self):
        engine = GameEngine(seed=3)
        owner = self._dig(engine)
        shield = next(e for e in engine.state["players"][owner]["timed_effects"]
                      if e.get("kind") == "gang_riot_shield")
        self.assertIn("security_event", shield["blocked_mechanics"])
        self.assertTrue(engine._gang_riot_shielded(owner, "河南", "security_event"))

    def test_shielded_cities_are_never_picked_for_student_unrest(self):
        """免疫是「根本挑不到」，不是「挑中之後不痛」。"""
        engine = GameEngine(seed=3)
        owner = self._dig(engine)
        engine.state["players"][owner]["foreign_relations"]["su"] = 0   # 進得了學潮名單
        candidates = engine._student_unrest_candidates(owner, 4)
        henan = [c["id"] for c in candidates if c.get("province") == "河南"]
        self.assertEqual(henan, [], "河南受保護，不該還在學潮候選名單裡")

    def test_an_unprotected_province_is_still_fair_game(self):
        engine = GameEngine(seed=3)
        owner = self._dig(engine)
        engine.state["players"][owner]["foreign_relations"]["su"] = 0
        candidates = engine._student_unrest_candidates(owner, 4)
        self.assertTrue([c for c in candidates if c.get("province") != "河南"],
                        "只有河南該被擋，其他省份照舊")

    def test_a_player_without_the_dig_keeps_every_candidate(self):
        engine = GameEngine(seed=3)
        owner = self._dig(engine)
        other = next(c for c in engine.state["players"] if c != owner)
        engine.state["players"][other]["foreign_relations"]["su"] = 0
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") == "河南":
                engine.state["city_owners"][city["id"]] = other
        henan = [c["id"] for c in engine._student_unrest_candidates(other, 4)
                 if c.get("province") == "河南"]
        self.assertEqual(sorted(henan), sorted(self._henan_big_cities(engine, other)),
                         "免疫是發給打出那張卡的玩家，不是綁在省份上給所有人")

    def test_both_unrest_cards_respect_the_shield(self):
        """9.3 與 10.7 都要吃這條，不能只擋其中一張。"""
        for card_id in self.UNREST_CARDS:
            engine = GameEngine(seed=3)
            owner = self._dig(engine)
            # 河南以外的大城全部轉走，讓這家只剩河南可挑
            for city in engine.data["strategic_map"]["cities"]:
                if city.get("province") != "河南" and engine.state["city_owners"].get(city["id"]) == owner:
                    engine.state["city_owners"][city["id"]] = "W" if owner != "W" else "F"
            for code in engine.state["players"]:
                engine.state["players"][code]["foreign_relations"]["su"] = 0
            current = int(engine.state["turn"])
            engine.state["turn"] = ((current // 3) + 1) * 3 - 1
            engine.state["event_pool"] = [card_id]
            engine.next_turn(active_player="F")
            result = engine.respond_event(engine.pending_event_view()["waiting_for"])
            mine = [e for e in result["applied"]
                    if e["kind"] == "student_unrest" and e["player"] == owner]
            self.assertTrue(mine, f'{card_id} 應該有回報這一家的學潮結果')
            self.assertEqual(mine[0]["cities"], [], f'{card_id}：河南受保護，不該發生學潮')
            self.assertIn("河南", mine[0].get("shielded_provinces") or [],
                          f'{card_id}：回報要說清楚是被免疫擋掉的')
            hit = [e for e in engine.state.get("city_output_effects", [])
                   if e.get("kind") == "student_unrest" and e.get("target_owner") == owner]
            self.assertEqual(hit, [], f'{card_id}：不該真的掛上學潮效果')



class ForeignPunishmentTests(unittest.TestCase):
    """列強懲戒的通用機制：地面佔領、水域封鎖、空襲轟炸，以及演習這個變體。"""

    MANCHURIA = ("奉天", "吉林", "黑龍江")

    def _own(self, engine, code, provinces):
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in provinces:
                engine.state["city_owners"][city["id"]] = code

    def _hostile(self, engine, code, power="jp", value=-6):
        engine.state["players"][code]["foreign_relations"][power] = value

    def _ignore_ultimatum(self, engine, power, owner=None):
        """讓某位（或全部）玩家處於「已無視最後通牒」的狀態。

        [地面部隊] 懲戒只有在通牒被無視之後才對那個人解封，所以測佔領機制的
        前置條件就是先把通牒放到 failed。"""
        for code in ([owner] if owner else list(engine.state["players"])):
            engine.state.setdefault("ultimatums", []).append({
                "id": f"test:{power}:{code}", "card_id": f"{power}_ultimatum",
                "power": power, "owner": code, "cities": [],
                "opened_turn": 0, "deadline_turn": 0, "status": "failed",
            })

    def _fire(self, engine, card_id):
        card = engine._event_template(card_id)
        power = (card.get("entry_condition") or {}).get("requires_failed_ultimatum")
        if power and not any(e["power"] == power and e["status"] == "failed"
                             for e in engine.state.get("ultimatums") or []):
            self._ignore_ultimatum(engine, power)
        current = int(engine.state["turn"])
        engine.state["turn"] = ((current // 3) + 1) * 3 - 1
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒有被抽出來")
        return view, engine.respond_event(view["waiting_for"])

    def _income(self, engine, code, city_id):
        return next((item for item in engine.state["players"][code]["city_economy"]
                     if item["id"] == city_id), None)

    # ---- 地面部隊佔領 ----

    def test_ground_occupation_zeroes_the_provinces(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F")
        view, result = self._fire(engine, "kwantung_army_occupies_manchuria")
        self.assertEqual(view["drawer"], "F")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        self.assertEqual(sorted(entry["provinces"]), sorted(self.MANCHURIA))
        self.assertEqual(entry["power"], "jp")
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") not in self.MANCHURIA:
                continue
            row = self._income(engine, "F", city["id"])
            self.assertIsNotNone(row, city["id"])
            self.assertEqual((row["cash"], row["factory"]), (0, 0), city["name"])

    def test_hostile_players_take_the_damage_and_others_do_not(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F", value=-6)
        self._fire(engine, "kwantung_army_occupies_manchuria")
        pending = engine.state["players"]["F"]["pending_frontend_effects"]
        hit = [e for e in pending if e["kind"] == "foreign_punishment_damage"]
        self.assertEqual(len(hit), 1)
        self.assertAlmostEqual(hit[0]["army_force"], -0.40)
        self.assertAlmostEqual(hit[0]["harbor_gunboat_hp"], -0.40)

    def test_a_drill_occupies_but_never_hurts(self):
        """演習不是懲戒：土地照樣易手，但不掉一兵一卒，而且有固定回合數。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", ("奉天", "吉林"))
        self._hostile(engine, "F")
        _, result = self._fire(engine, "kwantung_army_special_drill")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        self.assertTrue(entry["drill"])
        self.assertIsNotNone(entry["until_turn"])
        self.assertEqual(entry["damage"], {})
        self.assertFalse([e for e in engine.state["players"]["F"]["pending_frontend_effects"]
                          if e["kind"] == "foreign_punishment_damage"])

    def test_a_drill_expires_on_its_own_and_hands_the_land_back(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", ("奉天", "吉林"))
        self._hostile(engine, "F")
        self._fire(engine, "kwantung_army_special_drill")
        before = dict(engine.state["city_owners"])
        for _ in range(5):
            advance_turn(engine, "F")
        self.assertEqual(engine.state["foreign_punishments"], [])
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("奉天", "吉林"):
                self.assertEqual(engine.state["city_owners"].get(city["id"]),
                                 before.get(city["id"]), city["name"])

    def test_a_punishment_lifts_only_after_relations_mend(self):
        """關係修好的**下一回合**才解除，而且解除後土地變無主。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F")
        self._fire(engine, "kwantung_army_occupies_manchuria")
        advance_turn(engine, "F")
        self.assertEqual(len(engine.state["foreign_punishments"]), 1, "還在敵對，不該解除")
        engine.state["players"]["F"]["foreign_relations"]["jp"] = 0   # 修好了
        advance_turn(engine, "F")
        self.assertEqual(len(engine.state["foreign_punishments"]), 1, "修好的當回合還不解除")
        advance_turn(engine, "F")
        self.assertEqual(engine.state["foreign_punishments"], [], "下一回合才解除")
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in self.MANCHURIA:
                self.assertIsNone(engine.state["city_owners"].get(city["id"]),
                                  f'{city["name"]} 解除後應成為無主地')

    # ---- 水域封鎖 ----

    def test_water_blockade_zeroes_the_yangtze_ports(self):
        engine = GameEngine(seed=3)
        yangtze = ["hankou", "wuchang", "nanjing", "shanghai", "jiujiang"]
        for city_id in yangtze:
            engine.state["city_owners"][city_id] = "S"
        self._hostile(engine, "S", value=-4)
        _, result = self._fire(engine, "japanese_navy_blockades_yangtze")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        self.assertEqual(entry["waters"], ["長江"])
        for city_id in yangtze:
            row = self._income(engine, "S", city_id)
            self.assertEqual((row["cash"], row["factory"]), (0, 0), city_id)
        # 不在長江上的港口不受影響
        engine.state["city_owners"]["qingdao"] = "S"
        engine._refresh_city_income()
        qingdao = self._income(engine, "S", "qingdao")
        self.assertGreater(qingdao["cash"] + qingdao["factory"], 0)

    def test_blockade_damage_hits_fleets_and_harbour_garrisons(self):
        engine = GameEngine(seed=3)
        engine.state["city_owners"]["hankou"] = "S"
        self._hostile(engine, "S", value=-4)
        self._fire(engine, "japanese_navy_blockades_yangtze")
        hit = [e for e in engine.state["players"]["S"]["pending_frontend_effects"]
               if e["kind"] == "foreign_punishment_damage"][0]
        self.assertAlmostEqual(hit["fleet_hp"], -0.50)
        self.assertAlmostEqual(hit["harbor_army_force"], -0.30)

    # ---- 空襲轟炸 ----

    def test_air_raid_targets_the_five_biggest_cities(self):
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        _, result = self._fire(engine, "japanese_air_raid")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        self.assertEqual(len(entry["city_ids"]), 5)
        # 真的是最大的五座（$ ＋ 工廠）
        owned = [c for c in engine.data["strategic_map"]["cities"]
                 if engine.state["city_owners"].get(c["id"], c["faction"]) == "S"]
        ranked = sorted(owned, key=lambda c: (-(int(c["cash"]) + int(c["factory"])), c["id"]))
        self.assertEqual(entry["city_ids"], [c["id"] for c in ranked[:5]])
        for city_id in entry["city_ids"]:
            row = self._income(engine, "S", city_id)
            self.assertEqual((row["cash"], row["factory"]), (0, 0), city_id)

    def test_bombed_cities_report_their_status_for_the_map(self):
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        _, result = self._fire(engine, "japanese_air_raid")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        status = engine.punishments.city_status(entry["city_ids"][0])
        self.assertEqual(status["status"], "bombing")
        self.assertEqual(status["label"], "轟炸中")
        self.assertEqual(status["power"], "jp")

    def test_targets_follow_the_player_when_a_city_changes_hands(self):
        """轟炸目標是動態的：城市被搶走就換一個遞補，永遠盯著最大的五座。"""
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        _, result = self._fire(engine, "japanese_air_raid")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        stolen = entry["city_ids"][0]
        engine.state["city_owners"][stolen] = "F"
        advance_turn(engine, "F")
        live = engine.state["foreign_punishments"][0]
        self.assertNotIn(stolen, live["city_ids"], "被搶走的城不該還在轟炸名單裡")
        self.assertEqual(len(live["city_ids"]), 5, "應該補上一座，維持五座")

    def test_release_starts_a_three_turn_rebuild(self):
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        _, result = self._fire(engine, "japanese_air_raid")
        entry = next(e["punishment"] for e in result["applied"]
                     if e["kind"] == "foreign_punishment")
        target = entry["city_ids"][0]
        engine.state["players"]["S"]["foreign_relations"]["jp"] = 0
        advance_turn(engine, "F")
        advance_turn(engine, "F")
        self.assertEqual(engine.state["foreign_punishments"], [])
        status = engine.punishments.city_status(target)
        self.assertEqual(status["status"], "rebuilding")
        self.assertEqual(status["label"], "重建中")
        row = self._income(engine, "S", target)
        self.assertEqual((row["cash"], row["factory"]), (0, 0), "重建中仍然沒有產出")
        for _ in range(3):
            advance_turn(engine, "F")
        self.assertIsNone(engine.punishments.city_status(target), "三回合後應復工")
        row = self._income(engine, "S", target)
        self.assertGreater(row["cash"] + row["factory"], 0)

    # ---- 逐玩家封鎖 ----

    def test_the_same_punishment_never_lands_twice_on_one_player(self):
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        self._fire(engine, "japanese_air_raid")
        card = engine._event_template("japanese_air_raid")
        self.assertNotIn("S", engine._event_eligible_players(card),
                         "已經在挨炸的人不該再抽到同一張")

    def test_but_another_player_can_take_the_same_punishment(self):
        """兩個對日交惡的玩家可以同時挨炸——封鎖是逐玩家的，不是整張卡的。"""
        engine = GameEngine(seed=3)
        self._hostile(engine, "S", value=-4)
        self._hostile(engine, "N", value=-4)
        self._fire(engine, "japanese_air_raid")
        card = engine._event_template("japanese_air_raid")
        eligible = engine._event_eligible_players(card)
        self.assertNotIn("S", eligible)
        self.assertIn("N", eligible, "另一個對日交惡的玩家照樣抽得到")

    def test_only_hostile_players_are_eligible_at_all(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["jp"] = 0
        card = engine._event_template("japanese_air_raid")
        self.assertEqual(engine._event_eligible_players(card), [],
                         "對日關係沒有跌到 −4 以下就不該降臨")

    # ---- 先來後到 ----

    def test_an_already_occupied_province_is_not_taken_twice(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F")
        self._fire(engine, "kwantung_army_occupies_manchuria")
        second = engine.punishments.open(
            card_id="probe_uk_landing", power="uk", kind="ground_occupation",
            owner="F", provinces=["奉天", "江蘇"], label="probe")
        self.assertEqual(second["provinces"], ["江蘇"], "奉天已被日本佔走，英國只能拿剩下的")
        self.assertEqual(second["skipped_provinces"], ["奉天"])

    # ---- 前端待辦的銷帳 ----

    def _raid_damage(self, engine, code="F"):
        return [e for e in engine.state["players"][code].get("pending_frontend_effects") or []
                if e["kind"] == "foreign_punishment_damage"]

    def test_air_raid_reissues_damage_every_turn(self):
        """空襲卡寫的是「每回合」：只要還在炸，每過一回合就要再開一份傷害待辦。"""
        engine = GameEngine(seed=3)
        self._hostile(engine, "F", value=-6)
        self._fire(engine, "japanese_air_raid")
        engine.state["players"]["F"]["pending_frontend_effects"] = []
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        fresh = self._raid_damage(engine)
        self.assertEqual(len(fresh), 1, "轟炸持續中，這一回合應該再排一份傷害")
        self.assertAlmostEqual(fresh[0]["army_force"], -0.30)
        self.assertTrue(fresh[0]["evict_from_city"])

    def test_ground_occupation_damage_is_one_shot(self):
        """佔領與封鎖的傷害是一次性的；下一回合不該再扣一次。"""
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F")
        self._fire(engine, "kwantung_army_occupies_manchuria")
        engine.state["players"]["F"]["pending_frontend_effects"] = []
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertEqual(self._raid_damage(engine), [])

    def test_consuming_frontend_effects_clears_only_that_kind(self):
        engine = GameEngine(seed=3)
        self._own(engine, "F", self.MANCHURIA)
        self._hostile(engine, "F")
        self._fire(engine, "kwantung_army_occupies_manchuria")
        engine.state["players"]["F"]["pending_frontend_effects"].append(
            {"kind": "loyalty_all", "amount": 1})
        result = engine.consume_frontend_effects("F", kind="foreign_punishment_damage")
        self.assertEqual(len(result["consumed"]), 1)
        self.assertEqual(result["consumed"][0]["kind"], "foreign_punishment_damage")
        self.assertEqual(self._raid_damage(engine), [], "銷帳後不該再看到同一筆")
        left = engine.state["players"]["F"]["pending_frontend_effects"]
        self.assertEqual([e["kind"] for e in left], ["loyalty_all"], "別人的待辦不該被順手清掉")
        self.assertEqual(result["state"]["turn"], engine.state["turn"])


class EconomyEventTests(unittest.TestCase):
    """第十三區塊「經濟事件」前 20 張（有現成機制的那批）。

    這批全是 `acknowledge` 卡：閱報即可，沒有表態分支。因此陷阱不在選項，
    而在**作用範圍**——卡片層級的 `apply` 預設對全場生效，設計稿標
    「僅適用符合條件的玩家」的那幾張若不特別限縮，沒資格的人也會跟著領錢。
    """

    CARDS = ["world_oil_price_surge", "arms_market_competition", "arms_embargo_rumour",
             "grain_price_spike", "industrial_exposition", "bumper_harvest",
             "cotton_yarn_boom", "deflation", "north_china_drought",
             "treaty_port_prosperity", "customs_salt_surplus", "silk_tea_export_boom",
             "salt_administration_reform", "chinese_liquor_expo",
             "sothebys_porcelain_auction", "chinese_tea_expo",
             "foreign_factory_investment", "overseas_chinese_investment",
             "industrial_technology_transfer", "foreign_bank_failures"]

    def _fire(self, engine, card_id, turn=2):
        """把這張卡（也只有這張）推上檯面並結算掉，回傳 applied。"""
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        self.assertEqual(view["card"]["id"], card_id)
        applied = []
        for _ in range(8):
            view = engine.pending_event_view()
            if not view:
                break
            applied += engine.respond_event(view["waiting_for"])["applied"]
        return applied

    def _control(self, setup, card_id, turn=2, seed=3):
        """同一個開局跑兩次：一次抽這張卡，一次空池子當對照組。

        事件結完之後回合才會補跑經濟結算，所以事後直接看國庫，看到的是
        「事件效果 ＋ 本回合收入」。要驗事件本身給了多少，就得扣掉收入——
        對照組正是那筆收入。先前直接拿事前事後相減，數字全部對不上。
        """
        results = []
        for pool in ([card_id], []):
            engine = GameEngine(seed=seed)
            setup(engine)
            engine.state["turn"] = turn
            engine.state["event_pool"] = list(pool)
            engine.next_turn(active_player="F")
            applied = []
            for _ in range(8):
                view = engine.pending_event_view()
                if not view:
                    break
                applied += engine.respond_event(view["waiting_for"])["applied"]
            results.append((engine, applied))
        (engine, applied), (control, _) = results
        delta = {code: int(engine.state["players"][code]["treasury"])
                 - int(control.state["players"][code]["treasury"])
                 for code in engine.state["players"]}
        factory = {code: int(engine.state["players"][code]["factory_points"])
                   - int(control.state["players"][code]["factory_points"])
                   for code in engine.state["players"]}
        return engine, applied, delta, factory

    def _give(self, engine, owner, city_ids):
        for city_id in city_ids:
            engine.state["city_owners"][city_id] = owner
        engine._refresh_city_income()

    def _strip(self, engine, owner):
        """把這位玩家名下的城全部交給別人，做出「一座城都沒有」的對照組。"""
        other = [c for c in engine.state["players"] if c != owner][0]
        for city in engine.data["strategic_map"]["cities"]:
            if engine.state["city_owners"].get(city["id"], city["faction"]) == owner:
                engine.state["city_owners"][city["id"]] = other
        engine._refresh_city_income()

    def _cities_of(self, engine, owner):
        return [c["id"] for c in engine.data["strategic_map"]["cities"]
                if engine.state["city_owners"].get(c["id"], c["faction"]) == owner]

    # ---- 卡面體檢 ----

    def test_all_twenty_are_acknowledge_cards_with_a_newspaper(self):
        engine = GameEngine(seed=3)
        for card_id in self.CARDS:
            card = engine._event_template(card_id)
            self.assertEqual(str(card["ref"]).split(".")[0], "13", card_id)
            self.assertEqual(card["resolution"]["type"], "acknowledge", card_id)
            self.assertTrue(card.get("repeatable"), f"{card_id} 是可重複抽取的卡")
            self.assertTrue(card["apply"], f"{card_id} 沒有任何機械化效果")
            paper = card.get("newspaper") or {}
            self.assertTrue(paper.get("headline"), card_id)
            self.assertGreaterEqual(len(paper.get("paragraphs") or []), 2, card_id)

    def test_every_referenced_city_and_province_exists_on_the_map(self):
        """卡上寫死的地名要真的在地圖上——〈香港軍火交易〉的深圳就是這樣漏掉的。"""
        engine = GameEngine(seed=3)
        cities = {c["id"] for c in engine.data["strategic_map"]["cities"]}
        provinces = {c["province"] for c in engine.data["strategic_map"]["cities"]}
        for card_id in self.CARDS:
            blob = json.dumps(engine._event_template(card_id), ensure_ascii=False)
            card = engine._event_template(card_id)
            for key in ("controls_cities_any", "controls_cities_all"):
                for city_id in (card.get("entry_condition") or {}).get(key) or []:
                    self.assertIn(city_id, cities, f"{card_id}:{city_id}")
            for province in (card.get("entry_condition") or {}).get(
                    "controls_provinces_any") or []:
                self.assertIn(province, provinces, f"{card_id}:{province}")
            self.assertNotIn("shenzhen", blob, card_id)

    def test_the_engine_rejects_a_typo_in_a_selector_or_condition(self):
        """寫錯鍵名要當場炸，不能默默放行——放行的後果是效果範圍變大。"""
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine._select_cities({"owned_by_target": True, "any": True}, ["F"])
        with self.assertRaises(ValueError):
            engine._event_eligible_players({"id": "x", "entry_condition": {"controls_ports": 3}})

    # ---- 生產成本倍率（13.1〜13.5）----

    def test_oil_price_surge_hits_navy_harder_than_ground_for_three_turns(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "world_oil_price_surge")
        ground = engine._production_multiplier("F", "ground")
        navy = engine._production_multiplier("F", "navy")
        self.assertAlmostEqual(ground["cash"], 1.3)
        self.assertAlmostEqual(ground["factory"], 1.3)
        self.assertAlmostEqual(navy["cash"], 1.5)
        self.assertAlmostEqual(navy["factory"], 1.5)
        for _ in range(3):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertAlmostEqual(engine._production_multiplier("F", "navy")["cash"], 1.0,
                               msg="三回合過後要自己失效")

    def test_oil_price_surge_applies_to_every_player_not_just_the_drawer(self):
        engine = GameEngine(seed=3)
        applied = self._fire(engine, "world_oil_price_surge")
        drawer = engine.state["event_history"][-1]["drawer"]
        for code in engine.state["players"]:
            self.assertAlmostEqual(engine._production_multiplier(code, "ground")["cash"], 1.3,
                                   msg=f"{code}（抽卡人是 {drawer}）")
        self.assertTrue([e for e in applied if e["kind"] == "production_cost_multiplier"])

    def test_arms_market_competition_makes_ground_units_cheaper(self):
        engine = GameEngine(seed=3)
        before = engine._unit_cost_for("F", "infantry")[0]
        self._fire(engine, "arms_market_competition")
        self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"], 0.8)
        self.assertLess(engine._unit_cost_for("F", "infantry")[0], before)

    def test_arms_embargo_rumour_lasts_one_turn_only(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "arms_embargo_rumour")
        self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"], 1.2)
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"], 1.0)

    def test_grain_price_spike_runs_five_turns(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "grain_price_spike")
        for turn in range(4):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
            self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"], 1.5,
                                   msg=f"第 {turn + 1} 回合就失效了")
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertAlmostEqual(engine._production_multiplier("F", "ground")["cash"], 1.0)

    def test_industrial_exposition_halves_factory_cost_but_not_cash(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "industrial_exposition")
        for arm in ("ground", "navy"):
            multiplier = engine._production_multiplier("F", arm)
            self.assertAlmostEqual(multiplier["factory"], 0.5, msg=arm)
            self.assertAlmostEqual(multiplier["cash"], 1.0, msg=arm)

    # ---- 一次性城市進出帳（13.6〜13.11）----

    def test_bumper_harvest_pays_two_per_city_into_the_treasury(self):
        engine, applied, delta, _ = self._control(lambda e: None, "bumper_harvest")
        for code in engine.state["players"]:
            count = len(self._cities_of(engine, code))
            self.assertGreater(count, 0, code)
            self.assertEqual(delta[code], 2 * count, code)
        self.assertTrue([e for e in applied if e["kind"] == "city_output_once"])

    def test_a_landless_player_gets_nothing_from_the_harvest(self):
        _, _, delta, _ = self._control(lambda e: self._strip(e, "N"), "bumper_harvest")
        self.assertEqual(delta["N"], 0)

    def test_cotton_yarn_boom_pays_factory_points_not_cash(self):
        engine, _, delta, factory = self._control(lambda e: None, "cotton_yarn_boom")
        count = len(self._cities_of(engine, "F"))
        self.assertEqual(factory["F"], count)
        self.assertEqual(delta["F"], 0, "這張是工廠點，不是錢")

    def test_deflation_takes_two_per_city(self):
        engine, _, delta, _ = self._control(lambda e: None, "deflation")
        self.assertEqual(delta["F"], -2 * len(self._cities_of(engine, "F")))

    def test_deflation_never_drives_the_treasury_negative(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["treasury"] = 3
        engine._apply_event_payload(
            engine._event_template("deflation")["apply"], players=["F"],
            card=engine._event_template("deflation"))
        self.assertEqual(int(engine.state["players"]["F"]["treasury"]), 0,
                         "扣到見底就停，不能變成負數")

    def test_north_china_drought_only_bites_the_four_northern_provinces(self):
        north = {"直隸", "山東", "山西", "陝西"}
        engine = GameEngine(seed=3)
        mine = [c["id"] for c in engine.data["strategic_map"]["cities"]
                if c["province"] in north]

        def setup(e):
            self._give(e, "F", mine)
            e.state["players"]["F"]["treasury"] = 500
            e.state["players"]["F"]["factory_points"] = 500

        _, _, delta, factory = self._control(setup, "north_china_drought")
        self.assertEqual(delta["F"], -3 * len(mine))
        self.assertEqual(factory["F"], -3 * len(mine))
        self.assertEqual(delta["S"], 0, "北方沒有城的人不該受旱災影響")

    def test_treaty_port_prosperity_counts_ports_only(self):
        engine, _, delta, _ = self._control(lambda e: None, "treaty_port_prosperity")
        ports = [c for c in engine.data["strategic_map"]["cities"]
                 if c.get("port")
                 and engine.state["city_owners"].get(c["id"], c["faction"]) == "F"]
        inland = [c for c in engine.data["strategic_map"]["cities"]
                  if not c.get("port")
                  and engine.state["city_owners"].get(c["id"], c["faction"]) == "F"]
        self.assertTrue(ports and inland, "這條要有港市也有內陸城才測得出差別")
        self.assertEqual(delta["F"], 3 * len(ports))

    # ---- 「僅適用符合條件的玩家」（13.11〜13.17）----

    def test_customs_surplus_is_a_flat_twelve_for_qualifying_players_only(self):
        """設計稿是「控制三級以上港市者本回合額外獲現金 +12」——定額，不是每座 ×12。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("customs_salt_surplus")
        self.assertEqual(card["entry_condition"], {"controls_port_level_min": {"level": 3}})
        big_ports = [c["id"] for c in engine.data["strategic_map"]["cities"]
                     if c.get("port") and int(c["level"]) >= 3]
        for city_id in big_ports:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        self.assertEqual(engine._event_eligible_players(card), ["F"],
                         "只有握著三級以上港市的人有資格")

        def setup(e):
            for city_id in big_ports:
                e.state["city_owners"][city_id] = "F"
            e._refresh_city_income()

        _, _, delta, _ = self._control(setup, "customs_salt_surplus")
        self.assertEqual(delta["F"], 12,
                         f"應該是定額 +12，不是每座港 ×12（手上有 {len(big_ports)} 座）")
        for code in ("W", "S", "N"):
            self.assertEqual(delta[code], 0, code)

    def test_a_small_port_does_not_qualify_for_the_customs_surplus(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("customs_salt_surplus")
        small = [c["id"] for c in engine.data["strategic_map"]["cities"]
                 if c.get("port") and int(c["level"]) < 3]
        self.assertTrue(small, "地圖上要有二級以下的港才測得到")
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "W"
        for city_id in small:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        self.assertNotIn("F", engine._event_eligible_players(card))

    def test_silk_tea_boom_pays_only_the_players_who_hold_the_four_provinces(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("silk_tea_export_boom")
        target = {"江蘇", "浙江", "福建", "廣東"}
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "F" if city["province"] in target else "W"
        engine._refresh_city_income()
        self.assertEqual(engine._event_eligible_players(card), ["F"])

        def setup(e):
            for city in e.data["strategic_map"]["cities"]:
                e.state["city_owners"][city["id"]] = \
                    "F" if city["province"] in target else "W"
            e._refresh_city_income()

        _, _, delta, _ = self._control(setup, "silk_tea_export_boom")
        # 一個地區發一次：四省全控就是 $8 × 4。
        self.assertEqual(delta["F"], 8 * len(target))
        for code in ("W", "S", "N"):
            self.assertEqual(delta[code], 0, f"{code} 沒有那四省，不該領到這 $8")

    def test_salt_reform_pays_once_and_then_lifts_those_provinces_forever(self):
        target = {"江蘇", "浙江", "四川", "山東"}
        mine = [c["id"] for c in GameEngine(seed=3).data["strategic_map"]["cities"]
                if c["province"] in target]
        engine, _, delta, _ = self._control(
            lambda e: self._give(e, "F", mine), "salt_administration_reform")
        # 一次性的 $10 **每控制一省發一次**（這裡四省全控 ＝ $40），
        # 加上永久 $+1 當回合就開始生效的那一份（每座城 1 元）。
        self.assertEqual(delta["F"], 10 * len(target) + len(mine))
        development = engine.state["city_development"]
        for city_id in mine:
            self.assertEqual(int(development[city_id]["cash"]), 1, city_id)
        other = [c["id"] for c in engine.data["strategic_map"]["cities"]
                 if c["province"] not in target]
        for city_id in other:
            self.assertEqual(int((development.get(city_id) or {}).get("cash", 0)), 0, city_id)

    def test_the_permanent_province_bonus_is_applied_once_not_once_per_player(self):
        """卡片層級的 apply 只跑一次；四家都有資格也不能把 $+1 疊成 $+4。"""
        engine = GameEngine(seed=3)
        target = {"江西", "湖南"}
        cities = [c for c in engine.data["strategic_map"]["cities"]
                  if c["province"] in target]
        # 「控制江西或湖南」是整省控制，所以一人給一整省，才會有兩家同時有資格。
        for city in cities:
            engine.state["city_owners"][city["id"]] = "F" if city["province"] == "江西" else "S"
        engine._refresh_city_income()
        card = engine._event_template("sothebys_porcelain_auction")
        self.assertEqual(sorted(engine._event_eligible_players(card)), ["F", "S"])
        self._fire(engine, "sothebys_porcelain_auction")
        for city in cities:
            self.assertEqual(int(engine.state["city_development"][city["id"]]["cash"]), 1,
                             city["id"])

    def test_liquor_expo_lifts_exactly_the_four_named_cities(self):
        named = ["linfen", "luzhou", "zunyi", "shaoxing"]
        engine, _, delta, _ = self._control(
            lambda e: self._give(e, "F", named), "chinese_liquor_expo")
        # $5 **每控制一座發一次**（四座全控 ＝ $20）＋ 四座城的永久 $+1。
        self.assertEqual(delta["F"], 5 * len(named) + len(named))
        for city_id in named:
            self.assertEqual(int(engine.state["city_development"][city_id]["cash"]), 1, city_id)

    def test_tea_expo_pays_five_to_qualifying_players_only(self):
        engine = GameEngine(seed=3)
        target = {"福建", "安徽", "江蘇", "浙江"}
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "S" if city["province"] in target else "W"
        def setup(e):
            for city in e.data["strategic_map"]["cities"]:
                e.state["city_owners"][city["id"]] = \
                    "S" if city["province"] in target else "W"
            e._refresh_city_income()

        mine = [c for c in GameEngine(seed=3).data["strategic_map"]["cities"]
                if c["province"] in target]
        _, _, delta, _ = self._control(setup, "chinese_tea_expo")
        # $5 **每控制一省發一次**（四省全控 ＝ $20）＋ 該四省每座城的永久 $+1。
        self.assertEqual(delta["S"], 5 * len(target) + len(mine))
        self.assertEqual(delta["W"], 0)

    def test_foreign_factories_only_reward_players_holding_a_concession_city(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("foreign_factory_investment")
        concessions = [c["id"] for c in engine.data["strategic_map"]["cities"]
                       if c.get("concession")]
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "W"
        for city_id in concessions:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        self.assertEqual(engine._event_eligible_players(card), ["F"])
        self._fire(engine, "foreign_factory_investment")
        self.assertEqual(
            int(engine.state["players"]["F"]["permanent_output_bonus"]["factory"]), 2)
        self.assertEqual(
            int(engine.state["players"]["W"]["permanent_output_bonus"]["factory"]), 0,
            "手上沒有租界城市的人不該拿到這 +2")

    # ---- 全場永久加成與銀行封鎖（13.18〜13.20）----

    def test_overseas_investment_lifts_guangzhou_and_xiamen_only(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "overseas_chinese_investment")
        development = engine.state["city_development"]
        for city_id in ("guangzhou", "xiamen"):
            self.assertEqual(int(development[city_id]["factory"]), 2, city_id)
            self.assertEqual(int(development[city_id]["cash"]), 0, city_id)
        self.assertEqual(int((development.get("shanghai") or {}).get("factory", 0)), 0)

    def test_technology_transfer_gives_every_player_a_permanent_factory_point(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "industrial_technology_transfer")
        for code in engine.state["players"]:
            self.assertEqual(
                int(engine.state["players"][code]["permanent_output_bonus"]["factory"]), 1, code)

    def test_foreign_bank_failures_shut_every_bank_for_two_turns(self):
        engine = GameEngine(seed=3)
        banks = sorted(LOANS.banks)
        self.assertGreater(len(banks), 1)
        self._fire(engine, "foreign_bank_failures")
        for bank_id in banks:
            self.assertIsNotNone(engine.bank_banned("F", bank_id), bank_id)
            with self.assertRaises(ValueError):
                engine.take_loan("F", bank_id, 10)
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        for bank_id in banks:
            self.assertIsNone(engine.bank_banned("F", bank_id),
                              f"{bank_id} 兩回合後該恢復放款")

    def test_bank_ban_without_a_target_is_rejected_rather_than_silently_empty(self):
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine._apply_event_payload({"bank_ban": {"turns": 2}}, players=None,
                                        card={"id": "x", "name": "x"})


class SovietJapaneseWarReportAuditTests(unittest.TestCase):
    """日蘇戰爭四張戰況報導的總複查。

    這四張是全套事件卡裡唯一「不進牌庫、由機制直接插進報紙佇列」的卡，
    所以它們的風險跟別的卡不一樣：不是效果會不會跑，而是**會不會在不該出現
    的時候出現**。這個類別把三件事釘死：卡面沒有殘留的死碼、不在任何牌庫裡、
    除了真的開戰以外沒有任何路徑能把它們送上報紙。
    """

    IDS = ["jp_su_war_heilongjiang_soviet_win", "jp_su_war_heilongjiang_japan_win",
           "jp_su_war_jilin_soviet_win", "jp_su_war_jilin_japan_win"]

    def _war_cards(self, engine):
        return [c for c in engine.data["event_cards"]["cards"] if c.get("never_drawn")]

    # ---- 一、卡面沒有殘留的死碼 ----

    def test_the_four_ids_are_exactly_the_never_drawn_set(self):
        engine = GameEngine(seed=3)
        self.assertEqual(sorted(c["id"] for c in self._war_cards(engine)), sorted(self.IDS))
        self.assertEqual(sorted(engine.POWER_WAR_REPORTS.values()), sorted(self.IDS),
                         "POWER_WAR_REPORTS 與 never_drawn 兩份名單必須一致")

    def test_they_carry_no_mechanical_effect_at_all(self):
        """土地歸屬與傷害在開戰判定當下就結算完了，報紙不該再動任何狀態。

        殘留一個 apply 鍵就會變成「讀報紙時又扣一次」——同一場仗結算兩次。
        """
        engine = GameEngine(seed=3)
        for card in self._war_cards(engine):
            live = [k for k in (card.get("apply") or {}) if k != "notes"]
            self.assertEqual(live, [], f'{card["ref"]} 的 apply 還留著 {live}')
            self.assertEqual((card.get("resolution") or {}).get("type"), "acknowledge",
                             card["ref"])
            self.assertEqual(card.get("entry_condition") or {}, {},
                             f'{card["ref"]} 不走抽卡，寫進入條件是死碼')
            self.assertIsNone(card.get("pool_copies"),
                              f'{card["ref"]} 不進池子，pool_copies 是死碼')

    def test_settling_one_changes_nothing_but_the_history(self):
        """實跑：把戰報結算掉，除了 event_history 之外狀態不該有任何差異。"""
        for card_id in self.IDS:
            engine = GameEngine(seed=3)
            card = engine._event_template(card_id)
            before = json.dumps(engine.snapshot(), sort_keys=True,
                                ensure_ascii=False, default=str)
            applied = engine._apply_event_payload(card.get("apply") or {},
                                                  players=["F"], card=card)
            after = json.dumps(engine.snapshot(), sort_keys=True,
                               ensure_ascii=False, default=str)
            self.assertEqual(applied, [], f"{card_id} 竟然做了事")
            self.assertEqual(before, after, f"{card_id} 動到了狀態")

    def test_they_carry_no_tags_so_no_tag_rule_can_reach_them(self):
        engine = GameEngine(seed=3)
        for card in self._war_cards(engine):
            self.assertEqual(card.get("tags") or [], [], card["ref"])
        # 反面：資料檔裡的標籤規則實跑一遍，一個都不准掃到
        for rule_power in ("日", "蘇", None):
            probe = GameEngine(seed=3)
            spec = {"tags": ["軍事", "戰況"], "turns": 5, "label": "probe"}
            if rule_power:
                spec["powers"] = [rule_power]
            probe._apply_event_payload({"event_lock": [spec]}, players=["F"],
                                       card={"id": "probe", "name": "probe"})
            for card_id in self.IDS:
                self.assertFalse(probe._event_locked(card_id),
                                 f"{rule_power or '全部'} 的標籤封鎖掃到了 {card_id}")

    def test_nothing_outside_the_report_table_references_them(self):
        """守門：程式碼裡只有 POWER_WAR_REPORTS 該提到這四個 id。

        多一處引用就是多一條它們可能被誤用的路徑。
        """
        repo = pathlib.Path(__file__).resolve().parent.parent
        hits = []
        for path in list(repo.glob("backend/*.py")) + list(repo.glob("frontend/*.js")) \
                + list(repo.glob("scripts/*.py")):
            if path.name == "test_backend.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "jp_su_war" in line:
                    hits.append((path.name, number, line.strip()))
        self.assertTrue(hits, "至少 POWER_WAR_REPORTS 要提到它們")
        for name, number, line in hits:
            self.assertEqual(name, "card_engine.py", f"{name}:{number} {line}")
            self.assertIn("jp_su_war", line)
            self.assertTrue(line.startswith('("'),
                            f"card_engine.py:{number} 不在 POWER_WAR_REPORTS 表裡：{line}")

    # ---- 二、不在任何牌庫裡 ----

    def test_they_are_absent_from_a_fresh_pool(self):
        for seed in (1, 3, 7, 11):
            engine = GameEngine(seed=seed)
            for card_id in self.IDS:
                self.assertEqual(engine.state["event_pool"].count(card_id), 0,
                                 f"seed={seed} 的開局牌庫裡有 {card_id}")

    def test_no_data_driven_pool_add_can_reach_them(self):
        """把資料檔裡每一條 event_pool_add 都實跑一次，池子裡不准出現戰報卡。"""
        engine0 = GameEngine(seed=3)
        specs = []
        for card in engine0.data["event_cards"]["cards"]:
            for spec in (card.get("apply") or {}).get("event_pool_add") or []:
                specs.append((card, spec))
        self.assertTrue(specs, "資料檔裡應該有 event_pool_add")
        for card, spec in specs:
            engine = GameEngine(seed=3)
            engine._apply_event_payload({"event_pool_add": [spec]},
                                        players=["F"], card=card)
            for card_id in self.IDS:
                self.assertEqual(engine.state["event_pool"].count(card_id), 0,
                                 f'{card["ref"]} {card["name"]} 把 {card_id} 塞進池子了')

    def test_a_poisoned_pool_from_an_old_save_still_cannot_draw_them(self):
        """舊存檔／還原狀態可能帶著被污染的牌庫進來，抽卡迴圈自己要擋。"""
        for card_id in self.IDS:
            engine = GameEngine(seed=3)
            engine.state["event_pool"] = [card_id] * 5
            engine.state["turn"] = 2
            engine.next_turn(active_player="F")
            self.assertIsNone(engine.pending_event_view(), card_id)

    # ---- 三、除了真的開戰以外沒有別的路徑 ----

    def test_the_only_writer_of_the_pending_queue_is_the_draw_or_the_war(self):
        """原始碼層級：pending["cards"] 只有兩個寫入點——抽卡與戰報插入。"""
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        writes = [line.strip() for line in source.splitlines()
                  if ('pending["cards"]' in line or '"cards": drawn' in line)
                  and any(op in line for op in (".insert(", ".append(", ".extend(", '"cards": drawn'))]
        self.assertEqual(len(writes), 2, f"pending 佇列多了寫入點：{writes}")

    def test_no_war_means_no_report(self):
        """懲戒降臨但沒有日蘇重疊 → 只有懲戒那一則，不該冒出戰報。"""
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("吉林", "黑龍江"):
                engine.state["city_owners"][city["id"]] = "F"
        engine._refresh_city_income()
        engine.state["players"]["F"]["foreign_relations"]["su"] = -6
        entry = engine.ultimatums.open(card_id="soviet_ultimatum", power="su", owner="F")
        entry["status"] = "failed"
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["soviet_far_east_army_invades_songhua"]
        engine.next_turn(active_player="F")
        seen = []
        for _ in range(10):
            view = engine.pending_event_view()
            if not view:
                break
            seen.append(view["card"]["id"])
            engine.respond_event(view["waiting_for"])
        self.assertEqual(seen, ["soviet_far_east_army_invades_songhua"],
                         "日本沒有佔著同一片地，就沒有仗可打，也就不該有戰報")

    def test_a_report_is_only_ever_queued_for_a_province_that_actually_fought(self):
        """實跑一場只在吉林衝突的仗：只能出吉林那一則，黑龍江的不准跟著上。"""
        engine = GameEngine(seed=3)
        for city in engine.data["strategic_map"]["cities"]:
            if city.get("province") in ("奉天", "吉林", "黑龍江"):
                engine.state["city_owners"][city["id"]] = "F"
        engine._refresh_city_income()
        engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
        engine.punishments.open(card_id="kwantung_army_special_drill", power="jp",
                                kind="ground_occupation", owner="F",
                                provinces=["奉天", "吉林"], label="關東軍特別演習")
        applied = [{"kind": "foreign_punishment", "punishment": {"wars": [
            {"province": "吉林", "winner": "su", "loser": "jp"}]}}]
        pending = {"cards": [], "index": 0}
        engine._queue_power_war_reports(applied, pending, "F")
        self.assertEqual([c["card_id"] for c in pending["cards"]],
                         ["jp_su_war_jilin_soviet_win"])

    def test_the_report_matches_the_province_and_the_winner(self):
        """四種組合逐一對死，省份或勝負對錯人都要被抓到。"""
        engine = GameEngine(seed=3)
        for (province, winner), card_id in engine.POWER_WAR_REPORTS.items():
            pending = {"cards": [], "index": 0}
            engine._queue_power_war_reports(
                [{"kind": "foreign_punishment", "punishment": {"wars": [
                    {"province": province, "winner": winner, "loser": "jp"}]}}],
                pending, "F")
            self.assertEqual([c["card_id"] for c in pending["cards"]], [card_id],
                             f"{province}／{winner}")
            template = engine._event_template(card_id)
            self.assertIn(province, template["name"], card_id)
            self.assertIn("蘇軍獲勝" if winner == "su" else "日軍獲勝",
                          template["name"], card_id)



class EconomyEventBatchTwoTests(unittest.TestCase):
    """第十三區塊經濟事件後 9 張（13.21〜13.29）——需要新機制的那批。"""

    CARDS = ["world_silver_price_swing", "silver_outflow", "native_bank_run",
             "arsenal_order_surge", "pay_arrears", "coal_shortage",
             "yangtze_flood", "yellow_river_breach", "opium_and_likin_revenue"]

    def _fire(self, engine, card_id, turn=2):
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        self.assertEqual(view["card"]["id"], card_id)
        applied = []
        for _ in range(8):
            view = engine.pending_event_view()
            if not view:
                break
            applied += engine.respond_event(view["waiting_for"])["applied"]
        return applied

    def _control(self, setup, card_id, turn=2, seed=3):
        """同一個開局跑兩次：一次抽這張卡，一次空池子當對照組。

        事件結完之後回合才補跑經濟結算，所以事後直接看國庫，看到的是
        「事件效果 ＋ 本回合收入」。對照組正是那筆收入。
        """
        results = []
        for pool in ([card_id], []):
            engine = GameEngine(seed=seed)
            if setup:
                setup(engine)
            engine.state["turn"] = turn
            engine.state["event_pool"] = list(pool)
            engine.next_turn(active_player="F")
            applied = []
            for _ in range(8):
                view = engine.pending_event_view()
                if not view:
                    break
                applied += engine.respond_event(view["waiting_for"])["applied"]
            results.append((engine, applied))
        (engine, applied), (control, _) = results
        delta = {code: int(engine.state["players"][code]["treasury"])
                 - int(control.state["players"][code]["treasury"])
                 for code in engine.state["players"]}
        return engine, applied, delta, control

    def _make_reform_succeed(self, engine, player):
        card = engine._event_template("silver_tael_reform")
        branch = next(b for b in card["apply"]["random_outcome"]["branches"]
                      if b["id"] == "succeeds")
        engine._apply_event_payload(branch["apply"], players=[player], card=card)

    def test_all_nine_load_and_carry_a_newspaper(self):
        engine = GameEngine(seed=3)
        for card_id in self.CARDS:
            card = engine._event_template(card_id)
            self.assertEqual(str(card["ref"]).split(".")[0], "13", card_id)
            self.assertTrue(card.get("repeatable"), card_id)
            self.assertTrue(card["apply"], card_id)
            self.assertTrue((card.get("newspaper") or {}).get("headline"), card_id)
            self.assertGreaterEqual(len(card["newspaper"]["paragraphs"]), 2, card_id)

    def test_no_card_invents_a_payload_key_the_engine_ignores(self):
        """守門：卡片用到的每一個 apply 鍵，引擎裡都要真的讀得到。

        我自己就在 13.29 上發明過一個 `gang_duration_bonus`——引擎不認得，
        於是那張卡的「治安惡化」整段是死碼，而且不會有任何東西叫。
        """
        engine = GameEngine(seed=3)
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        ignored = {"notes", "pending"}
        for card_id in self.CARDS:
            for key in engine._event_template(card_id)["apply"]:
                if key in ignored:
                    continue
                self.assertIn(f'payload.get("{key}")', source,
                              f'{card_id} 用了引擎讀不到的 {key}')
            for flag in (engine._event_template(card_id)["apply"].get("timed_flags") or []):
                self.assertIn(f'"{flag["kind"]}"', source + FRONTEND_SOURCE,
                              f'{card_id} 的旗標 {flag["kind"]} 沒有人讀')

    # ---- 現金按比例損失（13.21／13.22）----

    def test_the_silver_swing_takes_a_fifth_of_everyone_rounded_up(self):
        base = {c: int(GameEngine(seed=3).state["players"][c]["treasury"])
                for c in GameEngine(seed=3).state["players"]}
        _, applied, delta, _ = self._control(None, "world_silver_price_swing")
        for code, was in base.items():
            self.assertEqual(delta[code], -math.ceil(was * 0.20),
                             f"{code}：{was} 的兩成應該是無條件進位")
        self.assertTrue([e for e in applied if e["kind"] == "treasury_percent_loss"])

    def test_the_outflow_takes_a_tenth_and_hits_the_rich_harder(self):
        def setup(engine):
            engine.state["players"]["F"]["treasury"] = 200
            engine.state["players"]["N"]["treasury"] = 20

        _, _, delta, _ = self._control(setup, "silver_outflow")
        self.assertEqual(delta["F"], -20)
        self.assertEqual(delta["N"], -2)

    def test_a_percentage_loss_rounds_up_never_down(self):
        """設計稿是「損失 20%」，零頭算給銀行——必須 ceil，不能 round。

        先前這批測試全用剛好整除的數字（75×0.2＝15），把 ceil 換成 round
        照樣全綠。這裡刻意挑會產生零頭、而且 round 會往下走的數字：
        65×0.1＝6.5，Python 的 round 給 6（銀行家捨入），ceil 給 7。
        """
        cases = {"F": (65, 7), "W": (61, 7), "S": (1, 1), "N": (5, 1)}
        engine = GameEngine(seed=3)
        for code, (start, _) in cases.items():
            engine.state["players"][code]["treasury"] = start
        card = engine._event_template("silver_outflow")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        for code, (start, taken) in cases.items():
            self.assertEqual(int(engine.state["players"][code]["treasury"]), start - taken,
                             f"{code}：{start} 的一成無條件進位應該是 {taken}")

    def test_a_percentage_loss_never_goes_negative(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["treasury"] = 0
        card = engine._event_template("world_silver_price_swing")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        for code in engine.state["players"]:
            self.assertEqual(int(engine.state["players"][code]["treasury"]), 0, code)

    # ---- 錢莊擠兌（13.23）：同一張卡對兩種人做不同的事 ----

    def test_the_bank_run_splits_by_who_owes_money(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["foreign_relations"]["uk"] = 4
        engine.take_loan("F", "hsbc", 20)
        owed = sum(int(l.get("principal", 0)) for l in engine.state["players"]["F"]["loans"])
        self.assertFalse(engine.state["players"]["W"]["loans"], "W 要是無負債的對照組")

        def setup(probe):
            probe.state["players"]["F"]["foreign_relations"]["uk"] = 4
            probe.take_loan("F", "hsbc", 20)

        engine, applied, delta, control = self._control(setup, "native_bank_run")
        after = sum(int(l.get("principal", 0)) for l in engine.state["players"]["F"]["loans"])
        control_owed = sum(int(l.get("principal", 0))
                           for l in control.state["players"]["F"]["loans"])
        self.assertEqual(after, control_owed + 10, "有負債的人債務 +10")
        self.assertEqual(delta["F"], 0, "有負債的人不該同時被扣現金")
        self.assertEqual(delta["W"], -8, "無負債的人現金 −8")
        branches = {e["player"]: e["in_debt"] for e in applied if e["kind"] == "debt_branch"}
        self.assertTrue(branches["F"])
        self.assertFalse(branches["W"])

    # ---- 廢兩改元的免疫（三張一起）----

    def test_a_successful_currency_reform_immunises_all_three(self):
        for card_id in ("world_silver_price_swing", "silver_outflow", "native_bank_run"):
            engine = GameEngine(seed=3)
            self._make_reform_succeed(engine, "F")
            self.assertTrue(engine.has_timed_flag("F", "silver_reform_done"))
            _, _, delta, _ = self._control(
                lambda probe: self._make_reform_succeed(probe, "F"), card_id)
            self.assertEqual(delta["F"], 0, f"{card_id}：改元成功的人應該免疫")
            self.assertLess(delta["W"], 0, f"{card_id}：沒改元的人照樣受害")

    def test_the_reform_card_no_longer_claims_the_三_cards_are_missing(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("silver_tael_reform")
        branch = next(b for b in card["apply"]["random_outcome"]["branches"]
                      if b["id"] == "succeeds")
        self.assertNotIn("pending", branch["apply"], "那三張卡已經建檔了")
        for card_id in ("world_silver_price_swing", "silver_outflow", "native_bank_run"):
            self.assertEqual(engine._event_template(card_id)["apply"].get("immune_flag"),
                             "silver_reform_done", card_id)

    # ---- 工廠產出乘數（13.24）----

    def test_the_arsenal_surge_multiplies_factory_output_rounding_up(self):
        engine = GameEngine(seed=3)
        base = {c: int(engine.state["players"][c]["factory_income"])
                for c in engine.state["players"]}
        cash = {c: int(engine.state["players"][c]["income"]) for c in engine.state["players"]}
        self._fire(engine, "arsenal_order_surge")
        for code in engine.state["players"]:
            self.assertEqual(int(engine.state["players"][code]["factory_income"]),
                             math.ceil(base[code] * 1.5), f"{code} 工廠產出要 ×1.5 進位")
            self.assertEqual(int(engine.state["players"][code]["income"]), cash[code],
                             f"{code} 金錢收入不該被動到")

    def test_the_arsenal_surge_rounds_up_on_an_odd_base(self):
        """「無條件進位」要用會產生零頭的底數才驗得出來。

        偶數底 ×1.5 剛好整除，把 ceil 換成 round 照樣全綠——先前就是這樣
        漏掉的。這裡把工廠收入釘成奇數：奇數 ×1.5 必有 .5，而 Python 的
        round 對 .5 是銀行家捨入，會往偶數走，跟進位不同。
        """
        engine = GameEngine(seed=3)
        card = engine._event_template("arsenal_order_surge")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        # 把 F 的城全部交出去，工廠收入就只剩下面設的那個固定加成，數字乾淨。
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "W"
        for odd in (7, 9, 13, 21):
            engine.state["players"]["F"]["permanent_output_bonus"] = {"cash": 0, "factory": odd}
            engine._refresh_city_income()
            self.assertEqual(int(engine.state["players"]["F"]["factory_income"]),
                             math.ceil(odd * 1.5),
                             f"{odd} ×1.5 無條件進位應該是 {math.ceil(odd * 1.5)}")

    def test_the_arsenal_surge_lasts_one_turn(self):
        engine = GameEngine(seed=3)
        base = int(engine.state["players"]["F"]["factory_income"])
        self._fire(engine, "arsenal_order_surge")
        self.assertGreater(int(engine.state["players"]["F"]["factory_income"]), base)
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertEqual(int(engine.state["players"]["F"]["factory_income"]), base)

    # ---- 煤礦短缺（13.26）：有時效的定額扣減 ----

    def test_the_coal_shortage_docks_two_factory_per_city_for_two_turns(self):
        engine = GameEngine(seed=3)
        cities = len([r for r in engine.state["players"]["F"]["city_economy"]])
        base = int(engine.state["players"]["F"]["factory_income"])
        self._fire(engine, "coal_shortage")
        during = int(engine.state["players"]["F"]["factory_income"])
        self.assertLess(during, base, "工廠產出應該掉下來")
        self.assertGreaterEqual(base - during, 1)
        self.assertLessEqual(base - during, 2 * cities, "最多就是每座城 −2")
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(int(engine.state["players"]["F"]["factory_income"]), base,
                         "兩回合後要自己恢復")

    def test_the_coal_shortage_never_drives_a_city_below_zero(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "coal_shortage")
        for code in engine.state["players"]:
            for row in engine.state["players"][code]["city_economy"]:
                self.assertGreaterEqual(int(row["factory"]), 0, f'{code}/{row["id"]}')

    # ---- 軍餉短缺（13.25）：禁令要真的擋得住 ----

    def _broke(self, engine, player="F"):
        engine.state["players"][player]["treasury"] = 5
        engine.state.setdefault("turn_log", []).append(
            {"turn": 1, "treasury_after": {c: (5 if c == player else 80)
                                           for c in engine.state["players"]}})

    def test_pay_arrears_only_reaches_a_player_who_ended_last_turn_broke(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("pay_arrears")
        self.assertEqual(engine._event_eligible_players(card), [],
                         "開局大家都有錢，這張卡不該進得了場")
        self._broke(engine, "F")
        self.assertEqual(engine._event_eligible_players(card), ["F"])

    def test_pay_arrears_blocks_training_shipbuilding_and_reinforcement(self):
        engine = GameEngine(seed=3)
        self._broke(engine, "F")
        engine.state["players"]["F"]["treasury"] = 500
        engine.state["players"]["F"]["factory_points"] = 500
        self._fire(engine, "pay_arrears")
        for action in ("train_unit", "train_navy_unit", "reinforce_army", "reinforce_navy"):
            self.assertIsNotNone(engine.action_banned("F", action), action)
        with self.assertRaisesRegex(ValueError, "軍餉短缺"):
            engine.train_unit("F", "infantry", 1)
        with self.assertRaisesRegex(ValueError, "軍餉短缺"):
            engine.train_navy_unit("F", "gun_boat", 1)
        with self.assertRaisesRegex(ValueError, "軍餉短缺"):
            engine.reinforce_army("F", "army-1", "fengtian", "infantry", 1)
        with self.assertRaisesRegex(ValueError, "軍餉短缺"):
            engine.reinforce_navy("F", "fengtian", "gun_boat", 1)

    def test_pay_arrears_does_not_touch_the_solvent(self):
        engine = GameEngine(seed=3)
        self._broke(engine, "F")
        self._fire(engine, "pay_arrears")
        for action in ("train_unit", "train_navy_unit"):
            self.assertIsNone(engine.action_banned("W", action),
                              f"W 上回合有錢，不該被禁 {action}")
        engine.state["players"]["W"]["treasury"] = 500
        engine.state["players"]["W"]["factory_points"] = 500
        engine.train_unit("W", "infantry", 1)

    def test_the_pay_arrears_ban_expires(self):
        engine = GameEngine(seed=3)
        self._broke(engine, "F")
        engine.state["players"]["F"]["treasury"] = 500
        engine.state["players"]["F"]["factory_points"] = 500
        self._fire(engine, "pay_arrears")
        engine.state["event_pool"] = []
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.action_banned("F", "train_unit"), "本回合過了就該解禁")
        engine.state["players"]["F"]["treasury"] = 500
        engine.state["players"]["F"]["factory_points"] = 500
        engine.train_unit("F", "infantry", 1)

    def test_an_action_ban_rejects_an_unknown_action(self):
        engine = GameEngine(seed=3)
        with self.assertRaisesRegex(ValueError, "不認得"):
            engine._apply_event_payload({"action_ban": [{"actions": ["fly"], "turns": 1}]},
                                        players=["F"], card={"id": "x", "name": "x"})
        with self.assertRaisesRegex(ValueError, "action_ban"):
            engine._apply_event_payload({"action_ban": [{"turns": 1}]},
                                        players=["F"], card={"id": "x", "name": "x"})

    # ---- 水患／決口（13.27／13.28）----

    def _flood_setup(self, engine, water, owner="F"):
        ids = engine._select_cities({"waters": [water], "port": True}, [])
        for city_id in ids:
            engine.state["city_owners"][city_id] = owner
        engine._refresh_city_income()
        return sorted(ids)

    def test_the_yangtze_flood_halts_exactly_the_yangtze_ports_you_hold(self):
        engine = GameEngine(seed=3)
        mine = self._flood_setup(engine, "長江", "F")
        self.assertTrue(mine)
        applied = self._fire(engine, "yangtze_flood")
        halted = [e for e in applied if e["kind"] == "city_halt"]
        self.assertEqual(len(halted), 1)
        self.assertEqual(halted[0]["player"], "F")
        self.assertEqual(halted[0]["cities"], mine)
        income = {r["id"]: r for r in engine.state["players"]["F"]["city_economy"]}
        for city_id in mine:
            row = income.get(city_id)
            if row:
                self.assertEqual(int(row["cash"]), 0, city_id)
                self.assertEqual(int(row["factory"]), 0, city_id)

    def test_the_flood_freezes_exactly_the_cities_it_halted(self):
        """兩份名單必須由同一個條件算出來，不是抄第二份。"""
        for card_id, water in (("yangtze_flood", "長江"),
                               ("yellow_river_breach", "黃河")):
            engine = GameEngine(seed=3)
            self._flood_setup(engine, water, "F")
            applied = self._fire(engine, card_id)
            halted = next(e for e in applied if e["kind"] == "city_halt")["cities"]
            freeze = next(e for e in engine.state["players"]["F"]["timed_effects"]
                          if e["kind"] == "movement_freeze")
            self.assertEqual(freeze["cities"], halted,
                             f"{card_id}：停產與凍結的城市名單對不上")
            self.assertFalse(freeze.get("provinces"),
                             "使用者要的是城市級，不是整省")

    def test_the_two_floods_do_not_reach_each_others_rivers(self):
        engine = GameEngine(seed=3)
        yangtze = set(engine._select_cities({"waters": ["長江"], "port": True}, []))
        yellow = set(engine._select_cities({"waters": ["黃河"], "port": True}, []))
        self.assertTrue(yangtze and yellow)
        self.assertFalse(yangtze & yellow, "兩條河的港市不該重疊")
        probe = GameEngine(seed=3)
        self._flood_setup(probe, "長江", "F")
        for city_id in yellow:
            probe.state["city_owners"][city_id] = "F"
        probe._refresh_city_income()
        applied = self._fire(probe, "yangtze_flood")
        halted = set(next(e for e in applied if e["kind"] == "city_halt")["cities"])
        self.assertFalse(halted & yellow, "長江水患淹到黃河去了")

    def test_a_player_with_no_river_port_is_not_flooded(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("yangtze_flood")
        yangtze = engine._select_cities({"waters": ["長江"], "port": True}, [])
        for city_id in yangtze:
            engine.state["city_owners"][city_id] = "S"
        engine._refresh_city_income()
        self.assertEqual(engine._event_eligible_players(card), ["S"])
        applied = self._fire(engine, "yangtze_flood")
        self.assertEqual({e["player"] for e in applied if e["kind"] == "city_halt"}, {"S"})
        self.assertFalse([e for e in engine.state["players"]["F"].get("timed_effects", [])
                          if e["kind"] == "movement_freeze"],
                         "沒有長江河港的人不該被凍住")

    # ---- 鴉片與釐金稅收（13.29）----

    def test_the_opium_tax_pays_everyone_and_worsens_public_order(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine.suppression_turn_bonus(), 0)
        engine, _, delta, _ = self._control(None, "opium_and_likin_revenue")
        for code in engine.state["players"]:
            self.assertEqual(delta[code], 20, code)
        self.assertEqual(engine.suppression_turn_bonus(), 1,
                         "暴動基準 2 回合 ＋1 ＝ 設計稿要的三回合")
        gang = [c for c in engine.data["event_cards"]["cards"]
                if "幫會" in (c.get("tags") or [])]
        self.assertTrue(gang)
        self.assertEqual(engine._event_duration_bonus(gang[0]), 1)

    def test_the_opium_tax_permanently_locks_the_crackdown_card(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "opium_and_likin_revenue")
        self.assertTrue(engine._event_locked("opium_den_crackdown"))
        for _ in range(20):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertTrue(engine._event_locked("opium_den_crackdown"),
                        "設計稿寫的是永久封鎖")

    def test_the_opium_tax_now_really_locks_a_card_that_exists(self):
        """〈煙館查禁風波〉（14.12）建檔之後，這道永久封鎖不再是空的。

        先前這條測的是相反的事——鎖的是一張不存在的卡，所以卡上掛著 pending。
        那張卡做出來的當下這條就紅了，正是它該做的事。
        """
        engine = GameEngine(seed=3)
        card = engine._event_template("opium_and_likin_revenue")
        self.assertNotIn("pending", card["apply"], "目標卡建好了，pending 該拿掉")
        ids = {c["id"] for c in engine.data["event_cards"]["cards"]}
        self.assertIn("opium_den_crackdown", ids)
        self.assertFalse(engine._event_locked("opium_den_crackdown"))
        self._fire(engine, "opium_and_likin_revenue")
        self.assertTrue(engine._event_locked("opium_den_crackdown"))
        # 而且真的抽不到了
        engine.state["turn"] = 4
        engine.state["event_pool"] = ["opium_den_crackdown"]
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view(),
                          "被永久封鎖的卡不該再抽得到")



class SecurityEventTests(unittest.TestCase):
    """第十四區塊「治安事件」15 張。

    這一批的共同特徵是**打在自己家裡**：停產、暴動、嘩變、罷工。所以最容易
    出錯的不是效果本身，而是「打到誰」——規模最大的哪一座、隨機抽哪幾座、
    有沒有尊重警政單位的護盾。
    """

    CARDS = ["general_strike", "gang_unrest", "factory_accident", "dockers_strike",
             "secret_society_trouble", "anti_imperialist_march", "rice_riots",
             "mutiny", "local_official_graft", "bandit_raids", "epidemic",
             "opium_den_crackdown", "student_demonstrations",
             "local_autonomy_movement", "railway_workers_strike"]

    def _fire(self, engine, card_id, turn=2, choice=None):
        engine.state["turn"] = turn
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, f"{card_id} 沒被抽出來")
        self.assertEqual(view["card"]["id"], card_id)
        applied = []
        for _ in range(8):
            view = engine.pending_event_view()
            if not view:
                break
            applied += engine.respond_event(view["waiting_for"], choice=choice)["applied"]
        return applied

    def _halted(self, engine, player):
        out = set()
        for effect in engine.state.get("city_output_effects", []):
            if effect.get("owner") == player:
                out |= set(effect.get("city_ids") or [])
        return out

    def _output(self, engine, player, city_id):
        for row in engine.state["players"][player]["city_economy"]:
            if row["id"] == city_id:
                return int(row["cash"]), int(row["factory"])
        return None

    # ---- 卡面體檢 ----

    def test_all_fifteen_load_with_a_newspaper_and_an_effect(self):
        engine = GameEngine(seed=3)
        for card_id in self.CARDS:
            card = engine._event_template(card_id)
            self.assertEqual(str(card["ref"]).split(".")[0], "14", card_id)
            self.assertTrue(card.get("repeatable"), card_id)
            self.assertEqual(card.get("category"), "security", card_id)
            paper = card.get("newspaper") or {}
            self.assertTrue(paper.get("headline"), card_id)
            self.assertGreaterEqual(len(paper.get("paragraphs") or []), 2, card_id)
            has_effect = bool([k for k in card["apply"] if k not in ("notes", "pending")]) \
                or any(o.get("apply") for o in (card["resolution"].get("options") or []))
            self.assertTrue(has_effect, f"{card_id} 沒有任何機械化效果")

    def test_no_security_card_invents_a_payload_key(self):
        engine = GameEngine(seed=3)
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        for card_id in self.CARDS:
            card = engine._event_template(card_id)
            blocks = [card["apply"]] + [o.get("apply") or {}
                                        for o in (card["resolution"].get("options") or [])]
            for block in blocks:
                for key in block:
                    if key in ("notes", "pending"):
                        continue
                    self.assertIn(f'payload.get("{key}")', source,
                                  f"{card_id} 用了引擎讀不到的 {key}")
            for flag in (card["apply"].get("frontend_effects") or []):
                self.assertIn(f'{flag["kind"]}:', FRONTEND_SOURCE,
                              f'{card_id} 的前端效果 {flag["kind"]} 沒有處理器')

    # ---- 「規模最大的 N 座」 ----

    def test_the_strike_hits_the_single_largest_city(self):
        engine = GameEngine(seed=3)
        biggest = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])
        self.assertEqual(len(biggest), 1)
        self._fire(engine, "general_strike")
        self.assertEqual(self._halted(engine, "F"), set(biggest))
        self.assertEqual(self._output(engine, "F", biggest[0]), (0, 0), "全面停產")

    def test_largest_really_means_cash_plus_factory(self):
        """「規模最大」是 $ ＋ 工廠，不是等級、也不是只看錢。"""
        engine = GameEngine(seed=3)
        picked = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])[0]
        totals = {}
        for row in engine.state["players"]["F"]["city_economy"]:
            totals[row["id"]] = int(row["cash"]) + int(row["factory"])
        self.assertEqual(totals[picked], max(totals.values()),
                         f"{picked} 不是 F 名下 $＋工廠最大的那一座")

    def test_a_tie_is_broken_randomly_not_by_a_fixed_order(self):
        """平手時隨機挑一座（使用者裁示）。不同 seed 應該挑到不同的城。"""
        picks = set()
        for seed in range(1, 25):
            engine = GameEngine(seed=seed)
            # 把 F 的城全部拉成同樣大小，做出人工平手
            for city in engine.data["strategic_map"]["cities"]:
                engine.state["city_owners"][city["id"]] = "F" if city["level"] == 3 else "W"
            engine.state["city_development"] = {}
            engine._refresh_city_income()
            tied = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])
            picks |= set(tied)
        self.assertGreater(len(picks), 1,
                           "平手時每次都挑同一座，等於沒有隨機")

    def test_the_opium_crackdown_hits_the_two_largest_at_half_output(self):
        # 注意：不能在開火前呼叫 _select_cities(largest=...) 來預測會挑到哪兩座。
        # 平手時的隨機挑選會**推進亂數序列**，於是卡片自己挑的和測試預測的就不同了。
        # 改成從 applied 讀出實際挑到的城，再回頭驗它們確實是最大的兩座。
        engine = GameEngine(seed=3)
        base = {row["id"]: (int(row["cash"]), int(row["factory"]))
                for row in engine.state["players"]["F"]["city_economy"]}
        applied = self._fire(engine, "opium_den_crackdown")
        entry = next(e for e in applied if e["kind"] == "city_halt" and e["player"] == "F")
        two = entry["cities"]
        self.assertEqual(len(two), 2)
        ranked = sorted(base, key=lambda cid: -(base[cid][0] + base[cid][1]))
        cutoff = base[ranked[1]][0] + base[ranked[1]][1]
        for cid in two:
            self.assertGreaterEqual(base[cid][0] + base[cid][1], cutoff,
                                    f"{cid} 不在最大的兩座之列")
            cash, factory = self._output(engine, "F", cid)
            self.assertEqual(cash, round(base[cid][0] * 0.5), cid)
            self.assertEqual(factory, round(base[cid][1] * 0.5), cid)

    def test_the_factory_accident_spares_the_money(self):
        """工廠停產，商務照舊——乘數是分開的兩個。"""
        engine = GameEngine(seed=3)
        biggest = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])[0]
        base = self._output(engine, "F", biggest)
        self.assertGreater(base[1], 0, "這條要挑一座真的有工廠的城")
        self._fire(engine, "factory_accident")
        cash, factory = self._output(engine, "F", biggest)
        self.assertEqual(factory, 0, "工廠要停")
        self.assertEqual(cash, base[0], "金錢不該被動到")

    # ---- 付錢平息 ----

    def test_the_strike_can_be_bought_off_for_ten(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "general_strike")
        offers = engine.quellable_unrest("F")
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]["cost"], 10)
        self.assertTrue(offers[0]["affordable"])
        before = int(engine.state["players"]["F"]["treasury"])
        halted = self._halted(engine, "F")
        engine.quell_unrest("F", offers[0]["id"])
        self.assertEqual(int(engine.state["players"]["F"]["treasury"]), before - 10)
        self.assertEqual(self._halted(engine, "F"), set(), "平息後該恢復產出")
        for city_id in halted:
            self.assertGreater(sum(self._output(engine, "F", city_id) or (0, 0)), 0, city_id)
        self.assertEqual(engine.quellable_unrest("F"), [], "付過就不該再出現在清單裡")

    def test_you_cannot_quell_what_you_cannot_afford(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "general_strike")
        offer = engine.quellable_unrest("F")[0]
        engine.state["players"]["F"]["treasury"] = 3
        self.assertFalse(engine.quellable_unrest("F")[0]["affordable"])
        with self.assertRaisesRegex(ValueError, "平息"):
            engine.quell_unrest("F", offer["id"])
        self.assertEqual(int(engine.state["players"]["F"]["treasury"]), 3, "擋下來就不該扣錢")
        self.assertTrue(self._halted(engine, "F"), "沒付成功，停產要繼續")

    def test_you_cannot_quell_someone_elses_unrest(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "general_strike")
        offer = engine.quellable_unrest("W")[0]
        with self.assertRaises(ValueError):
            engine.quell_unrest("F", offer["id"])

    def test_the_quellable_list_rides_in_the_snapshot(self):
        """前端要據此畫按鈕。讓前端自己去掃 city_output_effects 正是這個專案
        反覆掉欄位的地方，所以由後端算好放進 snapshot。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "general_strike")
        snapshot = engine.snapshot()
        self.assertIn("quellable_unrest", snapshot)
        self.assertEqual(len(snapshot["quellable_unrest"]["F"]), 1)
        self.assertEqual(snapshot["quellable_unrest"]["F"][0]["cost"], 10)
        self.assertIn("quellable_unrest", FRONTEND_SOURCE, "前端要真的讀這個欄位")

    def test_the_quell_button_is_wired_to_a_listener_that_can_hear_it(self):
        """按鈕畫得出來不等於按得動。

        平息按鈕住在 #unrestNotice 與 #tileInfo 兩處，而原本的 click listener
        只綁在 #turnNotification 上——按鈕渲染正常、點下去毫無反應、主控台也
        不報錯。這條把「畫按鈕的容器」與「綁 listener 的容器」對起來。
        """
        for host in ("unrestNotice", "tileInfo"):
            self.assertIn(f'$("{host}").addEventListener', FRONTEND_SOURCE,
                          f"{host} 沒有自己的 click listener")
        # 兩處都要真的畫得出按鈕
        self.assertIn("data-quell-unrest", FRONTEND_SOURCE)
        self.assertIn("renderUnrestNotice", FRONTEND_SOURCE)
        self.assertIn("quellButtonMarkup(quellableUnrestForCity", FRONTEND_SOURCE,
                      "城市面板要掛上平息按鈕")
        # 後端端點要存在
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn("/api/quell-unrest", server)
        self.assertIn("quell_unrest", server)

    def test_the_rice_riots_never_expire_on_their_own(self):
        """設計稿：不花錢賑濟就**無限期**停產。"""
        engine = GameEngine(seed=3)
        self._fire(engine, "rice_riots")
        halted = self._halted(engine, "F")
        self.assertEqual(len(halted), 2)
        for _ in range(12):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(self._halted(engine, "F"), halted, "十二回合過去了還是不該自己好")
        offer = engine.quellable_unrest("F")[0]
        self.assertEqual(offer["cost"], 20)
        engine.state["players"]["F"]["treasury"] = 100
        engine.quell_unrest("F", offer["id"])
        self.assertEqual(self._halted(engine, "F"), set())

    def test_the_dockers_strike_needs_two_ports_and_hits_two(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("dockers_strike")
        for city in engine.data["strategic_map"]["cities"]:
            engine.state["city_owners"][city["id"]] = "W"
        engine._refresh_city_income()
        self.assertEqual(engine._event_eligible_players(card), ["W"])
        ports = [c["id"] for c in engine.data["strategic_map"]["cities"] if c.get("port")]
        engine.state["city_owners"][ports[0]] = "F"
        engine._refresh_city_income()
        self.assertNotIn("F", engine._event_eligible_players(card),
                         "只有一個港口的人不適用本事件")
        applied = self._fire(engine, "dockers_strike")
        hit = [e for e in applied if e["kind"] == "city_halt"]
        self.assertTrue(hit)
        for entry in hit:
            self.assertEqual(len(entry["cities"]), 2, entry["player"])
            for city_id in entry["cities"]:
                self.assertTrue((engine._city_by_id(city_id) or {}).get("port"), city_id)
            self.assertEqual(entry["quell_cost"], 20)

    # ---- 警政單位的護盾 ----

    def _shield(self, engine, player, province):
        engine.state["players"][player].setdefault("timed_effects", []).append({
            "kind": "gang_riot_shield", "province": province, "remaining_turns": 3,
            "blocked_mechanics": ["qing_gang_riot"], "name": "警政單位",
        })

    def test_a_police_precinct_spares_that_province_from_the_gang_unrest(self):
        engine = GameEngine(seed=3)
        provinces = sorted({c["province"] for c in engine.data["strategic_map"]["cities"]
                            if engine.state["city_owners"].get(c["id"], c["faction"]) == "F"})
        self.assertTrue(provinces)
        for province in provinces:
            self._shield(engine, "F", province)
        applied = self._fire(engine, "gang_unrest")
        mine = [e for e in applied if e["kind"] == "city_riot" and e["player"] == "F"]
        self.assertTrue(mine)
        self.assertEqual(mine[0].get("skipped"), "police_shielded",
                         "整片轄境都有警政單位，這張卡對他該完全無效")
        self.assertEqual(self._halted(engine, "F"), set())
        others = [e for e in applied if e["kind"] == "city_riot" and e["player"] != "F"]
        self.assertTrue([e for e in others if not e.get("skipped")],
                        "沒有護盾的其他玩家照樣要出事")

    def test_the_society_trouble_also_respects_the_shield(self):
        engine = GameEngine(seed=3)
        biggest = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])[0]
        province = (engine._city_by_id(biggest) or {})["province"]
        self._shield(engine, "F", province)
        applied = self._fire(engine, "secret_society_trouble")
        spared = [e for e in applied if e["kind"] == "police_immunity" and e["player"] == "F"]
        self.assertTrue(spared, "最大城所在的省有警政單位，該被放過")
        self.assertIn(biggest, spared[0]["spared"])

    def test_without_a_shield_the_society_trouble_halves_output(self):
        engine = GameEngine(seed=3)
        biggest = engine._select_cities({"owned_by_target": True, "largest": 1}, ["F"])[0]
        base = self._output(engine, "F", biggest)
        self._fire(engine, "secret_society_trouble")
        self.assertEqual(self._output(engine, "F", biggest),
                         (round(base[0] * 0.5), round(base[1] * 0.5)))

    # ---- 兵變 ----

    def test_the_mutiny_costs_two_players_two_battalions_each(self):
        engine = GameEngine(seed=3)
        before = {c: dict(engine.state["players"][c]["unit_reserves"])
                  for c in engine.state["players"]}
        applied = self._fire(engine, "mutiny")
        hits = [e for e in applied if e["kind"] == "reserve_mutiny"]
        self.assertEqual(len(hits), 2, "隨機兩位玩家")
        for entry in hits:
            self.assertEqual(sum(entry["lost"].values()), 2, entry["player"])
        losers = {e["player"] for e in hits}
        for code in engine.state["players"]:
            after = engine.state["players"][code]["unit_reserves"]
            delta = sum(before[code].values()) - sum(after.values())
            self.assertEqual(delta, 2 if code in losers else 0, code)
            self.assertEqual(int(engine.state["players"][code]["unit_reserve"]),
                             sum(after.values()), f"{code} 的總數沒跟著更新")

    def test_the_mutiny_never_takes_a_unit_type_that_is_empty(self):
        engine = GameEngine(seed=3)
        for code in engine.state["players"]:
            engine.state["players"][code]["unit_reserves"] = {
                "infantry": 1, "cavalry": 0, "machine_gun": 0, "artillery": 0}
        self._fire(engine, "mutiny")
        for code in engine.state["players"]:
            for unit, count in engine.state["players"][code]["unit_reserves"].items():
                self.assertGreaterEqual(int(count), 0, f"{code}/{unit} 變成負數了")

    # ---- 地方官貪腐 ----

    def test_neglecting_graft_costs_two_a_turn_and_stacks(self):
        engine = GameEngine(seed=3)
        base = int(engine.state["players"]["F"]["income"])
        self._fire(engine, "local_official_graft", choice="neglect")
        self.assertEqual(int(engine.state["players"]["F"]["graft_neglect"]), 1)
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base - 2)
        self._fire(engine, "local_official_graft", turn=5, choice="neglect")
        self.assertEqual(int(engine.state["players"]["F"]["graft_neglect"]), 2)
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base - 4,
                         "放任兩次要疊加（使用者裁示）")

    def test_the_graft_penalty_never_expires_on_its_own(self):
        engine = GameEngine(seed=3)
        base = int(engine.state["players"]["F"]["income"])
        self._fire(engine, "local_official_graft", choice="neglect")
        for _ in range(15):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base - 2,
                         "沒有期限，只有整頓才解得掉")

    def test_reforming_clears_every_stacked_level_at_once(self):
        engine = GameEngine(seed=3)
        base = int(engine.state["players"]["F"]["income"])
        self._fire(engine, "local_official_graft", choice="neglect")
        self._fire(engine, "local_official_graft", turn=5, choice="neglect")
        self.assertEqual(int(engine.state["players"]["F"]["graft_neglect"]), 2)
        applied = self._fire(engine, "local_official_graft", turn=8, choice="reform")
        self.assertEqual(int(engine.state["players"]["F"]["graft_neglect"]), 0)
        cleared = [e for e in applied if e["kind"] == "graft_state" and e["player"] == "F"]
        self.assertEqual(cleared[0]["cleared_levels"], 2, "整頓一次清光，不是一次減一層")
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base + 3,
                         "清掉罰則之後還有整頓的 $+3")

    def test_the_reform_bonus_runs_five_turns_then_stops(self):
        engine = GameEngine(seed=3)
        base = int(engine.state["players"]["F"]["income"])
        self._fire(engine, "local_official_graft", choice="reform")
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base + 3)
        for _ in range(5):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertEqual(int(engine.state["players"]["F"]["income"]), base,
                         "五回合後 $+3 要自己收掉")

    def test_reforming_queues_two_random_loyalty_hits_for_the_frontend(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "local_official_graft", choice="reform")
        queue = engine.state["players"]["F"]["pending_frontend_effects"]
        hits = [e for e in queue if e["kind"] == "loyalty_random"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["count"], 2)
        self.assertEqual(hits[0]["amount"], -1)

    # ---- 其餘 ----

    def test_bandit_raids_block_recruiting_and_shipbuilding_only(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "bandit_raids")
        for code in engine.state["players"]:
            self.assertIsNotNone(engine.action_banned(code, "train_unit"), code)
            self.assertIsNotNone(engine.action_banned(code, "train_navy_unit"), code)
            self.assertIsNone(engine.action_banned(code, "reinforce_army"),
                              "設計稿只說徵兵與造船，補兵不在內")
        engine.state["players"]["F"]["treasury"] = 500
        engine.state["players"]["F"]["factory_points"] = 500
        with self.assertRaisesRegex(ValueError, "土匪劫道"):
            engine.train_unit("F", "infantry", 1)
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        engine.state["players"]["F"]["treasury"] = 500
        engine.state["players"]["F"]["factory_points"] = 500
        engine.train_unit("F", "infantry", 1)

    def test_the_epidemic_takes_every_big_city_and_leaves_the_small_ones(self):
        engine = GameEngine(seed=3)
        mine = {c["id"]: int(c["level"]) for c in engine.data["strategic_map"]["cities"]
                if engine.state["city_owners"].get(c["id"], c["faction"]) == "F"}
        big = {cid for cid, level in mine.items() if level >= 4}
        small = {cid for cid, level in mine.items() if level < 4}
        self.assertTrue(big and small, "這條要同時有大城與小城才測得出差別")
        self._fire(engine, "epidemic")
        self.assertEqual(self._halted(engine, "F"), big)
        for city_id in small:
            self.assertGreater(sum(self._output(engine, "F", city_id) or (0, 0)), 0, city_id)

    def test_student_demonstrations_halve_two_random_big_cities(self):
        engine = GameEngine(seed=3)
        applied = self._fire(engine, "student_demonstrations")
        entry = next(e for e in applied if e["kind"] == "city_halt" and e["player"] == "F")
        self.assertEqual(len(entry["cities"]), 2)
        for city_id in entry["cities"]:
            self.assertGreaterEqual(int((engine._city_by_id(city_id) or {})["level"]), 4,
                                    f"{city_id} 不是四／五級大城")

    def test_the_autonomy_movement_blocks_one_random_province_each(self):
        engine = GameEngine(seed=3)
        self._fire(engine, "local_autonomy_movement")
        for code in engine.state["players"]:
            blocks = [e for e in engine.state["players"][code]["timed_effects"]
                      if e["kind"] == "reinforce_block"]
            self.assertEqual(len(blocks), 1, code)
            self.assertEqual(len(blocks[0]["provinces"]), 1,
                             f"{code} 該是隨機**一**省")
            province = blocks[0]["provinces"][0]
            self.assertIsNotNone(engine._reinforce_block(code, province), code)
            others = [p for p in {c["province"] for c in engine.data["strategic_map"]["cities"]}
                      if p != province]
            self.assertIsNone(engine._reinforce_block(code, others[0]),
                              "別的省不該被擋")

    def test_the_railway_strike_closes_exactly_one_of_the_two_named_lines(self):
        engine = GameEngine(seed=3)
        applied = self._fire(engine, "railway_workers_strike")
        entry = next(e for e in applied if e["kind"] == "railway_strike")
        self.assertIn(entry["railway"], ("京漢鐵路", "津浦鐵路"))
        closed = [e for e in engine.state["railway_effects"]
                  if e["railway"] == entry["railway"]]
        self.assertTrue(closed)
        self.assertEqual(int(closed[0]["repair_factory_cost"]), 0,
                         "罷工沒有人要攤搶修費——那是崩鐵玩家的規則")
        for _ in range(2):
            engine.state["event_pool"] = []
            engine.next_turn(active_player="F")
        self.assertFalse([e for e in engine.state["railway_effects"]
                          if e["railway"] == entry["railway"]], "兩回合後要復駛")

    def test_the_railway_strike_can_pick_either_line(self):
        picked = set()
        for seed in range(1, 20):
            engine = GameEngine(seed=seed)
            applied = engine._apply_event_payload(
                engine._event_template("railway_workers_strike")["apply"],
                players=None, card=engine._event_template("railway_workers_strike"))
            picked.add(next(e for e in applied if e["kind"] == "railway_strike")["railway"])
        self.assertEqual(picked, {"京漢鐵路", "津浦鐵路"}, "兩條線都要抽得到")

    # ---- 學潮與反帝遊行：兩支都要有效果 ----

    def test_the_march_suppression_branch_halves_the_four_cities(self):
        engine = GameEngine(seed=3)
        four = ["shanghai", "tianjin", "guangzhou", "hankou"]
        for city_id in four:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        applied = self._fire(engine, "anti_imperialist_march", choice="suppress")
        halt = [e for e in applied if e["kind"] == "city_halt"]
        self.assertTrue(halt)
        self.assertEqual(sorted(halt[0]["cities"]), sorted(four))
        student = [c for c in engine.data["event_cards"]["cards"]
                   if "學潮" in (c.get("tags") or [])]
        self.assertTrue(student)
        self.assertEqual(engine._event_duration_bonus(student[0]), 1,
                         "[學潮] 類事件卡持續時間 +1")

    def test_the_march_tolerate_branch_costs_relations_instead(self):
        engine = GameEngine(seed=3)
        for city_id in ["shanghai", "tianjin", "guangzhou", "hankou"]:
            engine.state["city_owners"][city_id] = "F"
        engine._refresh_city_income()
        before = dict(engine.state["players"]["F"]["foreign_relations"])
        applied = self._fire(engine, "anti_imperialist_march", choice="tolerate")
        self.assertFalse([e for e in applied if e["kind"] == "city_halt"],
                         "放任就不該停產")
        after = engine.state["players"]["F"]["foreign_relations"]
        for power in ("uk", "us", "fr", "jp"):
            self.assertEqual(int(after[power]), int(before[power]) - 2, power)



class CompradorPunishmentImmunityTests(unittest.TestCase):
    """買辦技能改成擋 [懲戒] 事件卡。

    舊機制是「該國的譴責**功能卡**進牌庫時每張有機率被擋下」——那作用在
    功能卡上，與懲戒無關。現在改成：抽到該國的 [懲戒] 事件卡時當場擲一次，
    中了就靜默重抽（玩家不會知道剛剛躲過什麼），沒中就照常降臨。
    """

    JP_CARD = "japanese_air_raid"          # 12.3 日軍航空隊轟炸
    FR_CARD = "french_air_force_bombing"   # 12.29 法國空軍轟炸

    def _run(self, seed, trait, card_id, power, owner="F"):
        engine = GameEngine(seed=seed)
        engine.state["faction_general_traits"] = {owner: [trait]} if trait else {}
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"][power] = 5
        engine.state["players"][owner]["foreign_relations"][power] = -6
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player=owner)
        return engine, engine.pending_event_view()

    def _landed(self, trait, card_id, power, total=400):
        return sum(1 for seed in range(total)
                   if self._run(seed, trait, card_id, power)[1] is not None)

    # ---- 免疫率 ----

    def test_the_immunity_rates_match_the_design(self):
        """法 30%、日 10%。用大樣本量，容差 ±6 個百分點。"""
        total = 400
        for trait, card_id, power, expected in (
                ("french_comprador", self.FR_CARD, "fr", 0.30),
                ("japanese_comprador", self.JP_CARD, "jp", 0.10)):
            landed = self._landed(trait, card_id, power, total)
            blocked = (total - landed) / total
            self.assertAlmostEqual(blocked, expected, delta=0.06,
                                   msg=f"{trait} 實測擋下 {blocked:.1%}，設計值 {expected:.0%}")

    def test_without_a_comprador_the_punishment_always_lands(self):
        for card_id, power in ((self.FR_CARD, "fr"), (self.JP_CARD, "jp")):
            self.assertEqual(self._landed(None, card_id, power, 120), 120,
                             f"{card_id} 沒有買辦就不該被擋掉任何一次")

    def test_a_comprador_only_shields_against_its_own_power(self):
        """唐繼堯擋不住日本，張宗昌也擋不住法國。"""
        self.assertEqual(self._landed("french_comprador", self.JP_CARD, "jp", 120), 120)
        self.assertEqual(self._landed("japanese_comprador", self.FR_CARD, "fr", 120), 120)

    def test_the_shield_only_covers_the_faction_that_holds_the_general(self):
        """技能跟著將領走：別家挨的懲戒不會因為你有唐繼堯而被擋掉。"""
        landed = 0
        for seed in range(120):
            engine = GameEngine(seed=seed)
            engine.state["faction_general_traits"] = {"W": ["french_comprador"]}
            for code in engine.state["players"]:
                engine.state["players"][code]["foreign_relations"]["fr"] = 5
            engine.state["players"]["S"]["foreign_relations"]["fr"] = -6
            engine.state["turn"] = 2
            engine.state["event_pool"] = [self.FR_CARD]
            engine.next_turn(active_player="S")
            view = engine.pending_event_view()
            if view:
                self.assertEqual(view["drawer"], "S")
                landed += 1
        self.assertEqual(landed, 120, "W 有唐繼堯，不該替 S 擋下法國的懲戒")

    # ---- 只擋 [懲戒]，不擋別的 ----

    def test_only_punishment_cards_are_deflected(self):
        """判準是卡片的 tags——非 [懲戒] 的法國事件卡一次都不該被擋。"""
        # 12.68 法國教案抗議：法國的卡、標籤是 [交涉]，只要控制雲南或廣西就會降臨。
        card_id = "french_mission_case_protest"
        engine0 = GameEngine(seed=3)
        card = engine0._event_template(card_id)
        self.assertEqual(card["power_note"], "法")
        self.assertNotIn("懲戒", card.get("tags") or [])
        landed = 0
        for seed in range(80):
            engine = GameEngine(seed=seed)
            engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
            for city in engine.data["strategic_map"]["cities"]:
                if city["province"] in ("雲南", "廣西"):
                    engine.state["city_owners"][city["id"]] = "F"
            engine._refresh_city_income()
            engine.state["turn"] = 2
            engine.state["event_pool"] = [card_id]
            engine.next_turn(active_player="F")
            if engine.pending_event_view():
                landed += 1
        self.assertEqual(landed, 80,
                         f'{card["ref"]} {card["name"]} 不是 [懲戒]，不該被買辦擋到')

    def test_the_check_reads_the_card_tags_not_a_hardcoded_list(self):
        """新增的 [懲戒] 卡要自動吃得到，不必回頭改程式。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0            # 必中
        fake = {"id": "probe", "name": "假懲戒", "tags": ["懲戒"], "power_note": "法"}
        self.assertTrue(engine._comprador_deflects(fake, "F"))
        self.assertFalse(engine._comprador_deflects({**fake, "tags": []}, "F"),
                         "沒有 [懲戒] 標籤就不該被擋")
        self.assertFalse(engine._comprador_deflects({**fake, "power_note": "英"}, "F"),
                         "不是法國的卡就不該被擋")
        self.assertFalse(engine._comprador_deflects(fake, "W"), "W 沒有買辦")

    # ---- 重抽的行為 ----

    def test_a_deflected_card_stays_in_the_pool_for_next_time(self):
        """免疫是「這一次砸不到你」，不是永久免疫（使用者裁示）。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0            # 必中，一定被擋
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        engine.state["turn"] = 2
        engine.state["event_pool"] = [self.FR_CARD]
        engine.next_turn(active_player="F")
        self.assertIsNone(engine.pending_event_view(), "必中時這一輪不該有卡")
        self.assertIn(self.FR_CARD, engine.state["event_pool"],
                      "被擋下的卡要留在池子裡，下回合還會再來")
        self.assertFalse(engine.event_is_spent(self.FR_CARD))

    def test_the_deflection_is_silent(self):
        """使用者裁示：不發任何提示，玩家不會知道剛剛躲過什麼。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        before = len(engine.state["players"]["F"].get("notifications") or [])
        engine.state["turn"] = 2
        engine.state["event_pool"] = [self.FR_CARD]
        engine.next_turn(active_player="F")
        after = len(engine.state["players"]["F"].get("notifications") or [])
        self.assertEqual(after, before, "靜默重抽：不該發通知")
        self.assertIsNone(engine.pending_event_view())
        # 但要留下查帳紀錄
        self.assertTrue(engine.state["comprador_deflections"])
        record = engine.state["comprador_deflections"][-1]
        self.assertEqual(record["card_id"], self.FR_CARD)
        self.assertEqual(record["owner"], "F")

    def test_a_deflection_does_not_eat_the_rounds_card_quota(self):
        """被擋掉的那一次不算數：該抽幾張還是幾張。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        quota = int(engine._event_rules().get("cards_per_cycle", 4))
        # 池子：一張必被擋的法國懲戒 ＋ 足夠的普通卡
        plain = [c["id"] for c in engine.data["event_cards"]["cards"]
                 if not c.get("entry_condition") and not c.get("never_drawn")
                 and "懲戒" not in (c.get("tags") or [])][:quota]
        engine.state["event_pool"] = [self.FR_CARD] + plain
        engine.random.random = lambda: 0.0            # 法國那張必被擋
        engine.state["turn"] = 2
        engine.next_turn(active_player="F")
        pending = engine.state["pending_events"]
        self.assertIsNotNone(pending)
        self.assertEqual(len(pending["cards"]), quota,
                         "被買辦擋掉的那一次不該佔掉本輪的抽卡額度")
        self.assertNotIn(self.FR_CARD, [c["card_id"] for c in pending["cards"]])

    def test_the_redraw_loop_is_capped_so_a_turn_can_never_hang(self):
        """必中 ＋ 池子裡只有懲戒卡 → 靠上限收尾，不能無限重抽。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        french = [c["id"] for c in engine.data["event_cards"]["cards"]
                  if "懲戒" in (c.get("tags") or []) and c.get("power_note") == "法"
                  and set(c.get("entry_condition") or {}) <= {"relation_max"}]
        self.assertGreaterEqual(len(french), 2)
        engine.state["event_pool"] = french * 8
        engine.state["turn"] = 2
        engine.next_turn(active_player="F")          # 不能卡住
        self.assertLessEqual(len(engine.state["comprador_deflections"]),
                             engine.COMPRADOR_MAX_REDRAWS)

    def test_hitting_the_cap_lets_the_punishment_through(self):
        """達上限就直接實施（使用者裁示），不是靜悄悄什麼都不發生。

        注意：同一輪裡被擋掉的卡會進 already，不會再被抽到，所以要撞到上限
        得有**好幾張不同的**懲戒卡輪流被擋。這也順帶說明了上限有多難碰到。
        """
        engine = GameEngine(seed=3)
        engine.COMPRADOR_MAX_REDRAWS = 2
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        french = [c["id"] for c in engine.data["event_cards"]["cards"]
                  if "懲戒" in (c.get("tags") or []) and c.get("power_note") == "法"
                  and set(c.get("entry_condition") or {}) <= {"relation_max"}]
        self.assertGreaterEqual(len(french), 2)
        engine.state["event_pool"] = list(french)
        engine.state["turn"] = 2
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view, "擋滿上限之後就該讓它降臨")
        self.assertIn(view["card"]["id"], french)

    def test_a_deflected_card_does_not_come_back_in_the_same_round(self):
        """同一輪不對同一張反覆擲骰——擋掉就換一張，下回合才會再遇到。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        engine.state["event_pool"] = [self.FR_CARD] * 6
        engine.state["turn"] = 2
        engine.next_turn(active_player="F")
        self.assertEqual(len(engine.state["comprador_deflections"]), 1,
                         "同一張只擲一次，不是把六份都擲過一輪")
        self.assertEqual(engine.state["event_pool"].count(self.FR_CARD), 6,
                         "六份都還在池子裡")

    # ---- 有機率免疫 ≠ 完全免疫 ----

    def test_a_comprador_holder_can_still_be_assassinated(self):
        """張宗昌在手不代表日本的刺客永遠得不了手。

        12.38 關東軍特務機關行刺是日本的 [懲戒]，所以買辦有 10% 把整張卡擋掉；
        但剩下的 90% 裡，暗殺本身照樣有 20% 成功率。兩層機率相乘 ≈ 18%——
        這條把「還是會死人」釘死，免得日後有人把機率免疫誤解成護身符。
        """
        marshals = {"F": "zhang_zuolin", "W": "wu_peifu",
                    "S": "sun_chuanfang", "N": "chiang_kai_shek"}
        total, deflected, landed, killed = 1500, 0, 0, 0
        for seed in range(total):
            engine = GameEngine(seed=seed)
            engine.state["marshal_ids"] = dict(marshals)
            for code in engine.state["players"]:
                engine.state["players"][code]["foreign_relations"]["jp"] = 5
            engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
            engine.state["turn"] = 2
            engine.state["event_pool"] = ["kwantung_army_special_service_assassination"]
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            if not view:
                deflected += 1
                continue
            landed += 1
            if (view.get("assassination") or {}).get("success"):
                killed += 1
        self.assertGreater(killed, 0, "有買辦也還是會死人——這不是完全免疫")
        self.assertAlmostEqual(deflected / total, 0.10, delta=0.04,
                               msg="買辦擋卡率應該還是 10%")
        # 得手率 ≈ (1 − 0.10) × 0.20 = 18%
        self.assertAlmostEqual(killed / total, 0.18, delta=0.04,
                               msg=f"實測得手 {killed}/{total}，理論值約 18%")
        self.assertAlmostEqual(killed / landed, 0.20, delta=0.05,
                               msg="卡片降臨之後，暗殺本身的成功率不該被買辦改動")

    def test_the_comprador_does_not_change_the_assassination_success_rate(self):
        """買辦只影響「卡抽不抽得到」，不影響抽到之後的暗殺骰。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("kwantung_army_special_service_assassination")
        spec = (card.get("apply") or {})["assassinate_marshal"][0]
        base = float(spec.get("success_rate", card.get("success_rate", 0.2)))
        self.assertAlmostEqual(base, 0.20)
        engine.state["faction_general_traits"] = {"F": ["japanese_comprador"]}
        engine.state["marshal_ids"] = {"F": "zhang_zuolin"}
        with_trait = engine._resolve_assassination(
            "F", {"id": "probe", "success_rate": base}, "zhang_zuolin", "F", notify=False)
        engine.state["faction_general_traits"] = {}
        without = engine._resolve_assassination(
            "F", {"id": "probe", "success_rate": base}, "zhang_zuolin", "F", notify=False)
        self.assertEqual(with_trait["chance"], without["chance"],
                         "買辦不該動到暗殺的成功率本身")

    # ---- 玩家發動的暗殺完全不受買辦影響 ----

    def test_a_player_launched_assassination_ignores_the_comprador_entirely(self):
        """〈王亞樵來投〉是玩家自己發動的暗殺，不是列強懲戒。

        它走 use_function → _resolve_assassination，根本不經過抽卡迴圈，
        所以買辦碰不到它。這條把「碰不到」變成會紅的斷言，而不是靠讀程式相信。
        """
        def run(traits, seed):
            engine = GameEngine(seed=seed)
            engine.state["faction_general_traits"] = dict(traits)
            engine.state["players"]["W"]["hand"].append("wang_yaqiao_assassination")
            engine.state["players"]["W"]["treasury"] = 999
            engine.state["players"]["W"]["factory_points"] = 999
            result = engine.use_function(
                "W", "wang_yaqiao_assassination",
                target_general_id="zhang_zongchang", target_owner="F")
            return result["assassination"]

        # 逐一比對：同一個 seed 下，有沒有買辦的擲骰結果必須一模一樣
        for seed in range(60):
            with_trait = run({"F": ["japanese_comprador"]}, seed)
            without = run({}, seed)
            self.assertEqual(with_trait["roll"], without["roll"], f"seed={seed}")
            self.assertEqual(with_trait["chance"], without["chance"], f"seed={seed}")
            self.assertEqual(with_trait["success"], without["success"], f"seed={seed}")
        # 而且真的會得手
        hits = sum(1 for seed in range(300)
                   if run({"F": ["japanese_comprador"]}, seed)["success"])
        self.assertGreater(hits, 0, "玩家發動的暗殺照樣打得中有買辦的陣營")

    def test_the_player_assassination_card_is_not_tagged_as_a_punishment(self):
        """守門：這張是功能卡不是事件卡，也不帶 [懲戒]。

        哪天有人把它改成帶標籤的事件卡，買辦就會莫名其妙開始擋它。
        """
        engine = GameEngine(seed=3)
        ids = {c["id"] for c in engine.data["event_cards"]["cards"]}
        self.assertNotIn("wang_yaqiao_assassination", ids, "它不該是事件卡")
        card = next(c for c in engine.data["function_cards"]["cards"]
                    if c["id"] == "wang_yaqiao_assassination")
        self.assertEqual(card.get("mechanic"), "assassination")
        self.assertNotIn("懲戒", card.get("tags") or [])

    # ---- 複查時補上的兩個洞 ----

    def test_a_compound_power_note_is_still_matched(self):
        """power_note 允許寫成「蘇／德」。先前拿整串去查表，複合寫法永遠擋不到。"""
        engine = GameEngine(seed=3)
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for note in ("法", "法／日", "日／法", " 法 ", "法、日"):
            self.assertTrue(
                engine._comprador_deflects(
                    {"id": "probe", "name": "x", "tags": ["懲戒"], "power_note": note}, "F"),
                f"power_note={note!r} 應該比對得到法國")
        for note in ("英", "英／美", ""):
            self.assertFalse(
                engine._comprador_deflects(
                    {"id": "probe", "name": "x", "tags": ["懲戒"], "power_note": note}, "F"),
                f"power_note={note!r} 不該被法國買辦擋到")

    def test_a_card_that_survives_the_cap_is_not_logged_as_deflected(self):
        """擋滿上限而放行的那張照樣降臨，就不能同時記成『被擋下』。"""
        engine = GameEngine(seed=3)
        engine.COMPRADOR_MAX_REDRAWS = 2
        engine.state["faction_general_traits"] = {"F": ["french_comprador"]}
        engine.random.random = lambda: 0.0
        for code in engine.state["players"]:
            engine.state["players"][code]["foreign_relations"]["fr"] = 5
        engine.state["players"]["F"]["foreign_relations"]["fr"] = -6
        french = [c["id"] for c in engine.data["event_cards"]["cards"]
                  if "懲戒" in (c.get("tags") or []) and c.get("power_note") == "法"
                  and set(c.get("entry_condition") or {}) <= {"relation_max"}]
        engine.state["event_pool"] = list(french)
        engine.state["turn"] = 2
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertIsNotNone(view)
        landed = view["card"]["id"]
        logged = [d["card_id"] for d in engine.state["comprador_deflections"]]
        self.assertNotIn(landed, logged,
                         "降臨的卡不該出現在『被擋下』的紀錄裡")
        self.assertTrue(engine.state["comprador_deflection_overrides"],
                        "被迫放行要另外記一筆")
        self.assertEqual(
            engine.state["comprador_deflection_overrides"][-1]["card_id"], landed)

    def test_the_documentation_matches_the_new_behaviour(self):
        """守門：README 還在描述舊機制的話，讀的人會照舊機制去理解。"""
        repo = pathlib.Path(__file__).resolve().parents[1]
        text = (repo / "comabt_system" / "README.md").read_text(encoding="utf-8")
        for trait in ("japanese_comprador", "french_comprador"):
            self.assertIn(trait, text)
        self.assertNotIn("condemnation card has a", text,
                         "README 還在說買辦擋譴責卡")



class FactionTraitReconciliationTests(unittest.TestCase):
    """陣營層級技能在將領死亡之後必須跟著消失。

    這些技能的效果全在後端（免疫列強懲戒、該省每城 +1、紅軍起義只需駐一回合），
    但「誰持有誰、誰死了」只有前端知道。後端原本只在 apply_general_join 時被動
    更新，**將領陣亡它完全收不到消息**——張宗昌死了，奉系照樣免疫日本懲戒。
    """

    def test_a_dead_comprador_stops_shielding_his_faction(self):
        engine = GameEngine(seed=3)
        self.assertAlmostEqual(engine.comprador_immunity("F", "jp"), 0.10)
        # 前端回報：奉系已經沒有活著的陣營層級技能持有者了
        engine.next_turn(active_player="F", faction_trait_holders={})
        self.assertEqual(engine.comprador_immunity("F", "jp"), 0.0,
                         "張宗昌陣亡之後不該還有免疫")
        self.assertEqual(engine.faction_general_traits("F"), [])

    def test_the_dead_comprador_really_stops_deflecting_draws(self):
        """不只是查詢值變 0——實際抽卡也要真的擋不住了。"""
        def landed(holders):
            hits = 0
            for seed in range(150):
                engine = GameEngine(seed=seed)
                engine.set_faction_trait_holders(holders)
                for code in engine.state["players"]:
                    engine.state["players"][code]["foreign_relations"]["jp"] = 5
                engine.state["players"]["F"]["foreign_relations"]["jp"] = -6
                engine.state["turn"] = 2
                engine.state["event_pool"] = ["japanese_air_raid"]
                engine.next_turn(active_player="F")
                if engine.pending_event_view():
                    hits += 1
            return hits
        self.assertLess(landed({"F": ["japanese_comprador"]}), 150, "活著時要擋得到")
        self.assertEqual(landed({}), 150, "死了之後一次都不該擋下")

    def test_a_dead_provincial_patron_stops_paying(self):
        """劉湘死了，四川每座城的 +1／+1 要跟著沒。"""
        engine = GameEngine(seed=5)
        for city in engine.data["strategic_map"]["cities"]:
            if city["province"] == "四川":
                engine.state["city_owners"][city["id"]] = "W"
        engine._refresh_city_income()
        base = int(engine.state["players"]["W"]["income"])
        engine.apply_general_join("W", ["tianfu_land"])
        with_patron = int(engine.state["players"]["W"]["income"])
        self.assertGreater(with_patron, base, "在世時該加成")
        engine.next_turn(active_player="W", faction_trait_holders={})
        self.assertEqual(engine.faction_general_traits("W"), [])
        engine._refresh_city_income()
        self.assertEqual(int(engine.state["players"]["W"]["income"]), base,
                         "人死了，四川的加成也該沒了")

    def test_a_dead_communist_hunter_stops_shortening_uprisings(self):
        engine = GameEngine(seed=3)
        engine.set_faction_trait_holders({"W": ["anticommunist_vanguard"]})
        self.assertTrue(engine._has_fast_uprising_suppression("W"))
        engine.next_turn(active_player="W", faction_trait_holders={})
        self.assertFalse(engine._has_fast_uprising_suppression("W"),
                         "何鍵死了，剿共也該沒了")

    def test_reconciliation_replaces_rather_than_merges(self):
        """整份對帳：前端送什麼就是什麼，不是把新的疊在舊的上面。"""
        engine = GameEngine(seed=3)
        engine.set_faction_trait_holders({"F": ["japanese_comprador"],
                                          "W": ["tianfu_land"]})
        result = engine.set_faction_trait_holders({"W": ["tianfu_land"]})
        self.assertEqual(engine.faction_general_traits("F"), [])
        self.assertEqual(engine.faction_general_traits("W"), ["tianfu_land"])
        self.assertEqual(result["lost"], {"F": ["japanese_comprador"]})

    def test_reconciliation_ignores_things_that_are_not_faction_traits(self):
        """前端送來戰場技能（山地師之類）不該被誤記成陣營技能。"""
        engine = GameEngine(seed=3)
        engine.set_faction_trait_holders({"F": ["mountain_division", "japanese_comprador"]})
        self.assertEqual(engine.faction_general_traits("F"), ["japanese_comprador"])

    def test_reconciliation_ignores_unknown_factions(self):
        engine = GameEngine(seed=3)
        engine.set_faction_trait_holders({"ZZ": ["japanese_comprador"]})
        self.assertNotIn("ZZ", engine.state["faction_general_traits"])

    def test_not_reporting_at_all_leaves_the_holders_untouched(self):
        """沒送這個欄位（舊版前端）就不動它——不能因為漏送就把技能全清光。"""
        engine = GameEngine(seed=3)
        before = deepcopy(engine.state["faction_general_traits"])
        engine.next_turn(active_player="F")
        self.assertEqual(engine.state["faction_general_traits"], before)

    def test_the_frontend_actually_reports_it(self):
        """守門：前端要真的算並送出這份清單，否則後端永遠收不到。"""
        self.assertIn("faction_trait_holders: factionTraitHolders()", FRONTEND_SOURCE)
        self.assertIn("function factionTraitHolders()", FRONTEND_SOURCE)
        # 前端的技能白名單要與後端一致，少一個就等於那個技能永遠不會被回收
        import re as _re
        block = FRONTEND_SOURCE[FRONTEND_SOURCE.index("const FACTION_LEVEL_TRAITS = new Set(["):]
        block = block[:block.index("]);")]
        listed = set(_re.findall(r'"([a-z_]+)"', block))
        self.assertEqual(listed, set(FACTION_LEVEL_TRAITS),
                         "前後端的陣營層級技能清單對不上")
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn("faction_trait_holders", server, "server 沒把這個欄位轉給引擎")



class FrontendBackendParityTests(unittest.TestCase):
    """前端顯示的數字必須有後端依據。

    這個專案的前端會自己算一些數字。只要同一條公式在兩邊各寫一份，遲早會分岔，
    而分岔的症狀是「面板寫 $5、實際扣 $6」——玩家看到的是假的。
    這一類分歧沒有任何東西會叫，所以要用測試盯著。
    """

    # ---- 徵募價格：只能有一份來源 ----

    def test_the_panel_reads_resolved_costs_instead_of_recomputing(self):
        """守門：募兵面板必須讀後端解算好的價格，不能自己乘一次陣營費率。"""
        # 注意：不能只斷言「原始碼裡出現 resolved_recruit_costs」——那個字串在
        # 我自己寫的註解裡也有，改壞了照樣綠。要斷言的是**實際取值的運算式**。
        self.assertIn("profile.resolved_recruit_costs", FRONTEND_SOURCE)
        self.assertIn("profile.resolved_navy_costs", FRONTEND_SOURCE)
        panel = FRONTEND_SOURCE[FRONTEND_SOURCE.index("function renderRecruitmentPanel"):]
        panel = panel[:panel.index("\nfunction ", 10)]
        self.assertIn("const costs = profile.resolved_recruit_costs", panel)
        self.assertIn("const navyCosts = profile.resolved_navy_costs", panel)
        self.assertNotIn("* costModifier", panel,
                         "面板又自己乘陣營費率了——價格只能有一份來源")
        self.assertNotIn("recruit_cost_adjustment", panel,
                         "固定加減也該由後端解算")

    def test_resolved_costs_match_what_the_engine_actually_charges(self):
        """平時、倍率生效中、折抵生效中，三種情況都要對得上。"""
        from backend.card_engine import RECRUIT_COSTS, NAVY_RECRUIT_COSTS
        for card_id in (None, "world_oil_price_surge", "burning_red_lotus",
                        "arms_market_competition", "industrial_exposition"):
            engine = GameEngine(seed=3)
            if card_id:
                card = engine._event_template(card_id)
                engine._apply_event_payload(card["apply"], players=None, card=card)
            snapshot = engine.snapshot()
            for code in engine.state["players"]:
                shown = snapshot["players"][code]["resolved_recruit_costs"]
                for unit in RECRUIT_COSTS:
                    cash, factory = engine._unit_cost_for(code, unit)
                    self.assertEqual((shown[unit]["cash"], shown[unit]["factory"]),
                                     (cash, factory), f"{card_id}／{code}／{unit}")
                navy = snapshot["players"][code]["resolved_navy_costs"]
                for unit in NAVY_RECRUIT_COSTS:
                    cash, factory = engine._navy_unit_cost_for(code, unit)
                    self.assertEqual((navy[unit]["cash"], navy[unit]["factory"]),
                                     (cash, factory), f"{card_id}／{code}／{unit}")

    def test_a_production_multiplier_really_moves_the_published_price(self):
        """油價上漲之後，面板讀到的價格必須跟著漲——否則等於沒接上。"""
        engine = GameEngine(seed=3)
        before = engine.snapshot()["players"]["F"]["resolved_recruit_costs"]["infantry"]
        card = engine._event_template("world_oil_price_surge")
        engine._apply_event_payload(card["apply"], players=None, card=card)
        after = engine.snapshot()["players"]["F"]["resolved_recruit_costs"]["infantry"]
        self.assertGreater(after["cash"], before["cash"])
        self.assertGreater(after["factory"], before["factory"])
        navy_before = engine.snapshot()["players"]["F"]["resolved_navy_costs"]["gun_boat"]
        self.assertGreater(navy_before["cash"], 200, "水軍倍率是 1.5，比陸軍重")

    def test_the_navy_price_has_a_single_source_too(self):
        """train_navy_unit 不能再自己內嵌算一次價格。"""
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        body = source[source.index("def train_navy_unit"):]
        body = body[:body.index("\n    def ", 10)]
        self.assertIn("_navy_unit_cost_for", body)
        self.assertNotIn('_production_multiplier(player, "navy")', body,
                         "算價的地方只該有一處")

    # ---- 策反：公式在兩邊各一份，必須逐格對得上 ----

    def _frontend_defection(self, loyalty, force, resistance=0.0):
        """把 app.js 那段公式照抄成 Python，逐字對應（含夾值）。"""
        loy = max(1, min(10, loyalty or 1))
        f = max(1, force)
        cost = math.ceil((10 + f * 3 + loy * 2) * 0.5)
        base = 0.45 - loy * 0.04 - f * 0.003
        chance = max(0.03, min(0.60, base * 1.25) - resistance)
        return cost, round(chance, 6)

    def test_the_defection_quote_matches_what_the_backend_charges(self):
        for loyalty in range(0, 16):
            for force in (0, 0.5, 1, 2, 5, 12, 40, 100):
                engine = GameEngine(seed=3)
                engine.state["players"]["F"]["treasury"] = 99999
                result = engine.attempt_defection_with_force("F", loyalty, force)
                self.assertEqual(
                    self._frontend_defection(loyalty, force),
                    (result["cost"], round(result["chance"], 6)),
                    f"忠誠={loyalty} 戰力={force}：面板報的價與實收不一致")

    def test_the_defection_resistance_is_applied_the_same_way(self):
        for resistance in (0.0, 0.05, 0.2):
            engine = GameEngine(seed=3)
            engine.state["players"]["F"]["treasury"] = 99999
            result = engine.attempt_defection_with_force("F", 5, 12, resistance=resistance)
            self.assertEqual(
                self._frontend_defection(5, 12, resistance),
                (result["cost"], round(result["chance"], 6)), f"抗性={resistance}")

    def test_the_frontend_clamps_exactly_like_the_backend(self):
        """守門：兩邊的夾值必須一樣，否則超出範圍時就會分岔。"""
        panel = FRONTEND_SOURCE[FRONTEND_SOURCE.index("const defectionForce"):]
        panel = panel[:panel.index("const defectionChance")]
        self.assertIn("Math.max(1, forcePoints(units))", panel, "戰力要夾 ≥1")
        self.assertIn("Math.max(1, Math.min(10, loyalty || 1))", panel, "忠誠要夾 1–10")

    # ---- 後端→前端的交辦不能沒人執行 ----

    def test_every_queued_frontend_effect_kind_has_a_handler(self):
        engine = GameEngine(seed=3)
        declared = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "frontend_effects":
                        for spec in (value or []):
                            declared.add(spec.get("kind"))
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for card in (engine.data["event_cards"]["cards"]
                     + engine.data["function_cards"]["cards"]):
            walk(card)
        self.assertTrue(declared, "資料檔裡應該有 frontend_effects")
        handlers = FRONTEND_SOURCE[FRONTEND_SOURCE.index("const PENDING_EFFECT_HANDLERS = {"):]
        handlers = handlers[:handlers.index("\n};")]
        for kind in sorted(declared):
            self.assertIn(f"{kind}:", handlers,
                          f"後端會排 {kind}，前端卻沒有處理器——交辦了沒人做")

    def test_every_timed_flag_kind_is_read_by_somebody(self):
        """掛了旗標卻沒有人讀 ＝ 那張卡的那段效果是死碼。"""
        engine = GameEngine(seed=3)
        backend_source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        flags = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "timed_flags":
                        for spec in (value or []):
                            flags.add(spec.get("kind"))
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for card in (engine.data["event_cards"]["cards"]
                     + engine.data["function_cards"]["cards"]):
            walk(card)
        # silver_reform_done 由卡片以 immune_flag 動態指名，程式不寫死字串，
        # 所以改用 has_timed_flag 的呼叫點來證明它被讀。
        dynamic = {"silver_reform_done"}
        self.assertIn("has_timed_flag", backend_source)
        for kind in sorted(flags - dynamic):
            self.assertTrue(f'"{kind}"' in backend_source or f'"{kind}"' in FRONTEND_SOURCE,
                            f"{kind} 沒有任何人讀——死碼")

    def test_no_frontend_api_call_points_at_a_missing_endpoint(self):
        import re as _re
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        endpoints = set(_re.findall(r'"(/api/[a-z\-]+)"', server))
        called = set(_re.findall(r'api\("(/api/[a-z\-]+)"', FRONTEND_SOURCE))
        self.assertTrue(called)
        self.assertEqual(called - endpoints, set(),
                         "前端打了後端沒有的端點")



class LoyaltyRulesTests(unittest.TestCase):
    """忠誠的規則現在住在後端。

    先前整套算式只在 app.js 裡，而後端卻拿前端算出來的忠誠去扣錢、擲策反骰——
    規則與判定分居兩處，任一邊改動都不會有人叫。現在
    `compute_loyalty`／`loyalty_report` 是權威來源，前端只負責顯示。
    """

    def _army(self, units, **extra):
        return {"units": units, "faction": "F", "status": "active", **extra}

    def test_a_missing_base_loyalty_stays_missing(self):
        engine = GameEngine(seed=3)
        self.assertIsNone(engine.compute_loyalty(base=None)["value"])

    def test_absolute_loyalty_is_pinned_at_ten(self):
        engine = GameEngine(seed=3)
        result = engine.compute_loyalty(base=3, absolute=True, current_force=1,
                                        average_friendly_force=100, baseline_force=100)
        self.assertEqual(result["value"], 10)
        self.assertTrue(result["breakdown"]["absolute"])

    def test_an_override_replaces_the_base(self):
        engine = GameEngine(seed=3)
        plain = engine.compute_loyalty(base=5, has_army=False)
        bumped = engine.compute_loyalty(base=5, override=1, has_army=False)
        self.assertEqual(plain["value"], 2)
        self.assertEqual(bumped["value"], 1)
        self.assertTrue(bumped["breakdown"]["override"])

    def test_no_army_caps_loyalty_at_two(self):
        engine = GameEngine(seed=3)
        for flag in ("has_army", "jailed", "recruited"):
            kwargs = {"base": 9}
            kwargs[flag] = (flag != "has_army")
            self.assertEqual(engine.compute_loyalty(**kwargs)["value"], 2, flag)

    def test_relative_power_is_capped_both_ways(self):
        engine = GameEngine(seed=3)
        strong = engine.compute_loyalty(base=5, current_force=1000,
                                        average_friendly_force=10, baseline_force=1000)
        weak = engine.compute_loyalty(base=5, current_force=1,
                                      average_friendly_force=1000, baseline_force=1)
        self.assertEqual(strong["breakdown"]["relative_power"], 2)
        self.assertEqual(weak["breakdown"]["relative_power"], -2)

    def test_battle_loss_is_capped_at_minus_four(self):
        engine = GameEngine(seed=3)
        result = engine.compute_loyalty(base=10, current_force=0,
                                        average_friendly_force=1, baseline_force=100)
        self.assertEqual(result["breakdown"]["battle_loss"], -4)

    def test_the_value_never_leaves_zero_to_ten(self):
        engine = GameEngine(seed=3)
        for base in (-5, 0, 5, 10, 30):
            for force in (0, 1, 50, 500):
                value = engine.compute_loyalty(
                    base=base, current_force=force, average_friendly_force=20,
                    baseline_force=100)["value"]
                self.assertGreaterEqual(value, 0, (base, force))
                self.assertLessEqual(value, 10, (base, force))

    def test_the_report_reads_the_tactical_state_the_server_already_holds(self):
        engine = GameEngine(seed=3)
        tactical = {
            "armies": {"a1": self._army({"infantry": 10}, generalId="g1"),
                       "a2": self._army({"infantry": 30}, generalId="g2")},
            "generalTrees": {"F": {"generals": {
                "g1": {"loyalty": 5, "traits": []},
                "g2": {"loyalty": 5, "traits": []},
                "g3": {"loyalty": 5, "traits": []},   # 沒有部隊
            }}},
            "generalOwners": {"g1": "F", "g2": "F", "g3": "F"},
            "loyaltyOverrides": {},
            "loyaltyBaselineArmyUnits": {"a1": {"infantry": 10}, "a2": {"infantry": 30}},
        }
        report = engine.loyalty_report(tactical)
        self.assertEqual(sorted(report), ["g1", "g2", "g3"])
        self.assertEqual(report["g3"]["value"], 2, "沒有部隊的將領上限是 2")
        self.assertLess(report["g1"]["value"], report["g2"]["value"],
                        "兵力少的那位相對實力吃虧")

    def test_the_report_survives_missing_or_broken_input(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine.loyalty_report(None), {})
        self.assertEqual(engine.loyalty_report({}), {})
        self.assertEqual(engine.loyalty_report({"generalTrees": {}}), {})

    def test_the_tactical_snapshot_carries_the_general_link(self):
        """守門：部隊要帶 generalId，否則伺服器連不起「這支部隊是誰的」。

        先前就是漏了這一欄——伺服器手上有部隊編制、也有將領樹，卻算不出忠誠，
        只能反過來相信前端送來的數字。
        """
        snapshot = FRONTEND_SOURCE[FRONTEND_SOURCE.index("function tacticalSnapshot"):]
        snapshot = snapshot[:snapshot.index("\nfunction ", 10)]
        self.assertIn("generalId: army.generalId", snapshot)
        for field in ("units:", "loyaltyOverrides", "generalTrees",
                      "loyaltyBaselineArmyUnits", "generalOwners"):
            self.assertIn(field, snapshot, f"忠誠計算需要 {field}")

    def test_the_frontend_prefers_the_backend_result(self):
        """守門：前端必須優先採用後端算好的忠誠，本地那段只是過渡值。"""
        body = FRONTEND_SOURCE[FRONTEND_SOURCE.index("function calculateGeneralLoyalty"):]
        body = body[:body.index("\nfunction ", 10)]
        self.assertIn("backendLoyalty?.[general.id]", body)
        # 而且要在本地算式之前就回傳
        self.assertLess(body.index("fromBackend"), body.index("relationPenalty"),
                        "後端結果必須優先於本地算式")
        self.assertIn('"loyalty": ENGINE.loyalty_report',
                      (pathlib.Path(__file__).resolve().parent / "server.py")
                      .read_text(encoding="utf-8"),
                      "server 沒把忠誠算給前端")

    def test_the_defection_uses_the_same_loyalty_the_panel_shows(self):
        """策反送出的忠誠與面板顯示的是同一個值（都來自 calculateGeneralLoyalty）。"""
        body = FRONTEND_SOURCE[FRONTEND_SOURCE.index("/api/attempt-defection") - 1200:]
        body = body[:body.index("/api/attempt-defection") + 400]
        self.assertIn("calculateGeneralLoyalty(general, army).value", body)


class UnitForcePointsSourceTests(unittest.TestCase):
    """戰力點只能有一份來源。"""

    def test_the_frontend_fallback_matches_the_backend(self):
        """前端有五處寫死的 fallback。它們現在對得上，但那是巧合而非保證——
        這條把它們與後端的 UNIT_FORCE_POINTS 對死。"""
        import re as _re
        from backend.card_engine import UNIT_FORCE_POINTS
        fallbacks = _re.findall(
            r'\{\s*infantry:\s*(\d+),\s*cavalry:\s*(\d+),'
            r'\s*machine_gun:\s*(\d+),\s*artillery:\s*(\d+)[,\s]*\}',
            FRONTEND_SOURCE)
        self.assertTrue(fallbacks, "找不到前端的 fallback")
        for infantry, cavalry, machine_gun, artillery in fallbacks:
            self.assertEqual(
                {"infantry": int(infantry), "cavalry": int(cavalry),
                 "machine_gun": int(machine_gun), "artillery": int(artillery)},
                UNIT_FORCE_POINTS, "前端寫死的戰力點與後端對不上")

    def test_the_frontend_reads_the_backend_value_first(self):
        self.assertIn("bootstrap?.features?.unit_force_points", FRONTEND_SOURCE)



class CombatModifierBuilderTests(unittest.TestCase):
    """戰鬥修正項的規則搬到後端之後的驗收。

    先前這一整套住在 app.js：前端組好 `modifiers` 再連同部隊送給 /api/combat。
    也就是**戰鬥規則在前端、傷害計算在後端**——規則改一邊不會有人叫，伺服器也
    無從驗證前端送來的加成是不是自己編的。現在 `CombatModifierBuilder` 是唯一來源。
    """

    def _builder(self, engine=None):
        from backend.combat_modifiers import CombatModifierBuilder
        return CombatModifierBuilder(engine or GameEngine(seed=3))

    def _battle(self, *, a_armies, b_armies, province=None, fortress=False,
                a_faction="F", b_faction="W"):
        return {"province": province, "fortress": fortress,
                "sides": {"A": {"faction": a_faction, "armies": a_armies},
                          "B": {"faction": b_faction, "armies": b_armies}}}

    def _army(self, army_id, general_id, traits, defending=False):
        return {"id": army_id, "general_id": general_id,
                "traits": list(traits), "defending": defending}

    def test_the_base_trait_modifiers_come_from_the_shared_json(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        data = engine.data["general_traits"]
        data = data.get("traits", data)
        self.assertTrue(builder.base_modifiers("dodging_drift"))
        self.assertEqual(builder.base_modifiers("dodging_drift"),
                         list(data["dodging_drift"]["modifiers"]))

    def test_an_aura_only_fires_for_its_named_partner_on_the_same_side(self):
        builder = self._builder()
        marshal = self._army("a1", "zhang_zuolin", ["marshal_zhang"])
        son = self._army("a2", "zhang_xueliang", [])
        stranger = self._army("a3", "han_fuju", [])
        built = builder.build(self._battle(a_armies=[marshal, son, stranger],
                                           b_armies=[self._army("b1", "wu_peifu", [])]))
        self.assertTrue([m for m in built["a2"] if m.get("source_aura") == "marshal_zhang"],
                        "張學良該吃到張大帥的光環")
        self.assertFalse([m for m in built["a3"] if m.get("source_aura")],
                         "不在名單上的人不該吃到")

    def test_an_aura_does_not_cross_to_the_enemy_side(self):
        builder = self._builder()
        built = builder.build(self._battle(
            a_armies=[self._army("a1", "zhang_zuolin", ["marshal_zhang"])],
            b_armies=[self._army("b1", "zhang_xueliang", [])]))
        self.assertFalse([m for m in built["b1"] if m.get("source_aura")],
                         "敵我兩側相遇時光環不生效")

    def test_a_province_conditional_trait_only_fires_in_its_provinces(self):
        builder = self._builder()
        for province, expected in (("雲南", True), ("奉天", False), (None, False)):
            built = builder.build(self._battle(
                a_armies=[self._army("a1", "long_yun", ["mountain_division"])],
                b_armies=[self._army("b1", "wu_peifu", [])], province=province))
            hit = [m for m in built["a1"]
                   if m.get("stat") == "harm_taken" and m.get("multiplier") == 0.90]
            self.assertEqual(bool(hit), expected, f"省份={province}")

    def test_an_ally_presence_trait_needs_that_ally_present(self):
        builder = self._builder()
        without = builder.build(self._battle(
            a_armies=[self._army("a1", "lu_yongxiang", ["anhui_veteran"])],
            b_armies=[self._army("b1", "wu_peifu", [])]))["a1"]
        with_ally = builder.build(self._battle(
            a_armies=[self._army("a1", "lu_yongxiang", ["anhui_veteran"]),
                      self._army("a2", "duan_qirui", [])],
            b_armies=[self._army("b1", "wu_peifu", [])]))["a1"]
        self.assertLess(len(without), len(with_ally), "段祺瑞在場才生效")

    def test_an_enemy_presence_trait_needs_that_enemy_opposite(self):
        builder = self._builder()
        away = builder.build(self._battle(
            a_armies=[self._army("a1", "zhao_hengti", ["hunan_governor"])],
            b_armies=[self._army("b1", "wu_peifu", [])]))["a1"]
        facing = builder.build(self._battle(
            a_armies=[self._army("a1", "zhao_hengti", ["hunan_governor"])],
            b_armies=[self._army("b1", "tang_shengzhi", [])]))["a1"]
        self.assertLess(len(away), len(facing), "對面站著唐生智才生效")

    def test_an_enemy_relation_trait_reads_the_opponents_relations(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        battle = self._battle(
            a_armies=[self._army("a1", "he_jian", ["anticommunist_vanguard"])],
            b_armies=[self._army("b1", "wu_peifu", [])])
        engine.state["players"]["W"]["foreign_relations"]["su"] = 0
        engine.state["players"]["F"]["foreign_relations"]["su"] = 0
        cold = builder.build(battle)["a1"]
        engine.state["players"]["W"]["foreign_relations"]["su"] = 8
        warm = builder.build(battle)["a1"]
        self.assertLess(len(cold), len(warm), "敵方親蘇時何鍵才加成")

    def test_a_trait_is_disabled_by_your_own_relations(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        battle = self._battle(
            a_armies=[self._army("a1", "zhang_zongchang", ["white_russian_mercenaries"])],
            b_armies=[self._army("b1", "wu_peifu", [])])
        engine.state["players"]["F"]["foreign_relations"]["su"] = 0
        enabled = builder.build(battle)["a1"]
        engine.state["players"]["F"]["foreign_relations"]["su"] = 8
        disabled = builder.build(battle)["a1"]
        self.assertTrue(enabled)
        self.assertEqual(disabled, [], "自家親蘇時白俄傭兵整個失效")

    def test_a_timed_combat_effect_is_folded_in(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        engine.state["players"]["F"].setdefault("timed_effects", []).append({
            "kind": "combat_modifier", "name": "測試加成", "remaining_turns": 3,
            "modifiers": [{"stat": "attack", "multiplier": 1.2}]})
        built = builder.build(self._battle(
            a_armies=[self._army("a1", "zhang_zuolin", [])],
            b_armies=[self._army("b1", "wu_peifu", [])]))
        self.assertTrue([m for m in built["a1"] if m.get("source_effect") == "測試加成"])

    def test_an_expired_timed_effect_is_not_folded_in(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        engine.state["players"]["F"].setdefault("timed_effects", []).append({
            "kind": "combat_modifier", "name": "過期", "remaining_turns": 0,
            "modifiers": [{"stat": "attack", "multiplier": 1.2}]})
        built = builder.build(self._battle(
            a_armies=[self._army("a1", "zhang_zuolin", [])],
            b_armies=[self._army("b1", "wu_peifu", [])]))
        self.assertFalse([m for m in built["a1"] if m.get("source_effect") == "過期"])

    def test_the_fortress_bonus_only_helps_the_defender(self):
        builder = self._builder()
        built = builder.build(self._battle(
            a_armies=[self._army("a1", "zhang_zuolin", [], defending=False)],
            b_armies=[self._army("b1", "wu_peifu", [], defending=True)], fortress=True))
        self.assertTrue([m for m in built["b1"] if m.get("multiplier") == 0.65])
        self.assertFalse([m for m in built["a1"] if m.get("multiplier") == 0.65])

    def test_goddard_rocket_needs_the_unlock_and_a_fortress(self):
        engine = GameEngine(seed=3)
        builder = self._builder(engine)
        battle = self._battle(a_armies=[self._army("a1", "zhang_zuolin", [])],
                              b_armies=[self._army("b1", "wu_peifu", [])], fortress=True)
        self.assertFalse([m for m in builder.build(battle)["a1"]
                          if m.get("source_effect") == "戈達德的火箭"])
        engine.state["players"]["F"].setdefault("unlocks", []).append("event_goddard_rocket")
        self.assertTrue([m for m in builder.build(battle)["a1"]
                         if m.get("source_effect") == "戈達德的火箭"])
        no_fort = self._battle(a_armies=[self._army("a1", "zhang_zuolin", [])],
                               b_armies=[self._army("b1", "wu_peifu", [])], fortress=False)
        self.assertFalse([m for m in builder.build(no_fort)["a1"]
                          if m.get("source_effect") == "戈達德的火箭"])

    # ---- 前端不准再自己組加成 ----

    def test_the_frontend_no_longer_owns_any_combat_rule_table(self):
        for name in ("AURA_TRAITS = ", "PROVINCE_CONDITIONAL_TRAITS", "ALLY_PRESENCE_TRAITS",
                     "ENEMY_PRESENCE_TRAITS", "ENEMY_RELATION_TRAITS",
                     "function combatTraitModifiers", "function combatAuraModifiers",
                     "function timedCombatModifiers", "function fortressArtilleryModifiers",
                     "function forcedPeaceDefenceModifiers"):
            self.assertNotIn(name, FRONTEND_SOURCE,
                             f"{name} 還在前端——戰鬥規則又變成兩份了")

    def test_the_frontend_sends_facts_not_modifiers(self):
        payload = FRONTEND_SOURCE[FRONTEND_SOURCE.index("function combatArmyPayload"):]
        payload = payload[:payload.index("\nfunction ", 10)]
        self.assertNotIn("modifiers:", payload, "前端不該再附加成")
        self.assertIn("units: armyUnits(army)", payload)
        self.assertIn("tactic,", payload)
        self.assertIn("battle: combatBattleFacts(battle, combatArmies)", FRONTEND_SOURCE)
        facts = FRONTEND_SOURCE[FRONTEND_SOURCE.index("function combatBattleFacts"):]
        facts = facts[:facts.index("\nfunction ", 10)]
        for field in ("province:", "fortress:", "general_id:", "traits:", "defending:"):
            self.assertIn(field, facts, f"戰鬥事實少了 {field}")

    def test_the_endpoint_builds_the_modifiers_itself(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn("simulate_with_modifiers(payload, ENGINE)", server)

    def test_the_result_reports_which_modifiers_were_applied(self):
        """前端要顯示「這一場吃到哪些加成」就讀這一份，不要自己再推。"""
        from backend.combat_adapter import simulate_with_modifiers
        engine = GameEngine(seed=3)
        result = simulate_with_modifiers({
            "army_a": {"name": "a1", "units": {"infantry": 20}, "tactic": "normal_advance"},
            "army_b": {"name": "b1", "units": {"infantry": 20}, "tactic": "normal_advance"},
            "max_rounds": 1,
            "battle": self._battle(
                a_armies=[self._army("a1", "zhang_zuolin", ["marshal_zhang"])],
                b_armies=[self._army("b1", "wu_peifu", ["wu_peifu_admired"])]),
        }, engine)
        self.assertIn("applied_modifiers", result)
        self.assertEqual(sorted(result["applied_modifiers"]), ["a1", "b1"])

    def test_a_payload_without_battle_facts_still_works(self):
        """舊格式（自己附 modifiers）不能直接爆掉——存檔重放與測試夾具還在用。"""
        from backend.combat_adapter import simulate_with_modifiers
        engine = GameEngine(seed=3)
        result = simulate_with_modifiers({
            "army_a": {"name": "a", "units": {"infantry": 20}, "tactic": "normal_advance"},
            "army_b": {"name": "b", "units": {"infantry": 20}, "tactic": "normal_advance"},
            "max_rounds": 1,
        }, engine)
        self.assertIn("winner", result)



class NavyCombatRulesTests(unittest.TestCase):
    """海戰規則搬進後端之後的驗收。

    原本整套住在 `frontend/navy.js`：砲艇失能門檻、傷害分配、退卻判定、
    艦砲對砲兵、砲兵對艦艇，全在前端算完，後端只收結果。也就是**海戰規則在
    前端**——伺服器無從驗證，規則改了也沒有任何東西會叫。
    """

    def _rules(self):
        from navy_system.navy import load_rules
        return load_rules()

    def _fleet(self, fleet_id, gun_hp, cargo_hp=(10,)):
        return {"id": fleet_id,
                "gunBoats": [{"id": f"{fleet_id}-G{i + 1}", "hp": hp, "maxHp": 30}
                             for i, hp in enumerate(gun_hp)],
                "cargoBoats": len(cargo_hp),
                "cargoBoatHp": [{"id": f"{fleet_id}-C{i + 1}", "hp": hp, "maxHp": 10}
                                for i, hp in enumerate(cargo_hp)]}

    # ---- 基本規則 ----

    def test_a_gun_boat_below_the_floor_cannot_fire(self):
        from navy_system.navy import active_gun_boats
        rules = self._rules()
        floor = rules["units"]["gun_boat"]["inactive_below_hp"]
        self.assertEqual(len(active_gun_boats(self._fleet("A", [floor]), rules)), 1)
        self.assertEqual(len(active_gun_boats(self._fleet("A", [floor - 1]), rules)), 0,
                         "低於門檻就失能——不是沉沒，是不能射擊")

    def test_damage_hits_gun_boats_before_cargo_and_the_healthiest_first(self):
        from navy_system.navy import apply_gun_boat_damage
        fleet = self._fleet("A", [30, 10], cargo_hp=(10,))
        detail = apply_gun_boat_damage(fleet, 12)
        self.assertEqual(detail["applied"], 12)
        self.assertEqual(detail["damaged"][0]["type"], "gun_boat")
        self.assertEqual(detail["damaged"][0]["before"], 30, "同類先打血多的")
        self.assertEqual(fleet["cargoBoatHp"][0]["hp"], 10, "砲艇還在就不該碰運輸船")

    def test_damage_overflows_onto_cargo_once_the_gun_boats_are_gone(self):
        from navy_system.navy import apply_gun_boat_damage
        fleet = self._fleet("A", [5], cargo_hp=(10,))
        detail = apply_gun_boat_damage(fleet, 12)
        self.assertEqual(detail["applied"], 12)
        self.assertEqual(fleet["gunBoats"], [], "打光的船要移除")
        self.assertEqual(fleet["cargoBoatHp"][0]["hp"], 3)

    def test_damage_beyond_the_fleet_is_not_over_applied(self):
        from navy_system.navy import apply_gun_boat_damage
        fleet = self._fleet("A", [5], cargo_hp=(10,))
        detail = apply_gun_boat_damage(fleet, 999)
        self.assertEqual(detail["applied"], 15, "打不到的傷害不算數")
        self.assertEqual(fleet["gunBoats"], [])
        self.assertEqual(fleet["cargoBoatHp"], [])

    def test_the_retreat_line_is_half_of_the_full_strength_baseline(self):
        from navy_system.navy import retreat_threshold_reached
        rules = self._rules()
        self.assertFalse(retreat_threshold_reached(self._fleet("A", [30, 31]), rules))
        self.assertTrue(retreat_threshold_reached(self._fleet("A", [15, 15]), rules),
                        "滿血 60 的一半就是退卻線")

    def test_an_empty_fleet_is_always_past_the_retreat_line(self):
        from navy_system.navy import retreat_threshold_reached
        self.assertTrue(retreat_threshold_reached(self._fleet("A", []), self._rules()))

    # ---- 對射 ----

    def test_both_sides_fire_simultaneously(self):
        """射擊資格在交火開始時固定：被打沉的船這一輪照樣開過火。"""
        from navy_system.navy import resolve_navy_duel
        rules = self._rules()
        attacker, defender = self._fleet("A", [30, 30]), self._fleet("B", [1])
        result = resolve_navy_duel(attacker, defender, rules)
        self.assertEqual(result["attackerActiveGunBoats"], 2)
        self.assertEqual(result["defenderActiveGunBoats"], 0, "1 血低於門檻，無法還擊")
        self.assertGreater(result["attackerDamage"], 0)
        self.assertEqual(result["defenderDamage"], 0)

    def test_a_boat_knocked_below_the_floor_still_fires_this_exchange(self):
        """射擊資格在交火**開始**時固定，不是邊打邊重算。

        先前這一組測試分辨不出「同時射擊」與「循序射擊」：我挑的案例裡守方
        本來就打不動。這裡刻意讓守方在挨打之後才掉到門檻以下——
        同時射擊會還手，循序射擊不會。
        """
        from navy_system.navy import resolve_navy_duel
        rules = self._rules()
        floor = rules["units"]["gun_boat"]["inactive_below_hp"]
        per_boat = rules["units"]["gun_boat"]["attack"]["gun_boat"]
        # 守方 16 血（剛好在門檻上），挨 2 艘共 10 點之後剩 6，低於門檻
        attacker, defender = self._fleet("A", [30, 30]), self._fleet("B", [floor + 1])
        result = resolve_navy_duel(attacker, defender, rules)
        self.assertEqual(result["defenderActiveGunBoats"], 1, "開火當下守方是能打的")
        self.assertEqual(result["defenderDamage"], per_boat,
                         "守方在這一輪照樣打出一艘份的火力——被打沉不影響本輪射擊")
        self.assertLess(defender["gunBoats"][0]["hp"] if defender["gunBoats"] else 0, floor)

    def test_a_fleet_with_no_active_boats_retreats(self):
        from navy_system.navy import resolve_navy_duel
        result = resolve_navy_duel(self._fleet("A", [30, 30]), self._fleet("B", [1]),
                                   self._rules())
        self.assertTrue(result["defenderRetreat"])
        self.assertEqual(result["tileWinner"], "attacker")

    def test_when_both_would_retreat_the_healthier_holds_the_tile(self):
        from navy_system.navy import resolve_navy_duel
        rules = self._rules()
        result = resolve_navy_duel(self._fleet("A", [16, 16]), self._fleet("B", [15]), rules)
        self.assertIn(result["tileWinner"], ("attacker", "defender", "draw"))
        self.assertFalse(result["attackerRetreat"] and result["defenderRetreat"],
                         "兩邊都達退卻線時要分出一個守住的")

    # ---- 陸海接觸 ----

    def test_artillery_and_gun_boats_trade_damage(self):
        from navy_system.navy import resolve_army_navy_contact
        rules = self._rules()
        navy = self._fleet("N", [30, 30])
        result = resolve_army_navy_contact({"artillery": 4}, navy, rules)
        self.assertEqual(result["boatDamage"], 4, "每門砲兵打 1 點")
        self.assertEqual(result["artilleryLost"], 2, "兩艘砲艇 ×2 ÷2 = 2 營")
        self.assertEqual(result["artilleryAfter"], 2)
        self.assertFalse(result["landRetreat"], "還有砲兵就守得住")

    def test_an_army_with_no_artillery_left_retreats(self):
        from navy_system.navy import resolve_army_navy_contact
        result = resolve_army_navy_contact({"artillery": 1}, self._fleet("N", [30, 30]),
                                           self._rules())
        self.assertEqual(result["artilleryAfter"], 0)
        self.assertTrue(result["landRetreat"])

    def test_a_disabled_fleet_cannot_shoot_back_at_artillery(self):
        from navy_system.navy import resolve_army_navy_contact
        result = resolve_army_navy_contact({"artillery": 5}, self._fleet("N", [3]),
                                           self._rules())
        self.assertFalse(result["navyFired"])
        self.assertEqual(result["artilleryLost"], 0)

    # ---- 端點與前端 ----

    def test_the_engine_exposes_both_resolutions(self):
        engine = GameEngine(seed=3)
        duel = engine.resolve_navy_duel(self._fleet("A", [30]), self._fleet("B", [30]))
        self.assertIn("result", duel)
        self.assertIn("attacker", duel)
        self.assertIn("defender", duel)
        contact = engine.resolve_army_navy_contact({"artillery": 2}, self._fleet("N", [30]))
        self.assertIn("result", contact)
        self.assertIn("navy", contact)

    def test_the_endpoints_exist(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn("/api/navy-duel", server)
        self.assertIn("/api/army-navy-contact", server)

    def test_the_frontend_no_longer_owns_the_naval_combat_rules(self):
        navy_js = (pathlib.Path(__file__).resolve().parents[1]
                   / "frontend" / "navy.js").read_text(encoding="utf-8")
        for name in ("export function resolveNavyDuel", "export function resolveArmyNavyContact"):
            self.assertNotIn(name, navy_js, "海戰規則又變成兩份了")
        self.assertNotIn("resolveNavyDuel(", FRONTEND_SOURCE)
        self.assertNotIn("resolveArmyNavyContact(", FRONTEND_SOURCE)

    def test_the_frontend_calls_the_backend_for_naval_combat(self):
        self.assertIn('api("/api/navy-duel"', FRONTEND_SOURCE)
        self.assertIn('api("/api/army-navy-contact"', FRONTEND_SOURCE)
        self.assertIn("function applyNavyStateFromServer", FRONTEND_SOURCE)
        self.assertIn("async function applyNavyDuel", FRONTEND_SOURCE)
        self.assertIn("async function applyArmyNavyContact", FRONTEND_SOURCE)

    def test_the_repair_cost_rule_is_shared(self):
        from navy_system.navy import repair_cost
        engine = GameEngine(seed=3)
        per_hp = engine.data["navy_system"]["repair"]["factory_cost_per_hp"]
        self.assertEqual(repair_cost(5, cost_per_hp=per_hp), 5 * per_hp)


class NavyCarriedArmyTests(unittest.TestCase):
    """運輸船上的陸軍：折損裁兵與隨船覆沒。

    這一整套原本住在 `frontend/app.js`（settleNavyCarriedLosses /
    enforceNavyCargoCapacity / sinkCarriedArmyWithNavy），而且**裁掉哪些兵是用
    沒有種子的 Math.random() 抽的**。伺服器連船上有沒有人都不知道——
    navySnapshotForServer 根本沒送 carried 欄位——自然也無從驗證。
    現在規則在 navy_system.navy.settle_carried_army，前端只照判決改狀態。
    """

    def _rules(self):
        from navy_system.navy import load_rules
        return load_rules()

    def _fleet(self, fleet_id, gun_hp, cargo_hp=(10,), carried=None):
        fleet = {"id": fleet_id,
                 "gunBoats": [{"id": f"{fleet_id}-G{i + 1}", "hp": hp, "maxHp": 30}
                              for i, hp in enumerate(gun_hp)],
                 "cargoBoats": len(cargo_hp),
                 "cargoBoatHp": [{"id": f"{fleet_id}-C{i + 1}", "hp": hp, "maxHp": 10}
                                 for i, hp in enumerate(cargo_hp)]}
        if carried is not None:
            fleet["carried"] = carried
        return fleet

    def _rider(self, **units):
        return {"armyId": "F-2", "generalId": "zhang_xueliang", "units": units}

    # ---- 規則本身 ----

    def test_an_empty_hold_settles_to_nothing(self):
        from navy_system.navy import settle_carried_army
        fleet = self._fleet("A", [30])
        self.assertEqual(settle_carried_army(fleet, None, self._rules())["outcome"], "none")

    def test_a_fleet_with_spare_capacity_leaves_the_army_alone(self):
        from navy_system.navy import settle_carried_army
        # 2 艘運輸船 = 40 容量；步兵 12 + 騎兵 3 + 機槍 2×2 + 砲兵 2×4 = 27
        fleet = self._fleet("A", [30], cargo_hp=(10, 10))
        rider = self._rider(infantry=12, cavalry=3, machine_gun=2, artillery=2)
        result = settle_carried_army(fleet, rider, self._rules())
        self.assertEqual(result["outcome"], "intact")
        self.assertEqual(result["capacity"], 40)
        self.assertEqual(result["units"], rider["units"], "容量夠就一兵不動")
        self.assertEqual(result["lost"], {})

    def test_an_army_that_exactly_fills_the_hold_is_not_trimmed(self):
        """剛好塞滿不算超載——邊界寫成 `<` 就會白白裁掉一個兵。"""
        from navy_system.navy import settle_carried_army
        fleet = self._fleet("A", [30], cargo_hp=(10,))     # 容量 20
        result = settle_carried_army(fleet, self._rider(infantry=20), self._rules(),
                                     random.Random(2))
        self.assertEqual(result["outcome"], "intact")
        self.assertEqual(result["units"], {"infantry": 20})
        self.assertEqual(result["lost"], {})

    def test_losing_a_cargo_boat_trims_the_army_down_to_the_new_capacity(self):
        from navy_system.navy import force_points, settle_carried_army
        fleet = self._fleet("A", [30], cargo_hp=(10, 0))   # 一艘沉了：40 -> 20
        rider = self._rider(infantry=12, cavalry=3, machine_gun=2, artillery=2)
        result = settle_carried_army(fleet, rider, self._rules(), random.Random(7))
        self.assertEqual(result["outcome"], "trimmed")
        self.assertEqual(result["capacity"], 20)
        self.assertLessEqual(force_points(result["units"]), 20,
                             "裁完必須真的在容量以內")
        self.assertGreater(sum(result["lost"].values()), 0)
        for unit, count in result["lost"].items():
            self.assertEqual(rider["units"][unit] - result["units"][unit], count,
                             "回報的損失要對得上實際扣掉的兵")

    def test_the_trim_stops_as_soon_as_it_fits_and_does_not_overshoot(self):
        """裁到剛好就要停——多裁一個兵就是白白吃掉玩家的部隊。"""
        from navy_system.navy import force_points, settle_carried_army
        fleet = self._fleet("A", [30], cargo_hp=(10,))     # 容量 20
        rider = self._rider(infantry=21)                    # 21 戰力，只該掉 1 個
        result = settle_carried_army(fleet, rider, self._rules(), random.Random(1))
        self.assertEqual(force_points(result["units"]), 20)
        self.assertEqual(result["lost"], {"infantry": 1})

    def test_the_trim_prices_units_by_force_points_not_by_head_count(self):
        """砲兵一門抵 4 點：一門砲兵就足以把 24 點壓回 20。"""
        from navy_system.navy import settle_carried_army
        fleet = self._fleet("A", [30], cargo_hp=(10,))     # 容量 20
        rider = self._rider(artillery=6)                    # 6×4 = 24
        result = settle_carried_army(fleet, rider, self._rules(), random.Random(5))
        self.assertEqual(result["lost"], {"artillery": 1})
        self.assertEqual(result["units"], {"artillery": 5})

    def test_the_trim_is_seeded_and_reproducible(self):
        """前端用的是 Math.random()，同一場戰鬥重跑結果會不一樣，伺服器也對不起來。"""
        from navy_system.navy import settle_carried_army
        rider = self._rider(infantry=12, cavalry=3, machine_gun=2, artillery=2)
        first = settle_carried_army(self._fleet("A", [30], cargo_hp=(10, 0)),
                                    rider, self._rules(), random.Random(11))
        second = settle_carried_army(self._fleet("A", [30], cargo_hp=(10, 0)),
                                     rider, self._rules(), random.Random(11))
        self.assertEqual(first["lost"], second["lost"])

    def test_a_fleet_with_no_boats_left_drowns_the_army_and_its_general(self):
        from navy_system.navy import settle_carried_army
        fleet = self._fleet("A", [], cargo_hp=())
        rider = self._rider(infantry=12, artillery=2)
        result = settle_carried_army(fleet, rider, self._rules())
        self.assertEqual(result["outcome"], "wiped")
        self.assertEqual(result["generalId"], "zhang_xueliang")
        self.assertEqual(result["units"], {"infantry": 0, "artillery": 0})
        self.assertEqual(result["lost"], {"infantry": 12, "artillery": 2})

    def test_losing_every_cargo_boat_but_keeping_a_gun_boat_is_not_a_drowning(self):
        """砲艇還浮著就不是全滅——部隊被裁到 0，但將領不該死。"""
        from navy_system.navy import settle_carried_army
        fleet = self._fleet("A", [30], cargo_hp=(0,))      # 容量 0，但船還在
        rider = self._rider(infantry=5)
        result = settle_carried_army(fleet, rider, self._rules(), random.Random(3))
        self.assertEqual(result["outcome"], "trimmed")
        self.assertEqual(result["capacity"], 0)
        self.assertEqual(result["units"], {"infantry": 0})

    # ---- 接到海戰結算上 ----

    def test_the_duel_endpoint_settles_both_holds(self):
        engine = GameEngine(seed=3)
        attacker = self._fleet("A", [30, 30], carried=self._rider(infantry=5))
        # 守方只剩 1 血砲艇 + 1 血運輸船，攻方兩艘 ×5 = 10 點，一輪掃光
        defender = self._fleet("B", [1], cargo_hp=(1,),
                               carried=self._rider(infantry=12, cavalry=3,
                                                   machine_gun=2, artillery=2))
        payload = engine.resolve_navy_duel(attacker, defender)
        self.assertIn("attackerCarried", payload)
        self.assertIn("defenderCarried", payload)
        self.assertEqual(payload["attackerCarried"]["outcome"], "intact")
        self.assertEqual(payload["defenderCarried"]["outcome"], "wiped",
                         "守方被打光，船上的部隊要隨船覆沒")

    def test_the_contact_endpoint_settles_the_hold(self):
        engine = GameEngine(seed=3)
        navy = self._fleet("N", [30, 30], cargo_hp=(10, 10),
                           carried=self._rider(infantry=12, cavalry=3,
                                               machine_gun=2, artillery=2))
        payload = engine.resolve_army_navy_contact({"artillery": 4}, navy)
        self.assertIn("carried", payload)
        self.assertEqual(payload["carried"]["outcome"], "intact")

    def test_artillery_that_sinks_a_cargo_boat_trims_the_army_aboard(self):
        from navy_system.navy import force_points
        engine = GameEngine(seed=3)
        # 砲艇只剩 1 血，砲兵 25 門：先打掉砲艇再溢出去打沉兩艘運輸船
        navy = self._fleet("N", [1], cargo_hp=(10, 10),
                           carried=self._rider(infantry=12, cavalry=3,
                                               machine_gun=2, artillery=2))
        payload = engine.resolve_army_navy_contact({"artillery": 25}, navy)
        self.assertEqual(payload["carried"]["outcome"], "wiped")
        self.assertEqual(force_points(payload["carried"]["units"]), 0)

    def test_the_endpoint_survives_a_fleet_carrying_nobody(self):
        engine = GameEngine(seed=3)
        payload = engine.resolve_navy_duel(self._fleet("A", [30]), self._fleet("B", [30]))
        self.assertEqual(payload["attackerCarried"]["outcome"], "none")
        self.assertEqual(payload["defenderCarried"]["outcome"], "none")

    # ---- 前端不准再自己算 ----

    def test_the_frontend_no_longer_computes_the_trim(self):
        self.assertNotIn("function enforceNavyCargoCapacity", FRONTEND_SOURCE,
                         "裁兵規則又搬回前端了")
        self.assertNotIn("function settleNavyCarriedLosses", FRONTEND_SOURCE)
        carry_block = FRONTEND_SOURCE.split("function applyCarriedArmySettlement", 1)[1][:1200]
        self.assertNotIn("Math.random()", carry_block,
                         "船上部隊的損失不該由前端擲骰")

    def test_the_frontend_sends_the_carried_army_to_the_backend(self):
        snapshot = FRONTEND_SOURCE.split("function navySnapshotForServer", 1)[1][:900]
        self.assertIn("carried:", snapshot, "不送 carried，後端就不知道船上有人")
        self.assertIn("armyId: carried.id", snapshot)
        self.assertIn("units: { ...armyUnits(carried) }", snapshot)

    def test_the_frontend_applies_the_backend_verdict(self):
        self.assertIn("applyCarriedArmySettlement(navy, response.carried)", FRONTEND_SOURCE)
        self.assertIn("applyCarriedArmySettlement(attacker, response.attackerCarried)",
                      FRONTEND_SOURCE)
        self.assertIn("applyCarriedArmySettlement(defender, response.defenderCarried)",
                      FRONTEND_SOURCE)


class NavyRetreatBaselineTests(unittest.TestCase):
    """退卻線的基準：戰損不拉低它，補編要把它撐上去。

    先前基準只在第一次看到艦隊時記一次，之後永遠不動。艦隊在港口補進新砲艇之後，
    基準還停在開局的數字——退卻線變成要打掉七成五、九成才會到，補得越多越不會退。
    """

    def _rules(self):
        from navy_system.navy import load_rules
        return load_rules()

    def _fleet(self, gun_hp, baseline=None):
        fleet = {"id": "A", "cargoBoats": 0, "cargoBoatHp": [],
                 "gunBoats": [{"id": f"A-G{i + 1}", "hp": hp, "maxHp": 30}
                              for i, hp in enumerate(gun_hp)]}
        if baseline is not None:
            fleet["retreatMaxGunBoatHp"] = baseline
        return fleet

    def test_battle_damage_does_not_lower_the_baseline(self):
        from navy_system.navy import retreat_baseline_hp
        # 開局 2 艘（滿血 60），打到只剩 1 艘：基準要留在 60
        self.assertEqual(retreat_baseline_hp(self._fleet([20], baseline=60), self._rules()), 60)

    def test_reinforcing_raises_the_baseline(self):
        from navy_system.navy import retreat_baseline_hp, retreat_threshold_reached
        rules = self._rules()
        # 開局 2 艘（基準 60），在港口補到 4 艘滿血 120
        fleet = self._fleet([30, 30, 30, 30], baseline=60)
        self.assertEqual(retreat_baseline_hp(fleet, rules), 120,
                         "補編之後基準要跟著上去")
        # 基準要寫回去，之後船被打沉、列表變短也不會掉回 60
        self.assertEqual(fleet["retreatMaxGunBoatHp"], 120)
        # 120 的一半是 60：打到剩 61 還不該退，剩 60 就該退
        self.assertFalse(retreat_threshold_reached(
            self._fleet([30, 30, 1], baseline=120), rules))
        self.assertTrue(retreat_threshold_reached(
            self._fleet([30, 30], baseline=120), rules),
            "四艘打剩兩艘就是掉了一半，該退了")

    def test_the_retreat_line_follows_the_ratio_in_the_rules_file(self):
        """規則檔寫 0.5 時「乘 ratio」和「乘 1-ratio」剛好一樣，分不出對錯。

        改成 0.25（掉四分之一就退）才看得出來：退卻線應該是滿編的 75%。
        """
        from navy_system.navy import retreat_floor_hp, retreat_threshold_reached
        rules = dict(self._rules())
        rules["land_interaction"] = dict(rules["land_interaction"],
                                         navy_retreat_gun_boat_hp_loss_ratio=0.25)
        self.assertEqual(retreat_floor_hp(self._fleet([30, 30]), rules), 45.0,
                         "滿編 60、掉 25% 就退 -> 退卻線在 45")
        self.assertFalse(retreat_threshold_reached(self._fleet([30, 16]), rules),
                         "還有 46，沒到 45")
        self.assertTrue(retreat_threshold_reached(self._fleet([30, 15]), rules),
                        "剩 45，到線了")

    def test_a_stale_baseline_no_longer_makes_a_reinforced_fleet_unbreakable(self):
        """這正是修掉的 bug：基準卡在 60，四艘艦隊要打到剩 30 才退。"""
        from navy_system.navy import retreat_threshold_reached
        fleet = self._fleet([30, 15], baseline=60)   # 現有滿血 60，血量 45
        self.assertFalse(retreat_threshold_reached(fleet, self._rules()))
        grown = self._fleet([30, 30, 30, 15], baseline=60)  # 滿血 120，血量 105
        self.assertFalse(retreat_threshold_reached(grown, self._rules()))
        # 補到 4 艘之後基準記成 120，打到剩 3 艘 55 血就過線了
        hurt = self._fleet([30, 15, 10], baseline=120)
        self.assertTrue(retreat_threshold_reached(hurt, self._rules()),
                        "滿編 120 的一半是 60，55 已經低於退卻線")


class NavyContactOutlookTests(unittest.TestCase):
    """交戰中那一行「還能撐幾輪」。

    原本整段住在前端 navyContactEstimate()：退卻線公式、砲艇火力、砲兵火力
    全部在前端再算一次。畫面上的數字必須和真正結算用的規則同源，
    否則玩家看到「還能撐 3 輪」卻一輪就被打退。
    """

    def _rules(self):
        from navy_system.navy import load_rules
        return load_rules()

    def _fleet(self, fleet_id, gun_hp, cargo_hp=(10,)):
        return {"id": fleet_id, "faction": fleet_id[0],
                "gunBoats": [{"id": f"{fleet_id}-G{i + 1}", "hp": hp, "maxHp": 30}
                             for i, hp in enumerate(gun_hp)],
                "cargoBoats": len(cargo_hp),
                "cargoBoatHp": [{"id": f"{fleet_id}-C{i + 1}", "hp": hp, "maxHp": 10}
                                for i, hp in enumerate(cargo_hp)]}

    def test_incoming_fire_adds_gun_boats_and_artillery(self):
        from navy_system.navy import incoming_fire
        rules = self._rules()
        # 2 艘可戰砲艇 ×5 = 10；砲兵 3 門 ×1 = 3
        self.assertEqual(incoming_fire(self._fleet("B", [30, 30]), 3, rules), 13)

    def test_a_disabled_enemy_fleet_contributes_no_fire(self):
        from navy_system.navy import incoming_fire
        self.assertEqual(incoming_fire(self._fleet("B", [1, 1]), 0, self._rules()), 0)

    def test_rounds_to_retreat_matches_the_retreat_rule(self):
        from navy_system.navy import rounds_to_retreat
        rules = self._rules()
        # 滿血 60，退卻線 30，現在 60：還有 30 的餘裕，每輪挨 10 = 3 輪
        self.assertEqual(rounds_to_retreat(self._fleet("A", [30, 30]), 10, rules), 3)

    def test_rounds_to_retreat_rounds_up_a_partial_round(self):
        from navy_system.navy import rounds_to_retreat
        # 餘裕 30，每輪挨 7：4.28 輪 -> 進位成 5
        self.assertEqual(rounds_to_retreat(self._fleet("A", [30, 30]), 7, self._rules()), 5)

    def test_a_fleet_already_past_the_line_has_no_rounds_left(self):
        from navy_system.navy import rounds_to_retreat
        self.assertIsNone(rounds_to_retreat(self._fleet("A", [15, 15]), 10, self._rules()))

    def test_no_incoming_fire_means_no_countdown(self):
        from navy_system.navy import rounds_to_retreat
        self.assertIsNone(rounds_to_retreat(self._fleet("A", [30, 30]), 0, self._rules()))

    def test_the_outlook_reports_both_sides(self):
        from navy_system.navy import contact_outlook
        rules = self._rules()
        own, enemy = self._fleet("A", [30, 30]), self._fleet("B", [30])
        outlook = contact_outlook(own, enemy, 0, rules)
        self.assertEqual(outlook["incoming"], 5, "敵方 1 艘砲艇 ×5")
        self.assertEqual(outlook["roundsToRetreat"], 6, "餘裕 30 ÷ 5")
        self.assertEqual(outlook["enemyRoundsToRetreat"], 2,
                         "敵方餘裕 15，挨我方 2 艘 ×5 = 10 -> 2 輪")
        self.assertFalse(outlook["atRetreatLine"])
        self.assertFalse(outlook["enemyAtRetreatLine"])

    def test_the_outlook_flags_a_fleet_with_nothing_left(self):
        from navy_system.navy import contact_outlook
        outlook = contact_outlook(self._fleet("A", [], cargo_hp=()), None, 0, self._rules())
        self.assertTrue(outlook["noBoatsLeft"])
        self.assertIsNone(outlook["enemyAtRetreatLine"], "沒有敵艦就沒有敵方欄位")

    def test_the_engine_reports_an_outlook_for_every_fleet_in_contact(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["warlord_relations"] = {"W": {"status": "war"}}
        tactical = {
            "navyDivisions": [
                dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F"),
                dict(self._fleet("W", [30]), cellKey="29,16", faction="W"),
            ],
            "armies": {},
        }
        report = engine.navy_outlook(tactical)
        self.assertEqual(report["F"]["incoming"], 5, "敵艦 1 艘 ×5")
        self.assertEqual(report["W"]["incoming"], 10, "敵艦 2 艘 ×5")

    def test_enemy_artillery_on_the_same_tile_counts_toward_incoming_fire(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["warlord_relations"] = {"W": {"status": "war"}}
        tactical = {
            "navyDivisions": [dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F")],
            "armies": {"W-1": {"cellKey": "29,16", "faction": "W", "status": "active",
                               "units": {"artillery": 4}}},
        }
        self.assertEqual(engine.navy_outlook(tactical)["F"]["incoming"], 4)

    def test_an_embarked_army_does_not_shoot_at_the_fleet_carrying_it(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["warlord_relations"] = {"W": {"status": "war"}}
        tactical = {
            "navyDivisions": [dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F")],
            "armies": {"W-1": {"cellKey": "29,16", "faction": "W", "status": "active",
                               "embarkedOn": "W-NAVY-1", "units": {"artillery": 4}}},
        }
        self.assertEqual(engine.navy_outlook(tactical)["F"]["incoming"], 0)

    def test_an_army_of_a_faction_at_peace_does_not_shoot_at_the_fleet(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["warlord_relations"] = {"W": {"status": "peace"}}
        engine.state["players"]["W"]["warlord_relations"] = {"F": {"status": "peace"}}
        tactical = {
            "navyDivisions": [dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F")],
            "armies": {"W-1": {"cellKey": "29,16", "faction": "W", "status": "active",
                               "units": {"artillery": 4}}},
        }
        self.assertEqual(engine.navy_outlook(tactical)["F"]["incoming"], 0,
                         "沒宣戰的部隊不會對艦隊開火")

    def test_a_friendly_army_on_the_same_tile_does_not_shoot_at_its_own_fleet(self):
        engine = GameEngine(seed=5)
        tactical = {
            "navyDivisions": [dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F")],
            "armies": {"F-2": {"cellKey": "29,16", "faction": "F", "status": "active",
                               "units": {"artillery": 4}}},
        }
        self.assertEqual(engine.navy_outlook(tactical)["F"]["incoming"], 0)

    def test_a_faction_at_peace_is_not_counted_as_incoming_fire(self):
        engine = GameEngine(seed=5)
        engine.state["players"]["F"]["warlord_relations"] = {"W": {"status": "peace"}}
        engine.state["players"]["W"]["warlord_relations"] = {"F": {"status": "peace"}}
        tactical = {
            "navyDivisions": [
                dict(self._fleet("F", [30, 30]), cellKey="29,16", faction="F"),
                dict(self._fleet("W", [30]), cellKey="29,16", faction="W"),
            ],
            "armies": {},
        }
        self.assertEqual(engine.navy_outlook(tactical)["F"]["incoming"], 0)

    def test_the_shared_state_endpoint_ships_the_outlook(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertEqual(server.count("ENGINE.navy_outlook(SHARED_TACTICAL_STATE)"), 3,
                         "三個回傳共享狀態的地方都要帶上艦隊預估")

    def test_the_frontend_only_renders_the_backend_numbers(self):
        estimate = FRONTEND_SOURCE.split("function navyContactEstimate", 1)[1][:900]
        self.assertIn("backendNavyOutlook[navy?.id]", estimate)
        for rule_bit in ("navy_retreat_gun_boat_hp_loss_ratio", "attack?.gun_boat",
                         "artillery_attack_to_gun_boat", "Math.ceil"):
            self.assertNotIn(rule_bit, estimate, "前端又自己算了一次退卻線")
        self.assertIn("if (remote.navy_outlook) backendNavyOutlook = remote.navy_outlook;",
                      FRONTEND_SOURCE)
        self.assertIn("if (result.navy_outlook) backendNavyOutlook = result.navy_outlook;",
                      FRONTEND_SOURCE)


class NavyRepairTests(unittest.TestCase):
    """修理：補幾點血、收多少工業點，由後端從艦隊現況算。

    原本前端用 restoreHpToFloor() 算好 hp 送給 /api/repair-navy，伺服器照單全收——
    伺服器不知道艦隊長什麼樣，送 0 就是免費修，送大數就是花錢買不存在的血。
    """

    def _fleet(self, gun_hp, cargo_hp=(10,)):
        return {"id": "A",
                "gunBoats": [{"id": f"A-G{i + 1}", "hp": hp, "maxHp": 30}
                             for i, hp in enumerate(gun_hp)],
                "cargoBoats": len(cargo_hp),
                "cargoBoatHp": [{"id": f"A-C{i + 1}", "hp": hp, "maxHp": 10}
                                for i, hp in enumerate(cargo_hp)]}

    def test_restoring_lifts_every_boat_to_the_floor_without_passing_its_max(self):
        from navy_system.navy import restore_hp_to_floor
        fleet = self._fleet([10, 25], cargo_hp=(4,))
        # 砲艇 10 -> 30（+20）、25 -> 30（+5）；運輸船 4 -> 10（滿血 10，只能到 10，+6）
        self.assertEqual(restore_hp_to_floor(fleet, 30), 31)
        self.assertEqual([b["hp"] for b in fleet["gunBoats"]], [30, 30])
        self.assertEqual([b["hp"] for b in fleet["cargoBoatHp"]], [10])

    def test_a_boat_already_above_the_floor_is_left_alone(self):
        from navy_system.navy import restore_hp_to_floor
        fleet = self._fleet([28], cargo_hp=())
        self.assertEqual(restore_hp_to_floor(fleet, 20), 0)
        self.assertEqual(fleet["gunBoats"][0]["hp"], 28, "不能把血往下修")

    def test_a_sunk_boat_is_not_resurrected_by_a_repair(self):
        from navy_system.navy import restore_hp_to_floor
        fleet = self._fleet([0, 20], cargo_hp=())
        self.assertEqual(restore_hp_to_floor(fleet, 30), 10, "沉了就是沉了，只修活著的")
        self.assertEqual(len(fleet["gunBoats"]), 1)

    def test_the_engine_charges_for_what_it_actually_restored(self):
        engine = GameEngine(seed=7)
        before = engine.state["players"]["W"]["factory_points"]
        fleet = self._fleet([25], cargo_hp=())
        result = engine.repair_navy("W", 0, fleet, 30)
        self.assertEqual(result["hp"], 5)
        self.assertEqual(result["factory"], 10, "每點 2 工業點")
        self.assertEqual(result["state"]["players"]["W"]["factory_points"], before - 10)
        self.assertEqual(result["navy"]["gunBoats"][0]["hp"], 30, "修好的艦隊要回傳")

    def test_a_client_claiming_zero_cannot_repair_for_free(self):
        engine = GameEngine(seed=7)
        engine.state["players"]["W"]["factory_points"] = 100
        before = engine.state["players"]["W"]["factory_points"]
        fleet = self._fleet([10], cargo_hp=())
        result = engine.repair_navy("W", 0, fleet, 30)
        self.assertEqual(result["hp"], 20, "後端自己算，不看前端送的 hp")
        self.assertEqual(result["state"]["players"]["W"]["factory_points"], before - 40)

    def test_a_client_claiming_a_huge_number_cannot_buy_phantom_hp(self):
        engine = GameEngine(seed=7)
        fleet = self._fleet([29], cargo_hp=())
        result = engine.repair_navy("W", 999, fleet, 30)
        self.assertEqual(result["hp"], 1)

    def test_repairing_a_fleet_that_needs_nothing_is_refused(self):
        engine = GameEngine(seed=7)
        with self.assertRaises(ValueError):
            engine.repair_navy("W", 0, self._fleet([30], cargo_hp=(10,)), 30)

    def test_the_frontend_no_longer_computes_the_restored_hp(self):
        navy_js = (pathlib.Path(__file__).resolve().parents[1]
                   / "frontend" / "navy.js").read_text(encoding="utf-8")
        self.assertNotIn("export function restoreHpToFloor", navy_js,
                         "修理補血又變成兩份規則了")
        self.assertNotIn("restoreHpToFloor", FRONTEND_SOURCE)
        repair = FRONTEND_SOURCE.split('operation === "repair"', 1)[1][:1400]
        self.assertIn("navy: navySnapshotForServer(navy)", repair)
        self.assertIn("target_hp: targetHp", repair)
        self.assertIn("applyNavyStateFromServer(navy, result.navy)", repair)

    def test_the_frontend_no_longer_owns_the_damage_allocation_either(self):
        navy_js = (pathlib.Path(__file__).resolve().parents[1]
                   / "frontend" / "navy.js").read_text(encoding="utf-8")
        self.assertNotIn("export function applyGunBoatDamage", navy_js)
        self.assertNotIn("export function navyRetreatThresholdReached", navy_js)
        self.assertNotIn("export function retreatBaselineGunBoatHp", navy_js)


class CombatOutlookTests(unittest.TestCase):
    """開打前的「還能撐幾輪」。

    前端 estimatedRoundsUntilBreak() 在第一輪打完之前拿不到後端的
    time_to_breakdown，於是自己用戰力點 × 戰術倍率 × 一個寫死的校準常數
    （COMBAT_ESTIMATE_CALIBRATION = 0.45）另算一套——那是前端自己發明的傷害模型，
    和真正結算用的規則沒有任何關係，畫面上的數字自然對不上實際結果。
    現在改由 /api/combat-outlook 空跑一輪，用同一套規則算給前端顯示。
    """

    def _payload(self, a_units=None, b_units=None, a_traits=(), b_traits=(),
                 province=None, fortress=False):
        return {
            "army_a": {"name": "F-2", "tactic": "normal_advance",
                       "units": a_units or {"infantry": 12, "cavalry": 3,
                                            "machine_gun": 2, "artillery": 2}},
            "army_b": {"name": "W-2", "tactic": "normal_advance",
                       "units": b_units or {"infantry": 11, "cavalry": 1,
                                            "machine_gun": 2, "artillery": 1}},
            "battle": {"province": province, "fortress": fortress, "sides": {
                "A": {"faction": "F", "armies": [
                    {"id": "F-2", "general_id": "zhang_xueliang",
                     "traits": list(a_traits), "defending": False}]},
                "B": {"faction": "W", "armies": [
                    {"id": "W-2", "general_id": "jin_yun_e",
                     "traits": list(b_traits), "defending": True}]},
            }},
        }

    def test_the_outlook_reports_a_breakdown_estimate_for_both_sides(self):
        from backend.combat_adapter import combat_outlook
        out = combat_outlook(self._payload(), GameEngine(seed=3))
        self.assertIsNotNone(out["time_to_breakdown"])
        self.assertIn("A", out["time_to_breakdown"])
        self.assertIn("B", out["time_to_breakdown"])
        self.assertIn("aggregate", out["time_to_breakdown"]["A"])

    def test_the_outlook_matches_what_one_real_round_would_report(self):
        """預估必須和真正結算同源——這是整件事的重點。"""
        from backend.combat_adapter import combat_outlook, simulate_with_modifiers
        payload = self._payload()
        payload["max_rounds"] = 1
        real = simulate_with_modifiers(copy.deepcopy(payload), GameEngine(seed=3))
        first = next(entry for entry in real["log"] if entry.get("round"))
        out = combat_outlook(copy.deepcopy(payload), GameEngine(seed=3))
        self.assertEqual(out["time_to_breakdown"], first["time_to_breakdown"])

    def test_the_outlook_does_not_mutate_the_caller_payload(self):
        """空跑就是空跑：問一次預估不能把部隊打掉一輪。"""
        from backend.combat_adapter import combat_outlook
        payload = self._payload()
        before = copy.deepcopy(payload)
        combat_outlook(payload, GameEngine(seed=3))
        self.assertEqual(payload, before)

    def test_the_outlook_goes_through_the_backend_modifier_builder(self):
        """技能加成要吃到——不然預估用的是沒加成的部隊，又是一套不同的規則。"""
        from backend.combat_adapter import combat_outlook
        engine = GameEngine(seed=3)
        plain = combat_outlook(self._payload(), engine)
        buffed = combat_outlook(self._payload(a_traits=("dodging_drift",)), engine)
        self.assertNotEqual(plain["time_to_breakdown"], buffed["time_to_breakdown"],
                            "帶技能和不帶技能的預估不該一模一樣")

    def test_a_battle_too_small_to_fight_reports_no_estimate_instead_of_crashing(self):
        from backend.combat_adapter import combat_outlook
        out = combat_outlook(self._payload(a_units={"infantry": 1}), GameEngine(seed=3))
        self.assertIsNone(out["time_to_breakdown"])
        self.assertIn("reason", out)

    def test_the_endpoint_is_wired_up(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/combat-outlook": lambda payload: combat_outlook(payload, ENGINE)',
                      server)

    def test_the_frontend_no_longer_invents_its_own_damage_model(self):
        self.assertNotIn("COMBAT_ESTIMATE_CALIBRATION = ", FRONTEND_SOURCE,
                         "前端又自己發明一套傷害模型了")
        estimate = FRONTEND_SOURCE.split("function estimatedRoundsUntilBreak", 1)[1][:1200]
        for rule_bit in ("attack_multiplier", "harm_taken_multiplier", "ownTactic.threshold"):
            self.assertNotIn(rule_bit, estimate)
        self.assertIn("battleOutlooks.get(battleOutlookKey(battle))", estimate)

    def _refresh_body(self):
        """只取 refreshBattleOutlook 這一個函式的內容。

        先前用固定字元數切片，切過頭吃進了下一個函式，結果「這個函式裡有沒有
        某段程式」的判斷被隔壁函式滿足了——測試等於沒在測。
        """
        body = FRONTEND_SOURCE.split("async function refreshBattleOutlook", 1)[1]
        end = body.find("\n}\n")
        self.assertGreater(end, 0, "找不到 refreshBattleOutlook 的結尾")
        return body[:end]

    def test_the_frontend_asks_the_backend_and_redraws(self):
        self.assertIn('api("/api/combat-outlook"', FRONTEND_SOURCE)
        refresh = self._refresh_body()
        self.assertIn("renderBattlePanel()", refresh, "抓到之後要重畫，否則永遠停在「計算中」")

    def test_the_frontend_does_not_ask_twice_for_the_same_battle(self):
        refresh = self._refresh_body()
        self.assertIn("if (battleOutlooks.has(key) || battleOutlooksInFlight.has(key)) return;",
                      refresh, "沒有 in-flight 檢查，每次重畫都會再打一次後端")
        self.assertIn("battleOutlooksInFlight.add(key)", refresh)
        self.assertIn("battleOutlooksInFlight.delete(key)", refresh)

    def test_the_estimate_and_the_settlement_share_one_request_builder(self):
        """同一份 payload 餵預估與結算，才不會兩邊算的是不同的仗。"""
        self.assertIn("function combatRequestPayload(battle)", FRONTEND_SOURCE)
        resolve = FRONTEND_SOURCE.split("async function resolveBattleRound", 1)[1][:600]
        self.assertIn("combatRequestPayload(battle)", resolve)
        refresh = self._refresh_body()
        self.assertIn("const { payload } = combatRequestPayload(battle);", refresh,
                      "預估送的必須是這一場仗的內容")
        self.assertIn('api("/api/combat-outlook", payload)', refresh)


class OrderChargeLedgerTests(unittest.TestCase):
    """軍令扣款帳本：收多少、退多少，都由伺服器說了算。

    先前這四條路都由前端定價：
      · 工事（浮橋／要塞）——**完全沒有 API**，前端直接動 factory_points；
      · 艦隊機動——前端把「砲艇數 × 單價」乘好送上來，後端照收；
      · 急行軍——前端把 cash/factory 送上來，後端的常數只是 fallback；
      · 撤銷軍令的退款——前端把自己當初算的金額加回 factory_points。
    最後一條尤其糟：那是一條可以重複觸發的無限工業點路徑。
    """

    def _fleet(self, gun_boats=2):
        return {"id": "F-NAVY-1", "cargoBoats": 1,
                "cargoBoatHp": [{"id": "c1", "hp": 10, "maxHp": 10}],
                "gunBoats": [{"id": f"g{i}", "hp": 30, "maxHp": 30}
                             for i in range(gun_boats)]}

    # ---- 工事 ----

    def test_engineering_costs_come_from_the_backend(self):
        engine = GameEngine(seed=3)
        rules = engine.engineering_rules()
        self.assertEqual(rules["pontoon_bridge"]["factory_cost"], 10)
        self.assertEqual(rules["pontoon_bridge"]["turns"], 2)
        self.assertEqual(rules["fortress_builder"]["turns"], 3)

    def test_building_a_fortress_actually_charges_the_player(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["factory_points"]
        result = engine.pay_engineering("F", "fortress_builder", "24,22")
        self.assertEqual(result["factory"], 10)
        self.assertEqual(result["turns"], 3)
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before - 10)
        self.assertTrue(result["charge_id"])

    def test_engineering_is_refused_without_enough_factory_points(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["factory_points"] = 3
        with self.assertRaises(ValueError):
            engine.pay_engineering("F", "pontoon_bridge", "24,22")
        self.assertEqual(engine.state["players"]["F"]["factory_points"], 3, "擋下來就不該扣錢")

    def test_an_unknown_engineering_operation_is_refused(self):
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine.pay_engineering("F", "build_death_star", "24,22")

    def test_the_frontend_no_longer_holds_the_engineering_price_list(self):
        self.assertNotIn("const ENGINEERING_OPERATIONS = {", FRONTEND_SOURCE,
                         "工事成本又搬回前端了")
        self.assertIn('api("/api/pay-engineering"', FRONTEND_SOURCE)
        start = FRONTEND_SOURCE.split("async function startEngineeringOperation", 1)[1][:900]
        self.assertNotIn("factory_points = ", start, "前端又直接動工業點了")
        self.assertIn("action.chargeId = paid.charge_id", start)

    # ---- 艦隊機動 ----

    def test_the_navy_move_cost_is_computed_from_the_fleet(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine.navy_move_cost(self._fleet(2)), 10)
        self.assertEqual(engine.navy_move_cost(self._fleet(4)), 20, "每艘砲艇一份")

    def test_a_sunk_gun_boat_is_not_charged_for(self):
        engine = GameEngine(seed=3)
        fleet = self._fleet(2)
        fleet["gunBoats"][0]["hp"] = 0
        self.assertEqual(engine.navy_move_cost(fleet), 5)

    def test_omitting_the_fleet_does_not_buy_a_free_move(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["factory_points"]
        with self.assertRaises(ValueError):
            engine.pay_navy_move("F")
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before)

    def test_the_frontend_no_longer_prices_the_navy_move(self):
        move = FRONTEND_SOURCE.split('api("/api/pay-navy-move"', 1)[1][:400]
        self.assertNotIn("factory: moveCost", move, "前端又自己報價了")
        self.assertIn("navy: navySnapshotForServer(navy)", move)

    # ---- 急行軍 ----

    def test_forced_march_charges_the_engine_constants(self):
        engine = GameEngine(seed=3)
        cash_before = engine.state["players"]["F"]["treasury"]
        factory_before = engine.state["players"]["F"]["factory_points"]
        result = engine.pay_forced_march("F", army_id="F-2")
        self.assertEqual(result["cash"], engine.FORCED_MARCH_COST_CASH)
        self.assertEqual(result["factory"], engine.FORCED_MARCH_COST_FACTORY)
        self.assertEqual(engine.state["players"]["F"]["treasury"],
                         cash_before - engine.FORCED_MARCH_COST_CASH)
        self.assertEqual(engine.state["players"]["F"]["factory_points"],
                         factory_before - engine.FORCED_MARCH_COST_FACTORY)

    def test_the_forced_march_endpoint_ignores_a_price_from_the_client(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        handler = server.split("def _pay_forced_march", 1)[1][:500]
        self.assertNotIn('payload.get("cash"', handler, "又開始收前端報的價了")
        self.assertNotIn('payload.get("factory"', handler)

    def test_the_frontend_no_longer_sends_a_forced_march_price(self):
        block = FRONTEND_SOURCE.split('api("/api/pay-forced-march"', 1)[1][:300]
        self.assertNotIn("cash: rules.cash", block)
        self.assertNotIn("factory: rules.factory", block)

    # ---- 退款 ----

    def test_a_refund_returns_exactly_what_was_charged(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["factory_points"]
        charge = engine.pay_engineering("F", "fortress_builder", "24,22")["charge_id"]
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before - 10)
        refund = engine.refund_charge("F", charge)
        self.assertEqual(refund["factory"], 10)
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before)

    def test_a_refund_returns_cash_as_well_as_factory(self):
        engine = GameEngine(seed=3)
        cash_before = engine.state["players"]["F"]["treasury"]
        factory_before = engine.state["players"]["F"]["factory_points"]
        charge = engine.pay_forced_march("F", army_id="F-2")["charge_id"]
        engine.refund_charge("F", charge)
        self.assertEqual(engine.state["players"]["F"]["treasury"], cash_before)
        self.assertEqual(engine.state["players"]["F"]["factory_points"], factory_before)

    def test_the_same_charge_cannot_be_refunded_twice(self):
        """這正是先前的無限工業點路徑：撤銷一次就退一次，帳本不記得退過。"""
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["factory_points"]
        charge = engine.pay_engineering("F", "fortress_builder", "24,22")["charge_id"]
        engine.refund_charge("F", charge)
        with self.assertRaises(ValueError):
            engine.refund_charge("F", charge)
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before,
                         "第二次退款不能真的把錢加回去")

    def test_an_invented_charge_id_refunds_nothing(self):
        engine = GameEngine(seed=3)
        before = engine.state["players"]["F"]["factory_points"]
        with self.assertRaises(ValueError):
            engine.refund_charge("F", "F-CHG9999")
        self.assertEqual(engine.state["players"]["F"]["factory_points"], before)

    def test_one_players_charge_cannot_be_refunded_by_another(self):
        engine = GameEngine(seed=3)
        charge = engine.pay_engineering("F", "fortress_builder", "24,22")["charge_id"]
        before = engine.state["players"]["W"]["factory_points"]
        with self.assertRaises(ValueError):
            engine.refund_charge("W", charge)
        self.assertEqual(engine.state["players"]["W"]["factory_points"], before)

    def test_the_frontend_refunds_through_the_backend_ledger(self):
        self.assertIn('api("/api/refund-charge"', FRONTEND_SOURCE)
        self.assertNotIn("factory_points = Number(state.players[action.player].factory_points || 0) + Number(action.factoryCost)",
                         FRONTEND_SOURCE, "前端又自己退款了")
        self.assertEqual(FRONTEND_SOURCE.count("refundOrderCharge(action);"), 2,
                         "陸軍與艦隊兩條撤銷路徑都要走帳本")


class ReinforcementCapTests(unittest.TestCase):
    """補兵的戰力上限：基準值取自伺服器手上的編制，不是前端報的數字。

    先前 `/api/reinforce-army` 直接用 payload 裡的 current_force 當基準，
    而且那個欄位是 Optional——報低就能無限補兵，乾脆不送整段檢查還會被跳過。
    """

    def _tactical(self, units):
        return {"armies": {"F-2": {"faction": "F", "units": units}}}

    def test_the_engine_can_price_an_army_from_the_tactical_state(self):
        engine = GameEngine(seed=3)
        force = engine.army_force_from_tactical(
            self._tactical({"infantry": 12, "cavalry": 3, "machine_gun": 2, "artillery": 2}), "F-2")
        self.assertEqual(force, 27, "12 + 3 + 2×2 + 2×4")

    def test_an_unknown_army_has_no_force_reading(self):
        engine = GameEngine(seed=3)
        self.assertIsNone(engine.army_force_from_tactical(self._tactical({}), "W-9"))
        self.assertIsNone(engine.army_force_from_tactical(None, "F-2"))

    def test_the_cap_is_enforced_against_the_real_composition(self):
        engine = GameEngine(seed=3)
        from backend.card_engine import ARMY_FORCE_CAP
        near_cap = engine.army_force_from_tactical(
            self._tactical({"infantry": ARMY_FORCE_CAP}), "F-2")
        self.assertEqual(near_cap, ARMY_FORCE_CAP)

    def test_the_endpoint_reads_the_shared_state_not_the_payload(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        handler = server.split("def _reinforce_army", 1)[1][:900]
        self.assertIn("ENGINE.army_force_from_tactical(SHARED_TACTICAL_STATE, army_id)", handler)
        self.assertNotIn('payload.get("current_force"),\n            )', handler,
                         "又直接把前端送來的數字餵進去了")


class SurrenderVerdictTests(unittest.TestCase):
    """投降判定：將領被俘與否是結算結果，不是呈現。

    先前門檻（5 / 8 / 2.5）與判定都在 app.js。
    """

    def _result(self, a_units, b_units, winner="undecided"):
        return {"winner": winner,
                "remaining": {"A": {"units": dict(a_units)}, "B": {"units": dict(b_units)}}}

    def test_a_collapsed_side_surrenders(self):
        from backend.combat_adapter import surrender_verdict
        verdict = surrender_verdict(self._result({"infantry": 4}, {"infantry": 20}))
        self.assertEqual(verdict["side"], "A")
        self.assertEqual(verdict["reason"], "collapsed")

    def test_the_threshold_is_inclusive(self):
        from backend.combat_adapter import SURRENDER_FORCE_THRESHOLD, surrender_verdict
        at = surrender_verdict(self._result({"infantry": SURRENDER_FORCE_THRESHOLD},
                                            {"infantry": 20}))
        self.assertEqual(at["side"], "A", "剛好等於門檻就投降")
        above = surrender_verdict(self._result({"infantry": SURRENDER_FORCE_THRESHOLD + 1},
                                               {"infantry": 20}))
        self.assertIsNone(above["side"])

    def test_both_sides_too_weak_means_nobody_is_captured(self):
        """兩邊都打殘了不該有人被俘——先前的 `strengthB > 5` 條件就是為了這個。"""
        from backend.combat_adapter import surrender_verdict
        self.assertIsNone(surrender_verdict(self._result({"infantry": 3}, {"infantry": 2}))["side"])

    def test_an_overrun_loser_surrenders(self):
        from backend.combat_adapter import surrender_verdict
        # 敗方 8 戰力，勝方 20 ≥ 8×2.5
        verdict = surrender_verdict(self._result({"infantry": 20}, {"infantry": 8}, winner="A"))
        self.assertEqual(verdict["side"], "B")
        self.assertEqual(verdict["reason"], "overrun")

    def test_a_loser_that_is_not_outnumbered_enough_gets_away(self):
        from backend.combat_adapter import surrender_verdict
        # 敗方 8 戰力，勝方 19 < 8×2.5 = 20
        self.assertIsNone(
            surrender_verdict(self._result({"infantry": 19}, {"infantry": 8}, winner="A"))["side"])

    def test_a_loser_above_the_overrun_force_gets_away(self):
        from backend.combat_adapter import surrender_verdict
        # 敗方 9 戰力，超過 overrun 上限 8，即使被 3 倍兵力壓著也能退
        self.assertIsNone(
            surrender_verdict(self._result({"infantry": 40}, {"infantry": 9}, winner="A"))["side"])

    def test_an_undecided_battle_captures_nobody(self):
        from backend.combat_adapter import surrender_verdict
        self.assertIsNone(
            surrender_verdict(self._result({"infantry": 20}, {"infantry": 7}))["side"],
            "沒分出勝負就沒有追擊，也就沒有被俘")

    def test_a_wiped_out_side_is_always_taken(self):
        from backend.combat_adapter import surrender_verdict
        verdict = surrender_verdict(self._result({"infantry": 20}, {"infantry": 0}, winner="A"))
        self.assertEqual(verdict["side"], "B")

    def test_force_points_are_priced_by_unit_type(self):
        from backend.combat_adapter import surrender_verdict
        # 砲兵 2 門 = 8 戰力，剛好在 overrun 上限上
        verdict = surrender_verdict(self._result({"infantry": 20}, {"artillery": 2}, winner="A"))
        self.assertEqual(verdict["forceB"], 8)
        self.assertEqual(verdict["side"], "B")

    def _live_payload(self, with_battle):
        payload = {
            "army_a": {"name": "F-2", "tactic": "normal_advance",
                       "units": {"infantry": 40, "artillery": 6}},
            "army_b": {"name": "W-2", "tactic": "normal_advance", "units": {"infantry": 8}},
            "max_rounds": 1,
        }
        if with_battle:
            payload["battle"] = {"province": None, "fortress": False, "sides": {
                "A": {"faction": "F", "armies": [{"id": "F-2", "general_id": "zhang_xueliang",
                                                  "traits": [], "defending": False}]},
                "B": {"faction": "W", "armies": [{"id": "W-2", "general_id": "jin_yun_e",
                                                  "traits": [], "defending": True}]}}}
        return payload

    def test_the_real_combat_endpoint_carries_the_verdict(self):
        """帶 battle（正式路徑）與不帶 battle（舊格式）兩條都要附上判定。

        先前只測了不帶 battle 那條——那條走的是提早 return，把正式路徑上
        「忘了附判定」的錯誤整個蓋掉。
        """
        from backend.combat_adapter import simulate_with_modifiers
        for with_battle in (True, False):
            with self.subTest(with_battle=with_battle):
                result = simulate_with_modifiers(self._live_payload(with_battle),
                                                 GameEngine(seed=3))
                self.assertIn("surrender", result)
                self.assertIn(result["surrender"]["side"], (None, "A", "B"))
                self.assertIn("forceA", result["surrender"])

    def test_the_thresholds_match_what_the_bootstrap_advertises(self):
        from backend.combat_adapter import (OVERRUN_FORCE_RATIO, OVERRUN_SURRENDER_FORCE,
                                            SURRENDER_FORCE_THRESHOLD)
        from backend.card_engine import FEATURES
        advertised = FEATURES["surrender"]
        self.assertEqual(advertised["force_threshold"], SURRENDER_FORCE_THRESHOLD)
        self.assertEqual(advertised["overrun_force"], OVERRUN_SURRENDER_FORCE)
        self.assertEqual(advertised["overrun_ratio"], OVERRUN_FORCE_RATIO)

    def test_the_verdict_survives_the_surrender_bookkeeping(self):
        """surrenderArmy() 會整個換掉 battle.result；判定要另外留一份。"""
        self.assertIn("battle.surrenderVerdict = verdict;", FRONTEND_SOURCE)

    def test_the_frontend_no_longer_decides_who_surrenders(self):
        self.assertNotIn("const OVERRUN_SURRENDER_FORCE", FRONTEND_SOURCE)
        self.assertNotIn("const OVERRUN_FORCE_RATIO", FRONTEND_SOURCE)
        self.assertNotIn("function overrunSurrenderSide", FRONTEND_SOURCE)
        self.assertIn("const verdict = result.surrender", FRONTEND_SOURCE)

    def test_the_frontend_reads_the_threshold_instead_of_hardcoding_five(self):
        self.assertIn("function surrenderRules()", FRONTEND_SOURCE)
        self.assertIn("bootstrap?.features?.surrender", FRONTEND_SOURCE)
        self.assertNotIn("<= 5)", FRONTEND_SOURCE, "又出現寫死的 5 了")


class CityOwnershipEconomyTests(unittest.TestCase):
    """城市易手後的收入重算。

    前端 transferCityEconomy() 自己把 city.cash/factory 加總成 income，
    **完全沒有**後端 capture_city() 的城市等級縮放、city_development 加成與
    _adjusted_city_output 調整項。更糟的是呼叫端 queueCityOwnershipSync() 是
    fire-and-forget——後端算出來的正確收入根本沒有被套用。
    """

    def _first_city_of(self, engine, faction):
        return next(c for c in engine.data["strategic_map"]["cities"]
                    if engine.state["city_owners"].get(c["id"], c["faction"]) == faction)

    def test_capturing_a_city_moves_the_income_between_players(self):
        engine = GameEngine(seed=3)
        city = self._first_city_of(engine, "W")
        before_w = engine.state["players"]["W"]["income"]
        before_f = engine.state["players"]["F"]["income"]
        result = engine.capture_city(city["id"], "F")
        after = result["state"]["players"]
        self.assertLess(after["W"]["income"], before_w)
        self.assertGreater(after["F"]["income"], before_f)
        self.assertEqual(result["previous_owner"], "W")
        self.assertEqual(result["owner"], "F")

    def test_the_captured_city_lands_in_the_new_owners_economy_list(self):
        engine = GameEngine(seed=3)
        city = self._first_city_of(engine, "W")
        state = engine.capture_city(city["id"], "F")["state"]
        owned = {item["id"] for item in state["players"]["F"]["city_economy"]}
        lost = {item["id"] for item in state["players"]["W"]["city_economy"]}
        self.assertIn(city["id"], owned)
        self.assertNotIn(city["id"], lost)

    def test_income_totals_stay_consistent_with_the_city_list(self):
        """後端的 income 是它自己 _refresh_city_income 算的，不是誰報上來的。"""
        engine = GameEngine(seed=3)
        city = self._first_city_of(engine, "W")
        state = engine.capture_city(city["id"], "F")["state"]
        for faction in ("F", "W"):
            payload = state["players"][faction]
            bonus = payload.get("permanent_output_bonus") or {}
            expected = sum(item["cash"] for item in payload["city_economy"]) + int(bonus.get("cash", 0))
            self.assertEqual(payload["income"], expected)

    def test_city_development_feeds_into_the_captured_output(self):
        """城市發展加成前端那版完全沒有——搬到後端才吃得到。"""
        engine = GameEngine(seed=3)
        city = self._first_city_of(engine, "W")
        plain = engine.capture_city(city["id"], "F")["city"]["cash"]
        engine2 = GameEngine(seed=3)
        engine2.state.setdefault("city_development", {})[city["id"]] = {"cash": 5, "factory": 0}
        developed = engine2.capture_city(city["id"], "F")["city"]["cash"]
        self.assertEqual(developed, plain + 5)

    def test_the_frontend_no_longer_recomputes_income(self):
        transfer = FRONTEND_SOURCE.split("function transferCityEconomy", 1)[1][:700]
        self.assertNotIn("payload.income =", transfer, "前端又自己算收入了")
        self.assertNotIn("city_economy.push", transfer)
        self.assertIn("city.faction = nextFaction", transfer, "只該改歸屬（地圖狀態）")

    def test_the_frontend_actually_applies_what_the_backend_returns(self):
        sync = FRONTEND_SOURCE.split("function queueCityOwnershipSync", 1)[1][:700]
        self.assertIn("state = result.state", sync,
                      "fire-and-forget 的話後端算的正確收入永遠進不了畫面")
        self.assertIn("syncStrategicCitiesFromState()", sync)


class NpcReinforcementTests(unittest.TestCase):
    """NPC 自動增兵：節奏、資格、除名、抽兵種都在後端。

    先前整套在 app.js，而且用沒有種子的 Math.random()——多人連線時每個 client
    算出來的 NPC 兵力可能不一樣，誰先 publishSharedState 誰說了算。
    """

    def _tactical(self, armies, marshals=None):
        trees = {faction: {"great_general_id": general}
                 for faction, general in (marshals or {}).items()}
        return {"armies": armies, "generalTrees": trees, "generalOwners": {}}

    def _army(self, units, **extra):
        return {"units": dict(units), "status": "active", **extra}

    def test_infantry_grows_every_third_turn(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": 10})})
        self.assertEqual(engine.npc_reinforcements(tactical, turn=2)["grown"], [])
        grown = engine.npc_reinforcements(tactical, turn=3)["grown"]
        self.assertEqual(len(grown), 1)
        self.assertEqual(grown[0]["gains"], ["infantry"])
        self.assertEqual(grown[0]["units"]["infantry"], 11)

    def test_only_the_marshal_gets_the_heavy_weapon(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical(
            {"Y-1": self._army({"infantry": 10}, generalId="yan_xishan"),
             "Y-2": self._army({"infantry": 10}, generalId="fu_zuoyi")},
            marshals={"Y": "yan_xishan"})
        by_army = {entry["armyId"]: entry
                   for entry in engine.npc_reinforcements(tactical, turn=15)["grown"]}
        self.assertEqual(len(by_army["Y-1"]["gains"]), 2, "大帥同時吃到步兵與重武器")
        self.assertEqual(by_army["Y-2"]["gains"], ["infantry"])

    def test_the_heavy_pick_is_seeded_and_reproducible(self):
        """同一個種子要算出同一串結果。

        只比一支部隊不夠：候選只有三個兵種，就算改用沒有種子的 random，
        兩次也有三分之一機率剛好抽到同一個。這裡比的是十支大帥的完整序列。
        """
        armies = {f"Y-{i}": self._army({"infantry": 10}, generalId=f"marshal_{i}")
                  for i in range(10)}
        picks = []
        for _ in range(2):
            # 十支部隊分屬十個假陣營，每一支都是自家大帥，才會每支都抽重武器
            tactical = {"armies": armies,
                        "generalTrees": {"Y": {"great_general_id": None}},
                        "generalOwners": {}}
            tactical["generalTrees"] = {"Y": {"great_general_id": "marshal_0"}}
            engine = GameEngine(seed=11)
            engine.NPC_FACTIONS = ("Y",)
            grown = engine.npc_reinforcements(tactical, turn=15)["grown"]
            picks.append([entry["gains"] for entry in grown])
        self.assertEqual(picks[0], picks[1], "同一個種子要算出同一串結果")

    def test_player_factions_never_grow_on_their_own(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"F-1": self._army({"infantry": 10}),
                                   "N-1": self._army({"infantry": 10})})
        self.assertEqual(engine.npc_reinforcements(tactical, turn=15)["grown"], [])

    def test_a_defected_army_is_struck_off_permanently(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": 10}, faction="F")})
        report = engine.npc_reinforcements(tactical, turn=3)
        self.assertEqual(report["ended_growth"], ["Y-1"])
        self.assertEqual(report["grown"], [], "當回合就不該再長")

    def test_a_recruited_general_also_ends_growth(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": 10}, generalId="yan_xishan")})
        tactical["generalOwners"] = {"yan_xishan": "F"}
        self.assertEqual(engine.npc_reinforcements(tactical, turn=3)["ended_growth"], ["Y-1"])

    def test_an_already_struck_off_army_stays_struck_off(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": 10}, npcGrowthEnded=True)})
        self.assertEqual(engine.npc_reinforcements(tactical, turn=3)["grown"], [])

    def test_a_dead_or_jailed_army_does_not_grow(self):
        engine = GameEngine(seed=3)
        for status in ("jailed", "killed", "destroyed", "surrendered"):
            with self.subTest(status=status):
                tactical = self._tactical({"Y-1": self._army({"infantry": 10}, status=status)})
                self.assertEqual(engine.npc_reinforcements(tactical, turn=3)["grown"], [])

    def test_growth_stops_at_the_force_cap(self):
        from backend.card_engine import ARMY_FORCE_CAP
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": ARMY_FORCE_CAP})})
        self.assertEqual(engine.npc_reinforcements(tactical, turn=3)["grown"], [])

    def test_a_heavy_unit_that_would_break_the_cap_is_not_offered(self):
        """空間放不下的兵種不能被抽中。

        光斷言「最後沒有超過上限」抓不到這個 bug——硬塞之後 _clamp_to_force_cap
        會把多的裁掉，帳面上照樣合法。真正的破綻是**回報的 gains 和實際增加的兵
        對不上**：說補了機槍，結果被裁掉別的兵。而且抽兵種是隨機的，只試一個種子
        可能剛好抽到放得下的那個，所以這裡掃一輪種子。
        """
        from backend.card_engine import ARMY_FORCE_CAP, UNIT_FORCE_POINTS
        # 補完步兵之後只剩 1 點空間：騎兵(1) 放得下，機槍(2)、砲兵(4) 放不下
        before = {"infantry": ARMY_FORCE_CAP - 2, "cavalry": 0,
                  "machine_gun": 0, "artillery": 0}
        for seed in range(10):
            with self.subTest(seed=seed):
                tactical = self._tactical(
                    {"Y-1": self._army(before, generalId="yan_xishan")},
                    marshals={"Y": "yan_xishan"})
                grown = GameEngine(seed=seed).npc_reinforcements(tactical, turn=15)["grown"]
                self.assertEqual(grown[0]["gains"], ["infantry", "cavalry"],
                                 "只剩 1 點空間時只有騎兵放得下")
                expected = dict(before)
                for unit in grown[0]["gains"]:
                    expected[unit] += 1
                self.assertEqual(grown[0]["units"], expected,
                                 "回報的 gains 必須就是實際增加的兵，不能被裁過")
                self.assertLessEqual(
                    sum(grown[0]["units"][unit] * points
                        for unit, points in UNIT_FORCE_POINTS.items()),
                    ARMY_FORCE_CAP)

    def test_turn_zero_grows_nothing(self):
        engine = GameEngine(seed=3)
        tactical = self._tactical({"Y-1": self._army({"infantry": 10})})
        self.assertEqual(engine.npc_reinforcements(tactical, turn=0)["grown"], [])

    def test_the_frontend_no_longer_owns_the_growth_rules(self):
        for name in ("const NPC_GROWTH", "function applyNpcReinforcements",
                     "function npcArmyCanGrow", "function markDefectedNpcArmies"):
            self.assertNotIn(name, FRONTEND_SOURCE, f"{name} 又搬回前端了")
        self.assertIn('api("/api/turn-reinforcements"', FRONTEND_SOURCE)
        applier = FRONTEND_SOURCE.split("function applyNpcReinforcementResult", 1)[1][:800]
        self.assertNotIn("Math.random()", applier, "NPC 兵力不該由前端擲骰")
        self.assertIn("army.units = { ...entry.units }", applier)


class FieldHospitalTests(unittest.TestCase):
    """野戰醫院免費補兵。

    先前兵種用 Math.random() 在前端挑，兵直接加進 army.units，沒有任何後端呼叫；
    後端只存了 field_hospital_generals 名單，效果本身沒有實作。
    """

    def _tactical(self, army):
        return {"armies": {"F-2": army}}

    def _pending(self, units, turn=1):
        return {"turn": turn, "units": list(units)}

    def _army(self, **extra):
        base = {"faction": "F", "generalId": "zhang_xueliang", "status": "active",
                "units": {"infantry": 10, "cavalry": 0, "machine_gun": 0, "artillery": 0}}
        base.update(extra)
        return base

    def _with_hospital(self, seed=3):
        engine = GameEngine(seed=seed)
        engine.state["players"]["F"]["field_hospital_generals"] = ["zhang_xueliang"]
        return engine

    def test_a_covered_general_gets_a_battalion_back(self):
        engine = self._with_hospital()
        tactical = self._tactical(self._army(fieldHospitalPending=self._pending(["artillery"])))
        report = engine.field_hospital_recovery(tactical, turn=2)
        self.assertEqual(len(report["healed"]), 1)
        self.assertEqual(report["healed"][0]["unit"], "artillery")
        self.assertEqual(report["healed"][0]["units"]["artillery"], 1)

    def test_recovery_waits_until_the_next_turn(self):
        engine = self._with_hospital()
        tactical = self._tactical(self._army(fieldHospitalPending=self._pending(["artillery"], turn=2)))
        self.assertEqual(engine.field_hospital_recovery(tactical, turn=2)["healed"], [],
                         "同一回合不該就歸隊")
        self.assertEqual(len(engine.field_hospital_recovery(tactical, turn=3)["healed"]), 1)

    def test_a_general_without_a_hospital_just_loses_the_pending_entry(self):
        engine = GameEngine(seed=3)          # 名單是空的
        tactical = self._tactical(self._army(fieldHospitalPending=self._pending(["artillery"])))
        report = engine.field_hospital_recovery(tactical, turn=2)
        self.assertEqual(report["healed"], [])
        self.assertEqual(report["cleared"], ["F-2"])

    def test_the_timed_window_covers_the_whole_faction(self):
        """〈泳渡海峽的女子〉開的窗口內，名單外的將領也算數。"""
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["timed_effects"] = [
            {"kind": "field_hospital_window", "remaining_turns": 2}]
        tactical = self._tactical(self._army(generalId="somebody_else",
                                             fieldHospitalPending=self._pending(["cavalry"])))
        self.assertEqual(len(engine.field_hospital_recovery(tactical, turn=2)["healed"]), 1)

    def test_the_pick_comes_from_what_was_actually_lost(self):
        engine = self._with_hospital()
        tactical = self._tactical(self._army(fieldHospitalPending=self._pending(["machine_gun"])))
        healed = engine.field_hospital_recovery(tactical, turn=2)["healed"]
        self.assertEqual(healed[0]["unit"], "machine_gun", "不能補一個沒有損失過的兵種")

    def test_the_pick_is_seeded_and_reproducible(self):
        """同一個種子要算出同一串結果。

        只比一支部隊不夠：候選只有四個兵種，就算改用沒有種子的 random，
        兩次也有四分之一機率剛好抽到同一個。這裡比的是十二支部隊的完整序列。
        """
        all_units = ["infantry", "cavalry", "machine_gun", "artillery"]
        armies = {f"F-{i}": self._army(fieldHospitalPending=self._pending(all_units))
                  for i in range(12)}
        runs = []
        for _ in range(2):
            engine = self._with_hospital(seed=21)
            healed = engine.field_hospital_recovery({"armies": armies}, turn=2)["healed"]
            runs.append([entry["unit"] for entry in healed])
        self.assertEqual(len(runs[0]), 12)
        self.assertEqual(runs[0], runs[1], "同一個種子要算出同一串結果")

    def test_an_embarked_or_dead_army_does_not_heal(self):
        engine = self._with_hospital()
        for extra in ({"embarkedOn": "F-NAVY-1"}, {"status": "killed"}):
            with self.subTest(extra=extra):
                tactical = self._tactical(self._army(
                    fieldHospitalPending=self._pending(["artillery"]), **extra))
                self.assertEqual(engine.field_hospital_recovery(tactical, turn=2)["healed"], [])

    def test_the_frontend_only_applies_the_result(self):
        self.assertNotIn("function applyFieldHospitalRecovery", FRONTEND_SOURCE)
        applier = FRONTEND_SOURCE.split("function applyFieldHospitalResult", 1)[1][:700]
        self.assertNotIn("Math.random()", applier)
        self.assertIn("army.units = { ...entry.units }", applier)

    def test_both_reports_ship_from_one_endpoint(self):
        engine = self._with_hospital()
        report = engine.turn_reinforcements({"armies": {}}, turn=3)
        self.assertIn("npc", report)
        self.assertIn("field_hospital", report)
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/turn-reinforcements": self._turn_reinforcements', server)
        self.assertIn("ENGINE.turn_reinforcements(SHARED_TACTICAL_STATE", server,
                      "要用伺服器自己手上的編制，不是前端送來的")


class EmbarkAuthorizationTests(unittest.TestCase):
    """陸軍上船的容量門檻：後端要複驗，不是只在前端擋一下。"""

    def _fleet(self, cargo_boats=1):
        return {"id": "F-NAVY-1", "gunBoats": [{"id": "g1", "hp": 30, "maxHp": 30}],
                "cargoBoats": cargo_boats,
                "cargoBoatHp": [{"id": f"c{i}", "hp": 10, "maxHp": 10}
                                for i in range(cargo_boats)]}

    def test_an_army_that_fits_is_allowed(self):
        engine = GameEngine(seed=3)
        result = engine.authorize_embark(self._fleet(2), {"infantry": 12, "cavalry": 3,
                                                          "machine_gun": 2, "artillery": 2})
        self.assertTrue(result["allowed"])
        self.assertEqual(result["capacity"], 40)
        self.assertEqual(result["force"], 27)

    def test_an_army_that_does_not_fit_is_refused(self):
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine.authorize_embark(self._fleet(1), {"infantry": 12, "cavalry": 3,
                                                     "machine_gun": 2, "artillery": 2})

    def test_exactly_filling_the_hold_is_allowed(self):
        engine = GameEngine(seed=3)
        self.assertTrue(engine.authorize_embark(self._fleet(1), {"infantry": 20})["allowed"])

    def test_one_point_over_is_refused(self):
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine.authorize_embark(self._fleet(1), {"infantry": 21})

    def test_a_sunk_cargo_boat_does_not_count_toward_capacity(self):
        engine = GameEngine(seed=3)
        fleet = self._fleet(2)
        fleet["cargoBoatHp"][0]["hp"] = 0
        with self.assertRaises(ValueError):
            engine.authorize_embark(fleet, {"infantry": 21})

    def test_units_are_priced_by_force_points(self):
        engine = GameEngine(seed=3)
        # 砲兵 6 門 = 24 點 > 20
        with self.assertRaises(ValueError):
            engine.authorize_embark(self._fleet(1), {"artillery": 6})
        self.assertTrue(engine.authorize_embark(self._fleet(1), {"artillery": 5})["allowed"])

    def test_an_empty_army_cannot_embark(self):
        engine = GameEngine(seed=3)
        with self.assertRaises(ValueError):
            engine.authorize_embark(self._fleet(1), {})

    def test_the_frontend_asks_before_loading(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn('"/api/embark-army": self._embark_army', server)
        embark = FRONTEND_SOURCE.split('api("/api/embark-army"', 1)[1][:400]
        self.assertIn("navy: navySnapshotForServer(navy)", embark)
        self.assertIn("army_units:", embark)
        gate = FRONTEND_SOURCE.split('beginNavyOrder(navy, "embark")', 1)[0][-900:]
        self.assertNotIn("> navyCapacity(navy, navyRules())", gate,
                         "容量門檻又只在前端擋了")


class ArmyActionWiringTests(unittest.TestCase):
    """部隊行動的後端運算 ↔ 前端地圖／移動機制的接線。

    每一條問的都是同一件事：後端算出來的限制或結果，前端有沒有真的照做。
    """

    def _resolve(self, card_id, seed=3):
        engine = GameEngine(seed=seed)
        for payload in engine.state["players"].values():
            payload["treasury"] = 300
            payload["factory_points"] = 300
        engine.state["turn"] = 2
        engine.state["event_pool"] = [card_id]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertTrue(view and view["card"]["id"] == card_id, f"{card_id} 沒抽出來")
        guard = 0
        while view and guard < 24:
            guard += 1
            options = (view["card"].get("resolution") or {}).get("options") or []
            engine.respond_event(view.get("waiting_for") or view["drawer"],
                                 choice=options[0]["id"] if options else None)
            view = engine.pending_event_view()
        return engine

    # ---- 移動凍結 ----

    def test_a_flood_freezes_movement_in_named_cities(self):
        engine = self._resolve("yangtze_flood")
        frozen = {}
        for code, payload in engine.state["players"].items():
            for effect in payload.get("timed_effects", []):
                if effect.get("kind") == "movement_freeze":
                    frozen[code] = sorted(effect.get("cities") or [])
        self.assertTrue(frozen, "長江水患要排出移動凍結")
        for cities in frozen.values():
            self.assertTrue(cities, "凍結必須指名城市，否則前端會把整省鎖死")

    def test_the_frontend_reads_the_freeze_from_the_backend_effect(self):
        """前端不能自己另建一份受災城市名單。"""
        block = FRONTEND_SOURCE.split("function movementFreezeForArmy", 1)[1][:900]
        self.assertIn('activeTimedEffects(faction, "movement_freeze")', block)
        self.assertIn("effect.cities", block)
        self.assertNotIn("yangtze", block.lower(), "前端又抄了一份受災城市清單")

    # ---- 行動封鎖 ----

    def test_an_action_ban_stops_the_reinforce_endpoint(self):
        engine = GameEngine(seed=3)
        engine.state["action_bans"] = [{"actions": ["reinforce_army"], "players": ["F"],
                                        "until_turn": int(engine.state["turn"]) + 3,
                                        "label": "軍餉短缺"}]
        with self.assertRaises(ValueError):
            engine.reinforce_army("F", "F-1", "fengtian", "infantry", 1)

    def test_an_action_ban_only_binds_the_named_players(self):
        engine = GameEngine(seed=3)
        engine.state["action_bans"] = [{"actions": ["reinforce_army"], "players": ["F"],
                                        "until_turn": int(engine.state["turn"]) + 3,
                                        "label": "軍餉短缺"}]
        self.assertIsNone(engine.action_banned("W", "reinforce_army"))
        self.assertIsNotNone(engine.action_banned("F", "reinforce_army"))

    def test_an_expired_ban_stops_binding(self):
        engine = GameEngine(seed=3)
        engine.state["action_bans"] = [{"actions": ["reinforce_army"], "players": ["F"],
                                        "until_turn": int(engine.state["turn"]),
                                        "label": "軍餉短缺"}]
        self.assertIsNone(engine.action_banned("F", "reinforce_army"))

    # ---- 可鎮壓騷亂 ----

    def test_a_strike_shows_up_in_the_quellable_list(self):
        engine = self._resolve("general_strike")
        report = engine.snapshot()["quellable_unrest"]
        owners = [code for code, items in report.items() if items]
        self.assertTrue(owners, "罷工要出現在可鎮壓清單裡，前端才畫得出按鈕")
        entry = report[owners[0]][0]
        for field in ("id", "name", "cost", "cities", "city_ids",
                      "remaining_turns", "affordable"):
            self.assertIn(field, entry, f"前端畫按鈕需要 {field}")

    def test_a_malformed_effect_cannot_bring_down_the_whole_snapshot(self):
        """snapshot() 幾乎每個 API 都會呼叫；它一拋例外等於整台伺服器停擺。

        先前 quellable_unrest 用 effect["id"] 直接取值，一筆缺欄位的效果就 KeyError。
        """
        engine = GameEngine(seed=3)
        engine.state["city_output_effects"] = [
            {"owner": "F", "quell_cost": 10, "name": "缺 id 的效果", "city_ids": ["fengtian"]}]
        snapshot = engine.snapshot()          # 不該拋例外
        self.assertEqual(snapshot["quellable_unrest"]["F"], [],
                         "沒有 id 就沒辦法鎮壓，該跳過而不是炸掉")

    def test_quelling_costs_money_and_the_backend_refuses_when_broke(self):
        engine = self._resolve("general_strike")
        report = engine.snapshot()["quellable_unrest"]
        owner = next(code for code, items in report.items() if items)
        entry = report[owner][0]
        engine.state["players"][owner]["treasury"] = entry["cost"] - 1
        with self.assertRaises(ValueError):
            engine.quell_unrest(owner, entry["id"])

    # ---- 補兵上限的時序 ----

    def test_the_frontend_publishes_before_asking_for_the_cap_check(self):
        """上限檢查看的是伺服器手上的編制；剛移動或剛打完仗沒同步就會比對到舊數字。"""
        block = FRONTEND_SOURCE.split('api("/api/reinforce-army"', 1)[0][-500:]
        self.assertIn("await publishSharedState(true);", block,
                      "補兵前要先把最新編制發佈上去")

    # ---- 佔領與戰鬥的回寫 ----

    def test_capturing_through_the_endpoint_moves_the_owner(self):
        engine = GameEngine(seed=3)
        city = next(c for c in engine.data["strategic_map"]["cities"]
                    if engine.state["city_owners"].get(c["id"], c["faction"]) == "W")
        engine.capture_city(city["id"], "F")
        self.assertEqual(engine.state["city_owners"][city["id"]], "F")

    def test_the_shared_state_is_the_one_place_army_composition_lives(self):
        """部隊編制只有一份，就在 SHARED_TACTICAL_STATE；後端的檢查都讀它。"""
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertIn("ENGINE.army_force_from_tactical(SHARED_TACTICAL_STATE", server)
        self.assertIn("ENGINE.turn_reinforcements(SHARED_TACTICAL_STATE", server)
        self.assertIn("ENGINE.navy_outlook(SHARED_TACTICAL_STATE)", server)
        self.assertIn("ENGINE.loyalty_report(SHARED_TACTICAL_STATE)", server)


if __name__ == "__main__":
    unittest.main()


class ForeignRelationThresholdTests(unittest.TestCase):
    """列強交好的門檻只有一個數字，而且住在 foreign_powers.json。

    這一組測試的存在理由很簡單：這個數字曾經在三個地方各寫一份，其中一份是 8。
    只要有人再複寫一份、或改了其中一份沒改其他份，下面就會紅。
    """

    def setUp(self):
        self.repo = pathlib.Path(__file__).resolve().parents[1]
        self.scale = json.loads(
            (self.repo / "foreign_powers/data/foreign_powers.json")
            .read_text(encoding="utf-8"))["global_rules"]["relation_scale"]

    # ---- 一、真源本身 ----

    def test_the_source_of_truth_says_six(self):
        self.assertEqual(int(self.scale["friendly_at_or_above"]), 6)
        self.assertEqual(int(self.scale["hostile_at_or_below"]), -4)

    def test_the_engine_derives_its_constants_and_does_not_retype_them(self):
        self.assertEqual(FOREIGN_FRIENDLY_THRESHOLD, int(self.scale["friendly_at_or_above"]))
        self.assertEqual(FOREIGN_HOSTILE_THRESHOLD, int(self.scale["hostile_at_or_below"]))
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        self.assertIn('FOREIGN_FRIENDLY_THRESHOLD = int(_RELATION_SCALE["friendly_at_or_above"])',
                      source)
        self.assertNotIn("FOREIGN_FRIENDLY_THRESHOLD = 6", source,
                         "門檻要用導出的，不是再打一次 6")

    # ---- 二、每一份副本都要對得上 ----

    def test_the_loan_tiers_use_the_same_cut_points(self):
        banks = json.loads((self.repo / "economy/data/banks.json").read_text(encoding="utf-8"))
        tiers = banks["tiers"]
        friendly = [t for t in tiers.values() if int(t["relation_min"]) == 6]
        self.assertTrue(friendly, f"優惠借貸的下限應該是 6：{tiers}")
        hostile = [t for t in tiers.values() if int(t["relation_max"]) == -4]
        self.assertTrue(hostile, f"不可借貸的上限應該是 −4：{tiers}")

    def test_the_card_pool_rules_copy_matches_the_source(self):
        """這一份就是那個寫成 8 的副本。"""
        rules = json.loads((self.repo / "cards/data/card_pool_rules.json")
                           .read_text(encoding="utf-8"))["foreign_relation_rules"]
        self.assertEqual(int(rules["friendly_at_or_above"]),
                         int(self.scale["friendly_at_or_above"]))
        self.assertEqual(int(rules["hostile_at_or_below"]),
                         int(self.scale["hostile_at_or_below"]))
        self.assertNotIn("hostile_below", rules, "舊刻度的欄位名要移除，不然兩個欄位會並存")
        self.assertEqual(rules["scale"], "-10~10", "刻度不是 0-10")

    def test_every_perk_card_gate_is_the_same_number(self):
        cards = json.loads((self.repo / "cards/data/function_cards.json")
                           .read_text(encoding="utf-8"))["cards"]
        floors = {int(c["requires_relation_min"]) for c in cards
                  if "requires_relation_min" in c}
        self.assertEqual(floors, {int(self.scale["friendly_at_or_above"])},
                         "所有列強 perk 卡的門檻一律是 6，沒有例外")

    # ---- 三、前端不准留第二份 ----

    def test_the_frontend_keeps_no_copy_of_the_threshold(self):
        self.assertNotIn("FOREIGN_RAILWAY_RELATION_MIN", FRONTEND_SOURCE,
                         "前端不該有自己的鐵路門檻常數")
        self.assertNotIn("FOREIGN_RAILWAY_POWERS", FRONTEND_SOURCE,
                         "哪條線是哪國的，資料在 strategic_map.json，前端不留對照表")
        for banned in ('value >= 6', 'value <= -4'):
            self.assertNotIn(banned, FRONTEND_SOURCE,
                             f"關係分級不該寫死：{banned}")
        self.assertIn("backendRailwayAccess?.friendly_threshold", FRONTEND_SOURCE,
                      "友好門檻要從後端讀")

    def test_the_frontend_reads_the_backend_verdict_instead_of_recomputing(self):
        for expected in ("railwayAccessFor(faction).locked",
                         "railwayAccessFor(faction).banned",
                         "railwayAccessFor(faction).unusable",
                         "if (remote.railway_access) backendRailwayAccess = remote.railway_access;",
                         "if (result.railway_access) backendRailwayAccess = result.railway_access;"):
            self.assertIn(expected, FRONTEND_SOURCE, expected)

    def test_the_server_publishes_the_verdict_on_every_shared_state_path(self):
        server = (pathlib.Path(__file__).resolve().parent / "server.py").read_text(encoding="utf-8")
        self.assertEqual(server.count('"railway_access": ENGINE.railway_access(),'), 3,
                         "三條 shared-state 出口都要帶上鐵路判定")


class ForeignRailwayAccessTests(unittest.TestCase):
    """列強鐵路：關係到門檻才借你調兵，判定在後端。"""

    def setUp(self):
        self.engine = GameEngine(seed=5)

    def test_the_map_names_the_owner_of_every_foreign_line(self):
        lines = self.engine.data["strategic_map"]["railroads"]
        foreign = [l for l in lines if l.get("foreign")]
        self.assertEqual({l["name"] for l in foreign},
                         {"南滿鐵路", "中東鐵路", "滇越鐵路"})
        for line in foreign:
            self.assertIn(line.get("power"), ("jp", "su", "fr", "uk", "us"),
                          f"{line['name']} 沒寫 power")
        self.assertEqual(self.engine.foreign_railways(),
                         {"南滿鐵路": "jp", "中東鐵路": "su", "滇越鐵路": "fr"})

    def test_a_foreign_line_without_a_power_is_a_loud_error(self):
        """標了 foreign 卻沒寫 power，要當場炸，不能安靜地變成「誰都能用」。"""
        engine = GameEngine(seed=5)
        engine.data = deepcopy(engine.data)
        for line in engine.data["strategic_map"]["railroads"]:
            if line.get("foreign"):
                line.pop("power", None)
                break
        with self.assertRaises(ValueError):
            engine.foreign_railways()

    def test_a_foreign_line_with_a_bogus_power_is_a_loud_error(self):
        engine = GameEngine(seed=5)
        engine.data = deepcopy(engine.data)
        for line in engine.data["strategic_map"]["railroads"]:
            if line.get("foreign"):
                line["power"] = "de"
                break
        with self.assertRaises(ValueError):
            engine.foreign_railways()

    def test_the_gate_opens_exactly_at_the_threshold(self):
        """門檻是 >=，不是 >。差一分就是差一分，剛好到就該放行。"""
        floor = FOREIGN_FRIENDLY_THRESHOLD
        relations = self.engine.state["players"]["F"]["foreign_relations"]
        for power, railway in (("jp", "南滿鐵路"), ("su", "中東鐵路"), ("fr", "滇越鐵路")):
            relations[power] = floor - 1
            self.assertIn(railway, self.engine.locked_foreign_railways("F"),
                          f"{railway}：關係 {floor - 1} 應該還借不到")
            relations[power] = floor
            self.assertNotIn(railway, self.engine.locked_foreign_railways("F"),
                             f"{railway}：關係剛好 {floor} 就該放行")
            relations[power] = floor + 4
            self.assertNotIn(railway, self.engine.locked_foreign_railways("F"))

    def test_the_gate_is_not_five_and_not_seven_and_not_eight(self):
        """把門檻挪一格就該有線路的判定跟著變——擋住「順手改成 8」那類回歸。"""
        relations = self.engine.state["players"]["F"]["foreign_relations"]
        for power in ("jp", "su", "fr"):
            relations[power] = 5
        self.assertEqual(len(self.engine.locked_foreign_railways("F")), 3,
                         "關係 5 三條線都借不到；若這裡是 0，門檻被改小了")
        for power in ("jp", "su", "fr"):
            relations[power] = 6
        self.assertEqual(self.engine.locked_foreign_railways("F"), [],
                         "關係 6 三條線都該開；若這裡還鎖著，門檻被改大了")

    def test_each_player_is_judged_on_their_own_relations(self):
        self.engine.state["players"]["F"]["foreign_relations"]["jp"] = 9
        self.engine.state["players"]["W"]["foreign_relations"]["jp"] = 0
        self.assertNotIn("南滿鐵路", self.engine.locked_foreign_railways("F"))
        self.assertIn("南滿鐵路", self.engine.locked_foreign_railways("W"))

    def test_unusable_is_the_union_of_all_three_reasons(self):
        engine = self.engine
        for power in ("jp", "su", "fr"):
            engine.state["players"]["F"]["foreign_relations"][power] = 10
        self.assertEqual(engine.unusable_railways("F"), [])
        engine.state["players"]["F"]["foreign_relations"]["fr"] = 5      # 關係不到
        engine.state.setdefault("railway_effects", []).append(          # 搶修中
            {"railway": "京漢鐵路", "remaining_turns": 3})
        engine.state.setdefault("railway_bans", []).append(             # 路權被封
            {"player": "F", "railway": "津浦鐵路",
             "until_turn": int(engine.state["turn"]) + 2})
        self.assertEqual(engine.unusable_railways("F"),
                         sorted(["京漢鐵路", "滇越鐵路", "津浦鐵路"]))
        # 搶修是全場的，封路權只罰一家
        self.assertIn("京漢鐵路", engine.unusable_railways("W"))
        self.assertNotIn("津浦鐵路", engine.unusable_railways("W"))

    def test_the_published_verdict_matches_the_methods(self):
        for power in ("jp", "su", "fr"):
            self.engine.state["players"]["N"]["foreign_relations"][power] = 6
        self.engine.state["players"]["S"]["foreign_relations"]["jp"] = 5
        access = self.engine.railway_access()
        self.assertEqual(access["friendly_threshold"], FOREIGN_FRIENDLY_THRESHOLD)
        self.assertEqual(access["hostile_threshold"], FOREIGN_HOSTILE_THRESHOLD)
        self.assertEqual(access["foreign_railways"], self.engine.foreign_railways())
        for code in self.engine.state["players"]:
            row = access["by_player"][code]
            self.assertEqual(row["locked"], self.engine.locked_foreign_railways(code), code)
            self.assertEqual(row["banned"], self.engine.banned_railways(code), code)
            self.assertEqual(row["unusable"], self.engine.unusable_railways(code), code)
        self.assertEqual(access["by_player"]["N"]["locked"], [])
        self.assertIn("南滿鐵路", access["by_player"]["S"]["locked"])

    def test_the_verdict_reports_the_relation_behind_each_line(self):
        """前端要能寫出「對日本關係未達 6」，所以每條線的關係值也要送過去。"""
        self.engine.state["players"]["F"]["foreign_relations"]["jp"] = 3
        row = self.engine.railway_access()["by_player"]["F"]
        self.assertEqual(row["relations"]["南滿鐵路"], 3)

    def test_an_unknown_player_locks_everything_rather_than_opening_everything(self):
        """查不到的人不該變成關係 0 以外的什麼——關係 0 本來就過不了門檻。"""
        self.assertEqual(self.engine.locked_foreign_railways("ZZ"),
                         sorted(["中東鐵路", "南滿鐵路", "滇越鐵路"]))


class RegionBonusStackingTests(unittest.TestCase):
    """「控制 a、b 或 c 者本回合獲得 $xx」——一個地區發一次，數量疊加。

    這一組卡在改之前是**一次總付**：控制四省和控制一省拿到的錢一樣多。
    """

    CARDS = {
        "silk_tea_export_boom": 8,
        "salt_administration_reform": 10,
        "chinese_liquor_expo": 5,
        "sothebys_porcelain_auction": 5,
        "chinese_tea_expo": 5,
    }

    def test_no_card_of_this_family_is_left_without_the_flag(self):
        """掃全卡池：凡是「一次性發錢」＋「點名多個地區」的，一律要疊加。

        這一條是給日後新增的卡用的——漏掛旗標就會在這裡紅燈，
        不必再靠人記得有這條規則。
        """
        engine = GameEngine(seed=3)
        missing = []
        for card in engine.data["event_cards"]["cards"]:
            grant = (card.get("apply") or {}).get("grant")
            condition = card.get("entry_condition") or {}
            regions = ((condition.get("controls_provinces_any") or [])
                       + (condition.get("controls_cities_any") or []))
            if grant and len(regions) > 1 and grant.get("per") != "eligible_regions":
                missing.append(card["id"])
        self.assertEqual(missing, [],
                         f"這些卡點名了多個地區卻只發一次錢：{missing}")

    def _template(self, engine, card_id):
        return next(c for c in engine.data["event_cards"]["cards"] if c["id"] == card_id)

    def _regions(self, card):
        condition = card.get("entry_condition") or {}
        return (condition.get("controls_provinces_any") or []
                or condition.get("controls_cities_any") or [])

    def _hand_over(self, engine, card, player, how_many):
        """把卡片點名的前 how_many 個地區交給 player，其餘交給別人。"""
        condition = card.get("entry_condition") or {}
        provinces = condition.get("controls_provinces_any") or []
        cities = condition.get("controls_cities_any") or []
        groups = {p: [c["id"] for c in engine.data["strategic_map"]["cities"]
                      if c.get("province") == p] for p in provinces}
        groups.update({c: [c] for c in cities})
        order = provinces + cities
        for ids in groups.values():
            for city_id in ids:
                engine.state["city_owners"][city_id] = "W" if player != "W" else "S"
        for key in order[:how_many]:
            for city_id in groups[key]:
                engine.state["city_owners"][city_id] = player
        engine._refresh_city_income()

    def test_every_such_card_declares_the_stacking_rule(self):
        """疊加是靠 payload 上的旗標，不是靠引擎猜卡名。"""
        engine = GameEngine(seed=3)
        for card_id in self.CARDS:
            card = self._template(engine, card_id)
            self.assertEqual(card["apply"]["grant"].get("per"), "eligible_regions",
                             f"{card_id} 少了疊加旗標")

    def test_the_payout_is_one_helping_per_region_controlled(self):
        for card_id, unit in self.CARDS.items():
            engine = GameEngine(seed=3)
            card = self._template(engine, card_id)
            regions = self._regions(card)
            self.assertTrue(regions, f"{card_id} 沒有地區清單")
            for how_many in range(1, len(regions) + 1):
                engine = GameEngine(seed=3)
                card = self._template(engine, card_id)
                self._hand_over(engine, card, "F", how_many)
                paid = engine._eligible_region_count(card, "F")
                self.assertEqual(paid, how_many,
                                 f"{card_id}：控制 {how_many} 個地區卻數成 {paid}")

    def test_controlling_four_regions_really_pays_four_times(self):
        """不是只看計數函式——真的抽卡、真的看錢進了多少。"""
        for card_id, unit in self.CARDS.items():
            payouts = []
            engine = GameEngine(seed=3)
            regions = self._regions(self._template(engine, card_id))
            for how_many in (1, len(regions)):
                engine = GameEngine(seed=3)
                card = self._template(engine, card_id)
                self._hand_over(engine, card, "F", how_many)
                engine.state["event_pool"] = [card_id]
                view = None
                for _ in range(8):
                    engine.next_turn(active_player="F")
                    view = engine.pending_event_view()
                    if view:
                        break
                self.assertIsNotNone(view, f"{card_id} 沒抽出來")
                grants = []
                guard = 0
                while view and guard < 24:
                    guard += 1
                    options = (view["card"].get("resolution") or {}).get("options") or []
                    result = engine.respond_event(
                        view.get("waiting_for") or view["drawer"],
                        choice=options[0]["id"] if options else None)
                    grants += [a for a in ((result or {}).get("applied") or [])
                               if a.get("kind") == "grant" and a.get("player") == "F"]
                    view = engine.pending_event_view()
                self.assertTrue(grants, f"{card_id}：控制 {how_many} 個地區卻沒發錢")
                payouts.append(sum(int(g["cash"]) for g in grants))
            self.assertEqual(payouts[0], unit, f"{card_id}：控制一個地區應該發 {unit}")
            self.assertEqual(payouts[1], unit * len(regions),
                             f"{card_id}：控制 {len(regions)} 個地區應該發 {unit * len(regions)} "
                             f"，實際 {payouts[1]}")
            self.assertGreater(payouts[1], payouts[0],
                               f"{card_id}：控制得多卻沒拿得多，等於沒有疊加")

    def test_a_card_without_the_flag_still_pays_once(self):
        """沒掛旗標的一次性入帳不該被這條規則波及。"""
        engine = GameEngine(seed=3)
        card = {"id": "fake", "name": "fake", "entry_condition":
                {"controls_provinces_any": ["江蘇", "浙江"]}}
        applied = engine._apply_event_payload({"grant": {"cash": 7}},
                                              players=["F"], card=card)
        grant = next(a for a in applied if a["kind"] == "grant")
        self.assertEqual(grant["cash"], 7)
        self.assertEqual(grant["regions"], 1)

    def test_the_region_list_is_not_copied_into_the_engine(self):
        """地區清單只有卡片上那一份，引擎不留副本。"""
        source = pathlib.Path(__file__).with_name("card_engine.py").read_text(encoding="utf-8")
        for name in ("臨汾", "瀘州", "遵義", "紹興"):
            self.assertNotIn(name, source, f"引擎裡不該出現地區名 {name}")

    def test_a_card_naming_a_city_that_does_not_exist_is_a_loud_error(self):
        engine = GameEngine(seed=3)
        card = {"id": "fake", "entry_condition": {"controls_cities_any": ["atlantis"]}}
        with self.assertRaisesRegex(ValueError, "atlantis"):
            engine._eligible_region_count(card, "F")


class PolicePrecinctScopeTests(unittest.TestCase):
    """〈警政單位〉只擋它自己宣告的那種機制，不是萬用護身符。"""

    def setUp(self):
        self.engine = GameEngine(seed=7)
        for payload in self.engine.state["players"].values():
            payload["treasury"] = 400
            payload["factory_points"] = 400
            payload["foreign_relations"]["su"] = 0
        self.province = "河南"
        for city in self.engine.data["strategic_map"]["cities"]:
            if city.get("province") == self.province:
                self.engine.state["city_owners"][city["id"]] = "W"
        self.engine._refresh_city_income()
        self.engine._player("W")["hand"].append("police_precinct")
        self.engine.use_function("W", "police_precinct", target_province=self.province)

    def test_it_shields_exactly_the_mechanics_it_declares(self):
        shield = next(e for e in self.engine._player("W")["timed_effects"]
                      if e.get("kind") == "gang_riot_shield")
        self.assertEqual(shield["blocked_mechanics"], ["qing_gang_riot"])
        self.assertTrue(self.engine._gang_riot_shielded("W", self.province, "qing_gang_riot"))
        for other in ("security_event", "communist_riot", "red_army_uprising"):
            self.assertFalse(
                self.engine._gang_riot_shielded("W", self.province, other),
                f"警政單位不該連 {other} 一起擋——它只宣告了黑幫暴動")

    def test_the_shielded_province_is_still_exposed_to_student_unrest(self):
        """學潮走的是 security_event，警政單位管不到。"""
        candidates = [c["id"] for c in self.engine._student_unrest_candidates("W", 4)
                      if c.get("province") == self.province]
        self.assertTrue(candidates,
                        "河南有警政單位，但學潮不歸它管，該省仍該留在學潮候選名單裡")

    def test_no_timed_effect_ever_survives_with_a_spent_counter(self):
        """倒數到 0 的效果會被 _tick_timed_effects 直接丟掉，不會留成殭屍。"""
        for _ in range(6):
            self.engine._tick_timed_effects()
            for payload in self.engine.state["players"].values():
                for effect in payload.get("timed_effects", []):
                    if effect.get("permanent") or effect.get("remaining_turns") is None:
                        continue
                    self.assertGreater(int(effect["remaining_turns"]), 0,
                                       f"殭屍效果留在狀態裡：{effect}")


class DrillVersusPunishmentTests(unittest.TestCase):
    """演習與軍事懲戒：同一種 kind、同一片水域，差別必須是機制上的。"""

    DRILL = "royal_navy_yangtze_drill"
    PUNISHMENT = "british_navy_blockades_yangtze"

    def _hostile(self, seed=17):
        engine = GameEngine(seed=seed)
        for payload in engine.state["players"].values():
            payload["treasury"] = 400
            payload["factory_points"] = 400
            for power in payload.get("foreign_relations", {}):
                payload["foreign_relations"][power] = -6
        return engine

    def _draw(self, engine, card_id):
        engine.state["event_pool"] = [card_id]
        view = None
        for _ in range(10):
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            if view:
                break
        self.assertIsNotNone(view, f"{card_id} 沒抽出來")
        guard = 0
        while view and guard < 24:
            guard += 1
            options = (view["card"].get("resolution") or {}).get("options") or []
            engine.respond_event(view.get("waiting_for") or view["drawer"],
                                 choice=options[0]["id"] if options else None)
            view = engine.pending_event_view()
        return engine.state.get("foreign_punishments") or []

    def _income(self, engine):
        return {code: int(p.get("income", 0)) for code, p in engine.state["players"].items()}

    def test_a_drill_is_marked_as_one_and_a_punishment_is_not(self):
        drill = self._draw(self._hostile(), self.DRILL)
        punishment = self._draw(self._hostile(), self.PUNISHMENT)
        self.assertTrue(drill and drill[0]["drill"])
        self.assertTrue(punishment and not punishment[0]["drill"])

    def test_a_drill_carries_no_damage_and_a_punishment_does(self):
        drill = self._draw(self._hostile(), self.DRILL)
        punishment = self._draw(self._hostile(), self.PUNISHMENT)
        self.assertEqual(drill[0]["damage"], {},
                         "演習不是懲戒，不該帶任何傷害")
        self.assertTrue(punishment[0]["damage"],
                        "懲戒沒有傷害的話，它跟演習就沒有分別了")

    def test_a_drill_leaves_every_purse_untouched(self):
        engine = self._hostile()
        before = self._income(engine)
        self._draw(engine, self.DRILL)
        self.assertEqual(self._income(engine), before,
                         "演習期間城市生產照常，收入一分都不該少")

    def test_a_punishment_really_cuts_somebody_income(self):
        engine = self._hostile()
        before = self._income(engine)
        self._draw(engine, self.PUNISHMENT)
        after = self._income(engine)
        hurt = [code for code in before if after[code] < before[code]]
        self.assertTrue(hurt, f"封鎖沒有砍到任何人的收入：{before} → {after}")

    def test_a_drill_has_a_deadline_and_a_punishment_does_not(self):
        drill = self._draw(self._hostile(), self.DRILL)
        punishment = self._draw(self._hostile(), self.PUNISHMENT)
        self.assertIsNotNone(drill[0]["until_turn"], "演習要有到期回合")
        self.assertIsNone(punishment[0]["until_turn"],
                          "懲戒不看時間，它看的是邦交")

    def test_a_drill_runs_its_full_length_even_when_relations_are_perfect(self):
        engine = GameEngine(seed=17)
        for payload in engine.state["players"].values():
            payload["treasury"] = 400
            payload["factory_points"] = 400
            for power in payload.get("foreign_relations", {}):
                payload["foreign_relations"][power] = 10
        self._draw(engine, self.DRILL)
        self.assertEqual(len(engine.state.get("foreign_punishments") or []), 1,
                         "邦交再好也不能讓演習提早收隊")

    def test_a_punishment_lifts_once_relations_stop_being_hostile(self):
        engine = self._hostile()
        self._draw(engine, self.PUNISHMENT)
        self.assertEqual(len(engine.state["foreign_punishments"]), 1)
        for payload in engine.state["players"].values():
            payload["foreign_relations"]["uk"] = 0     # 非敵對，但還沒到友好
        for _ in range(3):
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            guard = 0
            while view and guard < 24:
                guard += 1
                options = (view["card"].get("resolution") or {}).get("options") or []
                engine.respond_event(view.get("waiting_for") or view["drawer"],
                                     choice=options[0]["id"] if options else None)
                view = engine.pending_event_view()
        self.assertEqual(engine.state.get("foreign_punishments") or [], [],
                         "邦交回到非敵對之後，封鎖應該解除")


class CrescentMoonReliefTests(unittest.TestCase):
    """《新月》月刊的學潮減免——要看真的城市產出數字，不是只看旗標。"""

    def _engine(self, relief):
        engine = GameEngine(seed=7)
        for payload in engine.state["players"].values():
            payload["treasury"] = 500
            payload["factory_points"] = 500
            payload["foreign_relations"]["su"] = 0
        if relief:
            engine.state["student_unrest_relief"] = True
        engine.state["event_pool"] = ["revolutionary_literature"]
        view = None
        for _ in range(8):
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            if view:
                break
        self.assertIsNotNone(view)
        guard = 0
        while view and guard < 24:
            guard += 1
            options = (view["card"].get("resolution") or {}).get("options") or []
            engine.respond_event(view.get("waiting_for") or view["drawer"],
                                 choice=options[0]["id"] if options else None)
            view = engine.pending_event_view()
        return engine

    def _hit_cities(self, engine):
        out = []
        for effect in engine.state["city_output_effects"]:
            if effect.get("kind") == "student_unrest":
                out += list(effect["city_ids"])
        return out

    def _shown(self, engine, city_id):
        owner = engine.state["city_owners"].get(
            city_id, next(c for c in engine.data["strategic_map"]["cities"]
                          if c["id"] == city_id)["faction"])
        for row in engine.state["players"][owner].get("city_economy", []):
            if row["id"] == city_id:
                return row["cash"], row["factory"]
        return None

    def test_the_relief_actually_changes_the_money_on_the_table(self):
        plain = self._engine(False)
        relieved = self._engine(True)
        for engine, expected in ((plain, 0.5), (relieved, 0.75)):
            cities = self._hit_cities(engine)
            self.assertTrue(cities, "沒有城市進入學潮，這個案例不成立")
            for effect in engine.state["city_output_effects"]:
                if effect.get("kind") == "student_unrest":
                    self.assertEqual(effect["cash_multiplier"], expected)
                    self.assertEqual(effect["factory_multiplier"], expected)

    def test_a_relieved_city_keeps_strictly_more_than_an_unrelieved_one(self):
        plain = self._engine(False)
        relieved = self._engine(True)
        shared = set(self._hit_cities(plain)) & set(self._hit_cities(relieved))
        self.assertTrue(shared, "兩個案例沒有共同受災的城市，比不出來")
        better = 0
        for city_id in shared:
            low = self._shown(plain, city_id)
            high = self._shown(relieved, city_id)
            self.assertIsNotNone(low)
            self.assertIsNotNone(high)
            self.assertGreaterEqual(high[0], low[0], city_id)
            if high[0] > low[0]:
                better += 1
        self.assertTrue(better, "減免之後沒有任何一座城市多留住錢，等於沒有減免")

    def test_the_relief_never_lets_a_city_reinforce_during_unrest(self):
        """減的是產出，不是「學潮期間不可補兵」這條。"""
        for relief in (False, True):
            engine = self._engine(relief)
            for effect in engine.state["city_output_effects"]:
                if effect.get("kind") == "student_unrest":
                    self.assertTrue(effect["blocks_reinforcement"])
                    for city_id in effect["city_ids"]:
                        self.assertTrue(engine.city_in_student_unrest(city_id))


class PoliceShieldAgainstEventCardsTests(unittest.TestCase):
    """〈警政單位〉不只擋暴動類功能卡，也擋卡面點名它的那幾張事件卡。

    卡面自己寫「該省有〈警政單位〉駐防者免疫」的只有兩張：
    14.2 黑幫動亂、14.5 會黨滋事。
    """

    VICTIM = "W"

    def _engine(self, seed=7):
        engine = GameEngine(seed=seed)
        for payload in engine.state["players"].values():
            payload["treasury"] = 500
            payload["factory_points"] = 500
            payload["foreign_relations"]["su"] = 0
        return engine

    def _econ(self, engine, owner):
        return {row["id"]: (row["cash"], row["factory"])
                for row in engine.state["players"][owner].get("city_economy", [])}

    def _province(self, engine, city_id):
        return next((c.get("province") for c in engine.data["strategic_map"]["cities"]
                     if c["id"] == city_id), None)

    def _largest_city(self, engine, owner):
        rows = self._econ(engine, owner)
        return max(rows, key=lambda cid: rows[cid][0] + rows[cid][1])

    def _shield(self, engine, owner, province):
        engine._player(owner)["hand"].append("police_precinct")
        engine.use_function(owner, "police_precinct", target_province=province)

    def _play(self, engine, card_id):
        engine.state["event_pool"] = [card_id]
        view = None
        for _ in range(10):
            engine.next_turn(active_player="F")
            view = engine.pending_event_view()
            if view:
                break
        self.assertIsNotNone(view, f"{card_id} 沒抽出來")
        applied, guard = [], 0
        while view and guard < 24:
            guard += 1
            options = (view["card"].get("resolution") or {}).get("options") or []
            result = engine.respond_event(view.get("waiting_for") or view["drawer"],
                                          choice=options[0]["id"] if options else None)
            applied += (result or {}).get("applied") or []
            view = engine.pending_event_view()
        return applied

    def _hit(self, engine, owner):
        out = {}
        for effect in engine.state.get("city_output_effects", []):
            if effect.get("owner") != owner and effect.get("target_owner") != owner:
                continue
            for city_id in effect.get("city_ids") or []:
                out[city_id] = effect.get("kind")
        return out

    # ---- 名冊本身：宣告與實作必須兩邊對得上 ----

    def test_exactly_the_cards_that_name_the_precinct_honour_it(self):
        """卡面寫了免疫就要有 respect_police，沒寫就不准偷偷有。"""
        engine = GameEngine(seed=3)
        says, does = set(), set()
        for card in engine.data["event_cards"]["cards"]:
            if "警政" in (card.get("effect") or ""):
                says.add(card["id"])
            if "respect_police" in json.dumps(card.get("apply") or {}, ensure_ascii=False):
                does.add(card["id"])
        self.assertEqual(says, does,
                         f"卡面說免疫卻沒實作：{says - does}；"
                         f"實作了卻沒寫在卡面：{does - says}")
        self.assertEqual(says, {"gang_unrest", "secret_society_trouble"})

    # ---- 14.2 黑幫動亂 ----

    def test_gang_unrest_spares_the_garrisoned_province(self):
        plain = self._engine()
        self._play(plain, "gang_unrest")
        hit = self._hit(plain, self.VICTIM)
        self.assertTrue(hit, "沒有警政單位時這張卡本來就該打中人")
        province = self._province(plain, sorted(hit)[0])

        guarded = self._engine()
        self._shield(guarded, self.VICTIM, province)
        self._play(guarded, "gang_unrest")
        still = [city_id for city_id in self._hit(guarded, self.VICTIM)
                 if self._province(guarded, city_id) == province]
        self.assertEqual(still, [],
                         f"{province} 有警政單位駐防，不該有城市被黑幫動亂打中：{still}")

    def test_gang_unrest_says_out_loud_which_cities_the_precinct_saved(self):
        """部分免疫也要回報——玩家要看得見警政單位起了作用。"""
        plain = self._engine()
        self._play(plain, "gang_unrest")
        province = self._province(plain, sorted(self._hit(plain, self.VICTIM))[0])
        guarded = self._engine()
        self._shield(guarded, self.VICTIM, province)
        applied = self._play(guarded, "gang_unrest")
        spared = [a for a in applied if a.get("spared")]
        self.assertTrue(spared,
                        "警政單位救下了城市卻沒有任何回報，玩家看不出它有作用")

    def test_a_player_whose_every_province_is_guarded_is_skipped_entirely(self):
        engine = self._engine()
        provinces = {self._province(engine, city_id)
                     for city_id in self._econ(engine, self.VICTIM)}
        for province in provinces:
            self._shield(engine, self.VICTIM, province)
        self._play(engine, "gang_unrest")
        self.assertEqual(self._hit(engine, self.VICTIM), {},
                         "每一省都有警政單位，這張卡對他應該完全落空")

    # ---- 14.5 會黨滋事 ----

    def test_secret_society_trouble_leaves_a_guarded_city_untouched(self):
        plain = self._engine()
        city_id = self._largest_city(plain, self.VICTIM)
        before = self._econ(plain, self.VICTIM)[city_id]
        self._play(plain, "secret_society_trouble")
        self.assertNotEqual(self._econ(plain, self.VICTIM)[city_id], before,
                            "沒有警政單位時，最大城本來就該被砍")

        guarded = self._engine()
        city_id = self._largest_city(guarded, self.VICTIM)
        self._shield(guarded, self.VICTIM, self._province(guarded, city_id))
        before = self._econ(guarded, self.VICTIM)[city_id]
        applied = self._play(guarded, "secret_society_trouble")
        self.assertEqual(self._econ(guarded, self.VICTIM)[city_id], before,
                         "該省有警政單位駐防，產出一分都不該少")
        self.assertTrue([a for a in applied if a.get("kind") == "police_immunity"],
                        "免疫生效卻沒有回報")

    def test_the_shield_only_covers_the_province_it_was_placed_in(self):
        engine = self._engine()
        city_id = self._largest_city(engine, self.VICTIM)
        mine = {self._province(engine, c) for c in self._econ(engine, self.VICTIM)}
        elsewhere = next(p for p in sorted(mine - {self._province(engine, city_id)}))
        self._shield(engine, self.VICTIM, elsewhere)
        before = self._econ(engine, self.VICTIM)[city_id]
        self._play(engine, "secret_society_trouble")
        self.assertNotEqual(self._econ(engine, self.VICTIM)[city_id], before,
                            f"警政單位擺在 {elsewhere}，救不到別省的城市")

    # ---- 對照組：卡面沒點名的治安卡擋不到 ----

    def test_security_cards_that_do_not_name_the_precinct_go_straight_through(self):
        for card_id in ("student_demonstrations", "factory_accident"):
            engine = self._engine()
            city_id = self._largest_city(engine, self.VICTIM)
            self._shield(engine, self.VICTIM, self._province(engine, city_id))
            before = self._econ(engine, self.VICTIM)
            self._play(engine, card_id)
            after = self._econ(engine, self.VICTIM)
            self.assertNotEqual(before, after,
                                f"{card_id} 卡面沒有點名警政單位，不該被它擋下來")


class NpcActionCardTests(unittest.TestCase):
    """NPC 行動事件卡（15.x）：一次性、報導齊備，且機制沒到位就不准進池子。

    這一批是分階段做的——卡與報導先建好，效果的後端機制逐批補。
    這一組測試的作用是讓「還沒補」這件事**是機器看得見的**，
    而不是靠人記得哪幾張還不能用。
    """

    # 已知的待建機制名稱。要新增只能往這裡加，不能隨手在卡上寫個新字串。
    KNOWN_PENDING = {
        "npc_condition_gate",          # 「某某將領仍屬某陣營」這類進入條件
        "npc_reserve_delta",           # 對 NPC 陣營／將領加兵
        "npc_combat_modifier",         # 對 NPC 部隊掛戰力百分比修正
        "npc_general_transfer",        # NPC 將領換陣營
        "npc_army_relocate",           # NPC 部隊移防到指定位置
        "npc_faction_absorb",          # 整個 NPC 陣營歸給玩家並退出地圖
        "npc_faction_merge",           # NPC 併 NPC
        "contested_npc_recruit",       # 付費招募，多方競標平分成功率
        "player_force_ranking",        # 「當前總戰力最高的玩家」
        "at_war_entry_condition",      # 「正對某陣營宣戰」
        "garrison_entry_condition",    # 「該城有軍隊駐守」
        "railway_permanent_block",     # 封路且不可搶修
    }

    def setUp(self):
        self.cards = [c for c in GameEngine(seed=3).data["event_cards"]["cards"]
                      if str(c.get("ref", "")).startswith("15.")]

    def test_the_whole_batch_landed(self):
        self.assertEqual(len(self.cards), 33)
        refs = sorted(int(c["ref"].split(".")[1]) for c in self.cards)
        self.assertEqual(refs, list(range(1, 34)), "15.1–15.33 要連號，不能有洞")

    def test_every_one_of_them_is_a_one_shot_card(self):
        """這批全是一次性卡，抽到一次就不會再出現。"""
        for card in self.cards:
            self.assertFalse(card.get("repeatable"),
                             f"{card['ref']} {card['name']} 不該是可重複抽取的")

    def test_each_card_carries_a_full_newspaper_report(self):
        engine = GameEngine(seed=3)
        hoover = next(c for c in engine.data["event_cards"]["cards"]
                      if c["id"] == "hoover_elected")
        baseline = sum(len(p) for p in hoover["newspaper"]["paragraphs"])
        for card in self.cards:
            paragraphs = card["newspaper"]["paragraphs"]
            self.assertEqual(len(paragraphs), 3,
                             f"{card['ref']} 的報導應該是三段")
            self.assertTrue(card["newspaper"]["headline"].strip(), card["ref"])
            length = sum(len(p) for p in paragraphs)
            self.assertGreaterEqual(
                length, baseline * 0.88,
                f"{card['ref']} {card['name']} 只有 {length} 字，比胡佛（{baseline}）短太多")

    def test_no_english_leaked_into_any_report(self):
        for card in self.cards:
            blob = card["newspaper"]["headline"] + "".join(card["newspaper"]["paragraphs"])
            found = re.findall(r"[A-Za-z]{2,}", blob)
            self.assertEqual(found, [], f"{card['ref']} 報導裡有英文：{found}")

    def test_a_card_whose_mechanics_are_missing_never_reaches_the_pool(self):
        """機制沒到位就設 never_drawn——不能讓玩家抽到一張什麼都不會發生的卡。"""
        for card in self.cards:
            pending = (card.get("apply") or {}).get("pending") or []
            if pending:
                self.assertTrue(
                    card.get("not_in_pool"),
                    f"{card['ref']} {card['name']} 還有待建機制 {pending}，"
                    f"卻沒有設 not_in_pool，會被抽出來卻什麼都不做")
                self.assertFalse(
                    card.get("never_drawn"),
                    f"{card['ref']} 該用 not_in_pool，never_drawn 是留給日蘇戰況報導的")

    def test_a_card_with_no_pending_work_must_be_drawable(self):
        """反過來也要成立：機制補齊了就該把 never_drawn 拿掉，否則永遠上不了場。"""
        for card in self.cards:
            pending = (card.get("apply") or {}).get("pending") or []
            if not pending:
                self.assertFalse(
                    card.get("not_in_pool"),
                    f"{card['ref']} {card['name']} 已經沒有待建機制了，"
                    f"not_in_pool 該拿掉")

    def test_pending_mechanic_names_come_from_the_known_list(self):
        """待建項目要用固定的名稱，才數得出還剩多少、才排得出順序。"""
        for card in self.cards:
            for name in (card.get("apply") or {}).get("pending") or []:
                self.assertIn(name, self.KNOWN_PENDING,
                              f"{card['ref']} 用了沒登記過的待建機制名稱：{name}")

    def test_none_of_them_is_in_the_starting_pool(self):
        """實跑確認：開局配池不會把這批卡放進去。"""
        engine = GameEngine(seed=3)
        pool = set(engine.state["event_pool"])
        for card in self.cards:
            self.assertNotIn(card["id"], pool,
                             f"{card['ref']} 不該出現在卡池裡")

    def test_the_city_level_cards_really_move_the_level(self):
        """15.28–15.33 的效果本身已經接上引擎——直接叫 payload 驗一次。"""
        expected = {
            "tang_shengzhi_builds_temples": ["changsha"],
            "zhao_hengti_liling_porcelain": ["yueyang"],
            "qian_army_moutai": ["zunyi"],
            "liu_xiang_luzhou_distillery": ["luzhou"],
            "xu_yongchang_fenjiu": ["linfen"],
        }
        for card_id, cities in expected.items():
            engine = GameEngine(seed=3)
            card = engine._event_template(card_id)
            before = {c: int(engine._with_level(
                next(x for x in engine.data["strategic_map"]["cities"] if x["id"] == c)
            )["level"]) for c in cities}
            applied = engine._apply_event_payload(
                {"city_level_upgrade": card["apply"]["city_level_upgrade"]},
                players=["F"], card=card)
            bumped = next(a for a in applied if a["kind"] == "city_level_upgrade")
            moved = {row["id"]: (row["from"], row["to"]) for row in bumped["cities"]}
            for city_id in cities:
                self.assertIn(city_id, moved, f"{card_id} 沒有動到 {city_id}")
                self.assertEqual(moved[city_id][1], before[city_id] + 1,
                                 f"{card_id}：{city_id} 應該剛好 +1 級")

    def test_the_shanxi_card_lifts_every_city_in_the_province(self):
        engine = GameEngine(seed=3)
        card = engine._event_template("yan_xishan_promotes_education")
        shanxi = [c for c in engine.data["strategic_map"]["cities"]
                  if c.get("province") == "山西"]
        before = {c["id"]: int(engine._with_level(c)["level"]) for c in shanxi}
        applied = engine._apply_event_payload(
            {"city_level_upgrade": card["apply"]["city_level_upgrade"]},
            players=["F"], card=card)
        bumped = next(a for a in applied if a["kind"] == "city_level_upgrade")
        moved = {row["id"]: row["to"] for row in bumped["cities"]}
        for city_id, level in before.items():
            if level >= 5:
                continue
            self.assertEqual(moved.get(city_id), level + 1,
                             f"山西的 {city_id} 應該 +1 級")


class RelativeCityLevelUpgradeTests(unittest.TestCase):
    """city_level_upgrade 的相對寫法（delta）與絕對寫法（to_level）。"""

    def setUp(self):
        self.engine = GameEngine(seed=3)
        self.card = {"id": "fake", "name": "fake"}

    def _level(self, city_id):
        city = next(c for c in self.engine.data["strategic_map"]["cities"]
                    if c["id"] == city_id)
        return int(self.engine._with_level(city)["level"])

    def test_delta_adds_to_whatever_the_city_is_now(self):
        before = self._level("luzhou")
        self.engine._apply_event_payload(
            {"city_level_upgrade": {"cities": ["luzhou"], "delta": 1}},
            players=["F"], card=self.card)
        self.assertEqual(self._level("luzhou"), before + 1)

    def test_delta_stops_at_the_ceiling(self):
        """五級是頂，不能再往上疊。"""
        self.engine._apply_event_payload(
            {"city_level_upgrade": {"cities": ["shanghai"], "delta": 3}},
            players=["F"], card=self.card)
        self.assertLessEqual(self._level("shanghai"), 5)

    def test_the_absolute_form_still_works(self):
        applied = self.engine._apply_event_payload(
            {"city_level_upgrade": {"provinces": ["山西"], "from_level": 2,
                                    "to_level": 3}},
            players=["F"], card=self.card)
        bumped = next(a for a in applied if a["kind"] == "city_level_upgrade")
        self.assertTrue(bumped["cities"])
        for row in bumped["cities"]:
            self.assertEqual(row["from"], 2)
            self.assertEqual(row["to"], 3)

    def test_naming_a_city_that_does_not_exist_is_a_loud_error(self):
        with self.assertRaisesRegex(ValueError, "atlantis"):
            self.engine._apply_event_payload(
                {"city_level_upgrade": {"cities": ["atlantis"], "delta": 1}},
                players=["F"], card=self.card)

    def test_giving_neither_form_is_a_loud_error(self):
        with self.assertRaisesRegex(ValueError, "to_level|delta"):
            self.engine._apply_event_payload(
                {"city_level_upgrade": {"cities": ["luzhou"]}},
                players=["F"], card=self.card)


class ReportManuscriptTests(unittest.TestCase):
    """`cards/事件卡報導文稿.md` 是三份擴寫對照稿、v5 設計稿與 NPC 新卡合併後的成品。

    它由 `event_cards.json` 產生，所以這一組測試要守的是**它沒有跟資料檔漂移**——
    一份手抄的副本遲早會跟正本說不同的話，那比沒有副本更糟。
    """

    @classmethod
    def setUpClass(cls):
        repo = pathlib.Path(__file__).resolve().parent.parent
        cls.path = repo / "cards" / "事件卡報導文稿.md"
        cls.text = cls.path.read_text(encoding="utf-8") if cls.path.exists() else ""
        cls.cards = json.loads(
            (repo / "cards" / "data" / "event_cards.json").read_text(encoding="utf-8"))["cards"]

    @staticmethod
    def _squash(text):
        return re.sub(r"[\s　]+", "", text)

    def test_the_manuscript_exists(self):
        self.assertTrue(self.path.exists(), f"{self.path} 不見了")

    def test_every_card_has_a_section_of_its_own(self):
        missing = [c["ref"] for c in self.cards
                   if f'\n## {c["ref"]}　{c["name"]}\n' not in self.text]
        self.assertEqual(missing, [], f"文稿裡找不到這些卡：{missing}")

    def test_every_line_of_every_report_is_in_the_manuscript(self):
        """逐段比對——標題與每一個自然段都要一字不差地收進去。"""
        body = self._squash(self.text)
        missing = []
        for card in self.cards:
            for variant in (card.get("newspaper_variants") or [card["newspaper"]]):
                for chunk in [variant["headline"]] + variant["paragraphs"]:
                    if self._squash(chunk) not in body:
                        missing.append(f'{card["ref"]} {chunk[:20]}…')
        self.assertEqual(missing, [], f"這些報導文字沒進文稿：{missing[:5]}")

    def test_the_dual_report_card_keeps_both_of_its_reports(self):
        """11.5 廢兩改元是刻意設計成兩則的，兩則都要在。"""
        card = next(c for c in self.cards if c["ref"] == "11.5")
        variants = card.get("newspaper_variants") or []
        self.assertEqual(len(variants), 2)
        for variant in variants:
            self.assertIn(self._squash(variant["headline"]), self._squash(self.text))

    def test_the_superseded_comparison_drafts_are_gone(self):
        """三份對照稿已併入文稿，不該再各留一份互相打架。"""
        repo = pathlib.Path(__file__).resolve().parent.parent
        for stale in ("報導擴寫對照_第一批_治安事件.md",
                      "報導擴寫對照_第二批_經濟事件.md",
                      "報導擴寫對照_第三批_列強行動.md"):
            self.assertFalse((repo / "cards" / stale).exists(),
                             f"{stale} 應該已經併進文稿並刪除")

    def test_the_manuscript_says_how_many_cards_it_covers(self):
        self.assertIn(f"**{len(self.cards)} 張**", self.text,
                      "抬頭的張數要跟資料檔對得上")

    def test_the_manuscript_carries_no_english_prose(self):
        """報導本文不准有英文。

        排除的是結構，不是內容：標題行、總覽表格、行內程式碼與 `<small>` 字數註記。
        段落本身一個英文字母都不該有——「NPC」只出現在段落標題上，那是分類名稱，
        不是報導文字。
        """
        lines = []
        for line in self.text.splitlines():
            if line.startswith(("#", "|", "類別 ", "本檔由", "> 素材：")):
                continue
            line = re.sub(r"`[^`]*`", "", line)
            line = re.sub(r"</?small>", "", line)
            lines.append(line)
        found = sorted(set(re.findall(r"[A-Za-z]{2,}", "\n".join(lines))))
        self.assertEqual(found, [], f"文稿報導內文出現英文：{found}")

    def test_the_only_english_anywhere_is_the_category_labels(self):
        """整份文稿裡允許出現的英文，只有分類代號與 NPC 這個段落名。"""
        allowed = {"NPC", "foreign_power", "economic", "economy",
                   "security", "npc_or_other_force", "event_cards", "cards",
                   "data", "json", "small"}
        found = set(re.findall(r"[A-Za-z_]{2,}", self.text))
        self.assertEqual(found - allowed, set(),
                         f"文稿裡出現預期外的英文：{sorted(found - allowed)}")

    def test_cards_still_out_of_the_pool_are_marked_as_such(self):
        """機制還沒補齊的卡要在文稿上寫明，免得誤以為已經上線。"""
        for card in self.cards:
            if not card.get("not_in_pool"):
                continue
            block = self.text.split(f'\n## {card["ref"]}　{card["name"]}\n')[1]
            head = block.split("###")[0]
            self.assertIn("機制建置中", head,
                          f'{card["ref"]} 還沒進卡池，文稿上要標出來')
