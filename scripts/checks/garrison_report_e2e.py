# -*- coding: utf-8 -*-
"""前端的駐軍回報：在真前端跑一次，看它報出來的是不是真的。

這份報告是**事實**（哪座城站著誰的幾營），規則（南京有兵才發南京事件）在後端。
所以這裡要驗的只有兩件事：報出來的城市真的有那些兵，以及它真的被送給了後端。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, signal, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8766'


def start_server():
        # 驗證一律用自己的存檔目錄：不然每次起伺服器都會接續玩家上一盤，
    # 檢查會變成空轉，而且會把玩家的存檔覆蓋掉。
    env = {**os.environ, 'NE_GAME_DATA_DIR': tempfile.mkdtemp(prefix='ne-check-')}
    proc = subprocess.Popen(['python3', '-m', 'backend.server'], cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    return proc


PROBE = r"""
const d = window.__neDebug;
const out = {};
const report = d.cityGarrisonReport();
out.回報的城市數 = Object.keys(report).length;
out.抽樣 = Object.fromEntries(Object.entries(report).slice(0, 6));

// 自己重數一次對照：站在城格上的部隊，照陣營加總營數。
const recount = {};
for (const army of d.allArmies()) {
  if (["jailed", "killed", "destroyed"].includes(army.status)) continue;
  const city = d.cityForArmy(army);
  if (!city) continue;
  const faction = d.factionForArmy(army);
  const n = Object.values(d.armyUnits(army)).reduce((s, c) => s + Number(c || 0), 0);
  if (n <= 0) continue;
  recount[city.id] = recount[city.id] || {};
  recount[city.id][faction] = (recount[city.id][faction] || 0) + n;
}
out.與獨立重數一致 = JSON.stringify(report) === JSON.stringify(recount);

// 空城不該出現在報告裡
out.有沒有空城混進來 = Object.entries(report)
  .filter(([, byFaction]) => !Object.values(byFaction).some(n => n > 0))
  .map(([id]) => id);
return out;
"""


async def main():
    proc = start_server()
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1500, 'height': 1000})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:200]))
        sent = []
        page.on('request', lambda r: sent.append(r.post_data or '')
                if r.url.endswith('/api/next-turn') else None)
        await page.goto(BASE + '/', wait_until='networkidle')
        await page.wait_for_timeout(6000)
        results['一_回報內容'] = await page.evaluate("async () => {" + PROBE + "}")
        # 「強制下一回合」那顆鈕平常是 hidden 的，直接叫它的 click。
        await page.evaluate("document.getElementById('debugForceTurnBtn').click()")
        await page.wait_for_timeout(5000)
        payloads = [json.loads(body) for body in sent if body]
        results['二_真的送給後端了'] = any('city_garrison_report' in p for p in payloads)
        results['二_送出的內容'] = next((p['city_garrison_report'] for p in payloads
                                  if 'city_garrison_report' in p), None)
        if errs:
            results['__主控台錯誤__'] = errs[:6]
        await page.close()
        await browser.close()
    proc.send_signal(signal.SIGKILL); proc.wait()
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))

asyncio.run(main())
