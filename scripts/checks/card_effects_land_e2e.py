# -*- coding: utf-8 -*-
"""真前端複查：忠誠卡、城市等級卡、以及後端自己改動共享狀態時前端有沒有跟上。

這一輪的病根不是「規則算錯」，而是**畫面沒有重畫**：app.js 呼叫了一個
從來沒有被定義過的 refreshBackendDerivedState()，ReferenceError 把後面的
updateTopBar / initMap / renderPanel 整段吃掉，於是卡明明生效了、後端也算對了，
玩起來卻是「點了沒有效果」。所以這支 e2e 一律**按真的按鈕**，並且檢查提示文字
不是例外訊息——只打 API 驗不到這種病。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8791'


def start_server():
    port = int(BASE.rsplit(':', 1)[1])
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉再量。")
    # 驗證一律用自己的存檔目錄：不然每次起伺服器都會接續玩家上一盤，
    # 檢查會變成空轉，而且會把玩家的存檔覆蓋掉。
    env = {**os.environ,
           'NE_GAME_DATA_DIR': tempfile.mkdtemp(prefix='ne-check-')}
    proc = subprocess.Popen(
        ['python3', '-c', f'from backend.server import run; run(port={port})'],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("伺服器起不來")


SETUP = r"""
async () => {
  const d = window.__neDebug;
  await d.switchFaction('N');
  await new Promise(r => setTimeout(r, 1200));
  const n = d.getCurrentPlayer();
  await d.publishSharedState(true);
  // 真實遊戲一定跑過回合；引擎的 _tactical 也是在這時才拿到。
  await d.api('/api/next-turn', { active_player: n, force: true });
  await d.pullSharedState();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.players[n].treasury = 500;
  snap.players[n].factory_points = 500;
  snap.players[n].hand = ['national_bulwark'];
  snap.pending_events = null;
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const tree = d.getGeneralTrees()[n]?.generals || {};
  const pick = Object.values(tree).find(g => g.loyalty !== null && !g.absolute_loyalty
    && !g.loyalty_exempt && d.allArmies(true).some(a => a.generalId === g.id));
  window.__pick = pick;
  const army = d.allArmies(true).find(a => a.generalId === pick.id);
  return { 玩家: n, 將領: pick.name, 出牌前忠誠: d.calculateGeneralLoyalty(pick, army).value };
}
"""

AFTER_LOYALTY = r"""
async () => {
  const d = window.__neDebug;
  const pick = window.__pick;
  const army = () => d.allArmies(true).find(a => a.generalId === pick.id);
  const remote = await d.api('/api/shared-state');
  return {
    出牌後顯示: d.calculateGeneralLoyalty(pick, army()).value,
    前端overrides: (d.getLoyaltyOverrides() || {})[pick.id],
    後端快照overrides: (remote.tactical?.loyaltyOverrides || {})[pick.id],
    後端loyalty_report: remote.loyalty?.[pick.id]?.value,
    畫面提示: d.getUiNotice(),
  };
}
"""

EVENT_CARDS = r"""
async ([cardId]) => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.event_pool = [cardId];
  const cur = Number(snap.turn);
  snap.turn = (Math.floor(cur / 3) + 1) * 3 - 1;
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  await d.api('/api/next-turn', { active_player: me, force: true });
  let guard = 0, applied = [];
  while (guard++ < 20) {
    await d.pullSharedState();
    const pending = d.getState()?.pending_events;
    if (!pending || !(pending.cards || [])[Number(pending.index || 0)]) break;
    let progressed = false;
    for (const code of ['N', 'F', 'W', 'S']) {
      try {
        const r = await d.api('/api/respond-event', { player: code, choice: 'acknowledge' });
        applied = applied.concat(r.applied || []); progressed = true; break;
      } catch (e) {
        try {
          const r = await d.api('/api/respond-event', { player: code });
          applied = applied.concat(r.applied || []); progressed = true; break;
        } catch (e2) { /* 不是這個人在等 */ }
      }
    }
    if (!progressed) break;
  }
  await d.pullSharedState();
  return applied.map(a => a.kind);
}
"""

MEASURE = r"""
async () => {
  const d = window.__neDebug;
  const st = d.getState();
  const cityOf = (id) => (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === id);
  const remote = await d.api('/api/shared-state');
  return {
    城市等級: {
      後端覆寫表: st.city_level_overrides,
      保定_前端顯示: cityOf('baoding')?.level,
      保定_後端city_economy: Object.values(st.players || {})
        .flatMap(p => p.city_economy || []).find(c => c.id === 'baoding')?.level,
    },
    吞併地格: {
      前端還剩幾格Q: Object.values(d.cells).filter(c => c.fac === 'Q').length,
      後端還剩幾格Q: Object.values(remote.tactical?.cellFactions || {}).filter(v => v === 'Q').length,
    },
  };
}
"""


DRAIN_IDEMPOTENCE = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const loyaltyOf = (f) => {
    const g = Object.values(d.getGeneralTrees()[f]?.generals || {})
      .find(x => x.loyalty !== null && !x.absolute_loyalty && !x.loyalty_exempt
        && d.allArmies(true).some(a => a.generalId === x.id));
    return g ? d.calculateGeneralLoyalty(g, d.allArmies(true).find(a => a.generalId === g.id)).value : null;
  };
  const inject = async (effects) => {
    const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
    for (const code of Object.keys(snap.players)) snap.players[code].pending_frontend_effects = [];
    snap.players[me].pending_frontend_effects = effects;
    await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
    await d.pullSharedState();
  };

  // 1) 一筆好的、一筆會讓後端回 400 的：好的要做完並銷帳，壞的留著，而且不能丟例外。
  await inject([
    { id: 'probe-good', kind: 'loyalty_all', label: '好的一筆', amount: -2 },
    { id: 'probe-bad', kind: 'loyalty_all', label: '壞的一筆', amount: '不是數字' },
  ]);
  const before = loyaltyOf(me);
  let threw = null;
  try { await d.consumePendingFrontendEffects(); } catch (e) { threw = String(e.message); }
  await d.pullSharedState();
  const afterFirst = loyaltyOf(me);
  const leftFirst = (d.getState().players[me].pending_frontend_effects || []).map(e => e.id);

  // 2) 把**同一個流水號**再塞回佇列（模擬「做完了但銷帳沒成功」）：
  //    第二次排空只該補銷帳，不該再套用一次。
  await inject([{ id: 'probe-good', kind: 'loyalty_all', label: '好的一筆', amount: -2 }]);
  await d.consumePendingFrontendEffects();
  await d.pullSharedState();
  return {
    排空有沒有丟例外: threw,
    第一次排空前: before,
    第一次排空後: afterFirst,
    第一次之後佇列剩下: leftFirst,
    重送同一筆之後: loyaltyOf(me),
    重送之後佇列剩下: (d.getState().players[me].pending_frontend_effects || []).map(e => e.id),
  };
}
"""


