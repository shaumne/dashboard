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

def load_and_process_data():
    """Load and process data with new pricing strategy"""
    try:
        print("\n=== Loading Data ===")
        
        # Read CSV as strings initially
        df = pd.read_csv('data/output/lots_details_with_ebay.csv', dtype=str)
        print("\n1. Initial data shape:", df.shape)
        
        # Clean price columns
        def clean_price(price_str):
            if pd.isna(price_str) or price_str in ['Unknown', 'Not Found', 'Not Available', 'No Bid']:
                return None
            # Remove '£' and convert to float
            try:
                return float(price_str.replace('£', '').strip())
            except:
                return None

        # Clean and convert price columns
        price_columns = ['ebay_lowest_price', 'suggested_price', 'current_bid', 'opening_bid']
        for col in price_columns:
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
        
        # Filter rows with prices
        df_with_prices = df.dropna(subset=['ebay_price'])
        
        print("\n=== Final Results ===")
        print(f"Total items: {len(df)}")
        print(f"Items with prices: {len(df_with_prices)}")
        print(f"Profitable items: {df_with_prices['is_profitable'].sum()}")
        
        if len(df_with_prices) > 0:
            print("\nProfitable Items:")
            profitable_items = df_with_prices[df_with_prices['is_profitable']]
            for _, row in profitable_items.iterrows():
                print(f"- {row['name']}: Cost=£{row['total_cost']:.2f}, eBay=£{row['ebay_price']:.2f}, Profit=£{row['profit']:.2f}")
            return profitable_items
        else:
            print("No items with valid prices found!")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"\nData processing error: {str(e)}")
        print("\nFull error traceback:")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()

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
    """Display item card with actions"""
    try:
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            
            # Image column
            with col1:
                if pd.notna(row.get('images')):
                    try:
                        # Convert string representation of list to actual list
                        image_list = eval(row['images']) if isinstance(row['images'], str) else row['images']
                        
                        # Get the first image for main display
                        main_image = image_list[0] if image_list else "assets/no-image.png"
                        st.image(main_image, 
                                caption="Main Image",
                                width=150)
                        
                        # Show thumbnails if there are more images
                        if len(image_list) > 1:
                            st.write("Additional Images:")
                            thumbnails_container = st.container()
                            with thumbnails_container:
                                thumbnail_cols = st.columns(min(3, len(image_list)-1))
                                for idx, thumb_col in enumerate(thumbnail_cols):
                                    if idx + 1 < len(image_list):
                                        with thumb_col:
                                            st.image(image_list[idx + 1], width=50)
                    except Exception as img_error:
                        st.warning(f"Error loading images: {str(img_error)}")
                        st.image("assets/no-image.png", 
                                caption="Image Load Error",
                                width=150)
                else:
                    st.image("assets/no-image.png",
                            caption="No Image Available",
                            width=150)
            
            # Info column
            with col2:
                st.markdown(f"### {index + 1}. {row['name']}")
                st.write(f"**Current Bid:** £{row['current_bid'] if pd.notna(row['current_bid']) else 'N/A'}")
                st.write(f"**eBay Price:** £{row['ebay_lowest_price'] if pd.notna(row['ebay_lowest_price']) else 'N/A'}")
                st.write(f"**Profit:** £{row['profit']:.2f}" if pd.notna(row.get('profit')) else "**Profit:** N/A")
                
                # Show URLs
                if pd.notna(row.get('url')):
                    st.write(f"[View Auction]({row['url']})")
                if pd.notna(row.get('ebay_url')):
                    st.write(f"[View on eBay]({row['ebay_url']})")
            
            # Button column
            with col3:
                if st.button("List on Website", key=f"list_{index}"):
                    try:
                        finder = EbayCategoryFinder()
                        ebay_url = row.get('ebay_url')
                        
                        if ebay_url:
                            item_id = finder.extract_item_id(ebay_url)
                            if item_id:
                                ebay_details = finder.get_item_categories(item_id)
                                show_product_editor(row, ebay_details)
                            else:
                                st.error("Could not extract eBay item ID")
                        else:
                            st.error(f"No eBay URL found for {row['name']}")
                            
                    except Exception as e:
                        st.error(f"Error getting eBay categories: {str(e)}")
                        
    except Exception as e:
        st.error(f"Error displaying item card: {str(e)}")

