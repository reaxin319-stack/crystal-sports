import os
import re
from datetime import datetime, timedelta
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
        for payload in self._fetch_api_payloads():
            matches = self._normalize_payload(payload)
            if matches:
                return matches

        try:
            scraped = self._scrape_matches()
            if scraped:
                return scraped
        except Exception:
            pass

        return self._fallback_matches()

    def _fetch_api_payloads(self) -> List[Dict[str, Any]]:
        payloads: List[Dict[str, Any]] = []
        for endpoint in self._get_api_endpoints():
            try:
                headers = self._build_headers()
                response = requests.get(endpoint, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    payloads.append(data)
            except Exception:
                continue
        return payloads

    def _get_api_endpoints(self) -> List[str]:
        configured = [item.strip() for item in os.getenv("SPORTS_API_URL", "").split(",") if item.strip()]
        defaults = [
            "https://www.thesportsdb.com/api/v1/json/1/search_all_leagues.php?c=England",
            "https://www.thesportsdb.com/api/v1/json/1/eventsnextleague.php?id=4328",
            "https://www.thesportsdb.com/api/v1/json/1/last5events.php?id=133602",
        ]
        return configured or defaults

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
        home = self._pick_first(item, ["home_team", "home", "homeTeam", "team_home", "team1", "homeName"])
        away = self._pick_first(item, ["away_team", "away", "awayTeam", "team_away", "team2", "awayName"])
        league = self._pick_first(item, ["league", "competition", "league_name", "competition_name", "tournament"])
        sport = self._guess_sport(league, home, away)
        market = self._guess_market(item)
        odds = self._extract_odds(item)

        if not home or not away or not odds:
            return None

        return {
            "home_team": home,
            "away_team": away,
            "league": league or "Live League",
            "sport": sport,
            "market": market,
            "odds": odds,
            "scheduled_at": self._build_future_schedule(),
        }

    def _guess_sport(self, league: str | None, home: str | None, away: str | None) -> str:
        text = " ".join([league or "", home or "", away or ""]).lower()
        if any(token in text for token in ["tennis", "atp", "wta", "grand slam"]):
            return "tennis"
        if any(token in text for token in ["hockey", "nhl", "ice"]):
            return "hockey"
        return "soccer"

    def _guess_market(self, item: Dict[str, Any]) -> str:
        if any(key in item for key in ["over_odds", "under_odds", "over", "under"]):
            return "Over/Under"
        if any(key in item for key in ["cards_over", "cards_under"]):
            return "Cards"
        if any(key in item for key in ["player_a", "player_b"]):
            return "Who Wins Set"
        return "WLD"

    def _extract_odds(self, item: Dict[str, Any]) -> Dict[str, Any]:
        odds = item.get("odds") if isinstance(item.get("odds"), dict) else {}
        if not odds:
            odds = item

        if self._guess_market(item) == "Over/Under":
            over = self._coerce_float(self._pick_first(item, ["over_odds", "over", "over_price", "overOdds"]))
            under = self._coerce_float(self._pick_first(item, ["under_odds", "under", "under_price", "underOdds"]))
            if over and under:
                return {"over": over, "under": under}

        if self._guess_market(item) == "Cards":
            cards_over = self._coerce_float(self._pick_first(item, ["cards_over", "cardsOver", "cards_over_odds"]))
            cards_under = self._coerce_float(self._pick_first(item, ["cards_under", "cardsUnder", "cards_under_odds"]))
            if cards_over and cards_under:
                return {"cards_over": cards_over, "cards_under": cards_under}

        if self._guess_market(item) == "Who Wins Set":
            player_a = self._coerce_float(self._pick_first(item, ["player_a", "playerA", "player_a_odds"]))
            player_b = self._coerce_float(self._pick_first(item, ["player_b", "playerB", "player_b_odds"]))
            if player_a and player_b:
                return {"player_a": player_a, "player_b": player_b}

        home = self._coerce_float(self._pick_first(odds, ["home", "home_odds", "home_price", "odds_home", "odd_home", "win_home"]))
        draw = self._coerce_float(self._pick_first(odds, ["draw", "draw_odds", "draw_price", "odds_draw", "odd_draw"]))
        away = self._coerce_float(self._pick_first(odds, ["away", "away_odds", "away_price", "odds_away", "odd_away", "win_away"]))
        if home and draw and away:
            return {"home": home, "draw": draw, "away": away}

        return {}

    def _pick_first(self, container: Dict[str, Any], keys: List[str]) -> Any:
        for key in keys:
            if key in container and container[key] not in [None, ""]:
                return container[key]
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
        future = datetime.utcnow() + timedelta(hours=4)
        return future.replace(microsecond=0).isoformat()

    def _scrape_matches(self) -> List[Dict[str, Any]]:
        url = os.getenv("SCRAPE_URL", "")
        if not url:
            return []

        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        rows = soup.select(os.getenv("SCRAPE_SELECTOR", "tr"))

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
        return [
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "league": "Premier League",
                "sport": "soccer",
                "market": "WLD",
                "odds": {"home": 1.95, "draw": 3.40, "away": 2.20},
                "scheduled_at": self._build_future_schedule(),
            },
            {
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
                "league": "NHL",
                "sport": "hockey",
                "market": "Over/Under",
                "odds": {"over": 1.85, "under": 1.95},
                "scheduled_at": self._build_future_schedule(),
            },
            {
                "home_team": "Novak Djokovic",
                "away_team": "Carlos Alcaraz",
                "league": "ATP",
                "sport": "tennis",
                "market": "Who Wins Set",
                "odds": {"player_a": 1.80, "player_b": 2.05},
                "scheduled_at": self._build_future_schedule(),
            },
        ]
