import os
import tempfile
import unittest
from unittest.mock import patch

import models


class ModelDefaultsTests(unittest.TestCase):
    def test_users_can_verify_by_email_or_existing_username(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                models.create_user("member_123", "person@example.com", "secure-password")

                self.assertIsNotNone(models.verify_user("PERSON@EXAMPLE.COM", "secure-password"))
                self.assertIsNotNone(models.verify_user("member_123", "secure-password"))

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
