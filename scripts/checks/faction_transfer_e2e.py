# -*- coding: utf-8 -*-
"""所有陣營吞併／歸屬轉移類的卡，逐張打真的 HTTP 進去驗。

要守的那條規定：**卡片改的必須是伺服器現在手上那份戰術快照。**

先前不是。這些卡全部在 `respond_event()` 裡結算（卡片的 apply 要等每一家都
回應完才跑），而 `self._tactical` 只有 `next_turn()` 會設。前端每推一次共享
狀態，`SHARED_TACTICAL_STATE` 就換成一份新的 dict，引擎手上那個變成孤兒——
黔軍的地格、部隊、城市確實都轉給了川軍，轉在一份再也沒有人看的字典上。
applied 回報成功，地圖一格沒動。時好時壞，端看那一輪前端有沒有剛好推過。

所以這支腳本刻意在 next-turn 與 respond-event 之間**換一份新的快照上去**，
換完才回應。這正是那個競態，也正是這支腳本存在的理由。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import copy, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request
sys.path.insert(0, REPO)

BASE = 'http://127.0.0.1:8793'
KEYS = ('npc_faction_merge', 'npc_faction_absorb', 'npc_general_transfer',
        'contested_npc_recruit', 'npc_unit_delta', 'npc_force_scale')

# 每種機制**至少**要改到快照的哪些部分。
# 只驗「有沒有變」不夠：吞併同時會動部隊與地格，光看「有東西變了」的話，
# 把地格轉移整段拿掉也照樣是綠的。
EXPECTED_PARTS = {
    'npc_faction_merge': ['cellFactions', 'armyStatus', 'armyUnits'],
    'npc_faction_absorb': ['cellFactions', 'armyFactions'],
    'npc_general_transfer': ['armyFactions', 'generalOwners'],
    'contested_npc_recruit': ['armyFactions', 'generalOwners'],
    'npc_unit_delta': ['armyUnits'],
    'npc_force_scale': ['armyUnits'],
}


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了，先關掉它")
    env = dict(os.environ)
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-check-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8793)'],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("伺服器啟動失敗")
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("伺服器起不來")


def post(path, payload):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as fh:
            return json.loads(fh.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} -> {exc.code} {exc.read().decode('utf-8')[:200]}") from None


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as fh:
        return json.loads(fh.read().decode('utf-8'))


def npc_armies_from_map_js():
    """從 frontend/map.js 的 ARMY_POSITIONS 生一份戰術快照。

    NPC 卡的觸發條件要看將領與編制的現況，所以名冊得是真的那一份，
    不能在這裡另外編一組——那就成了第二份真源。
    """
    script = r"""
    import { ARMY_POSITIONS } from '%s/frontend/map.js';
    const armies = {}, owners = {}, cells = {};
    let n = 0;
    for (const [faction, list] of Object.entries(ARMY_POSITIONS)) {
      for (const spec of list) {
        const cellKey = `900,${n++}`;      // 假地格，只要唯一就好
        armies[spec.id] = { id: spec.id, faction, generalId: spec.generalId,
                            cellKey, status: 'active', units: { ...spec.units } };
        owners[spec.generalId] = faction;
        cells[cellKey] = faction;
      }
    }
    console.log(JSON.stringify({ armies, generalOwners: owners, cellFactions: cells,
                                 generalTrees: {}, jailedGenerals: [], loyaltyOverrides: {} }));
    """ % REPO
    out = subprocess.run(['node', '--input-type=module', '-e', script],
                         cwd=REPO, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("讀不到 ARMY_POSITIONS：" + out.stderr[:400])
    return json.loads(out.stdout)


def relevant_cards():
    cards = json.loads((_pathlib.Path(REPO) / 'cards/data/event_cards.json')
                       .read_text(encoding='utf-8'))['cards']
    rows = []
    for card in cards:
        blob = json.dumps(card, ensure_ascii=False)
        keys = sorted({k for k in KEYS if f'"{k}"' in blob})
        if keys:
            rows.append((card, keys))
    return rows


def prime_engine_state(state, card_id):
    """把引擎狀態調成「下一次 next-turn 一定抽到這張卡」。"""
    state = copy.deepcopy(state)
    state['event_pool'] = [card_id]
    turn = int(state['turn'])
    state['turn'] = (turn // 3 + 1) * 3 - 1
    state['marshal_ids'] = {"F": "zhang_zuolin", "W": "wu_peifu",
                            "S": "sun_chuanfang", "N": "chiang_kai_shek"}
    for payload in state['players'].values():
        payload['treasury'] = 500
        payload['factory_points'] = 500
        payload['pending_draw'] = None
        for power in ('jp', 'uk', 'us', 'fr', 'su', 'de'):
            payload.setdefault('foreign_relations', {})[power] = 6
    state['pending_events'] = None
    state['retired_npc_factions'] = []
    # 15.18〈劉湘通電討直〉的入場條件是「當下正對直系宣戰」。沒有戰爭狀態
    # 這張卡根本進不了牌池，於是這支腳本會回報「沒抽到」——那是佈景不足，
    # 不是卡片壞了。這裡把國民革命軍與直系設成交戰狀態。
    for a, b in (('N', 'W'), ('W', 'N')):
        state['players'][a].setdefault('warlord_relations', {})[b] = {'status': 'war'}
    return state


def tactical_signature(tactical):
    """拿來比對「這份快照有沒有真的被改到」的指紋。"""
    armies = tactical.get('armies') or {}
    return {
        'cellFactions': dict(tactical.get('cellFactions') or {}),
        'generalOwners': dict(tactical.get('generalOwners') or {}),
        'armyFactions': {aid: a.get('faction') for aid, a in armies.items()},
        'armyStatus': {aid: a.get('status') for aid, a in armies.items()},
        'armyUnits': {aid: dict(a.get('units') or {}) for aid, a in armies.items()},
    }


def changed_parts(before, after):
    return sorted(k for k in before if before[k] != after[k])


def play(card, snapshot, base_state):
    """抽一張卡、換一份新快照上去、回應到結算完，回報現場的變化。"""
    card_id = card['id']
    post('/api/restore-shared-state',
         {'engine_state': prime_engine_state(base_state, card_id),
          'tactical': copy.deepcopy(snapshot)})
    applied = list((post('/api/next-turn',
                         {'active_player': 'F', 'force': True}).get('applied') or []))

    shared = get('/api/shared-state')
    view = (shared.get('engine_state') or {}).get('pending_events') or {}
    cards_in_flight = view.get('cards') or []
    drawn = cards_in_flight and cards_in_flight[int(view.get('index') or 0)].get('card_id')
    if drawn != card_id:
        return {'抽到了嗎': False, '抽到的是': drawn}

    # ★ 這一步就是那個競態：前端推一份**新的** dict 上來，
    #   伺服器換上它，引擎手上原本那份就作廢了。
    pushed = copy.deepcopy(shared['tactical'])
    pushed = post('/api/shared-state',
                  {'tactical': pushed, 'expected_revision': shared['revision']})['tactical']
    before = tactical_signature(pushed)

    guard = 0
    while guard < 24:
        guard += 1
        state = get('/api/shared-state')['engine_state']
        pending = state.get('pending_events') or {}
        entries = pending.get('cards') or []
        index = int(pending.get('index') or 0)
        if index >= len(entries):
            break
        entry = entries[index]
        if entry.get('card_id') != card_id:
            break
        options = ((card.get('resolution') or {}).get('options') or [])
        # 輪到誰，算法和後端 pending_event_view() 一樣：照 responders 的順序，
        # 挑第一個還沒回應的。這裡不能自己另外排一套順序——嚴格順序的卡會被擋。
        answered = entry.get('responses') or {}
        who = next((code for code in (entry.get('responders') or [])
                    if code not in answered), None)
        if who is None:
            who = next((code for code in ['F', 'W', 'S', 'N'] if code not in answered), None)
        if not who:
            break
        body = {'player': who}
        if options:
            body['choice'] = options[0]['id']
        try:
            applied += post('/api/respond-event', body).get('applied') or []
        except RuntimeError as exc:
            return {'抽到了嗎': True, '回應時炸了': str(exc)[:200]}

    after = tactical_signature(get('/api/shared-state')['tactical'])
    kinds = [str(a.get('kind')) for a in applied]
    settled = [k for k in kinds if k in KEYS]
    changed = changed_parts(before, after)
    # 這張卡真的結算了的機制，各自該動到的部分——一項都不能少。
    wanted = sorted({part for k in settled for part in EXPECTED_PARTS.get(k, [])})
    return {
        '抽到了嗎': True,
        '有沒有結算': bool(settled),
        '結算的 kind': settled,
        '有沒有 skipped': [k for k in kinds if k.endswith('_skipped')],
        '現場真的變了的部分': changed,
        '照機制該變而沒變的': [part for part in wanted if part not in changed],
    }


def main():
    proc = start_server()
    try:
        snapshot = npc_armies_from_map_js()
        base_state = get('/api/shared-state')['engine_state']
        rows = relevant_cards()
        results = {}
        for card, keys in rows:
            results[card['id']] = {'名稱': card.get('name'), '機制': keys,
                                   '結算方式': (card.get('resolution') or {}).get('type') or 'auto',
                                   **play(card, snapshot, base_state)}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()

    print(json.dumps(results, ensure_ascii=False, indent=1))
    print()
    bad = []
    for cid, row in results.items():
        problems = []
        if not row.get('抽到了嗎'):
            problems.append(f"沒抽到（抽到的是 {row.get('抽到的是')}）")
        elif row.get('回應時炸了'):
            problems.append("回應時炸了：" + row['回應時炸了'])
        else:
            if not row.get('有沒有結算'):
                problems.append("卡片沒有結算出任何一個相關機制")
            if row.get('有沒有 skipped'):
                problems.append("有 skipped：" + "、".join(row['有沒有 skipped']))
            if not row.get('現場真的變了的部分'):
                problems.append("**現場那份快照一格都沒變**——效果寫進孤兒了")
            elif row.get('照機制該變而沒變的'):
                problems.append("該動的部分沒動：" + "、".join(row['照機制該變而沒變的']))
        mark = '通過' if not problems else '**沒過**'
        print(f"  {mark}  {row['名稱']}（{cid}・{'/'.join(row['機制'])}）")
        for problem in problems:
            print(f"          {problem}")
        if problems:
            bad.append(cid)
    print()
    print(f"{len(results) - len(bad)}/{len(results)} 通過")
    return 1 if bad else 0


sys.exit(main())
