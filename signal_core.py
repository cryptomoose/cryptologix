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
import re
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
# WEEKLY DCA BUDGET — single source of truth
#
# Every headline weekly-DCA figure (report header, CHANGES, ACTIONS, WEEK
# AHEAD, capital router, Kraken fill-progress target) must read this, not
# recompute or hardcode its own total. Previously two figures disagreed:
# advisor_prompt's own $777-baseline calc vs kraken_client's separate
# DAILY_TARGETS-derived $855.47 (a stale pre-GTO Kraken-automation figure) —
# the two were never the same number by construction.
# ────────────────────────────────────────────────────────────────────────────
DCA_BASELINE_WEEKLY = 777.0  # user-set weekly baseline, do not hardcode elsewhere


def weekly_dca_budget(state: dict) -> dict:
    """Weekly DCA budget = baseline * continuous GTO multiplier.

    Accepts a crypto_state.json-shaped dict (reads state['ratios']['gto_multiplier']
    or state['gto_multiplier']) or a ratios dict directly."""
    r = state.get("ratios", state) or {}
    mult = state.get("gto_multiplier")
    if mult is None:
        mult = r.get("gto_multiplier", 1.0)
    mult = float(mult or 1.0)
    baseline = DCA_BASELINE_WEEKLY
    return {
        "baseline": baseline,
        "multiplier": round(mult, 2),
        "total": round(baseline * mult, 2),
    }


DCA_STALE_HOURS = 48.0  # a silent DCA halt is the highest-cost failure mode — alert loudly


def dca_health(state: dict) -> dict:
    """Flags a stalled Kraken DCA leg. hours_since_last_dca_fill should be the
    MOST STALE of the three tracked assets (BTC/ETH/SOL), not the most recent
    fill across any asset — an actively-firing asset can otherwise mask a
    halted one (e.g. SOL firing nightly while BTC/ETH automation is down).

    A user-confirmed manual pause (state['dca_manual_pause'], set via
    manage_state.py --pause-dca) suppresses the alert — a deliberate pause
    awaiting capital is not an automation fault. It still surfaces as
    'paused', not silently, so it doesn't look identical to a healthy week."""
    last_fill_hrs = state.get("hours_since_last_dca_fill")
    last_fill_hrs = float(last_fill_hrs) if last_fill_hrs is not None else 0.0
    pause = state.get("dca_manual_pause") or {}
    paused = bool(pause.get("active"))
    stale = (not paused) and last_fill_hrs > DCA_STALE_HOURS
    alert = None
    if paused:
        alert = f"DCA PAUSED (user-confirmed) — {pause.get('reason') or 'awaiting capital to deploy'}"
    elif stale:
        alert = f"DCA STALE — no Kraken fill in {last_fill_hrs:.0f}h, check automation"
    return {
        "last_fill_hrs": round(last_fill_hrs, 1),
        "stale": stale,
        "paused": paused,
        "pause_reason": pause.get("reason") if paused else None,
        "alert": alert,
    }


def paused_dca_cost(state: dict):
    """Quantify forgone expected value while DCA sits on a user-confirmed
    manual pause (state['dca_manual_pause']['active'], set via
    manage_state.py --pause-dca / --resume-dca). Returns None if not paused.

    This is not an instruction to resume — it prices the decision so the
    pause is deliberate rather than passive."""
    paused = bool((state.get('dca_manual_pause') or {}).get('active'))
    if not paused:
        return None

    weekly_budget = float((state.get('dca_budget') or {}).get('total', 0) or 0)
    hours_paused = float(state.get('hours_since_last_dca_fill', 0) or 0)
    weeks_paused = hours_paused / 168.0
    cycle_pct = float(state.get('cycle_percentile', 50))
    exp_90d = float(state.get('expected_90d_return', 0) or 0)

    undeployed = weekly_budget * weeks_paused
    # Forgone EV = undeployed capital × median 90d expected return
    forgone_ev_90d = undeployed * exp_90d

    return {
        'weeks_paused': round(weeks_paused, 1),
        'weekly_budget': round(weekly_budget, 2),
        'undeployed_usd': round(undeployed, 0),
        'cycle_pct': cycle_pct,
        'expected_90d_return_pct': round(exp_90d * 100, 1),
        'forgone_ev_90d_usd': round(forgone_ev_90d, 0),
        'note': (
            f"${undeployed:,.0f} undeployed over {weeks_paused:.1f}wk at "
            f"{cycle_pct:.1f}th pct. Model E[90d] +{exp_90d*100:.1f}% implies "
            f"~${forgone_ev_90d:,.0f} forgone expected value. "
            f"Pause is user-confirmed — this prices the decision, not a directive."
        ),
    }


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
# One hard gate sits in front of the score: TVL >= $75M AND audit >= 0.8,
# applied regardless of allocation size. A tiered exception used to let
# allocations <= $500 clear on a $25M TVL floor with no audit requirement —
# that's what let sub-$75M/sub-audit pools (e.g. stake-dao SDCRV, ~$26M TVL)
# win small router slots three times over. There is no dollar amount below
# which routing to a gate-failed protocol becomes acceptable, so the gate
# no longer varies with allocation_usd.
# ────────────────────────────────────────────────────────────────────────────
PRIMARY_MIN_TVL_M = 75.0     # TVL floor (millions) — applies to every allocation size
PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR = 0.8


def score_yield_opportunity(apy_pct: float, tvl_millions: float,
                            audit_factor: float) -> float:
    """Risk-adjusted score: APY * ln(TVL_millions)**1.5 * audit_factor.
    Callers should gate on PRIMARY_MIN_TVL_M and PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR
    before treating a high score as a primary-allocation recommendation — the
    score alone doesn't encode those hard gates."""
    if tvl_millions is None or tvl_millions <= 1:
        return 0.0
    return round(float(apy_pct) * (math.log(float(tvl_millions)) ** 1.5) * float(audit_factor), 2)


def eligible_for_primary(allocation_usd: float, tvl_millions: float,
                         audit_factor: float) -> bool:
    """Hard gate: TVL >= $75M AND audit >= 0.8, regardless of allocation size.
    allocation_usd is accepted for call-site compatibility but no longer
    changes the floor — see module note above."""
    if (tvl_millions or 0) < PRIMARY_MIN_TVL_M:
        return False
    if (audit_factor or 0) < PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR:
        return False
    return True


