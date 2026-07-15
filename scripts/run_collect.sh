#!/bin/bash
# CSP daily data collection → Feishu Base
# Invoked by launchd at 07:30 daily

set -e

# Source credentials
export HOME=/Users/fred2
source "$HOME/csp-automation/scripts/.env"

# ZClaw is on localhost tunnel — bypass proxy
export no_proxy="127.0.0.1,localhost"

LOG_DIR="$HOME/csp-automation/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/collect-$(date +%Y-%m-%d).log"

exec >> "$LOG_FILE" 2>&1

echo "=== $(date) ==="
echo "Starting CSP daily collect..."

/usr/bin/python3 "$HOME/csp-automation/scripts/csp_daily_collect.py" "$@"

echo "Done: $(date)"
