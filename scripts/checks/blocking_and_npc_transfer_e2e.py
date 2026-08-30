# -*- coding: utf-8 -*-
"""真前端複查：鐵路阻截、急行軍支援遠距戰場、NPC 轉屬重編番號、吞併類地盤易主。"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, subprocess, sys, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8771'


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉再量。")
    port = int(BASE.rsplit(':', 1)[1])
    proc = subprocess.Popen(
        ['python3', '-c', f'from backend.server import run; run(port={port})'],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("伺服器起不來")


PROBE = r"""
const d = window.__neDebug;
const out = {};
const me = d.getCurrentPlayer();
const other = ['F','W','S','N'].find(c => c !== me);
const cells = d.cells;

// ---------- 1. 鐵路阻截 ----------
{
  // 找一條真的排得出來、而且至少有一個中途格的鐵路路線。
  const railCells = Object.values(cells).filter(c => c.railroads?.size && !c.power);
  let found = null;
  for (const from of railCells) {
    for (const to of railCells) {
      if (from.key === to.key) continue;
      const path = d.railwayPath(from, to);
      if (path && path.length >= 3) { found = { from, to, path }; break; }
    }
    if (found) break;
  }
  if (!found) { out.鐵路阻截 = { 錯誤: '找不到長度 >= 3 的鐵路路線' }; }
  else {
    const mid = found.path[1];
    // 把一支敵軍搬到中途格上。
    const enemy = d.allArmies().find(a => d.factionForArmy(a) !== me);
    const wasAt = enemy.cellKey;
    const 阻截前 = (d.railwayPath(found.from, found.to) || []).length;
    d.moveArmyToCell(enemy, mid);
    const 阻截後 = (d.railwayPath(found.from, found.to) || []).length;
    const 繞得過去 = 阻截後 > 0 && !(d.railwayPath(found.from, found.to) || [])
      .some(c => c.key === mid.key);
    out.鐵路阻截 = {
      起點: found.from.key, 終點: found.to.key, 中途格: mid.key,
      阻截者: d.factionForArmy(enemy),
      阻截前路線長度: 阻截前,
      阻截後路線長度: 阻截後,
      阻截後仍走得到: 阻截後 > 0,
      繞過阻截走到終點: 繞得過去,
      擋路者回報: d.transitBlockedAt(mid, found.to, me),
    };
    const mover = { ...d.allArmies().find(a => d.factionForArmy(a) === me), cellKey: found.from.key };
    const 說明 = d.blockedTransitReason(found.from, found.to, mover);
    const 擋路陣營短名 = d.FACTIONS[d.factionForArmy(enemy)]?.shortName
      || d.factionForArmy(enemy);
    out.鐵路阻截.說明 = 說明;
    out.鐵路阻截.擋路陣營短名 = 擋路陣營短名;
    out.鐵路阻截.說明指的是真正擋路的那一支 = String(說明 || '').includes(擋路陣營短名);
    // 終點站著敵軍不該擋——那是要打進去的地方。
    const 終點有敵軍 = (() => {
      d.moveArmyToCell(enemy, found.to);
      const path = d.railwayPath(found.from, found.to);
      return Boolean(path);
    })();
    out.鐵路阻截.終點有敵軍仍可進攻 = 終點有敵軍;
    d.moveArmyToCell(enemy, cells[wasAt]);
  }
}