# ────────────────────────────────────────────────────────────────────────────
# PROTOCOL CONCENTRATION GATE
#
# The audit/TVL gate above scores each protocol independently — it can't see
# that "sky-lending USDS" and MakerDAO Vaults 30698/31944 share the same
# governance/smart-contract blast radius (Sky = MakerDAO rebranded; a
# governance action, oracle failure, or emergency shutdown hits both the
# yield sleeve and the collateral stack at once). This gate runs BEFORE the
# audit/TVL gate in allocate_capital and blocks any allocation that would
# push a correlated protocol family above 5% of NAV, counting BOTH existing
# collateral and debt (a governance failure impairs both sides).
# ────────────────────────────────────────────────────────────────────────────
CONCENTRATION_LIMIT_PCT = 0.05   # max 5% of NAV per protocol family

# Map protocol identifiers to their governance/risk family. Same family =
# same smart-contract + governance blast radius.
PROTOCOL_FAMILY = {
    'sky-lending': 'maker_sky',
    'sky': 'maker_sky',
    'makerdao': 'maker_sky',
    'spark': 'maker_sky',        # Spark is a Sky subDAO
    'usds': 'maker_sky',
    'dai': 'maker_sky',
    'susds': 'maker_sky',
    'aave': 'aave',
    'aave-v3': 'aave',
    'rocketpool': 'rocketpool',
    'reth': 'rocketpool',
    'rpl': 'rocketpool',
    'lido': 'lido',
    'wsteth': 'lido',            # wstETH is Lido — collateral in Maker vaults
}


def _family(name: str) -> str:
    """Token match, not substring — substring containment false-positives on
    names like "sUSDai" (contains "dai") or "SkyHarbor" (contains "sky") that
    share no actual governance relationship with Maker/Sky."""
    tokens = set(re.split(r'[^a-z0-9]+', str(name).lower().strip()))
    tokens.discard('')
    for k, fam in PROTOCOL_FAMILY.items():
        k_tokens = set(re.split(r'[^a-z0-9]+', k))
        if k_tokens & tokens:
            return fam
    return str(name).lower().strip()  # unknown protocols are their own family


def existing_protocol_exposure(state: dict) -> dict:
    """Current USD exposure per protocol family from live positions. Counts
    BOTH collateral and debt — a governance failure impairs both."""
    nav = float(state.get('portfolio_usd', 1) or 1)
    exposure = {}

    def add(family, usd):
        exposure[family] = exposure.get(family, 0) + float(usd or 0)

    # Maker/Sky vaults: collateral is the exposure at risk
    add('maker_sky', state.get('vault_30698_collateral_usd', 0))
    add('maker_sky', state.get('vault_31944_collateral_usd', 0))
    # wstETH collateral is ALSO Lido exposure (dual-family)
    add('lido', state.get('vault_30698_collateral_usd', 0))
    add('lido', state.get('vault_31944_collateral_usd', 0))
    # Aave
    add('aave', state.get('aave_collateral_usd', 0))
    # Rocketpool: validators + rETH
    add('rocketpool', state.get('eth_staked_usd', 0))
    add('rocketpool', state.get('reth_usd_value', 0))

    return {
        fam: {'usd': round(usd, 0), 'pct_of_nav': round(usd / nav * 100, 2)}
        for fam, usd in exposure.items()
    }


def concentration_check(protocol_name: str, allocation_usd: float,
                        state: dict) -> tuple:
    """Returns (allowed, reason). Blocks any allocation that would push a
    protocol family above CONCENTRATION_LIMIT_PCT of NAV. With no real NAV
    in state (portfolio_usd missing/<=0 — e.g. a caller that didn't pass
    live state), the gate is a no-op rather than maximally restrictive:
    without a real NAV, any allocation_usd would divide by the ~$1
    placeholder and "exceed" the limit trivially."""
    nav = float(state.get('portfolio_usd', 0) or 0)
    if nav <= 0:
        return True, "concentration OK (no portfolio_usd in state)"
    fam = _family(protocol_name)
    exposure = existing_protocol_exposure(state)
    current_usd = exposure.get(fam, {}).get('usd', 0)
    projected_pct = (current_usd + allocation_usd) / nav

    if projected_pct > CONCENTRATION_LIMIT_PCT:
        return False, (
            f"CONCENTRATION BLOCK — {fam} family already {current_usd/nav*100:.1f}% "
            f"of NAV (${current_usd:,.0f}); adding ${allocation_usd:,.0f} → "
            f"{projected_pct*100:.1f}% exceeds {CONCENTRATION_LIMIT_PCT*100:.0f}% limit. "
            f"Correlated blast radius with existing collateral/debt."
        )
    return True, "concentration OK"


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
                     yield_opportunities: list = None, state: dict = None) -> dict:
    """Route weekly deployable capital between spot DCA and yield positions
    via the Kelly-derived _kelly_dca_fraction (see module note above).

    yield_opportunities: [{"name": str, "apy": float, ...}] sorted or not;
    yield capital is split across the top 3 by APY, 50/30/20; the best APY
    among them (or 12.0 default) is passed to _kelly_dca_fraction.

    state: crypto_state.json-shaped dict, used by the protocol concentration
    gate (concentration_check) to see existing collateral/debt exposure.
    Omitted or empty means the concentration gate is a no-op (existing
    exposure reads as 0 for every family) — callers with live portfolio
    state should always pass it."""
    state = state or {}
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
            _name = o.get("name") or o.get("pool", "?")
            if audit_factor is None or tvl_m is None:
                filtered_protocols.append({"opportunity": _name,
                                           "apy": o.get("apy"), "audit_factor": audit_factor,
                                           "tvl_m": tvl_m, "reason": "missing audit_factor/tvl_m"})
                continue
            # Concentration gate runs BEFORE the audit/TVL gate — a protocol
            # can clear audit/TVL and still correlate with existing
            # collateral/debt (e.g. sky-lending USDS vs Maker vault
            # collateral). Tested against the full yield_usd since that's
            # the maximum this protocol could receive if it's the only one
            # that clears the remaining gates.
            _conc_ok, _conc_reason = concentration_check(_name, yield_usd, state)
            if not _conc_ok:
                filtered_protocols.append({"opportunity": _name,
                                           "apy": o.get("apy"), "audit_factor": audit_factor,
                                           "tvl_m": tvl_m, "reason": _conc_reason})
                continue
            if eligible_for_primary(yield_usd, float(tvl_m), float(audit_factor)):
                eligible.append(o)
            else:
                tvl_fails = float(tvl_m) < PRIMARY_MIN_TVL_M
                audit_fails = float(audit_factor) < PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR
                if tvl_fails and audit_fails:
                    reason = (f"below TVL floor (${tvl_m}M<${PRIMARY_MIN_TVL_M:.0f}M) "
                              f"AND below audit floor ({audit_factor}<{PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR})")
                elif tvl_fails:
                    reason = f"below TVL floor (${tvl_m}M<${PRIMARY_MIN_TVL_M:.0f}M); audit OK"
                else:
                    reason = f"below audit floor ({audit_factor}<{PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR}); TVL OK"
                filtered_protocols.append({"opportunity": o.get("name") or o.get("pool", "?"),
                                           "apy": o.get("apy"), "audit_factor": audit_factor,
                                           "tvl_m": tvl_m, "reason": reason})
        if not eligible:
            # No gate-cleared protocol this week — never route to a sub-gate
            # protocol. Redirect the yield-earmarked capital to DCA instead
            # of leaving it stranded in yield_usd with no slot to land in.
            dca_usd = cap
            yield_usd = 0.0
        else:
            top = sorted(eligible, key=lambda o: -(o.get("apy") or 0))[:3]
            shares = [0.5, 0.3, 0.2][:len(top)]
            norm = sum(shares) if top else 1
            for o, s in zip(top, shares):
                slots.append({"opportunity": o.get("name") or o.get("pool", "?"),
                              "apy": o.get("apy"),
                              "amount": round(yield_usd * s / norm, 2)})
    no_gate_cleared_note = (
        "Yield $0 — no protocol clears concentration + audit/TVL gates this week"
        if yield_usd == 0 and filtered_protocols and not slots else None
    )
    return {"dca": dca_usd, "yield_usd": yield_usd, "yield_slots": slots,
            "filtered_protocols": filtered_protocols,
            "no_gate_cleared_note": no_gate_cleared_note,
            "dca_frac": round(dca_usd / cap, 4) if cap else round(dca_frac, 4),
            "profit_taking_review": p >= 50.0}


