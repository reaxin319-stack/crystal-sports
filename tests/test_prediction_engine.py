import unittest
from datetime import datetime, timedelta, timezone

from services.lstm_prediction_engine import LSTMPredictionEngine


class LSTMPredictionEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 2.4, "draw": 3.2, "away": 1.6},
        }
        self.subscription = {
            "max_odds": 1,
            "allowed_sports": ["soccer"],
            "allowed_markets": ["WLD"],
        }
        self.admin_config = {"allowed_markets": {"soccer": ["WLD"]}}

    def _resolved_history(self):
        history = []
        for index in range(80):
            selection = "home" if index % 2 == 0 else "away"
            history.append(
                {
                    "sport": "soccer",
                    "market": "WLD",
                    "league": "Premier League",
                    "home_team": "Home FC",
                    "away_team": "Away FC",
                    "selection": selection,
                    "odds": 2.4 if selection == "home" else 1.6,
                    "status": "won" if selection == "home" else "lost",
                    "scheduled_at": (
                        datetime(2026, 1, 1, tzinfo=timezone.utc)
                        + timedelta(hours=index)
                    ).isoformat(),
                }
            )
        return history

    def test_no_resolved_history_uses_dixon_coles_soccer_fallback(self) -> None:
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        picks = engine.build_slips([self.match], self.subscription, self.admin_config)

        self.assertTrue(picks)
        self.assertFalse(engine.is_trained)
        self.assertEqual(engine.training_record_count, 0)
        self.assertIn("Dixon-Coles soccer fallback", picks[0]["reason"])

    def test_dixon_coles_fallback_supports_goal_lines(self) -> None:
        match = {
            **self.match,
            "market": "Over/Under",
            "odds": {
                "over_1_5": 1.4,
                "under_1_5": 3.0,
                "over_2_5": 1.8,
                "under_2_5": 2.0,
            },
        }
        subscription = {**self.subscription, "allowed_markets": ["Over/Under"]}
        admin_config = {"allowed_markets": {"soccer": ["Over/Under"]}}
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        picks = engine.build_slips([match], subscription, admin_config)

        self.assertTrue(picks)
        self.assertIn("Goals", picks[0]["selection"])
        self.assertIn("Dixon-Coles soccer fallback", picks[0]["reason"])

    def test_market_implied_fallback_predicts_hockey(self) -> None:
        match = {**self.match, "sport": "hockey"}
        subscription = {**self.subscription, "allowed_sports": ["hockey"]}
        admin_config = {"allowed_markets": {"hockey": ["WLD"]}}
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        picks = engine.build_slips([match], subscription, admin_config)

        self.assertEqual(len(picks), 1)
        self.assertIn(picks[0]["selection"], {"home", "draw", "away"})
        self.assertIn("Market-implied fallback", picks[0]["reason"])

    def test_market_implied_fallback_supports_tennis_winner_market(self) -> None:
        match = {
            **self.match,
            "sport": "tennis",
            "market": "Who Wins Set",
            "odds": {"player_a": 1.8, "player_b": 2.05},
        }
        subscription = {
            **self.subscription,
            "allowed_sports": ["tennis"],
            "allowed_markets": ["Who Wins Set"],
        }
        admin_config = {"allowed_markets": {"tennis": ["Who Wins Set"]}}
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        picks = engine.build_slips([match], subscription, admin_config)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["selection"], "Player A")
        self.assertEqual(picks[0]["odds"], 1.8)

    def test_market_implied_fallback_supports_cards_market(self) -> None:
        match = {
            **self.match,
            "market": "Cards",
            "odds": {"cards_over": 1.8, "cards_under": 1.9},
        }
        subscription = {**self.subscription, "allowed_markets": ["Cards"]}
        admin_config = {"allowed_markets": {"soccer": ["Cards"]}}
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        picks = engine.build_slips([match], subscription, admin_config)

        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0]["selection"], "Over Cards")

    def test_market_implied_fallback_supports_double_chance_btts_and_handicap(self) -> None:
        market_cases = [
            (
                "Double Chance",
                {"1x": 1.4, "12": 1.3, "x2": 1.6},
                "12",
            ),
            ("BTTS", {"yes": 1.8, "no": 2.0}, "Yes"),
            (
                "Handicap",
                {"home_handicap": 1.8, "away_handicap": 2.0, "line": -0.5},
                "Home -0.5",
            ),
        ]

        for market, odds, expected_selection in market_cases:
            with self.subTest(market=market):
                match = {**self.match, "market": market, "odds": odds}
                subscription = {**self.subscription, "allowed_markets": [market]}
                admin_config = {"allowed_markets": {"soccer": [market]}}
                engine = LSTMPredictionEngine(history_provider=lambda: [])

                picks = engine.build_slips([match], subscription, admin_config)

                self.assertEqual(len(picks), 1)
                self.assertEqual(picks[0]["selection"], expected_selection)

    def test_lstm_selects_learned_outcome_from_ordered_history(self) -> None:
        engine = LSTMPredictionEngine(history_provider=self._resolved_history)

        picks = engine.build_slips([self.match], self.subscription, self.admin_config)

        self.assertTrue(engine.is_trained)
        self.assertEqual(picks[0]["selection"], "home")
        self.assertIn("LSTM", picks[0]["reason"])

    def test_goal_total_candidates_keep_each_line_distinct(self) -> None:
        match = {
            **self.match,
            "market": "Over/Under",
            "odds": {
                "over_1_5": 1.35,
                "under_1_5": 3.1,
                "over_2_5": 1.9,
                "under_2_5": 1.95,
            },
        }
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        candidates = engine._build_candidates(match)

        self.assertEqual(
            {pick["selection"] for pick, _ in candidates},
            {"Over 1.5 Goals", "Under 1.5 Goals", "Over 2.5 Goals", "Under 2.5 Goals"},
        )


if __name__ == "__main__":
    unittest.main()
