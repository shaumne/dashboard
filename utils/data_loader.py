import streamlit as st
import pandas as pd

def clean_price(price):
    if pd.isna(price):
        return None
    if isinstance(price, (int, float)):
        return price
    try:
        if isinstance(price, str):
            price = price.replace('$', '').replace(',', '').strip()
            return float(price)
        return None
    except:
        return None

def load_data():
    with st.spinner('Loading lots...'):
        try:
            lots_df = pd.read_csv('lot_data.csv')
            
            if 'opening_price' in lots_df.columns:
                lots_df['opening_price'] = lots_df['opening_price'].apply(clean_price)
            if 'current_price' in lots_df.columns:
                lots_df['current_price'] = lots_df['current_price'].apply(clean_price)
            
            st.success(f"Loaded {len(lots_df)} lots!")
            st.session_state.lots_df = lots_df
            
        except Exception as e:
            st.error(f"Error loading data: {str(e)}") 