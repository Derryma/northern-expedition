import unittest

from backend.card_engine import GameEngine
from backend.combat_adapter import simulate
from backend.data_store import load_game_data


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

        self.assertEqual(updated["treasury"], before[0] - 13)
        self.assertEqual(updated["factory_points"], before[1] - 4)
        self.assertEqual(updated["unit_reserves"]["artillery"], before[2] + 1)

    def test_infantry_cost_matches_three_to_four_minor_city_turns(self):
        engine = GameEngine(seed=5)
        bootstrap = engine.bootstrap()
        minor_income = min(
            city["cash"] for city in bootstrap["strategic_map"]["cities"] if city["level"] == 2
        )
        base_cost = bootstrap["recruit_costs"]["infantry"]["cash"]

        self.assertGreaterEqual(base_cost, minor_income * 3)
        self.assertLessEqual(base_cost, minor_income * 4)

    def test_major_city_can_transfer_reserve_to_army(self):
        engine = GameEngine(seed=5)
        before = engine.state["players"]["N"]["unit_reserves"]["infantry"]

        result = engine.reinforce_army("N", "N-1", "guangzhou", "infantry")
        updated = result["state"]["players"]["N"]

        self.assertEqual(updated["unit_reserves"]["infantry"], before - 1)
        self.assertEqual(updated["army_reinforcements"]["N-1"]["infantry"], 1)

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
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("jp_condemnation"), 3)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("city_development"), 8)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("foreign_relation_jp"), 4)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("young_marshal_rises"), 1)
        self.assertEqual(engine.state["players"]["F"]["function_deck"].count("wang_yongjiang_financial_reform"), 1)
        self.assertEqual(engine.state["players"]["N"]["function_deck"].count("forced_march"), 4)
        self.assertIn("zhili_infantry_drill", engine.state["players"]["W"]["function_deck"])
        self.assertIn("zhili_infantry_drill", engine.state["players"]["S"]["function_deck"])

    def test_foreign_relation_unlocks_perk_cards(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["foreign_relations"]["su"] = 6
        player["hand"] = ["foreign_relation_su"]

        result = engine.use_function("N", "foreign_relation_su")

        self.assertEqual(result["foreign_relation_delta"]["before"], 6)
        self.assertEqual(result["foreign_relation_delta"]["after"], 8)
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

        with self.assertRaisesRegex(ValueError, "foreign relation"):
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

    def test_first_united_front_adds_reserves_with_loyalty_downside(self):
        engine = GameEngine(seed=4)
        player = engine.state["players"]["N"]
        player["hand"] = ["first_united_front"]
        before = player["unit_reserves"]["infantry"]

        result = engine.use_function("N", "first_united_front")

        self.assertEqual(result["state"]["players"]["N"]["unit_reserves"]["infantry"], before + 20)
        self.assertEqual(result["loyalty_delta_all"], {"owner": "N", "amount": -3})

    def test_zhili_anti_communist_declaration_returns_loyalty_swings(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["W"]["hand"] = ["zhili_anti_communist_declaration"]

        result = engine.use_function("W", "zhili_anti_communist_declaration")

        self.assertIn({"owner": "W", "amount": 3}, result["loyalty_swings"])
        self.assertIn({"owner": "S", "amount": 3}, result["loyalty_swings"])
        self.assertIn({"owner": "F", "amount": -1}, result["loyalty_swings"])
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

    def test_qing_gang_riot_halts_province_and_pays_until_suppressed(self):
        engine = GameEngine(seed=4)
        engine.state["players"]["N"]["hand"] = ["qing_gang_riot"]
        before_n_cash = engine.state["players"]["N"]["treasury"]
        before_w_income = engine.state["players"]["W"]["income"]
        before_w_factory = engine.state["players"]["W"]["factory_income"]

        result = engine.use_function("N", "qing_gang_riot", target_owner="W", target_province="湖北")
        effect = result["city_disruption"]

        self.assertEqual(effect["province"], "湖北")
        self.assertGreater(len(effect["city_ids"]), 0)
        self.assertLess(result["state"]["players"]["W"]["income"], before_w_income)
        self.assertLess(result["state"]["players"]["W"]["factory_income"], before_w_factory)

        turn = engine.next_turn(active_player="N")
        self.assertGreater(turn["state"]["players"]["N"]["treasury"], before_n_cash - 10)
        self.assertTrue(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))

        for _ in range(2):
            engine.next_turn(active_player="N", riot_garrisons={effect["id"]: True})
        self.assertTrue(any(item["id"] == effect["id"] for item in engine.state["city_output_effects"]))

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


if __name__ == "__main__":
    unittest.main()
