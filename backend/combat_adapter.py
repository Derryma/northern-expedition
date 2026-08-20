"""Adapter around the existing combat system module."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
COMBAT_PATH = REPO_ROOT / "comabt_system" / "combat.py"


def _load_combat_module():
    spec = importlib.util.spec_from_file_location("northern_combat", COMBAT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load combat module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def simulate_with_modifiers(payload: Dict[str, Any], engine) -> Dict[str, Any]:
    """後端自己組修正項，再打。

    前端只送「誰打誰、站在哪一省、有沒有要塞、誰在防守、用什麼戰術」這些它本來
    就擁有的事實；技能加成、光環、限時效果、要塞與強制和平全部由後端查表組出來。
    先前這一段在 app.js，等於戰鬥規則在前端、傷害計算在後端。

    payload 另外帶 `battle`（見 CombatModifierBuilder.build 的說明）。回傳結果會
    附上 `applied_modifiers`，讓前端照著顯示「這一場吃到哪些加成」而不必自己推。
    """
    from .combat_modifiers import CombatModifierBuilder

    battle = payload.get("battle")
    if not battle:
        plain = simulate(payload)
        plain["surrender"] = surrender_verdict(plain)
        return plain
    built = CombatModifierBuilder(engine).build(battle)
    enriched = dict(payload)
    for key in ("army_a", "army_b"):
        army = dict(enriched.get(key) or {})
        if army.get("name") in built:
            army["modifiers"] = built[army["name"]]
        enriched[key] = army
    reinforcements = []
    for entry in (enriched.get("reinforcements") or []):
        item = dict(entry)
        army = dict(item.get("army") or {})
        if army.get("name") in built:
            army["modifiers"] = built[army["name"]]
        item["army"] = army
        reinforcements.append(item)
    if reinforcements:
        enriched["reinforcements"] = reinforcements
    result = simulate(enriched)
    result["applied_modifiers"] = built
    result["surrender"] = surrender_verdict(result)
    return result


# ── 戰後投降判定 ──────────────────────────────────────────────────────
#
# 「兵力低於門檻即投降被俘」與「兵力過小又遭優勢兵力追擊即覆沒投降」原本是
# app.js 裡三個寫死的常數（5 / 8 / 2.5）加上前端自己跑的判定。將領被俘與否
# 是結算結果，不是呈現——規則搬到這裡，前端只照著 `surrender` 欄位動手。

SURRENDER_FORCE_THRESHOLD = 5      # 剩餘戰力低於此值，而對手還在，就投降被俘
OVERRUN_SURRENDER_FORCE = 8        # 敗方殘存戰力在此值以內…
OVERRUN_FORCE_RATIO = 2.5          # …且勝方戰力達其倍數，就是追上來的殲滅


def _side_force(result: Dict[str, Any], side: str) -> float:
    from .card_engine import UNIT_FORCE_POINTS
    units = ((result.get("remaining") or {}).get(side) or {}).get("units") or {}
    return float(sum(max(0, float(units.get(unit) or 0)) * points
                     for unit, points in UNIT_FORCE_POINTS.items()))


def _winner_side(result: Dict[str, Any]) -> Optional[str]:
    winner = result.get("winner")
    return winner if winner in ("A", "B") else None


def surrender_verdict(result: Dict[str, Any]) -> Dict[str, Any]:
    """這一輪結算之後，有沒有哪一方被迫投降。

    只回報「兵力」造成的兩種投降。第三種（敗軍無退路）取決於地圖上還有沒有
    可退的格子，那一份留在前端的地圖層。
    """
    force_a, force_b = _side_force(result, "A"), _side_force(result, "B")
    verdict = {"side": None, "reason": None,
               "forceA": force_a, "forceB": force_b,
               "threshold": SURRENDER_FORCE_THRESHOLD,
               "overrunForce": OVERRUN_SURRENDER_FORCE,
               "overrunRatio": OVERRUN_FORCE_RATIO}
    if force_a <= SURRENDER_FORCE_THRESHOLD < force_b:
        return {**verdict, "side": "A", "reason": "collapsed"}
    if force_b <= SURRENDER_FORCE_THRESHOLD < force_a:
        return {**verdict, "side": "B", "reason": "collapsed"}
    winner = _winner_side(result)
    if not winner:
        return verdict
    loser = "B" if winner == "A" else "A"
    winner_force = force_a if winner == "A" else force_b
    loser_force = force_a if loser == "A" else force_b
    if loser_force <= 0:
        return {**verdict, "side": loser, "reason": "overrun"}
    if (loser_force <= OVERRUN_SURRENDER_FORCE
            and winner_force >= loser_force * OVERRUN_FORCE_RATIO):
        return {**verdict, "side": loser, "reason": "overrun"}
    return verdict


def combat_outlook(payload: Dict[str, Any], engine) -> Dict[str, Any]:
    """開打前的「還能撐幾輪」：空跑一輪，只回傳退卻預估，不套用任何結果。

    前端 estimatedRoundsUntilBreak() 在第一輪打完之前無從取得後端的
    time_to_breakdown，於是自己用戰力點、戰術倍率與一個寫死的校準常數
    （一個寫死的 0.45 校準值）另外算一套——那是**前端自己發明的
    傷害模型**，和真正結算用的規則沒有任何關係。現在改由這裡空跑一輪給它。
    """
    probe = deepcopy(payload)
    probe["max_rounds"] = 1
    try:
        result = simulate_with_modifiers(probe, engine)
    except ValueError as exc:
        # 兵力太小之類的情形本來就打不起來，讓前端顯示「無法估計」而不是壞掉。
        return {"time_to_breakdown": None, "reason": str(exc)}
    first_round = next((entry for entry in (result.get("log") or []) if entry.get("round")), None)
    return {"time_to_breakdown": (first_round or {}).get("time_to_breakdown")}


def simulate(payload: Dict[str, Any]) -> Dict[str, Any]:
    combat = _load_combat_module()
    force_a = combat.calculate_force_strength(payload["army_a"].get("units", {}))
    force_b = combat.calculate_force_strength(payload["army_b"].get("units", {}))
    if force_a <= 5:
        raise ValueError("attacking army must have more than 5 force points")
    if force_b <= 5:
        units_a = combat._clean_counts(payload["army_a"].get("units", {}))
        zero_units = {unit: 0 for unit in combat.UNITS}
        return {
            "winner": "A",
            "surrendered": "B",
            "rounds": 0,
            "log": [],
            "remaining": {
                "A": {"label": "A", "units": units_a},
                "B": {"label": "B", "units": zero_units},
            },
        }
    return combat.simulate_battle(
        payload["army_a"],
        payload["army_b"],
        max_rounds=int(payload.get("max_rounds", 20)),
        reinforcements=payload.get("reinforcements"),
    )
