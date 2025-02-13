import openai
from typing import Dict, List, Tuple
import json
import hashlib
import os
from datetime import datetime, timedelta
import sqlite3

class ChatGPTManager:
    def __init__(self, api_key: str, cache_db: str = 'cache/chatgpt_cache.db'):
        self.api_key = api_key
        openai.api_key = api_key
        self.cache_db = cache_db
        self.setup_cache_db()
        
    def setup_cache_db(self):
        """Initialize SQLite cache database"""
        os.makedirs(os.path.dirname(self.cache_db), exist_ok=True)
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS response_cache (
                    query_hash TEXT PRIMARY KEY,
                    response TEXT,
                    timestamp DATETIME,
                    query_type TEXT
                )
            ''')

    def get_cache_key(self, query: str, query_type: str) -> str:
        """Generate unique cache key for a query"""
        return hashlib.md5(f"{query_type}:{query}".encode()).hexdigest()

    def get_cached_response(self, query: str, query_type: str) -> str:
        """Get cached response if exists and not expired"""
        cache_key = self.get_cache_key(query, query_type)
        with sqlite3.connect(self.cache_db) as conn:
            cursor = conn.execute(
                'SELECT response, timestamp FROM response_cache WHERE query_hash = ?', 
                (cache_key,)
            )
            result = cursor.fetchone()
            
            if result:
                response, timestamp = result
                cache_date = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                if datetime.now() - cache_date < timedelta(days=30):
                    return response
        return None

    def cache_response(self, query: str, query_type: str, response: str):
        """Cache the response"""
        cache_key = self.get_cache_key(query, query_type)
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO response_cache (query_hash, response, timestamp, query_type) VALUES (?, ?, ?, ?)',
                (cache_key, response, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), query_type)
            )

    def get_ebay_listing_content(self, title: str, description: str = None) -> Dict:
        """Get all required content for eBay listing"""
        query_type = 'ebay_listing'
        cached = self.get_cached_response(title, query_type)
        if cached:
            return json.loads(cached)

        prompts = [
            f"Write a 30-word technical sales description for: {title}",
            f"Extract only the brand name for: {title}",
            f"Extract only the model/part number for: {title}",
            f"What is the item type category for: {title}"
        ]

        responses = []
        for prompt in prompts:
            responses.append(self._make_api_call(prompt))

        result = {
            'technical_description': responses[0],
            'brand': responses[1],
            'model_number': responses[2],
            'item_type': responses[3]
        }

        self.cache_response(title, query_type, json.dumps(result))
        return result

    def get_website_listing_content(self, title: str) -> Dict:
        """Get content for website listing"""
        query_type = 'website_listing'
        cached = self.get_cached_response(title, query_type)
        if cached:
            return json.loads(cached)

        prompts = [
            f"Provide technical specifications in bullet points for: {title}",
            f"Extract category, make, and model for: {title} in JSON format"
        ]

        responses = []
        for prompt in prompts:
            responses.append(self._make_api_call(prompt))

        result = {
            'specifications': responses[0],
            'metadata': json.loads(responses[1])
        }

        self.cache_response(title, query_type, json.dumps(result))
        return result

    def get_shipping_info(self, title: str) -> Dict:
        """Get size and weight estimation"""
        query_type = 'shipping_info'
        cached = self.get_cached_response(title, query_type)
        if cached:
            return json.loads(cached)

        prompt = f"Estimate dimensions (cm) and weight (kg) for: {title}. Format: JSON with keys: length, width, height, weight"
        response = self._make_api_call(prompt)
        
        try:
            shipping_info = json.loads(response)
            # Add 5kg to weight as per specification
            shipping_info['weight'] += 5
            
            # Determine shipping category
            if (shipping_info['weight'] <= 15 and 
                max(shipping_info['length'], shipping_info['width'], shipping_info['height']) <= 120):
                category = 'small'
            elif shipping_info['weight'] <= 30:
                category = 'medium'
            else:
                category = 'large'
                
            shipping_info['category'] = category
            
            self.cache_response(title, query_type, json.dumps(shipping_info))
            return shipping_info
        except:
            return {'error': 'Could not parse shipping information'}

    def _make_api_call(self, prompt: str) -> str:
        """Make API call to ChatGPT with minimal tokens"""
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a precise technical writer. Respond only with the requested information, no explanations."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"ChatGPT API Error: {str(e)}")
            return "" 