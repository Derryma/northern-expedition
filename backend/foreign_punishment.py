"""列強懲戒的通用機制。

《可重複抽取事件卡》裡的懲戒卡都不是一次性的：關係一直不修好，同一種懲戒
會反覆降臨。這支模組把三類懲戒的共同骨架抽出來，卡片本身只負責宣告
「哪一國、哪一類、範圍是什麼」，其餘（佔領、解除、傷害、復工）都在這裡。

三類：

    ground_occupation  地面部隊佔領。指定省份整片換成列強領土，城市收入歸零，
                       境內部隊被鎖在原地，城內駐軍被趕到鄰近鄉野。
    water_blockade     水域封鎖。指定水域，艦隊鎖在原地，該水域的河港與鄰接
                       海港收入歸零。
    air_raid           空襲轟炸。動態鎖定被懲戒方最大的五座城市，收入歸零；
                       解除後每座城市還要三回合才復工。

共通規則：

  * **解除條件**：關係改善到非敵對（> −4）的**下一回合**才解除。
    演習（drill）例外——演習不是懲戒，有固定回合數，時間到就結束。
  * **傷害**：只有在關係真的處於敵對時才吃。演習一律不造成傷害。
  * **同一玩家同一懲戒不重複**：一個懲戒對某玩家還生效時，那張卡對他封鎖；
    但**不同玩家可以同時吃到同一張**（兩個對日交惡的人可以一起被炸）。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

# 敵對門檻。關係 <= 這個值算敵對，> 這個值就算修好了。
HOSTILE_AT_OR_BELOW = -4

# 轟炸解除之後，城市要停工幾回合才復工。
REBUILD_TURNS = 3

# 日蘇重疊區開戰的勝率（設計稿：蘇聯 60%、日本 40%），以及三段傷害的比率。
SOVIET_WIN_RATE = 0.60
GROUND_OCCUPATION_LOSS = 0.40
WAR_SPLASH_LOSS = 0.10

KINDS = ("ground_occupation", "water_blockade", "air_raid")

# 各列強的佔領區顏色（設計稿指定）。美國不使用地面部隊懲戒，所以沒有顏色。
POWER_TERRITORY_COLORS = {
    "jp": "#d8cfa8",   # 淺卡其
    "su": "#a3242b",   # 紅色，比西北軍更深
    "uk": "#9fc4de",   # 淺藍
    "fr": "#3f6fb5",   # 藍
}


# 港口城市屬於哪些水域。海港照經緯度分海域，用的是與前端 coastalSeaName()
# 相同的四條分界線（渤海海峽、長江口、平潭—富貴角、南澳島），河港則直接列出來——
# 河道走向沒辦法用一條經緯度規則講清楚，硬湊只會錯得很難查。
RIVER_PORTS = {
    "長江": ["yichang", "hankou", "wuchang", "jiujiang", "anqing",
             "nanjing", "suzhou", "shanghai", "chongqing", "luzhou"],
    "黃河": ["lanzhou", "baotou", "tongguan", "luoyang", "zhengzhou",
             "kaifeng", "jinan"],
    "珠江": ["guangzhou", "foshan", "wuzhou", "nanning"],
}


def coastal_sea_name(lon: float, lat: float) -> str:
    """海港屬於哪一片海。與 frontend/map.js 的 coastalSeaName() 同一套分界。"""
    if lat >= 37.6 and lon <= 122.3:
        return "渤海"
    if lat >= 31.8:
        return "黃海"
    if lat >= 25.4:
        return "東海"
    if lat >= 23.6 and lon >= 116.5:
        return "臺灣海峽"
    return "南海"


def waters_for_city(city: Dict[str, Any]) -> list:
    """這座城貼著哪些水域。不是港口就沒有。"""
    port = city.get("port")
    if port == "sea":
        return [coastal_sea_name(float(city.get("lon", 0)), float(city.get("lat", 0)))]
    if port == "river":
        return [name for name, ids in RIVER_PORTS.items() if city["id"] in ids]
    return []


def is_hostile(relation: int) -> bool:
    return int(relation) <= HOSTILE_AT_OR_BELOW


class PunishmentBook:
    """掛在 GameEngine 上的懲戒帳本。狀態全部存在 engine.state 裡，這裡只提供操作。"""

    def __init__(self, engine):
        self.engine = engine

    # ── 讀取 ────────────────────────────────────────────────────────────

    @property
    def entries(self) -> list:
        # new_game 建初始快照時 engine.state 還不存在，那時當然也還沒有任何懲戒。
        state = getattr(self.engine, "state", None)
        if not isinstance(state, dict):
            return []
        return state.setdefault("foreign_punishments", [])

    def for_owner(self, owner: str) -> list:
        return [e for e in self.entries if e.get("owner") == owner]

    def active_card_for(self, card_id: str, owner: str) -> Optional[Dict[str, Any]]:
        """這張懲戒卡是不是正對這個玩家生效中。

        用來擋掉重複懲戒——同一張卡在對同一個人生效期間不該再抽到，
        但別人照樣抽得到。
        """
        for entry in self.entries:
            if entry.get("card_id") == card_id and entry.get("owner") == owner:
                return entry
        return None

    def occupied_provinces(self) -> Dict[str, Dict[str, Any]]:
        """省份 → 佔領它的那一筆。先來後到：已經被佔的省不會被第二國蓋掉。"""
        out: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            if entry.get("kind") != "ground_occupation":
                continue
            for province in entry.get("provinces") or []:
                out.setdefault(province, entry)
        return out

    def blockaded_waters(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            if entry.get("kind") != "water_blockade":
                continue
            for water in entry.get("waters") or []:
                out.setdefault(water, entry)
        return out

    def bombed_cities(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for entry in self.entries:
            if entry.get("kind") != "air_raid":
                continue
            for city_id in entry.get("city_ids") or []:
                out.setdefault(city_id, entry)
        return out

    def rebuilding_cities(self) -> Dict[str, int]:
        """城市 → 還要幾回合才復工。"""
        state = getattr(self.engine, "state", None)
        if not isinstance(state, dict):
            return {}
        return dict(state.setdefault("city_rebuilding", {}))

    def city_status(self, city_id: str) -> Optional[Dict[str, Any]]:
        """給前端用：這座城現在是「轟炸中」還是「重建中」，是誰炸的。"""
        hit = self.bombed_cities().get(city_id)
        if hit:
            return {"status": "bombing", "label": "轟炸中", "power": hit.get("power"),
                    "card_id": hit.get("card_id")}
        remaining = self.rebuilding_cities().get(city_id)
        if remaining:
            return {"status": "rebuilding", "label": "重建中",
                    "remaining_turns": int(remaining)}
        return None

    def city_output_is_zero(self, city_id: str, owner: str) -> bool:
        """這座城現在該不該有產出。佔領、封鎖、轟炸、重建四種情形都歸零。

        海軍演習例外：設計稿明寫「領域內城市生產照常，不會減損」。
        陸軍演習則照樣歸零（12.4 關東軍特別演習：期間金錢與工廠收入歸零）。
        """
        if city_id in self.bombed_cities():
            return True
        if self.rebuilding_cities().get(city_id):
            return True
        city = self.engine._city_by_id(city_id)
        if not city:
            return False
        if city.get("province") in self.occupied_provinces():
            return True
        return self._port_is_blockaded(city)

    def _port_is_blockaded(self, city: Dict[str, Any]) -> bool:
        # 海軍演習不影響城市生產，所以查封鎖時把演習那幾筆排除掉。
        waters = {name: entry for name, entry in self.blockaded_waters().items()
                  if not entry.get("drill")}
        if not waters:
            return False
        return bool(set(waters_for_city(city)) & set(waters))

    # ── 建立 ────────────────────────────────────────────────────────────

    def open(self, *, card_id: str, power: str, kind: str, owner: str,
             provinces: Iterable[str] = (), waters: Iterable[str] = (),
             city_count: int = 5, drill_turns: Optional[int] = None,
             label: str = "") -> Dict[str, Any]:
        """開一筆懲戒（或演習）。回傳的 dict 會進 applied，讓報紙說得出發生什麼。"""
        if kind not in KINDS:
            raise ValueError(f"unknown punishment kind: {kind!r}")
        turn = int(self.engine.state["turn"])
        relation = int(self.engine._player(owner)
                       .get("foreign_relations", {}).get(power, 0))
        drill = drill_turns is not None
        entry: Dict[str, Any] = {
            "id": f"{card_id}:{owner}:{turn}",
            "card_id": card_id,
            "power": power,
            "kind": kind,
            "owner": owner,
            "label": label or card_id,
            "since_turn": turn,
            "drill": drill,
            "until_turn": (turn + int(drill_turns)) if drill else None,
            "provinces": [],
            "waters": [],
            "city_ids": [],
        }

        if kind == "ground_occupation":
            # 先來後到，唯獨日蘇之間例外：重疊的省會打一仗，由勝者佔領。
            taken = self.occupied_provinces()
            free, contested, skipped = [], [], []
            for province in provinces:
                incumbent = taken.get(province)
                if incumbent is None:
                    free.append(province)
                elif {incumbent["power"], power} == {"jp", "su"}:
                    contested.append((province, incumbent))
                else:
                    skipped.append(province)
            entry["provinces"] = list(free)
            entry["skipped_provinces"] = skipped
            entry["wars"] = [self._resolve_power_war(entry, province, incumbent)
                             for province, incumbent in contested]
            for war in entry["wars"]:
                if war["winner"] == power:
                    entry["provinces"].append(war["province"])
                else:
                    entry["skipped_provinces"].append(war["province"])
        elif kind == "water_blockade":
            taken = self.blockaded_waters()
            entry["waters"] = [w for w in waters if w not in taken]
            entry["skipped_waters"] = [w for w in waters if w in taken]
        else:
            entry["city_count"] = int(city_count)
            entry["city_ids"] = self._pick_bomb_targets(owner, int(city_count))

        self.entries.append(entry)
        # 傷害只在真的敵對時才吃；演習一律不傷。
        # 打過仗的省另計——那些省的傷害是三重疊加，由 _apply_war_damage 一次算清。
        war_provinces = {war["province"] for war in entry.get("wars") or []}
        entry["damage"] = ({} if drill or not is_hostile(relation)
                           else self._apply_damage(entry, exclude_provinces=war_provinces))
        for war in entry.get("wars") or []:
            self._apply_war_damage(war)
        self.engine._refresh_city_income()
        return entry

    # ── 日蘇重疊區的開戰判定 ────────────────────────────────────────────

    def _resolve_power_war(self, challenger: Dict[str, Any], province: str,
                           incumbent: Dict[str, Any]) -> Dict[str, Any]:
        """日蘇懲戒範圍重疊時，重疊的那一省要打一仗，勝者佔領。

        設計稿：勝率蘇聯 60%、日本 40%；**以省為單位**判定，衝突兩省就擲兩次、
        兩個結果。戰敗方只輸掉重疊的那一省，自己其餘的省照舊佔著。
        """
        challenger_power = challenger["power"]
        incumbent_power = incumbent["power"]
        roll = self.engine.random.random()
        # 擲一次骰，換算成「蘇聯是否獲勝」，再對應回挑戰方／守成方。
        soviet_wins = roll < SOVIET_WIN_RATE
        winner = "su" if soviet_wins else "jp"
        loser = "jp" if soviet_wins else "su"
        if winner == challenger_power:
            # 挑戰方贏：把這一省從守成方的佔領清單裡拿掉。
            incumbent["provinces"] = [p for p in incumbent.get("provinces") or []
                                      if p != province]
            incumbent.setdefault("lost_provinces", []).append(province)
        war = {
            "province": province,
            "challenger": challenger_power,
            "incumbent": incumbent_power,
            "winner": winner,
            "loser": loser,
            "roll": round(roll, 4),
            "turn": int(self.engine.state["turn"]),
            "winner_entry_id": challenger["id"] if winner == challenger_power else incumbent["id"],
            "owner": challenger["owner"],
        }
        self.engine.state.setdefault("power_wars", []).append(war)
        return war

    def cumulative_loss_for(self, owner: str, province: str) -> float:
        """某玩家在某省累計掉多少戰力／艦體，**以初始值為基準相加**。

        設計稿寫死的三段：日本懲戒 −40%、日蘇戰爭波及 −10%、蘇聯懲戒 −40%，
        蘇勝時剩 10%、日勝時剩 50%。所以是相加不是連乘（連乘會得到 32.4%／54%）。
        未與交戰雙方交惡的第三方只吃戰火波及那 10%。
        """
        relations = self.engine._player(owner).get("foreign_relations", {})
        total = 0.0
        for entry in self.entries:
            if entry.get("kind") != "ground_occupation" or entry.get("drill"):
                continue
            if entry.get("owner") != owner or province not in (entry.get("provinces") or []):
                continue
            if is_hostile(int(relations.get(entry["power"], 0))):
                total += GROUND_OCCUPATION_LOSS
        # 戰敗方的那一份打擊已經先落地了，仍然算在帳上。
        for entry in self.entries:
            if entry.get("kind") != "ground_occupation" or entry.get("drill"):
                continue
            if entry.get("owner") != owner or province not in (entry.get("lost_provinces") or []):
                continue
            if is_hostile(int(relations.get(entry["power"], 0))):
                total += GROUND_OCCUPATION_LOSS
        total += WAR_SPLASH_LOSS * sum(
            1 for war in self.engine.state.get("power_wars", [])
            if war["province"] == province)
        return min(1.0, round(total, 4))

    def _apply_war_damage(self, war: Dict[str, Any]) -> None:
        """戰火波及：該省上**所有勢力**的部隊與靠港砲艇 −10%。

        與日蘇任一方交惡的玩家還要加上懲戒本身的傷害，總量以初始值為基準相加，
        所以這裡送出的是「累計損失率」，前端照著把部隊拉回 初始 ×(1−累計)。
        """
        province = war["province"]
        for code in self.engine.state["players"]:
            cumulative = self.cumulative_loss_for(code, province)
            if cumulative <= 0:
                continue
            self.engine._player(code).setdefault("pending_frontend_effects", []).append({
                "kind": "foreign_punishment_damage",
                "punishment_kind": "power_war",
                "punishment_id": war["winner_entry_id"],
                "power": war["winner"],
                "provinces": [province],
                "waters": [],
                "city_ids": [],
                "war": {"winner": war["winner"], "loser": war["loser"]},
                # 以初始值為基準的累計損失，不是這一次額外扣多少。
                "chain": f"war:{province}",
                "cumulative_army_force": cumulative,
                "cumulative_harbor_gunboat_hp": cumulative,
            })

    def _pick_bomb_targets(self, owner: str, count: int) -> list:
        """挑被懲戒方最大的 N 座城（$ ＋ 工廠），動態的——每回合會重挑。"""
        scored = []
        for city in self.engine.data["strategic_map"]["cities"]:
            if self.engine.state["city_owners"].get(city["id"], city["faction"]) != owner:
                continue
            base = self.engine._with_level(city)
            scored.append((int(base.get("cash", 0)) + int(base.get("factory", 0)),
                           city["id"]))
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return [city_id for _, city_id in scored[:count]]

    def _apply_damage(self, entry: Dict[str, Any],
                      exclude_provinces: Optional[set] = None) -> Dict[str, Any]:
        """把傷害寫成前端待辦。部隊與艦隊都住在 app.js，後端只能開清單。

        設計稿的三組數字：
          地面佔領：範圍內我方部隊戰力 −40%，靠港砲艇總生命 −40%
          水域封鎖：範圍內艦隊總生命 −50%，鄰接港口駐軍戰力 −30%
          空襲轟炸：城內駐軍戰力 −30% 並被逐出城，靠港艦隊總生命 −50%

        exclude_provinces：打過日蘇戰爭的省不走這裡——那些省是三重疊加，
        由 _apply_war_damage 用「以初始值為基準的累計損失率」一次算清。
        """
        spec = {
            "ground_occupation": {"army_force": -GROUND_OCCUPATION_LOSS,
                                  "harbor_gunboat_hp": -GROUND_OCCUPATION_LOSS},
            "water_blockade": {"fleet_hp": -0.50, "harbor_army_force": -0.30},
            "air_raid": {"army_force": -0.30, "fleet_hp": -0.50, "evict_from_city": True},
        }[entry["kind"]]
        provinces = [p for p in (entry.get("provinces") or [])
                     if p not in (exclude_provinces or set())]
        if entry["kind"] == "ground_occupation" and not provinces:
            return {}
        effect = {
            "kind": "foreign_punishment_damage",
            "punishment_id": entry["id"],
            "punishment_kind": entry["kind"],
            "power": entry["power"],
            "provinces": provinces,
            "waters": list(entry.get("waters") or []),
            "city_ids": list(entry.get("city_ids") or []),
            **spec,
        }
        self.engine._player(entry["owner"]).setdefault(
            "pending_frontend_effects", []).append(effect)
        return spec

    # ── 每回合維護 ──────────────────────────────────────────────────────

    def tick(self) -> Dict[str, Any]:
        """回合推進時跑一次：解除該解的、重挑轟炸目標、推進重建進度。"""
        turn = int(self.engine.state["turn"])
        released, kept = [], []
        for entry in self.entries:
            if self._should_release(entry, turn):
                released.append(entry)
            else:
                kept.append(entry)
        self.engine.state["foreign_punishments"] = kept

        for entry in released:
            self._release(entry)

        # 轟炸目標是動態的：城市易主就換一個繼續炸，總是盯著最大的五座。
        retargeted = []
        for entry in kept:
            if entry.get("kind") != "air_raid":
                continue
            fresh = self._pick_bomb_targets(entry["owner"], int(entry.get("city_count", 5)))
            if fresh != entry["city_ids"]:
                retargeted.append({"punishment_id": entry["id"],
                                   "before": list(entry["city_ids"]), "after": fresh})
                entry["city_ids"] = fresh

        # 空襲照設計稿是**每回合**都炸：只要還在炸，就再開一份傷害待辦給前端。
        # 佔領與封鎖的傷害是一次性的，開卡當下就結清了，這裡不重開。
        for entry in kept:
            if entry.get("kind") == "air_raid":
                self._apply_damage(entry)

        rebuilt = self._tick_rebuilding()
        if released or retargeted or rebuilt:
            self.engine._refresh_city_income()
        return {"released": [e["id"] for e in released],
                "retargeted": retargeted, "rebuilt": rebuilt}

    def _should_release(self, entry: Dict[str, Any], turn: int) -> bool:
        if entry.get("drill"):
            return entry.get("until_turn") is not None and turn >= int(entry["until_turn"])
        # 懲戒：關係修好之後的**下一回合**才解除，所以先記下修好的回合。
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

    def _release(self, entry: Dict[str, Any]) -> None:
        if entry["kind"] == "ground_occupation" and not entry.get("drill"):
            # 懲戒解除後土地變無主，原屬勢力要重新佔領。演習則原封不動還回去。
            for city in self.engine.data["strategic_map"]["cities"]:
                if city.get("province") in (entry.get("provinces") or []):
                    self.engine.state["city_owners"].pop(city["id"], None)
                    self.engine.state.setdefault("ownerless_cities", [])
                    if city["id"] not in self.engine.state["ownerless_cities"]:
                        self.engine.state["ownerless_cities"].append(city["id"])
        if entry["kind"] == "air_raid":
            # 轟炸停了，城市還要三回合才復工。
            rebuilding = self.engine.state.setdefault("city_rebuilding", {})
            for city_id in entry.get("city_ids") or []:
                rebuilding[city_id] = REBUILD_TURNS

    def _tick_rebuilding(self) -> list:
        rebuilding = self.engine.state.setdefault("city_rebuilding", {})
        done = []
        for city_id in list(rebuilding):
            remaining = int(rebuilding[city_id]) - 1
            if remaining <= 0:
                rebuilding.pop(city_id)
                done.append(city_id)
            else:
                rebuilding[city_id] = remaining
        return done

    def start_rebuilding(self, city_id: str) -> None:
        """被別人打下來的轟炸城市：脫離轟炸，但一樣要三回合才復工。"""
        bombed = self.bombed_cities().get(city_id)
        if not bombed:
            return
        entry = bombed
        entry["city_ids"] = [c for c in entry.get("city_ids") or [] if c != city_id]
        self.engine.state.setdefault("city_rebuilding", {})[city_id] = REBUILD_TURNS