// ---------- 2. 急行軍支援 2 格外的戰鬥 ----------
{
  const mine = d.allArmies().filter(a => d.factionForArmy(a) === me);
  const supporter = mine[0];
  const attacker = mine.find(a => a.id !== supporter.id);
  const neigh = (c) => d.cellNeighbors(c).map(x => x.key);
  const home = cells[supporter.cellKey];
  const near = new Set(neigh(home));
  // 距支援部隊剛好 2 格：是某個鄰格的鄰格，但自己不是鄰格。
  let battleCell = null, between = null;
  for (const first of d.cellNeighbors(home)) {
    if (first.power) continue;
    const second = d.cellNeighbors(first)
      .find(c => !c.power && c.key !== home.key && !near.has(c.key));
    if (second) { battleCell = second; between = first; break; }
  }
  if (!battleCell) { out.急行軍支援 = { 錯誤: '找不到距支援部隊剛好 2 格的地格' }; }
  else {
    await d.api('/api/diplomacy', { player: me, target: other, status: 'war' });
    await d.pullSharedState();
    const enemy = d.allArmies().find(a => d.factionForArmy(a) === other);
    const blocker = d.allArmies().find(a => d.factionForArmy(a) !== me && a.id !== enemy.id);
    const attackerFrom = d.cellNeighbors(battleCell).find(c => !c.power && c.key !== between.key)
      || between;
    d.moveArmyToCell(attacker, attackerFrom);
    d.moveArmyToCell(enemy, battleCell);
    const battle = d.startBattle(attacker, enemy, battleCell, attackerFrom.key);
    d.clearArmyResolved(supporter.id);
    delete supporter.forcedMarchUntilTurn;
    const 沒買急行軍 = Boolean(d.joinableBattleForArmy(supporter));
    supporter.forcedMarchUntilTurn = Number(d.getState().turn) + 3;
    const 買了急行軍 = Boolean(d.joinableBattleForArmy(supporter));
    // 中途格塞一支敵軍，應該又投不進去。
    let 中途有敵軍 = null, blockerWas = null;
    if (blocker) {
      blockerWas = blocker.cellKey;
      d.moveArmyToCell(blocker, between);
      中途有敵軍 = Boolean(d.joinableBattleForArmy(supporter));
      d.moveArmyToCell(blocker, cells[blockerWas]);
    }
    out.急行軍支援 = {
      支援部隊所在: home.key, 中途格: between.key, 戰場: battleCell.key,
      支援部隊: supporter.designator,
      距離兩格: !near.has(battleCell.key),
      沒買急行軍就投得進去: 沒買急行軍,
      買了急行軍投得進去: 買了急行軍,
      中途有敵軍時投得進去: 中途有敵軍,
    };
    d.joinBattle(supporter, battle);
    out.急行軍支援.援軍名單 = JSON.parse(JSON.stringify(battle.reinforcementIds || {}));
    out.急行軍支援.真的投進去了 = Object.values(battle.reinforcementIds || {})
      .some(list => list.includes(supporter.id));
    out.急行軍支援.提示 = d.getUiNotice();
    battle.status = 'withdrawn';
  }
}

// ---------- 3./4. NPC 轉屬與吞併 ----------
const handlers = d.pendingEffectHandlers();
const armyOfGeneral = (gid) => d.allArmies(true).find(a => a.generalId === gid);

// 3. 韓復榘型：將領換陣營要重編番號、要進新陣營的將領樹。
{
  const army = armyOfGeneral('ma_fuxiang');   // 馬家軍第二軍
  const 轉屬前 = { 番號: army.designator, 陣營: d.factionForArmy(army),
                   在G的名冊裡: Boolean(d.getGeneralTrees()['G']?.generals?.ma_fuxiang) };
  const note = handlers.npc_general_transferred(me, {
    kind: 'npc_general_transferred', label: '西北軍結盟馬家軍',
    general: '馬福祥', general_id: 'ma_fuxiang',
    from_faction: 'M', to_faction: 'G',
    armies: [{ armyId: army.id, units: { ...army.units } }],
    relocate: { near_city: 'zhangjiakou', within: 1 },
  });
  const gAll = d.allArmies(true).filter(a => d.factionForArmy(a) === 'G')
    .map(a => a.designator);
  out.將領轉屬 = {
    轉屬前, 摘要: note,
    轉屬後番號: army.designator, 轉屬後陣營: d.factionForArmy(army),
    進了G的將領樹: Boolean(d.getGeneralTrees()['G']?.generals?.ma_fuxiang),
    離開M的將領樹: !d.getGeneralTrees()['M']?.generals?.ma_fuxiang,
    generalOwners: d.generalOwners.ma_fuxiang,
    西北軍全部番號: gAll,
    番號沒撞號: new Set(gAll).size === gAll.length,
  };
}

