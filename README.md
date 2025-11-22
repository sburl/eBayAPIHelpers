# shared_ebay

A Python library for eBay OAuth authentication and the Browse API.

## Installation

```bash
pip install git+https://github.com/sburl/eBayOauth.git
```

## Configuration

Create a `.env` file with your eBay credentials:

```env
EBAY_APP_ID=your_app_id
EBAY_CLIENT_SECRET=your_client_secret
EBAY_DEV_ID=your_dev_id
EBAY_USER_TOKEN=your_oauth_token
EBAY_REFRESH_TOKEN=your_refresh_token
```

## Usage

```python
from shared_ebay import eBayClient, ensure_valid_token

# Refresh token if needed
if ensure_valid_token():
    client = eBayClient()
    listing = client.fetch_listing_data("https://www.ebay.com/itm/123456789")
    print(listing.title, listing.price)
```

## License

MIT
