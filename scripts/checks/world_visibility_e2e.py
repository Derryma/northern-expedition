# -*- coding: utf-8 -*-
"""真前端複查：後端知道、玩家卻看不到的那些事。

這一輪守三個形狀不同、成因相同的缺陷：

  * **永久＝過期**：`remaining_turns` 為 None 在後端是「無限期」，前端卻在
    八個地方各寫一份 `Number(remaining_turns || 0) > 0`，於是〈閻錫山封鎖窄軌
    鐵路〉京漢與正太兩線全停，「持續效果」清單一筆都不列。
  * **擋得住卻不說**：被事件按住的功能卡、被禁掉的行動，後端會在路由上擋，
    但按鈕照樣亮著，玩家按下去才收到例外訊息。
  * **變無主卻沒人知道**：列強佔領解除時城市變無主，畫面卻仍畫成佔領前的持有者。

判準一律取自**真的算出來的畫面字串**（activeEffectsMarkup / renderCardsPanel /
renderRecruitmentPanel），不是讀原始碼——讀原始碼擋不住 `if (false)`。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8794'


def start_server():
    port = int(BASE.rsplit(':', 1)[1])
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉再量。")
    # 一支腳本一個埠，而且一律用自己的存檔目錄。
    env = {**os.environ, 'NE_GAME_DATA_DIR': tempfile.mkdtemp(prefix='ne-check-')}
    proc = subprocess.Popen(
        ['python3', '-c', f'from backend.server import run; run(port={port})'],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("伺服器啟動失敗（多半是埠被佔住）")
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
  const me = d.getCurrentPlayer();
  await d.publishSharedState(true);
  await d.api('/api/next-turn', { active_player: me, force: true });
  await d.pullSharedState();
  return { 玩家: me };
}
"""

# ── 1. 永久停擺的鐵路要出現在「持續效果」裡，而且字要對 ─────────────
PERMANENT_RAILWAY = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.railway_effects = [
    { id: 'probe:永久', card_id: 'yan_xishan_blocks_narrow_gauge',
      name: '閻錫山封鎖窄軌鐵路', railway: '正太鐵路', initiator: 'Y',
      remaining_turns: null, permanent: true, no_repair: true, repair_charges: {},
      until_general_leaves: { general: '閻錫山', faction: 'Y' } },
    { id: 'probe:搶修', card_id: 'railway_workers_strike', name: '鐵路工人罷工',
      railway: '京漢鐵路', initiator: 'Y', remaining_turns: 2, repair_charges: {} },
  ];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const markup = d.activeEffectsMarkup(d.getState().players[me]);
  const text = markup.replace(/<[^>]*>/g, ' ');
  return {
    後端認定停擺的線: [...d.disabledRailways()],
    後端蓋的active: (d.getState().railway_effects || []).map(e => [e.railway, e.active]),
    持續效果面板文字: text.replace(/\s+/g, ' ').trim(),
    永久那條的地格標籤: d.railwayStatusLabel('正太鐵路'),
    搶修那條的地格標籤: d.railwayStatusLabel('京漢鐵路'),
  };
}
"""

# ── 2. 永久的 timed_effect 也不能被當成過期 ─────────────────────────
PERMANENT_FLAG = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.players[me].timed_effects = [
    { id: 'probe-forever', kind: 'silver_reform_done', name: '廢兩改元永久免疫',
      remaining_turns: null, permanent: true, owners: [me] },
    { id: 'probe-spent', kind: 'counter_intel', name: '過期的那筆',
      remaining_turns: 0, owners: [me] },
  ];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const text = d.activeEffectsMarkup(d.getState().players[me]).replace(/<[^>]*>/g, ' ');
  return {
    後端蓋的active: (d.getState().players[me].timed_effects || []).map(e => [e.id, e.active]),
    面板文字: text.replace(/\s+/g, ' ').trim(),
  };
}
"""

