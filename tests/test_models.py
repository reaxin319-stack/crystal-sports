import os
import tempfile
import unittest
from unittest.mock import patch

import models


class ModelDefaultsTests(unittest.TestCase):
    def test_new_users_are_admin_and_use_default_password(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.db")
            with patch.object(models, "DB_PATH", db_path):
                user = models.create_user("adminuser", "admin@example.com", "")

                self.assertTrue(user["is_admin"])
                self.assertTrue(models.verify_user("adminuser", "Admin123!") is not None)
