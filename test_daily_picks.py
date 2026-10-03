import unittest
from datetime import datetime, timezone

from services.daily_picks import DailyPickService


class FakeDataService:
    def __init__(self) -> None:
        self.calls = 0

    def get_live_matches(self) -> list[dict[str, str]]:
        self.calls += 1
        return [{"home_team": "Home", "away_team": "Away"}]


class DailyPickServiceTests(unittest.TestCase):
    def test_generates_once_per_day_and_returns_copies(self) -> None:
        data_service = FakeDataService()
        service = DailyPickService()

        first = service.get_matches(data_service)
        first[0]["home_team"] = "Changed"
        second = service.get_matches(data_service)

        self.assertEqual(data_service.calls, 1)
        self.assertEqual(second[0]["home_team"], "Home")
        self.assertEqual(service.status()["date"], datetime.now(timezone.utc).date().isoformat())


if __name__ == "__main__":
    unittest.main()