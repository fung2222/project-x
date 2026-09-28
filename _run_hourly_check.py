#!/usr/bin/env python3
"""Hourly position check (legacy entry point kept for the Grok Bot routine).

Thin wrapper -> `python run.py hourly` engine (px/jobs/hourly.py).
Same outputs as before: _last_hourly_check.json, .last_hourly_quiet_hkt, the
Grok Bot automation state file (if that directory exists), printed JSON with
alerts / need_push / pushed. Telegram is alert-only plus ONE status message per
US session (was: per HKT day, i.e. twice a night). SL/TP hits are auto-executed
on the paper ledger (reported as *_EXECUTED in positions[].action and alerts).
Flags: --dry-run, --force.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from px.jobs import hourly  # noqa: E402

if __name__ == "__main__":
    res = hourly.run(dry_run="--dry-run" in sys.argv, force="--force" in sys.argv, legacy=True)
    if res.get("status") == "skipped":
        import json
        print(json.dumps({"skipped": True, "reason": res.get("reason"), "alerts": [], "need_push": False,
                          "pushed": False, "push_reason": "none"}, ensure_ascii=False, indent=2))
