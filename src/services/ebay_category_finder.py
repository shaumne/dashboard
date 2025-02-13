from ebaysdk.trading import Connection as Trading
import json
import logging
from pathlib import Path
import sys

class EbayCategoryFinder:
    def __init__(self):
        try:
            # settings.json dosyasından ayarları oku
            with open('config/settings.json', 'r') as f:
                settings = json.load(f)
            
            # Trading API bağlantısını kur
            self.api = Trading(
                domain='api.ebay.com',
                appid=settings['ebay_app_id'],
                devid=settings['ebay_dev_id'],
                certid=settings['ebay_cert_id'],
                token=settings['ebay_auth_token'],
                config_file=None
            )
            
            # Logging ayarla
            logging.basicConfig(level=logging.INFO)
            self.logger = logging.getLogger('ebay_category_finder')
            
        except Exception as e:
            print(f"Initialization error: {str(e)}")
            sys.exit(1)

    def extract_item_id(self, url: str) -> str:
        """eBay URL'sinden item ID'yi çıkar"""
        try:
            import re
            # Debug için URL'yi logla
            self.logger.info(f"Extracting item ID from URL: {url}")
            
            patterns = [
                r'/itm/(\d+)',
                r'/itm/[^/]+/(\d+)',
                r'item=(\d+)',
                r'item/(\d+)',
                r'(\d{12})'  # 12 haneli eBay item ID'leri için
            ]
            
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    item_id = match.group(1)
                    self.logger.info(f"Successfully extracted item ID: {item_id}")
                    return item_id
                    
            self.logger.error(f"Could not extract item ID from URL: {url}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting item ID: {str(e)}")
            return None

    def convert_to_woo_categories(self, ebay_category_path: str) -> list:
        """eBay kategori yolunu WooCommerce formatına dönüştür"""
        try:
            woo_categories = []
            
            # Kategori yolunu parçala
            categories = ebay_category_path.split(':')
            
            # Her kategoriyi WooCommerce formatına dönüştür
            for category in categories:
                woo_categories.append({
                    "name": category.strip()
                })
            
            self.logger.info(f"Converted categories: {woo_categories}")
            return woo_categories
            
        except Exception as e:
            self.logger.error(f"Error converting categories: {str(e)}")
            return []

    def get_item_categories(self, item_id: str) -> dict:
        """Item ID'den kategori bilgilerini al"""
        try:
            self.logger.info(f"Getting categories for item: {item_id}")
            
            # GetItem API çağrısı
            response = self.api.execute('GetItem', {
                'ItemID': item_id,
                'DetailLevel': 'ReturnAll',
                'IncludeItemSpecifics': True
            })
            
            item = response.dict()['Item']
            
            # Kategori yolunu al
            category_path = item.get('PrimaryCategory', {}).get('CategoryName', '')
            
            # WooCommerce formatına dönüştür
            woo_categories = self.convert_to_woo_categories(category_path)
            
            # Brand bilgisini bul
            brand = None
            if 'ItemSpecifics' in item and 'NameValueList' in item['ItemSpecifics']:
                for specific in item['ItemSpecifics']['NameValueList']:
                    if specific['Name'].lower() in ['brand', 'manufacturer', 'maker']:
                        brand = specific['Value']
                        if isinstance(brand, list):
                            brand = brand[0]
                        break
            
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
                'specifics': [],
                'raw_categories': [],
                'brand': brand,
                'woo_categories': woo_categories
            }
            
            # Item Specifics'i düzgün şekilde işle
            if 'ItemSpecifics' in item and 'NameValueList' in item['ItemSpecifics']:
                for specific in item['ItemSpecifics']['NameValueList']:
                    if isinstance(specific['Value'], list):
                        value = ', '.join(specific['Value'])
                    else:
                        value = specific['Value']
                    
                    categories['specifics'].append({
                        'Name': specific['Name'],
                        'Value': value
                    })
            
            # Ana kategoriyi ve yolunu ekle
            primary_cat = item.get('PrimaryCategory', {})
            if primary_cat:
                cat_name = primary_cat.get('CategoryName', '')
                if cat_name:
                    categories['raw_categories'].append(cat_name)
                    categories['category_path'].append({
                        'id': primary_cat.get('CategoryID', ''),
                        'name': cat_name
                    })
            
            # Debug için sonuçları logla
            self.logger.info(f"Categories and brand found: {categories}")
            return categories
            
        except Exception as e:
            self.logger.error(f"Error getting item categories: {str(e)}")
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

def main():
    """Ana işlem akışı"""
    try:
        finder = EbayCategoryFinder()
        
        # URL'yi kullanıcıdan al
        print("\nEbay ürün URL'sini veya Item ID'sini girin:")
        item_url_or_id = input("> ").strip()
        
        if not item_url_or_id:
            print("URL veya Item ID girilmedi!")
            sys.exit(1)
        
        # URL mi ID mi kontrol et
        if 'ebay' in item_url_or_id.lower():
            item_id = finder.extract_item_id(item_url_or_id)
            print(f"\nURL'den çıkarılan Item ID: {item_id}")
        else:
            item_id = item_url_or_id
            print(f"\nGirilen Item ID: {item_id}")
        
        if not item_id:
            print("Geçerli bir Item ID bulunamadı!")
            sys.exit(1)
        
        # Kategorileri al ve yazdır
        print("\nKategori bilgileri alınıyor...")
        categories = finder.get_item_categories(item_id)
        finder.print_categories(categories)

    except KeyboardInterrupt:
        print("\nİşlem kullanıcı tarafından sonlandırıldı.")
        sys.exit(0)
    except Exception as e:
        print(f"\nBir hata oluştu: {str(e)}")
        print("\nHata detayları:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 