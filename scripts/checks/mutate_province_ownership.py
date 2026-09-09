# -*- coding: utf-8 -*-
"""省界與省級歸屬這一輪的突變測試。

判定器同時跑：
  * backend.test_backend.ProvinceBordersAndOwnershipTests——守省界檔、城市省籍、
    宣告表的內容，以及「保證要在部隊入城前套用」這個順序；
  * scripts/checks/province_ownership_e2e.py——真前端跑完 boot() 之後逐格量。

寫突變時要小心：改的地方必須真的會讓結果不同。如果只是把一行搬到另一行、
或改成語意相同的寫法，突變會「逃掉」——那不是測試不夠力，是突變本身沒生效。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.ProvinceBordersAndOwnershipTests -q '
          '&& python3 scripts/checks/province_ownership_e2e.py']
JS = 'frontend/map.js'
APP = 'frontend/app.js'
MAP = 'scenario/data/strategic_map.json'

sys.exit(main([
    ("P1 四川那一條被刪掉（四川不再整省歸川軍）",
     "  { province: '四川', faction: 'C', keep: ['W'] },\n",
     "", JS),

    ("P2 川東的例外被拿掉（連直系的走廊也一起吞了）",
     "{ province: '四川', faction: 'C', keep: ['W'] }",
     "{ province: '四川', faction: 'C' }", JS),

    ("P3 察哈爾的緯度上限沒了（錫林郭勒草原被順手收走）",
     "{ province: '察哈爾', faction: 'G', maxLat: 42.4 }",
     "{ province: '察哈爾', faction: 'G' }", JS),

    ("P4 陝甘的 replaces 失效（改成整省改判，把直系晉系也吞了）",
     "      if (claim.replaces && !claim.replaces.includes(cell.fac)) continue;",
     "      if (false) continue;", JS),

    ("P5 省份索引不再套用歸屬保證",
     "  applyProvinceOwnershipClaims((cell) => cell.province, cityHomeCells());",
     "  void applyProvinceOwnershipClaims;", APP),

    ("P6 歸屬保證改到部隊入城之後才套用",
     "  indexProvinceCells();\n  indexScenarioCells();\n  snapArmiesToStartCities();",
     "  indexScenarioCells();\n  snapArmiesToStartCities();\n  indexProvinceCells();", APP),

    ("P7 韓復榘又回到西安（潼關空著）",
     "generalId: 'han_fuqu', general: '韓復榘', designator: '第三軍', startCityId: 'tongguan', lon: 110.2, lat: 34.5",
     "generalId: 'han_fuqu', general: '韓復榘', designator: '第三軍', startCityId: 'xian', lon: 108.9, lat: 34.3", JS),

    ("P9 護欄失效：條款把別家城市腳下那一格也收走（大同被擠開一格）",
     "      if (resident && resident !== claim.faction) continue;",
     "      if (false) continue;", JS),

    ("P10 護欄根本沒接上（套用條款時不看城市名冊）",
     "  applyProvinceOwnershipClaims((cell) => cell.province, cityHomeCells());",
     "  applyProvinceOwnershipClaims((cell) => cell.province);", APP),

    ("P11 城市不再讀釘選的地格（張家口、瀘州又被最近的同色格吸走）",
     "    if (city.cell_key) {",
     "    if (false) {", APP),

    ("P12 逐格例外表被清空（大同右下那一格回到奉系）",
     "  '25,15': 'Y',",
     "", JS),

    ("P8 西寧的省籍被改成青海（甘青邊界把西寧畫走了）",
     '"id": "xining",\n      "name": "西寧",\n      "province": "甘肅",',
     '"id": "xining",\n      "name": "西寧",\n      "province": "青海",', MAP),
], runner=RUNNER, timeout=3000))
