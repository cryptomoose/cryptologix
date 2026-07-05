import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

def format_number(number: Union[int, float], decimals: int = 2, prefix: str = "", suffix: str = "") -> str:
    """
    Format numbers for display with appropriate suffixes (K, M, B, T)
    
    Args:
        number (Union[int, float]): Number to format
        decimals (int): Number of decimal places
        prefix (str): Prefix to add (e.g., "$")
        suffix (str): Suffix to add (e.g., "%")
    
    Returns:
        str: Formatted number string
    """
    if pd.isna(number) or number is None:
        return "N/A"
    
    try:
        number = float(number)
    except (ValueError, TypeError):
        return "N/A"
    
    # Handle negative numbers
    is_negative = number < 0
    abs_number = abs(number)
    
    # Define suffixes
    suffixes = ['', 'K', 'M', 'B', 'T']
    
    # Determine appropriate suffix
    magnitude = 0
    while abs_number >= 1000 and magnitude < len(suffixes) - 1:
        abs_number /= 1000
        magnitude += 1
    
    # Format the number
    if magnitude == 0:
        # No suffix needed
        formatted = f"{abs_number:.{decimals}f}"
    else:
        # Use suffix
        formatted = f"{abs_number:.{decimals}f}{suffixes[magnitude]}"
    
    # Add negative sign back if needed
    if is_negative:
        formatted = f"-{formatted}"
    
    return f"{prefix}{formatted}{suffix}"

def format_currency(amount: Union[int, float], currency: str = "USD") -> str:
    """
    Format currency amounts
    
    Args:
        amount (Union[int, float]): Amount to format
        currency (str): Currency code
    
    Returns:
        str: Formatted currency string
    """
    if currency.upper() == "USD":
        return format_number(amount, decimals=2, prefix="$")
    else:
        return f"{format_number(amount, decimals=2)} {currency}"

_PRESERVE_UPPER_TOKENS = {'usd', 'btc', 'eth', 'sol', 'dca', 'apy', 'apr', 'tvl'}


def format_action_label(label: str) -> str:
    """
    Title-case a snake_case or space-separated label, keeping known
    ticker/acronym tokens (USD, BTC, ETH, SOL, DCA, APY, APR, TVL) uppercase
    instead of Python's .title()/.capitalize() mangling them (e.g. "Usd").

    Args:
        label (str): Raw label, e.g. "deploy_usd_aggressively"

    Returns:
        str: Formatted label, e.g. "Deploy USD Aggressively"
    """
    words = label.replace('_', ' ').split()
    return ' '.join(
        w.upper() if w.lower() in _PRESERVE_UPPER_TOKENS else w.capitalize()
        for w in words
    )


def format_percentage(value: Union[int, float], decimals: int = 2) -> str:
    """
    Format percentage values
    
    Args:
        value (Union[int, float]): Percentage value
        decimals (int): Number of decimal places
    
    Returns:
        str: Formatted percentage string
    """
    return format_number(value, decimals=decimals, suffix="%")

