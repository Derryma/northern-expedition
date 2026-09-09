# -*- coding: utf-8 -*-
"""「後端知道、玩家看不到」這一輪的突變測試。

判定器：
  * backend.test_backend.WorldVisibilityTests——守後端那一半（蓋 active、
    送出封鎖名單、無主城市由 city_owners 算出來）；
  * scripts/checks/world_visibility_e2e.py——真前端：持續效果面板列不列得出
    永久停擺、按鈕關不關得掉、無主城市畫不畫得成中立。

只跑其中一個會有突變體逃掉：前端那幾個改動單元測試看不到，
後端那幾個 e2e 只看得到症狀、分不出是哪一段壞的。
"""
import pathlib as _pathlib
import sys
sys.path.insert(0, str(_pathlib.Path(__file__).resolve().parent))
from mutate_safe import main

RUNNER = ['bash', '-lc',
          'python3 -m unittest backend.test_backend.WorldVisibilityTests '
          'backend.test_backend.EffectsReachThePlayerTests '
          'backend.test_backend.OccupationVersusDrillStateTests -q '
          '&& python3 scripts/checks/world_visibility_e2e.py']
APP = 'frontend/app.js'
ENG = 'backend/card_engine.py'
PUN = 'backend/foreign_punishment.py'
MOD = 'backend/combat_modifiers.py'
CARDS = 'cards/data/event_cards.json'

