# -*- coding: utf-8 -*-
"""批次四：五張陣營級結構變動的卡，走完整的抽卡→讀報→回應流程。

這一批動的是地盤與陣營存續，所以除了「效果有沒有發生」之外還要看兩件事：
被併吞的陣營是不是真的退場了，以及城市歸屬是不是真的換手了。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import json, sys
sys.path.insert(0, REPO)
from backend.card_engine import GameEngine

ARMIES = {
    "Y-1": {"generalId": "yan_xishan", "units": {"infantry": 10}, "status": "active"},
    "G-1": {"generalId": "feng_yuxiang", "units": {"infantry": 10}, "status": "active"},
    "M-1": {"generalId": "ma_qi", "units": {"cavalry": 4}, "status": "active"},
    "M-2": {"generalId": "ma_fuxiang", "units": {"cavalry": 3}, "status": "active"},
    "M-3": {"generalId": "ma_hongkui", "units": {"cavalry": 3}, "status": "active"},
    "Q-1": {"generalId": "qian_local_militia", "units": {"infantry": 5, "artillery": 1},
            "status": "active"},
    "C-1": {"generalId": "liu_xiang", "units": {"infantry": 9}, "status": "active"},
    "C-2": {"generalId": "liu_wenhui", "units": {"infantry": 7}, "status": "active"},
    "F-1": {"generalId": "zhang_zuolin", "units": {"infantry": 30}, "status": "active"},
    "W-1": {"generalId": "wu_peifu", "units": {"infantry": 20}, "status": "active"},
}
CARDS = ["yan_xishan_blocks_narrow_gauge", "northwest_allies_ma_clique",
         "ma_clique_submits", "liu_xiang_annexes_qian", "liu_wenhui_annexes_qian"]


def tactical():
    return {"armies": {k: {**v, "units": dict(v["units"])} for k, v in ARMIES.items()},
            "generalOwners": {}, "generalTrees": {}, "jailedGenerals": []}


def run(card_id):
    engine = GameEngine(seed=3)
    for payload in engine.state["players"].values():
        payload["treasury"] = 500
    engine.state["turn"] = 2
    engine.state["event_pool"] = [card_id]
    engine.state["city_owners"]["zhangjiakou"] = "G"     # 15.5 的進入條件
    snapshot = tactical()
    owners_before = dict(engine.state["city_owners"])

    engine.next_turn(active_player="F", tactical=snapshot)
    view = engine.pending_event_view()
    if not view or view["card"]["id"] != card_id:
        return {"抽到了": False, "實際抽到": (view or {}).get("card", {}).get("id")}
    for _ in range(24):
        view = engine.pending_event_view()
        if not view:
            break
        who = view.get("waiting_for") or view.get("drawer")
        if not who:
            break
        options = (view["card"].get("resolution") or {}).get("options") or []
        engine.respond_event(who, choice=options[0]["id"] if options else None)

    changed_cities = {c: owner for c, owner in engine.state["city_owners"].items()
                      if owners_before.get(c) != owner}
    flags = {aid: a.get("faction") for aid, a in snapshot["armies"].items() if a.get("faction")}
    return {
        "抽到了": True,
        "停運的鐵路": engine.disabled_railways(),
        "退出地圖的陣營": sorted(engine.retired_npc_factions()),
        "換手的城市": changed_cities,
        "改掛旗的部隊": flags,
        "併吞後的編制": {aid: a["units"] for aid, a in snapshot["armies"].items()
                   if a.get("status") == "merged" or aid in ("C-1", "C-2")},
        "交辦給前端": sorted({e["kind"] for p in engine.state["players"].values()
                        for e in (p.get("pending_frontend_effects") or [])}),
    }


out = {}
base = GameEngine(seed=3)
for card_id in CARDS:
    card = base._event_template(card_id)
    try:
        out[f'{card["ref"]} {card["name"]}'] = run(card_id)
    except Exception as exc:
        out[f'{card["ref"]} {card_id}'] = {"__炸了__": f"{type(exc).__name__}: {exc}"}
print(json.dumps(out, ensure_ascii=False, indent=1))
