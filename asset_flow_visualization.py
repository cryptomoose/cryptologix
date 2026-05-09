"""
Asset Flow Visualization Module
Creates animated visualizations showing the investment cycle and current flow recommendations
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

class AssetFlowVisualizer:
    def __init__(self):
        self.colors = {
            'usd': '#2E8B57',      # Sea Green
            'crypto': '#FF6B35',    # Orange Red  
            'eth': '#627EEA',       # Ethereum Blue
            'btc': '#F7931A',       # Bitcoin Orange
            'metals': '#FFD700',    # Gold
            'gold': '#FFD700',      # Gold
            'silver': '#C0C0C0',    # Silver
            'platinum': '#E5E4E2',  # Platinum
            'palladium': '#CED0DD', # Palladium
            'flow_active': '#00FF00', # Active flow
            'flow_inactive': '#666666' # Inactive flow
        }
        
    def create_flow_diagram(self, current_decision, portfolio_data):
        """Create animated flow diagram showing asset cycle and current recommendations"""
        
        # Create figure with subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Investment Flow Cycle', 'Current Portfolio State', 
                          'Flow Strength Indicators', 'Action Timeline'),
            specs=[[{"type": "scatter"}, {"type": "pie"}],
                   [{"type": "bar"}, {"type": "scatter"}]]
        )
        
        # 1. Investment Flow Cycle (top-left)
        self._add_flow_cycle(fig, current_decision, row=1, col=1)
        
        # 2. Current Portfolio State (top-right) 
        self._add_portfolio_pie(fig, portfolio_data, row=1, col=2)
        
        # 3. Flow Strength Indicators (bottom-left)
        self._add_flow_strength_bars(fig, current_decision, row=2, col=1)
        
        # 4. Action Timeline (bottom-right)
        self._add_action_timeline(fig, current_decision, row=2, col=2)
        
        # Update layout
        fig.update_layout(
            title={
                'text': '🔄 CRYPTOLOGIX ASSET FLOW VISUALIZATION',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 20, 'color': 'white'}
            },
            height=800,
            showlegend=True,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'}
        )
        
        return fig
    
    def _add_flow_cycle(self, fig, current_decision, row, col):
        """Add the main investment flow cycle diagram"""
        
        # Define flow cycle positions
        positions = {
            'USD': (0, 0),
            'CRYPTO': (2, 1), 
            'ETH': (1.5, 2),
            'BTC': (2.5, 2),
            'METALS': (4, 1),
            'GOLD': (3.5, 2),
            'SILVER': (4.5, 2),
            'ENDPOINT': (6, 0)
        }
        
        # Add nodes
        for asset, (x, y) in positions.items():
            if asset in ['USD', 'ENDPOINT']:
                color = self.colors['usd']
                symbol = 'circle'
                size = 30
            elif asset == 'CRYPTO':
                color = self.colors['crypto']
                symbol = 'diamond'
                size = 35
            elif asset in ['ETH', 'BTC']:
                color = self.colors[asset.lower()]
                symbol = 'hexagon'
                size = 25
            elif asset == 'METALS':
                color = self.colors['metals']
                symbol = 'square'
                size = 35
            else:  # Individual metals
                color = self.colors[asset.lower()]
                symbol = 'pentagon'
                size = 20
                
            fig.add_trace(
                go.Scatter(
                    x=[x], y=[y],
                    mode='markers+text',
                    marker=dict(size=size, color=color, symbol=symbol, line=dict(width=2, color='white')),
                    text=[asset],
                    textposition='middle center',
                    textfont=dict(size=10, color='white'),
                    name=asset,
                    showlegend=False
                ),
                row=row, col=col
            )
        
        # Add flow arrows
        self._add_flow_arrows(fig, positions, current_decision, row, col)
        
        # Update subplot layout
        fig.update_xaxes(showgrid=False, zeroline=False, showticklabels=False, row=row, col=col)
        fig.update_yaxes(showgrid=False, zeroline=False, showticklabels=False, row=row, col=col)
    
    def _add_flow_arrows(self, fig, positions, current_decision, row, col):
        """Add animated flow arrows based on current recommendations"""
        
        # Define flow paths
        flows = [
            ('USD', 'CRYPTO', 'USD→CRYPTO'),
            ('CRYPTO', 'ETH', 'CRYPTO SPLIT'),
            ('CRYPTO', 'BTC', 'CRYPTO SPLIT'),
            ('ETH', 'METALS', 'CRYPTO→METALS'),
            ('BTC', 'METALS', 'CRYPTO→METALS'),
            ('METALS', 'GOLD', 'METALS SPLIT'),
            ('METALS', 'SILVER', 'METALS SPLIT'),
            ('GOLD', 'ENDPOINT', 'METALS→USD'),
            ('SILVER', 'ENDPOINT', 'METALS→USD')
        ]
        
        # Determine active flows based on current decision
        active_flows = self._get_active_flows(current_decision)
        
        for start, end, flow_type in flows:
            if start in positions and end in positions:
                x0, y0 = positions[start]
                x1, y1 = positions[end]
                
                # Determine if this flow is currently active
                is_active = flow_type in active_flows
                color = self.colors['flow_active'] if is_active else self.colors['flow_inactive']
                width = 4 if is_active else 2
                opacity = 1.0 if is_active else 0.3
                
                # Add arrow
                fig.add_annotation(
                    x=x1, y=y1,
                    ax=x0, ay=y0,
                    xref=f'x{col}', yref=f'y{row}',
                    axref=f'x{col}', ayref=f'y{row}',
                    arrowhead=2,
                    arrowsize=2,
                    arrowwidth=width,
                    arrowcolor=color,
                    opacity=opacity,
                    row=row, col=col
                )
    
    def _get_active_flows(self, current_decision):
        """Determine which flows are currently active based on decision"""
        active_flows = []
        
        portfolio_decision = current_decision.get('portfolio_decision', '')
        
        if 'DCA' in portfolio_decision or 'ACCUMULATION' in portfolio_decision:
            active_flows.extend(['USD→CRYPTO', 'CRYPTO SPLIT'])
        
        if 'EXTREME TOP' in portfolio_decision:
            active_flows.extend(['CRYPTO→METALS', 'METALS SPLIT'])
        
        if 'METALS→USD' in portfolio_decision:
            active_flows.append('METALS→USD')
        
        if 'ROTATION' in portfolio_decision:
            active_flows.append('METALS SPLIT')
            
        return active_flows
    
    def _add_portfolio_pie(self, fig, portfolio_data, row, col):
        """Add current portfolio allocation pie chart"""
        
        # Sample portfolio data (in real implementation, this would come from user input)
        allocations = {
            'ETH': 35,
            'BTC': 25, 
            'Gold': 20,
            'Silver': 10,
            'USD': 10
        }
        
        colors = [self.colors.get(asset.lower(), '#666666') for asset in allocations.keys()]
        
        fig.add_trace(
            go.Pie(
                labels=list(allocations.keys()),
                values=list(allocations.values()),
                marker=dict(colors=colors, line=dict(color='white', width=2)),
                textfont=dict(color='white'),
                name="Portfolio"
            ),
            row=row, col=col
        )
    
    def _add_flow_strength_bars(self, fig, current_decision, row, col):
        """Add flow strength indicators"""
        
        # Extract scores from decision
        eth_score = current_decision.get('eth', {}).get('score', 0)
        btc_score = current_decision.get('btc', {}).get('score', 0)
        
        # Calculate flow strengths
        crypto_strength = (eth_score + btc_score) / 2
        metals_strength = -crypto_strength  # Inverse relationship
        
        flows = ['USD→CRYPTO', 'CRYPTO→METALS', 'METALS→USD']
        strengths = [
            max(0, crypto_strength),
            max(0, metals_strength), 
            max(0, -metals_strength)
        ]
        
        colors = [self.colors['crypto'], self.colors['metals'], self.colors['usd']]
        
        fig.add_trace(
            go.Bar(
                x=flows,
                y=strengths,
                marker=dict(color=colors),
                name="Flow Strength",
                showlegend=False
            ),
            row=row, col=col
        )
        
        fig.update_xaxes(tickangle=45, row=row, col=col)
        fig.update_yaxes(title="Strength", row=row, col=col)
    
    def _add_action_timeline(self, fig, current_decision, row, col):
        """Add action timeline showing recommended sequence"""
        
        # Create timeline data
        timeline_data = self._generate_timeline_data(current_decision)
        
        fig.add_trace(
            go.Scatter(
                x=timeline_data['time'],
                y=timeline_data['priority'],
                mode='markers+lines+text',
                marker=dict(size=15, color=timeline_data['colors']),
                text=timeline_data['actions'],
                textposition='top center',
                name="Action Timeline",
                showlegend=False
            ),
            row=row, col=col
        )
        
        fig.update_xaxes(title="Time", row=row, col=col)
        fig.update_yaxes(title="Priority", row=row, col=col)
    
    def _generate_timeline_data(self, current_decision):
        """Generate timeline data for action sequence"""
        
        actions = []
        priorities = []
        colors = []
        times = []
        
        # Extract action items from decision
        portfolio_decision = current_decision.get('portfolio_decision', '')
        
        if 'DCA' in portfolio_decision:
            actions.extend(['Continue DCA', 'ETH Staking', 'Monitor Markets'])
            priorities.extend([5, 4, 2])
            colors.extend([self.colors['crypto'], self.colors['eth'], self.colors['usd']])
            times.extend([1, 2, 3])
        
        elif 'EXTREME' in portfolio_decision:
            actions.extend(['Review Positions', 'Consider Rotation', 'Execute Gradually'])
            priorities.extend([5, 4, 3])
            colors.extend([self.colors['crypto'], self.colors['metals'], self.colors['usd']])
            times.extend([1, 2, 3])
        
        else:
            actions.extend(['Monitor', 'Hold', 'Maintain'])
            priorities.extend([3, 3, 3])
            colors.extend([self.colors['usd'], self.colors['crypto'], self.colors['metals']])
            times.extend([1, 2, 3])
        
        return {
            'actions': actions,
            'priority': priorities,
            'colors': colors,
            'time': times
        }
    
    def create_flow_animation(self, historical_decisions):
        """Create animated flow visualization over time"""
        
        frames = []
        
        for i, decision in enumerate(historical_decisions):
            # Create frame data
            frame_data = self._create_flow_frame(decision, i)
            frames.append(go.Frame(data=frame_data, name=str(i)))
        
        # Create initial figure
        fig = go.Figure(frames=frames)
        
        # Add animation controls
        fig.update_layout(
            updatemenus=[{
                "buttons": [
                    {
                        "args": [None, {"frame": {"duration": 500, "redraw": True},
                                       "fromcurrent": True, "transition": {"duration": 300}}],
                        "label": "Play",
                        "method": "animate"
                    },
                    {
                        "args": [[None], {"frame": {"duration": 0, "redraw": True},
                                         "mode": "immediate", "transition": {"duration": 0}}],
                        "label": "Pause",
                        "method": "animate"
                    }
                ],
                "direction": "left",
                "pad": {"r": 10, "t": 87},
                "showactive": False,
                "type": "buttons",
                "x": 0.1,
                "xanchor": "right",
                "y": 0,
                "yanchor": "top"
            }]
        )
        
        return fig
    
    def _create_flow_frame(self, decision, frame_index):
        """Create a single frame for the animation"""
        
        # This would contain the logic to create frame data
        # based on the decision state at a specific time
        pass
    
    def create_3d_flow_network(self, current_decision):
        """Create 3D network visualization of asset flows"""
        
        # Define 3D positions for assets
        positions_3d = {
            'USD': (0, 0, 0),
            'ETH': (2, 2, 1),
            'BTC': (2, -2, 1),
            'GOLD': (4, 0, 2),
            'SILVER': (4, 2, 2),
            'PLATINUM': (4, -2, 2),
            'PALLADIUM': (4, 0, 3)
        }
        
        # Create 3D scatter plot
        fig = go.Figure()
        
        for asset, (x, y, z) in positions_3d.items():
            fig.add_trace(
                go.Scatter3d(
                    x=[x], y=[y], z=[z],
                    mode='markers+text',
                    marker=dict(
                        size=20,
                        color=self.colors.get(asset.lower(), '#666666'),
                        opacity=0.8
                    ),
                    text=[asset],
                    textposition='middle center',
                    name=asset
                )
            )
        
        # Add flow connections
        self._add_3d_flow_connections(fig, positions_3d, current_decision)
        
        fig.update_layout(
            title='3D Asset Flow Network',
            scene=dict(
                xaxis_title='Investment Stage',
                yaxis_title='Asset Type',
                zaxis_title='Complexity Level',
                bgcolor='rgba(0,0,0,0)'
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            font={'color': 'white'}
        )
        
        return fig
    
    def _add_3d_flow_connections(self, fig, positions_3d, current_decision):
        """Add 3D flow connections between assets"""
        
        connections = [
            ('USD', 'ETH'),
            ('USD', 'BTC'),
            ('ETH', 'GOLD'),
            ('BTC', 'GOLD'),
            ('GOLD', 'SILVER'),
            ('GOLD', 'PLATINUM'),
            ('GOLD', 'PALLADIUM')
        ]
        
        for start, end in connections:
            if start in positions_3d and end in positions_3d:
                x0, y0, z0 = positions_3d[start]
                x1, y1, z1 = positions_3d[end]
                
                fig.add_trace(
                    go.Scatter3d(
                        x=[x0, x1], y=[y0, y1], z=[z0, z1],
                        mode='lines',
                        line=dict(color='rgba(255,255,255,0.5)', width=3),
                        showlegend=False
                    )
                )