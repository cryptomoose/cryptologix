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
import logging
from datetime import date

log = logging.getLogger(__name__)

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


def _raw_cycle_percentile(state: dict) -> float:
    """Unsmoothed blended cycle percentile = mean of BTC/USD and ETH/USD
    percentile ranks within the trailing 730-calendar-day window.

    Accepts a crypto_state.json-shaped dict (reads state['ratios']) or a
    ratios dict directly (btc_usd_pct / eth_usd_pct keys)."""
    r = state.get("ratios", state) or {}
    if r.get("avg_percentile") is not None and "btc_usd_pct" not in r:
        return float(r["avg_percentile"])
    btc = float(r.get("btc_usd_pct", 50) or 50)
    eth = float(r.get("eth_usd_pct", 50) or 50)
    return round((btc + eth) / 2, 1)


# Investigated 2026-07-02: cycle_percentile's own formula has no fear/greed
# term and no outsized single-component weight (it's a plain BTC/ETH rank
# average) — the swings traced to real BTC/ETH price moves (several percent
# over a few days) landing in the sparse left tail of the trailing-730d
# distribution, where the rank statistic is inherently high-derivative:
# a handful of historically-similar low prices sit close together, so a
# small % move can jump the rank past many of them at once. That's not a
# bug in the inputs, but it does make the raw number noisy day-to-day at
# cycle extremes — hence the smoothing guard below.
CYCLE_PCT_SMOOTHING_ALPHA = 0.3
CYCLE_PCT_JUMP_THRESHOLD_PP = 3.0
CYCLE_PCT_STABLE_BTC_MOVE_PCT = 2.0


def cycle_percentile(state: dict) -> float:
    """Blended cycle percentile (see _raw_cycle_percentile), with a
    stability guard: if the raw value jumps >3pp from the last computed
    value while BTC's 24h move is <2%, the jump is presumed to be
    rank-statistic noise (see note above) rather than a genuine regime
    change, and is damped via exponential smoothing (alpha=0.3) instead of
    passed through raw. Mutates state['cycle_percentile_prev'] and
    state['cycle_percentile_smoothing_applied'] as a side effect so the
    caller can persist them for the next run."""
    new_pct = _raw_cycle_percentile(state)
    prev_pct = state.get("cycle_percentile_prev")
    _btc_change = state.get("btc_24h_change_pct")
    if _btc_change is None:
        _btc_change = (state.get("prices", {}) or {}).get("btc_24h", 0)
    btc_change_pct = abs(float(_btc_change or 0))

    if prev_pct is not None:
        prev_pct = float(prev_pct)
        pct_change = abs(new_pct - prev_pct)
        if (pct_change > CYCLE_PCT_JUMP_THRESHOLD_PP and
                btc_change_pct < CYCLE_PCT_STABLE_BTC_MOVE_PCT):
            log.warning(f"Cycle percentile unstable: {prev_pct:.1f} -> {new_pct:.1f} "
                        f"on {btc_change_pct:.1f}% BTC move — applying smoothing")
            smoothed = round(CYCLE_PCT_SMOOTHING_ALPHA * new_pct +
                             (1 - CYCLE_PCT_SMOOTHING_ALPHA) * prev_pct, 2)
            state["cycle_percentile_prev"] = smoothed
            state["cycle_percentile_smoothing_applied"] = True
            return smoothed

    state["cycle_percentile_prev"] = new_pct
    state["cycle_percentile_smoothing_applied"] = False
    return new_pct


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


ROTATION_PROXIMITY_THRESHOLD_PP = 1.0  # alert when within 1pp of the 5th-pct trigger


def rotation_proximity_alert(state: dict):
    """Warn when either leg of the metals<->crypto dual rotation trigger
    (rotation_trigger above) is close enough that physical-metals sell
    orders should be prepped now — execution lag on those orders (1-3
    days) means waiting for the dual trigger to actually fire is too late.
    Accepts a crypto_state.json-shaped dict (reads state['ratios']) or a
    ratios dict directly. Returns None if both legs are >1pp from trigger."""
    r = state.get("ratios", state) or {}
    btc_gold_pct = float(state.get('btc_gold_percentile') if state.get('btc_gold_percentile') is not None
                         else r.get('btc_gold_pct', 100) or 100)
    eth_gold_pct = float(state.get('eth_gold_percentile') if state.get('eth_gold_percentile') is not None
                         else r.get('eth_gold_pct', 100) or 100)
    trigger = 5.0

    btc_gap = btc_gold_pct - trigger
    eth_gap = eth_gold_pct - trigger

    if eth_gap <= ROTATION_PROXIMITY_THRESHOLD_PP or btc_gap <= ROTATION_PROXIMITY_THRESHOLD_PP:
        closer_leg = 'ETH/Gold' if eth_gap <= btc_gap else 'BTC/Gold'
        closer_gap = min(eth_gap, btc_gap)
        return {
            'type': 'ROTATION_PROXIMITY',
            'eth_gold_pct': eth_gold_pct,
            'btc_gold_pct': btc_gold_pct,
            'eth_gap_pp': round(eth_gap, 2),
            'btc_gap_pp': round(btc_gap, 2),
            'closer_leg': closer_leg,
            'closer_gap_pp': round(closer_gap, 2),
            'dual_trigger_fired': btc_gold_pct < trigger and eth_gold_pct < trigger
        }
    return None


