# -*- coding: utf-8 -*-
"""15.8 劉湘防區擴軍：在真前端跑完整條路，看地圖上的部隊編制真的變了沒。

證明的不是「後端算得對」（那由 backend 測試守著），而是「後端算完之後，
畫面上那支部隊真的多了兩營步兵一營騎兵」——中間那段 pending_frontend_effects
的交接是這裡唯一要驗的東西。
"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8766'


def start_server():
    proc = subprocess.Popen(['python3', '-m', 'backend.server'],
                            cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    return proc


SCRIPT = r"""
const d = window.__neDebug;
const out = {};

// ---- 1. 地圖上找得到劉湘的部隊嗎 ----
const liu = d.allArmies().find(a => a.generalId === 'liu_xiang');
if (!liu) return { __錯誤__: '地圖上沒有劉湘的部隊' };
out.部隊 = { id: liu.id, 番號: liu.designator, 將領: liu.general };
out.補兵前 = { ...d.armyUnits(liu) };
// 對照組：這張卡沒點名的 NPC 部隊。它若也變多，那是每回合例行補兵，不是這張卡。
out.對照組補兵前 = Object.fromEntries(d.allArmies()
  .filter(a => ['yang_sen','liu_wenhui','feng_yuxiang'].includes(a.generalId))
  .map(a => [a.generalId, { ...d.armyUnits(a) }]));

// ---- 2. 把這張卡塞進牌堆，讓伺服器手上也有同一份戰術狀態 ----
await d.publishSharedState(true);
const shared = await d.api('/api/shared-state', {
  tactical: d.tacticalSnapshot(), expected_revision: null,
});
const snap = JSON.parse(JSON.stringify(shared.engine_state));
snap.event_pool = ['liu_xiang_expands'];
snap.turn = 2;
for (const code of Object.keys(snap.players)) snap.players[code].treasury = 500;
await d.api('/api/restore-shared-state', {
  engine_state: snap, tactical: d.tacticalSnapshot(),
});

// ---- 3. 真的走一次「下一回合」，把報紙讀出來 ----
const result = await d.api('/api/next-turn', {
  active_player: d.getCurrentPlayer(), force: true,
});
out.抽到的卡 = result.turn?.events?.[0]?.card_id
  || result.state?.pending_events?.cards?.[0]?.card_id;
out.等回應 = !!result.turn?.awaiting_events;
return out;
"""

RESPOND = r"""
const d = window.__neDebug;
const out = { 回應了: [] };
// 四家依序把報紙讀完；respondToEvent 走的就是玩家按下去的那條路，
// 裡面會呼叫 consumePendingFrontendEffects()。
for (let i = 0; i < 8; i += 1) {
  const view = d.pendingEventState();
  const waiting = view?.waiting_for || view?.drawer;
  if (!waiting) break;
  if (waiting !== d.getCurrentPlayer()) d.switchFaction(waiting);
  await d.respondToEvent(null);
  out.回應了.push(waiting);
  await new Promise(r => setTimeout(r, 250));
}
const liu = d.allArmies().find(a => a.generalId === 'liu_xiang');
out.補兵後 = liu ? { ...d.armyUnits(liu) } : null;
out.對照組補兵後 = Object.fromEntries(d.allArmies()
  .filter(a => ['yang_sen','liu_wenhui','feng_yuxiang'].includes(a.generalId))
  .map(a => [a.generalId, { ...d.armyUnits(a) }]));
out.本回合 = d.getState().turn;
out.佇列還剩 = Object.values(d.getState().players || {})
  .flatMap(p => p.pending_frontend_effects || [])
  .filter(e => e.kind === 'npc_army_units').length;
return out;
"""


async def main():
    proc = start_server()
    results = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1500, 'height': 1000})
        errs, warns = [], []
        page.on('pageerror', lambda e: errs.append(str(e)[:200]))
        page.on('console', lambda m: warns.append(m.text[:200])
                if m.type in ('error', 'warning') else None)
        await page.goto(BASE + '/', wait_until='networkidle')
        await page.wait_for_timeout(6000)
        results['一_設局'] = await page.evaluate("async () => {" + SCRIPT + "}")
        await page.wait_for_timeout(1200)
        results['二_讀報與結算'] = await page.evaluate("async () => {" + RESPOND + "}")
        if errs:
            results['__主控台錯誤__'] = errs[:6]
        bad = [w for w in warns if 'pending_frontend_effects' in w]
        if bad:
            results['__沒人消費的效果__'] = bad[:4]
        await page.close()
        await browser.close()
    proc.send_signal(signal.SIGKILL); proc.wait()
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))

asyncio.run(main())
