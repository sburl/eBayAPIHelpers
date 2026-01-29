"""
eBay Browse API Client

Provides high-level interface to eBay's Browse API with automatic OAuth token management.
Supports fetching listing data, parsing eBay URLs, and handling token refresh.
Includes retry logic with exponential backoff for transient errors.

BREAKING CHANGE (v2.0):
    Methods now RAISE EXCEPTIONS instead of returning None on errors.
    This provides better error handling and debugging, but requires updating
    downstream code that previously checked for None returns.

    Old behavior (v1.x):
        listing = client.fetch_listing_data(url)
        if listing is None:
            # Handle error

    New behavior (v2.0+):
        try:
            listing = client.fetch_listing_data(url)
        except ItemNotFoundError:
            # Item doesn't exist
        except UnauthorizedError:
            # Auth failed
        except RateLimitError:
            # Rate limit exceeded
        except APIError:
            # Other API errors

    Exceptions raised:
    - ItemNotFoundError: Item not found (404)
    - UnauthorizedError: Authentication failed (401)
    - RateLimitError: Rate limit exceeded (429)
    - APIError: Other API errors (4xx, 5xx, network errors)

Usage:
    from shared_ebay import eBayClient, ItemNotFoundError

    client = eBayClient()
    try:
        listing = client.fetch_listing_data("https://www.ebay.com/itm/123456789")
        print(f"{listing.title}: ${listing.price}")
    except ItemNotFoundError:
        print("Item not found")
    except APIError as e:
        print(f"API error: {e}")
"""
import requests
import logging
import time
import re
from typing import Optional, Tuple
from urllib.parse import urlparse
from datetime import datetime

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
                    elif response.status_code == 400:
                        # Check if this is an item group (error 11006)
                        try:
                            error_data = response.json()
                            errors = error_data.get('errors', [])
                            for error in errors:
                                if error.get('errorId') == 11006:
                                    # This is an item group - fetch group details instead
                                    logger.info(f"Item {item_id} is an item group, fetching group details...")
                                    return self._get_item_group_details(item_id, self.headers)
                        except (ValueError, KeyError):
                            pass  # Can't parse error, treat as generic 400

                        # Other 400 errors
                        logger.error(f"Client error 400 for item {item_id}: {response.text}")
                        raise APIError(f"API error 400: {response.text[:100]}")
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

    def _get_item_group_details(self, item_group_id: str, headers: dict) -> Optional[dict]:
        """
        Fetch item group details from eBay API.

        When an item ID is actually an item group (variations), this fetches the group details.

        Args:
            item_group_id: The item group ID
            headers: Request headers with auth token

        Returns:
            Item group data dict if successful, None otherwise
        """
        try:
            url = f"{self.base_url}/item_summary/search"
            params = {
                'item_group_id': item_group_id,
                'fieldgroups': 'MATCHING_ITEMS,FULL'
            }

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()

                # Extract the first item from the group
                if 'itemSummaries' in data and len(data['itemSummaries']) > 0:
                    # Get the first item from the group
                    first_item = data['itemSummaries'][0]

                    # Fetch full details for this specific item
                    if 'legacyItemId' in first_item:
                        item_id = first_item['legacyItemId']
                        logger.info(f"Item group {item_group_id} contains item {item_id}, fetching details...")
                        return self.get_item_details(item_id)

                    return first_item
                else:
                    logger.warning(f"No items found in item group {item_group_id}")
                    return None
            else:
                logger.warning(f"Failed to fetch item group {item_group_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error fetching item group {item_group_id}: {e}")
            return None

    def _extract_shipping_from_additional_fields(self, item_data: dict) -> float:
        """
        Extract shipping cost from additional fields when shippingOptions is not available.

        Uses multiple strategies:
        1. Check common shipping-related fields
        2. Parse shipping cost from text fields using regex

        Args:
            item_data: Raw eBay API response data

        Returns:
            Shipping cost as float, 0.0 if not found
        """
        shipping_cost = 0.0

        # Check for shipping information in various fields
        potential_fields = [
            'shippingCost',
            'shipping',
            'delivery',
            'shippingInfo',
            'shippingDetails'
        ]

        for field in potential_fields:
            if field in item_data:
                field_data = item_data[field]
                if isinstance(field_data, dict):
                    # Look for cost/value fields
                    for cost_field in ['cost', 'value', 'amount', 'price']:
                        if cost_field in field_data:
                            try:
                                cost_value = field_data[cost_field]
                                if isinstance(cost_value, (int, float)):
                                    shipping_cost = float(cost_value)
                                    break
                                elif isinstance(cost_value, dict) and 'value' in cost_value:
                                    shipping_cost = float(cost_value['value'])
                                    break
                            except (ValueError, TypeError):
                                continue
                    if shipping_cost > 0:
                        break

        # If still no shipping cost found, try to parse from text fields
        if shipping_cost == 0.0:
            text_fields = ['title', 'description', 'subtitle']
            for field in text_fields:
                if field in item_data:
                    text = str(item_data[field]).lower()
                    # Look for shipping cost patterns like "$42.65", "US $42.65", etc.
                    patterns = [
                        r'\$(\d+\.?\d*)\s*(?:shipping|ship)',
                        r'shipping[:\s]*\$(\d+\.?\d*)',
                        r'us\s*\$(\d+\.?\d*)\s*(?:shipping|ship)',
                        r'ground\s*advantage[:\s]*\$(\d+\.?\d*)'
                    ]

                    for pattern in patterns:
                        match = re.search(pattern, text)
                        if match:
                            try:
                                shipping_cost = float(match.group(1))
                                break
                            except (ValueError, IndexError):
                                continue
                    if shipping_cost > 0:
                        break

        return shipping_cost

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

        logger.debug(f"Extracted item ID: {item_id}")

        try:
            item_data = self.get_item_details(item_id)
            if not item_data:
                return None

            # Extract basic info
            title = item_data.get('title', '')

            # Extract price
            price_info = item_data.get('price', {})
            item_price = 0.0
            currency = 'USD'
            if price_info:
                item_price = float(price_info.get('value', 0))
                currency = price_info.get('currency', 'USD')

            # Extract shipping cost
            shipping_cost = 0.0
            shipping_type = 'Unknown'

            # Debug: Log shipping options availability
            if 'shippingOptions' in item_data:
                logger.debug(f"Found {len(item_data['shippingOptions'])} shipping options")
            else:
                logger.debug("No shippingOptions in response")

            if 'shippingOptions' in item_data and len(item_data['shippingOptions']) > 0:
                # Get the first (usually cheapest/default) shipping option
                first_shipping = item_data['shippingOptions'][0]
                logger.debug(f"First shipping option: {first_shipping}")

                if 'shippingCost' in first_shipping:
                    shipping_cost_info = first_shipping['shippingCost']
                    shipping_cost = float(shipping_cost_info.get('value', 0))
                shipping_type = first_shipping.get('shippingCostType', 'Unknown')

                # Check if shipping is free
                if shipping_type == 'FREE' or shipping_cost == 0:
                    shipping_type = 'FREE'
                    shipping_cost = 0.0
            else:
                # Fallback: Check for shipping information in other fields
                logger.debug("No shipping options found, checking for shipping indicators...")

                # Check if item has free shipping indicators
                item_text = f"{item_data.get('title', '')} {item_data.get('description', '')}".lower()
                if 'free shipping' in item_text or 'free delivery' in item_text:
                    shipping_type = 'FREE'
                    shipping_cost = 0.0
                    logger.debug("Detected free shipping from text")
                else:
                    # Try to extract shipping cost from additional fields
                    shipping_cost = self._extract_shipping_from_additional_fields(item_data)
                    if shipping_cost > 0:
                        shipping_type = 'CALCULATED'
                        logger.debug(f"Extracted shipping cost from additional fields: ${shipping_cost}")
                    else:
                        # Default to unknown shipping cost
                        shipping_type = 'Unknown'
                        shipping_cost = 0.0
                        logger.debug("No shipping info found, defaulting to unknown")

            # Extract ship from location/country
            ship_from_country = 'US'
            if 'itemLocation' in item_data:
                location_data = item_data['itemLocation']
                if isinstance(location_data, dict):
                    ship_from_country = location_data.get('country', 'US')

            # Extract or calculate import charges
            import_charges = 0.0
            if 'importDuty' in item_data:
                duty_info = item_data['importDuty']
                if isinstance(duty_info, dict) and 'amount' in duty_info:
                    import_charges = float(duty_info['amount'].get('value', 0))

            # If no import charges provided but item is from outside US, estimate 10%
            if import_charges == 0.0 and ship_from_country != 'US':
                import_charges = (item_price + shipping_cost) * 0.10

            # Calculate subtotal (item + shipping + import charges)
            subtotal = item_price + shipping_cost + import_charges

            # Calculate sales tax on subtotal (uses config, defaults to 0.0)
            sales_tax = subtotal * self.config.sales_tax_rate

            # Calculate total price (item + shipping + import charges + tax)
            price = subtotal + sales_tax

            # Extract condition
            condition = item_data.get('condition', 'Unknown')
            if isinstance(condition, dict):
                condition = condition.get('conditionDisplayName', 'Unknown')

            # Extract brand from various locations
            brand = None
            if 'brand' in item_data:
                brand = item_data['brand']

            # Try to find brand in item specifics
            if not brand and 'localizedAspects' in item_data:
                for aspect in item_data['localizedAspects']:
                    if aspect.get('name', '').lower() == 'brand':
                        brand = aspect.get('value', '')
                        break

            # Extract description
            description = item_data.get('description', '')
            if not description and 'shortDescription' in item_data:
                description = item_data['shortDescription']

            # Extract images
            images = []
            if 'image' in item_data:
                image_data = item_data['image']
                if isinstance(image_data, dict) and 'imageUrl' in image_data:
                    images.append(image_data['imageUrl'])

            if 'additionalImages' in item_data:
                for img in item_data['additionalImages']:
                    if isinstance(img, dict) and 'imageUrl' in img:
                        images.append(img['imageUrl'])

            # Limit images to 24 (reasonable default)
            images = images[:24]

            # Extract seller info
            seller_name = 'Unknown'
            seller_rating = None
            if 'seller' in item_data:
                seller_info = item_data['seller']
                seller_name = seller_info.get('username', 'Unknown')
                if 'feedbackScore' in seller_info:
                    seller_rating = float(seller_info['feedbackScore'])

            # Extract category
            category_id = ''
            if 'categoryPath' in item_data:
                category_id = item_data['categoryPath']
            elif 'categoryId' in item_data:
                category_id = item_data['categoryId']

            # Listing type and offers
            buying_options = item_data.get('buyingOptions', ['FIXED_PRICE'])
            listing_type = buying_options[0] if buying_options else 'FIXED_PRICE'
            accepts_offers = 'BEST_OFFER' in buying_options

            # Extract return policy
            returns_accepted = False
            return_period = None
            return_policy_text = 'Unknown'

            if 'returnTerms' in item_data:
                return_terms = item_data['returnTerms']
                returns_accepted = return_terms.get('returnsAccepted', False)

                if returns_accepted:
                    # Extract return period (e.g., "30 days")
                    if 'returnPeriod' in return_terms:
                        period_info = return_terms['returnPeriod']
                        value = period_info.get('value', '')
                        unit = period_info.get('unit', '')
                        return_period = f"{value} {unit}" if value and unit else None

                    return_policy_text = f"Returns accepted{f' ({return_period})' if return_period else ''}"
                else:
                    return_policy_text = "No returns"

            logger.info(f"Successfully parsed listing: {title[:50]}...")
            logger.debug(f"  Item Price: ${item_price:.2f}")
            logger.debug(f"  Shipping: {f'${shipping_cost:.2f}' if shipping_cost > 0 else 'FREE'}")
            if import_charges > 0:
                logger.debug(f"  Import Charges: ${import_charges:.2f} (from {ship_from_country})")
            logger.debug(f"  Subtotal: ${subtotal:.2f}")
            if sales_tax > 0:
                logger.debug(f"  Sales Tax: ${sales_tax:.2f}")
            logger.debug(f"  Total Price: ${price:.2f} {currency}")
            logger.debug(f"  Ships From: {ship_from_country}")
            logger.debug(f"  Brand: {brand or 'Unknown'}")
            logger.debug(f"  Returns: {return_policy_text}")
            logger.debug(f"  Images: {len(images)}")

            return ListingData(
                url=ebay_url,
                title=title,
                price=price,
                currency=currency,
                description=description,
                condition=condition,
                brand=brand,
                seller_name=seller_name,
                seller_rating=seller_rating,
                images=images,
                item_id=item_id,
                category_id=str(category_id),
                listing_type=listing_type,
                item_price=item_price,
                shipping_cost=shipping_cost,
                shipping_type=shipping_type,
                sales_tax=sales_tax,
                import_charges=import_charges,
                ship_from_country=ship_from_country,
                returns_accepted=returns_accepted,
                return_period=return_period,
                return_policy_text=return_policy_text,
                accepts_offers=accepts_offers
            )

        except (RateLimitError, ItemNotFoundError, UnauthorizedError, APIError):
            # Re-raise API errors for caller to handle
            raise
        except Exception as e:
            logger.error(f"Error parsing listing {item_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