# ────────────────────────────────────────────────────────────────────────────
# CARRY-TRADE MINIMUM VIABLE SIZE (replaces the arbitrary 0.1 ETH gate)
# Deferred — re-enable via carry_trade_enabled flag at cycle pct > 35th
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
# Deferred — re-enable via carry_trade_enabled flag at cycle pct > 35th
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
# Deferred — re-enable via carry_trade_enabled flag at cycle pct > 35th
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
# WEALTH COMPOUNDING OBJECTIVE (top-level objective)
#
# Replaces the prior UBI-income-target framing. There is no monthly USD
# income target anywhere in this engine — the objective is pure NAV
# compounding: grow via Kelly-optimal DCA, preserve via crypto<->metals
# rotation at cycle extremes, and eliminate crypto debt via the GTO
# debt-unwind optimizer below.
# ────────────────────────────────────────────────────────────────────────────
def wealth_compounding_objective(state: dict) -> dict:
    """
    Top-level objective: grow NAV via Kelly-optimal DCA, preserve via
    crypto<->metals rotation at extremes, eliminate crypto debt.
    Never denominated in a USD income target — pure capital compounding.
    """
    portfolio = float(state.get('portfolio_usd', 0))
    cost_basis_total = float(state.get('total_contributions_usd', 0) or 0)
    crypto_debt = (float(state.get('maker_debt_total_usd', 0) or 0) +
                   float(state.get('aave_debt_usd', 0) or 0))
    debt_at_peak = float(state.get('crypto_debt_peak_usd', crypto_debt) or crypto_debt)

    # Compounding efficiency: NAV per dollar contributed
    efficiency = (portfolio / cost_basis_total) if cost_basis_total > 0 else None

    # Debt unwind progress. Until closures actually start, debt sits at (or
    # near) its peak — a literal "0.0% unwound" reads as if no progress is
    # possible, when really it just means the closure signal hasn't fired
    # yet. at_or_near_peak distinguishes "haven't started" from "made no
    # progress despite trying."
    debt_unwind_pct = ((debt_at_peak - crypto_debt) / debt_at_peak * 100) if debt_at_peak > 0 else 0
    debt_at_or_near_peak = debt_unwind_pct < 1.0

    return {
        'nav_usd': round(portfolio, 0),
        'total_contributions_usd': round(cost_basis_total, 0),
        'compounding_efficiency': round(efficiency, 3) if efficiency else None,
        'compounding_note': (
            f"${portfolio:,.0f} NAV from ${cost_basis_total:,.0f} contributed "
            f"({efficiency:.2f}x)" if efficiency else "cost basis unavailable"
        ),
        'crypto_debt_outstanding_usd': round(crypto_debt, 0),
        'crypto_debt_peak_usd': round(debt_at_peak, 0),
        'crypto_debt_unwind_pct': round(debt_unwind_pct, 1),
        'debt_at_or_near_peak': debt_at_or_near_peak,
        'objective': 'Compound NAV via Kelly DCA | preserve via metals rotation at extremes | zero crypto debt',
    }


# ────────────────────────────────────────────────────────────────────────────
# CYCLE-TOP GOAL FRAMEWORK
#
# Two near-term goals sit on top of the permanent HODL/compound mandate,
# both scoped to fire only as the cycle top approaches:
#   GOAL 1: eliminate all crypto debt (3 DeFi positions)
#   GOAL 2: rotate crypto -> metals to lock gains
# Sequencing: debt closure FIRST (risk elimination + smallest collateral
# slice at collateral highs), THEN metals rotation (lock remaining gains
# unlevered — see metals_rotation_signal's BLOCKED_BY_DEBT gate below).
# Neither fires mid-cycle: below CYCLE_TOP_WARNING_PCT both goals are
# dormant and the correct action is HODL + Kelly DCA.
# ────────────────────────────────────────────────────────────────────────────
CYCLE_TOP_WARNING_PCT = 75.0    # begin staging cycle-top actions
CYCLE_TOP_ACTION_PCT = 85.0     # cycle-top actions become live
CYCLE_TOP_URGENT_PCT = 92.0     # execute — top is near


