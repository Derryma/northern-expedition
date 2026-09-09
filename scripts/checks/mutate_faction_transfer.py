# -*- coding: utf-8 -*-
"""陣營吞併／歸屬轉移這一輪的突變測試。

判定器同時跑：
  * backend.test_backend.FactionTransferTacticalTests——守引擎與伺服器的接縫；
  * scripts/checks/faction_transfer_e2e.py——21 張卡逐張打真的 HTTP，
    而且刻意在 next-turn 與 respond-event 中間換一份新快照上去。

T1 是這一輪的主角：它不會讓任何東西壞掉、不會丟例外、applied 照樣回報成功，
只是把「現在這一份」換成一份深拷貝——也就是原本那個缺陷的模樣。
測試如果抓不到 T1，就代表這一輪根本沒有守住任何東西。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.FactionTransferTacticalTests -q '
          '&& python3 scripts/checks/faction_transfer_e2e.py']
ENG = 'backend/card_engine.py'
SRV = 'backend/server.py'

sys.exit(main([
    ("T1 引擎拿到的是一份深拷貝（原本那個缺陷：寫進孤兒，applied 照樣說成功）",
     "    return SHARED_TACTICAL_STATE if isinstance(SHARED_TACTICAL_STATE, dict) else None",
     "    return (json.loads(json.dumps(SHARED_TACTICAL_STATE))\n"
     "            if isinstance(SHARED_TACTICAL_STATE, dict) else None)", SRV),

    ("T2 綁定挪到跑完路由之後（等於沒綁）",
     "        ENGINE._tactical = current_tactical()\n        result = handler(payload)",
     "        result = handler(payload)\n        ENGINE._tactical = current_tactical()", SRV),

    ("T3 吞併不再轉移地格",
     "        for cell_key, fac in list(cell_factions.items()):",
     "        for cell_key, fac in []:", ENG),

    ("T4 被併吞的部隊不標記退場（空殼繼續留在地圖上）",
     '                    army["status"] = "destroyed"',
     '                    pass', ENG),

    ("T5 招募成功卻不換旗",
     '                    army["faction"] = winner',
     '                    pass', ENG),

    ("T6 將領轉屬不換旗",
     '                army["faction"] = to_faction',
     '                pass', ENG),

    ("T7 沒有快照時的轉屬又變回靜默（假裝成功）",
     '                applied.append({"kind": "npc_general_transfer_skipped",\n'
     '                                "reason": "no_tactical", "general": name,\n'
     '                                "from_faction": home_faction, "to_faction": to_faction})\n'
     '                transfer = None',
     '                pass', ENG),

    ("T8 respond_event 收了現在這一份卻不理它",
     "        self._tactical = tactical if isinstance(tactical, dict) else self._tactical",
     "        self._tactical = self._tactical", ENG),
], runner=RUNNER, timeout=3000))
