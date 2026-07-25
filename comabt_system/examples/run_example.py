import json
import sys
from pathlib import Path
from pprint import pprint

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from combat import simulate_battle


HERE = Path(__file__).resolve().parent


def load_json(name):
    with open(HERE / name, "r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    a_1st = load_json("a_1st_army.json")
    a_2nd = load_json("a_2nd_army.json")
    b_1st = load_json("b_1st_army.json")

    result = simulate_battle(
        a_1st,
        b_1st,
        max_rounds=5,
        reinforcements=[
            {
                "round": 2,
                "side": "A",
                "army": a_2nd
            }
        ]
    )

    pprint(result)
