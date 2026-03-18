import os
import sys
import unittest
from unittest.mock import MagicMock, patch, mock_open
from datetime import datetime, timedelta
from pathlib import Path

APIHELPERS_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(APIHELPERS_SRC))

from shared_ebay import auth as shared_auth
from shared_ebay.auth import TokenStatus, REFRESH_THRESHOLD
from shared_ebay.config import Config


class TestTokenManager(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()
        # Set up minimal required env vars
        os.environ["EBAY_APP_ID"] = "test-app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "test-secret"
        shared_auth._token_managers = {}

        # Patch load_dotenv to prevent tests from reading real .env files
        # This makes tests hermetic and prevents false positives/negatives
        self.mock_auth_load_dotenv = patch('shared_ebay.auth.load_dotenv').start()
        self.mock_config_load_dotenv = patch('shared_ebay.config.load_dotenv').start()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        shared_auth._token_managers = {}

        # Stop all patches
        patch.stopall()

    def test_token_manager_initialization(self):
        manager = shared_auth.TokenManager()
        self.assertEqual(manager.suffix, "")
        self.assertIsNotNone(manager.config)
        self.assertEqual(manager.token_url, "https://api.ebay.com/identity/v1/oauth2/token")
        self.assertIsNone(manager.token_refreshed_at)

    def test_token_manager_with_suffix(self):
        os.environ["EBAY_APP_ID_2"] = "test-app-id-2"
        os.environ["EBAY_CLIENT_SECRET_2"] = "test-secret-2"

        manager = shared_auth.TokenManager("2")
        self.assertEqual(manager.suffix, "2")
        self.assertEqual(manager.config.ebay_app_id, "test-app-id-2")

    def test_get_current_token_no_token(self):
        os.environ.pop("EBAY_USER_TOKEN", None)
        manager = shared_auth.TokenManager()
        self.assertIsNone(manager.get_current_token())

    def test_get_current_token_with_token(self):
        os.environ["EBAY_USER_TOKEN"] = "test-token-123"
        manager = shared_auth.TokenManager()
        self.assertEqual(manager.get_current_token(), "test-token-123")

    def test_get_current_token_with_suffix(self):
        os.environ["EBAY_USER_TOKEN_2"] = "test-token-456"
        manager = shared_auth.TokenManager("2")
        self.assertEqual(manager.get_current_token(), "test-token-456")

    def test_get_refresh_token(self):
        os.environ["EBAY_REFRESH_TOKEN"] = "refresh-token-123"
        manager = shared_auth.TokenManager()
        self.assertEqual(manager.get_refresh_token(), "refresh-token-123")

    @patch('shared_ebay.auth.requests.get')
    def test_token_validity_valid_token(self, mock_get):
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        manager = shared_auth.TokenManager()
        status, error = manager.test_token_validity("valid-token")

        self.assertEqual(status, TokenStatus.VALID)
        self.assertIsNone(error)
        mock_get.assert_called_once()

    @patch('shared_ebay.auth.requests.get')
    def test_token_validity_expired_token(self, mock_get):
        # Mock 401 unauthorized response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        manager = shared_auth.TokenManager()
        status, error = manager.test_token_validity("expired-token")

        self.assertEqual(status, TokenStatus.INVALID)
        self.assertEqual(error, "Token is invalid or expired")

    @patch('shared_ebay.auth.requests.get')
    def test_token_validity_network_error(self, mock_get):
        # Mock network error - should return UNKNOWN (can't determine)
        import requests
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        manager = shared_auth.TokenManager()
        status, error = manager.test_token_validity("token")

        # Network errors return UNKNOWN (not VALID or INVALID)
        # This avoids false positives/negatives when eBay API is unreachable
        self.assertEqual(status, TokenStatus.UNKNOWN)
        self.assertIn("Network error", error)

    @patch('shared_ebay.auth.requests.post')
    def test_refresh_access_token_success(self, mock_post):
        # Mock successful token refresh
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'new-access-token',
            'refresh_token': 'new-refresh-token',
            'expires_in': 7200
        }
        mock_post.return_value = mock_response

        manager = shared_auth.TokenManager()
        result = manager.refresh_access_token("old-refresh-token")

        self.assertIsNotNone(result)
        self.assertEqual(result['access_token'], 'new-access-token')
        self.assertEqual(result['refresh_token'], 'new-refresh-token')
        mock_post.assert_called_once()

    @patch('shared_ebay.auth.requests.post')
    def test_refresh_access_token_invalid_refresh_token(self, mock_post):
        # Mock 400 bad request (invalid refresh token) — should NOT retry
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = Exception("Invalid refresh token")
        mock_post.return_value = mock_response

        manager = shared_auth.TokenManager()
        result = manager.refresh_access_token("invalid-refresh-token")

        self.assertIsNone(result)
        # Non-transient error: should only try once
        self.assertEqual(mock_post.call_count, 1)

    @patch('shared_ebay.auth.requests.post')
    def test_refresh_access_token_transient_network_error_retries(self, mock_post):
        """Transient connection errors should retry once."""
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("Connection refused")

        manager = shared_auth.TokenManager()
        result = manager.refresh_access_token("refresh-token")

        self.assertIsNone(result)
        # Should have tried twice (initial + 1 retry)
        self.assertEqual(mock_post.call_count, 2)

    @patch('shared_ebay.auth.requests.post')
    def test_refresh_access_token_transient_then_success(self, mock_post):
        """First attempt fails transiently, second succeeds."""
        import requests as req
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'access_token': 'new-token',
            'expires_in': 7200
        }
        mock_post.side_effect = [
            req.exceptions.Timeout("Timeout"),
            mock_response,
        ]

        manager = shared_auth.TokenManager()
        result = manager.refresh_access_token("refresh-token")

        self.assertIsNotNone(result)
        self.assertEqual(result['access_token'], 'new-token')
        self.assertEqual(mock_post.call_count, 2)

    @patch('shared_ebay.auth.set_key')
    @patch('shared_ebay.auth.load_dotenv')
    def test_save_tokens_success(self, mock_load_dotenv, mock_set_key):
        manager = shared_auth.TokenManager()
        token_data = {
            'access_token': 'new-access-token',
            'refresh_token': 'new-refresh-token'
        }

        result = manager.save_tokens(token_data)

        self.assertTrue(result)
        self.assertEqual(mock_set_key.call_count, 2)
        mock_load_dotenv.assert_called_once()
        # save_tokens should set token_refreshed_at
        self.assertIsNotNone(manager.token_refreshed_at)

    @patch('shared_ebay.auth.set_key')
    def test_save_tokens_with_suffix(self, mock_set_key):
        os.environ["EBAY_APP_ID_2"] = "test-app-id-2"
        os.environ["EBAY_CLIENT_SECRET_2"] = "test-secret-2"

        manager = shared_auth.TokenManager("2")
        token_data = {
            'access_token': 'new-access-token',
            'refresh_token': 'new-refresh-token'
        }

        manager.save_tokens(token_data)

        # Verify keys are saved with suffix
        calls = [str(call) for call in mock_set_key.call_args_list]
        self.assertTrue(any('EBAY_USER_TOKEN_2' in call for call in calls))
        self.assertTrue(any('EBAY_REFRESH_TOKEN_2' in call for call in calls))

    @patch('shared_ebay.auth.set_key')
    def test_save_tokens_error(self, mock_set_key):
        mock_set_key.side_effect = Exception("Permission denied")

        manager = shared_auth.TokenManager()
        token_data = {'access_token': 'token'}

        result = manager.save_tokens(token_data)

        self.assertFalse(result)

    # --- Token freshness tests ---

    def test_needs_refresh_when_just_refreshed(self):
        manager = shared_auth.TokenManager()
        manager.token_refreshed_at = datetime.now()
        self.assertFalse(manager.needs_refresh())

    def test_needs_refresh_when_old(self):
        manager = shared_auth.TokenManager()
        manager.token_refreshed_at = datetime.now() - timedelta(seconds=REFRESH_THRESHOLD + 100)
        self.assertTrue(manager.needs_refresh())

    def test_needs_refresh_when_unknown(self):
        manager = shared_auth.TokenManager()
        manager.token_refreshed_at = None
        self.assertTrue(manager.needs_refresh())

    # --- ensure_valid_token with local tracking ---

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    def test_ensure_valid_token_no_token(self, mock_get_current_token):
        mock_get_current_token.return_value = None

        manager = shared_auth.TokenManager()
        result = manager.ensure_valid_token(verbose=False)

        self.assertFalse(result)

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    def test_ensure_valid_token_skips_api_test_when_fresh(self, mock_test_validity, mock_get_current_token):
        """When token was recently refreshed, skip the API test call entirely."""
        mock_get_current_token.return_value = "valid-token"

        manager = shared_auth.TokenManager()
        manager.token_refreshed_at = datetime.now()  # Just refreshed

        result = manager.ensure_valid_token(verbose=False)

        self.assertTrue(result)
        # Should NOT have called test_token_validity — that's the whole point
        mock_test_validity.assert_not_called()

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, '_do_refresh')
    def test_ensure_valid_token_proactive_refresh_when_old(self, mock_do_refresh, mock_get_current_token):
        """When token is past threshold and has a known timestamp, proactively refresh."""
        mock_get_current_token.return_value = "old-token"
        mock_do_refresh.return_value = True

        manager = shared_auth.TokenManager()
        manager.token_refreshed_at = datetime.now() - timedelta(seconds=REFRESH_THRESHOLD + 100)

        result = manager.ensure_valid_token(verbose=False)

        self.assertTrue(result)
        mock_do_refresh.assert_called_once()

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    def test_ensure_valid_token_first_call_uses_api_test(self, mock_test_validity, mock_get_current_token):
        """On first call (no local timestamp), fall back to API test."""
        mock_get_current_token.return_value = "token"
        mock_test_validity.return_value = (TokenStatus.VALID, None)

        manager = shared_auth.TokenManager()
        # token_refreshed_at is None (first call)

        result = manager.ensure_valid_token(verbose=False)

        self.assertTrue(result)
        mock_test_validity.assert_called_once()
        # After successful API test, should have set a timestamp
        self.assertIsNotNone(manager.token_refreshed_at)

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    def test_ensure_valid_token_unknown_status(self, mock_test_validity, mock_get_current_token):
        # When status is UNKNOWN (network error), should return True (conservative)
        # and set timestamp to avoid hitting the API test again immediately
        mock_get_current_token.return_value = "token"
        mock_test_validity.return_value = (TokenStatus.UNKNOWN, "Network error")

        manager = shared_auth.TokenManager()
        result = manager.ensure_valid_token(verbose=False)

        self.assertTrue(result)  # Assumes token might be valid
        self.assertIsNotNone(manager.token_refreshed_at)  # Timestamp set

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    @patch.object(shared_auth.TokenManager, 'get_refresh_token')
    def test_ensure_valid_token_no_refresh_token(self, mock_get_refresh, mock_test_validity, mock_get_current_token):
        mock_get_current_token.return_value = "expired-token"
        mock_test_validity.return_value = (TokenStatus.INVALID, "Token expired")
        mock_get_refresh.return_value = None

        manager = shared_auth.TokenManager()
        result = manager.ensure_valid_token(verbose=False)

        self.assertFalse(result)

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    @patch.object(shared_auth.TokenManager, 'get_refresh_token')
    @patch.object(shared_auth.TokenManager, 'refresh_access_token')
    @patch.object(shared_auth.TokenManager, 'save_tokens')
    def test_ensure_valid_token_refresh_success(self, mock_save, mock_refresh, mock_get_refresh, mock_test_validity, mock_get_current_token):
        mock_get_current_token.return_value = "expired-token"
        mock_test_validity.return_value = (TokenStatus.INVALID, "Token expired")
        mock_get_refresh.return_value = "refresh-token"
        mock_refresh.return_value = {'access_token': 'new-token'}
        mock_save.return_value = True

        manager = shared_auth.TokenManager()
        result = manager.ensure_valid_token(verbose=False)

        self.assertTrue(result)
        mock_refresh.assert_called_once_with("refresh-token")
        mock_save.assert_called_once()

    @patch.object(shared_auth.TokenManager, 'get_current_token')
    @patch.object(shared_auth.TokenManager, 'test_token_validity')
    @patch.object(shared_auth.TokenManager, 'get_refresh_token')
    @patch.object(shared_auth.TokenManager, 'refresh_access_token')
    def test_ensure_valid_token_refresh_failure(self, mock_refresh, mock_get_refresh, mock_test_validity, mock_get_current_token):
        mock_get_current_token.return_value = "expired-token"
        mock_test_validity.return_value = (TokenStatus.INVALID, "Token expired")
        mock_get_refresh.return_value = "refresh-token"
        mock_refresh.return_value = None

        manager = shared_auth.TokenManager()
        result = manager.ensure_valid_token(verbose=False)

        self.assertFalse(result)


