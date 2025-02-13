import logging
from datetime import datetime

class ListingManager:
    def __init__(self):
        self.logger = logging.getLogger('listing_manager')

    def prepare_listing_data(self, product):
        """Ürün verilerini eBay listing formatına dönüştür"""
        try:
            # Fiyat kontrolü ve dönüşümü
            if 'ebay_lowest_price' in product:
                price = float(str(product['ebay_lowest_price']).replace('£', '').strip())
            elif 'price' in product:  # Test formundan gelen veri için
                price = float(product['price'])
            else:
                raise ValueError("Fiyat bilgisi bulunamadı")

            # Temel ürün bilgileri
            listing_data = {
                'title': product['title'],
                'description': self.generate_description(product),
                'price': price,
                'image_url': product.get('image_url', ''),
                'category_id': self.determine_category(product['title']),
                'condition_id': self.determine_condition(product['title'])['condition_id'],
                'paypal_email': 'your-paypal@email.com'  # PayPal email adresinizi girin
            }
            
            self.logger.debug(f"Hazırlanan listing verisi: {listing_data}")
            return listing_data
            
        except Exception as e:
            self.logger.error(f"Listing hazırlama hatası: {str(e)}")
            self.logger.debug(f"Gelen ürün verisi: {product}")
            raise

    def generate_description(self, product):
        """Ürün açıklaması oluştur"""
        try:
            # HTML özel karakterlerini escape et
            title = product['title'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # Fiyat bilgisini al
            if 'current_bid' in product:
                price = str(product['current_bid'])
            elif 'price' in product:
                price = f"£{product['price']}"
            else:
                price = "N/A"
            
            description = f"""
<![CDATA[
<div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
    <h2 style="color: #333;">{title}</h2>
    
    <div style="margin: 20px 0;">
        <h3 style="color: #666;">Ürün Detayları:</h3>
        <ul style="list-style-type: disc; margin-left: 20px;">
            <li>Durum: {self.determine_condition(title)['condition_text']}</li>
            <li>Orijinal Fiyat: {price}</li>
        </ul>
    </div>
    
    <div style="margin: 20px 0;">
        <h3 style="color: #666;">Kargo Bilgileri:</h3>
        <ul style="list-style-type: disc; margin-left: 20px;">
            <li>Royal Mail 2nd Class ile gönderim</li>
            <li>30 gün iade garantisi</li>
            <li>Güvenli paketleme</li>
        </ul>
    </div>
    
    <div style="margin: 20px 0; padding: 10px; background-color: #f9f9f9; border: 1px solid #ddd;">
        <p><strong>Not:</strong> Ürünlerimiz profesyonel olarak test edilmiş ve kontrol edilmiştir.</p>
    </div>
</div>
]]>"""
            return description
            
        except Exception as e:
            self.logger.error(f"Açıklama oluşturma hatası: {str(e)}")
            return f"<![CDATA[{product['title']}]]>"  # Fallback basit açıklama

    def determine_category(self, title):
        """Başlığa göre eBay kategori ID'sini belirle"""
        # Burada başlığa göre kategori belirleme mantığı eklenebilir
        # Şimdilik varsayılan kategori
        return "11450"  # Örnek kategori ID'si

    def determine_condition(self, title):
        """Ürün durumunu belirle"""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['new', 'sealed', 'unused']):
            return {
                'condition_id': '1000',
                'condition_text': 'New'
            }
        elif 'refurbished' in title_lower:
            return {
                'condition_id': '2500',
                'condition_text': 'Refurbished'
            }
        else:
            return {
                'condition_id': '3000',
                'condition_text': 'Used'
            }