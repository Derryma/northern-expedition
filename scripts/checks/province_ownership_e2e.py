# -*- coding: utf-8 -*-
"""開真前端，逐格檢查省界與省級歸屬保證有沒有真的落地。

這一輪要守的規定：
  1. 四川全境屬川軍，唯獨川東（巫山、奉節一帶）留給直系；
  2. 陝西南部與甘肅東南——西北軍與川軍接壤的那一段——屬西北軍，川軍不得有飛地；
  3. 察哈爾長城以北的定居區屬西北軍，多倫以北的錫林郭勒草原仍是奉系的；
  4. 青海已從甘肅切出來，整片在馬家軍手上，而西寧仍留在甘肅；
  5. 西北軍四個軍分駐歸綏、張家口、潼關、西安。

讀 map.js 或 geojson 不算數：這裡量的是瀏覽器裡真的跑完 boot() 之後的
cells[].fac，以及推上後端之後 cellFactions 有沒有跟著。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8772'
SHOTS = _pathlib.Path(REPO) / '_shots'


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉它，否則量到的是舊伺服器")
    import os
    env = dict(os.environ)
    # 驗證一律用自己的存檔目錄，不碰玩家的 game_data。
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-check-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8772)'],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("伺服器啟動失敗")
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("伺服器起不來")


PAGE_PROBE = r"""
const d = window.__neDebug;
const out = {};

const land = Object.values(d.cells).filter(c => c.land && !c.power);
const byProvince = {};
for (const cell of land) {
  const key = cell.province || '(不在任何省分)';
  (byProvince[key] = byProvince[key] || []).push(cell);
}
const tally = (list) => {
  const counts = {};
  for (const cell of list) counts[cell.fac || '(無主)'] = (counts[cell.fac || '(無主)'] || 0) + 1;
  return counts;
};

out.省份歸屬 = Object.fromEntries(
  Object.entries(byProvince).sort().map(([name, list]) => [name, tally(list)]));

// ---- 1. 四川 ----
{
  const sichuan = byProvince['四川'] || [];
  const notChuan = sichuan.filter(c => c.fac !== 'C');
  out.四川 = {
    總格數: sichuan.length,
    川軍格數: sichuan.filter(c => c.fac === 'C').length,
    非川軍的格: notChuan.map(c => ({ 陣營: c.fac, lon: +c.lon.toFixed(2), lat: +c.lat.toFixed(2) })),
    非川軍的都是直系: notChuan.length > 0 && notChuan.every(c => c.fac === 'W'),
    非川軍的都在川東: notChuan.every(c => c.lon >= 108.0),
  };
}

// ---- 2. 陝西、甘肅境內不得再有川軍 ----
out.秦嶺以北沒有川軍 = {
  陝西的川軍格: (byProvince['陝西'] || []).filter(c => c.fac === 'C').length,
  甘肅的川軍格: (byProvince['甘肅'] || []).filter(c => c.fac === 'C').length,
  陝西的西北軍格: (byProvince['陝西'] || []).filter(c => c.fac === 'G').length,
};

// ---- 3. 察哈爾：長城以北定居區歸西北軍，多倫以北的草原不准被順手收走 ----
{
  const chahar = byProvince['察哈爾'] || [];
  const settled = chahar.filter(c => c.lat <= 42.4);
  const steppe = chahar.filter(c => c.lat > 42.4);
  // 草原那一段的比對基準是 factionAt()——也就是還沒套用省級歸屬保證之前的歸屬。
  // 拿它比，才不必在測試裡再寫死一個「奉系應該有幾格」的數字。
  const untouched = (c) => {
    const before = d.factionAt(c.lon, c.lat);
    return before === null || before === c.fac;
  };
  // 別家城市腳下的那一格條款收不走（大同就在察哈爾境內），所以那些格子不算例外。
  const homes = d.cityHomeCells();
  const guarded = (c) => homes.has(c.key) && homes.get(c.key) !== 'G';
  out.察哈爾 = {
    定居區格數: settled.length,
    定居區全歸西北軍: settled.length > 0
      && settled.every(c => c.fac === 'G' || guarded(c)),
    護欄擋下的格: settled.filter(guarded)
      .map(c => ({ 陣營: c.fac, 護著哪一家的城: homes.get(c.key),
                   lon: +c.lon.toFixed(2), lat: +c.lat.toFixed(2) })),
    定居區裡的例外: settled.filter(c => c.fac !== 'G' && !guarded(c))
      .map(c => ({ 陣營: c.fac, lon: +c.lon.toFixed(2), lat: +c.lat.toFixed(2) })),
    草原格數: steppe.length,
    草原一格都沒被動到: steppe.length > 0 && steppe.every(untouched),
    草原上被動到的格: steppe.filter(c => !untouched(c))
      .map(c => ({ 原本: d.factionAt(c.lon, c.lat), 現在: c.fac,
                   lon: +c.lon.toFixed(2), lat: +c.lat.toFixed(2) })),
  };
}

