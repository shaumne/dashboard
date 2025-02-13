import streamlit as st
import json
import os

def load_settings():
    """Load settings from JSON file"""
    settings_file = 'config/settings.json'
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            return json.load(f)
    return {
        'items_per_page': 12,
        'ebay_app_id': '',
        'ebay_cert_id': '',
        'ebay_dev_id': '',
        'ebay_auth_token': '',
        'notification_email': '',
        'notification_whatsapp': '',
        'shipping_small_weight': 15,
        'shipping_medium_weight': 30,
        'shipping_small_price': 0,
        'shipping_medium_price': 20,
        'shipping_large_price': 150,
        'shipping_international_small': 100,
        'shipping_international_medium': 250,
        'shipping_international_large': 2500,
        'woocommerce_url': '',
        'woocommerce_consumer_key': '',
        'woocommerce_consumer_secret': '',
        'woocommerce_webhook_secret': ''
    }

def save_settings(settings):
    """Save settings to JSON file"""
    os.makedirs('config', exist_ok=True)
    with open('config/settings.json', 'w') as f:
        json.dump(settings, f, indent=4)

def show_settings():
    st.title("⚙️ Settings")
    
    # Load current settings
    settings = load_settings()
    
    # Display Settings
    st.subheader("📊 Display Settings")
    settings['items_per_page'] = st.number_input(
        "Items per page",
        min_value=6,
        max_value=24,
        value=settings.get('items_per_page', 12),
        step=3
    )
    
    # eBay API Settings
    st.subheader("🔑 eBay API Settings")
    with st.expander("eBay API Credentials", expanded=True):
        settings['ebay_app_id'] = st.text_input(
            "App ID (Client ID)", 
            value=settings.get('ebay_app_id', ''),
            type="password"
        )
        settings['ebay_cert_id'] = st.text_input(
            "Cert ID (Client Secret)", 
            value=settings.get('ebay_cert_id', ''),
            type="password"
        )
        settings['ebay_dev_id'] = st.text_input(
            "Dev ID", 
            value=settings.get('ebay_dev_id', ''),
            type="password"
        )
        settings['ebay_oauth_token'] = st.text_input(
            "OAuth Token", 
            value=settings.get('ebay_oauth_token', ''),
            type="password"
        )
    
    # Notification Settings
    st.subheader("📧 Notification Settings")
    with st.expander("Notification Preferences", expanded=True):
        settings['notification_email'] = st.text_input(
            "Email Address", 
            value=settings.get('notification_email', '')
        )
        settings['notification_whatsapp'] = st.text_input(
            "WhatsApp Number", 
            value=settings.get('notification_whatsapp', '')
        )
    
    
    # WooCommerce API Settings
    st.subheader("🛍️ WooCommerce Settings")
    with st.expander("WooCommerce API Credentials", expanded=True):
        settings['woocommerce_url'] = st.text_input(
            "Website URL (örn: https://your-store.com)", 
            value=settings.get('woocommerce_url', ''),
            help="WooCommerce sitenizin tam URL'si"
        )
        
        settings['woocommerce_consumer_key'] = st.text_input(
            "Consumer Key", 
            value=settings.get('woocommerce_consumer_key', ''),
            type="password",
            help="WooCommerce > Settings > Advanced > REST API'den alabilirsiniz"
        )
        
        settings['woocommerce_consumer_secret'] = st.text_input(
            "Consumer Secret", 
            value=settings.get('woocommerce_consumer_secret', ''),
            type="password",
            help="WooCommerce > Settings > Advanced > REST API'den alabilirsiniz"
        )
        
        settings['woocommerce_webhook_secret'] = st.text_input(
            "Webhook Secret (optional)", 
            value=settings.get('woocommerce_webhook_secret', ''),
            type="password",
            help="Webhook kullanıyorsanız güvenlik anahtarı"
        )
        
        # Test bağlantı butonu
        if st.button("Test Connection"):
            try:
                from woocommerce import API
                
                wcapi = API(
                    url=settings['woocommerce_url'],
                    consumer_key=settings['woocommerce_consumer_key'],
                    consumer_secret=settings['woocommerce_consumer_secret'],
                    version="wc/v3"
                )
                
                # Bağlantıyı test et
                response = wcapi.get("products")
                if response.status_code == 200:
                    st.success("✅ WooCommerce bağlantısı başarılı!")
                else:
                    st.error(f"❌ Bağlantı hatası: {response.status_code}")
                    
            except Exception as e:
                st.error(f"❌ Bağlantı hatası: {str(e)}")
    
    # Save Button
    if st.button("Save Settings", type="primary"):
        save_settings(settings)
        st.session_state.update(settings)
        st.success("✅ Settings saved successfully!")

if __name__ == "__main__":
    show_settings() 