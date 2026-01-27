# eBay API Helpers

A Python library for eBay OAuth authentication and the Browse API.

## Installation

```bash
pip install git+https://github.com/sburl/eBayAPIHelpers.git
```

## Configuration

Create a `.env` file with your eBay API credentials:

```env
EBAY_APP_ID=your_app_id
EBAY_CLIENT_SECRET=your_client_secret
```

### Getting OAuth Tokens

Run the token generation script to authenticate with eBay:

```bash
python -m shared_ebay.generate_token
```

This opens a browser for eBay authorization and saves your tokens to `.env`. Tokens refresh automatically.

## Usage

```python
from shared_ebay import eBayClient, ensure_valid_token

# Refresh token if needed
if ensure_valid_token():
    client = eBayClient()
    listing = client.fetch_listing_data("https://www.ebay.com/itm/123456789")
    print(listing.title, listing.price)
```

## Module Structure

```
src/shared_ebay/
├── auth.py            # Token validation and auto-refresh
├── client.py          # eBay Browse API client
├── config.py          # Configuration management
├── models.py          # Data models for listings
├── generate_token.py  # OAuth token generation script
└── token_manager.py   # Thin wrapper for external auth package
```

## Testing

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## License

MIT
