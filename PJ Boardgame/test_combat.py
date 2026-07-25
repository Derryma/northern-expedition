import unittest

from combat import simulate_battle


class CombatSimulationTests(unittest.TestCase):
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

        self.assertEqual(probing_damage, normal_damage * 0.5)
        self.assertEqual(damage_taken_by_probe, normal_damage * 0.6)

    def test_reinforcements_join_before_round_attacks(self):
        result = simulate_battle(
            {
                "units": {"infantry": 10},
                "modifiers": [{"stat": "harm_taken", "multiplier": 0.01}],
            },
            {
                "units": {"infantry": 10},
                "modifiers": [{"stat": "harm_taken", "multiplier": 0.01}],
            },
            max_rounds=2,
            reinforcements=[
                {"round": 2, "side": "A", "army": {"units": {"machine_gun": 1}}},
            ],
        )

        self.assertEqual(result["log"][1]["reinforcements"][0]["side"], "A")
        self.assertIn("machine_gun", result["remaining"]["A"]["units"])

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
        self.assertEqual(artillery_attack["damage"], 6.0)

    def test_winning_cavalry_pursues_fleeing_loser(self):
        result = simulate_battle(
            {"units": {"infantry": 8, "cavalry": 3, "artillery": 3}},
            {"units": {"infantry": 7, "machine_gun": 2}},
            max_rounds=5,
        )

        pursuit = result["log"][-1]
        self.assertEqual(pursuit["phase"], "pursuit")
        self.assertEqual(pursuit["cavalry"], 3)
        self.assertEqual(pursuit["casualty_multiplier"], 0.85)


if __name__ == "__main__":
    unittest.main()
