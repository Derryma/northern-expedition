# -*- coding: utf-8 -*-
"""空轉機制修復後的真前端複查。

後端算得對由 backend 測試守著。這裡驗的是玩家在畫面上真的被擋住／看得到差別：
非戰公約的宣戰鈕、治安期發動的暴動門檻、[幫會] 標籤延長，以及暴動進度顯示。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8766'


def start_server():
    proc = subprocess.Popen(['python3', '-m', 'backend.server'], cwd=REPO,
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
const me = d.getCurrentPlayer();
const pull = async () => (await d.api('/api/shared-state',
  { tactical: d.tacticalSnapshot(), expected_revision: null })).engine_state;
const push = async (snap) => d.api('/api/restore-shared-state',
  { engine_state: snap, tactical: d.tacticalSnapshot() });
const other = ['F','W','S','N'].find(c => c !== me);

// ---- 一、非戰公約：簽了就不能宣戰，鈕也要是關的 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  snap.players[me].timed_effects = [...(snap.players[me].timed_effects || []), {
    id: 'kellogg_briand_pact', name: '非戰公約：強制和平', kind: 'forced_peace',
    remaining_turns: 3, permanent: false, owners: [me],
    blocks_enemy_entry: true, blocks_declaration: true,
    withdraw_active_battles: true, defensive_harm_taken_multiplier: 0.92,
  }];
  snap.players[me].warlord_relations[other].status = 'peace';
  await push(snap);
  let blocked = '**沒有被擋**';
  try { await d.api('/api/diplomacy', { player: me, target: other, status: 'war' }); }
  catch (e) { blocked = '被擋：' + String(e.message).slice(0, 40); }
  document.querySelector('[data-panel="foreign"]').click();
  await new Promise(r => setTimeout(r, 500));
  const btn = document.querySelector(`[data-diplomacy-status="war"][data-target="${other}"]`);
  out.非戰公約 = {
    後端擋下宣戰: blocked,
    宣戰鈕是關的: btn ? btn.disabled : '(找不到按鈕)',
    鈕上的說明: btn ? btn.getAttribute('title') : null,
  };
}

// ---- 二、治安惡化期發動的暴動要多鎮壓一回合 ----
async function riotTurns(withCrackdown) {
  const snap = JSON.parse(JSON.stringify(await pull()));
  const hebei = (d.getBootstrap().strategic_map?.cities || [])
    .filter(c => c.province === '直隸').map(c => c.id);
  for (const id of hebei) snap.city_owners[id] = other;
  snap.city_output_effects = [];
  snap.players[me].hand = [...(snap.players[me].hand || []), 'red_spear_uprising'];
  snap.players[me].treasury = 500;
  snap.suppression_turn_bonuses = withCrackdown
    ? [{ id: 'burning_red_lotus', bonus: 1, until_turn: Number(snap.turn) + 3, label: '火燒紅蓮寺' }]
    : [];
  await push(snap);
  const r = await d.api('/api/use-function', {
    player: me, card_id: 'red_spear_uprising', target_owner: other, target_province: '直隸' });
  return r.city_disruption?.required_turns;
}
out.治安惡化 = {
  平時鎮壓回合: await riotTurns(false),
  火燒紅蓮寺期間: await riotTurns(true),
};

// ---- 三、暴動進度條讀的是後端門檻，不是前端自備的常數 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  const first = (snap.city_output_effects || []).find(e => e.kind === 'qing_gang_riot');
  out.進度顯示 = { 效果上的門檻: first?.required_turns };
  if (first) {
    first.garrison_progress = 1;
    await push(snap);
    // 推完之後前端手上還是舊 state，要先拉回來再畫，否則量到的是上一份畫面。
    await d.pullSharedState();
    document.querySelector('[data-panel="cards"]').click();
    await new Promise(r => setTimeout(r, 600));
    const text = document.body.innerText;
    out.進度顯示.畫面上有 = text.includes(`鎮壓 1/${first.required_turns}`)
      ? `鎮壓 1/${first.required_turns}` : '(沒找到)';
    const line = text.split('\n').find(l => l.includes('鎮壓'));
    out.進度顯示.那一行 = line || null;
  }
}
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
