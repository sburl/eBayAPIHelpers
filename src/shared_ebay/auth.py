"""
eBay OAuth Token Manager

Handles automatic token validation and refresh for eBay API authentication.
Tokens are stored in .env and automatically refreshed when they expire.
Supports multiple eBay accounts via suffix.

Token refresh strategy:
    - Access tokens expire every 2 hours (7200s)
    - Refresh tokens last ~18 months
    - We track token_refreshed_at locally to avoid unnecessary API test calls
    - Proactive refresh at 75% lifetime (5400s) avoids mid-request expiry
    - API test call only used on first run (no local timestamp yet)

Usage:
    from shared_ebay import ensure_valid_token

    if ensure_valid_token():
        # Token is valid, proceed with API calls
        pass

    # For second account:
    if ensure_valid_token(suffix="2"):
        # Second account token is valid
        pass
"""
import os
import base64
import time
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key
from typing import Optional, Tuple, Dict
from enum import Enum

from .config import get_config, _key


class TokenStatus(Enum):
    """Token validation status"""
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"  # Network error or unable to determine

load_dotenv()
logger = logging.getLogger(__name__)

# Proactive refresh threshold (seconds). Tokens are refreshed before this age
# to avoid mid-request expiry. eBay access tokens last 7200s (2 hours).
REFRESH_THRESHOLD = 5400    # 1.5 hours (75% of lifetime)

