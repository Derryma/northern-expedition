# -*- coding: utf-8 -*-
"""「存檔歸存檔、開局地圖歸開局地圖」這一輪的突變測試。

判定器：
  * scripts/checks/save_vs_opening_map_e2e.py——這條界線本身；
  * scripts/checks/province_ownership_e2e.py——開局地圖真的還是那一張
    （省級歸屬保證、城市落點、駐軍）。

只跑其中一個會有突變體逃掉：把還原改回「無條件全套」的話，界線那支立刻紅，
但省界那支照樣全綠（乾淨新局本來就沒有存檔可蓋）；反過來，把 applyOpeningMap()
改成只還原 SCENARIO_CELL_FACTIONS（省級歸屬保證不跑），界線那支只看得到
「重跑結果一致」——因為兩邊都錯得一樣——要靠省界那支才抓得到。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 scripts/checks/save_vs_opening_map_e2e.py '
          '&& python3 scripts/checks/province_ownership_e2e.py']
APP = 'frontend/app.js'

sys.exit(main([
    ("S1 存檔的地格歸屬又被無條件全套（這一輪修的就是它）",
     "  const mapNotice = applyCellFactionsFromSnapshot(snapshot);\n"
     "  if (mapNotice) uiNotice = mapNotice;",
     "  for (const [cellKey, faction] of Object.entries(snapshot.cellFactions || {})) {\n"
     "    if (cells[cellKey]) cells[cellKey].fac = faction;\n"
     "  }", APP),

    ("S2 存檔不再記下自己是照哪一版開局地圖存的",
     "    openingMap: {\n"
     "      revision: openingMapRevision,\n"
     "      cells: { ...(OPENING_CELL_FACTIONS || {}) },\n"
     "    },",
     "", APP),

    ("S3 版本對不上時不先歸零，直接疊（沒打過的格子留著舊地圖）",
     "  applyOpeningMap();\n"
     "  if (!savedCells) {",
     "  if (!savedCells) {", APP),

    ("S4 版本對不上時連玩家打下來的戰果也一起丟掉",
     "    if (faction === (savedCells[cellKey] ?? null)) { rebased++; continue; }  // 玩家沒動過\n"
     "    cells[cellKey].fac = faction;",
     "    if (faction === (savedCells[cellKey] ?? null)) { rebased++; continue; }  // 玩家沒動過\n"
     "    rebased++;", APP),

    ("S5 沒有 openingMap 的舊存檔又被照單全收",
     "  if (!savedCells) {\n"
     "    const stale = Object.entries(snapshot?.cellFactions || {})",
     "  if (!savedCells) {\n"
     "    for (const [k, v] of Object.entries(snapshot?.cellFactions || {})) {\n"
     "      if (cells[k]) cells[k].fac = v;\n"
     "    }\n"
     "    const stale = Object.entries(snapshot?.cellFactions || {})", APP),

    ("S6 版本改成寫死的號碼（地圖改了也不會變）",
     "  openingMapRevision = hashCellFactions(OPENING_CELL_FACTIONS);",
     "  openingMapRevision = 'v1';", APP),

    ("S7 開局地圖在套用存檔之後才拍（拍到的是存檔，不是開局）",
     "  indexScenarioCells();\n"
     "  // 開局地圖要在**套用任何存檔之前**拍下來。下面 applyTacticalSnapshot() 會拿它\n"
     "  // 當基準，判斷存檔裡哪些格是玩家真的打下來的。\n"
     "  captureOpeningMap();",
     "  indexScenarioCells();", APP),

    ("S8 重新開始又只還原 map.js 的原始快照（省級歸屬保證被抹掉）",
     "function applyOpeningMap() {\n"
     "  for (const cell of Object.values(cells)) cell.fac = SCENARIO_CELL_FACTIONS[cell.key];\n"
     "  indexProvinceCells();\n"
     "}",
     "function applyOpeningMap() {\n"
     "  for (const cell of Object.values(cells)) cell.fac = SCENARIO_CELL_FACTIONS[cell.key];\n"
     "}", APP),

    ("S9 版本不一樣時什麼都不說（玩家看不到地圖被重新對齊過）",
     "  return `存檔是照舊版開局地圖存的：${carried} 格戰果照舊保留，`\n"
     "    + `其餘 ${rebased} 格改以目前的開局地圖為準。`;",
     "  void carried; void rebased;\n  return null;", APP),

    ("S10 同版本也走重新對齊那條路（多人同步每次都被歸零）",
     "  if (saved?.revision && saved.revision === openingMapRevision) {",
     "  if (false) {", APP),
], runner=RUNNER, timeout=5400))
