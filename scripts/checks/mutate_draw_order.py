# -*- coding: utf-8 -*-
"""NPC 卡優先抽的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("D1 完全不篩，退回純隨機",
     '            eligible = self._pick_by_priority(\n'
     '                eligible, int(self.state.get("event_draw_index", 0)))',
     '            eligible = eligible'),

    ("D2 序號不遞增（節奏卡在第一格）",
     '            self.state["event_draw_index"] = int(self.state.get("event_draw_index", 0)) + 1',
     '            pass'),

    ("D3 每一格都是 NPC 格（沒有一般卡的空檔）",
     '        return (int(draw_index) % period) < priority',
     '        return True'),

    ("D4 節奏顛倒成 1 NPC + 3 一般",
     '        return (int(draw_index) % period) < priority',
     '        return (int(draw_index) % period) >= ordinary'),

    ("D5 一般格也可以抽 NPC 卡",
     '        wanted = [cid for cid in eligible if self.is_priority_event(cid) == want_priority]\n'
     '        return wanted or eligible',
     '        return eligible'),

    ("D6 優先組認錯卡（前綴比對失效）",
     '        return ref.startswith(str(rule["ref_prefix"]))',
     '        return False'),

    ("D7 節奏寫死不讀資料檔",
     '        priority = max(0, int(rule.get("draws", 0)))\n'
     '        ordinary = max(0, int(rule.get("then_ordinary", 0)))',
     '        priority, ordinary = 3, 1'),

    ("D8 沒有 NPC 卡時整個週期停擺（不退回一般卡）",
     '        return wanted or eligible',
     '        return wanted'),
]))
