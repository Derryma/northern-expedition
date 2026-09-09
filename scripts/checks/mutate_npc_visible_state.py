# -*- coding: utf-8 -*-
"""「後端算了、但畫面只更新玩家那一半」這一輪的突變測試。

判定器：
  * backend.test_backend.NpcVisibleStateTests——守城市等級的權威來源，
    以及「鐵路停擺的理由由後端說」；
  * scripts/checks/card_effects_land_e2e.py——真前端把〈黔軍整頓茅台酒造〉
    打在 NPC 手上的遵義，看畫面跟不跟得動。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.NpcVisibleStateTests -q '
          '&& python3 scripts/checks/card_effects_land_e2e.py']
APP = 'frontend/app.js'
ENG = 'backend/card_engine.py'

sys.exit(main([
    ("V1 城市等級又只讀玩家的 city_economy（NPC 的城再也不動）",
     "    const override = levelOverrides[city.id];\n"
     "    if (override !== undefined) city.level = Number(override);\n"
     "    else if (economy && economy.level !== undefined) city.level = economy.level;",
     "    if (economy && economy.level !== undefined) city.level = economy.level;", APP),

    ("V2 覆寫解除時回不到基準等級",
     "    else city.level = baseCityLevels.get(city.id);",
     "    else void baseCityLevels;", APP),

    ("V3 後端不再說明鐵路為什麼停（前端只好一律寫「搶修中」）",
     '            "disabled_detail": self.disabled_railway_detail(),',
     '            "disabled_detail": {},', ENG),

    ("V4 永久封鎖又被寫成「搶修中」",
     "    if (detail?.no_repair) {",
     "    if (false) {", APP),

    ("V5 停擺明細把「修不好」漏掉",
     '                "no_repair": bool(effect.get("no_repair")),',
     '                "no_repair": False,', ENG),
], runner=RUNNER, timeout=2400))
