# -*- coding: utf-8 -*-
"""指定幾張事件卡，在真前端逐張觸發，把「事前／事後」的證據拍下來。

和 faction_transfer_screenshots.py 的差別：那一支是隨機挑、只拍地圖；
這一支是**指定卡片**，而且每張卡拍的是它真正該看的地方——
地盤易主看地圖，城市等級看地格情報欄，封路看地格情報欄裡的鐵路狀態。

用法：python3 scripts/checks/card_effect_screenshots.py [卡片id ...]
不給就跑預設那四張。輸出在 _shots/card_<卡片id>_*.png。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, json, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8778'
SHOTS = _pathlib.Path(REPO) / '_shots'

# 每張卡要看哪裡：focus 是地圖鏡頭，tiles 是要打開情報欄的城市。
PLAN = {
    'liu_xiang_annexes_qian': {
        '說明': '黔軍地盤整片轉給川軍',
        'focus': (106.5, 28.5, 2.6),
        'tiles': ['guiyang', 'zunyi'],
    },
    'qian_army_moutai': {
        '說明': '遵義城市等級 +1',
        'focus': (106.9, 27.7, 3.4),
        'tiles': ['zunyi'],
    },
    'yan_xishan_promotes_education': {
        '說明': '山西所有城市等級 +1',
        'focus': (112.5, 37.5, 2.6),
        'tiles': ['taiyuan', 'datong', 'linfen'],
    },
    'yan_xishan_blocks_narrow_gauge': {
        '說明': '正太鐵路、京漢鐵路全線停擺且無法搶修',
        'focus': (114.0, 36.5, 2.2),
        # 太原是正太線的西端，鄭州與漢口在京漢線上；情報欄會逐條列出
        # 該地格經過的鐵路與它現在的狀態。
        'tiles': ['taiyuan', 'zhengzhou', 'hankou'],
        # 正太與京漢的交會點（正定一帶）沒有城市，用經緯度指過去。
        'cells': [(114.5, 38.0)],
    },
}
DEFAULT = list(PLAN)


def reset(base):
    """開一局新的。每張卡都要從乾淨的局面開始，否則前一張的效果會留著——
    〈劉湘吞併黔軍〉之後黔軍就退場了，〈黔軍整頓茅台酒造〉的入場條件
    （遵義仍歸黔軍）自然不成立，那張卡根本抽不到。"""
    request = urllib.request.Request(
        base + '/api/new-game', data=b'{}',
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as fh:
        fh.read()


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
        ['python3', '-c', 'from backend.server import run; run(port=8778)'],
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

STAGE = r"""
async ([cardId]) => {
  const d = window.__neDebug;
  // 每張卡都要從乾淨的局面開始。同一個伺服器連跑兩張時，前一張的效果會留著
  // ——〈劉湘吞併黔軍〉之後黔軍就退場了，〈黔軍整頓茅台酒造〉的入場條件
  // （遵義仍歸黔軍）自然不成立，那張卡根本抽不到。
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
  }
  await d.api('/api/restore-shared-state', { engine_state: snap, tactical: d.tacticalSnapshot() });
  await d.pullSharedState();
  await d.api('/api/next-turn', { active_player: d.getCurrentPlayer(), force: true });
  await d.pullSharedState();
  const pending = d.getState().pending_events;
  const entries = (pending && pending.cards) || [];
  return { 抽到的是: entries.length ? entries[Number(pending.index || 0)].card_id : null };
}
"""

# 事前／事後都量同一組事實，才比得出差別。
MEASURE = r"""
([cityIds]) => {
  const d = window.__neDebug;
  const cities = d.getBootstrap().strategic_map.cities;
  const byId = Object.fromEntries(cities.map(c => [c.id, c]));
  const owners = (fac) => Object.values(d.cells).filter(c => c.fac === fac).length;
  return {
    城市: Object.fromEntries(cityIds.map(id => {
      const city = byId[id];
      const cell = city ? d.cells[city.cellKey] : null;
      return [id, city ? { 名稱: city.name, 等級: city.level, 地格: city.cellKey,
                           地格歸屬: cell ? cell.fac : null } : null];
    })),
    地格數: Object.fromEntries(['F','W','S','N','Y','G','M','H','D','C','Q'].map(f => [f, owners(f)])),
    停擺的鐵路: [...d.disabledRailways()],
    後端城市等級覆寫: d.getState().city_level_overrides || null,
    後端鐵路效果: (d.getState().railway_effects || []).map(e => ({
      線: e.railway, 剩餘: e.remaining_turns, 永久: e.permanent, 不可修: e.no_repair })),
  };
}
"""

RESOLVE = r"""
async ([cardId]) => {
  const d = window.__neDebug;
  const kinds = [];
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
    kinds.push(...((await d.api('/api/respond-event', body)).applied || []).map(a => a.kind));
  }
  await d.pullSharedState();
  const notes = await d.consumePendingFrontendEffects();
  await d.pullSharedState();
  return { 結算的機制: kinds, 畫面提示: notes };
}
"""

OPEN_TILE = """
([cityId]) => {
  const d = window.__neDebug;
  const city = d.getBootstrap().strategic_map.cities.find(c => c.id === cityId);
  if (!city) return null;
  const cell = d.cells[city.cellKey];
  if (!cell) return null;
  d.selectTile(cell);
  return city.name;
}
"""

# 沒有城市的地格（例如正太與京漢的交會點）用經緯度找最近的那一格。
OPEN_CELL = """
([lon, lat]) => {
  const d = window.__neDebug;
  let best = null, bestDistance = Infinity;
  for (const cell of Object.values(d.cells)) {
    if (!cell.land) continue;
    const distance = (cell.lon - lon) ** 2 + (cell.lat - lat) ** 2;
    if (distance < bestDistance) { bestDistance = distance; best = cell; }
  }
  if (!best) return null;
  d.selectTile(best);
  return { 格: best.key, 鐵路: [...(best.railroads || [])] };
}
"""


async def shoot_tiles(page, card_id, phase, city_ids):
    """逐座城打開地格情報欄拍下來。等級與鐵路狀態都在那一欄裡。"""
    out = []
    for city_id in city_ids:
        name = await page.evaluate(OPEN_TILE, [city_id])
        if not name:
            continue
        await page.wait_for_timeout(350)
        path = SHOTS / f'card_{card_id}_{phase}_tile_{city_id}.png'
        await page.locator('#tileInfo').screenshot(path=str(path))
        out.append(str(path))
    return out


async def shoot_cells(page, card_id, phase, coords):
    out = []
    for index, (lon, lat) in enumerate(coords):
        info = await page.evaluate(OPEN_CELL, [lon, lat])
        if not info:
            continue
        await page.wait_for_timeout(350)
        path = SHOTS / f'card_{card_id}_{phase}_cell{index}.png'
        await page.locator('#tileInfo').screenshot(path=str(path))
        out.append((str(path), info))
    return out


async def main():
    card_ids = sys.argv[1:] or DEFAULT
    proc = start_server()
    SHOTS.mkdir(exist_ok=True)
    report = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            for card_id in card_ids:
                plan = PLAN.get(card_id) or {'focus': (110.0, 34.0, 1.4), 'tiles': []}
                # 開局必須在開頁面**之前**做完。順序反過來的話，頁面 boot() 時會先
                # 抓到上一張卡留下的共享狀態，把它的地格顏色套進自己的 cells——
                # 接著 new-game 只清掉伺服器那份，畫面上仍是上一輪的顏色。
                # 上一輪就這樣讓遵義在事件前看起來已經是川軍的了。
                reset(BASE)
                page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
                errs = []
                page.on('pageerror', lambda e: errs.append(str(e)[:200]))
                await page.goto(BASE + '/', wait_until='networkidle')
                await page.wait_for_timeout(7000)

                drawn = await page.evaluate(STAGE, [card_id])
                await page.wait_for_timeout(700)
                await page.screenshot(path=str(SHOTS / f'card_{card_id}_paper.png'))

                before = await page.evaluate(MEASURE, [plan['tiles']])
                await page.evaluate(HIDE)
                await page.evaluate(FOCUS, list(plan['focus']))
                await page.wait_for_timeout(500)
                await page.screenshot(path=str(SHOTS / f'card_{card_id}_before.png'))
                await shoot_tiles(page, card_id, 'before', plan['tiles'])
                cells_before = await shoot_cells(page, card_id, 'before', plan.get('cells') or [])

                resolved = await page.evaluate(RESOLVE, [card_id])
                after = await page.evaluate(MEASURE, [plan['tiles']])
                await page.evaluate(HIDE)
                await page.evaluate(FOCUS, list(plan['focus']))
                await page.wait_for_timeout(700)
                await page.screenshot(path=str(SHOTS / f'card_{card_id}_after.png'))
                await shoot_tiles(page, card_id, 'after', plan['tiles'])
                cells_after = await shoot_cells(page, card_id, 'after', plan.get('cells') or [])

                moved = {f: after['地格數'][f] - before['地格數'][f]
                         for f in before['地格數'] if after['地格數'][f] != before['地格數'][f]}
                levels = {cid: f"{before['城市'][cid]['等級']} → {after['城市'][cid]['等級']}"
                          for cid in plan['tiles']
                          if before['城市'].get(cid) and after['城市'].get(cid)
                          and before['城市'][cid]['等級'] != after['城市'][cid]['等級']}
                owners = {cid: f"{before['城市'][cid]['地格歸屬']} → {after['城市'][cid]['地格歸屬']}"
                          for cid in plan['tiles']
                          if before['城市'].get(cid) and after['城市'].get(cid)
                          and before['城市'][cid]['地格歸屬'] != after['城市'][cid]['地格歸屬']}
                report.append({
                    '卡': card_id, '說明': plan.get('說明'),
                    '抽到的是': drawn['抽到的是'],
                    '結算的機制': resolved['結算的機制'],
                    '畫面提示': resolved['畫面提示'],
                    '地格變化': moved,
                    '城市等級變化': levels,
                    '城市歸屬變化': owners,
                    '停擺的鐵路': {'事前': before['停擺的鐵路'], '事後': after['停擺的鐵路']},
                    '後端城市等級覆寫': {'事前': before['後端城市等級覆寫'],
                                       '事後': after['後端城市等級覆寫']},
                    '後端鐵路效果': {'事前': before['後端鐵路效果'], '事後': after['後端鐵路效果']},
                    '拍到的路口': [info for _, info in (cells_after or [])],
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
