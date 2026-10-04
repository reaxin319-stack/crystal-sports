import os
import re
from datetime import datetime, timedelta, timezone
from random import randint
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup

from config import LEAGUES, SPORTS


class DataService:
    def __init__(self) -> None:
        self.leagues = LEAGUES
        self.sports = SPORTS

    def get_configured_leagues(self) -> List[Dict[str, Any]]:
        return self.leagues

    def get_live_matches(self) -> List[Dict[str, Any]]:
        all_matches: List[Dict[str, Any]] = []
        for payload in self._fetch_api_payloads():
            matches = self._normalize_payload(payload)
            if matches:
                all_matches.extend(matches)

        now = datetime.now(timezone.utc)
        future_matches: List[Dict[str, Any]] = []
        for match in all_matches:
            if match.get("is_live") or self._is_upcoming_match(match.get("scheduled_at"), now):
                future_matches.append(match)

        if future_matches:
            return future_matches

        for scraper in self._get_free_odd_scrapers():
            try:
                scraped = self._scrape_matches_from_url(scraper)
                if scraped:
                    return scraped
            except Exception:
                continue

        try:
            scraped = self._scrape_matches()
            if scraped:
                return scraped
        except Exception:
            pass

        return self._fallback_matches()

    def _is_upcoming_match(self, scheduled_at: str | None, now: datetime | None = None) -> bool:
        if not scheduled_at:
            return False

        now = now or datetime.now(timezone.utc)
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            return False

        if scheduled_dt.tzinfo is None:
            scheduled_dt = scheduled_dt.replace(tzinfo=timezone.utc)

        return scheduled_dt >= now - timedelta(hours=3)

    def _fetch_api_payloads(self, target_date=None) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        target_date = target_date or (datetime.now(timezone.utc).date() + timedelta(days=1))
        for endpoint in self._get_api_endpoints():
            try:
                headers = self._build_headers()
                response = requests.get(endpoint, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    is_espn_scoreboard = endpoint.startswith("https://site.api.espn.com/") and "/scoreboard" in endpoint
                    if is_espn_scoreboard:
                        data = self._label_espn_payload(data, endpoint)
                    payloads.append(data)
                    if is_espn_scoreboard:
                        events = data.get("events", [])
                        has_target_date = any(
                            isinstance(event, dict)
                            and str(event.get("date", "")).startswith(target_date.isoformat())
                            for event in events[:10]
                        ) if isinstance(events, list) else False
                        if not has_target_date:
                            try:
                                dated_response = requests.get(
                                    endpoint,
                                    params={"dates": target_date.strftime("%Y%m%d")},
                                    headers=headers,
                                    timeout=10,
                                )
                                dated_response.raise_for_status()
                                dated_data = dated_response.json()
                                if isinstance(dated_data, dict):
                                    payloads.append(self._label_espn_payload(dated_data, endpoint))
                            except Exception:
                                pass
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            payloads.append(item)
            except Exception:
                continue
        return payloads

    def _label_espn_payload(self, payload: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
        league_code = endpoint.rstrip("/").split("/")[-2]
        league_names = {
            "eng.1": "Premier League",
            "esp.1": "La Liga",
            "ita.1": "Serie A",
            "usa.1": "MLS",
            "nba": "NBA",
            "nhl": "NHL",
            "atp": "ATP",
            "wta": "WTA",
            "nfl": "NFL",
            "mlb": "MLB",
        }
        source_league = league_names.get(league_code, league_code.upper())
        events = payload.get("events")
        if not isinstance(events, list):
            return payload

        labeled = dict(payload)
        labeled["events"] = [
            {**event, "_source_league": event.get("_source_league") or source_league}
            if isinstance(event, dict) else event
            for event in events
        ]
        return labeled

    def _get_api_endpoints(self) -> List[str]:
        configured = [item.strip() for item in os.getenv("SPORTS_API_URL", "").split(",") if item.strip()]
        defaults = [
            "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/soccer/esp.1/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/soccer/ita.1/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/tennis/wta/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard",
            "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard",
        ]
        return list(dict.fromkeys([*configured, *defaults]))

    def _get_free_odd_scrapers(self) -> List[Dict[str, str]]:
        configured = os.getenv("SCRAPE_URL", "")
        base_scrapers = [
            {"url": "https://www.oddschecker.com/football/england/premier-league", "selector": "tr, .betting-table tbody tr"},
            {"url": "https://www.oddschecker.com/hockey/nhl", "selector": "tr, .betting-table tbody tr"},
            {"url": "https://www.oddschecker.com/ice-hockey/nhl", "selector": "tr, .betting-table tbody tr"},
            {"url": "https://www.oddschecker.com/tennis", "selector": "tr, .betting-table tbody tr"},
            {"url": "https://www.oddschecker.com/basketball/nba", "selector": "tr, .betting-table tbody tr"},
        ]
        if configured:
            return [{"url": configured, "selector": os.getenv("SCRAPE_SELECTOR", "tr")}] + base_scrapers
        return base_scrapers

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"User-Agent": "Mozilla/5.0"}
        token = os.getenv("SPORTS_API_TOKEN") or os.getenv("SPORTS_API_KEY")
        if token:
            headers["Authorization"] = f"Bearer {token}"
            headers["X-Api-Key"] = token
        return headers

    def _normalize_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Any] = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            for key in ["events", "matches", "data", "fixtures", "results", "games"]:
                value = payload.get(key)
                if isinstance(value, list):
                    candidates = value
                    break
            if not candidates:
                for value in payload.values():
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        candidates = value
                        break

        matches: List[Dict[str, Any]] = []
        for item in candidates[:10]:
            if not isinstance(item, dict):
                continue
            match = self._build_match_from_payload(item)
            if match:
                matches.append(match)

        return matches

    def _build_match_from_payload(self, item: Dict[str, Any]) -> Dict[str, Any] | None:
        home = self._pick_first(item, ["home_team", "home", "homeTeam", "team_home", "team1", "homeName", "strHomeTeam", "side1", "home"])
        away = self._pick_first(item, ["away_team", "away", "awayTeam", "team_away", "team2", "awayName", "strAwayTeam", "side2", "away"])
        league = self._pick_first(item, ["league", "competition", "league_name", "competition_name", "tournament", "strLeague", "strCompetition", "strTournament", "competition"])
        sport_hint = self._pick_first(item, ["sport", "strSport", "sport_name", "game_sport", "competition_type"])

        if not home or not away:
            espn_home, espn_away, espn_league = self._extract_espn_teams(item)
            home = home or espn_home
            away = away or espn_away
            league = league or espn_league

        if not league or str(league).strip().casefold() in {"live league", "unknown"}:
            league = self._pick_first(item, ["_source_league"]) or league

        sport = self._guess_sport(league, home, away, sport_hint)
        market = self._guess_market(item)
        odds = self._extract_odds(item)

        if isinstance(home, dict):
            home = self._pick_first(home, ["name", "home_team", "team_name", "title"])
        if isinstance(away, dict):
            away = self._pick_first(away, ["name", "away_team", "team_name", "title"])
        if isinstance(league, dict):
            league = self._pick_first(league, ["name", "league", "competition", "title"])
        if not league or str(league).strip().casefold() in {"live league", "unknown"}:
            league = self._pick_first(item, ["_source_league"]) or league

        if not home or not away:
            return None

        if not odds:
            odds = self._build_fallback_odds(home, away, item)

        if not odds:
            return None

        home_score, away_score = self._extract_scores(item)
        status, status_detail, is_live = self._extract_status(item)

        return {
            "home_team": home,
            "away_team": away,
            "league": league or "Live League",
            "sport": sport,
            "market": market,
            "odds": odds,
            "scheduled_at": self._extract_scheduled_at(item) or self._build_future_schedule(),
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "status_detail": status_detail,
            "is_live": is_live,
        }

    def _extract_scores(self, item: Dict[str, Any]) -> tuple[Any, Any]:
        home_score = self._pick_first(item, ["home_score", "homeScore"])
        away_score = self._pick_first(item, ["away_score", "awayScore"])
        competitions = item.get("competitions")
        if home_score is not None and away_score is not None:
            return home_score, away_score
        if not isinstance(competitions, list):
            return home_score, away_score

        for competition in competitions:
            if not isinstance(competition, dict):
                continue
            competitors = competition.get("competitors")
            if not isinstance(competitors, list):
                continue
            for competitor in competitors:
                if not isinstance(competitor, dict):
                    continue
                score = competitor.get("score")
                if competitor.get("homeAway") == "home":
                    home_score = home_score if home_score is not None else score
                elif competitor.get("homeAway") == "away":
                    away_score = away_score if away_score is not None else score
            if home_score is not None or away_score is not None:
                return home_score, away_score
        return home_score, away_score

    def _extract_status(self, item: Dict[str, Any]) -> tuple[str, str, bool]:
        raw_status = item.get("status") or item.get("state") or item.get("strStatus")
        status_type = raw_status.get("type") if isinstance(raw_status, dict) else None
        if not isinstance(status_type, dict):
            status_type = {}

        status_name = (
            status_type.get("name")
            or status_type.get("description")
            or (raw_status.get("name") if isinstance(raw_status, dict) else raw_status)
            or "Scheduled"
        )
        status_state = status_type.get("state") or (raw_status.get("state") if isinstance(raw_status, dict) else "")
        status_detail = (
            (raw_status.get("displayClock") or raw_status.get("shortDetail") or raw_status.get("detail"))
            if isinstance(raw_status, dict)
            else ""
        ) or status_type.get("shortDetail") or ""
        status_text = str(status_name)
        is_live = str(status_state).casefold() in {"in", "live", "in_progress"} or any(
            marker in status_text.casefold() for marker in ("in progress", "in_progress", "live")
        )
        return status_text, str(status_detail), is_live

    def _guess_sport(self, league: str | None, home: str | None, away: str | None, sport_hint: Any = None) -> str:
        normalized = [str(value or "") for value in [league, home, away, sport_hint]]
        text = " ".join(normalized).lower()
        if any(token in text for token in ["tennis", "atp", "wta", "grand slam"]):
            return "tennis"
        if any(token in text for token in ["hockey", "nhl", "ice"]):
            return "hockey"
        if any(token in text for token in ["basketball", "nba"]):
            return "basketball"
        if any(token in text for token in ["baseball", "mlb"]):
            return "baseball"
        if any(token in text for token in ["american football", "nfl"]):
            return "football"
        return "soccer"

    def _guess_market(self, item: Dict[str, Any]) -> str:
        if not isinstance(item, dict):
            return "WLD"

        candidate_keys = []
        for container in [item, item.get("odds")]:
            if isinstance(container, dict):
                candidate_keys.extend(str(key).lower() for key in container.keys())

        normalized_keys = [re.sub(r"[^a-z0-9]", "", key) for key in candidate_keys]
        if any(
            key.startswith(("over", "under", "totalover", "totalunder", "goalsover", "goalsunder"))
            and ("15" in key or "25" in key)
            for key in normalized_keys
        ):
            return "Over/Under"

        if any(key in candidate_keys for key in [
            "home", "draw", "away",
            "home_odds", "draw_odds", "away_odds",
            "odds_home", "odds_draw", "odds_away",
            "stroddshome", "stroddsdraw", "stroddsaway",
            "homeodd", "drawodd", "awayodd",
            "moneyline",
        ]):
            return "WLD"

        if any(key in candidate_keys for key in [
            "over", "under", "over_odds", "under_odds",
            "overprice", "underprice",
            "stroddsover", "stroddsunder",
        ]):
            return "Over/Under"

        if any(key in candidate_keys for key in [
            "cards_over", "cards_under", "cardsover", "cardsunder",
        ]):
            return "Cards"

        if any(key in candidate_keys for key in [
            "player_a", "player_b", "playera", "playerb",
            "player_a_odds", "player_b_odds",
        ]):
            return "Who Wins Set"

        return "WLD"

    def _extract_espn_teams(self, item: Dict[str, Any]) -> tuple[str | None, str | None, str | None]:
        competitions = item.get("competitions") if isinstance(item, dict) else None
        if not isinstance(competitions, list):
            return None, None, None

        for competition in competitions:
            if not isinstance(competition, dict):
                continue
            competitors = competition.get("competitors")
            if not isinstance(competitors, list):
                continue

            home_team = None
            away_team = None
            for competitor in competitors:
                if not isinstance(competitor, dict):
                    continue
                team = competitor.get("team") if isinstance(competitor.get("team"), dict) else {}
                name = team.get("displayName") or team.get("name") or team.get("shortDisplayName")
                home_away = competitor.get("homeAway")
                if home_away == "home":
                    home_team = name
                elif home_away == "away":
                    away_team = name

            if home_team and away_team:
                league_name = None
                league = competition.get("league")
                if isinstance(league, dict):
                    league_name = league.get("name") or league.get("abbreviation")
                return home_team, away_team, league_name

        return None, None, None

    def _american_to_decimal(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, dict):
            for key in ["close", "open"]:
                if key in value and isinstance(value[key], dict):
                    return self._american_to_decimal(value[key].get("odds"))
            return self._american_to_decimal(value.get("odds"))
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            if cleaned.startswith("+") or cleaned.startswith("-"):
                try:
                    numeric = float(cleaned)
                except ValueError:
                    return None
                if numeric > 0:
                    return 1 + (numeric / 100)
                return 1 + (100 / abs(numeric))
            try:
                decimal = float(cleaned)
                return decimal if decimal > 1 else None
            except ValueError:
                return None
        return None

    def _extract_espn_odds(self, item: Dict[str, Any]) -> Dict[str, Any]:
        competitions = item.get("competitions") if isinstance(item, dict) else None
        if not isinstance(competitions, list):
            return {}

        for competition in competitions:
            if not isinstance(competition, dict):
                continue
            odd_entries = competition.get("odds")
            if not isinstance(odd_entries, list):
                continue

            for odd_entry in odd_entries:
                if not isinstance(odd_entry, dict):
                    continue
                moneyline = odd_entry.get("moneyline")
                if not isinstance(moneyline, dict):
                    continue

                home = self._american_to_decimal(moneyline.get("home"))
                draw = self._american_to_decimal(moneyline.get("draw"))
                away = self._american_to_decimal(moneyline.get("away"))

                if home is not None and draw is not None and away is not None:
                    return {"home": home, "draw": draw, "away": away}

        return {}

    def _extract_odds(self, item: Dict[str, Any]) -> Dict[str, Any]:
        odds = item.get("odds") if isinstance(item.get("odds"), dict) else {}
        if not odds:
            odds = item

        if self._guess_market(item) == "Over/Under":
            total_odds = {}
            line_aliases = {
                "over_1_5": ["over_1_5", "over_1.5", "over15", "over_15", "over_1_5_odds", "over15_odds", "over15Odds", "goals_over_1_5", "total_over_1_5"],
                "under_1_5": ["under_1_5", "under_1.5", "under15", "under_15", "under_1_5_odds", "under15_odds", "under15Odds", "goals_under_1_5", "total_under_1_5"],
                "over_2_5": ["over_2_5", "over_2.5", "over25", "over_25", "over_2_5_odds", "over25_odds", "over25Odds", "goals_over_2_5", "total_over_2_5"],
                "under_2_5": ["under_2_5", "under_2.5", "under25", "under_25", "under_2_5_odds", "under25_odds", "under25Odds", "goals_under_2_5", "total_under_2_5"],
            }
            for normalized_key, aliases in line_aliases.items():
                price = self._coerce_float(self._pick_first(odds, aliases))
                if price:
                    total_odds[normalized_key] = price

            over = self._coerce_float(self._pick_first(odds, ["over_odds", "over", "over_price", "overOdds", "strOddsOver"]))
            under = self._coerce_float(self._pick_first(odds, ["under_odds", "under", "under_price", "underOdds", "strOddsUnder"]))
            if total_odds:
                if over and under:
                    total_odds.update({"over": over, "under": under})
                return total_odds
            if over and under:
                return {"over": over, "under": under}

        espn_odds = self._extract_espn_odds(item)
        if espn_odds:
            return espn_odds

        if self._guess_market(item) == "Cards":
            cards_over = self._coerce_float(self._pick_first(item, ["cards_over", "cardsOver", "cards_over_odds", "strOddsOver", "overOdds"]))
            cards_under = self._coerce_float(self._pick_first(item, ["cards_under", "cardsUnder", "cards_under_odds", "strOddsUnder", "underOdds"]))
            if cards_over and cards_under:
                return {"cards_over": cards_over, "cards_under": cards_under}

        if self._guess_market(item) == "Who Wins Set":
            player_a = self._coerce_float(self._pick_first(item, ["player_a", "playerA", "player_a_odds", "strOddsHome", "homeOdds"]))
            player_b = self._coerce_float(self._pick_first(item, ["player_b", "playerB", "player_b_odds", "strOddsAway", "awayOdds"]))
            if player_a and player_b:
                return {"player_a": player_a, "player_b": player_b}

        home = self._coerce_float(self._pick_first(odds, ["home", "home_odds", "home_price", "odds_home", "odd_home", "win_home", "strOddsHome", "homeOdds", "homeOdd"]))
        draw = self._coerce_float(self._pick_first(odds, ["draw", "draw_odds", "draw_price", "odds_draw", "odd_draw", "strOddsDraw", "drawOdds", "drawOdd"]))
        away = self._coerce_float(self._pick_first(odds, ["away", "away_odds", "away_price", "odds_away", "odd_away", "win_away", "strOddsAway", "awayOdds", "awayOdd"]))
        if home and draw and away:
            return {"home": home, "draw": draw, "away": away}

        return {}

    def _pick_first(self, container: Dict[str, Any] | None, keys: List[str]) -> Any:
        if not isinstance(container, dict):
            return None
        for key in keys:
            value = container.get(key)
            if isinstance(value, dict):
                return value
            if value not in [None, ""]:
                return value
        return None

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[^0-9.\-]", "", value)
            if cleaned:
                try:
                    return float(cleaned)
                except ValueError:
                    return None
        return None

    def _build_future_schedule(self) -> str:
        future = datetime.now(timezone.utc) + timedelta(hours=4)
        return future.replace(microsecond=0).isoformat()

    def _build_fallback_odds(self, home: str | None, away: str | None, item: Dict[str, Any]) -> Dict[str, Any]:
        home_name = str(home or "").strip()
        away_name = str(away or "").strip()
        if not home_name or not away_name:
            return {}

        if any(token in str(item).lower() for token in ["tennis", "atp", "wta", "grand slam"]):
            return {"player_a": 1.80, "player_b": 2.05}

        if any(token in str(item).lower() for token in ["hockey", "nhl", "ice"]):
            return {"home": 2.05, "draw": 3.70, "away": 1.95}

        return {"home": 1.95, "draw": 3.40, "away": 2.20}

    def _extract_scheduled_at(self, item: Dict[str, Any]) -> str | None:
        for key in ["scheduled_at", "datetime", "date_time", "dateTime", "kickoff", "starts_at"]:
            value = self._pick_first(item, [key])
            if value:
                if isinstance(value, str):
                    try:
                        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            parsed = parsed.replace(tzinfo=timezone.utc)
                        return parsed.replace(microsecond=0).isoformat()
                    except ValueError:
                        pass
                if isinstance(value, (int, float)):
                    try:
                        parsed = datetime.fromtimestamp(int(value))
                        return parsed.replace(microsecond=0).isoformat()
                    except (OverflowError, ValueError):
                        pass

        date_value = self._pick_first(item, ["dateEvent", "date", "event_date", "date_time"])
        time_value = self._pick_first(item, ["strTime", "time", "event_time", "match_time"])
        if date_value:
            try:
                if isinstance(date_value, str) and time_value and isinstance(time_value, str):
                    combined = f"{date_value} {time_value}"
                    parsed = datetime.fromisoformat(combined)
                    return parsed.replace(microsecond=0).isoformat()
                parsed = datetime.fromisoformat(str(date_value))
                return parsed.replace(microsecond=0).isoformat()
            except ValueError:
                pass
        return None

    def _scrape_matches_from_url(self, scraper: Dict[str, str]) -> List[Dict[str, Any]]:
        url = scraper.get("url", "")
        selector = scraper.get("selector", "tr")
        if not url:
            return []

        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select(selector)

        scraped: List[Dict[str, Any]] = []
        for row in rows[:8]:
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td, th")]
            if len(cells) < 2:
                continue
            home = cells[0]
            away = cells[1]
            odds_text = " ".join(cells[2:])
            if not home or not away:
                continue
            odds = self._parse_scraped_odds(odds_text)
            if odds:
                scraped.append(
                    {
                        "home_team": home,
                        "away_team": away,
                        "league": "Scraped Live Market",
                        "sport": self._guess_sport(None, home, away),
                        "market": "WLD" if "home" in odds and "away" in odds else "Over/Under",
                        "odds": odds,
                        "scheduled_at": self._build_future_schedule(),
                    }
                )

        return scraped

    def _scrape_matches(self) -> List[Dict[str, Any]]:
        configured = os.getenv("SCRAPE_URL", "")
        if not configured:
            return []
        return self._scrape_matches_from_url({"url": configured, "selector": os.getenv("SCRAPE_SELECTOR", "tr")})

    def _parse_scraped_odds(self, text: str) -> Dict[str, Any]:
        if not text:
            return {}
        numbers = re.findall(r"(\d+(?:\.\d+)?)", text)
        if len(numbers) >= 3:
            return {"home": float(numbers[0]), "draw": float(numbers[1]), "away": float(numbers[2])}
        return {}

    def _scrape_demo_matches(self) -> List[Dict[str, Any]]:
        sample = []
        soccer_matches = [
            {"home_team": "Arsenal", "away_team": "Chelsea", "league": "Premier League", "sport": "soccer", "market": "WLD", "odds": {"home": 1.95, "draw": 3.40, "away": 2.20}},
            {"home_team": "Lorient", "away_team": "Le Havre", "league": "Ligue 2", "sport": "soccer", "market": "Cards", "odds": {"cards_over": 1.88, "cards_under": 1.92}},
            {"home_team": "PSG", "away_team": "Marseille", "league": "Ligue 1", "sport": "soccer", "market": "Over/Under", "odds": {"over": 1.90, "under": 1.90}},
        ]
        hockey_matches = [
            {"home_team": "Toronto Maple Leafs", "away_team": "Boston Bruins", "league": "NHL", "sport": "hockey", "market": "WLD", "odds": {"home": 2.05, "draw": 3.75, "away": 1.95}},
            {"home_team": "Colorado Avalanche", "away_team": "Edmonton Oilers", "league": "NHL", "sport": "hockey", "market": "Over/Under", "odds": {"over": 1.85, "under": 1.95}},
        ]
        tennis_matches = [
            {"home_team": "Novak Djokovic", "away_team": "Carlos Alcaraz", "league": "ATP", "sport": "tennis", "market": "WLD", "odds": {"home": 1.70, "draw": 2.10, "away": 2.40}},
            {"home_team": "Aryna Sabalenka", "away_team": "Iga Swiatek", "league": "WTA", "sport": "tennis", "market": "Who Wins Set", "odds": {"player_a": 1.80, "player_b": 2.05}},
        ]
        sample.extend(soccer_matches)
        sample.extend(hockey_matches)
        sample.extend(tennis_matches)
        return sample

    def _fallback_matches(self) -> List[Dict[str, Any]]:
        return []
