"""
Configuration settings for shared eBay client
"""
import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class ConfigurationError(Exception):
    """Raised when configuration is invalid or incomplete"""
    pass

class Config:
    """eBay Configuration"""
    
    def __init__(self):
        # Required eBay credentials
        self.ebay_app_id = os.getenv('EBAY_APP_ID')
        self.ebay_client_secret = os.getenv('EBAY_CLIENT_SECRET')
        self.ebay_dev_id = os.getenv('EBAY_DEV_ID')
        
        # User token (can be empty on first run, will be obtained via OAuth)
        self.ebay_user_token = os.getenv('EBAY_USER_TOKEN', '')
        self.ebay_refresh_token = os.getenv('EBAY_REFRESH_TOKEN', '')
        
        # API Endpoints
        self.ebay_browse_api_url = "https://api.ebay.com/buy/browse/v1"
            
    def validate(self):
        """Validate required configuration"""
        if not self.ebay_app_id:
            raise ConfigurationError("EBAY_APP_ID not set")
        if not self.ebay_client_secret:
            raise ConfigurationError("EBAY_CLIENT_SECRET not set")

# Global configuration instance
_config: Optional[Config] = None

def get_config() -> Config:
    """Get the global configuration instance"""
    global _config
    if _config is None:
        _config = Config()
    return _config
