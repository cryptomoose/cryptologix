"""
Main cryptologix app content - separated for clean importing
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from exponential_cycle_engine import ExponentialCycleEngine, CyclePhase
from portfolio_state_tracker import PortfolioStateTracker
from investment_signal_engine import InvestmentSignalEngine
from comparison_charts import ComparisonChartBuilder
from overview_content import render_overview_tab
from long_term_data_fetcher import LongTermDataFetcher
from eth_fundamentals import ETHFundamentals
import disk_cache

def render_crypto_app():
    """Render the main crypto analysis application"""
    
    # Custom CSS for cycle phase cards
    st.markdown("""
    <style>
        .cycle-phase-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 20px;
            color: white;
            text-align: center;
            margin: 1rem 0;
        }
        .action-card {
            padding: 2rem;
            border-radius: 15px;
            border-left: 5px solid;
            margin: 1rem 0;
        }
        .metric-value-white [data-testid="stMetricValue"] {
            color: #FFFFFF !important;
        }
        [data-testid="stMetricValue"] {
            color: #FFFFFF !important;
        }
        [data-testid="stMetricLabel"] {
            color: #FAFAFA !important;
        }
        .rotation-badge {
            display: inline-block;
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: bold;
            margin: 0.5rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Disclaimer
    st.warning("⚠️ **This app is a work in progress**")
    
    # Header
    st.markdown("# cryptologix")
    st.markdown("### **bit by bar** - exponential cycling strategy")
    st.markdown("Timing optimal rotations between cryptocurrency and precious metals for exponential wealth building")
    
    # Weekly DCA Amount Setting
    if 'base_weekly_dca' not in st.session_state:
        st.session_state.base_weekly_dca = 777
    
    # Get real-time prices for display (lightweight call, short cache)
    @st.cache_data(ttl=14400)
    def get_live_prices():
        fetcher = LongTermDataFetcher()
        return fetcher.get_realtime_prices()
    
    live_prices = get_live_prices()
    
    # Header with live prices and controls
    col_prices, col_mid, col_right = st.columns([2, 1, 1])
    
    with col_prices:
        if live_prices:
            btc_str = f"${live_prices['btc']:,.0f}" if live_prices.get('btc') else "N/A"
            eth_str = f"${live_prices['eth']:,.0f}" if live_prices.get('eth') else "N/A"
            gold_str = f"${live_prices['gold']:,.0f}" if live_prices.get('gold') else "N/A"
            silver_str = f"${live_prices['silver']:.2f}" if live_prices.get('silver') else "N/A"
            
            st.markdown(f"""
            <div style="display: flex; gap: 15px; flex-wrap: wrap; font-size: 0.9rem;">
                <span style="color: #f7931a;"><strong>BTC</strong> {btc_str}</span>
                <span style="color: #627eea;"><strong>ETH</strong> {eth_str}</span>
                <span style="color: #ffd700;"><strong>Gold</strong> {gold_str}/oz</span>
                <span style="color: #c0c0c0;"><strong>Silver</strong> {silver_str}/oz</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.caption("Live prices loading...")
    
    with col_mid:
        if st.button("🔄 Refresh Data", help="Force refresh all market data"):
            st.cache_data.clear()
            disk_cache.clear_all()
            st.rerun()
    with col_right:
        st.session_state.base_weekly_dca = st.number_input(
            "Weekly DCA Amount ($)",
            min_value=100,
            max_value=5000,
            value=st.session_state.base_weekly_dca,
            step=50,
            help="Your baseline weekly investment amount"
        )
    
    # Initialize components (not cached - needs to reflect current DCA amount)
    signal_engine = InvestmentSignalEngine()
    cycle_engine = ExponentialCycleEngine(base_weekly_dca=st.session_state.base_weekly_dca)
    chart_builder = ComparisonChartBuilder()
    tracker = PortfolioStateTracker()
    
    # Get signals
    signals = signal_engine.calculate_relative_valuation_scores()
    
    if signals is None:
        st.error("Unable to load market data. Please refresh the page.")
        st.stop()
    
    # Get portfolio state
    portfolio_state = tracker.get_current_state()
    
    # Generate cycle recommendation
    recommendation = cycle_engine.generate_weekly_recommendation(
        btc_percentile=signals['btc_percentile'],
        eth_percentile=signals['eth_percentile'],
        btc_signal=signals['btc_signal'],
        eth_signal=signals['eth_signal'],
        portfolio_state=portfolio_state
    )
    
    # Tab Layout
    tab1, tab2, tab3, tab0 = st.tabs(["📊 DCA Strategy", "🥇 Gold Analysis", "🥈 Silver Analysis", "📖 Overview"])
    
    # TAB 1: DCA STRATEGY (Main Cycle Interface)
    with tab1:
        # Main Layout
        col1, col2 = st.columns([2, 1])
    
        with col1:
            # Current Cycle Phase
            phase_colors = {
                CyclePhase.EXTREME_BOTTOM: "#FF6600",
                CyclePhase.AGGRESSIVE_DCA: "#00FF00",
                CyclePhase.ACCUMULATION: "#90EE90",
                CyclePhase.BULL_MARKET: "#FFA500",
                CyclePhase.EXTREME_TOP: "#FF4444",
                CyclePhase.GOLD_HOLDING: "#FFD700"
            }
        
            phase_color = phase_colors.get(recommendation.cycle_phase, "#808080")
        
            st.markdown(f"""
            <div class="cycle-phase-card">
                <h1 style="margin: 0; font-size: 3rem;">📊 {recommendation.cycle_phase.value.replace('_', ' ').upper()}</h1>
                <p style="font-size: 1.2rem; margin-top: 1rem;">Current Market Cycle Position</p>
            </div>
            """, unsafe_allow_html=True)
        
            # This Week's Action
            st.markdown("### 📅 This Week's Action")
            
            action_border_color = {
                CyclePhase.EXTREME_BOTTOM: "#FF6600",
                CyclePhase.AGGRESSIVE_DCA: "#00FF00",
                CyclePhase.ACCUMULATION: "#4CAF50",
                CyclePhase.BULL_MARKET: "#FFA500",
                CyclePhase.EXTREME_TOP: "#FF4444",
                CyclePhase.GOLD_HOLDING: "#FFD700"
            }.get(recommendation.cycle_phase, "#666666")
            
            # Format action text with proper DCA capitalization
            action_text = recommendation.primary_action.replace('_', ' ').title().replace('Dca', 'DCA')
            
            # Determine percentile status colors and labels
            def get_percentile_status(percentile):
                if percentile < 15:
                    return "#00FF00", "EXTREME UNDERVALUED"
                elif percentile < 45:
                    return "#90EE90", "UNDERVALUED"
                elif percentile < 55:
                    return "#FFA500", "FAIR VALUE"
                elif percentile < 85:
                    return "#FFD700", "ELEVATED"
                else:
                    return "#FF4444", "EXTREME OVERVALUED"
            
            btc_color, btc_status = get_percentile_status(signals['btc_percentile'])
            eth_color, eth_status = get_percentile_status(signals['eth_percentile'])
            
            # Use native Streamlit components instead of HTML
            st.markdown(f"#### {action_text}")
            # Use st.text() to preserve special characters like < and >
            st.caption(f"_{recommendation.reasoning}_")
            
            st.markdown("")  # Spacer
            
            # Display percentiles side by side with progress bars
            col_btc, col_eth = st.columns(2)
            
            with col_btc:
                st.markdown("**Bitcoin (BTC)**")
                st.markdown(f"### {signals['btc_percentile']:.1f}th percentile")
                st.progress(int(signals['btc_percentile']) / 100.0)
                # Use HTML for colored text since Streamlit markdown doesn't support hex colors
                st.markdown(f'<span style="color: {btc_color}; font-weight: bold;">{btc_status}</span>', unsafe_allow_html=True)
            
            with col_eth:
                st.markdown("**Ethereum (ETH)**")
                st.markdown(f"### {signals['eth_percentile']:.1f}th percentile")
                st.progress(int(signals['eth_percentile']) / 100.0)
                # Use HTML for colored text since Streamlit markdown doesn't support hex colors
                st.markdown(f'<span style="color: {eth_color}; font-weight: bold;">{eth_status}</span>', unsafe_allow_html=True)
            
            # Investment Allocation
            if recommendation.btc_amount_usd > 0 or recommendation.eth_amount_usd > 0:
                st.markdown("#### 💰 Investment Breakdown")
                
                # Calculate percentages and multiplier
                total_crypto_dca = recommendation.btc_amount_usd + recommendation.eth_amount_usd
                btc_pct = (recommendation.btc_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0
                eth_pct = (recommendation.eth_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0
                
                # Show total with multiplier if different from baseline
                base_dca = st.session_state.base_weekly_dca
                multiplier = total_crypto_dca / base_dca if base_dca > 0 else 1.0
                if abs(multiplier - 1.0) > 0.01:
                    st.info(f"**This Week's Total: ${total_crypto_dca:,.2f}** ({multiplier:.1f}x your ${base_dca:,.0f} baseline)")
                else:
                    st.info(f"**This Week's Total: ${total_crypto_dca:,.2f}**")
                
                col_btc, col_eth = st.columns(2)
                
                with col_btc:
                    st.metric(
                        "Bitcoin (BTC)",
                        f"${recommendation.btc_amount_usd:,.2f}",
                        f"{btc_pct:.1f}% allocation"
                    )
                
                with col_eth:
                    st.metric(
                        "Ethereum (ETH)",
                        f"${recommendation.eth_amount_usd:,.2f}",
                        f"{eth_pct:.1f}% allocation"
                    )
                
                # Show data range info
                from datetime import datetime
                if 'date_range' in signals:
                    data_info = f"📊 **Historical Data**: {signals.get('data_days', 0):,} days ({signals['date_range']})"
                    st.caption(data_info)
        
        with col2:
            # Portfolio State
            st.markdown("### 💼 Portfolio State")
            
            # Calculate USD allocation as remainder
            metals_allocation = portfolio_state.gold_allocation + portfolio_state.silver_allocation
            usd_allocation = 100 - portfolio_state.crypto_allocation - metals_allocation
            
            st.metric(
                "Crypto Holdings",
                f"{portfolio_state.crypto_allocation:.1f}%",
                "of portfolio"
            )
            
            col_gold, col_silver = st.columns(2)
            with col_gold:
                st.metric(
                    "Gold",
                    f"{portfolio_state.gold_allocation:.1f}%",
                    None
                )
            with col_silver:
                st.metric(
                    "Silver",
                    f"{portfolio_state.silver_allocation:.1f}%",
                    None
                )
            
            st.metric(
                "USD Available",
                f"{usd_allocation:.1f}%",
                f"${portfolio_state.usd_available:,.2f}" if portfolio_state.usd_available > 0 else "Ready to deploy"
            )
            
            st.markdown("---")
            
            # Quick Actions
            st.markdown("### ⚡ Quick Actions")
            
            if st.button("🔄 Execute Rotation", use_container_width=True):
                if recommendation.rotation_direction:
                    tracker.execute_rotation(
                        recommendation.rotation_direction,
                        recommendation.rotation_percentage,
                        gold_pct=recommendation.gold_rotation_pct,
                        silver_pct=recommendation.silver_rotation_pct
                    )
                    st.success(f"✅ Rotated {recommendation.rotation_direction}")
                    st.rerun()
                else:
                    st.info("No rotation recommended this week")
            
            if st.button("💵 Record DCA", use_container_width=True):
                if recommendation.btc_amount_usd > 0 or recommendation.eth_amount_usd > 0:
                    tracker.record_dca(
                        btc_amount=recommendation.btc_amount_usd,
                        eth_amount=recommendation.eth_amount_usd
                    )
                    st.success(f"✅ Recorded ${recommendation.dca_amount_usd:,.2f} DCA")
                    st.rerun()
                else:
                    st.info("No DCA recommended this week")
            
            st.markdown("---")
            
            # Data Freshness Status
            st.markdown("### 🕐 Data Freshness")
            
            # Helper function to format timestamp
            def format_freshness(timestamp, age_hours, is_fresh):
                if timestamp:
                    time_str = timestamp.strftime("%I:%M %p")
                    if age_hours < 1:
                        age_str = f"{int(age_hours * 60)}m ago"
                    elif age_hours < 24:
                        age_str = f"{age_hours:.1f}h ago"
                    else:
                        age_str = f"{age_hours/24:.1f}d ago"
                    
                    if is_fresh:
                        badge = "🟢"
                    else:
                        badge = "🟡"
                    
                    return f"{badge} {time_str} ({age_str})"
                return "❓ Unknown"
            
            # Display freshness for each asset
            if 'btc_timestamp' in signals:
                st.caption("**BTC**: " + format_freshness(
                    signals.get('btc_timestamp'),
                    signals.get('btc_age_hours', 0),
                    signals.get('btc_fresh', True)
                ))
                
                st.caption("**ETH**: " + format_freshness(
                    signals.get('eth_timestamp'),
                    signals.get('eth_age_hours', 0),
                    signals.get('eth_fresh', True)
                ))
                
                st.caption("**Gold**: " + format_freshness(
                    signals.get('gold_timestamp'),
                    signals.get('gold_age_hours', 0),
                    signals.get('gold_fresh', True)
                ))
                
                st.caption("**Silver**: " + format_freshness(
                    signals.get('silver_timestamp'),
                    signals.get('silver_age_hours', 0),
                    signals.get('silver_fresh', True)
                ))
                
                # Show warning if metals are stale
                if not signals.get('gold_fresh', True) or not signals.get('silver_fresh', True):
                    st.caption("⚠️ *Futures market closed*")
        
        # Market Signals
        st.markdown("---")
        st.markdown("### 📊 Market Signals")
        
        col_btc, col_eth = st.columns(2)
        
        with col_btc:
            st.markdown("#### Bitcoin")
            st.metric(
                "Historical Percentile",
                f"{signals['btc_percentile']:.1f}%",
                f"Signal: {signals['btc_signal']:.2f}"
            )
        
        with col_eth:
            st.markdown("#### Ethereum")
            st.metric(
                "Historical Percentile",
                f"{signals['eth_percentile']:.1f}%",
                f"Signal: {signals['eth_signal']:.2f}"
            )
        
        # Performance Metrics
        st.markdown("---")
        st.markdown("### 📈 Performance")
        
        perf_col1, perf_col2, perf_col3 = st.columns(3)
        
        with perf_col1:
            # Show allocation summary
            active_allocation = portfolio_state.crypto_allocation + portfolio_state.metals_allocation
            st.metric("Active Investment", f"{active_allocation:.1f}%", "deployed")
        
        with perf_col2:
            cycle_metrics = tracker.get_cycle_metrics()
            st.metric("Completed Cycles", cycle_metrics['complete_cycles'])
        
        with perf_col3:
            if portfolio_state.last_rotation_date:
                st.metric("Last Rotation", portfolio_state.last_rotation_date.strftime("%Y-%m-%d"))
            else:
                st.metric("Last Rotation", "N/A")
    
    # TAB 2: GOLD ANALYSIS
    with tab2:
        st.markdown("## 🥇 Gold Analysis")
        st.markdown("Compare BTC and ETH valuations against gold to identify rotation opportunities")
        
        # Data freshness indicator for gold
        if 'gold_timestamp' in signals and signals.get('gold_timestamp'):
            gold_ts = signals['gold_timestamp']
            gold_age = signals.get('gold_age_hours', 0)
            gold_fresh = signals.get('gold_fresh', True)
            
            time_str = gold_ts.strftime("%b %d, %I:%M %p")
            if gold_age < 1:
                age_str = f"{int(gold_age * 60)} minutes ago"
            elif gold_age < 24:
                age_str = f"{gold_age:.1f} hours ago"
            else:
                age_str = f"{gold_age/24:.1f} days ago"
            
            if gold_fresh:
                st.success(f"🟢 **Gold Data**: {time_str} ({age_str})")
            else:
                st.warning(f"🟡 **Gold Data**: {time_str} ({age_str}) - *Futures market closed*")
        
        # BTC/Gold Chart
        st.markdown("### Bitcoin vs Gold")
        with st.spinner("Loading BTC/Gold analysis..."):
            try:
                btc_gold_chart, _ = chart_builder.create_comparison_chart('BTC-USD', 'GC=F', 'Bitcoin', 'Gold')
                if btc_gold_chart is not None:
                    st.plotly_chart(btc_gold_chart, use_container_width=True)
                else:
                    st.warning("Unable to load BTC/Gold chart. Please refresh the page.")
            except Exception as e:
                st.error(f"Error loading BTC/Gold chart: {str(e)}")
        
        st.markdown("---")
        
        # ETH/Gold Chart
        st.markdown("### Ethereum vs Gold")
        with st.spinner("Loading ETH/Gold analysis..."):
            try:
                eth_gold_chart, _ = chart_builder.create_comparison_chart('ETH-USD', 'GC=F', 'Ethereum', 'Gold')
                if eth_gold_chart is not None:
                    st.plotly_chart(eth_gold_chart, use_container_width=True)
                else:
                    st.warning("Unable to load ETH/Gold chart. Please refresh the page.")
            except Exception as e:
                st.error(f"Error loading ETH/Gold chart: {str(e)}")
        
        # ETH Fundamentals Section
        st.markdown("---")
        st.markdown("### 📊 ETH Fundamentals")
        st.caption("On-chain metrics for context when evaluating ETH rotation signals")
        
        @st.cache_data(ttl=21600)
        def get_eth_fundamentals():
            fetcher = ETHFundamentals()
            return fetcher.get_all_fundamentals()
        
        try:
            fundamentals = get_eth_fundamentals()
            
            fund_col1, fund_col2, fund_col3, fund_col4 = st.columns(4)
            
            with fund_col1:
                tvl = fundamentals.get('tvl')
                if tvl:
                    st.metric("Total Value Locked", f"${tvl/1e9:.1f}B", help="DeFi deposits on Ethereum (DefiLlama)")
                else:
                    st.metric("Total Value Locked", "N/A")
            
            with fund_col2:
                staking = fundamentals.get('staking')
                if staking:
                    st.metric("ETH Staked", f"{staking['staking_pct']:.1f}%", help=f"{staking['staked_eth']/1e6:.1f}M ETH in validators")
                else:
                    st.metric("ETH Staked", "N/A")
            
            with fund_col3:
                fng = fundamentals.get('fear_greed')
                if fng:
                    value = fng['value']
                    if value <= 25:
                        emoji = "🔴"
                    elif value <= 45:
                        emoji = "🟠"
                    elif value <= 55:
                        emoji = "🟡"
                    else:
                        emoji = "🟢"
                    st.metric("Fear & Greed", f"{emoji} {value}", help=fng['classification'])
                else:
                    st.metric("Fear & Greed", "N/A")
            
            with fund_col4:
                eth_btc = fundamentals.get('eth_btc')
                if eth_btc:
                    st.metric("ETH/BTC Ratio", f"{eth_btc['ratio']:.4f}", help="ETH price relative to BTC")
                else:
                    st.metric("ETH/BTC Ratio", "N/A")
        except Exception as e:
            st.warning(f"Unable to load ETH fundamentals: {str(e)}")
        
        # Rotation Analysis Summary
        st.markdown("---")
        st.markdown("### 🎯 Rotation Analysis")
        
        rec_col1, rec_col2 = st.columns(2)
        
        with rec_col1:
            st.info(f"""
            **Bitcoin → Gold**  
            BTC/Gold Ratio Percentile: {signals.get('btc_gold_percentile', signals['btc_percentile']):.1f}th  
            Recommendation: {'Consider rotation' if signals.get('btc_gold_percentile', signals['btc_percentile']) > 85 else 'Hold position'}
            """)
        
        with rec_col2:
            st.info(f"""
            **Ethereum → Gold**  
            ETH/Gold Ratio Percentile: {signals.get('eth_gold_percentile', signals['eth_percentile']):.1f}th  
            Recommendation: {'Consider rotation' if signals.get('eth_gold_percentile', signals['eth_percentile']) > 85 else 'Hold position'}
            """)
    
    # TAB 3: SILVER ANALYSIS
    with tab3:
        st.markdown("## 🥈 Silver Analysis")
        st.markdown("Compare BTC and ETH valuations against silver for alternative precious metals rotation")
        
        # Data freshness indicator for silver
        if 'silver_timestamp' in signals and signals.get('silver_timestamp'):
            silver_ts = signals['silver_timestamp']
            silver_age = signals.get('silver_age_hours', 0)
            silver_fresh = signals.get('silver_fresh', True)
            
            time_str = silver_ts.strftime("%b %d, %I:%M %p")
            if silver_age < 1:
                age_str = f"{int(silver_age * 60)} minutes ago"
            elif silver_age < 24:
                age_str = f"{silver_age:.1f} hours ago"
            else:
                age_str = f"{silver_age/24:.1f} days ago"
            
            if silver_fresh:
                st.success(f"🟢 **Silver Data**: {time_str} ({age_str})")
            else:
                st.warning(f"🟡 **Silver Data**: {time_str} ({age_str}) - *Futures market closed*")
        
        # BTC/Silver Chart
        st.markdown("### Bitcoin vs Silver")
        with st.spinner("Loading BTC/Silver analysis..."):
            try:
                btc_silver_chart, _ = chart_builder.create_comparison_chart('BTC-USD', 'SI=F', 'Bitcoin', 'Silver')
                if btc_silver_chart is not None:
                    st.plotly_chart(btc_silver_chart, use_container_width=True)
                else:
                    st.warning("Unable to load BTC/Silver chart. Please refresh the page.")
            except Exception as e:
                st.error(f"Error loading BTC/Silver chart: {str(e)}")
        
        st.markdown("---")
        
        # ETH/Silver Chart
        st.markdown("### Ethereum vs Silver")
        with st.spinner("Loading ETH/Silver analysis..."):
            try:
                eth_silver_chart, _ = chart_builder.create_comparison_chart('ETH-USD', 'SI=F', 'Ethereum', 'Silver')
                if eth_silver_chart is not None:
                    st.plotly_chart(eth_silver_chart, use_container_width=True)
                else:
                    st.warning("Unable to load ETH/Silver chart. Please refresh the page.")
            except Exception as e:
                st.error(f"Error loading ETH/Silver chart: {str(e)}")
        
        # ETH Fundamentals Section (same as Gold tab, cached)
        st.markdown("---")
        st.markdown("### 📊 ETH Fundamentals")
        st.caption("On-chain metrics for context when evaluating ETH rotation signals")
        
        try:
            fundamentals = get_eth_fundamentals()
            
            fund_col1, fund_col2, fund_col3, fund_col4 = st.columns(4)
            
            with fund_col1:
                tvl = fundamentals.get('tvl')
                if tvl:
                    st.metric("Total Value Locked", f"${tvl/1e9:.1f}B", help="DeFi deposits on Ethereum (DefiLlama)")
                else:
                    st.metric("Total Value Locked", "N/A")
            
            with fund_col2:
                staking = fundamentals.get('staking')
                if staking:
                    st.metric("ETH Staked", f"{staking['staking_pct']:.1f}%", help=f"{staking['staked_eth']/1e6:.1f}M ETH in validators")
                else:
                    st.metric("ETH Staked", "N/A")
            
            with fund_col3:
                fng = fundamentals.get('fear_greed')
                if fng:
                    value = fng['value']
                    if value <= 25:
                        emoji = "🔴"
                    elif value <= 45:
                        emoji = "🟠"
                    elif value <= 55:
                        emoji = "🟡"
                    else:
                        emoji = "🟢"
                    st.metric("Fear & Greed", f"{emoji} {value}", help=fng['classification'])
                else:
                    st.metric("Fear & Greed", "N/A")
            
            with fund_col4:
                eth_btc = fundamentals.get('eth_btc')
                if eth_btc:
                    st.metric("ETH/BTC Ratio", f"{eth_btc['ratio']:.4f}", help="ETH price relative to BTC")
                else:
                    st.metric("ETH/BTC Ratio", "N/A")
        except Exception as e:
            st.warning(f"Unable to load ETH fundamentals: {str(e)}")
        
        # Rotation Analysis Summary
        st.markdown("---")
        st.markdown("### 🎯 Rotation Analysis")
        
        rec_col1, rec_col2 = st.columns(2)
        
        with rec_col1:
            btc_silver_pct = signals.get('btc_silver_percentile', signals.get('btc_gold_percentile', signals['btc_percentile']))
            percentile_str = f"{btc_silver_pct:.1f}th" if btc_silver_pct is not None else 'N/A'
            recommendation = 'Consider rotation' if (btc_silver_pct is not None and btc_silver_pct > 85) else 'Hold position'
            st.info(f"""
            **Bitcoin → Silver**  
            BTC/Silver Ratio Percentile: {percentile_str}  
            Recommendation: {recommendation}
            """)
        
        with rec_col2:
            eth_silver_pct = signals.get('eth_silver_percentile', signals.get('eth_gold_percentile', signals['eth_percentile']))
            percentile_str = f"{eth_silver_pct:.1f}th" if eth_silver_pct is not None else 'N/A'
            recommendation = 'Consider rotation' if (eth_silver_pct is not None and eth_silver_pct > 85) else 'Hold position'
            st.info(f"""
            **Ethereum → Silver**  
            ETH/Silver Ratio Percentile: {percentile_str}  
            Recommendation: {recommendation}
            """)
    
    # TAB 0: OVERVIEW (Investment Thesis & Explainer)
    with tab0:
        # Data freshness status at top of Overview
        st.markdown("## 📖 Overview")
        
        # Helper function to format freshness (same as DCA tab)
        def format_freshness_overview(timestamp, age_hours, is_fresh):
            if timestamp:
                time_str = timestamp.strftime("%b %d, %I:%M %p")
                if age_hours < 1:
                    age_str = f"{int(age_hours * 60)}m"
                elif age_hours < 24:
                    age_str = f"{age_hours:.1f}h"
                else:
                    age_str = f"{age_hours/24:.1f}d"
                
                badge = "🟢" if is_fresh else "🟡"
                return f"{badge} {time_str} ({age_str} ago)"
            return "❓ Unknown"
        
        # Display freshness for all assets in a compact format
        if 'btc_timestamp' in signals:
            st.markdown("### 🕐 Market Data Status")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Cryptocurrencies:**")
                st.caption("**BTC**: " + format_freshness_overview(
                    signals.get('btc_timestamp'),
                    signals.get('btc_age_hours', 0),
                    signals.get('btc_fresh', True)
                ))
                st.caption("**ETH**: " + format_freshness_overview(
                    signals.get('eth_timestamp'),
                    signals.get('eth_age_hours', 0),
                    signals.get('eth_fresh', True)
                ))
            
            with col2:
                st.markdown("**Precious Metals:**")
                st.caption("**Gold**: " + format_freshness_overview(
                    signals.get('gold_timestamp'),
                    signals.get('gold_age_hours', 0),
                    signals.get('gold_fresh', True)
                ))
                st.caption("**Silver**: " + format_freshness_overview(
                    signals.get('silver_timestamp'),
                    signals.get('silver_age_hours', 0),
                    signals.get('silver_fresh', True)
                ))
            
            # Show warning if metals are stale
            if not signals.get('gold_fresh', True) or not signals.get('silver_fresh', True):
                st.caption("⚠️ *Futures markets closed - metal prices from last trading session*")
        
        st.markdown("---")
        
        render_overview_tab()
    
    # FOOTER: Data Sources (appears on all pages)
    st.markdown("---")
    st.markdown("""
    <div style="background: #1a1a1a; padding: 1.5rem; border-radius: 10px; margin-top: 2rem;">
        <h4 style="margin-top: 0; color: #888;">📊 Data Sources</h4>
        <p style="font-size: 0.9rem; color: #aaa; margin-bottom: 1rem;">
            All recommendations are based on live market data from the following sources. 
            Click the links below to verify data freshness and accuracy.
        </p>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem;">
            <div>
                <strong style="color: #60a5fa;">Primary Sources (Yahoo Finance):</strong><br>
                <a href="https://finance.yahoo.com/quote/BTC-USD/" target="_blank" style="color: #93c5fd;">🪙 Bitcoin (BTC-USD)</a><br>
                <a href="https://finance.yahoo.com/quote/ETH-USD/" target="_blank" style="color: #93c5fd;">🪙 Ethereum (ETH-USD)</a><br>
                <a href="https://finance.yahoo.com/quote/GC=F/" target="_blank" style="color: #93c5fd;">🥇 Gold Futures (GC=F)</a><br>
                <a href="https://finance.yahoo.com/quote/SI=F/" target="_blank" style="color: #93c5fd;">🥈 Silver Futures (SI=F)</a>
            </div>
            <div>
                <strong style="color: #60a5fa;">Backup Sources (Redundancy):</strong><br>
                <span style="color: #aaa; font-size: 0.85rem;">
                • CoinGecko API (crypto)<br>
                • CryptoCompare API (crypto)<br>
                • Binance Public API (crypto)<br>
                • FRED API (gold historical data)
                </span>
            </div>
        </div>
        <p style="font-size: 0.8rem; color: #666; margin-top: 1rem; margin-bottom: 0;">
            ℹ️ The app automatically switches to backup sources if primary sources are unavailable, ensuring continuous operation.
        </p>
    </div>
    """, unsafe_allow_html=True)
