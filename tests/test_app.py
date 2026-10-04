import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import app
from services.daily_picks import DailyPickService
from services.lstm_prediction_engine import LSTMPredictionEngine


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()

    def test_home_page_displays_live_scores_in_feed(self) -> None:
        match = {
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "Premier League",
            "sport": "soccer",
            "home_score": "2",
            "away_score": "1",
            "is_live": True,
            "status_detail": "63'",
            "scheduled_at": "2026-10-01T12:00:00+00:00",
        }

        class TestDataService:
            def get_configured_leagues(self):
                return []

            def get_live_matches(self):
                return [match]

        class TestAdminService:
            def get_available_sports(self):
                return []

        with patch.dict(
            app.config,
            {"DATA_SERVICE": TestDataService(), "ADMIN_SERVICE": TestAdminService()},
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Live Feed", response.data)
        self.assertIn(b"Home FC", response.data)
        self.assertIn(b"2 - 1", response.data)
        self.assertIn(b"LIVE", response.data)

    def test_predictions_page_loads(self) -> None:
        response = self.client.get("/predictions")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Predictions", response.data)

    def test_predictions_page_shows_dixon_coles_fallback(self) -> None:
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
                "DAILY_PICK_SERVICE": DailyPickService(),
                "ADMIN_SERVICE": TestAdminService(),
                "PREDICTION_ENGINE": LSTMPredictionEngine(history_provider=lambda: []),
            },
        ):
            response = self.client.get("/predictions")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dixon-Coles Fallback Final Selections", response.data)
        self.assertIn(b"Dixon-Coles soccer fallback active.", response.data)
        self.assertIn(b"Selection: <strong>home</strong>", response.data)

    def test_register_requires_username_email_and_password(self) -> None:
        created_user = {"id": 42, "email": "new@example.com"}
        with patch("app.models.get_user_by_email", return_value=None), patch(
            "app.models.get_user_by_username", return_value=None
        ), patch("app.models.create_user", return_value=created_user) as create_user, patch(
            "app.models.set_confirm_token"
        ), patch("app.send_email"):
            response = self.client.post(
                "/register",
                data={"username": "newmember", "email": "new@example.com", "password": "secure-password"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(create_user.call_args.args, ("newmember", "new@example.com", "secure-password", "free"))
        self.assertEqual(response.location, "/dashboard")

    def test_register_rejects_missing_username(self) -> None:
        with patch("app.models.create_user") as create_user:
            response = self.client.post(
                "/register",
                data={"email": "new@example.com", "password": "secure-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Username, email, and password are required", response.data)
        create_user.assert_not_called()

    def test_registration_form_requires_username_email_and_password(self) -> None:
        response = self.client.get("/register")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="username"', response.data)
        self.assertIn(b'name="email"', response.data)
        self.assertIn(b'name="password"', response.data)
        self.assertNotIn(b'name="plan"', response.data)

    def test_login_uses_username_and_password(self) -> None:
        user = {"id": 42}
        with patch("app.models.verify_user", return_value=user) as verify_user:
            response = self.client.post(
                "/login",
                data={"username": "person", "password": "secure-password"},
            )

        self.assertEqual(response.status_code, 302)
        verify_user.assert_called_once_with("person", "secure-password")
        self.assertEqual(response.location, "/dashboard")

    def test_login_requires_username_even_if_email_is_supplied(self) -> None:
        with patch("app.models.verify_user") as verify_user:
            response = self.client.post(
                "/login",
                data={"email": "person@example.com", "password": "secure-password"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Username and password are required", response.data)
        verify_user.assert_not_called()

    def test_admin_login_route_logs_in_admin_user(self) -> None:
        admin_user = {"id": 99, "is_admin": 1}
        with patch("app.models.verify_user", return_value=admin_user) as verify_user:
            response = self.client.get("/admin-login")

        self.assertEqual(response.status_code, 302)
        verify_user.assert_called_once_with("admin", "Admin123!")
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_id"], 99)

    def test_account_page_displays_pick_results_and_statuses(self) -> None:
        user = {"id": 7, "username": "demo", "email": "demo@example.com", "plan": "free"}
        with patch("app.current_user", return_value=user), patch(
            "app.models.get_user_picks_for_user",
            return_value=[
                {"league": "NHL", "selection": "home", "status": "won", "scheduled_at": "2026-10-01T18:00:00+00:00"},
                {"league": "Premier League", "selection": "draw", "status": "lost", "scheduled_at": "2026-10-02T15:00:00+00:00"},
                {"league": "ATP", "selection": "Player A", "status": "pending", "scheduled_at": "2026-10-03T12:00:00+00:00"},
            ],
        ):
            response = self.client.get("/account")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Pick Results", response.data)
        self.assertIn(b"Won", response.data)
        self.assertIn(b"Lost", response.data)
        self.assertIn(b"Pending", response.data)

    def test_dashboard_shows_user_pick_history_and_result_counts(self) -> None:
        user = {"id": 7, "username": "demo"}
        picks = [
            {"home_team": "Home FC", "away_team": "Away FC", "market": "WLD", "selection": "home", "odds": 1.8, "scheduled_at": "2026-10-01", "status": "won"},
            {"home_team": "Team A", "away_team": "Team B", "market": "WLD", "selection": "draw", "odds": 3.2, "scheduled_at": "2026-10-02", "status": "lost"},
            {"home_team": "Player A", "away_team": "Player B", "market": "Who Wins Set", "selection": "Player A", "odds": 2.0, "scheduled_at": "2026-10-03", "status": "pending"},
        ]
        with patch("app.current_user", return_value=user), patch("app.build_current_user_picks") as build_picks, patch(
            "app.models.get_user_picks_for_user", return_value=picks
        ) as get_picks:
            with self.client.session_transaction() as session:
                session["user_id"] = user["id"]
            response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"demo's Dashboard", response.data)
        self.assertIn(b"Home FC vs Away FC", response.data)
        self.assertIn(b"Player A vs Player B", response.data)
        self.assertIn(b">Won</span>", response.data)
        self.assertIn(b">Lost</span>", response.data)
        self.assertIn(b">Pending</span>", response.data)
        self.assertIn(b"Dashboard", response.data)
        self.assertIn(b"Account", response.data)
        self.assertEqual(response.data.count(b"<strong>1</strong>"), 3)
        build_picks.assert_called_once_with(user)
        get_picks.assert_called_once_with(user["id"])

    def test_dashboard_requires_login(self) -> None:
        with patch("app.current_user", return_value=None):
            response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login?next=/dashboard")

    def test_dashboard_separates_future_pending_picks_from_history(self) -> None:
        future_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        picks = [
            {"home_team": "Upcoming Home", "away_team": "Upcoming Away", "market": "WLD", "selection": "home", "odds": 1.8, "scheduled_at": future_time, "status": "pending"},
            {"home_team": "Past Home", "away_team": "Past Away", "market": "WLD", "selection": "away", "odds": 2.1, "scheduled_at": past_time, "status": "pending"},
            {"home_team": "Settled Home", "away_team": "Settled Away", "market": "WLD", "selection": "home", "odds": 1.9, "scheduled_at": future_time, "status": "won"},
        ]
        with patch("app.current_user", return_value={"id": 7, "username": "demo"}), patch("app.build_current_user_picks"), patch(
            "app.models.get_user_picks_for_user", return_value=picks
        ):
            response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        upcoming_section = response.get_data(as_text=True).split("<h3>Pick History</h3>")[0]
        self.assertIn("Upcoming Home vs Upcoming Away", upcoming_section)
        self.assertNotIn("Past Home vs Past Away", upcoming_section)
        self.assertNotIn("Settled Home vs Settled Away", upcoming_section)
        self.assertIn("Past Home vs Past Away", response.get_data(as_text=True))
        self.assertIn("Settled Home vs Settled Away", response.get_data(as_text=True))

    def test_dashboard_generates_and_saves_upcoming_picks_on_first_visit(self) -> None:
        match_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        match = {
            "home_team": "Upcoming FC",
            "away_team": "Visitor FC",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 2.0, "draw": 3.5, "away": 4.0},
            "scheduled_at": match_time,
        }
        saved_pick = {
            **match,
            "selection": "home",
            "odds": 2.0,
            "status": "pending",
        }

        class TestDataService:
            def get_live_matches(self):
                return [match]

        class TestDailyPickService:
            def get_matches(self, _data_service):
                return [match]

        class TestAdminService:
            def get_plan(self, _plan_name):
                return {
                    "name": "Free",
                    "max_odds": 1,
                    "allowed_sports": ["soccer"],
                    "allowed_markets": ["WLD"],
                }

            def get_config(self):
                return {"allowed_markets": {"soccer": ["WLD"]}}

        class TestSubscriptionService:
            def is_active(self, _plan_name, _expires_at):
                return True

        user = {"id": 31, "username": "first-visit", "plan": "free"}
        with patch("app.current_user", return_value=user), patch(
            "app.models.persist_user_picks"
        ) as persist_picks, patch(
            "app.models.get_user_picks_for_user", return_value=[saved_pick]
        ), patch.dict(
            app.config,
            {
                "DATA_SERVICE": TestDataService(),
                "DAILY_PICK_SERVICE": TestDailyPickService(),
                "ADMIN_SERVICE": TestAdminService(),
                "SUBSCRIPTION_SERVICE": TestSubscriptionService(),
                "PREDICTION_ENGINE": LSTMPredictionEngine(history_provider=lambda: []),
            },
        ):
            response = self.client.get("/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Upcoming FC vs Visitor FC", response.data)
        self.assertIn("Dixon-Coles soccer fallback", persist_picks.call_args.args[1][0]["reason"])
        persist_picks.assert_called_once_with(user["id"], persist_picks.call_args.args[1])

    def test_results_page_calculates_win_rate_from_settled_picks(self) -> None:
        user = {"id": 7, "username": "demo"}
        picks = [
            {"home_team": "Home 1", "away_team": "Away 1", "status": "won"},
            {"home_team": "Home 2", "away_team": "Away 2", "status": "won"},
            {"home_team": "Home 3", "away_team": "Away 3", "status": "lost"},
            {"home_team": "Home 4", "away_team": "Away 4", "status": "pending"},
            {"home_team": "Home 5", "away_team": "Away 5", "status": "pending"},
        ]
        with patch("app.current_user", return_value=user), patch(
            "app.models.get_user_picks_for_user", return_value=picks
        ) as get_picks:
            response = self.client.get("/results")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"66.7%", response.data)
        self.assertIn(b"2 / 1", response.data)
        self.assertIn(b"Pick Results History", response.data)
        self.assertIn(b"pending", response.data)
        get_picks.assert_called_once_with(user["id"])

    def test_results_page_shows_no_rate_without_settled_picks(self) -> None:
        with patch("app.current_user", return_value={"id": 7, "username": "demo"}), patch(
            "app.models.get_user_picks_for_user", return_value=[{"status": "pending"}]
        ):
            response = self.client.get("/results")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"N/A", response.data)
        self.assertIn(b"Pending", response.data)

    def test_results_page_requires_login(self) -> None:
        with patch("app.current_user", return_value=None):
            response = self.client.get("/results")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login?next=/results")

    def test_predictions_page_persists_dixon_coles_fallback_picks(self) -> None:
        match = {
            "home_team": "Bears",
            "away_team": "Wolves",
            "league": "Premier League",
            "sport": "soccer",
            "market": "WLD",
            "odds": {"home": 2.1, "draw": 3.5, "away": 2.8},
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

        user = {"id": 9, "plan": "free"}
        with patch("app.current_user", return_value=user), patch.dict(
            app.config,
            {
                "DATA_SERVICE": TestDataService(),
                "DAILY_PICK_SERVICE": DailyPickService(),
                "ADMIN_SERVICE": TestAdminService(),
                "PREDICTION_ENGINE": LSTMPredictionEngine(history_provider=lambda: []),
            },
        ), patch("app.models.persist_user_picks") as persist_user_picks:
            response = self.client.get("/predictions")

        self.assertEqual(response.status_code, 200)
        persist_user_picks.assert_called_once()
        self.assertEqual(persist_user_picks.call_args.args[0], 9)
        self.assertIn("Dixon-Coles soccer fallback", persist_user_picks.call_args.args[1][0]["reason"])

    def test_admin_can_update_pick_result_status(self) -> None:
        user = {"id": 99, "is_admin": 1}
        with patch("app.current_user", return_value=user), patch("app.models.set_user_pick_status") as update_status:
            response = self.client.post(
                "/admin/picks",
                data={"pick_id": "12", "status": "won"},
            )

        self.assertEqual(response.status_code, 302)
        update_status.assert_called_once_with(12, "won")

    def test_admin_page_displays_previous_pick_results(self) -> None:
        user = {"id": 99, "is_admin": 1}
        pick = {
            "id": 12,
            "username": "reviewer",
            "league": "Premier League",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "selection": "home",
            "odds": 1.8,
            "scheduled_at": "2026-10-01T18:00:00+00:00",
            "status": "won",
        }
        with patch("app.current_user", return_value=user), patch(
            "app.models.get_all_user_picks", return_value=[pick]
        ):
            response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"All User Pick Results", response.data)
        self.assertIn(b"reviewer", response.data)
        self.assertIn(b"Scheduled: 2026-10-01T18:00:00+00:00", response.data)
        self.assertIn(b"Status: Won", response.data)


if __name__ == "__main__":
    unittest.main()
