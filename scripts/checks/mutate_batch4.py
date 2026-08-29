# -*- coding: utf-8 -*-
"""批次四（陣營級結構變動）的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

MUTANTS = [
    ("D-1 無限期封路照樣倒數到期",
     '            if effect.get("permanent"):',
     '            if False:'),

    ("D-2 閻錫山被俘也不解除封路",
     '                if gate and not self._npc_general_still_here(\n                        gate.get("general"), gate.get("faction")):',
     '                if False:'),

    ("D-3 沒快照時把封路誤解除",
     '        if not isinstance(self._tactical, dict):\n            return True\n        situation = self.npc_situation(self._tactical)',
     '        situation = self.npc_situation(self._tactical or {})'),

    ("D-4 封路照樣收搶修費",
     '                         "no_repair": True, "repair_charges": {},',
     '                         "no_repair": False, "repair_charges": {"F": 30},'),

    ("D-5 換陣營但部隊不跟著走",
     '                army["faction"] = to_faction\n                moved.append(',
     '                moved.append('),

    ("D-6 移防指令不交辦給前端",
     '                entry["relocate"] = {"near_city": city_id,\n                                     "within": int(relocate.get("within", 1))}',
     '                pass'),

    ("D-7 歸附給固定的第一家而不是戰力最高",
     '            winner = self._top_force_player()',
     '            winner = sorted(self.state["players"])[0]'),

    ("D-8 並列最高不隨機，固定取第一個",
     '        return tied[self.random.randrange(len(tied))]',
     '        return tied[0]'),

    ("D-9 歸附後地盤不轉屬",
     '                cities = self._npc_faction_cities(faction)\n                for city_id in cities:\n                    self.state["city_owners"][city_id] = winner',
     '                cities = self._npc_faction_cities(faction)'),

    ("D-10 歸附後陣營不退場",
     '                self._retire_npc_faction(faction)\n                self._refresh_city_income()',
     '                self._refresh_city_income()'),

    ("D-11 退場的陣營照樣算還在場上",
     '            if faction in retired:\n                out["factions"][faction] = {"generals": [], "battalions": 0}\n                continue',
     '            if False:\n                continue'),

    ("D-12 併吞不看戰力上限",
     '                            if self._force_of(units) + UNIT_FORCE_POINTS[unit] > ARMY_FORCE_CAP:\n                                overflow[unit] = overflow.get(unit, 0) + 1\n                                continue',
     '                            pass'),

    ("D-13 被併的部隊不清空",
     '                    army["units"] = {unit: 0 for unit in UNIT_FORCE_POINTS}\n                    army["status"] = "merged"',
     '                    army["status"] = "merged"'),

    ("D-14 併吞後黔軍地盤不轉屬",
     '                cities = self._npc_faction_cities(source)\n                for city_id in cities:\n                    self.state["city_owners"][city_id] = winner_faction',
     '                cities = self._npc_faction_cities(source)'),

    ("D-15 找不到吞併者的部隊就安靜略過",
     '                applied.append({"kind": "npc_faction_merge_skipped",\n                                "reason": "no_target_army", "into_general": name})',
     '                pass'),

    ("D-16 player_rank 條件不判",
     '            ranking = self.player_force_ranking()\n            if not ranking or ranking[0][1] <= 0:\n                return []',
     '            pass'),
]

sys.exit(main(MUTANTS))
