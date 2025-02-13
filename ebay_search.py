import csv
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
from tqdm import tqdm
import re
from difflib import SequenceMatcher
from selenium.webdriver.common.keys import Keys
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor

def read_lots_details():
    """Read products from lots_details.csv"""
    products = []
    try:
        with open('data/output/lots_details.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            products = list(reader)
        print(f"Total {len(products)} products loaded")
        return products
    except Exception as e:
        print(f"CSV reading error: {str(e)}")
        return []

class EbaySearchManager:
    def __init__(self):
        self.setup_driver()
        self.thread_count = 10
        self.result_queue = Queue()

    def setup_driver(self):
        """Configure Chrome driver"""
        self.chrome_options = webdriver.ChromeOptions()
        self.chrome_options.add_argument('--headless=new')
        self.chrome_options.add_argument('--disable-gpu')
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')

    def extract_price(self, price_text):
        """Extract numerical value from price text"""
        try:
            # Remove currency symbol and any extra spaces
            price_text = price_text.replace('£', '').strip()
            
            # Handle price ranges (take the lower price)
            if ' to ' in price_text:
                price_text = price_text.split(' to ')[0]
            
            # Remove any commas and convert to float
            price = float(price_text.replace(',', ''))
            
            print(f"Successfully extracted price: {price} from {price_text}")
            return price
            
        except Exception as e:
            print(f"Price extraction error: {str(e)} for text: {price_text}")
            return None

    def check_title_similarity(self, listing_title, original_title):
        """Check if listing title is similar enough to original title"""
        return SequenceMatcher(None, listing_title.lower(), original_title.lower()).ratio() > 0.8

    def clean_product_title(self, title):
        """Clean product title for better search results"""
        # Remove text within parentheses
        title = re.sub(r'\([^)]*\)', '', title)
        
        # Remove common unnecessary words and characters
        unnecessary_words = ['new', 'used', 'refurbished', 'untested', 'faulty', 
                            'broken', 'spares', 'repairs', 'working', 'tested',
                            '[', ']', '*', '/', '\\', '&', '1 block', 'block']
        
        cleaned_title = title.lower()
        
        # Remove unnecessary words
        for word in unnecessary_words:
            cleaned_title = cleaned_title.replace(word.lower(), '')
        
        # Remove multiple spaces and trim
        cleaned_title = ' '.join(cleaned_title.split())
        
        # Keep only meaningful product information
        words = cleaned_title.split()
        important_words = []
        
        # Keep brand name and key product identifiers
        for i, word in enumerate(words):
            # Skip single digits or numbers at the end
            if word.isdigit() and len(word) == 1:
                continue
            important_words.append(word)
        
        return ' '.join(important_words)

    def search_google_shopping(self, title):
        """Search Google Shopping for price backup with average pricing"""
        driver = webdriver.Chrome(options=self.chrome_options)
        try:
            # Clean the title for better search results
            cleaned_title = self.clean_product_title(title)
            print(f"\nSearching Google Shopping for: {cleaned_title}")
            
            # Go to Google Shopping with UK settings
            driver.get("https://shopping.google.co.uk")
            time.sleep(2)
            
            # Find and use the search box
            search_box = driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(cleaned_title)
            search_box.send_keys(Keys.RETURN)
            time.sleep(2)
            
            # Store search URL
            search_url = driver.current_url
            
            prices = []
            price_elements = driver.find_elements(By.CSS_SELECTOR, "span.T14wmb")  # Updated selector for prices
            
            # Collect all valid prices
            for element in price_elements[:10]:
                try:
                    price_text = element.text
                    if '£' in price_text:  # Only get GBP prices
                        price = self.extract_price(price_text)
                        if price and price > 0:
                            prices.append(price)
                except:
                    continue
            
            if prices:
                # Calculate average price
                avg_price = sum(prices) / len(prices)
                # Remove outliers (prices that are 50% above or below average)
                filtered_prices = [p for p in prices if 0.5 * avg_price <= p <= 1.5 * avg_price]
                
                if filtered_prices:
                    final_avg_price = sum(filtered_prices) / len(filtered_prices)
                    suggested_price = final_avg_price * 1.2  # 20% higher than average price
                    
                    return {
                        'ebay_url': '',  # Will be filled by eBay search
                        'google_url': search_url,  # Added Google search URL
                        'ebay_lowest_price': f"£{final_avg_price:.2f}",
                        'suggested_price': f"£{suggested_price:.2f}",
                        'all_prices': [f"£{p:.2f}" for p in prices],
                        'price_source': 'google'
                    }
            
        except Exception as e:
            print(f"Google Shopping search error: {str(e)}")
        finally:
            driver.quit()
        
        return None

    def process_batch(self, batch):
        """Process a batch of products"""
        try:
            driver = webdriver.Chrome(options=self.chrome_options)
            
            for product in batch:
                try:
                    title = product['name']
                    print(f"\nProcessing: {title}")
                    
                    result = self.search_single_product(driver, title)
                    if result:
                        print(f"Found result for {title}:")
                        print(f"Price: {result.get('ebay_lowest_price', 'Not Found')}")
                        print(f"Link: {result.get('ebay_product_link', 'Not Found')}")
                        
                        # Queue'ya eklerken kontrol et
                        print(f"Adding to queue: {title}")
                        self.result_queue.put((title, result))
                        print(f"Added to queue successfully: {title}")
                    else:
                        print(f"No result found for: {title}")
                        # Boş sonuç da ekleyelim
                        empty_result = {
                            'ebay_url': '',
                            'ebay_product_link': '',
                            'google_url': '',
                            'ebay_lowest_price': '',
                            'suggested_price': '',
                            'all_prices': [],
                            'price_source': ''
                        }
                        self.result_queue.put((title, empty_result))
                    
                except Exception as e:
                    print(f"Error processing product {title}: {str(e)}")
                    continue
                
            driver.quit()
            
        except Exception as e:
            print(f"Batch processing error: {str(e)}")

    def search_single_product(self, driver, title):
        """Search for a single product using provided driver"""
        try:
            wait = WebDriverWait(driver, 10)
            
            cleaned_title = self.clean_product_title(title)
            search_url = f"https://www.ebay.co.uk/sch/i.html?_nkw={cleaned_title.replace(' ', '+')}&LH_Complete=1&LH_Sold=1"
            
            driver.get(search_url)
            time.sleep(3)

            best_match = None
            highest_similarity = 0
            best_price = None
            best_link = None
            returning_link = None  # Returning result için link
            all_prices = []

            try:
                listings = wait.until(EC.presence_of_all_elements_located((
                    By.CSS_SELECTOR, "li.s-item"
                )))

                for listing in listings[:10]:
                    try:
                        # Get title and link
                        title_elem = listing.find_element(By.CSS_SELECTOR, "div.s-item__title")
                        listing_title = title_elem.text
                        
                        # Her listing için linki al
                        link_elem = listing.find_element(By.CSS_SELECTOR, "a.s-item__link")
                        product_link = link_elem.get_attribute('href')
                        
                        # İlk returning result linkini kaydet
                        if not returning_link:
                            returning_link = product_link
                            print(f"\nSaved first returning result link: {returning_link}")
                        
                        # Try multiple price selectors
                        price_text = None
                        for selector in [
                            "span.s-item__price",
                            "span.POSITIVE",
                            "span.s-item__price span.POSITIVE",
                            "span.s-item__price span"
                        ]:
                            try:
                                price_elem = listing.find_element(By.CSS_SELECTOR, selector)
                                price_text = price_elem.text.strip()
                                if price_text and '£' in price_text:
                                    break
                            except:
                                continue
                        
                        if not price_text:
                            continue
                        
                        # Check if item is sold
                        try:
                            sold_elem = listing.find_element(
                                By.CSS_SELECTOR, "span.POSITIVE:not(.s-item__price span.POSITIVE)"
                            )
                            is_sold = "Sold" in sold_elem.text
                        except:
                            try:
                                sold_elem = listing.find_element(
                                    By.CSS_SELECTOR, "span.s-item__caption--signal"
                                )
                                is_sold = "Sold" in sold_elem.text
                            except:
                                is_sold = False
                        
                        if is_sold and price_text:
                            price = self.extract_price(price_text)
                            if price:
                                similarity = SequenceMatcher(None, listing_title.lower(), title.lower()).ratio()
                                print(f"\nFound listing: {listing_title}")
                                print(f"Similarity: {similarity:.2f}")
                                print(f"Price: £{price:.2f}")
                                print(f"Link: {product_link}")
                                
                                # En iyi eşleşmeyi güncelle
                                if similarity > highest_similarity and similarity > 0.5:
                                    highest_similarity = similarity
                                    best_match = listing
                                    best_price = price
                                    best_link = product_link
                                    print("-> New best match!")
                                
                                # Tüm fiyatları kaydet
                                all_prices.append(f"£{price:.2f}")
                    
                    except Exception as e:
                        print(f"Error processing listing: {str(e)}")
                        continue

                # Sonuç oluştur
                if best_match and best_price:
                    print("\nUsing best match result")
                    suggested_price = best_price * 0.98
                    result = {
                        'ebay_url': best_link,
                        'google_url': '',
                        'ebay_lowest_price': f"£{best_price:.2f}",
                        'suggested_price': f"£{suggested_price:.2f}",
                        'all_prices': all_prices,
                        'price_source': 'ebay_sold'
                    }
                elif returning_link:
                    print("\nNo best match found, using returning result")
                    result = {
                        'ebay_url': returning_link,
                        'google_url': '',
                        'ebay_lowest_price': '',
                        'suggested_price': '',
                        'all_prices': all_prices,
                        'price_source': 'ebay_sold'
                    }
                else:
                    print("\nNo suitable links found")
                    result = {
                        'ebay_url': '',
                        'google_url': '',
                        'ebay_lowest_price': '',
                        'suggested_price': '',
                        'all_prices': [],
                        'price_source': ''
                    }

                print("\nReturning result:")
                print(result)
                
                return result
                
            except Exception as e:
                print(f"Error finding listings: {str(e)}")
                return None
            
        except Exception as e:
            print(f"Error searching for {title}: {str(e)}")
            return None

    def process_all_products(self, products):
        """Process all products using thread pool with improved result handling"""
        try:
            # Split products into batches
            batch_size = max(1, len(products) // self.thread_count)
            batches = [products[i:i + batch_size] for i in range(0, len(products), batch_size)]
            
            print(f"\nProcessing {len(products)} products in {len(batches)} batches")
            
            # Process batches in parallel
            with ThreadPoolExecutor(max_workers=self.thread_count) as executor:
                executor.map(self.process_batch, batches)
            
            # Collect and verify results
            results = {}
            print("\nCollecting results from queue...")
            while not self.result_queue.empty():
                title, result = self.result_queue.get()
                if result:  # Only add valid results
                    print(f"Found result for: {title}")
                    print(f"Price: {result.get('ebay_lowest_price', 'Not Found')}")
                    print(f"Link: {result.get('ebay_product_link', 'Not Found')}")  # Link'i de yazdır
                    results[title] = result
            
            print(f"\nTotal results collected: {len(results)}")
            return results
            
        except Exception as e:
            print(f"\nError in process_all_products: {str(e)}")
            return {}

    def calculate_total_cost(self, title):
        """Calculate total cost including fees"""
        try:
            # Get product details from lots_details.csv
            with open('lots_details.csv', 'r') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    if row['title'] == title:
                        bid = float(str(row['current_bid']).replace('GBP', '').strip())
                        vat = bid * (float(row['vat_rate']) / 100)
                        commission = bid * (float(row['commission']) / 100)
                        return bid + vat + commission
            return None
        except Exception as e:
            print(f"Cost calculation error: {str(e)}")
            return None

def save_results(products):
    """Save results to CSV with detailed logging"""
    try:
        print("\nSaving results to CSV...")
        fieldnames = [
            'name', 'current_bid', 'opening_bid', 'estimate_bid',
            'buy_it_now', 'end_time', 'description', 'images',
            'url', 'commission', 'vat_rate', 'has_buy_it_now',
            'has_estimate', 'has_current_bid', 'has_opening_bid',
            # Eski alanlar
            'ebay_lowest_price', 'suggested_price', 'price_source',
            'ebay_url', 'google_url', 'all_prices'
        ]
        
        # Debug: Print sample of data before saving
        print("\nSample of data being saved:")
        for product in products[:2]:
            print(f"\nProduct: {product.get('name', '')}")
            print(f"eBay Price: {product.get('ebay_lowest_price', 'Not Set')}")
            print(f"Suggested Price: {product.get('suggested_price', 'Not Set')}")
            print(f"Price Source: {product.get('price_source', 'Not Set')}")
        
        # Count products with prices
        products_with_prices = sum(1 for p in products if p.get('ebay_lowest_price') not in [None, '', 'Not Found'])
        print(f"\nTotal products with prices: {products_with_prices} out of {len(products)}")
        
        with open('data/output/lots_details_with_ebay.csv', 'w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            
            for product in products:
                # Ensure all required fields exist
                for field in fieldnames:
                    if field not in product:
                        product[field] = ''
                
                # Convert None values to empty strings
                for key in product:
                    if product[key] is None:
                        product[key] = ''
                
                writer.writerow(product)
            
        print("\nResults saved successfully!")
        
        # Verify saved data
        print("\nVerifying saved data...")
        with open('data/output/lots_details_with_ebay.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            saved_products = list(reader)
            prices_found = sum(1 for p in saved_products if p['ebay_lowest_price'] not in ['', 'Not Found'])
            print(f"Verified prices in CSV: {prices_found} products have prices")
            
    except Exception as e:
        print(f"\nError saving results: {str(e)}")
        print("Full error traceback:")
        import traceback
        traceback.print_exc()

def main():
    """Main process flow with improved error handling"""
    try:
        products = read_lots_details()
        if not products:
            print("No products loaded!")
            return
        
        print(f"\nLoaded {len(products)} products")
        
        ebay_manager = EbaySearchManager()
        results = ebay_manager.process_all_products(products)
        
        print(f"\nProcessing complete. Found {len(results)} results")
        
        # Update products with results - daha detaylı logging
        updated_count = 0
        for product in products:
            title = product['name']
            if title in results and results[title]:
                print(f"\nUpdating product: {title}")
                print(f"Before update: {product}")
                product.update(results[title])
                print(f"After update: {product}")
                updated_count += 1
            else:
                print(f"\nNo result found for product: {title}")
        
        print(f"\nUpdated {updated_count} products with new prices")
        
        # CSV kaydetmeden önce kontrol
        print("\nChecking products before saving:")
        for product in products[:5]:  # İlk 5 ürünü kontrol et
            print(f"\nProduct: {product['name']}")
            print(f"eBay Link: {product.get('ebay_product_link', 'Not Set')}")
            print(f"eBay Price: {product.get('ebay_lowest_price', 'Not Set')}")
        
        save_results(products)
        
    except Exception as e:
        print(f"\nMain process error: {str(e)}")
        print("Full error traceback:")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 