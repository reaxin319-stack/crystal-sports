import unittest

from services.prediction_engine import MarketFavoritePredictionEngine, PredictionEngine


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


if __name__ == "__main__":
    unittest.main()