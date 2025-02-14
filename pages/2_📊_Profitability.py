import csv
import pandas as pd
from datetime import datetime
import streamlit as st
import plotly.express as px
import numpy as np
from ebay_search import EbaySearchManager
from utils.ebay_api import EbayAPI
from utils.listing_manager import ListingManager
from urllib.parse import quote  # URL encoding için import ekleyin
from src.services.ebay_listing_service import listing_service
from src.services.woocommerce_service import WooCommerceService
from src.services.ebay_service import EbayService
from src.services.ebay_category_finder import EbayCategoryFinder
import json
import time
from woocommerce import API
import os

# Global instance
woo_service = WooCommerceService()
ebay_service = EbayService()

def get_price_from_estimate(estimate_str):
    """Extract higher price from estimate range"""
    try:
        if pd.isna(estimate_str) or estimate_str == 'Unknown':
            return None
        # "200 GBP - 300 GBP" formatından 300'ü al
        higher_price = estimate_str.split('-')[1].replace('GBP', '').strip()
        return float(higher_price)
    except:
        return None

def calculate_total_cost(row):
    """Calculate total cost using priority: buy_it_now > estimate_bid > current_bid > opening_bid"""
    try:
        # Hangi fiyat tipini kullanacağımızı belirle
        USE_BUY_IT_NOW = True  # Satın Al fiyatını kullan
        USE_ESTIMATE = True  # Tahmin edilen fiyatı kullan
        USE_CURRENT_BID = False  # Mevcut teklifi kullan
        USE_OPENING_BID = False  # Açılış teklifini kullan
        
        # Seçilen fiyat tipine göre current_bid'i güncelle
        if USE_BUY_IT_NOW and row['buy_it_now'] not in [None, 'Unknown', '']:
            bid = float(str(row['buy_it_now']).replace('GBP', '').strip())
            row['current_bid'] = bid  # current_bid'i güncelle
            
        elif USE_ESTIMATE and pd.notna(row['estimate_bid']):
            bid = get_price_from_estimate(row['estimate_bid'])
            if bid is not None:
                row['current_bid'] = bid  # current_bid'i güncelle
            else:
                return None
        
        elif USE_CURRENT_BID and row['current_bid'] not in [None, 'No Bid', '']:
            bid = float(str(row['current_bid']).strip())
            # current_bid zaten doğru değerde
            
        elif USE_OPENING_BID and row['opening_bid'] not in [None, '', 'Unknown']:
            bid = float(str(row['opening_bid']).strip())
            row['current_bid'] = bid  # current_bid'i güncelle
            
        else:
            print(f"No valid price found for {row['name']}")
            return None
            
        # VAT ve commission hesapla
        vat = bid * (float(row['vat_rate']) / 100)
        commission = bid * (float(row['commission']) / 100)
        
        total = bid + vat + commission
        print(f"Cost calculation for {row['name']}: Bid={bid}, VAT={vat}, Commission={commission}, Total={total}")
        return round(total, 2)
        
    except Exception as e:
        print(f"Cost calculation error ({row['name']}): {str(e)}")
        return None

def calculate_ebay_price(row):
    """Convert eBay price to number and validate source"""
    try:
        price_text = row['ebay_lowest_price']
        
        # Skip if price is missing or invalid
        if pd.isna(price_text):
            print(f"No valid price found for {row['title']}")
            return None
        
        # Remove £ symbol and convert to number
        price = float(str(price_text).replace('£', '').strip())
        source = row.get('price_source', 'unknown')
        print(f"Price converted: {price_text} -> {price} (Source: {source})")
        return price
    except Exception as e:
        print(f"Price conversion error for {row['title']}")
        print(f"Price text: '{price_text}'")
        print(f"Error: {str(e)}")
        return None

