#!/usr/bin/env python3
"""
signal_core.py — single source of truth for cycle/Kelly/rotation/allocation signals.

This module is shared VERBATIM between:
  ~/projects/willie-agent-stack/crypto/signal_core.py   (authoritative copy)
  ~/projects/cryptologix/signal_core.py                 (synced copy)

The two repos cannot share imports (cryptologix deploys standalone to
Streamlit Cloud), so the file is copied. Drift detection:
  - crypto_data_collector.py hashes both copies daily and raises a CRITICAL
    alert on mismatch (see check_signal_core_sync in the collector).
  - cryptologix/check_sync.py does the same check pre-push when run locally.
Edit the willie-agent-stack copy first, then copy to cryptologix.

Design principles:
  - Pure functions, stdlib-only (math/hashlib). No pandas/yfinance here —
    callers pass in percentiles/vols/returns they computed from their own
    data pipelines, so this file runs identically in both environments.
  - Every constant is either derived in-code or carries provenance comments.
"""
import math
import hashlib
import os

SIGNAL_CORE_VERSION = "1.0.0"

# ────────────────────────────────────────────────────────────────────────────
# EMPIRICAL 90-DAY FORWARD RETURN TABLES
#
# Provenance: bootstrapped 2026-07-02 from Yahoo Finance daily closes
# (BTC-USD 2014-09-17→2026-07-02, ETH-USD 2017-11-09→, SOL-USD 2020-04-10→).
# Method: for each day with ≥400 trading days in the trailing 730 calendar
# days, rank the close within that trailing window (same percentile method
# as cycle_percentile below), record the +90-calendar-day forward return,
# bucket by percentile band, take median and IQR. Regenerate with
# willie-agent-stack/crypto/tools/bootstrap_returns.py (same script archived
# in git) whenever recalibrating.
#
# Notable: BTC's 5-15 band median is NEGATIVE (bear-continuation days of
# 2015/2018/2022 dominate, n=51) while ETH's is +21%. SOL's 0-5 band is
# negative (FTX collapse). Small n at the extremes → treat these as noisy
# anchors, not gospel; kelly_split shrinks per-asset medians toward the
# cross-asset blend for exactly this reason.
# ────────────────────────────────────────────────────────────────────────────
RETURN_BANDS = [(0, 5), (5, 15), (15, 30), (30, 45), (45, 60),
                (60, 75), (75, 85), (85, 100)]

EMPIRICAL_90D_RETURNS = {
    #        (lo, hi): (median, iqr, n)
    "BTC": {(0, 5): (0.4511, 0.3104, 58),   (5, 15): (-0.0957, 0.2728, 51),
            (15, 30): (-0.0094, 0.3700, 215), (30, 45): (0.1087, 0.6191, 377),
            (45, 60): (-0.1246, 0.4402, 342), (60, 75): (-0.0554, 0.4258, 360),
            (75, 85): (0.1866, 0.4187, 506),  (85, 100): (0.1408, 0.6549, 1702)},
    "ETH": {(0, 5): (0.6245, 0.3895, 36),   (5, 15): (0.2106, 0.4187, 211),
            (15, 30): (0.2394, 0.5631, 379),  (30, 45): (-0.0078, 0.3115, 381),
            (45, 60): (-0.1333, 0.5501, 291), (60, 75): (0.0989, 0.7335, 278),
            (75, 85): (0.2354, 0.7249, 235),  (85, 100): (0.0689, 0.7450, 782)},
    "SOL": {(0, 5): (-0.0560, 0.2099, 56),  (5, 15): (0.1217, 0.7458, 198),
            (15, 30): (-0.0375, 0.6369, 197), (30, 45): (-0.2817, 0.9994, 123),
            (45, 60): (-0.0332, 0.4764, 159), (60, 75): (0.1046, 0.7894, 157),
            (75, 85): (0.0497, 1.0578, 259),  (85, 100): (-0.0434, 0.7481, 599)},
}

