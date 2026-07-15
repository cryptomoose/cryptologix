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
from utils import format_action_label

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

        # Metals Relationship — GSR, ratio-move decomposition, silver/crypto tail
        # correlation (signal_core, shared verbatim with willie-agent-stack/crypto).
        # General market data only (gold/silver/BTC/ETH price history) — no personal
        # portfolio, debt, or confirmation-gate state is read or shown here.
        #
        # The whole section is wrapped defensively: it makes its own lightweight
        # yfinance calls (period='6mo', not LongTermDataFetcher's 'max'/10+-year
        # fetches — the signal functions only need the trailing ~90 days, and
        # reusing the 'max' fetchers here would quadruple this page's Yahoo
        # Finance load on top of what InvestmentSignalEngine already does). A
        # failure here (rate limit, network hiccup) must degrade to a caption,
        # never take down the rest of the DCA Strategy tab.
        try:
            from signal_core import (gold_silver_ratio_signal, ratio_move_decomposition,
                                     metals_tail_correlation)

            @st.cache_data(ttl=21600, show_spinner=False)
            def get_metals_relationship_state():
                import yfinance as yf

                def _series(symbol):
                    try:
                        hist = yf.Ticker(symbol).history(period='6mo', interval='1d', auto_adjust=True)
                        if hist is None or hist.empty:
                            return []
                        if hist.index.tz is not None:
                            hist.index = hist.index.tz_localize(None)
                        tail = hist['Close'].dropna().tail(90)
                        return [[idx.strftime('%Y-%m-%d'), float(val)] for idx, val in tail.items()]
                    except Exception:
                        return []

                gold_hist = _series('GC=F')
                silver_hist = _series('SI=F')
                return {
                    'gold_usd': gold_hist[-1][1] if gold_hist else 0,
                    'silver_usd': silver_hist[-1][1] if silver_hist else 0,
                    'gold_price_history': gold_hist,
                    'silver_price_history': silver_hist,
                    'btc_price_history': _series('BTC-USD'),
                    'eth_price_history': _series('ETH-USD'),
                }

            _metals_state = get_metals_relationship_state()
            _gsr = gold_silver_ratio_signal(_metals_state)
            _rd = ratio_move_decomposition(_metals_state)
            _mtc = metals_tail_correlation(_metals_state)

            with st.expander("⚖️ Metals Relationship (Gold/Silver Ratio, ratio-move decomposition, tail correlation)", expanded=False):
                if _gsr.get('status') == 'ok':
                    g1, g2, g3 = st.columns(3)
                    g1.metric("Gold/Silver Ratio", f"{_gsr['gsr']:.2f}")
                    g2.metric(
                        "GSR Percentile",
                        f"{_gsr['gsr_percentile']}th" if _gsr.get('gsr_percentile') is not None else "N/A",
                        help=_gsr['gsr_percentile_note'],
                    )
                    g3.metric("Absolute Read", _gsr['absolute_read'])
                    # Note: the caveat string from signal_core references willie's
                    # personal "Goal 2" cycle-top framework, which is meaningless to
                    # public users — show a generic public-facing caveat here instead
                    # of the raw string, rather than editing the shared library file.
                    st.caption(
                        "Central bank structural gold demand may be shifting the "
                        "historical distribution — treat percentile and absolute "
                        "read as two independent checks, not a single number. "
                        "Informational context only."
                    )
                else:
                    st.info(f"GSR unavailable: {_gsr.get('reason', 'no data')}")

                st.markdown("**14-Day Ratio-Move Decomposition** — did the move come from crypto or from gold?")
                d1, d2 = st.columns(2)
                for _col, _label, _leg in ((d1, "BTC/Gold", _rd.get('btc_gold', {})),
                                            (d2, "ETH/Gold", _rd.get('eth_gold', {}))):
                    with _col:
                        st.markdown(f"*{_label}*")
                        if _leg.get('status') == 'ok':
                            st.write(f"Crypto {_leg['crypto_chg_pct']:+.1f}% vs Gold {_leg['gold_chg_pct']:+.1f}%")
                            st.write(f"Dominant leg: **{_leg['dominant_leg']}**")
                            if _leg.get('gold_driven_spike_flag'):
                                st.warning("⚠️ Gold-driven spike — move may mean-revert faster than a fundamental crypto move.")
                            st.caption(_leg['interpretation'])
                        else:
                            st.caption("Insufficient price history yet.")

                st.markdown("**Silver / Crypto Tail Correlation**")
                if _mtc.get('status') == 'ok':
                    c1, c2 = st.columns(2)
                    c1.metric("Silver vs BTC", f"{_mtc['silver_vs_btc']}")
                    c2.metric("Silver vs ETH", f"{_mtc['silver_vs_eth']}")
                    if _mtc.get('elevated_flag'):
                        st.warning("⚠️ Elevated correlation — silver moving with crypto, not as an independent safe-haven.")
                    st.caption(_mtc['interpretation'])
                else:
                    st.caption("Insufficient price history yet.")
        except Exception as _mr_ex:
            import logging as _mr_logging
            _mr_logging.getLogger(__name__).warning(f"Metals Relationship section failed: {_mr_ex}")
            st.caption("⚖️ Metals Relationship — temporarily unavailable.")

        # Capital Router — cycle-conditional DCA vs yield split (Kelly-derived)
        from signal_core import allocate_capital, expected_90d_return
        _avg_cycle_pct = (signals['btc_percentile'] + signals['eth_percentile']) / 2
        _weekly_dca_usd = recommendation.dca_amount_usd

        st.markdown("### 🚦 Capital Router")
        # No live yield-opportunity feed is wired into cryptologix yet, so
        # this call never passes yield_opportunities — allocate_capital's
        # gating block (concentration_check / eligible_for_primary) only runs
        # `if yield_usd > 0 and yield_opportunities`, meaning it silently
        # returns the *theoretical* Kelly dca/yield split without ever
        # checking real gates. yield_slots is still the correct ground truth
        # for "did a protocol actually clear gates" (it's populated only by
        # that gating block), so we reuse it here rather than trusting
        # router['dca']/['yield_usd'] directly — when yield_slots is empty,
        # 100% of capital goes to DCA, full stop; the theoretical split never
        # actually deploys anywhere and must not be displayed as if it did.
        router = allocate_capital(_avg_cycle_pct, _weekly_dca_usd)
        yield_slots = router.get("yield_slots", [])
        if yield_slots:
            dca_usd = router["dca"]
            yield_usd = router["yield_usd"]
        else:
            dca_usd = _weekly_dca_usd
            yield_usd = 0.0

        r1, r2, r3 = st.columns(3)
        r1.metric("This week's capital", f"${_weekly_dca_usd:,.0f}")
        r2.metric("→ DCA (cycle accumulation)", f"${dca_usd:,.0f}")
        r3.metric("→ Yield deployment", f"${yield_usd:,.0f}")

        med, iqr = expected_90d_return(_avg_cycle_pct)
        if not yield_slots:
            note = router.get("no_gate_cleared_note") or (
                "Yield $0 — no protocol clears concentration + audit/TVL gates this week"
            )
            st.caption(f"⛔ {note} — 100% of new capital routes to DCA.")
        else:
            st.caption(
                f"At the {_avg_cycle_pct:.1f}th percentile, {router['dca_frac']*100:.0f}% of new capital "
                f"routes to DCA and {100 - router['dca_frac']*100:.0f}% to yield. "
                f"Empirical E[90d return] here: {med*100:+.1f}% (IQR ±{iqr*100:.1f}%). "
                "Split is Kelly-derived from E[90d DCA] vs E[90d yield] edge over the risk-free rate "
                "(anchors: ~89% DCA at the 7th percentile down to yield-primary at the 65th+)."
            )
        if router.get("profit_taking_review"):
            st.warning(
                "⚠️ Cycle above the 50th percentile — review existing positions for "
                "profit-taking; new capital is mostly routed to yield."
            )

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
                CyclePhase.BULL_REDUCE: "#FF8C00",
                CyclePhase.EXTREME_TOP: "#FF4444",
                CyclePhase.ULTRA_TOP: "#CC0000",
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
            action_text = format_action_label(recommendation.primary_action)
            st.markdown(f"#### {action_text}")
            st.caption(recommendation.reasoning)

            # Lifecycle rotation banners
            if recommendation.cycle_phase == CyclePhase.BULL_REDUCE:
                st.warning(
                    "⚠️ BULL_REDUCE — Stop DCA. Prepare to sell. "
                    "Rotation triggers at 85th percentile: 70% metals + 30% stablecoins."
                )
            elif recommendation.cycle_phase in (CyclePhase.EXTREME_TOP, CyclePhase.ULTRA_TOP):
                rotation_pct = recommendation.rotation_percentage
                st.error(
                    f"🔴 {recommendation.cycle_phase.value.replace('_', ' ').upper()} — "
                    f"Rotate {rotation_pct:.0f}% → Metals {rotation_pct*0.70:.1f}% (gold 70% / silver 30%) "
                    f"+ Stables {rotation_pct*0.30:.1f}% (Aave/sDAI)"
                )

            st.markdown("")  # Spacer

            # Investment Allocation
            if recommendation.btc_amount_usd > 0 or recommendation.eth_amount_usd > 0:
                st.markdown("#### 💰 Investment Breakdown")

                # Rescale BTC/ETH to the Capital Router's ACTUAL DCA base
                # (dca_usd above), not recommendation.dca_amount_usd directly —
                # those only agree when yield_slots is empty (100% to DCA);
                # on a week a yield opportunity clears gates, dca_usd is the
                # post-yield-carve-out figure and Investment Breakdown must
                # reflect that same reduced base, not the pre-yield total.
                _reco_dca = recommendation.dca_amount_usd
                if _reco_dca > 0:
                    _btc_weight = recommendation.btc_amount_usd / _reco_dca
                    _eth_weight = recommendation.eth_amount_usd / _reco_dca
                else:
                    _btc_weight = _eth_weight = 0.0
                btc_amount_usd = dca_usd * _btc_weight
                eth_amount_usd = dca_usd * _eth_weight

                total_crypto_dca = btc_amount_usd + eth_amount_usd
                btc_pct = (btc_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0
                eth_pct = (eth_amount_usd / total_crypto_dca * 100) if total_crypto_dca > 0 else 0

                assert abs(total_crypto_dca - dca_usd) < 0.01, \
                    "BTC+ETH allocation must equal the Capital Router's DCA amount"

                base_dca = st.session_state.base_weekly_dca
                multiplier = total_crypto_dca / base_dca if base_dca > 0 else 1.0
                if abs(multiplier - 1.0) > 0.01:
                    st.info(f"This Week's Total: ${total_crypto_dca:,.2f} ({multiplier:.1f}x your ${base_dca:,.0f} baseline)")
                else:
                    st.info(f"This Week's Total: ${total_crypto_dca:,.2f}")

                col_btc2, col_eth2 = st.columns(2)
                with col_btc2:
                    st.metric("Bitcoin (BTC)", f"${btc_amount_usd:,.2f}", f"{btc_pct:.1f}% allocation")
                with col_eth2:
                    st.metric("Ethereum (ETH)", f"${eth_amount_usd:,.2f}", f"{eth_pct:.1f}% allocation")
                
                if 'date_range' in signals:
                    st.caption(f"📊 Historical Data: {signals.get('data_days', 0):,} days ({signals['date_range']})")
            elif recommendation.cycle_phase == CyclePhase.BULL_REDUCE:
                st.markdown("#### 💰 Investment Breakdown")
                col_btc2, col_eth2 = st.columns(2)
                with col_btc2:
                    st.metric("Bitcoin (BTC)", "$0.00")
                with col_eth2:
                    st.metric("Ethereum (ETH)", "$0.00")
                st.caption("DCA paused — preparing for rotation")
        
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
        # Top rotation banner — crypto→metals+stables
        elif recommendation.rotation_direction == 'crypto_to_metals_and_stables':
            rotation_pct = recommendation.rotation_percentage
            st.error(
                f"🚨 **TOP ROTATION SIGNAL ACTIVE** — "
                f"Rotate {rotation_pct:.0f}% → Metals {rotation_pct*0.70:.1f}% (gold 70% / silver 30%) "
                f"+ Stables {rotation_pct*0.30:.1f}% (Aave/sDAI). "
                f"{recommendation.reasoning}"
            )

        # Direction selector — default to signal recommendation if present
        direction_options = [
            "METALS_TO_CRYPTO",
            "CRYPTO_TO_METALS_AND_STABLES",
            "BTC_TO_GOLD", "ETH_TO_GOLD",
            "BTC_TO_SILVER", "ETH_TO_SILVER",
        ]
        default_direction = (
            "METALS_TO_CRYPTO"
            if recommendation.rotation_direction == "metals_to_crypto"
            else "CRYPTO_TO_METALS_AND_STABLES"
            if recommendation.rotation_direction == "crypto_to_metals_and_stables"
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
