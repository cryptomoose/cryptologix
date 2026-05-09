import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import streamlit as st

class CryptoDataFetcher:
    """Handles fetching cryptocurrency data from various sources"""
    
    def __init__(self):
        self.session = requests.Session()
        # Add headers to avoid rate limiting
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_crypto_data(self, symbol, period="max", interval="1d"):
        """
        Fetch cryptocurrency data using yfinance with maximum historical coverage
        
        Args:
            symbol (str): Cryptocurrency symbol (e.g., 'BTC-USD', 'ETH-USD')
            period (str): Time period ('1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'max')
            interval (str): Data interval ('1d', '1h', '1wk')
        
        Returns:
            pandas.DataFrame: Historical price data from earliest available date
        """
        try:
            # Create ticker object
            ticker = yf.Ticker(symbol)
            
            # Download historical data
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                st.error(f"No data found for symbol {symbol}")
                return pd.DataFrame()
            
            # Clean and prepare data
            df = df.drop(columns=['Dividends', 'Stock Splits'], errors='ignore')
            df.index = pd.to_datetime(df.index)
            
            # Remove any rows with missing data
            df = df.dropna()
            
            # Ensure we have required columns
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_columns):
                st.error(f"Missing required columns in data for {symbol}")
                return pd.DataFrame()
            
            # Sort by date
            df = df.sort_index()
            
            return df
            
        except Exception as e:
            st.error(f"Error fetching data for {symbol}: {str(e)}")
            return pd.DataFrame()
    
    def get_real_time_price(self, symbol):
        """
        Get current real-time price for a cryptocurrency
        
        Args:
            symbol (str): Cryptocurrency symbol
        
        Returns:
            dict: Current price information
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            current_price = info.get('regularMarketPrice', 0)
            if current_price == 0:
                # Fallback to fast_info
                current_price = ticker.fast_info.get('lastPrice', 0)
            
            return {
                'price': current_price,
                'change': info.get('regularMarketChange', 0),
                'change_percent': info.get('regularMarketChangePercent', 0),
                'volume': info.get('regularMarketVolume', 0),
                'market_cap': info.get('marketCap', 0)
            }
            
        except Exception as e:
            st.warning(f"Could not fetch real-time data for {symbol}: {str(e)}")
            return {'price': 0, 'change': 0, 'change_percent': 0, 'volume': 0, 'market_cap': 0}
    
    def validate_data_quality(self, df):
        """
        Validate the quality of fetched data
        
        Args:
            df (pandas.DataFrame): Price data
        
        Returns:
            dict: Data quality metrics
        """
        if df.empty:
            return {'valid': False, 'issues': ['No data available']}
        
        issues = []
        
        # Check for missing values
        missing_data = df.isnull().sum()
        if missing_data.any():
            issues.append(f"Missing data points: {missing_data.to_dict()}")
        
        # Check for price anomalies (prices <= 0)
        if (df['Close'] <= 0).any():
            issues.append("Invalid price data (prices <= 0)")
        
        # Check for volume anomalies
        if (df['Volume'] < 0).any():
            issues.append("Invalid volume data (negative volumes)")
        
        # Check data continuity (gaps in daily data)
        date_diff = df.index.to_series().diff().dt.days
        large_gaps = date_diff[date_diff > 2]  # More than 2 days gap
        if not large_gaps.empty:
            issues.append(f"Data gaps detected: {len(large_gaps)} gaps > 2 days")
        
        # Check minimum data points
        min_required_points = 50  # Minimum for meaningful analysis
        if len(df) < min_required_points:
            issues.append(f"Insufficient data points: {len(df)} < {min_required_points}")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues,
            'data_points': len(df),
            'date_range': f"{df.index.min().date()} to {df.index.max().date()}",
            'missing_percentage': (df.isnull().sum().sum() / df.size) * 100
        }
    
    def get_multiple_symbols(self, symbols, period="max"):
        """
        Fetch data for multiple cryptocurrency symbols
        
        Args:
            symbols (list): List of cryptocurrency symbols
            period (str): Time period
        
        Returns:
            dict: Dictionary with symbol as key and DataFrame as value
        """
        data = {}
        
        for symbol in symbols:
            try:
                df = self.get_crypto_data(symbol, period)
                if not df.empty:
                    data[symbol] = df
                    time.sleep(0.1)  # Small delay to avoid rate limiting
            except Exception as e:
                st.warning(f"Failed to fetch data for {symbol}: {str(e)}")
        
        return data
    
    def get_market_overview(self):
        """
        Get overview of major cryptocurrency markets
        
        Returns:
            pandas.DataFrame: Market overview data
        """
        major_cryptos = ['BTC-USD', 'ETH-USD', 'ADA-USD', 'DOT-USD', 'SOL-USD']
        overview_data = []
        
        for symbol in major_cryptos:
            try:
                real_time_data = self.get_real_time_price(symbol)
                if real_time_data['price'] > 0:
                    overview_data.append({
                        'Symbol': symbol.replace('-USD', ''),
                        'Price': real_time_data['price'],
                        'Change': real_time_data['change'],
                        'Change %': real_time_data['change_percent'],
                        'Volume': real_time_data['volume'],
                        'Market Cap': real_time_data['market_cap']
                    })
            except Exception as e:
                continue
        
        return pd.DataFrame(overview_data)
