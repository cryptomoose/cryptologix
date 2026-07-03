"""
UBI Gap dashboard — top-level objective tracker.

Renders the gap between target monthly passive income and current
distributable yield, plus the cycle-conditional capital router.
All math comes from signal_core (shared verbatim with the crypto engine);
this module is presentation only. The app is public, so portfolio and
yield figures are user inputs (session-persisted), never hardcoded.
"""

import streamlit as st

from signal_core import (
    UBI_TARGET_MONTHLY,
    allocate_capital,
    expected_90d_return,
    ubi_gap_report,
)


def render_ubi_gap_section(cycle_pct: float, weekly_dca_usd: float):
    """Prominent UBI Gap + Capital Router panel.

    cycle_pct: blended BTC/ETH USD cycle percentile (same input the
    crypto engine feeds signal_core).
    weekly_dca_usd: this week's recommended DCA (already GTO-scaled),
    used as the available capital for the router.
    """
    st.markdown("## 🎯 UBI Gap — Top-Level Objective")
    st.caption(
        "Every allocation decision serves one goal: closing the gap between "
        "target monthly passive income and current distributable yield. "
        "Same math as the daily advisory engine (signal_core)."
    )

    with st.expander("⚙️ Your income inputs", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            target_monthly = st.number_input(
                "Target monthly income (USD)",
                min_value=0.0, value=float(UBI_TARGET_MONTHLY), step=100.0,
                key="ubi_target_monthly",
            )
            portfolio_usd = st.number_input(
                "Yield-bearing portfolio value (USD)",
                min_value=0.0, value=100_000.0, step=1000.0,
                key="ubi_portfolio_usd",
                help="Total NAV of capital that produces or will produce yield.",
            )
        with c2:
            validators_ann = st.number_input(
                "Staking / validators (annual USD)",
                min_value=0.0, value=0.0, step=100.0, key="ubi_validators_ann",
            )
            carry_ann = st.number_input(
                "Funding / carry (annual USD)",
                min_value=0.0, value=0.0, step=100.0, key="ubi_carry_ann",
            )
            stable_ann = st.number_input(
                "Stablecoin yield (annual USD)",
                min_value=0.0, value=0.0, step=100.0, key="ubi_stable_ann",
            )

    report = ubi_gap_report(
        yield_sources={
            "validators": validators_ann,
            "carry_trade": carry_ann,
            "stablecoin": stable_ann,
        },
        target_monthly=target_monthly,
        portfolio_usd=portfolio_usd or None,
        cycle_pct=cycle_pct,
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Target / mo", f"${report['target_monthly']:,.0f}")
    m2.metric("Current yield / mo", f"${report['current_monthly']:,.0f}")
    m3.metric(
        "Gap / mo",
        f"${report['gap_monthly']:,.0f}",
        delta=f"-{report['coverage_pct']:.1f}% covered",
        delta_color="off",
    )
    mtc = report.get("months_to_close_base_case")
    m4.metric(
        "Months to close (base case)",
        "—" if mtc is None else f"{mtc:,.1f}",
    )

    st.progress(min(1.0, report["coverage_pct"] / 100.0))
    assumptions = report.get("base_case_assumptions")
    if assumptions:
        st.caption(
            f"Base case: {assumptions['blended_yield_rate_pct']:.2f}% blended yield on NAV, "
            f"{assumptions['price_growth_ann_pct']:.1f}%/yr fixed price-appreciation assumption "
            "(a conservative full-cycle BTC/ETH/SOL figure, not an annualized 90-day return)."
        )
    elif report["current_monthly"] == 0:
        st.info(
            "Enter your yield sources above to track the gap. "
            "With no yield sources, coverage is 0% by definition."
        )

    # ── Capital router — cycle-conditional DCA vs yield split ──────────────
    st.markdown("### 🚦 Capital Router")
    router = allocate_capital(cycle_pct, weekly_dca_usd)
    dca_usd = router["dca"]
    yield_usd = router["yield_usd"]

    r1, r2, r3 = st.columns(3)
    r1.metric("This week's capital", f"${weekly_dca_usd:,.0f}")
    r2.metric("→ DCA (cycle accumulation)", f"${dca_usd:,.0f}")
    r3.metric("→ Yield deployment", f"${yield_usd:,.0f}")

    med, iqr = expected_90d_return(cycle_pct)
    st.caption(
        f"At the {cycle_pct:.1f}th percentile, {router['dca_frac']*100:.0f}% of new capital "
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
