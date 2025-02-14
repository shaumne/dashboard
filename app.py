import streamlit as st
import pandas as pd
import time
import plotly.express as px
from datetime import datetime
import os


st.set_page_config(
    page_title="IBidder Auction Monitor",
    page_icon="📊",
    layout="wide"
)

@st.cache_data(ttl=10)  # 10 saniyelik cache
def load_data():
    try:
        if os.path.exists('data/output/products.csv'):
            products_df = pd.read_csv('data/output/products.csv')
        else:
            products_df = pd.DataFrame()
            
        if os.path.exists('data/output/lots_details.csv'):
            lots_df = pd.read_csv('data/output/lots_details.csv')
        else:
            lots_df = pd.DataFrame()
            
        return products_df, lots_df
    except Exception as e:
        st.error(f"Veri yükleme hatası: {str(e)}")
        return pd.DataFrame(), pd.DataFrame()

def main():
    st.title("📊 IBidder Auction Monitor")
    
    # Sidebar
    st.sidebar.header("Kontrol Paneli")
    
    # Sayfa seçimi
    page = st.sidebar.selectbox(
        "Sayfa Seçin",
        ["Genel Bakış", "Ürünler", "Teklifler"]
    )
    
    refresh_interval = st.sidebar.slider("Yenileme Aralığı (saniye)", 5, 60, 10)
    auto_refresh = st.sidebar.checkbox('Otomatik Yenileme', value=True)
    
    if st.sidebar.button('Manuel Yenile'):
        st.cache_data.clear()
    
    # Verileri yükle
    products_df, lots_df = load_data()
    
    # Seçilen sayfayı göster
    if page == "Genel Bakış":
        show_overview(products_df, lots_df)
    elif page == "Ürünler":
        show_products(products_df)
    elif page == "Teklifler":
        show_bids(lots_df)
    
    # Son güncelleme zamanı
    st.sidebar.caption(f"Son Güncelleme: {datetime.now().strftime('%H:%M:%S')}")
    
    # Otomatik yenileme
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main() 