// 3b. 韓復榘投靠南京（15.21 付費招募）：使用者點名的那個例子。
{
  const army = armyOfGeneral('han_fuqu');   // 西北軍第三軍
  const 招募前 = { 番號: army.designator, 陣營: d.factionForArmy(army) };
  const before = d.allArmies(true).filter(a => d.factionForArmy(a) === 'N')
    .map(a => a.designator);
  const note = handlers.npc_general_recruited(me, {
    kind: 'npc_general_recruited', label: '韓復榘投靠南京',
    general_id: 'han_fuqu', general: '韓復榘',
    from_faction: 'G', owner: 'N',
    armies: [{ armyId: army.id, units: { ...army.units } }],
  });
  const after = d.allArmies(true).filter(a => d.factionForArmy(a) === 'N')
    .map(a => a.designator);
  out.韓復榘 = {
    招募前, 摘要: note,
    招募後番號: army.designator, 招募後陣營: d.factionForArmy(army),
    南京原有番號: before, 南京現在番號: after,
    番號改了: army.designator !== 招募前.番號,
    番號沒撞號: new Set(after).size === after.length,
    進了南京名冊: Boolean(d.getGeneralTrees()['N']?.generals?.han_fuqu),
    離開西北軍名冊: !d.getGeneralTrees()['G']?.generals?.han_fuqu,
  };
}

// 4a. 整個陣營歸附玩家：部隊換旗＋重編番號＋城市易主。
{
  const cityIds = (d.getBootstrap().strategic_map?.cities || [])
    .filter(c => c.faction === 'M').map(c => c.id);
  const armies = d.allArmies(true).filter(a => d.factionForArmy(a) === 'M')
    .map(a => ({ armyId: a.id, generalId: a.generalId, units: { ...a.units } }));
  const 歸附前 = cityIds.map(id => {
    const city = (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === id);
    return { 城: city.name, 歸屬: city.faction, 地格: cells[city.cellKey]?.fac };
  });
  const note = handlers.npc_faction_absorbed(me, {
    kind: 'npc_faction_absorbed', label: '馬家軍歸附',
    faction: 'M', owner: me, armies, cities: cityIds,
  });
  const 歸附後 = cityIds.map(id => {
    const city = (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === id);
    return { 城: city.name, 歸屬: city.faction, 地格: cells[city.cellKey]?.fac };
  });
  const mineNow = d.allArmies(true).filter(a => d.factionForArmy(a) === me)
    .map(a => a.designator);
  out.陣營歸附 = {
    摘要: note, 歸附前, 歸附後,
    城市全數易主: 歸附後.every(c => c.歸屬 === me),
    地格全數易主: 歸附後.every(c => c.地格 === me),
    部隊全數改旗: armies.every(a => d.factionForArmy(d.armyById(a.armyId)) === me),
    新主陣營番號: mineNow,
    番號沒撞號: new Set(mineNow).size === mineNow.length,
    進了名冊: armies.map(a => a.generalId)
      .filter(g => g).every(g => Boolean(d.getGeneralTrees()[me]?.generals?.[g])),
  };
}

