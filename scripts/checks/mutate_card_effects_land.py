# -*- coding: utf-8 -*-
"""「卡的效果真的落到畫面上」這一輪的突變測試。

判定器同時跑兩件事：
  * backend.test_backend.EveryCalledFunctionExistsTests——抓「叫了但沒人定義」；
  * scripts/checks/card_effects_land_e2e.py——真前端按下按鈕，抓「畫面沒跟上」。
只跑其中一個都會有突變體逃掉：前者看不到同步問題，後者看不到還沒被呼叫到的死名字。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.EveryCalledFunctionExistsTests -q '
          '&& python3 scripts/checks/card_effects_land_e2e.py']
JS = 'frontend/app.js'
PY = 'backend/server.py'

sys.exit(main([
    ("R1 重畫用的衍生資料函式又變成不存在的名字",
     'async function refreshBackendDerivedState() {',
     'async function __gone_refreshBackendDerivedState() {', JS),

    ("R2 選戰報那條路又叫回不存在的 renderMapUnits",
     '    renderArmyMarkers(currentPlayer);\n    return;\n  }',
     '    renderMapUnits();\n    return;\n  }', JS),

    ("R3 伺服器自己改動共享狀態時不推進版本",
     '        if SHARED_REVISION == before_revision and _tactical_fingerprint() != before:',
     '        if False:', PY),

    ("R4 版本衝突時又直接把錯誤丟給呼叫端",
     '    await pullSharedState();\n'
     '    if (retried) throw error;\n'
     '    return publishSharedState(true, true);',
     '    await pullSharedState();\n'
     '    throw error;', JS),

    ("R5 重畫時不收後端送來的 tactical",
     '    if (remote.tactical && remote.revision !== sharedRevision) {\n'
     '      applyTacticalSnapshot(remote.tactical);',
     '    if (false) {\n'
     '      applyTacticalSnapshot(remote.tactical);', JS),

    ("R6 忠誠加減的結果不套回前端",
     '  applyLoyaltyOverrides(result.loyalty_overrides);',
     '  applyLoyaltyOverrides({});', JS),

    ("R7 城市等級不從後端的 city_economy 同步",
     '      if (economy.level !== undefined) {\n        city.level = economy.level;\n      }',
     '      if (false) {\n        city.level = economy.level;\n      }', JS),
], runner=RUNNER, timeout=1800))
