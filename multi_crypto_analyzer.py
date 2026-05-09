"""
Multi-cryptocurrency analyzer for CycleGeist
Handles analysis of multiple cryptocurrencies simultaneously
"""

import pandas as pd
import numpy as np
from datetime import datetime
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st

from data_fetcher import CryptoDataFetcher
from technical_indicators import TechnicalIndicators
from strategic_portfolio_advisor import StrategicPortfolioAdvisor
from crypto_config import TOP_CRYPTOCURRENCIES, get_cycle_thresholds, get_crypto_category

class MultiCryptoAnalyzer:
    def __init__(self):
        self.data_fetcher = CryptoDataFetcher()
        self.tech_indicators = TechnicalIndicators()
        self.strategic_advisor = StrategicPortfolioAdvisor()
        
    def analyze_single_crypto(self, crypto_name, symbol, progress_callback=None):
        """Analyze a single cryptocurrency and return cycle status"""
        try:
            if progress_callback:
                progress_callback(f"Analyzing {crypto_name}...")
            
            # Get data (shorter timeframe for faster processing)
            df = self.data_fetcher.get_crypto_data(symbol, "2y", "1d")
            if df.empty:
                return None
                
            # Add technical indicators
            df = self.tech_indicators.add_all_indicators(df, 14, 20, 50, 20, 2.0)
            
            # Get current metrics
            current_price = df['Close'].iloc[-1]
            ma_200 = df['MA_200'].iloc[-1] if 'MA_200' in df.columns else None
            rsi = df['RSI'].iloc[-1] if 'RSI' in df.columns else None
            
            # Calculate distance from 200MA
            ma_distance = ((current_price - ma_200) / ma_200 * 100) if ma_200 else 0
            
            # Get thresholds for this crypto type
            thresholds = get_cycle_thresholds(crypto_name)
            
            # Determine cycle status
            cycle_status = self._determine_cycle_status(ma_distance, rsi, thresholds)
            
            # Calculate additional metrics
            volume_avg = df['Volume'].rolling(20).mean().iloc[-1]
            current_volume = df['Volume'].iloc[-1]
            volume_ratio = current_volume / volume_avg if volume_avg > 0 else 1
            
            # Price change metrics
            price_1d = df['Close'].iloc[-2] if len(df) > 1 else current_price
            price_7d = df['Close'].iloc[-7] if len(df) > 7 else current_price
            price_30d = df['Close'].iloc[-30] if len(df) > 30 else current_price
            
            return {
                'name': crypto_name,
                'symbol': symbol,
                'current_price': current_price,
                'cycle_status': cycle_status,
                'ma_distance': ma_distance,
                'rsi': rsi,
                'volume_ratio': volume_ratio,
                'price_change_1d': ((current_price - price_1d) / price_1d * 100),
                'price_change_7d': ((current_price - price_7d) / price_7d * 100),
                'price_change_30d': ((current_price - price_30d) / price_30d * 100),
                'category': get_crypto_category(crypto_name),
                'last_updated': datetime.now()
            }
            
        except Exception as e:
            st.warning(f"Error analyzing {crypto_name}: {str(e)}")
            return None
    
    def _determine_cycle_status(self, ma_distance, rsi, thresholds):
        """Determine cycle status based on metrics and thresholds"""
        if ma_distance >= thresholds['extreme_bubble'] and rsi > 80:
            return "🔴 EXTREME BUBBLE"
        elif ma_distance >= thresholds['bubble_forming'] and rsi > 70:
            return "🟠 BUBBLE FORMING"
        elif ma_distance >= thresholds['bull_market']:
            return "🟢 BULL MARKET"
        elif ma_distance >= thresholds['accumulation']:
            return "🟡 ACCUMULATION"
        elif ma_distance >= thresholds['bear_market']:
            return "🔵 BEAR MARKET"
        elif ma_distance <= thresholds['extreme_bear']:
            return "🟣 EXTREME BEAR"
        else:
            return "⚪ NEUTRAL"
    
    def analyze_all_cryptos(self, max_workers=10):
        """Analyze all cryptocurrencies in parallel"""
        results = []
        
        # Create progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        def update_progress(current, total, message=""):
            progress = current / total
            progress_bar.progress(progress)
            status_text.text(f"Progress: {current}/{total} - {message}")
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_crypto = {
                executor.submit(self.analyze_single_crypto, name, symbol): name 
                for name, symbol in TOP_CRYPTOCURRENCIES.items()
            }
            
            completed = 0
            total = len(future_to_crypto)
            
            # Process completed tasks
            for future in as_completed(future_to_crypto):
                crypto_name = future_to_crypto[future]
                try:
                    result = future.result(timeout=30)  # 30 second timeout
                    if result:
                        results.append(result)
                    completed += 1
                    update_progress(completed, total, f"Completed {crypto_name}")
                except Exception as e:
                    st.warning(f"Failed to analyze {crypto_name}: {str(e)}")
                    completed += 1
                    update_progress(completed, total, f"Failed {crypto_name}")
        
        # Clean up progress indicators
        progress_bar.empty()
        status_text.empty()
        
        return results
    
    def create_summary_dataframe(self, results):
        """Create a summary DataFrame from analysis results"""
        if not results:
            return pd.DataFrame()
            
        df = pd.DataFrame(results)
        
        # Sort by cycle status priority and market cap (implied by order)
        cycle_order = [
            "🔴 EXTREME BUBBLE",
            "🟠 BUBBLE FORMING", 
            "🟢 BULL MARKET",
            "🟡 ACCUMULATION",
            "⚪ NEUTRAL",
            "🔵 BEAR MARKET",
            "🟣 EXTREME BEAR"
        ]
        
        df['cycle_priority'] = df['cycle_status'].apply(
            lambda x: cycle_order.index(x) if x in cycle_order else 999
        )
        
        df = df.sort_values(['cycle_priority', 'name'])
        df = df.drop('cycle_priority', axis=1)
        
        return df
    
    def get_cycle_summary_stats(self, results):
        """Get summary statistics of cycle statuses"""
        if not results:
            return {}
            
        df = pd.DataFrame(results)
        cycle_counts = df['cycle_status'].value_counts()
        
        total = len(results)
        summary = {
            'total_analyzed': total,
            'extreme_opportunities': cycle_counts.get('🔴 EXTREME BUBBLE', 0) + cycle_counts.get('🟣 EXTREME BEAR', 0),
            'bull_markets': cycle_counts.get('🟢 BULL MARKET', 0),
            'bear_markets': cycle_counts.get('🔵 BEAR MARKET', 0),
            'accumulation_phase': cycle_counts.get('🟡 ACCUMULATION', 0),
            'bubble_forming': cycle_counts.get('🟠 BUBBLE FORMING', 0),
            'cycle_distribution': cycle_counts.to_dict()
        }
        
        return summary