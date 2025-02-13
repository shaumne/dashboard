import requests
import base64
import json
from datetime import datetime, timedelta
import os
from pathlib import Path

class EbayTokenManager:
    def __init__(self):
        # Proje kök dizinini bul
        self.root_dir = Path(__file__).parent.parent.parent
        self.config_dir = self.root_dir / 'config'
        
        # Config dosyaları
        self.settings_file = self.config_dir / 'settings.json'
        self.token_file = self.config_dir / 'token_cache.json'
        
        # Config dizinini oluştur
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.load_credentials()
        
    def load_credentials(self):
        """Load credentials from settings.json"""
        try:
            with open(self.settings_file) as f:
                settings = json.load(f)
                self.client_id = settings['ebay_app_id']
                self.client_secret = settings['ebay_cert_id']
        except Exception as e:
            print(f"Error loading credentials: {str(e)}")
            raise

    def load_cached_token(self):
        """Load token from cache file if exists and valid"""
        try:
            if self.token_file.exists():
                with open(self.token_file, 'r') as f:
                    cache = json.load(f)
                    if datetime.fromisoformat(cache['expiry']) > datetime.now():
                        print("Using cached token")
                        return cache['token']
        except Exception as e:
            print(f"Error loading cached token: {str(e)}")
        return None

    def save_token_to_cache(self, token, expiry):
        """Save token and expiry to cache file"""
        try:
            cache = {
                'token': token,
                'expiry': expiry.isoformat()
            }
            with open(self.token_file, 'w') as f:
                json.dump(cache, f)
        except Exception as e:
            print(f"Error saving token to cache: {str(e)}")

    def get_access_token(self):
        """Get access token from cache or generate new one"""
        # Check cache first
        cached_token = self.load_cached_token()
        if cached_token:
            return cached_token

        print("Getting new access token...")
        
        try:
            # Create basic auth string
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {encoded_credentials}'
            }

            data = {
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope'
            }

            response = requests.post(
                'https://api.ebay.com/identity/v1/oauth2/token',
                headers=headers,
                data=data
            )
            
            response.raise_for_status()
            token_data = response.json()
            
            # Calculate expiry time (5 minutes before actual expiry)
            expiry = datetime.now() + timedelta(seconds=token_data['expires_in'] - 300)
            
            # Save to cache
            self.save_token_to_cache(token_data['access_token'], expiry)
            
            return token_data['access_token']
            
        except Exception as e:
            print(f"Error getting access token: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            raise

# Global instance
token_manager = EbayTokenManager() 