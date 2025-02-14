import csv
import re
from concurrent.futures import ThreadPoolExecutor
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IBidderScraper:
    def __init__(self):
        # Requests session için headers
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def scrape_all(self):
        """Ana iş akışı"""
        try:
            logger.info("Step 1: Creating products.csv...")
            self.create_products_csv()
            
            logger.info("\nStep 2: Creating lots_details.csv...")
            self.create_lots_details()
            
            logger.info("All done!")
            
        except Exception as e:
            logger.error(f"Error in scrape_all: {str(e)}")
            raise

    def create_lots_details(self):
        """Second step: Create lots_details.csv using Selenium"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
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
            for product in tqdm(products, desc="Processing lots"):
                try:
                    result = self.get_lot_details(driver, product)
                    if result:
                        results.append(result)
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error processing lot: {str(e)}")
                    continue
            
            driver.quit()
            
            if results:
                fieldnames = [
                    'name', 'current_bid', 'opening_bid', 'estimate_bid',
                    'buy_it_now', 'end_time', 'description', 'images', 'url',
                    'commission', 'vat_rate', 'has_buy_it_now', 'has_estimate',
                    'has_current_bid', 'has_opening_bid'
                ]
                
                with open('data/output/lots_details.csv', 'w', newline='', encoding='utf-8') as file:
                    writer = csv.DictWriter(file, fieldnames=fieldnames)
                    writer.writeheader()
                    for result in results:
                        writer.writerow(result)
                
                logger.info(f"\nProcessed {len(results)} lots successfully!")
            
        except Exception as e:
            logger.error(f"Error creating lots_details.csv: {str(e)}")
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

    def create_products_csv(self):
        """First step: Create products.csv with URLs and titles"""
        try:
            with open('data/output/products.csv', 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['title', 'url', 'image_url']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                # URL'leri oku
                urls = self.get_urls_from_file('data/input/urls.txt')
                logger.info(f"Number of URLs to read: {len(urls)}")
                
                # Auction URL'lerini topla
                all_auction_urls = []
                for url in urls:
                    target_category = self.get_category_from_url(url)
                    if not target_category:
                        logger.warning(f"Category code not found: {url}")
                        continue
                        
                    logger.info(f"Processing URL: {url}")
                    logger.info(f"Target category: {target_category}")
                    
                    auction_urls = self.get_auction_urls(url, target_category)
                    all_auction_urls.extend(auction_urls)
                
                logger.info(f"\nTotal auction URLs found: {len(all_auction_urls)}")
                
                # Her URL'yi sırayla işle
                for auction_url in tqdm(all_auction_urls, desc="Processing auctions"):
                    try:
                        products = self.get_product_details(auction_url)
                        if products:
                            for product in products:
                                writer.writerow(product)
                        time.sleep(1)  # Her istek arasında 1 saniye bekle
                    except Exception as e:
                        logger.error(f"Error processing auction: {str(e)}")
                
                logger.info("products.csv created successfully!")
                
        except Exception as e:
            logger.error(f"Error creating products.csv: {str(e)}")
            raise

    def get_product_details(self, url):
        """Get product details using requests"""
        try:
            logger.info(f"\nChecking auction: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            products = []
            
            # Find all product containers
            lot_divs = soup.find_all('div', class_='lot-single')
            
            for lot in lot_divs:
                product_data = {}
                
                # Get product link and image
                product_link = lot.find('a', class_='click-track', 
                                      attrs={'data-click-type': 'image'})
                
                if product_link:
                    # Get URL
                    product_url = product_link.get('href')
                    if product_url.startswith('/'):
                        product_url = f"https://www.i-bidder.com{product_url}"
                    product_data['url'] = product_url
                    
                    # Get image and title
                    product_img = product_link.find('img')
                    if product_img:
                        product_data['image_url'] = product_img.get('src', '')
                        product_data['title'] = product_img.get('alt', '').strip()
                
                if product_data:
                    products.append(product_data)
            
            return products
            
        except Exception as e:
            logger.error(f"Error getting product details: {str(e)}")
            return []

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
        """Ana sayfadaki açık artırma URL'lerini toplar"""
        try:
            logger.info(f"URL kontrol ediliyor: {url}")
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            auction_summaries = soup.find_all('div', class_='auction-summary-standard')
            
            matching_urls = []
            
            for auction in auction_summaries:
                # "Coming soon" kontrolü
                button = auction.find('a', class_='button')
                if button and 'Coming soon' in button.text.strip():
                    continue
                
                # Auction link kontrolü
                auction_link = auction.find('a', class_='auction-image-container')
                if auction_link and auction_link.get('href'):
                    base_url = auction_link.get('href')
                    if base_url.startswith('/'):
                        base_url = f"https://www.i-bidder.com{base_url}"
                    
                    final_url = f"{base_url}/search-filter?mastercategorycode={target_category}"
                    matching_urls.append(final_url)
            
            logger.info(f"Found {len(matching_urls)} auction URLs")
            return matching_urls
            
        except Exception as e:
            logger.error(f"Auction URLs alınırken hata: {str(e)}")
            return []

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