# ────────────────────────────────────────────────────────────────────────────
# CYCLE VELOCITY — OLS SLOPE, ADAPTIVE WINDOW
#
# Replaces a 2-point endpoint secant (recent[-1] - recent[0] over the last
# 28 readings) that used only the two ends of the window and ignored every
# point between them — a single new day's reading could swing the "weekly
# velocity" estimate 4x overnight (283wk -> 72wk ETA to staging on 2026-07-10)
# even though the 28-day window itself was long enough to be stable, because
# the two endpoints aren't a stable statistic on their own. An OLS slope
# over the same window uses every point, so one new day only nudges the
# fit instead of redefining it.
#
# Window is adaptive because only 30 days of cycle_percentile_history exist
# as of 2026-07-10: a 21d/28d OLS window can still be dominated by a single
# mid-window trough (see 2026-06-25..07-01 dip) while history is this thin.
# Prefer the shorter, more-recent 14d window until enough history (>45
# points) accumulates to make longer windows trustworthy, then prefer 21d.
# ────────────────────────────────────────────────────────────────────────────
def _velocity_ols(pct_history: list, window_days: int):
    """OLS slope (pp/week) over the trailing window_days of
    cycle_percentile_history. pct_history: chronological [(date_str, pct)].
    Returns None if fewer than 5 points fall within the window."""
    if not pct_history:
        return None
    cutoff = date.today().toordinal() - window_days
    pts = [(date.fromisoformat(d).toordinal(), p) for d, p in pct_history
           if date.fromisoformat(d).toordinal() >= cutoff]
    n = len(pts)
    if n < 5:
        return None
    x0 = pts[0][0]
    xs = [p[0] - x0 for p in pts]  # numerical stability
    ys = [p[1] for p in pts]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return (num / den) * 7  # pp/day -> pp/week


def cycle_top_velocity(state: dict) -> dict:
    """Adaptive-window OLS velocity estimate for cycle_percentile_history
    (see module note above). Never a 2-point endpoint secant."""
    pct_history = state.get('cycle_percentile_history', [])
    windows_by_pref = (14, 21, 28, 10) if len(pct_history) < 45 else (21, 14, 28, 10)

    computed = {w: _velocity_ols(pct_history, w) for w in (10, 14, 21, 28)}
    available = [(w, v) for w, v in computed.items() if v is not None]
    if not available:
        return {
            'velocity_pp_per_week': None,
            'window_days': None,
            'method': 'insufficient_history',
            'all_windows': {},
            'note': 'Fewer than 5 percentile readings in any window — need more days of history.',
        }

    chosen_window = next(w for w in windows_by_pref if computed.get(w) is not None)
    chosen_velocity = computed[chosen_window]

    return {
        'velocity_pp_per_week': round(chosen_velocity, 3),
        'window_days': chosen_window,
        'method': f'ols_slope_{chosen_window}d',
        'all_windows': {f'{w}d': round(v, 3) for w, v in sorted(available)},
        'note': (
            f'OLS slope over trailing {chosen_window}d ({len(pct_history)} total '
            f'readings available). Will prefer 21d once >45 days of history exist.'
        ),
    }


def cycle_top_readiness(state: dict) -> dict:
    """
    Tracks readiness for the two near-term cycle-top goals:
      GOAL 1: eliminate all crypto debt (3 DeFi positions)
      GOAL 2: rotate crypto -> metals to lock gains
    Both fire near the cycle top. Sequencing: debt closure FIRST (risk
    elimination + smallest collateral slice at collateral highs), THEN
    metals rotation (lock remaining gains unlevered).
    Neither fires mid-cycle — only as the top approaches.
    """
    cycle_pct = float(state.get('cycle_percentile', 50))
    btc_g = float(state.get('btc_gold_percentile', 50))
    eth_g = float(state.get('eth_gold_percentile', 50))
    # Prefer the raw maker+aave sum (already fresh this run — see
    # wealth_compounding_objective's identical formula) over any cached
    # debt_unwind total, since cycle_top_readiness is computed before
    # debt_unwind_optimizer in enrich_state (debt_unwind's third lens
    # needs this function's phase, so it can't come first — see collector
    # wiring notes).
    debt = float(state.get('maker_debt_total_usd', 0) or 0) + float(state.get('aave_debt_usd', 0) or 0)
    if not debt:
        debt = float((state.get('debt_unwind') or {}).get('total_crypto_debt_usd', 0) or 0)

    # Phase of cycle-top approach
    if cycle_pct >= CYCLE_TOP_URGENT_PCT:
        phase = 'TOP_URGENT'
    elif cycle_pct >= CYCLE_TOP_ACTION_PCT:
        phase = 'TOP_ACTION'
    elif cycle_pct >= CYCLE_TOP_WARNING_PCT:
        phase = 'TOP_STAGING'
    else:
        phase = 'ACCUMULATION'  # far from top — HODL/DCA, no top-actions

    # Goal readiness
    debt_ready = phase in ('TOP_ACTION', 'TOP_URGENT')
    # metals rotation only after debt cleared OR at urgent phase
    rotation_ready = (
        phase in ('TOP_ACTION', 'TOP_URGENT')
        and btc_g > 90 and eth_g > 90
    )

    # Sequencing directive
    if phase == 'ACCUMULATION':
        directive = 'HODL + DCA. No cycle-top actions. Debt is accretive leverage; metals rotation not warranted.'
    elif phase == 'TOP_STAGING':
        directive = (
            f'STAGE cycle-top plan. Cycle {cycle_pct:.0f}th approaching top. '
            f'Prepare: (1) debt closure sequence, (2) metals rotation orders. '
            f'Do NOT execute yet — await {CYCLE_TOP_ACTION_PCT:.0f}th pct.'
        )
    elif phase == 'TOP_ACTION':
        if debt > 0:
            directive = (
                f'EXECUTE GOAL 1 FIRST: close DeFi debt (${debt:,.0f}) while '
                f'collateral rich. THEN Goal 2 metals rotation once unlevered.'
            )
        elif rotation_ready:
            directive = 'Debt cleared. EXECUTE GOAL 2: rotate crypto -> metals to lock gains.'
        else:
            directive = 'Debt cleared. Metals rotation staged — await crypto-rich signal (BTC/G & ETH/G > 90th).'
    else:  # TOP_URGENT
        directive = (
            f'TOP URGENT ({cycle_pct:.0f}th). Complete both goals now: '
            f'{"close debt then " if debt > 0 else ""}rotate crypto -> metals. '
            f'Do not wait for a higher print.'
        )

    # Cycle velocity: pp per week, from percentile history (OLS, adaptive
    # window — see cycle_top_velocity above)
    velocity = cycle_top_velocity(state)
    velocity_pp_per_week = velocity['velocity_pp_per_week']
    velocity_window_days = velocity['window_days']

    pp_to_staging = max(0, CYCLE_TOP_WARNING_PCT - cycle_pct)
    if velocity_pp_per_week is None:
        staging_eta = "velocity unavailable (need percentile history)"
    elif velocity_pp_per_week > 0.1:
        weeks_to_staging = pp_to_staging / velocity_pp_per_week
        staging_eta = (f"~{weeks_to_staging:.0f} weeks at current velocity "
                        f"({velocity_pp_per_week:+.2f}pp/wk, {velocity_window_days}d OLS)")
    elif velocity_pp_per_week < -0.1:
        staging_eta = (f"receding ({velocity_pp_per_week:+.2f}pp/wk, {velocity_window_days}d OLS) "
                        f"— top not approaching")
    else:
        staging_eta = f"flat (±0.0pp/wk, {velocity_window_days}d OLS) — no directional signal"

    return {
        'cycle_pct': cycle_pct,
        'phase': phase,
        'staging_eta': staging_eta,
        'velocity_pp_per_week': velocity_pp_per_week,
        'goal1_debt_closure': {
            'target': 'zero crypto debt',
            'outstanding_usd': round(debt, 0),
            'ready_to_execute': debt_ready and debt > 0,
        },
        'goal2_metals_rotation': {
            'target': 'lock gains: crypto -> metals',
            'btc_gold_pct': btc_g, 'eth_gold_pct': eth_g,
            'ready_to_execute': rotation_ready,
        },
        'sequencing': 'debt closure BEFORE metals rotation',
        'directive': directive,
    }


