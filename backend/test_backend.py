import unittest

from backend.card_engine import GameEngine
from backend.combat_adapter import simulate
from backend.data_store import load_game_data


class BackendTests(unittest.TestCase):
    def test_data_loads_with_unique_card_ids(self):
        data = load_game_data()

        self.assertGreater(data["metadata"]["event_cards"], 100)
        self.assertGreater(data["metadata"]["function_cards"], 50)
        self.assertGreater(data["metadata"]["injected_event_cards"], 10)

    def test_turn_draws_event_and_player_function_cards(self):
        engine = GameEngine(seed=7)
        result = engine.next_turn()

        self.assertEqual(result["turn"]["turn"], 1)
        self.assertIn("id", result["turn"]["event"])
        for player in ("F", "W", "S", "N"):
            self.assertEqual(result["state"]["counts"]["players"][player]["hand"], 1)

    def test_using_function_injects_event_cards(self):
        engine = GameEngine(seed=3)
        engine.state["players"]["F"]["hand"].append("japanese_debt_for_firearms")
        before = len(engine.state["event_pool"])

        result = engine.use_function("F", "japanese_debt_for_firearms")

        self.assertGreater(len(engine.state["event_pool"]), before)
        self.assertEqual(result["injected"][0]["id"], "north_manchuria_railway_concession_demand")

    def test_combat_adapter_runs_existing_combat_system(self):
        result = simulate(
            {
                "army_a": {"units": {"infantry": 3}},
                "army_b": {"units": {"infantry": 3}},
                "max_rounds": 1,
            }
        )

        self.assertIn(result["winner"], {"A", "B", "draw", "stalemate", "undecided"})


if __name__ == "__main__":
    unittest.main()
