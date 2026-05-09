"""
Rotation Log — persistent CSV-backed ledger for DCA entries and rotations.

Storage: /tmp/cryptologix_rotation_log.csv (survives restarts, wiped on cold start)
Export: Download button in UI for local backup.

Each entry captures:
  - timestamp, entry_type (DCA | ROTATION)
  - btc_amount_usd, eth_amount_usd, total_usd
  - multiplier (DCA entries)
  - rotation_direction, rotation_pct (rotation entries)
  - btc_price, eth_price, gold_price, silver_price (at time of entry)
  - btc_percentile, eth_percentile, btc_signal, eth_signal (signal snapshot)
  - cycle_phase, notes
"""

import os
import csv
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

LOG_PATH = '/tmp/cryptologix_rotation_log.csv'

COLUMNS = [
    'timestamp',
    'entry_type',           # DCA | ROTATION
    'btc_amount_usd',
    'eth_amount_usd',
    'total_usd',
    'multiplier',           # DCA multiplier vs baseline
    'rotation_direction',   # CRYPTO_TO_GOLD | GOLD_TO_CRYPTO | etc.
    'rotation_pct',         # % of portfolio rotated
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
]


def _ensure_log():
    """Create log file with headers if it doesn't exist."""
    if not os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
        logger.info(f"Created new rotation log at {LOG_PATH}")


def _append_entry(entry: dict):
    """Append a single entry to the CSV."""
    _ensure_log()
    # Fill any missing columns with empty string
    row = {col: entry.get(col, '') for col in COLUMNS}
    with open(LOG_PATH, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writerow(row)
    logger.info(f"Rotation log entry appended: {entry.get('entry_type')} ${entry.get('total_usd', 0):,.2f}")


def log_dca(
    btc_amount_usd: float,
    eth_amount_usd: float,
    multiplier: float,
    signals: dict,
    live_prices: dict,
    cycle_phase: str,
    notes: str = ''
):
    """Record a DCA entry with full signal snapshot."""
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'entry_type': 'DCA',
        'btc_amount_usd': round(btc_amount_usd, 2),
        'eth_amount_usd': round(eth_amount_usd, 2),
        'total_usd': round(btc_amount_usd + eth_amount_usd, 2),
        'multiplier': round(multiplier, 3),
        'rotation_direction': '',
        'rotation_pct': '',
        'btc_price': round(live_prices.get('btc', 0), 2) if live_prices else '',
        'eth_price': round(live_prices.get('eth', 0), 2) if live_prices else '',
        'gold_price': round(live_prices.get('gold', 0), 2) if live_prices else '',
        'silver_price': round(live_prices.get('silver', 0), 4) if live_prices else '',
        'btc_percentile': round(signals.get('btc_percentile', 0), 1),
        'eth_percentile': round(signals.get('eth_percentile', 0), 1),
        'btc_signal': signals.get('btc_signal', ''),
        'eth_signal': signals.get('eth_signal', ''),
        'cycle_phase': cycle_phase,
        'notes': notes,
    }
    _append_entry(entry)


def log_rotation(
    rotation_direction: str,
    rotation_pct: float,
    total_usd: float,
    signals: dict,
    live_prices: dict,
    cycle_phase: str,
    notes: str = ''
):
    """Record a rotation entry with full signal snapshot."""
    entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'entry_type': 'ROTATION',
        'btc_amount_usd': '',
        'eth_amount_usd': '',
        'total_usd': round(total_usd, 2),
        'multiplier': '',
        'rotation_direction': rotation_direction,
        'rotation_pct': round(rotation_pct, 1),
        'btc_price': round(live_prices.get('btc', 0), 2) if live_prices else '',
        'eth_price': round(live_prices.get('eth', 0), 2) if live_prices else '',
        'gold_price': round(live_prices.get('gold', 0), 2) if live_prices else '',
        'silver_price': round(live_prices.get('silver', 0), 4) if live_prices else '',
        'btc_percentile': round(signals.get('btc_percentile', 0), 1),
        'eth_percentile': round(signals.get('eth_percentile', 0), 1),
        'btc_signal': signals.get('btc_signal', ''),
        'eth_signal': signals.get('eth_signal', ''),
        'cycle_phase': cycle_phase,
        'notes': notes,
    }
    _append_entry(entry)


def load_log() -> list[dict]:
    """Load all log entries as list of dicts. Returns [] if log doesn't exist."""
    _ensure_log()
    try:
        with open(LOG_PATH, 'r', newline='') as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        logger.error(f"Failed to load rotation log: {e}")
        return []


def get_log_csv_bytes() -> bytes:
    """Return raw CSV bytes for download button."""
    _ensure_log()
    try:
        with open(LOG_PATH, 'rb') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to read log for download: {e}")
        return b''


def get_summary_stats(entries: list[dict]) -> dict:
    """Compute summary stats from log entries."""
    if not entries:
        return {
            'total_dca_entries': 0,
            'total_rotation_entries': 0,
            'total_deployed_usd': 0,
            'total_btc_usd': 0,
            'total_eth_usd': 0,
            'avg_btc_percentile_at_dca': None,
            'avg_eth_percentile_at_dca': None,
            'last_entry_date': None,
        }

    dca = [e for e in entries if e['entry_type'] == 'DCA']
    rotations = [e for e in entries if e['entry_type'] == 'ROTATION']

    def safe_float(val, default=0.0):
        try:
            return float(val) if val != '' else default
        except (ValueError, TypeError):
            return default

    total_deployed = sum(safe_float(e['total_usd']) for e in dca)
    total_btc = sum(safe_float(e['btc_amount_usd']) for e in dca)
    total_eth = sum(safe_float(e['eth_amount_usd']) for e in dca)

    btc_pcts = [safe_float(e['btc_percentile']) for e in dca if e['btc_percentile'] != '']
    eth_pcts = [safe_float(e['eth_percentile']) for e in dca if e['eth_percentile'] != '']

    last_date = entries[-1]['timestamp'] if entries else None

    return {
        'total_dca_entries': len(dca),
        'total_rotation_entries': len(rotations),
        'total_deployed_usd': round(total_deployed, 2),
        'total_btc_usd': round(total_btc, 2),
        'total_eth_usd': round(total_eth, 2),
        'avg_btc_percentile_at_dca': round(sum(btc_pcts) / len(btc_pcts), 1) if btc_pcts else None,
        'avg_eth_percentile_at_dca': round(sum(eth_pcts) / len(eth_pcts), 1) if eth_pcts else None,
        'last_entry_date': last_date,
    }