def calculate_profitability(row):
    """Calculate profitability with new pricing strategy"""
    try:
        total_cost = row['total_cost']
        ebay_price = row['ebay_price']
        price_source = row.get('price_source', 'unknown')
        
        if total_cost is None or ebay_price is None:
            print(f"Cannot calculate profitability ({row['title']}): total_cost={total_cost}, ebay_price={ebay_price}")
            return None
        
        # eBay fees based on price source
        if price_source == 'ebay_exact':
            ebay_fee = ebay_price * 0.25  # 25% for exact matches
        elif price_source == 'google':
            ebay_fee = ebay_price * 0.12  # 12% for Google-sourced prices
        else:
            ebay_fee = ebay_price * 0.26  # 26% for similar matches
        
        # Calculate net profit
        profit = ebay_price - total_cost - ebay_fee
        print(f"Profitability calculated ({row['name']}): ebay={ebay_price}, cost={total_cost}, fee={ebay_fee}, profit={profit}")
        return round(profit, 2)
    except Exception as e:
        print(f"Profitability calculation error ({row['name']}): {str(e)}")
        return None

def is_profitable(row):
    """Check if item is profitable (cost must be <= 50% of eBay price)"""
    try:
        total_cost = row['total_cost']
        ebay_price = row['ebay_price']
        
        if total_cost is None or ebay_price is None:
            print(f"Cannot check profitability ({row['name']}): total_cost={total_cost}, ebay_price={ebay_price}")
            return False
        
        # Core rule: Total cost must be <= 50% of eBay price
        is_prof = total_cost <= (ebay_price * 0.5)
        print(f"Profitability check ({row['name']}): {is_prof} (cost={total_cost}, max_cost={ebay_price * 0.5})")
        return is_prof
    except Exception as e:
        print(f"Profitability check error ({row['name']}): {str(e)}")
        return False

def is_valid_image_url(url):
    """URL'nin geçerli bir resim URL'si olup olmadığını kontrol et"""
    if not url or not isinstance(url, str):
        return False
    
    # Azure blob storage URL'lerini kontrol et
    if 'azureedge.net' in url.lower():
        return True
        
    # Yaygın resim uzantılarını kontrol et
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    return any(ext in url.lower() for ext in valid_extensions)

@st.cache_data(ttl=2)  # 2 saniyelik cache
def load_and_process_data():
    """Load and process data with new pricing strategy"""
    try:
        print("\n=== Loading Data ===")
        
        # Read CSV as strings initially
        df = pd.read_csv('data/output/lots_details_with_ebay.csv', dtype=str)
        print("\n1. Initial data shape:", df.shape)
        
        # Clean price columns
        def clean_price(price_str):
            if pd.isna(price_str) or price_str in ['Unknown', 'Not Found', 'Not Available', 'No Bid', 'N/A']:
                return None
            # Remove '£' and convert to float
            try:
                return float(str(price_str).replace('£', '').strip())
            except:
                return None

        # Clean and convert price columns
        price_columns = ['ebay_lowest_price', 'suggested_price', 'current_bid', 'opening_bid', 'current_price']
        for col in price_columns:
            if col in df.columns:  # Kolon varsa işle
                df[col] = df[col].apply(clean_price)
            
        print("\n2. Price columns converted")
        
        # Convert commission and VAT rates
        numeric_columns = ['commission', 'vat_rate']
        for col in numeric_columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        print("\n3. Starting calculations")
        
        # Calculate total cost
        df['total_cost'] = df.apply(calculate_total_cost, axis=1)
        
        # Calculate eBay price
        df['ebay_price'] = df.apply(
            lambda row: calculate_ebay_price(row) if pd.notna(row['ebay_lowest_price']) else None, 
            axis=1
        )
        
        # Calculate profit
        df['profit'] = df.apply(
            lambda row: calculate_profitability(row) if pd.notna(row['ebay_price']) else None, 
            axis=1
        )
        
        # Check if profitable
        df['is_profitable'] = df.apply(
            lambda row: is_profitable(row) if pd.notna(row['ebay_price']) else False, 
            axis=1
        )
        
        # Filter rows with prices but keep all data
        df_with_prices = df.copy()
        
        print("\n=== Final Results ===")
        print(f"Total items: {len(df)}")
        print(f"Items with prices: {len(df_with_prices)}")
        print(f"Profitable items: {df_with_prices['is_profitable'].sum()}")
        
        return df_with_prices  # Tüm veriyi döndür
            
    except Exception as e:
        print(f"\nData processing error: {str(e)}")
        print("\nFull error traceback:")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()  # Hata durumunda boş DataFrame

