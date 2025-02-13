from ebaysdk.trading import Connection as Trading
from ebaysdk.exception import ConnectionError
import logging
import json
import yaml
import html
import re

class EbayAPI:
    def __init__(self):
        self.logger = logging.getLogger('ebay_api')
        self.sandbox = True
        
        try:
            # Settings ve template dosyalarını oku
            with open('config/settings.json', 'r') as f:
                settings = json.load(f)
                
            with open('config/ebay_template.yaml', 'r', encoding='utf-8') as f:
                self.template = yaml.safe_load(f)
                
            with open('config/description_template.yaml', 'r', encoding='utf-8') as f:
                self.description_template = yaml.safe_load(f)
            
            # SDK bağlantısını oluştur
            self.api = Trading(
                domain='api.sandbox.ebay.com' if self.sandbox else 'api.ebay.com',
                appid=settings['ebay_app_id'],
                devid=settings['ebay_dev_id'],
                certid=settings['ebay_cert_id'],
                token=settings['ebay_auth_token'],
                config_file=None
            )
            
            self.logger.info("eBay API bağlantısı başarıyla oluşturuldu")
            
        except Exception as e:
            self.logger.error(f"Yapılandırma yükleme hatası: {str(e)}")
            raise

    def create_listing_description(self, title, condition):
        """Basit HTML açıklama oluştur"""
        return f'''
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
    <h1>{title}</h1>
    <div style="margin: 20px 0;">
        <h3>Product Details:</h3>
        <ul>
            <li>Condition: {condition}</li>
            <li>Professional UK Seller</li>
            <li>Fast Shipping</li>
        </ul>
    </div>
    <div style="margin: 20px 0;">
        <h3>Shipping Information:</h3>
        <ul>
            <li>Royal Mail 2nd Class Delivery</li>
            <li>30 Day Return Policy</li>
            <li>Secure Packaging</li>
        </ul>
    </div>
</div>'''

    def create_draft_listing(self, item_data):
        """eBay'de ürün oluştur"""
        try:
            # Template'i kopyala
            listing_data = self.template.copy()
            
            # Description oluştur
            description = self.description_template['template'].format(
                title=item_data['title'],
                condition=item_data.get('condition', 'Used')
            )
            
            # Temel bilgileri güncelle
            listing_data['Item'].update({
                'Title': item_data['title'][:80],
                'Description': f'<![CDATA[{description}]]>',
                'StartPrice': str(item_data['price']),
                'PrimaryCategory': {'CategoryID': str(item_data['category_id'])},
                'ConditionID': str(item_data['condition_id']),
                'PayPalEmailAddress': item_data['paypal_email'],
                'PictureDetails': {
                    'PictureURL': [str(item_data['image_url'])]
                }
            })

            # Debug log
            self.logger.debug(f"Request data: {listing_data}")

            # API isteği gönder
            response = self.api.execute('AddFixedPriceItem', listing_data)
            
            if response.reply.Ack == 'Success' or response.reply.Ack == 'Warning':
                return {
                    'success': True,
                    'item_id': response.reply.ItemID,
                    'fees': float(response.reply.Fees.TotalFee.value) if hasattr(response.reply, 'Fees') else 0.0
                }
            else:
                error = response.reply.Errors[0].LongMessage if hasattr(response.reply, 'Errors') else 'Bilinmeyen hata'
                self.logger.error(f"eBay API Hatası: {error}")
                return {
                    'success': False,
                    'error': error
                }

        except Exception as e:
            error_msg = f"Listing oluşturma hatası: {str(e)}"
            self.logger.error(error_msg)
            return {'success': False, 'error': error_msg}

    def calculate_fees(self, price):
        """eBay ücretlerini hesapla"""
        try:
            # Temel eBay ücreti (%10)
            basic_fee = price * 0.10
            
            # Ek ücretler
            listing_fee = 0.35  # Listeleme ücreti
            
            total_fees = basic_fee + listing_fee
            
            return round(total_fees, 2)
            
        except Exception as e:
            self.logger.error(f"Ücret hesaplama hatası: {str(e)}")
            return 0.0