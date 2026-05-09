"""
Disk-based persistent cache for cryptologix.

Purpose: Survive Autoscale cold starts. Streamlit's @st.cache_data is in-memory
only — it is wiped every time the container restarts. This module saves computed
results to /tmp so that when the app cold-starts a new container, expensive
data fetches and calculations are skipped if a fresh copy is already on disk.

Usage:
    import disk_cache

    result = disk_cache.load('my_key', max_age_hours=24)
    if result is None:
        result = expensive_computation()
        disk_cache.save('my_key', result)
    return result
"""

import os
import pickle
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

CACHE_DIR = '/tmp/cryptologix_cache'


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _cache_path(key: str) -> str:
    safe_key = key.replace('/', '_').replace('=', '_').replace('-', '_').replace(' ', '_')
    return os.path.join(CACHE_DIR, f"{safe_key}.pkl")


def save(key: str, data) -> bool:
    """Persist data to disk. Returns True on success."""
    _ensure_cache_dir()
    path = _cache_path(key)
    try:
        payload = {'data': data, 'saved_at': datetime.now()}
        with open(path, 'wb') as f:
            pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"Disk cache saved: {key}")
        return True
    except Exception as e:
        logger.warning(f"Disk cache save failed for '{key}': {e}")
        return False


def load(key: str, max_age_hours: float = 24):
    """Load data from disk if it exists and is within max_age_hours. Returns None on miss."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            payload = pickle.load(f)
        saved_at = payload.get('saved_at')
        if saved_at is None:
            return None
        age_hours = (datetime.now() - saved_at).total_seconds() / 3600
        if age_hours > max_age_hours:
            logger.info(f"Disk cache expired for '{key}': {age_hours:.1f}h old (max {max_age_hours}h)")
            return None
        logger.info(f"Disk cache hit: '{key}' ({age_hours:.1f}h old)")
        return payload['data']
    except Exception as e:
        logger.warning(f"Disk cache load failed for '{key}': {e}")
        return None


def invalidate(key: str) -> bool:
    """Delete a specific cache entry."""
    path = _cache_path(key)
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Disk cache invalidated: {key}")
        return True
    except Exception as e:
        logger.warning(f"Disk cache invalidation failed for '{key}': {e}")
        return False


def clear_all() -> int:
    """Delete all cache files. Returns count of files deleted."""
    if not os.path.exists(CACHE_DIR):
        return 0
    count = 0
    for fname in os.listdir(CACHE_DIR):
        if fname.endswith('.pkl'):
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
                count += 1
            except Exception:
                pass
    logger.info(f"Disk cache cleared: {count} files deleted")
    return count
