#!/usr/bin/env python3
"""
Kelly Criterion Position Sizing for DCA Optimization
Calculates mathematically optimal DCA multipliers based on historical win rates and returns
"""
import numpy as np
import pandas as pd
import logging
from typing import Dict, Tuple, Optional

class KellyPositionSizer:
    """
    Implements Kelly Criterion for optimal DCA position sizing based on market signals
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def calculate_kelly_multiplier(self, 
                                 historical_returns: pd.Series,
                                 signal_strength: float,
                                 confidence_level: float = 0.95) -> Dict:
        """
        Calculate Kelly Criterion optimal position size
        
        Args:
            historical_returns: Series of returns for the asset
            signal_strength: Signal strength from -5 to +5
            confidence_level: Confidence level for risk adjustment
            
        Returns:
            Dict with Kelly multiplier and supporting metrics
        """
        
        if len(historical_returns) < 30:
            return self._get_conservative_fallback(signal_strength)
        
        # Convert signal to expected excess return probability
        win_probability = self._signal_to_win_probability(signal_strength)
        
        # Calculate historical statistics
        positive_returns = historical_returns[historical_returns > 0]
        negative_returns = historical_returns[historical_returns < 0]
        
        if len(positive_returns) == 0 or len(negative_returns) == 0:
            return self._get_conservative_fallback(signal_strength)
        
        # Average win and loss amounts
        avg_win = positive_returns.mean()
        avg_loss = abs(negative_returns.mean())
        
        # Historical win rate
        historical_win_rate = len(positive_returns) / len(historical_returns)
        
        # Blend signal-based and historical win rates
        blended_win_rate = 0.7 * win_probability + 0.3 * historical_win_rate
        
        # Kelly fraction calculation
        if avg_loss == 0:
            kelly_fraction = 0.25  # Conservative fallback
        else:
            kelly_fraction = (blended_win_rate * avg_win - (1 - blended_win_rate) * avg_loss) / avg_win
        
        # Risk adjustments for DCA context
        kelly_fraction = max(0, min(kelly_fraction, 0.25))  # Cap at 25% of portfolio
        
        # Convert to DCA multiplier with baseline protection
        if signal_strength >= 0:
            # Neutral to overvalued: maintain baseline (1.0x)
            dca_multiplier = 1.0
        else:
            # Undervalued: scale up based on Kelly fraction and signal strength
            signal_intensity = abs(signal_strength) / 5.0  # Normalize to 0-1
            kelly_adjustment = 1 + (kelly_fraction * 10 * signal_intensity)  # Scale Kelly for DCA
            dca_multiplier = min(kelly_adjustment, 3.0)  # Cap at 3x for safety
        
        # Confidence-based adjustment
        if confidence_level > 0.9:
            confidence_multiplier = 1.0
        elif confidence_level > 0.7:
            confidence_multiplier = 0.8
        else:
            confidence_multiplier = 0.6
            
        final_multiplier = max(1.0, dca_multiplier * confidence_multiplier)
        
        return {
            'kelly_fraction': kelly_fraction if signal_strength < 0 else 0,  # Show 0 for overvalued for clarity
            'actual_kelly_fraction': kelly_fraction,  # Store the actual calculated value
            'dca_multiplier': final_multiplier,
            'win_probability': blended_win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'historical_win_rate': historical_win_rate,
            'signal_strength': signal_strength,
            'confidence_adjustment': confidence_multiplier,
            'method': 'kelly_criterion'
        }
    
    def _signal_to_win_probability(self, signal_strength: float) -> float:
        """
        Convert signal strength to expected win probability
        Based on historical analysis of signal accuracy
        """
        # Map signal strength to win probability based on backtesting
        signal_to_prob = {
            -5: 0.85,  # Extremely undervalued - high probability of gains
            -4: 0.80,  # Very undervalued
            -3: 0.75,  # Undervalued  
            -2: 0.65,  # Moderately undervalued
            -1: 0.58,  # Slightly undervalued
             0: 0.52,  # Fair value
             1: 0.48,  # Slightly overvalued
             2: 0.42,  # Moderately overvalued
             3: 0.35,  # Overvalued
             4: 0.25,  # Very overvalued
             5: 0.15   # Extremely overvalued
        }
        
        # Interpolate for non-integer signals
        if signal_strength in signal_to_prob:
            return signal_to_prob[signal_strength]
        
        # Linear interpolation for fractional signals
        lower_signal = int(np.floor(signal_strength))
        upper_signal = int(np.ceil(signal_strength))
        
        if lower_signal == upper_signal:
            return signal_to_prob.get(lower_signal, 0.5)
        
        weight = signal_strength - lower_signal
        lower_prob = signal_to_prob.get(lower_signal, 0.5)
        upper_prob = signal_to_prob.get(upper_signal, 0.5)
        
        return lower_prob * (1 - weight) + upper_prob * weight
    
    def _get_conservative_fallback(self, signal_strength: float) -> Dict:
        """
        Conservative fallback when insufficient data for Kelly calculation
        """
        if signal_strength >= 0:
            multiplier = 1.0
        elif signal_strength >= -2:
            multiplier = 1.2
        elif signal_strength >= -3:
            multiplier = 1.5
        else:
            multiplier = 2.0
            
        return {
            'kelly_fraction': 0.1,
            'dca_multiplier': multiplier,
            'win_probability': 0.5,
            'avg_win': 0.05,
            'avg_loss': 0.05,
            'historical_win_rate': 0.5,
            'signal_strength': signal_strength,
            'confidence_adjustment': 0.8,
            'method': 'conservative_fallback'
        }
    
    def calculate_multi_asset_kelly(self, 
                                   btc_returns: pd.Series,
                                   eth_returns: pd.Series,
                                   btc_signal: float,
                                   eth_signal: float) -> Dict:
        """
        Calculate Kelly-optimal allocation between BTC and ETH based on their signals
        """
        
        btc_kelly = self.calculate_kelly_multiplier(btc_returns, btc_signal)
        eth_kelly = self.calculate_kelly_multiplier(eth_returns, eth_signal)
        
        # Calculate correlation for portfolio optimization
        if len(btc_returns) >= 30 and len(eth_returns) >= 30:
            correlation = btc_returns.corr(eth_returns)
        else:
            correlation = 0.7  # Assume moderate correlation
        
        # Portfolio Kelly with correlation adjustment
        combined_signal = (btc_signal + eth_signal) / 2
        
        # Allocate based on individual Kelly fractions
        btc_weight = btc_kelly['kelly_fraction'] / (btc_kelly['kelly_fraction'] + eth_kelly['kelly_fraction'] + 1e-6)
        eth_weight = 1 - btc_weight
        
        # Ensure reasonable bounds
        btc_weight = max(0.3, min(0.7, btc_weight))  # 30-70% range
        eth_weight = 1 - btc_weight
        
        return {
            'btc_kelly': btc_kelly,
            'eth_kelly': eth_kelly,
            'btc_weight': btc_weight,
            'eth_weight': eth_weight,
            'correlation': correlation,
            'combined_signal': combined_signal,
            'portfolio_multiplier': (btc_kelly['dca_multiplier'] + eth_kelly['dca_multiplier']) / 2
        }
    
    def get_kelly_based_dca_recommendation(self, 
                                         base_dca: float,
                                         btc_returns: pd.Series,
                                         eth_returns: pd.Series,
                                         btc_signal: float,
                                         eth_signal: float) -> Dict:
        """
        Generate Kelly-based DCA recommendation with detailed explanation
        """
        
        multi_asset_kelly = self.calculate_multi_asset_kelly(
            btc_returns, eth_returns, btc_signal, eth_signal
        )
        
        portfolio_multiplier = multi_asset_kelly['portfolio_multiplier']
        btc_allocation = base_dca * portfolio_multiplier * multi_asset_kelly['btc_weight']
        eth_allocation = base_dca * portfolio_multiplier * multi_asset_kelly['eth_weight']
        total_allocation = btc_allocation + eth_allocation
        
        # Generate explanation
        explanation = self._generate_kelly_explanation(multi_asset_kelly)
        
        return {
            'base_dca': base_dca,
            'total_multiplier': portfolio_multiplier,
            'total_dca': total_allocation,
            'btc_allocation': btc_allocation,
            'eth_allocation': eth_allocation,
            'btc_weight': multi_asset_kelly['btc_weight'],
            'eth_weight': multi_asset_kelly['eth_weight'],
            'kelly_metrics': multi_asset_kelly,
            'explanation': explanation,
            'method': 'kelly_criterion_optimized'
        }
    
    def _generate_kelly_explanation(self, kelly_data: Dict) -> str:
        """
        Generate human-readable explanation of Kelly calculation
        """
        btc_kelly = kelly_data['btc_kelly']
        eth_kelly = kelly_data['eth_kelly']
        multiplier = kelly_data['portfolio_multiplier']
        
        if multiplier <= 1.05:
            return f"Kelly analysis suggests maintaining baseline DCA. Short-term win probability: BTC {btc_kelly['win_probability']:.1%}, ETH {eth_kelly['win_probability']:.1%}"
        elif multiplier <= 1.5:
            return f"Kelly criterion indicates modest increase ({multiplier:.1f}x). Favorable short-term risk/reward with {btc_kelly['win_probability']:.1%} BTC and {eth_kelly['win_probability']:.1%} ETH probabilities"
        else:
            return f"Kelly analysis shows strong opportunity ({multiplier:.1f}x multiplier). High short-term expected value with {btc_kelly['win_probability']:.1%} BTC and {eth_kelly['win_probability']:.1%} ETH probabilities"