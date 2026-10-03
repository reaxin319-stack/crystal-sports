import math
from collections import Counter
from typing import Any, Callable, Dict, List

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction import DictVectorizer


def _available_market_outcomes(market: str, odds: Dict[str, Any]):
    if market == "Over/Under":
        goal_totals = [
            ("over_1_5", "Over 1.5 Goals"),
            ("under_1_5", "Under 1.5 Goals"),
            ("over_2_5", "Over 2.5 Goals"),
            ("under_2_5", "Under 2.5 Goals"),
        ]
        available_totals = [(key, label) for key, label in goal_totals if odds.get(key) is not None]
        return available_totals or [("over", "Over"), ("under", "Under")]

    return {
        "WLD": [("home", "home"), ("draw", "draw"), ("away", "away")],
        "Cards": [("cards_over", "Over Cards"), ("cards_under", "Under Cards")],
        "Who Wins Set": [("player_a", "Player A"), ("player_b", "Player B")],
    }.get(market, [])


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
        if selected_odds >= 1.5:
            return {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "soccer"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": "WLD",
                "selection": selected,
                "odds": selected_odds,
                "scheduled_at": match.get("scheduled_at"),
                "reason": f"Value edge on {selected} based on current market pricing.",
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
                "scheduled_at": match.get("scheduled_at"),
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
                "scheduled_at": match.get("scheduled_at"),
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
                "scheduled_at": match.get("scheduled_at"),
                "reason": "Surface and recent performance favor this set winner.",
            }
        return None

    def _pick_best_wld(self, home, draw, away) -> str:
        values = {"home": home, "draw": draw, "away": away}
        return max(values, key=values.get)


class MarketFavoritePredictionEngine(PredictionEngine):
    def build_slips(self, matches: List[Dict[str, Any]], subscription: Dict[str, Any], admin_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        max_picks = subscription.get("max_odds", 3)
        picks = []
        for match in matches:
            if not self._is_allowed(match, subscription, admin_config):
                continue

            pick = self._build_market_favorite_pick(match)
            if pick:
                picks.append(pick)
            if len(picks) >= max_picks:
                break
        return picks

    def _build_market_favorite_pick(self, match: Dict[str, Any]) -> Dict[str, Any] | None:
        market = match.get("market", "WLD")
        odds = match.get("odds", {})
        available = []
        for key, label in _available_market_outcomes(market, odds):
            try:
                price = float(odds.get(key))
            except (TypeError, ValueError):
                continue
            if 1.0 < price < float("inf"):
                available.append((price, label))

        if not available:
            return None

        selected_odds, selection = min(available, key=lambda outcome: outcome[0])
        return {
            "league": match.get("league", "Unknown"),
            "sport": match.get("sport", "soccer"),
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "market": market,
            "selection": selection,
            "odds": selected_odds,
            "scheduled_at": match.get("scheduled_at"),
            "reason": "Market favorite based on the shortest available decimal odds.",
        }


class RandomForestPredictionEngine(PredictionEngine):
    MIN_TRAINING_SAMPLES = 30
    MIN_SAMPLES_PER_RESULT = 10

    def __init__(self, history_provider: Callable[[], List[Dict[str, Any]]] | None = None) -> None:
        self.history_provider = history_provider
        self._training_signature = None
        self._vectorizer = None
        self._classifier = None

    def build_slips(
        self,
        matches: List[Dict[str, Any]],
        subscription: Dict[str, Any],
        admin_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        max_picks = int(subscription.get("max_odds", 3) or 0)
        if max_picks <= 0:
            return []

        vectorizer, classifier = self._get_model(self._get_history())
        picks = []
        for match in matches:
            if not self._is_allowed(match, subscription, admin_config):
                continue
            candidates = self._build_candidates(match)
            if not candidates:
                continue

            if vectorizer and classifier:
                features = vectorizer.transform([candidate[1] for candidate in candidates])
                win_index = list(classifier.classes_).index("won")
                probabilities = classifier.predict_proba(features)
                selected_index = max(
                    range(len(candidates)),
                    key=lambda index: probabilities[index][win_index],
                )
                reason = "Random Forest selected the outcome with the highest predicted win probability."
            else:
                selected_index = min(
                    range(len(candidates)),
                    key=lambda index: candidates[index][0]["odds"],
                )
                reason = (
                    "Cold-start fallback: market-implied favorite. Random Forest requires "
                    "30 resolved picks with at least 10 wins and 10 losses."
                )

            picks.append({**candidates[selected_index][0], "reason": reason})
            if len(picks) >= max_picks:
                break
        return picks

    def _get_history(self) -> List[Dict[str, Any]]:
        if self.history_provider:
            return self.history_provider()
        import models

        return models.get_resolved_user_picks()

    def _get_model(self, history: List[Dict[str, Any]]):
        examples = []
        for record in history:
            label = str(record.get("status", "")).strip().lower()
            features = self._features(record)
            if label in {"won", "lost"} and features:
                examples.append((features, label))

        signature = tuple(
            sorted((tuple(sorted(features.items())), label) for features, label in examples)
        )
        if signature == self._training_signature:
            return self._vectorizer, self._classifier

        self._training_signature = signature
        self._vectorizer = None
        self._classifier = None
        outcome_counts = Counter(label for _, label in examples)
        if (
            len(examples) < self.MIN_TRAINING_SAMPLES
            or outcome_counts["won"] < self.MIN_SAMPLES_PER_RESULT
            or outcome_counts["lost"] < self.MIN_SAMPLES_PER_RESULT
        ):
            return None, None

        self._vectorizer = DictVectorizer(sparse=False)
        training_features = self._vectorizer.fit_transform([features for features, _ in examples])
        self._classifier = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=1,
        )
        self._classifier.fit(training_features, [label for _, label in examples])
        return self._vectorizer, self._classifier

    def _features(self, record: Dict[str, Any]) -> Dict[str, Any] | None:
        try:
            odds = float(record.get("odds"))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(odds) or odds <= 1:
            return None
        return {
            "sport": str(record.get("sport") or "soccer").strip().lower(),
            "market": str(record.get("market") or "WLD").strip().lower(),
            "league": str(record.get("league") or "unknown").strip().lower(),
            "selection": str(record.get("selection") or "").strip().lower(),
            "odds": odds,
        }

    def _build_candidates(self, match: Dict[str, Any]):
        market = match.get("market", "WLD")
        odds = match.get("odds", {})
        candidates = []
        for odds_key, selection in _available_market_outcomes(market, odds):
            features = self._features({
                "sport": match.get("sport"),
                "market": market,
                "league": match.get("league"),
                "selection": selection,
                "odds": odds.get(odds_key),
            })
            if not features:
                continue
            candidates.append(({
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "soccer"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": market,
                "selection": selection,
                "odds": features["odds"],
                "scheduled_at": match.get("scheduled_at"),
            }, features))
        return candidates
