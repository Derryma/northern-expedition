import json
import unittest
from pathlib import Path

from general_tree import (
    add_loyalty,
    add_skill,
    add_trait,
    allocate_troops,
    calculate_force_strength,
    defect_general,
    increase_affiliation_slots,
    kill_general,
    loyalty_report,
    record_battle_loss,
    recruit_general,
    set_body_guard_level,
    transfer_troops_between_absolute_loyal_pair,
    validate_tree,
)


TEMPLATE = Path(__file__).parent / "data" / "general_tree_template.json"


def load_template():
    with TEMPLATE.open(encoding="utf-8") as handle:
        return json.load(handle)


class GeneralTreeTests(unittest.TestCase):
    def test_template_is_valid(self):
        tree = load_template()

        self.assertIs(validate_tree(tree), tree)

    def test_force_strength_uses_shared_points(self):
        self.assertEqual(
            calculate_force_strength({"infantry": 5, "cavalry": 3, "machine_gun": 2, "artillery": 1}),
            16.0,
        )

    def test_recruit_requires_force_and_empty_slot(self):
        tree = load_template()
        increase_affiliation_slots(tree, "he_yingqin")
        recruit_general(
            tree,
            parent_id="he_yingqin",
            general={
                "id": "new_major",
                "name": "New Major",
                "faction": "中央軍",
                "loyalty": 5,
                "command_cap": 12,
            },
            starting_units={"infantry": 5},
        )

        self.assertIn("new_major", tree["generals"]["he_yingqin"]["subordinates"])
        self.assertEqual(tree["generals"]["new_major"]["role"], "major_general")

    def test_affiliation_slots_cap_at_three_for_lieutenants_only(self):
        tree = load_template()
        increase_affiliation_slots(tree, "he_yingqin", amount=5)
        self.assertEqual(tree["generals"]["he_yingqin"]["subordinate_slots"], 3)
        with self.assertRaises(ValueError):
            increase_affiliation_slots(tree, "chiang_kai_shek")

    def test_battle_loss_removes_units_and_reduces_loyalty(self):
        tree = load_template()
        record_battle_loss(tree, "bai_chongxi", {"infantry": 3, "machine_gun": 1})

        self.assertEqual(tree["generals"]["bai_chongxi"]["units"]["infantry"], 9.0)
        self.assertEqual(tree["generals"]["bai_chongxi"]["units"]["machine_gun"], 2.0)
        self.assertEqual(tree["generals"]["bai_chongxi"]["loyalty"], 5.5)

    def test_killing_lieutenant_sets_major_loyalty_zero(self):
        tree = load_template()
        kill_general(tree, "bai_chongxi")

        self.assertEqual(tree["generals"]["li_zongren"]["loyalty"], 0)

    def test_defection_moves_whole_branch_and_resets_loyalty(self):
        tree = load_template()
        defect_general(tree, "bai_chongxi", "桂系獨立")

        self.assertEqual(tree["generals"]["bai_chongxi"]["faction"], "桂系獨立")
        self.assertEqual(tree["generals"]["li_zongren"]["faction"], "桂系獨立")
        self.assertEqual(tree["generals"]["li_zongren"]["loyalty"], 1)

    def test_allocation_only_adds_and_checks_cap(self):
        tree = load_template()
        allocate_troops(tree, "li_zongren", {"infantry": 2})

        self.assertEqual(tree["generals"]["li_zongren"]["units"]["infantry"], 11.0)
        with self.assertRaises(ValueError):
            allocate_troops(tree, "li_zongren", {"artillery": 99})

    def test_promotion_helpers_append_unique_entries(self):
        tree = load_template()
        add_trait(tree, "li_zongren", "steady_drillmaster")
        add_trait(tree, "li_zongren", "steady_drillmaster")
        add_skill(tree, "li_zongren", "pontoon_bridge")

        self.assertEqual(tree["generals"]["li_zongren"]["traits"].count("steady_drillmaster"), 1)
        self.assertIn("pontoon_bridge", tree["generals"]["li_zongren"]["skills"])

    def test_loyalty_report_tracks_non_core_relative_strength(self):
        tree = load_template()
        report = loyalty_report(tree)

        self.assertIsNone(report["generals"]["chiang_kai_shek"]["relative_strength"])
        self.assertGreater(report["generals"]["bai_chongxi"]["relative_strength"], 0)

    def test_add_loyalty_clamps(self):
        tree = load_template()
        add_loyalty(tree, "bai_chongxi", 10)
        self.assertEqual(tree["generals"]["bai_chongxi"]["loyalty"], 10.0)

        add_loyalty(tree, "bai_chongxi", -99)
        self.assertEqual(tree["generals"]["bai_chongxi"]["loyalty"], 0.0)

    def test_absolute_loyalty_is_fixed_at_ten(self):
        tree = load_template()
        add_loyalty(tree, "he_yingqin", -99)
        record_battle_loss(tree, "he_yingqin", {"infantry": 5})

        self.assertEqual(tree["generals"]["he_yingqin"]["loyalty"], 10)

    def test_absolute_loyal_pair_can_transfer_troops(self):
        tree = load_template()
        transfer_troops_between_absolute_loyal_pair(
            tree,
            from_general_id="chiang_kai_shek",
            to_general_id="he_yingqin",
            units={"infantry": 2},
        )

        self.assertEqual(tree["generals"]["chiang_kai_shek"]["units"]["infantry"], 16.0)
        self.assertEqual(tree["generals"]["he_yingqin"]["units"]["infantry"], 16.0)

    def test_body_guard_level_is_general_state(self):
        tree = load_template()
        set_body_guard_level(tree, "bai_chongxi", "high")

        self.assertEqual(tree["generals"]["bai_chongxi"]["body_guard_level"], "high")
        with self.assertRaises(ValueError):
            set_body_guard_level(tree, "bai_chongxi", "machine_gun_guard")


if __name__ == "__main__":
    unittest.main()
