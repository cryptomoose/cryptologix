"""
Portfolio Optimization for Cryptologix
Dynamic portfolio allocation and rebalancing recommendations
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

class PortfolioOptimizer:
    
    def calculate_optimal_allocation(self, crypto_data, gold_data, risk_tolerance='medium'):
        """Calculate optimal portfolio allocation using risk-adjusted returns"""
        
        if gold_data is None or gold_data.empty:
            return None
        
        # Align data
        crypto_prices = crypto_data['Close']
        gold_prices = gold_data['Close']
        
        common_start = max(crypto_prices.index[0], gold_prices.index[0])
        common_end = min(crypto_prices.index[-1], gold_prices.index[-1])
        
        crypto_aligned = crypto_prices[(crypto_prices.index >= common_start) & (crypto_prices.index <= common_end)]
        gold_aligned = gold_prices[(gold_prices.index >= common_start) & (gold_prices.index <= common_end)]
        
        if len(crypto_aligned) < 100 or len(gold_aligned) < 100:
            return None
        
        # Calculate returns
        crypto_returns = crypto_aligned.pct_change().dropna()
        gold_returns = gold_aligned.pct_change().dropna()
        
        # Align returns
        common_dates = crypto_returns.index.intersection(gold_returns.index)
        crypto_returns = crypto_returns[common_dates]
        gold_returns = gold_returns[common_dates]
        
        # Calculate metrics
        crypto_mean_return = crypto_returns.mean() * 365
        gold_mean_return = gold_returns.mean() * 365
        crypto_volatility = crypto_returns.std() * np.sqrt(365)
        gold_volatility = gold_returns.std() * np.sqrt(365)
        correlation = crypto_returns.corr(gold_returns)
        
        # Risk tolerance mapping
        risk_multipliers = {
            'conservative': 0.5,
            'medium': 1.0,
            'aggressive': 1.5
        }
        
        risk_multiplier = risk_multipliers.get(risk_tolerance, 1.0)
        
        # Simple portfolio optimization using Sharpe ratios
        crypto_sharpe = crypto_mean_return / crypto_volatility if crypto_volatility > 0 else 0
        gold_sharpe = gold_mean_return / gold_volatility if gold_volatility > 0 else 0
        
        # Adjust for risk tolerance
        adjusted_crypto_sharpe = crypto_sharpe * risk_multiplier
        adjusted_gold_sharpe = gold_sharpe
        
        # Calculate weights
        total_sharpe = abs(adjusted_crypto_sharpe) + abs(adjusted_gold_sharpe)
        
        if total_sharpe > 0:
            crypto_weight = abs(adjusted_crypto_sharpe) / total_sharpe
            gold_weight = abs(adjusted_gold_sharpe) / total_sharpe
        else:
            crypto_weight = 0.6  # Default allocation
            gold_weight = 0.4
        
        # Apply correlation adjustment
        if abs(correlation) > 0.7:  # High correlation reduces diversification benefit
            # Move towards less correlated allocation
            crypto_weight = crypto_weight * 0.8
            gold_weight = gold_weight * 1.2
        
        # Normalize weights
        total_weight = crypto_weight + gold_weight
        crypto_weight = crypto_weight / total_weight
        gold_weight = gold_weight / total_weight
        
        # Apply risk tolerance bounds
        if risk_tolerance == 'conservative':
            crypto_weight = min(crypto_weight, 0.4)  # Max 40% crypto
        elif risk_tolerance == 'aggressive':
            crypto_weight = max(crypto_weight, 0.6)  # Min 60% crypto
        
        gold_weight = 1 - crypto_weight
        
        return {
            'crypto_allocation': crypto_weight * 100,
            'gold_allocation': gold_weight * 100,
            'crypto_sharpe': crypto_sharpe,
            'gold_sharpe': gold_sharpe,
            'correlation': correlation,
            'expected_annual_return': (crypto_weight * crypto_mean_return + gold_weight * gold_mean_return) * 100,
            'expected_volatility': np.sqrt(
                (crypto_weight ** 2) * (crypto_volatility ** 2) +
                (gold_weight ** 2) * (gold_volatility ** 2) +
                2 * crypto_weight * gold_weight * correlation * crypto_volatility * gold_volatility
            ) * 100,
            'risk_tolerance': risk_tolerance
        }
    
    def generate_rebalancing_signals(self, current_allocation, optimal_allocation, threshold=5):
        """Generate rebalancing recommendations"""
        
        if not optimal_allocation:
            return None
        
        crypto_current = current_allocation.get('crypto_percent', 50)
        crypto_optimal = optimal_allocation['crypto_allocation']
        
        difference = abs(crypto_current - crypto_optimal)
        
        if difference > threshold:
            if crypto_current > crypto_optimal:
                action = 'REDUCE_CRYPTO'
                description = f"Reduce crypto allocation by {difference:.1f}% (from {crypto_current:.1f}% to {crypto_optimal:.1f}%)"
            else:
                action = 'INCREASE_CRYPTO'
                description = f"Increase crypto allocation by {difference:.1f}% (from {crypto_current:.1f}% to {crypto_optimal:.1f}%)"
            
            return {
                'action': action,
                'rebalance_needed': True,
                'current_crypto': crypto_current,
                'target_crypto': crypto_optimal,
                'difference': difference,
                'description': description,
                'urgency': 'HIGH' if difference > 15 else 'MEDIUM' if difference > 10 else 'LOW'
            }
        
        return {
            'action': 'HOLD',
            'rebalance_needed': False,
            'current_crypto': crypto_current,
            'target_crypto': crypto_optimal,
            'difference': difference,
            'description': f"Portfolio is well-balanced (difference: {difference:.1f}%)",
            'urgency': 'NONE'
        }
    
    def calculate_dollar_cost_averaging(self, historical_data, investment_amount=1000, frequency='monthly'):
        """Calculate DCA strategy performance"""
        
        if len(historical_data) < 100:
            return None
        
        # Determine investment frequency
        freq_days = {'weekly': 7, 'monthly': 30, 'quarterly': 90}
        days_between = freq_days.get(frequency, 30)
        
        # Sample data at regular intervals
        investment_dates = []
        current_date = historical_data.index[days_between]
        
        while current_date <= historical_data.index[-1]:
            investment_dates.append(current_date)
            # Find next investment date
            next_idx = historical_data.index.get_loc(current_date) + days_between
            if next_idx < len(historical_data):
                current_date = historical_data.index[next_idx]
            else:
                break
        
        # Calculate DCA performance
        total_invested = 0
        total_shares = 0
        investments = []
        
        for date in investment_dates:
            price = historical_data.loc[date, 'Close']
            shares_bought = investment_amount / price
            total_invested += investment_amount
            total_shares += shares_bought
            
            investments.append({
                'date': date,
                'price': price,
                'amount': investment_amount,
                'shares': shares_bought
            })
        
        if total_shares > 0:
            current_price = historical_data['Close'].iloc[-1]
            current_value = total_shares * current_price
            total_return = ((current_value - total_invested) / total_invested) * 100
            average_price = total_invested / total_shares
            
            return {
                'strategy': f'DCA {frequency}',
                'total_invested': total_invested,
                'current_value': current_value,
                'total_return_percent': total_return,
                'total_return_amount': current_value - total_invested,
                'average_purchase_price': average_price,
                'current_price': current_price,
                'number_of_investments': len(investments),
                'investment_period_days': (investment_dates[-1] - investment_dates[0]).days,
                'next_investment_recommendation': investment_amount
            }
        
        return None
    
    def generate_tax_optimization_advice(self, crypto_data, holding_period_days=365):
        """Generate tax-optimized trading advice"""
        
        current_price = crypto_data['Close'].iloc[-1]
        
        # Long-term vs short-term capital gains consideration
        advice = {
            'holding_period_days': holding_period_days,
            'recommendations': []
        }
        
        if holding_period_days < 365:
            advice['recommendations'].append({
                'type': 'tax_timing',
                'description': f'Consider holding for {365 - holding_period_days} more days for long-term capital gains treatment',
                'benefit': 'Potential tax savings of 10-20% on gains'
            })
        
        # Calculate potential tax-loss harvesting opportunities
        if len(crypto_data) > 30:
            recent_high = crypto_data['High'].tail(30).max()
            unrealized_loss_percent = ((current_price - recent_high) / recent_high) * 100
            
            if unrealized_loss_percent < -10:
                advice['recommendations'].append({
                    'type': 'tax_loss_harvesting',
                    'description': f'Consider tax-loss harvesting with {abs(unrealized_loss_percent):.1f}% unrealized loss',
                    'benefit': 'Offset capital gains and reduce tax liability'
                })
        
        # End-of-year timing considerations
        current_month = datetime.now().month
        if current_month >= 11:  # November/December
            advice['recommendations'].append({
                'type': 'year_end_planning',
                'description': 'Consider year-end tax planning strategies',
                'benefit': 'Optimize timing of gains/losses for current tax year'
            })
        
        return advice if advice['recommendations'] else None