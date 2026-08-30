# -*- coding: utf-8 -*-
"""忠誠加減、出牌摘要、地格標籤、情報網／情報局這一輪的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("L1 忠誠加減又加在顯示值上",
     '            current = overrides.get(general_id, base_of[general_id])',
     '            current = (self.loyalty_report(snapshot).get(general_id) or {}).get("value", 1)'),

    ("L2 忠誠加減不夾 1–10",
     '            value = int(max(self.LOYALTY_OVERRIDE_MIN,\n'
     '                            min(self.LOYALTY_OVERRIDE_MAX, float(current) + float(amount))))',
     '            value = int(float(current) + float(amount))'),

    ("L3 絕對忠誠／豁免的將領也被改",
     '                if absolute:\n                    continue',
     '                if False:\n                    continue'),

    ("L4 use_function 不再回傳新的 overrides",
     '            "loyalty_overrides": loyalty_overrides,\n            "state": self.snapshot(),',
     '            "loyalty_overrides": {},\n            "state": self.snapshot(),'),

    ("L5 事件卡的抽籤不照 count",
     '            picked = [pool[i] for i in self.random.sample(range(len(pool)), want)] if want else []',
     '            picked = list(pool)'),

    ("T1 地格標籤的駐軍進度永遠是 0",
     '                        "progress": int(progress or 0),',
     '                        "progress": 0,'),

    ("T2 逐城計數的紅軍起義取錯進度",
     '                    if isinstance(progress, dict):\n'
     '                        progress = progress.get(city_id, 0)',
     '                    if isinstance(progress, dict):\n'
     '                        progress = 0'),

    ("T3 共黨暴動又變回沒有 kind",
     '                "kind": "communist_riot",',
     '                "kind": "city_halt",'),

    ("I1 情報局擋不住情報網",
     '            "counter_intel_factions": sorted({\n'
     '                code for code in self.state["players"]\n'
     '                if self.has_timed_flag(code, "counter_intel")\n'
     '            }),',
     '            "counter_intel_factions": [],'),

    ("I2 飛艇也被情報局擋住",
     '  if (intel.aerial_provinces.includes(province)) return true;',
     '  if (false) return true;',
     'frontend/app.js'),

    ("S1 摘要又漏掉崩鐵玩家",
     '  if (action.railway_effect) {',
     '  if (false) {',
     'frontend/app.js'),
]))
