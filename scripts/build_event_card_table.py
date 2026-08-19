"""由 cards/data/event_cards.json 產生 cards/README.md 裡的「五九張事件卡逐張明細」。

README 那一段夾在 `<!-- EVENT-TABLE:BEGIN -->` 與 `<!-- EVENT-TABLE:END -->` 之間，
內容一律由這支程式產生，不要手改——改了下次跑就被蓋掉，而且
`test_event_card_table_matches_the_data` 會先讓你紅掉。

用法：
    python3 scripts/build_event_card_table.py          # 就地更新 README
    python3 scripts/build_event_card_table.py --check   # 只檢查是否同步，不寫檔
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "cards" / "data" / "event_cards.json"
README = REPO / "cards" / "README.md"
BEGIN = "<!-- EVENT-TABLE:BEGIN -->"
END = "<!-- EVENT-TABLE:END -->"
STORY_DATA = REPO / "cards" / "data" / "function_cards.json"
STORY_BEGIN = "<!-- STORY-TABLE:BEGIN -->"
STORY_END = "<!-- STORY-TABLE:END -->"

SECTIONS = {
    1: "一、政治", 2: "二、外交", 3: "三、文化", 4: "四、藝術",
    5: "五、體育", 6: "六、商業", 7: "七、學術", 8: "八、科技",
    9: "九、中國藝文界", 10: "十、中國學術界", 11: "十一、中國商業界",
    12: "十二、列強懲戒（可重複抽取）",
}

CATEGORY = {
    "foreign_power": "列強行動",
    "economic": "經濟事件",
    "npc_or_other_force": "其他勢力",
    "security": "治安事件",
}

POWER = {"uk": "英", "us": "美", "fr": "法", "de": "德",
         "jp": "日", "su": "蘇", "it": "義"}


def _city_names() -> dict:
    """城市 id → 中文名。表格給人看，不該印 `beijing` 這種內部代號。"""
    path = REPO / "scenario" / "data" / "strategic_map.json"
    cities = json.loads(path.read_text(encoding="utf-8"))["cities"]
    return {c["id"]: c["name"] for c in cities}


CITY_NAMES = _city_names()


def _frontend_handled() -> set:
    """`applyFrontendEventEffects()` 親自處理的卡。

    有些效果後端碰不到（部隊編制、將領忠誠、強制撤退），由前端在玩家按下
    「我知道了」之後補完。這些卡的 `apply` 只有 notes，但它們**不是**要玩家
    自己動手——照抄後端有沒有機械化效果來判斷會誤標，所以這裡直接去 app.js
    把它處理的卡號抓出來。
    """
    import re
    source = (REPO / "frontend" / "app.js").read_text(encoding="utf-8")
    start = source.index("function applyFrontendEventEffects(")
    depth, i, seen = 0, start, False
    while i < len(source):
        if source[i] == "{":
            depth += 1
            seen = True
        elif source[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    body = source[start:i + 1]
    return set(re.findall(r'cardId === "([a-z0-9_]+)"', body))


FRONTEND_CARDS = _frontend_handled()


def cell(text: str) -> str:
    """把一段文字塞進 Markdown 表格欄位：換行改成 <br>，直線要跳脫。"""
    return (str(text or "")
            .replace("|", "\\|")
            .replace("\n", "<br>")
            .strip())


def entry_condition_text(card: dict) -> str:
    ec = card.get("entry_condition") or {}
    if not ec:
        return "—"
    bits = []
    if ec.get("controls_province"):
        bits.append(f'完全控制{ec["controls_province"]}')
    cities = [CITY_NAMES.get(c, c) for c in (ec.get("controls_cities_any") or [])]
    if len(cities) == 1:
        bits.append(f"控制{cities[0]}")
    elif cities:
        bits.append("控制" + "或".join(cities))
    for power, value in (ec.get("relation_min") or {}).items():
        bits.append(f'對{POWER.get(power, power)}關係 ≥{value}')
    for power, value in (ec.get("relation_max") or {}).items():
        bits.append(f'對{POWER.get(power, power)}關係 ≤{value}')
    provinces_any = ec.get("controls_provinces_any") or []
    if provinces_any:
        bits.insert(0, "控制" + "或".join(provinces_any) + "其中一省")
    return "，且".join(bits) if bits else "—"


def resolution_text(card: dict) -> str:
    res = card.get("resolution") or {}
    kind = res.get("type")
    if kind == "choice":
        labels = "／".join(o.get("label", o.get("id", "")) for o in (res.get("options") or []))
        scope = res.get("scope", "all_players")
        who = "四家各自表態" if scope == "all_players" else "抽到的一家表態"
        return f"**{who}**：{labels}"
    return "閱報即可"


IGNORE_KEYS = {"notes", "pending"}


def _collect(card: dict) -> tuple:
    """把整張卡的機械化效果與待辦收齊。

    效果不只掛在最上層 `apply`——表態卡（2.3 亞克斯、2.5 非戰公約、7.3 殷墟、
    11.3 裁兵）的效果全在 `resolution.options[].apply` 底下，連同 follow_up。
    只看最上層會把這幾張誤判成「純敘事」，那是錯的。
    """
    mechanised, pending = [], []

    def walk(block):
        if not isinstance(block, dict):
            return
        for key, value in block.items():
            if key == "pending" and isinstance(value, list):
                pending.extend(value)
            elif key not in IGNORE_KEYS:
                mechanised.append(key)
            if isinstance(value, (dict, list)):
                for item in (value if isinstance(value, list) else [value]):
                    if isinstance(item, dict) and ("pending" in item or "apply" in item):
                        walk(item.get("apply") if "apply" in item else item)

    walk(card.get("apply") or {})
    for option in ((card.get("resolution") or {}).get("options") or []):
        walk(option.get("apply") or {})
        for sub in ((option.get("follow_up") or {}).get("options") or []):
            walk(sub.get("apply") or {})
    return mechanised, pending


def automation_text(card: dict) -> str:
    """誠實回報這張卡有多少是自動跑的、哪些真的還沒接上。

    分類依據是 `apply.pending`——那是「確實還沒自動化」的清單。
    `apply.notes` 只是說明機制怎麼運作，**不代表要玩家自己動手**，
    先前把兩者混為一談，害 9.5、10.1 這種全自動的卡被標成需人工。
    """
    mechanised, pending = _collect(card)
    front = card["id"] in FRONTEND_CARDS
    if not mechanised and not pending:
        return "無機械化效果（純敘事）"
    if not pending:
        return "全自動" + ("（後端 ＋ 前端）" if front else "")
    detail = cell("；".join(pending))
    prefix = "全自動（後端 ＋ 前端）" if front else "已自動化"
    return f"{prefix}，惟以下部分**待卡片建檔後才會生效**：{detail}"


def build() -> str:
    cards = json.loads(DATA.read_text(encoding="utf-8"))["cards"]
    by_section: dict[int, list] = {}
    for card in cards:
        by_section.setdefault(int(str(card["ref"]).split(".")[0]), []).append(card)

    partial = [c["ref"] for c in cards if _collect(c)[1]]
    frontend = [c["ref"] for c in cards if c["id"] in FRONTEND_CARDS]
    choice = [c["ref"] for c in cards
              if (c.get("resolution") or {}).get("type") == "choice"]
    gated = [c["ref"] for c in cards if c.get("entry_condition")]

    out = [BEGIN, "", "### 五九張事件卡逐張明細", "",
           "下面十一張表由 `scripts/build_event_card_table.py` 從 `data/event_cards.json`",
           "產生，**不要手改**——改了下次跑就被蓋掉，而且",
           "`test_event_card_table_matches_the_data` 會先讓你紅掉。改卡片請改資料檔，",
           "再跑一次 `python3 scripts/build_event_card_table.py`。", "",
           "欄位說明：", "",
           "- **進入條件**：不滿足就不會進事件卡池，也就抽不到。共 "
           f"{len(gated)} 張有條件（{'、'.join(gated)}）。",
           "- **結算方式**：多數卡是閱報即可；`choice` 卡要表態，"
           f"其中 {len(choice)} 張（{'、'.join(choice)}）是**四家各自表態、各自結算**。",
           "- **實作狀態**：機制**全部自動化**，沒有任何一張要玩家自己動手。"
           f"其中 {len(frontend)} 張（{'、'.join(frontend)}）的效果後端碰不到"
           "（部隊編制、將領忠誠、強制撤退），由前端 `applyFrontendEventEffects()` 補完，"
           "算在全自動裡。"
           f"另有 {len(partial)} 張（{'、'.join(partial)}）機制已建好但**目標卡尚未建檔**"
           "（[軍事]／[幫會] 標籤的卡還沒收錄），所以現階段空轉——"
           "那批卡進資料檔就自動生效，不必再改程式。", ""]

    for index in sorted(by_section):
        out.append(f"#### {SECTIONS[index]}（{len(by_section[index])} 張）")
        out.append("")
        out.append("| 編號 | 卡名 | 類別 | 進入條件 | 結算方式 | 效果 | 實作狀態 |")
        out.append("| ---: | --- | --- | --- | --- | --- | --- |")
        for card in sorted(by_section[index],
                           key=lambda c: [int(x) for x in str(c["ref"]).split(".")]):
            note = card.get("power_note")
            category = CATEGORY.get(card.get("category"), card.get("category", ""))
            if note:
                category += f"（{note}）"
            out.append("| {ref} | {name} | {cat} | {entry} | {res} | {effect} | {auto} |".format(
                ref=card["ref"],
                name=cell(card["name"]),
                cat=cell(category),
                entry=cell(entry_condition_text(card)),
                res=cell(resolution_text(card)),
                effect=cell(card.get("effect")),
                auto=automation_text(card),
            ))
        out.append("")
    out.append(END)
    return "\n".join(out)


def build_story_table() -> str:
    """功能卡的故事表。

    這張表原本是手寫的，於是〈票號金融網〉加進資料檔之後就沒人補上去——
    卡面有故事、README 卻查不到。改成從 function_cards.json 產生。
    """
    cards = json.loads(STORY_DATA.read_text(encoding="utf-8"))["cards"]
    told = [c for c in cards if (c.get("story") or "").strip()]
    out = [STORY_BEGIN, "",
           f"目前 **{len(told)}** 張卡帶有 `story`，全文如下；此表由",
           "`scripts/build_event_card_table.py` 從 `data/function_cards.json` 產生，不要手改。",
           "故事只影響卡面呈現，不影響任何判定。", "",
           "| 卡片 | 故事 |", "| --- | --- |"]
    for card in told:
        out.append(f'| {cell(card["name"])} | {cell(card["story"])} |')
    out += ["", STORY_END]
    return "\n".join(out)


def _replace(text: str, begin: str, end: str, body: str) -> str:
    head, rest = text.split(begin, 1)
    _, tail = rest.split(end, 1)
    return head + body + tail


def main() -> int:
    text = README.read_text(encoding="utf-8")
    if BEGIN not in text or END not in text:
        print(f"README 裡找不到 {BEGIN} / {END} 標記", file=sys.stderr)
        return 2
    if STORY_BEGIN not in text or STORY_END not in text:
        print(f"README 裡找不到 {STORY_BEGIN} / {STORY_END} 標記", file=sys.stderr)
        return 2
    updated = _replace(text, BEGIN, END, build())
    updated = _replace(updated, STORY_BEGIN, STORY_END, build_story_table())
    if "--check" in sys.argv:
        if updated != text:
            print("README 的產生區塊與資料檔不同步，請跑："
                  " python3 scripts/build_event_card_table.py", file=sys.stderr)
            return 1
        print("同步")
        return 0
    README.write_text(updated, encoding="utf-8")
    print(f"已更新 {README.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
