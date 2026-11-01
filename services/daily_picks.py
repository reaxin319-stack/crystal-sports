from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import logging
from threading import Event, Thread
from typing import Any, Dict, List

def next_daily_pick_run(
    now: datetime,
    last_run_date: date | None = None,
    hour: int = 4,
) -> datetime:
    now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    if not 0 <= hour < 6:
        raise ValueError("Daily picks must be scheduled before 06:00 UTC")

    scheduled = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    cutoff = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if last_run_date == now.date() or now >= cutoff:
        return scheduled + timedelta(days=1)
    if now >= scheduled:
        return now
    return scheduled


class DailyPickScheduler:
    def __init__(self, callback, hour: int = 4) -> None:
        if not 0 <= hour < 6:
            raise ValueError("Daily picks must be scheduled before 06:00 UTC")
        self.callback = callback
        self.hour = hour
        self._stop_event = Event()
        self._thread = Thread(target=self._run, name="daily-pick-scheduler", daemon=True)
        self._last_run_date: date | None = None

    def start(self):
        if not self._thread.is_alive():
            self._thread.start()
        return self

    def shutdown(self, wait: bool = True) -> None:
        self._stop_event.set()
        if wait and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            next_run = next_daily_pick_run(now, self._last_run_date, self.hour)
            delay = max(0.0, (next_run - now).total_seconds())
            if self._stop_event.wait(delay):
                return

            self._last_run_date = datetime.now(timezone.utc).date()
            try:
                self.callback()
            except Exception:
                logging.exception("Scheduled daily pick generation failed")


def create_daily_pick_scheduler(callback, hour: int = 4) -> DailyPickScheduler:
    return DailyPickScheduler(callback, hour)


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
