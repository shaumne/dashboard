# eBay API Configuration
EBAY_APP_ID = "your_app_id"
EBAY_CERT_ID = "your_cert_id"
EBAY_DEV_ID = "your_dev_id"
EBAY_AUTH_TOKEN = "your_auth_token"

# eBay API Endpoints
EBAY_TRADING_API_URL = "https://api.ebay.com/ws/api.dll"
EBAY_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"

# eBay Site ID for UK
EBAY_SITE_ID = "3"  # UK site ID 

import json
import os

def get_ebay_config():
    """Get eBay production configuration from settings"""
    settings_file = 'config/settings.json'
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            settings = json.load(f)
            return {
                'app_id': settings.get('ebay_app_id', ''),
                'cert_id': settings.get('ebay_cert_id', ''),
                'dev_id': settings.get('ebay_dev_id', ''),
                'auth_token': settings.get('ebay_auth_token', ''),
                'site_id': "3",  # UK site ID
                'trading_api_url': "https://api.ebay.com/ws/api.dll",  # Production URL
                'finding_api_url': "https://svcs.ebay.com/services/search/FindingService/v1",
                'domain': 'api.ebay.com',  # Production domain
                'warnings': True,
                'timeout': 20,
                'debug': False,
                'siteid': 3,  # UK siteid
                'config_file': None
            }
    return None

# Settings file structure example:
"""
{
    "ebay_app_id": "YOUR-PRODUCTION-APP-ID",
    "ebay_cert_id": "YOUR-PRODUCTION-CERT-ID",
    "ebay_dev_id": "YOUR-PRODUCTION-DEV-ID",
    "ebay_auth_token": "YOUR-PRODUCTION-AUTH-TOKEN"
}
""" 