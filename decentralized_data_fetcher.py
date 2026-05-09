"""
Decentralized Data Fetcher for Cryptologix
Multi-source redundancy with automatic failover for maximum reliability
"""

import yfinance as yf
import pandas as pd
import requests
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import streamlit as st

class DecentralizedDataFetcher:
    """
    Multi-source cryptocurrency data fetcher with automatic failover.
    Implements data source diversification for censorship resistance.
    """
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.sources = self._initialize_sources()
        self.cache = {}
        self.cache_duration = 0  # No caching - always fetch fresh data
        
    def _setup_logging(self):
        """Setup logging for data source monitoring"""
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)
    
    def _initialize_sources(self):
        """Initialize all available data sources with priority ranking"""
        return [
            {
                'name': 'yahoo_finance',
                'priority': 1,
                'fetcher': YahooFinanceFetcher(),
                'supports': ['BTC-USD', 'ETH-USD', 'GLD', 'SI=F', 'SLV', 'PPLT', 'PALL'],
                'status': 'active'
            },
            {
                'name': 'coingecko',
                'priority': 2,
                'fetcher': CoinGeckoFetcher(),
                'supports': ['bitcoin', 'ethereum'],
                'status': 'active'
            },
            {
                'name': 'cryptocompare',
                'priority': 3,
                'fetcher': CryptoCompareFetcher(),
                'supports': ['BTC', 'ETH'],
                'status': 'active'
            },
            {
                'name': 'binance',
                'priority': 4,
                'fetcher': BinanceFetcher(),
                'supports': ['BTCUSDT', 'ETHUSDT'],
                'status': 'active'
            }
        ]
    
    def get_crypto_data(self, symbol: str, period: str = "max", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch cryptocurrency data with automatic failover between sources
        
        Args:
            symbol: Crypto symbol (BTC-USD, ETH-USD, etc.)
            period: Time period (max, 1y, 2y, etc.)
            interval: Data interval (1d, 1h, 1wk)
            
        Returns:
            DataFrame with OHLCV data from most reliable available source
        """
        
        # Check cache first
        cache_key = f"{symbol}_{period}_{interval}"
        if self._is_cached_valid(cache_key):
            self.logger.info(f"Returning cached data for {symbol}")
            return self.cache[cache_key]['data']
        
        # Try each source in priority order
        for source in sorted(self.sources, key=lambda x: x['priority']):
            if source['status'] != 'active':
                continue
                
            # Convert symbol to source-specific format
            source_symbol = self._convert_symbol(symbol, source['name'])
            if source_symbol not in source['supports']:
                continue
            
            try:
                self.logger.info(f"Attempting to fetch {symbol} from {source['name']}")
                data = source['fetcher'].fetch_data(source_symbol, period, interval)
                
                if self._validate_data(data):
                    self.logger.info(f"Successfully fetched {symbol} from {source['name']}")
                    # Cache the result
                    self.cache[cache_key] = {
                        'data': data,
                        'timestamp': datetime.now(),
                        'source': source['name']
                    }
                    return data
                else:
                    self.logger.warning(f"Invalid data from {source['name']} for {symbol}")
                    
            except Exception as e:
                self.logger.error(f"Error fetching {symbol} from {source['name']}: {e}")
                source['status'] = 'error'  # Temporarily disable failed source
                continue
        
        # If all sources fail for GC=F, silently return None (handled by fallback)
        if symbol == 'GC=F':
            return None
            
        # For other symbols, show error
        st.error(f"All data sources failed for {symbol}")
        return pd.DataFrame()
    
    def _convert_symbol(self, symbol: str, source_name: str) -> str:
        """Convert symbol to source-specific format"""
        symbol_map = {
            'yahoo_finance': {
                'BTC-USD': 'BTC-USD',
                'ETH-USD': 'ETH-USD',
                'GLD': 'GLD',
                'SLV': 'SLV',
                'PPLT': 'PPLT',
                'PALL': 'PALL'
            },
            'coingecko': {
                'BTC-USD': 'bitcoin',
                'ETH-USD': 'ethereum'
            },
            'cryptocompare': {
                'BTC-USD': 'BTC',
                'ETH-USD': 'ETH'
            },
            'binance': {
                'BTC-USD': 'BTCUSDT',
                'ETH-USD': 'ETHUSDT'
            }
        }
        
        return symbol_map.get(source_name, {}).get(symbol, symbol)
    
    def _validate_data(self, data: pd.DataFrame) -> bool:
        """Validate that data meets quality requirements"""
        if data is None or data.empty:
            return False
            
        required_columns = ['Open', 'High', 'Low', 'Close']
        if not all(col in data.columns for col in required_columns):
            return False
            
        # Check for reasonable data (no negative prices, OHLC relationships)
        if (data[['Open', 'High', 'Low', 'Close']] <= 0).any().any():
            return False
            
        # Check OHLC consistency (High >= Low, etc.)
        if not (data['High'] >= data['Low']).all():
            return False
            
        return True
    
    def _is_cached_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self.cache:
            return False
            
        cache_age = (datetime.now() - self.cache[cache_key]['timestamp']).seconds
        return cache_age < self.cache_duration
    
    def get_source_status(self) -> Dict[str, Any]:
        """Get current status of all data sources"""
        return {
            source['name']: {
                'status': source['status'],
                'priority': source['priority'],
                'supports': source['supports']
            }
            for source in self.sources
        }


class YahooFinanceFetcher:
    """Yahoo Finance data fetcher (current primary source)"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_data(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data using yfinance"""
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            raise Exception(f"No data returned for {symbol}")
        
        # Clean data
        df = df.drop(columns=['Dividends', 'Stock Splits'], errors='ignore')
        df.index = pd.to_datetime(df.index)
        df = df.dropna()
        df = df.sort_index()
        
        return df


class CoinGeckoFetcher:
    """CoinGecko API data fetcher (free tier: 10-50 calls/minute)"""
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        self.session = requests.Session()
    
    def fetch_data(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data from CoinGecko API"""
        
        # Convert period to days
        days_map = {
            'max': 'max',
            '1y': '365',
            '2y': '730',
            '5y': '1825'
        }
        days = days_map.get(period, '365')
        
        url = f"{self.base_url}/coins/{symbol}/market_chart"
        params = {
            'vs_currency': 'usd',
            'days': days,
            'interval': 'daily' if interval == '1d' else 'hourly'
        }
        
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Convert to DataFrame
        prices = data['prices']
        volumes = data['total_volumes']
        
        df_data = []
        for i, (timestamp, price) in enumerate(prices):
            volume = volumes[i][1] if i < len(volumes) else 0
            df_data.append({
                'timestamp': pd.to_datetime(timestamp, unit='ms'),
                'Close': price,
                'Volume': volume,
                'Open': price,  # CoinGecko doesn't provide OHLC, use close as approximation
                'High': price,
                'Low': price
            })
        
        df = pd.DataFrame(df_data)
        df.set_index('timestamp', inplace=True)
        df = df.sort_index()
        
        return df


class CryptoCompareFetcher:
    """CryptoCompare API data fetcher (free tier: 100,000 calls/month)"""
    
    def __init__(self):
        self.base_url = "https://min-api.cryptocompare.com/data/v2"
        self.session = requests.Session()
    
    def fetch_data(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data from CryptoCompare API"""
        
        # Determine endpoint and limit
        if interval == '1d':
            endpoint = 'histoday'
            limit = 2000 if period == 'max' else 365
        elif interval == '1h':
            endpoint = 'histohour'
            limit = 2000
        else:
            endpoint = 'histoday'
            limit = 365
        
        url = f"{self.base_url}/{endpoint}"
        params = {
            'fsym': symbol,
            'tsym': 'USD',
            'limit': limit
        }
        
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data['Response'] != 'Success':
            raise Exception(f"CryptoCompare API error: {data.get('Message', 'Unknown error')}")
        
        # Convert to DataFrame
        price_data = data['Data']['Data']
        df_data = []
        
        for item in price_data:
            df_data.append({
                'timestamp': pd.to_datetime(item['time'], unit='s'),
                'Open': item['open'],
                'High': item['high'],
                'Low': item['low'],
                'Close': item['close'],
                'Volume': item['volumeto']
            })
        
        df = pd.DataFrame(df_data)
        df.set_index('timestamp', inplace=True)
        df = df.sort_index()
        
        return df


class BinanceFetcher:
    """Binance public API data fetcher (no authentication required)"""
    
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"
        self.session = requests.Session()
    
    def fetch_data(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """Fetch data from Binance public API"""
        
        # Convert interval
        interval_map = {
            '1d': '1d',
            '1h': '1h',
            '1wk': '1w'
        }
        binance_interval = interval_map.get(interval, '1d')
        
        # Calculate start time based on period
        end_time = int(datetime.now().timestamp() * 1000)
        period_days = {
            'max': 1500,  # Binance limit
            '1y': 365,
            '2y': 730,
            '5y': 1500
        }
        days = period_days.get(period, 365)
        start_time = end_time - (days * 24 * 60 * 60 * 1000)
        
        url = f"{self.base_url}/klines"
        params = {
            'symbol': symbol,
            'interval': binance_interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': 1000
        }
        
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Convert to DataFrame
        df_data = []
        for kline in data:
            df_data.append({
                'timestamp': pd.to_datetime(int(kline[0]), unit='ms'),
                'Open': float(kline[1]),
                'High': float(kline[2]),
                'Low': float(kline[3]),
                'Close': float(kline[4]),
                'Volume': float(kline[5])
            })
        
        df = pd.DataFrame(df_data)
        df.set_index('timestamp', inplace=True)
        df = df.sort_index()
        
        return df