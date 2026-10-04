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

    def test_dixon_coles_fallback_does_not_predict_other_sports(self) -> None:
        match = {**self.match, "sport": "hockey"}
        subscription = {**self.subscription, "allowed_sports": ["hockey"]}
        admin_config = {"allowed_markets": {"hockey": ["WLD"]}}
        engine = LSTMPredictionEngine(history_provider=lambda: [])

        self.assertEqual(engine.build_slips([match], subscription, admin_config), [])

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
