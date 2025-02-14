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
        self.csv_file = 'monitoring_results.csv'
        
        if not os.path.exists(self.csv_file):
            with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['url', 'price', 'time_remaining', 'last_update', 'status'])
                writer.writeheader()

    def setup_driver(self):
        """Yeni bir Chrome driver oluşturur ve yapılandırır"""
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-notifications')
        options.page_load_strategy = 'eager'  # Sayfa tam yüklenmeden devam et
        
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(30)  # Sayfa yükleme zaman aşımı
            driver.implicitly_wait(10)  # Element bekleme süresi
            return driver
        except Exception as e:
            print(f"Driver oluşturma hatası: {str(e)}")
            return None

    def write_to_csv(self, data):
        """Veriyi CSV'ye yazar"""
        try:
            with self.results_lock:
                with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['url', 'price', 'time_remaining', 'last_update', 'status'])
                    writer.writerow(data)
        except Exception as e:
            print(f"CSV yazma hatası: {str(e)}")

    def monitor_tab(self, driver, url, tab_index):
        """Tek bir tab'daki fiyat ve süreyi izler"""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries and not self.stop_event.is_set():
            try:
                # Tab'a geç
                driver.switch_to.window(driver.window_handles[tab_index])
                
                # URL'yi yükle
                driver.get(url)
                time.sleep(2)  # Sayfa yüklenmesi için kısa bekleme
                
                while not self.stop_event.is_set():
                    try:
                        # Fiyat elementini bekle
                        price_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "span#price span.amount strong"))
                        )
                        price = price_element.text.strip()
                        
                        # Süre elementini bekle
                        time_element = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div#timer span"))
                        )
                        time_remaining = time_element.text.strip()
                        
                        # Veriyi kaydet
                        data = {
                            'url': url,
                            'price': price,
                            'time_remaining': time_remaining,
                            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'status': 'success'
                        }
                        self.write_to_csv(data)
                        
                        time.sleep(5)  # 5 saniye bekle
                        driver.refresh()  # Sayfayı yenile
                        
                    except (TimeoutException, NoSuchElementException) as e:
                        error_data = {
                            'url': url,
                            'price': 'N/A',
                            'time_remaining': 'N/A',
                            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'status': f'error: {str(e)}'
                        }
                        self.write_to_csv(error_data)
                        time.sleep(10)
                        continue
                        
            except WebDriverException as e:
                retry_count += 1
                print(f"Tab yeniden deneniyor ({url}) - Deneme {retry_count}/{max_retries}")
                time.sleep(30)  # 30 saniye bekle ve tekrar dene
                
                if retry_count == max_retries:
                    error_data = {
                        'url': url,
                        'price': 'N/A',
                        'time_remaining': 'N/A',
                        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'status': f'failed after {max_retries} retries: {str(e)}'
                    }
                    self.write_to_csv(error_data)

    def monitor_driver(self, driver_index):
        """Bir driver'daki tüm tab'ları yönetir"""
        driver = self.setup_driver()
        if not driver:
            return
            
        self.drivers.append(driver)
        
        # Tab'ları oluştur
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

    def start_monitoring(self):
        """İzleme işlemini başlatır"""
        df = pd.read_csv('lots_details_with_ebay.csv')
        urls = df['url'].tolist()
        
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
    monitor = BidMonitor(driver_count=20, tabs_per_driver=10)
    
    try:
        monitor.start_monitoring()
    except KeyboardInterrupt:
        print("\nProgram durduruluyor...")
    finally:
        monitor.stop_monitoring()

if __name__ == "__main__":
    main()