def show_product_editor(row, ebay_details=None):
    """Show product editor with pre-filled eBay categories"""
    try:
        st.subheader("📝 Product Editor")
        
        with st.form("product_editor"):
            col1, col2 = st.columns(2)
            
            with col1:
                title = st.text_input("Title", value=row['name'])
                
                # Fiyat dönüşümü için güvenli kontrol
                if pd.notna(row.get('ebay_lowest_price')):
                    if isinstance(row['ebay_lowest_price'], str):
                        price = float(row['ebay_lowest_price'].replace('£','').strip())
                    else:
                        price = float(row['ebay_lowest_price'])
                else:
                    price = 0.0
                    
                regular_price = st.number_input("Regular Price", value=price)
                sku = st.text_input("SKU", value=f"AUC-{row.get('auction_id', '')}")
                stock = st.number_input("Stock", value=1)
                
            with col2:
                brand = st.text_input("Brand", 
                    value=ebay_details.get('brand', '') if ebay_details and ebay_details.get('brand') else '')
                
                condition = st.selectbox("Condition", 
                    options=['New', 'Used - Like New', 'Used - Good', 'Used - Fair'])
                warranty = st.selectbox("Warranty",
                    options=['No Warranty', '30 Days', '60 Days', '90 Days'])
            
            # Ürün açıklaması
            description = st.text_area("Description", 
                value=row.get('description', ''), 
                height=150,
                help="Product description from auction listing")
            
            # Resim galerisi
            if pd.notna(row.get('images')):
                try:
                    image_list = eval(row['images']) if isinstance(row['images'], str) else row['images']
                    st.write("Product Images:")
                    image_cols = st.columns(min(4, len(image_list)))
                    for idx, img_col in enumerate(image_cols):
                        if idx < len(image_list):
                            with img_col:
                                st.image(image_list[idx], width=100)
                                st.markdown(f'<a href="{image_list[idx]}" target="_blank">View Full Size</a>', 
                                          unsafe_allow_html=True)
                except Exception as img_error:
                    st.warning(f"Error loading images: {str(img_error)}")
            
            # Kategori seçimi
            if ebay_details and ebay_details.get('woo_categories'):
                st.write("eBay Categories Found:")
                for cat in ebay_details['woo_categories']:
                    st.write(f"- {cat['name']}")
                
                selected_categories = st.multiselect(
                    "Select Categories",
                    options=[cat['name'] for cat in ebay_details['woo_categories']],
                    default=[cat['name'] for cat in ebay_details['woo_categories']],
                    help="Select categories from eBay listing"
                )
            else:
                st.warning("⚠️ No eBay categories found. Please select manually.")
                selected_categories = st.multiselect(
                    "Categories",
                    ["Electronics", "Lab Equipment", "Industrial", "Tools", "Other"],
                    default=["Lab Equipment"]
                )

            if st.form_submit_button("Create Product"):
                create_product(row, title, regular_price, sku, stock, condition, 
                             warranty, selected_categories, ebay_details, brand, description)
                             
    except Exception as e:
        st.error(f"Error showing product editor: {str(e)}")

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
    """Create Streamlit dashboard with improved layout"""
    st.set_page_config(layout="wide", page_title="Auction Profitability Analysis")
    
    # Add title with emoji
    st.title("🎯 Auction Profitability Analysis")
    
    # Add eBay price update button
    update_ebay_prices()
    
    st.markdown("---")
    
    # Load data
    df = load_and_process_data()
    
    if df.empty:
        st.error("No data available for analysis!")
        return
    
    # Add filters in expandable section
    with st.expander("📊 Filter Options", expanded=True):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            min_profit = st.number_input("Min Profit (£)", value=0.0, step=10.0)
        with col2:
            max_cost = st.number_input("Max Cost (£)", value=1000.0, step=100.0)
        with col3:
            price_source = st.multiselect(
                "Price Source",
                ['ebay_sold', 'ebay_similar', 'google'],
                default=['ebay_sold', 'ebay_similar', 'google']
            )
        with col4:
            sort_by = st.selectbox(
                "Sort By",
                ['profit', 'total_cost', 'ebay_price', 'bidding_ends'],
                index=0
            )
    
    # Filter and sort data
    filtered_df = df[
        (df['profit'] >= min_profit) &
        (df['total_cost'] <= max_cost) &
        (df['price_source'].isin(price_source))
    ].sort_values(by=sort_by, ascending=False)
    
    # Display statistics
    st.subheader("📈 Statistics")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Items", len(filtered_df))
    with col2:
        avg_profit = filtered_df['profit'].mean()
        st.metric("Average Profit", f"£{avg_profit:.2f}" if pd.notna(avg_profit) else "£0.00")
    with col3:
        total_profit = filtered_df['profit'].sum()
        st.metric("Total Potential Profit", f"£{total_profit:.2f}" if pd.notna(total_profit) else "£0.00")
    with col4:
        source_counts = filtered_df['price_source'].value_counts()
        st.write("Price Sources:", source_counts.to_dict())
    
    # Display items with index
    st.subheader(f"📋 Profitable Items ({len(filtered_df)})")
    for index, (_, row) in enumerate(filtered_df.iterrows()):
        display_item_card(row, index)

def create_product(row, title, regular_price, sku, stock, condition, warranty, selected_categories, ebay_details, brand, description):
    """Create product in WooCommerce"""
    try:
        st.info("Creating product...")
        
        # Kategori listesini oluştur
        woo_categories = []
        for category in selected_categories:
            woo_categories.append({
                "name": category.strip()
            })
        
        # Ürün verilerini hazırla
        product_data = {
            "name": title,
            "type": "simple",
            "regular_price": str(regular_price),
            "sku": sku,
            "stock_quantity": stock,
            "manage_stock": True,
            "categories": woo_categories,
            "attributes": [
                {
                    "name": "Brand",
                    "visible": True,
                    "options": [brand] if brand else []
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
        
        # eBay özelliklerini ekle
        if ebay_details and ebay_details.get('specifics'):
            for specific in ebay_details['specifics']:
                product_data['attributes'].append({
                    "name": specific['Name'],
                    "visible": True,
                    "options": [specific['Value']]
                })
        
        # Ürünü oluştur
        response = woo_service.create_product(product_data)
        
        if response and response.get('id'):
            st.success(f"✅ Product created successfully! ID: {response['id']}")
            
            # Ürün URL'sini göster
            product_url = response.get('permalink')
            if product_url:
                st.markdown(f"[View Product]({product_url})")
        else:
            st.error("Failed to create product")
            
    except Exception as e:
        st.error(f"Error creating product: {str(e)}")
        st.error("Full error details:")
        st.exception(e)

if __name__ == "__main__":
    woo_service.start_monitoring()
    create_dashboard() 