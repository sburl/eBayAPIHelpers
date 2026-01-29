"""
eBay API Configuration

Manages eBay API credentials and endpoints loaded from environment variables.
Validates required credentials are present.
Supports multiple eBay accounts via suffix (e.g., EBAY_APP_ID_2 for second account).

Usage:
    from shared_ebay import get_config

    config = get_config()          # Default account
    config.validate()

    config2 = get_config("2")      # Second account using _2 suffix
    config2.validate()
"""
import os
import logging
from typing import Dict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete"""
    pass


def _key(base: str, suffix: str) -> str:
    """Helper to generate environment variable key with optional suffix"""
    return f"{base}_{suffix}" if suffix else base


class Config:
    """eBay Configuration (supports multiple accounts via numeric suffix)"""

    def __init__(self, suffix: str = ""):
        self.suffix = suffix
        env = lambda k, default=None: os.getenv(_key(k, suffix), default)

        # Required eBay credentials
        self.ebay_app_id = env('EBAY_APP_ID')
        self.ebay_client_secret = env('EBAY_CLIENT_SECRET')
        self.ebay_dev_id = env('EBAY_DEV_ID')

        # User token (can be empty on first run, will be obtained via OAuth)
        self.ebay_user_token = env('EBAY_USER_TOKEN', '')
        self.ebay_refresh_token = env('EBAY_REFRESH_TOKEN', '')

        # API Endpoints (Browse API used only for token validation)
        self.ebay_browse_api_url = "https://api.ebay.com/buy/browse/v1"

        # Optional: Sales tax rate for price calculations (0.0 = no tax)
        try:
            self.sales_tax_rate = float(env('SALES_TAX_RATE', '0.0'))
        except ValueError:
            logger.warning("Invalid SALES_TAX_RATE, using 0.0")
            self.sales_tax_rate = 0.0

    def validate(self):
        """Validate required configuration"""
        if not self.ebay_app_id:
            raise ConfigurationError(_key("EBAY_APP_ID", self.suffix) + " not set")
        if not self.ebay_client_secret:
            raise ConfigurationError(_key("EBAY_CLIENT_SECRET", self.suffix) + " not set")


# Global configuration instances keyed by suffix
_config: Dict[str, Config] = {}

def get_config(suffix: str = "") -> Config:
    """Get the global configuration instance"""
    global _config
    if suffix not in _config:
        _config[suffix] = Config(suffix)
    return _config[suffix]