# Annualized daily-return vol over the trailing 2 years (same bootstrap run).
# Callers should pass live-computed vols when available; these are fallbacks.
DEFAULT_VOL_ANN = {"BTC": 0.4665, "ETH": 0.7100, "SOL": 0.7990}

UBI_TARGET_MONTHLY = 1500.0


# ────────────────────────────────────────────────────────────────────────────
# CYCLE PERCENTILE
# ────────────────────────────────────────────────────────────────────────────
CYCLE_WINDOW_DAYS = 730  # 2-year rolling window, matches both pipelines


def cycle_percentile(state: dict) -> float:
    """Blended cycle percentile = mean of BTC/USD and ETH/USD percentile
    ranks within the trailing 730-calendar-day window.

    Accepts a crypto_state.json-shaped dict (reads state['ratios']) or a
    ratios dict directly (btc_usd_pct / eth_usd_pct keys)."""
    r = state.get("ratios", state) or {}
    if r.get("avg_percentile") is not None and "btc_usd_pct" not in r:
        return float(r["avg_percentile"])
    btc = float(r.get("btc_usd_pct", 50) or 50)
    eth = float(r.get("eth_usd_pct", 50) or 50)
    return round((btc + eth) / 2, 1)


def percentile_rank(window_values, current_value) -> float:
    """Share of window values <= current, in [0,100]. Both pipelines use
    this exact definition so percentiles are comparable."""
    vals = [v for v in window_values if v is not None]
    if not vals:
        return 50.0
    return round(sum(1 for v in vals if v <= current_value) / len(vals) * 100, 1)


# Unified phase thresholds (previously the two repos disagreed:
# collector used <10 AGGRESSIVE / <45 ACC / <85 BULL / ≥85 TOP;
# cryptologix used <15 AGGRESSIVE, 75-85 BULL_REDUCE, ≥92 ULTRA_TOP).
PHASE_THRESHOLDS = [
    (5, "EXTREME_BOTTOM"),
    (15, "AGGRESSIVE_DCA"),
    (45, "ACCUMULATION"),
    (75, "BULL_MARKET"),
    (85, "BULL_REDUCE"),
    (92, "EXTREME_TOP"),
    (101, "ULTRA_TOP"),
]


def classify_phase(avg_pct: float) -> str:
    for hi, name in PHASE_THRESHOLDS:
        if avg_pct < hi:
            return name
    return "ULTRA_TOP"


# ────────────────────────────────────────────────────────────────────────────
# CONTINUOUS GTO DCA MULTIPLIER
#
# Single logistic passing exactly through three anchors:
#   m(0)  = 3.0   maximum deploy (liquidity cap: 3x base is the most that can
#                 clear weekly without touching protected positions)
#   m(35) = 1.0   neutral baseline (35th pct = accumulation_regime thesis
#                 invalidation threshold already used by the advisor)
#   m(50) = 0.5   capital preservation / yield rotation begins
# Solving m(p) = M / (1 + exp(k*(p - p0))) for those anchors gives
# M≈4.5589, k≈0.05497, p0≈11.898 (closed-form: 1+u=M, 1+v=2M, 1+w=M/3 with
# u,v,w the exponentials at 35/50/0; M solves
# 35/15 = ln((M-1)/(M/3-1)) / ln((2M-1)/(M-1))).
# m decays smoothly toward 0 above the 85th pct (m(85)≈0.08) — DCA never
# steps discontinuously to zero the way the old 8-branch table did.
# ────────────────────────────────────────────────────────────────────────────
_GTO_M = 4.558929
_GTO_K = 0.0549679
_GTO_P0 = 11.89815


def gto_multiplier(cycle_pct: float) -> float:
    """Continuous Kelly-scaled DCA multiplier of weekly base budget."""
    p = min(max(float(cycle_pct), 0.0), 100.0)
    return round(_GTO_M / (1.0 + math.exp(_GTO_K * (p - _GTO_P0))), 4)


