import tempfile
import unittest

from services.admin_service import AdminConfigService


class AdminConfigServiceTests(unittest.TestCase):
    def test_free_plan_uses_four_odds_and_upgrades_saved_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            service = AdminConfigService(config_path=f"{tmpdir}/admin_config.json")

            self.assertEqual(service.get_plan("free")["max_odds"], 4)
            migrated = service._merge_defaults({"plans": {"free": {"max_odds": 3}}})
            customized = service._merge_defaults({"plans": {"free": {"max_odds": 5}}})

        self.assertEqual(migrated["plans"]["free"]["max_odds"], 4)
        self.assertEqual(customized["plans"]["free"]["max_odds"], 5)

    def test_stale_empty_plan_accessors_are_filled_from_defaults(self) -> None:
        stale = {
            "plans": {
                "free": {"max_odds": 3, "allowed_sports": [], "allowed_markets": []},
                "pro": {"allowed_sports": [], "allowed_markets": []},
                "elite": {"allowed_sports": [], "allowed_markets": []},
                "vip": {"allowed_sports": [], "allowed_markets": []},
            }
        }

        service = AdminConfigService(config_path="/tmp/unused_admin_config.json")
        merged = service._merge_defaults(stale)

        for plan_name in ["free", "pro", "elite", "vip"]:
            self.assertTrue(merged["plans"][plan_name]["allowed_sports"])
            self.assertTrue(merged["plans"][plan_name]["allowed_markets"])
            self.assertGreater(merged["plans"][plan_name]["max_odds"], 0)


if __name__ == "__main__":
    unittest.main()