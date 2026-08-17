import re
import unittest

from backend.card_engine import (
    FOREIGN_CONDEMNATION_CARDS,
    FOREIGN_PERK_CARDS,
    FOREIGN_CONDEMNATION_COPIES,
    FOREIGN_FRIENDLY_THRESHOLD,
    FOREIGN_HOSTILE_THRESHOLD,
    GameEngine,
    RECRUIT_COSTS,
)
from backend.combat_adapter import simulate
from backend.data_store import load_game_data
from economy import LoanBook

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
        self.assertEqual(data["metadata"]["event_cards"], 55)   # 設計稿一到十一區塊
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
        result = engine.pay_navy_move("N")
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
        engine.state["players"]["N"]["foreign_relations"]["su"] = 7
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

    def test_wang_jingwei_return_unlocks_the_united_front_and_cheapens_infantry(self):
        engine = GameEngine(seed=11)
        player = engine.state["players"]["N"]
        self.assertEqual(player["function_deck"].count("wang_jingwei_return"), 1)
        self.assertEqual(player["function_deck"].count("first_united_front"), 0)

        cash_before, _ = engine._unit_cost_for("N", "infantry")
        factory_before = player["factory_income"]
        player["hand"].append("wang_jingwei_return")
        engine.use_function("N", "wang_jingwei_return")

        self.assertIn("wang_jingwei_return", player["unlocks"])
        self.assertEqual(player["function_deck"].count("first_united_front"), 1)
        self.assertEqual(engine._unit_cost_for("N", "infantry")[0], cash_before - 1)
        self.assertEqual(player["factory_income"], factory_before + 1)

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
        player = engine.state["players"]["S"]
        player["unlocks"].append("jiangzhe_financiers")
        player["hand"].append("soong_patronage")
        engine.use_function("S", "soong_patronage")

        while engine.state["turn"] % 3 or not engine.state["turn"]:
            advance_turn(engine, "S")
        paid = [item for item in player["last_debt_service"]["cash_effects"] if item["name"] == "上海宋家支持"]
        self.assertEqual(paid, [{"name": "上海宋家支持", "amount": 5, "factory": 3, "cities": ["上海"]}])

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
        # 十五張列強友好卡 → 66；大港開炸再 +1 → 67。
        self.assertEqual(len(with_story), 67)
        for card in with_story:
            self.assertTrue(card["story"].strip(), card["id"])

    def test_narrative_moved_out_of_the_effect_text(self):
        """這五張的敘事原本混在效果文字裡，現在只應該出現在 story。"""
        index = load_game_data()["indexes"]["function_cards"]
        moved = {
            "wang_jingwei_return": "汪精衛返華",
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
        self.assertEqual(len(engine.state["event_pool"]), 55)
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
        engine.respond_event(engine.pending_event_view()["waiting_for"])
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("su_rifle_shipment"), 2)
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

    def test_kellogg_signatories_get_paid_three_turns_later(self):
        engine = GameEngine(seed=3)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["kellogg_briand_pact"]
        engine.next_turn(active_player="F")
        entry = engine.state["pending_events"]["cards"][0]
        entry["drawer"] = "F"
        entry["responders"] = ["F"]
        engine.respond_event("F", choice="sign")
        signer = engine.state["players"]["F"]
        self.assertTrue(any(effect["kind"] == "ceasefire" for effect in signer["timed_effects"]))
        self.assertFalse(any(effect["kind"] == "ceasefire"
                             for effect in engine.state["players"]["W"]["timed_effects"]))
        before = signer["treasury"]
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

        while engine.pending_event_view():
            current = engine.pending_event_view()
            resolution = current["card"].get("resolution") or {}
            choice = (resolution.get("options") or [{}])[0].get("id") if resolution.get("type") == "choice" else None
            engine.respond_event(current["waiting_for"], choice=choice)
        # 唯一一則結完，本回合的經濟才補跑。
        self.assertEqual(engine.state["turn_log"][-1]["turn"], 3)
        self.assertEqual(len(engine.state["event_history"]), 1)
        self.assertEqual(len(engine.state["event_pool"]), 54)

    def test_choice_cards_only_ask_the_drawer(self):
        """選擇事件只由本次抽中的勢力表態，效果只先落到那一家。"""
        engine = GameEngine(seed=3)
        card = engine._event_template("arcos_raid")
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["arcos_raid"]
        engine.next_turn(active_player="F")
        entry = engine.state["pending_events"]["cards"][0]
        entry["drawer"] = "F"
        entry["responders"] = ["F"]
        view = engine.pending_event_view()
        self.assertEqual(view["card"]["id"], "arcos_raid")
        self.assertEqual(view["responders"], ["F"])
        self.assertTrue(view["strict_order"])
        self.assertFalse(view["needs_every_faction"])
        self.assertEqual(card["resolution"]["type"], "choice")

        with self.assertRaisesRegex(ValueError, "現在輪到"):
            engine.respond_event("W", choice="back_britain")
        with self.assertRaisesRegex(ValueError, "需要選擇"):
            engine.respond_event("F")

        uk_before = {code: engine.state["players"][code]["foreign_relations"]["uk"] for code in "FWSN"}
        engine.respond_event("F", choice="back_britain")
        self.assertEqual(engine.state["players"]["F"]["foreign_relations"]["uk"], min(10, uk_before["F"] + 2))
        # 每家的選擇只作用在自己身上。
        self.assertEqual(engine.state["players"]["W"]["foreign_relations"]["uk"], uk_before["W"])
        self.assertIsNone(engine.state["pending_events"])
        self.assertEqual(engine.state["event_history"][-1]["responses"], {"F": "back_britain"})

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
        self.assertEqual(view["drawer"], "F")
        self.assertEqual(view["waiting_for"], "F")
        with self.assertRaisesRegex(ValueError, "現在輪到 F"):
            engine.respond_event("N")
        engine.respond_event("F")
        self.assertIsNone(engine.state["pending_events"])
        self.assertEqual(engine.state["event_history"][-1]["responses"], {"F": "acknowledged"})

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
        engine.respond_event("F")
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
        engine.respond_event("F")
        self.assertEqual(payload["function_deck"].count("jp_yokohama_specie_loan"), 0)
        with self.assertRaisesRegex(ValueError, "橫濱正金"):
            engine.take_loan("F", "yokohama_specie", 10)

    def test_event_card_can_rewrite_a_function_card(self):
        engine = GameEngine(seed=3)
        self.assertEqual(engine._card_template("artifact_smuggling")["payout_min"], 20)
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["bird_in_space_case"]
        engine.next_turn(active_player="F")
        engine.respond_event("F")
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
        self.assertGreaterEqual(len(seen) + len(engine.state["event_pool"]), 55)


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
            {"event_pool_add": [{"tags": ["軍事"], "powers": ["日"], "copies": 2}]},
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

    def test_the_comprador_sometimes_blocks_japanese_condemnation_cards(self):
        # 每張 10% 機率被擋，三張至少擋掉一張的機率約 27%，
        # 所以固定種子掃一輪應該同時看得到「有擋到」與「沒擋到」。
        blocked = 0
        for seed in range(40):
            engine = GameEngine(seed=seed)
            engine.state["faction_general_traits"] = {"W": ["japanese_comprador"]}
            engine.state["condemnation_blocked"] = {}
            engine.state["players"]["W"]["foreign_relations"]["jp"] = FOREIGN_HOSTILE_THRESHOLD
            engine._sync_foreign_deck_cards("W")
            count = engine.state["players"]["W"]["function_deck"].count("jp_condemnation")
            self.assertLessEqual(count, FOREIGN_CONDEMNATION_COPIES)
            if count < FOREIGN_CONDEMNATION_COPIES:
                blocked += 1
        self.assertGreater(blocked, 0)
        self.assertLess(blocked, 40)

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

    def test_the_french_comprador_blocks_more_condemnations_than_the_japanese_one(self):
        def blocked_copies(trait, power):
            blocked = 0
            for seed in range(60):
                engine = GameEngine(seed=seed)
                engine.state["faction_general_traits"] = {"W": [trait]}
                engine.state["condemnation_blocked"] = {}
                engine.state["players"]["W"]["foreign_relations"][power] = FOREIGN_HOSTILE_THRESHOLD
                engine._sync_foreign_deck_cards("W")
                blocked += FOREIGN_CONDEMNATION_COPIES - engine.state["players"]["W"]["function_deck"].count(
                    FOREIGN_CONDEMNATION_CARDS[power]
                )
            return blocked

        # 法國買辦 30% 對日本買辦 10%，擋下的總張數應該明顯較多。
        self.assertGreater(blocked_copies("french_comprador", "fr"), blocked_copies("japanese_comprador", "jp"))

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
        """9.4：五張貿易出口卡收益提升至 30，杭州每回合現金 +2。"""
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
        payload = engine.state["players"]["F"]
        payload["unit_reserves"]["infantry"] = 9
        payload["unit_reserves"]["cavalry"] = 4
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_economic_conference"]
        engine.next_turn(active_player="F")
        view = engine.pending_event_view()
        self.assertEqual(view["card"]["resolution"]["type"], "choice")
        engine.respond_event(view["waiting_for"], choice="disarm")
        self.assertEqual(payload["unit_reserves"]["infantry"], 7)
        self.assertEqual(payload["unit_reserves"]["cavalry"], 3)
        self.assertEqual(payload["loan_rate_overrides"], [])       # 裁成功就沒有懲罰

    def test_disarmament_falls_back_to_keeping_the_army_when_short(self):
        """預備隊湊不出步兵 2＋騎兵 1 時，自動改為不裁並吃下懲罰。"""
        engine = GameEngine(seed=3)
        payload = engine.state["players"]["F"]
        payload["unit_reserves"]["infantry"] = 1     # 不夠
        payload["unit_reserves"]["cavalry"] = 4
        engine.state["turn"] = 2
        engine.state["event_pool"] = ["national_economic_conference"]
        engine.next_turn(active_player="F")
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
        engine.respond_event(engine.pending_event_view()["waiting_for"], choice="keep_army")
        payload = engine.state["players"]["F"]
        payload["hand"].append("function_軍閥公債")
        engine.use_function("F", "function_軍閥公債")
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
        result = engine.respond_event(engine.pending_event_view()["waiting_for"], choice=choice)
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
        payload = engine.state["players"]["F"]
        payload["unit_reserves"]["infantry"] = 9
        payload["unit_reserves"]["cavalry"] = 4
        base = engine._delayed_output_bonus("F")
        self._fire(engine, "national_economic_conference", choice="disarm")
        during = engine._delayed_output_bonus("F")
        self.assertEqual(during["cash"] - base["cash"], 8)
        self.assertEqual(during["factory"] - base["factory"], 4)
        for _ in range(3):
            advance_turn(engine, "F")
        after = engine._delayed_output_bonus("F")
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


class EventCardCoverageTest(unittest.TestCase):
    """守門測試：每一張有機械化效果的事件卡都要被某條測試指名引用過。

    新增事件卡卻忘了寫測試時，這條會擋下來。
    """

    def test_every_card_with_an_effect_is_referenced_by_some_test(self):
        import pathlib
        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        data = load_game_data()
        missing = []
        for card in data["event_cards"]["cards"]:
            apply_block = card.get("apply") or {}
            has_effect = bool([k for k in apply_block if k != "notes"]) or any(
                option.get("apply")
                for option in ((card.get("resolution") or {}).get("options") or []))
            if has_effect and f'"{card["id"]}"' not in source:
                missing.append(f'{card.get("ref")} {card["name"]} ({card["id"]})')
        self.assertEqual(missing, [], "這些事件卡有效果卻沒有任何測試引用：" + "、".join(missing))


if __name__ == "__main__":
    unittest.main()
