"""
Rotation Log — CSV-backed ledger for crypto↔metals rotations with live performance tracking.

Storage: /tmp/cryptologix_rotation_log.csv (survives restarts, wiped on cold start)
Export:  Download button in UI.

Each rotation entry captures:
  - timestamp, direction (e.g. BTC_TO_GOLD)
  - rotation_pct: % of position rotated
  - prices at execution: btc, eth, gold, silver
  - signal snapshot: btc_percentile, eth_percentile, btc_signal, eth_signal, cycle_phase
  - status: OPEN | CLOSED
  - closed_at, close prices (on close)

Performance calculated live on load:
  - rotated_asset_return_pct: return on what you rotated INTO since execution
  - crypto_held_return_pct:   return on the crypto you EXITED if you had held
  - alpha_pct:                rotated - held (positive = rotation was correct)
"""

import os
import csv
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

LOG_PATH = '/tmp/cryptologix_rotation_log.csv'

COLUMNS = [
    'timestamp',
    'direction',
    'rotation_pct',
    'btc_price',
    'eth_price',
    'gold_price',
    'silver_price',
    'btc_percentile',
    'eth_percentile',
    'btc_signal',
    'eth_signal',
    'cycle_phase',
    'notes',
    'status',
    'closed_at',
    'close_btc_price',
    'close_eth_price',
    'close_gold_price',
    'close_silver_price',
]


def _ensure_log():
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()


def _rewrite_all(entries):
    with open(LOG_PATH, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for e in entries:
            writer.writerow({col: e.get(col, '') for col in COLUMNS})


def log_rotation(direction, rotation_pct, signals, live_prices, cycle_phase, notes=''):
    _ensure_log()
    entry = {
        'timestamp':      datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'direction':      direction,
        'rotation_pct':   round(rotation_pct, 1),
        'btc_price':      round(live_prices.get('btc', 0), 2) if live_prices else '',
        'eth_price':      round(live_prices.get('eth', 0), 2) if live_prices else '',
        'gold_price':     round(live_prices.get('gold', 0), 2) if live_prices else '',
        'silver_price':   round(live_prices.get('silver', 0), 4) if live_prices else '',
        'btc_percentile': round(signals.get('btc_percentile', 0), 1),
        'eth_percentile': round(signals.get('eth_percentile', 0), 1),
        'btc_signal':     signals.get('btc_signal', ''),
        'eth_signal':     signals.get('eth_signal', ''),
        'cycle_phase':    cycle_phase,
        'notes':          notes,
        'status':         'OPEN',
        'closed_at':      '',
        'close_btc_price':    '',
        'close_eth_price':    '',
        'close_gold_price':   '',
        'close_silver_price': '',
    }
    with open(LOG_PATH, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(entry)


def close_rotation(row_index, live_prices):
    entries = load_log_raw()
    if row_index >= len(entries):
        return False
    e = entries[row_index]
    if e['status'] == 'CLOSED':
        return False
    e['status']             = 'CLOSED'
    e['closed_at']          = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    e['close_btc_price']    = round(live_prices.get('btc', 0), 2)
    e['close_eth_price']    = round(live_prices.get('eth', 0), 2)
    e['close_gold_price']   = round(live_prices.get('gold', 0), 2)
    e['close_silver_price'] = round(live_prices.get('silver', 0), 4)
    _rewrite_all(entries)
    return True


def load_log_raw():
    _ensure_log()
    try:
        with open(LOG_PATH, 'r', newline='') as f:
            return list(csv.DictReader(f))
    except Exception as e:
        logger.error(f"Failed to load log: {e}")
        return []


def _safe_float(val, default=None):
    try:
        return float(val) if val != '' else default
    except (ValueError, TypeError):
        return default


def _parse_direction(direction):
    direction = (direction or '').upper().strip()
    if '_TO_' in direction:
        parts = direction.split('_TO_')
        return parts[0], parts[1]
    if direction == 'ROTATE_TO_GOLD':
        return 'BTC', 'GOLD'
    if direction == 'ROTATE_TO_CRYPTO':
        return 'GOLD', 'BTC'
    return None, None


def _price_key(asset):
    return {'BTC': 'btc', 'ETH': 'eth', 'GOLD': 'gold', 'SILVER': 'silver'}.get(asset)


def _entry_price(entry, asset, use_close=False):
    key_map = (
        {'BTC': 'close_btc_price', 'ETH': 'close_eth_price',
         'GOLD': 'close_gold_price', 'SILVER': 'close_silver_price'}
        if use_close else
        {'BTC': 'btc_price', 'ETH': 'eth_price',
         'GOLD': 'gold_price', 'SILVER': 'silver_price'}
    )
    return _safe_float(entry.get(key_map.get(asset, ''), ''))


def compute_performance(entry, live_prices):
    from_asset, to_asset = _parse_direction(entry.get('direction', ''))
    if from_asset is None:
        return {}

    is_closed = entry.get('status', 'OPEN') == 'CLOSED'

    entry_from = _entry_price(entry, from_asset)
    entry_to   = _entry_price(entry, to_asset)

    if is_closed:
        eval_from = _entry_price(entry, from_asset, use_close=True)
        eval_to   = _entry_price(entry, to_asset,   use_close=True)
        eval_label = 'close'
    else:
        eval_from = live_prices.get(_price_key(from_asset))
        eval_to   = live_prices.get(_price_key(to_asset))
        eval_label = 'live'

    rotated_return = ((eval_to - entry_to) / entry_to * 100
                      if entry_to and eval_to and entry_to > 0 else None)
    held_return    = ((eval_from - entry_from) / entry_from * 100
                      if entry_from and eval_from and entry_from > 0 else None)
    alpha = (rotated_return - held_return
             if rotated_return is not None and held_return is not None else None)

    return {
        'from_asset':               from_asset,
        'to_asset':                 to_asset,
        'rotated_asset_return_pct': rotated_return,
        'crypto_held_return_pct':   held_return,
        'alpha_pct':                alpha,
        'is_closed':                is_closed,
        'evaluation_prices':        eval_label,
    }


def load_log_with_performance(live_prices):
    return [{**e, **compute_performance(e, live_prices)} for e in load_log_raw()]


def get_performance_summary(entries_with_perf):
    if not entries_with_perf:
        return {}
    alphas = [e['alpha_pct'] for e in entries_with_perf if e.get('alpha_pct') is not None]
    return {
        'total_rotations':  len(entries_with_perf),
        'open_rotations':   sum(1 for e in entries_with_perf if e.get('status') == 'OPEN'),
        'closed_rotations': sum(1 for e in entries_with_perf if e.get('status') == 'CLOSED'),
        'avg_alpha_pct':    round(sum(alphas) / len(alphas), 2) if alphas else None,
        'win_rate_pct':     round(sum(1 for a in alphas if a > 0) / len(alphas) * 100, 1) if alphas else None,
        'best_alpha_pct':   round(max(alphas), 2) if alphas else None,
        'worst_alpha_pct':  round(min(alphas), 2) if alphas else None,
        'total_alpha_pct':  round(sum(alphas), 2) if alphas else None,
    }


def get_log_csv_bytes():
    _ensure_log()
    try:
        with open(LOG_PATH, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read log for download: {e}")
        return b''
