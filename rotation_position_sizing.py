"""
Advanced Position Sizing for Crypto → Gold Rotation Strategy
Calculates optimal rotation percentages based on statistical extremes and risk management
"""

import pandas as pd
import numpy as np
from datetime import datetime
import logging

class RotationPositionSizing:
    """
    Advanced position sizing engine for crypto-gold rotation strategy.
    Uses mathematical models to determine optimal rotation percentages.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def calculate_rotation_percentages(self, btc_percentile, eth_percentile, 
                                     btc_signal=None, eth_signal=None,
                                     current_crypto_allocation=60,
                                     risk_tolerance='moderate'):
        """
        Calculate optimal rotation percentages based on market extremes
        
        Args:
            btc_percentile: Current BTC/Gold percentile (0-100)
            eth_percentile: Current ETH/Gold percentile (0-100)
            btc_signal: BTC valuation signal (-5 to +5)
            eth_signal: ETH valuation signal (-5 to +5)
            current_crypto_allocation: Current crypto allocation % (0-100)
            risk_tolerance: 'conservative', 'moderate', 'aggressive'
        
        Returns:
            dict with rotation recommendations
        """
        
        # Calculate combined market extreme score
        avg_percentile = (btc_percentile + eth_percentile) / 2
        max_percentile = max(btc_percentile, eth_percentile)
        
        # Extreme detection with confidence weighting
        extreme_score = self._calculate_extreme_score(btc_percentile, eth_percentile, 
                                                     btc_signal, eth_signal)
        
        # === ROTATION TO GOLD (CRYPTO → GOLD) ===
        if avg_percentile >= 85:  # Top zone
            rotation_to_gold = self._calculate_sell_percentage(
                avg_percentile, max_percentile, extreme_score, 
                current_crypto_allocation, risk_tolerance
            )
            
            return {
                'action': 'ROTATE_TO_GOLD',
                'crypto_to_sell_percentage': rotation_to_gold['sell_percentage'],
                'target_crypto_allocation': rotation_to_gold['new_crypto_allocation'],
                'target_gold_allocation': rotation_to_gold['new_gold_allocation'],
                'confidence_level': rotation_to_gold['confidence'],
                'reasoning': rotation_to_gold['reasoning'],
                'execution_timeline': rotation_to_gold['timeline'],
                'risk_management': rotation_to_gold['risk_notes']
            }
            
        # === ROTATION TO CRYPTO (GOLD → CRYPTO) ===
        elif avg_percentile <= 15:  # Bottom zone
            rotation_to_crypto = self._calculate_buy_percentage(
                avg_percentile, max_percentile, extreme_score,
                current_crypto_allocation, risk_tolerance
            )
            
            return {
                'action': 'ROTATE_TO_CRYPTO',
                'gold_to_sell_percentage': rotation_to_crypto['sell_percentage'],
                'target_crypto_allocation': rotation_to_crypto['new_crypto_allocation'],
                'target_gold_allocation': rotation_to_crypto['new_gold_allocation'],
                'confidence_level': rotation_to_crypto['confidence'],
                'reasoning': rotation_to_crypto['reasoning'],
                'execution_timeline': rotation_to_crypto['timeline'],
                'risk_management': rotation_to_crypto['risk_notes']
            }
            
        # === HOLD POSITION ===
        else:
            return {
                'action': 'HOLD',
                'crypto_to_sell_percentage': 0,
                'gold_to_sell_percentage': 0,
                'target_crypto_allocation': current_crypto_allocation,
                'target_gold_allocation': 100 - current_crypto_allocation,
                'confidence_level': 'medium',
                'reasoning': f'Market in neutral zone ({avg_percentile:.1f}th percentile). Maintain current allocation.',
                'execution_timeline': 'No action required',
                'risk_management': 'Continue regular DCA schedule'
            }
    
    def _calculate_extreme_score(self, btc_percentile, eth_percentile, btc_signal, eth_signal):
        """Calculate weighted extreme score (0-10 scale)"""
        
        # Percentile-based score (0-5)
        percentile_score = 0
        avg_percentile = (btc_percentile + eth_percentile) / 2
        
        if avg_percentile >= 98:
            percentile_score = 5.0  # Extreme top
        elif avg_percentile >= 95:
            percentile_score = 4.5
        elif avg_percentile >= 90:
            percentile_score = 4.0
        elif avg_percentile >= 85:
            percentile_score = 3.5
        elif avg_percentile <= 2:
            percentile_score = 5.0  # Extreme bottom
        elif avg_percentile <= 5:
            percentile_score = 4.5
        elif avg_percentile <= 10:
            percentile_score = 4.0
        elif avg_percentile <= 15:
            percentile_score = 3.5
        else:
            percentile_score = 0
        
        # Signal-based score (0-5)
        signal_score = 0
        if btc_signal is not None and eth_signal is not None:
            avg_signal = abs((btc_signal + eth_signal) / 2)
            signal_score = min(avg_signal, 5.0)
        
        return min(percentile_score + signal_score, 10.0)
    
    def _calculate_sell_percentage(self, avg_percentile, max_percentile, extreme_score,
                                 current_crypto_allocation, risk_tolerance):
        """Calculate what percentage of crypto to sell for gold"""
        
        # Base sell percentage based on extremes
        base_sell_pct = 0
        
        if max_percentile >= 98:  # Ultra-extreme (top 2%)
            base_sell_pct = 80  # Sell 80% of crypto position
        elif max_percentile >= 95:  # Extreme top (top 5%)  
            base_sell_pct = 65  # Sell 65% of crypto position
        elif max_percentile >= 90:  # Very high (top 10%)
            base_sell_pct = 50  # Sell 50% of crypto position
        elif avg_percentile >= 85:  # High (top 15%)
            base_sell_pct = 35  # Sell 35% of crypto position
        
        # Risk tolerance adjustments
        risk_multipliers = {
            'conservative': 1.2,  # Sell more aggressively
            'moderate': 1.0,      # Standard selling
            'aggressive': 0.8     # Hold more crypto
        }
        
        adjusted_sell_pct = base_sell_pct * risk_multipliers.get(risk_tolerance, 1.0)
        adjusted_sell_pct = min(adjusted_sell_pct, 85)  # Never sell more than 85%
        
        # Calculate new allocations
        crypto_to_sell = (current_crypto_allocation * adjusted_sell_pct) / 100
        new_crypto_allocation = current_crypto_allocation - crypto_to_sell
        new_gold_allocation = 100 - new_crypto_allocation
        
        # Confidence and reasoning
        if max_percentile >= 95:
            confidence = 'high'
            reasoning = f'EXTREME OVERVALUATION: {max_percentile:.1f}th percentile indicates crypto extremely overvalued vs gold. Mathematical opportunity to lock in gains.'
            timeline = 'Execute over 1-2 weeks to avoid timing risk'
            risk_notes = 'Dollar-cost-average the sale over multiple days'
        else:
            confidence = 'medium'
            reasoning = f'OVERVALUATION: {avg_percentile:.1f}th percentile suggests reducing crypto exposure to rebalance portfolio.'
            timeline = 'Execute over 2-4 weeks'
            risk_notes = 'Partial rotation to reduce risk while maintaining upside exposure'
        
        return {
            'sell_percentage': round(adjusted_sell_pct, 1),
            'new_crypto_allocation': round(new_crypto_allocation, 1),
            'new_gold_allocation': round(new_gold_allocation, 1),
            'confidence': confidence,
            'reasoning': reasoning,
            'timeline': timeline,
            'risk_notes': risk_notes
        }
    
    def _calculate_buy_percentage(self, avg_percentile, min_percentile, extreme_score,
                                current_crypto_allocation, risk_tolerance):
        """Calculate what percentage of gold to sell for crypto"""
        
        min_percentile = min(avg_percentile, min_percentile) if hasattr(self, 'min_percentile') else avg_percentile
        
        # Base buy percentage based on extremes
        base_buy_pct = 0
        
        if min_percentile <= 2:   # Ultra-extreme (bottom 2%)
            base_buy_pct = 90     # Sell 90% of gold position
        elif min_percentile <= 5:   # Extreme bottom (bottom 5%)
            base_buy_pct = 75     # Sell 75% of gold position  
        elif min_percentile <= 10:  # Very low (bottom 10%)
            base_buy_pct = 60     # Sell 60% of gold position
        elif avg_percentile <= 15:  # Low (bottom 15%) 
            base_buy_pct = 45     # Sell 45% of gold position
        
        # Risk tolerance adjustments
        risk_multipliers = {
            'conservative': 0.8,  # Buy less aggressively
            'moderate': 1.0,      # Standard buying
            'aggressive': 1.3     # Buy more aggressively
        }
        
        adjusted_buy_pct = base_buy_pct * risk_multipliers.get(risk_tolerance, 1.0)
        adjusted_buy_pct = min(adjusted_buy_pct, 95)  # Never sell more than 95% of gold
        
        # Calculate new allocations
        current_gold_allocation = 100 - current_crypto_allocation
        gold_to_sell = (current_gold_allocation * adjusted_buy_pct) / 100
        new_gold_allocation = current_gold_allocation - gold_to_sell
        new_crypto_allocation = current_crypto_allocation + gold_to_sell
        
        # Ensure allocations don't exceed 100%
        if new_crypto_allocation > 95:
            new_crypto_allocation = 95
            new_gold_allocation = 5
            adjusted_buy_pct = ((95 - current_crypto_allocation) / current_gold_allocation) * 100
        
        # Confidence and reasoning
        if min_percentile <= 5:
            confidence = 'high' 
            reasoning = f'EXTREME UNDERVALUATION: {min_percentile:.1f}th percentile indicates crypto extremely undervalued vs gold. Mathematical opportunity for aggressive accumulation.'
            timeline = 'Execute immediately over 1-2 weeks to capture bottom'
            risk_notes = 'Maximum aggression warranted - historical opportunity'
        else:
            confidence = 'medium'
            reasoning = f'UNDERVALUATION: {avg_percentile:.1f}th percentile suggests increasing crypto exposure for better risk-adjusted returns.'
            timeline = 'Execute over 2-4 weeks'
            risk_notes = 'Gradual rotation to capture mean reversion opportunity'
        
        return {
            'sell_percentage': round(adjusted_buy_pct, 1),
            'new_crypto_allocation': round(new_crypto_allocation, 1), 
            'new_gold_allocation': round(new_gold_allocation, 1),
            'confidence': confidence,
            'reasoning': reasoning,
            'timeline': timeline,
            'risk_notes': risk_notes
        }
    
    def calculate_dca_adjustment(self, rotation_recommendation, weekly_dca_base=555):
        """
        Calculate adjusted DCA amounts based on rotation signals
        
        Args:
            rotation_recommendation: Output from calculate_rotation_percentages
            weekly_dca_base: Base weekly DCA amount
            
        Returns:
            dict with adjusted DCA recommendations
        """
        
        action = rotation_recommendation['action']
        confidence = rotation_recommendation['confidence_level']
        
        # DCA multipliers based on rotation signals
        if action == 'ROTATE_TO_CRYPTO':
            # Increase DCA during extreme bottoms
            if confidence == 'high':
                dca_multiplier = 3.0  # 3x aggressive DCA
                dca_reasoning = 'EXTREME BOTTOM: Triple DCA to maximize accumulation'
            else:
                dca_multiplier = 2.0  # 2x moderate increase
                dca_reasoning = 'UNDERVALUATION: Double DCA to capture opportunity'
                
        elif action == 'ROTATE_TO_GOLD':
            # Reduce/pause DCA during extreme tops
            if confidence == 'high':
                dca_multiplier = 0.2  # Minimal DCA (maintenance only)
                dca_reasoning = 'EXTREME TOP: Minimal DCA, focus on gold rotation'
            else:
                dca_multiplier = 0.5  # Reduced DCA
                dca_reasoning = 'OVERVALUATION: Reduced DCA, partial rotation'
                
        else:  # HOLD
            dca_multiplier = 1.0  # Normal DCA
            dca_reasoning = 'NEUTRAL MARKET: Continue normal DCA schedule'
        
        adjusted_dca = weekly_dca_base * dca_multiplier
        
        return {
            'weekly_dca_amount': round(adjusted_dca, 2),
            'dca_multiplier': dca_multiplier,
            'dca_reasoning': dca_reasoning,
            'minimum_dca_floor': max(weekly_dca_base * 0.2, 111)  # Never below $111/week
        }