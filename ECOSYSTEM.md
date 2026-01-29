# eBay Project Ecosystem

This document explains how APIHelpers fits into the broader eBay project ecosystem.

## Overview

```
┌─────────────────────────────────────────────────────────┐
│                    eBay Projects                        │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │   alert     │  │ eBay2Parcel  │  │  Future...   │  │
│  │             │  │              │  │              │  │
│  │ Evaluates   │  │ Auto-track   │  │    ...       │  │
│  │ listings    │  │ purchases    │  │              │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                  │          │
│         └────────┬────────┴──────────────────┘          │
│                  │                                      │
│                  ▼                                      │
│       ┌──────────────────────┐                         │
│       │    APIHelpers        │                         │
│       │  (shared_ebay)       │                         │
│       │                      │                         │
│       │  • Token Management  │                         │
│       │  • Browse API        │                         │
│       │  • Trading API Auth  │                         │
│       │  • ListingData Model │                         │
│       └──────────────────────┘                         │
│                  │                                      │
│                  ▼                                      │
│       ┌──────────────────────┐                         │
│       │      eBay APIs       │                         │
│       │                      │                         │
│       │  • Browse API        │                         │
│       │  • Trading API       │                         │
│       │  • Finding API       │                         │
│       └──────────────────────┘                         │
└─────────────────────────────────────────────────────────┘
```

## Projects

### APIHelpers (This Repository)
**Purpose**: Shared eBay API integration library

**What it provides**:
- OAuth token management (generation, refresh, validation)
- Browse API client (fetch listings, parse data)
- Trading API authentication (used by eBay2Parcel)
- ListingData model (comprehensive listing structure)
- Exception-based error handling
- HTTP retry logic with exponential backoff

**Used by**: alert, eBay2Parcel, future projects

**Version**: Pinned by dependent projects to specific commits

---

### alert
**Repository**: https://github.com/sburl/eBayAlert

**Purpose**: AI-powered eBay listing evaluator

**What it does**:
- Evaluates eBay listings for fit, value, quality, brand
- Uses reference garment measurements for size matching
- AI-powered assessment with detailed recommendations
- Web UI for viewing results

**Uses from APIHelpers**:
- `eBayClient` (Browse API integration)
- `ListingData` model
- Token management (`ensure_valid_token`, `get_token_manager`)

**Extensions**:
- `add_item_to_cart()` - Watchlist UI feature
- Shipping ZIP header - Location-specific shipping costs
- Exception → None wrapper - Backward compatibility

**Dependency**: `shared_ebay@4091854` (pinned)

---

### eBay2Parcel
**Repository**: https://github.com/sburl/eBay2Parcel

**Purpose**: Lightweight pipe between eBay purchases and Parcel tracking

**What it does**:
- Fetches your eBay orders (Trading API)
- Automatically creates shipment tracking in Parcel app
- Runs as cron job for hands-free tracking

**Uses from APIHelpers**:
- Token management only (`ensure_valid_token`, `get_token_manager`)
- Trading API authentication

**Does NOT use**:
- Browse API client (uses Trading API instead via ebaysdk)
- ListingData model (only cares about orders)
- Enhanced extraction features (not relevant)

**Dependency**: `shared_ebay@4091854` (pinned)

---

## Architecture Principles

### Single Source of Truth
- **eBay API integration** → APIHelpers
- **Token management** → APIHelpers
- **Data models** → APIHelpers
- **Business logic** → Individual projects

### Shared vs Project-Specific

**Add to APIHelpers if**:
✅ General-purpose eBay API feature
✅ Data extraction improvement
✅ Error handling enhancement
✅ Used by multiple projects (or could be)

**Keep in project if**:
✅ UI-specific feature
✅ Business logic (scoring, routing, etc.)
✅ Project workflow
✅ Project-specific configuration

### Version Management

**Pinning Strategy**:
- Projects pin to specific APIHelpers commits
- Prevents surprise breaking changes
- Update deliberately after testing

**Update Process**:
1. APIHelpers makes improvements → main branch
2. Project tests with new version
3. If compatible → update pin
4. If breaking → update project code first

**Example**:
```python
# requirements.txt
shared_ebay @ git+https://github.com/sburl/eBayAPIHelpers.git@4091854
```

---

## Integration Patterns

### Pattern 1: Full Browse API Integration (alert)
```python
from shared_ebay.client import eBayClient
from shared_ebay.models import ListingData

client = eBayClient()
listing = client.fetch_listing_data(url)
# Gets: shipping, returns, images, price components, etc.
```

