"""
Comparison Charts Module for Crypto vs Precious Metals Analysis
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import streamlit as st
from long_term_data_fetcher import LongTermDataFetcher
from rotation_optimizer import RotationRecommendationEngine
import disk_cache

# Cached data fetching functions (standalone for better caching)
@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_crypto_data_cached(symbol):
    """Cache crypto data - 24h Streamlit TTL + disk persistence for cold starts"""
    cache_key = f'chart_crypto_{symbol}'
    data = disk_cache.load(cache_key, max_age_hours=24)
    if data is not None:
        return data
    fetcher = LongTermDataFetcher()
    data = fetcher.get_comprehensive_crypto_data(symbol)
    if data is not None:
        disk_cache.save(cache_key, data)
    return data

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_metal_data_cached(symbol):
    """Cache metal data - 24h Streamlit TTL + disk persistence for cold starts"""
    cache_key = f'chart_metal_{symbol}'
    data = disk_cache.load(cache_key, max_age_hours=24)
    if data is not None:
        return data
    fetcher = LongTermDataFetcher()
    if symbol.endswith('=F'):
        data = fetcher.get_yahoo_finance_max_data(symbol)
    else:
        data = fetcher.get_comprehensive_gold_data()
    if data is not None:
        disk_cache.save(cache_key, data)
    return data


class ComparisonChartBuilder:
    """Build comprehensive comparison charts for crypto vs precious metals"""
    
    def __init__(self):
        self.data_fetcher = LongTermDataFetcher()
        self.rotation_engine = RotationRecommendationEngine()
    
    def calculate_ratio(self, crypto_data, metal_data):
        """Calculate crypto/metal price ratio"""
        # Align data by date
        df_crypto = crypto_data[['Close']].copy()
        df_metal = metal_data[['Close']].copy()
        
        # Normalize indexes to date only (remove time component)
        df_crypto.index = pd.to_datetime(df_crypto.index).normalize()
        df_metal.index = pd.to_datetime(df_metal.index).normalize()
        
        # Remove timezone information to allow proper join
        if df_crypto.index.tz is not None:
            df_crypto.index = df_crypto.index.tz_localize(None)
        if df_metal.index.tz is not None:
            df_metal.index = df_metal.index.tz_localize(None)
        
        # Rename columns
        df_crypto.columns = ['crypto_price']
        df_metal.columns = ['metal_price']
        
        # Merge on date index
        merged = df_crypto.join(df_metal, how='inner')
        
        # Calculate ratio
        merged['ratio'] = merged['crypto_price'] / merged['metal_price']
        
        return merged
    
    def add_technical_indicators(self, df):
        """Add technical indicators to ratio data"""
        # Moving averages
        df['MA50'] = df['ratio'].rolling(window=50).mean()
        df['MA200'] = df['ratio'].rolling(window=200).mean()
        
        # Bollinger Bands
        df['BB_middle'] = df['ratio'].rolling(window=50).mean()
        df['BB_std'] = df['ratio'].rolling(window=50).std()
        df['BB_upper'] = df['BB_middle'] + (df['BB_std'] * 2)
        df['BB_lower'] = df['BB_middle'] - (df['BB_std'] * 2)
        
        # RSI
        delta = df['ratio'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Percentile (relative valuation) - FIXED: correct calculation to reach 0/100 at extremes
        df['percentile'] = df['ratio'].rolling(window=252).apply(
            lambda x: (x.iloc[-1] >= x).sum() / len(x) * 100 if len(x) > 0 else 50
        )
        
        return df
    
    def create_comparison_chart(self, crypto_symbol, metal_symbol, crypto_name, metal_name):
        """Create comprehensive comparison chart with 3 subplots
        
        Returns: (fig, ratio_data) tuple to avoid redundant fetching
        """
        
        try:
            # Fetch data using cached functions
            crypto_data = _fetch_crypto_data_cached(crypto_symbol)
            if crypto_data is None:
                return None, None
            
            metal_data = _fetch_metal_data_cached(metal_symbol)
            if metal_data is None:
                return None, None
            
        except Exception:
            return None, None
        
        # Calculate ratio and indicators
        ratio_data = self.calculate_ratio(crypto_data, metal_data)
        ratio_data = self.add_technical_indicators(ratio_data)
        
        # Create subplots: [Ratio Chart, RSI, Percentile]
        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=(
                f'{crypto_name}/{metal_name} Ratio with Technical Indicators',
                'RSI (14)',
                'Historical Percentile'
            )
        )
        
        # Plot 1: Ratio with MA and Bollinger Bands
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['ratio'],
                name=f'{crypto_name}/{metal_name}',
                line=dict(color='#00D9FF', width=2)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['MA50'],
                name='MA50',
                line=dict(color='orange', width=1)
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['MA200'],
                name='MA200',
                line=dict(color='red', width=1)
            ),
            row=1, col=1
        )
        
        # Bollinger Bands
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['BB_upper'],
                name='BB Upper',
                line=dict(color='rgba(128,128,128,0.3)', width=1, dash='dash'),
                showlegend=False
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['BB_lower'],
                name='BB Lower',
                line=dict(color='rgba(128,128,128,0.3)', width=1, dash='dash'),
                fill='tonexty',
                fillcolor='rgba(128,128,128,0.1)',
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Plot 2: RSI
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['RSI'],
                name='RSI',
                line=dict(color='purple', width=2)
            ),
            row=2, col=1
        )
        
        # RSI reference lines
        fig.add_hline(y=70, line_dash="dash", line_color="red", opacity=0.5, row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", opacity=0.5, row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="gray", opacity=0.3, row=2, col=1)
        
        # Plot 3: Percentile
        fig.add_trace(
            go.Scatter(
                x=ratio_data.index,
                y=ratio_data['percentile'],
                name='Percentile',
                line=dict(color='#FFD700', width=2),
                fill='tozeroy',
                fillcolor='rgba(255,215,0,0.2)'
            ),
            row=3, col=1
        )
        
        # Percentile zones
        fig.add_hrect(y0=85, y1=100, line_width=0, fillcolor="red", opacity=0.1, row=3, col=1)
        fig.add_hrect(y0=0, y1=15, line_width=0, fillcolor="green", opacity=0.1, row=3, col=1)
        
        # Update layout
        fig.update_layout(
            height=800,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            hovermode='x unified',
            template='plotly_dark'
        )
        
        # Update axes
        fig.update_yaxes(title_text="Ratio", row=1, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
        fig.update_yaxes(title_text="Percentile %", range=[0, 100], row=3, col=1)
        fig.update_xaxes(title_text="Date", row=3, col=1)
        
        return fig, ratio_data
    
    def get_current_metrics(self, ratio_data):
        """Get current metrics from pre-calculated ratio data"""
        
        if ratio_data is None or len(ratio_data) == 0:
            return None
        
        # Get latest values
        latest = ratio_data.iloc[-1]
        
        return {
            'current_ratio': latest['ratio'],
            'ma50': latest['MA50'],
            'ma200': latest['MA200'],
            'rsi': latest['RSI'],
            'percentile': latest['percentile'],
            'bb_upper': latest['BB_upper'],
            'bb_lower': latest['BB_lower'],
            'days_of_data': len(ratio_data)
        }
    
    def get_rotation_recommendation(self, ratio_data):
        """Calculate rotation recommendation from ratio data
        
        Args:
            ratio_data: DataFrame with technical indicators
            
        Returns:
            Dictionary with rotation recommendation data
        """
        if ratio_data is None or len(ratio_data) == 0:
            return None
        
        # Get latest values
        latest = ratio_data.iloc[-1]
        
        # Calculate recommendation using rotation engine
        recommendation = self.rotation_engine.calculate_recommendation(
            ratio_data=ratio_data,
            percentile=latest['percentile'],
            rsi=latest['RSI'],
            current_ratio=latest['ratio']
        )
        
        return recommendation
