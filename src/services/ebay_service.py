import requests
import base64
from pathlib import Path
from ..api.ebay_token_manager import token_manager
from typing import Optional, Dict, Any, List
import urllib.parse
from ebaysdk.finding import Connection as Finding
from ebaysdk.shopping import Connection as Shopping
import json
import logging
from ebaysdk.trading import Connection as Trading

class EbayService:
    def __init__(self):
        try:
            # Settings'den ayarları oku
            settings_file = 'config/settings.json'
            with open(settings_file, 'r') as f:
                settings = json.load(f)
            
            self.app_id = settings.get('ebay_app_id')
            print(f"Initializing eBay API with app_id: {self.app_id}")
            
            # Trading API için yeni ayarlar
            self.trading_api = Trading(
                domain='api.ebay.com',
                appid=settings['ebay_app_id'],
                devid=settings['ebay_dev_id'],
                certid=settings['ebay_cert_id'],
                token=settings['ebay_auth_token'],
                config_file=None
            )
            
            self.finding_api = Finding(appid=self.app_id, config_file=None)
            self.shopping_api = Shopping(appid=self.app_id, config_file=None)
            self.logger = logging.getLogger('ebay_service')
            
        except Exception as e:
            print(f"Error initializing eBay service: {str(e)}")
            raise

    def get_headers(self) -> Dict[str, str]:
        """Get common API headers"""
        return {
            "Authorization": f"Bearer {token_manager.get_access_token()}",
            "X-EBAY-C-MARKPLACE-ID": "EBAY_GB",
            "Content-Type": "application/json"
        }

    def get_trading_headers(self) -> Dict[str, str]:
        """Get Trading API headers"""
        return {
            "X-EBAY-API-SITEID": "3",
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "GetCategories",
            "Content-Type": "application/xml",
            "X-EBAY-API-APP-NAME": token_manager.client_id,
            "X-EBAY-API-DEV-NAME": token_manager.dev_id,
            "X-EBAY-API-CERT-NAME": token_manager.client_secret
        }

    def get_all_categories(self) -> Optional[Dict[str, Any]]:
        """Get all eBay categories"""
        try:
            # XML request body
            xml_request = """<?xml version="1.0" encoding="utf-8"?>
            <GetCategoriesRequest xmlns="urn:ebay:apis:eBLBaseComponents">    
                <RequesterCredentials>
                    <eBayAuthToken>{}</eBayAuthToken>
                </RequesterCredentials>
                <ErrorLanguage>en_GB</ErrorLanguage>
                <WarningLevel>High</WarningLevel>
                <DetailLevel>ReturnAll</DetailLevel>
                <ViewAllNodes>true</ViewAllNodes>
                <CategorySiteID>3</CategorySiteID>
            </GetCategoriesRequest>""".format(token_manager.get_access_token())

            print("\nSending request to eBay Trading API (UK)...")
            print(f"Headers: {self.get_trading_headers()}")
            print(f"Request Body: {xml_request[:500]}...")

            # Make request
            response = requests.post(
                "https://api.ebay.com/ws/api.dll",
                headers=self.get_trading_headers(),
                data=xml_request
            )
            
            print(f"\nAPI Response Status: {response.status_code}")
            print(f"API Response Headers: {dict(response.headers)}")
            print(f"API Response Body: {response.text[:500]}...")
            
            if response.status_code == 200:
                # Parse XML response
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.text)
                
                # Check for errors
                errors = root.findall(".//Errors")
                if errors:
                    for error in errors:
                        error_id = error.find("ErrorCode")
                        error_msg = error.find("LongMessage")
                        if error_id is not None and error_msg is not None:
                            print(f"eBay Error {error_id.text}: {error_msg.text}")
                    return None
                
                categories = {}
                
                # Parse all categories
                for category in root.findall(".//Category"):
                    category_id = category.find("CategoryID")
                    category_name = category.find("CategoryName")
                    parent_id = category.find("CategoryParentID")
                    level = category.find("CategoryLevel")
                    leaf = category.find("LeafCategory")
                    
                    if all([category_id, category_name]):
                        categories[category_id.text] = {
                            "id": category_id.text,
                            "name": category_name.text,
                            "parent_id": parent_id.text if parent_id is not None else None,
                            "level": level.text if level is not None else None,
                            "is_leaf": leaf.text if leaf is not None else "false"
                        }
                
                if categories:
                    # Save categories to file for caching
                    cache_path = Path(__file__).parent.parent.parent / 'config' / 'categories_cache_uk.json'
                    with open(cache_path, 'w') as f:
                        import json
                        json.dump(categories, f, indent=2)
                    
                    print(f"\nCached {len(categories)} UK categories")
                    return categories
                else:
                    print("No categories found in response")
                    return None
                
            else:
                print(f"Error response: {response.text}")
                return None

        except Exception as e:
            print(f"Get categories error: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return None

    def find_category_by_name(self, title: str) -> Optional[Dict[str, Any]]:
        """Find category by matching title with category names"""
        try:
            # Try to load from cache first
            cache_path = Path(__file__).parent.parent.parent / 'config' / 'categories_cache.json'
            
            if not cache_path.exists():
                print("Categories cache not found, fetching categories...")
                categories = self.get_all_categories()
            else:
                print("Loading categories from cache...")
                with open(cache_path) as f:
                    import json
                    categories = json.load(f)
            
            if not categories:
                print("No categories available")
                return None
                
            # Clean and split the search title
            search_terms = set(title.lower().split())
            
            best_match = None
            best_score = 0
            
            # Search through categories
            for cat_id, cat_data in categories.items():
                cat_name = cat_data['name'].lower()
                cat_terms = set(cat_name.split())
                
                # Calculate match score
                matches = len(search_terms.intersection(cat_terms))
                if matches > best_score:
                    best_score = matches
                    best_match = cat_data
            
            if best_match:
                return {
                    "category_id": best_match['id'],
                    "category_name": best_match['name'],
                    "confidence": best_score / len(search_terms)
                }
            
            # Fallback for laboratory equipment
            return {
                "category_id": "171000",
                "category_name": "Laboratory Equipment",
                "confidence": 0.5
            }

        except Exception as e:
            print(f"Category search error: {str(e)}")
            return None

    def image_to_base64(self, image_url: str) -> Optional[str]:
        """Convert image URL to base64 string"""
        try:
            response = requests.get(image_url)
            response.raise_for_status()
            return base64.b64encode(response.content).decode('utf-8')
        except Exception as e:
            print(f"Error converting image to base64: {str(e)}")
            return None

    def search_by_image(self, image_url: str) -> Optional[Dict[str, Any]]:
        """Search items using image"""
        try:
            # Convert image to base64
            base64_image = self.image_to_base64(image_url)
            if not base64_image:
                return None

            # Prepare request
            url = "https://api.ebay.com/buy/browse/v1/item_summary/search_by_image"
            data = {"image": base64_image}
            params = {
                'limit': '3',
                'sort': '-price'
            }

            # Make request
            response = requests.post(
                url,
                headers=self.get_headers(),
                json=data,
                params=params
            )
            response.raise_for_status()
            
            results = response.json()
            
            if 'itemSummaries' in results:
                items = results['itemSummaries']
                if items:
                    best_match = items[0]  # En pahalı ürün (sort=-price)
                    price = float(best_match['price']['value'])
                    suggested_price = price * 0.98

                    return {
                        'ebay_url': best_match['itemWebUrl'],
                        'google_url': '',
                        'ebay_lowest_price': f"${price:.2f}",
                        'suggested_price': f"${suggested_price:.2f}",
                        'all_prices': [f"${price:.2f}"],
                        'price_source': 'ebay_image_api'
                    }

            return None

        except Exception as e:
            print(f"Search by image error: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return None

    def search_by_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Search items using keyword"""
        try:
            # Prepare request
            url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
            params = {
                'q': keyword,
                'filter': [
                    'buyingOptions:{FIXED_PRICE}',
                    'itemLocationCountry:GB'
                ],
                'sort': '-price',
                'limit': '10'
            }

            # Make request
            response = requests.get(
                url,
                headers=self.get_headers(),
                params=params
            )
            response.raise_for_status()
            
            results = response.json()
            
            if 'itemSummaries' in results:
                items = results['itemSummaries']
                if items:
                    best_match = items[0]  # En pahalı ürün
                    price = float(best_match['price']['value'])
                    suggested_price = price * 0.98

                    return {
                        'ebay_url': best_match['itemWebUrl'],
                        'google_url': '',
                        'ebay_lowest_price': f"£{price:.2f}",
                        'suggested_price': f"£{suggested_price:.2f}",
                        'all_prices': [f"£{price:.2f}"],
                        'price_source': 'ebay_keyword_api'
                    }

            return None

        except Exception as e:
            print(f"Search by keyword error: {str(e)}")
            if hasattr(e, 'response'):
                print(f"Response: {e.response.text}")
            return None

    def extract_item_id(self, url: str) -> Optional[str]:
        """eBay URL'sinden item ID'yi çıkar"""
        try:
            print(f"\nExtracting item ID from URL: {url}")
            # URL formatları:
            # https://www.ebay.co.uk/itm/123456789
            # https://www.ebay.co.uk/itm/item-title/123456789
            # https://www.ebay.co.uk/itm/123456789?hash=item...
            
            import re
            patterns = [
                r'/itm/(\d+)',  # Basit ID
                r'/itm/[^/]+/(\d+)',  # Başlıklı ID
                r'/itm/(\d+)\?',  # Query parametreli ID
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    item_id = match.group(1)
                    print(f"Found item ID: {item_id}")
                    return item_id
                    
            print(f"No item ID found in URL")
            return None
            
        except Exception as e:
            print(f"Error extracting item ID: {str(e)}")
            return None

    def get_item_details(self, item_url: str) -> Optional[Dict]:
        """eBay ürün linkinden detaylı bilgileri al"""
        try:
            print(f"\nGetting item details for URL: {item_url}")
            
            # URL'den item ID'yi çıkar
            item_id = self.extract_item_id(item_url)
            if not item_id:
                print("Could not extract item ID")
                return None

            print(f"Making API call for item ID: {item_id}")
            
            # Önce kategori cache'ini kontrol et
            cache_path = Path(__file__).parent.parent.parent / 'config' / 'categories_cache_uk.json'
            categories_cache = {}
            if cache_path.exists():
                with open(cache_path, 'r') as f:
                    categories_cache = json.load(f)

            # Shopping API ile ürün detaylarını al
            response = self.shopping_api.execute('GetSingleItem', {
                'ItemID': item_id,
                'IncludeSelector': 'Details,Categories,Variations'
            })
            
            print("API response received")
            item = response.dict()['Item']
            
            # Kategori bilgilerini al
            primary_category_id = item.get('PrimaryCategoryID')
            if not primary_category_id:
                print("No primary category ID found")
                return None

            # Kategori detaylarını al
            try:
                category_response = self.shopping_api.execute('GetCategories', {
                    'CategoryID': primary_category_id,
                    'DetailLevel': 'ReturnAll',
                    'ViewAllNodes': 'true'
                })
                
                category_info = category_response.dict()
                categories = []
                category_path = []

                # Kategori yolunu oluştur
                current_cat = category_info['Categories']['Category'][0]
                while current_cat:
                    categories.append(current_cat['CategoryName'])
                    category_path.insert(0, current_cat['CategoryName'])
                    
                    # Üst kategoriye geç
                    parent_id = current_cat.get('CategoryParentID')
                    if parent_id and parent_id != current_cat['CategoryID']:
                        # Cache'den veya API'den üst kategoriyi bul
                        if parent_id in categories_cache:
                            current_cat = categories_cache[parent_id]
                        else:
                            parent_response = self.shopping_api.execute('GetCategories', {
                                'CategoryID': parent_id,
                                'DetailLevel': 'ReturnAll'
                            })
                            current_cat = parent_response.dict()['Categories']['Category'][0]
                    else:
                        break

            except Exception as e:
                print(f"Error getting category details: {str(e)}")
                categories = []
                if 'PrimaryCategoryName' in item:
                    categories.append(item['PrimaryCategoryName'])
                
                if 'CategoryName' in item:
                    category_path = [cat.strip() for cat in item['CategoryName'].split(':')]
                    categories.extend(category_path)

            # Tekrar eden kategorileri temizle
            categories = list(dict.fromkeys(categories))
            print(f"Final categories: {categories}")
            
            result = {
                'title': item.get('Title', ''),
                'raw_categories': categories,
                'condition': item.get('ConditionDisplayName', ''),
                'item_specifics': item.get('ItemSpecifics', {}).get('NameValueList', []),
                'category_id': primary_category_id,
                'category_path': ' > '.join(categories) if categories else ''
            }
            
            print(f"Returning item details: {result}")
            return result

        except Exception as e:
            print(f"Error getting item details: {str(e)}")
            self.logger.error(f"eBay ürün detayları alınamadı: {str(e)}")
            return None

    def map_ebay_to_woo_categories(self, ebay_categories: List[str]) -> List[str]:
        """eBay kategorilerini WooCommerce kategorilerine dönüştür"""
        woo_categories = []
        
        # Kategori eşleştirme mantığı
        category_mapping = {
            'Business & Industrial': 'Industrial',
            'Test & Measurement': 'Lab Equipment',
            'Healthcare, Lab & Dental': 'Lab Equipment',
            'Lab Equipment': 'Lab Equipment',
            'Electronic Equipment': 'Electronics',
            'Medical, Lab & Life Science': 'Lab Equipment',
            'Industrial Automation': 'Industrial',
            'Electrical Equipment': 'Electronics',
            'Manufacturing & Metalworking': 'Industrial',
            'Heavy Equipment': 'Industrial',
            'Light Equipment & Tools': 'Tools'
        }
        
        # Her eBay kategorisi için eşleştirme yap
        for cat in ebay_categories:
            for ebay_cat, woo_cat in category_mapping.items():
                if ebay_cat.lower() in cat.lower():
                    if woo_cat not in woo_categories:
                        woo_categories.append(woo_cat)
        
        # Eğer hiç eşleşme bulunamazsa varsayılan kategori
        if not woo_categories:
            woo_categories = ['Other']
            
        return woo_categories

    def get_item_categories(self, item_id: str) -> dict:
        """Item ID'den kategori bilgilerini al"""
        try:
            self.logger.info(f"Getting categories for item: {item_id}")
            
            # GetItem API çağrısı
            response = self.trading_api.execute('GetItem', {
                'ItemID': item_id,
                'DetailLevel': 'ReturnAll',
                'IncludeItemSpecifics': True
            })
            
            item = response.dict()['Item']
            
            # Kategori bilgilerini topla
            categories = {
                'primary_category': {
                    'id': item.get('PrimaryCategory', {}).get('CategoryID', ''),
                    'name': item.get('PrimaryCategory', {}).get('CategoryName', '')
                },
                'secondary_category': {
                    'id': item.get('SecondaryCategory', {}).get('CategoryID', ''),
                    'name': item.get('SecondaryCategory', {}).get('CategoryName', '')
                },
                'store_category': {
                    'id': item.get('Storefront', {}).get('StoreCategoryID', ''),
                    'name': item.get('Storefront', {}).get('StoreCategoryName', '')
                },
                'category_path': [],
                'specifics': []
            }
            
            # Item Specifics'i işle
            if 'ItemSpecifics' in item and 'NameValueList' in item['ItemSpecifics']:
                for specific in item['ItemSpecifics']['NameValueList']:
                    if isinstance(specific['Value'], list):
                        value = ''.join(specific['Value'])
                    else:
                        value = specific['Value']
                    categories['specifics'].append({
                        'Name': specific['Name'],
                        'Value': value
                    })
            
            # Kategori yolunu al - düzeltilmiş versiyon
            try:
                category_id = categories['primary_category']['id']
                if category_id:
                    print(f"\nGetting category path for ID: {category_id}")
                    
                    # GetCategoryFeatures API çağrısı
                    cat_response = self.trading_api.execute('GetCategoryFeatures', {
                        'CategoryID': category_id,
                        'DetailLevel': 'ReturnAll',
                        'ViewAllNodes': True,
                        'AllFeaturesForCategory': True
                    })
                    
                    # Debug için yanıtı yazdır
                    print("\nCategory Features Response:")
                    cat_data = cat_response.dict()
                    print(json.dumps(cat_data, indent=2))
                    
                    # Kategori yolunu oluştur
                    if 'Category' in cat_data:
                        category = cat_data['Category']
                        path = []
                        
                        # Ana kategoriyi ekle
                        path.append({
                            'id': category_id,
                            'name': categories['primary_category']['name']
                        })
                        
                        # Üst kategorileri bul
                        current_id = category_id
                        while True:
                            parent_response = self.trading_api.execute('GetCategories', {
                                'CategoryID': current_id,
                                'LevelLimit': 1,
                                'DetailLevel': 'ReturnAll'
                            })
                            
                            parent_data = parent_response.dict()
                            if 'CategoryArray' in parent_data and parent_data['CategoryArray']:
                                cat = parent_data['CategoryArray']['Category'][0]
                                parent_id = cat.get('CategoryParentID')
                                
                                if parent_id and parent_id != current_id:
                                    path.insert(0, {
                                        'id': parent_id,
                                        'name': cat.get('CategoryName', '')
                                    })
                                    current_id = parent_id
                                else:
                                    break
                            else:
                                break
                        
                        categories['category_path'] = path
                        
            except Exception as e:
                self.logger.error(f"Error getting category path: {str(e)}")
                print(f"\nCategory path error details: {str(e)}")
            
            return categories
            
        except Exception as e:
            self.logger.error(f"Error getting item categories: {str(e)}")
            print(f"\nAPI error details: {str(e)}")
            return None

    def print_categories(self, categories: dict):
        """Kategori bilgilerini düzenli şekilde yazdır"""
        if not categories:
            print("No category information found")
            return
        
        print("\n=== Category Information ===")
        
        print("\nPrimary Category:")
        print(f"ID: {categories['primary_category']['id']}")
        print(f"Name: {categories['primary_category']['name']}")
        
        if categories['secondary_category']['id']:
            print("\nSecondary Category:")
            print(f"ID: {categories['secondary_category']['id']}")
            print(f"Name: {categories['secondary_category']['name']}")
        
        if categories['store_category']['id']:
            print("\nStore Category:")
            print(f"ID: {categories['store_category']['id']}")
            print(f"Name: {categories['store_category']['name']}")
        
        print("\nCategory Path:")
        for cat in categories['category_path']:
            print(f"- {cat['name']} (ID: {cat['id']})")
        
        print("\nItem Specifics:")
        for specific in categories['specifics']:
            print(f"- {specific['Name']}: {specific['Value']}")

# Global instance
ebay_service = EbayService() 