**Use when**: Need comprehensive listing data extraction

---

### Pattern 2: Auth Only (eBay2Parcel)
```python
from shared_ebay.auth import ensure_valid_token, get_token_manager

ensure_valid_token()  # Refresh if needed
token = get_token_manager().get_current_token()
# Use token with ebaysdk or other libraries
```

**Use when**: Only need OAuth, using different API (Trading, Finding)

---

### Pattern 3: Extension (alert)
```python
from shared_ebay.client import eBayClient as BaseeBayClient

class eBayClient(BaseeBayClient):
    def __init__(self):
        super().__init__()
        # Add project-specific features

    def project_specific_feature(self):
        # Custom functionality
```

**Use when**: Need to add project-specific extensions

---

## Testing Strategy

### APIHelpers Tests
- **65 tests** covering core functionality
- Token management, client methods, extraction
- Exception handling, retry logic
- Run on every APIHelpers commit

### Project Integration Tests
- Verify imports work
- Test compatibility with APIHelpers
- Validate behavioral contracts
- Run before updating APIHelpers pin

### Contract Tests (alert example)
- Price calculation semantics
- Exception handling behavior
- Required field availability
- Catch breaking changes early

---

## Benefits of Consolidation

### Before (Duplication)
```
alert:        601 lines eBayClient + 25 lines ListingData
eBay2Parcel:  Token management duplicated
APIHelpers:   Incomplete extraction
```
**Total**: ~900 lines of duplicated/partial code

### After (Consolidation)
```
alert:        108 lines wrapper (extensions only)
eBay2Parcel:  560 lines (no duplication)
APIHelpers:   Comprehensive implementation
```
**Total**: ~518 lines eliminated ✅

### Advantages
1. **Single source of truth** - Bug fixes in one place
2. **Automatic improvements** - Projects get enhancements for free
3. **Consistent behavior** - Same extraction logic everywhere
4. **Less maintenance** - One codebase to maintain
5. **Better testing** - Comprehensive test suite shared

---

## Adding a New Project

### 1. Install APIHelpers
```bash
# requirements.txt
shared_ebay @ git+https://github.com/sburl/eBayAPIHelpers.git@4091854
```

### 2. Import what you need
```python
# For Browse API (listings):
from shared_ebay.client import eBayClient
from shared_ebay.models import ListingData

# For auth only:
from shared_ebay.auth import ensure_valid_token, get_token_manager
```

### 3. Set up credentials
```bash
# .env
EBAY_APP_ID=your_app_id
EBAY_CLIENT_SECRET=your_secret
EBAY_DEV_ID=your_dev_id
```

### 4. Add tests
- Import verification
- Basic functionality
- Contract tests if needed

### 5. Pin the version
Update requirements.txt to specific commit after testing

---

## Migration Guide

Migrating an existing project to use APIHelpers:

### Step 1: Identify Usage
- What eBay APIs do you use?
- What data do you need?
- What's custom vs generic?

### Step 2: Install & Import
```python
# Replace local implementation
from shared_ebay.client import eBayClient  # instead of local client
from shared_ebay.models import ListingData  # instead of local model
```

### Step 3: Handle Differences
- APIHelpers uses exceptions (not None returns)
- Add wrapper if needed for backward compatibility
- Keep project-specific features in local wrapper

### Step 4: Test Thoroughly
- Run existing tests
- Add integration tests
- Verify no regressions

### Step 5: Document
- What you use from APIHelpers
- What's project-specific
- Why certain features are local

---

## Future Additions

Potential features to add to APIHelpers:

**Browse API**:
- Search/filter listings
- Get seller information
- Fetch categories

**Trading API**:
- Complete Trading API client
- Order management
- Seller tools

**Finding API**:
- Product research
- Market analysis
- Trend identification

**Utilities**:
- Rate limiting
- Caching
- Batch operations

---

## Contributing

### To APIHelpers:
1. Create feature branch
2. Add tests (65+ tests expected)
3. Update README if API changes
4. Create PR with clear description
5. Tag affected projects in PR

### To Projects:
1. Check if feature belongs in APIHelpers
2. If general-purpose → contribute to APIHelpers
3. If project-specific → implement locally
4. Document in project README

---

## Summary

**APIHelpers** = Foundation (auth + API + models)
**alert** = Evaluation engine (uses Browse API)
**eBay2Parcel** = Order tracker (uses auth only)
**Future projects** = Get foundation for free

**Result**: Less code, better quality, faster development
