import pandas as pd
import numpy as np
from scipy import stats
from typing import List, Dict, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class PatternRecognizer:
    """Identify chart patterns and market structure for cryptocurrency analysis"""
    
    def __init__(self):
        self.min_pattern_length = 10  # Minimum periods for pattern recognition
        self.trend_strength_threshold = 0.7  # Correlation threshold for trend identification
    
    def identify_support_resistance(self, df: pd.DataFrame, window: int = 20, num_levels: int = 5) -> Dict:
        """
        Identify support and resistance levels
        
        Args:
            df (pd.DataFrame): Price data
            window (int): Window for local extrema detection
            num_levels (int): Number of levels to identify
        
        Returns:
            Dict: Support and resistance levels
        """
        highs = df['High'].rolling(window=window, center=True).max()
        lows = df['Low'].rolling(window=window, center=True).min()
        
        # Find local maxima (resistance) and minima (support)
        resistance_points = df[df['High'] == highs]['High'].dropna()
        support_points = df[df['Low'] == lows]['Low'].dropna()
        
        # Group similar levels
        resistance_levels = self._group_price_levels(resistance_points.values, num_levels)
        support_levels = self._group_price_levels(support_points.values, num_levels)
        
        return {
            'resistance': sorted(resistance_levels, reverse=True),
            'support': sorted(support_levels),
            'resistance_points': resistance_points.to_dict(),
            'support_points': support_points.to_dict()
        }
    
    def _group_price_levels(self, prices: np.array, num_levels: int, tolerance: float = 0.02) -> List[float]:
        """Group similar price levels together"""
        if len(prices) == 0:
            return []
        
        sorted_prices = np.sort(prices)
        levels = []
        current_group = [sorted_prices[0]]
        
        for price in sorted_prices[1:]:
            if len(current_group) > 0 and abs(price - np.mean(current_group)) / np.mean(current_group) <= tolerance:
                current_group.append(price)
            else:
                if len(current_group) >= 2:  # Only consider levels touched multiple times
                    levels.append(np.mean(current_group))
                current_group = [price]
        
        if len(current_group) >= 2:
            levels.append(np.mean(current_group))
        
        # Return top levels by frequency/strength
        return sorted(levels, key=lambda x: len([p for p in prices if abs(p - x) / x <= tolerance]), reverse=True)[:num_levels]
    
    def identify_trend_channels(self, df: pd.DataFrame, window: int = 50) -> Dict:
        """
        Identify trend channels using linear regression
        
        Args:
            df (pd.DataFrame): Price data
            window (int): Window for trend analysis
        
        Returns:
            Dict: Trend channel information
        """
        if len(df) < window:
            return {'trend': 'INSUFFICIENT_DATA', 'channels': []}
        
        channels = []
        
        # Analyze trends in rolling windows
        for i in range(window, len(df)):
            window_data = df.iloc[i-window:i]
            
            # Linear regression on closing prices
            x = np.arange(len(window_data))
            y = window_data['Close'].values
            
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            
            if abs(r_value) > self.trend_strength_threshold:
                trend_type = 'UPTREND' if slope > 0 else 'DOWNTREND'
                
                # Calculate channel boundaries
                residuals = y - (slope * x + intercept)
                upper_bound = np.max(residuals)
                lower_bound = np.min(residuals)
                
                channels.append({
                    'start_date': window_data.index[0],
                    'end_date': window_data.index[-1],
                    'trend': trend_type,
                    'slope': slope,
                    'r_squared': r_value**2,
                    'upper_channel': upper_bound,
                    'lower_channel': lower_bound,
                    'strength': abs(r_value)
                })
        
        # Get current trend
        current_trend = 'SIDEWAYS'
        if channels:
            latest_channel = max(channels, key=lambda x: x['end_date'])
            current_trend = latest_channel['trend']
        
        return {
            'current_trend': current_trend,
            'channels': channels
        }
    
    def identify_chart_patterns(self, df: pd.DataFrame) -> List[Dict]:
        """
        Identify classic chart patterns
        
        Args:
            df (pd.DataFrame): Price data
        
        Returns:
            List[Dict]: Identified patterns
        """
        patterns = []
        
        # Head and Shoulders
        patterns.extend(self._find_head_and_shoulders(df))
        
        # Double Top/Bottom
        patterns.extend(self._find_double_tops_bottoms(df))
        
        # Triangles
        patterns.extend(self._find_triangles(df))
        
        # Flags and Pennants
        patterns.extend(self._find_flags_pennants(df))
        
        return patterns
    
    def _find_head_and_shoulders(self, df: pd.DataFrame) -> List[Dict]:
        """Find Head and Shoulders patterns"""
        patterns = []
        
        if len(df) < 50:
            return patterns
        
        # Find significant peaks
        peaks = self._find_peaks(df['High'], min_distance=10, prominence=0.02)
        
        for i in range(len(peaks) - 2):
            peak1, peak2, peak3 = peaks[i], peaks[i+1], peaks[i+2]
            
            # Check if middle peak is highest (head)
            if (df['High'].iloc[peak2] > df['High'].iloc[peak1] and 
                df['High'].iloc[peak2] > df['High'].iloc[peak3]):
                
                # Find neckline (valleys between peaks)
                valley1 = df['Low'].iloc[peak1:peak2].idxmin()
                valley2 = df['Low'].iloc[peak2:peak3].idxmin()
                
                neckline_slope = (df['Low'].loc[valley2] - df['Low'].loc[valley1]) / (valley2 - valley1).days
                
                patterns.append({
                    'type': 'HEAD_AND_SHOULDERS',
                    'start_date': df.index[peak1],
                    'end_date': df.index[peak3],
                    'confidence': self._calculate_pattern_confidence(df, peak1, peak3),
                    'target': df['Low'].loc[valley1] - (df['High'].iloc[peak2] - df['Low'].loc[valley1]),
                    'neckline_slope': neckline_slope
                })
        
        return patterns
    
    def _find_double_tops_bottoms(self, df: pd.DataFrame) -> List[Dict]:
        """Find Double Top and Double Bottom patterns"""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        # Find peaks and troughs
        peaks = self._find_peaks(df['High'], min_distance=10, prominence=0.02)
        troughs = self._find_peaks(-df['Low'], min_distance=10, prominence=0.02)
        
        # Double tops
        for i in range(len(peaks) - 1):
            peak1, peak2 = peaks[i], peaks[i+1]
            price_diff = abs(df['High'].iloc[peak1] - df['High'].iloc[peak2]) / df['High'].iloc[peak1]
            
            if price_diff < 0.03:  # Peaks are similar (within 3%)
                valley = df['Low'].iloc[peak1:peak2].idxmin()
                
                patterns.append({
                    'type': 'DOUBLE_TOP',
                    'start_date': df.index[peak1],
                    'end_date': df.index[peak2],
                    'confidence': self._calculate_pattern_confidence(df, peak1, peak2),
                    'target': df['Low'].loc[valley] - (df['High'].iloc[peak1] - df['Low'].loc[valley])
                })
        
        # Double bottoms
        for i in range(len(troughs) - 1):
            trough1, trough2 = troughs[i], troughs[i+1]
            price_diff = abs(df['Low'].iloc[trough1] - df['Low'].iloc[trough2]) / df['Low'].iloc[trough1]
            
            if price_diff < 0.03:  # Troughs are similar (within 3%)
                peak = df['High'].iloc[trough1:trough2].idxmax()
                
                patterns.append({
                    'type': 'DOUBLE_BOTTOM',
                    'start_date': df.index[trough1],
                    'end_date': df.index[trough2],
                    'confidence': self._calculate_pattern_confidence(df, trough1, trough2),
                    'target': df['High'].loc[peak] + (df['High'].loc[peak] - df['Low'].iloc[trough1])
                })
        
        return patterns
    
    def _find_triangles(self, df: pd.DataFrame) -> List[Dict]:
        """Find Triangle patterns (Ascending, Descending, Symmetrical)"""
        patterns = []
        
        if len(df) < 40:
            return patterns
        
        window = 40
        for i in range(window, len(df)):
            window_data = df.iloc[i-window:i]
            
            # Find trend lines for highs and lows
            highs = window_data['High']
            lows = window_data['Low']
            
            # Calculate slopes
            x = np.arange(len(window_data))
            
            # High trend line
            high_peaks = self._find_peaks(highs.values, min_distance=5)
            if len(high_peaks) >= 2:
                high_slope, _, high_r, _, _ = stats.linregress(high_peaks, highs.iloc[high_peaks].values)
                
                # Low trend line
                low_troughs = self._find_peaks(-lows.values, min_distance=5)
                if len(low_troughs) >= 2:
                    low_slope, _, low_r, _, _ = stats.linregress(low_troughs, lows.iloc[low_troughs].values)
                    
                    # Classify triangle type
                    if abs(high_r) > 0.7 and abs(low_r) > 0.7:
                        if high_slope < -0.001 and low_slope > 0.001:
                            triangle_type = 'SYMMETRICAL_TRIANGLE'
                        elif abs(high_slope) < 0.001 and low_slope > 0.001:
                            triangle_type = 'ASCENDING_TRIANGLE'
                        elif high_slope < -0.001 and abs(low_slope) < 0.001:
                            triangle_type = 'DESCENDING_TRIANGLE'
                        else:
                            continue
                        
                        patterns.append({
                            'type': triangle_type,
                            'start_date': window_data.index[0],
                            'end_date': window_data.index[-1],
                            'confidence': min(abs(high_r), abs(low_r)),
                            'high_slope': high_slope,
                            'low_slope': low_slope
                        })
        
        return patterns
    
    def _find_flags_pennants(self, df: pd.DataFrame) -> List[Dict]:
        """Find Flag and Pennant patterns"""
        patterns = []
        
        if len(df) < 30:
            return patterns
        
        # Look for strong price movements followed by consolidation
        for i in range(20, len(df) - 10):
            # Check for strong move (flag pole)
            pole_start = i - 20
            pole_end = i
            pole_data = df.iloc[pole_start:pole_end]
            
            price_change = (pole_data['Close'].iloc[-1] - pole_data['Close'].iloc[0]) / pole_data['Close'].iloc[0]
            
            if abs(price_change) > 0.15:  # Strong move (>15%)
                # Check for consolidation (flag)
                flag_data = df.iloc[i:i+10] if i+10 < len(df) else df.iloc[i:]
                
                if len(flag_data) >= 5:
                    flag_volatility = flag_data['Close'].std() / flag_data['Close'].mean()
                    
                    if flag_volatility < 0.05:  # Low volatility consolidation
                        pattern_type = 'BULL_FLAG' if price_change > 0 else 'BEAR_FLAG'
                        
                        patterns.append({
                            'type': pattern_type,
                            'start_date': pole_data.index[0],
                            'end_date': flag_data.index[-1],
                            'confidence': 1 - flag_volatility,  # Lower volatility = higher confidence
                            'pole_strength': abs(price_change),
                            'target': pole_data['Close'].iloc[-1] + price_change * pole_data['Close'].iloc[-1]
                        })
        
        return patterns
    
    def _find_peaks(self, data: np.array, min_distance: int = 1, prominence: float = 0.01) -> List[int]:
        """Find peaks in price data"""
        peaks = []
        
        for i in range(min_distance, len(data) - min_distance):
            # Check if point is higher than neighbors
            is_peak = True
            for j in range(1, min_distance + 1):
                if data[i] <= data[i-j] or data[i] <= data[i+j]:
                    is_peak = False
                    break
            
            # Check prominence
            if is_peak:
                left_min = np.min(data[max(0, i-20):i])
                right_min = np.min(data[i:min(len(data), i+20)])
                base_level = max(left_min, right_min)
                
                if (data[i] - base_level) / data[i] >= prominence:
                    peaks.append(i)
        
        return peaks
    
    def _calculate_pattern_confidence(self, df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
        """Calculate confidence score for a pattern"""
        pattern_data = df.iloc[start_idx:end_idx+1]
        
        if len(pattern_data) == 0:
            return 0.0
        
        # Factor 1: Volume confirmation
        avg_volume = df['Volume'].rolling(window=50).mean().iloc[end_idx]
        pattern_volume = pattern_data['Volume'].mean()
        volume_score = min(1.0, pattern_volume / avg_volume) if avg_volume > 0 else 0.5
        
        # Factor 2: Pattern duration (longer patterns are more reliable)
        duration_days = (pattern_data.index[-1] - pattern_data.index[0]).days
        duration_score = min(1.0, duration_days / 30)  # Normalize to 30 days
        
        # Factor 3: Price range (larger patterns are more significant)
        price_range = (pattern_data['High'].max() - pattern_data['Low'].min()) / pattern_data['Close'].mean()
        range_score = min(1.0, price_range / 0.2)  # Normalize to 20% range
        
        # Combine scores
        confidence = (volume_score * 0.3 + duration_score * 0.4 + range_score * 0.3)
        return min(1.0, confidence)
    
    def identify_patterns(self, df: pd.DataFrame) -> Dict:
        """
        Main method to identify all patterns
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
        
        Returns:
            Dict: All identified patterns and levels
        """
        patterns = {
            'support_resistance': self.identify_support_resistance(df),
            'trend_channels': self.identify_trend_channels(df),
            'chart_patterns': self.identify_chart_patterns(df),
            'pattern_summary': {}
        }
        
        # Create pattern summary
        all_patterns = patterns['chart_patterns']
        pattern_counts = {}
        for pattern in all_patterns:
            pattern_type = pattern['type']
            if pattern_type not in pattern_counts:
                pattern_counts[pattern_type] = 0
            pattern_counts[pattern_type] += 1
        
        patterns['pattern_summary'] = {
            'total_patterns': len(all_patterns),
            'pattern_types': pattern_counts,
            'most_recent': all_patterns[-1] if all_patterns else None,
            'highest_confidence': max(all_patterns, key=lambda x: x['confidence']) if all_patterns else None
        }
        
        return patterns
    
    def calculate_accuracy(self, patterns: Dict, df: pd.DataFrame, lookback_days: int = 30) -> Dict:
        """
        Calculate historical accuracy of pattern predictions
        
        Args:
            patterns (Dict): Identified patterns
            df (pd.DataFrame): Price data
            lookback_days (int): Days to look back for validation
        
        Returns:
            Dict: Accuracy metrics for each pattern type
        """
        if not patterns.get('chart_patterns'):
            return {}
        
        accuracy_results = {}
        current_date = df.index[-1]
        cutoff_date = current_date - pd.Timedelta(days=lookback_days)
        
        # Group patterns by type
        pattern_groups = {}
        for pattern in patterns['chart_patterns']:
            if pattern['end_date'] < cutoff_date:  # Only consider completed patterns
                pattern_type = pattern['type']
                if pattern_type not in pattern_groups:
                    pattern_groups[pattern_type] = []
                pattern_groups[pattern_type].append(pattern)
        
        # Calculate accuracy for each pattern type
        for pattern_type, pattern_list in pattern_groups.items():
            correct_predictions = 0
            total_predictions = len(pattern_list)
            
            for pattern in pattern_list:
                # Check if pattern prediction was correct
                end_date = pattern['end_date']
                target_price = pattern.get('target')
                
                if target_price:
                    # Look at price movement after pattern completion
                    future_data = df[df.index > end_date].head(10)  # Next 10 periods
                    
                    if not future_data.empty:
                        actual_price = future_data['Close'].iloc[-1]
                        pattern_direction = 'UP' if target_price > df.loc[end_date, 'Close'] else 'DOWN'
                        actual_direction = 'UP' if actual_price > df.loc[end_date, 'Close'] else 'DOWN'
                        
                        if pattern_direction == actual_direction:
                            correct_predictions += 1
            
            if total_predictions > 0:
                accuracy_results[pattern_type] = (correct_predictions / total_predictions) * 100
        
        return accuracy_results
