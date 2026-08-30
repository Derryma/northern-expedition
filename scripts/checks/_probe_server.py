# -*- coding: utf-8 -*-
"""測試用的伺服器啟動器：先把後端的規則數字換成隨機怪值，再起服務。

只給 backend_drives_ui_e2e.py 用。產品程式碼裡不留任何測試旗標——
要驗「前端有沒有自己那一份」，就得讓後端說一個前端絕對猜不到的數字。
"""
import json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

probe = json.loads(os.environ.get("NE_UI_PROBE") or "{}")

from backend import card_engine
from backend.card_engine import FEATURES, GameEngine

if probe:
    FEATURES["function_card_max_hand_size"] = probe["hand_size"]
    FEATURES["function_card_draw_cost"] = probe["draw_cost"]
    FEATURES["army_force_cap"] = probe["force_cap"]
    FEATURES["unit_force_points"]["cavalry"] = probe["cavalry_force_points"]
    FEATURES["forced_march"]["cash"] = probe["forced_march_cash"]
    FEATURES["forced_march"]["tiles"] = probe["forced_march_tiles"]
    GameEngine.ENGINEERING_OPERATIONS["pontoon_bridge"] = dict(
        GameEngine.ENGINEERING_OPERATIONS["pontoon_bridge"],
        factory_cost=probe["engineering_factory_cost"])
    GameEngine.DEFECTION_RESISTANCE_TRAITS = {
        "buddhist_general": probe["defection_resistance"]}

from backend import server

if probe:
    server.ENGINE.data["navy_system"]["move"]["factory_cost_per_gun_boat"] = \
        probe["navy_move_per_gun_boat"]

server.run()
