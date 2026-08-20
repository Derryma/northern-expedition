"""Small, isolated helpers for the experimental navy layer."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any, Mapping


DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "data" / "navy_rules.json"


def load_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def repair_cost(missing_hp: int, *, cost_per_hp: int = 2) -> int:
    missing = max(0, int(missing_hp))
    return missing * max(0, int(cost_per_hp))


def validate_initial_divisions(rules: Mapping[str, Any]) -> None:
    unit_rules = rules.get("units", {})
    if "gun_boat" not in unit_rules or "cargo_boat" not in unit_rules:
        raise ValueError("navy rules must define gun_boat and cargo_boat")
    seen = set()
    for division in rules.get("initial_divisions", []):
        division_id = str(division.get("id", ""))
        if not division_id:
            raise ValueError("navy division requires an id")
        if division_id in seen:
            raise ValueError(f"duplicate navy division id: {division_id}")
        seen.add(division_id)
        if int(division.get("gun_boats", 0)) < 1:
            raise ValueError(f"{division_id} requires at least one gun boat")
        if int(division.get("cargo_boats", 0)) < 1:
            raise ValueError(f"{division_id} requires at least one cargo boat")


# ── 艦隊戰鬥：規則的單一來源 ──────────────────────────────────────────
#
# 這一整套原本住在 `frontend/navy.js`：砲艇失能門檻、傷害分配、退卻判定、
# 艦砲對砲兵、砲兵對艦艇，全部在前端算完，後端只收一份結果。也就是**海戰規則
# 在前端**——伺服器無從驗證，規則改了也沒有任何東西會叫。
#
# 現在搬到這裡。前端只負責:接收玩家指令、把結果畫出來、處理地圖上的位置與撤退格。


def _rule(rules, path, default):
    node = rules or {}
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
        if node is None:
            return default
    return node


def normalize_division(navy: dict, rules: Mapping[str, Any] | None = None) -> dict:
    """把一支艦隊整理成標準形狀，並丟掉已經沉沒的船。

    與前端 normalizeNavyDivision 逐條對應：補 id、夾 hp ≥ 0、maxHp ≥ 1、
    第一次見到就把 retreatMaxGunBoatHp 記成滿血總量（退卻線的基準）。
    """
    if not navy:
        return navy
    gun_hp = int(_rule(rules, ("units", "gun_boat", "hp"), 30))
    cargo_hp = int(_rule(rules, ("units", "cargo_boat", "hp"), 10))
    gun_boats = []
    for index, boat in enumerate(navy.get("gunBoats") or []):
        gun_boats.append({
            "id": boat.get("id") or f'{navy.get("id")}-G{index + 1}',
            "hp": max(0, int(boat.get("hp", gun_hp))),
            "maxHp": max(1, int(boat.get("maxHp") or gun_hp)),
        })
    # 退卻線的基準只升不降：戰損（船被移除）不能把它拉低，但在港口補進新砲艇
    # 要把它撐上去。先前只在第一次見到艦隊時記一次，補編之後基準還停在開局的
    # 數字——退卻線變成要打掉七成五、九成才會到，補得越多越不會退。
    baseline = navy.get("retreatMaxGunBoatHp")
    recorded = float(baseline) if isinstance(baseline, (int, float)) and baseline > 0 else 0.0
    navy["retreatMaxGunBoatHp"] = int(max(
        recorded, sum(max(0, int(b["maxHp"])) for b in gun_boats)))
    navy["gunBoats"] = [b for b in gun_boats if b["hp"] > 0]
    if not isinstance(navy.get("cargoBoatHp"), list):
        navy["cargoBoatHp"] = [
            {"id": f'{navy.get("id")}-C{i + 1}', "hp": cargo_hp, "maxHp": cargo_hp}
            for i in range(int(navy.get("cargoBoats") or 0))]
    cargo = []
    for index, boat in enumerate(navy["cargoBoatHp"]):
        cargo.append({
            "id": boat.get("id") or f'{navy.get("id")}-C{index + 1}',
            "hp": max(0, int(boat.get("hp", cargo_hp))),
            "maxHp": max(1, int(boat.get("maxHp") or cargo_hp)),
        })
    navy["cargoBoatHp"] = [b for b in cargo if b["hp"] > 0]
    navy["cargoBoats"] = len(navy["cargoBoatHp"])
    return navy


def active_gun_boats(navy: dict, rules: Mapping[str, Any] | None = None) -> list:
    """還打得動的砲艇。低於 inactive_below_hp 就失能——不是沉沒，是不能射擊。"""
    normalize_division(navy, rules)
    floor = int(_rule(rules, ("units", "gun_boat", "inactive_below_hp"), 15))
    return [b for b in (navy.get("gunBoats") or []) if int(b.get("hp", 0)) >= floor]


def total_gun_boat_hp(navy: dict) -> int:
    normalize_division(navy)
    return sum(max(0, int(b.get("hp", 0))) for b in (navy.get("gunBoats") or []))


def max_gun_boat_hp(navy: dict) -> int:
    normalize_division(navy)
    return sum(max(0, int(b.get("maxHp", 0))) for b in (navy.get("gunBoats") or []))


def retreat_baseline_hp(navy: dict, rules: Mapping[str, Any] | None = None) -> int:
    """退卻線的基準：這支艦隊「滿編」時的砲艇總血量。

    基準只升不降的規則寫在 normalize_division 裡（戰損不拉低、補編要撐上去），
    所以這裡直接讀它算好的值就行。
    """
    normalize_division(navy, rules)
    return max(0, int(navy.get("retreatMaxGunBoatHp") or 0))


def retreat_threshold_reached(navy: dict, rules: Mapping[str, Any] | None = None) -> bool:
    """掉到滿血的一半（依規則檔）就達退卻線。"""
    normalize_division(navy, rules)
    baseline = retreat_baseline_hp(navy, rules)
    if baseline <= 0:
        return True
    ratio = float(_rule(rules, ("land_interaction", "navy_retreat_gun_boat_hp_loss_ratio"), 0.5))
    return total_gun_boat_hp(navy) <= baseline * (1 - ratio)


def apply_gun_boat_damage(navy: dict, damage) -> dict:
    """傷害分配：先打砲艇再打運輸船，同類先打血多的。"""
    normalize_division(navy)
    remaining = max(0, int(damage or 0))
    targets = ([{"boat": b, "type": "gun_boat"} for b in (navy.get("gunBoats") or [])]
               + [{"boat": b, "type": "cargo_boat"} for b in (navy.get("cargoBoatHp") or [])])
    targets.sort(key=lambda t: (0 if t["type"] == "gun_boat" else 1, -int(t["boat"].get("hp", 0))))
    damaged = []
    for target in targets:
        if remaining <= 0:
            break
        boat, kind = target["boat"], target["type"]
        before = max(0, int(boat.get("hp", 0)))
        if before <= 0:
            continue
        applied = min(before, remaining)
        boat["hp"] = before - applied
        remaining -= applied
        damaged.append({"boat_id": boat.get("id"), "type": kind, "before": before,
                        "after": boat["hp"], "damage": applied, "sunk": boat["hp"] <= 0})
    normalize_division(navy)
    return {"applied": max(0, int(damage or 0)) - remaining, "damaged": damaged}


# ── 船上的陸軍 ────────────────────────────────────────────────────────
#
# 這一段原本住在 `frontend/app.js` 的 settleNavyCarriedLosses /
# enforceNavyCargoCapacity / sinkCarriedArmyWithNavy：運輸船沉了要裁掉哪些兵
# 是**規則**，而且用的是前端沒有種子的 Math.random()——伺服器完全不知道船上有人，
# 更無從驗證裁掉的是什麼。現在規則搬到這裡，前端只負責照著回傳的指示改畫面。

DEFAULT_FORCE_POINTS = {"infantry": 1, "cavalry": 1, "machine_gun": 2, "artillery": 4}


def navy_capacity(navy: dict, rules: Mapping[str, Any] | None = None) -> int:
    normalize_division(navy, rules)
    live = [b for b in (navy.get("cargoBoatHp") or []) if int(b.get("hp", 0)) > 0]
    return len(live) * int(_rule(rules, ("units", "cargo_boat", "capacity_force_points"), 20))


def force_points(units: Mapping[str, Any] | None,
                 force_table: Mapping[str, Any] | None = None) -> int:
    table = force_table or DEFAULT_FORCE_POINTS
    return sum(max(0, int((units or {}).get(unit) or 0)) * int(points)
               for unit, points in table.items())


def settle_carried_army(navy: dict, carried: Mapping[str, Any] | None,
                        rules: Mapping[str, Any] | None = None,
                        rng=None,
                        force_table: Mapping[str, Any] | None = None) -> dict:
    """海戰結算之後處理船上的陸軍。

    三種結局：
      wiped  —— 艦隊一條船都不剩，部隊隨船覆沒，將領陣亡。
      trimmed—— 運輸船折損，可載運量低於部隊戰力，隨機裁兵到容量以內。
      intact —— 容量還夠，什麼都不動。
    """
    normalize_division(navy, rules)
    if not carried or not carried.get("armyId"):
        return {"outcome": "none"}
    table = force_table or DEFAULT_FORCE_POINTS
    army_id = carried.get("armyId")
    general_id = carried.get("generalId")
    units = {key: max(0, int(value or 0)) for key, value in (carried.get("units") or {}).items()}
    if not (navy.get("gunBoats") or []) and not (navy.get("cargoBoatHp") or []):
        return {
            "outcome": "wiped",
            "armyId": army_id,
            "generalId": general_id,
            "capacity": 0,
            "units": {key: 0 for key in units},
            "lost": dict(units),
        }
    capacity = navy_capacity(navy, rules)
    if force_points(units, table) <= capacity:
        return {"outcome": "intact", "armyId": army_id, "generalId": general_id,
                "capacity": capacity, "units": units, "lost": {}}
    picker = rng or random.Random(0)
    lost: dict[str, int] = {}
    remaining = dict(units)
    while force_points(remaining, table) > capacity:
        available = sorted(key for key, value in remaining.items() if int(value) > 0)
        if not available:
            break
        unit = available[picker.randrange(len(available))]
        remaining[unit] -= 1
        lost[unit] = lost.get(unit, 0) + 1
    return {"outcome": "trimmed", "armyId": army_id, "generalId": general_id,
            "capacity": capacity, "units": remaining, "lost": lost}


def restore_hp_to_floor(navy: dict, target_hp, rules: Mapping[str, Any] | None = None) -> int:
    """把現存艦艇都補到至少 target_hp（不超過各自滿血），回傳實際補了幾點。

    「補了幾點」決定收多少工業點，所以這是規則。原本前端算完直接把數字送給
    /api/repair-navy，伺服器照單全收——送 0 就免費修。
    """
    normalize_division(navy, rules)
    target = max(0, int(target_hp or 0))
    restored = 0
    for boat in list(navy.get("gunBoats") or []) + list(navy.get("cargoBoatHp") or []):
        max_hp = max(0, int(boat.get("maxHp", 0)))
        before = max(0, int(boat.get("hp", 0)))
        after = min(max_hp, max(before, target))
        restored += max(0, after - before)
        boat["hp"] = after
    return restored


def retreat_floor_hp(navy: dict, rules: Mapping[str, Any] | None = None) -> float:
    ratio = float(_rule(rules, ("land_interaction", "navy_retreat_gun_boat_hp_loss_ratio"), 0.5))
    return retreat_baseline_hp(navy, rules) * (1 - ratio)


def incoming_fire(enemy_navy: dict | None, enemy_artillery: int = 0,
                  rules: Mapping[str, Any] | None = None) -> int:
    """一輪接觸打進來的反艦火力。對射與陸海接觸用的是同一組數字。"""
    total = 0
    if enemy_navy:
        total += len(active_gun_boats(enemy_navy, rules)) * int(
            _rule(rules, ("units", "gun_boat", "attack", "gun_boat"), 5))
    total += max(0, int(enemy_artillery or 0)) * int(
        _rule(rules, ("land_interaction", "artillery_attack_to_gun_boat"), 1))
    return total


def rounds_to_retreat(navy: dict, incoming: int,
                      rules: Mapping[str, Any] | None = None) -> int | None:
    """照這個火力還能撐幾輪才到退卻線。撐不到或已經到了就回 None。"""
    if incoming <= 0:
        return None
    gap = total_gun_boat_hp(navy) - retreat_floor_hp(navy, rules)
    if gap <= 0:
        return None
    return max(1, math.ceil(gap / incoming))


def contact_outlook(navy: dict, enemy_navy: dict | None = None,
                    enemy_artillery: int = 0,
                    rules: Mapping[str, Any] | None = None) -> dict:
    """交戰中那一行預估「還能撐幾輪」。

    原本整段住在前端 navyContactEstimate()：退卻線公式、砲艇火力、砲兵火力，
    全都在前端再算一次。畫面上的數字**必須**和真正結算用的規則同源，
    否則玩家看到「還能撐 3 輪」卻一輪就被打退。
    """
    normalize_division(navy, rules)
    incoming = incoming_fire(enemy_navy, enemy_artillery, rules)
    baseline = retreat_baseline_hp(navy, rules)
    own_rounds = rounds_to_retreat(navy, incoming, rules)
    enemy_rounds = None
    if enemy_navy is not None:
        enemy_incoming = incoming_fire(navy, 0, rules)
        enemy_rounds = rounds_to_retreat(enemy_navy, enemy_incoming, rules)
    return {
        "baselineHp": baseline,
        "currentHp": total_gun_boat_hp(navy),
        "retreatFloorHp": retreat_floor_hp(navy, rules),
        "incoming": incoming,
        "atRetreatLine": retreat_threshold_reached(navy, rules),
        "noBoatsLeft": baseline <= 0,
        "roundsToRetreat": own_rounds,
        "enemyAtRetreatLine": (retreat_threshold_reached(enemy_navy, rules)
                               if enemy_navy is not None else None),
        "enemyRoundsToRetreat": enemy_rounds,
    }


def resolve_army_navy_contact(army_units: Mapping[str, Any], navy: dict,
                              rules: Mapping[str, Any] | None = None) -> dict:
    """陸軍砲兵與艦隊接觸。"""
    artillery_before = max(0, round(float((army_units or {}).get("artillery") or 0)))
    active = active_gun_boats(navy, rules)
    boat_damage = artillery_before * int(
        _rule(rules, ("land_interaction", "artillery_attack_to_gun_boat"), 1))
    gun_attack = len(active) * int(_rule(rules, ("units", "gun_boat", "attack", "artillery"), 2))
    detail = apply_gun_boat_damage(navy, boat_damage)
    artillery_lost = min(artillery_before, math.ceil(gun_attack / 2))
    artillery_after = max(0, artillery_before - artillery_lost)
    return {
        "kind": "army_navy",
        "activeGunBoats": len(active),
        "navyFired": len(active) > 0,
        "boatDamage": detail["applied"],
        "boatDamageDetail": detail,
        "artilleryBefore": artillery_before,
        "artilleryLost": artillery_lost,
        "artilleryAfter": artillery_after,
        # 還有砲兵就守得住那一格；先前用「損失百分比」判，導致一次交火就退，
        # 陸海接觸永遠打不完。
        "landRetreat": artillery_after <= 0,
        "navyRetreat": retreat_threshold_reached(navy, rules)
        or len(active_gun_boats(navy, rules)) == 0,
    }


def resolve_navy_duel(attacker: dict, defender: dict,
                      rules: Mapping[str, Any] | None = None) -> dict:
    """兩支艦隊對射。射擊資格在交火開始時就固定——沒有可戰砲艇的一方挨打不還手。"""
    active_a = len(active_gun_boats(attacker, rules))
    active_b = len(active_gun_boats(defender, rules))
    per_boat = int(_rule(rules, ("units", "gun_boat", "attack", "gun_boat"), 5))
    damage_to_a = apply_gun_boat_damage(attacker, active_b * per_boat)
    damage_to_b = apply_gun_boat_damage(defender, active_a * per_boat)
    attacker_retreat = (len(active_gun_boats(attacker, rules)) == 0
                        or retreat_threshold_reached(attacker, rules))
    defender_retreat = (len(active_gun_boats(defender, rules)) == 0
                        or retreat_threshold_reached(defender, rules))
    tile_winner = None
    if attacker_retreat and defender_retreat:
        hp_a, hp_b = total_gun_boat_hp(attacker), total_gun_boat_hp(defender)
        if hp_a > hp_b:
            attacker_retreat, tile_winner = False, "attacker"
        elif hp_b > hp_a:
            defender_retreat, tile_winner = False, "defender"
        else:
            tile_winner = "draw"
    elif attacker_retreat != defender_retreat:
        tile_winner = "defender" if attacker_retreat else "attacker"
    return {
        "kind": "navy_duel",
        "attackerActiveGunBoats": active_a,
        "defenderActiveGunBoats": active_b,
        "attackerDamage": damage_to_b["applied"],
        "attackerDamageDetail": damage_to_b,
        "defenderDamage": damage_to_a["applied"],
        "defenderDamageDetail": damage_to_a,
        "attackerRetreat": attacker_retreat,
        "defenderRetreat": defender_retreat,
        "tileWinner": tile_winner,
    }
