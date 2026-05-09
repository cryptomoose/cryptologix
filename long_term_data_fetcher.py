import pandas as pd
import numpy as np
import requests
import yfinance as yf
from datetime import datetime, timedelta
import time
import logging

class LongTermDataFetcher:
    """
    Comprehensive data fetcher with multiple sources for 10+ year historical data
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._cache = {}
        self._cache_expiry = {}
        self.cache_duration = 21600  # 6 hour cache matches Streamlit cache layer
    
    def validate_data_freshness(self, data, symbol, max_age_hours=24):
        """
        Validate that data is fresh enough for weekly strategy decisions
        Relaxed thresholds since we use daily data only (no intraday)
        Returns (is_fresh, age_hours, latest_timestamp)
        """
        if data is None or len(data) == 0:
            return False, None, None
        
        latest_timestamp = data.index[-1]
        if latest_timestamp.tzinfo is not None:
            latest_timestamp = latest_timestamp.replace(tzinfo=None)
        
        age = datetime.now() - latest_timestamp
        age_hours = age.total_seconds() / 3600
        
        is_fresh = age_hours <= max_age_hours
        
        if not is_fresh:
            self.logger.warning(f"⚠️ {symbol} data is {age_hours:.1f} hours old (threshold: {max_age_hours}h)")
        else:
            self.logger.info(f"✓ {symbol} data is fresh: {age_hours:.1f} hours old")
        
        return is_fresh, age_hours, latest_timestamp
        
    def get_coingecko_data(self, coin_id, days='max'):
        """
        Get historical data from CoinGecko (free API)
        coin_id: 'bitcoin' or 'ethereum'
        days: 'max' for maximum available data, or specific number of days
        """
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            
            # Use maximum available data for CoinGecko (try very large number)
            if days == 'max':
                days = 5000  # ~13+ years, should capture all crypto history
            
            params = {
                'vs_currency': 'usd',
                'days': days,
                'interval': 'daily'
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            # Convert to DataFrame
            prices = data['prices']
            volumes = data['total_volumes']
            
            df = pd.DataFrame(prices, columns=['timestamp', 'close'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            # Add volume data
            vol_df = pd.DataFrame(volumes, columns=['timestamp', 'volume'])
            vol_df['timestamp'] = pd.to_datetime(vol_df['timestamp'], unit='ms')
            vol_df.set_index('timestamp', inplace=True)
            
            df['volume'] = vol_df['volume']
            
            # For OHLC, we'll use close as approximation (CoinGecko free doesn't provide OHLC)
            df['open'] = df['close'].shift(1)
            df['high'] = df['close'] * 1.02  # Rough approximation
            df['low'] = df['close'] * 0.98   # Rough approximation
            df.dropna(inplace=True)
            
            # Rename columns to match yfinance format
            df.columns = ['Close', 'Volume', 'Open', 'High', 'Low']
            df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
            return df
            
        except Exception as e:
            self.logger.error(f"CoinGecko API failed for {coin_id}: {str(e)}")
            return None
            
    def get_fred_gold_data(self):
        """
        Get gold price data from FRED (Federal Reserve Economic Data)
        Free API with very long historical data
        """
        try:
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': 'GOLDAMGBD228NLBM',  # Gold price USD per ounce
                'api_key': 'demo',  # Demo key - user can provide real key
                'file_type': 'json',
                'observation_start': '1970-01-01'  # Get maximum historical gold data (50+ years)
            }
            
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                observations = data['observations']
                
                df = pd.DataFrame(observations)
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                df.set_index('date', inplace=True)
                df.dropna(inplace=True)
                
                # Create OHLC format from daily close prices
                df['Close'] = df['value']
                df['Open'] = df['Close'].shift(1)
                df['High'] = df['Close'] * 1.001
                df['Low'] = df['Close'] * 0.999
                df['Volume'] = 1000000  # Dummy volume
                
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
                return df
                
        except Exception as e:
            self.logger.error(f"FRED API failed: {str(e)}")
            
        return None
        
    def get_yahoo_finance_max_data(self, symbol):
        """
        Get maximum available data from Yahoo Finance - daily data only
        Simplified for weekly strategy - no intraday complexity needed
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # Get historical daily data (sufficient for weekly strategy)
            data = ticker.history(period='max', interval='1d', auto_adjust=True)
            
            if data.empty:
                self.logger.error(f"No historical data for {symbol}")
                return None
            
            # Normalize timezone
            try:
                if data.index.tz is not None:
                    data.index = data.index.tz_localize(None)
            except TypeError:
                pass
            
            if len(data) > 0:
                # Ensure proper column names
                if 'Adj Close' in data.columns:
                    data['Close'] = data['Adj Close']
                
                latest_price = data['Close'].iloc[-1]
                self.logger.info(f"{symbol}: {len(data)} days, latest price: ${latest_price:,.2f}")
                
                return data[['Open', 'High', 'Low', 'Close', 'Volume']]
            return None
            
        except Exception as e:
            self.logger.error(f"Yahoo Finance failed for {symbol}: {str(e)}")
            return None
    
    def get_comprehensive_crypto_data(self, symbol):
        """
        Get crypto data from multiple sources with fallback
        """
        # Map symbols to CoinGecko IDs
        coingecko_map = {
            'BTC-USD': 'bitcoin',
            'ETH-USD': 'ethereum'
        }
        
        # Try Yahoo Finance first (most reliable OHLC)
        data = self.get_yahoo_finance_max_data(symbol)
        if data is not None and len(data) > 1000:
            self.logger.info(f"Yahoo Finance success for {symbol}: {len(data)} days")
            return data
            
        # Try CoinGecko as fallback
        if symbol in coingecko_map:
            coin_id = coingecko_map[symbol]
            data = self.get_coingecko_data(coin_id, days='max')
            if data is not None and len(data) > 500:
                self.logger.info(f"CoinGecko success for {symbol}: {len(data)} days")
                return data
                
        return None
        
    def get_comprehensive_gold_data(self):
        """
        Get gold data from multiple sources with fallback - simplified and stable
        """
        # Try Yahoo Finance Gold Futures (GC=F) first - spot gold per ounce for physical gold coins
        data = self.get_yahoo_finance_max_data('GC=F')
        if data is not None and len(data) > 1000:
            self.logger.info(f"Yahoo Spot Gold (GC=F per oz) success: {len(data)} days")
            return data
            
        # Fallback to GLD ETF if spot gold unavailable, convert to equivalent spot price
        data = self.get_yahoo_finance_max_data('GLD')
        if data is not None and len(data) > 1000:
            # Convert GLD to spot gold equivalent (current factor: 11.03x)
            conversion_factor = 11.03  # Based on spot gold $3388.50 / GLD $307.25
            for col in ['Open', 'High', 'Low', 'Close']:
                data[col] = data[col] * conversion_factor
            self.logger.info(f"Yahoo GLD (converted to spot gold equiv) success: {len(data)} days")
            return data
            
        # Try IAU as alternative
        data = self.get_yahoo_finance_max_data('IAU') 
        if data is not None and len(data) > 1000:
            # Convert IAU to per-ounce (IAU ≈ 1/100 oz)
            for col in ['Open', 'High', 'Low', 'Close']:
                data[col] = data[col] * 100
            self.logger.info(f"Yahoo IAU success: {len(data)} days")
            return data
            
        # Try FRED as last resort
        data = self.get_fred_gold_data()
        if data is not None and len(data) > 500:
            self.logger.info(f"FRED gold success: {len(data)} days")
            return data
            
        return None
    
    def get_comprehensive_silver_data(self):
        """
        Get silver data from multiple sources with fallback
        """
        # Try Yahoo Finance Silver Futures (SI=F) first - spot silver per ounce
        data = self.get_yahoo_finance_max_data('SI=F')
        if data is not None and len(data) > 1000:
            self.logger.info(f"Yahoo Spot Silver (SI=F per oz) success: {len(data)} days")
            return data
            
        # Fallback to SLV ETF if spot silver unavailable
        data = self.get_yahoo_finance_max_data('SLV')
        if data is not None and len(data) > 1000:
            self.logger.info(f"Yahoo SLV success: {len(data)} days")
            return data
            
        return None
    
    def clear_cache(self):
        """Clear all cached data to force fresh fetch"""
        self._cache.clear()
        self._cache_expiry.clear()
        self.logger.info("Cache cleared - next fetch will be fresh")
    
    def is_cache_valid(self, key):
        """Check if cached data is still valid"""
        if key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]
    
    def get_fresh_aligned_historical_data(self, force_fresh=False):
        """
        Get aligned BTC, ETH, and Gold data with fresh data priority
        """
        cache_key = "aligned_historical_data"
        
        # Check cache unless forcing fresh data
        if not force_fresh and self.is_cache_valid(cache_key):
            self.logger.info("Returning cached aligned historical data")
            return self._cache[cache_key]
        
        self.logger.info("Fetching fresh comprehensive historical data...")
        
        # Clear any stale yfinance sessions
        import yfinance as yf
        yf.shared._ERRORS = {}
        yf.shared._CACHE = {}
        
        # Get fresh data from all sources
        btc_data = self.get_comprehensive_crypto_data('BTC-USD')
        eth_data = self.get_comprehensive_crypto_data('ETH-USD')
        gold_data = self.get_comprehensive_gold_data()
        
        if btc_data is None or eth_data is None or gold_data is None:
            return None
            
        # Normalize all indexes to remove timezone issues
        if btc_data.index.tz is not None:
            btc_data.index = btc_data.index.tz_localize(None)
        if eth_data.index.tz is not None:
            eth_data.index = eth_data.index.tz_localize(None)
        if gold_data.index.tz is not None:
            gold_data.index = gold_data.index.tz_localize(None)
        
        # Find common date range
        start_date = max(btc_data.index.min(), eth_data.index.min(), gold_data.index.min())
        end_date = min(btc_data.index.max(), eth_data.index.max(), gold_data.index.max())
        
        self.logger.info(f"Common date range: {start_date} to {end_date}")
        
        # Filter to common range and align by business days
        btc_filtered = btc_data.loc[start_date:end_date]
        eth_filtered = eth_data.loc[start_date:end_date]
        gold_filtered = gold_data.loc[start_date:end_date]
        
        # Use gold's business days as reference (most restrictive)
        business_days = gold_filtered.index
        
        # Reindex crypto data to business days with forward fill
        btc_aligned = btc_filtered.reindex(business_days, method='ffill').dropna()
        eth_aligned = eth_filtered.reindex(business_days, method='ffill').dropna()
        
        # Find final common dates
        common_dates = btc_aligned.index.intersection(eth_aligned.index).intersection(business_days)
        
        if len(common_dates) < 100:
            self.logger.error(f"Insufficient aligned data: {len(common_dates)} days")
            return None
        
        result = {
            'btc_data': btc_aligned.loc[common_dates],
            'eth_data': eth_aligned.loc[common_dates], 
            'gold_data': gold_filtered.loc[common_dates],
            'common_dates': common_dates,
            'date_range': f"{common_dates.min().date()} to {common_dates.max().date()}",
            'total_days': len(common_dates)
        }
        
        # Cache the result
        self._cache[cache_key] = result
        self._cache_expiry[cache_key] = datetime.now() + timedelta(seconds=self.cache_duration)
        
        return result
        
    def get_aligned_historical_data(self):
        """
        Get aligned BTC, ETH, and Gold data for risk analysis
        """
        self.logger.info("Fetching comprehensive historical data...")
        
        # Get data from all sources
        btc_data = self.get_comprehensive_crypto_data('BTC-USD')
        eth_data = self.get_comprehensive_crypto_data('ETH-USD')
        gold_data = self.get_comprehensive_gold_data()
        
        if btc_data is None or eth_data is None or gold_data is None:
            return None
            
        # Normalize all indexes to remove timezone issues
        if btc_data.index.tz is not None:
            btc_data.index = btc_data.index.tz_localize(None)
        if eth_data.index.tz is not None:
            eth_data.index = eth_data.index.tz_localize(None)
        if gold_data.index.tz is not None:
            gold_data.index = gold_data.index.tz_localize(None)
        
        # Find common date range
        start_date = max(btc_data.index.min(), eth_data.index.min(), gold_data.index.min())
        end_date = min(btc_data.index.max(), eth_data.index.max(), gold_data.index.max())
        
        self.logger.info(f"Common date range: {start_date} to {end_date}")
        
        # Filter to common range and align by business days
        btc_filtered = btc_data.loc[start_date:end_date]
        eth_filtered = eth_data.loc[start_date:end_date]
        gold_filtered = gold_data.loc[start_date:end_date]
        
        # Use gold's business days as reference (most restrictive)
        business_days = gold_filtered.index
        
        # Reindex crypto data to business days with forward fill
        btc_aligned = btc_filtered.reindex(business_days, method='ffill').dropna()
        eth_aligned = eth_filtered.reindex(business_days, method='ffill').dropna()
        
        # Find final common dates
        common_dates = btc_aligned.index.intersection(eth_aligned.index).intersection(business_days)
        
        if len(common_dates) < 100:
            self.logger.error(f"Insufficient aligned data: {len(common_dates)} days")
            return None
            
        return {
            'btc_data': btc_aligned.loc[common_dates],
            'eth_data': eth_aligned.loc[common_dates], 
            'gold_data': gold_filtered.loc[common_dates],
            'common_dates': common_dates,
            'date_range': f"{common_dates.min().date()} to {common_dates.max().date()}",
            'total_days': len(common_dates)
        }
    
    def get_realtime_prices(self):
        """
        Get current real-time prices for display purposes only.
        Uses lightweight API calls - not for historical calculations.
        Returns dict with current prices or None on failure.
        """
        prices = {}
        
        try:
            btc = yf.Ticker("BTC-USD")
            btc_info = btc.fast_info
            prices['btc'] = btc_info.get('lastPrice') or btc_info.get('last_price')
            prices['btc_change'] = btc_info.get('regularMarketChangePercent', 0)
        except Exception as e:
            self.logger.warning(f"Failed to get BTC realtime price: {e}")
            prices['btc'] = None
            prices['btc_change'] = 0
        
        try:
            eth = yf.Ticker("ETH-USD")
            eth_info = eth.fast_info
            prices['eth'] = eth_info.get('lastPrice') or eth_info.get('last_price')
            prices['eth_change'] = eth_info.get('regularMarketChangePercent', 0)
        except Exception as e:
            self.logger.warning(f"Failed to get ETH realtime price: {e}")
            prices['eth'] = None
            prices['eth_change'] = 0
        
        try:
            gold = yf.Ticker("GC=F")
            gold_info = gold.fast_info
            prices['gold'] = gold_info.get('lastPrice') or gold_info.get('last_price')
            prices['gold_change'] = gold_info.get('regularMarketChangePercent', 0)
        except Exception as e:
            self.logger.warning(f"Failed to get Gold realtime price: {e}")
            prices['gold'] = None
            prices['gold_change'] = 0
        
        try:
            silver = yf.Ticker("SI=F")
            silver_info = silver.fast_info
            prices['silver'] = silver_info.get('lastPrice') or silver_info.get('last_price')
            prices['silver_change'] = silver_info.get('regularMarketChangePercent', 0)
        except Exception as e:
            self.logger.warning(f"Failed to get Silver realtime price: {e}")
            prices['silver'] = None
            prices['silver_change'] = 0
        
        prices['timestamp'] = datetime.now()
        return prices