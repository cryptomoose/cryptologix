#!/usr/bin/env python3
"""
Sync check: cryptologix/signal_core.py must be byte-identical to the
authoritative copy in the crypto advisory engine. Discrepancies are bugs.

Run manually or from CI:  python3 check_sync.py
Exit 0 = in sync, exit 1 = drift (or authoritative copy not found locally,
which is a skip on cloud deploys — exit 0 with a notice).

The crypto engine runs the mirror-image check daily (crypto_data_collector
calls signal_core.verify_sync and raises a CRITICAL alert on drift).
"""

import os
import sys

from signal_core import SIGNAL_CORE_VERSION, file_hash

AUTHORITATIVE = os.path.expanduser(
    "~/projects/willie-agent-stack/crypto/signal_core.py"
)


def main() -> int:
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signal_core.py")
    if not os.path.exists(AUTHORITATIVE):
        print(f"SKIP: authoritative copy not found at {AUTHORITATIVE} "
              "(expected on cloud deploys)")
        return 0
    h_local, h_auth = file_hash(local), file_hash(AUTHORITATIVE)
    if h_local == h_auth:
        print(f"OK: signal_core v{SIGNAL_CORE_VERSION} in sync ({h_local[:12]}…)")
        return 0
    print("CRITICAL: signal_core.py has drifted between repos!")
    print(f"  cryptologix:  {h_local}")
    print(f"  crypto engine: {h_auth}")
    print(f"  Fix: cp {AUTHORITATIVE} {local}  (crypto engine is authoritative)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
