# -*- coding: utf-8 -*-
"""批次二 A（NPC 按比例增減戰力）的突變測試。"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

MUTANTS = [
    # 四捨五入改回無條件捨去：小部隊會被砍過頭。
    ("S-1 改回無條件捨去",
     '                         int(math.floor(current * factors[army_id] + 0.5)))',
     '                         int(math.floor(current * factors[army_id])))'),

    # 改成銀行家捨入：.5 依前一位進退，同樣的半點給出不同答案。
    ("S-2 改成銀行家捨入",
     '                         int(math.floor(current * factors[army_id] + 0.5)))',
     '                         int(round(current * factors[army_id])))'),

    # 多條規則相加而不是相乘。
    ("S-3 多條規則相加而非相乘",
     '                factors[army_id] *= multiplier',
     '                factors[army_id] -= (1.0 - multiplier)'),

    # 裁兵改回會裁過頭的版本。
    ("S-4 裁兵裁過頭",
     '                after = self._cut_down_to_force(before, target)',
     '                after = self._trim_to_force(before, target)'),

    # 裁兵改成先裁便宜的。
    ("S-5 先裁便宜的兵種",
     '        order = sorted(UNIT_FORCE_POINTS, key=lambda unit: -UNIT_FORCE_POINTS[unit])\n        target = max(0, int(target))',
     '        order = sorted(UNIT_FORCE_POINTS, key=lambda unit: UNIT_FORCE_POINTS[unit])\n        target = max(0, int(target))'),

    # 增益不看戰力上限。
    ("S-6 增益不看戰力上限",
     '                target = min(ARMY_FORCE_CAP,\n                             int(math.floor(current * factors[army_id] + 0.5)))',
     '                target = int(math.floor(current * factors[army_id] + 0.5))'),

    # 沒變動也報一筆。
    ("S-7 沒變動也報一筆",
     '            changed = {unit: after[unit] - before[unit]\n                       for unit in UNIT_FORCE_POINTS if after[unit] != before[unit]}\n            if not changed:\n                continue',
     '            changed = {unit: after[unit] - before[unit]\n                       for unit in UNIT_FORCE_POINTS if after[unit] != before[unit]}\n            if False:\n                continue'),

    # 負倍率不拋錯。
    ("S-8 負倍率不拋錯",
     '                raise ValueError(f"{card.get(\'id\')} 的 npc_force_scale 倍率不能是負的：{multiplier}")',
     '                multiplier = 0.0'),

    # 少了 multiplier 不拋錯，靜默當成 1.0。
    ("S-9 少了 multiplier 靜默當 1.0",
     '            if "multiplier" not in spec:\n                raise ValueError(f"{card.get(\'id\')} 的 npc_force_scale 少了 multiplier：{spec}")\n            multiplier = float(spec["multiplier"])',
     '            multiplier = float(spec.get("multiplier", 1.0))'),

    # 增益改成補砲兵而不是步兵（會補得不精準，而且超上限）。
    ("S-10 增益改補砲兵",
     '                while self._force_of(after) + UNIT_FORCE_POINTS["infantry"] <= target:\n                    after["infantry"] += 1',
     '                while self._force_of(after) + UNIT_FORCE_POINTS["artillery"] <= target:\n                    after["artillery"] += 1'),
]

sys.exit(main(MUTANTS))
