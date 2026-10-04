import math
from typing import Any, Dict, List


RHO = -0.08
MAX_GOALS = 10
GOAL_TOTALS = (
    ("over_1_5", "Over 1.5 Goals", 1.5),
    ("under_1_5", "Under 1.5 Goals", 1.5),
    ("over_2_5", "Over 2.5 Goals", 2.5),
    ("under_2_5", "Under 2.5 Goals", 2.5),
)


def _price(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result > 1 else None


def _fair_probabilities(prices: Dict[str, Any], outcomes: List[str]) -> Dict[str, float] | None:
    implied = {}
    for outcome in outcomes:
        price = _price(prices.get(outcome))
        if price is None:
            return None
        implied[outcome] = 1 / price
    overround = sum(implied.values())
    if overround <= 0:
        return None
    return {outcome: probability / overround for outcome, probability in implied.items()}


def _poisson(rate: float) -> List[float]:
    probabilities = [math.exp(-rate)]
    for goals in range(1, MAX_GOALS + 1):
        probabilities.append(probabilities[-1] * rate / goals)
    return probabilities


def _score_matrix(home_rate: float, away_rate: float) -> List[List[float]]:
    home_scores = _poisson(home_rate)
    away_scores = _poisson(away_rate)
    matrix = []
    for home_goals, home_probability in enumerate(home_scores):
        row = []
        for away_goals, away_probability in enumerate(away_scores):
            correction = 1.0
            if home_goals == 0 and away_goals == 0:
                correction = 1 - home_rate * away_rate * RHO
            elif home_goals == 0 and away_goals == 1:
                correction = 1 + home_rate * RHO
            elif home_goals == 1 and away_goals == 0:
                correction = 1 + away_rate * RHO
            elif home_goals == 1 and away_goals == 1:
                correction = 1 - RHO
            row.append(home_probability * away_probability * correction)
        matrix.append(row)

    total = sum(sum(row) for row in matrix)
    return [[probability / total for probability in row] for row in matrix]


def _outcome_probabilities(matrix: List[List[float]]) -> Dict[str, float]:
    home = draw = away = 0.0
    for home_goals, row in enumerate(matrix):
        for away_goals, probability in enumerate(row):
            if home_goals > away_goals:
                home += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                away += probability
    return {"home": home, "draw": draw, "away": away}


def _fit_rates(target: Dict[str, float]) -> tuple[float, float]:
    best_home, best_away, best_error = 1.4, 1.2, float("inf")
    for step, radius in ((0.1, 5.0), (0.02, 0.12), (0.005, 0.025)):
        if best_error == float("inf"):
            home_rates = [index * step for index in range(2, int(radius / step) + 1)]
            away_rates = home_rates
        else:
            home_rates = [
                best_home + offset * step
                for offset in range(-int(radius / step), int(radius / step) + 1)
                if 0.05 <= best_home + offset * step <= 5.0
            ]
            away_rates = [
                best_away + offset * step
                for offset in range(-int(radius / step), int(radius / step) + 1)
                if 0.05 <= best_away + offset * step <= 5.0
            ]

        for home_rate in home_rates:
            for away_rate in away_rates:
                probabilities = _outcome_probabilities(_score_matrix(home_rate, away_rate))
                error = sum((probabilities[key] - target[key]) ** 2 for key in ("home", "draw", "away"))
                if error < best_error:
                    best_home, best_away, best_error = home_rate, away_rate, error
    return best_home, best_away


def _fit_total_rate(odds: Dict[str, Any]) -> float | None:
    line = None
    target_over = None
    for over_key, under_key, threshold in (
        ("over_2_5", "under_2_5", 2.5),
        ("over_1_5", "under_1_5", 1.5),
    ):
        probabilities = _fair_probabilities(odds, [over_key, under_key])
        if probabilities:
            line = threshold
            target_over = probabilities[over_key]
            break
    if line is None or target_over is None:
        return None

    goal_count = math.floor(line) + 1
    best_rate, best_error = 2.6, float("inf")
    for step, values in ((0.1, [index / 10 for index in range(2, 61)]), (0.01, [])):
        if not values:
            values = [best_rate + index * step for index in range(-10, 11) if 0.1 <= best_rate + index * step <= 6.0]
        for total_rate in values:
            matrix = _score_matrix(total_rate / 2, total_rate / 2)
            over_probability = sum(
                matrix[home_goals][away_goals]
                for home_goals in range(len(matrix))
                for away_goals in range(len(matrix[home_goals]))
                if home_goals + away_goals >= goal_count
            )
            error = abs(over_probability - target_over)
            if error < best_error:
                best_rate, best_error = total_rate, error
    return best_rate


class DixonColesFallback:
    """Market-calibrated Dixon-Coles soccer fallback for an untrained sequence model."""

    def build_slips(
        self,
        matches: List[Dict[str, Any]],
        subscription: Dict[str, Any],
        admin_config: Dict[str, Any],
        training_record_count: int,
        min_training_records: int,
    ) -> List[Dict[str, Any]]:
        max_picks = int(subscription.get("max_odds", 3) or 0)
        picks = []
        if max_picks <= 0:
            return picks

        for match in matches:
            if not self._is_allowed(match, subscription, admin_config):
                continue
            pick = self._build_pick(match, training_record_count, min_training_records)
            if pick:
                picks.append(pick)
            if len(picks) >= max_picks:
                break
        return picks

    def _build_pick(
        self,
        match: Dict[str, Any],
        training_record_count: int,
        min_training_records: int,
    ) -> Dict[str, Any] | None:
        if str(match.get("sport", "")).casefold() != "soccer":
            return None

        market = match.get("market", "WLD")
        odds = match.get("odds", {})
        if market == "WLD":
            target = _fair_probabilities(odds, ["home", "draw", "away"])
            if not target:
                return None
            home_rate, away_rate = _fit_rates(target)
            probabilities = _outcome_probabilities(_score_matrix(home_rate, away_rate))
            selection = max(probabilities, key=probabilities.get)
            selected_odds = _price(odds.get(selection))
            confidence = probabilities[selection]
        elif market == "Over/Under":
            total_rate = _fit_total_rate(odds)
            if total_rate is None:
                return None
            matrix = _score_matrix(total_rate / 2, total_rate / 2)
            candidates = []
            for odds_key, label, line in GOAL_TOTALS:
                price = _price(odds.get(odds_key))
                if price is None:
                    continue
                total_goals = sum(
                    matrix[home_goals][away_goals]
                    for home_goals in range(len(matrix))
                    for away_goals in range(len(matrix[home_goals]))
                    if home_goals + away_goals > line
                )
                probability = total_goals if label.startswith("Over") else 1 - total_goals
                candidates.append((label, price, probability))
            if not candidates:
                return None
            selection, selected_odds, confidence = max(candidates, key=lambda candidate: candidate[2])
            home_rate = away_rate = total_rate / 2
        else:
            return None

        return {
            "league": match.get("league", "Unknown"),
            "sport": "soccer",
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "market": market,
            "selection": selection,
            "odds": selected_odds,
            "scheduled_at": match.get("scheduled_at"),
            "reason": (
                "Dixon-Coles soccer fallback calibrated from market odds; "
                f"estimated goals {home_rate:.2f}-{away_rate:.2f}, "
                f"outcome probability {confidence:.0%}. LSTM training: "
                f"{training_record_count}/{min_training_records} resolved picks."
            ),
        }

    def _is_allowed(
        self,
        match: Dict[str, Any],
        subscription: Dict[str, Any],
        admin_config: Dict[str, Any],
    ) -> bool:
        sport = match.get("sport", "soccer")
        market = match.get("market", "WLD")
        if sport not in subscription.get("allowed_sports", ["soccer"]):
            return False
        if market not in subscription.get("allowed_markets", ["WLD"]):
            return False
        allowed_markets = admin_config.get("allowed_markets", {}).get(sport, [])
        return market in allowed_markets or market == "WLD"
