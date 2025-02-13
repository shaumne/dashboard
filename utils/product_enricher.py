from utils.chatgpt_manager import ChatGPTManager
from typing import Dict
import os

class ProductEnricher:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        self.chatgpt = ChatGPTManager(api_key)

    def enrich_product(self, product_data: Dict) -> Dict:
        """Enrich product data with ChatGPT generated content"""
        title = product_data['title']
        
        # Cache'den veya API'den bilgileri al
        enriched_data = {
            'technical_description': self.chatgpt.get_technical_description(title),
            'specifications': self.chatgpt.get_specifications(title),
            'model_number': self.chatgpt.get_model_number(title),
            'brand': self.chatgpt.get_brand(title)
        }
        
        return {**product_data, **enriched_data} 