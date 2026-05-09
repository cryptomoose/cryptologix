import pandas as pd
import numpy as np
from typing import Tuple, Optional

class TechnicalIndicators:
    """Calculate various technical indicators for cryptocurrency analysis"""
    
    def __init__(self):
        pass
    
    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            prices (pd.Series): Price series (typically closing prices)
            period (int): RSI period
        
        Returns:
            pd.Series: RSI values
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            prices (pd.Series): Price series
            fast (int): Fast EMA period
            slow (int): Slow EMA period
            signal (int): Signal line EMA period
        
        Returns:
            Tuple[pd.Series, pd.Series, pd.Series]: MACD line, Signal line, Histogram
        """
        exp_fast = prices.ewm(span=fast).mean()
        exp_slow = prices.ewm(span=slow).mean()
        macd = exp_fast - exp_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
    
    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands
        
        Args:
            prices (pd.Series): Price series
            period (int): Moving average period
            std_dev (float): Standard deviation multiplier
        
        Returns:
            Tuple[pd.Series, pd.Series, pd.Series]: Upper band, Lower band, Middle band (SMA)
        """
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        bb_upper = sma + (std * std_dev)
        bb_lower = sma - (std * std_dev)
        return bb_upper, bb_lower, sma
    
    def calculate_moving_averages(self, prices: pd.Series, short_period: int = 20, long_period: int = 50) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Simple Moving Averages
        
        Args:
            prices (pd.Series): Price series
            short_period (int): Short MA period
            long_period (int): Long MA period
        
        Returns:
            Tuple[pd.Series, pd.Series]: Short MA, Long MA
        """
        short_ma = prices.rolling(window=short_period).mean()
        long_ma = prices.rolling(window=long_period).mean()
        return short_ma, long_ma
    
    def calculate_long_term_cycle_indicators(self, prices: pd.Series, high: pd.Series = None, low: pd.Series = None) -> dict:
        """
        Calculate long-term cycle indicators optimized for multi-year analysis
        
        Args:
            prices (pd.Series): Price series (daily)
            high (pd.Series): High prices (optional)
            low (pd.Series): Low prices (optional)
        
        Returns:
            dict: Long-term cycle indicators
        """
        results = {}
        
        # Long-term RSI (29 periods - better for cycles)
        results['rsi_long'] = self.calculate_rsi(prices, period=29)
        
        # Cycle-optimized MACD (21/50/9 - better for long-term trends)
        macd, signal, hist = self.calculate_macd(prices, fast=21, slow=50, signal=9)
        results['macd_cycle'] = macd
        results['macd_signal_cycle'] = signal
        results['macd_hist_cycle'] = hist
        
        # Super long-term MAs (for cycle analysis)
        results['ma_100'] = prices.rolling(window=100).mean()
        results['ma_300'] = prices.rolling(window=300).mean()
        results['ma_600'] = prices.rolling(window=600).mean()  # ~2 year cycle
        
        # Logarithmic regression for long-term trend
        if len(prices) > 365:
            results['log_regression'] = self.calculate_log_regression_trend(prices)
        
        # Pi Cycle Bottom (experimental - needs weekly data conversion)
        if len(prices) > 1000:
            results['pi_cycle_bottom'] = self.calculate_pi_cycle_bottom(prices)
        
        return results
    
    def calculate_log_regression_trend(self, prices: pd.Series) -> pd.Series:
        """
        Calculate logarithmic regression trend line for long-term analysis
        
        Args:
            prices (pd.Series): Price series
            
        Returns:
            pd.Series: Log regression trend values
        """
        try:
            # Convert to log prices
            log_prices = np.log(prices.dropna())
            
            # Create time index
            x = np.arange(len(log_prices))
            
            # Calculate regression coefficients
            coeffs = np.polyfit(x, log_prices, 1)
            
            # Generate trend line
            trend_log = coeffs[0] * np.arange(len(prices)) + coeffs[1]
            trend_prices = np.exp(trend_log)
            
            return pd.Series(trend_prices, index=prices.index)
            
        except Exception:
            # Fallback to simple moving average
            return prices.rolling(window=200).mean()
    
    def calculate_pi_cycle_bottom(self, prices: pd.Series) -> dict:
        """
        Calculate Pi Cycle Bottom indicator for extreme low detection
        
        Args:
            prices (pd.Series): Daily price series
            
        Returns:
            dict: Pi cycle signals and levels
        """
        try:
            # Convert daily to weekly approximation (every 7th day)
            weekly_prices = prices.iloc[::7]
            
            if len(weekly_prices) < 200:
                return {'signal': False, 'level': None}
            
            # 200-week MA approximation
            ma_200w = weekly_prices.rolling(window=200).mean()
            
            # Current vs 200-week MA
            current_price = prices.iloc[-1]
            ma_200w_current = ma_200w.iloc[-1] if not ma_200w.empty else current_price
            
            # Pi Cycle Bottom signal (when price crosses above 200W MA)
            signal = current_price > ma_200w_current * 1.1  # 10% above for confirmation
            
            return {
                'signal': signal,
                'ma_200w_level': ma_200w_current,
                'distance_from_ma': ((current_price - ma_200w_current) / ma_200w_current * 100) if ma_200w_current else 0
            }
            
        except Exception:
            return {'signal': False, 'level': None}
    
    def calculate_future_projections(self, prices: pd.Series, days_ahead: int = 90) -> dict:
        """
        Calculate future price projections based on current trends
        
        Args:
            prices (pd.Series): Historical prices
            days_ahead (int): Number of days to project ahead
            
        Returns:
            dict: Projection levels and timeframes
        """
        try:
            if len(prices) < 100:
                return {'projections': None}
            
            # Recent trend analysis (last 90 days)
            recent_prices = prices.tail(90)
            
            # Calculate trend slope
            x = np.arange(len(recent_prices))
            log_prices = np.log(recent_prices)
            coeffs = np.polyfit(x, log_prices, 1)
            
            # Project forward
            future_x = np.arange(len(recent_prices), len(recent_prices) + days_ahead)
            future_log_prices = coeffs[0] * future_x + coeffs[1]
            future_prices = np.exp(future_log_prices)
            
            # Calculate volatility-adjusted ranges
            recent_volatility = recent_prices.pct_change().std()
            
            projections = {
                'trend_projection': future_prices[-1],
                'optimistic_target': future_prices[-1] * (1 + recent_volatility * 2),
                'pessimistic_target': future_prices[-1] * (1 - recent_volatility * 2),
                'days_ahead': days_ahead,
                'confidence': min(0.9, 1 - (recent_volatility * 2))  # Lower confidence for high volatility
            }
            
            return projections
            
        except Exception:
            return {'projections': None}
    
    def calculate_ema(self, prices: pd.Series, period: int = 20) -> pd.Series:
        """
        Calculate Exponential Moving Average
        
        Args:
            prices (pd.Series): Price series
            period (int): EMA period
        
        Returns:
            pd.Series: EMA values
        """
        return prices.ewm(span=period).mean()
    
    def calculate_stochastic(self, high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic Oscillator
        
        Args:
            high (pd.Series): High prices
            low (pd.Series): Low prices
            close (pd.Series): Close prices
            k_period (int): %K period
            d_period (int): %D period
        
        Returns:
            Tuple[pd.Series, pd.Series]: %K, %D
        """
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d_percent = k_percent.rolling(window=d_period).mean()
        return k_percent, d_percent
    
    def calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range (ATR)
        
        Args:
            high (pd.Series): High prices
            low (pd.Series): Low prices
            close (pd.Series): Close prices
            period (int): ATR period
        
        Returns:
            pd.Series: ATR values
        """
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr
    
    def calculate_volume_indicators(self, close: pd.Series, volume: pd.Series) -> dict:
        """
        Calculate volume-based indicators
        
        Args:
            close (pd.Series): Close prices
            volume (pd.Series): Volume data
        
        Returns:
            dict: Volume indicators
        """
        # Volume Moving Average
        volume_ma = volume.rolling(window=20).mean()
        
        # Volume Rate of Change
        volume_roc = volume.pct_change(periods=1) * 100
        
        # On-Balance Volume (OBV)
        obv = (volume * np.where(close.diff() > 0, 1, np.where(close.diff() < 0, -1, 0))).cumsum()
        
        # Volume Price Trend (VPT)
        vpt = (volume * (close.pct_change())).cumsum()
        
        return {
            'Volume_MA': volume_ma,
            'Volume_ROC': volume_roc,
            'OBV': obv,
            'VPT': vpt
        }
    
    def calculate_momentum_indicators(self, close: pd.Series, high: pd.Series, low: pd.Series) -> dict:
        """
        Calculate momentum indicators
        
        Args:
            close (pd.Series): Close prices
            high (pd.Series): High prices
            low (pd.Series): Low prices
        
        Returns:
            dict: Momentum indicators
        """
        # Rate of Change
        roc = close.pct_change(periods=10) * 100
        
        # Commodity Channel Index (CCI)
        typical_price = (high + low + close) / 3
        sma_tp = typical_price.rolling(window=20).mean()
        mad = typical_price.rolling(window=20).apply(lambda x: np.mean(np.abs(x - np.mean(x))))
        cci = (typical_price - sma_tp) / (0.015 * mad)
        
        # Williams %R
        highest_high = high.rolling(window=14).max()
        lowest_low = low.rolling(window=14).min()
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
        
        return {
            'ROC': roc,
            'CCI': cci,
            'Williams_R': williams_r
        }
    
    def add_all_indicators(self, df: pd.DataFrame, rsi_period: int = 14, ma_short: int = 20, 
                          ma_long: int = 50, bb_period: int = 20, bb_std: float = 2) -> pd.DataFrame:
        """
        Add all technical indicators to the dataframe
        
        Args:
            df (pd.DataFrame): Price data with OHLCV columns
            rsi_period (int): RSI period
            ma_short (int): Short moving average period
            ma_long (int): Long moving average period
            bb_period (int): Bollinger Bands period
            bb_std (float): Bollinger Bands standard deviation
        
        Returns:
            pd.DataFrame: DataFrame with all indicators added
        """
        df = df.copy()
        
        # Basic indicators
        df['RSI'] = self.calculate_rsi(df['Close'], rsi_period)
        
        # MACD
        macd, macd_signal, macd_hist = self.calculate_macd(df['Close'])
        df['MACD'] = macd
        df['MACD_Signal'] = macd_signal
        df['MACD_Hist'] = macd_hist
        
        # Bollinger Bands
        bb_upper, bb_lower, bb_middle = self.calculate_bollinger_bands(df['Close'], bb_period, bb_std)
        df['BB_Upper'] = bb_upper
        df['BB_Lower'] = bb_lower
        df['BB_Middle'] = bb_middle
        
        # Moving Averages - Standardized naming
        ma_short_vals, ma_long_vals = self.calculate_moving_averages(df['Close'], ma_short, ma_long)
        df[f'MA_{ma_short}'] = ma_short_vals  # MA_20
        df[f'MA_{ma_long}'] = ma_long_vals    # MA_50
        df['MA_Short'] = ma_short_vals
        df['MA_Long'] = ma_long_vals
        
        # EMA
        df['EMA_20'] = self.calculate_ema(df['Close'], 20)
        df['EMA_50'] = self.calculate_ema(df['Close'], 50)
        
        # Stochastic
        stoch_k, stoch_d = self.calculate_stochastic(df['High'], df['Low'], df['Close'])
        df['Stoch_K'] = stoch_k
        df['Stoch_D'] = stoch_d
        
        # ATR
        df['ATR'] = self.calculate_atr(df['High'], df['Low'], df['Close'])
        
        # Volume indicators
        volume_indicators = self.calculate_volume_indicators(df['Close'], df['Volume'])
        for key, value in volume_indicators.items():
            df[key] = value
        
        # Momentum indicators
        momentum_indicators = self.calculate_momentum_indicators(df['Close'], df['High'], df['Low'])
        for key, value in momentum_indicators.items():
            df[key] = value
        
        # Price action indicators
        df['Price_Change'] = df['Close'].pct_change() * 100
        df['High_Low_Pct'] = ((df['High'] - df['Low']) / df['Close']) * 100
        df['Close_Position'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
        
        return df
    
    def get_signal_strength(self, df: pd.DataFrame, index: int = -1) -> dict:
        """
        Calculate signal strength based on multiple indicators
        
        Args:
            df (pd.DataFrame): DataFrame with technical indicators
            index (int): Index position to analyze (-1 for latest)
        
        Returns:
            dict: Signal strength analysis
        """
        if len(df) == 0 or abs(index) > len(df):
            return {'overall': 'NEUTRAL', 'strength': 0, 'signals': []}
        
        signals = []
        bullish_count = 0
        bearish_count = 0
        
        row = df.iloc[index]
        
        # RSI signals
        if 'RSI' in df.columns:
            if row['RSI'] < 30:
                signals.append(('RSI', 'BULLISH', 'Oversold condition'))
                bullish_count += 2
            elif row['RSI'] > 70:
                signals.append(('RSI', 'BEARISH', 'Overbought condition'))
                bearish_count += 2
            elif 40 <= row['RSI'] <= 60:
                signals.append(('RSI', 'NEUTRAL', 'Neutral zone'))
        
        # MACD signals
        if all(col in df.columns for col in ['MACD', 'MACD_Signal', 'MACD_Hist']):
            if row['MACD'] > row['MACD_Signal'] and row['MACD_Hist'] > 0:
                signals.append(('MACD', 'BULLISH', 'MACD above signal line'))
                bullish_count += 1
            elif row['MACD'] < row['MACD_Signal'] and row['MACD_Hist'] < 0:
                signals.append(('MACD', 'BEARISH', 'MACD below signal line'))
                bearish_count += 1
        
        # Bollinger Bands signals
        if all(col in df.columns for col in ['Close', 'BB_Upper', 'BB_Lower']):
            if row['Close'] < row['BB_Lower']:
                signals.append(('BB', 'BULLISH', 'Price below lower Bollinger Band'))
                bullish_count += 1
            elif row['Close'] > row['BB_Upper']:
                signals.append(('BB', 'BEARISH', 'Price above upper Bollinger Band'))
                bearish_count += 1
        
        # Moving Average signals
        if all(col in df.columns for col in ['MA_Short', 'MA_Long']):
            if row['MA_Short'] > row['MA_Long']:
                signals.append(('MA', 'BULLISH', 'Short MA above long MA'))
                bullish_count += 1
            else:
                signals.append(('MA', 'BEARISH', 'Short MA below long MA'))
                bearish_count += 1
        
        # Stochastic signals
        if all(col in df.columns for col in ['Stoch_K', 'Stoch_D']):
            if row['Stoch_K'] < 20 and row['Stoch_D'] < 20:
                signals.append(('STOCH', 'BULLISH', 'Stochastic oversold'))
                bullish_count += 1
            elif row['Stoch_K'] > 80 and row['Stoch_D'] > 80:
                signals.append(('STOCH', 'BEARISH', 'Stochastic overbought'))
                bearish_count += 1
        
        # Determine overall signal
        total_signals = bullish_count + bearish_count
        if total_signals == 0:
            overall_signal = 'NEUTRAL'
            strength = 0
        else:
            if bullish_count > bearish_count:
                overall_signal = 'BULLISH'
                strength = min(10, int((bullish_count / total_signals) * 10))
            elif bearish_count > bullish_count:
                overall_signal = 'BEARISH'
                strength = min(10, int((bearish_count / total_signals) * 10))
            else:
                overall_signal = 'NEUTRAL'
                strength = 5
        
        return {
            'overall': overall_signal,
            'strength': strength,
            'signals': signals,
            'bullish_count': bullish_count,
            'bearish_count': bearish_count
        }