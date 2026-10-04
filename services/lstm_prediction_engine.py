import hashlib
import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

import torch
from torch import nn

from services.dixon_coles import DixonColesFallback


FEATURE_SIZE = 34
SEQUENCE_LENGTH = 5


def _available_market_outcomes(market: str, odds: Dict[str, Any]):
    if market == "Over/Under":
        goal_totals = [
            ("over_1_5", "Over 1.5 Goals"),
            ("under_1_5", "Under 1.5 Goals"),
            ("over_2_5", "Over 2.5 Goals"),
            ("under_2_5", "Under 2.5 Goals"),
        ]
        available_totals = [
            (key, label)
            for key, label in goal_totals
            if _valid_price(odds.get(key))
        ]
        return available_totals or [("over", "Over"), ("under", "Under")]

    return {
        "WLD": [("home", "home"), ("draw", "draw"), ("away", "away")],
        "Cards": [("cards_over", "Over Cards"), ("cards_under", "Under Cards")],
        "Who Wins Set": [("player_a", "Player A"), ("player_b", "Player B")],
    }.get(market, [])


def _valid_price(value: Any) -> bool:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(price) and price > 1.0


class _OutcomeLSTM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.sequence = nn.LSTM(
            input_size=FEATURE_SIZE,
            hidden_size=32,
            num_layers=1,
            batch_first=True,
        )
        self.classifier = nn.Sequential(nn.LayerNorm(32), nn.Linear(32, 1))

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        outputs, _ = self.sequence(features)
        return self.classifier(outputs[:, -1, :]).squeeze(-1)


