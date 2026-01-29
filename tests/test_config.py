import os
import sys
import unittest
from pathlib import Path

APIHELPERS_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(APIHELPERS_SRC))

from shared_ebay import config as shared_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        shared_config._config = None

    def test_config_validate_success(self):
        os.environ["EBAY_APP_ID"] = "app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "secret"

        cfg = shared_config.Config()
        cfg.validate()

    def test_config_validate_missing_app_id(self):
        os.environ.pop("EBAY_APP_ID", None)
        os.environ["EBAY_CLIENT_SECRET"] = "secret"

        with self.assertRaises(shared_config.ConfigurationError):
            shared_config.Config().validate()

    def test_config_validate_missing_client_secret(self):
        os.environ["EBAY_APP_ID"] = "app-id"
        os.environ.pop("EBAY_CLIENT_SECRET", None)

        with self.assertRaises(shared_config.ConfigurationError):
            shared_config.Config().validate()

    def test_config_values_set_correctly(self):
        os.environ["EBAY_APP_ID"] = "test-app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "test-secret"

        cfg = shared_config.Config()
        cfg.validate()

        self.assertEqual(cfg.ebay_app_id, "test-app-id")
        self.assertEqual(cfg.ebay_client_secret, "test-secret")

    def test_get_config_singleton(self):
        os.environ["EBAY_APP_ID"] = "app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "secret"

        first = shared_config.get_config()
        second = shared_config.get_config()

        self.assertIs(first, second)
