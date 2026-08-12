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


class FlatCommandTreeTest(unittest.TestCase):
    """川軍與湘軍沒有大帥，將領彼此平行、互不隸屬。"""

    def flat_tree(self):
        return {
            "flat_command": True,
            "great_general_id": None,
            "generals": {
                "liu_xiang": {
                    "id": "liu_xiang", "name": "劉湘", "role": "lieutenant_general",
                    "faction": "川軍", "loyalty": None, "loyalty_exempt": True,
                    "body_guard_level": None, "command_cap": 42,
                    "units": {"infantry": 9}, "parent_id": None,
                    "subordinate_slots": 0, "subordinates": [], "status": "active",
                },
                "yang_sen": {
                    "id": "yang_sen", "name": "楊森", "role": "lieutenant_general",
                    "faction": "川軍", "loyalty": 4, "loyalty_exempt": False,
                    "body_guard_level": None, "command_cap": 26,
                    "units": {"infantry": 7}, "parent_id": None,
                    "subordinate_slots": 0, "subordinates": [], "status": "active",
                },
            },
        }

    def test_a_flat_tree_needs_no_great_general(self):
        self.assertIs(validate_tree(self.flat_tree())["great_general_id"], None)

    def test_a_flat_tree_rejects_a_great_general(self):
        tree = self.flat_tree()
        tree["generals"]["liu_xiang"]["role"] = "great_general"
        with self.assertRaises(ValueError):
            validate_tree(tree)

    def test_a_flat_tree_rejects_parent_links(self):
        tree = self.flat_tree()
        tree["generals"]["yang_sen"]["parent_id"] = "liu_xiang"
        with self.assertRaises(ValueError):
            validate_tree(tree)

    def test_loyalty_report_works_without_a_great_general(self):
        report = loyalty_report(self.flat_tree())
        self.assertEqual(report["core_faction"], "川軍")
        self.assertIn("yang_sen", report["generals"])

    def test_a_normal_tree_still_requires_a_great_general(self):
        tree = load_template()
        tree["great_general_id"] = None
        with self.assertRaises(ValueError):
            validate_tree(tree)


