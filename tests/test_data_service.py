import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import resolve_display_date
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
            self.assertGreater(parsed, datetime.now(timezone.utc) + timedelta(hours=3))

    def test_default_live_sources_cover_multiple_free_feeds(self) -> None:
        service = DataService()
        endpoints = service._get_api_endpoints()

        self.assertGreaterEqual(len(endpoints), 6)
        self.assertTrue(any("soccer" in endpoint for endpoint in endpoints))
        self.assertTrue(any("basketball" in endpoint or "nba" in endpoint for endpoint in endpoints))
        self.assertTrue(any("hockey" in endpoint or "nhl" in endpoint for endpoint in endpoints))
        self.assertTrue(any("tennis" in endpoint or "atp" in endpoint for endpoint in endpoints))

    def test_configured_feed_keeps_default_live_sources_as_fallbacks(self) -> None:
        configured_url = "https://www.scorebat.com/video-api/v1/"
        with patch.dict("os.environ", {"SPORTS_API_URL": configured_url}):
            endpoints = DataService()._get_api_endpoints()

        self.assertEqual(endpoints[0], configured_url)
        self.assertTrue(any("site.api.espn.com" in endpoint for endpoint in endpoints))

    def test_free_scrapers_include_hockey_feed(self) -> None:
        scrapers = DataService()._get_free_odd_scrapers()

        self.assertTrue(any("hockey" in scraper["url"] or "nhl" in scraper["url"] for scraper in scrapers))

    def test_tomorrow_matches_appear_after_9pm_cutoff(self) -> None:
        now = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
        scheduled = datetime(2026, 9, 30, 23, 30, tzinfo=timezone.utc)

        self.assertEqual(resolve_display_date(scheduled, now), datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc).date())

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
