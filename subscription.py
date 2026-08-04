from typing import Dict, Any


class SubscriptionService:
    def __init__(self) -> None:
        self.plans = {}

    def get_plan(self, plan_name: str) -> Dict[str, Any]:
        return self.plans.get(plan_name, self.plans.get("free", {}))

    def is_active(self, plan_name: str | None, expires_at: str | None) -> bool:
        if plan_name in {"pro", "elite", "vip"} and expires_at:
            return True
        return plan_name == "free"
