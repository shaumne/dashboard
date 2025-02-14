import streamlit as st
import pandas as pd
from math import ceil
import subprocess
import sys
import os
import signal
import nest_asyncio
import time
from datetime import datetime

@st.cache_data(ttl=2)
def load_lots_data():
    """Load data from lots_details.csv"""
    try:
        if os.path.exists('data/output/lots_details.csv'):
            lots_df = pd.read_csv('data/output/lots_details.csv')
            
            # Clean data
            def clean_percentage(value):
                if pd.isna(value):
                    return 0.0
                if isinstance(value, str):
                    return float(value.replace('%', '').strip())
                return float(value)
            
            lots_df['commission'] = lots_df['commission'].apply(clean_percentage)
            lots_df['vat_rate'] = lots_df['vat_rate'].apply(clean_percentage)
            
            # Fill NaN values
            lots_df['url'] = lots_df['url'].fillna('')
            lots_df['current_bid'] = lots_df['current_bid'].fillna('No Bid')
            lots_df['images'] = lots_df['images'].fillna('[]').apply(eval)
            
            return lots_df
        else:
            return None
            
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return None

class Dashboard:
    def __init__(self):
        st.set_page_config(
            page_title="i-bidder Lots Dashboard",
            page_icon="🔨",
            layout="wide"
        )
        
        # Session state initialization
        if 'lots_df' not in st.session_state:
            st.session_state.lots_df = None
        if 'page_number' not in st.session_state:
            st.session_state.page_number = 1
        if 'process' not in st.session_state:
            st.session_state.process = None
        if 'last_refresh' not in st.session_state:
            st.session_state.last_refresh = time.time()
            
        self.items_per_page = 12
        self.refresh_interval = 2  # 2 saniye

    def clean_price(self, price):
        """Clean and convert price value"""
        if pd.isna(price):
            return None
        if isinstance(price, (int, float)):
            return price
        try:
            # Clean and convert if string
            if isinstance(price, str):
                price = price.replace('$', '').replace(',', '').strip()
                return float(price)
            return None
        except:
            return None

    def update_ibidder_data(self):
        """Update i-bidder data section"""
        st.subheader("🔄 Update i-bidder Data")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            info_placeholder = st.empty()
            error_placeholder = st.empty()
            info_placeholder.info("This will fetch new data from i-bidder.com")
        
        with col2:
            if st.button("Update Data", type="primary", help="Fetch new data from i-bidder"):
                with st.spinner("Updating data... This may take a while..."):
                    try:
                        # Import scraper
                        from src.scrapers.ibidder_scraper import run_scraper
                        
                        # Create progress bar
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        # Run the scraper
                        status_text.text("Step 1/2: Fetching product listings...")
                        progress_bar.progress(25)
                        
                        if run_scraper():
                            progress_bar.progress(100)
                            status_text.text("Completed! Refreshing page...")
                            st.success("✅ Data updated successfully!")
                            time.sleep(2)  # Give time to see success message
                            st.rerun()  # Refresh the page
                        else:
                            progress_bar.empty()
                            status_text.empty()
                            st.error("❌ Error updating data")
                            
                    except Exception as e:
                        st.error(f"Error running scraper: {str(e)}")
                    finally:
                        # Clean up progress indicators
                        try:
                            progress_bar.empty()
                            status_text.empty()
                        except:
                            pass

    def show_metrics(self):
        if st.session_state.lots_df is not None:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Lots", len(st.session_state.lots_df))
            
            with col2:
                has_current = st.session_state.lots_df['has_current_bid'].eq('TRUE').sum()
                st.metric("Lots with Bids", has_current)
            
            with col3:
                avg_commission = st.session_state.lots_df['commission'].mean()
                st.metric("Average Commission", f"{avg_commission:.1f}%")
            
            with col4:
                avg_vat = st.session_state.lots_df['vat_rate'].mean()
                st.metric("Average VAT", f"{avg_vat:.1f}%")

    def show_lots_grid(self, lots_df):
        # Calculate total pages
        total_pages = ceil(len(lots_df) / self.items_per_page)
        
        # Check page number
        if st.session_state.page_number > total_pages:
            st.session_state.page_number = total_pages
        
        # Get current page items
        start_idx = (st.session_state.page_number - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_items = lots_df.iloc[start_idx:end_idx]
        
        # Pagination controls
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown(f"Page {st.session_state.page_number} of {total_pages}")
            
            prev, _ , next = st.columns([1, 2, 1])
            with prev:
                if st.button("Previous") and st.session_state.page_number > 1:
                    st.session_state.page_number -= 1
                    st.rerun()
            with next:
                if st.button("Next") and st.session_state.page_number < total_pages:
                    st.session_state.page_number += 1
                    st.rerun()
        
        # Grid display
        cols = st.columns(3)
        for idx, lot in page_items.iterrows():
            with cols[idx % 3]:
                st.markdown("---")
                
                # Image handling
                if lot['images'] and len(lot['images']) > 0:
                    try:
                        st.image(lot['images'][0], use_container_width=True)
                    except:
                        st.markdown("📷 No Image Available")
                else:
                    st.markdown("📷 No Image Available")
                
                # Lot name
                st.markdown(f"**{lot.get('name', 'N/A')}**")
                
                # Bid information
                if lot.get('has_current_bid'):
                    st.markdown(f"🔨 Current Bid: {lot['current_bid']}")
                if lot.get('has_opening_bid'):
                    st.markdown(f"🎯 Opening Bid: {lot['opening_bid']}")
                if lot.get('has_estimate'):
                    st.markdown(f"📊 Estimate: {lot['estimate_bid']}")
                if lot.get('has_buy_it_now'):
                    st.markdown(f"💰 Buy It Now: {lot['buy_it_now']}")
                
                # Commission and VAT info
                if pd.notna(lot.get('commission')):
                    st.markdown(f"💼 Commission: {lot['commission']}%")
                if pd.notna(lot.get('vat_rate')):
                    st.markdown(f"📊 VAT: {lot['vat_rate']}%")
                
                # End time
                if pd.notna(lot.get('end_time')):
                    st.markdown(f"⏰ {lot['end_time']}")
                
                # URL button
                if lot.get('url'):
                    st.markdown(f'''
                        <a href="{lot['url']}" target="_blank">
                            <button style="
                                background-color: #4CAF50;
                                border: none;
                                color: white;
                                padding: 10px 24px;
                                text-align: center;
                                text-decoration: none;
                                display: inline-block;
                                font-size: 16px;
                                margin: 4px 2px;
                                cursor: pointer;
                                border-radius: 4px;
                                width: 100%;">
                                View Lot 🔍
                            </button>
                        </a>
                    ''', unsafe_allow_html=True)

    def open_lot(self, url):
        """Lot URL'sini yeni sekmede aç"""
        js = f"""<script>window.open('{url}', '_blank').focus();</script>"""
        st.markdown(js, unsafe_allow_html=True)

    def show_filters(self):
        col1, col2 = st.columns(2)
        
        filters = {}
        with col1:
            search = st.text_input("Search lots...", "")
            if search:
                filters['search'] = search
        
        return filters

    def apply_filters(self, df, filters):
        if 'search' in filters:
            df = df[df['name'].str.contains(filters['search'], case=False, na=False)]
        return df

    def run(self):
        st.title("🔨 i-bidder Lots Dashboard")
        
        # Auto refresh control in sidebar
        with st.sidebar:
            auto_refresh = st.checkbox("Otomatik Yenileme", value=True)
            st.caption(f"Son yenileme: {datetime.now().strftime('%H:%M:%S')}")
        
        # Update data section
        self.update_ibidder_data()
        
        st.markdown("---")
        
        # Check if it's time to refresh
        current_time = time.time()
        if auto_refresh and (current_time - st.session_state.last_refresh) >= self.refresh_interval:
            st.cache_data.clear()
            st.session_state.last_refresh = current_time
        
        # Load data - sınıf dışındaki fonksiyonu kullan
        lots_df = load_lots_data()
        if lots_df is not None:
            st.session_state.lots_df = lots_df
            
            # Main metrics
            self.show_metrics()
            
            # Filters
            filters = self.show_filters()
            
            # Apply filters
            filtered_df = self.apply_filters(st.session_state.lots_df.copy(), filters)
            
            self.show_lots_grid(filtered_df)
            
            # Auto refresh if enabled
            if auto_refresh:
                time.sleep(self.refresh_interval)
                st.rerun()

if __name__ == "__main__":
    dashboard = Dashboard()
    dashboard.run() 