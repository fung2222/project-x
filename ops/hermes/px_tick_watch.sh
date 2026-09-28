#!/usr/bin/env bash
# px_tick_watch.sh — Hermes-cron watchdog for supercronic (spec §5 step 2b, §6 amendments).
# Called every 10 minutes by Hermes cron (`hermes cron create --script --no-agent */10 * * * *`).
# Detects existing supercronic (by /proc/<pid>/comm), starts it via setsid+nohup if missing,
# updates the PID file, never spawns a duplicate. Logs to $PX_RUN_DIR/px_tick_watch.log.
set -uo pipefail
PX_BIN_DIR="${PX_BIN_DIR:-/opt/data/bin}"
PX_HOME="${PX_HOME:-/opt/data/project-x}"
PX_RUN_DIR="${PX_RUN_DIR:-/opt/data/project-x/run}"
PX_CRONTAB="${PX_HOME}/ops/hermes/crontab.txt"
PID_FILE="$PX_RUN_DIR/supercronic.pid"
LOG_FILE="$PX_RUN_DIR/px_tick_watch.log"
mkdir -p "$PX_RUN_DIR"
ts() { date '+%F %T'; }
log() { printf '[%s] %s\n' "$(ts)" "$*" >>"$LOG_FILE"; }

# pid_alive_and_real $pid -> exit 0 only if the pid is a running (non-zombie) process whose
# /proc/$pid/comm is exactly "supercronic". A zombie would otherwise satisfy kill -0
# (zombies are in the process table even when not runnable) and confuse this check.
pid_alive_and_real() {
    local pid="$1"
    [ -n "$pid" ] || return 1
    [ -r "/proc/$pid/status" ] || return 1
    local state
    state="$(awk '/^State:/ {print $2}' "/proc/$pid/status" 2>/dev/null)"
    [ "$state" = "R" ] || [ "$state" = "S" ] || [ "$state" = "D" ] || [ "$state" = "I" ] || return 1
    [ -r "/proc/$pid/comm" ] || return 1
    [ "$(cat "/proc/$pid/comm" 2>/dev/null)" = "supercronic" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    return 0
}

is_running() {
    local pid
    pid="$(cat "$PID_FILE" 2>/dev/null)" || return 1
    [ -n "$pid" ] || { rm -f "$PID_FILE"; return 1; }
    if pid_alive_and_real "$pid"; then
        return 0
    fi
    # PID file is stale OR points at a zombie OR was reused. Try to adopt an existing
    # supercronic whose cmdline references our crontab, instead of spawning a duplicate.
    local existing
    existing="$(pgrep -f "supercronic.*ops/hermes/crontab\\.txt" | head -n1)"
    if [ -n "$existing" ] && pid_alive_and_real "$existing"; then
        echo "$existing" >"$PID_FILE"
        log "adopted orphan supercronic pid=$existing (was looking for pid=$pid)"
        return 0
    fi
    log "stale pid $pid; clearing (state check or pgrep failed)"
    rm -f "$PID_FILE"
    return 1
}

if is_running; then
    log "supercronic alive (pid=$(cat "$PID_FILE"))"
    exit 0
fi

log "supercronic not running; starting (setsid+nohup)"
setsid nohup "$PX_BIN_DIR/supercronic" -quiet "$PX_CRONTAB" \
    >>"$PX_RUN_DIR/supercronic.log" 2>&1 < /dev/null &
echo $! >"$PID_FILE"
sleep 1
NEW_PID="$(cat "$PID_FILE")"
if pid_alive_and_real "$NEW_PID"; then
    log "started supercronic pid=$NEW_PID"
    exit 0
else
    log "ERROR: supercronic failed to start (pid file: $NEW_PID)"
    exit 3
fi
