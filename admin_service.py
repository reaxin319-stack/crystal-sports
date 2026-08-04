import json
from pathlib import Path
from typing import Any, Dict, List

from config import ALL_MARKETS, SPORTS


class AdminConfigService:
    def __init__(self, config_path: str | None = None) -> None:
        self.config_path = Path(config_path or Path(__file__).resolve().parent.parent / "data" / "admin_config.json")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self._load_or_create()

    def _load_or_create(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with self.config_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return self._merge_defaults(data)
            except Exception:
                pass

        default = self._default_config()
        self.save(default)
        return default

    def _default_config(self) -> Dict[str, Any]:
        return {
            "enabled_sports": ["soccer", "hockey", "tennis"],
            "allowed_markets": {
                "soccer": ["WLD", "Over/Under", "Cards"],
                "hockey": ["WLD", "Over/Under"],
                "tennis": ["WLD", "Who Wins Set"],
            },
            "plans": {
                "free": {
                    "name": "Free",
                    "price": "$0",
                    "duration": "1 month",
                    "max_odds": 3,
                    "allowed_sports": ["soccer", "hockey", "tennis"],
                    "allowed_markets": ["WLD", "Over/Under", "Who Wins Set"],
                    "description": "View live soccer, hockey, and tennis picks for one month.",
                        "stripe_price_id": "",
                },
                "pro": {
                    "name": "Pro",
                    "price": "$19",
                    "duration": "1 month",
                    "max_odds": 5,
                    "allowed_sports": ["soccer", "hockey"],
                    "allowed_markets": ["WLD", "Over/Under"],
                    "description": "Unlock soccer and hockey picks with 5-odds slips.",
                        "stripe_price_id": "",
                },
                "elite": {
                    "name": "Elite",
                    "price": "$39",
                    "duration": "1 month",
                    "max_odds": 10,
                    "allowed_sports": ["soccer", "hockey", "tennis"],
                    "allowed_markets": ["WLD", "Over/Under", "Who Wins Set"],
                    "description": "Access all three sports and 10-odds slips.",
                        "stripe_price_id": "",
                },
                "vip": {
                    "name": "VIP",
                    "price": "$79",
                    "duration": "1 month",
                    "max_odds": 20,
                    "allowed_sports": ["soccer", "hockey", "tennis"],
                    "allowed_markets": ["WLD", "Over/Under", "Cards", "Who Wins Set"],
                    "description": "Unlock premium multi-sport slips and auto magic combinations.",
                        "stripe_price_id": "",
                },
            },
        }

    def _merge_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        default = self._default_config()
        merged = default.copy()
        merged.update(config)
        merged["plans"] = {**default["plans"], **config.get("plans", {})}
        for plan_name, plan_value in merged["plans"].items():
            if isinstance(plan_value, dict):
                default_plan = default["plans"].get(plan_name, {})
                merged["plans"][plan_name] = {**default_plan, **plan_value}
        merged["allowed_markets"] = {**default["allowed_markets"], **config.get("allowed_markets", {})}
        return merged

    def save(self, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
        data = self._merge_defaults(config or self.config)
        self.config = data
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
        return data

    def get_config(self) -> Dict[str, Any]:
        return self.config

    def get_plans(self) -> Dict[str, Any]:
        return self.config.get("plans", {})

    def get_plan(self, plan_name: str) -> Dict[str, Any]:
        return self.config.get("plans", {}).get(plan_name, self.config.get("plans", {}).get("free", {}))

    def get_enabled_sports(self) -> List[str]:
        return self.config.get("enabled_sports", [])

    def get_allowed_markets(self, sport: str) -> List[str]:
        return self.config.get("allowed_markets", {}).get(sport, [])

    def get_available_sports(self) -> List[Dict[str, Any]]:
        return [
            {"key": key, "name": value["name"], "leagues": value["leagues"]}
            for key, value in SPORTS.items()
        ]

    def get_all_markets(self) -> List[str]:
        return ALL_MARKETS

    def update_from_form(self, form_data: Dict[str, Any] | Any) -> Dict[str, Any]:
        form_values = getattr(form_data, "form", form_data)

        self.config["enabled_sports"] = [value for value in form_values.getlist("sports")]

        allowed_markets = {}
        for sport in SPORTS:
            markets = [value for value in form_values.getlist(f"markets_{sport}")]
            allowed_markets[sport] = markets or ["WLD"]
        self.config["allowed_markets"] = allowed_markets

        for plan_name, plan in self.config.get("plans", {}).items():
            plan["max_odds"] = int(form_values.get(f"{plan_name}_max_odds", plan.get("max_odds", 3)))
            plan["price"] = form_values.get(f"{plan_name}_price", plan.get("price", "$0"))
            plan["duration"] = form_values.get(f"{plan_name}_duration", plan.get("duration", "1 month"))
            plan["description"] = form_values.get(f"{plan_name}_description", plan.get("description", ""))
            plan["stripe_price_id"] = form_values.get(f"{plan_name}_stripe_price", plan.get("stripe_price_id", ""))
            plan["allowed_sports"] = [value for value in form_values.getlist(f"{plan_name}_sports")]
            plan["allowed_markets"] = [value for value in form_values.getlist(f"{plan_name}_markets")]

        return self.save(self.config)
