import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class BacktestingFramework:
    """Comprehensive backtesting framework for cryptocurrency trading strategies"""
    
    def __init__(self):
        self.initial_capital = 10000
        self.commission_rate = 0.001  # 0.1% trading fee
        self.slippage = 0.0005  # 0.05% slippage
    
    def backtest_cycle_strategy(self, df: pd.DataFrame, cycles: List[Dict], 
                               strategy_params: Dict = None) -> Dict:
        """
        Backtest a market cycle-based trading strategy
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
            cycles (List[Dict]): Identified market cycles
            strategy_params (Dict): Strategy parameters
        
        Returns:
            Dict: Backtesting results
        """
        if strategy_params is None:
            strategy_params = {
                'bull_entry_threshold': 0.05,  # Enter on 5% cycle confirmation
                'bear_exit_threshold': -0.03,  # Exit on 3% cycle reversal
                'max_position_size': 0.8,      # Maximum 80% portfolio allocation
                'stop_loss': -0.15,            # 15% stop loss
                'take_profit': 0.50            # 50% take profit
            }
        
        # Initialize portfolio
        portfolio = {
            'cash': self.initial_capital,
            'crypto_holdings': 0,
            'total_value': self.initial_capital,
            'trades': [],
            'positions': []
        }
        
        # Process each cycle
        for cycle in cycles:
            cycle_type = cycle.get('cycle_type', cycle.get('type', ''))
            if cycle_type in ['Strong Bull Market', 'Bull Market', 'Volatile Bull Market', 'Bull']:
                self._process_bull_cycle(df, cycle, portfolio, strategy_params)
            elif cycle_type in ['Strong Bear Market', 'Bear Market', 'Volatile Bear Market', 'Bear']:
                self._process_bear_cycle(df, cycle, portfolio, strategy_params)
        
        # Calculate final results
        final_price = df['Close'].iloc[-1]
        final_portfolio_value = portfolio['cash'] + (portfolio['crypto_holdings'] * final_price)
        
        return self._calculate_backtest_metrics(portfolio, final_portfolio_value, df)
    
    def _process_bull_cycle(self, df: pd.DataFrame, cycle: Dict, portfolio: Dict, params: Dict):
        """Process bull market cycle for backtesting"""
        cycle_start = cycle['start_date']
        cycle_end = cycle['end_date']
        
        # Find entry point (cycle confirmation)
        entry_data = df[(df.index >= cycle_start) & (df.index <= cycle_end)]
        if entry_data.empty:
            return
        
        entry_price = entry_data['Close'].iloc[0] * (1 + params['bull_entry_threshold'])
        entry_point = entry_data[entry_data['Close'] >= entry_price]
        
        if entry_point.empty:
            return
        
        entry_date = entry_point.index[0]
        entry_price = entry_point['Close'].iloc[0]
        
        # Calculate position size
        max_investment = portfolio['cash'] * params['max_position_size']
        shares_to_buy = max_investment / (entry_price * (1 + self.commission_rate + self.slippage))
        
        if shares_to_buy > 0:
            # Execute buy order
            cost = shares_to_buy * entry_price * (1 + self.commission_rate + self.slippage)
            portfolio['cash'] -= cost
            portfolio['crypto_holdings'] += shares_to_buy
            
            # Record trade
            portfolio['trades'].append({
                'date': entry_date,
                'type': 'BUY',
                'shares': shares_to_buy,
                'price': entry_price,
                'cost': cost,
                'reason': 'Bull cycle entry'
            })
            
            # Look for exit signals
            self._look_for_exit_signals(df, entry_date, cycle_end, portfolio, params, entry_price)
    
    def _process_bear_cycle(self, df: pd.DataFrame, cycle: Dict, portfolio: Dict, params: Dict):
        """Process bear market cycle for backtesting"""
        if portfolio['crypto_holdings'] <= 0:
            return
        
        cycle_start = cycle['start_date']
        cycle_end = cycle['end_date']
        
        # Find exit point (bear cycle confirmation)
        exit_data = df[(df.index >= cycle_start) & (df.index <= cycle_end)]
        if exit_data.empty:
            return
        
        exit_price = exit_data['Close'].iloc[0] * (1 + params['bear_exit_threshold'])
        exit_point = exit_data[exit_data['Close'] <= exit_price]
        
        if not exit_point.empty:
            exit_date = exit_point.index[0]
            exit_price = exit_point['Close'].iloc[0]
            
            # Execute sell order
            proceeds = portfolio['crypto_holdings'] * exit_price * (1 - self.commission_rate - self.slippage)
            portfolio['cash'] += proceeds
            
            # Record trade
            portfolio['trades'].append({
                'date': exit_date,
                'type': 'SELL',
                'shares': portfolio['crypto_holdings'],
                'price': exit_price,
                'proceeds': proceeds,
                'reason': 'Bear cycle exit'
            })
            
            portfolio['crypto_holdings'] = 0
    
    def _look_for_exit_signals(self, df: pd.DataFrame, entry_date: pd.Timestamp, 
                              cycle_end: pd.Timestamp, portfolio: Dict, params: Dict, entry_price: float):
        """Look for exit signals during a position"""
        if portfolio['crypto_holdings'] <= 0:
            return
        
        exit_data = df[(df.index > entry_date) & (df.index <= cycle_end)]
        
        for date, row in exit_data.iterrows():
            current_price = row['Close']
            return_pct = (current_price - entry_price) / entry_price
            
            # Check stop loss
            if return_pct <= params['stop_loss']:
                self._execute_sell(portfolio, date, current_price, 'Stop loss')
                break
            
            # Check take profit
            elif return_pct >= params['take_profit']:
                self._execute_sell(portfolio, date, current_price, 'Take profit')
                break
    
    def _execute_sell(self, portfolio: Dict, date: pd.Timestamp, price: float, reason: str):
        """Execute a sell order"""
        if portfolio['crypto_holdings'] <= 0:
            return
        
        proceeds = portfolio['crypto_holdings'] * price * (1 - self.commission_rate - self.slippage)
        portfolio['cash'] += proceeds
        
        portfolio['trades'].append({
            'date': date,
            'type': 'SELL',
            'shares': portfolio['crypto_holdings'],
            'price': price,
            'proceeds': proceeds,
            'reason': reason
        })
        
        portfolio['crypto_holdings'] = 0
    
    def _calculate_backtest_metrics(self, portfolio: Dict, final_value: float, df: pd.DataFrame) -> Dict:
        """Calculate comprehensive backtesting metrics"""
        trades_df = pd.DataFrame(portfolio['trades']) if portfolio['trades'] else pd.DataFrame()
        
        if trades_df.empty:
            return {
                'total_return': 0,
                'annualized_return': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'profit_factor': 0,
                'num_trades': 0,
                'avg_trade_return': 0
            }
        
        # Basic metrics
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100
        
        # Calculate trade-by-trade returns
        trade_returns = []
        buy_trades = trades_df[trades_df['type'] == 'BUY']
        sell_trades = trades_df[trades_df['type'] == 'SELL']
        
        for i in range(min(len(buy_trades), len(sell_trades))):
            buy_cost = buy_trades.iloc[i]['cost']
            sell_proceeds = sell_trades.iloc[i]['proceeds']
            trade_return = ((sell_proceeds - buy_cost) / buy_cost) * 100
            trade_returns.append(trade_return)
        
        # Performance metrics
        if trade_returns:
            winning_trades = [r for r in trade_returns if r > 0]
            losing_trades = [r for r in trade_returns if r < 0]
            
            win_rate = (len(winning_trades) / len(trade_returns)) * 100 if trade_returns else 0
            avg_win = np.mean(winning_trades) if winning_trades else 0
            avg_loss = np.mean(losing_trades) if losing_trades else 0
            profit_factor = abs(sum(winning_trades) / sum(losing_trades)) if losing_trades else float('inf')
            avg_trade_return = np.mean(trade_returns)
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            profit_factor = 0
            avg_trade_return = 0
        
        # Time-based metrics
        start_date = df.index[0]
        end_date = df.index[-1]
        days = (end_date - start_date).days
        years = days / 365.25
        
        annualized_return = ((final_value / self.initial_capital) ** (1 / years) - 1) * 100 if years > 0 else 0
        
        # Sharpe ratio (simplified - assuming 0% risk-free rate)
        if trade_returns:
            sharpe_ratio = (np.mean(trade_returns) / np.std(trade_returns)) * np.sqrt(len(trade_returns)) if len(trade_returns) > 1 else 0
        else:
            sharpe_ratio = 0
        
        # Maximum drawdown calculation
        portfolio_values = [self.initial_capital]
        current_value = self.initial_capital
        
        for _, trade in trades_df.iterrows():
            if trade['type'] == 'BUY':
                current_value -= trade['cost']
            else:
                current_value += trade['proceeds']
            portfolio_values.append(current_value)
        
        portfolio_values.append(final_value)
        
        # Calculate drawdown
        peak = portfolio_values[0]
        max_dd = 0
        for value in portfolio_values[1:]:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
        
        max_drawdown = max_dd * 100
        
        return {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'num_trades': len(trade_returns),
            'avg_trade_return': avg_trade_return,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': max(trade_returns) if trade_returns else 0,
            'worst_trade': min(trade_returns) if trade_returns else 0,
            'trades': portfolio['trades']
        }
    
    def monte_carlo_simulation(self, df: pd.DataFrame, strategy_results: Dict, 
                              num_simulations: int = 1000) -> Dict:
        """
        Run Monte Carlo simulation on strategy performance
        
        Args:
            df (pd.DataFrame): Historical price data
            strategy_results (Dict): Original strategy backtest results
            num_simulations (int): Number of simulations to run
        
        Returns:
            Dict: Monte Carlo simulation results
        """
        if not strategy_results.get('trades'):
            return {'error': 'No trades found for simulation'}
        
        trade_returns = []
        trades = strategy_results['trades']
        
        # Calculate historical trade returns
        for i in range(0, len(trades) - 1, 2):  # Pairs of buy/sell
            if i + 1 < len(trades) and trades[i]['type'] == 'BUY' and trades[i + 1]['type'] == 'SELL':
                buy_cost = trades[i]['cost']
                sell_proceeds = trades[i + 1]['proceeds']
                trade_return = (sell_proceeds - buy_cost) / buy_cost
                trade_returns.append(trade_return)
        
        if not trade_returns:
            return {'error': 'Insufficient trade data for simulation'}
        
        # Run simulations
        simulation_results = []
        
        for _ in range(num_simulations):
            # Randomly sample trade returns with replacement
            simulated_returns = np.random.choice(trade_returns, size=len(trade_returns), replace=True)
            
            # Calculate portfolio value evolution
            portfolio_value = self.initial_capital
            for ret in simulated_returns:
                portfolio_value *= (1 + ret)
            
            final_return = (portfolio_value - self.initial_capital) / self.initial_capital
            simulation_results.append(final_return * 100)
        
        # Calculate statistics
        simulation_results = np.array(simulation_results)
        
        return {
            'mean_return': np.mean(simulation_results),
            'median_return': np.median(simulation_results),
            'std_return': np.std(simulation_results),
            'var_95': np.percentile(simulation_results, 5),
            'var_99': np.percentile(simulation_results, 1),
            'probability_of_loss': (simulation_results < 0).mean() * 100,
            'probability_of_doubling': (simulation_results >= 100).mean() * 100,
            'best_case': np.max(simulation_results),
            'worst_case': np.min(simulation_results),
            'confidence_intervals': {
                '90%': [np.percentile(simulation_results, 5), np.percentile(simulation_results, 95)],
                '95%': [np.percentile(simulation_results, 2.5), np.percentile(simulation_results, 97.5)]
            }
        }
    
    def optimize_strategy_parameters(self, df: pd.DataFrame, cycles: List[Dict]) -> Dict:
        """
        Optimize strategy parameters using grid search
        
        Args:
            df (pd.DataFrame): Price data
            cycles (List[Dict]): Market cycles
        
        Returns:
            Dict: Optimization results
        """
        # Define parameter ranges
        param_ranges = {
            'bull_entry_threshold': [0.02, 0.05, 0.08, 0.10],
            'bear_exit_threshold': [-0.02, -0.03, -0.05, -0.08],
            'max_position_size': [0.5, 0.7, 0.8, 1.0],
            'stop_loss': [-0.10, -0.15, -0.20, -0.25],
            'take_profit': [0.25, 0.50, 0.75, 1.00]
        }
        
        best_sharpe = -float('inf')
        best_params = {}
        results = []
        
        # Grid search
        for bull_thresh in param_ranges['bull_entry_threshold']:
            for bear_thresh in param_ranges['bear_exit_threshold']:
                for pos_size in param_ranges['max_position_size']:
                    for stop_loss in param_ranges['stop_loss']:
                        for take_profit in param_ranges['take_profit']:
                            
                            params = {
                                'bull_entry_threshold': bull_thresh,
                                'bear_exit_threshold': bear_thresh,
                                'max_position_size': pos_size,
                                'stop_loss': stop_loss,
                                'take_profit': take_profit
                            }
                            
                            # Run backtest
                            result = self.backtest_cycle_strategy(df, cycles, params)
                            
                            # Store results
                            result['parameters'] = params.copy()
                            results.append(result)
                            
                            # Check if this is the best result
                            if result['sharpe_ratio'] > best_sharpe:
                                best_sharpe = result['sharpe_ratio']
                                best_params = params.copy()
        
        # Sort results by Sharpe ratio
        results.sort(key=lambda x: x['sharpe_ratio'], reverse=True)
        
        return {
            'best_parameters': best_params,
            'best_sharpe_ratio': best_sharpe,
            'optimization_results': results[:10],  # Top 10 results
            'total_combinations_tested': len(results)
        }