# ── 3. 被事件按住的功能卡 ───────────────────────────────────────────
BLOCKED_CARD = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.players[me].hand = ['uk_vickers_contract'];
  snap.players[me].pending_draw = null;
  snap.perk_suspensions = [{
    cards: ['uk_vickers_contract'], until_turn: Number(snap.turn) + 3,
    label: '大英總罷工：英國 perk 暫停', source_card: 'british_general_strike' }];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const markup = d.renderCardsPanel();
  // 真的按下去會怎樣：後端該擋，而且理由要跟畫面說的是同一句。
  let backendSaid = null;
  try {
    await d.api('/api/use-function', { player: me, card_id: 'uk_vickers_contract' });
  } catch (e) { backendSaid = String(e.message); }
  return {
    後端回報的封鎖: d.blockedCard('uk_vickers_contract'),
    畫面理由: d.blockedCardNote('uk_vickers_contract'),
    打出鈕是否關掉: /data-use="uk_vickers_contract"[^>]*disabled/.test(markup),
    畫面有沒有寫理由: markup.includes('大英總罷工'),
    後端擋下來的訊息: backendSaid,
  };
}
"""

# ── 4. 被事件禁掉的行動 ─────────────────────────────────────────────
BLOCKED_ACTION = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.action_bans = [{ actions: ['train_unit', 'train_navy_unit', 'reinforce_army', 'reinforce_navy'],
                        until_turn: Number(snap.turn) + 1, label: '軍餉短缺', players: [me] }];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const markup = d.renderRecruitmentPanel();
  let backendSaid = null;
  try {
    await d.api('/api/train-unit', { player: me, unit_type: 'infantry', count: 1 });
  } catch (e) { backendSaid = String(e.message); }
  return {
    後端回報的禁令: d.blockedAction('train_unit'),
    畫面理由: d.blockedActionNote('train_unit'),
    訓練鈕是否關掉: /data-train-unit="infantry"[^>]*disabled/.test(markup),
    造船鈕是否關掉: /data-train-navy-unit="gun_boat"[^>]*disabled/.test(markup),
    畫面有沒有寫理由: markup.includes('軍餉短缺'),
    後端擋下來的訊息: backendSaid,
  };
}
"""

# ── 5. 無主城市 ─────────────────────────────────────────────────────
OWNERLESS = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  // 挑一座**現在真的有人的**城，且它的原主與劇本原主是同一家——
  // 這樣才驗得到「不是悄悄回到劇本原主」。
  const cityId = Object.keys(snap.city_owners).find(id => snap.city_owners[id] === me);
  snap.city_owners[cityId] = null;
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const cityOf = (id) => (d.getBootstrap().strategic_map?.cities || []).find(c => c.id === id);
  const city = cityOf(cityId);
  return {
    城: cityId,
    後端無主名單裡有它: (d.getState().ownerless_cities || []).includes(cityId),
    前端城市歸屬: city?.faction ?? null,
    劇本原主: city?.scenario_faction ?? null,
    地格歸屬: d.cells[city?.cellKey]?.fac ?? null,
    有沒有人聲稱控制它: ['N', 'F', 'W', 'S'].filter(f => d.cityControlledBy(city, f)),
  };
}
"""

# ── 6. 轟炸／重建狀態只由後端說 ─────────────────────────────────────
PUNISHMENT_STATUS = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  const cityId = Object.keys(snap.city_owners).find(id => snap.city_owners[id] === me);
  snap.city_rebuilding = { [cityId]: 2 };
  snap.foreign_punishments = [];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  return {
    城: cityId,
    後端算的: (d.getState().city_punishment_status || {})[cityId] || null,
    前端讀到的: d.cityPunishmentStatus(cityId),
  };
}
"""

# ── 7. 事件卡改寫過的功能卡數字，手上那張卡要跟著改 ────────────────
CARD_REWRITE = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.players[me].hand = ['artifact_smuggling'];
  snap.players[me].pending_draw = null;
  snap.perk_suspensions = [];
  snap.function_card_overrides = [{ card_id: 'artifact_smuggling',
    fields: { payout_min: 30, payout_max: 60 }, until_turn: null }];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const markup = d.renderCardsPanel();
  return {
    後端算的改寫: d.cardFieldChanges('artifact_smuggling'),
    畫面有沒有寫出來: markup.includes('事件改寫'),
    畫面有沒有新數字: markup.includes('$30') && markup.includes('$60'),
  };
}
"""

# ── 8. 單一銀行被事件停貸，借款面板要說 ────────────────────────────
BANK_BAN = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.bank_bans = [{ bank: 'hsbc', until_turn: Number(snap.turn) + 3,
                      label: '大英總罷工：匯豐停止新放款' }];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const offers = await d.api('/api/loan-offers', { player: me });
  const markup = d.renderLoansMarkup(offers);
  const row = (offers.offers || []).find(o => o.bank === 'hsbc');
  let backendSaid = null;
  try { await d.api('/api/take-loan', { player: me, bank: 'hsbc', amount: 5 }); }
  catch (e) { backendSaid = String(e.message); }
  return {
    後端標記: row && { can_borrow: row.can_borrow, available: row.available, bank_ban: row.bank_ban },
    畫面有沒有寫理由: markup.includes('大英總罷工'),
    // 「不承作」那一欄要寫出剩幾回合——只有那一格會印這句，
    // 分級欄印的是同一個 label，只斷言 label 的話這一關擋不住東西。
    停貸那一列的說明: (markup.match(/<span class="loan-blocked-note">([^<]*)<\/span>/g) || [])
      .filter(s => s.includes('大英總罷工')),
    畫面還有沒有借款鈕: /data-borrow-bank="hsbc"/.test(markup),
    後端擋下來的訊息: backendSaid,
  };
}
"""

