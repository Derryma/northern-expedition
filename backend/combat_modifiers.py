"""戰鬥修正項的組裝：規則的單一來源。

先前這一整套住在 `frontend/app.js`：前端讀將領樹、判斷光環／省份／友軍在場／
敵將在場／敵方關係，組出一份 `modifiers` 再連同部隊一起送給 `/api/combat`。
也就是說**戰鬥規則在前端、傷害計算在後端**——規則改一邊不會有人叫，而且伺服器
無從驗證前端送來的加成是不是它自己編的。

現在規則搬到這裡。前端只負責送「誰打誰、站在哪、用什麼戰術」這些它本來就擁有的
事實，加成由後端自己查表組出來。

資料來源：
  * 技能的基礎 modifiers → `comabt_system/data/general_traits.json`（本來就是後端資料）
  * 將領歸屬與技能      → 前端送上來的戰術狀態（將領樹住在前端的資料檔）
  * 列強關係、限時效果   → `GameEngine.state`（本來就在後端）
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

# 光環：帶著這個技能的將領，替**同一場戰鬥、同一邊**的指定部屬加成。
# 兩人若分屬敵我兩側就不生效——這是規則，不是提示。
AURA_TRAITS: Dict[str, Dict[str, Any]] = {
    "advantage_is_ours": {"partners": ["he_yingqin"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "northwest_overlord": {"partners": ["song_zheyuan", "lu_zhonglin"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "shanxi_king": {"partners": ["fu_zuoyi", "xu_yongchang"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "xining_garrison": {"partners": ["ma_fuxiang", "ma_hongbin"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "marshal_zhang": {"partners": ["zhang_xueliang"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "five_provinces_alliance": {"partners": ["meng_zhaoyue", "lu_xiangting"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
    "wu_peifu_admired": {"partners": ["jin_yun_e", "kou_yingjie", "chen_jiamo"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
}

SOUTHERN_MOUNTAIN_PROVINCES = ["廣東", "廣西", "雲南", "貴州", "四川", "湖南"]
SOUTHEAST_WATER_PROVINCES = ["廣西", "廣東", "福建", "浙江", "江蘇", "安徽", "江西"]

# 只在特定省份生效。
PROVINCE_CONDITIONAL_TRAITS: Dict[str, Dict[str, Any]] = {
    "riverine_warfare": {"provinces": set(SOUTHEAST_WATER_PROVINCES),
                         "modifiers": [{"stat": "harm_taken", "multiplier": 0.90}]},
    "mountain_division": {"provinces": set(SOUTHERN_MOUNTAIN_PROVINCES),
                          "modifiers": [{"stat": "harm_taken", "multiplier": 0.90}]},
    "elite_mountain_division": {"provinces": set(SOUTHERN_MOUNTAIN_PROVINCES),
                                "modifiers": [{"stat": "harm_taken", "multiplier": 0.90},
                                              {"stat": "attack", "multiplier": 1.05}]},
}

# 自家陣營對某列強太親近時，這個技能整個失效（並扣忠誠，忠誠那半在 card_engine）。
RELATION_DISABLED_TRAITS: Dict[str, Dict[str, Any]] = {
    "white_russian_mercenaries": {"power": "su", "min": 6, "loyalty_penalty": 5},
    "anticommunist_vanguard": {"power": "su", "min": 6, "loyalty_penalty": 5},
}

# 指定友軍同場才生效。
ALLY_PRESENCE_TRAITS: Dict[str, Dict[str, Any]] = {
    "anhui_veteran": {"allies": ["duan_qirui"], "modifiers": [{"stat": "hp", "multiplier": 1.10}]},
}

# 對面出現指定將領才生效。
ENEMY_PRESENCE_TRAITS: Dict[str, Dict[str, Any]] = {
    "hunan_governor": {"enemies": ["tang_shengzhi"], "modifiers": [{"stat": "attack", "multiplier": 1.10}]},
}

# 敵方陣營對某列強夠友好才生效。
ENEMY_RELATION_TRAITS: Dict[str, Dict[str, Any]] = {
    "anticommunist_vanguard": {"power": "su", "min": 6,
                               "modifiers": [{"stat": "attack", "multiplier": 1.10}]},
}

FORTRESS_DEFENCE_MODIFIER = {"stat": "harm_taken", "multiplier": 0.65}
GODDARD_ROCKET_UNLOCK = "event_goddard_rocket"
GODDARD_ROCKET_MODIFIER = {"stat": "attack", "unit": "artillery", "multiplier": 1.05,
                           "source_effect": "戈達德的火箭"}
DEFAULT_FORCED_PEACE_MULTIPLIER = 0.92


class CombatModifierBuilder:
    """把一支部隊在這一場戰鬥裡吃到的所有加成組出來。"""

    def __init__(self, engine, trait_data: Optional[Dict[str, Any]] = None):
        self.engine = engine
        raw = trait_data if trait_data is not None else \
            (engine.data.get("general_traits") or {})
        self.traits = raw.get("traits", raw) if isinstance(raw, dict) else {}

    # ── 基礎 ────────────────────────────────────────────────────────────
    def base_modifiers(self, trait: str) -> List[Dict[str, Any]]:
        return list((self.traits.get(trait) or {}).get("modifiers") or [])

    def trait_disabled(self, trait: str, faction: str) -> bool:
        rule = RELATION_DISABLED_TRAITS.get(trait)
        if not rule:
            return False
        value = int(self.engine._player(faction).get("foreign_relations", {})
                    .get(rule["power"], 0)) if faction in self.engine.state["players"] else 0
        if "min" in rule and value >= int(rule["min"]):
            return True
        if "max" in rule and value <= int(rule["max"]):
            return True
        return False

    # ── 各條規則 ────────────────────────────────────────────────────────
    def trait_modifiers(self, *, traits: Iterable[str], faction: str, province: Optional[str],
                        ally_general_ids: Iterable[str], enemy_general_ids: Iterable[str],
                        own_general_id: Optional[str],
                        opponent_faction: Optional[str]) -> List[Dict[str, Any]]:
        allies = set(ally_general_ids or [])
        enemies = set(enemy_general_ids or [])
        out: List[Dict[str, Any]] = []
        for trait in traits or []:
            if self.trait_disabled(trait, faction):
                continue
            extra: List[Dict[str, Any]] = []
            province_rule = PROVINCE_CONDITIONAL_TRAITS.get(trait)
            if province_rule and province in province_rule["provinces"]:
                extra += province_rule["modifiers"]
            ally_rule = ALLY_PRESENCE_TRAITS.get(trait)
            if ally_rule and any(gid != own_general_id and gid in allies
                                 for gid in ally_rule["allies"]):
                extra += ally_rule["modifiers"]
            enemy_rule = ENEMY_PRESENCE_TRAITS.get(trait)
            if enemy_rule and any(gid in enemies for gid in enemy_rule["enemies"]):
                extra += enemy_rule["modifiers"]
            relation_rule = ENEMY_RELATION_TRAITS.get(trait)
            if relation_rule and opponent_faction in self.engine.state["players"]:
                value = int(self.engine._player(opponent_faction)
                            .get("foreign_relations", {}).get(relation_rule["power"], 0))
                if value >= int(relation_rule["min"]):
                    extra += relation_rule["modifiers"]
            out += [dict(m) for m in self.base_modifiers(trait) + extra]
        return out

    def aura_modifiers(self, *, own_general_id: Optional[str],
                       allies: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """同一邊的友軍將領帶來的光環。敵我兩側相遇不生效。"""
        out: List[Dict[str, Any]] = []
        for ally in allies or []:
            if ally.get("general_id") == own_general_id:
                continue
            for trait in ally.get("traits") or []:
                aura = AURA_TRAITS.get(trait)
                if not aura or own_general_id not in aura["partners"]:
                    continue
                out += [{**m, "source_aura": trait} for m in aura["modifiers"]]
        return out

    def timed_modifiers(self, faction: str,
                        opponent_faction: Optional[str] = None) -> List[Dict[str, Any]]:
        if faction not in self.engine.state["players"]:
            return []
        payload = self.engine._player(faction)
        out: List[Dict[str, Any]] = []
        for effect in payload.get("timed_effects", []):
            if effect.get("kind") != "combat_modifier":
                continue
            if int(effect.get("remaining_turns") or 0) <= 0:
                continue
            if effect.get("target_faction") and opponent_faction \
                    and effect["target_faction"] != opponent_faction:
                continue
            floor = effect.get("expires_below_relation")
            power = effect.get("foreign_power_key")
            if floor is not None and power:
                if int(payload.get("foreign_relations", {}).get(power, 0)) < int(floor):
                    continue
            out += [{**m, "source_effect": effect.get("name")}
                    for m in (effect.get("modifiers") or [])]
        return out

    def situational_modifiers(self, *, faction: str, defending: bool,
                              fortress: bool) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        payload = self.engine._player(faction) if faction in self.engine.state["players"] else {}
        # 8.2 戈達德的火箭：要塞戰時雙方砲兵 +5%。
        if fortress and GODDARD_ROCKET_UNLOCK in (payload.get("unlocks") or []):
            out.append(dict(GODDARD_ROCKET_MODIFIER))
        if defending:
            peace = self._forced_peace(faction)
            if peace:
                out.append({"stat": "harm_taken",
                            "multiplier": float(peace.get("defensive_harm_taken_multiplier",
                                                          DEFAULT_FORCED_PEACE_MULTIPLIER)),
                            "source_effect": peace.get("name") or "強制和平"})
            if fortress:
                out.append(dict(FORTRESS_DEFENCE_MODIFIER))
        return out

    def _forced_peace(self, faction: str) -> Optional[Dict[str, Any]]:
        if faction not in self.engine.state["players"]:
            return None
        for effect in self.engine._player(faction).get("timed_effects", []):
            if effect.get("kind") != "forced_peace":
                continue
            remaining = effect.get("remaining_turns")
            if effect.get("permanent") or remaining is None or int(remaining) > 0:
                return effect
        return None

    # ── 對外：組一整場 ──────────────────────────────────────────────────
    def build(self, battle: Dict[str, Any]) -> Dict[str, Any]:
        """輸入一場戰鬥的事實，輸出每支部隊的 modifiers。

        battle = {
          province, fortress,
          sides: {"A": {"faction": .., "armies": [{id, general_id, traits, units,
                                                   tactic, defending}]}, "B": {...}}
        }
        """
        sides = battle.get("sides") or {}
        province = battle.get("province")
        fortress = bool(battle.get("fortress"))
        general_ids = {key: [a.get("general_id") for a in (side.get("armies") or [])]
                       for key, side in sides.items()}
        out: Dict[str, Any] = {}
        for key, side in sides.items():
            faction = side.get("faction")
            other = next((k for k in sides if k != key), None)
            opponent = (sides.get(other) or {}).get("faction")
            for army in side.get("armies") or []:
                modifiers = self.trait_modifiers(
                    traits=army.get("traits") or [], faction=faction, province=province,
                    ally_general_ids=general_ids.get(key) or [],
                    enemy_general_ids=general_ids.get(other) or [],
                    own_general_id=army.get("general_id"), opponent_faction=opponent)
                modifiers += self.aura_modifiers(
                    own_general_id=army.get("general_id"),
                    allies=side.get("armies") or [])
                modifiers += self.timed_modifiers(faction, opponent)
                modifiers += self.situational_modifiers(
                    faction=faction, defending=bool(army.get("defending")), fortress=fortress)
                out[army["id"]] = modifiers
        return out
