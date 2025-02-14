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

class BidMonitor:
    def __init__(self, driver_count=20, tabs_per_driver=10):
        self.driver_count = driver_count
        self.tabs_per_driver = tabs_per_driver
        self.drivers = []
        self.stop_event = threading.Event()
        self.url_queue = Queue()
        self.results_lock = threading.Lock()
        self.results = {}
        self.csv_file = 'data/output/lots_details_with_ebay.csv'
        
        # Mevcut CSV'yi DataFrame olarak yükle
        self.df = pd.read_csv(self.csv_file)
        # Yeni kolonları ekle (yoksa)
        if 'current_price' not in self.df.columns:
            self.df['current_price'] = None
        if 'time_remaining' not in self.df.columns:
            self.df['time_remaining'] = None
        if 'last_update' not in self.df.columns:
            self.df['last_update'] = None

    def update_csv(self, url, price, time_remaining):
        """Mevcut CSV'deki veriyi günceller"""
        try:
            with self.results_lock:
                # URL'ye göre ilgili satırı bul
                mask = self.df['url'] == url
                
                # Fiyatı temizle ve float'a çevir
                if price not in ['N/A', None, '']:
                    try:
                        # Fiyattaki para birimi ve boşlukları temizle
                        clean_price = price.replace('£', '').replace('GBP', '').strip()
                        # Float'a çevir
                        price_float = float(clean_price)
                        self.df.loc[mask, 'current_price'] = price_float
                    except (ValueError, TypeError) as e:
                        print(f"Fiyat dönüştürme hatası ({url}): {str(e)}")
                        self.df.loc[mask, 'current_price'] = None
                else:
                    self.df.loc[mask, 'current_price'] = None
                
                # Süreyi güncelle
                self.df.loc[mask, 'time_remaining'] = time_remaining
                # Son güncelleme zamanını ekle
                self.df.loc[mask, 'last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # DataFrame'i CSV'ye kaydet
                self.df.to_csv(self.csv_file, index=False)
                
        except Exception as e:
            print(f"CSV güncelleme hatası ({url}): {str(e)}")

    def get_price_element(self, driver):
        """Fiyat elementini farklı seçicilerle bulmayı dener"""
        selectors = [
            "span#price span.amount strong",
            "span.amount strong",
            ".current-bid strong",
            ".lot-price strong",
            "#current-bid",
            ".bid-amount"
        ]
        
        for selector in selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                # Fiyatı temizle
                price_text = element.text.strip()
                return price_text
            except:
                continue
        return None

    def get_time_element(self, driver):
        """Süre elementini farklı seçicilerle bulmayı dener"""
        selectors = [
            "div#timer span",
            ".time-remaining",
            "#expiryDateTime span",
            ".lot-timer span",
            ".countdown"
        ]
        
        for selector in selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                return element.text.strip()
            except:
                continue
        return None

    def monitor_tab(self, driver, url, tab_index):
        """Tek bir tab'daki fiyat ve süreyi izler"""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries and not self.stop_event.is_set():
            try:
                driver.switch_to.window(driver.window_handles[tab_index])
                driver.get(url)
                time.sleep(2)
                
                while not self.stop_event.is_set():
                    try:
                        # Fiyat ve süre elementlerini al
                        price = self.get_price_element(driver)
                        time_remaining = self.get_time_element(driver)
                        
                        if price or time_remaining:  # En az biri bulunduysa
                            self.update_csv(url, 
                                          price if price else 'N/A',
                                          time_remaining if time_remaining else 'N/A')
                        
                        # Sayfayı yenile ve bekle
                        time.sleep(5)
                        driver.refresh()
                        
                    except Exception as e:
                        print(f"Element izleme hatası ({url}): {str(e)}")
                        time.sleep(10)
                        continue
                        
            except WebDriverException as e:
                retry_count += 1
                print(f"Tab yeniden deneniyor ({url}) - Deneme {retry_count}/{max_retries}")
                time.sleep(30)
                
                if retry_count == max_retries:
                    self.update_csv(url, 'N/A', 'N/A')

    def monitor_driver(self, driver_index):
        """Bir driver'daki tüm tab'ları yönetir"""
        driver = self.setup_driver()
        if not driver:
            return
            
        self.drivers.append(driver)
        
        for _ in range(self.tabs_per_driver):
            driver.execute_script("window.open()")
        
        tabs = []
        for i in range(self.tabs_per_driver):
            if not self.url_queue.empty():
                url = self.url_queue.get()
                thread = threading.Thread(target=self.monitor_tab, args=(driver, url, i))
                thread.start()
                tabs.append(thread)
        
        for tab in tabs:
            tab.join()

    def setup_driver(self):
        """Chrome driver'ı yapılandırır"""
        options = webdriver.ChromeOptions()
        # options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-notifications')
        options.add_argument('--disable-popup-blocking')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.page_load_strategy = 'eager'
        
        try:
            driver = webdriver.Chrome(options=options)
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
            })
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(10)
            return driver
        except Exception as e:
            print(f"Driver oluşturma hatası: {str(e)}")
            return None

    def start_monitoring(self):
        """İzleme işlemini başlatır"""
        urls = self.df['url'].tolist()
        
        for url in urls:
            self.url_queue.put(url)
        
        driver_threads = []
        for i in range(self.driver_count):
            thread = threading.Thread(target=self.monitor_driver, args=(i,))
            thread.start()
            driver_threads.append(thread)
        
        for thread in driver_threads:
            thread.join()

    def stop_monitoring(self):
        """İzleme işlemini durdurur"""
        self.stop_event.set()
        for driver in self.drivers:
            try:
                driver.quit()
            except:
                pass

def main():
    monitor = BidMonitor(driver_count=2, tabs_per_driver=2)
    
    try:
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\nProgram durduruluyor...")
    finally:
        monitor.stop_monitoring()

if __name__ == "__main__":
    main()