# ── 9. 佔領與演習在畫面上要分得開 ──────────────────────────────────
OCCUPATION_VS_DRILL = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.foreign_punishments = [
    { id: 'probe-punish', kind: 'ground_occupation', power: 'jp', owner: me,
      label: '關東軍侵占東北三省', mode: 'punishment',
      release_rule: 'becomes_ownerless', until_turn: null,
      provinces: ['奉天'], waters: [], city_ids: [] },
    { id: 'probe-drill', kind: 'ground_occupation', power: 'su', owner: me,
      label: '蘇蒙聯軍演習', mode: 'drill',
      release_rule: 'returns_to_owner', until_turn: Number(snap.turn) + 3,
      provinces: ['熱河'], waters: [], city_ids: [] },
  ];
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  const cellFor = (province) => Object.values(d.cells).find(
    (c) => c.land && d.provinceAt(c.lon, c.lat) === province);
  const read = (province) => {
    const cell = cellFor(province);
    const entry = cell && d.occupationForCell(cell);
    return entry ? { 標題: d.punishmentLockLabel(entry),
                     說明: d.punishmentReleaseNote(entry),
                     是演習: d.punishmentIsDrill(entry) } : null;
  };
  return { 佔領: read('奉天'), 演習: read('熱河') };
}
"""

# ── 10. 戰鬥加成要印得出來 ────────────────────────────────────────
COMBAT_MODIFIERS = r"""
async () => {
  const d = window.__neDebug;
  const armies = d.allArmies(true);
  const a = armies[0], b = armies.find(x => x.id !== armies[0].id);
  const battle = {
    id: 'probe', attackerId: a.id, defenderId: b.id,
    attackerFaction: d.factionForArmy(a), defenderFaction: d.factionForArmy(b),
    appliedModifiers: { [a.id]: [{ stat: 'hp', multiplier: 1.08,
                                   label: '傅作義加固城防：生命 +8%' }] },
  };
  const markup = d.appliedModifiersMarkup(battle, ['A', 'B']);
  return { 有沒有印出來: markup.includes('傅作義加固城防：生命 +8%'),
           空的時候不佔位: d.appliedModifiersMarkup({ id: 'x' }, ['A', 'B']) === '' };
}
"""

# ── 11. 列強懲戒的一次性戰力損失 ──────────────────────────────────
#
# 這是**唯一**由前端做算術的戰力路徑：後端只送「損失率」，削兵在前端做。
# 部隊住在前端，所以只能這樣分工——但也因此它一直沒有 e2e 覆蓋。
# 這一關驗兩件事：削的量對不對，以及三重疊加走的是「以初始值為基準相加」
# （−40%−10%−40% → 剩 10%），不是逐次相乘（那會剩 32.4%）。
PUNISHMENT_FORCE_LOSS = r"""
async () => {
  const d = window.__neDebug;
  const me = d.getCurrentPlayer();
  const mine = d.allArmies(true).filter(a => d.factionForArmy(a) === me
    && a.status === 'active' && d.cells[a.cellKey]?.land);
  const army = mine[0];
  const cell = d.cells[army.cellKey];
  const province = d.strategicProvinceForCell(cell);
  const forceOf = (a) => d.forcePoints(d.armyUnits(a));
  const before = forceOf(army);
  const unitsBefore = { ...d.armyUnits(army) };

  const inject = async (effect) => {
    const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
    for (const code of Object.keys(snap.players)) snap.players[code].pending_frontend_effects = [];
    snap.players[me].pending_frontend_effects = [effect];
    await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
    await d.pullSharedState();
    await d.consumePendingFrontendEffects();
  };

  await inject({ id: 'probe-damage', kind: 'foreign_punishment_damage',
                 punishment_id: 'probe', punishment_kind: 'ground_occupation',
                 power: 'jp', provinces: [province], waters: [], city_ids: [],
                 army_force: -0.4 });
  const afterSingle = forceOf(army);
  const unitsAfterSingle = { ...d.armyUnits(army) };

  // 三重疊加：後端送的是**累計**損失率，前端要從這條鏈開始前的初始值重算。
  await inject({ id: 'probe-chain-1', kind: 'foreign_punishment_damage',
                 punishment_id: 'probe2', punishment_kind: 'ground_occupation',
                 power: 'su', provinces: [province], waters: [], city_ids: [],
                 chain: 'probe-chain', cumulative_army_force: 0.4 });
  const chain1 = forceOf(army);
  await inject({ id: 'probe-chain-2', kind: 'foreign_punishment_damage',
                 punishment_id: 'probe2', punishment_kind: 'ground_occupation',
                 power: 'su', provinces: [province], waters: [], city_ids: [],
                 chain: 'probe-chain', cumulative_army_force: 0.9 });
  const chain2 = forceOf(army);

  // 期望值也跟後端要——這一關要驗的是「前端有沒有照後端的裁法裁」，
  // 不是「前端的算式跟我寫在測試裡的算式一不一樣」。
  const expectSingle = (await d.api('/api/cut-force',
    { units: unitsBefore, multiplier: 0.6 })).force_after;
  return {
    省: province, 原始戰力: before,
    單筆minus40之後: afterSingle,
    單筆該剩: expectSingle,
    鏈第一段之後: chain1, 鏈第二段之後: chain2,
    鏈第二段該剩: (await d.api('/api/cut-force',
      { units: unitsAfterSingle, multiplier: 0.1 })).force_after,
    鏈中途不該停在: chain1,
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
            out['永久停擺的鐵路'] = await page.evaluate(PERMANENT_RAILWAY)
            out['永久旗標'] = await page.evaluate(PERMANENT_FLAG)
            out['被按住的卡'] = await page.evaluate(BLOCKED_CARD)
            out['被禁掉的行動'] = await page.evaluate(BLOCKED_ACTION)
            out['無主城市'] = await page.evaluate(OWNERLESS)
            out['轟炸重建狀態'] = await page.evaluate(PUNISHMENT_STATUS)
            out['卡片改寫'] = await page.evaluate(CARD_REWRITE)
            out['銀行停貸'] = await page.evaluate(BANK_BAN)
            out['佔領與演習'] = await page.evaluate(OCCUPATION_VS_DRILL)
            out['戰鬥加成'] = await page.evaluate(COMBAT_MODIFIERS)
            out['懲戒戰力損失'] = await page.evaluate(PUNISHMENT_FORCE_LOSS)
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
    rail = out.get('永久停擺的鐵路') or {}
    flag = out.get('永久旗標') or {}
    card = out.get('被按住的卡') or {}
    action = out.get('被禁掉的行動') or {}
    free = out.get('無主城市') or {}
    punish = out.get('轟炸重建狀態') or {}
    rewrite = out.get('卡片改寫') or {}
    bank = out.get('銀行停貸') or {}
    occ = out.get('佔領與演習') or {}
    modifiers = out.get('戰鬥加成') or {}
    damage = out.get('懲戒戰力損失') or {}
    checks = {
        "永久停擺：後端認定兩條線都停了":
            sorted(rail.get('後端認定停擺的線') or []) == ['京漢鐵路', '正太鐵路'],
        "永久停擺：後端替沒有回合上限的那筆蓋了 active":
            dict(rail.get('後端蓋的active') or {}).get('正太鐵路') is True,
        "永久停擺：持續效果面板真的列出正太鐵路":
            '正太鐵路' in str(rail.get('持續效果面板文字') or ''),
        "永久停擺：面板寫的是「無法搶修」，不是「搶修中」":
            '無法搶修' in str(rail.get('持續效果面板文字') or ''),
        "永久停擺：面板同時也列得出真的在搶修的那一條":
            '京漢鐵路' in str(rail.get('持續效果面板文字') or ''),
        "永久停擺：地格標籤分得出兩者":
            '無法搶修' in str(rail.get('永久那條的地格標籤') or '')
            and '搶修中' in str(rail.get('搶修那條的地格標籤') or '')
            and '無法搶修' not in str(rail.get('搶修那條的地格標籤') or ''),
        "永久旗標：無期限的那筆被蓋成生效":
            dict(flag.get('後端蓋的active') or {}).get('probe-forever') is True,
        "永久旗標：真的過期的那筆被蓋成不生效":
            dict(flag.get('後端蓋的active') or {}).get('probe-spent') is False,
        "永久旗標：面板列得出無期限的那筆":
            '廢兩改元永久免疫' in str(flag.get('面板文字') or ''),
        "永久旗標：過期的那筆沒被列出來":
            '過期的那筆' not in str(flag.get('面板文字') or ''),
        "被按住的卡：後端有把封鎖送出來": bool(card.get('後端回報的封鎖')),
        "被按住的卡：畫面上的「打出」鈕真的關掉了": card.get('打出鈕是否關掉') is True,
        "被按住的卡：畫面寫出了擋住它的是什麼": card.get('畫面有沒有寫理由') is True,
        "被按住的卡：後端也真的擋得住（不是只有畫面演）":
            '打不出來' in str(card.get('後端擋下來的訊息') or ''),
        "被禁掉的行動：後端有把禁令送出來": bool(action.get('後端回報的禁令')),
        "被禁掉的行動：訓練鈕關掉了": action.get('訓練鈕是否關掉') is True,
        "被禁掉的行動：造船鈕關掉了": action.get('造船鈕是否關掉') is True,
        "被禁掉的行動：畫面寫出了理由": action.get('畫面有沒有寫理由') is True,
        "被禁掉的行動：後端也真的擋得住":
            '不可訓練部隊' in str(action.get('後端擋下來的訊息') or ''),
        "無主城市：後端算得出無主名單": free.get('後端無主名單裡有它') is True,
        "無主城市：畫面上的城市不屬於任何人": free.get('前端城市歸屬') is None,
        "無主城市：腳下那一格也變中立": free.get('地格歸屬') is None,
        "無主城市：沒有任何一家還聲稱控制它": (free.get('有沒有人聲稱控制它') or []) == [],
        "無主城市：驗得到東西（它本來有劇本原主，才可能被悄悄還回去）":
            bool(free.get('劇本原主')),
        "轟炸重建：前端讀的就是後端算的那一份":
            punish.get('前端讀到的') is not None
            and punish.get('前端讀到的') == punish.get('後端算的'),
        "卡片改寫：後端算得出哪些數字被改過": bool(rewrite.get('後端算的改寫')),
        "卡片改寫：手上那張卡有標出來": rewrite.get('畫面有沒有寫出來') is True,
        "卡片改寫：畫面印的是新數字": rewrite.get('畫面有沒有新數字') is True,
        "銀行停貸：後端把那一家標成不可借":
            (bank.get('後端標記') or {}).get('can_borrow') is False
            and (bank.get('後端標記') or {}).get('available') == 0,
        "銀行停貸：面板寫出了理由": bank.get('畫面有沒有寫理由') is True,
        "銀行停貸：「不承作」那一格寫的是停貸令與剩餘回合":
            any('剩' in text and '回合' in text
                for text in (bank.get('停貸那一列的說明') or [])),
        "銀行停貸：借款鈕消失了": bank.get('畫面還有沒有借款鈕') is False,
        "銀行停貸：後端也真的擋得住":
            '匯豐' in str(bank.get('後端擋下來的訊息') or '')
            or '停止新放款' in str(bank.get('後端擋下來的訊息') or ''),
        "佔領與演習：兩者的標題不同":
            (occ.get('佔領') or {}).get('標題') != (occ.get('演習') or {}).get('標題')
            and (occ.get('佔領') or {}).get('標題') is not None,
        "佔領與演習：佔領說土地會變無主":
            '無主' in str((occ.get('佔領') or {}).get('說明') or ''),
        "佔領與演習：演習說會原封歸還":
            '歸還' in str((occ.get('演習') or {}).get('說明') or ''),
        "佔領與演習：前端分得出哪一種是演習":
            (occ.get('演習') or {}).get('是演習') is True
            and (occ.get('佔領') or {}).get('是演習') is False,
        "戰鬥加成：面板印得出後端貼的說明": modifiers.get('有沒有印出來') is True,
        "戰鬥加成：沒有加成時不佔版面": modifiers.get('空的時候不佔位') is True,
        "懲戒戰力：驗得到東西（部隊本來有兵）": (damage.get('原始戰力') or 0) > 0,
        "懲戒戰力：單筆 −40% 削的量對":
            damage.get('單筆minus40之後') == damage.get('單筆該剩'),
        "懲戒戰力：疊加是以初始值為基準相加（第二段從基準重算，不是在現值上再乘）":
            damage.get('鏈第二段之後') == damage.get('鏈第二段該剩')
            and damage.get('鏈第二段之後') < damage.get('鏈中途不該停在'),
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