async def main():
    proc = start_server()
    out = {}
    try:
        async with async_playwright() as pw:
            b = await pw.chromium.launch(args=['--no-sandbox'])
            page = await b.new_page(viewport={'width': 1500, 'height': 950})
            errs = []
            page.on('pageerror', lambda e: errs.append(str(e)[:300]))
            await page.goto(BASE + '/', wait_until='networkidle')
            await page.wait_for_timeout(7000)

            out['設定'] = await page.evaluate(SETUP)
            await page.evaluate("() => document.querySelector('[data-panel=\"cards\"]')?.click()")
            await page.wait_for_timeout(900)
            btn = page.locator('[data-use="national_bulwark"]')
            out['找到打出鈕'] = await btn.count()
            if await btn.count():
                await btn.first.click()
                await page.wait_for_timeout(2500)
            out['忠誠卡'] = await page.evaluate(AFTER_LOYALTY)

            out['城市等級卡applied'] = await page.evaluate(EVENT_CARDS, ['yan_yangchu_rural_education'])
            before_q = await page.evaluate(
                "() => Object.values(window.__neDebug.cells).filter(c => c.fac === 'Q').length")
            out['吞併前的Q地格'] = before_q
            out['吞併卡applied'] = await page.evaluate(EVENT_CARDS, ['liu_xiang_annexes_qian'])
            out.update(await page.evaluate(MEASURE))
            out['交辦排空'] = await page.evaluate(DRAIN_IDEMPOTENCE)
            if errs:
                out['__主控台錯誤__'] = errs[:5]
            await page.close(); await b.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    loyal = out.get('忠誠卡') or {}
    city = (out.get('城市等級') or {})
    merge = (out.get('吞併地格') or {})
    drain = (out.get('交辦排空') or {})
    checks = {
        "排空：一筆失敗不會丟例外出來": drain.get('排空有沒有丟例外') is None,
        "排空：好的那筆真的套用了":
            drain.get('第一次排空前') is not None
            and drain.get('第一次排空後') == drain.get('第一次排空前') - 2,
        "排空：壞的那筆留著待重試、好的已銷帳":
            drain.get('第一次之後佇列剩下') == ['probe-bad'],
        "排空：同一個流水號重送不會再套用一次":
            drain.get('重送同一筆之後') == drain.get('第一次排空後'),
        "排空：重送的那筆有被補銷帳": drain.get('重送之後佇列剩下') == [],
        "忠誠卡：畫面數字真的加了 2":
            loyal.get('出牌後顯示') == (out.get('設定') or {}).get('出牌前忠誠', 0) + 2,
        "忠誠卡：前端等於後端":
            loyal.get('出牌後顯示') is not None
            and loyal.get('出牌後顯示') == loyal.get('後端loyalty_report'),
        "忠誠卡：覆寫值有寫進共享快照":
            loyal.get('後端快照overrides') is not None,
        "忠誠卡：提示是卡的說明、不是例外訊息":
            'is not defined' not in str(loyal.get('畫面提示') or '')
            and 'undefined' not in str(loyal.get('畫面提示') or ''),
        "城市等級：後端有寫覆寫表": bool(city.get('後端覆寫表')),
        "城市等級：畫面上的保定升到 3": city.get('保定_前端顯示') == 3,
        "城市等級：畫面等於後端":
            city.get('保定_前端顯示') == city.get('保定_後端city_economy'),
        "吞併：事件前畫面上真的有黔軍地盤": (out.get('吞併前的Q地格') or 0) > 3,
        "吞併：後端把黔軍地盤清空": merge.get('後端還剩幾格Q') == 0,
        "吞併：畫面跟著清空（後端改動有傳到前端）": merge.get('前端還剩幾格Q') == 0,
    }
    print()
    failed = [n for n, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'通過' if ok else '**沒過**'}  {name}")
    if out.get('__主控台錯誤__'):
        print("  **主控台有錯**", out['__主控台錯誤__'])
        failed.append('主控台有錯')
    print()
    print(f"{len(checks) - len(failed)}/{len(checks)} 通過")
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
