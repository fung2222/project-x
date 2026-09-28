#!/usr/bin/env bash
# px_runner_install.sh — Idempotent install of supercronic + (optional) s6 service for Project X tick.
# Path conventions: /opt/data/project-x (symlink to clone), /opt/data/bin (binary), /opt/data/project-x/ops/hermes.
#
# This script:
#   1. Ensures /opt/data/project-x symlink exists -> /opt/data/github-repos/project-x
#   2. Downloads supercronic v0.2.33 to /opt/data/bin/supercronic (if missing)
#   3. Validates ops/hermes/crontab.txt with supercronic -test
#   4. Tries to write s6 service files at /etc/s6-overlay/s6-rc.d/svc-px-tick (requires root; we are not root)
#      -> If writable, enable; else skip with explicit reason.
#   5. Installs /opt/data/bin/px_tick_watch.sh by copying the version-controlled repo file verbatim
#      (avoids heredoc-escape fragility; keep the two files in sync via the repo as single source of truth).
#   6. Idempotent: safe to re-run.
#
# Usage:
#   px_runner_install.sh                       # full install (logs only)
#   px_runner_install.sh check                 # report status, no changes
#   px_runner_install.sh uninstall             # remove binary, s6 service
#
# Exit codes:
#   0 = ok
#   1 = download failed
#   2 = crontab.txt invalid
#
# env: PX_HOME, PX_BIN_DIR, SUPERICRONIC_VERSION

set -uo pipefail

PX_HOME="${PX_HOME:-/opt/data/project-x}"
PX_BIN_DIR="${PX_BIN_DIR:-/opt/data/bin}"
SUPERICRONIC_VERSION="${SUPERICRONIC_VERSION:-v0.2.33}"
LOG_FILE="${LOG_FILE:-/opt/data/project-x/logs/px_runner_install.log}"
RUN_DIR="${PX_RUN_DIR:-/opt/data/project-x/run}"
mkdir -p "$(dirname "$LOG_FILE")" "$RUN_DIR"
PID_FILE="$RUN_DIR/supercronic.pid"
S6_DIR="/etc/s6-overlay/s6-rc.d/svc-px-tick"

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$LOG_FILE" >&2 ; }

ensure_symlink() {
    if [ ! -e "/opt/data/project-x" ]; then
        if [ -e "/opt/data/github-repos/project-x" ]; then
            log "Creating symlink /opt/data/project-x -> /opt/data/github-repos/project-x"
            ln -s /opt/data/github-repos/project-x /opt/data/project-x
        else
            log "ERROR: source /opt/data/github-repos/project-x not found"
            return 1
        fi
    else
        log "Symlink /opt/data/project-x already exists"
    fi
}

download_supercronic() {
    mkdir -p "$PX_BIN_DIR"
    local bin="$PX_BIN_DIR/supercronic"
    if [ -x "$bin" ] && "$bin" -version >/dev/null 2>&1; then
        local current
        current="$("$bin" -version 2>&1 | head -1)"
        log "supercronic already installed: $current"
        return 0
    fi
    log "Downloading supercronic $SUPERICRONIC_VERSION ..."
    local url="https://github.com/aptible/supercronic/releases/download/$SUPERICRONIC_VERSION/supercronic-linux-amd64"
    if ! curl -fsSL -o "$bin.tmp" "$url"; then
        log "ERROR: download failed ($url)"
        return 1
    fi
    chmod +x "$bin.tmp"
    mv "$bin.tmp" "$bin"
    log "Installed: $bin ($("$bin" -version 2>&1 | head -1))"
}

validate_crontab() {
    local tab="$PX_HOME/ops/hermes/crontab.txt"
    if [ ! -f "$tab" ]; then
        log "ERROR: crontab not found: $tab"
        return 1
    fi
    if ! "$PX_BIN_DIR/supercronic" -test "$tab" >/dev/null 2>&1; then
        log "ERROR: crontab validation FAILED. Run: $PX_BIN_DIR/supercronic -test $tab"
        return 1
    fi
    log "crontab validated: $tab"
}