# ────────────────────────────────────────────────────────────────────────────
# CAPITAL FLOW CONSTITUTION (hard constraint)
#
# Permitted flows ONLY:
#   USD    -> crypto   (DCA entry)
#   crypto -> metals   (rotation at crypto-rich extreme)
#   metals -> USD      (rotation at metals-rich extreme, re-enters as crypto)
#   crypto -> USD      (ONLY for DeFi debt closure — see debt_unwind_optimizer)
# FORBIDDEN:
#   crypto -> USD for profit-taking / de-risking / any non-debt purpose
# ────────────────────────────────────────────────────────────────────────────
CAPITAL_FLOW_RULE = {
    'usd_to_crypto': True,
    'crypto_to_metals': True,
    'metals_to_usd': True,
    'crypto_to_usd_profit': False,   # NEVER
    'crypto_to_usd_debt_closure': True,  # scoped exception only
}


def validate_action_flow(action_type: str) -> tuple:
    """Guard: reject any recommendation that would sell crypto to USD
    outside debt closure. Called before any sell/rotate action is emitted."""
    forbidden = {
        'sell_crypto_usd', 'take_profit_usd', 'derisk_to_stable',
        'crypto_to_cash', 'trim_to_usd'
    }
    if action_type in forbidden:
        return False, ("BLOCKED by capital flow rule: crypto never converts "
                       "to USD except DeFi debt closure. Route via metals instead.")
    return True, "permitted"


# ────────────────────────────────────────────────────────────────────────────
# BIDIRECTIONAL METALS ROTATION
#
# crypto CHEAP vs metals (both ratios < 5th pct)  -> rotate metals INTO crypto
# crypto RICH  vs metals (both ratios > 90th pct) -> rotate crypto INTO metals
# Both legs require BOTH BTC/Gold AND ETH/Gold to confirm.
# ────────────────────────────────────────────────────────────────────────────
ROTATION_CRYPTO_CHEAP_PCT = 5.0
ROTATION_CRYPTO_RICH_PCT = 90.0


def metals_rotation_signal(state: dict) -> dict:
    """Bidirectional rotation at market extremes (see module note above).

    The crypto->metals leg (GOAL 2 of cycle_top_readiness) is additionally
    gated by cycle phase and debt status: it's the second of two sequenced
    near-term goals (debt closure first — see debt_unwind_optimizer's
    cycle-top lens), so it should never fire ahead of debt closure, and
    shouldn't fire as a routine mid-cycle action even if the BTC/ETH-vs-gold
    ratio alone crosses the rich threshold. The metals->crypto leg (buying
    the dip in crypto) has no such gate — it's a bottom signal, not a
    near-term goal, and firing on the raw ratio is correct at any cycle
    phase."""
    btc_g = float(state.get('btc_gold_percentile', 50))
    eth_g = float(state.get('eth_gold_percentile', 50))

    metals_to_crypto = btc_g < ROTATION_CRYPTO_CHEAP_PCT and eth_g < ROTATION_CRYPTO_CHEAP_PCT
    crypto_to_metals = btc_g > ROTATION_CRYPTO_RICH_PCT and eth_g > ROTATION_CRYPTO_RICH_PCT

    cycle_phase = (state.get('cycle_top_readiness') or {}).get('phase', 'ACCUMULATION')
    debt = float(state.get('maker_debt_total_usd', 0) or 0) + float(state.get('aave_debt_usd', 0) or 0)
    if not debt:
        debt = float((state.get('debt_unwind') or {}).get('total_crypto_debt_usd', 0) or 0)

    if metals_to_crypto:
        direction, action = 'METALS_TO_CRYPTO', 'Sell physical metals -> buy BTC/ETH spot (Kelly split)'
    elif crypto_to_metals:
        if cycle_phase not in ('TOP_ACTION', 'TOP_URGENT'):
            direction, action = 'NONE', (
                f'Crypto/gold ratio rich but cycle phase {cycle_phase} — GOAL 2 rotation dormant '
                f'below the {CYCLE_TOP_ACTION_PCT:.0f}th pct staging threshold, not a routine mid-cycle action.'
            )
        elif debt > 0:
            direction, action = 'CRYPTO_TO_METALS_BLOCKED_BY_DEBT', (
                'Close DeFi debt first, then rotate. Sequencing: debt before metals.'
            )
        else:
            direction, action = 'CRYPTO_TO_METALS', 'Rotate BTC/ETH -> physical metals (lock gains as metals, never USD)'
    else:
        direction, action = 'NONE', 'No rotation — ratios between extremes'

    dist_cheap = max(btc_g - ROTATION_CRYPTO_CHEAP_PCT, eth_g - ROTATION_CRYPTO_CHEAP_PCT)
    dist_rich = max(ROTATION_CRYPTO_RICH_PCT - btc_g, ROTATION_CRYPTO_RICH_PCT - eth_g)

    return {
        'direction': direction,
        'action': action,
        'btc_gold_pct': btc_g,
        'eth_gold_pct': eth_g,
        'dist_to_cheap_trigger_pp': round(dist_cheap, 1),
        'dist_to_rich_trigger_pp': round(dist_rich, 1),
        'cheap_trigger': ROTATION_CRYPTO_CHEAP_PCT,
        'rich_trigger': ROTATION_CRYPTO_RICH_PCT,
    }


