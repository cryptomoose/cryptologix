"""
cryptologix - Open Access Version (Authentication Disabled)
Entry point for the application without login requirement

To re-enable authentication: Replace this file with app_protected.py
or update the workflow to run: streamlit run app_protected.py --server.port 5000

Health check: Streamlit provides built-in health endpoint at /_stcore/health
"""
import streamlit as st
import logging

# Configure logging - WARNING level to minimize compute overhead for cost optimization
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s - %(name)s - %(message)s'
)

# Page config - must be first Streamlit command
st.set_page_config(
    page_title="cryptologix - Exponential Crypto Wealth",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for dark theme and styling
st.markdown("""
<style>
    /* Dark theme enforcement */
    .stApp {
        background-color: #0E1117;
        color: #FAFAFA;
    }
    
    /* Card styling */
    .cycle-phase-card {
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.05));
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .action-card {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 1.5rem;
        border-left: 4px solid;
        margin: 1rem 0;
    }
    
    /* Metric styling */
    .stMetric {
        background: rgba(255, 255, 255, 0.05);
        padding: 1rem;
        border-radius: 8px;
    }
    
    /* Button styling */
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
    }
    
    /* Sidebar hide */
    [data-testid="stSidebar"] {
        display: none;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 1rem 2rem;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

def main():
    """Main application entry point - Direct access without authentication"""
    
    # Lazy import - defer heavy module loading until needed
    # This allows health checks to pass before heavy imports complete
    from main_app_content import render_crypto_app
    
    # Render the crypto analysis app
    render_crypto_app()

if __name__ == "__main__":
    main()
