# -*- coding: utf-8 -*-
"""開真前端，驗「存檔歸存檔、開局地圖歸開局地圖」這條界線。

病史（使用者連續兩次回報「地格歸屬又跑掉了」）：`applyTacticalSnapshot()`
先前是無條件把 `snapshot.cellFactions` 蓋到地圖上。開局地圖一改——省界、
省級歸屬保證、新增城市——**舊存檔就把整張地圖蓋回舊版本**，連玩家從來沒
打過的格子都一起倒退。實測使用者本機那兩份存檔（9/7 與 8/30）與乾淨新局
差 40 格，而且差的正好是批次 23 修掉的那批：川軍 52/64、西北軍 124/140、
馬家軍 75/69、直系 69/57。

現在存檔會連同「它是照哪一版開局地圖存的」一起寫（`openingMap`）：
  1. 版本一樣   → 照舊全套（同一局的多人同步走這條，行為必須完全不變）；
  2. 版本不一樣 → 先回到現在的開局地圖，只疊玩家真的打下來的格子；
  3. 沒有 openingMap（版本化之前的舊存檔）→ 地格歸屬整層不套，並且要出提示；
  4. 不管載入過什麼，按「重新開始」都要回到開局地圖，一格不差。

這裡量的是瀏覽器裡真的跑完 boot() 之後的 cells[]，不是讀 app.js。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8822'


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉它，否則量到的是舊伺服器")
    env = dict(os.environ)
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-save-map-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8822)'],
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
const opening = d.getOpeningCellFactions();
const revision = d.getOpeningMapRevision();
const liveMap = () => Object.fromEntries(Object.values(d.cells).map(c => [c.key, c.fac ?? null]));
const diffFromOpening = (map) => Object.keys(opening)
  .filter(k => (map[k] ?? null) !== (opening[k] ?? null));

// 一律走**真正的還原入口** applyTacticalSnapshot()，不要直接叫底下那支規則函式。
// 先前這裡是直接叫 applyCellFactionsFromSnapshot()，於是「把入口改回無條件全套」
// 的突變體整個看不到——測到的是規則本身，不是玩家會走的那條路。
//
// 呼叫前先把地圖弄髒（塗成一個開局與存檔都不會有的值）。不弄髒的話，
// 「版本對不上要先歸零回開局地圖」那一步是隱形的：地圖本來就已經是開局地圖了。
const DIRT = 'Q';
function restore(snapshot) {
  const dirtied = Object.keys(opening).slice(0, 60);
  for (const key of dirtied) if (d.cells[key]) d.cells[key].fac = DIRT;
  d.setUiNotice(null);
  d.applyTacticalSnapshot(snapshot);
  return { notice: d.getUiNotice(), dirtied };
}

out.開局地圖 = {
  格數: Object.keys(opening).length,
  版本: revision,
  版本會跟著地圖走: revision === d.hashCellFactions(opening)
    && revision !== d.hashCellFactions({ ...opening, '__fake__': 'X' }),
  'boot之後就等於開局地圖': diffFromOpening(liveMap()).length === 0,
};

// ---- 1. 重新套一次開局地圖，必須完全一樣（applyOpeningMap 只有一份定義）----
d.applyOpeningMap();
out.重跑開局 = { 差幾格: diffFromOpening(liveMap()).length };

// 挑三格屬於不同陣營、而且不是城市的地格當「玩家打下來的戰果」。
const spoils = Object.values(d.cells)
  .filter(c => c.land && !c.power && !c.city && c.fac)
  .slice(0, 3)
  .map(c => c.key);
const enemyOf = (fac) => (fac === 'F' ? 'N' : 'F');

// ---- 2. 版本一樣：照舊全套，多人同步不能被動到 ----
{
  d.applyOpeningMap();
  const snapshot = d.tacticalSnapshot();
  for (const key of spoils) snapshot.cellFactions[key] = enemyOf(opening[key]);
  const { notice } = restore(snapshot);
  const map = liveMap();
  out.同版本 = {
    // 用 ?. ——存檔沒帶 openingMap 時要報成「沒過」，不是讓整支腳本當掉。
    存檔版本: snapshot.openingMap?.revision ?? null,
    與目前一致: snapshot.openingMap?.revision === revision,
    戰果有套上: spoils.every(k => map[k] === enemyOf(opening[k])),
    其餘一格沒動: diffFromOpening(map).filter(k => !spoils.includes(k)).length === 0,
    有沒有提示: notice,
  };
}

// ---- 3. 版本不一樣：只疊玩家真的改過的格，其餘回到現在的開局地圖 ----
{
  d.applyOpeningMap();
  const snapshot = d.tacticalSnapshot();
  // 假裝這份存檔是照一版「舊地圖」存的：舊地圖有 12 格屬於別人，
  // 而玩家在那一局裡另外打下了 spoils 這三格。
  const stale = Object.keys(opening).filter(k => !spoils.includes(k)).slice(0, 12);
  const oldOpening = { ...opening };
  for (const key of stale) oldOpening[key] = enemyOf(opening[key]);
  for (const key of stale) snapshot.cellFactions[key] = oldOpening[key];
  for (const key of spoils) snapshot.cellFactions[key] = enemyOf(opening[key]);
  snapshot.openingMap = { revision: d.hashCellFactions(oldOpening), cells: oldOpening };

  const { notice, dirtied } = restore(snapshot);
  const map = liveMap();
  out.舊版本 = {
    弄髒的格子有沒有被歸零: dirtied
      .filter(k => !spoils.includes(k) && !stale.includes(k))
      .every(k => map[k] === opening[k]),
    '舊地圖那12格有沒有回到現在的開局': stale.every(k => map[k] === opening[k]),
    玩家打下來的三格有沒有保留: spoils.every(k => map[k] === enemyOf(opening[k])),
    被改動的格數: diffFromOpening(map).length,
    提示: notice,
    有提示: Boolean(notice),
  };
}

// ---- 4. 沒有 openingMap 的舊存檔：地格歸屬整層不套 ----
{
  d.applyOpeningMap();
  const snapshot = d.tacticalSnapshot();
  const stale = Object.keys(opening).slice(0, 40);
  for (const key of stale) snapshot.cellFactions[key] = enemyOf(opening[key]);
  delete snapshot.openingMap;

  const { notice } = restore(snapshot);
  const map = liveMap();
  out.沒有版本 = {
    地圖等於開局地圖: diffFromOpening(map).length === 0,
    提示: notice,
    有提示: Boolean(notice),
  };
}

// ---- 5. 不管載入過什麼，重新開始都要回到開局地圖 ----
{
  d.applyOpeningMap();
  const snapshot = d.tacticalSnapshot();
  for (const key of Object.keys(opening).slice(0, 40)) {
    snapshot.cellFactions[key] = enemyOf(opening[key]);
  }
  delete snapshot.openingMap;
  restore(snapshot);
  out.重新開始 = { 載入後與開局差幾格: diffFromOpening(liveMap()).length };
}
return out;
"""

