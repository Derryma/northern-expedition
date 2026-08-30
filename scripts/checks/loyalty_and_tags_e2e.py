# -*- coding: utf-8 -*-
"""真前端複查：忠誠加減、出牌摘要、地格癱瘓標籤、情報網／情報局。"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8766'


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉再量。")
    proc = subprocess.Popen(['python3', '-m', 'backend.server'], cwd=REPO,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    raise SystemExit("伺服器起不來")


PROBE = r"""
const d = window.__neDebug;
const out = {};
const me = d.getCurrentPlayer();
const other = ['F','W','S','N'].find(c => c !== me);
const pull = async () => (await d.api('/api/shared-state',
  { tactical: d.tacticalSnapshot(), expected_revision: null })).engine_state;
const push = async (snap) => d.api('/api/restore-shared-state',
  { engine_state: snap, tactical: d.tacticalSnapshot() });

// ---- 1. 功能卡的忠誠加減真的落地 ----
{
  const armies = () => d.allArmies(true);
  const pick = Object.values(d.getGeneralTrees()[me]?.generals || {})
    .filter(g => g.loyalty !== null && !g.absolute_loyalty && !g.loyalty_exempt)
    .find(g => armies().some(a => a.generalId === g.id && a.status !== 'jailed'));
  const armyOf = () => armies().find(a => a.generalId === pick.id);
  await d.publishSharedState(true);
  const before = d.calculateGeneralLoyalty(pick, armyOf()).value;
  // 直接走後端：算出「+2」之後的新 override，再照抄回去（前端的 applyLoyaltyOverrides
  // 做的就是這件事）。
  const resolved = await d.api('/api/loyalty-effect',
    { kind: 'loyalty_all', faction: me, effect: { amount: 2 } });
  const snap = d.tacticalSnapshot();
  Object.assign(snap.loyaltyOverrides, resolved.overrides);
  const pushed = await d.api('/api/shared-state', { tactical: snap, expected_revision: null });
  await d.pullSharedState();
  const after = d.calculateGeneralLoyalty(pick, armyOf()).value;
  out.忠誠加減 = {
    將領: pick.name, 改前: before, 改後: after, 實際變化: after - before,
    後端算的: pushed.loyalty?.[pick.id]?.value,
    前端等於後端: after === pushed.loyalty?.[pick.id]?.value,
    影響幾位: Object.keys(resolved.overrides).length,
  };
}

// ---- 2. 崩鐵玩家的出牌摘要不再說「無效果」 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  snap.players[me].treasury = 500;
  snap.players[me].factory_points = 500;
  snap.players[me].hand = ['railway_saboteur'];
  await push(snap);
  await d.pullSharedState();
  const card = (d.getCardIndex() || {})['railway_saboteur'];
  const railway = (card?.railways || [])[0]
    || (d.getBootstrap().strategic_map?.railroads || [])[0]?.name;
  const result = await d.api('/api/use-function',
    { player: me, card_id: 'railway_saboteur', target_railway: railway });
  out.崩鐵玩家 = {
    指定鐵路: railway,
    後端回傳: result.railway_effect,
    摘要: d.functionActionMessage({ ...result, player: me, type: 'function_card' }, me),
  };
}

// ---- 3. 地格資訊欄的癱瘓標籤 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  const jiangsu = (d.getBootstrap().strategic_map?.cities || [])
    .filter(c => c.province === '江蘇');
  for (const city of jiangsu) snap.city_owners[city.id] = other;
  snap.players[me].treasury = 500;
  snap.players[me].hand = ['du_yuesheng_gamble'];
  await push(snap);
  await d.pullSharedState();
  await d.api('/api/use-function', { player: me, card_id: 'du_yuesheng_gamble',
    target_owner: other, target_province: '江蘇' });
  await d.pullSharedState();
  const target = jiangsu[0];
  out.地格標籤 = {
    城市: target.name,
    後端回報: d.getState().city_disruptions?.[target.id],
  };
  const cell = d.cells[target.cellKey];
  if (cell) {
    d.selectTile(cell);
    await new Promise(r => setTimeout(r, 600));
    const text = document.getElementById('tileInfo')?.innerText || '';
    out.地格標籤.畫面上的標籤 = (text.split('\n').find(l => /暴動|起義|產出受阻/.test(l))
      || '(畫面上找不到癱瘓標籤)').trim();
  }
}