# ────────────────────────────────────────────────────────────────────────────
# EXPECTED RETURN (empirical, no hardcoded guesses)
# ────────────────────────────────────────────────────────────────────────────
def expected_90d_return(cycle_pct: float, historical_data: dict = None,
                        asset: str = None) -> tuple:
    """Returns (median_return, confidence_interval_width) for a 90-day
    horizon at the given cycle percentile.

    historical_data: optional {"ASSET": {(lo,hi): (median, iqr, n)}} table —
    e.g. a freshly bootstrapped one from the collector. Defaults to the
    module's EMPIRICAL_90D_RETURNS (provenance in header).
    asset: "BTC"/"ETH"/"SOL" for a single asset; None = BTC+ETH blend
    (the DCA-relevant pair). Linear interpolation between band centers so the
    output is continuous in cycle_pct — no step function."""
    tables = historical_data or EMPIRICAL_90D_RETURNS
    assets = [asset] if asset else ["BTC", "ETH"]
    meds, iqrs = [], []
    for a in assets:
        tbl = tables.get(a)
        if not tbl:
            continue
        pts = []  # (band_center, median, iqr)
        for (lo, hi) in RETURN_BANDS:
            entry = tbl.get((lo, hi))
            if entry and entry[0] is not None:
                pts.append(((lo + hi) / 2.0, entry[0], entry[1]))
        if not pts:
            continue
        p = min(max(float(cycle_pct), pts[0][0]), pts[-1][0])
        med = pts[0][1]
        iqr = pts[0][2]
        for (c0, m0, i0), (c1, m1, i1) in zip(pts, pts[1:]):
            if c0 <= p <= c1:
                t = (p - c0) / (c1 - c0) if c1 > c0 else 0.0
                med = m0 + t * (m1 - m0)
                iqr = i0 + t * (i1 - i0)
                break
        meds.append(med)
        iqrs.append(iqr)
    if not meds:
        return (0.0, 0.0)
    return (round(sum(meds) / len(meds), 4), round(sum(iqrs) / len(iqrs), 4))


# ────────────────────────────────────────────────────────────────────────────
# KELLY-DERIVED ASSET SPLIT (BTC / ETH / SOL)
#
# Continuous-time Kelly for asset i (independent approx): f_i = μ_i / σ_i².
# μ_i = empirical 90d expected return at that asset's own cycle percentile,
# shrunk 50% toward the cross-asset blend (small-n bands are noisy — see
# table provenance). σ_i = 90d vol from annualized vol × sqrt(90/365).
# Weights = f_i / Σf_j, then clipped to sanity bounds and renormalized:
#   BTC, ETH ∈ [0.25, 0.65]  (neither core asset abandoned on noisy medians)
#   SOL ∈ [0.05, 0.15]       (satellite: capped — highest vol, shortest
#                             history, empirically weakest bottom signal)
# Correlation note: BTC/ETH/SOL daily correlations run 0.6-0.85, which under
# joint Kelly (Σ⁻¹μ) shrinks ALL positions roughly proportionally rather
# than reordering them — the total budget is set by gto_multiplier, so the
# proportional shrink cancels in the normalized split. Hence the independent
# approximation + bounds is used deliberately; correlation is handled at the
# sizing layer (the 1/8 fractional cap in the advisor), not the split layer.
# ────────────────────────────────────────────────────────────────────────────
KELLY_BOUNDS = {"BTC": (0.25, 0.65), "ETH": (0.25, 0.65), "SOL": (0.05, 0.15)}


