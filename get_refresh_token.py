"""
Get eBay Refresh Token via OAuth Authorization Code Flow

This script implements the OAuth flow to get a refresh token.
Since eBay requires a configured RuName, this uses a manual code entry approach.
"""
import os
import sys
import base64
import requests
import webbrowser
from urllib.parse import urlencode
from dotenv import load_dotenv, set_key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
load_dotenv()


class eBayOAuthFlow:
    """Handle eBay OAuth authorization code flow"""
    
    def __init__(self):
        self.app_id = os.getenv('EBAY_APP_ID')
        self.client_secret = os.getenv('EBAY_CLIENT_SECRET')
        
        if not all([self.app_id, self.client_secret]):
            raise ValueError("EBAY_APP_ID and EBAY_CLIENT_SECRET must be set in .env")
        
        # Get RuName from env or use eBay's default
        # The RuName is configured in your eBay developer account
        self.ru_name = os.getenv('EBAY_RUNAME', '')
        
        self.auth_url = "https://auth.ebay.com/oauth2/authorize"
        self.token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        self.env_file = self._find_env_file()
    
    def _find_env_file(self) -> str:
        """Find the .env file"""
        current_dir = os.path.dirname(__file__)
        env_file = os.path.join(current_dir, '..', '.env')
        if os.path.exists(env_file):
            return env_file
        return '.env'
    
    def get_authorization_url(self) -> str:
        """Generate the OAuth authorization URL"""
        # Request all available scopes for full API access
        scopes = [
            'https://api.ebay.com/oauth/api_scope',
            'https://api.ebay.com/oauth/api_scope/sell.marketing.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.marketing',
            'https://api.ebay.com/oauth/api_scope/sell.inventory.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.inventory',
            'https://api.ebay.com/oauth/api_scope/sell.account.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.account',
            'https://api.ebay.com/oauth/api_scope/sell.fulfillment.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.fulfillment',
            'https://api.ebay.com/oauth/api_scope/sell.analytics.readonly',
            'https://api.ebay.com/oauth/api_scope/sell.finances',
            'https://api.ebay.com/oauth/api_scope/sell.payment.dispute',
            'https://api.ebay.com/oauth/api_scope/commerce.identity.readonly',
            'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription',
            'https://api.ebay.com/oauth/api_scope/commerce.notification.subscription.readonly',
        ]
        
        # If no RuName, we'll have user copy the code from error page
        redirect_uri = self.ru_name if self.ru_name else 'INVALID_WILL_GET_CODE_FROM_URL'
        
        params = {
            'client_id': self.app_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'scope': ' '.join(scopes),
            'state': 'ebay_alert_oauth'
        }
        
        return f"{self.auth_url}?{urlencode(params)}"
    
    def exchange_code_for_tokens(self, auth_code: str) -> dict:
        """Exchange authorization code for access and refresh tokens"""
        # Create Basic auth header
        credentials = f"{self.app_id}:{self.client_secret}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {b64_credentials}'
        }
        
        # Use the same redirect_uri as authorization
        redirect_uri = self.ru_name if self.ru_name else 'INVALID_WILL_GET_CODE_FROM_URL'
        
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': redirect_uri
        }
        
        try:
            response = requests.post(self.token_url, headers=headers, data=data, timeout=30)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error exchanging code for tokens: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            raise
    
    def save_tokens(self, token_data: dict):
        """Save tokens to .env file"""
        from urllib.parse import unquote
        
        if 'access_token' in token_data:
            # Ensure we save the raw, decoded token
            access_token = unquote(token_data['access_token'])
            set_key(self.env_file, 'EBAY_USER_TOKEN', access_token)
            print(f"✓ Access token saved")
            print(f"  Expires in: {token_data.get('expires_in', 'unknown')} seconds (~2 hours)")
        
        if 'refresh_token' in token_data:
            # Ensure we save the raw, decoded token
            refresh_token = unquote(token_data['refresh_token'])
            set_key(self.env_file, 'EBAY_REFRESH_TOKEN', refresh_token)
            refresh_expires = token_data.get('refresh_token_expires_in', 47304000)
            days = refresh_expires // 86400
            print(f"✓ Refresh token saved")
            print(f"  Expires in: {refresh_expires} seconds (~{days} days / ~{days//30} months)")
    
    def extract_code_from_text(self, text: str) -> str:
        """Extract authorization code from URL or raw string"""
        if not text:
            return ""
            
        auth_code = text
        
        # Check if input is a URL and extract code
        if 'code=' in text:
            try:
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(text)
                query_params = parse_qs(parsed.query)
                if 'code' in query_params:
                    auth_code = query_params['code'][0]
                else:
                    # Fallback if it's just the query string part
                    query_params = parse_qs(text)
                    if 'code' in query_params:
                        auth_code = query_params['code'][0]
            except Exception:
                pass
        
        # URL decode if needed
        from urllib.parse import unquote
        return unquote(auth_code)

    def run_oauth_flow(self):
        """Run the OAuth flow with manual code entry"""
        print("="*80)
        print("eBay OAuth Flow - Get Refresh Token")
        print("="*80)
        print()
        
        if not self.ru_name:
            print("⚠️  No RuName configured - using simplified flow")
            print()
            print("OPTION 1: Set up RuName (recommended for repeated use)")
            print("-" * 80)
            print("1. Go to: https://developer.ebay.com/my/keys")
            print("2. Click on your application")
            print("3. Under 'User Tokens' > 'Auth Accepted' settings")
            print("4. Create or find your RuName")
            print("5. Add to .env: EBAY_RUNAME=Your-App-Name-Your-App-I-Your_A-xxxxx")
            print()
            print("OPTION 2: Use simplified flow (works now)")
            print("-" * 80)
            print("Continue with manual code entry (see below)")
            print()
        
        print("How this works:")
        print("1. Browser opens to eBay authorization page")
        print("2. You sign in and grant permissions")
        print("3. eBay redirects (may show an error page - that's OK!)")
        print("4. Copy the 'code' from the URL in your browser")
        print("5. Paste it here to get your tokens")
        print()
        
        auth_url = self.get_authorization_url()
        
        print("Opening browser for authorization...")
        print()
        print("If browser doesn't open, go to this URL:")
        print(f"{auth_url}")
        print()
        
        webbrowser.open(auth_url)
        
        print("After you authorize:")
        print("- Look at the URL in your browser")
        print("- It will contain: ...?code=v%5E1.1%23i%5E1%23...")
        print("- Copy EVERYTHING after 'code=' (up to the next & or end of URL)")
        print()
        print("Example URL:")
        print("  Copy: v%5E1.1%23i%5E1%23p%5E3...")
        print()
        print("TIP: You can also paste the ENTIRE URL from the address bar.")
        print()
        
        auth_input = input("Paste the authorization code (or full URL) here: ").strip()
        
        if not auth_input:
            print("❌ No code provided")
            return False
            
        auth_code = self.extract_code_from_text(auth_input)
        
        print(f"\n✓ Code received: {auth_code[:30]}...")
        print()
        
        # Exchange code for tokens
        print("Exchanging authorization code for tokens...")
        try:
            token_data = self.exchange_code_for_tokens(auth_code)
            print("✓ Tokens received!")
            print()
            
            # Save tokens
            print("Saving tokens to .env file...")
            self.save_tokens(token_data)
            print()
            
            print("="*80)
            print("SUCCESS!")
            print("="*80)
            print()
            print("Your tokens have been saved to .env")
            print()
            print("✓ Access token (valid for 2 hours)")
            print("✓ Refresh token (valid for ~18 months)")
            print()
            print("You can now run:")
            print("  python utils/export_watched_items.py")
            print()
            print("The system will automatically refresh your access token when needed.")
            print()
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to get tokens: {e}")
            print()
            print("Common issues:")
            print("- Code expired (they expire quickly, try again)")
            print("- Code was already used (get a new one)")
            print("- Wrong redirect_uri (check RuName configuration)")
            return False


def main():
    """Main entry point"""
    try:
        flow = eBayOAuthFlow()
        success = flow.run_oauth_flow()
        return 0 if success else 1
        
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        print()
        print("Make sure your .env file has:")
        print("  EBAY_APP_ID=your_app_id")
        print("  EBAY_CLIENT_SECRET=your_client_secret")
        return 1
        
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        return 1
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
