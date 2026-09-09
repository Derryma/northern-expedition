# -*- coding: utf-8 -*-
"""隨機挑幾張地盤吞併／將領移轉類的事件卡，在真前端實際觸發，拍事件前後的地圖。

存到 _shots/transfer_<卡片id>_{before,after}.png，外加一張報紙版面。
不做判定——判定在 faction_transfer_e2e.py，這支只負責讓人看得見。

用法：python3 scripts/checks/faction_transfer_screenshots.py [種子] [張數]
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, random, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8777'
SHOTS = _pathlib.Path(REPO) / '_shots'
SEED = int(sys.argv[1]) if len(sys.argv) > 1 else 20260908
HOW_MANY = int(sys.argv[2]) if len(sys.argv) > 2 else 3

# 只挑「地盤或歸屬真的換手」的那幾類，不含單純加減兵。
TRANSFER_KEYS = ('npc_faction_merge', 'npc_faction_absorb',
                 'npc_general_transfer', 'contested_npc_recruit')


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉它")
    env = dict(os.environ)
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-shot-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8777)'],
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


def pick_cards():
    cards = json.loads((_pathlib.Path(REPO) / 'cards/data/event_cards.json')
                       .read_text(encoding='utf-8'))['cards']
    pool = [c for c in cards
            if any(f'"{k}"' in json.dumps(c, ensure_ascii=False) for k in TRANSFER_KEYS)]
    rng = random.Random(SEED)
    return rng.sample(pool, min(HOW_MANY, len(pool)))


HIDE = """
() => {
  for (const sel of ['#turnDock', '.turn-dock', '.overlay-panel', '#battlePanel',
                     '.phase-banner', '.map-controls', '#newspaperBackdrop']) {
    document.querySelectorAll(sel).forEach((el) => { el.style.display = 'none'; });
  }
}
"""

FOCUS = """
([lon, lat, zoom]) => {
  const stage = document.getElementById('mapStage');
  const container = document.querySelector('.map-container');
  const x = (lon - 95) * 36, y = (54 - lat) * 36;
  const sx = (x / 1440) * stage.offsetWidth, sy = (y / 1296) * stage.offsetHeight;
  stage.style.transform =
    `translate(${container.clientWidth / 2 - sx * zoom}px, ${container.clientHeight / 2 - sy * zoom}px) scale(${zoom})`;
}
"""

# 佈景：把牌池換成指定的那張，回合推到抽卡的那一格，並讓國民革命軍與直系交戰
# （15.18 的入場條件要用到）。
STAGE = r"""
async ([cardId]) => {
  const d = window.__neDebug;
  await d.publishSharedState(true);
  const snap = JSON.parse(JSON.stringify((await d.api('/api/shared-state')).engine_state));
  snap.event_pool = [cardId];
  snap.turn = (Math.floor(Number(snap.turn) / 3) + 1) * 3 - 1;
  snap.pending_events = null;
  snap.retired_npc_factions = [];
  snap.marshal_ids = { F: 'zhang_zuolin', W: 'wu_peifu', S: 'sun_chuanfang', N: 'chiang_kai_shek' };
  for (const code of Object.keys(snap.players)) {
    snap.players[code].treasury = 500;
    snap.players[code].factory_points = 500;
    snap.players[code].pending_draw = null;
    for (const pw of ['jp', 'uk', 'us', 'fr', 'su', 'de']) {
      snap.players[code].foreign_relations = snap.players[code].foreign_relations || {};
      snap.players[code].foreign_relations[pw] = 6;
    }
  }
  snap.players.N.warlord_relations = { ...(snap.players.N.warlord_relations || {}), W: { status: 'war' } };
  snap.players.W.warlord_relations = { ...(snap.players.W.warlord_relations || {}), N: { status: 'war' } };
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  await d.api('/api/next-turn', { active_player: d.getCurrentPlayer(), force: true });
  await d.pullSharedState();
  const owners = (fac) => Object.values(d.cells).filter(c => c.fac === fac).length;
  return { 各家地格: Object.fromEntries(['F','W','S','N','Y','G','M','H','D','C','Q'].map(f => [f, owners(f)])) };
}
"""

# 回應到結算完，順便把交辦排空（吞併換色、將領轉屬都是靠它落到畫面上）。
RESOLVE = r"""
async ([cardId]) => {
  const d = window.__neDebug;
  const notes = [];
  for (let guard = 0; guard < 24; guard++) {
    await d.pullSharedState();
    const pending = d.getState().pending_events;
    const entries = (pending && pending.cards) || [];
    const index = Number((pending && pending.index) || 0);
    if (index >= entries.length) break;
    const entry = entries[index];
    if (entry.card_id !== cardId) break;
    const answered = entry.responses || {};
    const who = (entry.responders || []).find(c => !(c in answered))
      || ['F','W','S','N'].find(c => !(c in answered));
    if (!who) break;
    const card = d.getBootstrap().cards.event.find(c => c.id === cardId);
    const options = ((card && card.resolution && card.resolution.options) || []);
    const body = { player: who };
    if (options.length) body.choice = options[0].id;
    const result = await d.api('/api/respond-event', body);
    notes.push(...(result.applied || []).map(a => a.kind));
  }
  await d.pullSharedState();
  const drained = await d.consumePendingFrontendEffects();
  await d.pullSharedState();
  const owners = (fac) => Object.values(d.cells).filter(c => c.fac === fac).length;
  return {
    結算的機制: notes,
    畫面提示: drained,
    各家地格: Object.fromEntries(['F','W','S','N','Y','G','M','H','D','C','Q'].map(f => [f, owners(f)])),
  };
}
"""


async def main():
    proc = start_server()
    SHOTS.mkdir(exist_ok=True)
    report = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            for card in pick_cards():
                page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
                errs = []
                page.on('pageerror', lambda e: errs.append(str(e)[:200]))
                await page.goto(BASE + '/', wait_until='networkidle')
                await page.wait_for_timeout(7000)
                before = await page.evaluate(STAGE, [card['id']])
                # 先把報紙那一版拍下來，再收起來拍地圖。
                await page.wait_for_timeout(700)
                await page.screenshot(path=str(SHOTS / f"transfer_{card['id']}_paper.png"))
                await page.evaluate(HIDE)
                await page.evaluate(FOCUS, [108.0, 33.0, 1.35])
                await page.wait_for_timeout(600)
                await page.screenshot(path=str(SHOTS / f"transfer_{card['id']}_before.png"))

                after = await page.evaluate(RESOLVE, [card['id']])
                await page.evaluate(HIDE)
                await page.evaluate(FOCUS, [108.0, 33.0, 1.35])
                await page.wait_for_timeout(800)
                await page.screenshot(path=str(SHOTS / f"transfer_{card['id']}_after.png"))

                moved = {f: after['各家地格'][f] - before['各家地格'][f]
                         for f in before['各家地格']
                         if after['各家地格'][f] != before['各家地格'][f]}
                report.append({
                    '卡': card['name'], 'id': card['id'],
                    '標題': card['newspaper']['headline'],
                    '結算的機制': after['結算的機制'],
                    '地格變化': moved,
                    '畫面提示': after['畫面提示'],
                    '主控台錯誤': errs[:3],
                })
                await page.close()
            await browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


sys.exit(asyncio.run(main()))
