import unittest
from datetime import datetime, timezone

from services.daily_picks import DailyPickService, next_daily_pick_run


class FakeDataService:
    def __init__(self) -> None:
        self.calls = 0

    def get_live_matches(self) -> list[dict[str, str]]:
        self.calls += 1
        return [{"home_team": "Home", "away_team": "Away"}]


class DailyPickServiceTests(unittest.TestCase):
    def test_daily_generation_is_scheduled_for_four_utc(self) -> None:
        now = datetime(2026, 10, 4, 3, 30, tzinfo=timezone.utc)

        next_run = next_daily_pick_run(now)

        self.assertEqual(next_run, datetime(2026, 10, 4, 4, 0, tzinfo=timezone.utc))

    def test_scheduler_catches_up_before_six_and_defers_after_six(self) -> None:
        before_six = datetime(2026, 10, 4, 5, 30, tzinfo=timezone.utc)
        after_six = datetime(2026, 10, 4, 6, 1, tzinfo=timezone.utc)

        self.assertEqual(next_daily_pick_run(before_six), before_six)
        self.assertEqual(
            next_daily_pick_run(after_six),
            datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc),
        )

    def test_scheduler_runs_once_per_date(self) -> None:
        current_time = datetime(2026, 10, 4, 5, 30, tzinfo=timezone.utc)

        next_run = next_daily_pick_run(current_time, last_run_date=current_time.date())

        self.assertEqual(next_run, datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc))

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