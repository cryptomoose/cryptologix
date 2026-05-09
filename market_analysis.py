import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class MarketAnalyzer:
    """Analyze market cycles and generate predictions for cryptocurrency markets"""
    
    def __init__(self):
        self.bull_threshold = 1.5  # 150% gain threshold for bull market
        self.bear_threshold = -0.5  # 50% loss threshold for bear market
        self.min_cycle_duration = 30  # Minimum cycle duration in days
        self.cycle_confirmation_period = 14  # Days to confirm cycle change
    
    def identify_market_cycles(self, df: pd.DataFrame, patterns: Dict) -> List[Dict]:
        """
        Identify bull and bear market cycles
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
            patterns (Dict): Pattern analysis results
        
        Returns:
            List[Dict]: Market cycles with start/end dates and characteristics
        """
        if len(df) < 60:  # Need at least 2 months of data
            return []
        
        cycles = []
        
        # Calculate rolling maximum and minimum for cycle detection
        df['Rolling_Max'] = df['Close'].rolling(window=50, min_periods=1).max()
        df['Rolling_Min'] = df['Close'].rolling(window=50, min_periods=1).min()
        
        # Calculate drawdown from rolling maximum
        df['Drawdown'] = (df['Close'] - df['Rolling_Max']) / df['Rolling_Max']
        
        # Calculate advance from rolling minimum
        df['Advance'] = (df['Close'] - df['Rolling_Min']) / df['Rolling_Min']
        
        # Identify cycle turning points
        cycle_points = self._identify_cycle_turning_points(df)
        
        # Convert turning points to cycles
        for i in range(len(cycle_points) - 1):
            start_point = cycle_points[i]
            end_point = cycle_points[i + 1]
            
            start_date = start_point['date']
            end_date = end_point['date']
            start_price = start_point['price']
            end_price = end_point['price']
            
            # Calculate cycle characteristics
            duration = (end_date - start_date).days
            price_change = (end_price - start_price) / start_price
            
            # Determine cycle type
            if price_change > 0.20:  # 20% gain
                cycle_type = 'Bull Market'
            elif price_change < -0.20:  # 20% loss
                cycle_type = 'Bear Market'
            else:
                cycle_type = 'Sideways Market'
            
            # Calculate additional metrics
            cycle_data = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if not cycle_data.empty:
                max_price = cycle_data['High'].max()
                min_price = cycle_data['Low'].min()
                avg_volume = cycle_data['Volume'].mean()
                volatility = cycle_data['Close'].pct_change().std() * np.sqrt(252)
                
                cycles.append({
                    'type': cycle_type,
                    'start_date': start_date,
                    'end_date': end_date,
                    'duration_days': duration,
                    'start_price': start_price,
                    'end_price': end_price,
                    'price_change_pct': price_change * 100,
                    'max_price': max_price,
                    'min_price': min_price,
                    'max_gain': ((max_price - start_price) / start_price) * 100,
                    'max_loss': ((min_price - start_price) / start_price) * 100,
                    'avg_volume': avg_volume,
                    'volatility': volatility * 100,
                    'strength': self._calculate_cycle_strength(cycle_data, cycle_type)
                })
        
        return cycles
    
    def _identify_cycle_turning_points(self, df: pd.DataFrame) -> List[Dict]:
        """Identify major turning points in the market"""
        turning_points = []
        
        # Use a combination of price action and technical indicators
        df['MA_20'] = df['Close'].rolling(window=20).mean()
        df['MA_50'] = df['Close'].rolling(window=50).mean()
        
        # Look for significant trend changes
        for i in range(50, len(df) - 20):  # Leave buffer at start and end
            current_date = df.index[i]
            current_price = df['Close'].iloc[i]
            
            # Look back and forward for trend confirmation
            lookback_period = 30
            lookahead_period = 20
            
            start_idx = max(0, i - lookback_period)
            end_idx = min(len(df), i + lookahead_period)
            
            past_data = df.iloc[start_idx:i]
            future_data = df.iloc[i:end_idx]
            
            if len(past_data) >= 20 and len(future_data) >= 10:
                # Calculate trend before and after
                past_trend = self._calculate_trend_slope(past_data['Close'])
                future_trend = self._calculate_trend_slope(future_data['Close'])
                
                # Check for significant trend reversal
                if (past_trend > 0.001 and future_trend < -0.001) or \
                   (past_trend < -0.001 and future_trend > 0.001):
                    
                    # Additional confirmation using technical indicators
                    rsi = df['RSI'].iloc[i] if 'RSI' in df.columns else 50
                    macd_hist = df['MACD_Hist'].iloc[i] if 'MACD_Hist' in df.columns else 0
                    
                    # Check for volume confirmation
                    recent_volume = df['Volume'].iloc[i-5:i+5].mean()
                    avg_volume = df['Volume'].rolling(window=50).mean().iloc[i]
                    volume_confirmation = recent_volume > avg_volume * 1.2
                    
                    # Score the turning point
                    score = self._score_turning_point(past_trend, future_trend, rsi, macd_hist, volume_confirmation)
                    
                    if score > 0.6:  # Threshold for significance
                        turning_points.append({
                            'date': current_date,
                            'price': current_price,
                            'past_trend': past_trend,
                            'future_trend': future_trend,
                            'score': score,
                            'type': 'PEAK' if past_trend > 0 else 'TROUGH'
                        })
        
        # Remove duplicate nearby turning points
        filtered_points = self._filter_nearby_turning_points(turning_points, min_distance_days=30)
        
        return filtered_points
    
    def _calculate_trend_slope(self, prices: pd.Series) -> float:
        """Calculate the slope of price trend using linear regression"""
        if len(prices) < 2:
            return 0
        
        x = np.arange(len(prices))
        y = prices.values
        
        # Simple linear regression
        n = len(x)
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - np.sum(x)**2)
        
        return slope / np.mean(y)  # Normalize by price level
    
    def _score_turning_point(self, past_trend: float, future_trend: float, rsi: float, 
                           macd_hist: float, volume_confirmation: bool) -> float:
        """Score the significance of a turning point"""
        # Trend reversal strength
        trend_score = min(1.0, abs(past_trend - future_trend) / 0.01)
        
        # RSI confirmation (extreme readings support turning points)
        rsi_score = 0
        if rsi > 70 and past_trend > 0:  # Overbought peak
            rsi_score = 0.3
        elif rsi < 30 and past_trend < 0:  # Oversold trough
            rsi_score = 0.3
        
        # MACD histogram confirmation
        macd_score = 0
        if (past_trend > 0 and macd_hist < 0) or (past_trend < 0 and macd_hist > 0):
            macd_score = 0.2
        
        # Volume confirmation
        volume_score = 0.2 if volume_confirmation else 0
        
        total_score = (trend_score * 0.5 + rsi_score + macd_score + volume_score)
        return min(1.0, total_score)
    
    def _filter_nearby_turning_points(self, turning_points: List[Dict], min_distance_days: int) -> List[Dict]:
        """Filter out turning points that are too close to each other"""
        if not turning_points:
            return []
        
        # Sort by date
        sorted_points = sorted(turning_points, key=lambda x: x['date'])
        filtered_points = [sorted_points[0]]
        
        for point in sorted_points[1:]:
            last_point = filtered_points[-1]
            days_diff = (point['date'] - last_point['date']).days
            
            if days_diff >= min_distance_days:
                filtered_points.append(point)
            elif point['score'] > last_point['score']:
                # Replace with higher scoring point
                filtered_points[-1] = point
        
        return filtered_points
    
    def _calculate_cycle_strength(self, cycle_data: pd.DataFrame, cycle_type: str) -> float:
        """Calculate the strength of a market cycle"""
        if cycle_data.empty:
            return 0.0
        
        price_momentum = abs(cycle_data['Close'].iloc[-1] - cycle_data['Close'].iloc[0]) / cycle_data['Close'].iloc[0]
        
        # Volume strength
        avg_volume = cycle_data['Volume'].mean()
        volume_trend = cycle_data['Volume'].iloc[-10:].mean() / cycle_data['Volume'].iloc[:10].mean() if len(cycle_data) > 20 else 1.0
        
        # Volatility (inverse relationship with strength for bull markets)
        volatility = cycle_data['Close'].pct_change().std()
        volatility_score = max(0, 1 - volatility * 10) if cycle_type == 'Bull Market' else volatility * 5
        
        # Combine metrics
        strength = (price_momentum * 0.5 + min(1.0, volume_trend) * 0.3 + volatility_score * 0.2)
        return min(1.0, strength)
    
    def get_current_trend(self, df: pd.DataFrame, period: int = 20) -> str:
        """
        Determine current market trend
        
        Args:
            df (pd.DataFrame): Price data
            period (int): Period for trend analysis
        
        Returns:
            str: Current trend direction
        """
        if len(df) < period:
            return "Insufficient Data"
        
        recent_data = df.tail(period)
        
        # Calculate trend using multiple methods
        
        # 1. Moving average trend
        ma_short = recent_data['Close'].rolling(window=5).mean().iloc[-1]
        ma_long = recent_data['Close'].rolling(window=period).mean().iloc[-1]
        ma_trend = "Bullish" if ma_short > ma_long else "Bearish"
        
        # 2. Linear regression trend
        slope = self._calculate_trend_slope(recent_data['Close'])
        slope_trend = "Bullish" if slope > 0.001 else "Bearish" if slope < -0.001 else "Sideways"
        
        # 3. Technical indicator trend
        tech_trend = "Neutral"
        if 'RSI' in df.columns and 'MACD_Hist' in df.columns:
            current_rsi = df['RSI'].iloc[-1]
            current_macd = df['MACD_Hist'].iloc[-1]
            
            bullish_signals = 0
            bearish_signals = 0
            
            if current_rsi > 50:
                bullish_signals += 1
            else:
                bearish_signals += 1
            
            if current_macd > 0:
                bullish_signals += 1
            else:
                bearish_signals += 1
            
            tech_trend = "Bullish" if bullish_signals > bearish_signals else "Bearish"
        
        # Combine all trends
        trends = [ma_trend, slope_trend, tech_trend]
        bullish_count = trends.count("Bullish")
        bearish_count = trends.count("Bearish")
        
        if bullish_count > bearish_count:
            return "Bullish"
        elif bearish_count > bullish_count:
            return "Bearish"
        else:
            return "Sideways"
    
    def get_current_cycle_phase(self, df: pd.DataFrame, cycles: List[Dict]) -> str:
        """
        Determine current market cycle phase
        
        Args:
            df (pd.DataFrame): Price data
            cycles (List[Dict]): Identified market cycles
        
        Returns:
            str: Current cycle phase
        """
        if not cycles:
            return "Unknown"
        
        current_date = df.index[-1]
        current_price = df['Close'].iloc[-1]
        
        # Find the most recent cycle
        recent_cycles = [c for c in cycles if c['end_date'] >= current_date - pd.Timedelta(days=90)]
        
        if recent_cycles:
            latest_cycle = max(recent_cycles, key=lambda x: x['end_date'])
            return latest_cycle['type']
        
        # If no recent cycle, analyze current conditions
        recent_performance = (current_price - df['Close'].iloc[-90]) / df['Close'].iloc[-90] * 100 if len(df) >= 90 else 0
        
        if recent_performance > 20:
            return "Bull Market"
        elif recent_performance < -20:
            return "Bear Market"
        else:
            return "Sideways Market"
    
    def calculate_cycle_statistics(self, cycles: List[Dict], df: pd.DataFrame) -> Dict:
        """Calculate statistics for different cycle types"""
        if not cycles:
            return {}
        
        stats = {}
        cycle_types = ['Bull Market', 'Bear Market', 'Sideways Market']
        
        for cycle_type in cycle_types:
            type_cycles = [c for c in cycles if c['type'] == cycle_type]
            
            if type_cycles:
                durations = [c['duration_days'] for c in type_cycles]
                returns = [c['price_change_pct'] for c in type_cycles]
                
                stats[cycle_type] = {
                    'count': len(type_cycles),
                    'avg_duration': np.mean(durations),
                    'median_duration': np.median(durations),
                    'avg_return': np.mean(returns),
                    'median_return': np.median(returns),
                    'best_return': max(returns),
                    'worst_return': min(returns),
                    'success_rate': len([r for r in returns if (r > 0 and cycle_type == 'Bull Market') or 
                                       (r < 0 and cycle_type == 'Bear Market')]) / len(returns) * 100
                }
        
        return stats
    
    def generate_predictions(self, df: pd.DataFrame, cycles: List[Dict], patterns: Dict) -> Dict:
        """
        Generate market predictions based on cycles and patterns
        
        Args:
            df (pd.DataFrame): Price data
            cycles (List[Dict]): Market cycles
            patterns (Dict): Pattern analysis
        
        Returns:
            Dict: Predictions and signals
        """
        current_price = df['Close'].iloc[-1]
        current_date = df.index[-1]
        
        predictions = {
            'signals': [],
            'targets': {},
            'timeline': {},
            'confidence': 0
        }
        
        # Analyze current market conditions
        current_trend = self.get_current_trend(df)
        current_cycle = self.get_current_cycle_phase(df, cycles)
        
        # Technical indicator signals
        signals = self._generate_technical_signals(df)
        
        # Pattern-based signals
        pattern_signals = self._generate_pattern_signals(patterns, df)
        
        # Cycle-based signals
        cycle_signals = self._generate_cycle_signals(cycles, df)
        
        # Combine all signals
        all_signals = signals + pattern_signals + cycle_signals
        
        # Calculate price targets
        targets = self._calculate_price_targets(df, patterns, cycles)
        
        # Generate timeline predictions
        timeline = self._generate_timeline_predictions(df, cycles, current_trend)
        
        # Calculate overall confidence
        confidence = self._calculate_prediction_confidence(all_signals, patterns, cycles)
        
        predictions.update({
            'signals': all_signals,
            'targets': targets,
            'timeline': timeline,
            'confidence': confidence
        })
        
        return predictions
    
    def _generate_technical_signals(self, df: pd.DataFrame) -> List[Dict]:
        """Generate signals based on technical indicators"""
        signals = []
        
        if len(df) < 20:
            return signals
        
        current_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # RSI signals
        if 'RSI' in df.columns:
            rsi = current_row['RSI']
            if rsi < 25:
                signals.append({
                    'type': 'BUY',
                    'strength': 8,
                    'message': f'RSI extremely oversold at {rsi:.1f}',
                    'source': 'RSI'
                })
            elif rsi > 75:
                signals.append({
                    'type': 'SELL',
                    'strength': 8,
                    'message': f'RSI extremely overbought at {rsi:.1f}',
                    'source': 'RSI'
                })
            elif rsi < 35:
                signals.append({
                    'type': 'BUY',
                    'strength': 6,
                    'message': f'RSI oversold at {rsi:.1f}',
                    'source': 'RSI'
                })
            elif rsi > 65:
                signals.append({
                    'type': 'SELL',
                    'strength': 6,
                    'message': f'RSI overbought at {rsi:.1f}',
                    'source': 'RSI'
                })
        
        # MACD signals
        if 'MACD' in df.columns and 'MACD_Signal' in df.columns:
            macd = current_row['MACD']
            macd_signal = current_row['MACD_Signal']
            prev_macd = prev_row['MACD']
            prev_signal = prev_row['MACD_Signal']
            
            # MACD crossover
            if prev_macd <= prev_signal and macd > macd_signal:
                signals.append({
                    'type': 'BUY',
                    'strength': 7,
                    'message': 'MACD bullish crossover detected',
                    'source': 'MACD'
                })
            elif prev_macd >= prev_signal and macd < macd_signal:
                signals.append({
                    'type': 'SELL',
                    'strength': 7,
                    'message': 'MACD bearish crossover detected',
                    'source': 'MACD'
                })
        
        # Bollinger Bands signals
        if 'BB_Upper' in df.columns and 'BB_Lower' in df.columns:
            close = current_row['Close']
            bb_upper = current_row['BB_Upper']
            bb_lower = current_row['BB_Lower']
            
            if close < bb_lower:
                signals.append({
                    'type': 'BUY',
                    'strength': 6,
                    'message': 'Price below lower Bollinger Band - potential bounce',
                    'source': 'Bollinger Bands'
                })
            elif close > bb_upper:
                signals.append({
                    'type': 'SELL',
                    'strength': 6,
                    'message': 'Price above upper Bollinger Band - potential pullback',
                    'source': 'Bollinger Bands'
                })
        
        # Moving Average signals
        if 'MA_Short' in df.columns and 'MA_Long' in df.columns:
            ma_short = current_row['MA_Short']
            ma_long = current_row['MA_Long']
            prev_ma_short = prev_row['MA_Short']
            prev_ma_long = prev_row['MA_Long']
            
            # Golden Cross / Death Cross
            if prev_ma_short <= prev_ma_long and ma_short > ma_long:
                signals.append({
                    'type': 'BUY',
                    'strength': 8,
                    'message': 'Golden Cross - Short MA crossed above Long MA',
                    'source': 'Moving Averages'
                })
            elif prev_ma_short >= prev_ma_long and ma_short < ma_long:
                signals.append({
                    'type': 'SELL',
                    'strength': 8,
                    'message': 'Death Cross - Short MA crossed below Long MA',
                    'source': 'Moving Averages'
                })
        
        return signals
    
    def _generate_pattern_signals(self, patterns: Dict, df: pd.DataFrame) -> List[Dict]:
        """Generate signals based on chart patterns"""
        signals = []
        
        if not patterns.get('chart_patterns'):
            return signals
        
        current_date = df.index[-1]
        current_price = df['Close'].iloc[-1]
        
        # Check recent patterns
        recent_patterns = [p for p in patterns['chart_patterns'] 
                          if (current_date - p['end_date']).days <= 5]
        
        for pattern in recent_patterns:
            pattern_type = pattern['type']
            confidence = pattern['confidence']
            
            if pattern_type in ['DOUBLE_BOTTOM', 'HEAD_AND_SHOULDERS_INVERSE']:
                signals.append({
                    'type': 'BUY',
                    'strength': int(confidence * 10),
                    'message': f'{pattern_type} pattern completed - bullish reversal expected',
                    'source': 'Chart Patterns'
                })
            elif pattern_type in ['DOUBLE_TOP', 'HEAD_AND_SHOULDERS']:
                signals.append({
                    'type': 'SELL',
                    'strength': int(confidence * 10),
                    'message': f'{pattern_type} pattern completed - bearish reversal expected',
                    'source': 'Chart Patterns'
                })
            elif pattern_type in ['BULL_FLAG', 'ASCENDING_TRIANGLE']:
                signals.append({
                    'type': 'BUY',
                    'strength': int(confidence * 8),
                    'message': f'{pattern_type} pattern - continuation expected',
                    'source': 'Chart Patterns'
                })
            elif pattern_type in ['BEAR_FLAG', 'DESCENDING_TRIANGLE']:
                signals.append({
                    'type': 'SELL',
                    'strength': int(confidence * 8),
                    'message': f'{pattern_type} pattern - continuation expected',
                    'source': 'Chart Patterns'
                })
        
        # Support/Resistance signals
        if patterns.get('support_resistance'):
            support_levels = patterns['support_resistance']['support']
            resistance_levels = patterns['support_resistance']['resistance']
            
            # Check if price is near support or resistance
            for support in support_levels[:3]:  # Top 3 support levels
                if abs(current_price - support) / current_price < 0.02:  # Within 2%
                    signals.append({
                        'type': 'BUY',
                        'strength': 6,
                        'message': f'Price near strong support level at ${support:.2f}',
                        'source': 'Support/Resistance'
                    })
            
            for resistance in resistance_levels[:3]:  # Top 3 resistance levels
                if abs(current_price - resistance) / current_price < 0.02:  # Within 2%
                    signals.append({
                        'type': 'SELL',
                        'strength': 6,
                        'message': f'Price near strong resistance level at ${resistance:.2f}',
                        'source': 'Support/Resistance'
                    })
        
        return signals
    
    def _generate_cycle_signals(self, cycles: List[Dict], df: pd.DataFrame) -> List[Dict]:
        """Generate signals based on market cycles"""
        signals = []
        
        if not cycles:
            return signals
        
        current_date = df.index[-1]
        current_price = df['Close'].iloc[-1]
        
        # Analyze cycle patterns
        cycle_stats = self.calculate_cycle_statistics(cycles, df)
        
        # Check if we're near typical cycle turning points
        if cycle_stats:
            for cycle_type, stats in cycle_stats.items():
                if cycle_type in ['Bull Market', 'Bear Market']:
                    avg_duration = stats['avg_duration']
                    
                    # Find current cycle duration
                    recent_cycles = [c for c in cycles if c['end_date'] >= current_date - pd.Timedelta(days=30)]
                    
                    if recent_cycles:
                        current_cycle = max(recent_cycles, key=lambda x: x['end_date'])
                        current_duration = (current_date - current_cycle['start_date']).days
                        
                        # Signal if cycle is getting long
                        if current_duration > avg_duration * 1.5:
                            opposite_signal = 'SELL' if cycle_type == 'Bull Market' else 'BUY'
                            signals.append({
                                'type': opposite_signal,
                                'strength': 5,
                                'message': f'Current {cycle_type.lower()} cycle duration ({current_duration} days) exceeds average ({avg_duration:.0f} days)',
                                'source': 'Cycle Analysis'
                            })
        
        return signals
    
    def _calculate_price_targets(self, df: pd.DataFrame, patterns: Dict, cycles: List[Dict]) -> Dict:
        """Calculate price targets based on analysis"""
        current_price = df['Close'].iloc[-1]
        targets = {}
        
        # Support and resistance targets
        if patterns.get('support_resistance'):
            support_levels = patterns['support_resistance']['support']
            resistance_levels = patterns['support_resistance']['resistance']
            
            if support_levels:
                targets['support'] = support_levels[0]
            if resistance_levels:
                targets['resistance'] = resistance_levels[0]
        
        # Cycle-based targets
        if cycles:
            recent_cycles = [c for c in cycles if c['end_date'] >= df.index[-1] - pd.Timedelta(days=180)]
            
            if recent_cycles:
                bull_cycles = [c for c in recent_cycles if c['type'] == 'Bull Market']
                bear_cycles = [c for c in recent_cycles if c['type'] == 'Bear Market']
                
                if bull_cycles:
                    avg_bull_gain = np.mean([c['price_change_pct'] for c in bull_cycles])
                    targets['bull_target'] = current_price * (1 + avg_bull_gain / 100)
                
                if bear_cycles:
                    avg_bear_loss = np.mean([c['price_change_pct'] for c in bear_cycles])
                    targets['bear_target'] = current_price * (1 + avg_bear_loss / 100)
        
        # Technical targets
        if 'ATR' in df.columns:
            atr = df['ATR'].iloc[-1]
            targets['short_term_high'] = current_price + (atr * 2)
            targets['short_term_low'] = current_price - (atr * 2)
        
        return targets
    
    def _generate_timeline_predictions(self, df: pd.DataFrame, cycles: List[Dict], current_trend: str) -> Dict:
        """Generate timeline-based predictions"""
        timeline = {}
        
        if cycles:
            cycle_stats = self.calculate_cycle_statistics(cycles, df)
            
            # Predict next cycle change
            if current_trend == 'Bullish' and 'Bull Market' in cycle_stats:
                avg_bull_duration = cycle_stats['Bull Market']['avg_duration']
                timeline['next_major_top'] = f"Expected in {int(avg_bull_duration * 0.7)}-{int(avg_bull_duration * 1.3)} days"
            
            elif current_trend == 'Bearish' and 'Bear Market' in cycle_stats:
                avg_bear_duration = cycle_stats['Bear Market']['avg_duration']
                timeline['next_major_bottom'] = f"Expected in {int(avg_bear_duration * 0.7)}-{int(avg_bear_duration * 1.3)} days"
        
        # Short-term predictions based on technical indicators
        if 'RSI' in df.columns:
            rsi = df['RSI'].iloc[-1]
            if rsi > 70:
                timeline['short_term_pullback'] = "Expected within 5-10 days"
            elif rsi < 30:
                timeline['short_term_bounce'] = "Expected within 5-10 days"
        
        return timeline
    
    def _calculate_prediction_confidence(self, signals: List[Dict], patterns: Dict, cycles: List[Dict]) -> float:
        """Calculate overall confidence in predictions"""
        if not signals:
            return 0.0
        
        # Factor 1: Signal consensus
        buy_signals = [s for s in signals if s['type'] == 'BUY']
        sell_signals = [s for s in signals if s['type'] == 'SELL']
        
        signal_consensus = 0
        if len(buy_signals) > len(sell_signals):
            signal_consensus = len(buy_signals) / (len(buy_signals) + len(sell_signals))
        elif len(sell_signals) > len(buy_signals):
            signal_consensus = len(sell_signals) / (len(buy_signals) + len(sell_signals))
        else:
            signal_consensus = 0.5
        
        # Factor 2: Signal strength
        avg_strength = np.mean([s['strength'] for s in signals]) / 10
        
        # Factor 3: Pattern quality
        pattern_quality = 0
        if patterns.get('chart_patterns'):
            confidences = [p['confidence'] for p in patterns['chart_patterns']]
            pattern_quality = np.mean(confidences) if confidences else 0
        
        # Factor 4: Cycle clarity
        cycle_clarity = len(cycles) / 10 if cycles else 0  # More cycles = better understanding
        cycle_clarity = min(1.0, cycle_clarity)
        
        # Combine factors
        overall_confidence = (
            signal_consensus * 0.3 +
            avg_strength * 0.3 +
            pattern_quality * 0.2 +
            cycle_clarity * 0.2
        )
        
        return min(1.0, overall_confidence)
    
    def backtest_strategy(self, df: pd.DataFrame, cycles: List[Dict]) -> Optional[Dict]:
        """
        Backtest the trading strategy based on identified cycles
        
        Args:
            df (pd.DataFrame): Price data
            cycles (List[Dict]): Identified cycles
        
        Returns:
            Optional[Dict]: Backtest results
        """
        if not cycles or len(df) < 100:
            return None
        
        # Simulate trading based on cycle signals
        initial_capital = 10000
        capital = initial_capital
        position = 0  # 0 = cash, 1 = long
        trades = []
        
        for cycle in cycles:
            start_date = cycle['start_date']
            end_date = cycle['end_date']
            cycle_type = cycle['type']
            
            # Find corresponding price data
            cycle_data = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if cycle_data.empty:
                continue
            
            start_price = cycle_data['Close'].iloc[0]
            end_price = cycle_data['Close'].iloc[-1]
            
            # Trading logic
            if cycle_type == 'Bull Market' and position == 0:
                # Buy at cycle start
                shares = capital / start_price
                position = 1
                trades.append({
                    'date': start_date,
                    'action': 'BUY',
                    'price': start_price,
                    'shares': shares,
                    'capital': capital
                })
            
            elif cycle_type == 'Bear Market' and position == 1:
                # Sell at cycle start
                capital = shares * start_price
                position = 0
                trades.append({
                    'date': start_date,
                    'action': 'SELL',
                    'price': start_price,
                    'shares': shares,
                    'capital': capital
                })
        
        # Calculate performance metrics
        if not trades:
            return None
        
        final_capital = capital
        if position == 1:  # Still holding
            final_capital = shares * df['Close'].iloc[-1]
        
        total_return = (final_capital - initial_capital) / initial_capital * 100
        
        # Calculate other metrics
        returns = []
        for i in range(1, len(trades)):
            if trades[i]['action'] == 'SELL' and trades[i-1]['action'] == 'BUY':
                trade_return = (trades[i]['capital'] - trades[i-1]['capital']) / trades[i-1]['capital']
                returns.append(trade_return)
        
        if returns:
            win_rate = len([r for r in returns if r > 0]) / len(returns) * 100
            avg_return = np.mean(returns) * 100
            
            # Calculate Sharpe ratio (simplified)
            if len(returns) > 1:
                sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
            else:
                sharpe_ratio = 0
            
            # Calculate max drawdown
            portfolio_values = [initial_capital]
            current_capital = initial_capital
            
            for trade in trades:
                if trade['action'] == 'BUY':
                    current_capital = trade['capital']
                else:
                    current_capital = trade['capital']
                portfolio_values.append(current_capital)
            
            peak = portfolio_values[0]
            max_drawdown = 0
            for value in portfolio_values:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)
        
        else:
            win_rate = 0
            avg_return = 0
            sharpe_ratio = 0
            max_drawdown = 0
        
        return {
            'total_return': total_return,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'num_trades': len(trades),
            'final_capital': final_capital
        }
