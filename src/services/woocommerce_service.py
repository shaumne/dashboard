from woocommerce import API
import pandas as pd
import time
import logging
from typing import Dict, Any, Optional
import threading
import json
import os

class WooCommerceService:
    def __init__(self):
        # Settings'den ayarları oku
        settings_file = 'config/settings.json'
        with open(settings_file, 'r') as f:
            settings = json.load(f)
        
        self.wcapi = API(
            url=settings.get('woocommerce_url', ''),
            consumer_key=settings.get('woocommerce_consumer_key', ''),
            consumer_secret=settings.get('woocommerce_consumer_secret', ''),
            version="wc/v3"
        )
        
        self.webhook_secret = settings.get('woocommerce_webhook_secret', '')
        self.logger = logging.getLogger('woocommerce_service')
        self.source_csv_path = 'lots_details_with_ebay.csv'
        self.published_products_csv = 'published_products.csv'
        self.ensure_published_products_csv()
        
    def ensure_published_products_csv(self):
        """Published products CSV dosyasını oluştur veya kontrol et"""
        if not os.path.exists(self.published_products_csv):
            df = pd.DataFrame(columns=['title', 'auction_url', 'woo_product_id', 'product_url'])
            df.to_csv(self.published_products_csv, index=False)
            
    def create_product(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ürünü WooCommerce'de oluştur ve published_products.csv'ye kaydet"""
        try:
            # WooCommerce API formatına uygun veri hazırlama
            data = {
                "name": item_data['title'],
                "type": "simple",
                "regular_price": str(item_data['price']),
                "sale_price": str(item_data['sale_price']) if item_data.get('sale_price') else "",
                "description": item_data['description'],
                "short_description": f"Professional {item_data['title']} - {item_data['condition']}", # Kısa açıklama
                "categories": [{"name": cat} for cat in item_data['categories']],
                "images": item_data['images'],
                "status": "publish",
                
                # Stok bilgileri
                "sku": item_data.get('sku', ''),
                "manage_stock": True,
                "stock_quantity": item_data.get('stock', 1),
                
                # Gönderim bilgileri
                "weight": item_data.get('weight', ''),
                "shipping_class": item_data.get('shipping_class', ''),
                "shipping_required": item_data.get('requires_shipping', True),
                
                # Meta veriler
                "meta_data": [
                    {
                        "key": "auction_url",
                        "value": item_data['auction_url']
                    },
                    {
                        "key": "condition",
                        "value": item_data.get('condition', '')
                    },
                    {
                        "key": "warranty",
                        "value": item_data.get('warranty', '')
                    },
                    {
                        "key": "_warranty_info",  # WooCommerce garanti alanı
                        "value": item_data.get('warranty', '')
                    }
                ]
            }
            
            # Ürünü oluştur
            response = self.wcapi.post("products", data).json()
            
            if 'id' in response:
                # Başarılı oluşturma durumunda CSV'ye kaydet
                df = pd.read_csv(self.published_products_csv)
                new_row = {
                    'title': item_data['title'],
                    'auction_url': item_data['auction_url'],
                    'woo_product_id': response['id'],
                    'product_url': response['permalink']
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(self.published_products_csv, index=False)
                
                self.logger.info(f"Ürün başarıyla oluşturuldu: {item_data['title']}")
                
                return {
                    "success": True,
                    "product_id": response['id'],
                    "product_url": response['permalink']
                }
                
            self.logger.error(f"Ürün oluşturma hatası: {response.get('message', 'Bilinmeyen hata')}")
            return {"success": False, "error": response.get('message', 'Ürün oluşturulamadı')}
            
        except Exception as e:
            self.logger.error(f"WooCommerce ürün oluşturma hatası: {str(e)}")
            return {"success": False, "error": str(e)}

    def get_product_by_auction_url(self, auction_url: str) -> Optional[Dict]:
        """Auction URL'ye göre WooCommerce ürününü bul"""
        try:
            df = pd.read_csv(self.published_products_csv)
            product = df[df['auction_url'] == auction_url]
            
            if not product.empty:
                response = self.wcapi.get(f"products/{product.iloc[0]['woo_product_id']}").json()
                return response
                
        except Exception as e:
            self.logger.error(f"Ürün arama hatası: {str(e)}")
        
        return None

    def sync_products(self):
        """CSV'deki değişiklikleri kontrol et ve siteyi güncelle"""
        try:
            # Ana CSV'yi oku
            source_df = pd.read_csv(self.source_csv_path)
            current_auctions = set(source_df['auction_url'].tolist())
            current_titles = dict(zip(source_df['auction_url'], source_df['title']))
            
            # Yayınlanmış ürünler CSV'sini oku
            published_df = pd.read_csv(self.published_products_csv)
            
            # Her yayınlanmış ürün için kontrol yap
            for _, row in published_df.iterrows():
                auction_url = row['auction_url']
                
                # Eğer ürün artık ana CSV'de yoksa veya başlığı değiştiyse
                if auction_url not in current_auctions or \
                   (auction_url in current_titles and current_titles[auction_url] != row['title']):
                    # WooCommerce'den kaldır
                    self.wcapi.delete(f"products/{row['woo_product_id']}")
                    self.logger.info(f"Ürün kaldırıldı: {row['title']}")
                    
                    # CSV'den kaldır
                    published_df = published_df[published_df['auction_url'] != auction_url]
            
            # Güncellenmiş listeyi kaydet
            published_df.to_csv(self.published_products_csv, index=False)

        except Exception as e:
            self.logger.error(f"Senkronizasyon hatası: {str(e)}")

    def start_monitoring(self, check_interval: int = 300):
        """Arka planda CSV değişikliklerini izle"""
        def monitor():
            while True:
                self.sync_products()
                time.sleep(check_interval)
        
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

# Global instance
woo_service = WooCommerceService() 