import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(
    page_title="i-bidder Data Center",
    page_icon="📊",
    layout="wide"
)

st.title("📊 i-bidder Data Center")

def clean_price(price_str):
    """Clean price string and convert to float"""
    try:
        if pd.isna(price_str):
            return 0.0
        return float(str(price_str).replace('GBP', '').replace('£', '').replace(',', '').strip())
    except:
        return 0.0

try:
    # Load data
    lots_df = pd.read_csv('.\data\output\lots_details.csv')
    lots_with_ebay_df = pd.read_csv('.\data\output\lots_details_with_ebay.csv')
    
    # Clean price data
    lots_df['current_bid'] = lots_df['current_bid'].apply(clean_price)
    lots_with_ebay_df['ebay_lowest_price'] = lots_with_ebay_df['ebay_lowest_price'].apply(clean_price)
    
    # Calculate total cost including fees
    lots_df['total_cost'] = lots_df.apply(
        lambda row: row['current_bid'] * (1 + float(row['commission'])/100 + float(row['vat_rate'])/100), 
        axis=1
    )
    
    # Dashboard metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Active Lots",
            value=len(lots_df),
            delta=f"{len(lots_df)} items"
        )
    
    with col2:
        avg_commission = lots_df['commission'].mean()
        st.metric(
            label="Average Commission",
            value=f"{avg_commission:.1f}%"
        )
    
    with col3:
        avg_vat = lots_df['vat_rate'].mean()
        st.metric(
            label="Average VAT",
            value=f"{avg_vat:.1f}%"
        )
    
    with col4:
        total_value = lots_df['current_bid'].sum()
        st.metric(
            label="Total Lots Value",
            value=f"£{total_value:,.2f}"
        )
    
    # Data Analysis Tabs
    st.markdown("### 📈 Market Analysis")
    
    tab1, tab2, tab3 = st.tabs(["Price Distribution", "Price Analysis", "Time Analysis"])
    
    with tab1:
        col1, col2 = st.columns(2)
        
        with col1:
            # Current Bids Distribution
            fig = px.histogram(
                lots_df,
                x='current_bid',
                nbins=30,
                title='Distribution of Current Bids',
                labels={'current_bid': 'Current Bid (£)', 'count': 'Number of Lots'}
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Box Plot of Prices
            fig = px.box(
                lots_df,
                y='current_bid',
                title='Price Distribution Statistics'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            # Price Comparison with eBay
            merged_df = pd.merge(lots_df, lots_with_ebay_df[['title', 'ebay_lowest_price']], on='title', how='inner')
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=merged_df['current_bid'],
                y=merged_df['ebay_lowest_price'],
                mode='markers',
                name='Items'
            ))
            fig.add_trace(go.Scatter(
                x=[0, merged_df['current_bid'].max()],
                y=[0, merged_df['current_bid'].max()],
                mode='lines',
                name='Equal Price Line',
                line=dict(dash='dash')
            ))
            fig.update_layout(
                title='Current Bid vs eBay Price Comparison',
                xaxis_title='Current Bid (£)',
                yaxis_title='eBay Price (£)'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Price Range Distribution
            price_ranges = pd.cut(lots_df['current_bid'], 
                                bins=[0, 100, 500, 1000, 5000, float('inf')],
                                labels=['0-100', '101-500', '501-1000', '1001-5000', '5000+'])
            range_counts = price_ranges.value_counts().sort_index()
            
            fig = px.pie(
                values=range_counts.values,
                names=range_counts.index,
                title='Price Range Distribution (£)'
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        # Time Analysis
        try:
            # Tarih formatını düzelt
            lots_df['bidding_ends'] = lots_df['bidding_ends'].str.replace('Bidding ends:', '').str.strip()
            lots_df['bidding_ends'] = pd.to_datetime(lots_df['bidding_ends'], format='%d %b %Y %H:%M GMT')
            lots_df['days_left'] = (lots_df['bidding_ends'] - pd.Timestamp.now()).dt.total_seconds() / (24*60*60)
            
            # Zaman analizi grafikleri
            col1, col2 = st.columns(2)
            
            with col1:
                # Günlere göre lot dağılımı
                fig = px.histogram(
                    lots_df,
                    x='days_left',
                    nbins=20,
                    title='Distribution of Auction End Times',
                    labels={'days_left': 'Days Left', 'count': 'Number of Lots'}
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Fiyat vs Kalan Süre
                fig = px.scatter(
                    lots_df,
                    x='days_left',
                    y='current_bid',
                    title='Price vs Time Left',
                    labels={'days_left': 'Days Left', 'current_bid': 'Current Bid (£)'}
                )
                fig.update_traces(marker=dict(size=8))
                fig.update_layout(
                    xaxis_title="Days Left",
                    yaxis_title="Current Bid (£)",
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"Error in time analysis: {str(e)}")
            st.info("Time analysis charts could not be displayed due to date format issues.")
    
    # Navigation Section
    st.markdown("### 🧭 Navigation")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        #### 🔨 Lots Dashboard
        View and filter all active auction lots
        """)
        st.page_link("pages/1_🔨_Lots.py", label="Go to Lots Dashboard")
    
    with col2:
        st.markdown("""
        #### 📊 Profitability Analysis
        Analyze potential profits and opportunities
        """)
        st.page_link("pages/2_📊_Profitability.py", label="Go to Profitability Analysis")
    

except Exception as e:
    st.error("Error loading data. Please ensure data files exist and are valid.")
    st.error(f"Error details: {str(e)}") 