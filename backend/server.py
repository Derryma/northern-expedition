"""Stdlib HTTP server for the playtest frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from .card_engine import DEFAULT_PLAYERS, GameEngine
from .combat_adapter import simulate as simulate_combat
from .data_store import REPO_ROOT


FRONTEND_ROOT = REPO_ROOT / "frontend"
PJ_ROOT = REPO_ROOT / "PJ Boardgame"
PORTRAIT_ROOT = REPO_ROOT / "PJ Boardgame" / "portraits"
ENGINE = GameEngine()
SHARED_LOCK = RLock()
SHARED_TACTICAL_STATE: Optional[Dict[str, Any]] = None
SHARED_REVISION = 0


class SharedStateConflict(Exception):
    pass


class PlaytestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(ENGINE.bootstrap())
            return
        if parsed.path == "/api/state":
            self._send_json(ENGINE.snapshot())
            return
        if parsed.path == "/api/shared-state":
            with SHARED_LOCK:
                self._send_json({
                    "revision": SHARED_REVISION,
                    "tactical": SHARED_TACTICAL_STATE,
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
        }

        filename = tree_files.get(faction, tree_files['N'])
        return load_json(filename)

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
            "/api/next-turn": lambda payload: ENGINE.next_turn(payload.get("active_player")),
            "/api/draw-event": lambda _: ENGINE.draw_event(),
            "/api/draw-function": self._draw_function,
            "/api/use-function": self._use_function,
            "/api/discard-for-draw": self._discard_for_draw,
            "/api/diplomacy": self._diplomacy,
            "/api/deal": self._deal,
            "/api/respond-deal": self._respond_deal,
            "/api/train-unit": self._train_unit,
            "/api/reinforce-army": self._reinforce_army,
            "/api/repay-debt": self._repay_debt,
            "/api/capture-city": self._capture_city,
            "/api/recruit-captive-general": self._recruit_captive_general,
            "/api/attempt-defection": self._attempt_defection,
            "/api/shared-state": self._shared_state,
            "/api/combat": lambda payload: simulate_combat(payload),
        }
        parsed = urlparse(self.path)
        if parsed.path not in routes:
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json()
            self._send_json(routes[parsed.path](payload))
        except SharedStateConflict as exc:
            self._send_json({"error": str(exc), "revision": SHARED_REVISION}, status=409)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _new_game(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        global SHARED_TACTICAL_STATE, SHARED_REVISION
        players = payload.get("players") or DEFAULT_PLAYERS
        seed = payload.get("seed")
        result = ENGINE.new_game(players=players, seed=seed)
        with SHARED_LOCK:
            SHARED_TACTICAL_STATE = None
            SHARED_REVISION += 1
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
            return {
                "revision": SHARED_REVISION,
                "tactical": SHARED_TACTICAL_STATE,
                "engine_state": ENGINE.snapshot(),
            }

    def _draw_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.draw_function(str(payload["player"]))

    def _use_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.use_function(
            str(payload["player"]),
            str(payload["card_id"]),
            target_general_id=payload.get("target_general_id"),
            target_owner=payload.get("target_owner"),
            target_city_id=payload.get("target_city_id"),
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

    def _capture_city(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.capture_city(str(payload["city_id"]), str(payload["faction"]))

    def _recruit_captive_general(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.recruit_captive_general(str(payload["player"]))

    def _attempt_defection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.attempt_defection_with_force(
            str(payload["player"]), int(payload["loyalty"]), float(payload.get("force", 1)),
        )

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

    def _reinforce_army(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.reinforce_army(
            str(payload["player"]),
            str(payload["army_id"]),
            str(payload["city_id"]),
            str(payload["unit_type"]),
            int(payload.get("count", 1)),
        )

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
            file_path = PORTRAIT_ROOT / unquote(path.removeprefix("/assets/portraits/"))
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
    server = ThreadingHTTPServer((host, port), PlaytestHandler)
    print(f"Playtest server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
