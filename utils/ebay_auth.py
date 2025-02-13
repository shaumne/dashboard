import requests
import base64
import time
from config.ebay_config import get_ebay_config
import logging

class EbayAuth:
    def __init__(self):
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger('ebay_auth')
        
        self.config = get_ebay_config()
        if not self.config:
            raise ValueError("eBay configuration not found")
            
        self.logger.debug(f"Config loaded: {self.config}")
            
        self.sandbox = True
        
        # OAuth endpoints
        if self.sandbox:
            self.auth_url = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
        else:
            self.auth_url = "https://api.ebay.com/identity/v1/oauth2/token"

    def get_token(self):
        """Get existing auth token"""
        try:
            if not self.config.get('auth_token'):
                self.logger.error("No auth token found in config")
                return None
                
            self.logger.debug(f"Using auth token from config: {self.config['auth_token'][:10]}...")
                
            return {
                'access_token': self.config['auth_token'],
                'token_type': 'Bearer'
            }
            
        except Exception as e:
            self.logger.error(f"Error getting token: {str(e)}")
            return None

    def get_application_token(self):
        """Get OAuth application token - fallback method"""
        try:
            credentials = base64.b64encode(
                f"{self.config['app_id']}:{self.config['cert_id']}".encode('utf-8')
            ).decode('utf-8')
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': f'Basic {credentials}'
            }
            
            body = {
                'grant_type': 'client_credentials',
                'scope': 'https://api.ebay.com/oauth/api_scope'
            }
            
            response = requests.post(self.auth_url, headers=headers, data=body)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            self.logger.error(f"Error getting application token: {str(e)}")
            return None 