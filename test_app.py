import unittest
from unittest.mock import patch

from app import app


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()

    def test_predictions_page_loads(self) -> None:
        response = self.client.get("/predictions")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Predictions", response.data)

    def test_pricing_plan_buttons_lead_to_registration(self) -> None:
        response = self.client.get("/pricing")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'method="get" action="/register"', response.data)
        self.assertIn(b'name="plan" value="vip"', response.data)

    def test_registration_preserves_selected_plan(self) -> None:
        response = self.client.get("/register?plan=elite")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<option value="elite" selected>Elite</option>', response.data)

    def test_admin_button_is_only_on_registration_page(self) -> None:
        home_response = self.client.get("/")
        registration_response = self.client.get("/register")
        self.assertNotIn(b'href="/admin"', home_response.data)
        self.assertIn(b'href="/admin"', registration_response.data)

    @patch("app.current_user", return_value=None)
    def test_admin_redirects_unauthenticated_users_to_login(self, _current_user) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login?next=/admin")

    @patch("app.current_user", return_value={"is_admin": 0})
    def test_admin_redirects_non_admin_users_home(self, _current_user) -> None:
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/")

    @patch("app.current_user", return_value=None)
    def test_daily_pick_generation_requires_admin(self, _current_user) -> None:
        response = self.client.post("/admin/generate-picks")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "/login?next=/admin")


if __name__ == "__main__":
    unittest.main()