class TokenManager:
    """Manages eBay OAuth tokens with automatic refresh.

    This is the single source of truth for token lifecycle. eBayClient
    delegates all refresh decisions here via ensure_valid_token().
    """

    def __init__(self, suffix: str = ""):
        self.suffix = suffix
        self.config = get_config(suffix)
        self.token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        self.env_file = self._find_env_file()
        self.token_refreshed_at: Optional[datetime] = None

    def _find_env_file(self) -> str:
        """Find the .env file location"""
        # Look for .env in current directory or parent directories
        current = os.getcwd()
        while True:
            env_path = os.path.join(current, '.env')
            if os.path.exists(env_path):
                return env_path
            parent = os.path.dirname(current)
            if parent == current:
                return '.env'  # Fallback
            current = parent

    def _env_key(self, base: str) -> str:
        """Get environment variable key with optional suffix"""
        return _key(base, self.suffix)

    def _token_age_seconds(self) -> Optional[float]:
        """Return how many seconds since the token was last refreshed, or None if unknown."""
        if self.token_refreshed_at is None:
            return None
        return (datetime.now() - self.token_refreshed_at).total_seconds()

    def needs_refresh(self) -> bool:
        """Check if the token needs refreshing (past threshold or unknown age).

        Used by eBayClient to decide whether to call ensure_valid_token()
        before API calls, avoiding duplicate refresh logic.
        """
        age = self._token_age_seconds()
        if age is None:
            return True  # Unknown age — needs verification
        return age >= REFRESH_THRESHOLD

    def invalidate(self):
        """Mark the current token as needing re-validation.

        Forces the next ensure_valid_token() call to verify or refresh
        rather than trusting the local timestamp.
        """
        self.token_refreshed_at = None

    def get_current_token(self) -> Optional[str]:
        """Get the current access token from environment"""
        load_dotenv(override=True)
        return os.getenv(self._env_key('EBAY_USER_TOKEN'))

    def get_refresh_token(self) -> Optional[str]:
        """Get the refresh token from environment"""
        load_dotenv(override=True)
        return os.getenv(self._env_key('EBAY_REFRESH_TOKEN'))

    def test_token_validity(self, token: str) -> Tuple[TokenStatus, Optional[str]]:
        """
        Test if a token is valid by making a simple API call.

        Returns:
            (TokenStatus, error_message): Status and optional error message
            - VALID: Token is valid and working
            - INVALID: Token is expired or unauthorized (401)
            - UNKNOWN: Network error or unable to determine (conservative approach)
        """
        url = f"{self.config.ebay_browse_api_url}/item/get_item_by_legacy_id"
        headers = {
            'Authorization': f'Bearer {token}',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
            'Accept': 'application/json'
        }
        params = {'legacy_item_id': '123456789'}  # Dummy ID

        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 401:
                return TokenStatus.INVALID, "Token is invalid or expired"
            # Any other response (200, 404 item not found, etc.) means token is valid
            return TokenStatus.VALID, None
        except requests.exceptions.RequestException as e:
            # Network error - we can't determine validity, return UNKNOWN
            logger.warning(f"Unable to verify token validity due to network error: {e}")
            return TokenStatus.UNKNOWN, f"Network error: {str(e)}"

    def refresh_access_token(self, refresh_token: str) -> Optional[dict]:
        """Use refresh token to get a new access token.

        Retries once on transient network errors with a 2-second backoff.
        """
        if not self.config.ebay_app_id or not self.config.ebay_client_secret:
            logger.error("EBAY_APP_ID or EBAY_CLIENT_SECRET not configured")
            return None

        credentials = f"{self.config.ebay_app_id}:{self.config.ebay_client_secret}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {b64_credentials}'
        }

        # Standard scopes — override via EBAY_OAUTH_SCOPES env var if the app
        # only has a subset approved in the OAuth consent flow.
        scopes_env = os.getenv(self._env_key('EBAY_OAUTH_SCOPES'), '')
        if scopes_env.strip():
            scopes = scopes_env.strip().split()
        else:
            scopes = [
                'https://api.ebay.com/oauth/api_scope',
                'https://api.ebay.com/oauth/api_scope/buy.order',
                'https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',
                'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
                'https://api.ebay.com/oauth/api_scope/sell.account.readonly',
            ]

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': ' '.join(scopes)
        }

        last_error = None
        for attempt in range(2):  # Try twice for transient errors
            try:
                response = requests.post(self.token_url, headers=headers, data=data, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.ConnectionError as e:
                last_error = e
                logger.warning(f"Refresh attempt {attempt + 1} failed (connection error): {e}")
                if attempt == 0:
                    time.sleep(2)
                continue
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.warning(f"Refresh attempt {attempt + 1} failed (timeout): {e}")
                if attempt == 0:
                    time.sleep(2)
                continue
            except Exception as e:
                # Non-transient error (e.g. 400 invalid refresh token) — don't retry
                logger.error(f"Error refreshing token ({self.suffix or 'default'}): {e}")
                return None

        logger.error(f"Token refresh failed after 2 attempts ({self.suffix or 'default'}): {last_error}")
        return None

    def save_tokens(self, token_data: dict) -> bool:
        """Save tokens to .env file and update local refresh timestamp."""
        try:
            if 'access_token' in token_data:
                set_key(self.env_file, self._env_key('EBAY_USER_TOKEN'), token_data['access_token'])
            if 'refresh_token' in token_data:
                set_key(self.env_file, self._env_key('EBAY_REFRESH_TOKEN'), token_data['refresh_token'])
            load_dotenv(override=True)
            self.token_refreshed_at = datetime.now()
            return True
        except Exception as e:
            logger.error(f"Error saving tokens ({self.suffix or 'default'}): {e}")
            return False

    def _do_refresh(self, verbose: bool) -> bool:
        """Attempt to refresh the access token using the refresh token."""
        refresh_token = self.get_refresh_token()
        if not refresh_token:
            if verbose: print(f"❌ No refresh token found for suffix '{self.suffix}'")
            return False

        token_data = self.refresh_access_token(refresh_token)
        if not token_data:
            if verbose: print("❌ Failed to refresh token")
            return False

        if self.save_tokens(token_data):
            if verbose: print("✓ Token refreshed successfully!")
            return True

        if verbose: print("❌ Failed to save refreshed token")
        return False

    def ensure_valid_token(self, verbose: bool = True) -> bool:
        """
        Ensure we have a valid access token, refreshing if necessary.

        Strategy:
            1. If token was refreshed recently (within REFRESH_THRESHOLD), skip validation
            2. If token is past the proactive refresh threshold, refresh immediately
            3. Otherwise (first call, unknown age), test via API and refresh if invalid

        Returns:
            bool: True if token is valid or successfully refreshed, False otherwise
        """
        current_token = self.get_current_token()
        if not current_token:
            if verbose: print(f"❌ No access token found in .env for suffix '{self.suffix}'")
            return False

        # Fast path: token was refreshed recently, skip API test
        if not self.needs_refresh():
            return True

        # If we have a timestamp and it's past threshold, proactively refresh
        if self.token_refreshed_at is not None:
            if verbose: print(f"⚠️  Token approaching expiry, refreshing proactively...")
            return self._do_refresh(verbose)

        # Unknown age (first call): verify via API
        status, error = self.test_token_validity(current_token)

        if status == TokenStatus.VALID:
            # Token is valid now but we don't know its actual age. Set timestamp
            # to half-threshold ago so we'll re-check in ~45 min rather than
            # assuming it's fresh for the full 90 min (it could be close to expiry).
            self.token_refreshed_at = datetime.now() - timedelta(seconds=REFRESH_THRESHOLD / 2)
            return True

        if status == TokenStatus.UNKNOWN:
            # Network error — assume token might be valid. Set timestamp so we
            # don't hit the API test again immediately on the next call.
            if verbose: print(f"⚠️  Unable to verify token (network error), assuming valid: {error}")
            self.token_refreshed_at = datetime.now() - timedelta(seconds=REFRESH_THRESHOLD / 2)
            return True

        # Token is INVALID — attempt refresh
        if verbose: print(f"⚠️  Access token invalid, refreshing... (suffix '{self.suffix}')")
        return self._do_refresh(verbose)


_token_managers: Dict[str, TokenManager] = {}


def get_token_manager(suffix: str = "") -> TokenManager:
    global _token_managers
    if suffix not in _token_managers:
        _token_managers[suffix] = TokenManager(suffix)
    return _token_managers[suffix]


def ensure_valid_token(verbose: bool = True, suffix: str = "") -> bool:
    return get_token_manager(suffix).ensure_valid_token(verbose=verbose)
