# -*- coding: utf-8 -*-
"""批次一（NPC 增兵）的突變測試。每一條都是「這行如果寫錯，測試會不會紅」。"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

MUTANTS = [
    # 累加改成覆蓋：同一支部隊被兩條規則點到時，後面那條會蓋掉前面那條。
    ("D-1 兩條規則不累加，直接覆蓋",
     '                    totals[army_id][unit] = totals[army_id].get(unit, 0) + int(amount)',
     '                    totals[army_id][unit] = int(amount)'),

    # 排除名單失效：15.3 的馮玉祥會多吃一營步兵。
    ("D-2 except_generals 不生效",
     '        excluded = spec.get("except_generals")',
     '        excluded = None'),

    # 死人照樣補兵。
    ("D-3 陣亡／被俘的部隊照樣補兵",
     '            if army.get("status") in self.DEAD_ARMY_STATUSES:\n                continue\n            if self._npc_defected(army_id, army, owners):\n                continue\n            if army.get("generalId") in jailed:\n                continue\n            out[army_id] = army',
     '            out[army_id] = army'),

    # 跳槽的部隊照樣補兵。
    ("D-4 跳槽過的部隊照樣補兵",
     '            if self._npc_defected(army_id, army, owners):\n                continue\n            if army.get("generalId") in jailed:',
     '            if army.get("generalId") in jailed:'),

    # 玩家的部隊也被當成 NPC。
    ("D-5 玩家部隊也吃得到 NPC 補兵",
     '            if self._home_faction(army_id) not in self.NPC_FACTIONS:\n                continue\n            if army.get("status") in self.DEAD_ARMY_STATUSES:',
     '            if army.get("status") in self.DEAD_ARMY_STATUSES:'),

    # 戰力上限不管了。
    ("D-6 補兵不看戰力上限",
     '                    if self._force_of(after) + UNIT_FORCE_POINTS[unit] > ARMY_FORCE_CAP:\n                        break',
     '                    if False:\n                        break'),

    # 伺服器手上那份不改：同一週期後面的卡看到的是舊現況。
    ("D-7 後端不改自己手上的戰術快照",
     '                    if army is not None:\n                        army["units"] = dict(entry["units"])',
     '                    if army is not None:\n                        pass'),

    # 前端的佇列不掛：畫面永遠看不到補兵。
    ("D-8 不掛前端佇列",
     '                    self._player(holder).setdefault("pending_frontend_effects", []).append({\n                        "kind": "npc_army_units", "label": label, "armies": patch})',
     '                    pass'),

    # 查無此人靜默略過，而不是拋錯。
    ("D-9 查無此人不拋錯",
     '                    raise ValueError(f"{card_id} 的 npc_unit_delta 點名了查無此人的將領：{name}")',
     '                    continue'),

    # 不認得的兵種靜默略過。
    ("D-10 不認得的兵種不拋錯",
     '                raise ValueError(\n                    f"{card.get(\'id\')} 的 npc_unit_delta 用了不認得的兵種：{sorted(unknown)}")',
     '                deltas = {k: v for k, v in deltas.items() if k in UNIT_FORCE_POINTS}'),

    # 沒變動也報一筆。
    ("D-11 沒補到兵也報一筆",
     '            if not gained:\n                continue',
     '            if False:\n                continue'),

    # 減損也被上限邏輯吃掉（負數當成正數補）。
    ("D-12 減損不生效",
     '                if int(amount) < 0:\n                    after[unit] = max(0, after[unit] + int(amount))',
     '                if False:\n                    after[unit] = max(0, after[unit] + int(amount))'),
]

sys.exit(main(MUTANTS))
