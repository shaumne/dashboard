import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
import time
import threading
from queue import Queue
import csv
from datetime import datetime
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

class PriceMonitor:
    def __init__(self, driver_count=5, tabs_per_driver=5):
        self.driver_count = driver_count
        self.tabs_per_driver = tabs_per_driver
        self.drivers = []
        self.stop_event = threading.Event()
        self.url_queue = Queue()
        self.results_lock = threading.Lock()
        self.results = {}
        self.csv_file = 'data/check/published_products.csv'
        self.settings_file = 'config/settings.json'
        
        # Settings'den email bilgilerini al
        with open(self.settings_file, 'r') as f:
            self.settings = json.load(f)
        
        # CSV dosyası yoksa veya boşsa, başlangıç yapısını oluştur
        if not os.path.exists(self.csv_file) or os.path.getsize(self.csv_file) == 0:
            columns = ['title', 'auction_url', 'woo_product_id', 'product_url', 
                      'current_price', 'last_price', 'last_check']
            self.df = pd.DataFrame(columns=columns)
            self.df.to_csv(self.csv_file, index=False)
        else:
            # CSV'yi DataFrame olarak yükle
            self.df = pd.read_csv(self.csv_file)
            
            # Yeni kolonları ekle (yoksa)
            if 'current_price' not in self.df.columns:
                self.df['current_price'] = None
            if 'last_price' not in self.df.columns:
                self.df['last_price'] = None
            if 'last_check' not in self.df.columns:
                self.df['last_check'] = None
            
            # Değişiklikleri kaydet
            self.df.to_csv(self.csv_file, index=False)

    def send_email_alert(self, product_title, old_price, new_price, product_url):
        """Fiyat değişikliği için email gönder"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.settings['notification_email']
            msg['To'] = self.settings['notification_email']
            msg['Subject'] = f"Price Change Alert: {product_title}"
            
            body = f"""
            Price change detected for: {product_title}
            Old Price: £{old_price}
            New Price: £{new_price}
            Product URL: {product_url}
            
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Email gönderme işlemi (SMTP ayarlarını settings.json'dan al)
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.settings['notification_email'], self.settings['email_password'])
            text = msg.as_string()
            server.sendmail(self.settings['notification_email'], self.settings['notification_email'], text)
            server.quit()
            
            print(f"Email sent for price change: {product_title}")
            
        except Exception as e:
            print(f"Email sending error: {str(e)}")

    def update_csv(self, url, current_price):
        """CSV'deki fiyat bilgisini güncelle"""
        try:
            with self.results_lock:
                # URL'ye göre ilgili satırı bul
                mask = self.df['auction_url'] == url
                
                if not mask.any():
                    return
                
                row = self.df.loc[mask].iloc[0]
                old_price = row.get('current_price')
                
                # Fiyatı temizle ve float'a çevir
                if current_price not in ['N/A', None, '']:
                    try:
                        clean_price = current_price.replace('£', '').replace('GBP', '').strip()
                        price_float = float(clean_price)
                        
                        # Fiyat değişikliği kontrolü
                        if old_price is not None and price_float != old_price:
                            self.send_email_alert(
                                row['title'],
                                old_price,
                                price_float,
                                row['product_url']
                            )
                        
                        # Fiyatları güncelle
                        self.df.loc[mask, 'last_price'] = old_price
                        self.df.loc[mask, 'current_price'] = price_float
                        self.df.loc[mask, 'last_check'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        
                    except (ValueError, TypeError) as e:
                        print(f"Price conversion error ({url}): {str(e)}")
                        return
                
                # DataFrame'i CSV'ye kaydet
                self.df.to_csv(self.csv_file, index=False)
                
        except Exception as e:
            print(f"CSV update error ({url}): {str(e)}")

    def monitor_urls(self):
        """Published ürünlerin fiyatlarını izle"""
        while True:
            try:
                # CSV'den URL'leri al
                urls = self.df['auction_url'].tolist()
                
                for url in urls:
                    self.url_queue.put(url)
                
                # Driver'ları başlat
                driver_threads = []
                for i in range(self.driver_count):
                    thread = threading.Thread(target=self.monitor_driver, args=(i,))
                    thread.start()
                    driver_threads.append(thread)
                
                # Thread'leri bekle
                for thread in driver_threads:
                    thread.join()
                
                # Belirli bir süre bekle
                time.sleep(300)  # 5 dakika bekle
                
            except Exception as e:
                print(f"Monitoring error: {str(e)}")
                time.sleep(60)  # Hata durumunda 1 dakika bekle
                continue

    def monitor_driver(self, driver_id):
        """Selenium driver ile fiyatları izle"""
        try:
            # Chrome driver'ı başlat
            options = webdriver.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            driver = webdriver.Chrome(options=options)
            self.drivers.append(driver)
            
            while not self.stop_event.is_set():
                try:
                    # URL kuyruğu boşsa bekle
                    if self.url_queue.empty():
                        time.sleep(5)
                        continue
                    
                    # Kuyruktan URL al
                    url = self.url_queue.get(timeout=1)
                    if not url or pd.isna(url):
                        continue
                    
                    print(f"Driver {driver_id} checking URL: {url}")
                    
                    # Sayfayı yükle
                    driver.get(url)
                    
                    try:
                        # Fiyat elementini bekle ve bul (farklı selektörler denenir)
                        selectors = [
                            ".priceTxt", 
                            ".price-value", 
                            ".price",
                            "span[data-price]",
                            "[itemprop='price']",
                            ".current-price"
                        ]
                        
                        price_element = None
                        for selector in selectors:
                            try:
                                price_element = WebDriverWait(driver, 5).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                                )
                                if price_element:
                                    break
                            except:
                                continue
                        
                        if price_element:
                            current_price = price_element.text.strip()
                            print(f"Found price for {url}: {current_price}")
                            self.update_csv(url, current_price)
                        else:
                            print(f"No price element found for {url}")
                        
                    except TimeoutException:
                        print(f"Timeout waiting for price element: {url}")
                    except NoSuchElementException:
                        print(f"Price element not found: {url}")
                    except Exception as e:
                        print(f"Error checking price for {url}: {str(e)}")
                    
                    time.sleep(2)
                    
                except Exception as e:
                    if not self.stop_event.is_set():
                        print(f"Driver {driver_id} error while processing URL: {str(e)}")
                    continue
                
        except Exception as e:
            print(f"Driver {driver_id} initialization error: {str(e)}")
        finally:
            try:
                driver.quit()
            except:
                pass

def main():
    monitor = PriceMonitor(driver_count=2, tabs_per_driver=2)
    
    try:
        monitor.monitor_urls()
    except KeyboardInterrupt:
        print("\nProgram stopping...")
    finally:
        monitor.stop_event.set()
        for driver in monitor.drivers:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    main()