sys.exit(main([
    ("W1 永久又被當成過期（remaining_turns 為 None 一律判成結束）",
     "        if effect.get(\"permanent\"):\n"
     "            return True\n"
     "        remaining = effect.get(\"remaining_turns\")\n"
     "        if remaining is None:\n"
     "            return True\n"
     "        return int(remaining or 0) > 0",
     "        return int(effect.get(\"remaining_turns\") or 0) > 0", ENG),

    ("W2 後端不再替限時效果蓋 active（前端只好又自己判）",
     "        self._stamp_effect_activity(state)",
     "        pass", ENG),

    ("W3 前端 effectActive 又自己算一次 remaining_turns",
     "  if (effect.active !== undefined) return Boolean(effect.active);",
     "  if (true) return Number(effect.remaining_turns || 0) > 0;", APP),

    ("W4 持續效果面板又從 railway_effects 自己篩（永久停擺整筆消失）",
     "  const railways = [...disabledRailways()];",
     "  const railways = (state.railway_effects || [])\n"
     "    .filter((effect) => Number(effect.remaining_turns || 0) > 0)\n"
     "    .map((effect) => effect.railway);", APP),

    ("W5 永久封鎖又被寫成「搶修中」（面板不讀後端給的理由）",
     "    ${railways.map((name) => `<span>${railwayStatusLabel(name)}</span>`).join(\"\")}",
     "    ${railways.map((name) => `<span>${name} 搶修中</span>`).join(\"\")}", APP),

    ("W6 被事件按住的卡不再送出去（畫面無從得知）",
     "            payload[\"blocked_cards\"] = self.blocked_cards(player)",
     "            payload[\"blocked_cards\"] = {}", ENG),

    ("W7 手牌的「打出」鈕又不關（按下去才知道打不出來）",
     "              blocked ? ` disabled title=\"${blocked}\"` : \"\"}>打出</button>`}",
     "              \"\"}>打出</button>`}", APP),

    ("W8 被禁掉的行動不再送出去",
     "            payload[\"blocked_actions\"] = self.blocked_actions(player)",
     "            payload[\"blocked_actions\"] = {}", ENG),

    ("W9 募兵面板的按鈕又不關",
     "<button class=\"train-unit-btn\" data-train-unit=\"${type}\"${trainBlock ? ` disabled title=\"${trainBlock}\"` : \"\"}>訓練 +1</button>",
     "<button class=\"train-unit-btn\" data-train-unit=\"${type}\">訓練 +1</button>", APP),

    ("W10 懲戒解除又把城市從 city_owners 移除（悄悄回到 1926 劇本原主）",
     "                    self.engine.state[\"city_owners\"][city[\"id\"]] = None",
     "                    self.engine.state[\"city_owners\"].pop(city[\"id\"], None)", PUN),

    ("W11 解除時不再開交辦（後端變無主、地圖一格沒動）",
     "                self.engine.queue_frontend_effect(entry[\"owner\"], {\n"
     "                    \"kind\": \"cities_became_ownerless\",",
     "                self.engine.queue_frontend_effect(entry[\"owner\"], {\n"
     "                    \"kind\": \"foreign_punishment_damage\",", PUN),

    ("W12 前端同步時不再讀無主名單（換一台瀏覽器就看不到）",
     "    if (ownerless.has(city.id)) city.faction = null;",
     "    void ownerless;", APP),

    ("W13 轟炸／重建狀態前端又自己重算一份",
     "  return (state?.city_punishment_status || {})[String(cityId)] || null;",
     "  const bombed = bombedCities()[cityId];\n"
     "  if (bombed) return { status: 'bombing', label: '轟炸中', power: bombed.power };\n"
     "  const remaining = (state?.city_rebuilding || {})[cityId];\n"
     "  if (remaining) return { status: 'rebuilding', label: '重建中' };\n"
     "  return null;", APP),

    ("W14 又把沒人讀的 npc_accounts 塞回狀態裡",
     "            \"turn_log\": [],",
     "            \"npc_accounts\": {},\n            \"turn_log\": [],", ENG),

    # ── 第二十二批：卡面寫了、後端算了，玩家卻看不到 ────────────────
    ("W15 戰鬥修正項又變回沒有出處的數字",
     "                for modifier in modifiers:\n"
     "                    modifier[\"label\"] = self._modifier_label(modifier)",
     "                pass", MOD),

    ("W16 技能加成不再記得自己是哪個技能來的",
     "            out += [{**dict(m), \"source_trait\": trait}\n"
     "                    for m in self.base_modifiers(trait) + extra]",
     "            out += [dict(m) for m in self.base_modifiers(trait) + extra]", MOD),

    ("W17 戰鬥面板又不印加成（算了一整套沒人看）",
     "    ${appliedModifiersMarkup(battle, sideOrder)}",
     "    ${\"\"}", APP),

    ("W18 事件改寫過的卡片數字不再送出去",
     "            payload[\"card_field_changes\"] = self.card_field_changes(player)",
     "            payload[\"card_field_changes\"] = {}", ENG),

    ("W19 手牌不再標出改寫（玩家看到的還是原本那組數字）",
     "      ${cardFieldChanges(card.id).length",
     "      ${false", APP),

    ("W20 單一銀行的停貸令又不進借款面板",
     "            offer[\"can_borrow\"] = False\n"
     "            offer[\"available\"] = 0\n"
     "            offer[\"bank_ban\"] = {",
     "            offer[\"bank_ban\"] = {", ENG),

    ("W21 借款面板不印停貸理由",
     "            row.bank_ban ? `${row.bank_ban.label}（剩 ${row.bank_ban.remaining_turns} 回合）`",
     "            false ? ``", APP),

    ("W22 鐵路交涉的代價又擴大成整個省",
     '''                "select": {
                  "railways": [
                    "南滿鐵路"
                  ]
                },''',
     '''                "select": {
                  "provinces": [
                    "奉天",
                    "吉林"
                  ]
                },''', CARDS),

    ("W23 演習又回到先來後到的爭奪（一場演習就能挑起日蘇戰爭）",
     '            if entry.get("kind") != "ground_occupation" or is_drill(entry):\n'
     '                continue\n'
     '            for province in entry.get("provinces") or []:\n'
     '                out.setdefault(province, entry)\n'
     '        return out\n'
     '\n'
     '    def drilled_provinces',
     '            if entry.get("kind") != "ground_occupation":\n'
     '                continue\n'
     '            for province in entry.get("provinces") or []:\n'
     '                out.setdefault(province, entry)\n'
     '        return out\n'
     '\n'
     '    def drilled_provinces', PUN),

    ("W24 佔領與演習的解除規則又寫成同一種",
     '            "release_rule": (RELEASE_BECOMES_OWNERLESS\n'
     '                             if (not drill and kind == "ground_occupation")\n'
     '                             else RELEASE_RETURNS_TO_OWNER),',
     '            "release_rule": RELEASE_RETURNS_TO_OWNER,', PUN),

    ("W25 前端又分不出演習與佔領",
     "  if (entry?.kind === 'water_blockade') {\n"
     "    return punishmentIsDrill(entry) ? `${power}演習水域` : `${power}封鎖水域`;\n"
     "  }\n"
     "  return punishmentIsDrill(entry) ? `${power}演習區` : `${power}佔領區`;",
     "  return entry?.kind === 'water_blockade' ? `${power}封鎖水域` : `${power}佔領區`;", APP),
], runner=RUNNER, timeout=5400))
