# -*- coding: utf-8 -*-
"""美孚石油免疫與暴動不可重疊的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("O-1 免疫又變回沒人讀的旗標",
     '            if entry.get("card_id") in immune and (\n                    float(entry.get("cash", 1)) > 1 or float(entry.get("factory", 1)) > 1):\n                continue',
     '            if False:\n                continue'),

    ("O-2 免疫連降價也一起擋掉",
     '            if entry.get("card_id") in immune and (\n                    float(entry.get("cash", 1)) > 1 or float(entry.get("factory", 1)) > 1):',
     '            if entry.get("card_id") in immune:'),

    ("O-3 免疫變成全場適用，不只持有者",
     '        if player not in self.state["players"]:\n            return set()\n        out: set = set()\n        for effect in self._player(player).get("timed_effects", []):',
     '        out: set = set()\n        for effect in [e for p in self.state["players"] for e in self._player(p).get("timed_effects", [])]:'),

    ("O-4 免疫到期了還算數",
     '            remaining = effect.get("remaining_turns")\n            if remaining is not None and int(remaining) <= 0:\n                continue\n            out |= {str(x) for x in (effect.get("immune_cards") or [])}',
     '            out |= {str(x) for x in (effect.get("immune_cards") or [])}'),

    ("O-5 生產乘數不記來源卡（免疫就對不上了）",
     '                "card_id": str(card.get("id") or ""),',
     '                "card_id": "",'),

    ("R-1 同一省可以重複發動暴動",
     '            if any(effect.get("kind") == mechanic\n                   and effect.get("target_owner") == target_owner\n                   and effect.get("province") == province\n                   for effect in self.state.get("city_output_effects", [])):\n                raise ValueError(f"{province}已經在暴動中，不能重複發動")',
     '            pass'),

    ("R-2 擋過頭：連別的省也不准發動",
     '                   and effect.get("province") == province\n                   for effect in self.state.get("city_output_effects", [])):',
     '                   for effect in self.state.get("city_output_effects", [])):'),
]))