class TestHelperFunctions(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()
        os.environ["EBAY_APP_ID"] = "test-app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "test-secret"
        shared_auth._token_managers = {}

        # Patch load_dotenv to prevent tests from reading real .env files
        self.mock_auth_load_dotenv = patch('shared_ebay.auth.load_dotenv').start()
        self.mock_config_load_dotenv = patch('shared_ebay.config.load_dotenv').start()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)
        shared_auth._token_managers = {}

        # Stop all patches
        patch.stopall()

    def test_get_token_manager_singleton(self):
        manager1 = shared_auth.get_token_manager()
        manager2 = shared_auth.get_token_manager()

        self.assertIs(manager1, manager2)

    def test_get_token_manager_with_different_suffixes(self):
        os.environ["EBAY_APP_ID_2"] = "test-app-id-2"
        os.environ["EBAY_CLIENT_SECRET_2"] = "test-secret-2"

        manager1 = shared_auth.get_token_manager()
        manager2 = shared_auth.get_token_manager("2")

        self.assertIsNot(manager1, manager2)
        self.assertEqual(manager1.suffix, "")
        self.assertEqual(manager2.suffix, "2")

    @patch.object(shared_auth.TokenManager, 'ensure_valid_token')
    def test_ensure_valid_token_helper(self, mock_ensure):
        mock_ensure.return_value = True

        result = shared_auth.ensure_valid_token(verbose=False)

        self.assertTrue(result)
        mock_ensure.assert_called_once_with(verbose=False)

    @patch.object(shared_auth.TokenManager, 'ensure_valid_token')
    def test_ensure_valid_token_with_suffix(self, mock_ensure):
        os.environ["EBAY_APP_ID_2"] = "test-app-id-2"
        os.environ["EBAY_CLIENT_SECRET_2"] = "test-secret-2"
        mock_ensure.return_value = True

        result = shared_auth.ensure_valid_token(verbose=False, suffix="2")

        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
