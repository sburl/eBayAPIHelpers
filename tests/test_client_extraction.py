"""
Tests for enhanced listing data extraction in eBayClient

Tests shipping extraction, import charges, sales tax, return policies,
and additional images extraction.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from shared_ebay.client import eBayClient
from shared_ebay.models import ListingData
from shared_ebay import config as config_module


class TestShippingExtraction(unittest.TestCase):
    """Test shipping cost extraction from various eBay API formats"""

    def setUp(self):
        """Set up test environment"""
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_shipping_from_shipping_options(self, mock_get, mock_token):
        """Should extract shipping cost from shippingOptions field"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'shippingOptions': [{
                'shippingCost': {'value': 10.50, 'currency': 'USD'},
                'shippingCostType': 'CALCULATED'
            }],
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.shipping_cost, 10.50)
        self.assertEqual(listing.shipping_type, 'CALCULATED')

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_free_shipping_detection(self, mock_get, mock_token):
        """Should detect free shipping from shippingCostType"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'shippingOptions': [{
                'shippingCost': {'value': 0.0, 'currency': 'USD'},
                'shippingCostType': 'FREE'
            }],
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.shipping_cost, 0.0)
        self.assertEqual(listing.shipping_type, 'FREE')

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_free_shipping_from_text(self, mock_get, mock_token):
        """Should detect 'free shipping' in title/description"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item - Free Shipping!',
            'price': {'value': 100.0, 'currency': 'USD'},
            'description': 'Great item with free delivery',
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.shipping_cost, 0.0)
        self.assertEqual(listing.shipping_type, 'FREE')

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_shipping_from_additional_fields(self, mock_get, mock_token):
        """Should extract shipping from shippingCost field (fallback)"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'shippingCost': {'value': 15.75},
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.shipping_cost, 15.75)
        self.assertEqual(listing.shipping_type, 'CALCULATED')


class TestImportCharges(unittest.TestCase):
    """Test import charge extraction and estimation"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_extract_import_duty(self, mock_get, mock_token):
        """Should extract import charges from importDuty field"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'GB'},
            'importDuty': {'amount': {'value': 12.50}}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.import_charges, 12.50)
        self.assertEqual(listing.ship_from_country, 'GB')

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_estimate_import_charges_international(self, mock_get, mock_token):
        """Should estimate 10% import charges for international items without explicit charges"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'JP'},
            'shippingOptions': [{
                'shippingCost': {'value': 20.0, 'currency': 'USD'}
            }]
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        # Should be 10% of (item + shipping) = 10% of 120 = 12.0
        self.assertEqual(listing.import_charges, 12.0)

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_no_import_charges_domestic(self, mock_get, mock_token):
        """Should not add import charges for US domestic items"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.import_charges, 0.0)


class TestSalesTax(unittest.TestCase):
    """Test sales tax calculation"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_sales_tax_calculation_with_rate(self, mock_get, mock_token):
        """Should calculate sales tax when SALES_TAX_RATE is set"""
        os.environ['SALES_TAX_RATE'] = '0.10'  # 10% tax
        # Clear cached config to reload with new tax rate
        config_module._config.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        # Tax on $100 item at 10% = $10
        self.assertEqual(listing.sales_tax, 10.0)
        # Total price = item + tax = $110
        self.assertEqual(listing.price, 110.0)

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_sales_tax_default_zero(self, mock_get, mock_token):
        """Should default to 0.0 sales tax when SALES_TAX_RATE not set"""
        if 'SALES_TAX_RATE' in os.environ:
            del os.environ['SALES_TAX_RATE']
        # Clear cached config to reload with no tax rate
        config_module._config.clear()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'}
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(listing.sales_tax, 0.0)
        # Total price = item only when no tax
        self.assertEqual(listing.price, 100.0)


class TestPriceCalculation(unittest.TestCase):
    """Test total price calculation (item + shipping + import + tax)"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'
        os.environ['SALES_TAX_RATE'] = '0.08'  # 8% tax
        # Clear cached config to reload with new tax rate
        config_module._config.clear()

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_total_price_all_components(self, mock_get, mock_token):
        """Should calculate total price = item + shipping + import + tax"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'shippingOptions': [{
                'shippingCost': {'value': 10.0}
            }],
            'itemLocation': {'country': 'JP'},  # International = 10% import
            'importDuty': {'amount': {'value': 11.0}}  # Explicit import duty
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        # Subtotal = 100 (item) + 10 (ship) + 11 (import) = 121
        # Tax = 121 * 0.08 = 9.68
        # Total = 121 + 9.68 = 130.68
        self.assertEqual(listing.item_price, 100.0)
        self.assertEqual(listing.shipping_cost, 10.0)
        self.assertEqual(listing.import_charges, 11.0)
        self.assertAlmostEqual(listing.sales_tax, 9.68, places=2)
        self.assertAlmostEqual(listing.price, 130.68, places=2)


