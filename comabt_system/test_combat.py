import unittest

from combat import TACTICS, calculate_force_strength, simulate_battle


class CombatSimulationTests(unittest.TestCase):
    def test_force_strength_uses_force_points_not_attack(self):
        strength = calculate_force_strength(
            {"infantry": 5, "cavalry": 3, "machine_gun": 2, "artillery": 1}
        )

        self.assertEqual(strength, 16.0)

    def test_artillery_rolls_to_next_priority_after_artillery_flees(self):
        result = simulate_battle(
            {
                "name": "A",
                "units": {"infantry": 100, "artillery": 1},
                "modifiers": [{"stat": "harm_taken", "multiplier": 0.01}],
            },
            {
                "name": "B",
                "units": {"infantry": 100, "artillery": 1},
                "modifiers": [
                    {"stat": "harm_taken", "unit": "infantry", "multiplier": 0.01},
                    {"stat": "harm_taken", "unit": "machine_gun", "multiplier": 0.01},
                ],
            },
            max_rounds=2,
        )

        first_round_targets = [
            attack["target_section"]
            for attack in result["log"][0]["attacks"]
            if attack["attacker"] == "A" and attack["source_unit"] == "artillery"
        ]
        second_round_targets = [
            attack["target_section"]
            for attack in result["log"][1]["attacks"]
            if attack["attacker"] == "A" and attack["source_unit"] == "artillery"
        ]

        self.assertEqual(first_round_targets, ["artillery"])
        self.assertEqual(second_round_targets, ["line"])

    def test_probing_attack_reduces_attack_and_harm_taken(self):
        normal = simulate_battle(
            {"units": {"infantry": 10}, "tactic": "normal_advance"},
            {"units": {"infantry": 10}, "tactic": "normal_advance"},
            max_rounds=1,
        )
        probing = simulate_battle(
            {"units": {"infantry": 10}, "tactic": "probing_attack"},
            {"units": {"infantry": 10}, "tactic": "normal_advance"},
            max_rounds=1,
        )

        normal_damage = normal["log"][0]["attacks"][0]["damage"]
        probing_damage = probing["log"][0]["attacks"][0]["damage"]
        damage_taken_by_probe = probing["log"][0]["attacks"][1]["damage"]

        self.assertEqual(probing_damage, normal_damage * 0.35)
        self.assertEqual(damage_taken_by_probe, normal_damage * 0.45)

    def test_reinforcements_join_as_separate_allied_armies(self):
        result = simulate_battle(
            {
                "name": "Main A",
                "units": {"infantry": 10},
                "modifiers": [{"stat": "harm_taken", "multiplier": 0.01}],
            },
            {
                "name": "Main B",
                "units": {"infantry": 100},
            },
            max_rounds=2,
            reinforcements=[
                {
                    "round": 2,
                    "side": "A",
                    "army": {
                        "name": "Allied MG Corps",
                        "units": {"machine_gun": 1},
                        "tactic": "all_out_offense",
                        "modifiers": [{"stat": "attack", "unit": "machine_gun", "multiplier": 2.0}],
                    },
                },
            ],
        )

        self.assertEqual(result["log"][1]["reinforcements"][0]["side"], "A")
        army_names = [army["name"] for army in result["remaining"]["A"]["armies"]]
        self.assertIn("Main A", army_names)
        self.assertIn("Allied MG Corps", army_names)

        allied_attacks = [
            attack
            for attack in result["log"][1]["attacks"]
            if attack["attacker_army"] == "Allied MG Corps"
        ]
        self.assertEqual(allied_attacks[0]["damage"], 6.8)

    def test_default_fire_spreads_evenly_across_enemy_armies(self):
        result = simulate_battle(
            {"name": "A Artillery", "units": {"artillery": 1}},
            {"name": "B Front", "units": {"infantry": 20}},
            max_rounds=1,
            reinforcements=[
                {"round": 1, "side": "B", "army": {"name": "B Reserve", "units": {"infantry": 20}}},
            ],
        )

        b_armies = {army["name"]: army for army in result["remaining"]["B"]["armies"]}
        self.assertAlmostEqual(b_armies["B Front"]["raw_hp"]["infantry"], 80.0)
        self.assertAlmostEqual(b_armies["B Reserve"]["raw_hp"]["infantry"], 80.0)
        artillery_attack = [
            attack
            for attack in result["log"][0]["attacks"]
            if attack["attacker_army"] == "A Artillery" and attack["source_unit"] == "artillery"
        ][0]
        self.assertEqual(artillery_attack["target_armies"], ["B Front", "B Reserve"])

    def test_focus_fire_concentrates_on_named_enemy_army(self):
        result = simulate_battle(
            {"name": "A First Army", "units": {"artillery": 1}, "focus": "B Front"},
            {"name": "B Front", "units": {"infantry": 20}},
            max_rounds=1,
            reinforcements=[
                {
                    "round": 1,
                    "side": "A",
                    "army": {"name": "A Second Army", "units": {"artillery": 1}, "focus": "B Front"},
                },
                {"round": 1, "side": "B", "army": {"name": "B Reserve", "units": {"infantry": 20}}},
            ],
        )

        b_armies = {army["name"]: army for army in result["remaining"]["B"]["armies"]}
        self.assertAlmostEqual(b_armies["B Front"]["raw_hp"]["infantry"], 72.0)
        self.assertEqual(b_armies["B Reserve"]["raw_hp"]["infantry"], 80.0)

        focused_attacks = [
            attack
            for attack in result["log"][0]["attacks"]
            if attack["attacker"] == "A" and attack["source_unit"] == "artillery"
        ]
        self.assertEqual([attack["target_armies"] for attack in focused_attacks], [["B Front"], ["B Front"]])

    def test_target_specific_modifier_works_inside_line_pool(self):
        result = simulate_battle(
            {
                "units": {"artillery": 1},
                "modifiers": [
                    {"stat": "attack", "unit": "artillery", "target": "machine_gun", "multiplier": 2.0}
                ],
            },
            {"units": {"infantry": 1, "machine_gun": 1}},
            max_rounds=1,
        )

        artillery_attack = result["log"][0]["attacks"][0]
        self.assertEqual(artillery_attack["target_section"], "line")
        self.assertEqual(artillery_attack["damage"], 4.5)
        damage_by_unit = {
            target["unit"]: target["damage"]
            for target in artillery_attack["damage_by_target"]
        }
        self.assertEqual(damage_by_unit["infantry"], 1.5)
        self.assertEqual(damage_by_unit["machine_gun"], 3.0)

    def test_attack_matrix_makes_machine_guns_better_than_artillery_against_cavalry(self):
        mg_result = simulate_battle(
            {"name": "MG", "units": {"machine_gun": 1}},
            {"name": "Cav", "units": {"cavalry": 10}},
            max_rounds=1,
        )
        art_result = simulate_battle(
            {"name": "Art", "units": {"artillery": 1}},
            {"name": "Cav", "units": {"cavalry": 10}},
            max_rounds=1,
        )

        mg_damage = mg_result["log"][0]["attacks"][0]["damage"]
        art_damage = art_result["log"][0]["attacks"][0]["damage"]

        self.assertGreater(mg_damage, art_damage)
        self.assertEqual(mg_damage, 3.0)
        self.assertEqual(art_damage, 1.0)

    def test_cavalry_contact_forces_artillery_to_fire_at_cavalry(self):
        result = simulate_battle(
            {"name": "A Screen", "units": {"cavalry": 1, "artillery": 1}},
            {"name": "B Guns", "units": {"artillery": 1}},
            max_rounds=1,
        )

        contacts = result["log"][0]["artillery_contacts"]
        self.assertEqual(contacts["B"]["B Guns"], ("A Screen",))

        a_artillery_attack = [
            attack
            for attack in result["log"][0]["attacks"]
            if attack["attacker"] == "A" and attack["source_unit"] == "artillery"
        ][0]
        b_artillery_attack = [
            attack
            for attack in result["log"][0]["attacks"]
            if attack["attacker"] == "B" and attack["source_unit"] == "artillery"
        ][0]

        self.assertEqual(a_artillery_attack["target_section"], "artillery")
        self.assertFalse(a_artillery_attack["forced_contact"])
        self.assertEqual(b_artillery_attack["target_section"], "cavalry")
        self.assertTrue(b_artillery_attack["forced_contact"])
        self.assertEqual(b_artillery_attack["target_armies"], ["A Screen"])
        self.assertEqual(result["remaining"]["A"]["raw_hp"]["artillery"], 2.0)
        self.assertEqual(result["remaining"]["A"]["raw_hp"]["cavalry"], 3.0)

    def test_last_stand_holds_longer_than_layered_delaying(self):
        layered = TACTICS["layered_delaying"]["threshold"] / TACTICS["layered_delaying"]["harm_taken_multiplier"]
        last_stand = TACTICS["last_stand"]["threshold"] / TACTICS["last_stand"]["harm_taken_multiplier"]

        self.assertGreater(last_stand, layered)

    def test_winning_cavalry_pursues_fleeing_loser(self):
        result = simulate_battle(
            {"units": {"infantry": 8, "cavalry": 3, "artillery": 3}},
            {"units": {"infantry": 7, "machine_gun": 2}},
            max_rounds=5,
        )

        pursuit = result["log"][-1]
        self.assertEqual(pursuit["phase"], "pursuit")
        self.assertEqual(pursuit["cavalry"], 3)
        self.assertTrue(pursuit["eligible"])
        damage = {target["unit"]: target["applied_damage"] for target in pursuit["damage_by_target"]}
        self.assertEqual(damage["infantry"], 6.0)
        self.assertAlmostEqual(damage["machine_gun"], 1.5)
        self.assertEqual(pursuit["after"]["units"]["infantry"], 3)
        self.assertEqual(pursuit["after"]["units"]["machine_gun"], 0)

    def test_loser_cavalry_cover_takes_pursuit_then_spills_damage(self):
        result = simulate_battle(
            {"units": {"infantry": 8, "cavalry": 3, "artillery": 3}},
            {"units": {"infantry": 7, "cavalry": 1, "machine_gun": 2}},
            max_rounds=5,
        )

        pursuit = result["log"][-1]
        self.assertEqual(pursuit["phase"], "pursuit")
        self.assertTrue(pursuit["eligible"])
        self.assertTrue(pursuit["covering_cavalry"])
        damage = {(target["unit"], target["source"]): target["applied_damage"] for target in pursuit["damage_by_target"]}
        self.assertEqual(damage[("cavalry", "cavalry_cover")], 1.5)
        self.assertGreater(damage[("infantry", "cavalry_cover_spillover")], 0)
        self.assertEqual(pursuit["after"]["units"]["cavalry"], 0)

    def test_initial_units_preserve_retreat_baseline_between_api_rounds(self):
        first = simulate_battle(
            {"name": "A", "units": {"infantry": 20}, "tactic": "normal_advance"},
            {"name": "B", "units": {"infantry": 20}, "tactic": "last_stand"},
            max_rounds=1,
        )
        remaining_a = first["remaining"]["A"]["units"]
        remaining_b = first["remaining"]["B"]["units"]
        second = simulate_battle(
            {
                "name": "A",
                "units": remaining_a,
                "initial_units": {"infantry": 20},
                "tactic": "normal_advance",
            },
            {
                "name": "B",
                "units": remaining_b,
                "initial_units": {"infantry": 20},
                "tactic": "last_stand",
            },
            max_rounds=1,
        )

        self.assertEqual(second["winner"], "B")
        self.assertGreater(second["remaining"]["A"]["units"]["infantry"], 0)

    def test_retreat_threshold_prevents_annihilation_before_pursuit(self):
        result = simulate_battle(
            {"units": {"artillery": 20}, "modifiers": [{"stat": "harm_taken", "multiplier": 0.01}]},
            {"units": {"infantry": 10}, "tactic": "last_stand"},
            max_rounds=1,
        )

        self.assertEqual(result["winner"], "A")
        self.assertGreater(result["log"][0]["remaining"]["B"]["units"]["infantry"], 0)
        pursuit = next(entry for entry in result["log"] if entry.get("phase") == "pursuit")
        self.assertEqual(pursuit["cavalry"], 0)
        self.assertEqual(pursuit["before"]["units"], pursuit["after"]["units"])


if __name__ == "__main__":
    unittest.main()
