"""
Data models for eBay listing data
"""
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ListingData:
    """Raw listing data from eBay"""
    url: str
    title: str
    price: float  # Total price (item + shipping)
    currency: str
    description: str
    condition: str
    brand: Optional[str]
    seller_name: str
    seller_rating: Optional[float]
    images: List[str]  # URLs to images
    item_id: str
    category_id: str
    listing_type: str  # auction, fixed_price, etc.
    item_price: float = 0.0  # Item price only (before shipping and tax)
    shipping_cost: float = 0.0  # Shipping cost
    shipping_type: str = 'Unknown'  # FREE, CALCULATED, FIXED, etc.
    sales_tax: float = 0.0  # Sales tax (calculated on item + shipping)
    import_charges: float = 0.0  # Import charges for international items
    ship_from_country: str = 'US'  # Country item ships from
    returns_accepted: bool = False  # Whether returns are accepted
    return_period: Optional[str] = None  # e.g., "30 days"
    return_policy_text: str = 'Unknown'  # Human-readable return policy
    accepts_offers: bool = False  # Whether the listing accepts best offers
