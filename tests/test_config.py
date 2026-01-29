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
        shared_config._config = {}

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

    def test_suffix_key_helper(self):
        self.assertEqual(shared_config._key("EBAY_APP_ID", ""), "EBAY_APP_ID")
        self.assertEqual(shared_config._key("EBAY_APP_ID", "2"), "EBAY_APP_ID_2")

    def test_suffix_specific_config(self):
        os.environ["EBAY_APP_ID"] = "app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "secret"
        os.environ["EBAY_APP_ID_2"] = "app-id-2"
        os.environ["EBAY_CLIENT_SECRET_2"] = "secret-2"

        default_cfg = shared_config.get_config()
        suffix_cfg = shared_config.get_config("2")

        self.assertNotEqual(default_cfg.ebay_app_id, suffix_cfg.ebay_app_id)
        self.assertEqual(default_cfg.ebay_app_id, "app-id")
        self.assertEqual(suffix_cfg.ebay_app_id, "app-id-2")
        self.assertEqual(default_cfg.ebay_client_secret, "secret")
        self.assertEqual(suffix_cfg.ebay_client_secret, "secret-2")