def calculate_performance_metrics(df: pd.DataFrame, benchmark_col: str = 'Close') -> Dict:
    """
    Calculate various performance metrics for a price series
    
    Args:
        df (pd.DataFrame): DataFrame with price data
        benchmark_col (str): Column name for benchmark prices
    
    Returns:
        Dict: Performance metrics
    """
    if df.empty or benchmark_col not in df.columns:
        return {}
    
    prices = df[benchmark_col].dropna()
    
    if len(prices) < 2:
        return {}
    
    # Calculate returns
    returns = prices.pct_change().dropna()
    
    if len(returns) == 0:
        return {}
    
    # Basic metrics
    total_return = (prices.iloc[-1] / prices.iloc[0] - 1) * 100
    
    # Annualized metrics
    trading_days = len(returns)
    years = trading_days / 252  # Assuming 252 trading days per year
    
    if years > 0:
        annualized_return = (((prices.iloc[-1] / prices.iloc[0]) ** (1/years)) - 1) * 100
    else:
        annualized_return = 0
    
    # Volatility
    daily_volatility = returns.std()
    annualized_volatility = daily_volatility * np.sqrt(252) * 100
    
    # Sharpe ratio (assuming 0% risk-free rate)
    if daily_volatility != 0:
        sharpe_ratio = (returns.mean() / daily_volatility) * np.sqrt(252)
    else:
        sharpe_ratio = 0
    
    # Maximum drawdown
    cumulative_returns = (1 + returns).cumprod()
    running_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - running_max) / running_max
    max_drawdown = drawdown.min() * 100
    
    # Calmar ratio (annualized return / max drawdown)
    if max_drawdown != 0:
        calmar_ratio = abs(annualized_return / max_drawdown)
    else:
        calmar_ratio = 0
    
    # Win rate
    positive_returns = returns[returns > 0]
    win_rate = (len(positive_returns) / len(returns)) * 100 if len(returns) > 0 else 0
    
    # Average win/loss
    avg_win = positive_returns.mean() * 100 if len(positive_returns) > 0 else 0
    negative_returns = returns[returns < 0]
    avg_loss = negative_returns.mean() * 100 if len(negative_returns) > 0 else 0
    
    # Profit factor
    total_wins = positive_returns.sum()
    total_losses = abs(negative_returns.sum())
    profit_factor = total_wins / total_losses if total_losses != 0 else float('inf')
    
    # Value at Risk (VaR) - 95% confidence level
    var_95 = np.percentile(returns, 5) * 100
    
    # Expected Shortfall (Conditional VaR)
    cvar_95 = returns[returns <= np.percentile(returns, 5)].mean() * 100
    
    # Skewness and Kurtosis
    skewness = returns.skew()
    kurtosis = returns.kurtosis()
    
    return {
        'total_return': total_return,
        'annualized_return': annualized_return,
        'volatility': annualized_volatility,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'calmar_ratio': calmar_ratio,
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'var_95': var_95,
        'cvar_95': cvar_95,
        'skewness': skewness,
        'kurtosis': kurtosis,
        'trading_days': trading_days,
        'years': years
    }

def calculate_correlation_metrics(df1: pd.DataFrame, df2: pd.DataFrame, col1: str = 'Close', col2: str = 'Close') -> Dict:
    """
    Calculate correlation metrics between two price series
    
    Args:
        df1 (pd.DataFrame): First DataFrame
        df2 (pd.DataFrame): Second DataFrame  
        col1 (str): Column name in first DataFrame
        col2 (str): Column name in second DataFrame
    
    Returns:
        Dict: Correlation metrics
    """
    if df1.empty or df2.empty or col1 not in df1.columns or col2 not in df2.columns:
        return {}
    
    # Align dates and get overlapping period
    common_dates = df1.index.intersection(df2.index)
    
    if len(common_dates) < 10:  # Need minimum data points
        return {}
    
    series1 = df1.loc[common_dates, col1]
    series2 = df2.loc[common_dates, col2]
    
    # Calculate returns
    returns1 = series1.pct_change().dropna()
    returns2 = series2.pct_change().dropna()
    
    # Align returns
    common_return_dates = returns1.index.intersection(returns2.index)
    returns1 = returns1.loc[common_return_dates]
    returns2 = returns2.loc[common_return_dates]
    
    if len(returns1) < 5:
        return {}
    
    # Pearson correlation
    correlation = returns1.corr(returns2)
    
    # Rolling correlation (30-day)
    rolling_corr = returns1.rolling(window=30).corr(returns2)
    avg_rolling_corr = rolling_corr.mean()
    
    # Beta (series1 relative to series2)
    covariance = np.cov(returns1, returns2)[0][1]
    variance2 = np.var(returns2)
    beta = covariance / variance2 if variance2 != 0 else 0
    
    return {
        'correlation': correlation,
        'avg_rolling_correlation': avg_rolling_corr,
        'beta': beta,
        'covariance': covariance,
        'r_squared': correlation ** 2
    }

