# -*- coding: utf-8 -*-
"""前後端同步稽核這一輪的突變測試。

判定器同時跑：
  * backend.test_backend.FrontendBackendSyncTests——守「每條線都有人走、
    交辦逐筆銷帳、伺服器改動要推進版本、驗證不准寫玩家存檔」；
  * scripts/checks/card_effects_land_e2e.py——真前端按按鈕，守「畫面真的跟上」。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.FrontendBackendSyncTests '
          'backend.test_backend.FrontendEffectChannelTests -q '
          '&& python3 scripts/checks/card_effects_land_e2e.py']
JS = 'frontend/app.js'
PY = 'backend/server.py'
ENG = 'backend/card_engine.py'

sys.exit(main([
    ("S1 交辦又不蓋流水號（只能整批銷帳）",
     '        stamped = {"id": f"fe{seq}", **entry}',
     '        stamped = {**entry}', ENG),

    ("S2 銷帳忽略點名的流水號，照舊整批清",
     '        if ids is not None:',
     '        if False:', ENG),

    ("S3 排空時不記已套用的流水號（銷帳失敗就重複套用）",
     '          appliedFrontendEffectIds.add(id);',
     '          void id;', JS),

    ("S4 一筆失敗又拖垮整個佇列",
     '      } catch (error) {\n'
     '        // 一筆做不成不該拖垮其他筆，更不該讓已經做完的沒被銷帳——\n'
     '        // 那會在下一次排空時把同一筆效果再套一次。',
     '      } catch (error) {\n'
     '        throw error;\n'
     '        // 一筆做不成不該拖垮其他筆，更不該讓已經做完的沒被銷帳——\n'
     '        // 那會在下一次排空時把同一筆效果再套一次。', JS),

    ("S5 伺服器自己改動共享狀態時不推進版本",
     '        if SHARED_REVISION == before_revision and _tactical_fingerprint() != before:',
     '        if False:', PY),

    ("S6 存檔目錄又寫死成玩家的 game_data",
     '''GAME_DATA_DIR = pathlib.Path(
    os.environ.get("NE_GAME_DATA_DIR") or (REPO_ROOT / "game_data"))''',
     'GAME_DATA_DIR = REPO_ROOT / "game_data"', PY),

    ("S7 重畫用的衍生資料函式又不存在",
     'async function refreshBackendDerivedState() {',
     'async function __gone_refreshBackendDerivedState() {', JS),
], runner=RUNNER, timeout=1800))