def kelly_split(state_or_percentiles, vols: dict = None,
                return_tables: dict = None) -> dict:
    """Kelly-derived DCA split across BTC/ETH/SOL.

    Accepts a crypto_state.json-shaped dict OR a percentile dict like
    {"BTC": 9.7, "ETH": 3.8, "SOL": 50}. Missing SOL percentile falls back
    to the BTC/ETH average. Returns {"BTC": w, "ETH": w, "SOL": w} summing
    to 1.0, plus "_diag" with the raw Kelly fractions."""
    sp = state_or_percentiles or {}
    if "ratios" in sp or "btc_usd_pct" in sp.get("ratios", sp):
        r = sp.get("ratios", sp) or {}
        pcts = {"BTC": float(r.get("btc_usd_pct", 50) or 50),
                "ETH": float(r.get("eth_usd_pct", 50) or 50),
                "SOL": float(r.get("sol_usd_pct") or
                             (float(r.get("btc_usd_pct", 50) or 50) +
                              float(r.get("eth_usd_pct", 50) or 50)) / 2)}
        vols = vols or r.get("vols")
    else:
        pcts = {k.upper(): float(v) for k, v in sp.items()}
        if "SOL" not in pcts:
            pcts["SOL"] = (pcts.get("BTC", 50) + pcts.get("ETH", 50)) / 2
    vols = {k.upper(): float(v) for k, v in (vols or {}).items()} if vols else dict(DEFAULT_VOL_ANN)

    blend_mu, _ = expected_90d_return((pcts["BTC"] + pcts["ETH"]) / 2,
                                      return_tables)
    fracs = {}
    for a in ("BTC", "ETH", "SOL"):
        mu_own, _ = expected_90d_return(pcts[a], return_tables, asset=a)
        mu = 0.5 * mu_own + 0.5 * blend_mu  # shrink toward blend (noisy bands)
        vol_90d = vols.get(a, DEFAULT_VOL_ANN[a]) * math.sqrt(90.0 / 365.0)
        fracs[a] = max(0.0, mu) / (vol_90d ** 2) if vol_90d > 0 else 0.0

    total = sum(fracs.values())
    if total <= 0:
        weights = {"BTC": 0.40, "ETH": 0.45, "SOL": 0.15}  # all-negative-mu fallback
    else:
        weights = {a: f / total for a, f in fracs.items()}
    # clip to bounds, renormalize (iterate twice — enough for 3 assets)
    for _ in range(2):
        clipped = {a: min(max(w, KELLY_BOUNDS[a][0]), KELLY_BOUNDS[a][1])
                   for a, w in weights.items()}
        s = sum(clipped.values())
        weights = {a: w / s for a, w in clipped.items()}
    out = {a: round(w, 4) for a, w in weights.items()}
    out["_diag"] = {"kelly_fractions": {a: round(f, 4) for a, f in fracs.items()},
                    "percentiles": pcts}
    return out


def kelly_split_btc_eth(btc_percentile: float, eth_percentile: float) -> tuple:
    """Two-asset convenience wrapper (legacy call sites: cryptologix
    ExponentialCycleEngine, advisor Kelly line). Returns (btc_w, eth_w)
    renormalized over BTC+ETH only."""
    w = kelly_split({"BTC": btc_percentile, "ETH": eth_percentile})
    be = w["BTC"] + w["ETH"]
    return (round(w["BTC"] / be, 4), round(w["ETH"] / be, 4))


# ────────────────────────────────────────────────────────────────────────────
# ROTATION TRIGGERS (metals ↔ crypto) — unified for both repos
# ────────────────────────────────────────────────────────────────────────────
def rotation_trigger(btc_gold_pct: float, eth_gold_pct: float) -> dict:
    """Metals→crypto rotation. Dual-signal: BOTH BTC/Gold AND ETH/Gold must
    be below the 5th percentile of the 730-day window (~25 trading days of
    the window — rare by construction; 'watch' when only one side fires).
    Rotation size scales continuously with depth: 40% at the 5th pct up to
    75% at the 0th (replaces the old 75/61.5/40 steps)."""
    b, e = float(btc_gold_pct), float(eth_gold_pct)
    avg = (b + e) / 2
    if b < 5.0 and e < 5.0:
        size = round(min(75.0, max(40.0, 75.0 - 7.0 * avg)), 1)
        return {"signal": "triggered", "direction": "metals_to_crypto",
                "rotation_pct": size, "avg_gold_pct": round(avg, 1)}
    if b < 5.0 or e < 5.0:
        return {"signal": "watch", "direction": None, "rotation_pct": 0.0,
                "avg_gold_pct": round(avg, 1)}
    return {"signal": "none", "direction": None, "rotation_pct": 0.0,
            "avg_gold_pct": round(avg, 1)}


