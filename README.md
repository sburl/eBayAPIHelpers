# eBay API Helpers

A Python library for eBay OAuth authentication and the Browse API.

**Part of the eBay project ecosystem** - Shared foundation for [alert](https://github.com/sburl/eBayAlert) (listing evaluator), [eBay2Parcel](https://github.com/sburl/eBay2Parcel) (order tracker), and future projects.

📚 **[See ECOSYSTEM.md](./ECOSYSTEM.md) for architecture overview and integration patterns**

## Installation

```bash
pip install git+https://github.com/sburl/eBayAPIHelpers.git
```

## Configuration

Create a `.env` file with your eBay API credentials:

```env
# Required eBay API credentials
EBAY_APP_ID=your_app_id
EBAY_CLIENT_SECRET=your_client_secret

# Optional: Sales tax rate for price calculations (default: 0.0 = no tax)
# Example: 0.08625 for 8.625% sales tax
SALES_TAX_RATE=0.0
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
    print(f"{listing.title}: ${listing.price}")
    print(f"  Item: ${listing.item_price}")
    print(f"  Shipping: ${listing.shipping_cost}")
    print(f"  Tax: ${listing.sales_tax}")
    print(f"  Total: ${listing.price}")
```

### Price Calculation

**IMPORTANT**: `ListingData.price` represents the **total out-the-door price** including:
- Item price (`item_price`)
- Shipping cost (`shipping_cost`)
- Import charges (`import_charges`) - for international items
- Sales tax (`sales_tax`) - calculated using `SALES_TAX_RATE` from config

**Formula**: `price = item_price + shipping_cost + import_charges + sales_tax`

If you need just the item price without additional costs, use `listing.item_price`.

### Data Extracted from Listings

The `fetch_listing_data` method extracts comprehensive data:

**Pricing:**
- `item_price` - Base item price
- `shipping_cost` - Shipping cost (extracted from multiple field formats)
- `import_charges` - Import duties for international items (10% estimate if not provided)
- `sales_tax` - Calculated sales tax (based on `SALES_TAX_RATE` config)
- `price` - **Total price** (sum of all above)

**Shipping & Returns:**
- `shipping_type` - "FREE", "CALCULATED", or "Unknown"
- `ship_from_country` - Origin country
- `returns_accepted` - Boolean
- `return_period` - e.g., "30 days"
- `return_policy_text` - Full return policy description

**Item Details:**
- `title`, `description`, `condition`, `brand`
- `images` - Up to 24 images
- `item_id`, `category_id`
- `listing_type` - "FIXED_PRICE", "AUCTION", etc.
- `accepts_offers` - Boolean (Best Offer available)

**Seller Info:**
- `seller_name`
- `seller_rating` - Feedback score

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
