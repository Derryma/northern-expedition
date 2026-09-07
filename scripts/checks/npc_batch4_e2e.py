# -*- coding: utf-8 -*-
"""批次四的前端交接：換陣營＋移防、整批歸附、併吞，在真前端各跑一次。

後端算好的部分（誰換旗、哪些城轉屬）由 backend 測試守著。這裡只驗
前端那三個處理器真的有做事——尤其是移防：**只有前端有座標**，
後端只說「搬到張家口周邊一格」，格子是前端挑的。
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
const handlers = d.pendingEffectHandlers();

// ---- 1. 換陣營＋移防 ----
const ma = d.allArmies().find(a => a.generalId === 'ma_fuxiang');
out.馬福祥 = ma ? { 原本陣營: d.factionForArmy(ma), 原本位置: ma.cellKey } : null;
if (ma) {
  handlers.npc_general_transferred('F', {
    general: '馬福祥', general_id: 'ma_fuxiang',
    from_faction: 'M', to_faction: 'G',
    armies: [{ armyId: ma.id, units: { ...d.armyUnits(ma) } }],
    relocate: { near_city: 'zhangjiakou', within: 1 },
  });
  const zjk = (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === 'zhangjiakou');
  const home = Object.values(d.cells).find(c => c.city?.id === 'zhangjiakou');
  out.移防後 = {
    陣營: d.factionForArmy(ma), 位置: ma.cellKey,
    真的移動了: ma.cellKey !== out.馬福祥.原本位置,
    是張家口的鄰格: home ? d.cellNeighbors(home).some(c => c.key === ma.cellKey) : null,
    沒進城: !d.cells[ma.cellKey]?.city,
  };
}

// ---- 2. 整批歸附 ----
const maArmies = d.allArmies().filter(a => a.id.startsWith('M-'));
handlers.npc_faction_absorbed('F', {
  faction: 'M', owner: 'N', cities: ['xining'],
  armies: maArmies.map(a => ({ armyId: a.id, generalId: a.generalId })),
});
out.歸附後的馬家軍陣營 = maArmies.map(a => d.factionForArmy(a));

// ---- 3. 併吞 ----
const liu = d.allArmies().find(a => a.generalId === 'liu_xiang');
const qian = d.allArmies().find(a => a.id.startsWith('Q-'));
out.併吞前 = { 劉湘: { ...d.armyUnits(liu) }, 黔軍: { ...d.armyUnits(qian) } };
handlers.npc_faction_merged('F', {
  from_faction: 'Q', into_faction: 'C',
  into_general_id: 'liu_xiang', into_army_id: liu.id,
  units: { infantry: 42, cavalry: 0, machine_gun: 0, artillery: 3 },
  absorbed: [{ armyId: qian.id }], cities: ['guiyang', 'zunyi', 'anshun'],
});
out.併吞後 = {
  劉湘: { ...d.armyUnits(liu) },
  黔軍戰力: d.forcePoints(d.armyUnits(qian)),
  黔軍狀態: qian.status,
};
return out;
"""


async def main():
    proc = start_server()
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1500, 'height': 1000})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:300]))
        await page.goto(BASE + '/', wait_until='networkidle')
        await page.wait_for_timeout(6000)
        results['結果'] = await page.evaluate("async () => {" + PROBE + "}")
        if errs:
            results['__主控台錯誤__'] = errs[:6]
        await page.close()
        await browser.close()
    proc.send_signal(signal.SIGKILL); proc.wait()
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))

asyncio.run(main())
