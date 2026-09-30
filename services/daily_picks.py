from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any, Dict, List


class DailyPickService:
    """Generate one shared source set of matches for each UTC day."""

    def __init__(self) -> None:
        self._generated_date: date | None = None
        self._generated_at: datetime | None = None
        self._matches: List[Dict[str, Any]] = []

    def get_matches(self, data_service: Any) -> List[Dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        if self._generated_date != today:
            self._generate(today, data_service)
        return deepcopy(self._matches)

    def refresh(self, data_service: Any) -> List[Dict[str, Any]]:
        today = datetime.now(timezone.utc).date()
        self._generate(today, data_service)
        return deepcopy(self._matches)

    def status(self) -> Dict[str, Any]:
        return {
            "date": self._generated_date.isoformat() if self._generated_date else None,
            "generated_at": self._generated_at.isoformat() if self._generated_at else None,
            "match_count": len(self._matches),
        }

    def _generate(self, today: date, data_service: Any) -> None:
        self._matches = data_service.get_live_matches()
        self._generated_date = today
        self._generated_at = datetime.now(timezone.utc)
