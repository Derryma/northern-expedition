# -*- coding: utf-8 -*-
"""批次二 B（NPC 戰鬥修正）與批次三（付費招募、兩個進入條件）的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

MUTANTS = [
    # ---- 批次二 B ----
    ("B-1 抽到的那回合就開始倒數（5 回合變 4 回合）",
     '                if effect.pop("granted_this_turn", None):\n                    alive.append(effect)\n                    continue',
     '                effect.pop("granted_this_turn", None)'),

    ("B-2 效果到期不移除",
     '                if remaining <= 0:\n                    continue\n                effect["remaining_turns"] = remaining',
     '                effect["remaining_turns"] = max(1, remaining)'),

    ("B-3 將領離場也不移除",
     '                    if general_id not in here:\n                        continue',
     '                    pass'),

    ("B-4 沒快照時把效果誤刪",
     '                if situation and situation.get("available") and general_id and faction:',
     '                if True:'),

    ("B-5 指定將領的效果變成整個陣營都吃到",
     '            if want_general and want_general != general_id:\n                continue',
     '            if False:\n                continue',
     'backend/combat_modifiers.py'),

    ("B-6 玩家部隊也吃得到 NPC 修正",
     '        if not faction or faction in self.engine.state["players"]:\n            return []',
     '        if not faction:\n            return []',
     'backend/combat_modifiers.py'),

    ("B-7 build() 不掛 NPC 修正",
     '                modifiers += self.npc_combat_modifiers(faction, army.get("general_id"))',
     '                modifiers += []',
     'backend/combat_modifiers.py'),

    ("B-8 效期不明的效果不擋",
     '            if turns is None and not until_leaves:\n                raise ValueError(',
     '            if False:\n                raise ValueError('),

    # ---- 批次三 ----
    ("C-1 沒抽中的也退錢",
     '                for code in bidders:\n                    self._player(code)["treasury"] = int(self._player(code)["treasury"]) - cost',
     '                self._player(bidders[0])["treasury"] = int(self._player(bidders[0])["treasury"]) - cost'),

    ("C-2 不抽籤，固定第一個人贏",
     '                winner = bidders[self.random.randrange(len(bidders))]',
     '                winner = bidders[0]'),

    ("C-3 贏了但部隊沒跟著走",
     '                    army["faction"] = winner\n                    moved.append(',
     '                    moved.append('),

    ("C-4 錢不夠的照樣算進分母",
     '                if int(self._player(code).get("treasury", 0)) < cost:\n                    broke.append(code)\n                    continue',
     '                pass'),

    ("C-5 沒表態的人也被當成出價",
     '                if self._event_responses(card).get(code) != option_id:\n                    continue',
     '                if False:\n                    continue'),

    ("C-6 宣戰條件不判",
     '            if at_war_with and not self._at_war(code, str(at_war_with)):\n                continue',
     '            if False:\n                continue'),

    ("C-7 駐軍條件不判",
     '            if not any(int(n) > 0 for n in here.values()):\n                return []',
     '            if False:\n                return []'),

    ("C-8 駐軍 0 營也算有兵",
     '            if not any(int(n) > 0 for n in here.values()):',
     '            if city_id not in (self._city_garrisons or {}):'),
]

sys.exit(main(MUTANTS))
