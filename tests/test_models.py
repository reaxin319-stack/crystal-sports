import os
import tempfile
import unittest
from unittest.mock import patch

import models


class ModelDefaultsTests(unittest.TestCase):
    def test_users_can_verify_by_username_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                models.create_user("member_123", "person@example.com", "secure-password")

                self.assertIsNotNone(models.verify_user("member_123", "secure-password"))
                self.assertIsNone(models.verify_user("PERSON@EXAMPLE.COM", "secure-password"))

    def test_new_users_are_admin_and_use_default_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                user = models.create_user("adminuser", "admin@example.com", "", is_admin=True)

                self.assertTrue(user["is_admin"])
                self.assertTrue(models.verify_user("adminuser", "Admin123!") is not None)

    def test_default_seeded_accounts_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                models.init_db()
                admin = models.get_user_by_username(models.DEFAULT_ADMIN_USERNAME)
                free_user = models.get_user_by_username(models.DEFAULT_FREE_USERNAME)

                self.assertIsNotNone(admin)
                self.assertTrue(admin["is_admin"])
                self.assertTrue(models.verify_user(models.DEFAULT_ADMIN_USERNAME, models.DEFAULT_ADMIN_PASSWORD) is not None)

                self.assertIsNotNone(free_user)
                self.assertFalse(free_user["is_admin"])
                self.assertTrue(models.verify_user(models.DEFAULT_FREE_USERNAME, models.DEFAULT_FREE_PASSWORD) is not None)

    def test_admin_pick_results_include_more_than_200_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                user = models.create_user("reviewer", "reviewer@example.com", "secure-password")
                for number in range(201):
                    models.record_user_pick(
                        user["id"],
                        {
                            "league": "Premier League",
                            "home_team": f"Home {number}",
                            "away_team": "Away FC",
                            "selection": "home",
                            "scheduled_at": f"2026-10-01T{number:03d}",
                            "status": "won",
                        },
                    )

                picks = models.get_all_user_picks()

        self.assertEqual(len(picks), 201)
        self.assertTrue(all(pick["status"] == "won" for pick in picks))

    def test_resolved_pick_history_excludes_pending_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                user = models.create_user("reviewer", "reviewer@example.com", "secure-password")
                for status in ("pending", "won", "lost"):
                    models.record_user_pick(
                        user["id"],
                        {
                            "league": "Premier League",
                            "home_team": "Home FC",
                            "away_team": "Away FC",
                            "selection": "home",
                            "odds": 2.0,
                            "scheduled_at": f"2026-10-01T{status}",
                            "status": status,
                        },
                    )

                picks = models.get_resolved_user_picks()

        self.assertEqual({pick["status"] for pick in picks}, {"won", "lost"})

    def test_daily_pick_recipients_include_only_non_secret_user_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                first = models.create_user("member_one", "one@example.com", "secure-password")
                second = models.create_user("member_two", "two@example.com", "secure-password", "pro")

                users = models.get_users_for_daily_picks()

        returned_ids = {user["id"] for user in users}
        returned_usernames = {user["username"] for user in users}
        self.assertTrue({first["id"], second["id"]}.issubset(returned_ids))
        self.assertTrue({"member_one", "member_two"}.issubset(returned_usernames))
        self.assertTrue(all("password_hash" not in user for user in users))
