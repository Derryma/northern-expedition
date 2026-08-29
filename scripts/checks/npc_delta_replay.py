# -*- coding: utf-8 -*-
"""7 張 NPC 增兵卡，走完整的抽卡→讀報→回應流程，看部隊編制真的變了沒。

不是呼叫 _apply_event_payload 就算數——那是繞過抽卡閘門的近路。這裡要的是
next_turn 真的把卡抽出來、respond_event 真的結完，然後戰術快照上的數字變了。
"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import json, sys
sys.path.insert(0, REPO)
from backend.card_engine import GameEngine

ARMIES = {
    "Y-1": {"generalId": "yan_xishan", "units": {"infantry": 10}, "status": "active"},
    "Y-2": {"generalId": "fu_zuoyi", "units": {"infantry": 7}, "status": "active"},
    "Y-3": {"generalId": "xu_yongchang", "units": {"infantry": 6}, "status": "active"},
    "G-1": {"generalId": "feng_yuxiang", "units": {"infantry": 10}, "status": "active"},
    "G-2": {"generalId": "song_zheyuan", "units": {"infantry": 7}, "status": "active"},
    "G-3": {"generalId": "han_fuqu", "units": {"infantry": 6}, "status": "active"},
    "G-4": {"generalId": "lu_zhonglin", "units": {"infantry": 5}, "status": "active"},
    "M-1": {"generalId": "ma_qi", "units": {"cavalry": 4}, "status": "active"},
    "M-2": {"generalId": "ma_fuxiang", "units": {"cavalry": 3}, "status": "active"},
    "M-3": {"generalId": "ma_hongkui", "units": {"cavalry": 3}, "status": "active"},
    "C-1": {"generalId": "liu_xiang", "units": {"infantry": 9}, "status": "active"},
    "C-2": {"generalId": "liu_wenhui", "units": {"infantry": 7}, "status": "active"},
    "C-3": {"generalId": "yang_sen", "units": {"infantry": 6}, "status": "active"},
    "F-1": {"generalId": "chiang_kaishek", "units": {"infantry": 9}, "status": "active"},
}

CARDS = ["feng_yuxiang_wuyuan_oath", "northwest_soviet_aid", "liu_xiang_expands",
         "ma_clique_expands", "jinsui_army_expands", "yang_sen_expands",
         "liu_wenhui_expands"]


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
    before = {k: dict(v["units"]) for k, v in snapshot["armies"].items()}

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

    after = {k: dict(v["units"]) for k, v in snapshot["armies"].items()}
    moved = {k: {u: after[k].get(u, 0) - before[k].get(u, 0)
                 for u in set(before[k]) | set(after[k])
                 if after[k].get(u, 0) != before[k].get(u, 0)}
             for k in before if after[k] != before[k]}
    queued = [e for p in engine.state["players"].values()
              for e in (p.get("pending_frontend_effects") or [])
              if e["kind"] == "npc_army_units"]
    return {"抽到了": True, "後端快照的變動": moved,
            "掛給前端的佇列筆數": len(queued),
            "佇列裡的部隊數": sum(len(e["armies"]) for e in queued),
            "佇列與快照一致": all(
                snapshot["armies"][a["armyId"]]["units"] == a["units"]
                for e in queued for a in e["armies"])}


out = {}
for card_id in CARDS:
    engine = GameEngine(seed=3)
    ref = engine._event_template(card_id)["ref"]
    try:
        out[f"{ref} {engine._event_template(card_id)['name']}"] = run(card_id)
    except Exception as exc:
        out[f"{ref} {card_id}"] = {"__炸了__": f"{type(exc).__name__}: {exc}"}
print(json.dumps(out, ensure_ascii=False, indent=1))
