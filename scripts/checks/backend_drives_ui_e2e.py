# -*- coding: utf-8 -*-
"""隨機改後端的數字，看真前端有沒有立刻跟著變。

驗的不是「兩邊算出同一個值」——那是兩份規則加一個看門的。
驗的是「後端說什麼，畫面就說什麼」：把後端的數字改成一個隨機的怪值，
畫面如果沒跟著變，代表那個數字前端自己也有一份。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, random, signal, subprocess, sys, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8766'
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20260830
rng = random.Random(SEED)

# 隨機挑的怪值：故意離預設值很遠，前端若留著自己那份就會被看穿。
PROBE = {
    "loyalty": rng.randint(1, 10),
    "hand_size": rng.randint(11, 40),
    "draw_cost": rng.randint(41, 90),
    "force_cap": rng.randint(111, 400),
    "cavalry_force_points": rng.randint(5, 9),
    "forced_march_cash": rng.randint(41, 90),
    "forced_march_tiles": rng.randint(4, 8),
    "engineering_factory_cost": rng.randint(41, 90),
    "navy_move_per_gun_boat": rng.randint(11, 40),
    "defection_resistance": round(rng.uniform(0.11, 0.4), 3),
    "su_low": rng.randint(-10, 0),
    "su_high": rng.randint(6, 10),
}


def start_server(env):
    # 上一輪留下來的伺服器如果還佔著這個埠，新的會綁不上，而輪詢又會立刻成功——
    # 於是整份量測都是對著**舊的**伺服器做的，結果看起來像產品壞了。
    # 這裡先確認埠是空的，不空就直接停下來。
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了。先把它關掉，"
                         f"否則量到的是舊伺服器的數字：pkill -f _probe_server.py")
    proc = subprocess.Popen(['python3', 'scripts/checks/_probe_server.py'], cwd=REPO,
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("探針伺服器啟動失敗（多半是埠被佔住）")
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    raise SystemExit("探針伺服器起不來")


def patched_env():
    """在伺服器啟動前把後端的規則數字換成隨機怪值。"""
    import os
    env = dict(os.environ)
    env["NE_UI_PROBE"] = json.dumps(PROBE, ensure_ascii=False)
    return env


PAGE_PROBE = r"""
const d = window.__neDebug;
const out = {};
const me = d.getCurrentPlayer();
const boot = d.getBootstrap();
const probe = JSON.parse(document.documentElement.dataset.neProbe || '{}');
// 先確認伺服器真的吃到這一輪的探針值。對不上就代表量到的是別的伺服器
// （上一輪沒收乾淨的那一個），整份量測都不算數。
out.探針有生效 = boot.features.function_card_max_hand_size === probe.hand_size
  && boot.features.function_card_draw_cost === probe.draw_cost
  && boot.features.army_force_cap === probe.force_cap;

// ---- 1. bootstrap 送來的規則數字，畫面上要照抄 ----
out.規則數字 = {
  手牌上限: boot.features.function_card_max_hand_size,
  抽卡現金: boot.features.function_card_draw_cost,
  戰力上限: boot.features.army_force_cap,
  騎兵戰力點: boot.features.unit_force_points.cavalry,
  急行軍現金: boot.features.forced_march.cash,
  急行軍格數: boot.features.forced_march.tiles,
  浮橋工業點: boot.engineering.pontoon_bridge.factory_cost,
  每艘砲艇移動工業點: boot.navy_system.move.factory_cost_per_gun_boat,
};

// 畫面上真的印出來的字串。手牌是空的時候面板走另一個分支（只印「目前無手牌」），
// 所以先塞一張卡進手牌，讓「手牌 n/上限」那一行真的被畫出來。
{
  const shared = await d.api('/api/shared-state',
    { tactical: d.tacticalSnapshot(), expected_revision: null });
  const snap = JSON.parse(JSON.stringify(shared.engine_state));
  snap.players[me].hand = [snap.players[me].function_deck[0]];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
}
document.querySelector('[data-panel="cards"]').click();
await new Promise(r => setTimeout(r, 600));
const cardsText = document.getElementById('cardsContent').innerText;
out.畫面 = {
  手牌面板那一行: (cardsText.split('\n').find(l => l.includes('手牌')) || '(找不到)').slice(0, 90),
  手牌上限跟著後端: cardsText.includes(`/${probe.hand_size}`),
  抽卡價跟著後端: cardsText.includes(String(probe.draw_cost)),
};
document.querySelector('[data-panel="cards"]').click();

