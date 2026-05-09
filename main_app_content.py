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
import rotation_log as rlog

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
    
    # Initialize components
    signal_engine = InvestmentSignalEngine()
    cycle_engine = ExponentialCycleEngine(base_weekly_dca=st.session_state.base_weekly_dca)
    chart_builder = ComparisonChartBuilder()
    tracker = PortfolioStateTracker()
    
    # Get signals
    signals = signal_engine.calculate_relative_valuation_scores()
    
    if signals is None:
        st.error("Unable to load market data. Please refresh the page.")
        st.stop()

    # USD percentile fallback warning — surfaces Task 2 fix
    if signals.get('usd_percentile_source') == 'gold_ratio_fallback':
        st.warning("⚠️ USD price data unavailable — DCA percentiles are using gold-ratio values as fallback.")
    
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
    
    # Tab Layout — DCA Strategy | Gold Analysis | Silver Analysis | Rotation Log | Overview
    tab1, tab2, tab3, tab4, tab0 = st.tabs([
        "📊 DCA Strategy",
        "🥇 Gold Analysis",
        "🥈 Silver Analysis",
        "🔁 Rotation Log",
        "📖 Overview"
    ])
    
    # ── TAB 1: DCA STRATEGY ────────────────────────────────────────────────────
    with tab1:

        # Percentile meters — TOP of tab
        st.markdown("### 📊 Market Percentiles")

        def get_percentile_status(percentile):
            if percentile < 15:
                return "#00FF00", "EXTREME UNDERVALUED"
            elif percentile < 40:
                return "#90EE90", "UNDERVALUED"
            elif percentile < 60:
                return "#FFA500", "FAIR VALUE"
            elif percentile < 85:
                return "#FFD700", "ELEVATED"
            else:
                return "#FF4444", "EXTREME OVERVALUED"

        btc_color, btc_status = get_percentile_status(signals['btc_percentile'])
        eth_color, eth_status = get_percentile_status(signals['eth_percentile'])

        col_btc, col_eth = st.columns(2)
        with col_btc:
            st.markdown("**Bitcoin (BTC)**")
            st.markdown(f"### {signals['btc_percentile']:.1f}th percentile")
            st.progress(int(signals['btc_percentile']) / 100.0)
            st.markdown(f'<span style="color: {btc_color}; font-weight: bold;">{btc_status}</span>', unsafe_allow_html=True)
        with col_eth:
            st.markdown("**Ethereum (ETH)**")
            st.markdown(f"### {signals['eth_percentile']:.1f}th percentile")
            st.progress(int(signals['eth_percentile']) / 100.0)
            st.markdown(f'<span style="color: {eth_color}; font-weight: bold;">{eth_status}</span>', unsafe_allow_html=True)

        st.markdown("---")

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
            
            # Format action text — no raw asterisks
            action_text = recommendation.primary_action.replace('_', ' ').title().replace('Dca', 'DCA')
            st.markdown(f"#### {action_text}")
            st.caption(recommendation.reasoning)
            
            st.markdown("")  # Spacer
            
            # Investment Allocation
            if recommendation.btc_amount_usd > 0 or recommendation.eth_amount_usd > 0:
                st.markdown("#### 💰 Investment Breakdown")
                
                total_crypto_dca = recommendation.btc_amount_usd + recommendation.eth_amount_usd
                btc_pct = (recommendation.btc_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0
                eth_pct = (recommendation.eth_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0
                
                base_dca = st.session_state.base_weekly_dca
                multiplier = total_crypto_dca / base_dca if base_dca > 0 else 1.0
                if abs(multiplier - 1.0) > 0.01:
                    st.info(f"This Week's Total: ${total_crypto_dca:,.2f} ({multiplier:.1f}x your ${base_dca:,.0f} baseline)")
                else:
                    st.info(f"This Week's Total: ${total_crypto_dca:,.2f}")
                
                col_btc2, col_eth2 = st.columns(2)
                with col_btc2:
                    st.metric("Bitcoin (BTC)", f"${recommendation.btc_amount_usd:,.2f}", f"{btc_pct:.1f}% allocation")
                with col_eth2:
                    st.metric("Ethereum (ETH)", f"${recommendation.eth_amount_usd:,.2f}", f"{eth_pct:.1f}% allocation")
                
                if 'date_range' in signals:
                    st.caption(f"📊 Historical Data: {signals.get('data_days', 0):,} days ({signals['date_range']})")
        
        with col2:
            # Data Freshness Status
            st.markdown("### 🕐 Data Freshness")
            
            def format_freshness(timestamp, age_hours, is_fresh):
                if timestamp:
                    time_str = timestamp.strftime("%I:%M %p")
                    if age_hours < 1:
                        age_str = f"{int(age_hours * 60)}m ago"
                    elif age_hours < 24:
                        age_str = f"{age_hours:.1f}h ago"
                    else:
                        age_str = f"{age_hours/24:.1f}d ago"
                    badge = "🟢" if is_fresh else "🟡"
                    return f"{badge} {time_str} ({age_str})"
                return "❓ Unknown"
            
            if 'btc_timestamp' in signals:
                st.caption("**BTC**: " + format_freshness(
                    signals.get('btc_timestamp'), signals.get('btc_age_hours', 0), signals.get('btc_fresh', True)
                ))
                st.caption("**ETH**: " + format_freshness(
                    signals.get('eth_timestamp'), signals.get('eth_age_hours', 0), signals.get('eth_fresh', True)
                ))
                st.caption("**Gold**: " + format_freshness(
                    signals.get('gold_timestamp'), signals.get('gold_age_hours', 0), signals.get('gold_fresh', True)
                ))
                st.caption("**Silver**: " + format_freshness(
                    signals.get('silver_timestamp'), signals.get('silver_age_hours', 0), signals.get('silver_fresh', True)
                ))
                if not signals.get('gold_fresh', True) or not signals.get('silver_fresh', True):
                    st.caption("⚠️ Futures market closed")

            st.markdown("---")

            # Market Signals (non-duplicate — signals, not percentile meters)
            st.markdown("### 📡 Signals")
            st.metric("BTC Signal", f"{signals['btc_signal']:.2f}", f"{signals['btc_percentile']:.1f}th pct")
            st.metric("ETH Signal", f"{signals['eth_signal']:.2f}", f"{signals['eth_percentile']:.1f}th pct")

    # ── TAB 2: GOLD ANALYSIS ───────────────────────────────────────────────────
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
                st.success(f"🟢 Gold Data: {time_str} ({age_str})")
            else:
                st.warning(f"🟡 Gold Data: {time_str} ({age_str}) — Futures market closed")
        
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
        
        # ETH Fundamentals
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
                st.metric("Total Value Locked", f"${tvl/1e9:.1f}B" if tvl else "N/A",
                          help="DeFi deposits on Ethereum (DefiLlama)")
            with fund_col2:
                staking = fundamentals.get('staking')
                st.metric("ETH Staked",
                          f"{staking['staking_pct']:.1f}%" if staking else "N/A",
                          help=f"{staking['staked_eth']/1e6:.1f}M ETH in validators" if staking else None)
            with fund_col3:
                fng = fundamentals.get('fear_greed')
                if fng:
                    value = fng['value']
                    emoji = "🔴" if value <= 25 else "🟠" if value <= 45 else "🟡" if value <= 55 else "🟢"
                    st.metric("Fear & Greed", f"{emoji} {value}", help=fng['classification'])
                else:
                    st.metric("Fear & Greed", "N/A")
            with fund_col4:
                eth_btc = fundamentals.get('eth_btc')
                st.metric("ETH/BTC Ratio",
                          f"{eth_btc['ratio']:.4f}" if eth_btc else "N/A",
                          help="ETH price relative to BTC")
        except Exception as e:
            st.warning(f"Unable to load ETH fundamentals: {str(e)}")
        
        # Rotation Analysis Summary
        st.markdown("---")
        st.markdown("### 🎯 Rotation Analysis")
        rec_col1, rec_col2 = st.columns(2)
        with rec_col1:
            btc_gold_pct = signals.get('btc_gold_percentile', signals['btc_percentile'])
            st.info(f"**Bitcoin → Gold**\n\nBTC/Gold Ratio Percentile: {btc_gold_pct:.1f}th\n\nRecommendation: {'Consider rotation' if btc_gold_pct > 85 else 'Hold position'}")
        with rec_col2:
            eth_gold_pct = signals.get('eth_gold_percentile', signals['eth_percentile'])
            st.info(f"**Ethereum → Gold**\n\nETH/Gold Ratio Percentile: {eth_gold_pct:.1f}th\n\nRecommendation: {'Consider rotation' if eth_gold_pct > 85 else 'Hold position'}")

    # ── TAB 3: SILVER ANALYSIS ─────────────────────────────────────────────────
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
                st.success(f"🟢 Silver Data: {time_str} ({age_str})")
            else:
                st.warning(f"🟡 Silver Data: {time_str} ({age_str}) — Futures market closed")
        
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
        
        # Rotation Analysis Summary — mirrors Gold Analysis layout
        st.markdown("---")
        st.markdown("### 🎯 Rotation Analysis")
        rec_col1, rec_col2 = st.columns(2)
        with rec_col1:
            btc_silver_pct = signals.get('btc_silver_percentile', signals.get('btc_gold_percentile', signals['btc_percentile']))
            percentile_str = f"{btc_silver_pct:.1f}th" if btc_silver_pct is not None else 'N/A'
            rec_str = 'Consider rotation' if (btc_silver_pct is not None and btc_silver_pct > 85) else 'Hold position'
            st.info(f"**Bitcoin → Silver**\n\nBTC/Silver Ratio Percentile: {percentile_str}\n\nRecommendation: {rec_str}")
        with rec_col2:
            eth_silver_pct = signals.get('eth_silver_percentile', signals.get('eth_gold_percentile', signals['eth_percentile']))
            percentile_str = f"{eth_silver_pct:.1f}th" if eth_silver_pct is not None else 'N/A'
            rec_str = 'Consider rotation' if (eth_silver_pct is not None and eth_silver_pct > 85) else 'Hold position'
            st.info(f"**Ethereum → Silver**\n\nETH/Silver Ratio Percentile: {percentile_str}\n\nRecommendation: {rec_str}")

    # ── TAB 4: ROTATION LOG ────────────────────────────────────────────────────
    with tab4:
        st.markdown("## 🔁 Rotation Log")

        # ── Actions ───────────────────────────────────────────────────────────
        action_col1, action_col2 = st.columns(2)

        with action_col1:
            st.markdown("### ⚡ Execute Rotation")
            if st.button("🔄 Execute Rotation", use_container_width=True):
                if recommendation.rotation_direction:
                    tracker.execute_rotation(
                        recommendation.rotation_direction,
                        recommendation.rotation_percentage,
                        gold_pct=recommendation.gold_rotation_pct,
                        silver_pct=recommendation.silver_rotation_pct
                    )
                    rlog.log_rotation(
                        rotation_direction=recommendation.rotation_direction,
                        rotation_pct=recommendation.rotation_percentage,
                        total_usd=recommendation.rotation_percentage / 100 * st.session_state.base_weekly_dca,
                        signals=signals,
                        live_prices=live_prices,
                        cycle_phase=recommendation.cycle_phase.value,
                    )
                    st.success(f"✅ Rotated {recommendation.rotation_direction}")
                    st.rerun()
                else:
                    st.info("No rotation recommended this week")

        with action_col2:
            st.markdown("### 💵 Record DCA")
            if st.button("💵 Record DCA", use_container_width=True):
                if recommendation.btc_amount_usd > 0 or recommendation.eth_amount_usd > 0:
                    tracker.record_dca(
                        btc_amount=recommendation.btc_amount_usd,
                        eth_amount=recommendation.eth_amount_usd
                    )
                    total = recommendation.btc_amount_usd + recommendation.eth_amount_usd
                    multiplier = total / st.session_state.base_weekly_dca if st.session_state.base_weekly_dca else 1.0
                    rlog.log_dca(
                        btc_amount_usd=recommendation.btc_amount_usd,
                        eth_amount_usd=recommendation.eth_amount_usd,
                        multiplier=multiplier,
                        signals=signals,
                        live_prices=live_prices,
                        cycle_phase=recommendation.cycle_phase.value,
                    )
                    st.success(f"✅ Recorded ${total:,.2f} DCA")
                    st.rerun()
                else:
                    st.info("No DCA recommended this week")

        st.markdown("---")

        # ── Load log ──────────────────────────────────────────────────────────
        entries = rlog.load_log()
        stats = rlog.get_summary_stats(entries)

        # ── Summary metrics ───────────────────────────────────────────────────
        st.markdown("### 📊 Summary")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("DCA Entries", stats['total_dca_entries'])
        m2.metric("Rotations", stats['total_rotation_entries'])
        m3.metric("Total Deployed", f"${stats['total_deployed_usd']:,.0f}")
        m4.metric("Avg BTC %ile at DCA",
                  f"{stats['avg_btc_percentile_at_dca']:.1f}th" if stats['avg_btc_percentile_at_dca'] is not None else "—")
        m5.metric("Avg ETH %ile at DCA",
                  f"{stats['avg_eth_percentile_at_dca']:.1f}th" if stats['avg_eth_percentile_at_dca'] is not None else "—")

        st.markdown("---")

        if entries:
            df = pd.DataFrame(entries)

            # ── Charts ────────────────────────────────────────────────────────
            st.markdown("### 📈 Charts")

            dca_entries = df[df['entry_type'] == 'DCA'].copy()

            if not dca_entries.empty:
                dca_entries['timestamp'] = pd.to_datetime(dca_entries['timestamp'])
                dca_entries['total_usd'] = pd.to_numeric(dca_entries['total_usd'], errors='coerce').fillna(0)
                dca_entries['btc_amount_usd'] = pd.to_numeric(dca_entries['btc_amount_usd'], errors='coerce').fillna(0)
                dca_entries['eth_amount_usd'] = pd.to_numeric(dca_entries['eth_amount_usd'], errors='coerce').fillna(0)
                dca_entries['btc_percentile'] = pd.to_numeric(dca_entries['btc_percentile'], errors='coerce')
                dca_entries['eth_percentile'] = pd.to_numeric(dca_entries['eth_percentile'], errors='coerce')

                # Cumulative DCA deployed
                dca_entries['cumulative_usd'] = dca_entries['total_usd'].cumsum()

                chart_col1, chart_col2 = st.columns(2)

                with chart_col1:
                    st.markdown("**Cumulative DCA Deployed ($)**")
                    st.area_chart(
                        dca_entries.set_index('timestamp')['cumulative_usd'],
                        color='#00D9FF'
                    )

                with chart_col2:
                    st.markdown("**BTC vs ETH Allocation per Entry ($)**")
                    alloc_df = dca_entries.set_index('timestamp')[['btc_amount_usd', 'eth_amount_usd']]
                    alloc_df.columns = ['BTC', 'ETH']
                    st.bar_chart(alloc_df, color=['#f7931a', '#627eea'])

                # Signal percentiles at DCA entries
                if dca_entries['btc_percentile'].notna().any():
                    st.markdown("**Signal Percentiles at Each DCA Entry**")
                    pct_df = dca_entries.set_index('timestamp')[['btc_percentile', 'eth_percentile']].dropna()
                    pct_df.columns = ['BTC %ile', 'ETH %ile']
                    st.line_chart(pct_df, color=['#f7931a', '#627eea'])
                    st.caption("Lower = more undervalued at time of purchase. Good DCA entries cluster below 40th percentile.")

            # Rotation markers
            rotation_entries = df[df['entry_type'] == 'ROTATION']
            if not rotation_entries.empty:
                st.markdown("**Rotation Events**")
                rot_display = rotation_entries[['timestamp', 'rotation_direction', 'rotation_pct',
                                                'btc_percentile', 'eth_percentile', 'cycle_phase']].copy()
                rot_display.columns = ['Date', 'Direction', 'Pct Rotated', 'BTC %ile', 'ETH %ile', 'Phase']
                st.dataframe(rot_display, use_container_width=True, hide_index=True)

            st.markdown("---")

            # ── Full log table ────────────────────────────────────────────────
            st.markdown("### 📋 Full History")

            # Type filter
            filter_type = st.selectbox("Filter by type", ["All", "DCA", "ROTATION"], index=0)
            display_df = df if filter_type == "All" else df[df['entry_type'] == filter_type]

            # Format for display
            display_cols = ['timestamp', 'entry_type', 'total_usd', 'btc_amount_usd', 'eth_amount_usd',
                            'multiplier', 'rotation_direction', 'rotation_pct',
                            'btc_percentile', 'eth_percentile', 'btc_signal', 'eth_signal',
                            'btc_price', 'eth_price', 'cycle_phase', 'notes']
            st.dataframe(
                display_df[display_cols].rename(columns={
                    'timestamp': 'Date',
                    'entry_type': 'Type',
                    'total_usd': 'Total $',
                    'btc_amount_usd': 'BTC $',
                    'eth_amount_usd': 'ETH $',
                    'multiplier': 'Mult',
                    'rotation_direction': 'Direction',
                    'rotation_pct': 'Rot %',
                    'btc_percentile': 'BTC %ile',
                    'eth_percentile': 'ETH %ile',
                    'btc_signal': 'BTC Sig',
                    'eth_signal': 'ETH Sig',
                    'btc_price': 'BTC Price',
                    'eth_price': 'ETH Price',
                    'cycle_phase': 'Phase',
                    'notes': 'Notes',
                }),
                use_container_width=True,
                hide_index=True
            )

        else:
            st.info("No entries yet. Use the buttons above to record your first DCA or rotation.")

        st.markdown("---")

        # ── Download ──────────────────────────────────────────────────────────
        st.markdown("### 💾 Export")
        csv_bytes = rlog.get_log_csv_bytes()
        st.download_button(
            label="⬇️ Download CSV",
            data=csv_bytes,
            file_name=f"cryptologix_log_{datetime.now().strftime('%Y%m%d')}.csv",
            mime='text/csv',
            help="Download full log as CSV for local backup"
        )

    # ── TAB 0: OVERVIEW ────────────────────────────────────────────────────────
    with tab0:
        st.markdown("## 📖 Overview")
        
        # Data freshness status
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
        
        if 'btc_timestamp' in signals:
            st.markdown("### 🕐 Market Data Status")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Cryptocurrencies:**")
                st.caption("**BTC**: " + format_freshness_overview(
                    signals.get('btc_timestamp'), signals.get('btc_age_hours', 0), signals.get('btc_fresh', True)
                ))
                st.caption("**ETH**: " + format_freshness_overview(
                    signals.get('eth_timestamp'), signals.get('eth_age_hours', 0), signals.get('eth_fresh', True)
                ))
            with col2:
                st.markdown("**Precious Metals:**")
                st.caption("**Gold**: " + format_freshness_overview(
                    signals.get('gold_timestamp'), signals.get('gold_age_hours', 0), signals.get('gold_fresh', True)
                ))
                st.caption("**Silver**: " + format_freshness_overview(
                    signals.get('silver_timestamp'), signals.get('silver_age_hours', 0), signals.get('silver_fresh', True)
                ))
            if not signals.get('gold_fresh', True) or not signals.get('silver_fresh', True):
                st.caption("⚠️ Futures markets closed — metal prices from last trading session")
        
        st.markdown("---")
        
        # Data Sources — moved here from footer
        st.markdown("### 📊 Data Sources")
        st.markdown("""
All recommendations use live market data from:

**Primary (Yahoo Finance):** [BTC-USD](https://finance.yahoo.com/quote/BTC-USD/) · [ETH-USD](https://finance.yahoo.com/quote/ETH-USD/) · [Gold GC=F](https://finance.yahoo.com/quote/GC=F/) · [Silver SI=F](https://finance.yahoo.com/quote/SI=F/)

**Backup (Redundancy):** CoinGecko API · CryptoCompare API · Binance Public API · FRED API (gold historical)

The app automatically switches to backup sources if primary sources are unavailable.
        """)
        
        st.markdown("---")
        
        render_overview_tab()
