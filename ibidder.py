import requests
from bs4 import BeautifulSoup
import re
import csv
from datetime import datetime
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import os
import asyncio
from playwright.async_api import async_playwright

def get_urls_from_file(filename):
    """URL'leri dosyadan okur"""
    with open(filename, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def standardize_category_code(code):
    """CategoryCode değerini standartlaştırır"""
    return code.strip().upper()

def get_category_from_url(url):
    """Extracts category code from URL"""
    try:
        match = re.search(r'category[Cc]ode=([A-Z]+)', url)
        if match:
            return match.group(1).upper()
    except Exception as e:
        print(f"Error extracting category code: {str(e)}")
    return None

def get_auction_urls(url, target_category):
    """Ana sayfadaki açık artırma URL'lerini toplar"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        print(f"URL kontrol ediliyor: {url}")
        response = requests.get(url, headers=headers)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        auction_summaries = soup.find_all('div', class_='auction-summary-standard')
        
        matching_urls = []
        
        for auction in auction_summaries:
            button = auction.find('a', class_='button')
            if button and 'Coming soon' in button.text.strip():
                continue
            
            auction_link = auction.find('a', class_='auction-image-container')
            if auction_link and auction_link.get('href'):
                base_url = auction_link.get('href')
                if base_url.startswith('/'):
                    base_url = f"https://www.i-bidder.com{base_url}"
                
                final_url = f"{base_url}/search-filter?mastercategorycode={target_category}"
                matching_urls.append(final_url)
        
        return matching_urls
        
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        return []

def get_product_details(url, headers):
    """Ürün detay sayfasından bilgileri çeker"""
    try:
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        products = []
        lot_divs = soup.find_all('div', class_='lot-single')
        
        for lot in lot_divs:
            product_data = {}
            
            product_link = lot.find('a', class_='click-track', attrs={'data-click-type': 'image'})
            if product_link:
                product_url = product_link.get('href')
                if product_url.startswith('/'):
                    product_url = f"https://www.i-bidder.com{product_url}"
                product_data['url'] = product_url
                
                product_img = product_link.find('img')
                if product_img:
                    product_data['image_url'] = product_img.get('src')
                    product_data['title'] = product_img.get('alt')
            
            if product_data:
                products.append(product_data)
        
        return products
        
    except Exception as e:
        print(f"Ürün detayları alınırken hata oluştu: {str(e)}")
        return []

async def get_lot_details(context, product_info):
    """Extracts lot details from the detail page using Playwright"""
    page = None
    try:
        page = await context.new_page()
        print(f"Processing: {product_info['url']}")
        
        await page.goto(product_info['url'], wait_until="networkidle")
        
        lot_data = {
            'title': product_info.get('title', ''),
            'image_url': '',
            'current_bid': '',
            'commission': '',
            'vat_rate': '',
            'auction_url': product_info['url'],
            'bidding_ends': ''
        }
        
        # Yeni image URL'yi al
        try:
            img_element = await page.query_selector('//html/body/div[1]/main/div/div[6]/div[1]/div/div[1]/div/div[2]/div/div/div/div[1]/img')
            if img_element:
                lot_data['image_url'] = await img_element.get_attribute('src')
        except Exception as e:
            print(f"Error getting image URL: {str(e)}")
            lot_data['image_url'] = product_info.get('image_url', '')
        
        # Fiyat alma
        try:
            bid_span = await page.query_selector('//html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[1]/span')
            if bid_span:
                class_attr = await bid_span.get_attribute('class')
                if class_attr and 'noBid' in class_attr:
                    alt_price = await page.query_selector('//html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[3]/div/div/div[3]/p/span/span/span')
                    if alt_price:
                        price_text = await alt_price.text_content()
                        lot_data['current_bid'] = f"{price_text.strip()} GBP"
                else:
                    price_text = await bid_span.text_content()
                    currency_span = await page.query_selector('//html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[2]/div[1]/form/div/div[1]/div/div[2]/span/span[2]/span/strong')
                    currency = await currency_span.text_content() if currency_span else "GBP"
                    lot_data['current_bid'] = f"{price_text.strip()} {currency}"
        except Exception as e:
            print(f"Error getting price: {str(e)}")
            try:
                opening_bid = await page.query_selector('//span[contains(@class, "minBidAmount")]')
                if opening_bid:
                    opening_bid_text = await opening_bid.text_content()
                    lot_data['current_bid'] = f"{opening_bid_text.strip()} GBP (Opening Bid)"
            except Exception as e:
                print(f"Error getting opening bid: {str(e)}")
        
        # Commission ve VAT alma
        try:
            html_content = await page.content()
            soup = BeautifulSoup(html_content, 'html.parser')
            
            popup_div = soup.find('div', class_='ui popup top left transition visible')
            if popup_div:
                commission_row = popup_div.find('tr', {'name': 'commissions'})
                if commission_row:
                    commission_span = commission_row.find('span', id='commissionsExVAT')
                    if commission_span:
                        lot_data['commission'] = commission_span.text.replace('%', '').strip()
                
                vat_span = popup_div.find('span', id='additionalFeeVatRate')
                if vat_span:
                    lot_data['vat_rate'] = vat_span.text.replace('%', '').strip()
            
            if not lot_data['commission'] or not lot_data['vat_rate']:
                scripts = soup.find_all('script')
                for script in scripts:
                    if script.string and 'commissionsExVAT' in script.string:
                        commission_match = re.search(r'commissionsExVAT">([\d.]+)%', script.string)
                        vat_match = re.search(r'additionalFeeVatRate">([\d.]+)%', script.string)
                        
                        if commission_match and not lot_data['commission']:
                            lot_data['commission'] = commission_match.group(1)
                        if vat_match and not lot_data['vat_rate']:
                            lot_data['vat_rate'] = vat_match.group(1)
        except Exception as e:
            print(f"Commission/VAT extraction error: {str(e)}")
        
        # Get bidding ends time
        try:
            timer_element = await page.query_selector('//html/body/div[1]/main/div/div[6]/div[1]/div/div[2]/div[6]/div/div[1]/div[2]')
            if timer_element:
                lot_data['bidding_ends'] = await timer_element.text_content()
        except Exception as e:
            print(f"Error getting bidding end time: {str(e)}")
        
        return lot_data
        
    except Exception as e:
        print(f"Error processing {product_info['title']}: {str(e)}")
        return None
    finally:
        if page:
            await page.close()

def create_products_csv():
    """First step: Create products.csv with URLs and titles"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    with open('products.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['title', 'url', 'image_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        urls = get_urls_from_file('urls.txt')
        print(f"Number of URLs to read: {len(urls)}")
        
        all_auction_urls = []
        for url in urls:
            target_category = get_category_from_url(url)
            if not target_category:
                print(f"Category code not found: {url}")
                continue
                
            print(f"Processing URL: {url}")
            print(f"Target category: {target_category}")
            
            auction_urls = get_auction_urls(url, target_category)
            all_auction_urls.extend(auction_urls)
        
        print(f"\nTotal auction URLs found: {len(all_auction_urls)}")
        
        for auction_url in all_auction_urls:
            print(f"\nChecking auction: {auction_url}")
            products = get_product_details(auction_url, headers)
            
            for product in products:
                writer.writerow(product)
    
    print("products.csv created successfully!")

async def process_with_playwright():
    """Process all products with Playwright using multiple browsers"""
    try:
        if not os.path.exists('products.csv'):
            raise FileNotFoundError("products.csv not found")
            
        products = []
        with open('products.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            products = list(reader)
        
        print(f"Found {len(products)} products to process")
        results = []
        
        async with async_playwright() as p:
            # 10 browser instance oluştur
            browsers = []
            contexts = []
            for _ in range(10):
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                context.set_default_timeout(60000)
                browsers.append(browser)
                contexts.append(context)
            
            print("Created 10 browser instances")
            
            # Ürünleri browser'lar arasında dağıt
            tasks = []
            for i, product in enumerate(products):
                context = contexts[i % 10]  # Round-robin dağıtım
                tasks.append(get_lot_details(context, product))
            
            # Tüm taskları çalıştır
            chunk_size = 10  # Her seferde 10 ürün işle
            for i in range(0, len(tasks), chunk_size):
                chunk = tasks[i:i + chunk_size]
                print(f"Processing chunk {i//chunk_size + 1}/{len(tasks)//chunk_size + 1}")
                chunk_results = await asyncio.gather(*chunk)
                results.extend([r for r in chunk_results if r])
                
            # Browser'ları kapat
            for browser in browsers:
                await browser.close()
                
        if results:
            output_file = 'lots_details.csv'
            fieldnames = ['title', 'image_url', 'current_bid', 'commission', 
                        'vat_rate', 'auction_url', 'bidding_ends']
            
            with open(output_file, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                for result in results:
                    writer.writerow(result)
            
            print(f"\nCSV file created successfully: {output_file}")
            print(f"Processed {len(results)} products")
            
    except Exception as e:
        print(f"Error in process_with_playwright: {str(e)}")
        print("Full error traceback:")
        import traceback
        traceback.print_exc()

async def main():
    """Main function to control the workflow"""
    try:
        print("Step 1: Creating products.csv...")
        create_products_csv()
        
        print("\nStep 2: Processing with Selenium...")
        await process_with_playwright()
        
        print("All processes completed!")
    except Exception as e:
        print(f"Error in main process: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())