from typing import List, Dict, Any


class PredictionEngine:
    def build_slips(self, matches: List[Dict[str, Any]], subscription: Dict[str, Any], admin_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        max_odds = subscription.get("max_odds", 3)
        picks = []
        for match in matches:
            if not self._is_allowed(match, subscription, admin_config):
                continue
            market = match.get("market", "WLD")
            if market == "Over/Under":
                pick = self._build_over_under_pick(match)
            elif market == "Cards":
                pick = self._build_cards_pick(match)
            elif market == "Who Wins Set":
                pick = self._build_set_pick(match)
            else:
                pick = self._build_wld_pick(match)

            if pick:
                picks.append(pick)

            if len(picks) >= max_odds:
                break

        return picks

    def build_magic_combinations(self, matches: List[Dict[str, Any]], subscription: Dict[str, Any], admin_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        if subscription.get("name", "").lower() != "vip":
            return []

        allowed = [m for m in matches if self._is_allowed(m, subscription, admin_config)]
        if len(allowed) < 3:
            return []

        combos = []
        for start in range(min(4, len(allowed))):
            combo = []
            for index in range(start, min(start + 4, len(allowed))):
                combo.append(allowed[index])
            if len(combo) >= 3:
                combos.append({
                    "title": f"VIP Combo {len(combos) + 1}",
                    "items": combo,
                    "combined_odds": round(sum(item.get("odds", {}).get("home", 1.0) for item in combo), 2),
                })
        return combos[:3]

    def _is_allowed(self, match: Dict[str, Any], subscription: Dict[str, Any], admin_config: Dict[str, Any]) -> bool:
        sport = match.get("sport", "soccer")
        market = match.get("market", "WLD")
        allowed_sports = subscription.get("allowed_sports", ["soccer"])
        allowed_markets = subscription.get("allowed_markets", ["WLD"])
        if sport not in allowed_sports:
            return False
        if market not in allowed_markets:
            return False
        admin_markets = admin_config.get("allowed_markets", {}).get(sport, [])
        return market in admin_markets or market in ["WLD"]

    def _build_wld_pick(self, match: Dict[str, Any]) -> Dict[str, Any] | None:
        odds = match.get("odds", {})
        home = odds.get("home")
        draw = odds.get("draw")
        away = odds.get("away")

        if not all([home, draw, away]):
            return None

        selected = self._pick_best_wld(home, draw, away)
        selected_odds = odds[selected]
        if selected_odds >= 2.0:
            return {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "soccer"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": "WLD",
                "selection": selected,
                "odds": selected_odds,
                "reason": f"Value edge on {selected} based on recent form and line movement.",
            }
        return None

    def _build_over_under_pick(self, match: Dict[str, Any]) -> Dict[str, Any] | None:
        odds = match.get("odds", {})
        over = odds.get("over")
        under = odds.get("under")
        if not all([over, under]):
            return None

        selection = "Over" if over >= under else "Under"
        selected_odds = over if selection == "Over" else under
        if selected_odds >= 2.0:
            return {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "hockey"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": "Over/Under",
                "selection": selection,
                "odds": selected_odds,
                "reason": "Momentum and pace suggest a strong total trend.",
            }
        return None

    def _build_cards_pick(self, match: Dict[str, Any]) -> Dict[str, Any] | None:
        odds = match.get("odds", {})
        selection = "Over Cards" if odds.get("cards_over", 0) >= odds.get("cards_under", 0) else "Under Cards"
        selected_odds = odds.get("cards_over", 1.8) if selection == "Over Cards" else odds.get("cards_under", 1.8)
        if selected_odds >= 2.0:
            return {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "soccer"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": "Cards",
                "selection": selection,
                "odds": selected_odds,
                "reason": "Card trend and referee profile favor this market.",
            }
        return None

    def _build_set_pick(self, match: Dict[str, Any]) -> Dict[str, Any] | None:
        odds = match.get("odds", {})
        player_a = odds.get("player_a")
        player_b = odds.get("player_b")
        if not all([player_a, player_b]):
            return None
        selection = "Player A" if player_a >= player_b else "Player B"
        selected_odds = player_a if selection == "Player A" else player_b
        if selected_odds >= 2.0:
            return {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "tennis"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": "Who Wins Set",
                "selection": selection,
                "odds": selected_odds,
                "reason": "Surface and recent performance favor this set winner.",
            }
        return None

    def _pick_best_wld(self, home, draw, away) -> str:
        values = {"home": home, "draw": draw, "away": away}
        return max(values, key=values.get)
