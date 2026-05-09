"""
Rotation Recommendation Engine for Crypto-to-Precious-Metals Rotations

Provides game-theory-optimal rotation recommendations with:
- Signal strength scoring (-5 to +5 scale)
- Confidence level assessment (Low/Medium/High/Very High)
- Optimal rotation percentage (0-75%)

Uses multi-indicator convergence analysis based on:
- Percentile positioning (40% weight)
- RSI divergence (30% weight)
- MA crossover signals (20% weight)
- Bollinger Band position (10% weight)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


class RotationRecommendationEngine:
    """Calculate rotation recommendations for crypto-to-precious-metals strategy"""
    
    def __init__(self):
        # Indicator weights for signal calculation
        self.weights = {
            'percentile': 0.40,
            'rsi': 0.30,
            'ma_crossover': 0.20,
            'bollinger': 0.10
        }
        
    def calculate_recommendation(
        self,
        ratio_data: pd.DataFrame,
        percentile: float,
        rsi: float,
        current_ratio: float
    ) -> Dict:
        """
        Calculate complete rotation recommendation
        
        Args:
            ratio_data: DataFrame with ratio, MA50, MA200, BB_upper, BB_lower
            percentile: Current percentile (0-100)
            rsi: Current RSI value
            current_ratio: Current crypto/metal ratio
            
        Returns:
            Dict with signal_score, confidence, rotation_pct, recommendation
        """
        # Calculate individual indicator signals
        percentile_signal = self._calculate_percentile_signal(percentile)
        rsi_signal = self._calculate_rsi_signal(rsi)
        ma_signal = self._calculate_ma_signal(ratio_data)
        bb_signal = self._calculate_bollinger_signal(ratio_data, current_ratio)
        
        # Weighted signal score (-5 to +5 scale)
        signal_score = (
            percentile_signal * self.weights['percentile'] +
            rsi_signal * self.weights['rsi'] +
            ma_signal * self.weights['ma_crossover'] +
            bb_signal * self.weights['bollinger']
        )
        
        # Calculate indicator convergence for confidence
        signals = [percentile_signal, rsi_signal, ma_signal, bb_signal]
        confidence = self._calculate_confidence(signals)
        
        # Game-theory optimal rotation percentage
        rotation_pct = self._calculate_rotation_percentage(
            signal_score, percentile, confidence
        )
        
        # Generate recommendation text
        recommendation = self._generate_recommendation(signal_score, rotation_pct)
        
        return {
            'signal_score': round(signal_score, 2),
            'confidence': confidence,
            'rotation_pct': round(rotation_pct, 1),
            'recommendation': recommendation,
            'indicators': {
                'percentile_signal': round(percentile_signal, 2),
                'rsi_signal': round(rsi_signal, 2),
                'ma_signal': round(ma_signal, 2),
                'bb_signal': round(bb_signal, 2)
            }
        }
    
    def _calculate_percentile_signal(self, percentile: float) -> float:
        """
        Calculate signal from percentile position
        
        Returns:
            Signal from -5 (extreme low) to +5 (extreme high)
        """
        if percentile >= 95:
            return 5.0
        elif percentile >= 90:
            return 4.0 + (percentile - 90) / 5.0
        elif percentile >= 85:
            return 3.0 + (percentile - 85) / 5.0
        elif percentile >= 70:
            return 1.0 + (percentile - 70) / 7.5
        elif percentile >= 50:
            return (percentile - 50) / 20.0
        elif percentile >= 30:
            return -1.0 + (percentile - 30) / 20.0
        elif percentile >= 15:
            return -2.0 + (percentile - 15) / 15.0
        elif percentile >= 10:
            return -3.0 + (percentile - 10) / 5.0
        elif percentile >= 5:
            return -4.0 + (percentile - 5) / 5.0
        else:
            return -5.0
    
    def _calculate_rsi_signal(self, rsi: float) -> float:
        """
        Calculate signal from RSI
        
        Returns:
            Signal from -5 (oversold) to +5 (overbought)
        """
        if rsi >= 80:
            return 5.0
        elif rsi >= 70:
            return 3.0 + (rsi - 70) / 5.0
        elif rsi >= 60:
            return 1.0 + (rsi - 60) / 5.0
        elif rsi >= 50:
            return (rsi - 50) / 10.0
        elif rsi >= 40:
            return -1.0 + (rsi - 40) / 10.0
        elif rsi >= 30:
            return -3.0 + (rsi - 30) / 5.0
        elif rsi >= 20:
            return -4.0 + (rsi - 20) / 10.0
        else:
            return -5.0
    
    def _calculate_ma_signal(self, ratio_data: pd.DataFrame) -> float:
        """
        Calculate signal from MA crossover
        
        Returns:
            Signal based on MA50 vs MA200 position
        """
        if len(ratio_data) < 200:
            return 0.0
        
        # Get latest values
        current_ratio = ratio_data['ratio'].iloc[-1]
        ma50 = ratio_data['MA50'].iloc[-1]
        ma200 = ratio_data['MA200'].iloc[-1]
        
        # Calculate position relative to MAs
        if pd.isna(ma50) or pd.isna(ma200):
            return 0.0
        
        # Strong signals when price crosses MAs
        if current_ratio > ma50 > ma200:
            # Bullish configuration (higher ratios = rotate to metal)
            distance_pct = ((current_ratio - ma50) / ma50) * 100
            return min(5.0, max(2.0, 2.0 + distance_pct / 2))
        elif current_ratio < ma50 < ma200:
            # Bearish configuration (lower ratios = hold crypto)
            distance_pct = ((ma50 - current_ratio) / ma50) * 100
            return max(-5.0, min(-2.0, -2.0 - distance_pct / 2))
        elif ma50 > ma200:
            # Golden cross (bullish for ratio)
            return 1.0
        else:
            # Death cross (bearish for ratio)
            return -1.0
    
    def _calculate_bollinger_signal(
        self,
        ratio_data: pd.DataFrame,
        current_ratio: float
    ) -> float:
        """
        Calculate signal from Bollinger Band position
        
        Returns:
            Signal from -5 (below lower band) to +5 (above upper band)
        """
        if len(ratio_data) < 50:
            return 0.0
        
        bb_upper = ratio_data['BB_upper'].iloc[-1]
        bb_lower = ratio_data['BB_lower'].iloc[-1]
        ma50 = ratio_data['MA50'].iloc[-1]
        
        if pd.isna(bb_upper) or pd.isna(bb_lower) or pd.isna(ma50):
            return 0.0
        
        # Calculate position within bands
        band_width = bb_upper - bb_lower
        if band_width == 0:
            return 0.0
        
        if current_ratio > bb_upper:
            # Above upper band - strong rotation signal
            distance = (current_ratio - bb_upper) / band_width
            return min(5.0, 4.0 + distance)
        elif current_ratio < bb_lower:
            # Below lower band - strong hold crypto signal
            distance = (bb_lower - current_ratio) / band_width
            return max(-5.0, -4.0 - distance)
        else:
            # Within bands - interpolate between -2 and +2
            position = (current_ratio - bb_lower) / band_width  # 0 to 1
            return -2.0 + (position * 4.0)
    
    def _calculate_confidence(self, signals: list) -> str:
        """
        Calculate confidence level based on indicator convergence
        
        Args:
            signals: List of individual indicator signals
            
        Returns:
            'Very High', 'High', 'Medium', or 'Low'
        """
        # Determine if signals are bullish (>1), neutral (-1 to 1), or bearish (<-1)
        classifications = []
        for sig in signals:
            if sig > 1.0:
                classifications.append('bullish')
            elif sig < -1.0:
                classifications.append('bearish')
            else:
                classifications.append('neutral')
        
        # Count convergence
        bullish_count = classifications.count('bullish')
        bearish_count = classifications.count('bearish')
        
        # All 4 indicators agree
        if bullish_count == 4 or bearish_count == 4:
            return 'Very High'
        # 3 indicators agree
        elif bullish_count >= 3 or bearish_count >= 3:
            return 'High'
        # 2 indicators agree
        elif bullish_count >= 2 or bearish_count >= 2:
            return 'Medium'
        # Little to no agreement
        else:
            return 'Low'
    
    def _calculate_rotation_percentage(
        self,
        signal_score: float,
        percentile: float,
        confidence: str
    ) -> float:
        """
        Calculate game-theory-optimal rotation percentage
        
        Uses Kelly-inspired formula with volatility adjustment
        
        Args:
            signal_score: Overall signal (-5 to +5)
            percentile: Current percentile (0-100)
            confidence: Confidence level
            
        Returns:
            Rotation percentage (0-75%)
        """
        # Only rotate on positive signals (crypto overvalued)
        if signal_score <= 0:
            return 0.0
        
        # Base edge from signal strength (0 to 1)
        edge = signal_score / 5.0
        
        # Percentile strength (how extreme is the overvaluation)
        if percentile >= 85:
            percentile_strength = min(1.0, (percentile - 85) / 15)
        else:
            percentile_strength = 0.0
        
        # Confidence multiplier
        confidence_multipliers = {
            'Very High': 1.0,
            'High': 0.8,
            'Medium': 0.6,
            'Low': 0.4
        }
        conf_mult = confidence_multipliers.get(confidence, 0.5)
        
        # Kelly-inspired formula: rotation% = edge × percentile_strength × confidence
        rotation_base = edge * percentile_strength * conf_mult * 100
        
        # Cap at 75% maximum (never rotate entire portfolio)
        rotation_pct = min(75.0, rotation_base)
        
        # Minimum threshold - only recommend if >10%
        if rotation_pct < 10.0:
            return 0.0
        
        return rotation_pct
    
    def _generate_recommendation(
        self,
        signal_score: float,
        rotation_pct: float
    ) -> str:
        """
        Generate human-readable recommendation
        
        Args:
            signal_score: Overall signal (-5 to +5)
            rotation_pct: Calculated rotation percentage
            
        Returns:
            Recommendation text
        """
        if rotation_pct == 0:
            if signal_score < -2:
                return "STRONG HOLD - Crypto significantly undervalued"
            elif signal_score < 0:
                return "HOLD CRYPTO - Market below fair value"
            else:
                return "HOLD CRYPTO - Rotation threshold not met"
        elif rotation_pct < 25:
            return f"CONSIDER ROTATION - {int(rotation_pct)}% to precious metal"
        elif rotation_pct < 50:
            return f"PARTIAL ROTATION - {int(rotation_pct)}% to precious metal"
        else:
            return f"STRONG ROTATION - {int(rotation_pct)}% to precious metal"
