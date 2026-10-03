import unittest

from services.prediction_engine import MarketFavoritePredictionEngine, PredictionEngine, RandomForestPredictionEngine


class MarketFavoritePredictionEngineTests(unittest.TestCase):
    def test_favorite_engine_selects_shortest_wld_odds(self) -> None:
        match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 1.8, "draw": 3.2, "away": 4.0},
            "scheduled_at": "2026-10-01T18:00:00+00:00",
        }
        subscription = {"max_odds": 3, "allowed_sports": ["soccer"], "allowed_markets": ["WLD"]}
        admin_config = {"allowed_markets": {"soccer": ["WLD"]}}

        value_pick = PredictionEngine().build_slips([match], subscription, admin_config)[0]
        favorite_pick = MarketFavoritePredictionEngine().build_slips([match], subscription, admin_config)[0]

        self.assertEqual(value_pick["selection"], "away")
        self.assertEqual(favorite_pick["selection"], "home")
        self.assertIn("favorite", favorite_pick["reason"].lower())

    def test_favorite_engine_selects_shortest_two_way_odds(self) -> None:
        match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "NHL",
            "sport": "hockey",
            "market": "Over/Under",
            "odds": {"over": 2.2, "under": 1.7},
            "scheduled_at": "2026-10-01T18:00:00+00:00",
        }
        subscription = {"max_odds": 3, "allowed_sports": ["hockey"], "allowed_markets": ["Over/Under"]}
        admin_config = {"allowed_markets": {"hockey": ["Over/Under"]}}

        picks = MarketFavoritePredictionEngine().build_slips([match], subscription, admin_config)

        self.assertEqual(picks[0]["selection"], "Under")


class RandomForestPredictionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 2.4, "draw": 3.2, "away": 1.6},
        }
        self.subscription = {"max_odds": 1, "allowed_sports": ["soccer"], "allowed_markets": ["WLD"]}
        self.admin_config = {"allowed_markets": {"soccer": ["WLD"]}}

    def test_random_forest_selects_highest_predicted_win_probability(self) -> None:
        history = []
        for selection, odds, wins, losses in [
            ("home", 2.4, 24, 6),
            ("away", 1.6, 6, 24),
            ("draw", 3.2, 10, 20),
        ]:
            for _ in range(wins):
                history.append({"sport": "soccer", "market": "WLD", "league": "Premier League", "selection": selection, "odds": odds, "status": "won"})
            for _ in range(losses):
                history.append({"sport": "soccer", "market": "WLD", "league": "Premier League", "selection": selection, "odds": odds, "status": "lost"})

        engine = RandomForestPredictionEngine(history_provider=lambda: history)
        pick = engine.build_slips([self.match], self.subscription, self.admin_config)[0]

        self.assertEqual(pick["selection"], "home")
        self.assertIn("Random Forest", pick["reason"])

    def test_random_forest_can_select_a_specific_goal_line(self) -> None:
        match = {
            **self.match,
            "market": "Over/Under",
            "odds": {"over_1_5": 1.4, "under_1_5": 3.2, "over_2_5": 1.9, "under_2_5": 2.0},
        }
        history = []
        for selection, odds, wins, losses in [
            ("Over 1.5 Goals", 1.4, 6, 24),
            ("Under 1.5 Goals", 3.2, 24, 6),
            ("Over 2.5 Goals", 1.9, 10, 20),
            ("Under 2.5 Goals", 2.0, 10, 20),
        ]:
            for _ in range(wins):
                history.append({"sport": "soccer", "market": "Over/Under", "league": "Premier League", "selection": selection, "odds": odds, "status": "won"})
            for _ in range(losses):
                history.append({"sport": "soccer", "market": "Over/Under", "league": "Premier League", "selection": selection, "odds": odds, "status": "lost"})

        engine = RandomForestPredictionEngine(history_provider=lambda: history)
        subscription = {**self.subscription, "allowed_markets": ["Over/Under"]}
        admin_config = {"allowed_markets": {"soccer": ["Over/Under"]}}
        pick = engine.build_slips([match], subscription, admin_config)[0]

        self.assertEqual(pick["selection"], "Under 1.5 Goals")

    def test_empty_history_uses_explicit_market_favorite_cold_start(self) -> None:
        engine = RandomForestPredictionEngine(history_provider=lambda: [])

        pick = engine.build_slips([self.match], self.subscription, self.admin_config)[0]

        self.assertEqual(pick["selection"], "away")
        self.assertIn("Cold-start", pick["reason"])


if __name__ == "__main__":
    unittest.main()