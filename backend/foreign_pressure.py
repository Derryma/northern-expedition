"""最後通牒與租界管制。

兩者都不是「佔地／封水／轟炸」那種佔領式懲戒，所以不放在 foreign_punishment.py，
但共用同一條解除規則：關係修好到非敵對（`> −4`）的**下一回合**才鬆手。

  * **最後通牒**：抽出後 5 回合內要派部隊到該國指定城市**周邊一格**駐紮至少
    1 回合。做到了 → 關係 +1，該國的 [地面部隊] 懲戒不解封；沒做到 → 下一回合起
    該國所有 [地面部隊] 懲戒對你解封。只有日、蘇、英、法有（美國不用地面部隊）。
  * **租界管制**：與你交惡的列強收緊租界商務。你持有的該國租界城市每回合
    額外 $−3、工廠 −3（可疊加至歸零為止）；但**租界加成**只有在該城**所有**
    租界國都對你管制時才會消失——加成綁的是城市的「租界」狀態，不是單一國家。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from .foreign_punishment import is_hostile

ULTIMATUM_TURNS = 5
CONCESSION_CONTROL_PENALTY = 3

# 各國最後通牒的指定城市（設計稿）。美國沒有最後通牒。
ULTIMATUM_CITIES = {
    "jp": ["lushun", "suzhou", "hankou"],
    "uk": ["hongkong", "shanghai", "tianjin"],
    "su": ["vladivostok", "zhangjiakou"],
    "fr": ["kunming", "shanghai", "tianjin"],
}


class _RelationReleaseMixin:
    """共用的解除判定：關係修好之後的**下一回合**才解除。"""

    def _should_release(self, entry: Dict[str, Any], turn: int) -> bool:
        relation = int(self.engine._player(entry["owner"])
                       .get("foreign_relations", {}).get(entry["power"], 0))
        if is_hostile(relation):
            entry.pop("mended_turn", None)
            return False
        mended = entry.get("mended_turn")
        if mended is None:
            entry["mended_turn"] = turn
            return False
        return turn > int(mended)


class UltimatumBook(_RelationReleaseMixin):
    """最後通牒的帳本。"""

    def __init__(self, engine):
        self.engine = engine

    @property
    def entries(self) -> list:
        state = getattr(self.engine, "state", None)
        if not isinstance(state, dict):
            return []
        return state.setdefault("ultimatums", [])

    def active_for(self, power: str, owner: str) -> Optional[Dict[str, Any]]:
        """這一國對這位玩家還有沒有沒結案的通牒（用來擋重複抽到）。"""
        for entry in self.entries:
            if entry["power"] == power and entry["owner"] == owner \
                    and entry["status"] == "open":
                return entry
        return None

    def failed_powers(self, owner: str) -> Set[str]:
        """哪些國家的通牒被這位玩家無視了——他們的 [地面部隊] 因此解封。"""
        return {e["power"] for e in self.entries
                if e["owner"] == owner and e["status"] == "failed"}

    def open(self, *, card_id: str, power: str, owner: str,
             cities: Optional[Iterable[str]] = None,
             turns: int = ULTIMATUM_TURNS) -> Dict[str, Any]:
        turn = int(self.engine.state["turn"])
        entry = {
            "id": f"{card_id}:{owner}:{turn}",
            "card_id": card_id,
            "power": power,
            "owner": owner,
            "cities": list(cities if cities is not None else ULTIMATUM_CITIES.get(power, [])),
            "opened_turn": turn,
            "deadline_turn": turn + int(turns),
            "status": "open",
        }
        self.entries.append(entry)
        return entry

    def report_garrisons(self, garrisons: Dict[str, Any]) -> list:
        """前端每回合回報「哪些城市周邊一格有我方部隊」，這裡結案。

        駐紮「至少 1 回合」＝ 連續兩次回合推進都看得到；所以第一次記在
        `seen_turn` 上，下一回合還在才算數。
        """
        met = []
        turn = int(self.engine.state["turn"])
        for entry in self.entries:
            if entry["status"] != "open":
                continue
            posted = set(garrisons.get(entry["owner"]) or [])
            if not posted & set(entry["cities"]):
                entry.pop("seen_turn", None)
                continue
            if entry.get("seen_turn") is None:
                entry["seen_turn"] = turn
                continue
            if turn <= int(entry["seen_turn"]):
                continue
            entry["status"] = "met"
            entry["met_turn"] = turn
            relations = self.engine._player(entry["owner"]).setdefault("foreign_relations", {})
            relations[entry["power"]] = int(relations.get(entry["power"], 0)) + 1
            met.append(entry)
        return met

    def tick(self) -> Dict[str, Any]:
        """回合推進：關係修好的通牒先作廢，其餘過期的判定為無視。

        [懲戒] 類的通則是「關係回升到門檻以上就自動失效」，最後通牒也不例外：
        還在倒數的通牒，只要關係回到非敵對（`> −4`）的下一回合就一筆勾銷，
        不會等到期限到了再判失敗。順序很重要——先作廢再判逾期，否則
        「最後一回合把關係修好」會被判成無視。
        """
        turn = int(self.engine.state["turn"])
        voided = []
        for entry in self.entries:
            if entry["status"] != "open":
                continue
            if self._should_release(entry, turn):
                entry["status"] = "voided"
                entry["voided_turn"] = turn
                voided.append(entry)
        failed = []
        for entry in self.entries:
            if entry["status"] == "open" and turn > int(entry["deadline_turn"]):
                entry["status"] = "failed"
                entry["failed_turn"] = turn
                failed.append(entry)
        # 關係改善之後，該國的 [地面部隊] 重新上鎖（設計稿：關係改善後被封鎖）。
        lifted = []
        for entry in list(self.entries):
            if entry["status"] != "failed":
                continue
            if self._should_release(entry, turn):
                entry["status"] = "lifted"
                lifted.append(entry)
        return {"failed": [e["id"] for e in failed], "lifted": [e["id"] for e in lifted],
                "voided": [e["id"] for e in voided]}


class ConcessionControlBook(_RelationReleaseMixin):
    """租界管制的帳本。"""

    def __init__(self, engine):
        self.engine = engine

    @property
    def entries(self) -> list:
        state = getattr(self.engine, "state", None)
        if not isinstance(state, dict):
            return []
        return state.setdefault("concession_controls", [])

    def active_for(self, power: str, owner: str) -> Optional[Dict[str, Any]]:
        for entry in self.entries:
            if entry["power"] == power and entry["owner"] == owner:
                return entry
        return None

    def controlled_powers(self, owner: str) -> Set[str]:
        return {e["power"] for e in self.entries if e["owner"] == owner}

    def open(self, *, card_id: str, power: str, owner: str) -> Dict[str, Any]:
        existing = self.active_for(power, owner)
        if existing:
            return existing
        entry = {
            "id": f"{card_id}:{owner}:{int(self.engine.state['turn'])}",
            "card_id": card_id,
            "power": power,
            "owner": owner,
            "since_turn": int(self.engine.state["turn"]),
        }
        self.entries.append(entry)
        return entry

    # ── 對城市的作用 ────────────────────────────────────────────────────

    def penalty_for_city(self, city: Dict[str, Any], owner: str) -> int:
        """這座城因為租界管制，每回合要扣掉多少（$ 與工廠同額）。

        一城多國租界時可以疊加——廣州同時被英法管制就是 −3−3，
        但夾在後面的 max(0, ...) 會讓它最多扣到歸零為止。
        """
        concessions = set(city.get("concession") or [])
        if not concessions:
            return 0
        hits = concessions & self.controlled_powers(owner)
        return CONCESSION_CONTROL_PENALTY * len(hits)

    def bonus_suspended(self, city: Dict[str, Any], owner: str) -> bool:
        """租界加成有沒有消失。

        加成綁的是城市的「租界」狀態：一城多國租界時，只有**所有**租界國都
        對你管制，這座城才算失去租界狀態；只被其中一國管制不影響加成。
        """
        concessions = set(city.get("concession") or [])
        if not concessions:
            return False
        return concessions <= self.controlled_powers(owner)

    def tick(self) -> Dict[str, Any]:
        turn = int(self.engine.state["turn"])
        released, kept = [], []
        for entry in self.entries:
            (released if self._should_release(entry, turn) else kept).append(entry)
        self.engine.state["concession_controls"] = kept
        return {"released": [e["id"] for e in released]}
