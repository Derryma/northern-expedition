# -*- coding: utf-8 -*-
"""7 張「戰力 ±x%」的卡，走完整的抽卡→讀報→回應流程，看戰力點真的變了沒。

呼叫 _apply_event_payload 是繞過抽卡閘門的近路，不算數。這裡要的是
next_turn 真的把卡抽出來、respond_event 真的結完，戰術快照上的戰力點才算變了。
"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import json, sys
sys.path.insert(0, REPO)
from backend.card_engine import GameEngine, UNIT_FORCE_POINTS

ARMIES = {
    "G-1": {"generalId": "feng_yuxiang", "units": {"infantry": 10, "cavalry": 2,
                                                   "machine_gun": 2, "artillery": 1},
            "status": "active"},
    "G-2": {"generalId": "song_zheyuan", "units": {"infantry": 8}, "status": "active"},
    "G-3": {"generalId": "han_fuqu", "units": {"infantry": 6}, "status": "active"},
    "G-4": {"generalId": "lu_zhonglin", "units": {"infantry": 7}, "status": "active"},
    "Y-1": {"generalId": "yan_xishan", "units": {"infantry": 10}, "status": "active"},
    "Y-2": {"generalId": "fu_zuoyi", "units": {"infantry": 5}, "status": "active"},
    "Y-3": {"generalId": "xu_yongchang", "units": {"infantry": 6}, "status": "active"},
    "H-1": {"generalId": "tang_shengzhi", "units": {"infantry": 12, "artillery": 2},
            "status": "active"},
    "H-2": {"generalId": "zhao_hengti", "units": {"infantry": 10}, "status": "active"},
    "H-3": {"generalId": "he_jian", "units": {"infantry": 8}, "status": "active"},
    "C-1": {"generalId": "liu_xiang", "units": {"infantry": 9}, "status": "active"},
    "C-2": {"generalId": "liu_wenhui", "units": {"infantry": 10}, "status": "active"},
    "C-3": {"generalId": "yang_sen", "units": {"infantry": 9, "artillery": 1},
            "status": "active"},
    "D-1": {"generalId": "tang_jiyao", "units": {"infantry": 10}, "status": "active"},
    "D-2": {"generalId": "long_yun", "units": {"infantry": 6}, "status": "active"},
    "F-1": {"generalId": "chiang_kaishek", "units": {"infantry": 20}, "status": "active"},
}

CARDS = ["northwest_jin_war", "sichuan_internal_war", "tang_jiyao_shaken",
         "wanxian_incident", "powers_punish_soviet_proxy",
         "zhao_hengti_provincial_constitution"]


def force(units):
    return sum(max(0, int(units.get(u) or 0)) * p for u, p in UNIT_FORCE_POINTS.items())


def tactical():
    return {"armies": {k: {**v, "units": dict(v["units"])} for k, v in ARMIES.items()},
            "generalOwners": {}, "generalTrees": {}, "jailedGenerals": []}


def run(card_id):
    engine = GameEngine(seed=3)
    for payload in engine.state["players"].values():
        payload["treasury"] = 500
    engine.state["turn"] = 2
    engine.state["event_pool"] = [card_id]
    snapshot = tactical()
    before = {k: force(v["units"]) for k, v in snapshot["armies"].items()}

    engine.next_turn(active_player="F", tactical=snapshot)
    view = engine.pending_event_view()
    if not view or view["card"]["id"] != card_id:
        return {"抽到了": False, "實際抽到": (view or {}).get("card", {}).get("id")}

    guard = 0
    while view and guard < 24:
        guard += 1
        options = (view["card"].get("resolution") or {}).get("options") or []
        who = view.get("waiting_for") or view.get("drawer")
        if not who:
            break
        engine.respond_event(who, choice=options[0].get("id") if options else None)
        view = engine.pending_event_view()

    after = {k: force(v["units"]) for k, v in snapshot["armies"].items()}
    moved = {k: f"{before[k]} → {after[k]}（{(after[k] / before[k] - 1) * 100:+.0f}%）"
             for k in before if after[k] != before[k]}
    queued = [e for p in engine.state["players"].values()
              for e in (p.get("pending_frontend_effects") or [])
              if e["kind"] == "npc_army_units"]
    return {"抽到了": True, "戰力點變動": moved,
            "玩家部隊沒動": before["F-1"] == after["F-1"],
            "掛給前端的佇列筆數": len(queued),
            "佇列與快照一致": all(
                snapshot["armies"][a["armyId"]]["units"] == a["units"]
                for e in queued for a in e["armies"])}


out = {}
base = GameEngine(seed=3)
for card_id in CARDS:
    card = base._event_template(card_id)
    try:
        out[f"{card['ref']} {card['name']}"] = run(card_id)
    except Exception as exc:
        out[f"{card['ref']} {card_id}"] = {"__炸了__": f"{type(exc).__name__}: {exc}"}
print(json.dumps(out, ensure_ascii=False, indent=1))
