"""
Cycle Predictor for Cryptologix
Predicts maximum/minimum prices and timing for market cycles
"""

import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime, timedelta
import math

class CyclePredictor:
    
    def __init__(self):
        self.fibonacci_ratios = [1.618, 2.618, 4.236, 6.854]  # Golden ratio extensions
        self.cycle_multipliers = {
            'conservative': 1.0,
            'moderate': 1.5,
            'aggressive': 2.0
        }
    
    def predict_cycle_extremes(self, crypto_data, gold_data, symbol):
        """Predict maximum top, minimum bottom, and timing"""
        
        if crypto_data is None or crypto_data.empty:
            return None
        
        current_price = crypto_data['Close'].iloc[-1]
        prices = crypto_data['Close'].values
        dates = crypto_data.index
        
        # Calculate historical cycle characteristics
        cycle_analysis = self._analyze_historical_cycles(crypto_data, gold_data)
        
        # Predict maximum cycle top
        max_prediction = self._predict_cycle_maximum(crypto_data, cycle_analysis)
        
        # Predict minimum cycle bottom
        min_prediction = self._predict_cycle_minimum(crypto_data, cycle_analysis)
        
        # Predict timing to extremes
        timing_prediction = self._predict_timing_to_extremes(crypto_data, gold_data, cycle_analysis)
        
        return {
            'symbol': symbol,
            'current_price': current_price,
            'max_prediction': max_prediction,
            'min_prediction': min_prediction,
            'timing_prediction': timing_prediction,
            'cycle_analysis': cycle_analysis,
            'confidence_score': self._calculate_prediction_confidence(cycle_analysis),
            'last_updated': datetime.now()
        }
    
    def _analyze_historical_cycles(self, crypto_data, gold_data):
        """Analyze historical market cycles"""
        
        prices = crypto_data['Close'].values
        
        # Find historical peaks and troughs using rolling windows
        window = 50  # 50-day window for peak/trough identification
        
        peaks = []
        troughs = []
        
        for i in range(window, len(prices) - window):
            price_window = prices[i-window:i+window+1]
            center_price = prices[i]
            
            if center_price == max(price_window):
                peaks.append({'date': crypto_data.index[i], 'price': center_price, 'index': i})
            elif center_price == min(price_window):
                troughs.append({'date': crypto_data.index[i], 'price': center_price, 'index': i})
        
        # Calculate cycle characteristics
        cycle_lengths = []
        peak_to_peak_ratios = []
        trough_to_trough_ratios = []
        
        # Peak to peak analysis
        if len(peaks) >= 2:
            for i in range(1, len(peaks)):
                cycle_length = (peaks[i]['date'] - peaks[i-1]['date']).days
                cycle_lengths.append(cycle_length)
                
                price_ratio = peaks[i]['price'] / peaks[i-1]['price']
                peak_to_peak_ratios.append(price_ratio)
        
        # Trough to trough analysis
        if len(troughs) >= 2:
            for i in range(1, len(troughs)):
                if len(cycle_lengths) < 10:  # Don't override if we have good peak data
                    cycle_length = (troughs[i]['date'] - troughs[i-1]['date']).days
                    cycle_lengths.append(cycle_length)
                
                price_ratio = troughs[i]['price'] / troughs[i-1]['price']
                trough_to_trough_ratios.append(price_ratio)
        
        # Calculate average cycle characteristics
        avg_cycle_length = np.mean(cycle_lengths) if cycle_lengths else 365 * 4  # Default 4 years
        avg_peak_ratio = np.mean(peak_to_peak_ratios) if peak_to_peak_ratios else 10.0
        avg_trough_ratio = np.mean(trough_to_trough_ratios) if trough_to_trough_ratios else 1.5
        
        # Calculate drawdown characteristics
        max_drawdowns = []
        for peak in peaks:
            future_prices = prices[peak['index']:]
            if len(future_prices) > 30:  # Need at least 30 days of data
                min_future = min(future_prices)
                drawdown = (peak['price'] - min_future) / peak['price']
                max_drawdowns.append(drawdown)
        
        avg_max_drawdown = np.mean(max_drawdowns) if max_drawdowns else 0.8  # Default 80%
        
        return {
            'peaks': peaks,
            'troughs': troughs,
            'avg_cycle_length_days': avg_cycle_length,
            'avg_peak_ratio': avg_peak_ratio,
            'avg_trough_ratio': avg_trough_ratio,
            'avg_max_drawdown': avg_max_drawdown,
            'total_cycles': len(peaks),
            'data_years': len(crypto_data) / 365.25
        }
    
    def _predict_cycle_maximum(self, crypto_data, cycle_analysis):
        """Predict maximum price for current cycle"""
        
        current_price = crypto_data['Close'].iloc[-1]
        
        # Method 1: Fibonacci extensions from last major low
        recent_lows = [t['price'] for t in cycle_analysis['troughs'][-3:]]  # Last 3 lows
        if recent_lows:
            base_low = min(recent_lows)
            fib_targets = []
            
            for ratio in self.fibonacci_ratios:
                fib_target = base_low * ratio
                if fib_target > current_price:  # Only consider targets above current price
                    fib_targets.append(fib_target)
        else:
            fib_targets = [current_price * 2, current_price * 4, current_price * 8]
        
        # Method 2: Historical peak ratio analysis
        if cycle_analysis['avg_peak_ratio'] > 1:
            # Find last major low to project from
            prices = crypto_data['Close'].values
            last_year_low = min(prices[-365:]) if len(prices) >= 365 else min(prices)
            
            ratio_targets = []
            for multiplier in [1.0, 1.5, 2.0]:  # Conservative to aggressive
                projected_ratio = cycle_analysis['avg_peak_ratio'] * multiplier
                ratio_target = last_year_low * projected_ratio
                if ratio_target > current_price:
                    ratio_targets.append(ratio_target)
        else:
            ratio_targets = []
        
        # Method 3: Log regression trend projection
        log_prices = np.log(crypto_data['Close'].values)
        time_index = np.arange(len(log_prices))
        
        # Fit trend line to recent data (use all available data for better trend analysis)
        recent_data_points = len(log_prices)  # Use all available historical data
        recent_log_prices = log_prices[-recent_data_points:]
        recent_time = time_index[-recent_data_points:]
        
        slope, intercept, r_value, _, _ = stats.linregress(recent_time, recent_log_prices)
        
        # Project trend forward (next 1-2 years)
        future_time_points = [len(log_prices) + 365, len(log_prices) + 730]  # 1 and 2 years
        trend_targets = []
        
        for future_time in future_time_points:
            projected_log_price = slope * future_time + intercept
            projected_price = np.exp(projected_log_price)
            if projected_price > current_price:
                trend_targets.append(projected_price)
        
        # Combine all methods
        all_targets = fib_targets + ratio_targets + trend_targets
        
        if all_targets:
            conservative_target = np.percentile(all_targets, 25)
            moderate_target = np.percentile(all_targets, 50)
            aggressive_target = np.percentile(all_targets, 75)
        else:
            # Fallback predictions
            conservative_target = current_price * 2
            moderate_target = current_price * 5
            aggressive_target = current_price * 10
        
        return {
            'conservative': conservative_target,
            'moderate': moderate_target,
            'aggressive': aggressive_target,
            'fibonacci_targets': fib_targets[:3] if fib_targets else [],
            'ratio_targets': ratio_targets[:3] if ratio_targets else [],
            'trend_targets': trend_targets[:2] if trend_targets else [],
            'method_count': len([x for x in [fib_targets, ratio_targets, trend_targets] if x])
        }
    
    def _predict_cycle_minimum(self, crypto_data, cycle_analysis):
        """Predict minimum price for current cycle"""
        
        current_price = crypto_data['Close'].iloc[-1]
        
        # Method 1: Historical drawdown analysis
        avg_drawdown = cycle_analysis['avg_max_drawdown']
        
        # Find recent peak to calculate drawdown from
        recent_peaks = cycle_analysis['peaks'][-3:] if cycle_analysis['peaks'] else []
        if recent_peaks:
            recent_high = max([p['price'] for p in recent_peaks])
        else:
            recent_high = crypto_data['High'].tail(365).max()  # Last year high
        
        drawdown_targets = []
        for severity in [0.5, 0.7, 0.9]:  # 50%, 70%, 90% drawdowns
            target = recent_high * (1 - avg_drawdown * severity)
            if target < current_price:  # Only consider targets below current price
                drawdown_targets.append(target)
        
        # Method 2: Support level analysis
        prices = crypto_data['Close'].values
        support_levels = []
        
        # Find significant historical support levels
        for lookback in [365, 730, 1095]:  # 1, 2, 3 years
            if len(prices) >= lookback:
                period_low = min(prices[-lookback:])
                support_levels.append(period_low)
        
        # Method 3: Moving average support
        ma_supports = []
        for period in [200, 300, 500]:  # Long-term MAs
            if len(prices) >= period:
                ma = np.mean(prices[-period:])
                # Typical support is 20-40% below long-term MA during bear markets
                ma_supports.extend([ma * 0.6, ma * 0.7, ma * 0.8])
        
        ma_supports = [s for s in ma_supports if s < current_price]
        
        # Combine all methods
        all_targets = drawdown_targets + support_levels + ma_supports
        
        if all_targets:
            # Filter out unrealistic targets (too close to zero)
            realistic_targets = [t for t in all_targets if t > current_price * 0.05]
            
            if realistic_targets:
                conservative_target = np.percentile(realistic_targets, 75)  # Higher price (less severe)
                moderate_target = np.percentile(realistic_targets, 50)
                aggressive_target = np.percentile(realistic_targets, 25)  # Lower price (more severe)
            else:
                conservative_target = current_price * 0.5
                moderate_target = current_price * 0.3
                aggressive_target = current_price * 0.1
        else:
            # Fallback predictions
            conservative_target = current_price * 0.5
            moderate_target = current_price * 0.3
            aggressive_target = current_price * 0.1
        
        return {
            'conservative': conservative_target,
            'moderate': moderate_target,
            'aggressive': aggressive_target,
            'drawdown_targets': drawdown_targets[:3] if drawdown_targets else [],
            'support_levels': support_levels,
            'ma_supports': ma_supports[:3] if ma_supports else []
        }
    
    def _predict_timing_to_extremes(self, crypto_data, gold_data, cycle_analysis):
        """Predict timing to reach cycle extremes"""
        
        # Analyze current cycle position
        current_date = crypto_data.index[-1]
        
        # Estimate where we are in the current cycle
        if cycle_analysis['peaks'] and cycle_analysis['troughs']:
            last_peak = cycle_analysis['peaks'][-1] if cycle_analysis['peaks'] else None
            last_trough = cycle_analysis['troughs'][-1] if cycle_analysis['troughs'] else None
            
            # Determine if we're closer to peak or trough timing
            if last_peak and last_trough:
                if last_peak['date'] > last_trough['date']:
                    # Last major move was a peak - likely in downtrend
                    days_since_peak = (current_date - last_peak['date']).days
                    cycle_position = 'post_peak'
                else:
                    # Last major move was a trough - likely in uptrend
                    days_since_trough = (current_date - last_trough['date']).days
                    cycle_position = 'post_trough'
            else:
                cycle_position = 'unknown'
        else:
            cycle_position = 'unknown'
        
        avg_cycle_length = cycle_analysis['avg_cycle_length_days']
        
        # Predict timing based on cycle position and historical patterns
        if cycle_position == 'post_trough':
            # Typically peaks occur 1-3 years after major troughs
            days_to_peak_conservative = int(avg_cycle_length * 0.3)  # 30% through cycle
            days_to_peak_moderate = int(avg_cycle_length * 0.5)      # 50% through cycle
            days_to_peak_aggressive = int(avg_cycle_length * 0.7)    # 70% through cycle
            
            # Bottoms are further out (next cycle)
            days_to_bottom_conservative = int(avg_cycle_length * 0.8)
            days_to_bottom_moderate = int(avg_cycle_length * 1.2)
            days_to_bottom_aggressive = int(avg_cycle_length * 1.5)
            
        elif cycle_position == 'post_peak':
            # Bottoms typically occur 1-2 years after peaks
            days_to_bottom_conservative = int(avg_cycle_length * 0.2)
            days_to_bottom_moderate = int(avg_cycle_length * 0.4)
            days_to_bottom_aggressive = int(avg_cycle_length * 0.6)
            
            # Next peak is further out
            days_to_peak_conservative = int(avg_cycle_length * 0.7)
            days_to_peak_moderate = int(avg_cycle_length * 1.0)
            days_to_peak_aggressive = int(avg_cycle_length * 1.3)
            
        else:
            # Unknown position - use average estimates
            half_cycle = int(avg_cycle_length / 2)
            days_to_peak_conservative = half_cycle - 180
            days_to_peak_moderate = half_cycle
            days_to_peak_aggressive = half_cycle + 180
            
            days_to_bottom_conservative = half_cycle - 180
            days_to_bottom_moderate = half_cycle
            days_to_bottom_aggressive = half_cycle + 180
        
        # Ensure minimum realistic timeframes
        days_to_peak_conservative = max(30, days_to_peak_conservative)
        days_to_peak_moderate = max(90, days_to_peak_moderate)
        days_to_peak_aggressive = max(180, days_to_peak_aggressive)
        
        days_to_bottom_conservative = max(30, days_to_bottom_conservative)
        days_to_bottom_moderate = max(90, days_to_bottom_moderate)
        days_to_bottom_aggressive = max(180, days_to_bottom_aggressive)
        
        return {
            'cycle_position': cycle_position,
            'days_to_peak': {
                'conservative': days_to_peak_conservative,
                'moderate': days_to_peak_moderate,
                'aggressive': days_to_peak_aggressive
            },
            'days_to_bottom': {
                'conservative': days_to_bottom_conservative,
                'moderate': days_to_bottom_moderate,
                'aggressive': days_to_bottom_aggressive
            },
            'peak_dates': {
                'conservative': current_date + timedelta(days=days_to_peak_conservative),
                'moderate': current_date + timedelta(days=days_to_peak_moderate),
                'aggressive': current_date + timedelta(days=days_to_peak_aggressive)
            },
            'bottom_dates': {
                'conservative': current_date + timedelta(days=days_to_bottom_conservative),
                'moderate': current_date + timedelta(days=days_to_bottom_moderate),
                'aggressive': current_date + timedelta(days=days_to_bottom_aggressive)
            }
        }
    
    def _calculate_prediction_confidence(self, cycle_analysis):
        """Calculate confidence score for predictions"""
        
        confidence = 50  # Base confidence
        
        # More historical data increases confidence
        if cycle_analysis['data_years'] >= 5:
            confidence += 20
        elif cycle_analysis['data_years'] >= 3:
            confidence += 10
        
        # More complete cycles increase confidence
        if cycle_analysis['total_cycles'] >= 3:
            confidence += 15
        elif cycle_analysis['total_cycles'] >= 2:
            confidence += 10
        elif cycle_analysis['total_cycles'] >= 1:
            confidence += 5
        
        # Consistent cycle patterns increase confidence
        if len(cycle_analysis['peaks']) >= 2:
            confidence += 10
        
        return min(95, max(30, confidence))  # Cap between 30-95%