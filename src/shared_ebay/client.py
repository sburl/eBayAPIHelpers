"""
eBay Browse API Client

Provides high-level interface to eBay's Browse API with automatic OAuth token management.
Supports fetching listing data, parsing eBay URLs, and handling token refresh.
Includes retry logic with exponential backoff for transient errors.

Usage:
    from shared_ebay import eBayClient

    client = eBayClient()
    listing = client.fetch_listing_data("https://www.ebay.com/itm/123456789")
    print(f"{listing.title}: ${listing.price}")
"""
import requests
import logging
import time
from typing import Optional, Tuple
from urllib.parse import urlparse
from datetime import datetime
from enum import Enum

from .config import get_config
from .models import ListingData
from .auth import ensure_valid_token

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors"""
    pass


class RateLimitError(APIError):
    """Raised when API rate limit is exceeded (429)"""
    pass


class ItemNotFoundError(APIError):
    """Raised when item is not found (404)"""
    pass


class UnauthorizedError(APIError):
    """Raised when authentication fails (401)"""
    pass

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

    def get_item_details(self, item_id: str, max_retries: int = 3) -> Optional[dict]:
        """
        Fetch item details from eBay Browse API with retry logic.

        Args:
            item_id: eBay item ID
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            Item data dict if successful, None otherwise

        Raises:
            RateLimitError: If rate limit is exceeded (429)
            ItemNotFoundError: If item is not found (404)
            UnauthorizedError: If authentication fails (401)
            APIError: For other API errors

        Retries with exponential backoff on transient errors (5xx, network errors).
        Does not retry on client errors (4xx) except 429 rate limiting.
        """
        if self._should_refresh_token():
            self._refresh_token()

        url = f"{self.base_url}/item/get_item_by_legacy_id"
        params = {
            'legacy_item_id': item_id,
            'fieldgroups': 'PRODUCT,ADDITIONAL_SELLER_DETAILS'
        }

        last_exception = None
        for attempt in range(max_retries):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=30)

                # Success
                if response.status_code == 200:
                    logger.debug(f"Successfully fetched item {item_id}")
                    return response.json()

                # Client errors - don't retry (except 429)
                if 400 <= response.status_code < 500:
                    if response.status_code == 401:
                        logger.error(f"Unauthorized (401) for item {item_id}")
                        raise UnauthorizedError(f"Authentication failed for item {item_id}")
                    elif response.status_code == 404:
                        logger.warning(f"Item not found (404): {item_id}")
                        raise ItemNotFoundError(f"Item {item_id} not found")
                    elif response.status_code == 429:
                        logger.warning(f"Rate limit exceeded (429) for item {item_id}, attempt {attempt + 1}/{max_retries}")
                        if attempt < max_retries - 1:
                            # Exponential backoff for rate limiting
                            wait_time = (2 ** attempt) * 2  # 2, 4, 8 seconds
                            time.sleep(wait_time)
                            continue
                        raise RateLimitError(f"Rate limit exceeded for item {item_id}")
                    else:
                        logger.error(f"Client error {response.status_code} for item {item_id}: {response.text}")
                        raise APIError(f"API error {response.status_code}: {response.text[:100]}")

                # Server errors (5xx) - retry with exponential backoff
                if response.status_code >= 500:
                    logger.warning(f"Server error {response.status_code} for item {item_id}, attempt {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt)  # 1, 2, 4 seconds
                        time.sleep(wait_time)
                        continue
                    raise APIError(f"Server error {response.status_code} after {max_retries} attempts")

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                # Network errors - retry with exponential backoff
                logger.warning(f"Network error for item {item_id}, attempt {attempt + 1}/{max_retries}: {e}")
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt)  # 1, 2, 4 seconds
                    time.sleep(wait_time)
                    continue
                raise APIError(f"Network error after {max_retries} attempts: {str(e)}")

            except (RateLimitError, ItemNotFoundError, UnauthorizedError, APIError):
                # Re-raise our custom exceptions
                raise

            except Exception as e:
                # Unexpected errors - log and return None
                logger.error(f"Unexpected error fetching item {item_id}: {e}")
                raise APIError(f"Unexpected error: {str(e)}")

        # Should not reach here, but just in case
        return None

    def fetch_listing_data(self, ebay_url: str) -> Optional[ListingData]:
        """
        Fetch and parse listing data from an eBay URL.

        Args:
            ebay_url: Full eBay item URL

        Returns:
            ListingData object if successful, None if URL is invalid or parsing fails

        Raises:
            RateLimitError: If rate limit is exceeded
            ItemNotFoundError: If item is not found
            UnauthorizedError: If authentication fails
            APIError: For other API errors
        """
        item_id = self.extract_item_id_from_url(ebay_url)
        if not item_id:
            logger.warning(f"Could not extract item ID from URL: {ebay_url}")
            return None

        try:
            item_data = self.get_item_details(item_id)
            if not item_data:
                return None

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
        except (RateLimitError, ItemNotFoundError, UnauthorizedError, APIError):
            # Re-raise API errors for caller to handle
            raise
        except Exception as e:
            logger.error(f"Error parsing listing {item_id}: {e}")
            return None