def detect_outliers(series: pd.Series, method: str = 'iqr', threshold: float = 1.5) -> pd.Series:
    """
    Detect outliers in a data series
    
    Args:
        series (pd.Series): Data series
        method (str): Method to use ('iqr', 'zscore', 'modified_zscore')
        threshold (float): Threshold for outlier detection
    
    Returns:
        pd.Series: Boolean series indicating outliers
    """
    if series.empty:
        return pd.Series(dtype=bool)
    
    if method == 'iqr':
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - threshold * IQR
        upper_bound = Q3 + threshold * IQR
        outliers = (series < lower_bound) | (series > upper_bound)
        
    elif method == 'zscore':
        z_scores = np.abs((series - series.mean()) / series.std())
        outliers = z_scores > threshold
        
    elif method == 'modified_zscore':
        median = series.median()
        mad = np.median(np.abs(series - median))
        modified_z_scores = 0.6745 * (series - median) / mad
        outliers = np.abs(modified_z_scores) > threshold
        
    else:
        raise ValueError("Method must be 'iqr', 'zscore', or 'modified_zscore'")
    
    return outliers

def calculate_support_resistance_strength(prices: pd.Series, level: float, tolerance: float = 0.02) -> Dict:
    """
    Calculate the strength of a support or resistance level
    
    Args:
        prices (pd.Series): Price series
        level (float): Support/resistance level
        tolerance (float): Tolerance as percentage of level
    
    Returns:
        Dict: Strength metrics
    """
    if prices.empty:
        return {}
    
    # Define the range around the level
    lower_bound = level * (1 - tolerance)
    upper_bound = level * (1 + tolerance)
    
    # Count touches
    touches = prices[(prices >= lower_bound) & (prices <= upper_bound)]
    touch_count = len(touches)
    
    # Calculate time span of touches
    if touch_count > 1:
        first_touch = touches.index[0]
        last_touch = touches.index[-1]
        time_span = (last_touch - first_touch).days
    else:
        time_span = 0
    
    # Calculate average volume at level (if available)
    # This would require volume data to be passed separately
    
    # Strength score (0-100)
    touch_score = min(touch_count * 10, 50)  # Max 50 points for touches
    time_score = min(time_span / 30 * 25, 25)  # Max 25 points for time span
    consistency_score = 25 if touch_count >= 3 else touch_count * 8  # Max 25 points
    
    strength_score = touch_score + time_score + consistency_score
    
    return {
        'strength_score': strength_score,
        'touch_count': touch_count,
        'time_span_days': time_span,
        'level': level,
        'first_touch': touches.index[0] if touch_count > 0 else None,
        'last_touch': touches.index[-1] if touch_count > 0 else None
    }

def calculate_trend_strength(prices: pd.Series, window: int = 20) -> Dict:
    """
    Calculate trend strength metrics
    
    Args:
        prices (pd.Series): Price series
        window (int): Window for calculations
    
    Returns:
        Dict: Trend strength metrics
    """
    if len(prices) < window:
        return {}
    
    # Linear regression slope
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices.values, 1)
    
    # R-squared
    y_pred = slope * x + intercept
    ss_res = np.sum((prices.values - y_pred) ** 2)
    ss_tot = np.sum((prices.values - np.mean(prices.values)) ** 2)
    r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
    
    # Trend direction
    trend_direction = 'UPTREND' if slope > 0 else 'DOWNTREND'
    
    # Average Directional Index (ADX) approximation
    # Simplified calculation without true range
    price_changes = prices.diff().abs()
    avg_change = price_changes.rolling(window=window).mean().iloc[-1]
    
    # Trend strength classification
    if r_squared > 0.8:
        strength = 'VERY_STRONG'
    elif r_squared > 0.6:
        strength = 'STRONG'
    elif r_squared > 0.4:
        strength = 'MODERATE'
    elif r_squared > 0.2:
        strength = 'WEAK'
    else:
        strength = 'NO_TREND'
    
    return {
        'slope': slope,
        'r_squared': r_squared,
        'trend_direction': trend_direction,
        'strength_category': strength,
        'avg_change': avg_change,
        'trend_angle': np.degrees(np.arctan(slope))
    }

