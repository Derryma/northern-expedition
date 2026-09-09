# -*- coding: utf-8 -*-
"""卡面 vs 實作 vs 畫面：全卡池三軸稽核（不判定，只出報告）。

第二十二批用來掃完 207 張事件卡 ＋ 90 張功能卡的那支工具。先前它只活在 /tmp，
方法寫進了 README 卻沒留下程式碼——下一個人要重跑就得整支重寫。放這裡。

三個軸：

  軸一 數字   卡面 `effect` 文字裡的每個數字，對照 payload 裡的每個數字。
              百分比會展開成 `p`／`1+p`／`1-p` 三種可能的存法，
              免得「文字寫 −15%、資料存 0.85」被誤報。
  軸二 具名   文字提到的城市／省份／鐵路／水域／銀行，對照 payload 的清單，
              兩個方向都看（文字有資料沒有、資料有文字沒提）。
  軸三 畫面   **實跑**：對每張卡開一局乾淨的引擎、套用它的 payload、
              比對前後的 snapshot()，列出它真正改了哪些鍵，
              再問 frontend/app.js 有沒有讀那個鍵。

三軸都只做「候選篩選」，最後仍然要人看。假警報很多是正常的——
軸一那 127 張裡真正的不一致只有 3 張。**不要把這支腳本的輸出當成結論。**

用法：

    python3 scripts/checks/card_effect_audit.py             # 三軸全跑
    python3 scripts/checks/card_effect_audit.py 畫面        # 只跑軸三
    python3 scripts/checks/card_effect_audit.py 數字 具名   # 挑幾軸
"""
import pathlib as _pathlib
REPO = _pathlib.Path(__file__).resolve().parents[2]

import json
import math
import re
import sys
import unicodedata
from collections import Counter

sys.path.insert(0, str(REPO))

EVENT_CARDS = REPO / "cards/data/event_cards.json"
FUNCTION_CARDS = REPO / "cards/data/function_cards.json"
STRATEGIC_MAP = REPO / "scenario/data/strategic_map.json"
BANKS = REPO / "economy/data/banks.json"
APP_JS = REPO / "frontend/app.js"

# 說明文字用的欄位，不是效果參數，掃描時一律跳過。
PROSE_KEYS = {"story", "effect", "effect_text", "name", "newspaper", "notes",
              "note", "id", "ref", "label", "text", "condition", "prompt",
              "background", "disruption_label"}


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def payloads_of(card):
    """一張事件卡真正會被套用的 payload：apply ＋ resolution 每個選項。

    效果藏在 resolution 裡的卡不少（12.58 南滿鐵路交涉的 apply 是空的），
    只看 apply 會整批漏掉。
    """
    out = {"apply": card.get("apply") or {}}
    for option in (card.get("resolution") or {}).get("options") or []:
        out[f'option:{option.get("id")}'] = option.get("apply") or {}
    if card.get("entry_condition"):
        out["entry_condition"] = card["entry_condition"]
    return out


def card_text(card):
    parts = [card.get("effect") or ""]
    for option in (card.get("resolution") or {}).get("options") or []:
        parts.append(option.get("effect_text") or "")
    return "\n".join(parts)


def card_payload(card, kind):
    if kind == "event":
        return payloads_of(card)
    return {k: v for k, v in card.items() if k not in PROSE_KEYS}


# ── 軸一：數字 ──────────────────────────────────────────────────────────
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def text_numbers(text):
    normalised = unicodedata.normalize("NFKC", text or "")
    for dash in "−–—":
        normalised = normalised.replace(dash, "-")
    out = []
    for match in NUMBER.finditer(normalised):
        value = float(match.group(0))
        out.append(value)
        if match.end() < len(normalised) and normalised[match.end()] == "%":
            # 百分比可能被存成 0.15 / 1.15 / 0.85 任何一種。
            out += [value / 100,
                    round(1 + value / 100, 6),
                    round(1 - value / 100, 6)]
    return out


def data_numbers(node, out=None):
    if out is None:
        out = []
    if isinstance(node, bool):
        return out
    if isinstance(node, (int, float)):
        out.append(float(node))
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in PROSE_KEYS:
                continue
            data_numbers(value, out)
    elif isinstance(node, list):
        for value in node:
            data_numbers(value, out)
    return out