// ---- 2. 忠誠：改後端的覆寫兩次，畫面要跟著跳兩次，而且每次都等於後端 ----
{
  const armies = () => d.allArmies(true);
  const pick = Object.values(d.getGeneralTrees()[me]?.generals || {})
    .filter(g => g.loyalty !== null && !g.absolute_loyalty && !g.loyalty_exempt)
    .find(g => armies().some(a => a.generalId === g.id && a.status !== 'jailed'));
  const armyOf = () => armies().find(a => a.generalId === pick.id);
  const setOverride = async (value) => {
    const snap = d.tacticalSnapshot();
    snap.loyaltyOverrides[pick.id] = value;
    const pushed = await d.api('/api/shared-state', { tactical: snap, expected_revision: null });
    await d.pullSharedState();
    document.querySelector('[data-panel="generals"]').click();
    await new Promise(r => setTimeout(r, 700));
    const backend = pushed.loyalty?.[pick.id]?.value;
    const shown = d.calculateGeneralLoyalty(pick, armyOf()).value;
    const result = {
      後端覆寫: value, 後端算出來: backend, 前端顯示: shown,
      前端等於後端: shown === backend,
      畫面上的忠誠欄: document
        .querySelector(`.tree-general-card[data-general="${pick.id}"] .loyalty-num`)?.textContent
        ?? "(卡片上沒有忠誠欄)",
    };
    document.querySelector('[data-panel="generals"]').click();
    return result;
  };
  if (pick) {
    const low = await setOverride(1);
    const high = await setOverride(10);
    out.忠誠 = {
      將領: pick.name, 覆寫成1: low, 覆寫成10: high,
      兩次都等於後端: low.前端等於後端 && high.前端等於後端,
      畫面真的跟著變了: low.前端顯示 !== high.前端顯示,
    };
  }
}

// ---- 3. 技能因列強關係失效：把後端關係拉低再拉高，畫面判定要跟著兩次都變 ----
{
  const read = async (su) => {
    const shared = await d.api('/api/shared-state',
      { tactical: d.tacticalSnapshot(), expected_revision: null });
    const snap = JSON.parse(JSON.stringify(shared.engine_state));
    snap.players[me].foreign_relations.su = su;
    await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
    await d.pullSharedState();
    return {
      後端名單: d.getState().players[me].disabled_traits,
      前端判定: d.traitDisabledByRelations('white_russian_mercenaries', me),
    };
  };
  out.技能失效 = { 對蘇拉到低檔: await read(probe.su_low), 對蘇拉到高檔: await read(probe.su_high) };
}

// ---- 3b. 其他規則數字有沒有真的印在畫面上 ----
{
  const army = d.allArmies(true).find(a => d.generalOwners[a.generalId] === me);
  if (army) {
    d.selectArmy(army.id);
    await new Promise(r => setTimeout(r, 700));
    const detail = document.getElementById('armyDetail')?.innerText || "";
    out.部隊面板 = {
      急行軍價出現: detail.includes(String(probe.forced_march_cash)),
      戰力上限出現: detail.includes(String(probe.force_cap)),
      那幾行: detail.split("\n").filter(l => /急行軍|戰力/.test(l)).slice(0, 4),
    };
  }
}

// ---- 4. 策反報價：後端說多少就是多少 ----
{
  const enemy = ['F','W','S','N'].find(c => c !== me);
  const army = d.allArmies(true).find(a => d.generalOwners[a.generalId] === enemy);
  if (army) {
    await d.api('/api/shared-state', { tactical: d.tacticalSnapshot(), expected_revision: null });
    const quote = await d.api('/api/defection-quote', { general_id: army.generalId });
    out.策反報價 = { 將領: army.general, 後端報價: quote };
  }
}
return out;
"""


async def main():
    proc = start_server(patched_env())
    try:
        return await _run(proc)
    finally:
        proc.send_signal(signal.SIGKILL)
        proc.wait()


async def _run(proc):
    results = {"探針值": PROBE}
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=['--no-sandbox'])
        page = await b.new_page(viewport={'width': 1400, 'height': 900})
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)[:200]))
        await page.goto(BASE + '/', wait_until='networkidle')
        await page.wait_for_timeout(6500)
        await page.evaluate("(p) => { document.documentElement.dataset.neProbe = p; }",
                            json.dumps(PROBE))
        results['結果'] = await page.evaluate("async () => {" + PAGE_PROBE + "}")
        if errs:
            results['__主控台錯誤__'] = errs[:5]
        await page.close(); await b.close()
    print(json.dumps(results, ensure_ascii=False, indent=1, default=str))

    r = results.get("結果") or {}
    checks = {
        "探針值真的進了後端": (r.get("探針有生效") is True),
        "手牌上限跟著後端": (r.get("畫面") or {}).get("手牌上限跟著後端"),
        "抽卡價跟著後端": (r.get("畫面") or {}).get("抽卡價跟著後端"),
        "忠誠每次都等於後端": (r.get("忠誠") or {}).get("兩次都等於後端"),
        "忠誠畫面真的跟著變": (r.get("忠誠") or {}).get("畫面真的跟著變了"),
        "技能失效低檔為空": (r.get("技能失效") or {}).get("對蘇拉到低檔", {}).get("後端名單") == [],
        "技能失效高檔前端判定一致":
            (r.get("技能失效") or {}).get("對蘇拉到高檔", {}).get("前端判定") is True,
        "急行軍價跟著後端": (r.get("部隊面板") or {}).get("急行軍價出現"),
        "戰力上限跟著後端": (r.get("部隊面板") or {}).get("戰力上限出現"),
        "策反報價來自後端": bool((r.get("策反報價") or {}).get("後端報價")),
    }
    print()
    print(f"—— 隨機種子 {SEED} ——")
    for name, ok in checks.items():
        print(f"  {'通過' if ok else '**沒過**'}  {name}")
    if results.get("__主控台錯誤__"):
        print("  **主控台有錯**", results["__主控台錯誤__"])
    failed = [n for n, ok in checks.items() if not ok] + \
             (["主控台有錯"] if results.get("__主控台錯誤__") else [])
    return 1 if failed else 0

sys.exit(asyncio.run(main()))