def top_rotation_pct(avg_pct: float) -> float:
    """Crypto→metals+stables rotation share at cycle tops. Continuous ramp
    from 30% at the 85th pct to 90% at the 97th+ (replaces the advisor's
    75/60/45/30 steps and the engine's flat 85/90)."""
    p = float(avg_pct)
    if p < 85.0:
        return 0.0
    return round(min(90.0, 30.0 + (p - 85.0) * 5.0), 1)


# ────────────────────────────────────────────────────────────────────────────
# YIELD OPPORTUNITY RISK-ADJUSTED SCORING
#
# score = APY * ln(TVL_millions)**1.5 * audit_factor — TVL exponent raised
# from 1.0 to 1.5 because the plain-log version was APY-dominated: it let
# small unaudited pools outscore large audited ones by 3-4x on APY alone.
# Two gates sit in front of the score:
#   1. TVL floor — below it, WATCH LIST only, never primary allocation.
#   2. Audit floor for primary allocation above $500 — even a good score
#      can't carry an unaudited protocol into a >$500 primary slot.
# ────────────────────────────────────────────────────────────────────────────
PRIMARY_TVL_FLOOR_USD = 500.0
PRIMARY_MIN_TVL_M = 75.0     # TVL floor (millions) for allocations > $500
SECONDARY_MIN_TVL_M = 25.0   # TVL floor (millions) for allocations <= $500
PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR = 0.8


def score_yield_opportunity(apy_pct: float, tvl_millions: float,
                            audit_factor: float) -> float:
    """Risk-adjusted score: APY * ln(TVL_millions)**1.5 * audit_factor.
    Callers should gate on TVL floors (PRIMARY_MIN_TVL_M / SECONDARY_MIN_TVL_M)
    and PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR before treating a high score as a
    primary-allocation recommendation — the score alone doesn't encode those
    hard gates."""
    if tvl_millions is None or tvl_millions <= 1:
        return 0.0
    return round(float(apy_pct) * (math.log(float(tvl_millions)) ** 1.5) * float(audit_factor), 2)


def eligible_for_primary(allocation_usd: float, tvl_millions: float,
                         audit_factor: float) -> bool:
    """Gate 1 (TVL floor, tiered by allocation size) + Gate 2 (audit floor
    above the $500 primary-allocation threshold)."""
    floor = PRIMARY_MIN_TVL_M if allocation_usd > PRIMARY_TVL_FLOOR_USD else SECONDARY_MIN_TVL_M
    if (tvl_millions or 0) < floor:
        return False
    if allocation_usd > PRIMARY_TVL_FLOOR_USD and audit_factor < PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR:
        return False
    return True


# ────────────────────────────────────────────────────────────────────────────
# CYCLE-CONDITIONAL CAPITAL ROUTER
#
# dca_frac is Kelly-derived, not an arbitrary step function. At each cycle
# percentile:
#   DCA edge   = E[90d DCA return]   - risk_free_per_90d
#   Yield edge = E[90d yield return] - risk_free_per_90d
#   Kelly DCA fraction = dca_edge / (dca_edge + yield_edge)
# risk_free_per_90d = 4.5% annual / 4 = 1.125% per 90d.
#
# Calibration points (E[90d yield] = 12% APY / 4 = 3.0% per 90d, held fixed
# as the "best available yield" reference; E[90d DCA] from the empirical
# 90d return table above at each percentile):
#   pct=0:   E[90d DCA]=+60.0% (max historical) vs E[90d yield]=+3.0% -> DCA Kelly=96.9%
#   pct=7:   E[90d DCA]=+23.4% vs E[90d yield]=+3.0% -> DCA Kelly=88.6%
#   pct=15:  E[90d DCA]=+18.0% vs E[90d yield]=+3.0% -> DCA Kelly=85.7%
#   pct=35:  E[90d DCA]=+8.0%  vs E[90d yield]=+3.0% -> DCA Kelly=72.7%
#   pct=50:  E[90d DCA]=+3.0%  vs E[90d yield]=+3.0% -> DCA Kelly=50.0%
#   pct=65:  E[90d DCA]=+0.0%  vs E[90d yield]=+3.0% -> DCA Kelly=0.0% (yield primary)
# Piecewise-linear interpolation between these anchors. The prior hardcoded
# 40%/25% breakpoints at the 35th/50th pct underweighted DCA relative to
# this math (Kelly supports ~73% DCA at the 35th pct, not 40%).
#
# The 0th-pct anchor used to be missing, so cycle_pct <= 7 flat-clamped at
# 88.6% — which silently contradicted the "100% DCA below 15th" framing used
# elsewhere (e.g. the capital-router fallback label). There is no discontinuity
# to fix in the math itself (Kelly was never actually 100% anywhere), but the
# curve is now anchored all the way to 0 so nothing downstream can describe it
# as flat/100% below any threshold. Kelly at 0th pct: (0.60 - 0.01125) /
# (0.60 - 0.01125 + 0.03 - 0.01125) = 96.9% — still short of 100%, which is
# correct Kelly behavior (yield always retains some edge as a hedge).
# ────────────────────────────────────────────────────────────────────────────
_KELLY_DCA_ANCHORS = [(0.0, 0.969), (7.0, 0.886), (15.0, 0.857), (35.0, 0.727),
                      (50.0, 0.500), (65.0, 0.0)]


