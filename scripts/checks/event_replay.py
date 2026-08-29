# -*- coding: utf-8 -*-
"""逐張把每一張事件卡真的抽出來、真的回應完，看有沒有炸掉或完全不動後端。

判準不是「程式碼看起來有沒有處理」，而是「回應完之後 snapshot 差在哪」。
"""

import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死 /tmp/ne——
# 換一個容器、換一台機器都還跑得動。
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import json, os, sys
from copy import deepcopy

ROOT = os.environ.get("NE_ROOT", REPO)
sys.path.insert(0, ROOT)
from backend.card_engine import GameEngine   # noqa: E402

NOISE_PLAYER = {"hand", "discard", "function_deck", "pending_draw",
                "function_purchase_count", "function_purchase_used", "notifications"}
NOISE_TOP = {"last_action", "counts", "turn", "event_pool", "pending_events",
             "turn_log", "event_log", "newspaper"}


def strip(state):
    s = deepcopy(state)
    for k in NOISE_TOP:
        s.pop(k, None)
    for payload in (s.get("players") or {}).values():
        for k in NOISE_PLAYER:
            payload.pop(k, None)
    return s


def diff_keys(a, b, prefix=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in set(a) | set(b):
            out += diff_keys(a.get(k), b.get(k), f"{prefix}.{k}" if prefix else str(k))
    elif a != b:
        out.append(prefix)
    return out


def fresh():
    e = GameEngine(seed=3)
    for code, p in e.state["players"].items():
        p["treasury"] = 500
        p["factory_points"] = 500
        for pw in ("jp", "uk", "us", "fr", "su", "de"):
            p.setdefault("foreign_relations", {})[pw] = 6
    e.state["marshal_ids"] = {"F": "zhang_zuolin", "W": "wu_peifu",
                              "S": "sun_chuanfang", "N": "chiang_kai_shek"}
    e.state["turn"] = 2
    return e


def play(card_id):
    """把一張事件卡塞進池子、跑完回合、把四張都回應掉。"""
    e = fresh()
    e.state["event_pool"] = [card_id]
    before = strip(e.snapshot())
    e.next_turn(active_player="F")
    view = e.pending_event_view()
    if not view:
        return {"drawn": False, "changed": diff_keys(before, strip(e.snapshot())), "errors": []}
    if view["card"]["id"] != card_id:
        return {"drawn": False, "note": f'抽到的是 {view["card"]["id"]}', "errors": []}
    errors = []
    guard = 0
    while view and guard < 24:
        guard += 1
        resolution = view["card"].get("resolution") or {}
        options = resolution.get("options") or []
        choice = options[0].get("id") if options else None
        who = view.get("waiting_for") or view.get("drawer")
        if not who:
            break
        try:
            e.respond_event(who, choice=choice)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            break
        view = e.pending_event_view()
    return {"drawn": True, "changed": diff_keys(before, strip(e.snapshot())),
            "errors": errors}


base = fresh()
cards = (base.data.get("event_cards") or {}).get("cards", [])
rows = []
for card in cards:
    cid = card["id"]
    try:
        result = play(cid)
    except Exception as exc:
        result = {"drawn": False, "errors": [f"{type(exc).__name__}: {exc}"], "changed": []}
    rows.append({"id": cid, "name": card.get("name"),
                 "section": card.get("section"), **result})

crashed = [r for r in rows if r.get("errors")]
undrawn = [r for r in rows if not r.get("drawn") and not r.get("errors")]
inert = [r for r in rows if r.get("drawn") and not r.get("changed") and not r.get("errors")]
ok = [r for r in rows if r.get("drawn") and r.get("changed") and not r.get("errors")]

summary = {"total": len(rows), "ok": len(ok), "inert": len(inert),
           "undrawn": len(undrawn), "crashed": len(crashed)}
print(json.dumps(summary, ensure_ascii=False))
out = {"summary": summary,
       "crashed": [{"id": r["id"], "name": r["name"], "errors": r["errors"][:2]} for r in crashed],
       "inert": [{"id": r["id"], "name": r["name"]} for r in inert],
       "undrawn": [{"id": r["id"], "name": r["name"], "note": r.get("note")} for r in undrawn],
       "changed_by_card": {r["id"]: sorted(r["changed"]) for r in rows}}
dest = os.environ.get("NE_OUT", "/tmp/event_replay_now.json")
with open(dest, "w", encoding="utf-8") as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print("→", dest)
