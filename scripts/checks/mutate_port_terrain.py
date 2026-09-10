# -*- coding: utf-8 -*-
"""港口水域與地形這一輪的突變測試。

判定器：
  * backend.test_backend.PortWaterRosterTests——守名單那一半（每座港市都有
    水域、每座河港剛好在一份名單裡、bootstrap 真的把 waters 送出去）；
  * backend.test_backend.CityRosterTests——守名冊那一半；
  * scripts/checks/port_terrain_e2e.py——真前端：河港地格變成水域且河名等於
    後端給的、陸軍走得過去、艦隊進得去、海港仍是陸地且貼著海。

只跑其中一個會有突變體逃掉：名單漏一座城市單元測試抓得到、e2e 只看得到
「地圖說長江、後端說沒有」；前端改回自己算最近的河，單元測試一點感覺都沒有。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.PortWaterRosterTests '
          'backend.test_backend.CityRosterTests -q '
          '&& python3 scripts/checks/port_terrain_e2e.py']
APP = 'frontend/app.js'
ENG = 'backend/card_engine.py'
PUN = 'backend/foreign_punishment.py'
MAP = 'scenario/data/strategic_map.json'

sys.exit(main([
    ("P1 後端不再把水域送出去（前端只好又自己猜）",
     '            if city.get("port"):\n'
     '                city["waters"] = list(waters_for_city(city))',
     '            pass', ENG),

    ("P2 前端又自己拿最近的河當港口水系",
     '    cell.river = portWaterName(cell.city);',
     '    if (!cell.river) cell.river = "長江";', APP),

    ("P3 河港地格不再變成水域",
     '    cell.portWater = true;\n'
     '    cell.river = portWaterName(cell.city);',
     '    cell.river = portWaterName(cell.city);', APP),

    ("P4 沙市又從長江名單裡漏掉（畫面淹、結算不淹）",
     '"shashi", "chengdu", "xiangyang"],',
     '"chengdu", "xiangyang"],', PUN),

    ("P5 成都與襄陽又漏回去（這一輪修的就是它）",
     '"shashi", "chengdu", "xiangyang"],',
     '"shashi"],', PUN),

    ("P6 惠州的海港被拿掉",
     '      "lat": 23.11,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1,\n'
     '      "port": "sea"',
     '      "lat": 23.11,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1', MAP),

    # 自貢一度做成河港，使用者改回普通陸地城市。這一關守的是「改回去要改乾淨」：
    # 名冊沒有 port、水系名單也沒有它——只回退一半就會被抓到。
    ("P7 自貢又被偷偷做回河港（名冊那一半）",
     '      "id": "zigong",\n'
     '      "name": "自貢",\n'
     '      "province": "四川",\n'
     '      "faction": "C",\n'
     '      "lon": 104.78,\n'
     '      "lat": 29.35,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1',
     '      "id": "zigong",\n'
     '      "name": "自貢",\n'
     '      "province": "四川",\n'
     '      "faction": "C",\n'
     '      "lon": 104.78,\n'
     '      "lat": 29.35,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1,\n'
     '      "port": "river"', MAP),

    ("P7b 自貢又被偷偷放回長江名單（水系那一半）",
     '"shashi", "chengdu", "xiangyang"],',
     '"shashi", "chengdu", "xiangyang", "zigong"],', PUN),

    ("P8b 沙市的河港被拿掉",
     '      "lat": 30.32,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1,\n'
     '      "port": "river"',
     '      "lat": 30.32,\n'
     '      "level": 2,\n'
     '      "cash": 4,\n'
     '      "factory": 1', MAP),

    ("P8 河港又需要浮橋才過得去（陸軍被自家港口擋住）",
     '  return riverCells.every((cell) => cell.city?.port === "river"\n'
     '    || completedPontoons.has(cell.key)',
     '  return riverCells.every((cell) => completedPontoons.has(cell.key)', APP),

    ("P9 光禿禿的河道也放行（過河規則整條失效）",
     '  const riverCells = [from, to].filter((cell) => cell.river);\n'
     '  if (!riverCells.length) return true;',
     '  const riverCells = [from, to].filter((cell) => cell.river);\n'
     '  return true;\n'
     '  if (!riverCells.length) return true;', APP),

    ("P10 海港的地格也被改成水域",
     '    if (cell.city?.port !== "river") continue;',
     '    if (!cell.city?.port) continue;', APP),

    # P11 之所以要有專屬的一關去驗那個 throw：只改 fallback 而資料仍然完整的話，
    # 那一行永遠跑不到，突變體與原始碼在實際資料下等價、任何判定器都看不出差別。
    # e2e 裡的「名單漏掉時前端會大聲拒絕」直接拿一座假的港市去問 portWaterName()，
    # 這一關才驗得到。
    ("P11 名單漏掉時前端悄悄補一個名字，不再大聲拒絕",
     '  if (waters.length) return waters[0];',
     '  if (!waters.length) return "內河";\n  if (waters.length) return waters[0];', APP),
], runner=RUNNER, timeout=5400))