def _kelly_dca_fraction(cycle_pct: float, best_yield_apy: float = 12.0) -> float:
    """Kelly-derived DCA fraction at a cycle percentile, piecewise-linear
    between _KELLY_DCA_ANCHORS. best_yield_apy is accepted for future
    recalibration (e.g. re-deriving anchors off a live yield figure instead
    of the fixed 12% APY reference) but the anchor table above already bakes
    in that reference, so it is not currently used to rescale mid-curve."""
    p = min(max(float(cycle_pct), 0.0), 100.0)
    anchors = _KELLY_DCA_ANCHORS
    if p <= anchors[0][0]:
        return anchors[0][1]
    if p >= anchors[-1][0]:
        return anchors[-1][1]
    for (p0, f0), (p1, f1) in zip(anchors, anchors[1:]):
        if p0 <= p <= p1:
            t = (p - p0) / (p1 - p0)
            return f0 + t * (f1 - f0)
    return anchors[-1][1]


def allocate_capital(cycle_pct: float, available_capital: float,
                     yield_opportunities: list = None) -> dict:
    """Route weekly deployable capital between spot DCA and yield positions
    via the Kelly-derived _kelly_dca_fraction (see module note above).

    yield_opportunities: [{"name": str, "apy": float, ...}] sorted or not;
    yield capital is split across the top 3 by APY, 50/30/20; the best APY
    among them (or 12.0 default) is passed to _kelly_dca_fraction."""
    p = min(max(float(cycle_pct), 0.0), 100.0)
    cap = max(0.0, float(available_capital))
    best_yield_apy = 12.0
    if yield_opportunities:
        apys = [o.get("apy") for o in yield_opportunities if o.get("apy")]
        if apys:
            best_yield_apy = max(apys)
    dca_frac = _kelly_dca_fraction(p, best_yield_apy)
    dca_usd = round(cap * dca_frac, 2)
    yield_usd = round(cap - dca_usd, 2)
    slots = []
    filtered_protocols = []
    if yield_usd > 0 and yield_opportunities:
        # Gate on audit_factor/tvl_m BEFORE ranking by APY — otherwise a high
        # APY on an unaudited or thin-TVL pool can win a primary slot on
        # yield alone (see eligible_for_primary / PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR
        # above). Missing audit_factor is NOT eligible-by-default: absence of
        # data is not evidence of an audit.
        eligible = []
        for o in yield_opportunities:
            tvl_m = o.get("tvl_m")
            audit_factor = o.get("audit_factor")
            if audit_factor is None or tvl_m is None:
                filtered_protocols.append({"opportunity": o.get("name") or o.get("pool", "?"),
                                           "apy": o.get("apy"), "audit_factor": audit_factor,
                                           "tvl_m": tvl_m, "reason": "missing audit_factor/tvl_m"})
                continue
            if eligible_for_primary(yield_usd, float(tvl_m), float(audit_factor)):
                eligible.append(o)
            else:
                filtered_protocols.append({"opportunity": o.get("name") or o.get("pool", "?"),
                                           "apy": o.get("apy"), "audit_factor": audit_factor,
                                           "tvl_m": tvl_m, "reason": "below audit/TVL floor"})
        top = sorted(eligible, key=lambda o: -(o.get("apy") or 0))[:3]
        shares = [0.5, 0.3, 0.2][:len(top)]
        norm = sum(shares) if top else 1
        for o, s in zip(top, shares):
            slots.append({"opportunity": o.get("name") or o.get("pool", "?"),
                          "apy": o.get("apy"),
                          "amount": round(yield_usd * s / norm, 2)})
    return {"dca": dca_usd, "yield_usd": yield_usd, "yield_slots": slots,
            "filtered_protocols": filtered_protocols,
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
# CARRY-TRADE RECHECK DATE
#
# The gate itself is carry_min_eth() above. This answers "when will the gate
# realistically open" — the naive version (gap / staking_accrual_only) ignores
# two near-term inflows that are already known and scheduled: the minipool
# distribute (claimable on demand, not a future accrual) and RPL unstaking
# proceeds converted to ETH (only counted if landing within 14 days — beyond
# that it's not "near-term" and shouldn't pull the recheck date forward).
# ────────────────────────────────────────────────────────────────────────────
def carry_trade_recheck_date(withdrawal_eth: float, minipool_pending_eth: float,
                             daily_accrual_eth: float, carry_min_eth_target: float,
                             rpl_unstaking_amount: float = 0.0, rpl_usd: float = 0.0,
                             eth_usd: float = 0.0, rpl_unstake_date: str = None,
                             carry_first_confirmed: bool = False,
                             today=None) -> dict:
    """Recheck date(s) for the carry-trade capital gate (carry_min_eth_target).

    RPL unstaking proceeds are only a near-term inflow toward this gate if the
    user has actually confirmed routing them there (carry_first_confirmed) —
    otherwise they're just as likely to go to sUSDAI, and counting them here
    while sUSDAI also expects them double-counts the same capital (see
    detect_capital_conflicts). So this always computes both branches:

    - conservative_date: withdrawal ETH + minipool distribute only, accrual
      thereafter — the correct default while routing is unconfirmed
      (the "SUSDAI branch"), since it doesn't assume RPL proceeds land here.
    - carry_first_date: the above PLUS RPL unstaking proceeds converted to
      ETH, if landing within 14 days — the "CARRY_FIRST branch", valid only
      once the user has confirmed that routing.

    recheck_date is carry_first_date when confirmed, else conservative_date."""
    from datetime import date, timedelta
    today = today or date.today()
    base_projected = withdrawal_eth + max(0.0, minipool_pending_eth)
    carry_first_projected = base_projected
    if rpl_unstake_date and rpl_unstaking_amount > 0 and eth_usd > 0:
        try:
            ud = date.fromisoformat(rpl_unstake_date)
            if 0 <= (ud - today).days <= 14:
                carry_first_projected += (rpl_unstaking_amount * rpl_usd) / eth_usd
        except ValueError:
            pass

    def _date_for(projected):
        if projected >= carry_min_eth_target:
            return today.isoformat()
        gap = carry_min_eth_target - projected
        days = int(gap / daily_accrual_eth) + 1 if daily_accrual_eth > 0 else 999
        return (today + timedelta(days=days)).isoformat()

    conservative_date = _date_for(base_projected)
    carry_first_date = _date_for(carry_first_projected)
    return {
        "conservative_date": conservative_date,
        "carry_first_date": carry_first_date,
        "recheck_date": carry_first_date if carry_first_confirmed else conservative_date,
        "branch": "carry_first" if carry_first_confirmed else "dual",
    }


# ────────────────────────────────────────────────────────────────────────────
# PERPS / CARRY-TRADE DUAL GATE
#
# The old single 0.1 ETH "capital present" gate has been fully superseded by
# carry_min_eth() (cost-recovery derived — currently ≈0.926 ETH at ~10.95%
# ARB funding / ~$1,700 ETH). But the carry trade ALSO needs cycle_pct above
# the 10th pct — below that, directional DCA edge dominates carry yield (see
# _KELLY_DCA_ANCHORS), so the trade is cycle-suppressed even when the ETH
# size gate is open. These are two independent conditions with unrelated
# recheck horizons (one is a capital-accrual projection, the other is a
# percentile-regime call signal_core cannot forecast precisely) — report
# them separately rather than collapsing to one recheck date.
# ────────────────────────────────────────────────────────────────────────────
CARRY_MIN_VIABLE_ETH = 0.926  # carry_min_eth(10.95, ~1700) at current live
                              # funding/price — fallback for callers without
                              # live inputs; prefer a fresh carry_min_eth()
                              # call when funding/price are available.
PERPS_CYCLE_GATE_PCT = 10.0   # below this, DCA edge dominates carry yield


def cycle_gate_recheck_estimate(cycle_pct: float) -> str:
    """Coarse recheck band for the cycle-percentile perps gate. Percentile
    isn't a time series signal_core can forecast precisely, so this is a
    deliberately wide band, not a point projection."""
    p = float(cycle_pct)
    if p >= PERPS_CYCLE_GATE_PCT:
        return "cleared"
    if p < 5.0:
        return "est. 30-60 days"
    return "est. 7-21 days"


def perps_gate_status(withdrawal_eth: float, cycle_pct: float,
                      eth_gate_recheck_date: str,
                      carry_min_eth_target: float = CARRY_MIN_VIABLE_ETH,
                      cycle_gate_threshold: float = PERPS_CYCLE_GATE_PCT) -> dict:
    """Dual-gate perps/carry-trade status: withdrawal_eth >= carry_min_eth_target
    AND cycle_pct >= cycle_gate_threshold must BOTH hold before deployment.
    Returns both gates' current values and recheck estimates separately."""
    eth_open = withdrawal_eth >= carry_min_eth_target
    cycle_open = cycle_pct >= cycle_gate_threshold
    return {
        "eth_gate_open": eth_open,
        "eth_gate_current": round(float(withdrawal_eth), 4),
        "eth_gate_target": carry_min_eth_target,
        "eth_gate_recheck_date": eth_gate_recheck_date,
        "cycle_gate_open": cycle_open,
        "cycle_gate_current": round(float(cycle_pct), 1),
        "cycle_gate_threshold": cycle_gate_threshold,
        "cycle_gate_recheck_estimate": cycle_gate_recheck_estimate(cycle_pct),
        "suppressed": not (eth_open and cycle_open),
    }


# ────────────────────────────────────────────────────────────────────────────
# UBI GAP TRACKER
#
# months_to_close_base_case previously annualized the empirical 90d median
# return — (1+med90)**(365/90)-1 — as a proxy for long-run price growth.
# That's invalid: cycle percentile rises as price rises, so the 90d forward
# return shrinks as the portfolio grows: compounding a single 90d-horizon
# figure at that power systematically overstates long-run appreciation.
# The base case instead uses a fixed, conservative full-cycle appreciation
# rate for a BTC/ETH/SOL portfolio, independent of the current percentile.
# ────────────────────────────────────────────────────────────────────────────
BASE_CASE_ANNUAL_APPRECIATION = 0.15  # conservative full-cycle BTC/ETH/SOL assumption


def ubi_gap_report(yield_sources: dict, target_monthly: float = UBI_TARGET_MONTHLY,
                   portfolio_usd: float = None, cycle_pct: float = None) -> dict:
    """UBI gap = target monthly income minus current distributable yield.

    yield_sources: {"name": annual_usd, ...} (annual USD per source).
    Returns gap, coverage %, and — when portfolio_usd is given — a base-case
    months-to-close estimate assuming the portfolio grows at a fixed
    BASE_CASE_ANNUAL_APPRECIATION rate (not an annualized 90d figure — see
    module note above) while the blended yield rate on NAV holds constant."""
    annual = {k: float(v or 0) for k, v in (yield_sources or {}).items()}
    total_annual = sum(annual.values())
    monthly = total_annual / 12.0
    gap = max(0.0, target_monthly - monthly)
    out = {"target_monthly": round(target_monthly, 2),
           "current_monthly": round(monthly, 2),
           "gap_monthly": round(gap, 2),
           "coverage_pct": round(monthly / target_monthly * 100, 1) if target_monthly else 0.0,
           "sources_annual": {k: round(v, 2) for k, v in annual.items()},
           "months_to_close_base_case": None,
           "base_case_monthly_yield_now": round(monthly, 2)}
    if portfolio_usd and portfolio_usd > 0 and total_annual > 0:
        yield_rate = total_annual / portfolio_usd  # blended realized yield on NAV
        growth_ann = BASE_CASE_ANNUAL_APPRECIATION
        portfolio_90d = portfolio_usd * (1 + growth_ann) ** (90.0 / 365.0)
        portfolio_12mo = portfolio_usd * (1 + growth_ann)
        out["base_case_monthly_yield_90d"] = round(portfolio_90d * yield_rate / 12.0, 2)
        out["base_case_monthly_yield_12mo"] = round(portfolio_12mo * yield_rate / 12.0, 2)
        out["portfolio_required_at_current_yield_rate"] = round(target_monthly * 12.0 / yield_rate, 2)
        if gap > 0:
            needed_nav = target_monthly * 12.0 / yield_rate
            g_m = (1 + growth_ann) ** (1 / 12.0) - 1
            if needed_nav <= portfolio_usd:
                out["months_to_close_base_case"] = 0
            elif g_m > 0:
                months = math.log(needed_nav / portfolio_usd) / math.log(1 + g_m)
                out["months_to_close_base_case"] = round(months, 1)
        else:
            out["months_to_close_base_case"] = 0
        out["base_case_assumptions"] = {
            "blended_yield_rate_pct": round(yield_rate * 100, 2),
            "price_growth_ann_pct": round(growth_ann * 100, 1),
            "note": "fixed base-case appreciation rate, NOT an annualized "
                    "90d empirical return; yield rate held constant on NAV"}
    return out


# ────────────────────────────────────────────────────────────────────────────
# RPL UNSTAKING PROCEEDS — RESTAKE VS SELL GTO
#
# The 821 RPL unstaking proceeds can go one of two places: restake against
# the LEB8 minipools for an incremental commission boost, or sell on Kraken
# and deploy to sUSDAI for yield on the full proceeds. These are mutually
# exclusive uses of the same capital — compare net annual value (after gas)
# and recommend whichever is larger.
# ────────────────────────────────────────────────────────────────────────────
def rpl_unstaking_gto_action(state: dict) -> dict:
    """Compare restaking 821 RPL proceeds against LEB8 minipools (commission
    boost) vs selling to sUSDAI (yield on full proceeds). Returns the
    recommended action and the math behind it."""
    rpl_amount = float(state.get('rpl_unstaking_amount') or
                       (state.get('rpl_data') or {}).get('megapool_rpl_unstaking', 821))
    rpl_usd = float(state.get('rpl_usd') or (state.get('prices') or {}).get('rpl_usd', 1.71))
    eth_usd = float(state.get('eth_usd') or (state.get('prices') or {}).get('eth_usd', 1705))
    proceeds_usd = rpl_amount * rpl_usd

    # Option A: Restake against LEB8s
    leb8_count = 3
    leb8_borrowed_eth = leb8_count * 24  # 72 ETH
    rpl_data = state.get('rpl_data') or {}
    current_commission = float(state.get('leb8_commission_rate_current') or
                               rpl_data.get('leb8_commission_rate_current', 10.5))
    after_commission = float(state.get('leb8_commission_rate_after_restake') or
                             rpl_data.get('leb8_commission_rate_after_restake', 10.6))
    commission_delta_pct = after_commission - current_commission
    eth_staking_apy = 0.035
    restake_annual_usd = (commission_delta_pct / 100) * leb8_borrowed_eth * eth_staking_apy * eth_usd
    gas_cost_usd = float(state.get('eth_gas_cost_usd_estimate', 15.0))
    restake_net_annual_usd = restake_annual_usd - gas_cost_usd
    restake_payback_years = gas_cost_usd / max(0.01, restake_annual_usd)

    # Option B: Sell → sUSDAI
    susdai_apy = float(state.get('yield_apy_susdai', 0.076))
    susdai_annual_usd = proceeds_usd * susdai_apy
    susdai_gas_usd = 3.0
    susdai_net_annual_usd = susdai_annual_usd - susdai_gas_usd

    recommended = 'SELL_TO_SUSDAI' if susdai_net_annual_usd > restake_net_annual_usd else 'RESTAKE_LEB8'

    return {
        'rpl_amount': rpl_amount,
        'proceeds_usd': round(proceeds_usd, 2),
        'option_a_restake': {
            'commission_delta_pp': round(commission_delta_pct, 2),
            'annual_value_usd': round(restake_annual_usd, 2),
            'gas_cost_usd': gas_cost_usd,
            'net_annual_usd': round(restake_net_annual_usd, 2),
            'gas_payback_years': round(restake_payback_years, 1)
        },
        'option_b_susdai': {
            'apy': susdai_apy,
            'annual_value_usd': round(susdai_annual_usd, 2),
            'gas_cost_usd': susdai_gas_usd,
            'net_annual_usd': round(susdai_net_annual_usd, 2)
        },
        'recommended': recommended,
        'recommended_reason': (
            f"sUSDAI yields ${susdai_net_annual_usd:.2f}/yr vs restake ${restake_net_annual_usd:.2f}/yr"
            if recommended == 'SELL_TO_SUSDAI'
            else f"Restake yields ${restake_net_annual_usd:.2f}/yr vs sUSDAI ${susdai_net_annual_usd:.2f}/yr"
        )
    }


# ────────────────────────────────────────────────────────────────────────────
# CAPITAL CONFLICT DETECTION
#
# Several sections of the advisor independently propose uses for the same
# pool of capital (e.g. RPL unstaking proceeds routed to sUSDAI in one place
# and counted toward the carry-trade capital gate in another). This flags
# when that's happened so the report doesn't silently double-count capital.
# ────────────────────────────────────────────────────────────────────────────
def detect_capital_conflicts(state: dict) -> list:
    """Detect cases where the same capital is allocated to multiple uses.
    Returns a list of conflict dicts."""
    conflicts = []

    rpl_data = state.get('rpl_data') or {}
    rpl_amount = float(state.get('rpl_unstaking_amount') or
                       rpl_data.get('megapool_rpl_unstaking', 0) or 0)
    rpl_usd = float(state.get('rpl_usd') or (state.get('prices') or {}).get('rpl_usd', 0) or 0)
    rpl_proceeds = rpl_amount * rpl_usd
    carry_threshold = float(state.get('carry_min_viable_eth', CARRY_MIN_VIABLE_ETH))
    withdrawal_eth = float(state.get('withdrawal_eth') or
                           (state.get('validators') or {}).get('withdrawal_address_eth', 0) or 0)
    minipool_pending = float(state.get('minipool_pending_eth') or
                             (state.get('minipool_rewards') or {}).get('no_share_eth', 0) or 0)
    eth_usd = float(state.get('eth_usd') or (state.get('prices') or {}).get('eth_usd', 1705) or 1705)
    rpl_gto = state.get('rpl_unstaking_gto') or {}

    eth_after_distribute = withdrawal_eth + minipool_pending
    eth_gap_to_carry = max(0, carry_threshold - eth_after_distribute)
    rpl_proceeds_eth = rpl_proceeds / eth_usd if eth_usd else 0

    if eth_gap_to_carry > 0 and rpl_proceeds_eth > 0:
        if rpl_gto.get('recommended') == 'SELL_TO_SUSDAI':
            conflicts.append({
                'type': 'RPL_PROCEEDS_DOUBLE_ALLOCATED',
                'description': (
                    f"RPL proceeds (~{rpl_proceeds_eth:.3f} ETH equiv / ${rpl_proceeds:.0f}) "
                    f"directed to sUSDAI but also needed to close carry gate "
                    f"(gap: {eth_gap_to_carry:.3f} ETH after distribute). "
                    f"Cannot do both. Decision required: "
                    f"sUSDAI (${rpl_proceeds * 0.076:.0f}/yr) vs "
                    f"carry trade activation (est. yield TBD once active)."
                ),
                'resolution': (
                    'SUSDAI_FIRST' if rpl_proceeds * 0.076 > 200
                    else 'CARRY_FIRST'
                ),
                # A resolution computed here is a recommendation, not a standing
                # order — real capital shouldn't move on an auto-resolved
                # conflict without the user explicitly locking it in (see
                # manage_state.py --confirm). Downstream renders must show
                # both options until confirmed, per this flag.
                'requires_confirmation': True,
                'confirmation_key': 'carry_first_confirmed',
                'confirmation_prompt': (
                    f"Confirm CARRY_FIRST routing of ~${rpl_proceeds:.0f} RPL proceeds to carry gate "
                    "instead of sUSDAI. Reply 'confirm carry' to lock in routing. "
                    "This decision persists until manually overridden."
                )
            })

    return conflicts


# ────────────────────────────────────────────────────────────────────────────
# SATELLITE ANALYSIS — LIT (Lighter) + VVV (Venice AI)
#
# Daily GTO monitoring for the two $500-max satellite positions tracked in
# candidate_investments.json. Not core capital — must never influence the
# BTC/ETH/SOL DCA split or capital router above. Reads prices from either a
# flat dict (lit_usd/vvv_usd/diem_usd keys) or a crypto_state.json-shaped
# dict (state['prices'][...]), matching the accessor pattern used elsewhere
# in this file (e.g. rpl_unstaking_gto_action).
# ────────────────────────────────────────────────────────────────────────────
LIT_ENTRY_TRIGGER = 1.50
VVV_ENTRY_TRIGGER = 10.0
SATELLITE_POSITION_USD = 500.0


def satellite_analysis(state: dict) -> dict:
    """Daily GTO analysis for the LIT and VVV satellite positions. Returns
    {"lit": {...}, "vvv": {...}} — price vs. entry trigger, yield mechanics,
    supply/unlock risk flags, and a GTO action string for each."""
    prices = state.get("prices") or {}

    def _get(key, default=0):
        v = state.get(key)
        if v is None:
            v = prices.get(key, default)
        return v if v is not None else default

    # ── LIT ──────────────────────────────────────────────────────────────
    lit_price = float(_get("lit_usd") or 0)
    lit_change_24h = float(_get("lit_24h_change_pct") or 0)
    lit_change_7d = float(_get("lit_7d_change_pct") or 0)

    lit_days_to_unlock = (date(2026, 12, 30) - date.today()).days  # major 750M-token unlock
    lit_unlock_monthly_usd = 13_500_000 * lit_price if lit_price else 0  # post-cliff run rate
    # Q1 2026 buybacks: $14.6M over 3 months
    lit_buyback_monthly_usd = float(state.get("lit_monthly_buyback_usd") or (14_600_000 / 3))

    lit_above_trigger = lit_price > LIT_ENTRY_TRIGGER if lit_price else True
    lit_pct_from_trigger = ((lit_price - LIT_ENTRY_TRIGGER) / LIT_ENTRY_TRIGGER * 100) if lit_price else 0.0

    # LLP yield estimate: perp-DEX LP vaults have historically run ~15-25%
    # APY, but LLP is a direct counterparty to trader PnL (see Oct 2025
    # cascade) — use a conservative 12% placeholder pending a live feed.
    lit_llp_apy_estimate = 0.12
    lit_llp_usdc_per_lit = 10  # 1 staked LIT unlocks 10 USDC of LLP exposure
    lit_llp_usdc_exposure = (SATELLITE_POSITION_USD / lit_price * lit_llp_usdc_per_lit) if lit_price else 0
    lit_llp_annual_per_500 = lit_llp_usdc_exposure * lit_llp_apy_estimate

    lit_net_supply_pressure = lit_unlock_monthly_usd - lit_buyback_monthly_usd

    lit = {
        "name": "Lighter (LIT)",
        "price": lit_price,
        "trigger": LIT_ENTRY_TRIGGER,
        "above_trigger": lit_above_trigger,
        "pct_from_trigger": round(lit_pct_from_trigger, 1),
        "status": "WATCH" if lit_above_trigger else "ENTRY_SIGNAL",
        "change_24h_pct": round(lit_change_24h, 2),
        "change_7d_pct": round(lit_change_7d, 2),
        "staking_apy_target": 0.06,
        "staking_note": "LIT-denominated from ecosystem reserve — NOT revenue yield",
        "llp_usdc_exposure_per_500": round(lit_llp_usdc_exposure, 2),
        "llp_yield_estimate_annual": round(lit_llp_annual_per_500, 2),
        "llp_note": f"$500 position -> LLP access on ~${lit_llp_usdc_exposure:,.0f} USDC at ~{lit_llp_apy_estimate*100:.0f}% est.",
        "days_to_major_unlock": lit_days_to_unlock,
        "unlock_monthly_usd_post_cliff": round(lit_unlock_monthly_usd, 0),
        "buyback_monthly_usd_est": round(lit_buyback_monthly_usd, 0),
        "net_supply_pressure_monthly": round(lit_net_supply_pressure, 0),
        "gto_action": (
            f"WAIT — enter post-December 2026 unlock if volume sticky and price holds >$1. "
            f"Currently {lit_pct_from_trigger:+.1f}% from ${LIT_ENTRY_TRIGGER:.2f} trigger."
            if lit_above_trigger else
            f"ENTRY SIGNAL — price below ${LIT_ENTRY_TRIGGER:.2f} trigger. "
            "Stake immediately for LLP access. $500 max."
        ),
        "risk_flags": [
            f"Major unlock in ~{lit_days_to_unlock} days: 750M LIT (75% supply) hits market",
            (f"Net monthly supply pressure post-unlock: ${lit_net_supply_pressure:,.0f}"
             if lit_price else "Price unavailable — net supply pressure not computable"),
            "Staking yield is reserve-funded LIT dilution, not protocol revenue",
            "Robinhood volume not yet confirmed as sticky (90-day gas subsidy active)",
        ],
    }

    # ── VVV ──────────────────────────────────────────────────────────────
    vvv_price = float(_get("vvv_usd") or 0)
    vvv_above_trigger = vvv_price > VVV_ENTRY_TRIGGER if vvv_price else True
    vvv_pct_from_trigger = ((vvv_price - VVV_ENTRY_TRIGGER) / VVV_ENTRY_TRIGGER * 100) if vvv_price else 0.0

    # DIEM: not on CoinGecko, priced off its Base/Aerodrome pool by the
    # collector (crypto_data_collector.fetch_prices -> state['prices']['diem_usd']).
    diem_price = float(_get("diem_usd") or 0)
    diem_payback_years = (diem_price / 365.0) if diem_price else None
    # vvv_per_diem_ratio: rough implied cost (in VVV) to mint $1/day of DIEM,
    # backed out from DIEM's market price vs VVV's spot price — the protocol
    # doesn't publish this ratio directly, so DIEM's market price is used as
    # the equilibrium proxy.
    vvv_per_diem_ratio = (diem_price / vvv_price) if (diem_price and vvv_price) else None

    vvv_tokens = (SATELLITE_POSITION_USD / vvv_price) if vvv_price else 0
    diem_mintable = (vvv_tokens / vvv_per_diem_ratio) if vvv_per_diem_ratio else 0
    diem_annual_value = diem_mintable * 365
    staking_apy_vvv = float(state.get("vvv_staking_apy") or 0.10)  # current emissions-based estimate
    staking_annual_value = SATELLITE_POSITION_USD * staking_apy_vvv

    vvv = {
        "name": "Venice AI (VVV)",
        "price": vvv_price,
        "trigger": VVV_ENTRY_TRIGGER,
        "above_trigger": vvv_above_trigger,
        "pct_from_trigger": round(vvv_pct_from_trigger, 1),
        "status": "WATCH" if vvv_above_trigger else "ENTRY_SIGNAL",
        "diem_price_usd": diem_price,
        "diem_payback_years": round(diem_payback_years, 1) if diem_payback_years is not None else None,
        "position_500_vvv_tokens": round(vvv_tokens, 2),
        "position_500_diem_mintable": round(diem_mintable, 4),
        "position_500_diem_annual_usd": round(diem_annual_value, 2),
        "position_500_staking_annual_usd": round(staking_annual_value, 2),
        "position_500_total_annual_usd": round(diem_annual_value + staking_annual_value, 2),
        "supply_burned_pct": 42.0,
        "emissions_annual": 6_000_000,
        "gto_action": (
            (
                f"WATCH — {vvv_pct_from_trigger:+.1f}% above ${VVV_ENTRY_TRIGGER:.0f} trigger. "
                + (f"DIEM payback {diem_payback_years:.1f}yr — enters favorable range <2.75yr at <${VVV_ENTRY_TRIGGER:.0f}. "
                   if diem_payback_years is not None else "DIEM price unavailable. ")
                + f"Set limit order at ${VVV_ENTRY_TRIGGER - 0.5:.2f}."
            ) if vvv_above_trigger else (
                f"ENTRY SIGNAL — below ${VVV_ENTRY_TRIGGER:.0f} trigger. "
                f"Buy $500, stake 100% immediately. "
                + (f"Lock sVVV -> mint {diem_mintable:.4f} DIEM -> sell on Aerodrome for "
                   f"~${diem_annual_value:.2f}/yr cash yield + ${staking_annual_value:.2f}/yr staking."
                   if diem_mintable else "DIEM price unavailable for payback calc.")
            )
        ),
        "risk_flags": [
            "Venice company holds 35% genesis supply — concentrated, no governance rights for holders",
            "10M tokens vesting through 2026 — team selling pressure",
            (f"DIEM payback {diem_payback_years:.1f}yr at current price — unattractive above ${VVV_ENTRY_TRIGGER:.0f}"
             if diem_payback_years is not None else "DIEM price unavailable — payback not computable"),
            "Privacy AI moat contestable — major labs investing in privacy products",
        ],
    }

    return {"lit": lit, "vvv": vvv}


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
    assert 850 < alloc["dca"] < 900, alloc  # Kelly at ~7th pct: ~88.6% DCA, not 100%
    alloc2 = allocate_capital(25, 1000, [{"name": "sUSDai", "apy": 7.8}])
    assert 0 < alloc2["yield_usd"] < 1000
    # Synthetic test figures only — not real portfolio data (this file is
    # mirrored to a public repo).
    from datetime import date, timedelta as _td
    _cr = carry_trade_recheck_date(
        withdrawal_eth=0.05, minipool_pending_eth=0.1, daily_accrual_eth=0.01,
        carry_min_eth_target=0.5, rpl_unstaking_amount=100.0, rpl_usd=2.0,
        eth_usd=2000.0, rpl_unstake_date=(date.today() + _td(days=5)).isoformat())
    assert _cr["branch"] == "dual"  # unconfirmed by default -> both dates shown
    assert len(_cr["conservative_date"]) == 10 and len(_cr["carry_first_date"]) == 10
    assert _cr["recheck_date"] == _cr["conservative_date"]  # conservative is the default
    _cr_confirmed = carry_trade_recheck_date(
        withdrawal_eth=0.05, minipool_pending_eth=0.1, daily_accrual_eth=0.01,
        carry_min_eth_target=0.5, rpl_unstaking_amount=100.0, rpl_usd=2.0,
        eth_usd=2000.0, rpl_unstake_date=(date.today() + _td(days=5)).isoformat(),
        carry_first_confirmed=True)
    assert _cr_confirmed["branch"] == "carry_first"
    assert _cr_confirmed["recheck_date"] == _cr_confirmed["carry_first_date"]
    print("signal_core self-test OK",
          {"gto(6.8)": gto_multiplier(6.8), "split": ks,
           "e90(6.8)": expected_90d_return(6.8),
           "alloc(6.8)": alloc, "alloc(25)": alloc2,
           "rot": rotation_trigger(9.1, 6.0),
           "carry_min": carry_min_eth(10.95, 2400)})
