import os
from random import randint
from typing import List, Dict, Any

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
        try:
            endpoint = os.getenv("SPORTS_API_URL")
            if endpoint:
                response = requests.get(endpoint, timeout=8)
                if response.ok:
                    payload = response.json()
                    return self._normalize_payload(payload)
        except Exception:
            pass

        try:
            return self._scrape_demo_matches()
        except Exception:
            return self._fallback_matches()

    def _normalize_payload(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        matches = []
        for item in payload.get("events", [])[:10]:
            home = item.get("home_team") or item.get("home") or "Home"
            away = item.get("away_team") or item.get("away") or "Away"
            league = item.get("league") or "Unknown"
            competition = item.get("competition") or league
            matches.append(
                {
                    "home_team": home,
                    "away_team": away,
                    "league": competition,
                    "market": "WLD",
                    "odds": {
                        "home": round(1.9 + randint(0, 20) / 20, 2),
                        "draw": round(3.3 + randint(0, 15) / 20, 2),
                        "away": round(2.0 + randint(0, 20) / 20, 2),
                    },
                }
            )
        return matches or self._fallback_matches()

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
            },
            {
                "home_team": "Toronto Maple Leafs",
                "away_team": "Boston Bruins",
                "league": "NHL",
                "sport": "hockey",
                "market": "Over/Under",
                "odds": {"over": 1.85, "under": 1.95},
            },
            {
                "home_team": "Novak Djokovic",
                "away_team": "Carlos Alcaraz",
                "league": "ATP",
                "sport": "tennis",
                "market": "Who Wins Set",
                "odds": {"player_a": 1.80, "player_b": 2.05},
            },
        ]
