# -*- coding: utf-8 -*-
"""「後端是唯一計算引擎」這一輪的突變測試。"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

sys.exit(main([
    ("U1 策反又相信客戶端送來的數字",
     '        if general_id:\n            quote = self.defection_quote(str(general_id), tactical)',
     '        if False:\n            quote = self.defection_quote(str(general_id), tactical)'),

    ("U2 抗策反表被忽略",
     '        return sum(self.DEFECTION_RESISTANCE_TRAITS.get(str(t), 0.0)\n'
     '                   for t in (traits or []))',
     '        return 0.0'),

    ("U3 報價不看戰術快照的忠誠",
     '        report = self.loyalty_report(snapshot).get(general_id) or {}',
     '        report = {}'),

    ("U4 失效技能名單永遠是空的",
     '        return sorted(trait for trait, rule in RELATION_DISABLED_TRAITS.items()\n'
     '                      if self._trait_relation_disabled(player, rule))',
     '        return []'),

    ("U5 snapshot 不再送失效技能名單",
     '            payload["disabled_traits"] = self.disabled_traits(player)',
     '            payload["disabled_traits"] = []'),

    ("U6 前端又自己算忠誠（把過渡算式放回去）",
     '  const fromBackend = backendLoyalty?.[general.id];\n'
     '  if (fromBackend && fromBackend.value !== null && fromBackend.value !== undefined) {',
     '  const relativePower = 0;\n'
     '  const fromBackend = backendLoyalty?.[general.id];\n'
     '  if (false) {',
     'frontend/app.js'),

    ("U7 面板重畫前不再確認後端數字是不是舊的",
     '  ensureBackendDerivedFresh(panelName);\n',
     '',
     'frontend/app.js'),

    ("U8 手牌上限又寫死一份",
     '  return backendNumber("features.function_card_max_hand_size");',
     '  return 6;',
     'frontend/app.js'),
]))