// ---- 3b. 全圖回歸：只有條款與逐格例外表講到的格子可以變，其餘一格都不准動 ----
{
  const overrides = d.CELL_OWNERSHIP_OVERRIDES || {};
  const inScope = (c) => {
    if (Object.prototype.hasOwnProperty.call(overrides, c.key)) return true;
    const before = d.factionAt(c.lon, c.lat);
    if (c.province === '四川') return before !== 'W';
    if (c.province === '察哈爾') return c.lat <= 42.4;
    if (c.province === '陝西' || c.province === '甘肅') return before === 'C';
    return false;
  };
  const strays = land.filter((c) => {
    const before = d.factionAt(c.lon, c.lat);
    return before !== null && before !== c.fac && !inScope(c);
  });
  out.全圖回歸 = {
    條款外被動到的格數: strays.length,
    明細: strays.slice(0, 12).map(c => ({ 省: c.province, 原本: d.factionAt(c.lon, c.lat),
                                         現在: c.fac, lon: +c.lon.toFixed(2), lat: +c.lat.toFixed(2) })),
  };
}

// ---- 4. 青海 ----
{
  const qinghai = byProvince['青海'] || [];
  out.青海 = {
    格數: qinghai.length,
    全在馬家軍手上: qinghai.length > 0 && qinghai.every(c => c.fac === 'M'),
    西寧那一格屬於: d.provinceAt(101.77, 36.62),
    青海湖那一格屬於: d.provinceAt(100.20, 36.90),
    柴達木那一格屬於: d.provinceAt(97.40, 37.40),
    貴德那一格屬於: d.provinceAt(101.43, 36.04),
  };
}

// ---- 5. 西北軍四個軍的駐地 ----
{
  const wanted = { feng_yuxiang: '歸綏', song_zheyuan: '張家口', han_fuqu: '潼關', lu_zhonglin: '西安' };
  const armies = d.allArmies(true);
  const garrisons = {};
  let allRight = true;
  for (const [generalId, cityName] of Object.entries(wanted)) {
    const army = armies.find(a => a.generalId === generalId);
    const cell = army ? d.cells[army.cellKey] : null;
    const here = cell?.city?.name || '(不在城裡)';
    garrisons[d.generalById(generalId)?.name || generalId] = {
      應駐: cityName, 實際: here, 地格: army?.cellKey || null, 地格歸屬: cell?.fac || null,
    };
    if (here !== cityName || cell?.fac !== 'G') allRight = false;
  }
  out.西北軍駐防 = { 明細: garrisons, 四個軍都到位: allRight };
}

// ---- 5b. 城市落點 ----
// 城市平常是挑「和自己同陣營、又離名義座標最近」的地格落腳的。地格歸屬一動，
// 最近的同色格就可能換一個，城市於是在畫面上跳一格。名冊上釘了 cell_key 的
// 城市不參與這場搶格子，一定要在釘住的那一格上。
{
  const cities = d.getBootstrap().strategic_map.cities;
  const info = cities.map((city) => {
    const cell = d.cells[city.cellKey];
    return {
      名稱: city.name, 陣營: city.faction, 格: city.cellKey, 釘: city.cell_key || null,
      格歸屬: cell ? cell.fac : null,
      偏離度: cell
        ? +Math.hypot(cell.lon - city.lon, cell.lat - city.lat).toFixed(3)
        : null,
    };
  });
  const pinned = info.filter((c) => c.釘);
  const free = info.filter((c) => !c.釘);
  out.城市落點 = {
    釘選的: pinned,
    沒到釘選位置的: pinned.filter((c) => c.格 !== c.釘),
    // 一格的間距約 0.75°（東西）與 0.87°（南北），沒釘的城市超過 1.0° 一定是被擠開了。
    被擠開超過一格的: free.filter((c) => c.偏離度 === null || c.偏離度 > 1.0),
    站在別家顏色格上的: info.filter((c) => c.格歸屬 !== c.陣營),
    最偏的五座: info.slice().sort((a, b) => b.偏離度 - a.偏離度).slice(0, 5),
  };
}