def top_rotation_pct(avg_pct: float) -> float:
    """Crypto→metals+stables rotation share at cycle tops. Continuous ramp
    from 30% at the 85th pct to 90% at the 97th+ (replaces the advisor's
    75/60/45/30 steps and the engine's flat 85/90)."""
    p = float(avg_pct)
    if p < 85.0:
        return 0.0
    return round(min(90.0, 30.0 + (p - 85.0) * 5.0), 1)


# ────────────────────────────────────────────────────────────────────────────
# CYCLE-CONDITIONAL CAPITAL ROUTER
# ────────────────────────────────────────────────────────────────────────────
def allocate_capital(cycle_pct: float, available_capital: float,
                     yield_opportunities: list = None) -> dict:
    """Route weekly deployable capital between spot DCA and yield positions
    as a function of the cycle percentile.

      < 15th:   100% DCA — directional upside dominates any carry.
      15-35th:  linear blend, DCA share 1.0 → 0.40.
      35-50th:  yield primary, DCA share 0.40 → 0.25.
      > 50th:   DCA 25%, remainder to yield; profit-taking review flagged.

    yield_opportunities: [{"name": str, "apy": float, ...}] sorted or not;
    yield capital is split across the top 3 by APY, 50/30/20."""
    p = min(max(float(cycle_pct), 0.0), 100.0)
    cap = max(0.0, float(available_capital))
    if p < 15.0:
        dca_frac = 1.0
    elif p < 35.0:
        dca_frac = 1.0 - 0.60 * (p - 15.0) / 20.0
    elif p < 50.0:
        dca_frac = 0.40 - 0.15 * (p - 35.0) / 15.0
    else:
        dca_frac = 0.25
    dca_usd = round(cap * dca_frac, 2)
    yield_usd = round(cap - dca_usd, 2)
    slots = []
    if yield_usd > 0 and yield_opportunities:
        top = sorted(yield_opportunities,
                     key=lambda o: -(o.get("apy") or 0))[:3]
        shares = [0.5, 0.3, 0.2][:len(top)]
        norm = sum(shares)
        for o, s in zip(top, shares):
            slots.append({"opportunity": o.get("name") or o.get("pool", "?"),
                          "apy": o.get("apy"),
                          "amount": round(yield_usd * s / norm, 2)})
    return {"dca": dca_usd, "yield_usd": yield_usd, "yield_slots": slots,
            "dca_frac": round(dca_frac, 4),
            "profit_taking_review": p >= 50.0}


# ────────────────────────────────────────────────────────────────────────────
# CARRY-TRADE MINIMUM VIABLE SIZE (replaces the arbitrary 0.1 ETH gate)
# ────────────────────────────────────────────────────────────────────────────
def carry_min_eth(funding_ann_pct: float, eth_price: float,
                  fixed_costs_usd: float = 12.0,
                  taker_fee_pct: float = 0.07,
                  payback_days: int = 30) -> float:
    """Smallest ETH position where expected funding over `payback_days`
    covers round-trip costs. Costs: 2× taker fee (0.035% Hyperliquid taker
    ×2 legs ≈ 0.07% of notional each way → 0.14% round trip) plus ~$12
    fixed (bridge gas + spot-leg transfer). Returns ETH, floored at 0.02."""
    if funding_ann_pct <= 0 or eth_price <= 0:
        return float("inf")
    daily = funding_ann_pct / 100.0 / 365.0
    fee_frac = 2 * taker_fee_pct / 100.0
    denom = daily * payback_days - fee_frac
    if denom <= 0:
        return float("inf")
    return round(max(0.02, fixed_costs_usd / (denom * eth_price)), 4)


