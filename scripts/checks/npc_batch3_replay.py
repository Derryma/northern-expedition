# -*- coding: utf-8 -*-
"""批次二 B 與批次三：走完整的抽卡→讀報→回應流程，看效果真的落地沒。

呼叫 _apply_event_payload 是繞過抽卡閘門與回應流程的近路，不算數。
競標招募尤其要走真流程——它的結算點在「所有人都回應完」之後，
繞過去就驗不到那個時機對不對。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import json, sys
sys.path.insert(0, REPO)
from backend.card_engine import GameEngine

ARMIES = {
    "Y-1": {"generalId": "yan_xishan", "units": {"infantry": 10}, "status": "active"},
    "Y-2": {"generalId": "fu_zuoyi", "units": {"infantry": 8}, "status": "active"},
    "Y-3": {"generalId": "xu_yongchang", "units": {"infantry": 6}, "status": "active"},
    "G-1": {"generalId": "feng_yuxiang", "units": {"infantry": 10}, "status": "active"},
    "G-2": {"generalId": "song_zheyuan", "units": {"infantry": 7}, "status": "active"},
    "G-3": {"generalId": "han_fuqu", "units": {"infantry": 6}, "status": "active"},
    "H-1": {"generalId": "tang_shengzhi", "units": {"infantry": 12}, "status": "active"},
    "H-2": {"generalId": "zhao_hengti", "units": {"infantry": 10}, "status": "active"},
    "H-3": {"generalId": "he_jian", "units": {"infantry": 8}, "status": "active"},
    "C-1": {"generalId": "liu_xiang", "units": {"infantry": 9}, "status": "active"},
    "D-2": {"generalId": "long_yun", "units": {"infantry": 6}, "status": "active"},
}
MODIFIER_CARDS = ["fu_zuoyi_fortifies", "xu_yongchang_reorganises",
                  "song_zheyuan_broadsword_corps", "he_jian_holds_south_hunan"]
RECRUIT_CARDS = ["tang_shengzhi_seeks_help", "long_yun_coup_brewing",
                 "liu_xiang_denounces_zhili", "han_fuju_defects_to_nanjing"]


def tactical():
    return {"armies": {k: {**v, "units": dict(v["units"])} for k, v in ARMIES.items()},
            "generalOwners": {}, "generalTrees": {}, "jailedGenerals": []}


def setup(card_id):
    engine = GameEngine(seed=3)
    for payload in engine.state["players"].values():
        payload["treasury"] = 500
        for power in ("jp", "uk", "us", "fr", "su", "de"):
            payload.setdefault("foreign_relations", {})[power] = 6
    engine.state["turn"] = 2
    engine.state["event_pool"] = [card_id]
    # 讓每一張的進入條件都成立
    for city in ("hankou", "guangzhou", "nanjing"):
        engine.state["city_owners"][city] = "F"
    for province_city in engine.data["strategic_map"]["cities"]:
        if province_city.get("province") in ("廣西", "貴州"):
            engine.state["city_owners"][province_city["id"]] = "F"
    for a, b in (("F", "W"), ("W", "F")):
        engine.state["players"][a].setdefault("warlord_relations", {})[b] = {"status": "war"}
    return engine


def drive(engine, snapshot, card_id, choice_for):
    engine.next_turn(active_player="F", tactical=snapshot,
                     city_garrison_report={"nanjing": {"F": 5}})
    view = engine.pending_event_view()
    if not view or view["card"]["id"] != card_id:
        return {"抽到了": False, "實際抽到": (view or {}).get("card", {}).get("id")}
    responded = []
    for _ in range(24):
        view = engine.pending_event_view()
        if not view:
            break
        who = view.get("waiting_for") or view.get("drawer")
        if not who:
            break
        options = (view["card"].get("resolution") or {}).get("options") or []
        pick = choice_for(who, options) if options else None
        engine.respond_event(who, choice=pick)
        responded.append(f"{who}:{pick or '閱報'}")
    return {"抽到了": True, "回應": responded}


out = {}
base = GameEngine(seed=3)

for card_id in MODIFIER_CARDS:
    card = base._event_template(card_id)
    engine = setup(card_id)
    snapshot = tactical()
    result = drive(engine, snapshot, card_id, lambda who, opts: opts[0]["id"])
    effects = engine.state.get("npc_combat_effects") or []
    result["掛上的效果"] = [{"陣營": e["faction"], "將領": e["general_id"],
                       "回合": e["remaining_turns"],
                       "離場為止": e["until_general_leaves"],
                       "修正": e["modifiers"]} for e in effects]
    out[f'{card["ref"]} {card["name"]}'] = result

for card_id in RECRUIT_CARDS:
    card = base._event_template(card_id)
    engine = setup(card_id)
    snapshot = tactical()
    before = {code: engine.state["players"][code]["treasury"] for code in engine.state["players"]}
    # F 與 W 都出價，其餘不出：驗多方競標
    result = drive(engine, snapshot, card_id,
                   lambda who, opts: "recruit" if who in ("F", "W") else "decline")
    after = {code: engine.state["players"][code]["treasury"] for code in engine.state["players"]}
    result["現金變動"] = {k: after[k] - before[k] for k in before if after[k] != before[k]}
    moved = {aid: a.get("faction") for aid, a in snapshot["armies"].items() if a.get("faction")}
    result["改掛旗的部隊"] = moved
    result["交辦給前端"] = [e["general"] + "→" + e["owner"]
                      for code in engine.state["players"]
                      for e in engine.state["players"][code]["pending_frontend_effects"]
                      if e["kind"] == "npc_general_recruited"]
    out[f'{card["ref"]} {card["name"]}'] = result

print(json.dumps(out, ensure_ascii=False, indent=1))
