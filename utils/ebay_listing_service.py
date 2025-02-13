import pandas as pd
from ebaysdk.trading import Connection as Trading
from ebaysdk.exception import ConnectionError
from config.ebay_config import get_ebay_config
import html
import re
import json
import time
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

class EbayListingService:
    def __init__(self):
        """Initialize eBay Trading API with production credentials"""
        config = get_ebay_config()
        if not config:
            raise ValueError("eBay configuration not found!")
            
        self.api = Trading(
            domain=config['domain'],
            appid=config['app_id'],
            devid=config['dev_id'],
            certid=config['cert_id'],
            token=config['auth_token'],
            config_file=config['config_file'],
            siteid=config['siteid'],
            warnings=config['warnings'],
            timeout=config['timeout']
        )

    def validate_image_url(self, url: str) -> bool:
        """Resim URL'sinin geçerli olup olmadığını kontrol eder"""
        try:
            if not url:
                return False
            
            parsed = urlparse(url)
            return bool(parsed.scheme and parsed.netloc)
        except:
            return False

    def clean_text(self, text: str) -> str:
        """Metni XML için güvenli hale getirir"""
        try:
            if not text:
                return "No Description Available"
            
            # String'e çevir
            text = str(text)
            
            # XML için tehlikeli karakterleri temizle
            unsafe_chars = {
                '&': 'and',  # & karakterini "and" ile değiştir
                '<': ' less than ',
                '>': ' greater than ',
                '"': "'",
                "'": "'",
                '—': '-',
                '–': '-',
                '\n': ' ',  # Yeni satırları boşlukla değiştir
                '\r': ' '
            }
            
            for char, replacement in unsafe_chars.items():
                text = text.replace(char, replacement)
            
            # Çift boşlukları temizle
            text = ' '.join(text.split())
            
            return text.strip()
        except Exception as e:
            print(f"⚠️ Metin temizleme hatası: {str(e)}")
            return "Product Description"

    def clean_price(self, price: Any) -> Optional[float]:
        """Fiyatı temizler ve float'a çevirir"""
        try:
            if isinstance(price, (int, float)):
                return float(price)
            
            if isinstance(price, str):
                # "Not Available" veya "Not Found" kontrolü
                if "not" in price.lower():
                    return None
                
                # £ işareti ve boşlukları kaldır
                cleaned = price.replace('£', '').strip()
                # Virgülleri kaldır (örn: 1,234.56 -> 1234.56)
                cleaned = cleaned.replace(',', '')
                return float(cleaned)
            
            return None
        except:
            return None

    def prepare_item_data(self, row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """eBay listing için item datasını hazırlar"""
        try:
            title = self.clean_text(row.get('title'))
            if not title:
                print("⚠️ Başlık bulunamadı")
                return None

            price = self.clean_price(row.get('suggested_price'))
            if not price:
                print(f"⚠️ Geçersiz fiyat: {row.get('suggested_price')}")
                return None

            image_url = row.get('image_url')
            if not self.validate_image_url(image_url):
                print(f"⚠️ Geçersiz resim URL'si: {image_url}")
                image_url = "https://i.ebayimg.com/images/g/default/s-l1600.jpg"

            myitem = {
                "Item": {
                    "Title": title[:80],
                    "Description": self.clean_text(f"""
{title}

Condition: Used - Good working condition
Professional equipment available for immediate dispatch.

Features:
- Professionally tested
- In good working order
- UK stock
- Fast shipping

Payment and Shipping:
- Payment via PayPal
- Ships within 3 business days
- Free UK mainland shipping
- International shipping available (contact for rates)

Returns:
- 30-day return policy
- Buyer pays return shipping
- Item must be returned in original condition
                    """),
                    "PrimaryCategory": {"CategoryID": "92074"},
                    "StartPrice": str(price),
                    "CategoryMappingAllowed": "true",
                    "Country": "GB",
                    "ConditionID": "3000",
                    "Currency": "GBP",
                    "DispatchTimeMax": "3",
                    "ListingDuration": "Days_30",
                    "ListingType": "FixedPriceItem",
                    "PaymentMethods": "PayPal",
                    "PayPalEmailAddress": "your-paypal@email.com",
                    "PictureDetails": {"PictureURL": image_url},
                    "PostalCode": "W1A 1AA",
                    "Quantity": "1",
                    "ReturnPolicy": {
                        "ReturnsAcceptedOption": "ReturnsAccepted",
                        "RefundOption": "MoneyBack",
                        "ReturnsWithinOption": "Days_30",
                        "ShippingCostPaidByOption": "Buyer"
                    },
                    "ShippingDetails": {
                        "ShippingType": "Flat",
                        "ShippingServiceOptions": {
                            "ShippingServicePriority": "1",
                            "ShippingService": "UK_RoyalMailSecondClass",
                            "ShippingServiceCost": "0.00",
                            "FreeShipping": "true"
                        }
                    },
                    "Site": "UK"
                }
            }
            return myitem

        except Exception as e:
            print(f"⚠️ Item data hazırlama hatası: {str(e)}")
            return None

    def list_item(self, row: Dict[str, Any]) -> Optional[str]:
        """Ürünü eBay'de listeler"""
        try:
            item_data = self.prepare_item_data(row)
            if not item_data:
                return None

            response = self.api.execute('AddFixedPriceItem', item_data)
            result = response.dict()

            if response.reply.Ack == 'Success':
                item_id = result.get('ItemID')
                return f"https://www.ebay.co.uk/itm/{item_id}"
            else:
                print("❌ eBay API Hatası:")
                print(json.dumps(result, indent=2))
                return None

        except ConnectionError as e:
            print(f"❌ Bağlantı hatası: {str(e)}")
            return None
        except Exception as e:
            print(f"❌ Listeleme hatası: {str(e)}")
            return None

    def bulk_list_items(self, csv_path: str) -> None:
        """CSV'den toplu listeleme yapar"""
        try:
            # CSV'yi oku
            df = pd.read_csv(csv_path, encoding='utf-8')
            print(f"Toplam ürün sayısı: {len(df)}")

            # Her ürün için listeleme yap
            for index, row in df.iterrows():
                print(f"\n{index + 1}. ürün işleniyor: {row['title']}")
                
                ebay_url = self.list_item(row.to_dict())
                
                if ebay_url:
                    print(f"✅ Başarıyla listelendi: {ebay_url}")
                else:
                    print("❌ Listeleme başarısız")
                
                # API limitlerini aşmamak için bekle
                time.sleep(2)

        except Exception as e:
            print(f"❌ CSV işleme hatası: {str(e)}")

def main():
    service = EbayListingService()
    service.bulk_list_items('lots_details_with_ebay.csv')

if __name__ == "__main__":
    main() 