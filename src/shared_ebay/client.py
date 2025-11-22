"""
eBay API client using Browse API with OAuth authentication
"""
import requests
import logging
from typing import Optional
from urllib.parse import urlparse
from datetime import datetime

from .config import get_config
from .models import ListingData
from .auth import ensure_valid_token

logger = logging.getLogger(__name__)

class eBayClient:
    def __init__(self):
        self.config = get_config()
        self.base_url = self.config.ebay_browse_api_url
        self.token_refreshed_at = None
        self.token_lifetime_seconds = 7200
        self.token_refresh_threshold = 5400
        self._refresh_token()

    def _should_refresh_token(self) -> bool:
        if self.token_refreshed_at is None:
            return True
        age_seconds = (datetime.now() - self.token_refreshed_at).seconds
        return age_seconds > self.token_refresh_threshold

    def _refresh_token(self):
        if not ensure_valid_token(verbose=False):
            raise ValueError("Unable to obtain valid eBay token")

        # Reload to get latest token
        from dotenv import load_dotenv
        import os
        load_dotenv(override=True)
        
        self.user_token = os.getenv('EBAY_USER_TOKEN')
        if not self.user_token:
            raise ValueError("EBAY_USER_TOKEN not found")

        self.headers = {
            'Authorization': f'Bearer {self.user_token}',
            'Content-Type': 'application/json',
            'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'
        }
        self.token_refreshed_at = datetime.now()
    
    def extract_item_id_from_url(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            if 'ebay.com' not in parsed.netloc:
                return None
            
            if '/itm/' in url:
                path_parts = parsed.path.split('/')
                for i, part in enumerate(path_parts):
                    if part == 'itm' and i + 1 < len(path_parts):
                        for j in range(i + 1, len(path_parts)):
                            potential_id = path_parts[j].split('?')[0]
                            if potential_id.isdigit():
                                return potential_id
            return None
        except Exception:
            return None

    def get_item_details(self, item_id: str) -> Optional[dict]:
        if self._should_refresh_token():
            self._refresh_token()

        url = f"{self.base_url}/item/get_item_by_legacy_id"
        params = {
            'legacy_item_id': item_id,
            'fieldgroups': 'PRODUCT,ADDITIONAL_SELLER_DETAILS'
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error fetching item: {e}")
            return None

    def fetch_listing_data(self, ebay_url: str) -> Optional[ListingData]:
        item_id = self.extract_item_id_from_url(ebay_url)
        if not item_id:
            return None
        
        item_data = self.get_item_details(item_id)
        if not item_data:
            return None
        
        try:
            # Basic extraction logic (simplified for shared library)
            title = item_data.get('title', '')
            price_info = item_data.get('price', {})
            price = float(price_info.get('value', 0)) if price_info else 0.0
            currency = price_info.get('currency', 'USD') if price_info else 'USD'
            
            # Images
            images = []
            if 'image' in item_data:
                img = item_data['image']
                if isinstance(img, dict) and 'imageUrl' in img:
                    images.append(img['imageUrl'])
            
            return ListingData(
                url=ebay_url,
                title=title,
                price=price,
                currency=currency,
                description=item_data.get('description', ''),
                condition=item_data.get('condition', 'Unknown'),
                brand=item_data.get('brand'),
                seller_name=item_data.get('seller', {}).get('username', 'Unknown'),
                seller_rating=None,
                images=images,
                item_id=item_id,
                category_id=item_data.get('categoryId', ''),
                listing_type='FIXED_PRICE'
            )
        except Exception as e:
            logger.error(f"Error parsing listing: {e}")
            return None
