import unittest
from datetime import datetime, timedelta

from services.data_service import DataService


class DataServiceScheduleTests(unittest.TestCase):
    def test_matches_include_future_schedule_at_least_three_hours_ahead(self) -> None:
        service = DataService()
        matches = service.get_live_matches()
        self.assertTrue(matches)
        for match in matches:
            scheduled_at = match.get("scheduled_at")
            self.assertIsNotNone(scheduled_at)
            parsed = datetime.fromisoformat(scheduled_at)
            self.assertGreater(parsed, datetime.utcnow() + timedelta(hours=3))

    def test_thesportsdb_style_payloads_are_normalized(self) -> None:
        service = DataService()
        payload = {
            "events": [
                {
                    "idEvent": "1",
                    "strHomeTeam": "Arsenal",
                    "strAwayTeam": "Chelsea",
                    "strLeague": "English Premier League",
                    "strSport": "Soccer",
                    "dateEvent": "2026-08-04",
                    "strTime": "19:30:00",
                    "strOddsHome": "2.10",
                    "strOddsDraw": "3.30",
                    "strOddsAway": "3.60",
                }
            ]
        }

        matches = service._normalize_payload(payload)

        self.assertTrue(matches)
        match = matches[0]
        self.assertEqual(match["home_team"], "Arsenal")
        self.assertEqual(match["away_team"], "Chelsea")
        self.assertEqual(match["league"], "English Premier League")
        self.assertEqual(match["sport"], "soccer")
        self.assertEqual(match["market"], "WLD")
        self.assertEqual(match["odds"]["home"], 2.10)
        self.assertEqual(match["odds"]["draw"], 3.30)
        self.assertEqual(match["odds"]["away"], 3.60)


if __name__ == "__main__":
    unittest.main()