# ────────────────────────────────────────────────────────────────────────────
# UBI GAP TRACKER
# ────────────────────────────────────────────────────────────────────────────
def ubi_gap_report(yield_sources: dict, target_monthly: float = UBI_TARGET_MONTHLY,
                   portfolio_usd: float = None, cycle_pct: float = None) -> dict:
    """UBI gap = target monthly income minus current distributable yield.

    yield_sources: {"name": annual_usd, ...} (annual USD per source).
    Returns gap, coverage %, and — when portfolio_usd/cycle_pct given — a
    base-case months-to-close estimate assuming yield-bearing capital grows
    via the empirical 90d expected return (annualized) plus reinvested yield,
    at a blended deployable-yield rate equal to the current portfolio-wide
    yield rate (no heroic assumptions)."""
    annual = {k: float(v or 0) for k, v in (yield_sources or {}).items()}
    total_annual = sum(annual.values())
    monthly = total_annual / 12.0
    gap = max(0.0, target_monthly - monthly)
    out = {"target_monthly": round(target_monthly, 2),
           "current_monthly": round(monthly, 2),
           "gap_monthly": round(gap, 2),
           "coverage_pct": round(monthly / target_monthly * 100, 1) if target_monthly else 0.0,
           "sources_annual": {k: round(v, 2) for k, v in annual.items()},
           "months_to_close_base_case": None}
    if gap > 0 and portfolio_usd and portfolio_usd > 0 and total_annual > 0:
        yield_rate = total_annual / portfolio_usd  # blended realized yield on NAV
        growth_ann = 0.0
        if cycle_pct is not None:
            med90, _ = expected_90d_return(cycle_pct)
            growth_ann = max(0.0, (1 + med90) ** (365.0 / 90.0) - 1)
        # months until portfolio_usd*(1+g)^t * yield_rate / 12 >= target
        needed_nav = target_monthly * 12.0 / yield_rate
        g_m = (1 + growth_ann) ** (1 / 12.0) - 1
        if needed_nav <= portfolio_usd:
            out["months_to_close_base_case"] = 0
        elif g_m > 0:
            months = math.log(needed_nav / portfolio_usd) / math.log(1 + g_m)
            out["months_to_close_base_case"] = round(months, 1)
        out["base_case_assumptions"] = {
            "blended_yield_rate_pct": round(yield_rate * 100, 2),
            "price_growth_ann_pct": round(growth_ann * 100, 1),
            "note": "growth from empirical 90d median at current cycle pct, "
                    "annualized; yield rate held constant on NAV"}
    return out


# ────────────────────────────────────────────────────────────────────────────
# SYNC CHECK
# ────────────────────────────────────────────────────────────────────────────
def file_hash(path: str = None) -> str:
    path = path or os.path.abspath(__file__)
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify_sync(other_path: str) -> dict:
    """Compare this file's hash with the sibling repo's copy."""
    try:
        mine, theirs = file_hash(), file_hash(os.path.expanduser(other_path))
        return {"in_sync": mine == theirs, "mine": mine[:12], "theirs": theirs[:12]}
    except FileNotFoundError:
        return {"in_sync": False, "error": f"missing: {other_path}"}


if __name__ == "__main__":
    # anchor self-test
    assert abs(gto_multiplier(0) - 3.0) < 0.01, gto_multiplier(0)
    assert abs(gto_multiplier(35) - 1.0) < 0.01, gto_multiplier(35)
    assert abs(gto_multiplier(50) - 0.5) < 0.01, gto_multiplier(50)
    assert gto_multiplier(85) < 0.12
    m, w = expected_90d_return(2.5)
    assert m > 0.4, m
    ks = kelly_split({"BTC": 9.7, "ETH": 3.8})
    assert abs(sum(v for k, v in ks.items() if k != "_diag") - 1.0) < 1e-6
    alloc = allocate_capital(6.8, 1000, [{"name": "sUSDai", "apy": 7.8}])
    assert alloc["dca"] == 1000.0
    alloc2 = allocate_capital(25, 1000, [{"name": "sUSDai", "apy": 7.8}])
    assert 0 < alloc2["yield_usd"] < 1000
    print("signal_core self-test OK",
          {"gto(6.8)": gto_multiplier(6.8), "split": ks,
           "e90(6.8)": expected_90d_return(6.8),
           "alloc(6.8)": alloc, "alloc(25)": alloc2,
           "rot": rotation_trigger(9.1, 6.0),
           "carry_min": carry_min_eth(10.95, 2400)})
