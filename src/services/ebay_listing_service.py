import requests
from pathlib import Path
from ..api.ebay_token_manager import token_manager
from typing import Optional, Dict, Any
import html
import re
import xml.etree.ElementTree as ET
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class EbayListingService:
    def __init__(self):
        self.trading_url = "https://api.sandbox.ebay.com/ws/api.dll"  # Sandbox URL
        self.site_id = "3"  # UK
        self.app_id = "Emrecane-testlist-SBX-9e009f392-75ffd09b"
        self.dev_id = "16e78c19-03b2-4fe1-be62-f61a04aea50e"
        self.cert_id = "SBX-e009f392631c-74f8-43a1-8953-f5b7"
        self.auth_token = "v^1.1#i^1#I^3#r^0#f^0#p^3#t^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"

    def get_trading_headers(self) -> Dict[str, str]:
        """Get Trading API headers"""
        return {
            "X-EBAY-API-SITEID": self.site_id,
            "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
            "X-EBAY-API-CALL-NAME": "AddItem",
            "Content-Type": "application/xml",
            "X-EBAY-API-APP-NAME": self.app_id,
            "X-EBAY-API-DEV-NAME": self.dev_id,
            "X-EBAY-API-CERT-NAME": self.cert_id
        }

    def sanitize_text(self, text: str) -> str:
        """Clean text for XML"""
        if not text:
            return ""
        # HTML entities'e çevir
        text = html.escape(str(text))
        # Geçersiz XML karakterlerini temizle
        text = re.sub(r'[^\x09\x0A\x0D\x20-\x7E\x85\xA0-\xFF\u0100-\uD7FF\uE000-\uFFFD]', '', text)
        return text

    def format_price(self, price: Any) -> float:
        """Format price as float"""
        if isinstance(price, str):
            # Remove currency symbols and convert to float
            price = price.replace('£', '').replace('GBP', '').strip()
        return float(price)

    def create_listing(self, 
                      item_data: Dict[str, Any],
                      oauth_token: str) -> Dict[str, Any]:
        """Create fixed price item listing"""
        try:
            # XML request body
            xml_request = """<?xml version="1.0" encoding="utf-8"?>
                <AddItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
                    <RequesterCredentials>
                        <eBayAuthToken>v^1.1#i^1#I^3#r^0#f^0#p^3#t^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"</eBayAuthToken>
                    </RequesterCredentials>
                    <Item>
                        <Title>Hach Lange DR 2800 Spectrophotometer - Professional Lab Equipment</Title>
                        <Description><![CDATA[
                            <h2>Hach Lange DR 2800 Spectrophotometer</h2>
                            
                            <h3>Product Details:</h3>
                            <ul>
                                <li>Brand: Hach Lange</li>
                                <li>Model: DR 2800</li>
                                <li>Type: Spectrophotometer</li>
                                <li>Condition: Used - Tested Working</li>
                            </ul>

                            <h3>Features:</h3>
                            <ul>
                                <li>Professional laboratory spectrophotometer</li>
                                <li>Accurate and reliable measurements</li>
                                <li>Ideal for water analysis and quality control</li>
                                <li>User-friendly interface</li>
                            </ul>

                            <h3>Condition Details:</h3>
                            <p>This item has been professionally tested and is in good working condition. Shows normal signs of previous use but maintains full functionality.</p>

                            <h3>Shipping & Returns:</h3>
                            <ul>
                                <li>Fast shipping within 1-3 business days</li>
                                <li>Carefully packaged for safe delivery</li>
                                <li>30-day return policy</li>
                                <li>Professional after-sales support</li>
                            </ul>

                            <p>We are a professional seller specializing in laboratory and test equipment. All our items are thoroughly tested before listing.</p>
                        ]]></Description>
                        <PrimaryCategory>
                            <CategoryID>184653</CategoryID>  <!-- Lab Equipment category -->
                        </PrimaryCategory>
                        <StartPrice currencyID="GBP">1536.22</StartPrice>  <!-- 5% below market price -->
                        <ConditionID>3000</ConditionID>  <!-- Used -->
                        <Country>GB</Country>
                        <Currency>GBP</Currency>
                        <DispatchTimeMax>3</DispatchTimeMax>
                        <ListingDuration>Days_7</ListingDuration>
                        <ListingType>FixedPriceItem</ListingType>
                        <Location>London</Location>
                        <Quantity>1</Quantity>
                        <PictureDetails>
                            <PictureURL>https://portal-images.azureedge.net/auctions-2025/ibsia10300/images/24721dd0-fc7f-46cc-bd87-b2810182b0e6.jpg</PictureURL>
                        </PictureDetails>
                        <ShippingDetails>
                            <ShippingType>Flat</ShippingType>
                            <ShippingServiceOptions>
                                <ShippingService>UK_RoyalMailSecondClass</ShippingService>
                                <ShippingServiceCost currencyID="GBP">9.99</ShippingServiceCost>
                            </ShippingServiceOptions>
                        </ShippingDetails>
                        <ReturnPolicy>
                            <ReturnsAcceptedOption>ReturnsAccepted</ReturnsAcceptedOption>
                            <RefundOption>MoneyBack</RefundOption>
                            <ReturnsWithinOption>Days_30</ReturnsWithinOption>
                            <ShippingCostPaidByOption>Buyer</ShippingCostPaidByOption>
                        </ReturnPolicy>
                    </Item>
                </AddItemRequest>""".format(self.auth_token)

            # Bağlantı ayarları
            session = requests.Session()
            session.verify = False
            
            timeout = (30, 60)
            api_url = "https://api.sandbox.ebay.com/ws/api.dll"
            
            retries = Retry(
                total=5,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
            session.mount('https://', HTTPAdapter(max_retries=retries))
            
            response = session.post(
                api_url,
                headers=self.get_trading_headers(),
                data=xml_request.encode('utf-8'),
                timeout=timeout
            )
            
            if response.status_code == 200:
                # Parse XML response
                root = ET.fromstring(response.text)
                
                # Debug print
                print("XML Response:", response.text)
                
                # Check for Ack status
                ack = root.find(".//Ack")
                if ack is not None and ack.text == "Success":
                    item_id = root.find(".//ItemID")
                    if item_id is not None:
                        item_url = f"https://sandbox.ebay.com/itm/{item_id.text}"
                        return {
                            "success": True,
                            "item_id": item_id.text,
                            "item_url": item_url
                        }
                
                # If we get here, something went wrong
                error_msg = root.find(".//Errors/LongMessage")
                if error_msg is not None:
                    return {"success": False, "error": f"API Error: {error_msg.text}"}
                
                return {"success": False, "error": "Unknown error occurred"}
            else:
                return {"success": False, "error": f"HTTP Error: {response.status_code} - {response.text}"}

        except requests.exceptions.ConnectTimeout:
            return {"success": False, "error": "Bağlantı zaman aşımı - lütfen tekrar deneyin"}
        except requests.exceptions.RequestException as e:
            return {"success": False, "error": f"Bağlantı hatası: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": f"Beklenmeyen hata: {str(e)}"}

# Global instance
listing_service = EbayListingService() 