class ShippedTreeDataTest(unittest.TestCase):
    """倉庫裡實際使用的將領樹檔案都要通過驗證。"""

    DATA_DIR = Path(__file__).parent / "data"

    NAMED_SKILLS = {
        "feng_yuxiang": "northwest_overlord", "han_fuqu": "dodging_drift",
        "song_zheyuan": "broadsword_corps", "lu_zhonglin": "northwest_vanguard",
        "yan_xishan": "shanxi_king", "fu_zuoyi": "iron_bulwark",
        "xu_yongchang": "chief_of_staff", "ma_qi": "xining_garrison",
        "ma_fuxiang": "desert_guard", "ma_hongbin": "valiant_horse",
        "zhang_zuolin": "marshal_zhang", "zhang_xueliang": "young_marshal",
        "zhang_zongchang": "white_russian_mercenaries", "yang_yuting": "elite_artillery",
        "sun_chuanfang": "five_provinces_alliance", "zhou_yinren": "riverine_warfare",
        "meng_zhaoyue": "assault_breaker", "lu_xiangting": "riverine_warfare",
        "wu_peifu": "wu_peifu_admired", "jin_yun_e": "defensive_specialist",
        "kou_yingjie": "central_plains_veteran", "chen_jiamo": "wuchang_veteran",
        "chiang_kai_shek": "advantage_is_ours", "he_yingqin": "whampoa_spirit",
        "bai_chongxi": "precision_barrage", "li_zongren": "cavalry_screen_commander",
        "tang_jiyao": "french_comprador", "long_yun": "mountain_division",
        "liu_xiang": "tianfu_land", "liu_wenhui": "elite_mountain_division",
        "yang_sen": "mountain_division", "tang_shengzhi": "buddhist_general",
        "zhao_hengti": "hunan_governor", "he_jian": "anticommunist_vanguard",
    }

    MOUNTAIN_DIVISION = (
        "li_zongren", "bai_chongxi", "tang_jiyao", "long_yun", "liu_xiang", "yang_sen",
    )

    ENGINEERING = {
        "han_fuqu": "pontoon_bridge", "zhang_xueliang": "pontoon_bridge",
        "zhou_yinren": "pontoon_bridge", "lu_xiangting": "pontoon_bridge",
        "kou_yingjie": "pontoon_bridge",
        "song_zheyuan": "fortress_builder", "fu_zuoyi": "fortress_builder",
        "zhang_zuolin": "fortress_builder", "yang_yuting": "fortress_builder",
        "meng_zhaoyue": "fortress_builder", "jin_yun_e": "fortress_builder",
        "he_yingqin": "pontoon_bridge",
        "chiang_kai_shek": "fortress_builder", "liu_wenhui": "fortress_builder",
        "yang_sen": "fortress_builder", "zhao_hengti": "fortress_builder",
    }

    def all_trees(self):
        for path in sorted(self.DATA_DIR.glob("general_tree_*.json")):
            with path.open(encoding="utf-8") as handle:
                yield path.name, json.load(handle)

    def all_generals(self):
        # general_tree_template.json 只是建樹用的骨架，裡面的人物與實際對局無關，
        # 合併時要跳過，否則會蓋掉 playtest（國民革命軍）與湘軍的真正設定。
        merged = {}
        for name, tree in self.all_trees():
            if name == "general_tree_template.json":
                continue
            merged.update(tree.get("generals", {}))
        return merged

    def test_every_shipped_tree_validates(self):
        for name, tree in self.all_trees():
            with self.subTest(tree=name):
                validate_tree(tree)
                loyalty_report(tree)

    def test_named_skills_are_assigned(self):
        generals = self.all_generals()
        for general_id, skill in self.NAMED_SKILLS.items():
            with self.subTest(general=general_id):
                self.assertIn(skill, generals[general_id]["traits"])

    def test_zhang_zongchang_also_carries_the_comprador_trait(self):
        self.assertIn("japanese_comprador", self.all_generals()["zhang_zongchang"]["traits"])

    def test_the_southern_generals_all_carry_the_mountain_division_skill(self):
        generals = self.all_generals()
        for general_id in self.MOUNTAIN_DIVISION:
            with self.subTest(general=general_id):
                self.assertIn("mountain_division", generals[general_id]["traits"])

    def test_engineering_skills_are_assigned(self):
        generals = self.all_generals()
        for general_id, skill in self.ENGINEERING.items():
            with self.subTest(general=general_id):
                self.assertIn(skill, generals[general_id]["skills"])

    def test_sichuan_and_hunan_have_no_marshal(self):
        for name in ("general_tree_npc_C.json", "general_tree_npc_H.json"):
            with (self.DATA_DIR / name).open(encoding="utf-8") as handle:
                tree = json.load(handle)
            with self.subTest(tree=name):
                self.assertTrue(tree["flat_command"])
                self.assertIsNone(tree["great_general_id"])
                for general in tree["generals"].values():
                    self.assertIsNone(general["parent_id"])
                    self.assertEqual(general["subordinates"], [])

    def test_every_sichuan_and_hunan_general_can_be_turned(self):
        # 沒有大帥，就沒有人享有大帥的忠誠豁免；全員都策反得動。
        for name in ("general_tree_npc_C.json", "general_tree_npc_H.json"):
            with (self.DATA_DIR / name).open(encoding="utf-8") as handle:
                tree = json.load(handle)
            for general_id, general in tree["generals"].items():
                with self.subTest(general=general_id):
                    self.assertFalse(general["loyalty_exempt"])
                    self.assertFalse(general.get("absolute_loyalty", False))
                    self.assertIsNotNone(general["loyalty"])

    def test_liu_xiang_and_tang_shengzhi_start_at_loyalty_five(self):
        generals = self.all_generals()
        self.assertEqual(generals["liu_xiang"]["loyalty"], 5)
        self.assertEqual(generals["tang_shengzhi"]["loyalty"], 5)

    def test_the_other_npc_factions_keep_everyone_under_the_leader(self):
        leaders = {
            "general_tree_npc_G.json": "feng_yuxiang",
            "general_tree_npc_Y.json": "yan_xishan",
            "general_tree_npc_M.json": "ma_qi",
            "general_tree_npc_D.json": "tang_jiyao",
        }
        for name, leader in leaders.items():
            with (self.DATA_DIR / name).open(encoding="utf-8") as handle:
                tree = json.load(handle)
            with self.subTest(tree=name):
                self.assertEqual(tree["great_general_id"], leader)
                for general_id, general in tree["generals"].items():
                    if general_id == leader:
                        continue
                    self.assertEqual(general["parent_id"], leader)


if __name__ == "__main__":
    unittest.main()
