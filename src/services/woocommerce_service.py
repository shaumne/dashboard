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
        self.source_csv_path = 'data/output/lots_details_with_ebay.csv'
        self.published_products_csv = 'data/check/published_products.csv'
        self.ensure_published_products_csv()
        
    def ensure_published_products_csv(self):
        """published_products.csv dosyasının varlığını kontrol et ve gerekirse oluştur"""
        try:
            if not os.path.exists('data/check'):
                os.makedirs('data/check')
            
            if not os.path.exists(self.published_products_csv):
                df = pd.DataFrame(columns=['title', 'auction_url', 'woo_product_id', 'product_url'])
                df.to_csv(self.published_products_csv, index=False)
                self.logger.info("published_products.csv oluşturuldu")
        except Exception as e:
            self.logger.error(f"CSV dosyası kontrol hatası: {str(e)}")

    def create_product(self, item_data: Dict[str, Any]) -> Dict[str, Any]:
        """Ürünü WooCommerce'de oluştur ve published_products.csv'ye kaydet"""
        try:
            self.logger.info(f"Ürün oluşturma başladı: {item_data.get('name', 'Unknown')}")
            self.logger.debug(f"Gelen veri: {json.dumps(item_data, indent=2)}")
            
            # CSV dosyasının varlığını kontrol et
            self.ensure_published_products_csv()
            
            # Fiyat kontrolü
            price = str(item_data.get('regular_price', '0'))
            if not price or price == '0':
                self.logger.error("Geçersiz fiyat")
                return {"success": False, "error": "Geçersiz fiyat"}

            # WooCommerce API formatına uygun veri hazırlama
            data = {
                "name": item_data['name'],
                "type": "simple",
                "regular_price": price,
                "description": item_data.get('description', ''),
                "short_description": item_data.get('short_description', ''),
                "categories": item_data.get('categories', []),
                "status": "publish",
                "manage_stock": True,
                "stock_quantity": item_data.get('stock_quantity', 1),
                "attributes": item_data.get('attributes', []),
                "images": item_data.get('images', [])
            }

            self.logger.debug(f"WooCommerce'a gönderilecek veri: {json.dumps(data, indent=2)}")
            
            try:
                # API isteği gönder
                response = self.wcapi.post("products", data)
                self.logger.debug(f"API yanıt kodu: {response.status_code}")
                self.logger.debug(f"API yanıt içeriği: {response.text}")
                
                response_data = response.json()
                self.logger.debug(f"WooCommerce API yanıtı: {json.dumps(response_data, indent=2)}")
                
                if response.status_code not in [200, 201]:
                    self.logger.error(f"API hatası: {response.status_code} - {response.text}")
                    return {"success": False, "error": f"API hatası: {response.status_code}"}
                    
                if 'id' in response_data:
                    try:
                        # CSV'ye kaydet
                        new_product = {
                            'title': item_data['name'],
                            'auction_url': item_data['url'],
                            'woo_product_id': response_data['id'],
                            'product_url': response_data.get('permalink', '')
                        }
                        
                        self.logger.debug(f"CSV'ye eklenecek veri: {new_product}")
                        
                        df = pd.read_csv(self.published_products_csv)
                        df = pd.concat([df, pd.DataFrame([new_product])], ignore_index=True)
                        df.to_csv(self.published_products_csv, index=False)
                        
                        self.logger.info(f"Ürün başarıyla oluşturuldu: ID={response_data['id']}")
                        return response_data
                        
                    except Exception as e:
                        self.logger.error(f"CSV kayıt hatası: {str(e)}")
                        return {"success": False, "error": f"Ürün oluşturuldu ama CSV'ye kaydedilemedi: {str(e)}"}
                else:
                    error_msg = response_data.get('message', 'Bilinmeyen hata')
                    self.logger.error(f"WooCommerce API hatası: {error_msg}")
                    return {"success": False, "error": error_msg}
                    
            except Exception as e:
                self.logger.error(f"API isteği hatası: {str(e)}")
                return {"success": False, "error": f"API isteği hatası: {str(e)}"}
            
        except Exception as e:
            self.logger.error(f"Genel hata: {str(e)}")
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
            # Ana CSV'yi oku - tam dosya yolunu kullan
            source_df = pd.read_csv(self.source_csv_path)  # self.source_csv_path kullan
            current_auctions = set(source_df['url'].tolist())
            current_titles = dict(zip(source_df['url'], source_df['name']))
            
            # Yayınlanmış ürünler CSV'sini oku
            if os.path.exists(self.published_products_csv):
                published_df = pd.read_csv(self.published_products_csv)
                
                # Her yayınlanmış ürün için kontrol yap
                for _, row in published_df.iterrows():
                    auction_url = row['auction_url']  # auction_url kullan
                    
                    # Eğer ürün artık ana CSV'de yoksa veya başlığı değiştiyse
                    if auction_url not in current_auctions or \
                       (auction_url in current_titles and current_titles[auction_url] != row['title']):
                        try:
                            # WooCommerce'den kaldır
                            self.wcapi.delete(f"products/{row['woo_product_id']}")
                            self.logger.info(f"Ürün kaldırıldı: {row['title']}")
                            
                            # CSV'den kaldır
                            published_df = published_df[published_df['auction_url'] != auction_url]
                        except Exception as delete_error:
                            self.logger.error(f"Ürün silme hatası: {str(delete_error)}")
                
                # Güncellenmiş listeyi kaydet
                published_df.to_csv(self.published_products_csv, index=False)
            else:
                self.logger.warning(f"Published products CSV bulunamadı: {self.published_products_csv}")
                self.ensure_published_products_csv()

        except FileNotFoundError as e:
            self.logger.error(f"CSV dosyası bulunamadı: {str(e)}")
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