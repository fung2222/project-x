#!/usr/bin/env python3
"""Project X open-monitor (legacy entry point kept for the Grok Bot routine).

Thin wrapper -> `python run.py open` engine (px/jobs/open_monitor.py).
Same outputs as before: Telegram (1 msg, now guarded against double-send per
US session), _last_open_monitor.json, Reports/OpenMonitor_<date>.txt, and the
printed JSON / ---MSG--- / ---TG--- block. SL/TP hits are now auto-executed on
the paper ledger (and reported as *_EXECUTED) instead of only flagged.
Flags: --dry-run (no Telegram / no writes), --force (ignore window + guard).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from px.jobs import open_monitor  # noqa: E402

if __name__ == "__main__":
    res = open_monitor.run(dry_run="--dry-run" in sys.argv, force="--force" in sys.argv, legacy=True)
    if res.get("status") in ("skipped", "duplicate"):
        print("---TG--- skipped", res.get("reason"))