def search_ebay_for_item():
    """Manual eBay search interface"""
    st.subheader("🔍 Manual eBay Search")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        search_title = st.text_input("Enter item title to search on eBay")
    
    with col2:
        if st.button("Search eBay", type="primary"):
            if search_title:
                with st.spinner("Searching eBay..."):
                    try:
                        ebay_manager = EbaySearchManager()
                        result = ebay_manager.search_single_product(ebay_manager.setup_driver(), search_title)
                        
                        if result and result.get('ebay_lowest_price') != 'Not Found':
                            st.success("Price found!")
                            st.write("eBay Price:", result['ebay_lowest_price'])
                            st.write("Suggested Price:", result['suggested_price'])
                            if result.get('ebay_url'):
                                st.markdown(f"[View on eBay]({result['ebay_url']})")
                        else:
                            st.warning("No price found on eBay")
                    except Exception as e:
                        st.error(f"Error searching eBay: {str(e)}")
            else:
                st.warning("Please enter a title to search")

def display_item_card(row, index):
    """Ürün kartını göster"""
    st.markdown("""
        <style>
        .item-grid {
            display: grid;
            grid-template-columns: 200px 1fr 250px;
            gap: 20px;
            align-items: start;
        }
        .item-image {
            width: 100%;
            border-radius: 8px;
        }
        .item-details {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .item-actions {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        .price-tag {
            font-size: 1.2rem;
            font-weight: bold;
            color: #4CAF50;
            background: rgba(76, 175, 80, 0.1);
            padding: 5px 10px;
            border-radius: 4px;
        }
        .bid-info {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin: 10px 0;
        }
        .bid-box {
            background: #262626;
            padding: 10px;
            border-radius: 4px;
        }
        .item-title {
            font-size: 1.2rem;
            font-weight: 500;
            color: #E0E0E0;
            margin-bottom: 10px;
        }
        </style>
    """, unsafe_allow_html=True)

    with st.container():
        col1, col2, col3 = st.columns([2, 5, 3])
        
        # Resim kolonu
        with col1:
            try:
                images = eval(row['images']) if isinstance(row['images'], str) else row['images']
                if images and len(images) > 0:
                    st.image(images[0], use_container_width=True)
            except:
                st.image("https://via.placeholder.com/200", use_container_width=True)

        # Detaylar kolonu
        with col2:
            st.markdown(f"#### {row['name'][:100]}...")
            
            # Fiyat ve teklif bilgileri
            st.markdown("<div class='bid-info'>", unsafe_allow_html=True)
            
            # Current Bid
            st.markdown(f"""
                <div class='bid-box'>
                    <small>Current Bid</small><br>
                    <strong>£{row['current_bid']}</strong>
                </div>
            """, unsafe_allow_html=True)
            
            # eBay Price
            st.markdown(f"""
                <div class='bid-box'>
                    <small>eBay Price</small><br>
                    <strong>£{row['ebay_price']:.2f}</strong>
                </div>
            """, unsafe_allow_html=True)
            
            # Profit
            st.markdown(f"""
                <div class='bid-box'>
                    <small>Potential Profit</small><br>
                    <strong class='profit-positive'>£{row['profit']:.2f}</strong>
                </div>
            """, unsafe_allow_html=True)
            
            # Time Remaining
            st.markdown(f"""
                <div class='bid-box'>
                    <small>Time Remaining</small><br>
                    <strong>{row.get('time_remaining', 'N/A')}</strong>
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

        # Aksiyonlar kolonu
        with col3:
            st.markdown("<div class='item-actions'>", unsafe_allow_html=True)
            
            # Butonlar
            if st.button(f"🔍 View Auction", key=f"view_{index}"):
                st.markdown(f"[Open Auction]({row['url']})")
            
            if st.button(f"📊 View on eBay", key=f"ebay_{index}"):
                st.markdown(f"[Open on eBay]({row['ebay_url']})")
            
            # List on Website butonu - yeni sayfaya yönlendir
            if st.button(f"🛍️ List on Website", key=f"list_{index}"):
                st.session_state.product_data = row
                # JavaScript ile yönlendirme
                js = f"""
                    <script>
                        window.parent.location.href = '/Create_Product';
                    </script>
                """
                st.markdown(js, unsafe_allow_html=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

def show_product_editor(row, ebay_details=None):
    """Show product editor with pre-filled eBay categories"""
    try:
        print(f"show_product_editor başladı: {row.get('name', 'Unknown')}")  # Debug log
        
        # Form durumunu kontrol et
        if 'product_editor_submitted' not in st.session_state:
            st.session_state['product_editor_submitted'] = False
            
        if not st.session_state.get('product_editor_submitted', False):
            with st.form("product_editor", clear_on_submit=False):
                st.subheader("Ürün Detayları")
                
                # Temel bilgiler
                title = st.text_input("Başlık", value=row['name'])
                regular_price = st.number_input("Fiyat (£)", value=float(row['ebay_lowest_price']) if pd.notna(row.get('ebay_lowest_price')) else 0.0)
                sku = st.text_input("SKU", value=row.get('sku', ''))
                stock = st.number_input("Stok", value=1, min_value=1)
                
                # Durum ve garanti
                condition = st.selectbox("Durum", ["New", "Used", "Refurbished"], index=0)
                warranty = st.selectbox("Garanti", ["No Warranty", "1 Year", "2 Years"], index=0)
                
                # Marka
                brand = st.text_input("Marka", value=ebay_details.get('brand', '') if ebay_details else '')
                
                # Açıklama
                description = st.text_area("Açıklama", value=row.get('description', ''))
                
                # Resim galerisi
                if pd.notna(row.get('images')):
                    try:
                        image_list = eval(row['images']) if isinstance(row['images'], str) else row['images']
                        st.write("Ürün Resimleri:")
                        image_cols = st.columns(min(4, len(image_list)))
                        for idx, img_col in enumerate(image_cols):
                            if idx < len(image_list):
                                with img_col:
                                    st.image(image_list[idx], width=100)
                                    st.markdown(f'<a href="{image_list[idx]}" target="_blank">Tam Boyut</a>', 
                                              unsafe_allow_html=True)
                    except Exception as img_error:
                        print(f"Resim işleme hatası: {str(img_error)}")
                        st.warning("Resimler işlenirken hata oluştu")
                
                # Kategori seçimi
                if ebay_details and ebay_details.get('woo_categories'):
                    st.write("eBay Kategorileri:")
                    selected_categories = st.multiselect(
                        "Kategoriler",
                        options=[cat['name'] for cat in ebay_details['woo_categories']],
                        default=[cat['name'] for cat in ebay_details['woo_categories']],
                        help="eBay listesinden kategorileri seçin"
                    )
                else:
                    st.warning("⚠️ eBay kategorileri bulunamadı. Lütfen manuel seçin.")
                    selected_categories = st.multiselect(
                        "Kategoriler",
                        ["Electronics", "Lab Equipment", "Industrial", "Tools", "Other"],
                        default=["Lab Equipment"]
                    )

                submitted = st.form_submit_button("Ürün Oluştur")
                
                if submitted:
                    success = create_product(row, title, regular_price, sku, stock, condition, 
                                          warranty, selected_categories, ebay_details, brand, description)
                    if success:
                        st.session_state['product_editor_submitted'] = True
                        st.success("✅ Ürün başarıyla oluşturuldu!")
                        
        else:
            # Form başarıyla gönderildiyse yeni bir buton göster
            if st.button("Yeni Ürün Ekle"):
                st.session_state['product_editor_submitted'] = False
                st.experimental_rerun()
                
    except Exception as e:
        print(f"show_product_editor hatası: {str(e)}")
        st.error(f"Ürün editörü gösterilirken hata: {str(e)}")

def update_ebay_prices():
    """Update eBay prices using ebay_search.py"""
    st.subheader("🔄 Update eBay Prices")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.info("This will update all eBay prices in the CSV file")
    
    with col2:
        if st.button("Update Prices", type="primary", help="Run eBay search for all items"):
            with st.spinner("Updating eBay prices... This may take a while..."):
                try:
                    # Import main function from ebay_search.py
                    from ebay_search import main as ebay_search_main
                    
                    # Run the eBay search
                    ebay_search_main()
                    
                    # Reload the data
                    st.success("✅ Prices updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error updating prices: {str(e)}")

def create_dashboard():
    # Sayfa genişliğini maksimuma ayarla
    st.set_page_config(layout="wide")
    
    # Ana stil
    st.markdown("""
        <style>
        .main-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .stApp {
            background-color: #121212;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Sayfa başlığı ve stil
    st.markdown("""
        <style>
        .main-header {
            font-size: 2.5rem;
            font-weight: 600;
            color: #1E88E5;
            margin-bottom: 2rem;
        }
        .stat-card {
            background-color: #1E1E1E;
            padding: 1rem;
            border-radius: 10px;
            border: 1px solid #333;
        }
        .filter-section {
            background-color: #262626;
            padding: 1.5rem;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        .item-card {
            background-color: #1E1E1E;
            padding: 1.5rem;
            border-radius: 10px;
            border: 1px solid #333;
            margin-bottom: 1rem;
        }
        .profit-positive {
            color: #4CAF50;
            font-weight: bold;
        }
        .profit-negative {
            color: #F44336;
            font-weight: bold;
        }
        </style>
        <h1 class='main-header'>📊 Profitability Analysis</h1>
    """, unsafe_allow_html=True)
    
    # Sidebar düzeni
    with st.sidebar:
        st.markdown("### 🔄 Refresh Settings")
        auto_refresh = st.checkbox("Auto Refresh", value=True)
        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
        
        st.markdown("---")
        st.markdown("### 🎯 Quick Filters")
        quick_filter = st.radio(
            "Show Items",
            ["All", "High Profit (>£100)", "Low Cost (<£200)", "Best ROI (>50%)"]
        )
    
    # Session state kontrolü
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()
    
    # Yenileme kontrolü
    current_time = time.time()
    if auto_refresh and (current_time - st.session_state.last_refresh) >= 2:
        st.cache_data.clear()
        st.session_state.last_refresh = current_time
    
    # Veri yükleme
    df = load_and_process_data()
    
    if not df.empty:
        # Filtre bölümü
        st.markdown("<div class='filter-section'>", unsafe_allow_html=True)
        st.subheader("🎯 Filter Options")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            min_profit = st.number_input("Min Profit (£)", 
                value=0.0, 
                step=10.0,
                help="Minimum profit threshold")
        
        with col2:
            max_cost = st.number_input("Max Cost (£)", 
                value=1000.0, 
                step=100.0,
                help="Maximum item cost")
        
        with col3:
            price_source = st.multiselect(
                "Price Source",
                ['ebay_sold', 'ebay_similar', 'google'],
                default=['ebay_sold', 'ebay_similar', 'google'],
                help="Select price data sources"
            )
        
        with col4:
            sort_by = st.selectbox(
                "Sort By",
                ['profit', 'total_cost', 'ebay_price', 'bidding_ends'],
                index=0,
                help="Choose sorting criteria"
            )
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Quick filter uygulama
        if quick_filter == "High Profit (>£100)":
            df = df[df['profit'] > 100]
        elif quick_filter == "Low Cost (<£200)":
            df = df[df['total_cost'] < 200]
        elif quick_filter == "Best ROI (>50%)":
            df = df[df['profit'] / df['total_cost'] > 0.5]
        
        # Ana filtreleme
        filtered_df = df[
            (df['profit'] >= min_profit) &
            (df['total_cost'] <= max_cost) &
            (df['price_source'].isin(price_source))
        ].sort_values(by=sort_by, ascending=False)
        
        # İstatistikler
        st.markdown("<div class='stat-card'>", unsafe_allow_html=True)
        st.subheader("📈 Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Items", 
                     len(filtered_df),
                     delta=f"{len(filtered_df) - len(df)} from filters")
        
        with col2:
            avg_profit = filtered_df['profit'].mean()
            st.metric("Average Profit", 
                     f"£{avg_profit:.2f}" if pd.notna(avg_profit) else "£0.00",
                     delta=f"£{filtered_df['profit'].std():.2f} std")
        
        with col3:
            total_profit = filtered_df['profit'].sum()
            st.metric("Total Potential Profit", 
                     f"£{total_profit:.2f}" if pd.notna(total_profit) else "£0.00")
        
        with col4:
            source_counts = filtered_df['price_source'].value_counts()
            st.write("Price Sources:", source_counts.to_dict())
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Ürün listesi
        st.markdown(f"### 📋 Profitable Items ({len(filtered_df)})")
        for index, (_, row) in enumerate(filtered_df.iterrows()):
            with st.container():
                st.markdown("<div class='item-card'>", unsafe_allow_html=True)
                display_item_card(row, index)
                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("⚠️ No profitable items found!")
    
    # Otomatik yenileme
    if auto_refresh:
        time.sleep(2)
        st.rerun()

def create_product(row, title, regular_price, sku, stock, condition, warranty, 
                  selected_categories, ebay_details, brand, description):
    """WooCommerce'de ürün oluştur ve CSV'ye kaydet"""
    try:
        # Settings'den WooCommerce bilgilerini al
        with open('config/settings.json', 'r') as f:
            settings = json.load(f)
        
        # WooCommerce API bağlantısı
        wcapi = API(
            url=settings['woocommerce_url'],
            consumer_key=settings['woocommerce_consumer_key'],
            consumer_secret=settings['woocommerce_consumer_secret'],
            version="wc/v3"
        )
        
        # Ürün verilerini hazırla
        product_data = {
            "name": title,
            "type": "simple",
            "regular_price": str(regular_price),
            "description": description,
            "short_description": ebay_details,
            "categories": [{"name": cat} for cat in selected_categories],
            "sku": sku,
            "manage_stock": True,
            "stock_quantity": stock,
            "status": "publish",
            "attributes": [
                {
                    "name": "Brand",
                    "visible": True,
                    "options": [brand]
                },
                {
                    "name": "Condition",
                    "visible": True,
                    "options": [condition]
                },
                {
                    "name": "Warranty",
                    "visible": True,
                    "options": [warranty]
                }
            ]
        }
        
        # Resimleri ekle
        if 'images' in row and row['images']:
            try:
                images = eval(row['images']) if isinstance(row['images'], str) else row['images']
                if images:
                    product_data["images"] = [{"src": img} for img in images]
            except:
                st.warning("Resimler eklenemedi")
        
        # WooCommerce'de ürün oluştur
        response = wcapi.post("products", product_data)
        
        if response.status_code in [200, 201]:
            product = response.json()
            
            # CSV'ye kaydet
            csv_data = {
                'title': title,
                'auction_url': row['url'],
                'woo_product_id': product['id'],
                'product_url': product['permalink'],
                'ebay_url': row.get('ebay_url', ''),
                'price': regular_price,
                'condition': condition,
                'warranty': warranty,
                'brand': brand,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            # CSV dosyasını kontrol et ve yeni veriyi ekle
            csv_file = 'data/check/published_products.csv'
            
            # Dosya yoksa başlıkları oluştur
            if not os.path.exists(csv_file):
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=csv_data.keys())
                    writer.writeheader()
            
            # Yeni veriyi ekle
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=csv_data.keys())
                writer.writerow(csv_data)
            
            st.success(f"""
                ✅ Ürün başarıyla oluşturuldu!
                - ID: {product['id']}
                - URL: {product['permalink']}
                """)
            return True
            
        else:
            st.error(f"Ürün oluşturma hatası: {response.text}")
            return False
            
    except Exception as e:
        st.error(f"Ürün oluşturma hatası: {str(e)}")
        return False

def create_product_form(row):
    """Ürün oluşturma formu"""
    # eBay kategori finder'ı başlat
    finder = EbayCategoryFinder()
    
    # eBay URL'sinden kategori ve marka bilgilerini al
    ebay_url = row.get('ebay_url', '')
    categories_info = None
    if ebay_url:
        try:
            item_id = finder.extract_item_id(ebay_url)
            if item_id:
                categories_info = finder.get_item_categories(item_id)
        except Exception as e:
            st.warning(f"eBay kategori bilgileri alınamadı: {str(e)}")

    with st.form(key=f"create_product_form_{str(row.name)}"):
        st.subheader("Create Product")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Temel bilgiler
            title = st.text_input("Title", value=row['name'])
            regular_price = st.number_input("Price (£)", 
                value=float(row['ebay_price']) if pd.notna(row['ebay_price']) else 0.0,
                step=0.01)
                
            # SKU oluşturma
            product_name = str(row['name'])
            safe_sku = ''.join(e for e in product_name if e.isalnum())[:20]
            sku = st.text_input("SKU", value=f"AUC-{safe_sku}")
            
            stock = st.number_input("Stock", value=1, min_value=1)
            
            # Durum ve garanti
            condition_options = ["New", "Used - Like New", "Used - Good", "Used - Fair"]
            condition = st.selectbox("Condition", condition_options, 
                index=0 if "new" in str(row['name']).lower() else 1)
            
            warranty_options = ["No Warranty", "30 Days", "90 Days", "1 Year"]
            warranty = st.selectbox("Warranty", warranty_options)
            
        with col2:
            # eBay'den gelen kategorileri göster
            if categories_info and categories_info.get('woo_categories'):
                default_categories = [cat['name'] for cat in categories_info['woo_categories']]
            else:
                default_categories = ["Electronics", "Computers", "Mobile Phones"]
            
            selected_categories = st.multiselect(
                "Categories",
                options=default_categories + ["Electronics", "Computers", "Mobile Phones"],
                default=default_categories[:3]  # İlk 3 kategoriyi seç
            )
            
            # eBay'den gelen marka bilgisini kullan
            if categories_info and categories_info.get('brand'):
                default_brand = categories_info['brand']
            else:
                brand_list = ["Apple", "Samsung", "Microsoft", "Sony", "HP", "Dell"]
                default_brand = next(
                    (b for b in brand_list if b.lower() in str(row['name']).lower()),
                    ""
                )
            brand = st.text_input("Brand", value=default_brand)
            
            # Item Specifics'i açıklamaya ekle
            specs_text = ""
            if categories_info and categories_info.get('specifics'):
                specs_text = "\n\nProduct Specifications:\n"
                for spec in categories_info['specifics']:
                    specs_text += f"- {spec['Name']}: {spec['Value']}\n"
            
            # eBay detayları
            ebay_details = st.text_area("eBay Details", 
                value=f"Original Price: £{row['ebay_price']}\nSource: {row['price_source']}")
            
            # Açıklama
            description = st.text_area("Description", 
                value=f"{row['description']}{specs_text}\n\nCondition: {condition}\nWarranty: {warranty}")

        # Form gönderme butonu
        submit = st.form_submit_button("Create Product", type="primary")
        
        if submit:
            success = create_product(
                row=row,
                title=title,
                regular_price=regular_price,
                sku=sku,
                stock=stock,
                condition=condition,
                warranty=warranty,
                selected_categories=selected_categories,
                ebay_details=ebay_details,
                brand=brand,
                description=description
            )
            
            if success:
                st.success("✅ Product created successfully!")
                st.experimental_rerun()

if __name__ == "__main__":
    woo_service.start_monitoring()
    create_dashboard() 