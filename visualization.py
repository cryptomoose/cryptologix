import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import plotly.express as px

class ChartVisualizer:
    """Create interactive charts for cryptocurrency market analysis"""
    
    def __init__(self):
        self.color_scheme = {
            'bull': '#26a69a',  # Green
            'bear': '#ef5350',  # Red
            'neutral': '#ffa726',  # Orange
            'background': '#ffffff',
            'grid': '#e0e0e0',
            'text': '#333333'
        }
    
    def create_main_chart(self, df: pd.DataFrame, crypto_name: str, cycles: List[Dict]) -> go.Figure:
        """
        Create main price chart with technical indicators
        
        Args:
            df (pd.DataFrame): Price data with technical indicators
            crypto_name (str): Name of cryptocurrency
            cycles (List[Dict]): Market cycles for highlighting
        
        Returns:
            go.Figure: Interactive plotly chart
        """
        # Create subplots
        fig = make_subplots(
            rows=4, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            subplot_titles=(
                f'{crypto_name} Price & Moving Averages',
                'RSI',
                'MACD',
                'Volume'
            ),
            row_heights=[0.5, 0.2, 0.2, 0.1]
        )
        
        # Main price chart
        fig.add_trace(
            go.Candlestick(
                x=df.index,
                open=df['Open'],
                high=df['High'],
                low=df['Low'],
                close=df['Close'],
                name='Price',
                increasing_line_color=self.color_scheme['bull'],
                decreasing_line_color=self.color_scheme['bear']
            ),
            row=1, col=1
        )
        
        # Moving averages
        if 'MA_Short' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['MA_Short'],
                    mode='lines',
                    name='MA Short',
                    line=dict(color='blue', width=1)
                ),
                row=1, col=1
            )
        
        if 'MA_Long' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['MA_Long'],
                    mode='lines',
                    name='MA Long',
                    line=dict(color='red', width=1)
                ),
                row=1, col=1
            )
        
        # Bollinger Bands
        if all(col in df.columns for col in ['BB_Upper', 'BB_Lower', 'BB_Middle']):
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['BB_Upper'],
                    mode='lines',
                    name='BB Upper',
                    line=dict(color='gray', width=1, dash='dash'),
                    showlegend=False
                ),
                row=1, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['BB_Lower'],
                    mode='lines',
                    name='BB Lower',
                    line=dict(color='gray', width=1, dash='dash'),
                    fill='tonexty',
                    fillcolor='rgba(128,128,128,0.1)',
                    showlegend=False
                ),
                row=1, col=1
            )
        
        # RSI
        if 'RSI' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['RSI'],
                    mode='lines',
                    name='RSI',
                    line=dict(color='purple', width=2)
                ),
                row=2, col=1
            )
            
            # RSI levels
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)
            fig.add_hline(y=50, line_dash="dot", line_color="gray", row=2, col=1)
        
        # MACD
        if all(col in df.columns for col in ['MACD', 'MACD_Signal', 'MACD_Hist']):
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['MACD'],
                    mode='lines',
                    name='MACD',
                    line=dict(color='blue', width=1)
                ),
                row=3, col=1
            )
            
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['MACD_Signal'],
                    mode='lines',
                    name='MACD Signal',
                    line=dict(color='red', width=1)
                ),
                row=3, col=1
            )
            
            # MACD Histogram
            colors = ['green' if val >= 0 else 'red' for val in df['MACD_Hist']]
            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df['MACD_Hist'],
                    name='MACD Histogram',
                    marker_color=colors,
                    opacity=0.6
                ),
                row=3, col=1
            )
        
        # Volume
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['Volume'],
                name='Volume',
                marker_color='lightblue',
                opacity=0.7
            ),
            row=4, col=1
        )
        
        # Add cycle highlights
        self._add_cycle_highlights(fig, cycles, df)
        
        # Update layout
        fig.update_layout(
            title=f'{crypto_name} Market Analysis Dashboard',
            xaxis_rangeslider_visible=False,
            height=800,
            showlegend=True,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        # Update y-axes
        fig.update_yaxes(title_text="Price ($)", row=1, col=1)
        fig.update_yaxes(title_text="RSI", row=2, col=1, range=[0, 100])
        fig.update_yaxes(title_text="MACD", row=3, col=1)
        fig.update_yaxes(title_text="Volume", row=4, col=1)
        
        return fig
    
    def create_cycle_chart(self, df: pd.DataFrame, cycles: List[Dict], crypto_name: str) -> go.Figure:
        """
        Create chart specifically focused on market cycles
        
        Args:
            df (pd.DataFrame): Price data
            cycles (List[Dict]): Market cycles
            crypto_name (str): Cryptocurrency name
        
        Returns:
            go.Figure: Cycle analysis chart
        """
        fig = go.Figure()
        
        # Price line
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['Close'],
                mode='lines',
                name='Price',
                line=dict(color='black', width=2)
            )
        )
        
        # Color-code cycles
        for cycle in cycles:
            start_date = cycle['start_date']
            end_date = cycle['end_date']
            cycle_type = cycle.get('cycle_type', cycle.get('type', 'Unknown'))
            
            # Get cycle data
            cycle_data = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if not cycle_data.empty:
                color = self.color_scheme['bull'] if cycle_type == 'Bull Market' else \
                       self.color_scheme['bear'] if cycle_type == 'Bear Market' else \
                       self.color_scheme['neutral']
                
                fig.add_trace(
                    go.Scatter(
                        x=cycle_data.index,
                        y=cycle_data['Close'],
                        mode='lines',
                        name=f'{cycle_type} ({cycle.get("duration_days", 0)}d)',
                        line=dict(color=color, width=4),
                        hovertemplate=f'<b>{cycle_type}</b><br>' +
                                    f'Duration: {cycle.get("duration_days", 0)} days<br>' +
                                    f'Return: {cycle.get("price_change_pct", cycle.get("total_return", 0)):.1f}%<br>' +
                                    f'Date: %{{x}}<br>' +
                                    f'Price: $%{{y:.2f}}<extra></extra>'
                    )
                )
                
                # Add cycle annotations
                mid_date = start_date + (end_date - start_date) / 2
                mid_price = cycle_data['Close'].iloc[len(cycle_data)//2] if len(cycle_data) > 0 else 0
                
                fig.add_annotation(
                    x=mid_date,
                    y=mid_price,
                    text=f'{cycle_type}<br>{cycle.get("price_change_pct", cycle.get("total_return", 0)):.1f}%',
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    arrowwidth=2,
                    arrowcolor=color,
                    bgcolor=color,
                    bordercolor=color,
                    font=dict(color='white', size=10)
                )
        
        fig.update_layout(
            title=f'{crypto_name} Market Cycles Analysis',
            xaxis_title='Date',
            yaxis_title='Price ($)',
            height=500,
            showlegend=True,
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        return fig
    
    def create_correlation_matrix(self, df: pd.DataFrame) -> go.Figure:
        """Create correlation matrix of technical indicators"""
        # Select numeric columns for correlation
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # Calculate correlation matrix
        corr_matrix = df[numeric_cols].corr()
        
        fig = go.Figure(data=go.Heatmap(
            z=corr_matrix.values,
            x=corr_matrix.columns,
            y=corr_matrix.columns,
            colorscale='RdBu',
            zmid=0,
            text=corr_matrix.round(2).values,
            texttemplate='%{text}',
            textfont={"size": 10},
            hoverongaps=False
        ))
        
        fig.update_layout(
            title='Technical Indicators Correlation Matrix',
            height=600,
            width=800
        )
        
        return fig
    
    def create_performance_chart(self, performance_data: Dict) -> go.Figure:
        """Create performance metrics visualization"""
        if not performance_data:
            # Create empty chart with message
            fig = go.Figure()
            fig.add_annotation(
                text="Insufficient data for performance analysis",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(
                title='Strategy Performance',
                height=400
            )
            return fig
        
        # Create performance metrics chart
        metrics = ['Total Return (%)', 'Win Rate (%)', 'Sharpe Ratio', 'Max Drawdown (%)']
        values = [
            performance_data.get('total_return', 0),
            performance_data.get('win_rate', 0),
            performance_data.get('sharpe_ratio', 0) * 10,  # Scale for visibility
            performance_data.get('max_drawdown', 0)
        ]
        
        colors = ['green' if v > 0 else 'red' for v in values]
        
        fig = go.Figure(data=[
            go.Bar(x=metrics, y=values, marker_color=colors)
        ])
        
        fig.update_layout(
            title='Strategy Performance Metrics',
            yaxis_title='Value',
            height=400
        )
        
        return fig
    
    def create_signal_strength_chart(self, signals: List[Dict]) -> go.Figure:
        """Create signal strength visualization"""
        if not signals:
            fig = go.Figure()
            fig.add_annotation(
                text="No signals generated",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(
                title='Signal Strength Analysis',
                height=400
            )
            return fig
        
        # Group signals by type
        signal_types = [s['type'] for s in signals]
        signal_strengths = [s['strength'] for s in signals]
        signal_sources = [s['source'] for s in signals]
        
        colors = ['green' if t == 'BUY' else 'red' if t == 'SELL' else 'orange' for t in signal_types]
        
        fig = go.Figure(data=[
            go.Bar(
                x=signal_sources,
                y=signal_strengths,
                marker_color=colors,
                text=signal_types,
                textposition='auto',
                hovertemplate='<b>%{text}</b><br>' +
                            'Source: %{x}<br>' +
                            'Strength: %{y}/10<extra></extra>'
            )
        ])
        
        fig.update_layout(
            title='Current Signal Strength by Source',
            xaxis_title='Signal Source',
            yaxis_title='Signal Strength (1-10)',
            yaxis=dict(range=[0, 10]),
            height=400
        )
        
        return fig
    
    def create_pattern_confidence_chart(self, patterns: Dict) -> go.Figure:
        """Create pattern confidence visualization"""
        chart_patterns = patterns.get('chart_patterns', [])
        
        if not chart_patterns:
            fig = go.Figure()
            fig.add_annotation(
                text="No chart patterns identified",
                xref="paper", yref="paper",
                x=0.5, y=0.5, xanchor='center', yanchor='middle',
                showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(
                title='Chart Pattern Confidence',
                height=400
            )
            return fig
        
        # Extract pattern data
        pattern_types = [p['type'] for p in chart_patterns]
        confidences = [p['confidence'] * 100 for p in chart_patterns]  # Convert to percentage
        
        fig = go.Figure(data=[
            go.Bar(
                x=pattern_types,
                y=confidences,
                marker_color='lightblue',
                text=[f'{c:.1f}%' for c in confidences],
                textposition='auto'
            )
        ])
        
        fig.update_layout(
            title='Chart Pattern Confidence Levels',
            xaxis_title='Pattern Type',
            yaxis_title='Confidence (%)',
            yaxis=dict(range=[0, 100]),
            height=400,
            xaxis_tickangle=45
        )
        
        return fig
    
    def _add_cycle_highlights(self, fig: go.Figure, cycles: List[Dict], df: pd.DataFrame):
        """Add cycle highlighting to the main chart"""
        for cycle in cycles:
            start_date = cycle['start_date']
            end_date = cycle['end_date']
            cycle_type = cycle.get('cycle_type', cycle.get('type', 'Unknown'))
            
            color = self.color_scheme['bull'] if cycle_type == 'Bull Market' else \
                   self.color_scheme['bear'] if cycle_type == 'Bear Market' else \
                   self.color_scheme['neutral']
            
            # Add vertical rectangle to highlight cycle period
            fig.add_vrect(
                x0=start_date,
                x1=end_date,
                fillcolor=color,
                opacity=0.1,
                layer="below",
                line_width=0,
                row=1, col=1
            )
            
            # Add cycle label
            mid_date = start_date + (end_date - start_date) / 2
            cycle_data = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if not cycle_data.empty:
                max_price = cycle_data['High'].max()
                
                fig.add_annotation(
                    x=mid_date,
                    y=max_price,
                    text=f'{cycle_type[:4]}<br>{cycle.get("price_change_pct", cycle.get("total_return", 0)):.0f}%',
                    showarrow=False,
                    bgcolor=color,
                    bordercolor=color,
                    font=dict(color='white', size=8),
                    row=1, col=1
                )
    
    def create_volume_analysis_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create volume analysis chart"""
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=('Price vs Volume', 'Volume Indicators'),
            row_heights=[0.7, 0.3]
        )
        
        # Price and volume
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df['Close'],
                mode='lines',
                name='Price',
                line=dict(color='black'),
                yaxis='y'
            ),
            row=1, col=1
        )
        
        fig.add_trace(
            go.Bar(
                x=df.index,
                y=df['Volume'],
                name='Volume',
                marker_color='lightblue',
                opacity=0.6,
                yaxis='y2'
            ),
            row=1, col=1
        )
        
        # Volume indicators
        if 'OBV' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['OBV'],
                    mode='lines',
                    name='OBV',
                    line=dict(color='green')
                ),
                row=2, col=1
            )
        
        if 'Volume_MA' in df.columns:
            fig.add_trace(
                go.Scatter(
                    x=df.index,
                    y=df['Volume_MA'],
                    mode='lines',
                    name='Volume MA',
                    line=dict(color='red', dash='dash')
                ),
                row=1, col=1
            )
        
        # Update layout
        fig.update_layout(
            title='Volume Analysis',
            height=600,
            yaxis=dict(title='Price ($)', side='left'),
            yaxis2=dict(title='Volume', side='right', overlaying='y'),
            showlegend=True
        )
        
        return fig
    
    def create_risk_metrics_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create risk metrics visualization"""
        # Calculate risk metrics
        returns = df['Close'].pct_change().dropna()
        
        # Rolling volatility
        rolling_vol = returns.rolling(window=30).std() * np.sqrt(252) * 100
        
        # Value at Risk (VaR)
        var_95 = returns.rolling(window=30).quantile(0.05) * 100
        
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=('30-Day Rolling Volatility (%)', 'Value at Risk (95% confidence)')
        )
        
        # Volatility
        fig.add_trace(
            go.Scatter(
                x=df.index[1:],
                y=rolling_vol,
                mode='lines',
                name='30-Day Volatility',
                line=dict(color='orange'),
                fill='tonexty'
            ),
            row=1, col=1
        )
        
        # VaR
        fig.add_trace(
            go.Scatter(
                x=df.index[1:],
                y=var_95,
                mode='lines',
                name='VaR (95%)',
                line=dict(color='red'),
                fill='tonexty'
            ),
            row=2, col=1
        )
        
        fig.update_layout(
            title='Risk Metrics Dashboard',
            height=500,
            showlegend=True
        )
        
        fig.update_yaxes(title_text="Volatility (%)", row=1, col=1)
        fig.update_yaxes(title_text="VaR (%)", row=2, col=1)
        
        return fig