// ---- 5c. 大同右下那一格劃給晉系 ----
// 這一格在直隸境內（蔚縣、淶源一帶），不屬於任何省級條款，靠逐格例外表指定。
// 鄰格是從大同實際落腳的那一格推算出來的，不是照抄例外表裡的字串——
// 格子網要是變了，這一關會先紅。
{
  const datong = d.getBootstrap().strategic_map.cities.find((c) => c.name === '大同');
  const cell = datong ? d.cells[datong.cellKey] : null;
  // boot() 半路炸掉時 cellKey 會是 undefined。這裡不要跟著爆——爆了整份量測就
  // 只剩一行 TypeError，看不出是哪一關壞的。
  if (!cell) {
    out.大同右下 = { 大同的格: null, 右下那一格: null, 歸屬: null, 備註: '大同沒有落點，開局多半炸了' };
  } else {
    const rows = cell.c % 2 ? [cell.r, cell.r + 1] : [cell.r - 1, cell.r];
    const key = `${cell.c + 1},${rows[1]}`;
    const target = d.cells[key];
    out.大同右下 = {
      大同的格: cell.key, 右下那一格: key, 歸屬: target ? target.fac : null,
      經度: target ? +target.lon.toFixed(2) : null,
      緯度: target ? +target.lat.toFixed(2) : null,
    };
  }
}

// ---- 5c-2. 逐格例外表本身 ----
// 這張表是繞過所有條款與護欄的後門，所以它有幾格、是哪幾格，都要盯著。
out.逐格例外 = {
  表裡有哪幾格: Object.keys(d.CELL_OWNERSHIP_OVERRIDES || {}),
  逐格結果: Object.fromEntries(Object.entries(d.CELL_OWNERSHIP_OVERRIDES || {})
    .map(([key, faction]) => [key, { 應為: faction, 實際: d.cells[key]?.fac ?? null }])),
};

// ---- 5d. 駐軍要跟著城市走 ----
// 城市換格之後，起始部隊如果沒跟著，就會落在離城好幾格的空地上。
// 楊森例外：他在名冊上就有指定的起始地格（重慶只有一格，他被指到萬縣）。
{
  const cities = new Map(d.getBootstrap().strategic_map.cities.map((c) => [c.id, c]));
  const neighbourKeys = (c) => {
    const rows = c.c % 2 ? [c.r, c.r + 1] : [c.r - 1, c.r];
    return [`${c.c},${c.r - 1}`, `${c.c},${c.r + 1}`,
            `${c.c - 1},${rows[0]}`, `${c.c - 1},${rows[1]}`,
            `${c.c + 1},${rows[0]}`, `${c.c + 1},${rows[1]}`];
  };
  const strays = [];
  let checked = 0;
  for (const list of Object.values(d.ARMY_POSITIONS)) {
    for (const spec of list) {
      if (spec.startCellKey) continue;          // 名冊上自己指定了落點的不算
      const army = d.allArmies(true).find((a) => a.id === spec.id);
      const home = cities.get(spec.startCityId);
      const homeCell = home ? d.cells[home.cellKey] : null;
      const at = army ? d.cells[army.cellKey] : null;
      if (!at || !homeCell) { strays.push({ 部隊: spec.id, 問題: '找不到格子' }); continue; }
      checked += 1;
      if (at.key === homeCell.key || neighbourKeys(homeCell).includes(at.key)) continue;
      strays.push({ 部隊: spec.id, 將領: spec.general, 城市: home.name,
                    城市格: homeCell.key, 部隊格: at.key,
                    距離: +Math.hypot(at.lon - homeCell.lon, at.lat - homeCell.lat).toFixed(2) });
    }
  }
  out.駐軍跟著城市 = { 檢查了幾支: checked, 沒跟上的: strays };
}

