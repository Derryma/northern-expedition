# -*- coding: utf-8 -*-
"""空轉機制稽核修復的突變測試。

每一個突變體都是「把修好的那條線再拆回去」。如果哪一項逃掉了，
代表 DeadMechanismAuditTests 裡對應的那條測試其實沒在守門。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("A1-1 非戰公約不再擋宣戰",
     '        if status == "war":\n            peace = self.active_timed_flag(player, "forced_peace") or {}\n            if peace.get("blocks_declaration"):',
     '        if False:\n            peace = self.active_timed_flag(player, "forced_peace") or {}\n            if peace.get("blocks_declaration"):'),

    ("A1-2 旗標參數不看，只要有強制和平就擋（連議和也擋）",
     '        if status == "war":\n            peace = self.active_timed_flag(player, "forced_peace") or {}',
     '        if True:\n            peace = self.active_timed_flag(player, "forced_peace") or {}'),

    ("A1-3 active_timed_flag 不管到期",
     '            if int(effect.get("remaining_turns", 0)) > 0:\n                return effect\n        return None',
     '            return effect\n        return None'),

    ("A2-1 幫會暴動的鎮壓加碼拿掉",
     '                "required_turns": int(card.get("suppression_turns", 2)) + self.suppression_turn_bonus(),',
     '                "required_turns": int(card.get("suppression_turns", 2)),'),

    ("A2-2 紅軍起義的鎮壓加碼拿掉",
     '            required_turns = int(card.get("required_turns", 2)) + self.suppression_turn_bonus()',
     '            required_turns = int(card.get("required_turns", 2))'),

    ("A2-3 通知文字自備一份回合數",
     '                f"每城需連續駐紮至少 {required} 營 {required_turns} 回合才能恢復。",',
     '                f"每城需連續駐紮至少 {required} 營 2 回合才能恢復。",'),

    ("A3-1 city_halt 不吃標籤加碼",
     '                span = self._extended_duration(card, halt.get("turns", 1))',
     '                span = halt.get("turns", 1)'),

    ("A3-2 action_ban 不吃標籤加碼",
     '                "until_turn": turn + int(self._extended_duration(card, spec.get("turns", 1), 1)),',
     '                "until_turn": turn + int(spec.get("turns", 1)),'),

    ("A3-3 student_unrest 不吃標籤加碼",
     '            span = int(self._extended_duration(card, unrest.get("turns", 3), 3))',
     '            span = int(unrest.get("turns", 3))'),

    ("A3-4 事件暴動又寫回 suppression_turns",
     '            "required_turns": int(self._extended_duration(\n                card, spec.get("required_turns", spec.get("suppression_turns")), 2)),',
     '            "suppression_turns": int(spec.get("suppression_turns", 1)),'),

    ("A3-5 加碼不分標籤，全部卡都吃",
     '            if tags & set(entry.get("tags") or []):\n                bonus += int(entry.get("bonus", 0))',
     '            if True:\n                bonus += int(entry.get("bonus", 0))'),

    ("A5-1 eligible_players 又塌回只問抽卡者",
     '    EVERY_FACTION_SCOPES = ("all_players", "eligible_players")',
     '    EVERY_FACTION_SCOPES = ("all_players",)'),

    ("A5-2 每家表態變成全場都問，不分資格",
     '        eligible = set(self._event_eligible_players(card)) & set(self.state["players"])',
     '        eligible = set(self.state["players"])'),

    ("C1-1 野戰醫院又寫死 +1",
     '            battalions = self._field_hospital_battalions(faction, general_id)',
     '            battalions = 1'),

    ("C2-1 將領綁定名單又寫死",
     '''    @property
    def GENERAL_BOUND_PERK_KEYS(self) -> tuple:
        keys = []''',
     '''    @property
    def GENERAL_BOUND_PERK_KEYS(self) -> tuple:
        return ("permanent_forced_march_generals", "field_hospital_generals")
        keys = []'''),

    ("B4-1 clear_cards 又變成沒人走得到",
     '                removed = self._purge_card_everywhere(code, card_id)\n                if removed:\n                    applied.append({"kind": "clear_cards", "player": code,',
     '                removed = 0\n                if removed:\n                    applied.append({"kind": "clear_cards", "player": code,'),
]))
