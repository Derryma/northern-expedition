# -*- coding: utf-8 -*-
"""排空競態與驗證腳本埠號這一輪的突變測試。

這一輪修的兩件事都是「間歇性」的，所以判定器以結構斷言為主、e2e 為輔——
單跑一次 e2e 抓不牢六次裡才紅兩次的東西。

判定器：
  * backend.test_backend.DrainRaceTests——守「背景同步不得插隊排空」；
  * backend.test_backend.CheckScriptPortTests——守「一支腳本一個埠、
    啟動的埠就是輪詢的埠、綁不上要出聲」；
  * scripts/checks/card_effects_land_e2e.py——真前端跑一次，確認沒改壞。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.DrainRaceTests '
          'backend.test_backend.CheckScriptPortTests -q '
          '&& python3 scripts/checks/card_effects_land_e2e.py']
APP = 'frontend/app.js'
LOY = 'scripts/checks/loyalty_and_tags_e2e.py'

sys.exit(main([
    ("D1 背景同步又會插隊到排空中途（那筆效果會被 pull 蓋掉且永不重做）",
     "  if (!sharedReady || sharedSyncInFlight || drainInFlight) return;",
     "  if (!sharedReady || sharedSyncInFlight) return;", APP),

    ("D2 排空之後不再把成果推上共享狀態",
     "      await publishSharedState(true);\n"
     "    } catch (error) {\n"
     "      console.error(`[pending_frontend_effects] 排空後發佈失敗：${error.message}`);",
     "      void publishSharedState;\n"
     "    } catch (error) {\n"
     "      console.error(`[pending_frontend_effects] 排空後發佈失敗：${error.message}`);", APP),

    ("D3 降旗不放在 finally（排空丟例外就永遠降不下來，同步從此停擺）",
     "  return notes;\n  } finally {\n    drainInFlight = false;\n  }\n}",
     "  drainInFlight = false;\n  return notes;\n  } finally {\n  }\n}", APP),

    ("D4 兩支腳本又共用同一個埠",
     "BASE = 'http://127.0.0.1:8769'",
     "BASE = 'http://127.0.0.1:8767'", LOY),

    ("D5 綁不上埠時不再出聲（會默默量到別人那一台）",
     "        if proc.poll() is not None:\n"
     "            raise SystemExit(\"伺服器啟動失敗（多半是埠被佔住）\")\n",
     "", LOY),

    ("D6 啟動指令又不指定埠（綁預設的 8766，和輪詢的埠對不上）",
     "['python3', '-c', 'from backend.server import run; run(port=8769)']",
     "['python3', '-m', 'backend.server']", LOY),
], runner=RUNNER, timeout=2400))