// 4b. NPC 併 NPC：被併的部隊要真的退場，地盤要轉屬。
{
  const qian = d.allArmies(true).filter(a => d.factionForArmy(a) === 'Q');
  const target = armyOfGeneral('liu_xiang');
  const cityIds = (d.getBootstrap().strategic_map?.cities || [])
    .filter(c => c.faction === 'Q').map(c => c.id);
  const 併前 = { 黔軍還在地圖上: d.allArmies().some(a => d.factionForArmy(a) === 'Q'),
                 黔城歸屬: cityIds.map(id => (d.getBootstrap().strategic_map.cities
                   .find(c => c.id === id) || {}).faction) };
  const note = handlers.npc_faction_merged(me, {
    kind: 'npc_faction_merged', label: '劉湘吞併黔軍',
    from_faction: 'Q', into_faction: 'C',
    into_general_id: 'liu_xiang', into_army_id: target.id,
    units: { infantry: 16, cavalry: 4, artillery: 2, machine_gun: 2 },
    absorbed: qian.map(a => ({ armyId: a.id, units: { ...a.units } })),
    cities: cityIds,
  });
  out.陣營吞併 = {
    摘要: note, 併前,
    黔軍還在地圖上: d.allArmies().some(a => d.factionForArmy(a) === 'Q'),
    被併部隊狀態: qian.map(a => a.status),
    黔城歸屬: cityIds.map(id => (d.getBootstrap().strategic_map.cities
      .find(c => c.id === id) || {}).faction),
    黔地格歸屬: cityIds.map(id => {
      const city = d.getBootstrap().strategic_map.cities.find(c => c.id === id);
      return cells[city.cellKey]?.fac;
    }),
    劉湘部編制: { ...target.units },
  };
}
return out;
"""


async def main():
    proc = start_server()
    try:
        results = {}
        async with async_playwright() as pw:
            b = await pw.chromium.launch(args=['--no-sandbox'])
            page = await b.new_page(viewport={'width': 1400, 'height': 900})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)[:300]))
            await page.goto(BASE + '/', wait_until='networkidle')
            await page.wait_for_timeout(7000)
            results['結果'] = await page.evaluate("async () => {" + PROBE + "}")
            if errs:
                results['__主控台錯誤__'] = errs[:5]
            await page.close(); await b.close()
        print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
        r = results.get('結果') or {}
        rail = r.get('鐵路阻截') or {}
        march = r.get('急行軍支援') or {}
        move = r.get('將領轉屬') or {}
        absorb = r.get('陣營歸附') or {}
        merge = r.get('陣營吞併') or {}
        han = r.get('韓復榘') or {}
        checks = {
            "鐵路：中途有敵軍就排不出路線": rail.get('阻截後仍走得到') is False,
            "鐵路：沒有從敵軍旁邊繞過去": rail.get('繞過阻截走到終點') is False,
            "鐵路：擋路者有具名回報": bool(rail.get('擋路者回報')),
            "鐵路：說得出是被誰擋住": '阻截' in str(rail.get('說明') or ''),
            "鐵路：說明指的是真正擋路的那一支":
                rail.get('說明指的是真正擋路的那一支') is True,
            "鐵路：終點站著敵軍仍可進攻": rail.get('終點有敵軍仍可進攻') is True,
            "急行軍：戰場真的在 2 格外": march.get('距離兩格') is True,
            "急行軍：沒買就投不進去": march.get('沒買急行軍就投得進去') is False,
            "急行軍：買了就投得進去": march.get('買了急行軍投得進去') is True,
            "急行軍：中途有敵軍就投不進去": march.get('中途有敵軍時投得進去') in (False, None),
            "急行軍：真的進了援軍名單": march.get('真的投進去了') is True,
            "轉屬：番號改了": (move.get('轉屬前') or {}).get('番號') != move.get('轉屬後番號'),
            "轉屬：換了陣營": move.get('轉屬後陣營') == 'G',
            "轉屬：進了新陣營將領樹": move.get('進了G的將領樹') is True,
            "轉屬：離開舊陣營將領樹": move.get('離開M的將領樹') is True,
            "轉屬：新陣營番號沒撞號": move.get('番號沒撞號') is True,
            "韓復榘：番號改了": han.get('番號改了') is True,
            "韓復榘：改隸南京": han.get('招募後陣營') == 'N',
            "韓復榘：番號沒撞號": han.get('番號沒撞號') is True,
            "韓復榘：進了南京名冊": han.get('進了南京名冊') is True,
            "韓復榘：離開西北軍名冊": han.get('離開西北軍名冊') is True,
            "歸附：城市真的易主": absorb.get('城市全數易主') is True,
            "歸附：地格真的易主": absorb.get('地格全數易主') is True,
            "歸附：部隊全數改旗": absorb.get('部隊全數改旗') is True,
            "歸附：番號沒撞號": absorb.get('番號沒撞號') is True,
            "歸附：將領進了名冊": absorb.get('進了名冊') is True,
            "吞併：黔軍退出地圖": merge.get('黔軍還在地圖上') is False,
            "吞併：黔城改屬川軍": merge.get('黔城歸屬') == ['C'] * len(merge.get('黔城歸屬') or []),
            "吞併：黔地格改屬川軍": merge.get('黔地格歸屬') == ['C'] * len(merge.get('黔地格歸屬') or []),
        }
        print()
        failed = [n for n, ok in checks.items() if not ok]
        for name, ok in checks.items():
            print(f"  {'通過' if ok else '**沒過**'}  {name}")
        if results.get('__主控台錯誤__'):
            print("  **主控台有錯**", results['__主控台錯誤__'])
            failed.append('主控台有錯')
        print()
        print(f"{len(checks) - len(failed)}/{len(checks)} 通過")
        return 1 if failed else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
