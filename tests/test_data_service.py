import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock, patch

from app import build_display_picks, resolve_display_date
from services.prediction_engine import PredictionEngine
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

    def test_espn_requests_target_date_when_default_feed_omits_it(self) -> None:
        endpoint = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
        default_response = Mock()
        default_response.json.return_value = {"events": [{"date": "2026-10-10T18:00Z"}]}
        dated_response = Mock()
        dated_response.json.return_value = {"events": [{"date": "2026-10-01T23:00Z"}]}

        with patch.object(DataService, "_get_api_endpoints", return_value=[endpoint]), patch(
            "services.data_service.requests.get",
            side_effect=[default_response, dated_response],
        ) as get:
            payloads = DataService()._fetch_api_payloads(date(2026, 10, 1))

        self.assertEqual(len(payloads), 2)
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"dates": "20261001"})
        self.assertEqual(payloads[1]["events"][0]["_source_league"], "NHL")

    def test_espn_source_league_sets_sport_during_normalization(self) -> None:
        service = DataService()
        payload = service._label_espn_payload(
            {
                "events": [
                    {
                        "date": "2026-10-01T23:00:00Z",
                        "competitions": [
                            {
                                "competitors": [
                                    {"homeAway": "home", "team": {"displayName": "Buffalo Sabres"}},
                                    {"homeAway": "away", "team": {"displayName": "Columbus Blue Jackets"}},
                                ]
                            }
                        ],
                    }
                ]
            },
            "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
        )

        match = service._normalize_payload(payload)[0]

        self.assertEqual(match["league"], "NHL")
        self.assertEqual(match["sport"], "hockey")

    def test_free_scrapers_include_hockey_feed(self) -> None:
        scrapers = DataService()._get_free_odd_scrapers()

        self.assertTrue(any("hockey" in scraper["url"] or "nhl" in scraper["url"] for scraper in scrapers))

    def test_tomorrow_matches_appear_after_9pm_cutoff(self) -> None:
        now = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
        scheduled = datetime(2026, 9, 30, 23, 30, tzinfo=timezone.utc)

        self.assertEqual(resolve_display_date(scheduled, now), datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc).date())

    def test_free_pick_limit_is_applied_per_display_date(self) -> None:
        now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        matches = [
            {
                "home_team": "Later Home",
                "away_team": "Later Away",
                "sport": "soccer",
                "market": "WLD",
                "odds": {"home": 2.0, "draw": 3.0, "away": 2.5},
                "scheduled_at": "2026-10-02T18:00:00+00:00",
            }
        ]
        for index in range(3):
            matches.append({
                "home_team": f"Tomorrow Home {index}",
                "away_team": f"Tomorrow Away {index}",
                "sport": "soccer",
                "market": "WLD",
                "odds": {"home": 2.0, "draw": 3.0, "away": 2.5},
                "scheduled_at": "2026-10-01T18:00:00+00:00",
            })

        picks = build_display_picks(
            matches,
            PredictionEngine(),
            {"max_odds": 3, "allowed_sports": ["soccer"], "allowed_markets": ["WLD"]},
            {"allowed_markets": {"soccer": ["WLD"]}},
            now,
        )

        self.assertEqual(sum(pick["scheduled_at"].startswith("2026-10-01") for pick in picks), 3)

    def test_free_picks_include_multiple_fixture_leagues(self) -> None:
        now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        matches = []
        for index in range(3):
            matches.append({
                "home_team": f"Soccer Home {index}",
                "away_team": f"Soccer Away {index}",
                "league": "League A",
                "sport": "soccer",
                "market": "WLD",
                "odds": {"home": 2.0, "draw": 3.0, "away": 2.5},
                "scheduled_at": "2026-10-01T18:00:00+00:00",
            })
        for index in range(2):
            matches.append({
                "home_team": f"Hockey Home {index}",
                "away_team": f"Hockey Away {index}",
                "league": "League B",
                "sport": "hockey",
                "market": "WLD",
                "odds": {"home": 2.0, "draw": 3.0, "away": 2.5},
                "scheduled_at": "2026-10-01T19:00:00+00:00",
            })

        picks = build_display_picks(
            matches,
            PredictionEngine(),
            {"max_odds": 3, "allowed_sports": ["soccer", "hockey"], "allowed_markets": ["WLD"]},
            {"allowed_markets": {"soccer": ["WLD"], "hockey": ["WLD"]}},
            now,
        )

        self.assertEqual({pick["league"] for pick in picks}, {"League A", "League B"})

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