try_s6_install() {
    # Spec §5 step 2a requested. We try; if /etc/s6-overlay not writable, skip and rely on Hermes cron fallback.
    if [ -w "/etc/s6-overlay/s6-rc.d" ]; then
        log "s6 overlay writable, installing svc-px-tick"
        mkdir -p "$S6_DIR"
        printf 'longrun\n' >"$S6_DIR/type"
        cat >"$S6_DIR/run" <<RUNEOF
#!/usr/bin/with-contenv bash
exec "$PX_BIN_DIR/supercronic" "$PX_HOME/ops/hermes/crontab.txt"
RUNEOF
        chmod +x "$S6_DIR/run"
        touch /etc/s6-overlay/s6-rc.d/user/contents.d/svc-px-tick 2>/dev/null || true
        if command -v s6-rc-bundle >/dev/null 2>&1; then
            s6-rc-bundle -i /etc/s6-overlay/s6-rc.d add svc-px-tick default 2>/dev/null || true
        fi
        log "s6 service installed at $S6_DIR (NOT started per spec §5 step 3c)"
        return 0
    else
        log "SKIP s6 install: /etc/s6-overlay/s6-rc.d not writable (hermes user lacks root). Falling back to Hermes cron watch (spec §5 step 2b)."
        return 1
    fi
}

write_watch_script() {
    # Source of truth is the version-controlled copy in the repo. Copy verbatim to /opt/data/bin
    # so future re-runs stay in sync. No heredoc fragility.
    local src="$PX_HOME/ops/hermes/px_tick_watch.sh"
    if [ ! -f "$src" ]; then
        log "ERROR: source watch script missing: $src"
        return 1
    fi
    install -m 0755 "$src" "$PX_BIN_DIR/px_tick_watch.sh"
    log "wrote watchdog: $PX_BIN_DIR/px_tick_watch.sh (sourced from $src)"
}

status() {
    log "=== status ==="
    log "PX_HOME=$PX_HOME -> $(readlink -f "$PX_HOME" 2>/dev/null || echo MISSING)"
    log "supercronic: $("$PX_BIN_DIR/supercronic" -version 2>&1 | head -1)"
    local pid
    if [ -f "$PID_FILE" ] && pid="$(cat "$PID_FILE")" && kill -0 "$pid" 2>/dev/null \
        && [ -r "/proc/$pid/comm" ] && [ "$(cat "/proc/$pid/comm" 2>/dev/null)" = "supercronic" ]; then
        log "supercronic PID=$pid alive"
    else
        log "supercronic NOT running"
    fi
    if [ -e "$S6_DIR/run" ]; then
        log "s6 service exists at $S6_DIR"
    else
        log "s6 service not installed (root required; using Hermes cron fallback)"
    fi
    log "watch script: $PX_BIN_DIR/px_tick_watch.sh"
}

uninstall() {
    log "=== uninstall ==="
    if [ -f "$PID_FILE" ]; then
        local pid
        pid="$(cat "$PID_FILE")"
        kill "$pid" 2>/dev/null && log "killed supercronic $pid" || log "supercronic already gone"
        rm -f "$PID_FILE"
    fi
    if [ -e "$S6_DIR" ]; then
        if [ -w "/etc/s6-overlay/s6-rc.d" ]; then
            rm -rf "$S6_DIR"
            log "removed $S6_DIR"
        else
            log "skip $S6_DIR (no write access)"
        fi
    fi
    log "uninstall done (binary, crontab, watcher untouched; remove manually if desired)"
}

case "${1:-install}" in
    install)
        ensure_symlink || exit 1
        download_supercronic || exit 1
        validate_crontab || exit 2
        try_s6_install || true     # never fatal
        write_watch_script
        status
        ;;
    check)
        status
        ;;
    uninstall)
        uninstall
        ;;
    *)
        echo "usage: $0 [install|check|uninstall]" >&2
        exit 64
        ;;
esac
