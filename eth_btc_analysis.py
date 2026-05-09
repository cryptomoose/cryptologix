"""
ETH/BTC Ratio Analysis Module for CycleGeist
Analyzes the ETH/BTC ratio to determine optimal rotation timing between assets
"""

import pandas as pd
import numpy as np
from typing import Dict
from scipy.signal import find_peaks
from data_fetcher import CryptoDataFetcher
from technical_indicators import TechnicalIndicators

class EthBtcAnalyzer:
    def __init__(self):
        self.data_fetcher = CryptoDataFetcher()
        self.tech_indicators = TechnicalIndicators()
    
    def get_eth_btc_ratio_data(self):
        """
        Fetch ETH and BTC data over maximum timeframe and calculate ratio
        """
        try:
            # Fetch maximum data for both assets
            eth_data = self.data_fetcher.get_crypto_data('ETH-USD', 'max', '1d')
            btc_data = self.data_fetcher.get_crypto_data('BTC-USD', 'max', '1d')
            
            if eth_data.empty or btc_data.empty:
                return None
            
            # Align data by date (use inner join to get common dates)
            common_dates = eth_data.index.intersection(btc_data.index)
            eth_aligned = eth_data.loc[common_dates]
            btc_aligned = btc_data.loc[common_dates]
            
            # Calculate ETH/BTC ratio
            ratio_data = pd.DataFrame(index=common_dates)
            ratio_data['ETH_Price'] = eth_aligned['Close']
            ratio_data['BTC_Price'] = btc_aligned['Close']
            ratio_data['ETH_BTC_Ratio'] = eth_aligned['Close'] / btc_aligned['Close']
            
            # Add technical indicators to the ratio
            ratio_data = self.add_ratio_indicators(ratio_data)
            
            return ratio_data
            
        except Exception as e:
            print(f"Error fetching ETH/BTC ratio data: {e}")
            return None
    
    def add_ratio_indicators(self, df):
        """
        Add technical indicators specific to ETH/BTC ratio analysis
        """
        if df.empty:
            return df
        
        ratio = df['ETH_BTC_Ratio']
        
        # Moving averages for trend identification
        df['Ratio_SMA_20'] = ratio.rolling(window=20).mean()
        df['Ratio_SMA_50'] = ratio.rolling(window=50).mean()
        df['Ratio_SMA_200'] = ratio.rolling(window=200).mean()
        
        # RSI for ratio momentum
        df['Ratio_RSI'] = self.calculate_rsi(ratio, 14)
        
        # Bollinger Bands for ratio volatility
        bb_period = 20
        bb_std = 2
        sma = ratio.rolling(window=bb_period).mean()
        std = ratio.rolling(window=bb_period).std()
        df['Ratio_BB_Upper'] = sma + (bb_std * std)
        df['Ratio_BB_Lower'] = sma - (bb_std * std)
        
        # MACD for ratio momentum changes
        ema_12 = ratio.ewm(span=12).mean()
        ema_26 = ratio.ewm(span=26).mean()
        df['Ratio_MACD'] = ema_12 - ema_26
        df['Ratio_MACD_Signal'] = df['Ratio_MACD'].ewm(span=9).mean()
        df['Ratio_MACD_Histogram'] = df['Ratio_MACD'] - df['Ratio_MACD_Signal']
        
        # Historical percentiles for context
        df['Ratio_Percentile'] = ratio.rolling(window=252).rank(pct=True) * 100  # 1-year rolling percentile
        
        return df
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI for the ratio"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def identify_ratio_extremes(self, df):
        """
        Identify extreme ETH/BTC ratio levels that suggest rotation opportunities
        """
        if df.empty or 'ETH_BTC_Ratio' not in df.columns:
            return {
                'current_ratio': 0,
                'ratio_signal': 'NEUTRAL',
                'rotation_recommendation': 'HOLD',
                'confidence': 0,
                'reasoning': ['No ratio data available']
            }
        
        current_ratio = df['ETH_BTC_Ratio'].iloc[-1]
        current_percentile = df['Ratio_Percentile'].iloc[-1] if not df['Ratio_Percentile'].isna().all() else 50
        current_rsi = df['Ratio_RSI'].iloc[-1] if not df['Ratio_RSI'].isna().all() else 50
        
        # Historical extreme levels (approximate based on historical data)
        EXTREME_HIGH_PERCENTILE = 95  # Top 5% historically
        HIGH_PERCENTILE = 80         # Top 20% historically
        LOW_PERCENTILE = 20          # Bottom 20% historically
        EXTREME_LOW_PERCENTILE = 5   # Bottom 5% historically
        
        reasoning = []
        confidence = 0
        
        # Analyze current position
        if current_percentile >= EXTREME_HIGH_PERCENTILE:
            ratio_signal = 'EXTREME_HIGH'
            rotation_recommendation = 'ROTATE_TO_BTC'
            confidence = 80 + min(20, (current_percentile - EXTREME_HIGH_PERCENTILE) * 4)
            reasoning.append(f"ETH/BTC ratio at extreme high ({current_percentile:.1f}th percentile)")
        elif current_percentile >= HIGH_PERCENTILE:
            ratio_signal = 'HIGH'
            rotation_recommendation = 'CONSIDER_BTC'
            confidence = 60 + (current_percentile - HIGH_PERCENTILE) * 1.33
            reasoning.append(f"ETH/BTC ratio elevated ({current_percentile:.1f}th percentile)")
        elif current_percentile <= EXTREME_LOW_PERCENTILE:
            ratio_signal = 'EXTREME_LOW'
            rotation_recommendation = 'ROTATE_TO_ETH'
            confidence = 80 + min(20, (EXTREME_LOW_PERCENTILE - current_percentile) * 4)
            reasoning.append(f"ETH/BTC ratio at extreme low ({current_percentile:.1f}th percentile)")
        elif current_percentile <= LOW_PERCENTILE:
            ratio_signal = 'LOW'
            rotation_recommendation = 'CONSIDER_ETH'
            confidence = 60 + (LOW_PERCENTILE - current_percentile) * 1.33
            reasoning.append(f"ETH/BTC ratio depressed ({current_percentile:.1f}th percentile)")
        else:
            ratio_signal = 'NEUTRAL'
            rotation_recommendation = 'HOLD'
            confidence = 30
            reasoning.append(f"ETH/BTC ratio in neutral range ({current_percentile:.1f}th percentile)")
        
        # Add RSI confirmation
        if current_rsi >= 80:
            reasoning.append(f"Ratio RSI overbought ({current_rsi:.1f})")
            confidence += 10
        elif current_rsi <= 20:
            reasoning.append(f"Ratio RSI oversold ({current_rsi:.1f})")
            confidence += 10
        
        # Add trend confirmation
        if not df['Ratio_SMA_50'].isna().all() and not df['Ratio_SMA_200'].isna().all():
            sma_50 = df['Ratio_SMA_50'].iloc[-1]
            sma_200 = df['Ratio_SMA_200'].iloc[-1]
            
            if sma_50 > sma_200:
                reasoning.append("Short-term trend favors ETH")
            else:
                reasoning.append("Short-term trend favors BTC")
        
        confidence = min(100, max(0, confidence))
        
        return {
            'current_ratio': current_ratio,
            'ratio_signal': ratio_signal,
            'rotation_recommendation': rotation_recommendation,
            'confidence': int(confidence),
            'current_percentile': current_percentile,
            'current_rsi': current_rsi,
            'reasoning': reasoning,
            'historical_context': self.get_historical_context(df)
        }
    
    def get_historical_context(self, df):
        """
        Provide historical context for current ratio levels
        """
        if df.empty:
            return {}
        
        ratio = df['ETH_BTC_Ratio']
        current_ratio = ratio.iloc[-1]
        
        # Historical statistics
        all_time_high = ratio.max()
        all_time_low = ratio.min()
        mean_ratio = ratio.mean()
        
        # Recent performance
        ratio_1m = ratio.iloc[-30:].iloc[0] if len(ratio) >= 30 else ratio.iloc[0]
        ratio_3m = ratio.iloc[-90:].iloc[0] if len(ratio) >= 90 else ratio.iloc[0]
        ratio_1y = ratio.iloc[-365:].iloc[0] if len(ratio) >= 365 else ratio.iloc[0]
        
        return {
            'all_time_high': all_time_high,
            'all_time_low': all_time_low,
            'mean_ratio': mean_ratio,
            'distance_from_ath': ((all_time_high - current_ratio) / all_time_high) * 100,
            'distance_from_atl': ((current_ratio - all_time_low) / all_time_low) * 100,
            'performance_1m': ((current_ratio - ratio_1m) / ratio_1m) * 100,
            'performance_3m': ((current_ratio - ratio_3m) / ratio_3m) * 100,
            'performance_1y': ((current_ratio - ratio_1y) / ratio_1y) * 100
        }
    
    def generate_rotation_strategy(self, ratio_analysis, current_crypto):
        """
        Generate specific rotation strategy based on ratio analysis and current holding
        """
        rotation_rec = ratio_analysis['rotation_recommendation']
        confidence = ratio_analysis['confidence']
        current_ratio = ratio_analysis['current_ratio']
        
        if rotation_rec == 'ROTATE_TO_BTC':
            if current_crypto == 'Ethereum':
                strategy = f"STRONG ROTATE: Sell ETH, Buy BTC - Ratio at {current_ratio:.4f} suggests BTC outperformance ahead"
                position_action = "FULL ROTATION TO BTC"
            else:
                strategy = f"HOLD BTC: Ratio at {current_ratio:.4f} supports BTC over ETH"
                position_action = "MAINTAIN BTC POSITION"
        
        elif rotation_rec == 'ROTATE_TO_ETH':
            if current_crypto == 'Bitcoin':
                strategy = f"STRONG ROTATE: Sell BTC, Buy ETH - Ratio at {current_ratio:.4f} suggests ETH outperformance ahead"
                position_action = "FULL ROTATION TO ETH"
            else:
                strategy = f"HOLD ETH: Ratio at {current_ratio:.4f} supports ETH over BTC"
                position_action = "MAINTAIN ETH POSITION"
        
        elif rotation_rec == 'CONSIDER_BTC':
            if current_crypto == 'Ethereum':
                strategy = f"CONSIDER ROTATE: Partial rotation to BTC - Ratio at {current_ratio:.4f} slightly favors BTC"
                position_action = "PARTIAL ROTATION TO BTC (25-50%)"
            else:
                strategy = f"LEAN BTC: Current position aligned with ratio analysis"
                position_action = "MAINTAIN BTC POSITION"
        
        elif rotation_rec == 'CONSIDER_ETH':
            if current_crypto == 'Bitcoin':
                strategy = f"CONSIDER ROTATE: Partial rotation to ETH - Ratio at {current_ratio:.4f} slightly favors ETH"
                position_action = "PARTIAL ROTATION TO ETH (25-50%)"
            else:
                strategy = f"LEAN ETH: Current position aligned with ratio analysis"
                position_action = "MAINTAIN ETH POSITION"
        
        else:  # HOLD
            strategy = f"HOLD CURRENT: Ratio at {current_ratio:.4f} in neutral territory"
            position_action = "MAINTAIN CURRENT ALLOCATION"
        
        return {
            'strategy_summary': strategy,
            'position_action': position_action,
            'confidence': confidence
        }
    
    def analyze_eth_btc_ratio(self) -> Dict:
        """Main analysis method for ETH/BTC ratio"""
        try:
            ratio_data = self.get_eth_btc_ratio_data()
            if ratio_data is None or ratio_data.empty:
                return {'error': 'Unable to fetch ratio data'}
            
            current_ratio = ratio_data['ETH_BTC_Ratio'].iloc[-1]
            ratio_30d_change = ((current_ratio - ratio_data['ETH_BTC_Ratio'].iloc[-30]) / ratio_data['ETH_BTC_Ratio'].iloc[-30] * 100) if len(ratio_data) > 30 else 0
            
            # Calculate historical percentile
            historical_percentile = (ratio_data['ETH_BTC_Ratio'] < current_ratio).mean() * 100
            
            # Determine rotation signal
            rotation_signal = 'Hold'
            confidence = 50
            
            if historical_percentile > 80:
                rotation_signal = 'Rotate ETH to BTC'
                confidence = min(100, int(historical_percentile))
            elif historical_percentile < 20:
                rotation_signal = 'Rotate BTC to ETH'
                confidence = min(100, int(100 - historical_percentile))
            
            # Determine trend
            ratio_trend = 'Neutral'
            if ratio_30d_change > 5:
                ratio_trend = 'ETH Strengthening'
            elif ratio_30d_change < -5:
                ratio_trend = 'BTC Strengthening'
            
            # Generate insights
            insights = []
            insights.append(f"ETH/BTC ratio is at {historical_percentile:.0f}th percentile historically")
            
            if historical_percentile > 90:
                insights.append("ETH is at extremely high levels vs BTC - consider rotation")
            elif historical_percentile < 10:
                insights.append("ETH is at extremely low levels vs BTC - potential opportunity")
            
            if abs(ratio_30d_change) > 10:
                insights.append(f"Strong momentum: {ratio_30d_change:+.1f}% change in 30 days")
            
            return {
                'current_ratio': current_ratio,
                'ratio_change_30d': ratio_30d_change,
                'historical_percentile': historical_percentile,
                'rotation_signal': rotation_signal,
                'confidence': confidence,
                'ratio_trend': ratio_trend,
                'insights': insights,
                'data_points': len(ratio_data)
            }
            
        except Exception as e:
            return {'error': f'ETH/BTC analysis failed: {str(e)}'}