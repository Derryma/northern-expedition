# -*- coding: utf-8 -*-
"""開真前端，逐座港市檢查地形狀態與通行規則有沒有跟名冊對上。

這一輪要守的規定：
  1. 港市貼著哪片水域**只有後端那一份答案**（`city.waters`，來自
     `foreign_punishment.RIVER_PORTS` 與 `coastal_sea_name()`）。前端不再
     自己拿最近的河去猜——先前成都與襄陽就是這樣變成「地圖上是長江、
     後端不屬於任何水系」，封鎖的斜紋塗上去、結算卻跳過它們；
  2. 河港的地格是水域（`portWater`），河名等於後端給的水系；
  3. 河港地格陸軍走得過去（不必架浮橋），但**沒有城市的河道照樣攔得住**——
     沒有這條對照組，上一關等於沒驗；
  4. 海港的地格仍是陸地、不是河道，而且至少貼著一格近海，艦隊進得來；
  5. 每一座港市的地格艦隊都進得去（`navyCanEnterCell`）。

讀 app.js 不算數：這裡量的是瀏覽器裡真的跑完 boot() 之後的 cells[] 與
真正的判定函式。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8819'
SHOTS = _pathlib.Path(REPO) / '_shots'


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉它，否則量到的是舊伺服器")
    env = dict(os.environ)
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-port-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8819)'],
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
const cities = d.getBootstrap().strategic_map.cities;
const ports = cities.filter(c => c.port);

// ---- 1. 水域只有後端那一份 ----
const noWater = [];
const nameMismatch = [];
const notWater = [];
const brokenSea = [];
const sealess = [];
const navyLockedOut = [];
for (const city of ports) {
  const cell = d.cells[city.cellKey];
  const waters = city.waters || [];
  if (!waters.length) { noWater.push(city.name); continue; }
  if (city.port === 'river') {
    if (!cell.portWater) notWater.push(city.name);
    if (cell.river !== waters[0]) nameMismatch.push(city.name + ':地圖' + cell.river + '/後端' + waters[0]);
  }
  if (city.port === 'sea') {
    if (cell.river) brokenSea.push(city.name + ' 的地格被標成河道 ' + cell.river);
    if (cell.land === false) brokenSea.push(city.name + ' 的地格不是陸地');
    if (!d.cellNeighbors(cell).some(n => n.coastalWater)) sealess.push(city.name);
  }
  if (!d.navyCanEnterCell(cell)) navyLockedOut.push(city.name);
}
out.水域 = {
  港市數: ports.length,
  河港數: ports.filter(c => c.port === 'river').length,
  海港數: ports.filter(c => c.port === 'sea').length,
  沒有水域的: noWater,
  河名對不上的: nameMismatch,
  河港地格不是水域的: notWater,
  海港地格被弄壞的: brokenSea,
  海港沒貼著海的: sealess,
  艦隊進不去的: navyLockedOut,
};

// ---- 2. 通行規則：河港放行、光禿禿的河道攔得住 ----
// riverStepAllowed(from, to) 是陸軍過河的判定入口。
const blockedRiverPorts = [];
for (const city of ports) {
  if (city.port !== 'river') continue;
  const cell = d.cells[city.cellKey];
  const dry = d.cellNeighbors(cell).find(n => n.land !== false && !n.river && !n.power);
  if (!dry) continue;
  if (!d.riverStepAllowed(dry, cell, false)) blockedRiverPorts.push(city.name);
}
// 對照組：沒有城市、也沒有浮橋的河道格必須攔得住陸軍。
const plainRiverCells = Object.values(d.cells)
  .filter(c => c.river && !c.city && !c.coastalWater && !c.navalRoute);
const leakyPlainRivers = [];
for (const cell of plainRiverCells) {
  const dry = d.cellNeighbors(cell).find(n => n.land !== false && !n.river && !n.power);
  if (!dry) continue;
  if (d.riverStepAllowed(dry, cell, false)) leakyPlainRivers.push(cell.key);
}
out.通行 = {
  河港擋住陸軍的: blockedRiverPorts,
  沒有城市的河道格數: plainRiverCells.length,
  沒城市卻放行的河道: leakyPlainRivers.slice(0, 8),
  放行的河道格數: leakyPlainRivers.length,
};

// ---- 3. 這一輪改動的兩座港口 ----
const detail = {};
for (const id of ['huizhou', 'shashi']) {
  const city = cities.find(c => c.id === id);
  const cell = d.cells[city.cellKey];
  const dry = d.cellNeighbors(cell).find(n => n.land !== false && !n.river && !n.power);
  detail[city.name] = {
    港型: city.port,
    後端水域: city.waters,
    地格河名: cell.river,
    地格是水域: !!cell.portWater,
    地格是陸地: cell.land !== false,
    貼著幾格近海: d.cellNeighbors(cell).filter(n => n.coastalWater).length,
    貼著幾格同名水系: d.cellNeighbors(cell).filter(n => n.river === (city.waters || [])[0]).length,
    艦隊進得去: d.navyCanEnterCell(cell),
    陸軍走得過去: dry ? d.riverStepAllowed(dry, cell, false) : null,
  };
}
out.新港 = detail;

// ---- 4. 地格資訊面板真的印得出港型 ----
const tags = {};
for (const id of ['huizhou', 'shashi']) {
  const city = cities.find(c => c.id === id);
  d.selectTile(d.cells[city.cellKey]);
  const text = document.body.innerText;
  tags[city.name] = {
    有海港字樣: text.includes('海港'),
    有河港字樣: text.includes('河港'),
    有城市名: text.includes(city.name),
  };
}
out.地格資訊 = tags;

// ---- 4b. 自貢一度做成河港，使用者改回普通陸地城市 ----
// 只把名冊裡的 "port" 拿掉、卻忘了地格還留著水域狀態的話，這裡會抓到。
{
  const zg = cities.find(c => c.id === 'zigong');
  const cell = d.cells[zg.cellKey];
  out.自貢 = {
    有沒有港口: zg.port || null,
    有沒有水域: zg.waters || null,
    地格是水域: !!cell.portWater,
    地格河名: cell.river,
    地格是陸地: cell.land !== false,
    艦隊進得去: d.navyCanEnterCell(cell),
  };
}

// ---- 5. 名單漏掉時前端要大聲拒絕，不能悄悄補一個名字 ----
// 沒有這一關，`portWaterName()` 裡那個 throw 在資料完整時永遠跑不到，
// 把它改成「回傳內河」的突變體就與原始碼等價，誰都驗不出來。
let refused = null;
try {
  d.portWaterName({ id: '__fake__', name: '沒有水域的假港', port: 'river', waters: [] });
  refused = false;
} catch (err) {
  refused = true;
}
out.漏名單 = { 前端有沒有拒絕: refused };
return out;
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
            results['結果'] = await page.evaluate("(() => {" + PAGE_PROBE + "})()")
            if errs:
                results['__主控台錯誤__'] = errs[:5]
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
    water = r.get('水域') or {}
    passage = r.get('通行') or {}
    new = r.get('新港') or {}
    tags = r.get('地格資訊') or {}
    hui = new.get('惠州') or {}
    sha = new.get('沙市') or {}
    zi = r.get('自貢') or {}
    checks = {
        "驗得到東西（港市數量對得上）": (water.get('港市數') or 0) >= 30
            and (water.get('河港數') or 0) >= 20 and (water.get('海港數') or 0) >= 10,
        "每一座港市都問得出水域": water.get('沒有水域的') == [],
        "河港的河名等於後端給的水系": water.get('河名對不上的') == [],
        "河港的地格是水域": water.get('河港地格不是水域的') == [],
        "海港的地格仍是陸地、不是河道": water.get('海港地格被弄壞的') == [],
        "海港都貼著近海": water.get('海港沒貼著海的') == [],
        "每一座港市艦隊都進得去": water.get('艦隊進不去的') == [],
        "河港放陸軍通行（不必架浮橋）": passage.get('河港擋住陸軍的') == [],
        "對照組：沒有城市的河道有東西可驗": (passage.get('沒有城市的河道格數') or 0) >= 20,
        "對照組：沒有城市的河道照樣攔得住陸軍": passage.get('放行的河道格數') == 0,
        "惠州是海港、水域是南海": hui.get('港型') == 'sea' and hui.get('後端水域') == ['南海'],
        "惠州的地格仍是陸地、且貼著海": hui.get('地格是陸地') is True
            and (hui.get('貼著幾格近海') or 0) >= 1 and hui.get('地格河名') in (None, ''),
        "惠州艦隊停得進去": hui.get('艦隊進得去') is True,
        "沙市是河港、水域是長江": sha.get('港型') == 'river' and sha.get('後端水域') == ['長江'],
        "沙市的地格變成長江水域": sha.get('地格是水域') is True and sha.get('地格河名') == '長江',
        "沙市接得上長江（鄰格有同一條河）": (sha.get('貼著幾格同名水系') or 0) >= 1,
        "沙市陸軍走得過去、艦隊也進得去":
            sha.get('陸軍走得過去') is True and sha.get('艦隊進得去') is True,
        "自貢是普通陸地城市（沒有港口、沒有水域）":
            zi.get('有沒有港口') is None and not zi.get('有沒有水域'),
        "自貢的地格是陸地、不是水域":
            zi.get('地格是水域') is False and zi.get('地格是陸地') is True
            and zi.get('地格河名') in (None, ''),
        "自貢艦隊進不去（它不再是港口）": zi.get('艦隊進得去') is False,
        "惠州的地格資訊印得出海港": (tags.get('惠州') or {}).get('有海港字樣') is True,
        "沙市的地格資訊印得出河港": (tags.get('沙市') or {}).get('有河港字樣') is True,
        "名單漏掉時前端會大聲拒絕（不會悄悄補一個河名）":
            (r.get('漏名單') or {}).get('前端有沒有拒絕') is True,
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