METALS_ROTATION_TARGET_PCT = 0.30  # rotate 30% of liquid crypto to metals at top


def metals_rotation_plan(state: dict) -> dict:
    """
    GTO-sized metals rotation at cycle top. Rotates a defined fraction of
    LIQUID crypto (spot BTC/ETH/SOL, NOT staked validators — those keep
    compounding) into physical gold/silver to lock gains.
    Validators are NOT rotated — they are the permanent HODL core.
    """
    btc_spot_usd = float(state.get('btc_spot_usd', 0) or state.get('btc_usd_value', 0) or 0)
    # Liquid crypto = spot holdings, excludes staked ETH validators + rETH core
    liquid_crypto_usd = (
        float(state.get('btc_usd_value', 0) or 0) +
        float(state.get('sol_usd_value', 0) or 0)
        # ETH validators excluded — permanent stake
    )
    rotation_usd = liquid_crypto_usd * METALS_ROTATION_TARGET_PCT
    # Kelly split within metals: gold/silver by relative percentile cheapness
    gold_pct = float(state.get('gold_percentile', 50))
    silver_pct = float(state.get('silver_percentile', 50))
    # Buy the cheaper metal more heavily
    if gold_pct + silver_pct > 0:
        gold_weight = silver_pct / (gold_pct + silver_pct)  # inverse — cheaper gets more
        silver_weight = gold_pct / (gold_pct + silver_pct)
    else:
        gold_weight, silver_weight = 0.6, 0.4

    return {
        'target_pct_of_liquid_crypto': METALS_ROTATION_TARGET_PCT,
        'liquid_crypto_usd': round(liquid_crypto_usd, 0),
        'rotation_usd': round(rotation_usd, 0),
        'validators_excluded': 'ETH validators + rETH remain permanent HODL core — never rotated',
        'gold_allocation_usd': round(rotation_usd * gold_weight, 0),
        'silver_allocation_usd': round(rotation_usd * silver_weight, 0),
        'note': 'Executes only at cycle top (phase TOP_ACTION+) AND after debt cleared',
    }


