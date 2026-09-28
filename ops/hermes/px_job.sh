#!/usr/bin/env bash
# Project X job wrapper for Hermes (Linux). No LLM involved.
#   ops/hermes/px_job.sh tick            # every minute from cron (recommended; runs due jobs + watchdog)
#   ops/hermes/px_job.sh <job> [args]    # open|daily|hourly|close|morning|weekly|check|status|tgcheck|scan
# Env (all optional):
#   PX_HOME     repo clone            (default /opt/data/project-x)
#   PX_VENV     python venv           (default $PX_HOME/.venv)
#   PX_ENV_FILE secrets file          (default /opt/data/.env; repo .env also read; PX_* names win)
#   PX_LOG_DIR  log directory         (default $PX_HOME/logs, 30-day retention)
#   PX_TIMEOUT  per-run timeout, sec  (default 900)
set -uo pipefail
JOB="${1:-}"; shift || true
[ -n "$JOB" ] || { echo "usage: $0 <job> [args]"; exit 64; }
PX_HOME="${PX_HOME:-/opt/data/project-x}"
PX_VENV="${PX_VENV:-$PX_HOME/.venv}"
export PX_ENV_FILE="${PX_ENV_FILE:-/opt/data/.env}"
LOG_DIR="${PX_LOG_DIR:-$PX_HOME/logs}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$(date +%Y-%m-%d)_${JOB}.log"
cd "$PX_HOME" || { echo "[px_job] cannot cd $PX_HOME" >&2; exit 1; }

case "$JOB" in
  open|daily|hourly|close|morning|weekly|check|tick) PUSH="--push" ;;
  *) PUSH="" ;;
esac

# tick runs every minute: skip instantly if a previous run still holds the lock (-n);
# direct job runs wait up to 10 min for the lock (-w 600) so two jobs never run at once.
if [ "$JOB" = "tick" ]; then LOCKOPT="-n"; else LOCKOPT="-w 600"; fi

(
  flock $LOCKOPT 9 || { [ "$JOB" = "tick" ] || echo "[px_job] $(date '+%F %T') lock busy, $JOB not run" >>"$LOG"; exit 0; }
  # sync with origin first (Roy/Hermes may have edited data/futu_positions.json elsewhere)
  git pull --rebase --autostash -q origin main >/dev/null 2>&1 || echo "[px_job] $(date '+%F %T') git pull failed; using local copy" >>"$LOG"
  OUT="$(timeout "${PX_TIMEOUT:-900}" "$PX_VENV/bin/python" run.py "$JOB" $PUSH "$@" 2>&1)"; RC=$?
  # tick is silent when nothing is due -> only log when it did something or failed
  if [ "$JOB" != "tick" ] || [ -n "$OUT" ] || [ $RC -ne 0 ]; then
    { echo "=== $(date '+%F %T %Z') $JOB $* (exit $RC)"; echo "$OUT"; } >>"$LOG"
  fi
  [ $RC -eq 124 ] && echo "[px_job] $(date '+%F %T') $JOB TIMEOUT after ${PX_TIMEOUT:-900}s" >>"$LOG"
  exit $RC
) 9>"$PX_HOME/.px.lock"
RC=$?
find "$LOG_DIR" -name '*.log' -mtime +30 -delete 2>/dev/null || true
exit $RC