// ---- 3b. 到期型的暴動（共黨暴動）標籤 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  snap.players[me].treasury = 500;
  snap.players[me].foreign_relations.su = 8;
  snap.players[me].hand = ['communist_riot'];
  await push(snap);
  await d.pullSharedState();
  const played = await d.api('/api/use-function',
    { player: me, card_id: 'communist_riot', target_owner: other });
  await d.pullSharedState();
  const hit = (played.city_disruption?.city_ids || [])[0];
  const cityMeta = (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === hit);
  out.共黨暴動標籤 = { 城市: cityMeta?.name, 後端回報: d.getState().city_disruptions?.[hit] };
  const cell = cityMeta && d.cells[cityMeta.cellKey];
  if (cell) {
    d.selectTile(cell);
    await new Promise(r => setTimeout(r, 600));
    const text = document.getElementById('tileInfo')?.innerText || '';
    out.共黨暴動標籤.畫面上的標籤 = (text.split('\n').find(l => /共黨暴動/.test(l))
      || '(畫面上找不到)').trim();
  }
}

// ---- 4. 情報網／情報局 ----
{
  const snap = JSON.parse(JSON.stringify(await pull()));
  snap.players[me].timed_effects = [
    { kind: 'intel_network', target_province: '直隸', remaining_turns: 1, owners: [me] }];
  snap.players[other].timed_effects = [];
  await push(snap);
  await d.pullSharedState();
  const 沒有情報局 = d.getState().intel?.[me];
  const snap2 = JSON.parse(JSON.stringify(await pull()));
  snap2.players[other].timed_effects = [
    { kind: 'counter_intel', remaining_turns: 3, owners: [other] }];
  await push(snap2);
  await d.pullSharedState();
  out.偵查 = {
    情報網揭露的省: 沒有情報局?.intel_provinces,
    對方設情報局前_有反情報的陣營: 沒有情報局?.counter_intel_factions,
    對方設情報局後_有反情報的陣營: d.getState().intel?.[me]?.counter_intel_factions,
    前端判定直隸對該陣營可見: d.provinceRevealedTo?.('直隸', other, me),
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
            page.on('pageerror', lambda e: errs.append(str(e)[:200]))
            await page.goto(BASE + '/', wait_until='networkidle')
            await page.wait_for_timeout(6500)
            results['結果'] = await page.evaluate("async () => {" + PROBE + "}")
            if errs:
                results['__主控台錯誤__'] = errs[:5]
            await page.close(); await b.close()
        print(json.dumps(results, ensure_ascii=False, indent=1, default=str))
        r = results.get('結果') or {}
        checks = {
            "忠誠 +2 真的加了 2": (r.get('忠誠加減') or {}).get('實際變化') == 2,
            "忠誠前端等於後端": (r.get('忠誠加減') or {}).get('前端等於後端') is True,
            "崩鐵玩家有回傳效果": bool((r.get('崩鐵玩家') or {}).get('後端回傳')),
            "崩鐵玩家摘要不說無效果":
                "無效果" not in str((r.get('崩鐵玩家') or {}).get('摘要', '')),
            "地格標籤後端有回報": bool((r.get('地格標籤') or {}).get('後端回報')),
            "地格標籤畫面看得到":
                "找不到" not in str((r.get('地格標籤') or {}).get('畫面上的標籤', '找不到')),
            "共黨暴動標籤畫面看得到":
                "找不到" not in str((r.get('共黨暴動標籤') or {}).get('畫面上的標籤', '找不到')),
            "情報局擋得住情報網":
                (r.get('偵查') or {}).get('前端判定直隸對該陣營可見') is False
                and (r.get('偵查') or {}).get('對方設情報局後_有反情報的陣營'),
        }
        print()
        for name, ok in checks.items():
            print(f"  {'通過' if ok else '**沒過**'}  {name}")
        if results.get('__主控台錯誤__'):
            print("  **主控台有錯**", results['__主控台錯誤__'])
        return 1 if [n for n, ok in checks.items() if not ok] or results.get('__主控台錯誤__') else 0
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait()

sys.exit(asyncio.run(main()))
