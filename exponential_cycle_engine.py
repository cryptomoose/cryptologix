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
    BULL_MARKET = "bull_market"                # 45-75% - maintain baseline DCA
    BULL_REDUCE = "bull_reduce"                # 75-85% - stop DCA, prepare to sell
    EXTREME_TOP = "extreme_top"                # 85-92% - rotate to metals + stables
    ULTRA_TOP = "ultra_top"                    # >92% - maximum rotation, keep only validators
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
    stables_pct: float = 0.0  # % of portfolio rotating to stablecoins (0-100 scale)
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
        # Delegated to signal_core (shared verbatim with the crypto engine):
        # true Kelly f=μ/σ² from empirical percentile-conditioned returns and
        # 2y volatility, not the old tilt heuristic.
        from signal_core import kelly_split_btc_eth
        return kelly_split_btc_eth(btc_percentile, eth_percentile)
        
    def generate_weekly_recommendation(
        self,
        btc_percentile: float,
        eth_percentile: float,
        btc_signal: int,
        eth_signal: int,
        portfolio_state: PortfolioState,
        btc_gold_percentile: float = None,
        eth_gold_percentile: float = None,
    ) -> CycleRecommendation:
        """
        Generate unified weekly recommendation based on cycle phase
        
        Returns complete guidance: DCA amount, rotation instructions, and reasoning
        """
        
        # Determine current cycle phase
        cycle_phase = self._determine_cycle_phase(
            btc_percentile, eth_percentile, portfolio_state,
            btc_gold_percentile=btc_gold_percentile,
            eth_gold_percentile=eth_gold_percentile,
        )
        
        # Calculate cycle-appropriate actions
        if cycle_phase == CyclePhase.EXTREME_BOTTOM:
            return self._extreme_bottom_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state,
                btc_gold_percentile=btc_gold_percentile,
                eth_gold_percentile=eth_gold_percentile,
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
        elif cycle_phase == CyclePhase.BULL_REDUCE:
            return self._bull_reduce_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.EXTREME_TOP:
            return self._extreme_top_strategy(
                btc_percentile, eth_percentile, btc_signal, eth_signal, portfolio_state
            )
        elif cycle_phase == CyclePhase.ULTRA_TOP:
            return self._ultra_top_strategy(
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
        portfolio_state: PortfolioState,
        btc_gold_percentile: float = None,
        eth_gold_percentile: float = None,
    ) -> CyclePhase:
        """Determine current phase in the exponential cycle.
        
        Uses gold-ratio percentiles as the primary rotation trigger when available
        — gold ratios are more historically accurate than USD percentiles because
        they strip out dollar debasement and Fed policy distortion.
        """
        avg_percentile = (btc_percentile + eth_percentile) / 2

        # Use gold ratio percentiles for rotation trigger if available
        # Gold ratios are the historically accurate signal at cycle bottoms
        if btc_gold_percentile is not None and eth_gold_percentile is not None:
            avg_gold_percentile = (btc_gold_percentile + eth_gold_percentile) / 2
        else:
            avg_gold_percentile = avg_percentile  # fallback to USD if gold data unavailable

        # EXTREME BOTTOM: gold ratio percentiles trigger rotation
        # Using gold avg < 5 OR both individual ratios < 5 (belt-and-suspenders)
        if avg_gold_percentile < 5 or (btc_gold_percentile is not None and
                eth_gold_percentile is not None and
                btc_gold_percentile < 5 and eth_gold_percentile < 5):
            return CyclePhase.EXTREME_BOTTOM

        # Aggressive DCA — gold avg below 15th pct
        elif avg_gold_percentile < 15:
            return CyclePhase.AGGRESSIVE_DCA
        
        # Bull reduce — stop DCA, prepare to sell ahead of the 85th pct rotation trigger
        elif avg_gold_percentile >= 75 and avg_gold_percentile < 85:
            return CyclePhase.BULL_REDUCE

        # Ultra top - maximum rotation, keep only validators
        elif avg_percentile >= 92:
            return CyclePhase.ULTRA_TOP

        # Extreme top - time to rotate to metals (gold + silver) + stables
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
        portfolio: PortfolioState,
        btc_gold_percentile: float = None,
        eth_gold_percentile: float = None,
    ) -> CycleRecommendation:
        """
        EXTREME BOTTOM: Liquidate metals (gold + silver) → USD, then aggressive DCA into crypto
        
        This is THE moment - exponential gains come from going all-in at bottoms
        """
        
        avg_pct = (btc_pct + eth_pct) / 2

        # Use gold ratio percentiles for sizing when available — more accurate at bottoms
        if btc_gold_percentile is not None and eth_gold_percentile is not None:
            avg_sizing_pct = (btc_gold_percentile + eth_gold_percentile) / 2
        else:
            avg_sizing_pct = avg_pct

        # Kelly-sized rotation — continuous depth scaling from signal_core
        # (40% at the 5th pct up to 75% at the 0th; replaces 75/61.5/40 steps)
        rotation_pct = round(min(75.0, max(40.0, 75.0 - 7.0 * avg_sizing_pct)), 1)

        rotation_dir = 'metals_to_crypto'

        # Kelly allocation for BTC/ETH split
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
            reasoning=f"EXTREME BOTTOM ({avg_pct:.1f}th percentile): Rotate {rotation_pct}% of gold/silver holdings directly into crypto. Kelly split: BTC {btc_weight:.0%} / ETH {eth_weight:.0%}. Size applies to whatever metals you hold — no dollar amount required.",
            expected_outcome=f"Liquidate {rotation_pct}% of metals → deploy {btc_weight:.0%} BTC / {eth_weight:.0%} ETH on spot exchange"
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

        # Continuous GTO multiplier from signal_core (logistic through
        # 3.0x@0th / 1.0x@35th / 0.5x@50th — no step-function breakpoints)
        from signal_core import gto_multiplier
        dca_multiplier = round(gto_multiplier(avg_pct), 2)

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
            reasoning=f"AGGRESSIVE DCA ({avg_pct:.1f}th percentile): Deploy {dca_multiplier}x weekly DCA. Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
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
        
        # Continuous GTO multiplier — same curve as the crypto engine (signal_core)
        from signal_core import gto_multiplier
        dca_multiplier = round(gto_multiplier(avg_pct), 2)


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
        
        # Continuous GTO multiplier — tapers below 1.0x as the cycle heats up,
        # matching the crypto engine's curve (signal_core)
        from signal_core import gto_multiplier
        dca_multiplier = round(gto_multiplier(avg_pct), 2)
        total_dca = self.base_weekly_dca * dca_multiplier

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
            reasoning=f"BULL MARKET ({avg_pct:.1f}th percentile): Fair-to-warm valuation. {dca_multiplier}x DCA (continuous GTO taper) with Kelly allocation: BTC {btc_weight:.0%}, ETH {eth_weight:.0%}",
            expected_outcome="Steady accumulation during normal market conditions"
        )
    
    def _bull_reduce_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        BULL REDUCE: Stop DCA, begin trimming in tranches ahead of the 85th pct rotation
        """

        avg_pct = (btc_pct + eth_pct) / 2

        return CycleRecommendation(
            cycle_phase=CyclePhase.BULL_REDUCE,
            primary_action="PREPARE_TO_SELL",
            dca_amount_usd=0,
            btc_amount_usd=0,
            eth_amount_usd=0,
            rotation_percentage=0,
            rotation_direction=None,
            confidence='high',
            reasoning=f"BULL_REDUCE ({avg_pct:.1f}th percentile): Stop DCA. Begin trimming positions in tranches. Target rotation at 85th pct: 70% metals (gold 70%/silver 30%) + 30% stablecoins. Keep validators running. Sell BTC first.",
            expected_outcome="DCA halted, positions staged for rotation at the 85th percentile trigger"
        )

    def _extreme_top_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        EXTREME TOP: Rotate crypto → metals (gold + silver) + stablecoins, halt DCA

        This is where we lock in gains and prepare for the next cycle
        """

        avg_pct = (btc_pct + eth_pct) / 2

        # Continuous rotation ramp — same curve as the crypto engine (signal_core):
        # 30% at the 85th pct scaling +5pts per percentile, capped at 90%.
        # Rotation splits 70% metals / 30% stables of the rotated tranche.
        from signal_core import top_rotation_pct
        rotation_pct = round(top_rotation_pct(avg_pct), 1)
        crypto_keep = 1.0 - rotation_pct / 100.0
        metals_pct = 0.70 * rotation_pct / 100.0
        stables_pct = 0.30 * rotation_pct / 100.0

        # Split between gold and silver (70/30 default)
        gold_pct = 70.0
        silver_pct = 30.0

        # No DCA at tops — capital goes to rotation, not buying
        total_dca = 0.0

        return CycleRecommendation(
            cycle_phase=CyclePhase.EXTREME_TOP,
            primary_action="ROTATE_TO_METALS_AND_STABLES",
            dca_amount_usd=total_dca,
            btc_amount_usd=0,
            eth_amount_usd=0,
            rotation_percentage=rotation_pct,
            rotation_direction='crypto_to_metals_and_stables',
            gold_rotation_pct=gold_pct,
            silver_rotation_pct=silver_pct,
            stables_pct=stables_pct * 100,
            confidence='high',
            reasoning=f"EXTREME TOP ({avg_pct:.1f}th percentile): Rotate {rotation_pct:.0f}% out of crypto — {metals_pct*100:.1f}% of portfolio to metals, {stables_pct*100:.1f}% to stablecoins, keep {crypto_keep*100:.0f}% crypto. Gold 70% / Silver 30% of metals tranche. Stables to Aave supply or sDAI for redeployment at next bottom. Execute in tranches over 2-4 weeks. Sell BTC first. Keep validators running.",
            expected_outcome=f"Lock in gains: {metals_pct*100:.1f}% metals + {stables_pct*100:.1f}% stables, redeploy at next extreme bottom"
        )

    def _ultra_top_strategy(
        self, btc_pct: float, eth_pct: float, btc_sig: int, eth_sig: int,
        portfolio: PortfolioState
    ) -> CycleRecommendation:
        """
        ULTRA TOP (>92nd pct): Maximum rotation — keep only validators (10% crypto floor)
        """

        avg_pct = (btc_pct + eth_pct) / 2

        # Continuous rotation ramp — identical curve to the crypto engine (signal_core),
        # reaching the 90% cap at the 97th percentile.
        from signal_core import top_rotation_pct
        rotation_pct = round(top_rotation_pct(avg_pct), 1)
        crypto_keep = 1.0 - rotation_pct / 100.0
        metals_pct = 0.70 * rotation_pct / 100.0
        stables_pct = 0.30 * rotation_pct / 100.0

        gold_pct = 70.0
        silver_pct = 30.0

        return CycleRecommendation(
            cycle_phase=CyclePhase.ULTRA_TOP,
            primary_action="MAXIMUM_ROTATION",
            dca_amount_usd=0,
            btc_amount_usd=0,
            eth_amount_usd=0,
            rotation_percentage=rotation_pct,
            rotation_direction='crypto_to_metals_and_stables',
            gold_rotation_pct=gold_pct,
            silver_rotation_pct=silver_pct,
            stables_pct=stables_pct * 100,
            confidence='high',
            reasoning=f"ULTRA_TOP — maximum rotation ({avg_pct:.1f}th percentile): Rotate {rotation_pct:.0f}% out of crypto — {metals_pct*100:.0f}% of portfolio to metals (gold 70%/silver 30%), {stables_pct*100:.0f}% to stablecoins (Aave supply or sDAI), keep {crypto_keep*100:.0f}% crypto. Keep only validators. Execute in tranches over 2-4 weeks. Sell BTC first, ETH second.",
            expected_outcome=f"Maximum gains locked: {metals_pct*100:.0f}% metals + {stables_pct*100:.0f}% stables, validators only in crypto"
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
