"""Stdlib HTTP server for the playtest frontend and JSON API."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.parse import unquote, urlparse

from .card_engine import DEFAULT_PLAYERS, GameEngine
from .combat_adapter import simulate as simulate_combat
from .data_store import REPO_ROOT


FRONTEND_ROOT = REPO_ROOT / "frontend"
PORTRAIT_ROOT = REPO_ROOT / "PJ Boardgame" / "portraits"
ENGINE = GameEngine()


class PlaytestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(ENGINE.bootstrap())
            return
        if parsed.path == "/api/state":
            self._send_json(ENGINE.snapshot())
            return
        self._serve_static(parsed.path)

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
            "/api/next-turn": lambda _: ENGINE.next_turn(),
            "/api/draw-event": lambda _: ENGINE.draw_event(),
            "/api/draw-function": self._draw_function,
            "/api/use-function": self._use_function,
            "/api/combat": lambda payload: simulate_combat(payload),
        }
        parsed = urlparse(self.path)
        if parsed.path not in routes:
            self._send_json({"error": "not found"}, status=404)
            return
        try:
            payload = self._read_json()
            self._send_json(routes[parsed.path](payload))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _new_game(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        players = payload.get("players") or DEFAULT_PLAYERS
        seed = payload.get("seed")
        return ENGINE.new_game(players=players, seed=seed)

    def _draw_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.draw_function(str(payload["player"]))

    def _use_function(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return ENGINE.use_function(str(payload["player"]), str(payload["card_id"]))

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
        elif path.startswith("/assets/portraits/"):
            file_path = PORTRAIT_ROOT / unquote(path.removeprefix("/assets/portraits/"))
        else:
            file_path = FRONTEND_ROOT / unquote(path.lstrip("/"))
        resolved = file_path.resolve()
        if not (
            str(resolved).startswith(str(FRONTEND_ROOT.resolve()))
            or str(resolved).startswith(str(PORTRAIT_ROOT.resolve()))
        ):
            raise FileNotFoundError
        if not resolved.is_file():
            raise FileNotFoundError
        return resolved


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), PlaytestHandler)
    print(f"Playtest server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
