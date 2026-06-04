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
    @st.cache_data(ttl=0, show_spinner=False)
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
        portfolio_state=portfolio_state,
        btc_gold_percentile=signals.get('btc_gold_percentile'),
        eth_gold_percentile=signals.get('eth_gold_percentile'),
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
        
        @st.cache_data(ttl=0, show_spinner=False)
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

        entries = rlog.load_log_with_performance(live_prices or {})
        summary = rlog.get_performance_summary(entries)

        # ── Execute Rotation ──────────────────────────────────────────────────
        st.markdown("### ⚡ Execute Rotation")

        # Signal recommendation display
        sig_col1, sig_col2, sig_col3 = st.columns(3)
        with sig_col1:
            if recommendation.rotation_direction:
                st.metric("Signal Direction", recommendation.rotation_direction.replace('_', ' '))
            else:
                st.metric("Signal", "HOLD — no rotation")
        with sig_col2:
            st.metric("Signal Suggested %",
                      f"{recommendation.rotation_percentage:.1f}%" if recommendation.rotation_direction else "—")
        with sig_col3:
            st.metric("Cycle Phase", recommendation.cycle_phase.value.replace('_', ' '))

        st.markdown("**Configure actual rotation:**")

        # Metals→crypto rotation banner
        if recommendation.rotation_direction == 'metals_to_crypto':
            st.error(
                f"🚨 **METALS→CRYPTO ROTATION SIGNAL ACTIVE** — "
                f"Liquidate **{recommendation.rotation_percentage:.1f}%** of gold/silver holdings → buy BTC/ETH spot. "
                f"{recommendation.reasoning}"
            )

        # Direction selector — default to signal recommendation if present
        direction_options = [
            "METALS_TO_CRYPTO",
            "BTC_TO_GOLD", "ETH_TO_GOLD",
            "BTC_TO_SILVER", "ETH_TO_SILVER",
        ]
        default_direction = (
            "METALS_TO_CRYPTO"
            if recommendation.rotation_direction == "metals_to_crypto"
            else recommendation.rotation_direction
            if recommendation.rotation_direction in direction_options
            else direction_options[0]
        )
        input_col1, input_col2, input_col3 = st.columns(3)
        with input_col1:
            selected_direction = st.selectbox(
                "Direction",
                direction_options,
                index=direction_options.index(default_direction),
                format_func=lambda x: x.replace('_', ' ')
            )
        with input_col2:
            # Parse from/to assets for labeling
            parts = selected_direction.split('_TO_')
            from_asset = parts[0] if len(parts) == 2 else 'CRYPTO'
            to_asset   = parts[1] if len(parts) == 2 else 'METAL'
            suggested_pct = recommendation.rotation_percentage if recommendation.rotation_direction else 25.0
            actual_pct = st.number_input(
                f"% of {from_asset} to rotate",
                min_value=1.0,
                max_value=100.0,
                value=float(round(suggested_pct, 1)),
                step=5.0,
                help="Suggested by signal engine — override as needed"
            )
        with input_col3:
            rotation_notes = st.text_input("Notes (optional)", placeholder="e.g. partial take-profit")

        if st.button("🔄 Execute Rotation", use_container_width=True):
            tracker.execute_rotation(
                selected_direction,
                actual_pct,
                gold_pct=actual_pct if 'GOLD' in selected_direction else 0,
                silver_pct=actual_pct if 'SILVER' in selected_direction else 0,
            )
            rlog.log_rotation(
                direction=selected_direction,
                rotation_pct=actual_pct,
                signals=signals,
                live_prices=live_prices,
                cycle_phase=recommendation.cycle_phase.value,
                notes=rotation_notes,
            )
            st.success(f"✅ Logged: {selected_direction.replace('_', ' ')} {actual_pct:.1f}%")
            st.rerun()

        st.markdown("---")

        if not entries:
            st.info("No rotations logged yet. Execute a rotation above to begin tracking.")
        else:
            # ── Performance Summary ───────────────────────────────────────────
            st.markdown("### 📊 Performance Summary")
            s1, s2, s3, s4, s5, s6 = st.columns(6)
            s1.metric("Total Rotations", summary.get('total_rotations', 0))
            s2.metric("Open",            summary.get('open_rotations', 0))
            s3.metric("Closed",          summary.get('closed_rotations', 0))
            avg_alpha = summary.get('avg_alpha_pct')
            s4.metric("Avg Alpha",
                      f"{avg_alpha:+.1f}%" if avg_alpha is not None else "—",
                      help="Avg (rotated return − crypto held return). Positive = rotation added value.")
            win_rate = summary.get('win_rate_pct')
            s5.metric("Win Rate",
                      f"{win_rate:.0f}%" if win_rate is not None else "—",
                      help="% of rotations where alpha > 0")
            total_alpha = summary.get('total_alpha_pct')
            s6.metric("Total Alpha",
                      f"{total_alpha:+.1f}%" if total_alpha is not None else "—")

            st.markdown("---")

            # ── Open Rotations ────────────────────────────────────────────────
            open_entries = [(i, e) for i, e in enumerate(entries) if e.get('status') == 'OPEN']
            if open_entries:
                st.markdown("### 🟢 Open Rotations")
                st.caption("Live performance — updates on each refresh")

                for i, e in open_entries:
                    c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                    with c1:
                        st.markdown(f"**{e.get('direction','').replace('_',' ')}** — {e.get('rotation_pct','')}%")
                        st.caption(f"{e.get('timestamp','')} · {e.get('cycle_phase','')}")

                    rotated_ret = e.get('rotated_asset_return_pct')
                    held_ret    = e.get('crypto_held_return_pct')
                    alpha       = e.get('alpha_pct')

                    with c2:
                        st.metric(f"{e.get('to_asset','')} Return",
                                  f"{rotated_ret:+.1f}%" if rotated_ret is not None else "—")
                    with c3:
                        st.metric(f"{e.get('from_asset','')} If Held",
                                  f"{held_ret:+.1f}%" if held_ret is not None else "—")
                    with c4:
                        st.metric("Alpha",
                                  f"{alpha:+.1f}%" if alpha is not None else "—",
                                  help="Positive = rotation outperformed holding crypto")
                    with c5:
                        if st.button("✅ Close", key=f"close_{i}",
                                     help="Mark closed at current prices"):
                            rlog.close_rotation(i, live_prices or {})
                            st.success("Rotation closed.")
                            st.rerun()

                    st.caption(
                        f"Signal at entry — BTC: {e.get('btc_percentile','')}th pct "
                        f"(signal {e.get('btc_signal','')}) · "
                        f"ETH: {e.get('eth_percentile','')}th pct "
                        f"(signal {e.get('eth_signal','')})"
                    )
                    st.divider()

            # ── Closed Rotations ──────────────────────────────────────────────
            closed_entries = [(i, e) for i, e in enumerate(entries) if e.get('status') == 'CLOSED']
            if closed_entries:
                st.markdown("### ⚫ Closed Rotations")
                closed_rows = []
                for i, e in closed_entries:
                    rotated_ret = e.get('rotated_asset_return_pct')
                    held_ret    = e.get('crypto_held_return_pct')
                    alpha       = e.get('alpha_pct')
                    closed_rows.append({
                        'Entered':     e.get('timestamp', '')[:10],
                        'Direction':   e.get('direction', '').replace('_', ' '),
                        'Rot %':       e.get('rotation_pct', ''),
                        'Closed':      e.get('closed_at', '')[:10],
                        '→ Return':    f"{rotated_ret:+.1f}%" if rotated_ret is not None else '—',
                        'If Held':     f"{held_ret:+.1f}%" if held_ret is not None else '—',
                        'Alpha':       f"{alpha:+.1f}%" if alpha is not None else '—',
                        'BTC %ile':    e.get('btc_percentile', ''),
                        'ETH %ile':    e.get('eth_percentile', ''),
                        'Phase':       e.get('cycle_phase', ''),
                    })
                st.dataframe(pd.DataFrame(closed_rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Export / Reset ────────────────────────────────────────────────────
        exp_col, reset_col = st.columns([2, 1])
        with exp_col:
            st.download_button(
                label="⬇️ Download CSV",
                data=rlog.get_log_csv_bytes(),
                file_name=f"cryptologix_rotations_{datetime.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
            )
        with reset_col:
            if 'confirm_reset' not in st.session_state:
                st.session_state.confirm_reset = False
            if not st.session_state.confirm_reset:
                if st.button("🗑️ Reset Log", use_container_width=True):
                    st.session_state.confirm_reset = True
                    st.rerun()
            else:
                st.warning("Delete all rotation history?")
                yes_col, no_col = st.columns(2)
                with yes_col:
                    if st.button("✅ Yes, delete", use_container_width=True):
                        import os
                        if os.path.exists(rlog.LOG_PATH):
                            os.remove(rlog.LOG_PATH)
                        st.session_state.confirm_reset = False
                        st.success("Log cleared.")
                        st.rerun()
                with no_col:
                    if st.button("❌ Cancel", use_container_width=True):
                        st.session_state.confirm_reset = False
                        st.rerun()

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
