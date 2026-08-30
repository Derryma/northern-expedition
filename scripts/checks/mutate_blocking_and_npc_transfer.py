# -*- coding: utf-8 -*-
"""鐵路阻截、急行軍支援、NPC 轉屬重編番號、吞併類地盤易主這一輪的突變測試。

這一輪改的幾乎全在前端，所以判定器不是單元測試，而是真前端的 e2e——
讀原始碼的字串斷言擋不住 `if (false) {` 這種突變，跑瀏覽器的擋得住。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

E2E = [sys.executable, 'scripts/checks/blocking_and_npc_transfer_e2e.py']
JS = 'frontend/app.js'

sys.exit(main([
    ("B1 鐵路又可以從敵軍頭上開過去",
     '      if (!ignoreBlockers && transitBlockedAt(next, destination, currentPlayer)) continue;',
     '      if (false) continue;', JS),

    ("B2 阻截只認艦隊、不認部隊",
     '  const army = blockingArmyAtCell(cell, movingFaction);\n'
     '  if (army) return { kind: "army", faction: factionForArmy(army) };',
     '  const army = null;\n'
     '  if (army) return { kind: "army", faction: factionForArmy(army) };', JS),

    ("B3 連終點的敵軍也擋（變成永遠打不進去）",
     '  if (!cell || (destination && cell.key === destination.key)) return null;',
     '  if (!cell) return null;', JS),

    ("M1 支援戰場又只認相鄰格",
     '  if (cellNeighbors(source).some((cell) => cell.key === target.key)) return true;\n'
     '  return Boolean(forcedMarchPath(source, target, army));',
     '  return cellNeighbors(source).some((cell) => cell.key === target.key);', JS),

    ("M2 急行軍路徑不理會沿途的敵軍",
     '      if (!ignoreBlockers && transitBlockedAt(next, destination, army && factionForArmy(army))) continue;',
     '      if (false) continue;', JS),

    ("N1 轉屬不重編番號",
     '  army.designator = formatArmyDesignator(nextAvailableArmyNumber(toFaction, army.id));',
     '  army.designator = army.designator;', JS),

    ("N2 轉屬不把將領掛進新陣營的將領樹",
     '      attachGeneralToFaction(copy, toFaction);',
     '      generalOwners[generalId] = toFaction;', JS),

    ("N3 轉屬不把將領從舊將領樹拆下來",
     '      if (sourceTree?.generals) delete sourceTree.generals[id];',
     '      if (false) delete sourceTree.generals[id];', JS),

    # 注意：這個突變體必須真的**拿掉**重編，不能只是把呼叫搬到上一行——
    # 第一版就是那樣寫的，號照重編，於是「逃掉了」其實是突變體沒生效。
    ("N4 付費招募類不重編番號",
     '      notes.push(`改編為${reassignGeneralAndArmy(army, effect.general_id, effect.owner)}`);',
     '      army.faction = effect.owner;\n'
     '      notes.push(`改編為${army.designator}`);', JS),

    ("N5 阻截說明指著起點自己",
     '  const blocked = openPath.slice(1).find((cell) => transitBlockedAt(cell, destination, movingFaction));',
     '  const blocked = openPath.find((cell) => transitBlockedAt(cell, destination, movingFaction));', JS),

    ("C1 吞併類的城市易主沒有畫上地圖",
     '    if (city.faction !== faction) transferCityEconomy(city, city.faction, faction);',
     '    if (false) transferCityEconomy(city, city.faction, faction);', JS),

    ("C2 吞併類的地格顏色沒有跟著改",
     '    const cell = cells[city.cellKey];\n    if (cell) cell.fac = faction;\n    names.push(city.name);',
     '    const cell = cells[city.cellKey];\n    if (false) cell.fac = faction;\n    names.push(city.name);', JS),

    ("C3 被併掉的部隊又用了沒人認得的退場狀態",
     '      army.status = "destroyed";\n    }\n    const cities = applyBackendCityTransfers(effect.cities, effect.into_faction);',
     '      army.status = "merged";\n    }\n    const cities = applyBackendCityTransfers(effect.cities, effect.into_faction);', JS),

    ("C4 歸附類的部隊沒有改旗",
     '      const designator = reassignGeneralAndArmy(army, entry.generalId, effect.owner);\n'
     '      if (designator) designators.push(designator);',
     '      const designator = null;\n'
     '      if (designator) designators.push(designator);', JS),
], runner=E2E, timeout=1800))
