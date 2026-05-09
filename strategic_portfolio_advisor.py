"""
Strategic Portfolio Advisor for Long-term Crypto DCA Investors
Identifies extreme bubble tops for liquidation and crash lows for bulk accumulation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

class StrategicPortfolioAdvisor:
    """
    Strategic advisor for long-term crypto investors who:
    1. Dollar-cost average regularly
    2. Liquidate to precious metals during bubble peaks
    3. Bulk buy during crash lows after liquidating other assets
    """
    
    def __init__(self):
        # Strategic thresholds for extreme market conditions
        self.strategic_thresholds = {
            # Bubble detection (for liquidation to precious metals)
            'bubble_rsi_threshold': 85,  # Extreme overbought
            'bubble_gain_threshold': 5.0,  # 500% gain from previous low
            'bubble_volume_surge': 3.0,  # 3x volume surge
            'bubble_parabolic_move': 0.20,  # 20% weekly gains
            
            # Crash detection (for bulk accumulation)
            'crash_decline_threshold': -0.80,  # 80% decline from peak
            'crash_capitulation_rsi': 15,  # Extreme oversold
            'crash_volume_spike': 5.0,  # 5x volume during selling
            'crash_support_test': 0.05,  # Testing major support levels
            
            # DCA adjustment factors
            'normal_dca_multiplier': 1.0,  # Standard DCA amount
            'moderate_opportunity_multiplier': 2.0,  # 2x DCA on moderate dips
            'extreme_opportunity_multiplier': 5.0,  # 5x DCA on crash lows
        }
    
    def analyze_bubble_conditions(self, df: pd.DataFrame) -> Dict:
        """
        Analyze current conditions for potential bubble/peak liquidation
        
        Returns:
            Dict: Bubble analysis with liquidation recommendations
        """
        if len(df) < 200:
            return {'bubble_score': 0, 'liquidation_signal': 'HOLD'}
        
        current_price = df['Close'].iloc[-1]
        bubble_indicators = []
        bubble_score = 0
        
        # 1. Extreme RSI Analysis (25 points max)
        if 'RSI' in df.columns:
            current_rsi = df['RSI'].iloc[-1]
            if current_rsi > self.strategic_thresholds['bubble_rsi_threshold']:
                rsi_score = min(25, (current_rsi - 70) * 1.25)
                bubble_indicators.append(f"Extreme RSI: {current_rsi:.1f}")
                bubble_score += rsi_score
        
        # 2. Massive Gain from Previous Low (30 points max)
        if len(df) >= 365:
            # Find major low in past 2-4 years
            lookback_period = min(len(df), 1460)  # 4 years max
            historical_low = df['Close'].iloc[-lookback_period:].min()
            total_gain = (current_price - historical_low) / historical_low
            
            if total_gain > self.strategic_thresholds['bubble_gain_threshold']:
                gain_score = min(30, total_gain * 6)  # Scale factor
                bubble_indicators.append(f"Massive gain: {total_gain*100:.0f}% from low")
                bubble_score += gain_score
        
        # 3. Parabolic Price Movement (20 points max)
        if len(df) >= 30:
            weekly_returns = df['Close'].pct_change(7).dropna().tail(4)  # Last 4 weeks
            avg_weekly_return = weekly_returns.mean()
            
            if avg_weekly_return > self.strategic_thresholds['bubble_parabolic_move']:
                parabolic_score = min(20, avg_weekly_return * 100)
                bubble_indicators.append(f"Parabolic move: {avg_weekly_return*100:.1f}% weekly")
                bubble_score += parabolic_score
        
        # 4. Volume Surge Analysis (15 points max)
        if len(df) >= 50:
            recent_volume = df['Volume'].tail(7).mean()
            baseline_volume = df['Volume'].tail(100).mean()
            volume_ratio = recent_volume / baseline_volume
            
            if volume_ratio > self.strategic_thresholds['bubble_volume_surge']:
                volume_score = min(15, (volume_ratio - 1) * 5)
                bubble_indicators.append(f"Volume surge: {volume_ratio:.1f}x")
                bubble_score += volume_score
        
        # 5. Technical Divergence (10 points max)
        if 'MACD' in df.columns and len(df) >= 50:
            # Price making new highs but MACD not confirming
            recent_price_high = df['Close'].tail(20).max()
            is_price_new_high = recent_price_high == df['Close'].tail(50).max()
            
            recent_macd_high = df['MACD'].tail(20).max()
            is_macd_new_high = recent_macd_high == df['MACD'].tail(50).max()
            
            if is_price_new_high and not is_macd_new_high:
                bubble_indicators.append("Bearish MACD divergence")
                bubble_score += 10
        
        # Generate liquidation recommendation
        if bubble_score >= 70:
            liquidation_signal = 'LIQUIDATE_MAJOR'  # 75-100% liquidation
            recommendation = f"EXTREME BUBBLE DETECTED - Consider liquidating 75-100% to precious metals"
        elif bubble_score >= 50:
            liquidation_signal = 'LIQUIDATE_PARTIAL'  # 25-50% liquidation
            recommendation = f"BUBBLE CONDITIONS - Consider liquidating 25-50% to precious metals"
        elif bubble_score >= 30:
            liquidation_signal = 'REDUCE_DCA'  # Pause DCA, hold existing
            recommendation = f"ELEVATED RISK - Pause DCA, prepare for potential peak"
        else:
            liquidation_signal = 'HOLD'
            recommendation = f"Continue normal DCA strategy"
        
        return {
            'bubble_score': round(bubble_score, 1),
            'liquidation_signal': liquidation_signal,
            'recommendation': recommendation,
            'indicators': bubble_indicators,
            'current_price': current_price,
            'risk_level': 'EXTREME' if bubble_score >= 70 else 'HIGH' if bubble_score >= 50 else 'MODERATE' if bubble_score >= 30 else 'LOW'
        }
        
        # Add price level predictions
        bubble_result['predicted_peak_range'] = self._predict_peak_price_levels(df, bubble_score)
        bubble_result['resistance_levels'] = self._identify_resistance_levels(df)
        
        return bubble_result
    
    def analyze_crash_opportunities(self, df: pd.DataFrame) -> Dict:
        """
        Analyze current conditions for bulk accumulation opportunities
        
        Returns:
            Dict: Crash analysis with accumulation recommendations
        """
        if len(df) < 200:
            return {'crash_score': 0, 'accumulation_signal': 'NORMAL_DCA'}
        
        current_price = df['Close'].iloc[-1]
        crash_indicators = []
        crash_score = 0
        
        # 1. Major Decline from Peak (35 points max)
        if len(df) >= 365:
            # Find major peak in past 2-4 years
            lookback_period = min(len(df), 1460)  # 4 years max
            historical_high = df['Close'].iloc[-lookback_period:].max()
            total_decline = (current_price - historical_high) / historical_high
            
            if total_decline < self.strategic_thresholds['crash_decline_threshold']:
                decline_score = min(35, abs(total_decline) * 40)  # Scale factor
                crash_indicators.append(f"Major crash: {total_decline*100:.0f}% from peak")
                crash_score += decline_score
        
        # 2. Extreme Oversold RSI (25 points max)
        if 'RSI' in df.columns:
            current_rsi = df['RSI'].iloc[-1]
            if current_rsi < self.strategic_thresholds['crash_capitulation_rsi']:
                rsi_score = min(25, (30 - current_rsi) * 1.67)
                crash_indicators.append(f"Capitulation RSI: {current_rsi:.1f}")
                crash_score += rsi_score
        
        # 3. Volume Capitulation Spike (20 points max)
        if len(df) >= 50:
            recent_volume = df['Volume'].tail(7).mean()
            baseline_volume = df['Volume'].tail(100).mean()
            volume_ratio = recent_volume / baseline_volume
            
            if volume_ratio > self.strategic_thresholds['crash_volume_spike']:
                volume_score = min(20, (volume_ratio - 1) * 4)
                crash_indicators.append(f"Capitulation volume: {volume_ratio:.1f}x")
                crash_score += volume_score
        
        # 4. Support Level Test (15 points max)
        if len(df) >= 730:  # 2 years of data
            # Major historical support levels
            historical_lows = df['Close'].iloc[:-90].quantile([0.05, 0.10, 0.15])  # Bottom percentiles
            
            for percentile, support_level in historical_lows.items():
                if abs(current_price - support_level) / support_level < self.strategic_thresholds['crash_support_test']:
                    crash_indicators.append(f"Testing {percentile*100:.0f}th percentile support")
                    crash_score += 15
                    break
        
        # 5. Bullish Divergence (5 points max)
        if 'MACD' in df.columns and len(df) >= 50:
            # Price making new lows but MACD showing strength
            recent_price_low = df['Close'].tail(20).min()
            is_price_new_low = recent_price_low == df['Close'].tail(50).min()
            
            recent_macd_low = df['MACD'].tail(20).min()
            is_macd_new_low = recent_macd_low == df['MACD'].tail(50).min()
            
            if is_price_new_low and not is_macd_new_low:
                crash_indicators.append("Bullish MACD divergence")
                crash_score += 5
        
        # Generate accumulation recommendation
        if crash_score >= 60:
            accumulation_signal = 'BULK_BUY_EXTREME'  # 5x+ normal DCA
            dca_multiplier = self.strategic_thresholds['extreme_opportunity_multiplier']
            recommendation = f"EXTREME CRASH OPPORTUNITY - Liquidate other assets for 5x+ accumulation"
        elif crash_score >= 40:
            accumulation_signal = 'BULK_BUY_MAJOR'  # 3x normal DCA
            dca_multiplier = 3.0
            recommendation = f"MAJOR CRASH OPPORTUNITY - Consider 3x normal accumulation"
        elif crash_score >= 25:
            accumulation_signal = 'DCA_INCREASE'  # 2x normal DCA
            dca_multiplier = self.strategic_thresholds['moderate_opportunity_multiplier']
            recommendation = f"GOOD OPPORTUNITY - Increase DCA to 2x normal amount"
        else:
            accumulation_signal = 'NORMAL_DCA'
            dca_multiplier = self.strategic_thresholds['normal_dca_multiplier']
            recommendation = f"Continue normal DCA strategy"
        
        return {
            'crash_score': round(crash_score, 1),
            'accumulation_signal': accumulation_signal,
            'dca_multiplier': dca_multiplier,
            'recommendation': recommendation,
            'indicators': crash_indicators,
            'current_price': current_price,
            'opportunity_level': 'EXTREME' if crash_score >= 60 else 'MAJOR' if crash_score >= 40 else 'GOOD' if crash_score >= 25 else 'NORMAL'
        }
        
        # Add price level predictions  
        crash_result['predicted_trough_range'] = self._predict_trough_price_levels(df, crash_score)
        crash_result['support_levels'] = self._identify_support_levels(df)
        
        return crash_result
    
    def generate_strategic_advice(self, df: pd.DataFrame, current_portfolio_value: float = 100000) -> Dict:
        """
        Generate comprehensive strategic advice for long-term DCA investors
        
        Args:
            df (pd.DataFrame): Price data with indicators
            current_portfolio_value (float): Current crypto portfolio value
            
        Returns:
            Dict: Strategic advice with specific actions
        """
        bubble_analysis = self.analyze_bubble_conditions(df)
        crash_analysis = self.analyze_crash_opportunities(df)
        
        # Determine primary recommendation
        if bubble_analysis['bubble_score'] > crash_analysis['crash_score']:
            primary_signal = 'LIQUIDATION_OPPORTUNITY'
            primary_analysis = bubble_analysis
            secondary_analysis = crash_analysis
        else:
            primary_signal = 'ACCUMULATION_OPPORTUNITY'
            primary_analysis = crash_analysis
            secondary_analysis = bubble_analysis
        
        # Calculate specific dollar amounts for different scenarios
        weekly_dca_amount = 500  # Assume $500 weekly DCA
        
        strategic_advice = {
            'primary_signal': primary_signal,
            'bubble_analysis': bubble_analysis,
            'crash_analysis': crash_analysis,
            'current_price': df['Close'].iloc[-1],
            'timestamp': datetime.now(),
        }
        
        # Generate specific action plan
        if bubble_analysis['liquidation_signal'] == 'LIQUIDATE_MAJOR':
            strategic_advice['action_plan'] = {
                'immediate_action': 'SELL',
                'percentage_to_liquidate': '75-100%',
                'target_asset': 'Physical gold/silver',
                'reasoning': 'Extreme bubble conditions detected - preserve wealth in precious metals',
                'timeline': 'Within 1-2 weeks',
                'estimated_liquidation': f"${current_portfolio_value * 0.75:,.0f} - ${current_portfolio_value:,.0f}"
            }
        elif bubble_analysis['liquidation_signal'] == 'LIQUIDATE_PARTIAL':
            strategic_advice['action_plan'] = {
                'immediate_action': 'PARTIAL_SELL',
                'percentage_to_liquidate': '25-50%',
                'target_asset': 'Physical gold/silver or cash',
                'reasoning': 'Bubble conditions forming - take some profits',
                'timeline': 'Within 2-4 weeks',
                'estimated_liquidation': f"${current_portfolio_value * 0.25:,.0f} - ${current_portfolio_value * 0.5:,.0f}"
            }
        elif crash_analysis['accumulation_signal'] == 'BULK_BUY_EXTREME':
            strategic_advice['action_plan'] = {
                'immediate_action': 'BULK_ACCUMULATE',
                'dca_adjustment': '5x+ normal amount',
                'funding_source': 'Liquidate other assets (stocks, bonds, etc.)',
                'reasoning': 'Extreme crash opportunity - maximum accumulation',
                'timeline': 'Over next 4-8 weeks',
                'weekly_amount': f"${weekly_dca_amount * 5:,.0f}+ per week"
            }
        elif crash_analysis['accumulation_signal'] == 'BULK_BUY_MAJOR':
            strategic_advice['action_plan'] = {
                'immediate_action': 'INCREASE_ACCUMULATION',
                'dca_adjustment': '3x normal amount',
                'funding_source': 'Available cash reserves',
                'reasoning': 'Major crash opportunity - significant accumulation',
                'timeline': 'Over next 6-10 weeks',
                'weekly_amount': f"${weekly_dca_amount * 3:,.0f} per week"
            }
        else:
            strategic_advice['action_plan'] = {
                'immediate_action': 'CONTINUE_DCA',
                'dca_adjustment': f"{crash_analysis['dca_multiplier']:.1f}x normal amount",
                'reasoning': 'Normal market conditions - stick to plan',
                'weekly_amount': f"${weekly_dca_amount * crash_analysis['dca_multiplier']:,.0f} per week"
            }
        
        return strategic_advice
    
    def format_strategic_summary(self, analysis: Dict) -> str:
        """Format the strategic analysis into a clear one-line summary"""
        
        if analysis['primary_signal'] == 'LIQUIDATION_OPPORTUNITY':
            bubble = analysis['bubble_analysis']
            if bubble['liquidation_signal'] == 'LIQUIDATE_MAJOR':
                return f"🔴 EXTREME BUBBLE: Liquidate {analysis['action_plan']['percentage_to_liquidate']} to precious metals - Risk Level: {bubble['risk_level']}"
            elif bubble['liquidation_signal'] == 'LIQUIDATE_PARTIAL':
                return f"🟠 BUBBLE FORMING: Liquidate {analysis['action_plan']['percentage_to_liquidate']} to precious metals - Risk Level: {bubble['risk_level']}"
            else:
                return f"🟡 ELEVATED RISK: Pause DCA, monitor for peak - Continue holding current positions"
        else:
            crash = analysis['crash_analysis']
            if crash['accumulation_signal'] == 'BULK_BUY_EXTREME':
                return f"🟢 EXTREME CRASH: Liquidate other assets for {crash['dca_multiplier']:.0f}x+ DCA - Opportunity Level: {crash['opportunity_level']}"
            elif crash['accumulation_signal'] == 'BULK_BUY_MAJOR':
                return f"🟢 MAJOR CRASH: Increase to {crash['dca_multiplier']:.0f}x normal DCA - Opportunity Level: {crash['opportunity_level']}"
            elif crash['accumulation_signal'] == 'DCA_INCREASE':
                return f"🔵 GOOD OPPORTUNITY: Increase to {crash['dca_multiplier']:.0f}x normal DCA - Opportunity Level: {crash['opportunity_level']}"
            else:
                return f"⚪ NORMAL CONDITIONS: Continue regular ${crash.get('weekly_amount', 'normal')} DCA strategy"
    
    def _predict_peak_price_levels(self, df: pd.DataFrame, bubble_score: float) -> Dict:
        """Predict potential peak price levels with confidence indicators"""
        current_price = df['Close'].iloc[-1]
        
        # Calculate resistance levels and projections
        if len(df) < 100:
            return {'prediction': 'Insufficient data', 'confidence': 0}
        
        # Historical resistance levels
        recent_highs = df['High'].tail(365).nlargest(10) if len(df) >= 365 else df['High'].nlargest(10)
        resistance_levels = []
        
        for high in recent_highs:
            if high > current_price * 1.05:  # At least 5% above current
                resistance_levels.append(high)
        
        # Fibonacci extensions from recent major swing
        if len(df) >= 200:
            # Find major low and high for fibonacci calculation
            lookback = min(200, len(df))
            recent_data = df.tail(lookback)
            major_low = recent_data['Low'].min()
            major_high = recent_data['High'].max()
            
            fib_range = major_high - major_low
            fib_levels = {
                '1.618': major_high + (fib_range * 0.618),
                '2.618': major_high + (fib_range * 1.618),
                '4.236': major_high + (fib_range * 3.236)
            }
        else:
            fib_levels = {}
        
        # Logarithmic trend projection
        log_projection = None
        confidence = 50  # Base confidence
        
        if bubble_score >= 50:
            # Higher confidence predictions when bubble conditions exist
            confidence = min(85, 50 + bubble_score * 0.5)
            
            # Project based on current parabolic trend
            if len(df) >= 50:
                recent_gains = df['Close'].pct_change(20).tail(5).mean()  # 20-day returns, last 5 periods
                if recent_gains > 0.1:  # 10%+ recent gains
                    projected_peak = current_price * (1 + recent_gains * 2)  # Conservative projection
                    log_projection = projected_peak
        
        # Determine most likely peak range
        potential_targets = []
        
        if resistance_levels:
            potential_targets.extend(resistance_levels[:3])  # Top 3 resistance levels
        
        if fib_levels:
            potential_targets.extend([level for level in fib_levels.values() if level > current_price])
        
        if log_projection:
            potential_targets.append(log_projection)
        
        if potential_targets:
            potential_targets.sort()
            
            # Create range prediction
            if bubble_score >= 70:
                # Extreme bubble - expect higher targets
                target_range = {
                    'low': potential_targets[0] if potential_targets else current_price * 1.2,
                    'high': potential_targets[-1] if potential_targets else current_price * 2.0,
                    'most_likely': potential_targets[len(potential_targets)//2] if potential_targets else current_price * 1.5
                }
            elif bubble_score >= 50:
                # Moderate bubble
                target_range = {
                    'low': current_price * 1.1,
                    'high': potential_targets[0] if potential_targets else current_price * 1.5,
                    'most_likely': current_price * 1.25
                }
            else:
                # No significant bubble
                target_range = {
                    'low': current_price * 1.05,
                    'high': current_price * 1.2,
                    'most_likely': current_price * 1.1
                }
        else:
            # Fallback range when no clear targets
            multiplier = 1.5 if bubble_score >= 50 else 1.2
            target_range = {
                'low': current_price * 1.05,
                'high': current_price * multiplier,
                'most_likely': current_price * (1.05 + multiplier) / 2
            }
        
        return {
            'target_range': target_range,
            'resistance_levels': resistance_levels[:5],  # Top 5
            'fibonacci_extensions': fib_levels,
            'confidence': round(confidence),
            'timeframe_estimate': '2-8 weeks' if bubble_score >= 50 else '1-6 months'
        }
    
    def _predict_trough_price_levels(self, df: pd.DataFrame, crash_score: float) -> Dict:
        """Predict potential trough price levels with confidence indicators"""
        current_price = df['Close'].iloc[-1]
        
        if len(df) < 100:
            return {'prediction': 'Insufficient data', 'confidence': 0}
        
        # Historical support levels
        recent_lows = df['Low'].tail(365).nsmallest(10) if len(df) >= 365 else df['Low'].nsmallest(10)
        support_levels = []
        
        for low in recent_lows:
            if low < current_price * 0.95:  # At least 5% below current
                support_levels.append(low)
        
        # Major historical support (multi-year lows)
        if len(df) >= 730:  # 2+ years of data
            major_supports = df['Low'].tail(730).nsmallest(5)
            major_support_levels = [level for level in major_supports if level < current_price * 0.8]
        else:
            major_support_levels = []
        
        # Fibonacci retracements from recent major swing
        if len(df) >= 200:
            lookback = min(365, len(df))
            recent_data = df.tail(lookback)
            major_high = recent_data['High'].max()
            major_low = recent_data['Low'].min()
            
            fib_range = major_high - major_low
            fib_retracements = {
                '50%': major_high - (fib_range * 0.5),
                '61.8%': major_high - (fib_range * 0.618),
                '78.6%': major_high - (fib_range * 0.786),
                '88.6%': major_high - (fib_range * 0.886)
            }
        else:
            fib_retracements = {}
        
        # Confidence based on crash indicators
        confidence = 40  # Base confidence
        
        if crash_score >= 40:
            confidence = min(90, 40 + crash_score * 1.0)
        
        # Determine most likely trough range
        potential_targets = []
        
        if support_levels:
            potential_targets.extend(support_levels[:5])
        
        if major_support_levels:
            potential_targets.extend(major_support_levels[:3])
        
        if fib_retracements:
            potential_targets.extend([level for level in fib_retracements.values() if level < current_price])
        
        if potential_targets:
            potential_targets.sort(reverse=True)  # Highest to lowest
            
            if crash_score >= 60:
                # Extreme crash - expect lower targets
                target_range = {
                    'high': potential_targets[0] if potential_targets else current_price * 0.8,
                    'low': potential_targets[-1] if potential_targets else current_price * 0.5,
                    'most_likely': potential_targets[len(potential_targets)//2] if potential_targets else current_price * 0.65
                }
            elif crash_score >= 40:
                # Major crash
                target_range = {
                    'high': current_price * 0.9,
                    'low': potential_targets[-1] if potential_targets else current_price * 0.7,
                    'most_likely': current_price * 0.8
                }
            else:
                # Moderate decline
                target_range = {
                    'high': current_price * 0.95,
                    'low': current_price * 0.85,
                    'most_likely': current_price * 0.9
                }
        else:
            # Fallback when no clear support levels
            decline_factor = 0.7 if crash_score >= 40 else 0.85
            target_range = {
                'high': current_price * 0.95,
                'low': current_price * decline_factor,
                'most_likely': current_price * (0.95 + decline_factor) / 2
            }
        
        return {
            'target_range': target_range,
            'support_levels': support_levels[:5],
            'major_supports': major_support_levels[:3],
            'fibonacci_retracements': fib_retracements,
            'confidence': round(confidence),
            'timeframe_estimate': '2-12 weeks' if crash_score >= 40 else '1-6 months'
        }
    
    def _identify_resistance_levels(self, df: pd.DataFrame) -> List[float]:
        """Identify key resistance levels above current price"""
        current_price = df['Close'].iloc[-1]
        
        if len(df) < 50:
            return []
        
        # Find recent highs that could act as resistance
        lookback = min(365, len(df))
        recent_data = df.tail(lookback)
        
        # Get significant highs (local maxima)
        highs = []
        window = 10  # Look for highs over 10-day windows
        
        for i in range(window, len(recent_data) - window):
            if recent_data['High'].iloc[i] == recent_data['High'].iloc[i-window:i+window].max():
                high_price = recent_data['High'].iloc[i]
                if high_price > current_price * 1.02:  # At least 2% above current
                    highs.append(high_price)
        
        # Remove duplicates and sort
        unique_highs = list(set([round(h, 2) for h in highs]))
        unique_highs.sort()
        
        return unique_highs[:10]  # Return top 10
    
    def _identify_support_levels(self, df: pd.DataFrame) -> List[float]:
        """Identify key support levels below current price"""
        current_price = df['Close'].iloc[-1]
        
        if len(df) < 50:
            return []
        
        # Find recent lows that could act as support
        lookback = min(365, len(df))
        recent_data = df.tail(lookback)
        
        # Get significant lows (local minima)
        lows = []
        window = 10
        
        for i in range(window, len(recent_data) - window):
            if recent_data['Low'].iloc[i] == recent_data['Low'].iloc[i-window:i+window].min():
                low_price = recent_data['Low'].iloc[i]
                if low_price < current_price * 0.98:  # At least 2% below current
                    lows.append(low_price)
        
        # Remove duplicates and sort
        unique_lows = list(set([round(l, 2) for l in lows]))
        unique_lows.sort(reverse=True)
        
        return unique_lows[:10]
    
    def generate_metric_explanations(self, analysis: Dict) -> Dict:
        """
        Generate detailed explanations for each metric with actionable advice
        
        Args:
            analysis: Strategic analysis results
            
        Returns:
            Dict: Metric explanations with actionable advice
        """
        bubble = analysis['bubble_analysis']
        crash = analysis['crash_analysis']
        current_price = analysis['current_price']
        
        explanations = {}
        
        # 1. Bubble Risk Score Explanation
        bubble_score = bubble['bubble_score']
        if bubble_score >= 70:
            explanations['bubble_risk'] = {
                'meaning': f"EXTREME BUBBLE ({bubble_score:.0f}/100): Multiple parabolic indicators suggest market euphoria and unsustainable price levels.",
                'action': "LIQUIDATE 75-100% of crypto holdings to precious metals (gold/silver). This is a major selling opportunity.",
                'why': "Historical patterns show extreme bubble conditions precede 50-80% crashes within weeks/months.",
                'timeframe': "Act within days - bubble peaks are short-lived"
            }
        elif bubble_score >= 50:
            explanations['bubble_risk'] = {
                'meaning': f"BUBBLE FORMING ({bubble_score:.0f}/100): Early bubble indicators present - price acceleration and momentum extremes detected.",
                'action': "LIQUIDATE 25-50% of crypto holdings to precious metals. Prepare for larger liquidation if score increases.",
                'why': "Getting ahead of the crowd before euphoria peaks maximizes exit prices and reduces timing risk.",
                'timeframe': "Begin liquidation over 1-2 weeks, monitor for escalation"
            }
        elif bubble_score >= 30:
            explanations['bubble_risk'] = {
                'meaning': f"ELEVATED RISK ({bubble_score:.0f}/100): Some bubble characteristics emerging - market showing overextension signals.",
                'action': "PAUSE regular DCA purchases. Keep existing holdings but stop adding new money.",
                'why': "Avoiding new purchases near potential peaks prevents buying at the worst possible time.",
                'timeframe': "Stop DCA immediately, reassess weekly"
            }
        else:
            explanations['bubble_risk'] = {
                'meaning': f"LOW BUBBLE RISK ({bubble_score:.0f}/100): No significant bubble indicators. Market conditions appear sustainable.",
                'action': "Continue normal DCA strategy. No liquidation needed at current levels.",
                'why': "No compelling signals to exit positions. Normal market conditions support continued accumulation.",
                'timeframe': "Maintain current strategy, monitor monthly"
            }
        
        # 2. Opportunity Score Explanation
        crash_score = crash['crash_score']
        if crash_score >= 60:
            explanations['opportunity_score'] = {
                'meaning': f"EXTREME CRASH ({crash_score:.0f}/100): Severe oversold conditions with capitulation indicators suggest major bottom forming.",
                'action': f"INCREASE DCA to {crash['dca_multiplier']:.0f}x normal amount. Deploy extra cash reserves for bulk buying.",
                'why': "Extreme crashes create once-per-cycle accumulation opportunities with 200-500% upside potential.",
                'timeframe': "Act immediately - extreme lows don't last long"
            }
        elif crash_score >= 40:
            explanations['opportunity_score'] = {
                'meaning': f"MAJOR CRASH ({crash_score:.0f}/100): Significant decline with oversold readings suggests strong accumulation opportunity.",
                'action': f"INCREASE DCA to {crash['dca_multiplier']:.0f}x normal amount. Use this decline to build larger positions.",
                'why': "Major crashes typically offer 50-200% recovery potential as markets revert to fair value.",
                'timeframe': "Increase purchases over 2-4 weeks while conditions persist"
            }
        elif crash_score >= 25:
            explanations['opportunity_score'] = {
                'meaning': f"GOOD OPPORTUNITY ({crash_score:.0f}/100): Moderate oversold conditions present above-average buying opportunity.",
                'action': f"INCREASE DCA to {crash['dca_multiplier']:.0f}x normal amount. Good time to add to positions.",
                'why': "Moderate dips offer lower-risk entry points with better risk/reward than normal levels.",
                'timeframe': "Increase purchases for 1-2 weeks"
            }
        else:
            explanations['opportunity_score'] = {
                'meaning': f"NORMAL CONDITIONS ({crash_score:.0f}/100): No significant oversold conditions. Standard market environment.",
                'action': "Continue regular DCA amount. No special opportunity to exploit.",
                'why': "Normal conditions don't offer exceptional value. Stick to consistent accumulation strategy.",
                'timeframe': "Maintain regular schedule"
            }
        
        # 3. Current Price Context
        explanations['current_price'] = {
            'meaning': f"Current price of ${current_price:,.0f} represents the market's current valuation based on supply/demand.",
            'action': "Use this as baseline for measuring bubble/crash deviations and setting price targets.",
            'why': "Understanding current price relative to historical levels helps time major portfolio moves.",
            'context': "Price alone doesn't determine action - it's the bubble/crash scores that matter for DCA strategy"
        }
        
        # 4. Expected Price Levels (if available)
        if 'predicted_peak_range' in bubble and bubble['bubble_score'] >= 30:
            peak_pred = bubble['predicted_peak_range']
            if 'target_range' in peak_pred:
                target = peak_pred['target_range']
                upside = ((target['most_likely'] - current_price) / current_price) * 100
                confidence = peak_pred['confidence']
                
                explanations['liquidation_target'] = {
                    'meaning': f"Expected peak around ${target['most_likely']:,.0f} (+{upside:.0f}%) with {confidence}% confidence based on technical analysis.",
                    'action': f"Plan to liquidate holdings if price reaches ${target['low']:,.0f}-${target['high']:,.0f} range.",
                    'why': "Having predetermined exit levels removes emotion and ensures profit-taking near peaks.",
                    'strategy': "Set price alerts and prepare precious metals allocation in advance"
                }
        
        if 'predicted_trough_range' in crash and crash['crash_score'] >= 25:
            trough_pred = crash['predicted_trough_range']
            if 'target_range' in trough_pred:
                target = trough_pred['target_range']
                downside = ((current_price - target['most_likely']) / current_price) * 100
                confidence = trough_pred['confidence']
                
                explanations['accumulation_target'] = {
                    'meaning': f"Expected bottom around ${target['most_likely']:,.0f} (-{downside:.0f}%) with {confidence}% confidence based on support levels.",
                    'action': f"Plan major accumulation if price drops to ${target['low']:,.0f}-${target['high']:,.0f} range.",
                    'why': "Predetermined buying levels ensure you accumulate at the best possible prices during panic.",
                    'strategy': "Prepare extra cash reserves and set buy orders near target levels"
                }
        
        return explanations