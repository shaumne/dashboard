import streamlit as st
import pandas as pd
from woocommerce import API
import json
import csv
import os
from datetime import datetime
from src.services.ebay_category_finder import EbayCategoryFinder
import time

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
            
            # CSV'ye kaydetme işlemi
            csv_file = 'data/check/published_products.csv'
            
            # CSV verilerini hazırla
            csv_data = {
                'title': title,
                'auction_url': row.get('url', ''),  # Açık artırma URL'si
                'woo_product_id': product['id'],    # WooCommerce ürün ID'si
                'product_url': product['permalink'],  # WooCommerce ürün URL'si
                'current_price': regular_price,      # Current price
                'last_price': regular_price,        # Initial last price is same as current
                'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Initial check time
            }
            
            # CSV dosyası yoksa oluştur
            if not os.path.exists(csv_file):
                with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['title', 'auction_url', 'woo_product_id', 
                                                         'product_url', 'current_price', 'last_price', 
                                                         'last_check'])
                    writer.writeheader()
            
            # CSV'ye yeni satır ekle
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['title', 'auction_url', 'woo_product_id', 
                                                     'product_url', 'current_price', 'last_price', 
                                                     'last_check'])
                writer.writerow(csv_data)
            
            st.success(f"""
                ✅ Ürün başarıyla oluşturuldu!
                - ID: {product['id']}
                - URL: {product['permalink']}
                - CSV'ye kaydedildi ✓
            """)
            
            # Ürün sayfasını aç
            js = f"""
                <script>
                    window.open('{product['permalink']}', '_blank');
                </script>
            """
            st.markdown(js, unsafe_allow_html=True)
            
            return True
            
        else:
            st.error(f"Ürün oluşturma hatası: {response.text}")
            return False
            
    except Exception as e:
        st.error(f"Ürün oluşturma hatası: {str(e)}")
        return False

def create_product_page():
    st.title("🛍️ Create New Product")
    
    if 'product_data' not in st.session_state:
        st.error("No product selected! Please select a product from the Profitability page.")
        # JavaScript ile geri dönüş
        js = """
            <script>
                var button = document.querySelector('button');
                button.onclick = function() {
                    window.parent.location.href = '/Profitability';
                }
            </script>
        """
        st.markdown(js, unsafe_allow_html=True)
        if st.button("← Go Back"):
            pass  # JavaScript ile yönlendirme yapılacak
        return
        
    row = st.session_state.product_data
    
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

    with st.form(key="create_product_form"):
        st.markdown("<div class='form-container'>", unsafe_allow_html=True)
        
        # Ana bilgiler
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📝 Basic Information")
            title = st.text_input("Title", value=row['name'])
            regular_price = st.number_input("Price (£)", 
                value=float(row['ebay_price']) if pd.notna(row['ebay_price']) else 0.0,
                step=0.01)
                
            # SKU oluşturma
            product_name = str(row['name'])
            safe_sku = ''.join(e for e in product_name if e.isalnum())[:20]
            sku = st.text_input("SKU", value=f"AUC-{safe_sku}")
            
            stock = st.number_input("Stock", value=1, min_value=1)
        
        with col2:
            st.subheader("🏷️ Product Details")
            # Durum ve garanti
            condition_options = ["New", "Used - Like New", "Used - Good", "Used - Fair"]
            condition = st.selectbox("Condition", condition_options, 
                index=0 if "new" in str(row['name']).lower() else 1)
            
            warranty_options = ["No Warranty", "30 Days", "90 Days", "1 Year"]
            warranty = st.selectbox("Warranty", warranty_options)
            
            # eBay'den gelen kategorileri göster
            if categories_info and categories_info.get('woo_categories'):
                default_categories = [cat['name'] for cat in categories_info['woo_categories']]
            else:
                default_categories = ["Electronics", "Computers", "Mobile Phones"]
            
            selected_categories = st.multiselect(
                "Categories",
                options=default_categories + ["Electronics", "Computers", "Mobile Phones"],
                default=default_categories[:3]
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

        # Açıklama ve detaylar
        st.subheader("📄 Description & Details")
        
        # Item Specifics'i açıklamaya ekle
        specs_text = ""
        if categories_info and categories_info.get('specifics'):
            specs_text = "\n\nProduct Specifications:\n"
            for spec in categories_info['specifics']:
                specs_text += f"- {spec['Name']}: {spec['Value']}\n"
        
        col3, col4 = st.columns(2)
        
        with col3:
            ebay_details = st.text_area("eBay Details", 
                value=f"Original Price: £{row['ebay_price']}\nSource: {row['price_source']}")
        
        with col4:
            description = st.text_area("Description", 
                value=f"{row['description']}{specs_text}\n\nCondition: {condition}\nWarranty: {warranty}")

        st.markdown("</div>", unsafe_allow_html=True)
        
        # Önizleme
        with st.expander("👁️ Preview Product"):
            st.markdown("<div class='preview-container'>", unsafe_allow_html=True)
            st.image(eval(row['images'])[0] if isinstance(row['images'], str) and eval(row['images']) else "https://via.placeholder.com/400")
            st.markdown(f"### {title}")
            st.markdown(f"**Price:** £{regular_price}")
            st.markdown(f"**SKU:** {sku}")
            st.markdown(f"**Brand:** {brand}")
            st.markdown(f"**Condition:** {condition}")
            st.markdown("#### Description")
            st.markdown(description)
            st.markdown("</div>", unsafe_allow_html=True)

        # Form gönderme butonu
        submit = st.form_submit_button("🚀 Create Product", type="primary", use_container_width=True)
        
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
                st.balloons()
                # 3 saniye sonra Profitability sayfasına dön
                time.sleep(3)
                js = """
                    <script>
                        window.parent.location.href = '/Profitability';
                    </script>
                """
                st.markdown(js, unsafe_allow_html=True)

if __name__ == "__main__":
    create_product_page() 