RESET_PROBE = r"""
async () => {
  const d = window.__neDebug;
  const opening = d.getOpeningCellFactions();
  await d.resetGame();
  const map = Object.fromEntries(Object.values(d.cells).map(c => [c.key, c.fac ?? null]));
  const diff = Object.keys(opening).filter(k => (map[k] ?? null) !== (opening[k] ?? null));
  return { 重新開始之後與開局差幾格: diff.length, 差在哪幾格: diff.slice(0, 8) };
}
"""


async def main():
    proc = start_server()
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
            results['重開'] = await page.evaluate(RESET_PROBE)
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
    opening = r.get('開局地圖') or {}
    same = r.get('同版本') or {}
    stale = r.get('舊版本') or {}
    none_ = r.get('沒有版本') or {}
    reset = results.get('重開') or {}
    checks = {
        "驗得到東西（開局地圖不是空的）": (opening.get('格數') or 0) >= 800,
        "boot 之後的地圖就是開局地圖": opening.get('boot之後就等於開局地圖') is True,
        "地圖版本跟著地圖本身走（不是手寫版本號）": opening.get('版本會跟著地圖走') is True,
        "重跑 applyOpeningMap() 結果一模一樣": (r.get('重跑開局') or {}).get('差幾格') == 0,
        "同版本存檔：戰果照舊全部套上": same.get('戰果有套上') is True,
        "同版本存檔：其餘一格都沒被動到": same.get('其餘一格沒動') is True,
        "同版本存檔：不該有任何提示（多人同步是常態）": same.get('有沒有提示') is None,
        "存檔真的帶著開局地圖版本": same.get('與目前一致') is True,
        "舊版本存檔：舊地圖那批格子回到現在的開局":
            stale.get('舊地圖那12格有沒有回到現在的開局') is True,
        "舊版本存檔：玩家真的打下來的格子有保留":
            stale.get('玩家打下來的三格有沒有保留') is True,
        "舊版本存檔：只剩玩家那三格與開局不同": stale.get('被改動的格數') == 3,
        "舊版本存檔：呼叫前弄髒的格子都被歸零（真的有先回到開局地圖）":
            stale.get('弄髒的格子有沒有被歸零') is True,
        "舊版本存檔：有告訴玩家發生了什麼": stale.get('有提示') is True,
        "無版本舊存檔：地格歸屬整層不套，地圖等於開局":
            none_.get('地圖等於開局地圖') is True,
        "無版本舊存檔：有告訴玩家發生了什麼": none_.get('有提示') is True,
        "重新開始之後地圖回到開局配置，一格不差":
            reset.get('重新開始之後與開局差幾格') == 0,
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
