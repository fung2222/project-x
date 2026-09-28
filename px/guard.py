"""Duplicate-send / idempotency guard: state/job_runs.json

{ "<session_date ET>": { "<job>": {"sent": {"<part>": {"at":..,"ids":[..]}},
                                   "status": "ok|failed|skipped", "runs": n, ... } } }
A message part recorded as sent is never sent again for that session unless --force.
Entries older than 45 days are pruned."""
import datetime as dt
import json
import os
import tempfile

from . import clock
from .config import STATE_DIR

PATH = os.path.join(STATE_DIR, "job_runs.json")


def _load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(STATE_DIR, exist_ok=True)
    cutoff = (dt.date.today() - dt.timedelta(days=45)).isoformat()
    d = {k: v for k, v in d.items() if k >= cutoff}
    fd, tmp = tempfile.mkstemp(prefix=".job_runs.", dir=STATE_DIR)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(d.items())), f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)


def job_state(session, job):
    return _load().get(str(session), {}).get(job, {})


def was_sent(session, job, part):
    return part in job_state(session, job).get("sent", {})


def mark_sent(session, job, part, ids=None):
    d = _load()
    j = d.setdefault(str(session), {}).setdefault(job, {})
    j.setdefault("sent", {})[part] = {"at": clock.now_hkt().isoformat(timespec="seconds"), "ids": ids or []}
    _save(d)


def update(session, job, **fields):
    d = _load()
    j = d.setdefault(str(session), {}).setdefault(job, {})
    if fields.pop("_inc_runs", False):
        j["runs"] = j.get("runs", 0) + 1
    j.update(fields)
    _save(d)
    return j


def get_all():
    return _load()


# ---------------------------------------------------------------- shared REAL-position alert de-dup
# One store per US session shared by hourly + realwatch (+ any job that pushes real alerts), so the same condition
# (e.g. "IONQ SL@38.0", "IONQ DROP step 5") is pushed at most once per session whichever job sees it first.
REAL_KEY = "real"


def real_alerted(session):
    return dict(job_state(session, REAL_KEY).get("alerts", {}))


def save_real_alerted(session, alerted, by=None):
    """Merge (never drop) alert keys after a SUCCESSFUL send."""
    d = _load()
    j = d.setdefault(str(session), {}).setdefault(REAL_KEY, {})
    cur = j.setdefault("alerts", {})
    cur.update(alerted or {})
    j["updated"] = clock.now_hkt().isoformat(timespec="seconds")
    if by:
        j["last_by"] = by
    _save(d)
    return cur