# ────────────────────────────────────────────────────────────────────────────
# DEFI DEBT-UNWIND OPTIMIZER
#
# Goal: eliminate all crypto debt (Maker vaults 30698, 31944 + Aave), closing
# each independently at its GTO-optimal point. GTO = close when the interest
# + liquidation risk saved exceeds expected appreciation forfeited on the
# collateral surrendered to repay.
# ────────────────────────────────────────────────────────────────────────────
def debt_unwind_optimizer(state: dict) -> dict:
    """
    Per-position unwind analysis under a buy/borrow/die thesis: debt is
    free leverage as long as it's economically accretive, and the separate
    goal of eliminating it entirely (the preservation mandate) is a risk
    decision, not an EV decision. Two independent lenses:

    LENS 1 — Economic (is the leverage still free money?)
      economic_edge = (collateral_staking_yield + annualized_appreciation)
                       - borrow_apr
      edge > 0: leverage is accretive, HOLD is EV-correct.
      edge < 0: leverage is costing you net of yield/appreciation, close
      for EV regardless of collateral ratio.

    LENS 2 — Risk (cost to close, independent of EV)
      crypto_units_to_close = debt_usd / current_price — the collateral
      slice surrendered to clear the debt. This shrinks as collateral
      appreciates, so the cheapest (in crypto terms) risk-reduction exit
      is at a local high in the collateral ratio — tracked run over run
      via each position's previous cost-to-close.

    LENS 3 — Cycle-top goal (signal_core.cycle_top_readiness)
      Near the cycle top, GOAL 1 is to close all debt even if leverage is
      still marginally accretive on Lens 1 — locking in the cycle at
      collateral highs is the mandate, not maximizing EV on the leverage.
      Fires only once cycle_top_readiness's phase reaches TOP_ACTION or
      TOP_URGENT, and only after the force-close and economic checks have
      already had their say (a distressed or genuinely uneconomic position
      is still reported as such, not relabeled as a deliberate cycle-top
      close).

    Priority: force-close > economic close > cycle-top close > HOLD.
    """
    exp_90d = float(state.get('expected_90d_return', 0.10))  # from empirical_90d_return
    annualized_appreciation = exp_90d * 4  # 90d -> annual proxy
    cycle_phase = (state.get('cycle_top_readiness') or {}).get('phase', 'ACCUMULATION')
    positions = []

    def analyze(name, state_key, collateral_usd, debt_usd, collateral_ratio,
                borrow_apr, liq_price, current_price, collateral_staking_yield=0.037):
        if debt_usd <= 0:
            return {'name': name, 'status': 'NO_DEBT', 'action': 'none'}

        # LENS 1 — economic edge: is the leverage still free money?
        economic_edge = (collateral_staking_yield + annualized_appreciation) - borrow_apr
        leverage_accretive = economic_edge > 0

        # LENS 2 — risk / cost-to-close, independent of EV
        crypto_units_to_close = debt_usd / current_price if current_price else 0
        buffer_pct = (current_price - liq_price) / current_price if current_price else 1
        prev_units_key = f'{state_key}_prev_close_units'
        prev_units = state.get(prev_units_key)
        at_local_min = prev_units is not None and crypto_units_to_close < prev_units
        state[prev_units_key] = crypto_units_to_close

        hist = state.get('debt_close_cost_history', {}).get(name, [])
        cost_to_close_trend = None
        if len(hist) >= 7:
            recent_avg = sum(h[1] for h in hist[-7:]) / 7
            older_avg = sum(h[1] for h in hist[-14:-7]) / max(1, len(hist[-14:-7]))
            if older_avg > 0:
                trend_pct = (recent_avg - older_avg) / older_avg * 100
                cost_to_close_trend = f"cost-to-close {'falling' if trend_pct<0 else 'rising'} {abs(trend_pct):.1f}% (7d)"

        annual_carry = debt_usd * borrow_apr
        force_close = buffer_pct < 0.15

        if force_close:
            status, action = 'FORCE_CLOSE', f'FORCE CLOSE — buffer {buffer_pct*100:.0f}% dangerously low'
        elif not leverage_accretive:
            status, action = 'CLOSE_ECONOMIC', (
                f'CLOSE — leverage no longer accretive: economic edge {economic_edge*100:+.1f}% '
                f'(collateral yield {collateral_staking_yield*100:.1f}% + appreciation '
                f'{annualized_appreciation*100:.1f}% < borrow {borrow_apr*100:.1f}%)'
            )
        elif cycle_phase in ('TOP_ACTION', 'TOP_URGENT'):
            status, action = 'CLOSE_CYCLE_TOP', (
                f'CLOSE — cycle-top goal: collateral rich ({collateral_ratio:.0f}%), '
                f'cost-to-close at cycle-low {crypto_units_to_close:.3f} ETH-equiv. '
                f'Eliminate debt before rotation per near-term mandate.'
            )
        else:
            status, action = 'HOLD', (
                f'HOLD — leverage accretive (edge {economic_edge*100:+.1f}%). '
                f'Cost to close now: {crypto_units_to_close:.3f} ETH-equiv. '
                + ('At local cost-min — opportunistic close window if reducing risk.'
                   if at_local_min else
                   'Await lower cost-to-close (higher collateral ratio) for risk-reduction exit.')
            )

        return {
            'name': name,
            'debt_usd': round(debt_usd, 0),
            'collateral_usd': round(collateral_usd, 0),
            'collateral_ratio_pct': round(collateral_ratio, 1),
            'economic_edge_pct': round(economic_edge * 100, 2),
            'leverage_accretive': leverage_accretive,
            'crypto_units_to_close': round(crypto_units_to_close, 3),
            'at_local_cost_min': at_local_min,
            'annual_carry_cost': round(annual_carry, 0),
            'buffer_pct': round(buffer_pct * 100, 1),
            'status': status,
            'action': action,
            'cost_to_close_trend': cost_to_close_trend,
        }

    eth_usd = float(state.get('eth_usd', 1794))
    positions.append(analyze(
        'Maker Vault 30698', 'vault_30698',
        float(state.get('vault_30698_collateral_usd', 0) or 0),
        float(state.get('vault_30698_debt_usd', 0) or 0),
        float(state.get('vault_30698_ratio', 0) or 0),
        float(state.get('maker_stability_fee', 0.055) or 0.055),
        float(state.get('vault_30698_liq_price', 0) or 0),
        eth_usd,
    ))
    positions.append(analyze(
        'Maker Vault 31944', 'vault_31944',
        float(state.get('vault_31944_collateral_usd', 0) or 0),
        float(state.get('vault_31944_debt_usd', 0) or 0),
        float(state.get('vault_31944_ratio', 0) or 0),
        float(state.get('maker_stability_fee', 0.055) or 0.055),
        float(state.get('vault_31944_liq_price', 0) or 0),
        eth_usd,
    ))
    positions.append(analyze(
        'Aave V3 Arbitrum', 'aave',
        float(state.get('aave_collateral_usd', 0) or 0),
        float(state.get('aave_debt_usd', 0) or 0),
        float(state.get('aave_hf', 0) or 0) * 100,  # HF as ratio proxy
        float(state.get('aave_borrow_apr', 0.04) or 0.04),
        float(state.get('aave_liq_price', 0) or 0),
        eth_usd,
    ))

    any_close = any(p.get('status') in ('CLOSE_ECONOMIC', 'FORCE_CLOSE', 'CLOSE_CYCLE_TOP') for p in positions)
    any_economic_close = any(p.get('status') == 'CLOSE_ECONOMIC' for p in positions)
    any_force_close = any(p.get('status') == 'FORCE_CLOSE' for p in positions)
    any_cycle_top_close = any(p.get('status') == 'CLOSE_CYCLE_TOP' for p in positions)
    total_debt = sum(p.get('debt_usd', 0) for p in positions if isinstance(p.get('debt_usd'), (int, float)))
    buffers = [p['buffer_pct'] for p in positions if 'buffer_pct' in p]
    min_buffer_pct = round(min(buffers), 1) if buffers else None

    return {
        'positions': positions,
        'total_crypto_debt_usd': round(total_debt, 0),
        'any_close_signal': any_close,
        'any_economic_close_signal': any_economic_close,
        'any_force_close_signal': any_force_close,
        'any_cycle_top_close_signal': any_cycle_top_close,
        'min_buffer_pct': min_buffer_pct,
        'target': 'zero crypto debt',
        'method': 'three-lens: economic edge (accretive leverage, EV) + cost-to-close local minimum (risk reduction) + cycle-top goal (close before rotation near the top)',
        'strategy_note': (
            'Buy/borrow/die: debt is free leverage while collateral yield + '
            'appreciation > borrow rate. Economic closure only when edge turns '
            'negative. Risk-reduction closure is opportunistic at collateral highs '
            '(cost-to-close local minimum). Force-close only on liquidation danger.'
        ),
    }


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


def leverage_stress_test(state: dict) -> dict:
    """Read-only ETH price-shock stress test across every ETH-collateralized
    debt position (Aave + Maker vaults 30698/31944). Debt on all three is
    stablecoin-denominated while collateral is ETH/wstETH, so collateral
    value — and therefore HF/collateral-ratio — scales linearly with the ETH
    price; each position's liq_price (already computed by the collector as
    the ETH price at which it gets liquidated) doesn't move under the shock.
    That means "shocked_eth_usd < liq_price" is exactly the liquidation
    trigger, no re-derivation of liquidation thresholds needed.

    Scenarios are -15%/-30%/-50% ETH price shocks (mild/moderate/severe).
    Purely informational — fires no alerts and mutates nothing."""
    prices = state.get("prices") or {}
    eth_usd = float(state.get("eth_usd") or prices.get("eth_usd") or 0)
    if not eth_usd:
        return {"error": "eth_usd unavailable"}

    positions = [
        {"name": "Aave (wstETH/USDC)", "metric": "health_factor",
         "current": float(state.get("aave_hf") or 0),
         "liq_price": float(state.get("aave_liq_price") or 0)},
        {"name": "Maker vault 30698", "metric": "collateral_ratio_pct",
         "current": float(state.get("vault_30698_ratio") or 0),
         "liq_price": float(state.get("vault_30698_liq_price") or 0)},
        {"name": "Maker vault 31944", "metric": "collateral_ratio_pct",
         "current": float(state.get("vault_31944_ratio") or 0),
         "liq_price": float(state.get("vault_31944_liq_price") or 0)},
    ]

    scenarios = {}
    any_liquidation_risk_at_severe = False
    for label, pct in (("mild", 0.15), ("moderate", 0.30), ("severe", 0.50)):
        shocked_eth = eth_usd * (1 - pct)
        scale = shocked_eth / eth_usd
        rows = []
        for p in positions:
            if not p["current"] or not p["liq_price"]:
                continue
            liquidated = shocked_eth < p["liq_price"]
            if label == "severe" and liquidated:
                any_liquidation_risk_at_severe = True
            rows.append({
                "name": p["name"],
                "metric": p["metric"],
                "current": round(p["current"], 4),
                "shocked": round(p["current"] * scale, 4),
                "liq_price": round(p["liq_price"], 2),
                "liquidated": liquidated,
                "pct_headroom_to_liq_price": round((shocked_eth - p["liq_price"]) / p["liq_price"] * 100, 1),
            })
        scenarios[label] = {
            "eth_shock_pct": -pct * 100,
            "shocked_eth_usd": round(shocked_eth, 2),
            "positions": rows,
        }

    return {
        "eth_usd_current": eth_usd,
        "scenarios": scenarios,
        "any_liquidation_risk_at_severe": any_liquidation_risk_at_severe,
    }