// ---- 6. 推上後端之後，後端手上的地格歸屬要和畫面一致 ----
{
  await d.publishSharedState(true);
  const shared = await d.api('/api/shared-state');
  const remote = shared.tactical?.cellFactions || {};
  const mismatched = [];
  for (const cell of land) {
    if ((remote[cell.key] || null) !== (cell.fac || null)) {
      mismatched.push({ 格: cell.key, 前端: cell.fac, 後端: remote[cell.key] ?? null });
    }
  }
  out.後端同一份地圖 = {
    後端收到的格數: Object.keys(remote).length,
    前端陸地格數: land.length,
    對不上的格: mismatched.slice(0, 10),
    完全一致: mismatched.length === 0,
  };
}
"""


# 按「重新開始」之後，地圖必須還是同一張。
#
# 先前 resetGame() 把 cell.fac 寫回一份 module-load 時抓的快照，而省級歸屬保證
# （四川全境、察哈爾、陝甘飛地、青海）是 boot() 裡才套的——快照比它早。
# 於是按一次新局，那整套條款就被抹掉：川軍 64→52、西北軍 140→124、
# 馬家軍 69→75。部隊照樣重新入城，所以症狀是「駐軍變了、地格沒變」。
NEW_GAME_KEEPS_THE_MAP = r"""
async () => {
  const d = window.__neDebug;
  const count = () => {
    const out = {};
    for (const c of Object.values(d.cells)) { if (!c.land) continue;
      out[c.fac ?? 'null'] = (out[c.fac ?? 'null'] || 0) + 1; }
    return out;
  };
  const before = count();
  await d.resetGame();
  await new Promise(r => setTimeout(r, 1500));
  return { 新局前: before, 新局後: count() };
}
"""

# 整省沒有半座城市的省份（青海：西寧照舊民國地圖歸甘肅），
# 地格資訊也要說得出它是哪一省。
PROVINCE_WITHOUT_A_CITY = r"""
() => {
  const d = window.__neDebug;
  const read = (lon, lat) => { const c = d.cellAt(lon, lat);
    return c ? { 幾何: c.province, 顯示: d.strategicProvinceForCell(c) } : null; };
  const hasCity = (name) => (d.getBootstrap().strategic_map?.cities || [])
    .some(city => city.province === name);
  return { 青海湖: read(100.2, 36.9), 都蘭: read(98.1, 36.3),
           西寧一帶: read(101.8, 36.6),
           青海有沒有城市: hasCity('青海'), 甘肅有沒有城市: hasCity('甘肅') };
}
"""


# 省級歸屬保證是**開局的一次性播種**，不是每次重畫都跑一遍的規則。
# 跑第二次就會把玩家打下來的地盤還給原主，所以這一關驗兩件事：
#   1. 佔領之後，經過推回後端／拉回來／換回合／重畫，歸屬還是佔領者的；
#   2. 地格本身的屬性（省份、鐵路、河流、城市、租借地）一格都沒被弄壞。
CAPTURE_KEEPS_OWNERSHIP = r"""
async () => {
  const d = window.__neDebug;
  await d.switchFaction('N');
  await new Promise(r => setTimeout(r, 1200));
  const me = d.getCurrentPlayer();

  // 挑一格「省級歸屬保證管到、而且現在不是我的」的地：四川境內的川軍地。
  const target = Object.values(d.cells).find(c =>
    c.land && c.fac === 'C' && c.province === '四川' && !c.city && !c.power);
  const neighbourBefore = Object.values(d.cells)
    .filter(c => c.land && c.province === '四川' && c.key !== target.key)
    .map(c => [c.key, c.fac]);
  const attrsOf = (c) => ({ province: c.province, river: c.river ?? null,
    city: c.city?.id ?? null, power: c.power ?? null,
    rail: [...(c.railroads || [])].sort(), land: c.land === true });
  const attrsBefore = Object.fromEntries(
    Object.values(d.cells).filter(c => c.land).map(c => [c.key, JSON.stringify(attrsOf(c))]));

  // 真的佔下來（occupyTile 是移動與艦隊佔城共用的那一支）。
  await d.occupyTile(target, me);
  const rightAfter = d.cells[target.key].fac;

  // 接著把所有「可能重畫地圖」的路徑都走一遍。
  await d.publishSharedState(true);
  await d.pullSharedState();
  await d.api('/api/next-turn', { active_player: me, force: true });
  await d.pullSharedState();
  d.initMap();

  const neighbourAfter = Object.values(d.cells)
    .filter(c => c.land && c.province === '四川' && c.key !== target.key)
    .map(c => [c.key, c.fac]);
  const attrsAfter = Object.fromEntries(
    Object.values(d.cells).filter(c => c.land).map(c => [c.key, JSON.stringify(attrsOf(c))]));
  const brokenAttrs = Object.keys(attrsBefore)
    .filter(k => attrsBefore[k] !== attrsAfter[k]).slice(0, 5);

  return {
    佔的那一格: target.key,
    佔領當下: rightAfter,
    走完一輪之後: d.cells[target.key].fac,
    四川其餘地格有沒有被動到:
      JSON.stringify(neighbourBefore) === JSON.stringify(neighbourAfter),
    地格屬性被弄壞的: brokenAttrs,
    後端那份地圖同一格是誰的:
      (await d.api('/api/shared-state')).tactical?.cellFactions?.[target.key] ?? null,
  };
}
"""

# 城市易主之後，城市歸屬與後端的 city_owners 要一起動。
CITY_CAPTURE_FOLLOWS = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const city = (d.getBootstrap().strategic_map?.cities || []).find(c =>
    c.faction && c.faction !== me && d.cells[c.cellKey] && !d.cells[c.cellKey].power);
  const cell = d.cells[city.cellKey];
  const before = { 城: city.id, 原主: city.faction, 地格: cell.fac };
  await d.occupyTile(cell, me);
  await new Promise(r => setTimeout(r, 1200));
  await d.publishSharedState(true);
  await d.pullSharedState();
  const st = d.getState();
  return {
    ...before,
    佔領後的地格: d.cells[city.cellKey].fac,
    佔領後的城市歸屬: city.faction,
    後端city_owners: (st.city_owners || {})[city.id] ?? null,
    後端有沒有把它算進我的產出:
      Object.values(st.players || {}).some(p =>
        (p.city_economy || []).some(c => c.id === city.id)) ,
    我的產出裡有沒有它:
      ((st.players || {})[me]?.city_economy || []).some(c => c.id === city.id),
  };
}
"""


