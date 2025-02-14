import streamlit as st
import pandas as pd
import time
import plotly.express as px
from datetime import datetime
import os
from src.scrapers.price import PriceMonitor


st.set_page_config(
    page_title="IBidder Auction Monitor",
    page_icon="📊",
    layout="wide"
)

@st.cache_data(ttl=10)  # 10 seconds cache
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
            
        # Load price monitoring data
        if os.path.exists('data/check/published_products.csv'):
            price_df = pd.read_csv('data/check/published_products.csv')
        else:
            price_df = pd.DataFrame()
            
        return products_df, lots_df, price_df
    except Exception as e:
        st.error(f"Data loading error: {str(e)}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def main():
    st.title("📊 IBidder Auction Monitor")
    
    # Sidebar
    st.sidebar.header("Control Panel")
    
    # Page selection
    page = st.sidebar.selectbox(
        "Select Page",
        ["Overview", "Products", "Bids", "Price Monitor"]
    )
    
    refresh_interval = st.sidebar.slider("Refresh Interval (seconds)", 5, 60, 10)
    auto_refresh = st.sidebar.checkbox('Auto Refresh', value=True)
    
    if st.sidebar.button('Manual Refresh'):
        st.cache_data.clear()
    
    # Load data
    products_df, lots_df, price_df = load_data()
    
    # Display selected page
    if page == "Price Monitor":
        st.subheader("💰 Price Monitor")
        
        # Price monitoring controls
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Start Price Monitor"):
                monitor = PriceMonitor(driver_count=2, tabs_per_driver=2)
                st.session_state['price_monitor'] = monitor
                st.success("Price monitoring started!")
                
        with col2:
            if st.button("Stop Monitor"):
                if 'price_monitor' in st.session_state:
                    st.session_state['price_monitor'].stop_event.set()
                    del st.session_state['price_monitor']
                    st.info("Price monitoring stopped.")
                    
        with col3:
            if st.button("Check Now"):
                if 'price_monitor' in st.session_state:
                    st.session_state['price_monitor'].monitor_urls()
                    st.success("Price check initiated!")
        
        # Display price monitoring data
        if not price_df.empty:
            st.dataframe(
                price_df.style.apply(lambda x: ['background: #ffcdd2' if x['current_price'] != x['last_price'] 
                                              else '' for i in x], axis=1),
                use_container_width=True
            )
            
            # Price changes chart
            if 'current_price' in price_df.columns and 'last_price' in price_df.columns:
                price_changes = price_df[price_df['current_price'] != price_df['last_price']]
                if not price_changes.empty:
                    fig = px.bar(price_changes, 
                               x='title', 
                               y=['current_price', 'last_price'],
                               title='Price Changes',
                               labels={'value': 'Price (£)', 'variable': 'Price Type'},
                               barmode='group')
                    st.plotly_chart(fig)
        else:
            st.info("No price monitoring data available.")
    
    # Last update time
    st.sidebar.caption(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
    
    # Auto refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main() 