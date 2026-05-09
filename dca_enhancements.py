"""
DCA Enhancements Module
Advanced Dollar Cost Averaging with Seasonal, Kelly Criterion, and Equal allocation modes
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import calendar
import json
from typing import Dict, List, Any, Optional, Tuple
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Month constants
MONTHS = ["January","February","March","April","May","June",
          "July","August","September","October","November","December"]

class DCAEnhancementConfig:
    """Configuration class for DCA enhancements"""
    
    def __init__(self, config_dict: Optional[Dict] = None):
        """Initialize with default or custom configuration"""
        default_config = {
            "enabled": False,  # Backward compatibility - disabled by default
            "baseline_per_day_usd": 100,
            "pair": ["BTC", "ETH"],
            "mode": "equal",  # equal | seasonal | kelly_half | kelly_full
            "rebalance_cadence": "monthly",
            "cap_floor": {"min": 0.30, "max": 0.70},
            "normalize_annual_spend": True,
            "download_artifacts": True
        }
        
        self.config = {**default_config, **(config_dict or {})}
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.config.get(key, default)
    
    def is_enabled(self) -> bool:
        """Check if enhancements are enabled"""
        return self.config.get("enabled", False)

def month_stats(returns_by_month: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    """Calculate mean, std dev, and Kelly edge for each month"""
    stats = {}
    for m, arr in returns_by_month.items():
        arr = np.asarray(arr, dtype=float)
        mu = float(np.nanmean(arr)) if arr.size else 0.0
        sigma = float(np.nanstd(arr, ddof=1)) if arr.size > 1 else 0.0
        k = max(0.0, mu/(sigma**2)) if sigma and sigma > 0 else 0.0
        stats[m] = {"mu": mu, "sigma": sigma, "kelly": k, "count": len(arr)}
    return stats

def kelly_split(stats_a: Dict, stats_b: Dict, month: str, 
               caps: Tuple[float, float] = (0.30, 0.70), half: bool = False) -> Tuple[float, float]:
    """Calculate Kelly-optimal split between two assets"""
    ka = float(stats_a[month]["kelly"])
    kb = float(stats_b[month]["kelly"])
    s = ka + kb
    wa = 0.5 if s <= 0 else ka / s   # asset A weight
    
    if half:
        wa = 0.5 * wa + 0.25         # shrink 50% toward equal for 2 assets
    
    lo, hi = caps
    wa = min(max(wa, lo), hi)
    wb = 1.0 - wa
    return wa, wb

def seasonal_multiplier(stats_asset: Dict, caps: Tuple[float, float] = (0.70, 1.50)) -> Dict[str, float]:
    """Calculate seasonal multipliers for an asset"""
    emap = {}
    for m in MONTHS:
        mu = float(stats_asset[m]["mu"])
        sigma = float(stats_asset[m]["sigma"])
        e = max(0.0, mu/(sigma**2)) if sigma and sigma > 0 else 0.0
        emap[m] = e
    
    vals = np.array(list(emap.values()), dtype=float)
    mean = float(vals.mean()) if vals.mean() > 0 else 1.0
    for m in emap: 
        emap[m] = emap[m] / mean
    
    lo, hi = caps
    for m in emap: 
        emap[m] = min(max(emap[m], lo), hi)
    
    return emap

def annual_normalize(mults: Dict[str, float], days_in_month: Dict[str, int]) -> Dict[str, float]:
    """Normalize multipliers to preserve annual spend"""
    lhs = sum(mults[m] * days_in_month[m] for m in MONTHS)
    rhs = sum(days_in_month[m] for m in MONTHS)
    adj = rhs / lhs if lhs > 0 else 1.0
    return {m: mults[m] * adj for m in MONTHS}

def get_days_in_month() -> Dict[str, int]:
    """Get days in each month (using current year)"""
    current_year = datetime.now().year
    return {
        MONTHS[i]: calendar.monthrange(current_year, i+1)[1] 
        for i in range(12)
    }

def allocate_month(mode: str, month_spend_usd: float, prices: Dict[str, float], 
                  month_name: str, stats_btc: Dict, stats_eth: Dict, 
                  days_in_month: Dict[str, int], cfg: DCAEnhancementConfig) -> Dict:
    """Allocate monthly spend between assets based on mode"""
    
    # Determine weights based on mode
    if mode == "equal":
        w_btc, w_eth = 0.5, 0.5
        rationale = "Equal 50/50 allocation between BTC and ETH."
        
    elif mode == "kelly_full":
        caps = (cfg.get("cap_floor", {}).get("min", 0.30), 
                cfg.get("cap_floor", {}).get("max", 0.70))
        w_btc, w_eth = kelly_split(stats_btc, stats_eth, month_name, caps=caps, half=False)
        rationale = f"Full Kelly allocation for {month_name}: BTC {w_btc:.1%}, ETH {w_eth:.1%} based on μ/σ² optimization."
        
    elif mode == "kelly_half":
        caps = (cfg.get("cap_floor", {}).get("min", 0.30), 
                cfg.get("cap_floor", {}).get("max", 0.70))
        w_btc, w_eth = kelly_split(stats_btc, stats_eth, month_name, caps=caps, half=True)
        rationale = f"Half-Kelly allocation for {month_name}: BTC {w_btc:.1%}, ETH {w_eth:.1%} (50% shrinkage toward equal)."
        
    elif mode == "seasonal":
        # Calculate seasonal multipliers for each asset
        btc_seasonal_mults = seasonal_multiplier(stats_btc)
        eth_seasonal_mults = seasonal_multiplier(stats_eth)
        
        # Get current month multipliers
        btc_mult = btc_seasonal_mults[month_name]
        eth_mult = eth_seasonal_mults[month_name]
        
        # Annual normalize the multipliers
        btc_normalized = annual_normalize(btc_seasonal_mults, days_in_month)
        eth_normalized = annual_normalize(eth_seasonal_mults, days_in_month)
        
        # Get normalized multipliers for current month
        btc_norm_mult = btc_normalized[month_name]
        eth_norm_mult = eth_normalized[month_name]
        
        # Pro-rata normalize between assets to maintain total monthly spend
        total_mult = btc_norm_mult + eth_norm_mult
        if total_mult > 0:
            w_btc = btc_norm_mult / total_mult
            w_eth = eth_norm_mult / total_mult
        else:
            w_btc, w_eth = 0.5, 0.5
        
        rationale = f"Seasonal allocation for {month_name}: BTC {w_btc:.1%} (mult: {btc_mult:.2f}), ETH {w_eth:.1%} (mult: {eth_mult:.2f}) based on historical monthly patterns."
        
    else:
        # Fallback to equal
        w_btc, w_eth = 0.5, 0.5
        rationale = f"Unknown mode '{mode}' - using equal fallback allocation."

    # Calculate USD amounts
    usd_btc = month_spend_usd * w_btc
    usd_eth = month_spend_usd * w_eth
    
    # Calculate units (if prices available)
    units_btc = usd_btc / prices.get("BTC", 1) if prices.get("BTC", 0) > 0 else 0.0
    units_eth = usd_eth / prices.get("ETH", 1) if prices.get("ETH", 0) > 0 else 0.0
    
    return {
        "weights": {"BTC": w_btc, "ETH": w_eth},
        "usd": {"BTC": usd_btc, "ETH": usd_eth},
        "units": {"BTC": units_btc, "ETH": units_eth},
        "rationale": rationale
    }

class DCAEnhancementEngine:
    """Main engine for DCA enhancements"""
    
    def __init__(self, config: Optional[DCAEnhancementConfig] = None):
        self.config = config or DCAEnhancementConfig()
        self.historical_returns = {}
        self.days_in_month = get_days_in_month()
        
    def is_enabled(self) -> bool:
        """Check if enhancements are enabled"""
        return self.config.is_enabled()
    
    def calculate_monthly_returns(self, price_data: pd.DataFrame, asset: str) -> Dict[str, List[float]]:
        """Calculate monthly returns grouped by calendar month"""
        if price_data.empty:
            return {month: [] for month in MONTHS}
        
        # Ensure we have a datetime index
        df = price_data.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        
        # Calculate monthly returns
        monthly_data = df.resample('ME').last()  # Use 'ME' instead of deprecated 'M'
        monthly_returns = monthly_data.pct_change().dropna()
        
        # Group by calendar month
        returns_by_month = {month: [] for month in MONTHS}
        
        for date, return_val in monthly_returns.items():
            if pd.notna(return_val):
                month_name = MONTHS[date.month - 1]
                returns_by_month[month_name].append(float(return_val))
        
        return returns_by_month
    
    def has_sufficient_data(self, returns_by_month: Dict[str, List[float]], min_observations: int = 24) -> bool:
        """Check if we have sufficient historical data"""
        total_observations = sum(len(returns) for returns in returns_by_month.values())
        return total_observations >= min_observations
    
    def generate_enhanced_dca_advice(self, btc_data: pd.DataFrame, eth_data: pd.DataFrame, 
                                   btc_price: float, eth_price: float, 
                                   base_weekly_amount: Optional[float] = None) -> Dict[str, Any]:
        """Generate enhanced DCA advice with seasonal/Kelly modes"""
        
        if not self.is_enabled():
            return {"enabled": False, "message": "DCA enhancements disabled"}
        
        # Use configured baseline or fallback
        baseline_daily = base_weekly_amount / 7 if base_weekly_amount else self.config.get("baseline_per_day_usd", 100)
        
        # Current month
        current_month = MONTHS[datetime.now().month - 1]
        days_in_current_month = self.days_in_month[current_month]
        month_spend_usd = baseline_daily * days_in_current_month
        
        # Calculate historical returns
        btc_returns = self.calculate_monthly_returns(btc_data, "BTC")
        eth_returns = self.calculate_monthly_returns(eth_data, "ETH")
        
        # Check data sufficiency
        btc_sufficient = self.has_sufficient_data(btc_returns)
        eth_sufficient = self.has_sufficient_data(eth_returns)
        
        mode = self.config.get("mode", "equal")
        
        # Fallback to equal if insufficient data
        if not btc_sufficient or not eth_sufficient:
            mode = "equal"
            fallback_reason = "Insufficient historical data - using equal allocation"
        else:
            fallback_reason = None
        
        # Calculate month statistics
        stats_btc = month_stats(btc_returns)
        stats_eth = month_stats(eth_returns)
        
        # Get current prices
        prices = {"BTC": btc_price, "ETH": eth_price}
        
        # Generate allocation
        allocation = allocate_month(
            mode=mode,
            month_spend_usd=month_spend_usd,
            prices=prices,
            month_name=current_month,
            stats_btc=stats_btc,
            stats_eth=stats_eth,
            days_in_month=self.days_in_month,
            cfg=self.config
        )
        
        # Format response
        response = {
            "enabled": True,
            "dca_advice": {
                "mode_used": mode,
                "month": f"{current_month} {datetime.now().year}",
                "baseline_per_day_usd": baseline_daily,
                "month_spend_usd": month_spend_usd,
                "allocations": [
                    {
                        "asset": "BTC",
                        "weight": allocation["weights"]["BTC"],
                        "usd": allocation["usd"]["BTC"],
                        "price": btc_price,
                        "units": allocation["units"]["BTC"]
                    },
                    {
                        "asset": "ETH", 
                        "weight": allocation["weights"]["ETH"],
                        "usd": allocation["usd"]["ETH"],
                        "price": eth_price,
                        "units": allocation["units"]["ETH"]
                    }
                ],
                "rationale_summary": fallback_reason or allocation["rationale"]
            },
            "statistics": {
                "btc_month_stats": stats_btc.get(current_month, {}),
                "eth_month_stats": stats_eth.get(current_month, {}),
                "data_sufficiency": {
                    "btc_sufficient": btc_sufficient,
                    "eth_sufficient": eth_sufficient,
                    "btc_observations": sum(len(returns) for returns in btc_returns.values()),
                    "eth_observations": sum(len(returns) for returns in eth_returns.values())
                }
            }
        }
        
        return response
    
    def generate_historical_performance_analysis(self, btc_data: pd.DataFrame, eth_data: pd.DataFrame, 
                                               initial_investment: float = 10000, monthly_dca: float = 1000) -> Dict[str, Any]:
        """
        Generate historical performance analysis comparing all Enhanced DCA modes
        
        Args:
            btc_data: Historical BTC price data with 'Close' column
            eth_data: Historical ETH price data with 'Close' column  
            initial_investment: Starting portfolio value in USD
            monthly_dca: Monthly DCA amount in USD
            
        Returns:
            Dictionary with performance data and visualization
        """
        try:
            # Ensure we have enough data
            if len(btc_data) < 365 or len(eth_data) < 365:
                return {'error': 'Insufficient historical data for performance analysis'}
            
            # Align data to common date range
            btc_prices = btc_data['Close'].dropna()
            eth_prices = eth_data['Close'].dropna()
            
            # Find overlapping date range
            start_date = max(btc_prices.index.min(), eth_prices.index.min())
            end_date = min(btc_prices.index.max(), eth_prices.index.max())
            
            # Filter to common date range
            btc_aligned = btc_prices[start_date:end_date].resample('D').ffill()
            eth_aligned = eth_prices[start_date:end_date].resample('D').ffill()
            
            # Generate monthly statistics for the full period - simplified version
            btc_monthly_stats = self._generate_simplified_monthly_stats(btc_aligned)
            eth_monthly_stats = self._generate_simplified_monthly_stats(eth_aligned)
            
            # Initialize performance tracking for each mode
            modes = ['equal', 'seasonal', 'kelly_half', 'kelly_full']
            performance_data = {}
            
            for mode in modes:
                performance_data[mode] = self._simulate_mode_performance(
                    btc_aligned, eth_aligned, btc_monthly_stats, eth_monthly_stats,
                    mode, initial_investment, monthly_dca
                )
            
            # Create comparison visualization
            chart = self._create_performance_chart(performance_data, start_date, end_date)
            
            # Calculate summary metrics
            summary_metrics = self._calculate_summary_metrics(performance_data)
            
            return {
                'success': True,
                'performance_data': performance_data,
                'chart': chart,
                'summary_metrics': summary_metrics,
                'analysis_period': {
                    'start_date': start_date.strftime('%Y-%m-%d'),
                    'end_date': end_date.strftime('%Y-%m-%d'),
                    'total_days': len(btc_aligned),
                    'total_years': len(btc_aligned) / 365.25
                }
            }
            
        except Exception as e:
            return {'error': f'Performance analysis failed: {str(e)}'}
    
    def _simulate_mode_performance(self, btc_prices: pd.Series, eth_prices: pd.Series,
                                 btc_stats: Dict, eth_stats: Dict, mode: str,
                                 initial_investment: float, monthly_dca: float) -> Dict[str, Any]:
        """Simulate performance for a specific Enhanced DCA mode"""
        
        portfolio_values = []
        btc_holdings = 0
        eth_holdings = 0
        cash_balance = initial_investment
        dates = []
        
        # Track monthly investments
        last_investment_month = None
        
        for date in btc_prices.index:
            # Add monthly DCA investment
            current_month = date.month if hasattr(date, 'month') else date.to_pydatetime().month
            if last_investment_month != current_month:
                cash_balance += monthly_dca
                
                # Calculate allocation weights for this month
                month_name = calendar.month_name[current_month]
                weights = self._get_mode_allocation_weights(mode, month_name, btc_stats, eth_stats)
                
                # Invest the monthly DCA according to mode allocation
                btc_investment = monthly_dca * weights[0]
                eth_investment = monthly_dca * weights[1]
                
                # Buy assets at current prices
                if btc_prices[date] > 0:
                    btc_holdings += btc_investment / btc_prices[date]
                    cash_balance -= btc_investment
                
                if eth_prices[date] > 0:
                    eth_holdings += eth_investment / eth_prices[date]
                    cash_balance -= eth_investment
                
                last_investment_month = current_month
            
            # Calculate current portfolio value
            portfolio_value = (btc_holdings * btc_prices[date] + 
                             eth_holdings * eth_prices[date] + 
                             cash_balance)
            
            portfolio_values.append(portfolio_value)
            dates.append(date)
        
        return {
            'dates': dates,
            'portfolio_values': portfolio_values,
            'final_value': portfolio_values[-1] if portfolio_values else initial_investment,
            'btc_holdings': btc_holdings,
            'eth_holdings': eth_holdings,
            'cash_balance': cash_balance
        }
    
    def _get_mode_allocation_weights(self, mode: str, month_name: str, btc_stats: Dict, eth_stats: Dict) -> Tuple[float, float]:
        """Get BTC/ETH allocation weights for a specific mode and month"""
        
        if mode == 'equal':
            return (0.5, 0.5)
        elif mode == 'seasonal':
            # Use seasonal multipliers - simplified version
            btc_mult = btc_stats.get('monthly_multipliers', {}).get(month_name, 1.0)
            eth_mult = eth_stats.get('monthly_multipliers', {}).get(month_name, 1.0)
            total = btc_mult + eth_mult
            if total > 0:
                return (btc_mult / total, eth_mult / total)
            else:
                return (0.5, 0.5)
        elif mode in ['kelly_half', 'kelly_full']:
            # Simplified Kelly allocation based on historical performance
            btc_return = btc_stats.get('monthly_returns', {}).get(month_name, 0.02)
            eth_return = eth_stats.get('monthly_returns', {}).get(month_name, 0.03)
            btc_vol = btc_stats.get('monthly_volatility', {}).get(month_name, 0.15)
            eth_vol = eth_stats.get('monthly_volatility', {}).get(month_name, 0.18)
            
            # Kelly fraction calculation
            btc_kelly = max(0, min(0.7, btc_return / (btc_vol ** 2))) if btc_vol > 0 else 0.4
            eth_kelly = max(0, min(0.7, eth_return / (eth_vol ** 2))) if eth_vol > 0 else 0.6
            
            if mode == 'kelly_half':
                # Conservative approach - 50% shrinkage toward equal
                btc_kelly = (btc_kelly + 0.5) / 2
                eth_kelly = (eth_kelly + 0.5) / 2
            
            total = btc_kelly + eth_kelly
            if total > 0:
                return (btc_kelly / total, eth_kelly / total)
            else:
                return (0.4, 0.6)  # Default BTC/ETH split
        
        return (0.5, 0.5)  # Fallback
    
    def _create_performance_chart(self, performance_data: Dict, start_date, end_date) -> go.Figure:
        """Create performance comparison chart"""
        
        fig = go.Figure()
        
        colors = {
            'equal': '#FFA500',      # Orange
            'seasonal': '#32CD32',   # Lime Green  
            'kelly_half': '#1E90FF', # Dodger Blue
            'kelly_full': '#FF4500'  # Red Orange
        }
        
        mode_names = {
            'equal': 'Equal (50/50)',
            'seasonal': 'Seasonal Optimization',
            'kelly_half': 'Kelly Half (Conservative)',
            'kelly_full': 'Kelly Full (Aggressive)'
        }
        
        for mode, data in performance_data.items():
            if 'portfolio_values' in data:
                fig.add_trace(go.Scatter(
                    x=data['dates'],
                    y=data['portfolio_values'],
                    mode='lines',
                    name=mode_names[mode],
                    line=dict(color=colors[mode], width=2.5),
                    hovertemplate=f'{mode_names[mode]}<br>Date: %{{x}}<br>Portfolio Value: $%{{y:,.0f}}<extra></extra>'
                ))
        
        # Calculate optimal y-axis range for clear visibility of all trend lines
        all_values = []
        for mode, data in performance_data.items():
            if 'portfolio_values' in data and data['portfolio_values']:
                all_values.extend(data['portfolio_values'])
        
        if all_values:
            min_val = min(all_values)
            max_val = max(all_values)
            # Add 10% margin on both ends for clear visibility
            margin = (max_val - min_val) * 0.1
            y_min = max(0, min_val - margin)  # Don't go below 0
            y_max = max_val + margin
        else:
            y_min = 0
            y_max = 100000  # Fallback range
        
        fig.update_layout(
            title={
                'text': 'Enhanced DCA Modes: Historical Performance Comparison',
                'x': 0.5,
                'font': {'size': 18, 'color': 'white'}
            },
            xaxis_title='Date',
            yaxis_title='Portfolio Value ($)',
            hovermode='x unified',
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'},
            xaxis=dict(
                gridcolor='rgba(255,255,255,0.2)', 
                color='white',
                showgrid=True
            ),
            yaxis=dict(
                gridcolor='rgba(255,255,255,0.2)', 
                color='white',
                showgrid=True,
                range=[y_min, y_max],  # Set explicit range for optimal scaling
                tickformat='$,.0f'  # Format y-axis labels as currency
            ),
            legend=dict(
                yanchor="top",
                y=0.99,
                xanchor="left", 
                x=0.01,
                bgcolor='rgba(0,0,0,0.7)',
                bordercolor='rgba(255,255,255,0.3)',
                borderwidth=1
            ),
            height=500,  # Set explicit height for better visibility
            margin=dict(l=80, r=40, t=80, b=60)  # Adjust margins for better label visibility
        )
        
        return fig
    
    def _calculate_summary_metrics(self, performance_data: Dict) -> Dict[str, Any]:
        """Calculate summary performance metrics for each mode"""
        
        metrics = {}
        
        for mode, data in performance_data.items():
            if 'portfolio_values' in data:
                values = data['portfolio_values']
                if len(values) > 1:
                    total_return = (values[-1] - values[0]) / values[0]
                    
                    # Calculate annualized return (approximate)
                    years = len(values) / 365.25
                    annualized_return = (values[-1] / values[0]) ** (1/years) - 1 if years > 0 else 0
                    
                    # Calculate volatility (simplified)
                    daily_returns = np.diff(values) / values[:-1]
                    volatility = np.std(daily_returns) * np.sqrt(365.25) if len(daily_returns) > 0 else 0
                    
                    # Sharpe ratio (simplified, assuming 2% risk-free rate)
                    sharpe_ratio = (annualized_return - 0.02) / volatility if volatility > 0 else 0
                    
                    metrics[mode] = {
                        'final_value': values[-1],
                        'total_return': total_return,
                        'annualized_return': annualized_return,
                        'volatility': volatility,
                        'sharpe_ratio': sharpe_ratio
                    }
        
        return metrics
    
    def _generate_simplified_monthly_stats(self, price_data: pd.Series) -> Dict[str, Any]:
        """Generate simplified monthly statistics for performance analysis"""
        
        try:
            # Calculate monthly returns
            monthly_prices = price_data.resample('ME').last()  # Use 'ME' instead of deprecated 'M'
            monthly_returns = monthly_prices.pct_change().dropna()
            
            # Group by month name
            monthly_stats = {}
            for month in range(1, 13):
                month_name = calendar.month_name[month]
                month_data = monthly_returns[monthly_returns.index.month == month]
                
                if len(month_data) > 0:
                    monthly_stats[month_name] = {
                        'mean_return': float(month_data.mean()),
                        'volatility': float(month_data.std()),
                        'count': len(month_data)
                    }
                else:
                    monthly_stats[month_name] = {
                        'mean_return': 0.0,
                        'volatility': 0.1,
                        'count': 0
                    }
            
            # Calculate multipliers (simplified)
            multipliers = {}
            for month_name, stats in monthly_stats.items():
                # Simple multiplier based on historical performance
                if stats['mean_return'] > 0:
                    multipliers[month_name] = 1.0 + stats['mean_return']
                else:
                    multipliers[month_name] = 1.0
            
            return {
                'monthly_returns': {k: v['mean_return'] for k, v in monthly_stats.items()},
                'monthly_volatility': {k: v['volatility'] for k, v in monthly_stats.items()},
                'monthly_multipliers': multipliers
            }
            
        except Exception as e:
            # Fallback to default values
            months = ["January","February","March","April","May","June",
                     "July","August","September","October","November","December"]
            
            return {
                'monthly_returns': {month: 0.02 for month in months},
                'monthly_volatility': {month: 0.15 for month in months},
                'monthly_multipliers': {month: 1.0 for month in months}
            }