def validate_data_integrity(df: pd.DataFrame) -> Dict:
    """
    Validate data integrity and quality
    
    Args:
        df (pd.DataFrame): DataFrame to validate
    
    Returns:
        Dict: Validation results
    """
    results = {
        'is_valid': True,
        'issues': [],
        'warnings': [],
        'metrics': {}
    }
    
    if df.empty:
        results['is_valid'] = False
        results['issues'].append('DataFrame is empty')
        return results
    
    # Check for required columns
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        results['is_valid'] = False
        results['issues'].append(f'Missing required columns: {missing_cols}')
    
    # Check for negative prices
    price_cols = ['Open', 'High', 'Low', 'Close']
    for col in price_cols:
        if col in df.columns and (df[col] <= 0).any():
            results['issues'].append(f'Invalid prices in {col} column (negative or zero values)')
            results['is_valid'] = False
    
    # Check for logical price relationships
    if all(col in df.columns for col in ['High', 'Low', 'Close']):
        invalid_high_low = df['High'] < df['Low']
        if invalid_high_low.any():
            results['issues'].append('High prices lower than Low prices detected')
            results['is_valid'] = False
        
        invalid_close = (df['Close'] > df['High']) | (df['Close'] < df['Low'])
        if invalid_close.any():
            results['issues'].append('Close prices outside High-Low range detected')
            results['is_valid'] = False
    
    # Check for missing data
    null_counts = df.isnull().sum()
    total_nulls = null_counts.sum()
    
    if total_nulls > 0:
        results['warnings'].append(f'Missing data points: {total_nulls}')
        results['metrics']['null_percentage'] = (total_nulls / df.size) * 100
    
    # Check for duplicate dates
    if df.index.duplicated().any():
        results['warnings'].append('Duplicate dates found in index')
        results['metrics']['duplicate_dates'] = df.index.duplicated().sum()
    
    # Check data continuity
    if hasattr(df.index, 'freq') or len(df) > 1:
        date_diffs = df.index.to_series().diff().dt.days.dropna()
        large_gaps = date_diffs[date_diffs > 3]  # Gaps larger than 3 days
        
        if not large_gaps.empty:
            results['warnings'].append(f'Large data gaps detected: {len(large_gaps)} gaps > 3 days')
            results['metrics']['max_gap_days'] = large_gaps.max()
    
    # Data quality metrics
    results['metrics'].update({
        'total_records': len(df),
        'date_range': f"{df.index.min()} to {df.index.max()}",
        'columns': list(df.columns),
        'data_types': df.dtypes.to_dict()
    })
    
    return results

def create_summary_statistics(df: pd.DataFrame, price_col: str = 'Close') -> Dict:
    """
    Create comprehensive summary statistics
    
    Args:
        df (pd.DataFrame): DataFrame with price data
        price_col (str): Column name for price analysis
    
    Returns:
        Dict: Summary statistics
    """
    if df.empty or price_col not in df.columns:
        return {}
    
    prices = df[price_col].dropna()
    
    if len(prices) == 0:
        return {}
    
    # Basic statistics
    stats = {
        'count': len(prices),
        'mean': prices.mean(),
        'median': prices.median(),
        'std': prices.std(),
        'min': prices.min(),
        'max': prices.max(),
        'range': prices.max() - prices.min(),
        'skewness': prices.skew(),
        'kurtosis': prices.kurtosis()
    }
    
    # Percentiles
    percentiles = [5, 10, 25, 75, 90, 95]
    for p in percentiles:
        stats[f'percentile_{p}'] = prices.quantile(p / 100)
    
    # Recent performance
    if len(prices) >= 30:
        stats['30d_return'] = (prices.iloc[-1] / prices.iloc[-30] - 1) * 100
    
    if len(prices) >= 7:
        stats['7d_return'] = (prices.iloc[-1] / prices.iloc[-7] - 1) * 100
    
    if len(prices) >= 1:
        stats['1d_return'] = (prices.iloc[-1] / prices.iloc[-2] - 1) * 100 if len(prices) >= 2 else 0
    
    # Volatility metrics
    if len(prices) >= 2:
        returns = prices.pct_change().dropna()
        stats['daily_volatility'] = returns.std() * 100
        stats['annualized_volatility'] = returns.std() * np.sqrt(252) * 100
    
    return stats
