# -*- coding: utf-8 -*-
"""第二輪空轉機制稽核的突變測試。

每一個突變體都是把這一輪修好的那條線再拆回去。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("S1 海軍修理不再判港口",
     '        self._navy_repair_port(city_id)\n',
     ''),

    ("S2 港口門檻不看等級",
     '        if level < floor:',
     '        if False:'),

    ("S3 港務癱瘓照樣能修",
     '        if any(effect.get("city_id") == str(city_id)\n'
     '               for effect in self.state.get("port_effects", [])\n'
     '               if int(effect.get("remaining_turns", 0)) > 0):',
     '        if False:'),

    ("S4 harbor_only 開關被忽略（永遠擋）",
     '        if not rules.get("harbor_only"):\n            return {}',
     '        if False:\n            return {}'),

    ("S5 戰力點又寫死一份",
     'UNIT_FORCE_POINTS = {\n'
     '    unit: int(stats["force_points"])\n'
     '    for unit, stats in load_game_data()["unit_stats"]["units"].items()\n'
     '}',
     'UNIT_FORCE_POINTS = {"infantry": 1, "cavalry": 1, "machine_gun": 2, "artillery": 4}'),

    ("S6 攻擊矩陣又寫死一份",
     'ATTACK_MATRIX = {\n'
     '    source: {target: float(value) for target, value in row.items()}\n'
     '    for source, row in _UNIT_STATS["attack_matrix"].items()\n'
     '}',
     'ATTACK_MATRIX = {\n'
     '    "infantry": {"infantry": 1.0, "cavalry": 1.0, "artillery": 1.0, "machine_gun": 1.0},\n'
     '    "cavalry": {"infantry": 2.0, "cavalry": 2.0, "artillery": 3.0, "machine_gun": 1.0},\n'
     '    "artillery": {"infantry": 3.0, "cavalry": 1.0, "artillery": 2.0, "machine_gun": 3.0},\n'
     '    "machine_gun": {"infantry": 2.0, "cavalry": 3.0, "artillery": 1.0, "machine_gun": 1.0},\n'
     '}',
     'comabt_system/combat.py'),

    ("S7 每營 HP 又寫死一份",
     'BASE_STATS = {\n'
     '    unit: {"hp": float(stats["hp"]), "force_points": float(stats["force_points"])}\n'
     '    for unit, stats in _UNIT_STATS["units"].items()\n'
     '}',
     'BASE_STATS = {\n'
     '    "infantry": {"hp": 3.0, "force_points": 1.0},\n'
     '    "cavalry": {"hp": 3.0, "force_points": 1.0},\n'
     '    "artillery": {"hp": 2.0, "force_points": 4.0},\n'
     '    "machine_gun": {"hp": 3.0, "force_points": 2.0},\n'
     '}',
     'comabt_system/combat.py'),

    ("S8 陸上撤退旗標又被忽略",
     '        "landRetreat": (artillery_after <= 0\n'
     '                        if bool(_rule(rules, ("land_interaction",\n'
     '                                              "land_retreat_when_no_artillery"), True))\n'
     '                        else False),',
     '        "landRetreat": artillery_after <= 0,',
     'navy_system/navy.py'),

    ("S9 親衛隊折減又寫死",
     '        reduction = float(guard["reduction"]) if guard else 0.0',
     '        reduction = 0.05 if guard else 0.0'),

    ("R1 紅槍會又用自己的標籤",
     '"disruption_label": "黑幫暴動"\n    },\n    {\n      "id": "red_spear_uprising"',
     '"disruption_label": "紅槍會暴動"\n    },\n    {\n      "id": "red_spear_uprising"',
     'cards/data/function_cards.json'),
]))