class LSTMPredictionEngine:
    MIN_TRAINING_RECORDS = 40
    MIN_SAMPLES_PER_RESULT = 15
    TRAINING_EPOCHS = 120

    def __init__(self, history_provider: Callable[[], List[Dict[str, Any]]] | None = None) -> None:
        self.history_provider = history_provider
        self._training_signature = None
        self._model: _OutcomeLSTM | None = None
        self._dixon_coles = DixonColesFallback()
        self._history_features: List[List[float]] = []
        self.training_record_count = 0

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def prepare(self) -> bool:
        history = self._get_history()
        records = []
        for record in history:
            result = str(record.get("status", "")).strip().lower()
            features = self._features(record)
            if result in {"won", "lost"} and features:
                records.append((record, features, result))
        records.sort(key=lambda item: self._record_time(item[0]))

        signature = tuple(
            (
                tuple(features),
                result,
                self._record_time(record),
            )
            for record, features, result in records
        )
        if signature == self._training_signature:
            return self.is_trained

        self._training_signature = signature
        self._model = None
        self._history_features = [features for _, features, _ in records]
        self.training_record_count = len(records)
        result_counts = Counter(result for _, _, result in records)
        if (
            len(records) < self.MIN_TRAINING_RECORDS
            or result_counts["won"] < self.MIN_SAMPLES_PER_RESULT
            or result_counts["lost"] < self.MIN_SAMPLES_PER_RESULT
            or len(records) < SEQUENCE_LENGTH
        ):
            return False

        training_sequences = []
        training_targets = []
        for end in range(SEQUENCE_LENGTH - 1, len(records)):
            start = end - SEQUENCE_LENGTH + 1
            training_sequences.append(self._history_features[start : end + 1])
            training_targets.append(1.0 if records[end][2] == "won" else 0.0)

        torch.manual_seed(42)
        self._model = _OutcomeLSTM()
        features_tensor = torch.tensor(training_sequences, dtype=torch.float32)
        targets_tensor = torch.tensor(training_targets, dtype=torch.float32)
        positives = float(sum(training_targets))
        negatives = float(len(training_targets) - positives)
        positive_weight = torch.tensor([negatives / max(positives, 1.0)])
        loss_function = nn.BCEWithLogitsLoss(pos_weight=positive_weight)
        optimizer = torch.optim.AdamW(self._model.parameters(), lr=0.004, weight_decay=0.01)

        self._model.train()
        for _ in range(self.TRAINING_EPOCHS):
            optimizer.zero_grad()
            logits = self._model(features_tensor)
            loss = loss_function(logits, targets_tensor)
            loss.backward()
            optimizer.step()

        self._model.eval()
        return True

    def build_slips(
        self,
        matches: List[Dict[str, Any]],
        subscription: Dict[str, Any],
        admin_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if not self.prepare():
            return self._dixon_coles.build_slips(
                matches,
                subscription,
                admin_config,
                self.training_record_count,
                self.MIN_TRAINING_RECORDS,
            )

        max_picks = int(subscription.get("max_odds", 3) or 0)
        if max_picks <= 0:
            return []

        picks = []
        for match in matches:
            if not self._is_allowed(match, subscription, admin_config):
                continue
            candidates = self._build_candidates(match)
            if not candidates:
                continue

            sequences = [
                self._candidate_sequence(features)
                for _, features in candidates
            ]
            with torch.no_grad():
                logits = self._model(torch.tensor(sequences, dtype=torch.float32))
                probabilities = torch.sigmoid(logits).tolist()
            selected_index = max(range(len(candidates)), key=probabilities.__getitem__)
            pick = candidates[selected_index][0]
            pick["reason"] = (
                "LSTM sequence model selected the highest predicted win probability "
                f"({probabilities[selected_index]:.0%})."
            )
            picks.append(pick)
            if len(picks) >= max_picks:
                break
        return picks

    def build_magic_combinations(
        self,
        matches: List[Dict[str, Any]],
        subscription: Dict[str, Any],
        admin_config: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        if subscription.get("name", "").lower() != "vip":
            return []

        allowed = [match for match in matches if self._is_allowed(match, subscription, admin_config)]
        if len(allowed) < 3:
            return []

        combos = []
        for start in range(min(4, len(allowed))):
            items = allowed[start : start + 4]
            if len(items) >= 3:
                combos.append({
                    "title": f"VIP Combo {len(combos) + 1}",
                    "items": items,
                    "combined_odds": round(sum(item.get("odds", {}).get("home", 1.0) for item in items), 2),
                })
        return combos[:3]

    def _get_history(self) -> List[Dict[str, Any]]:
        if self.history_provider is not None:
            return self.history_provider()
        import models

        return models.get_resolved_user_picks()

    def _candidate_sequence(self, features: List[float]) -> List[List[float]]:
        prior_features = self._history_features[-(SEQUENCE_LENGTH - 1) :]
        padding = [[0.0] * FEATURE_SIZE] * (SEQUENCE_LENGTH - 1 - len(prior_features))
        return [*padding, *prior_features, features]

    def _build_candidates(self, match: Dict[str, Any]):
        market = match.get("market", "WLD")
        odds = match.get("odds", {})
        candidates = []
        for odds_key, selection in _available_market_outcomes(market, odds):
            price = odds.get(odds_key)
            if not _valid_price(price):
                continue
            pick = {
                "league": match.get("league", "Unknown"),
                "sport": match.get("sport", "soccer"),
                "home_team": match.get("home_team"),
                "away_team": match.get("away_team"),
                "market": market,
                "selection": selection,
                "odds": float(price),
                "scheduled_at": match.get("scheduled_at"),
            }
            candidates.append((pick, self._features(pick)))
        return candidates

    def _features(self, record: Dict[str, Any]) -> List[float] | None:
        try:
            odds = float(record.get("odds"))
        except (TypeError, ValueError):
            return None
        if not math.isfinite(odds) or odds <= 1.0:
            return None

        features = [0.0] * FEATURE_SIZE
        features[0] = min(odds, 30.0) / 30.0
        features[1] = 1.0 / odds
        categories = (
            f"sport:{record.get('sport') or 'soccer'}",
            f"market:{record.get('market') or 'WLD'}",
            f"league:{record.get('league') or 'unknown'}",
            f"home:{record.get('home_team') or 'unknown'}",
            f"away:{record.get('away_team') or 'unknown'}",
            f"selection:{record.get('selection') or 'unknown'}",
        )
        for category in categories:
            digest = hashlib.blake2b(category.casefold().encode("utf-8"), digest_size=4).digest()
            bucket = 2 + int.from_bytes(digest, "big") % (FEATURE_SIZE - 2)
            features[bucket] += 1.0
        return features

    def _record_time(self, record: Dict[str, Any]) -> str:
        value = str(record.get("scheduled_at") or record.get("created_at") or "")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return value

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
        admin_markets = admin_config.get("allowed_markets", {}).get(sport, [])
        return market in admin_markets or market == "WLD"
