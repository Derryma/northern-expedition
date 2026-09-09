# -*- coding: utf-8 -*-
"""紅槍會起義與美孚石油：在真前端各走一次，看畫面上真的動了沒。

後端算得對由 backend 測試守著。這裡驗的是「打出去之後，玩家看得到的東西變了」。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, signal, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8775'


def start_server():
        # 驗證一律用自己的存檔目錄：不然每次起伺服器都會接續玩家上一盤，
    # 檢查會變成空轉，而且會把玩家的存檔覆蓋掉。
    env = {**os.environ, 'NE_GAME_DATA_DIR': tempfile.mkdtemp(prefix='ne-check-')}
    proc = subprocess.Popen(['python3', '-c', 'from backend.server import run; run(port=8775)'], cwd=REPO, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        # Popen 綁不上埠時子程序會立刻死掉，而輪詢仍可能連上**別人那一台**，
        # 於是整份量測都是對著別的伺服器做的。先確認自己的那台真的活著。
        if proc.poll() is not None:
            raise SystemExit("伺服器啟動失敗（多半是埠被佔住）")
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    return proc


PROBE = r"""
const d = window.__neDebug;
const out = {};
const me = d.getCurrentPlayer();

// ---- 紅槍會起義 ----
// 把直隸三座城判給直系，再讓自己手上有這張卡。
const shared = await d.api('/api/shared-state', { tactical: d.tacticalSnapshot(), expected_revision: null });
const snap = JSON.parse(JSON.stringify(shared.engine_state));
const hebei = (d.getBootstrap().strategic_map?.cities || [])
  .filter(c => c.province === '直隸').map(c => c.id);
for (const id of hebei) snap.city_owners[id] = 'W';
// 兩份：第一份打出去會被消耗掉，沒有第二份就撞不到「同省不可重複」那道關，
// 只會撞到「手上沒這張卡」——那證明不了任何事。
snap.players[me].hand = [...(snap.players[me].hand || []), 'red_spear_uprising', 'red_spear_uprising'];
await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });

const beforeIncome = (await d.api('/api/shared-state',
  { tactical: d.tacticalSnapshot(), expected_revision: null })).engine_state.players.W.income;
const result = await d.api('/api/use-function', {
  player: me, card_id: 'red_spear_uprising',
  target_owner: 'W', target_province: '直隸',
});
out.紅槍會 = {
  後端有回傳暴動: !!result.city_disruption,
  暴動標籤: result.city_disruption?.label,
  受影響城市: (result.city_disruption?.cities || []).map(c => c.name),
  需要戰力: result.city_disruption?.required_force,
  需要回合: result.city_disruption?.required_turns,
  直系收入: `${beforeIncome} → ${result.state.players.W.income}`,
};
// 同一省不能再打第二次
try {
  await d.api('/api/use-function', {
    player: me, card_id: 'red_spear_uprising', target_owner: 'W', target_province: '直隸' });
  out.紅槍會.重複發動 = '**沒有被擋**';
} catch (e) { out.紅槍會.重複發動 = '被擋：' + String(e.message).slice(0, 40); }

// ---- 美孚石油 ----
const s2 = await d.api('/api/shared-state', { tactical: d.tacticalSnapshot(), expected_revision: null });
const snap2 = JSON.parse(JSON.stringify(s2.engine_state));
snap2.players[me].foreign_relations.us = 6;
snap2.players[me].hand = ['us_socony_oil'];
snap2.production_cost_multipliers = [];
await d.api('/api/restore-shared-state', { engine_state: snap2, tactical: d.tacticalSnapshot() });
const oil = await d.api('/api/use-function', { player: me, card_id: 'us_socony_oil' });
const eff = (oil.state.players[me].timed_effects || []).find(e => e.kind === 'oil_price_immunity');
out.美孚 = { 掛上效果: !!eff, 免疫名單: eff?.immune_cards, 回合數: eff?.remaining_turns };
return out;
"""


async def main():
    proc = start_server()
    results = {}
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=['--no-sandbox'])
        page = await b.new_page(viewport={'width': 1400, 'height': 900})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:200]))
        await page.goto(BASE + '/', wait_until='networkidle')
        await page.wait_for_timeout(6500)
        results['結果'] = await page.evaluate("async () => {" + PROBE + "}")
        if errs:
            results['__主控台錯誤__'] = errs[:5]
        await page.close(); await b.close()
    proc.send_signal(signal.SIGKILL); proc.wait()
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))

asyncio.run(main())
