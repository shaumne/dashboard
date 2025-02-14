import csv
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait 
from selenium.webdriver.support import expected_conditions as EC
import time
import logging
from queue import Queue
import threading
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IBidderScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.thread_local = threading.local()
        self.max_workers = 1

    def get_session(self):
        """Her thread için ayrı bir session oluştur"""
        if not hasattr(self.thread_local, "session"):
            self.thread_local.session = requests.Session()
            self.thread_local.session.headers.update(self.headers)
        return self.thread_local.session

    def get_driver(self):
        """Her thread için ayrı bir Selenium driver oluştur"""
        if not hasattr(self.thread_local, "driver"):
            chrome_options = Options()
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--headless')
            self.thread_local.driver = webdriver.Chrome(options=chrome_options)
            self.thread_local.driver.implicitly_wait(10)
        return self.thread_local.driver

    def process_page(self, page_number, base_url):
        """Tek bir sayfayı işle"""
        session = self.get_session()
        page_url = f"{base_url}&page={page_number}" if "?" in base_url else f"{base_url}?page={page_number}"
        
        try:
            response = session.get(page_url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            auction_links = soup.find_all('a', class_='click-track')
            
            urls = set()
            for link in auction_links:
                auction_url = link.get('href')
                if auction_url:
                    if not auction_url.startswith('http'):
                        auction_url = f"https://www.i-bidder.com{auction_url}"
                    urls.add(auction_url)
            
            return list(urls)
        except Exception as e:
            logger.error(f"Sayfa işleme hatası {page_number}: {str(e)}")
            return []

    def process_product(self, url):
        """Process a single product"""
        session = self.get_session()
        try:
            logger.info(f"Processing product: {url}")
            response = session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            product_data = {
                'title': 'Unknown',
                'url': url,
                'image_url': ''
            }
            
            # Get title
            title_elem = soup.find('h1')
            if title_elem:
                product_data['title'] = title_elem.text.strip()
            
            # Get image
            img_elem = soup.find('img', {'class': 'lot-image'})
            if img_elem:
                product_data['image_url'] = img_elem.get('src', '')
            
            logger.debug(f"Product data collected: {product_data}")
            return product_data
            
        except Exception as e:
            logger.error(f"Error processing product {url}: {str(e)}")
            # Hata durumunda bile URL'yi kaydet
            return {
                'title': 'Error',
                'url': url,
                'image_url': ''
            }

    def process_lot_details(self, url):
        """Tek bir lot detayını işle"""
        driver = self.get_driver()
        try:
            return self.get_lot_details(driver, {'url': url})
        except Exception as e:
            logger.error(f"Lot detay hatası {url}: {str(e)}")
            return None

    def create_products_csv(self):
        """Create products.csv with single thread processing"""
        try:
            logger.info("Starting product collection process...")
            
            # URL'leri topla
            all_auction_urls = []
            urls = self.get_urls_from_file('data/input/urls.txt')
            
            for url in urls:
                try:
                    page_urls = self.get_auction_urls(url, '')
                    all_auction_urls.extend(page_urls)
                except Exception as e:
                    logger.error(f"Error collecting URLs from {url}: {str(e)}")
            
            all_auction_urls = list(set(all_auction_urls))  # Tekrarları temizle
            logger.info(f"Total unique URLs collected: {len(all_auction_urls)}")
            
            # Ürünleri işle
            products = []
            with tqdm(total=len(all_auction_urls), desc="Processing products") as pbar:
                for url in all_auction_urls:
                    try:
                        product = self.process_product(url)
                        if product:
                            products.append(product)
                        pbar.update(1)
                        
                        # Her 50 üründe bir log
                        if len(products) % 50 == 0:
                            logger.info(f"Processed {len(products)}/{len(all_auction_urls)} products")
                            
                        # Her 100 üründe bir kaydet
                        if len(products) % 100 == 0:
                            self.save_to_csv(products, 'data/output/products.csv')
                            
                    except Exception as e:
                        logger.error(f"Error processing URL {url}: {str(e)}")
                        continue
            
            # Kalan ürünleri kaydet
            if products:
                self.save_to_csv(products, 'data/output/products.csv')
            
            logger.info(f"Successfully processed {len(products)} products")
            
        except Exception as e:
            logger.error(f"Critical error in create_products_csv: {str(e)}")
            raise

    def save_to_csv(self, products, filename):
        """Save products to CSV file"""
        try:
            mode = 'w' if not os.path.exists(filename) else 'a'
            with open(filename, mode, newline='', encoding='utf-8') as csvfile:
                fieldnames = ['title', 'url', 'image_url']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                if mode == 'w':  # Yeni dosya ise başlık yaz
                    writer.writeheader()
                
                writer.writerows(products)
                
            logger.info(f"Saved {len(products)} products to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving to CSV: {str(e)}")

    def create_lots_details(self):
        """Create lots_details.csv with batch saving"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--window-size=1920,1080')
            
            products = []
            with open('data/output/products.csv', 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                products = list(reader)
            
            logger.info(f"Found {len(products)} products to process")
            
            driver = webdriver.Chrome(options=chrome_options)
            driver.implicitly_wait(10)
            
            results = []
            batch_size = 20  # Her 20 üründe bir kaydet
            fieldnames = [
                'name', 'current_bid', 'opening_bid', 'estimate_bid',
                'buy_it_now', 'end_time', 'description', 'images', 'url',
                'commission', 'vat_rate', 'has_buy_it_now', 'has_estimate',
                'has_current_bid', 'has_opening_bid'
            ]
            
            # CSV dosyasını oluştur ve başlıkları yaz
            with open('data/output/lots_details.csv', 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
            
            for index, product in enumerate(tqdm(products, desc="Processing lots")):
                try:
                    result = self.get_lot_details(driver, product)
                    if result:
                        results.append(result)
                    
                    # Her 20 üründe bir veya son ürünse kaydet
                    if (len(results) >= batch_size) or (index == len(products) - 1):
                        logger.info(f"Saving batch of {len(results)} products to CSV...")
                        with open('data/output/lots_details.csv', 'a', newline='', encoding='utf-8') as file:
                            writer = csv.DictWriter(file, fieldnames=fieldnames)
                            writer.writerows(results)
                        
                        # Kaydedilen ürünleri temizle
                        results = []
                        logger.info(f"Batch saved. Total progress: {index + 1}/{len(products)}")
                    
                    time.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    logger.error(f"Error processing lot {index + 1}: {str(e)}")
                    continue
            
            driver.quit()
            logger.info("Lots details collection completed!")
            
        except Exception as e:
            logger.error(f"Error creating lots_details.csv: {str(e)}")
            if 'driver' in locals():
                driver.quit()
            raise

    def cleanup(self):
        """Thread-local kaynakları temizle"""
        if hasattr(self.thread_local, "driver"):
            self.thread_local.driver.quit()

    def __del__(self):
        """Destructor: Kaynakları temizle"""
        self.cleanup()

    def scrape_all(self):
        """Main workflow with detailed progress tracking"""
        try:
            total_steps = 2
            current_step = 1
            
            logger.info("=== Starting IBidder Scraping Process ===")
            logger.info(f"Step {current_step}/{total_steps}: Creating products.csv")
            start_time = time.time()
            self.create_products_csv()
            
            current_step += 1
            logger.info(f"\nStep {current_step}/{total_steps}: Creating lots_details.csv")
            self.create_lots_details()
            
            end_time = time.time()
            total_time = end_time - start_time
            logger.info("\n=== Scraping Process Completed ===")
            logger.info(f"Total execution time: {total_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Critical error in main workflow: {str(e)}")
            raise

    def get_lot_details(self, driver, product):
        """Get lot details using Selenium"""
        try:
            logger.info(f"\nProcessing: {product['url']}")
            driver.get(product['url'])
            wait = WebDriverWait(driver, 10)
            
            lot_data = {
                'name': 'Unknown',
                'current_bid': 'No Bid',
                'opening_bid': 'Unknown',
                'estimate_bid': 'Unknown',
                'buy_it_now': 'Unknown',
                'end_time': 'Unknown',
                'description': 'Unknown',
                'images': [],
                'url': product['url'],
                'commission': '0',
                'vat_rate': '0',
                'has_buy_it_now': '',  # Boş string ile başlat
                'has_estimate': '',
                'has_current_bid': '',
                'has_opening_bid': ''
            }
            
            try:
                # Name
                name = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[1]/div/div[2]/div/h1')
                if name:
                    lot_data['name'] = name.text.strip()
                
                # Fees butonuna tıkla
                fees_button = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[5]/div/div[1]/span')
                fees_button.click()
                time.sleep(1)
                
                # Commission ve VAT bilgilerini al
                commission = driver.find_element(By.ID, 'commissionsExVAT')
                vat = driver.find_element(By.ID, 'additionalFeeVatRate')
                
                if commission:
                    lot_data['commission'] = commission.text.replace('%', '').strip()
                if vat:
                    lot_data['vat_rate'] = vat.text.replace('%', '').strip()
                
                # Buy It Now kontrolü
                try:
                    buy_now = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/div/div[2]/div[2]/span/span[1]')
                    if buy_now and buy_now.text.strip():  # Boş değilse
                        lot_data['buy_it_now'] = buy_now.text.strip()
                        lot_data['has_buy_it_now'] = 'TRUE'
                except:
                    pass
                
                # Estimate Bid kontrolü
                try:
                    estimate = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[4]/div[2]')
                    if estimate and estimate.text.strip():  # Boş değilse
                        lot_data['estimate_bid'] = estimate.text.strip()
                        lot_data['has_estimate'] = 'TRUE'
                except:
                    pass
                
                # Current Bid kontrolü
                try:
                    current_bid = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span/strong')
                    if current_bid and current_bid.text.strip():  # Boş değilse
                        lot_data['current_bid'] = current_bid.text.strip()
                        lot_data['has_current_bid'] = 'TRUE'
                except:
                    pass
                
                # Opening Bid kontrolü - Sadece sayıyı al
                try:
                    opening_bid = driver.find_element(By.CSS_SELECTOR, 'span.minBidAmount')
                    if opening_bid and opening_bid.text.strip():  # Boş değilse
                        lot_data['opening_bid'] = opening_bid.text.strip()
                        lot_data['has_opening_bid'] = 'TRUE'
                except:
                    pass
                
                # End Time
                end_time = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]')
                if end_time:
                    lot_data['end_time'] = end_time.text.strip()
                
                # Description
                description = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[9]/div/div[1]/div/div[2]')
                if description:
                    lot_data['description'] = description.text.strip()
                
                # Images
                image_container = driver.find_element(By.XPATH, '/html/body/div[1]/main/div/div[6]/div[1]/div/div[1]')
                images = image_container.find_elements(By.TAG_NAME, 'img')
                lot_data['images'] = [img.get_attribute('src') for img in images if img.get_attribute('src')]
                
            except Exception as e:
                logger.error(f"Error getting element: {str(e)}")
            
            return lot_data
            
        except Exception as e:
            logger.error(f"Error processing lot details: {str(e)}")
            return None

    def get_category_from_url(self, url):
        """Extract category code from URL"""
        try:
            match = re.search(r'category[Cc]ode=([A-Z]+)', url)
            if match:
                return match.group(1).upper()
        except Exception as e:
            logger.error(f"Error extracting category code: {str(e)}")
        return None

    def get_urls_from_file(self, filename):
        """Read URLs from file"""
        try:
            with open(filename, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        except Exception as e:
            logger.error(f"Error reading URLs file: {str(e)}")
            return []

    def get_auction_urls(self, url, target_category):
        """Collects auction URLs from main page"""
        try:
            logger.info(f"Checking URL: {url}")
            
            # Get page number
            current_page = 1
            if "page=" in url:
                current_page = int(url.split("page=")[1])
            
            matching_urls = []
            
            while current_page <= 2:
                try:
                    # Check current page
                    page_url = url.replace(f"page={current_page-1}", f"page={current_page}") if "page=" in url else f"{url}&page={current_page}"
                    
                    logger.info(f"Processing page {current_page}: {page_url}")
                    response = self.session.get(page_url)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # Find all <a> tags with class='click-track'
                    auction_links = soup.find_all('a', class_='click-track')
                    
                    # Collect auction URLs from the page
                    page_urls = []
                    for link in auction_links:
                        try:
                            # Get href attribute
                            auction_url = link.get('href')
                            if auction_url:
                                if not auction_url.startswith('http'):
                                    auction_url = f"https://www.i-bidder.com{auction_url}"
                                page_urls.append(auction_url)
                        except Exception as e:
                            logger.warning(f"Error processing link: {str(e)}")
                            continue
                    
                    # Remove duplicate URLs
                    page_urls = list(set(page_urls))
                    matching_urls.extend(page_urls)
                    
                    logger.info(f"Page {current_page}: Found {len(page_urls)} auction URLs")
                    
                    # If no URLs found on page, end loop
                    if len(page_urls) == 0:
                        logger.warning(f"No URLs found on page {current_page}, stopping process")
                        break
                    
                    current_page += 1
                    time.sleep(1)  # Rate limiting delay
                    
                except Exception as e:
                    logger.error(f"Error processing page {current_page}: {str(e)}")
                    break
            
            # Remove all duplicate URLs
            matching_urls = list(set(matching_urls))
            logger.info(f"Total unique auction URLs found: {len(matching_urls)}")
            return matching_urls
            
        except Exception as e:
            logger.error(f"Error collecting auction URLs: {str(e)}")
            if not url.startswith('http'):
                url = f"https://www.i-bidder.com{url}"
            return [url]

def run_scraper():
    """Ana scraping işlemini başlatan fonksiyon"""
    try:
        scraper = IBidderScraper()
        
        logger.info("Step 1: Creating products.csv...")
        scraper.create_products_csv()
        
        logger.info("\nStep 2: Creating lots_details.csv...")
        scraper.create_lots_details()
        
        logger.info("All processes completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Error in scraping process: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    run_scraper() 