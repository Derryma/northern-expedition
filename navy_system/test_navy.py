import unittest

from navy_system import repair_cost, validate_initial_divisions
from navy_system.navy import load_rules


class NavyRuleTests(unittest.TestCase):
    def test_rules_load_with_four_playable_navies(self):
        rules = load_rules()
        validate_initial_divisions(rules)
        self.assertEqual(
            {division["faction"] for division in rules["initial_divisions"]},
            {"F", "W", "S", "N"},
        )
        for division in rules["initial_divisions"]:
            self.assertEqual(division["gun_boats"], 2)
            self.assertEqual(division["cargo_boats"], 1)

    def test_repair_cost_is_two_factory_per_hp(self):
        self.assertEqual(repair_cost(0), 0)
        self.assertEqual(repair_cost(7), 14)
        self.assertEqual(repair_cost(-5), 0)


if __name__ == "__main__":
    unittest.main()