class TestReturnPolicyExtraction(unittest.TestCase):
    """Test return policy parsing"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_extract_return_policy_accepted(self, mock_get, mock_token):
        """Should extract return policy when returns accepted"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'},
            'returnTerms': {
                'returnsAccepted': True,
                'returnPeriod': {'value': 30, 'unit': 'days'}
            }
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertTrue(listing.returns_accepted)
        self.assertEqual(listing.return_period, '30 days')
        self.assertEqual(listing.return_policy_text, 'Returns accepted (30 days)')

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_extract_return_policy_not_accepted(self, mock_get, mock_token):
        """Should handle no returns accepted"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'},
            'returnTerms': {
                'returnsAccepted': False
            }
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertFalse(listing.returns_accepted)
        self.assertEqual(listing.return_policy_text, 'No returns')


class TestAdditionalImages(unittest.TestCase):
    """Test extraction of multiple images"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_extract_multiple_images(self, mock_get, mock_token):
        """Should extract main image and additional images"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'},
            'image': {'imageUrl': 'http://example.com/main.jpg'},
            'additionalImages': [
                {'imageUrl': 'http://example.com/img1.jpg'},
                {'imageUrl': 'http://example.com/img2.jpg'},
                {'imageUrl': 'http://example.com/img3.jpg'}
            ]
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        self.assertEqual(len(listing.images), 4)
        self.assertIn('http://example.com/main.jpg', listing.images)
        self.assertIn('http://example.com/img1.jpg', listing.images)

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_limit_images_to_24(self, mock_get, mock_token):
        """Should limit images to 24 maximum"""
        additional = [{'imageUrl': f'http://example.com/img{i}.jpg'} for i in range(30)]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'title': 'Test Item',
            'price': {'value': 100.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'},
            'image': {'imageUrl': 'http://example.com/main.jpg'},
            'additionalImages': additional
        }
        mock_get.return_value = mock_response

        client = eBayClient()
        listing = client.fetch_listing_data('https://ebay.com/itm/123456')

        # Should be limited to 24 images total
        self.assertEqual(len(listing.images), 24)


class TestItemGroupHandling(unittest.TestCase):
    """Test item group (variations) handling"""

    def setUp(self):
        os.environ['EBAY_APP_ID'] = 'test-app-id'
        os.environ['EBAY_CLIENT_SECRET'] = 'test-secret'
        os.environ['EBAY_USER_TOKEN'] = 'test-token'

    @patch('shared_ebay.client.ensure_valid_token', return_value=True)
    @patch('shared_ebay.client.requests.get')
    def test_detect_and_handle_item_group(self, mock_get, mock_token):
        """Should detect error 11006 and call _get_item_group_details"""
        # First call returns 400 with error 11006 (item group)
        mock_error_response = MagicMock()
        mock_error_response.status_code = 400
        mock_error_response.json.return_value = {
            'errors': [{'errorId': 11006, 'message': 'This is an item group'}]
        }

        # Second call (item group search) returns group data
        mock_group_response = MagicMock()
        mock_group_response.status_code = 200
        mock_group_response.json.return_value = {
            'itemSummaries': [{
                'legacyItemId': '999888777',
                'title': 'Item from group'
            }]
        }

        # Third call (get_item_details for specific item) returns item data
        mock_item_response = MagicMock()
        mock_item_response.status_code = 200
        mock_item_response.json.return_value = {
            'title': 'Specific Item',
            'price': {'value': 50.0, 'currency': 'USD'},
            'itemLocation': {'country': 'US'}
        }

        mock_get.side_effect = [mock_error_response, mock_group_response, mock_item_response]

        client = eBayClient()
        result = client.get_item_details('123456789')

        # Should have called the API 3 times: initial attempt, group search, item details
        self.assertEqual(mock_get.call_count, 3)
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Specific Item')


if __name__ == '__main__':
    unittest.main()
