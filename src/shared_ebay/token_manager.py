"""
Thin wrapper around the shared OAuth token manager.

The actual implementation now lives in https://github.com/sburl/eBayOauth and is
distributed as the ``shared_ebay`` package.  Keeping the heavy lifting there
lets multiple projects stay in sync on OAuth handling while this repo only
depends on the exported API surface.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def _import_shared_module():
    """
    Import ``shared_ebay.auth`` with a local fallback.

    When developers have the sibling `eBayOauth` repo checked out but not
    installed into their virtualenv yet, we add that source directory to
    ``sys.path`` so imports keep working out of the box.
    """
    try:
        from shared_ebay import auth as shared_auth  # type: ignore
        return shared_auth
    except ImportError:
        project_root = Path(__file__).resolve().parents[1]
        sibling_repo_src = project_root.parent / "eBayOauth" / "src"
        if sibling_repo_src.exists():
            sys.path.insert(0, str(sibling_repo_src))
            from shared_ebay import auth as shared_auth  # type: ignore
            return shared_auth
        raise


_shared_auth = _import_shared_module()

TokenManager = _shared_auth.TokenManager


def get_token_manager() -> TokenManager:
    """Expose the shared token manager instance."""
    return _shared_auth.get_token_manager()


def ensure_valid_token(verbose: bool = True) -> bool:
    """Proxy to the shared helper so existing call sites stay unchanged."""
    return _shared_auth.ensure_valid_token(verbose=verbose)


def get_valid_token() -> Optional[str]:
    """
    Convenience helper retained from the legacy module.

    Returns:
        Valid access token string or ``None`` if the refresh failed.
    """
    manager = get_token_manager()
    if manager.ensure_valid_token(verbose=False):
        return manager.get_current_token()
    return None

