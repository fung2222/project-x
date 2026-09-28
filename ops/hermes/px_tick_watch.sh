#!/usr/bin/env bash
# px_tick_watch.sh — Hermes-cron watchdog for supercronic (spec §5 step 2b).
# Called every 10 minutes by Hermes cron (`hermes cron create --script --no-agent * */10 * * *`).
# If supercronic is not running, start it. Logs to $PX_RUN_DIR/px_tick_watch.log.
set -uo pipefail
PX_BIN_DIR="${PX_BIN_DIR:-/opt/data/bin}"
PX_HOME="${PX_HOME:-/opt/data/project-x}"
PX_RUN_DIR="${PX_RUN_DIR:-/opt/data/project-x/run}"
PID_FILE="$PX_RUN_DIR/supercronic.pid"
LOG_FILE="$PX_RUN_DIR/px_tick_watch.log"
mkdir -p "$PX_RUN_DIR"
ts() { date '+%F %T'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

is_running() {
    [ -f "$PID_FILE" ] || return 1
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null)" || return 1
    [ -n "$pid" ] || { rm -f "$PID_FILE"; return 1; }
    kill -0 "$pid" 2>/dev/null && return 0
    log "stale pid $pid; clearing"
    rm -f "$PID_FILE"
    return 1
}

if is_running; then
    log "supercronic alive (pid=$(cat "$PID_FILE"))"
    exit 0
fi

log "supercronic not running; starting"
nohup "$PX_BIN_DIR/supercronic" "$PX_HOME/ops/hermes/crontab.txt" \
    >"$PX_RUN_DIR/supercronic.log" 2>&1 &
echo $! >"$PID_FILE"
sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "started supercronic pid=$(cat "$PID_FILE")"
    exit 0
else
    log "ERROR: supercronic failed to start"
    exit 3
fi