def axis_numbers(cards, kind, label):
    rows = []
    for card in cards:
        text = card_text(card)
        found = set(data_numbers(card_payload(card, kind)))
        missing = sorted({n for n in text_numbers(text)
                          if n not in found and abs(n) > 0})
        if missing:
            rows.append((card.get("ref") or card["id"], card.get("name"), missing))
    print(f"\n【軸一・數字】{label}：{len(rows)}/{len(cards)} 張有「文字有、資料沒有」的數字")
    for ref, name, missing in rows:
        print(f"  [{ref}] {name} → {missing}")
    print("  ※ 多數是假警報：常數住在 foreign_punishment.py 之類的地方，或是"
          "文字寫百分比、資料存倍率的第四種寫法。逐張看過再下結論。")
    return rows


# ── 軸二：具名實體 ──────────────────────────────────────────────────────
def collect_strings(node, out=None):
    if out is None:
        out = set()
    if isinstance(node, str):
        out.add(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key in PROSE_KEYS:
                continue
            collect_strings(value, out)
    elif isinstance(node, list):
        for value in node:
            collect_strings(value, out)
    return out


def axis_entities(cards, kind, label):
    strategic = load(STRATEGIC_MAP)
    cities = {c["name"]: c["id"] for c in strategic["cities"]}
    provinces = sorted({c.get("province") for c in strategic["cities"] if c.get("province")})
    railways = sorted({r["name"] for r in strategic.get("railroads", [])})
    banks = {b["name"]: b["id"] for b in load(BANKS)["banks"]}
    waters = ["長江", "黃河", "珠江", "南海", "東海", "黃海", "渤海", "臺灣海峽"]

    rows = []
    for card in cards:
        text = card_text(card)
        values = collect_strings(card_payload(card, kind))
        problems = []
        for name, city_id in cities.items():
            if name in text and city_id not in values and name not in values:
                problems.append(f"城市「{name}」文字提到、資料沒有")
        for name, bank_id in banks.items():
            if name in text and bank_id not in values and name not in values:
                problems.append(f"銀行「{name}」文字提到、資料沒有")
        for kind_label, names in (("省份", provinces), ("鐵路", railways), ("水域", waters)):
            for name in names:
                if name in text and name not in values:
                    problems.append(f"{kind_label}「{name}」文字提到、資料沒有")
                if name in values and name not in text:
                    problems.append(f"{kind_label}「{name}」資料有、文字沒提")
        if problems:
            rows.append((card.get("ref") or card["id"], card.get("name"),
                         sorted(set(problems))))
    print(f"\n【軸二・具名】{label}：{len(rows)}/{len(cards)} 張有具名實體對不上")
    for ref, name, problems in rows:
        print(f"  [{ref}] {name}")
        for problem in problems:
            print(f"      - {problem}")
    print("  ※ 「資料有、文字沒提」常常是刻意的（爆破鐵路是隨機挑一條，"
          "所以資料列出全部候選）。看的是**範圍**對不對，不是字面。")
    return rows


# ── 軸三：效果有沒有出現在畫面上 ────────────────────────────────────────
# 比對 snapshot 時要跳過的鍵：抽牌序、回合日誌這些每次都會動，不是卡片效果。
VOLATILE_STATE = {"players", "counts", "turn_log", "event_pool", "pending_events",
                  "event_history", "event_draw_index", "last_action"}
VOLATILE_PLAYER = {"function_deck", "hand", "discard", "notifications",
                   "pending_frontend_effects"}


def flatten(state):
    out = {}
    for key, value in state.items():
        if key in VOLATILE_STATE:
            continue
        out[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    for payload in (state.get("players") or {}).values():
        for key, value in payload.items():
            if key in VOLATILE_PLAYER:
                continue
            name = f"players.{key}"
            out[name] = out.get(name, "") + json.dumps(
                value, ensure_ascii=False, sort_keys=True, default=str)
    return out


def axis_visible():
    from backend.card_engine import GameEngine

    app = APP_JS.read_text(encoding="utf-8")
    # 剝註解再找：要守的欄位名在解釋它的註解裡也常常有一份。
    app_code = "\n".join(re.sub(r"//.*$", "", line) for line in app.split("\n"))

    # 有些原始狀態鍵前端本來就不該直接讀——後端會把它解算成另一個欄位送出去，
    # 前端讀那個。這張表把「等價的出口」列出來，免得報告一直對著已經修好的
    # 東西喊狼來了。新增這種「後端解算、前端只讀結果」的欄位時，記得補一行。
    DERIVED_OUTLETS = {
        "perk_suspensions": "blocked_cards",          # 被事件按住的功能卡
        "action_bans": "blocked_actions",             # 被禁掉的訓練／造船／補兵
        "function_card_overrides": "card_field_changes",   # 卡片數字被改寫
        "player_card_overrides": "card_field_changes",
        "bank_bans": "bank_ban",                      # 借款面板上的停貸令
        "bank_limit_multipliers": "loan-offers",       # 額度直接算進 offers
        "loan_surcharges": "interest_per_turn",        # 加碼利率算進既有貸款
        "railway_effects": "railway_access",           # 停擺與理由
        "city_rebuilding": "city_punishment_status",
        "foreign_punishments": "foreign_punishments",
        "npc_combat_effects": "appliedModifiers",       # 戰鬥面板的加成清單
        "production_cost_multipliers": "resolved_recruit_costs",
        "province_recruit_discounts": "resolved_recruit_costs",
    }

    def frontend_reads(key):
        leaf = key.split(".")[-1]
        if leaf in app_code:
            return True
        outlet = DERIVED_OUTLETS.get(leaf)
        return bool(outlet) and outlet in app_code

    cards = load(EVENT_CARDS)["cards"]
    rows = []
    for card in cards:
        changed, errors = set(), []
        for tag, payload in payloads_of(card).items():
            if tag == "entry_condition" or not payload:
                continue
            engine = GameEngine(seed=7)
            before = flatten(engine.snapshot())
            try:
                engine._apply_event_payload(
                    payload, players=sorted(engine.state["players"]), card=card)
            except Exception as exc:                      # noqa: BLE001 — 報告用
                errors.append(f"{tag}: {type(exc).__name__}: {exc}")
                continue
            after = flatten(engine.snapshot())
            changed |= {k for k in set(before) | set(after)
                        if before.get(k) != after.get(k)}
        rows.append({"ref": card.get("ref"), "name": card.get("name"),
                     "changed": sorted(changed), "errors": errors})

    seen = Counter(k for row in rows for k in row["changed"])
    print("\n【軸三・畫面】被事件卡改動過的狀態鍵，以及前端讀不讀得到：")
    for key, count in seen.most_common():
        mark = "讀得到" if frontend_reads(key) else "**前端沒讀**"
        print(f"  {mark}  {key}（{count} 張卡）")

    blind = [r for r in rows
             if r["changed"] and not any(frontend_reads(k) for k in r["changed"])]
    print(f"\n  改動全部落在前端讀不到的鍵上的卡：{len(blind)}")
    for row in blind:
        print(f"    [{row['ref']}] {row['name']} → {row['changed']}")

    broken = [r for r in rows if r["errors"]]
    print(f"\n  套用時丟例外的卡：{len(broken)}")
    for row in broken:
        print(f"    [{row['ref']}] {row['name']}: {row['errors']}")

    print("  ※ 「前端沒讀」不等於缺陷：event_locks／scheduled_event_effects／"
          "unlocks 改的是**未來的抽牌機率**，當下畫面沒有東西可以動。")
    print("  ※ 15.x 那批 NPC 卡在這裡會顯示「一格狀態都沒動」，因為它們寫的是"
          "戰術快照（SHARED_TACTICAL_STATE），這支腳本沒有交快照進去。"
          "那一批由 faction_transfer_e2e.py 負責。")
    return rows


def main(argv):
    axes = set(argv[1:]) or {"數字", "具名", "畫面"}
    events = load(EVENT_CARDS)["cards"]
    functions = load(FUNCTION_CARDS)["cards"]
    print(f"事件卡 {len(events)} 張、功能卡 {len(functions)} 張")
    if "數字" in axes:
        axis_numbers(events, "event", "事件卡")
        axis_numbers(functions, "function", "功能卡")
    if "具名" in axes:
        axis_entities(events, "event", "事件卡")
        axis_entities(functions, "function", "功能卡")
    if "畫面" in axes:
        axis_visible()
    print("\n這支腳本不判定成敗，離開碼一律 0。結論要人看。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
