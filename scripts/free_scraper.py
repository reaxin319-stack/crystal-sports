#!/usr/bin/env python3
"""Fetch free sportsbook data for prediction generation.

This helper is intentionally lightweight: it accepts a list of public odds pages,
parses the first rows of team names and prices, and emits JSON in the schema the
app already expects from match payloads.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests
from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.data_service import DataService

DEFAULT_SCRAPERS = [
    {"sport": "soccer", "url": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard"},
    {"sport": "hockey", "url": "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"},
    {"sport": "tennis", "url": "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard"},
    {"sport": "basketball", "url": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"},
]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def parse_decimal(value: str) -> float | None:
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    if not numbers:
        return None
    try:
        return float(numbers[0])
    except ValueError:
        return None


def extract_odds_from_text(text: str) -> Dict[str, float]:
    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    if len(numbers) < 3:
        return {}
    odds = [float(number) for number in numbers[:3]]
    return {"home": odds[0], "draw": odds[1], "away": odds[2]}


def scrape_page(url: str, selector: str = "tr, .betting-table tbody tr", limit: int = 8) -> List[Dict[str, Any]]:
    response = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, (dict, list)):
        normalized = DataService()._normalize_payload(payload if isinstance(payload, dict) else {"events": payload})
        if normalized:
            return normalized[:limit]

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select(selector)

    matches: List[Dict[str, Any]] = []
    for row in rows[:limit]:
        cells = [clean_text(cell.get_text(" ", strip=True)) for cell in row.select("td, th")]
        if len(cells) < 2:
            continue

        home = cells[0]
        away = cells[1]
        odds_text = " ".join(cells[2:])
        if not home or not away:
            continue

        odds = extract_odds_from_text(odds_text)
        if not odds:
            continue

        matches.append(
            {
                "home_team": home,
                "away_team": away,
                "league": "Free Scraped Market",
                "sport": "soccer",
                "market": "WLD",
                "odds": odds,
            }
        )

    return matches


def iter_scrapers(custom_urls: Iterable[str] | None = None) -> List[Dict[str, str]]:
    if custom_urls:
        return [{"sport": "custom", "url": url} for url in custom_urls]

    return [{"sport": item["sport"], "url": item["url"]} for item in DEFAULT_SCRAPERS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape free public odds pages and emit prediction-ready JSON.")
    parser.add_argument("--url", nargs="*", help="Override the free odds URL(s) to scrape.")
    parser.add_argument("--selector", default="tr, .betting-table tbody tr", help="CSS selector for the rows to parse.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum rows to inspect on each page.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the JSON output.")
    args = parser.parse_args()

    sources = iter_scrapers(args.url)
    payload: List[Dict[str, Any]] = []
    for scraper in sources:
        try:
            matches = scrape_page(scraper["url"], selector=args.selector, limit=args.limit)
        except Exception:
            continue
        for match in matches:
            match["sport"] = scraper["sport"]
            payload.append(match)

    if not payload:
        print(json.dumps([], indent=2 if args.pretty else None))
        return

    print(json.dumps(payload, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
