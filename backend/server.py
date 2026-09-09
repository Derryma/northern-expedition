"""Stdlib HTTP server for the playtest frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
import hashlib
import os
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .card_engine import DEFAULT_PLAYERS, GameEngine
from .combat_adapter import simulate as simulate_combat
from .combat_adapter import combat_outlook, simulate_with_modifiers
from .data_store import REPO_ROOT


FRONTEND_ROOT = REPO_ROOT / "frontend"
PJ_ROOT = REPO_ROOT / "PJ Boardgame"
PORTRAIT_ROOT = REPO_ROOT / "PJ Boardgame" / "portraits"
# 本作自有的肖像目錄。PJ Boardgame 資料夾只供參考、不得改動，所以新畫或新增的
# 肖像一律放這裡，並且優先於 PJ 目錄被採用。
LOCAL_PORTRAIT_ROOT = FRONTEND_ROOT / "assets" / "portraits"
# 戰術狀態持久化：伺服器重啟後不會丟失部隊編制與地圖狀態。
#
# 路徑可以用 NE_GAME_DATA_DIR 換掉，**驗證腳本一定要換**：
#   * 不換的話每次起伺服器都會接續玩家上一盤的棋盤，e2e 就不可重現——
#     曾經有一條檢查因此變成空轉（黔軍早就被吞併了，「事件前有黔軍地盤」不成立）。
#   * 更糟的是跑測試會把玩家的存檔直接覆蓋掉。
GAME_DATA_DIR = pathlib.Path(
    os.environ.get("NE_GAME_DATA_DIR") or (REPO_ROOT / "game_data"))
TACTICAL_STATE_FILE = GAME_DATA_DIR / "tactical_state.json"
ENGINE = GameEngine()
SHARED_LOCK = RLock()
SHARED_TACTICAL_STATE: Optional[Dict[str, Any]] = None
SHARED_REVISION = 0


def current_tactical() -> Optional[Dict[str, Any]]:
    """伺服器現在手上那份戰術快照。

    所有會讀它或改它的東西都必須拿這一份，而且是**每次請求重新拿**。
    前端每推一次共享狀態，SHARED_TACTICAL_STATE 就換成新的 dict；
    誰要是把上一次拿到的那個存起來重複用，寫進去的東西就沒有人看得到。
    這個專案已經為此付過一次代價：所有吞併與歸屬轉移的事件卡都在
    respond_event() 裡結算，而引擎手上那份是上一次 next_turn 留下的，
    於是卡片回報成功、地圖一格沒動，而且時好時壞——端看那一輪前端有沒有
    剛好在中間推過一次。

    這是唯一的定義。不要在別處再寫一次 `SHARED_TACTICAL_STATE if ... else None`。
    """
    return SHARED_TACTICAL_STATE if isinstance(SHARED_TACTICAL_STATE, dict) else None


def _tactical_fingerprint() -> str:
    """共享戰術狀態現在長什麼樣。用來判斷伺服器自己有沒有動過它。"""
    if SHARED_TACTICAL_STATE is None:
        return ""
    blob = json.dumps(SHARED_TACTICAL_STATE, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def save_tactical_state() -> None:
    """將戰術狀態寫入磁碟，防止伺服器重啟時資料丟失。"""
    if SHARED_TACTICAL_STATE is None:
        return
    try:
        GAME_DATA_DIR.mkdir(exist_ok=True)
        with open(TACTICAL_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(SHARED_TACTICAL_STATE, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save tactical state: {e}")


def load_tactical_state() -> None:
    """伺服器啟動時從磁碟載入戰術狀態。"""
    global SHARED_TACTICAL_STATE
    if TACTICAL_STATE_FILE.exists():
        try:
            with open(TACTICAL_STATE_FILE, 'r', encoding='utf-8') as f:
                SHARED_TACTICAL_STATE = json.load(f)
            print(f"Loaded tactical state from {TACTICAL_STATE_FILE}")
        except Exception as e:
            print(f"Warning: Failed to load tactical state: {e}")
            SHARED_TACTICAL_STATE = None


class SharedStateConflict(Exception):
    pass


class PlaytestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(ENGINE.bootstrap())
            return
        if parsed.path == "/api/shared-state":
            with SHARED_LOCK:
                self._send_json({
                    "revision": SHARED_REVISION,
                    "tactical": SHARED_TACTICAL_STATE,
                    "loyalty": ENGINE.loyalty_report(SHARED_TACTICAL_STATE),
                    "navy_outlook": ENGINE.navy_outlook(SHARED_TACTICAL_STATE),
                    "railway_access": ENGINE.railway_access(),
                    "engine_state": ENGINE.snapshot(),
                })
            return
        if parsed.path == "/api/general-tree":
            # Parse query params to get faction
            query_params = parse_qs(parsed.query)
            faction = query_params.get('faction', ['N'])[0]
            self._send_json(self._load_general_tree(faction))
            return
        self._serve_static(parsed.path)

    def _load_general_tree(self, faction: str = 'N') -> Dict[str, Any]:
        from .data_store import load_json

        # Map faction codes to tree files
        tree_files = {
            'N': 'general_tree/data/general_tree_playtest.json',  # 國民革命軍
            'F': 'general_tree/data/general_tree_fengtian.json',   # 奉系 - 張作霖
            'W': 'general_tree/data/general_tree_zhili.json',      # 直系 - 吳佩孚
            'S': 'general_tree/data/general_tree_sunfang.json',    # 五省聯軍 - 孫傳芳
            'Y': 'general_tree/data/general_tree_npc_Y.json',      # 晉系 - 閻錫山
            'G': 'general_tree/data/general_tree_npc_G.json',      # 西北軍 - 馮玉祥
            'M': 'general_tree/data/general_tree_npc_M.json',      # 西北馬家軍
            'H': 'general_tree/data/general_tree_npc_H.json',      # 湘軍 - 唐生智
            'C': 'general_tree/data/general_tree_npc_C.json',      # 川軍
            'D': 'general_tree/data/general_tree_npc_D.json',      # 滇系
            'Q': 'general_tree/data/general_tree_npc_Q.json',      # 黔軍
        }

        filename = tree_files.get(faction, tree_files['N'])
        tree = load_json(filename)
        # 川軍、湘軍是平行編制：沒有大帥，也不掛任何部屬，直接照檔案送出。
        if tree.get("flat_command"):
            return tree
        for general in tree.get("generals", {}).values():
            role = general.get("role")
            if role == "great_general":
                general["subordinate_slots"] = 3
            elif role == "lieutenant_general":
                general["subordinate_slots"] = min(3, max(2, int(general.get("subordinate_slots", 2))))
            else:
                general["subordinate_slots"] = 0
                general["subordinates"] = []
        return tree

    def do_HEAD(self) -> None:
        try:
            resolved = self._resolve_static_path(urlparse(self.path).path)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(resolved.stat().st_size))
        self.end_headers()

    def do_POST(self) -> None:
        routes: Dict[str, Callable[[Dict[str, Any]], Any]] = {
            "/api/new-game": self._new_game,
            "/api/next-turn": self._next_turn,
            "/api/respond-event": self._respond_event,
            "/api/ack-frontend-effects": self._ack_frontend_effects,
            "/api/draw-function": self._draw_function,
            "/api/cut-force": self._cut_force,
            "/api/use-function": self._use_function,
            "/api/discard-for-draw": self._discard_for_draw,
            "/api/diplomacy": self._diplomacy,
            "/api/deal": self._deal,
            "/api/respond-deal": self._respond_deal,
            "/api/train-unit": self._train_unit,
            "/api/train-navy-unit": self._train_navy_unit,
            "/api/reinforce-army": self._reinforce_army,
            "/api/reinforce-navy": self._reinforce_navy,
            "/api/quell-unrest": self._quell_unrest,
            "/api/repay-debt": self._repay_debt,
            "/api/loan-offers": self._loan_offers,
            "/api/take-loan": self._take_loan,
            "/api/pay-forced-march": self._pay_forced_march,
            "/api/pay-navy-move": self._pay_navy_move,
            "/api/pay-engineering": self._pay_engineering,
            "/api/turn-reinforcements": self._turn_reinforcements,
            "/api/embark-army": self._embark_army,
            "/api/refund-charge": self._refund_charge,
            "/api/repair-navy": self._repair_navy,
            "/api/navy-duel": self._navy_duel,
            "/api/army-navy-contact": self._army_navy_contact,
            "/api/capture-city": self._capture_city,
            "/api/recruit-captive-general": self._recruit_captive_general,
            "/api/attempt-defection": self._attempt_defection,
            "/api/defection-quote": self._defection_quote,
            "/api/loyalty-effect": self._loyalty_effect,
            "/api/shared-state": self._shared_state,
            "/api/restore-shared-state": self._restore_shared_state,
            "/api/combat": lambda payload: simulate_with_modifiers(payload, ENGINE),
            # 開打前的退卻預估：空跑一輪，只回傳數字，不改任何狀態。
            "/api/combat-outlook": lambda payload: combat_outlook(payload, ENGINE),
        }
        parsed = urlparse(self.path)
        if parsed.path not in routes:
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json()
            self._send_json(self._run_route(routes[parsed.path], payload))
        except SharedStateConflict as exc:
            self._send_json({"error": str(exc), "revision": SHARED_REVISION}, status=409)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def _run_route(self, handler, payload: Dict[str, Any]) -> Dict[str, Any]:
        """跑一個 POST 路由，並且在**伺服器自己改動了共享戰術狀態**時把版本推進。

        引擎會直接改 SHARED_TACTICAL_STATE：NPC 吞併換地格歸屬、部隊整批換旗、
        將領轉屬都是。先前 SHARED_REVISION 只在「前端推上來」時才加，於是這些
        改動的版本號原封不動——前端 pullSharedState() 看到版本沒變就不套用，
        後端算對的東西一格都畫不到地圖上，接著還會被前端那份舊快照覆蓋回去。

        判準是**內容真的變了**（比對前後的指紋），不是列一張「哪些路由會改」的
        清單——那種清單遲早會漏掉新加的路由。
        """
        global SHARED_REVISION
        before_revision = SHARED_REVISION
        before = _tactical_fingerprint()
        # 引擎手上那份戰術快照，每一個請求都重新綁成**現在這一份**。
        #
        # 先前只有 /api/next-turn 會傳 tactical 進去，其餘路由沿用上一次留下的
        # 那個物件。可是前端每推一次共享狀態，SHARED_TACTICAL_STATE 就會換成
        # 一份新的 dict，於是引擎手上那個變成孤兒：事件卡在 respond_event 裡
        # 把黔軍的地格、部隊、城市全部轉給了川軍——轉在一份沒有人再看的字典上。
        # applied 回報成功，地圖一格沒動。
        #
        # 綁在這裡而不是各路由自己傳，理由和下面推進版本那段一樣：
        # 「哪些路由會用到戰術快照」是一張遲早會漏掉新成員的清單。
        ENGINE._tactical = current_tactical()
        result = handler(payload)
        # 路由自己管過版本（/api/shared-state、/api/restore-shared-state）就不重複加。
        if SHARED_REVISION == before_revision and _tactical_fingerprint() != before:
            with SHARED_LOCK:
                SHARED_REVISION += 1
                save_tactical_state()
            if isinstance(result, dict) and "revision" not in result:
                result["revision"] = SHARED_REVISION
        return result

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _next_turn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        force = bool(payload.get("force")) and self.client_address[0] in {"127.0.0.1", "::1"}
        return ENGINE.next_turn(
            payload.get("active_player"),
            force=force,
            riot_garrisons=payload.get("riot_garrisons") or {},
            city_garrisons=payload.get("city_garrisons") or {},
            contested_provinces=payload.get("contested_provinces"),
            fallen_marshals=payload.get("fallen_marshals"),
            faction_trait_holders=payload.get("faction_trait_holders"),
            ultimatum_garrisons=payload.get("ultimatum_garrisons") or {},
            # 哪些城市有誰的駐軍——前端報事實，規則在後端判（15.16 南京事件）。
            city_garrison_report=payload.get("city_garrison_report") or {},
            marshal_ids=payload.get("marshal_ids") or {},
            # NPC 事件卡的觸發條件要看將領與編制的現況，那份資料在共享戰術狀態裡。
            tactical=current_tactical(),
        )

    def _new_game(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        global SHARED_TACTICAL_STATE, SHARED_REVISION
        players = payload.get("players") or DEFAULT_PLAYERS
        seed = payload.get("seed")
        result = ENGINE.new_game(players=players, seed=seed)
        with SHARED_LOCK:
            SHARED_TACTICAL_STATE = None
            SHARED_REVISION += 1
            # 清除舊遊戲的戰術狀態檔案
            save_tactical_state()
        return result

    def _shared_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        global SHARED_TACTICAL_STATE, SHARED_REVISION
        tactical = payload.get("tactical")
        if not isinstance(tactical, dict):
            raise ValueError("shared tactical state must be an object")
        with SHARED_LOCK:
            expected = payload.get("expected_revision")
            if expected is not None and int(expected) != SHARED_REVISION:
                raise SharedStateConflict("shared game changed on another device")
            SHARED_TACTICAL_STATE = tactical
            SHARED_REVISION += 1
            # 寫入磁碟，防止伺服器重啟時丟失戰術狀態
            save_tactical_state()
            return {
                "revision": SHARED_REVISION,
                "tactical": SHARED_TACTICAL_STATE,
                # 忠誠的規則住在後端。前端送上來的是它擁有的事實（部隊編制、
                # 忠誠覆寫、誰在誰手上），算出來的數字由後端回給它顯示——
                # 同一套算式不該在兩邊各跑一次。
                "loyalty": ENGINE.loyalty_report(SHARED_TACTICAL_STATE),
                "navy_outlook": ENGINE.navy_outlook(SHARED_TACTICAL_STATE),
                "railway_access": ENGINE.railway_access(),
                "engine_state": ENGINE.snapshot(),
            }

    def _restore_shared_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        global SHARED_TACTICAL_STATE, SHARED_REVISION
        engine_state = payload.get("engine_state")
        if not isinstance(engine_state, dict):
            raise ValueError("restore requires engine_state")
        tactical = payload.get("tactical")
        if tactical is not None and not isinstance(tactical, dict):
            raise ValueError("tactical state must be an object")
        restored_engine = ENGINE.restore_snapshot(engine_state)
        with SHARED_LOCK:
            SHARED_TACTICAL_STATE = tactical
            SHARED_REVISION = int(payload.get("revision", SHARED_REVISION)) + 1
            return {
                "revision": SHARED_REVISION,
                "tactical": SHARED_TACTICAL_STATE,
                "loyalty": ENGINE.loyalty_report(SHARED_TACTICAL_STATE),
                "navy_outlook": ENGINE.navy_outlook(SHARED_TACTICAL_STATE),
                "railway_access": ENGINE.railway_access(),
                "engine_state": restored_engine,
            }

    def _draw_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.draw_function(str(payload["player"]))

    def _cut_force(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """把一支部隊裁到指定的戰力點。部隊住在前端，裁法住在後端。"""
        return ENGINE.cut_units_to_force(
            payload.get("units") or {},
            target=payload.get("target"),
            multiplier=payload.get("multiplier"),
        )

    def _use_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.use_function(
            str(payload["player"]),
            str(payload["card_id"]),
            target_general_id=payload.get("target_general_id"),
            target_owner=payload.get("target_owner"),
            target_city_id=payload.get("target_city_id"),
            target_city_ids=payload.get("target_city_ids"),
            target_province=payload.get("target_province"),
            target_provinces=payload.get("target_provinces"),
            target_railway=payload.get("target_railway"),
            target_power=payload.get("target_power"),
            exchange_direction=payload.get("exchange_direction"),
            exchange_amount=payload.get("exchange_amount"),
            current_slots=payload.get("current_slots"),
        )

    def _respond_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.respond_event(
            str(payload["player"]), choice=payload.get("choice"), follow_up=payload.get("follow_up"),
            # 吞併、歸屬轉移、編制增減的卡全部在這裡結算，改的是戰術快照。
            # 傳的必須是伺服器現在手上這一份，不能沿用上一次 next_turn 留下的。
            tactical=current_tactical(),
        )

    def _ack_frontend_effects(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 前端把 pending_frontend_effects 執行完之後回來銷帳。
        return ENGINE.consume_frontend_effects(
            str(payload["player"]), kind=payload.get("kind") or None,
            # 逐筆銷帳：前端只銷它真的做完的那幾筆。
            ids=payload.get("ids"),
        )

    def _discard_for_draw(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.discard_for_draw(str(payload["player"]), str(payload["card_id"]))

    def _diplomacy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.set_diplomacy(
            str(payload["player"]),
            str(payload["target"]),
            str(payload["status"]),
            peace_card_id=payload.get("peace_card_id"),
        )

    def _loan_offers(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.loan_offers(str(payload["player"]))

    def _take_loan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.take_loan(str(payload["player"]), str(payload["bank"]), int(payload["amount"]))

    def _pay_forced_march(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 金額由引擎的常數決定；payload 裡的 cash/factory 一律不採用。
        return ENGINE.pay_forced_march(
            str(payload["player"]),
            army_id=str(payload.get("army_id") or ""),
        )

    def _pay_navy_move(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 成本由艦隊現況算出來，不收前端送來的 factory。
        return ENGINE.pay_navy_move(
            str(payload["player"]),
            navy=payload.get("navy"),
            navy_id=str(payload.get("navy_id") or "") or None,
        )

    def _pay_engineering(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.pay_engineering(
            str(payload["player"]),
            str(payload["operation"]),
            str(payload.get("cell_key") or "") or None,
        )

    def _refund_charge(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.refund_charge(str(payload["player"]), str(payload["charge_id"]))

    def _turn_reinforcements(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 回合結束時的自動補兵：NPC 增援與野戰醫院。規則與擲骰都在後端，
        # 用的是伺服器自己手上的編制，前端只把回傳的編制寫回去。
        with SHARED_LOCK:
            return ENGINE.turn_reinforcements(SHARED_TACTICAL_STATE, payload.get("turn"))

    def _embark_army(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """陸軍上船的容量門檻由後端把關，不是只在前端擋一下。"""
        return ENGINE.authorize_embark(payload.get("navy") or {},
                                       payload.get("army_units") or {})

    def _navy_duel(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """兩支艦隊對射。前端送兩支艦隊的現況，後端結算並回傳更新後的艦隊。"""
        return ENGINE.resolve_navy_duel(payload["attacker"], payload["defender"])

    def _army_navy_contact(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """陸軍砲兵與艦隊接觸。"""
        return ENGINE.resolve_army_navy_contact(payload.get("army_units") or {},
                                                payload["navy"])

    def _repair_navy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 前端送艦隊現況與目標 HP，補幾點、收多少工業點由後端算。
        return ENGINE.repair_navy(
            str(payload["player"]),
            int(payload.get("hp", 0)),
            payload.get("navy"),
            payload.get("target_hp"),
            payload.get("city_id"),
        )

    def _capture_city(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.capture_city(str(payload["city_id"]), str(payload["faction"]))

    def _recruit_captive_general(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.recruit_captive_general(
            str(payload["player"]), payload.get("traits"), payload.get("general_id"),
        )

    def _attempt_defection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 成本與成功率由後端從共享戰術快照算。前端只要指名對象；
        # loyalty／force／resistance 這三個欄位還收，只是為了舊的呼叫端，
        # 有 general_id 時一概忽略。
        return ENGINE.attempt_defection_with_force(
            str(payload["player"]),
            int(payload.get("loyalty", 0) or 0),
            float(payload.get("force", 0) or 0),
            payload.get("traits"),
            float(payload.get("resistance", 0) or 0),
            payload.get("general_id"),
            tactical=current_tactical(),
        )

    def _loyalty_effect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 忠誠加減：挑誰、加多少、算成什麼樣的 override，全在後端。
        return ENGINE.resolve_loyalty_effect(
            str(payload["kind"]), str(payload["faction"]), payload.get("effect") or {},
            tactical=current_tactical())

    def _defection_quote(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 面板上的「策反費用／成功率」只能有一個來源。
        return ENGINE.defection_quote(str(payload["general_id"]),
                                      tactical=current_tactical())

    def _deal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.make_deal(
            str(payload["player"]),
            str(payload["target"]),
            funds=int(payload.get("funds", 0)),
            unit_type=payload.get("unit_type"),
            reserve=int(payload.get("reserve", 0)),
        )

    def _respond_deal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.respond_to_deal(
            str(payload["player"]), int(payload["deal_id"]), bool(payload.get("accept"))
        )

    def _train_unit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.train_unit(
            str(payload["player"]),
            str(payload["unit_type"]),
            int(payload.get("count", 1)),
        )

    def _train_navy_unit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.train_navy_unit(
            str(payload["player"]),
            str(payload["unit_type"]),
            int(payload.get("count", 1)),
        )

    def _reinforce_army(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # 戰力上限的基準值取自伺服器自己手上的部隊編制（SHARED_TACTICAL_STATE），
        # 不是前端送來的 current_force——那個數字前端可以隨便報，報低就能無限補兵，
        # 而且欄位是 Optional，乾脆不送整段檢查就被跳過。
        army_id = str(payload["army_id"])
        current_force = ENGINE.army_force_from_tactical(SHARED_TACTICAL_STATE, army_id)
        if current_force is None:
            current_force = payload.get("current_force")
        return ENGINE.reinforce_army(
            str(payload["player"]),
            army_id,
            str(payload["city_id"]),
            str(payload["unit_type"]),
            int(payload.get("count", 1)),
            current_force,
        )

    def _reinforce_navy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.reinforce_navy(
            str(payload["player"]),
            str(payload["city_id"]),
            str(payload["unit_type"]),
            int(payload.get("count", 1)),
        )

    def _quell_unrest(self, payload):
        """付錢提前平息一起治安事件（罷工 $10、碼頭工潮／米騷動 $20）。"""
        return ENGINE.quell_unrest(str(payload["player"]), str(payload["effect_id"]))

    def _repay_debt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.repay_debt(str(payload["player"]), int(payload.get("amount", 0)))

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def _send_json(self, payload: Any, *, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        try:
            resolved = self._resolve_static_path(path)
            body = resolved.read_bytes()
        except FileNotFoundError:
            self._send_json({"error": "not found"}, status=404)
            return
        content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _resolve_static_path(self, path: str) -> Path:
        if path in ("", "/"):
            file_path = FRONTEND_ROOT / "index.html"
        elif path.startswith("/pj/"):
            file_path = PJ_ROOT / unquote(path.removeprefix("/pj/"))
        elif path.startswith("/assets/portraits/"):
            name = unquote(path.removeprefix("/assets/portraits/"))
            local = LOCAL_PORTRAIT_ROOT / name
            file_path = local if local.is_file() else PORTRAIT_ROOT / name
        else:
            file_path = FRONTEND_ROOT / unquote(path.lstrip("/"))
        resolved = file_path.resolve()
        if not (
            str(resolved).startswith(str(FRONTEND_ROOT.resolve()))
            or str(resolved).startswith(str(PJ_ROOT.resolve()))
            or str(resolved).startswith(str(PORTRAIT_ROOT.resolve()))
        ):
            raise FileNotFoundError
        if not resolved.is_file():
            raise FileNotFoundError
        return resolved


def run(host: str = "0.0.0.0", port: int = 8766) -> None:
    # 伺服器啟動時載入先前保存的戰術狀態，避免重啟後資料丟失
    load_tactical_state()
    server = ThreadingHTTPServer((host, port), PlaytestHandler)
    print(f"Playtest server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
