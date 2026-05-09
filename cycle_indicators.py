import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class CycleIndicators:
    """
    Advanced cycle prediction indicators for identifying market tops and bottoms
    Based on historical patterns and proven technical analysis methods
    """
    
    def __init__(self):
        self.cycle_thresholds = {
            'extreme_rsi_bottom': 30,
            'extreme_rsi_top': 70,
            'parabolic_std_dev': 3,
            'rsi_divergence_threshold': 200,
            'volatility_compression_threshold': 0.5
        }
    
    def calculate_cycle_top_indicators(self, df: pd.DataFrame) -> Dict:
        """
        Calculate indicators that predict cycle tops (market peaks)
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
        
        Returns:
            Dict: Top prediction indicators and scores
        """
        if len(df) < 200:
            return {'error': 'Insufficient data for cycle top analysis'}
        
        indicators = {}
        
        # 1. RSI Divergence Detection
        rsi_divergence = self._detect_rsi_divergence(df)
        indicators['rsi_divergence'] = rsi_divergence
        
        # 2. Logarithmic Chart Extensions
        log_extension = self._calculate_log_extension(df)
        indicators['log_extension'] = log_extension
        
        # 3. Parabolic Rise Detection (3+ std dev above 200-week SMA)
        parabolic_rise = self._detect_parabolic_rise(df)
        indicators['parabolic_rise'] = parabolic_rise
        
        # 4. MACD Bearish Crossover
        macd_bearish = self._detect_macd_bearish_crossover(df)
        indicators['macd_bearish_crossover'] = macd_bearish
        
        # 5. Momentum Exhaustion Score
        momentum_exhaustion = self._calculate_momentum_exhaustion(df)
        indicators['momentum_exhaustion'] = momentum_exhaustion
        
        # 6. Volatility Spike Detection
        volatility_spike = self._detect_volatility_spike(df)
        indicators['volatility_spike'] = volatility_spike
        
        # Calculate overall top prediction score (0-100)
        top_score = self._calculate_top_prediction_score(indicators)
        indicators['top_prediction_score'] = top_score
        
        return indicators
    
    def calculate_cycle_bottom_indicators(self, df: pd.DataFrame) -> Dict:
        """
        Calculate indicators that predict cycle bottoms (market lows)
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
        
        Returns:
            Dict: Bottom prediction indicators and scores
        """
        if len(df) < 200:
            return {'error': 'Insufficient data for cycle bottom analysis'}
        
        indicators = {}
        
        # 1. 200-Week SMA Touch/Breach
        sma_200w_test = self._test_200_week_sma(df)
        indicators['sma_200w_test'] = sma_200w_test
        
        # 2. Pi Cycle Bottom Indicator
        pi_cycle_bottom = self._calculate_pi_cycle_bottom(df)
        indicators['pi_cycle_bottom'] = pi_cycle_bottom
        
        # 3. Extreme RSI (Weekly RSI < 30)
        extreme_rsi = self._detect_extreme_rsi_bottom(df)
        indicators['extreme_rsi'] = extreme_rsi
        
        # 4. Volatility Compression
        volatility_compression = self._detect_volatility_compression(df)
        indicators['volatility_compression'] = volatility_compression
        
        # 5. Capitulation Volume Analysis
        capitulation_volume = self._analyze_capitulation_volume(df)
        indicators['capitulation_volume'] = capitulation_volume
        
        # 6. Support Level Confluence
        support_confluence = self._calculate_support_confluence(df)
        indicators['support_confluence'] = support_confluence
        
        # Calculate overall bottom prediction score (0-100)
        bottom_score = self._calculate_bottom_prediction_score(indicators)
        indicators['bottom_prediction_score'] = bottom_score
        
        return indicators
    
    def _detect_rsi_divergence(self, df: pd.DataFrame, lookback: int = 100) -> Dict:
        """Detect RSI divergence patterns"""
        if 'RSI' not in df.columns or len(df) < lookback:
            return {'divergence_detected': False, 'strength': 0}
        
        recent_data = df.tail(lookback)
        
        # Find recent price highs and RSI highs
        price_highs = []
        rsi_highs = []
        
        for i in range(10, len(recent_data) - 10):
            # Check if this is a local high
            window = recent_data.iloc[i-10:i+10]
            if recent_data['High'].iloc[i] == window['High'].max():
                price_highs.append({'date': recent_data.index[i], 
                                   'price': recent_data['High'].iloc[i],
                                   'rsi': recent_data['RSI'].iloc[i]})
        
        # Look for divergence in last 2 highs
        if len(price_highs) >= 2:
            last_high = price_highs[-1]
            prev_high = price_highs[-2]
            
            price_higher = last_high['price'] > prev_high['price']
            rsi_lower = last_high['rsi'] < prev_high['rsi']
            
            if price_higher and rsi_lower:
                divergence_strength = abs(last_high['rsi'] - prev_high['rsi'])
                return {
                    'divergence_detected': True,
                    'strength': min(divergence_strength, 100),
                    'last_high_rsi': last_high['rsi'],
                    'prev_high_rsi': prev_high['rsi']
                }
        
        return {'divergence_detected': False, 'strength': 0}
    
    def _calculate_log_extension(self, df: pd.DataFrame) -> Dict:
        """Calculate how far price is extended on logarithmic scale"""
        if len(df) < 200:
            return {'extension_ratio': 0, 'risk_level': 'low'}
        
        # Calculate log prices and regression channel
        log_prices = np.log(df['Close'].values)
        x = np.arange(len(log_prices))
        
        # Linear regression on log scale
        slope, intercept = np.polyfit(x, log_prices, 1)
        regression_line = slope * x + intercept
        
        # Calculate standard deviation of residuals
        residuals = log_prices - regression_line
        std_dev = np.std(residuals)
        
        # Current extension from regression line
        current_extension = (log_prices[-1] - regression_line[-1]) / std_dev
        
        # Determine risk level
        if current_extension > 2.5:
            risk_level = 'extreme'
        elif current_extension > 2.0:
            risk_level = 'high'
        elif current_extension > 1.5:
            risk_level = 'moderate'
        else:
            risk_level = 'low'
        
        return {
            'extension_ratio': current_extension,
            'risk_level': risk_level,
            'std_deviations': current_extension
        }
    
    def _detect_parabolic_rise(self, df: pd.DataFrame, window: int = 200) -> Dict:
        """Detect parabolic price movements"""
        if len(df) < window:
            return {'parabolic_detected': False, 'acceleration': 0}
        
        recent_data = df.tail(window)
        
        # Calculate 200-period moving average (approximating 200-week SMA for daily data)
        sma_200 = recent_data['Close'].rolling(window=min(200, len(recent_data))).mean()
        
        if sma_200.empty:
            return {'parabolic_detected': False, 'acceleration': 0}
        
        # Calculate distance from SMA in standard deviations
        price_sma_diff = (recent_data['Close'] - sma_200) / sma_200
        std_dev = price_sma_diff.std()
        
        current_deviation = price_sma_diff.iloc[-1] / std_dev if std_dev > 0 else 0
        
        # Check for parabolic acceleration
        price_changes = recent_data['Close'].pct_change(20).tail(10)  # 20-period returns
        acceleration = price_changes.mean()
        
        parabolic_detected = (current_deviation > self.cycle_thresholds['parabolic_std_dev'] and 
                             acceleration > 0.1)  # 10% average 20-day returns
        
        return {
            'parabolic_detected': parabolic_detected,
            'acceleration': acceleration,
            'std_deviations_above_sma': current_deviation,
            'current_vs_sma': price_sma_diff.iloc[-1]
        }
    
    def _detect_macd_bearish_crossover(self, df: pd.DataFrame) -> Dict:
        """Detect MACD bearish crossover on longer timeframes"""
        if 'MACD' not in df.columns or 'MACD_Signal' not in df.columns:
            return {'crossover_detected': False, 'days_since': None}
        
        # Look for recent bearish crossover
        macd = df['MACD'].values
        signal = df['MACD_Signal'].values
        
        crossover_detected = False
        days_since = None
        
        # Check last 20 periods for crossover
        for i in range(len(macd) - 20, len(macd) - 1):
            if i > 0:
                # Bearish crossover: MACD crosses below signal
                if macd[i-1] > signal[i-1] and macd[i] < signal[i]:
                    crossover_detected = True
                    days_since = len(macd) - i - 1
                    break
        
        return {
            'crossover_detected': crossover_detected,
            'days_since': days_since,
            'current_macd': macd[-1],
            'current_signal': signal[-1],
            'momentum_strength': abs(macd[-1] - signal[-1]) if len(macd) > 0 else 0
        }
    
    def _calculate_momentum_exhaustion(self, df: pd.DataFrame) -> Dict:
        """Calculate momentum exhaustion indicators"""
        if len(df) < 50:
            return {'exhaustion_score': 0}
        
        # Multiple momentum indicators
        scores = []
        
        # 1. RSI momentum
        if 'RSI' in df.columns:
            rsi_current = df['RSI'].iloc[-1]
            rsi_score = max(0, rsi_current - 70) / 30 * 100  # Score 0-100 for RSI > 70
            scores.append(rsi_score)
        
        # 2. Price momentum vs moving average
        sma_20 = df['Close'].rolling(20).mean()
        if not sma_20.empty:
            price_vs_sma = ((df['Close'].iloc[-1] - sma_20.iloc[-1]) / sma_20.iloc[-1]) * 100
            momentum_score = min(100, max(0, price_vs_sma * 2))  # Scale to 0-100
            scores.append(momentum_score)
        
        # 3. Volume confirmation
        volume_sma = df['Volume'].rolling(20).mean()
        if not volume_sma.empty:
            volume_ratio = df['Volume'].iloc[-1] / volume_sma.iloc[-1]
            volume_score = min(100, volume_ratio * 50)  # High volume = higher exhaustion risk
            scores.append(volume_score)
        
        exhaustion_score = np.mean(scores) if scores else 0
        
        return {
            'exhaustion_score': exhaustion_score,
            'rsi_contribution': scores[0] if len(scores) > 0 else 0,
            'momentum_contribution': scores[1] if len(scores) > 1 else 0,
            'volume_contribution': scores[2] if len(scores) > 2 else 0
        }
    
    def _detect_volatility_spike(self, df: pd.DataFrame, window: int = 20) -> Dict:
        """Detect volatility spikes that often accompany tops"""
        if len(df) < window * 2:
            return {'spike_detected': False, 'current_volatility': 0}
        
        # Calculate rolling volatility
        returns = df['Close'].pct_change()
        volatility = returns.rolling(window).std() * np.sqrt(252)  # Annualized
        
        current_vol = volatility.iloc[-1]
        avg_vol = volatility.tail(100).mean()
        
        spike_detected = current_vol > avg_vol * 1.5  # 50% above average
        
        return {
            'spike_detected': spike_detected,
            'current_volatility': current_vol,
            'average_volatility': avg_vol,
            'volatility_ratio': current_vol / avg_vol if avg_vol > 0 else 0
        }
    
    def _test_200_week_sma(self, df: pd.DataFrame) -> Dict:
        """Test proximity to 200-week SMA (approximated with 200-day for daily data)"""
        if len(df) < 200:
            return {'near_sma': False, 'distance_percent': None}
        
        sma_200 = df['Close'].rolling(200).mean()
        current_price = df['Close'].iloc[-1]
        sma_current = sma_200.iloc[-1]
        
        distance_percent = ((current_price - sma_current) / sma_current) * 100
        near_sma = abs(distance_percent) < 10  # Within 10% of 200 SMA
        
        return {
            'near_sma': near_sma,
            'distance_percent': distance_percent,
            'current_price': current_price,
            'sma_200_level': sma_current,
            'below_sma': current_price < sma_current
        }
    
    def _calculate_pi_cycle_bottom(self, df: pd.DataFrame) -> Dict:
        """Pi Cycle Bottom Indicator: 471-day EMA vs 150x 14-day MA"""
        if len(df) < 471:
            return {'signal_active': False, 'cross_detected': False}
        
        # Calculate the Pi Cycle Bottom components
        ema_471 = df['Close'].ewm(span=471).mean()
        ma_14 = df['Close'].rolling(14).mean()
        scaled_ma_14 = ma_14 * 1.50  # 150% scaling factor
        
        current_ema = ema_471.iloc[-1]
        current_scaled_ma = scaled_ma_14.iloc[-1]
        
        # Check for crossover (scaled MA crossing above EMA from below)
        cross_detected = False
        if len(df) > 1:
            prev_ema = ema_471.iloc[-2]
            prev_scaled_ma = scaled_ma_14.iloc[-2]
            
            cross_detected = (prev_scaled_ma < prev_ema and current_scaled_ma >= current_ema)
        
        # Distance between lines
        distance = abs(current_scaled_ma - current_ema) / current_ema * 100
        
        return {
            'signal_active': distance < 5,  # Lines within 5% of each other
            'cross_detected': cross_detected,
            'ema_471': current_ema,
            'scaled_ma_14': current_scaled_ma,
            'distance_percent': distance
        }
    
    def _detect_extreme_rsi_bottom(self, df: pd.DataFrame) -> Dict:
        """Detect extreme RSI levels indicating capitulation"""
        if 'RSI' not in df.columns:
            return {'extreme_rsi': False, 'rsi_value': None}
        
        current_rsi = df['RSI'].iloc[-1]
        extreme_rsi = current_rsi < self.cycle_thresholds['extreme_rsi_bottom']
        
        # Additional context
        rsi_recent_low = df['RSI'].tail(50).min()
        
        return {
            'extreme_rsi': extreme_rsi,
            'rsi_value': current_rsi,
            'recent_low_rsi': rsi_recent_low,
            'capitulation_level': max(0, (30 - current_rsi) / 30 * 100)  # 0-100 score
        }
    
    def _detect_volatility_compression(self, df: pd.DataFrame, window: int = 50) -> Dict:
        """Detect volatility compression near potential bottoms"""
        if len(df) < window * 2:
            return {'compression_detected': False, 'volatility_ratio': 0}
        
        returns = df['Close'].pct_change()
        
        # Current volatility vs historical average
        current_vol = returns.tail(window).std()
        historical_vol = returns.tail(200).std()
        
        volatility_ratio = current_vol / historical_vol if historical_vol > 0 else 1
        compression_detected = volatility_ratio < self.cycle_thresholds['volatility_compression_threshold']
        
        return {
            'compression_detected': compression_detected,
            'volatility_ratio': volatility_ratio,
            'current_volatility': current_vol,
            'historical_volatility': historical_vol
        }
    
    def _analyze_capitulation_volume(self, df: pd.DataFrame) -> Dict:
        """Analyze volume patterns for capitulation signals"""
        if len(df) < 50:
            return {'capitulation_detected': False, 'volume_spike': False}
        
        volume_sma = df['Volume'].rolling(20).mean()
        current_volume = df['Volume'].iloc[-1]
        avg_volume = volume_sma.iloc[-1]
        
        # Look for volume spike with price decline
        price_decline = df['Close'].pct_change(5).iloc[-1] < -0.05  # 5% decline
        volume_spike = current_volume > avg_volume * 1.5  # 50% above average
        
        capitulation_detected = price_decline and volume_spike
        
        return {
            'capitulation_detected': capitulation_detected,
            'volume_spike': volume_spike,
            'price_decline': price_decline,
            'volume_ratio': current_volume / avg_volume if avg_volume > 0 else 0
        }
    
    def _calculate_support_confluence(self, df: pd.DataFrame) -> Dict:
        """Calculate confluence of support levels"""
        current_price = df['Close'].iloc[-1]
        support_levels = []
        
        # Previous significant lows
        lows = df['Low'].tail(200)
        for i in range(20, len(lows) - 20):
            if lows.iloc[i] == lows.iloc[i-20:i+20].min():
                support_levels.append(lows.iloc[i])
        
        # Moving averages as support
        if len(df) >= 50:
            support_levels.append(df['Close'].rolling(50).mean().iloc[-1])
        if len(df) >= 200:
            support_levels.append(df['Close'].rolling(200).mean().iloc[-1])
        
        # Find confluence near current price
        nearby_supports = [level for level in support_levels 
                          if abs(level - current_price) / current_price < 0.05]  # Within 5%
        
        return {
            'confluence_count': len(nearby_supports),
            'support_levels': nearby_supports,
            'strongest_support': min(nearby_supports) if nearby_supports else None,
            'confluence_strength': min(len(nearby_supports) * 25, 100)  # 0-100 score
        }
    
    def _calculate_top_prediction_score(self, indicators: Dict) -> float:
        """Calculate overall top prediction score (0-100)"""
        score = 0
        weights = {
            'rsi_divergence': 25,
            'log_extension': 20,
            'parabolic_rise': 20,
            'macd_bearish_crossover': 15,
            'momentum_exhaustion': 15,
            'volatility_spike': 5
        }
        
        # RSI divergence
        if indicators.get('rsi_divergence', {}).get('divergence_detected'):
            score += weights['rsi_divergence'] * (indicators['rsi_divergence']['strength'] / 100)
        
        # Log extension
        log_ext = indicators.get('log_extension', {})
        if log_ext.get('risk_level') == 'extreme':
            score += weights['log_extension']
        elif log_ext.get('risk_level') == 'high':
            score += weights['log_extension'] * 0.7
        elif log_ext.get('risk_level') == 'moderate':
            score += weights['log_extension'] * 0.4
        
        # Parabolic rise
        if indicators.get('parabolic_rise', {}).get('parabolic_detected'):
            score += weights['parabolic_rise']
        
        # MACD bearish crossover
        if indicators.get('macd_bearish_crossover', {}).get('crossover_detected'):
            days_since = indicators['macd_bearish_crossover'].get('days_since', 30)
            recency_factor = max(0, 1 - days_since / 30)  # Decay over 30 days
            score += weights['macd_bearish_crossover'] * recency_factor
        
        # Momentum exhaustion
        exhaustion_score = indicators.get('momentum_exhaustion', {}).get('exhaustion_score', 0)
        score += weights['momentum_exhaustion'] * (exhaustion_score / 100)
        
        # Volatility spike
        if indicators.get('volatility_spike', {}).get('spike_detected'):
            score += weights['volatility_spike']
        
        return min(score, 100)
    
    def _calculate_bottom_prediction_score(self, indicators: Dict) -> float:
        """Calculate overall bottom prediction score (0-100)"""
        score = 0
        weights = {
            'sma_200w_test': 25,
            'pi_cycle_bottom': 20,
            'extreme_rsi': 20,
            'volatility_compression': 15,
            'capitulation_volume': 15,
            'support_confluence': 5
        }
        
        # 200-week SMA test
        sma_test = indicators.get('sma_200w_test', {})
        if sma_test.get('near_sma') and sma_test.get('below_sma'):
            score += weights['sma_200w_test']
        elif sma_test.get('near_sma'):
            score += weights['sma_200w_test'] * 0.6
        
        # Pi cycle bottom
        pi_cycle = indicators.get('pi_cycle_bottom', {})
        if pi_cycle.get('cross_detected'):
            score += weights['pi_cycle_bottom']
        elif pi_cycle.get('signal_active'):
            score += weights['pi_cycle_bottom'] * 0.5
        
        # Extreme RSI
        extreme_rsi = indicators.get('extreme_rsi', {})
        if extreme_rsi.get('extreme_rsi'):
            capitulation_level = extreme_rsi.get('capitulation_level', 0)
            score += weights['extreme_rsi'] * (capitulation_level / 100)
        
        # Volatility compression
        if indicators.get('volatility_compression', {}).get('compression_detected'):
            score += weights['volatility_compression']
        
        # Capitulation volume
        if indicators.get('capitulation_volume', {}).get('capitulation_detected'):
            score += weights['capitulation_volume']
        
        # Support confluence
        confluence_strength = indicators.get('support_confluence', {}).get('confluence_strength', 0)
        score += weights['support_confluence'] * (confluence_strength / 100)
        
        return min(score, 100)