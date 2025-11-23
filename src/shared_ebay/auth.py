"""
eBay OAuth Token Manager

Handles automatic token validation and refresh for eBay API authentication.
Tokens are stored in .env and automatically refreshed when they expire.

Usage:
    from shared_ebay import ensure_valid_token

    if ensure_valid_token():
        # Token is valid, proceed with API calls
        pass
"""
import os
import base64
import requests
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv, set_key
from typing import Optional, Tuple

from .config import get_config

load_dotenv()
logger = logging.getLogger(__name__)

class TokenManager:
    """Manages eBay OAuth tokens with automatic refresh"""
    
    def __init__(self):
        self.config = get_config()
        self.token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        self.env_file = self._find_env_file()
    
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
                return '.env' # Fallback
            current = parent
    
    def get_current_token(self) -> Optional[str]:
        """Get the current access token from environment"""
        load_dotenv(override=True)
        return os.getenv('EBAY_USER_TOKEN')
    
    def get_refresh_token(self) -> Optional[str]:
        """Get the refresh token from environment"""
        load_dotenv(override=True)
        return os.getenv('EBAY_REFRESH_TOKEN')
    
    def test_token_validity(self, token: str) -> Tuple[bool, Optional[str]]:
        """Test if a token is valid by making a simple API call"""
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
                return False, "Token is invalid or expired"
            return True, None
        except requests.exceptions.RequestException:
            return True, None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[dict]:
        """Use refresh token to get a new access token"""
        if not self.config.ebay_app_id or not self.config.ebay_client_secret:
            logger.error("EBAY_APP_ID or EBAY_CLIENT_SECRET not configured")
            return None
        
        credentials = f"{self.config.ebay_app_id}:{self.config.ebay_client_secret}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {b64_credentials}'
        }
        
        # Standard scopes
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
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            return None
    
    def save_tokens(self, token_data: dict) -> bool:
        """Save tokens to .env file"""
        try:
            if 'access_token' in token_data:
                set_key(self.env_file, 'EBAY_USER_TOKEN', token_data['access_token'])
            if 'refresh_token' in token_data:
                set_key(self.env_file, 'EBAY_REFRESH_TOKEN', token_data['refresh_token'])
            load_dotenv(override=True)
            return True
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
            return False

    def ensure_valid_token(self, verbose: bool = True) -> bool:
        """Ensure we have a valid access token, refreshing if necessary"""
        current_token = self.get_current_token()
        if not current_token:
            if verbose: print("❌ No access token found in .env")
            return False
            
        is_valid, error = self.test_token_validity(current_token)
        if is_valid:
            return True
            
        if verbose: print(f"⚠️  Access token invalid, refreshing...")
        
        refresh_token = self.get_refresh_token()
        if not refresh_token:
            if verbose: print("❌ No refresh token found")
            return False
            
        token_data = self.refresh_access_token(refresh_token)
        if not token_data:
            if verbose: print("❌ Failed to refresh token")
            return False
            
        if self.save_tokens(token_data):
            if verbose: print("✓ Token refreshed successfully!")
            return True
            
        return False

_token_manager = None

def get_token_manager() -> TokenManager:
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager

def ensure_valid_token(verbose: bool = True) -> bool:
    return get_token_manager().ensure_valid_token(verbose=verbose)
