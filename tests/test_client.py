import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

APIHELPERS_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(APIHELPERS_SRC))

from shared_ebay import client as shared_client
from shared_ebay.client import (
    eBayClient,
    APIError,
    RateLimitError,
    ItemNotFoundError,
    UnauthorizedError
)


@patch('shared_ebay.client.ensure_valid_token')
@patch('shared_ebay.config.load_dotenv')
@patch('dotenv.load_dotenv')
class TesteBayClient(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.copy()
        os.environ["EBAY_APP_ID"] = "test-app-id"
        os.environ["EBAY_CLIENT_SECRET"] = "test-secret"
        os.environ["EBAY_USER_TOKEN"] = "test-token"

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._original_env)

    def test_client_initialization(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        client = eBayClient()

        self.assertIsNotNone(client.config)
        self.assertEqual(client.user_token, "test-token")
        mock_ensure.assert_called_once()

    def test_extract_item_id_from_url_standard(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        client = eBayClient()

        # Standard eBay URL
        item_id = client.extract_item_id_from_url("https://www.ebay.com/itm/123456789")
        self.assertEqual(item_id, "123456789")

    def test_extract_item_id_from_url_with_title(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        client = eBayClient()

        # URL with title
        item_id = client.extract_item_id_from_url("https://www.ebay.com/itm/product-title/123456789")
        self.assertEqual(item_id, "123456789")

    def test_extract_item_id_from_url_with_query_params(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        client = eBayClient()

        # URL with query parameters
        item_id = client.extract_item_id_from_url("https://www.ebay.com/itm/123456789?hash=item123")
        self.assertEqual(item_id, "123456789")

    def test_extract_item_id_invalid_url(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        client = eBayClient()

        # Invalid URLs
        self.assertIsNone(client.extract_item_id_from_url("https://google.com"))
        self.assertIsNone(client.extract_item_id_from_url("not-a-url"))
        self.assertIsNone(client.extract_item_id_from_url("https://www.ebay.com/other"))

    @patch('shared_ebay.client.requests.get')
    def test_get_item_details_success(self, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'title': 'Test Item', 'price': {'value': '10.00'}}
        mock_get.return_value = mock_response

        client = eBayClient()
        result = client.get_item_details("123456789")

        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Test Item')
        mock_get.assert_called_once()

    @patch('shared_ebay.client.requests.get')
    def test_get_item_details_404_not_found(self, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        client = eBayClient()

        with self.assertRaises(ItemNotFoundError):
            client.get_item_details("123456789")

    @patch('shared_ebay.client.requests.get')
    def test_get_item_details_401_unauthorized(self, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 401 response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_get.return_value = mock_response

        client = eBayClient()

        with self.assertRaises(UnauthorizedError):
            client.get_item_details("123456789")

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_429_rate_limit_with_retry(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 429 responses then success
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'title': 'Test Item'}

        mock_get.side_effect = [mock_response_429, mock_response_200]

        client = eBayClient()
        result = client.get_item_details("123456789")

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(2)  # First retry wait

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_429_rate_limit_exhausted(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 429 for all retries
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        client = eBayClient()

        with self.assertRaises(RateLimitError):
            client.get_item_details("123456789", max_retries=3)

        self.assertEqual(mock_get.call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)  # Sleep between retries

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_500_server_error_with_retry(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 500 error then success
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'title': 'Test Item'}

        mock_get.side_effect = [mock_response_500, mock_response_200]

        client = eBayClient()
        result = client.get_item_details("123456789")

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1)  # First retry wait

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_500_exhausted_retries(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 500 for all retries
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        client = eBayClient()

        with self.assertRaises(APIError) as context:
            client.get_item_details("123456789", max_retries=3)

        self.assertIn("Server error", str(context.exception))
        self.assertEqual(mock_get.call_count, 3)

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_network_error_with_retry(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        import requests

        # Mock network error then success
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'title': 'Test Item'}

        mock_get.side_effect = [
            requests.exceptions.ConnectionError("Network error"),
            mock_response_200
        ]

        client = eBayClient()
        result = client.get_item_details("123456789")

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(1)

    @patch('shared_ebay.client.requests.get')
    @patch('shared_ebay.client.time.sleep')
    def test_get_item_details_timeout_with_retry(self, mock_sleep, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        import requests

        # Mock timeout then success
        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'title': 'Test Item'}

        mock_get.side_effect = [
            requests.exceptions.Timeout("Timeout"),
            mock_response_200
        ]

        client = eBayClient()
        result = client.get_item_details("123456789")

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)

    @patch('shared_ebay.client.requests.get')
    def test_get_item_details_400_bad_request(self, mock_get, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock 400 response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_get.return_value = mock_response

        client = eBayClient()

        with self.assertRaises(APIError) as context:
            client.get_item_details("123456789")

        self.assertIn("400", str(context.exception))

    @patch.object(eBayClient, 'get_item_details')
    def test_fetch_listing_data_success(self, mock_get_details, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        # Mock item data
        mock_get_details.return_value = {
            'title': 'Test Item',
            'price': {'value': '25.50', 'currency': 'USD'},
            'description': 'Test description',
            'condition': 'New',
            'brand': 'TestBrand',
            'seller': {'username': 'testseller'},
            'image': {'imageUrl': 'https://example.com/image.jpg'},
            'categoryId': '12345'
        }

        client = eBayClient()
        listing = client.fetch_listing_data("https://www.ebay.com/itm/123456789")

        self.assertIsNotNone(listing)
        self.assertEqual(listing.title, 'Test Item')
        self.assertEqual(listing.price, 25.50)
        self.assertEqual(listing.currency, 'USD')
        self.assertEqual(listing.brand, 'TestBrand')

    @patch.object(eBayClient, 'get_item_details')
    def test_fetch_listing_data_item_not_found(self, mock_get_details, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True
        mock_get_details.side_effect = ItemNotFoundError("Item not found")

        client = eBayClient()

        with self.assertRaises(ItemNotFoundError):
            client.fetch_listing_data("https://www.ebay.com/itm/123456789")

    def test_fetch_listing_data_invalid_url(self, mock_dotenv_load, mock_config_load, mock_ensure):
        mock_ensure.return_value = True

        client = eBayClient()
        listing = client.fetch_listing_data("https://google.com")

        self.assertIsNone(listing)


if __name__ == '__main__':
    unittest.main()