SATELLITE_CORR_MIN_DAYS = 15  # below this, a return-series correlation is noise, not signal


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return None
    return cov / math.sqrt(vx * vy)


def satellite_correlation(state: dict) -> dict:
    """Rolling daily-return correlation of each satellite asset (LIT/VVV/RPL/
    HYPE) vs BTC and vs ETH. Purely informational — no position sizing or
    alerts derive from this, it's context for whether a satellite is adding
    diversification or just riding BTC/ETH beta.

    Reads state['satellite_price_history'], a list of daily
    {date, btc_usd, eth_usd, lit_usd, vvv_usd, rpl_usd, hype_usd} snapshots
    appended by the collector (missing keys on a given day are fine — dates
    are aligned per-asset before the return series is built). Needs
    >= SATELLITE_CORR_MIN_DAYS aligned day-over-day returns per asset;
    returns 'insufficient_data' status per-asset until then rather than a
    correlation computed on a handful of noisy points."""
    history = [e for e in (state.get("satellite_price_history") or []) if e.get("date")]
    history.sort(key=lambda e: e["date"])

    def daily_returns(key):
        series = [(e["date"], e[key]) for e in history if e.get(key)]
        out = {}
        for (d0, p0), (d1, p1) in zip(series, series[1:]):
            if p0:
                out[d1] = (p1 / p0) - 1
        return out

    btc_r = daily_returns("btc_usd")
    eth_r = daily_returns("eth_usd")

    out = {}
    for name, key in (("lit", "lit_usd"), ("vvv", "vvv_usd"), ("rpl", "rpl_usd"), ("hype", "hype_usd")):
        sat_r = daily_returns(key)
        dates_btc = sorted(set(sat_r) & set(btc_r))
        dates_eth = sorted(set(sat_r) & set(eth_r))
        if len(dates_btc) < SATELLITE_CORR_MIN_DAYS or len(dates_eth) < SATELLITE_CORR_MIN_DAYS:
            out[name] = {
                "status": "insufficient_data",
                "n_days_vs_btc": len(dates_btc),
                "n_days_vs_eth": len(dates_eth),
                "vs_btc": None,
                "vs_eth": None,
            }
            continue
        corr_btc = _pearson([sat_r[d] for d in dates_btc], [btc_r[d] for d in dates_btc])
        corr_eth = _pearson([sat_r[d] for d in dates_eth], [eth_r[d] for d in dates_eth])
        out[name] = {
            "status": "ok",
            "n_days_vs_btc": len(dates_btc),
            "n_days_vs_eth": len(dates_eth),
            "vs_btc": round(corr_btc, 3) if corr_btc is not None else None,
            "vs_eth": round(corr_eth, 3) if corr_eth is not None else None,
        }
    return out


def supply_overhang(state: dict) -> dict:
    """Track known structural BTC/ETH supply overhangs that suppress price
    (forced sellers, unlocks). These CREATE the cheap DCA prices — context,
    not alarm. Sourced live from state['strategy_monitor'] (EDGAR 8-K
    parsing of Strategy's actual realized BTC sales — see strategy_monitor.py),
    not a static authorized-capacity figure: authorized ≠ sold."""
    sm = state.get('strategy_monitor') or {}
    if not sm:
        return {'active_count': 0, 'line': None}

    auth = sm.get('authorized', {})
    real = sm.get('realized', {})
    rr = sm.get('run_rate', {})

    realized_usd = real.get('cumulative_usd_proceeds', 0)
    realized_btc = real.get('cumulative_btc_sold', 0)
    weekly = rr.get('weekly_usd_run_rate', 0)
    monthly_btc = rr.get('implied_monthly_btc_supply', 0)
    esc = ' ⚠ ESCALATING' if rr.get('escalating') else ''

    line = (
        f"Supply overhang: Strategy ≥${auth.get('capped_total_usd', 0) / 1e9:.2f}B "
        f"authorized (1 uncapped bucket) | realized ${realized_usd / 1e6:.0f}M "
        f"({realized_btc:,} BTC) | run-rate ${weekly / 1e6:.0f}M/wk "
        f"→ ~{monthly_btc:,.0f} BTC/mo{esc} — suppresses price, feeds DCA thesis"
    )
    return {
        'active_count': 1,
        'line': line,
        'escalating': rr.get('escalating', False),
        'months_coverage': sm.get('solvency', {}).get('months_coverage'),
    }


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
    # audit_factor/tvl_m must clear PRIMARY_MIN_TVL_M/PRIMARY_ALLOCATION_MIN_AUDIT_FACTOR
    # or the gate routes 100% to DCA regardless of cycle pct (see allocate_capital).
    alloc = allocate_capital(6.8, 1000, [{"name": "sUSDai", "apy": 7.8, "tvl_m": 200, "audit_factor": 0.9}])
    assert 850 < alloc["dca"] < 900, alloc  # Kelly at ~7th pct: ~88.6% DCA, not 100%
    alloc2 = allocate_capital(25, 1000, [{"name": "sUSDai", "apy": 7.8, "tvl_m": 200, "audit_factor": 0.9}])
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
