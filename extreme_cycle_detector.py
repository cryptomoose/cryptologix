"""
Extreme Cycle Detector for Cryptologix
Identifies market tops and bottoms using crypto/gold ratio analysis
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.signal import find_peaks
from datetime import datetime, timedelta

class ExtremeCycleDetector:
    
    def __init__(self):
        self.extreme_threshold_high = 95  # 95th percentile for tops
        self.extreme_threshold_low = 5    # 5th percentile for bottoms
        
    def calculate_crypto_gold_ratio(self, crypto_data, gold_data):
        """Calculate crypto/gold ratio for extreme cycle detection"""
        
        if gold_data is None or gold_data.empty or crypto_data is None or crypto_data.empty:
            return None
        
        # Align data by common dates
        crypto_prices = crypto_data['Close']
        gold_prices = gold_data['Close']
        
        # Find common date range
        common_start = max(crypto_prices.index[0], gold_prices.index[0])
        common_end = min(crypto_prices.index[-1], gold_prices.index[-1])
        
        crypto_aligned = crypto_prices[(crypto_prices.index >= common_start) & (crypto_prices.index <= common_end)]
        gold_aligned = gold_prices[(gold_prices.index >= common_start) & (gold_prices.index <= common_end)]
        
        # Ensure same dates
        common_dates = crypto_aligned.index.intersection(gold_aligned.index)
        
        if len(common_dates) < 100:
            return None
        
        crypto_common = crypto_aligned[common_dates]
        gold_common = gold_aligned[common_dates]
        
        # Calculate ratio
        ratio = crypto_common / gold_common
        
        return pd.DataFrame({
            'ratio': ratio,
            'crypto_price': crypto_common,
            'gold_price': gold_common
        })
    
    def detect_extreme_peaks(self, ratio_data, lookback_periods=252):
        """Detect extreme market tops using statistical methods"""
        
        if ratio_data is None or len(ratio_data) < lookback_periods:
            return None
        
        ratio_series = ratio_data['ratio']
        
        # Calculate rolling percentiles for context
        rolling_high = ratio_series.rolling(lookback_periods).quantile(0.95)
        rolling_low = ratio_series.rolling(lookback_periods).quantile(0.05)
        rolling_median = ratio_series.rolling(lookback_periods).median()
        
        # Use scipy to find peaks
        peaks, peak_properties = find_peaks(
            ratio_series.values,
            height=ratio_series.quantile(0.8),  # Must be above 80th percentile
            distance=30,  # At least 30 periods apart
            prominence=ratio_series.std() * 0.5  # Must be prominent
        )
        
        # Find troughs
        inverted_ratio = -ratio_series.values
        troughs, trough_properties = find_peaks(
            inverted_ratio,
            height=-ratio_series.quantile(0.2),  # Must be below 20th percentile
            distance=30,
            prominence=ratio_series.std() * 0.5
        )
        
        extreme_signals = []
        current_ratio = ratio_series.iloc[-1]
        current_date = ratio_series.index[-1]
        
        # Analyze peaks for extreme tops
        if len(peaks) > 0:
            recent_peaks = peaks[peaks > len(ratio_series) - 100]  # Last 100 periods
            
            for peak_idx in recent_peaks:
                peak_ratio = ratio_series.iloc[peak_idx]
                peak_date = ratio_series.index[peak_idx]
                
                # Calculate extremeness score (0-100)
                historical_percentile = stats.percentileofscore(ratio_series.values, peak_ratio)
                
                if historical_percentile >= self.extreme_threshold_high:
                    days_ago = (current_date - peak_date).days
                    
                    extreme_signals.append({
                        'type': 'EXTREME_TOP',
                        'date': peak_date,
                        'ratio_value': peak_ratio,
                        'crypto_price': ratio_data['crypto_price'].iloc[peak_idx],
                        'extremeness_score': historical_percentile,
                        'days_ago': days_ago,
                        'signal_strength': 'CRITICAL' if historical_percentile >= 98 else 'HIGH',
                        'description': f'Extreme market top detected - crypto/gold ratio at {historical_percentile:.1f}th percentile'
                    })
        
        # Analyze troughs for extreme bottoms
        if len(troughs) > 0:
            recent_troughs = troughs[troughs > len(ratio_series) - 100]
            
            for trough_idx in recent_troughs:
                trough_ratio = ratio_series.iloc[trough_idx]
                trough_date = ratio_series.index[trough_idx]
                
                historical_percentile = stats.percentileofscore(ratio_series.values, trough_ratio)
                
                if historical_percentile <= self.extreme_threshold_low:
                    days_ago = (current_date - trough_date).days
                    
                    extreme_signals.append({
                        'type': 'EXTREME_BOTTOM',
                        'date': trough_date,
                        'ratio_value': trough_ratio,
                        'crypto_price': ratio_data['crypto_price'].iloc[trough_idx],
                        'extremeness_score': historical_percentile,
                        'days_ago': days_ago,
                        'signal_strength': 'CRITICAL' if historical_percentile <= 2 else 'HIGH',
                        'description': f'Extreme market bottom detected - crypto/gold ratio at {historical_percentile:.1f}th percentile'
                    })
        
        # Check current extreme conditions
        current_percentile = stats.percentileofscore(ratio_series.values, current_ratio)
        
        if current_percentile >= self.extreme_threshold_high:
            extreme_signals.append({
                'type': 'CURRENT_EXTREME_TOP',
                'date': current_date,
                'ratio_value': current_ratio,
                'crypto_price': ratio_data['crypto_price'].iloc[-1],
                'extremeness_score': current_percentile,
                'days_ago': 0,
                'signal_strength': 'CRITICAL' if current_percentile >= 98 else 'HIGH',
                'description': f'CURRENT EXTREME TOP - crypto/gold ratio at {current_percentile:.1f}th percentile'
            })
        
        elif current_percentile <= self.extreme_threshold_low:
            extreme_signals.append({
                'type': 'CURRENT_EXTREME_BOTTOM',
                'date': current_date,
                'ratio_value': current_ratio,
                'crypto_price': ratio_data['crypto_price'].iloc[-1],
                'extremeness_score': current_percentile,
                'days_ago': 0,
                'signal_strength': 'CRITICAL' if current_percentile <= 2 else 'HIGH',
                'description': f'CURRENT EXTREME BOTTOM - crypto/gold ratio at {current_percentile:.1f}th percentile'
            })
        
        return {
            'extreme_signals': extreme_signals,
            'current_ratio': current_ratio,
            'current_percentile': current_percentile,
            'historical_high': ratio_series.max(),
            'historical_low': ratio_series.min(),
            'ratio_data': ratio_data
        }
    
    def generate_extreme_trading_recommendation(self, extreme_analysis, crypto_symbol):
        """Generate specific trading recommendations based on extreme analysis"""
        
        if not extreme_analysis or not extreme_analysis['extreme_signals']:
            return None
        
        current_percentile = extreme_analysis['current_percentile']
        signals = extreme_analysis['extreme_signals']
        
        # Find most recent extreme signal
        recent_signals = [s for s in signals if s['days_ago'] <= 30]  # Last 30 days
        current_signals = [s for s in signals if s['days_ago'] == 0]  # Today
        
        recommendations = {
            'primary_signal': None,
            'confidence': 0,
            'action': 'HOLD',
            'allocation_recommendation': '50%',
            'specific_actions': [],
            'risk_warnings': [],
            'historical_context': []
        }
        
        # Analyze current extreme conditions
        if current_signals:
            signal = current_signals[0]
            
            if signal['type'] == 'CURRENT_EXTREME_TOP':
                recommendations.update({
                    'primary_signal': 'EXTREME_SELL',
                    'confidence': min(95, 70 + (signal['extremeness_score'] - 95) * 5),
                    'action': 'STRONG SELL',
                    'allocation_recommendation': '0-20%',
                    'specific_actions': [
                        f'IMMEDIATE: Reduce {crypto_symbol.replace("-USD", "")} position to 0-20%',
                        'Take profits at current extreme levels',
                        'Set tight stop-losses on remaining positions',
                        'Consider rotating to gold allocation',
                        'Wait for ratio to drop below 50th percentile before re-entering'
                    ],
                    'risk_warnings': [
                        f'Crypto/gold ratio at extreme {signal["extremeness_score"]:.1f}th percentile',
                        'Historical data shows major corrections from these levels',
                        'Risk of 30-70% drawdown from current levels'
                    ]
                })
            
            elif signal['type'] == 'CURRENT_EXTREME_BOTTOM':
                recommendations.update({
                    'primary_signal': 'EXTREME_BUY',
                    'confidence': min(95, 70 + (5 - signal['extremeness_score']) * 5),
                    'action': 'STRONG BUY',
                    'allocation_recommendation': '80-100%',
                    'specific_actions': [
                        f'IMMEDIATE: Increase {crypto_symbol.replace("-USD", "")} allocation to 80-100%',
                        'Deploy significant capital at these extreme lows',
                        'Use dollar-cost averaging over next 2-4 weeks',
                        'Reduce gold allocation temporarily',
                        'Set wide stop-losses to avoid shakeouts'
                    ],
                    'risk_warnings': [
                        f'Crypto/gold ratio at extreme {signal["extremeness_score"]:.1f}th percentile',
                        'High probability of multi-year bull market from these levels',
                        'Expect high volatility during recovery phase'
                    ]
                })
        
        # Analyze recent extreme signals
        elif recent_signals:
            signal = recent_signals[0]  # Most recent
            
            if signal['type'] == 'EXTREME_TOP':
                if current_percentile > 70:  # Still elevated
                    recommendations.update({
                        'primary_signal': 'POST_EXTREME_TOP',
                        'confidence': 75,
                        'action': 'SELL',
                        'allocation_recommendation': '20-40%',
                        'specific_actions': [
                            f'Recent extreme top {signal["days_ago"]} days ago',
                            'Continue reducing positions while above 70th percentile',
                            'Look for ratio to fall below median for re-entry',
                            'Maintain defensive allocation'
                        ]
                    })
                else:
                    recommendations.update({
                        'primary_signal': 'RECOVERING_FROM_TOP',
                        'confidence': 60,
                        'action': 'CAUTIOUS_BUY',
                        'allocation_recommendation': '40-60%',
                        'specific_actions': [
                            'Ratio declining from recent extreme top',
                            'Begin gradual re-accumulation',
                            'Wait for clear trend reversal confirmation'
                        ]
                    })
            
            elif signal['type'] == 'EXTREME_BOTTOM':
                if current_percentile < 30:  # Still depressed
                    recommendations.update({
                        'primary_signal': 'POST_EXTREME_BOTTOM',
                        'confidence': 85,
                        'action': 'BUY',
                        'allocation_recommendation': '70-90%',
                        'specific_actions': [
                            f'Recent extreme bottom {signal["days_ago"]} days ago',
                            'Excellent accumulation opportunity continues',
                            'Ratio still below 30th percentile',
                            'Aggressive buying recommended'
                        ]
                    })
                else:
                    recommendations.update({
                        'primary_signal': 'RECOVERING_FROM_BOTTOM',
                        'confidence': 70,
                        'action': 'HOLD_STRONG',
                        'allocation_recommendation': '60-80%',
                        'specific_actions': [
                            'Recovery from extreme bottom in progress',
                            'Maintain strong allocation',
                            'Add on any significant dips'
                        ]
                    })
        
        # Add historical context
        all_tops = [s for s in signals if 'TOP' in s['type']]
        all_bottoms = [s for s in signals if 'BOTTOM' in s['type']]
        
        if all_tops:
            last_top = max(all_tops, key=lambda x: x['date'])
            recommendations['historical_context'].append(
                f"Last extreme top: {last_top['date'].strftime('%Y-%m-%d')} "
                f"({last_top['extremeness_score']:.1f}th percentile)"
            )
        
        if all_bottoms:
            last_bottom = max(all_bottoms, key=lambda x: x['date'])
            recommendations['historical_context'].append(
                f"Last extreme bottom: {last_bottom['date'].strftime('%Y-%m-%d')} "
                f"({last_bottom['extremeness_score']:.1f}th percentile)"
            )
        
        return recommendations
    
    def calculate_cycle_position(self, ratio_data):
        """Determine current position in market cycle"""
        
        if ratio_data is None:
            return None
        
        ratio_series = ratio_data['ratio']
        current_ratio = ratio_series.iloc[-1]
        
        # Calculate percentile position
        percentile = stats.percentileofscore(ratio_series.values, current_ratio)
        
        # Determine cycle phase
        if percentile >= 95:
            phase = "EXTREME_EUPHORIA"
            phase_description = "Maximum speculation - historically optimal selling zone"
            color = "#8B0000"  # Dark red
        elif percentile >= 80:
            phase = "LATE_BULL"
            phase_description = "Late bull market - consider taking profits"
            color = "#FF4500"  # Orange red
        elif percentile >= 60:
            phase = "MID_BULL"
            phase_description = "Bull market continuation - hold positions"
            color = "#32CD32"  # Lime green
        elif percentile >= 40:
            phase = "ACCUMULATION"
            phase_description = "Neutral zone - accumulate on dips"
            color = "#FFD700"  # Gold
        elif percentile >= 20:
            phase = "EARLY_BEAR"
            phase_description = "Bear market - reduce risk exposure"
            color = "#FF8C00"  # Dark orange
        elif percentile >= 5:
            phase = "DEEP_BEAR"
            phase_description = "Deep bear market - prepare for opportunity"
            color = "#B22222"  # Fire brick
        else:
            phase = "EXTREME_DESPAIR"
            phase_description = "Maximum pessimism - historically optimal buying zone"
            color = "#006400"  # Dark green
        
        return {
            'current_phase': phase,
            'phase_description': phase_description,
            'percentile': percentile,
            'color': color,
            'cycle_progress': percentile,
            'distance_to_top': 100 - percentile,
            'distance_to_bottom': percentile
        }