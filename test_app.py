import unittest

from app import app


class AppRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = app.test_client()

    def test_predictions_page_loads(self) -> None:
        response = self.client.get("/predictions")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Predictions", response.data)


if __name__ == "__main__":
    unittest.main()
