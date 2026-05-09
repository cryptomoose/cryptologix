"""
Portfolio State Tracker - Manages portfolio allocations and rotation history
Uses persistent JSON storage + Streamlit session state for data persistence
"""

import streamlit as st
from datetime import datetime
from typing import Dict, List, Optional
import json
from exponential_cycle_engine import PortfolioState
from persistent_storage import PersistentStorage

class PortfolioStateTracker:
    """
    Manages portfolio state across user session
    Tracks: current allocations, rotation history, cycle metrics
    Uses persistent JSON storage for data that survives browser refreshes
    """
    
    def __init__(self):
        self.storage = PersistentStorage()
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize portfolio state - load from persistent storage if available"""
        if 'portfolio_state' not in st.session_state:
            # Load from persistent storage
            saved_portfolio = self.storage.get_portfolio_state()
            saved_dca_history = self.storage.get_dca_history()
            total_dca = self.storage.get_total_dca_contributions()
            
            st.session_state.portfolio_state = {
                'crypto_allocation': saved_portfolio.get('crypto_allocation', 100.0),
                'gold_allocation': saved_portfolio.get('gold_allocation', 0.0),
                'silver_allocation': saved_portfolio.get('silver_allocation', 0.0),
                'usd_allocation': saved_portfolio.get('usd_available', 0.0),
                'last_rotation_date': None,
                'last_rotation_type': None,
                'rotation_history': saved_portfolio.get('rotation_history', []),
                'total_invested': total_dca,  # Load from persistent DCA history
                'dca_history': saved_dca_history  # Load saved DCA history
            }
    
    def get_current_state(self) -> PortfolioState:
        """Get current portfolio state"""
        state = st.session_state.portfolio_state
        
        # Note: PortfolioState uses usd_available field, but we track usd_allocation in state
        usd_value = state.get('usd_allocation', state.get('usd_available', 0))
        
        return PortfolioState(
            crypto_allocation=state['crypto_allocation'],
            gold_allocation=state['gold_allocation'],
            silver_allocation=state.get('silver_allocation', 0.0),
            usd_available=usd_value,  # Map usd_allocation to usd_available for compatibility
            last_rotation_date=state.get('last_rotation_date'),
            last_rotation_type=state.get('last_rotation_type'),
            rotation_history=state.get('rotation_history', [])
        )
    
    def update_allocation(self, crypto_pct: float, gold_pct: float, silver_pct: float = None, usd_pct: float = None):
        """Update portfolio allocation percentages
        
        Note: crypto + gold + silver + usd should sum to ~100%, but we allow flexibility
        for rotations where assets are temporarily in transition
        """
        st.session_state.portfolio_state['crypto_allocation'] = crypto_pct
        st.session_state.portfolio_state['gold_allocation'] = gold_pct
        
        if silver_pct is not None:
            st.session_state.portfolio_state['silver_allocation'] = silver_pct
        
        silver = st.session_state.portfolio_state.get('silver_allocation', 0)
        
        if usd_pct is not None:
            st.session_state.portfolio_state['usd_allocation'] = usd_pct
        else:
            # Calculate USD as remainder to maintain 100% total
            st.session_state.portfolio_state['usd_allocation'] = max(0, 100 - crypto_pct - gold_pct - silver)
        
        # Save to persistent storage
        self.storage.save_portfolio_state(crypto_pct, gold_pct, 
                                         st.session_state.portfolio_state['usd_allocation'],
                                         silver_pct=silver)
    
    def record_rotation(
        self, 
        rotation_type: str,  # 'crypto_to_metals' or 'metals_to_usd'
        percentage: float,
        from_asset: str,
        to_asset: str,
        reasoning: str,
        gold_pct: float = 70.0,  # % of metals going to gold
        silver_pct: float = 30.0  # % of metals going to silver
    ):
        """Record a rotation in history"""
        rotation = {
            'date': datetime.now().isoformat(),
            'type': rotation_type,
            'percentage': percentage,
            'from_asset': from_asset,
            'to_asset': to_asset,
            'reasoning': reasoning,
            'crypto_allocation_before': st.session_state.portfolio_state['crypto_allocation'],
            'gold_allocation_before': st.session_state.portfolio_state['gold_allocation'],
            'silver_allocation_before': st.session_state.portfolio_state.get('silver_allocation', 0)
        }
        
        # Update rotation history
        if 'rotation_history' not in st.session_state.portfolio_state:
            st.session_state.portfolio_state['rotation_history'] = []
        
        st.session_state.portfolio_state['rotation_history'].append(rotation)
        st.session_state.portfolio_state['last_rotation_date'] = datetime.now()
        st.session_state.portfolio_state['last_rotation_type'] = rotation_type
        
        # Save rotation to persistent storage
        self.storage.add_rotation_to_history(rotation)
        
        new_silver = st.session_state.portfolio_state.get('silver_allocation', 0)
        
        # Calculate new allocations based on rotation
        if rotation_type in ['crypto_to_gold', 'crypto_to_metals']:
            # Rotate crypto → metals (gold + silver)
            crypto_to_move = st.session_state.portfolio_state['crypto_allocation'] * (percentage / 100)
            new_crypto = st.session_state.portfolio_state['crypto_allocation'] - crypto_to_move
            # Split between gold and silver
            new_gold = st.session_state.portfolio_state['gold_allocation'] + (crypto_to_move * gold_pct / 100)
            new_silver = st.session_state.portfolio_state.get('silver_allocation', 0) + (crypto_to_move * silver_pct / 100)
            new_usd = st.session_state.portfolio_state.get('usd_allocation', 0)  # Unchanged
            
        elif rotation_type in ['gold_to_usd', 'metals_to_usd']:
            # Liquidate both gold AND silver → USD (for aggressive DCA deployment)
            gold_to_liquidate = st.session_state.portfolio_state['gold_allocation'] * (percentage / 100)
            silver_to_liquidate = st.session_state.portfolio_state.get('silver_allocation', 0) * (percentage / 100)
            new_gold = st.session_state.portfolio_state['gold_allocation'] - gold_to_liquidate
            new_silver = st.session_state.portfolio_state.get('silver_allocation', 0) - silver_to_liquidate
            new_crypto = st.session_state.portfolio_state['crypto_allocation']  # Unchanged until DCA
            new_usd = st.session_state.portfolio_state.get('usd_allocation', 0) + gold_to_liquidate + silver_to_liquidate
        else:
            # Default: no change
            new_crypto = st.session_state.portfolio_state['crypto_allocation']
            new_gold = st.session_state.portfolio_state['gold_allocation']
            new_silver = st.session_state.portfolio_state.get('silver_allocation', 0)
            new_usd = st.session_state.portfolio_state.get('usd_allocation', 0)
        
        # Update allocations (all four: crypto, gold, silver, USD)
        self.update_allocation(new_crypto, new_gold, new_silver, new_usd)
        
        # Record in rotation history with new allocations
        rotation['crypto_allocation_after'] = new_crypto
        rotation['gold_allocation_after'] = new_gold
        rotation['silver_allocation_after'] = new_silver
    
    def record_dca_purchase(
        self,
        amount_usd: float,
        btc_amount: float,
        eth_amount: float,
        multiplier: float,
        reasoning: str
    ):
        """Record a DCA purchase and convert USD to crypto if available"""
        dca_record = {
            'date': datetime.now().isoformat(),
            'total_usd': amount_usd,
            'btc_usd': btc_amount,
            'eth_usd': eth_amount,
            'multiplier': multiplier,
            'reasoning': reasoning
        }
        
        if 'dca_history' not in st.session_state.portfolio_state:
            st.session_state.portfolio_state['dca_history'] = []
        
        st.session_state.portfolio_state['dca_history'].append(dca_record)
        st.session_state.portfolio_state['total_invested'] = \
            st.session_state.portfolio_state.get('total_invested', 0) + amount_usd
        
        # Save DCA contribution to persistent storage with full details
        self.storage.add_dca_contribution(dca_record)
        
        # Convert USD to crypto (from gold liquidations)
        usd_allocation = st.session_state.portfolio_state.get('usd_allocation', 0)
        if usd_allocation > 0:
            # Use available USD to buy crypto
            usd_to_crypto = min(usd_allocation, 100)  # Convert up to 100% of USD
            new_crypto = st.session_state.portfolio_state['crypto_allocation'] + usd_to_crypto
            new_usd = usd_allocation - usd_to_crypto
            new_gold = st.session_state.portfolio_state['gold_allocation']
            
            self.update_allocation(new_crypto, new_gold, new_usd)
    
    def get_rotation_history(self) -> List[Dict]:
        """Get all rotations"""
        return st.session_state.portfolio_state.get('rotation_history', [])
    
    def get_dca_history(self) -> List[Dict]:
        """Get all DCA purchases"""
        return st.session_state.portfolio_state.get('dca_history', [])
    
    def get_total_invested(self) -> float:
        """Get total USD invested via DCA"""
        return st.session_state.portfolio_state.get('total_invested', 0)
    
    def get_cycle_metrics(self) -> Dict:
        """Calculate cycle performance metrics"""
        rotation_history = self.get_rotation_history()
        
        # Count complete cycles
        to_metals = [r for r in rotation_history if r['type'] in ['crypto_to_gold', 'crypto_to_metals']]
        to_usd = [r for r in rotation_history if r['type'] in ['gold_to_usd', 'metals_to_usd']]
        complete_cycles = min(len(to_metals), len(to_usd))
        
        # Calculate average rotation percentages
        avg_to_metals = sum(r['percentage'] for r in to_metals) / len(to_metals) if to_metals else 0
        avg_to_usd = sum(r['percentage'] for r in to_usd) / len(to_usd) if to_usd else 0
        
        return {
            'complete_cycles': complete_cycles,
            'total_rotations': len(rotation_history),
            'rotations_to_metals': len(to_metals),
            'rotations_to_usd': len(to_usd),
            'avg_rotation_to_metals_pct': avg_to_metals,
            'avg_rotation_to_usd_pct': avg_to_usd,
            'last_rotation': rotation_history[-1] if rotation_history else None
        }
    
    def execute_rotation(self, rotation_direction: str, rotation_percentage: float, 
                         gold_pct: float = 70.0, silver_pct: float = 30.0):
        """
        Execute a rotation (wrapper for record_rotation with simpler API)
        
        Args:
            rotation_direction: e.g., "crypto_to_metals" or "metals_to_usd"
            rotation_percentage: percentage to rotate (0-100)
            gold_pct: percentage of metals going to gold (default 70%)
            silver_pct: percentage of metals going to silver (default 30%)
        """
        # Map direction to from/to assets
        if rotation_direction in ["crypto_to_gold", "crypto_to_metals"]:
            from_asset = "crypto"
            to_asset = "metals"
            reasoning = f"Market at extreme top - rotating {rotation_percentage:.1f}% to preserve gains ({gold_pct:.0f}% gold, {silver_pct:.0f}% silver)"
        elif rotation_direction in ["gold_to_usd", "metals_to_usd"]:
            from_asset = "metals"
            to_asset = "usd"
            reasoning = f"Market at extreme bottom - liquidating {rotation_percentage:.1f}% precious metals to USD for aggressive DCA"
        else:
            return  # Unknown direction, skip
        
        self.record_rotation(
            rotation_type=rotation_direction,
            percentage=rotation_percentage,
            from_asset=from_asset,
            to_asset=to_asset,
            reasoning=reasoning,
            gold_pct=gold_pct,
            silver_pct=silver_pct
        )
    
    def record_dca(self, btc_amount: float, eth_amount: float):
        """
        Record DCA purchase (wrapper for record_dca_purchase with simpler API)
        
        Args:
            btc_amount: USD amount for BTC purchase
            eth_amount: USD amount for ETH purchase
        """
        total_amount = btc_amount + eth_amount
        
        # Determine multiplier based on total invested and current recommendation
        # For now, use 1.0x baseline (could be enhanced later)
        multiplier = 1.0
        reasoning = f"Weekly DCA: ${btc_amount:.2f} BTC + ${eth_amount:.2f} ETH"
        
        self.record_dca_purchase(
            amount_usd=total_amount,
            btc_amount=btc_amount,
            eth_amount=eth_amount,
            multiplier=multiplier,
            reasoning=reasoning
        )
    
    def reset_portfolio(self):
        """Reset portfolio to initial state (for testing or fresh start)"""
        st.session_state.portfolio_state = {
            'crypto_allocation': 100.0,
            'gold_allocation': 0.0,
            'silver_allocation': 0.0,
            'usd_allocation': 0.0,
            'last_rotation_date': None,
            'last_rotation_type': None,
            'rotation_history': [],
            'total_invested': 0.0,
            'dca_history': []
        }
    
    def render_portfolio_summary(self):
        """Render portfolio state in Streamlit UI"""
        state = st.session_state.portfolio_state
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Crypto",
                f"{state['crypto_allocation']:.1f}%",
                delta=None
            )
        
        with col2:
            st.metric(
                "Gold", 
                f"{state['gold_allocation']:.1f}%",
                delta=None
            )
        
        with col3:
            st.metric(
                "Silver",
                f"{state.get('silver_allocation', 0):.1f}%",
                delta=None
            )
        
        with col4:
            st.metric(
                "USD",
                f"{state.get('usd_allocation', 0):.1f}%",
                help="From metals liquidations, ready to deploy via DCA"
            )
        
        # Show last rotation if exists
        if state.get('last_rotation_date'):
            last_rotation = state.get('rotation_history', [])[-1] if state.get('rotation_history') else None
            if last_rotation:
                st.info(
                    f"**Last Rotation:** {last_rotation['type'].replace('_', ' ').title()} "
                    f"({last_rotation['percentage']:.0f}%) on {last_rotation['date'][:10]}"
                )