async def main():
    proc = start_server()
    SHOTS.mkdir(exist_ok=True)
    results = {}
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 1500, 'height': 950})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)[:200]))
            await page.goto(BASE + '/', wait_until='networkidle')
            await page.wait_for_timeout(7000)
            results['結果'] = await page.evaluate("async () => {" + PAGE_PROBE + "\nreturn out; }")
            results['新局'] = await page.evaluate(NEW_GAME_KEEPS_THE_MAP)
            results['沒有城市的省份'] = await page.evaluate(PROVINCE_WITHOUT_A_CITY)
            results['佔領之後'] = await page.evaluate(CAPTURE_KEEPS_OWNERSHIP)
            results['城市易主'] = await page.evaluate(CITY_CAPTURE_FOLLOWS)
            if errs:
                results['__主控台錯誤__'] = errs[:5]
            await page.screenshot(path=str(SHOTS / 'province_ownership_map.png'))
            await page.close()
            await browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()

    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    r = results.get('結果') or {}
    reset = results.get('新局') or {}
    cap = results.get('佔領之後') or {}
    citycap = results.get('城市易主') or {}
    nocity = results.get('沒有城市的省份') or {}
    checks = {
        "佔領：當下那一格就換人了": cap.get('佔領當下') is not None
            and cap.get('佔領當下') == cap.get('走完一輪之後'),
        "佔領：推回後端、換回合、重畫之後歸屬沒有被還回去":
            cap.get('走完一輪之後') is not None
            and cap.get('走完一輪之後') == cap.get('後端那份地圖同一格是誰的'),
        "佔領：同省其他地格一格都沒被動到":
            cap.get('四川其餘地格有沒有被動到') is True,
        "佔領：地格屬性（省份／鐵路／河流／城市／租借地）沒被弄壞":
            (cap.get('地格屬性被弄壞的') or []) == [],
        "城市易主：地格與城市歸屬一起動":
            citycap.get('佔領後的地格') == citycap.get('佔領後的城市歸屬')
            and citycap.get('佔領後的城市歸屬') != citycap.get('原主'),
        "城市易主：後端的 city_owners 跟著改":
            citycap.get('後端city_owners') == citycap.get('佔領後的城市歸屬'),
        "城市易主：後端把它算進新主人的產出": citycap.get('我的產出裡有沒有它') is True,
        "新局之後地圖還是同一張（省級歸屬保證沒被抹掉）":
            bool(reset.get('新局前')) and reset.get('新局前') == reset.get('新局後'),
        "青海整省沒有城市（不然下面兩關驗不到東西）":
            nocity.get('青海有沒有城市') is False and nocity.get('甘肅有沒有城市') is True,
        "青海境內的地格說得出自己在青海":
            (nocity.get('青海湖') or {}).get('顯示') == '青海'
            and (nocity.get('都蘭') or {}).get('顯示') == '青海',
        "西寧一帶仍然報甘肅（省界沒有被畫走）":
            (nocity.get('西寧一帶') or {}).get('顯示') == '甘肅',
        "四川全境歸川軍（川東除外）": (r.get('四川') or {}).get('非川軍的都是直系'),
        "四川的例外只在川東": (r.get('四川') or {}).get('非川軍的都在川東'),
        "陝西境內沒有川軍飛地": (r.get('秦嶺以北沒有川軍') or {}).get('陝西的川軍格') == 0,
        "甘肅境內沒有川軍飛地": (r.get('秦嶺以北沒有川軍') or {}).get('甘肅的川軍格') == 0,
        "察哈爾定居區全歸西北軍": (r.get('察哈爾') or {}).get('定居區全歸西北軍'),
        "錫林郭勒草原一格都沒被動到": (r.get('察哈爾') or {}).get('草原一格都沒被動到'),
        "條款與例外表以外全圖一格都沒動": (r.get('全圖回歸') or {}).get('條款外被動到的格數') == 0,
        "逐格例外表只有講好的那幾格": sorted(((r.get('逐格例外') or {}).get('表裡有哪幾格') or [])) == ['25,15'],
        "青海整片在馬家軍手上": (r.get('青海') or {}).get('全在馬家軍手上'),
        "青海不是空的": ((r.get('青海') or {}).get('格數') or 0) >= 25,
        "西寧仍在甘肅": (r.get('青海') or {}).get('西寧那一格屬於') == '甘肅',
        "青海湖在青海": (r.get('青海') or {}).get('青海湖那一格屬於') == '青海',
        "貴德仍在甘肅": (r.get('青海') or {}).get('貴德那一格屬於') == '甘肅',
        "西北軍四個軍各就各位": (r.get('西北軍駐防') or {}).get('四個軍都到位'),
        "釘選的城市都在釘住的那一格": (r.get('城市落點') or {}).get('沒到釘選位置的') == [],
        "沒釘的城市沒被擠開超過一格": (r.get('城市落點') or {}).get('被擠開超過一格的') == [],
        "每座城市都站在自家顏色的格上": (r.get('城市落點') or {}).get('站在別家顏色格上的') == [],
        "大同右下那一格是晉系": (r.get('大同右下') or {}).get('歸屬') == 'Y',
        "駐軍都跟著自己的城市": (r.get('駐軍跟著城市') or {}).get('沒跟上的') == [],
        "駐軍檢查真的有跑到": ((r.get('駐軍跟著城市') or {}).get('檢查了幾支') or 0) >= 25,
        "後端拿到的是同一份地圖": (r.get('後端同一份地圖') or {}).get('完全一致'),
    }
    print()
    for name, ok in checks.items():
        print(f"  {'通過' if ok else '**沒過**'}  {name}")
    if results.get('__主控台錯誤__'):
        print("  **主控台有錯**", results['__主控台錯誤__'])
    failed = [n for n, ok in checks.items() if not ok]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if (failed or results.get('__主控台錯誤__')) else 0


sys.exit(asyncio.run(main()))
