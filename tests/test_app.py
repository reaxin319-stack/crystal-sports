import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import app
from services.prediction_engine import MarketFavoritePredictionEngine, PredictionEngine


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()

    def test_predictions_page_loads(self) -> None:
        response = self.client.get("/predictions")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Predictions", response.data)

    def test_predictions_page_shows_market_favorite_engine(self) -> None:
        match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 1.8, "draw": 3.2, "away": 4.0},
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        }

        class TestDataService:
            def get_live_matches(self):
                return [match]

            def get_configured_leagues(self):
                return []

        class TestAdminService:
            def get_plan(self, _plan_name):
                return {
                    "name": "Free",
                    "duration": "1 month",
                    "max_odds": 3,
                    "allowed_sports": ["soccer"],
                    "allowed_markets": ["WLD"],
                }

            def get_config(self):
                return {"allowed_markets": {"soccer": ["WLD"]}}

        with patch.dict(
            app.config,
            {
                "DATA_SERVICE": TestDataService(),
                "ADMIN_SERVICE": TestAdminService(),
                "PREDICTION_ENGINE": PredictionEngine(),
                "MARKET_FAVORITE_PREDICTION_ENGINE": MarketFavoritePredictionEngine(),
            },
        ):
            response = self.client.get("/predictions")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Market Favorite Engine", response.data)
        self.assertIn(b"Selection: <strong>home</strong>", response.data)

    def test_register_requires_only_email_and_password_and_ignores_plan(self) -> None:
        created_user = {"id": 42, "email": "new@example.com"}
        with patch("app.models.get_user_by_email", return_value=None), patch(
            "app.models.get_user_by_username", return_value=None
        ), patch("app.models.create_user", return_value=created_user) as create_user, patch(
            "app.models.set_confirm_token"
        ), patch("app.send_email"):
            response = self.client.post(
                "/register",
                data={"email": "new@example.com", "password": "secure-password", "plan": "vip"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(create_user.call_args.args[0].startswith("member_"))
        self.assertEqual(create_user.call_args.args[1:], ("new@example.com", "secure-password", "free"))

    def test_registration_form_only_requests_email_and_password(self) -> None:
        response = self.client.get("/register")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="email"', response.data)
        self.assertIn(b'name="password"', response.data)
        self.assertNotIn(b'name="username"', response.data)
        self.assertNotIn(b'name="plan"', response.data)

    def test_login_accepts_email(self) -> None:
        user = {"id": 42}
        with patch("app.models.verify_user", return_value=user) as verify_user:
            response = self.client.post(
                "/login",
                data={"email": "person@example.com", "password": "secure-password"},
            )

        self.assertEqual(response.status_code, 302)
        verify_user.assert_called_once_with("person@example.com", "secure-password")


if __name__ == "__main__":
    unittest.main()
