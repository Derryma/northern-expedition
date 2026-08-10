import unittest

from backend.card_engine import FOREIGN_FRIENDLY_THRESHOLD, GameEngine, RECRUIT_COSTS
from backend.combat_adapter import simulate
from backend.data_store import load_game_data
from economy import LoanBook

LOANS = LoanBook()


class BackendTests(unittest.TestCase):
    def test_data_loads_with_unique_card_ids(self):
        data = load_game_data()

        self.assertGreater(data["metadata"]["event_cards"], 100)
        self.assertGreater(data["metadata"]["function_cards"], 50)
        self.assertGreater(data["metadata"]["injected_event_cards"], 10)

    def test_turn_keeps_events_disabled_and_does_not_auto_buy_function_cards(self):
        engine = GameEngine(seed=7)
        result = engine.next_turn()

        self.assertEqual(result["turn"]["turn"], 1)
        self.assertIsNone(result["turn"]["event"])
        self.assertIsNone(result["turn"]["function_purchase_offer"])
        for player in ("F", "W", "S", "N"):
            self.assertEqual(result["state"]["counts"]["players"][player]["hand"], 0)
            self.assertFalse(result["state"]["players"][player]["function_purchase_used"])
        self.assertEqual(engine.bootstrap()["features"]["event_interval"], 3)

    def test_active_player_gets_optional_function_purchase_offer(self):
        engine = GameEngine(seed=7)
        result = engine.next_turn(active_player="N")

        self.assertEqual(result["turn"]["function_purchase_offer"], "N")
        for player in ("F", "W", "S", "N"):
            self.assertEqual(result["state"]["counts"]["players"][player]["hand"], 0)

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
        self.assertEqual(updated["army_reinforcements"]["N-1"]["infantry"], 1)

    def test_captured_major_city_can_reinforce_army(self):
        engine = GameEngine(seed=5)
        engine.capture_city("hankou", "N")
        before = engine.state["players"]["N"]["unit_reserves"]["machine_gun"]

        result = engine.reinforce_army("N", "N-1", "hankou", "machine_gun")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["unit_reserves"]["machine_gun"], before - 1)
        self.assertEqual(updated["army_reinforcements"]["N-1"]["machine_gun"], 1)

    def test_restore_snapshot_rehydrates_engine_state(self):
        engine = GameEngine(seed=5)
        snapshot = engine.capture_city("hankou", "N")["state"]
        fresh = GameEngine(seed=8)

        restored = fresh.restore_snapshot(snapshot)

        self.assertEqual(restored["turn"], snapshot["turn"])
        self.assertEqual(restored["city_owners"]["hankou"], "N")
        self.assertEqual(restored["players"]["N"]["income"], snapshot["players"]["N"]["income"])

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
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("foreign_relation_jp"), 4)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("young_marshal_rises"), 1)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("wang_yongjiang_financial_reform"), 1)
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("forced_march"), 8)
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

    def test_forced_march_creates_rural_movement_effect(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["forced_march"]

        result = engine.use_function("N", "forced_march")

        self.assertEqual(result["timed_effect"]["kind"], "rural_movement")
        self.assertEqual(result["timed_effect"]["tiles"], 2)
        self.assertEqual(result["timed_effect"]["remaining_turns"], 3)

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

        self.assertEqual(updated["last_debt_service"]["interest"], 1)  # round(20 * 0.03)
        self.assertEqual(updated["debt"], 21)
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

        這裡刻意不寫死任何陣營代號：規則是「跨過友好門檻就有 2 張，掉下去就收走」，
        開局誰拿得到只是初始關係值的結果，不是陣營特權。
        """
        cards = ("communist_riot", "red_army_uprising")
        for card_id in cards:
            self.assertIsNone(load_game_data()["indexes"]["function_cards"][card_id].get("allowed_players"), card_id)

        engine = GameEngine(seed=3)
        friendly = FOREIGN_FRIENDLY_THRESHOLD
        for code in engine.state["players"]:
            player = engine.state["players"][code]
            for relation, expected in ((friendly, 2), (friendly - 1, 0)):
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
            engine.next_turn("F")
            self.assertEqual(engine.disabled_railways(), ["京漢鐵路"])
        engine.next_turn("F")
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
        self.assertAlmostEqual(loan["interest_per_turn"], 0.03)
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
            engine.next_turn("S")
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

    def test_warlord_bond_makes_bank_lending_a_gamble(self):
        engine = GameEngine(seed=6)
        player = engine.state["players"]["N"]
        self.assertIsNone(player["bank_success_rate"])
        player["hand"].append("function_軍閥公債")
        cash_before = player["treasury"]
        engine.use_function("N", "function_軍閥公債")
        self.assertEqual(player["treasury"], cash_before + 50)
        self.assertEqual(player["loans"][-1]["principal"], 25)
        self.assertAlmostEqual(player["loans"][-1]["interest_per_turn"], 0.05)
        self.assertAlmostEqual(player["bank_success_rate"], 0.75)

        player["foreign_relations"]["uk"] = 0
        accepted = refused = 0
        for _ in range(400):
            try:
                engine.take_loan("N", "hsbc", 1)
                accepted += 1
                player["loans"] = [loan for loan in player["loans"] if loan["bank"] != "hsbc"]
            except ValueError as error:
                self.assertIn("拒絕", str(error))
                refused += 1
        self.assertAlmostEqual(accepted / 400, 0.75, delta=0.06)

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

        self.assertAlmostEqual(new_loan["interest_per_turn"], 0.02)
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
            engine.next_turn("S")
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

    def test_free_china_educators_shield_and_its_criteria(self):
        engine = GameEngine(seed=8)
        shielded = engine.state["players"]["F"]      # 開局持北京、對蘇 -7
        rival = engine.state["players"]["N"]

        # 同回合對手先出手，護盾要能回頭取消掉。
        rival["hand"].append("communist_riot")
        engine.use_function("N", "communist_riot", target_owner="F")
        hurt_income = shielded["income"]
        shielded["hand"].append("free_china_educators")
        result = engine.use_function("F", "free_china_educators")
        self.assertEqual(result["timed_effect"]["cancelled_effects"], ["共黨暴動"])
        self.assertGreater(shielded["income"], hurt_income)
        self.assertEqual(result["timed_effect"]["remaining_turns"], 10)

        for card_id in ("communist_riot", "red_army_uprising"):
            rival["hand"].append(card_id)
            with self.assertRaisesRegex(ValueError, "自由中國教育家"):
                engine.use_function("N", card_id, target_owner="F")

    def test_free_china_educators_requires_beijing_and_a_cool_moscow(self):
        engine = GameEngine(seed=8)
        player = engine.state["players"]["N"]        # 對蘇 9，不持北京
        player["hand"].append("free_china_educators")
        with self.assertRaisesRegex(ValueError, "北京"):
            engine.use_function("N", "free_china_educators")
        engine.state["city_owners"]["beijing"] = "N"
        with self.assertRaisesRegex(ValueError, "對蘇關係"):
            engine.use_function("N", "free_china_educators")

    def test_peking_university_movement_cancels_the_shield(self):
        engine = GameEngine(seed=8)
        shielded = engine.state["players"]["F"]
        rival = engine.state["players"]["N"]
        shielded["hand"].append("free_china_educators")
        engine.use_function("F", "free_china_educators")

        rival["hand"].append("peking_university_movement")
        result = engine.use_function("N", "peking_university_movement")
        self.assertEqual(result["unlock_effect"]["cleared"], ["F"])
        self.assertIsNone(engine._ideology_shield("F", "communist_riot"))

        # 護盾沒了，暴動又打得進去。
        rival["hand"].append("communist_riot")
        engine.use_function("N", "communist_riot", target_owner="F")

        rival["hand"].append("peking_university_movement")
        with self.assertRaisesRegex(ValueError, "沒有生效中"):
            engine.use_function("N", "peking_university_movement")

    def test_peking_university_movement_needs_moscow_on_side(self):
        engine = GameEngine(seed=8)
        engine.state["players"]["F"]["hand"].append("free_china_educators")
        engine.use_function("F", "free_china_educators")
        rival = engine.state["players"]["W"]         # 對蘇 -8
        rival["hand"].append("peking_university_movement")
        with self.assertRaisesRegex(ValueError, "對蘇關係需達"):
            engine.use_function("W", "peking_university_movement")


    # ---- 第五批：反共條件、外交副作用、交涉成功率、卡面故事 ----------------

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
        for player, card_id in (("W", "zhili_anti_communist_declaration"), ("F", "free_china_educators")):
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

    def test_negotiation_succeeds_about_seventy_percent_and_does_nothing_on_failure(self):
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
        self.assertAlmostEqual(wins / rounds, 0.70, delta=0.03)

    def test_every_negotiation_card_carries_the_same_odds(self):
        index = load_game_data()["indexes"]["function_cards"]
        for power in ("jp", "su", "uk", "fr", "us"):
            self.assertAlmostEqual(index["foreign_relation_" + power]["success_rate"], 0.70, msg=power)

    def test_twentyseven_cards_carry_a_story(self):
        # 17 → 18（在野名將投效）→ 27：設立情報局、盜賣文物、中國人之恥、
        # 警政單位、五張貿易出口卡各補了故事。
        cards = load_game_data()["function_cards"]["cards"]
        with_story = [card for card in cards if card.get("story")]
        self.assertEqual(len(with_story), 27)
        for card in with_story:
            self.assertTrue(card["story"].strip(), card["id"])

    def test_narrative_moved_out_of_the_effect_text(self):
        """這五張的敘事原本混在效果文字裡，現在只應該出現在 story。"""
        index = load_game_data()["indexes"]["function_cards"]
        moved = {
            "wang_jingwei_return": "汪精衛返華",
            "free_china_educators": "蔡元培",
            "peking_university_movement": "李大釗",
            "soong_patronage": "宋家",
            "kong_xiangxi_office": "孔祥熙",
        }
        for card_id, phrase in moved.items():
            card = index[card_id]
            self.assertIn(phrase, card["story"], card_id)
            self.assertNotIn(phrase, card["effect"], card_id)


if __name__ == "__main__":
    unittest.main()


class ExileGeneralTests(unittest.TestCase):
    """在野將領池與〈在野名將投效〉。"""

    POOL_IDS = {
        "duan_qirui", "chen_jiongming", "lu_hongtao", "tian_zhongyu",
        "wang_chengbin", "li_houji", "lu_yongxiang",
    }

    def test_pool_holds_the_seven_generals_off_board_and_factionless(self):
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
        self.assertEqual(outcome["price"], 22)          # 延攬費為身價全額
        self.assertEqual(outcome["owner"], "W")
        self.assertEqual(outcome["units"], {"infantry": 6, "cavalry": 1, "artillery": 2, "machine_gun": 1})
        self.assertEqual(engine.state["players"]["W"]["treasury"], before - 22)
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
            self.assertEqual(deck.count("local_autonomy_agitation"), 5, code)
            self.assertEqual(deck.count("body_guard_squad"), 5, code)
            self.assertEqual(deck.count("wang_yaqiao_assassination"), 3, code)
            self.assertEqual(deck.count("forced_march"), 8, code)
            self.assertEqual(deck.count("artifact_smuggling"), 3, code)
            self.assertEqual(deck.count("police_precinct"), 5, code)
            for power in ("jp", "su", "uk", "fr", "us"):
                self.assertEqual(deck.count(f"trade_export_{power}"), 3, f"{code}/{power}")
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
