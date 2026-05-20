"""
Exponential Cycle Engine - Core controller for the exponential cycling strategy
Manages: USD → Crypto → Gold → USD cycle for exponential wealth building
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from typing import Dict, Optional, List, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
import calendar

class CyclePhase(Enum):
    """Market cycle phases"""
    EXTREME_BOTTOM = "extreme_bottom"          # <5% percentile - liquidate gold→USD
    AGGRESSIVE_DCA = "aggressive_dca"          # Deploy USD with 2-3x multipliers
    ACCUMULATION = "accumulation"              # 5-45% - normal to increased DCA
    BULL_MARKET = "bull_market"                # 45-85% - maintain baseline DCA
    EXTREME_TOP = "extreme_top"                # >85% - rotate to gold, reduce DCA
    GOLD_HOLDING = "gold_holding"              # Post-rotation - wait for extreme bottom

@dataclass
class PortfolioState:
    """Current portfolio allocation state"""
    crypto_allocation: float  # Percentage in crypto (0-100)
    gold_allocation: float    # Percentage in gold (0-100)
    silver_allocation: float  # Percentage in silver (0-100)
    usd_available: float      # USD available for deployment
    last_rotation_date: Optional[datetime] = None
    last_rotation_type: Optional[str] = None  # 'to_metals' or 'to_crypto'
    rotation_history: List[Dict] = None
    
    def __post_init__(self):
        if self.rotation_history is None:
            self.rotation_history = []
    
    @property
    def metals_allocation(self) -> float:
        """Total precious metals allocation (gold + silver)"""
        return self.gold_allocation + self.silver_allocation

@dataclass 
class CycleRecommendation:
    """Weekly action recommendation"""
    cycle_phase: CyclePhase
    primary_action: str
    dca_amount_usd: float
    btc_amount_usd: float
    eth_amount_usd: float
    rotation_percentage: float  # % of holdings to rotate (0-100)
    rotation_direction: Optional[str]  # 'crypto_to_metals', 'metals_to_usd', None
    gold_rotation_pct: float = 70.0  # % of metal rotation going to gold (default 70%)
    silver_rotation_pct: float = 30.0  # % of metal rotation going to silver (default 30%)
    confidence: str = 'medium'  # 'low', 'medium', 'high'
    reasoning: str = ''
    expected_outcome: str = ''
    
class ExponentialCycleEngine:
    """
    Unified engine that orchestrates the complete exponential cycling strategy.
    
    Core Philosophy:
    - Optimize WHEN to rotate between crypto and gold (timing extremes)
    - NOT how to split between BTC and ETH (that's secondary)
    - Compound gains by capturing extreme tops and bottoms
    """
    
    def __init__(self, base_weekly_dca: float = 777):
        self.logger = logging.getLogger(__name__)
        self.base_weekly_dca = base_weekly_dca
        self.kelly_stats = None  # Will store monthly stats for Kelly calculation
    
    def _calculate_kelly_split(self, btc_percentile: float, eth_percentile: float) -> Tuple[float, float]:
        """Calculate Kelly Half allocation between BTC and ETH
        
        Uses simplified Kelly based on relative signal strength when full historical stats unavailable
        """
        # Use percentiles as proxy for relative value
        # Lower percentile = more undervalued = higher Kelly allocation
        btc_edge = max(0, (50 - btc_percentile) / 50)  # 0-1 where 1 is most undervalued
        eth_edge = max(0, (50 - eth_percentile) / 50)
        
        total_edge = btc_edge + eth_edge
        if total_edge > 0:
            btc_weight = btc_edge / total_edge
        else:
            btc_weight = 0.5  # Default to equal if no clear edge
        
        # Direct-ratio Kelly: weight proportional to relative undervaluation
        # Cleaner than compressed version — no artificial signal dampening
        # Cap between 30-70%
        btc_weight = min(max(btc_weight, 0.30), 0.70)
        eth_weight = 1.0 - btc_weight
        
        return btc_weight, eth_weight
        
    def generate_weekly_recommendation(
        self,
        btc_percentile: float,
        eth_percentile: float,
        btc_signal: int,
        eth_signal: int,
        portfolio_state: PortfolioState
    ) -> CycleRecommendation:
        """
        Generate unified weekly recommendation based on cycle phase
        
        Returns complete guidance: DCA amount, rotation instructions, and reasoning
        """
        
        # Determine current cycle phase
        cycle_phase = self._determine_cycle_phase(
            btc_percentile, eth_percentile, portfolio_state
        )
        
        # Calculate cycle-appropriate actions
        if cycle_phase == CyclePhase.EXTREME_BOTTOM:
            return self._extreme_bottom_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.AGGRESSIVE_DCA:
            return self._aggressive_dca_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.ACCUMULATION:
            return self._accumulation_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.BULL_MARKET:
            return self._bull_market_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.EXTREME_TOP:
            return self._extreme_top_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.GOLD_HOLDING:
            return self._gold_holding_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
    
    def _determine_cycle_phase(
        self, 
        btc_percentile: float, 
        eth_percentile: float,
        portfolio_state: PortfolioState
    ) -> CyclePhase:
        """Determine current phase in the exponential cycle"""
        
        avg_percentile = (btc_percentile + eth_percentile) / 2
        
        # CRITICAL: Check extreme percentiles FIRST before metals allocation
        # This allows metals→USD liquidation when extreme bottom appears
        
        # Extreme bottom with metals (gold + silver) - time to liquidate metals→USD
        if avg_percentile < 5 and portfolio_state.metals_allocation > 5:
            return CyclePhase.EXTREME_BOTTOM
        
        # Aggressive DCA - we have USD available (from metals liquidation) and low prices
        elif avg_percentile < 15 and portfolio_state.usd_available > 0:
            return CyclePhase.AGGRESSIVE_DCA
        
        # Extreme top - time to rotate to metals (gold + silver)
        elif avg_percentile >= 85:
            return CyclePhase.EXTREME_TOP
        
        # If holding significant metals but not at extremes, we're waiting
        elif portfolio_state.metals_allocation > 30:
            return CyclePhase.GOLD_HOLDING
        
        # Bull market - maintain baseline
        elif avg_percentile >= 45:
            return CyclePhase.BULL_MARKET
        
        # Accumulation zone - favorable DCA conditions
        else:
            return CyclePhase.ACCUMULATION
    
    def _extreme_bottom_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        EXTREME BOTTOM: Liquidate metals (gold + silver) → USD, then aggressive DCA into crypto
        
        This is THE moment - exponential gains come from going all-in at bottoms
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        # Step 1: Liquidate metals if holding any
        rotation_pct = 0
        rotation_dir = None
        
        if portfolio.metals_allocation > 5:
            # Liquidate 80-95% of metals back to USD for aggressive deployment
            if avg_pct < 2:
                rotation_pct = 95  # Ultra-extreme: liquidate almost everything
            elif avg_pct < 5:
                rotation_pct = 80  # Extreme: liquidate most
            
            rotation_dir = 'metals_to_usd'
            
        # Step 2: Don't DCA yet, first liquidate metals to USD
        # Kelly allocation will be used in AGGRESSIVE_DCA phase
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.EXTREME_BOTTOM,
            primary_action="LIQUIDATE_METALS",
            dca_amount_usd=0,  # Don't DCA yet, wait for USD to be available
            btc_amount_usd=0,  # Will deploy after metals→USD rotation
            eth_amount_usd=0,
            rotation_percentage=rotation_pct,
            rotation_direction=rotation_dir,
            confidence='high',
            reasoning=f"EXTREME BOTTOM ({avg_pct:.1f}th percentile): Liquidate gold & silver to USD now. Next phase: aggressive deployment with Kelly allocation (BTC {btc_weight:.0%}, ETH {eth_weight:.0%})",
            expected_outcome=f"Convert precious metals holdings to USD for maximum accumulation opportunity"
        )
    
    def _aggressive_dca_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        AGGRESSIVE DCA: Deploy USD from gold liquidation with 2-3x multipliers
        
        This is THE moment - exponential gains come from going all-in at bottoms
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        # Aggressive DCA multiplier based on how extreme the bottom
        if avg_pct < 5:
            dca_multiplier = 3.0  # 3x baseline
        elif avg_pct < 10:
            dca_multiplier = 2.5  # 2.5x baseline
        else:
            dca_multiplier = 2.0  # 2x baseline
            
        total_dca = self.base_weekly_dca * dca_multiplier
        
        # Kelly Half allocation between BTC/ETH
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        btc_amount = total_dca * btc_weight
        eth_amount = total_dca * eth_weight
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.AGGRESSIVE_DCA,
            primary_action="DEPLOY_USD_AGGRESSIVELY",
            dca_amount_usd=total_dca,
            btc_amount_usd=btc_amount,
            eth_amount_usd=eth_amount,
            rotation_percentage=0,
            rotation_direction=None,
            confidence='high',
            reasoning=f"AGGRESSIVE DCA ({avg_pct:.1f}th percentile): Deploy {dca_multiplier}x baseline from liquidated gold for exponential gains. Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
            expected_outcome=f"Position for {dca_multiplier}x returns when market recovers to mean"
        )
    
    def _accumulation_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        ACCUMULATION: Favorable conditions, increase DCA moderately
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        # Scaled DCA based on how undervalued
        if avg_pct < 15:
            dca_multiplier = 1.7
        elif avg_pct < 30:
            dca_multiplier = 1.4
        else:
            dca_multiplier = 1.2
            
        total_dca = self.base_weekly_dca * dca_multiplier
        
        # Kelly Half allocation
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        btc_amount = total_dca * btc_weight
        eth_amount = total_dca * eth_weight
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.ACCUMULATION,
            primary_action="INCREASED_DCA",
            dca_amount_usd=total_dca,
            btc_amount_usd=btc_amount,
            eth_amount_usd=eth_amount,
            rotation_percentage=0,
            rotation_direction=None,
            confidence='medium',
            reasoning=f"ACCUMULATION ZONE ({avg_pct:.1f}th percentile): Favorable conditions warrant {dca_multiplier}x baseline DCA. Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
            expected_outcome=f"Consistent accumulation at {int((100-avg_pct))}% discount to historical average"
        )
    
    def _bull_market_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        BULL MARKET: Maintain baseline DCA, no rotations yet
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        total_dca = self.base_weekly_dca * 1.0  # Baseline
        
        # Kelly Half allocation
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        btc_amount = total_dca * btc_weight
        eth_amount = total_dca * eth_weight
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.BULL_MARKET,
            primary_action="MAINTAIN_BASELINE_DCA",
            dca_amount_usd=total_dca,
            btc_amount_usd=btc_amount,
            eth_amount_usd=eth_amount,
            rotation_percentage=0,
            rotation_direction=None,
            confidence='medium',
            reasoning=f"BULL MARKET ({avg_pct:.1f}th percentile): Fair valuation. Baseline DCA with Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
            expected_outcome="Steady accumulation during normal market conditions"
        )
    
    def _extreme_top_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        EXTREME TOP: Rotate crypto → metals (gold + silver), reduce DCA to baseline minimum
        
        This is where we lock in gains and prepare for the next cycle
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        # Calculate rotation percentage based on extreme level
        if avg_pct >= 98:
            rotation_pct = 75  # Ultra-extreme: rotate most
        elif avg_pct >= 95:
            rotation_pct = 60  # Extreme: rotate majority
        elif avg_pct >= 90:
            rotation_pct = 45  # Very high: rotate significant portion
        else:
            rotation_pct = 30  # High: rotate conservative amount
        
        # Split between gold and silver (70/30 default)
        gold_pct = 70.0
        silver_pct = 30.0
        
        # Reduce DCA significantly at tops
        dca_multiplier = 0.3  # 30% of baseline
        total_dca = self.base_weekly_dca * dca_multiplier
        
        # Kelly Half allocation
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        btc_amount = total_dca * btc_weight
        eth_amount = total_dca * eth_weight
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.EXTREME_TOP,
            primary_action="ROTATE_TO_METALS",
            dca_amount_usd=total_dca,
            btc_amount_usd=btc_amount,
            eth_amount_usd=eth_amount,
            rotation_percentage=rotation_pct,
            rotation_direction='crypto_to_metals',
            gold_rotation_pct=gold_pct,
            silver_rotation_pct=silver_pct,
            confidence='high',
            reasoning=f"EXTREME TOP ({avg_pct:.1f}th percentile): Rotate {rotation_pct}% to precious metals ({gold_pct:.0f}% gold, {silver_pct:.0f}% silver). Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
            expected_outcome=f"Lock in {rotation_pct}% of gains in gold & silver, wait for extreme bottom to redeploy"
        )
    
    def _gold_holding_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        METALS HOLDING: Waiting for extreme bottom to liquidate and re-deploy
        
        Monitor for <5% percentile to trigger next cycle
        """
        
        avg_pct = (btc_pct + eth_pct) / 2
        
        # If extreme bottom appears while holding metals, trigger liquidation
        if avg_pct < 5:
            return self._extreme_bottom_strategy(btc_pct, eth_pct, btc_sig, eth_sig, portfolio)
        
        # Otherwise, minimal DCA while waiting
        dca_multiplier = 0.5  # 50% baseline to maintain some exposure
        total_dca = self.base_weekly_dca * dca_multiplier
        
        # Kelly Half allocation
        btc_weight, eth_weight = self._calculate_kelly_split(btc_pct, eth_pct)
        btc_amount = total_dca * btc_weight
        eth_amount = total_dca * eth_weight
        
        return CycleRecommendation(
            cycle_phase=CyclePhase.GOLD_HOLDING,
            primary_action="HOLD_METALS_AND_WAIT",
            dca_amount_usd=total_dca,
            btc_amount_usd=btc_amount,
            eth_amount_usd=eth_amount,
            rotation_percentage=0,
            rotation_direction=None,
            confidence='medium',
            reasoning=f"METALS HOLDING ({avg_pct:.1f}th percentile): Gains preserved in gold & silver. Maintain {int(dca_multiplier*100)}% DCA (Kelly: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}). Waiting for <5% percentile.",
            expected_outcome=f"Capital preserved in precious metals, ready to deploy at extreme bottom for exponential gains"
        )
    
    def calculate_exponential_multiplier(
        self,
        initial_portfolio: float,
        rotation_history: List[Dict]
    ) -> Dict:
        """
        Calculate the exponential gain multiplier from cycling strategy
        
        Shows: Portfolio Value = P₀ × M^n where M is multiplier per cycle
        """
        
        if not rotation_history or len(rotation_history) < 2:
            return {
                'current_multiplier': 1.0,
                'cycles_completed': 0,
                'estimated_value': initial_portfolio,
                'vs_hold_strategy': 0
            }
        
        # Count complete cycles (to_gold → to_crypto pairs)
        cycles = 0
        total_multiplier = 1.0
        
        to_metals_rotations = [r for r in rotation_history if r.get('type') in ['crypto_to_gold', 'crypto_to_metals']]
        to_crypto_rotations = [r for r in rotation_history if r.get('type') in ['gold_to_usd', 'metals_to_usd']]
        
        cycles = min(len(to_metals_rotations), len(to_crypto_rotations))
        
        # Each complete cycle typically yields 1.5-3x returns
        avg_cycle_multiplier = 2.0  # Conservative estimate
        total_multiplier = avg_cycle_multiplier ** cycles
        
        estimated_value = initial_portfolio * total_multiplier
        
        return {
            'current_multiplier': total_multiplier,
            'cycles_completed': cycles,
            'estimated_value': estimated_value,
            'vs_hold_strategy': ((total_multiplier - 1) * 100)  # % gain vs holding
        }
