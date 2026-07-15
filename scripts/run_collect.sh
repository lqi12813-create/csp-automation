#!/bin/bash
# CSP daily data collection → Feishu Base
# Invoked by launchd at 07:30 daily
#
# Pre-flight: check SSH tunnel + ZClaw alive
# On failure: notify via Feishu (lark-cli)
# On success: silent (Hermes reports at 08:00)

set -e

export HOME=/Users/fred2
source "$HOME/csp-automation/scripts/.env"
export no_proxy="127.0.0.1,localhost"

LOG_DIR="$HOME/csp-automation/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/collect-$(date +%Y-%m-%d).log"
exec >> "$LOG_FILE" 2>&1

CHAT_ID="oc_4a5f4cda0599518b492939f71e4d3b96"
ERRORS=()

notify() {
    local level="$1" msg="$2"
    echo "[$level] $msg"
    lark-cli im +messages-send --chat-id "$CHAT_ID" --markdown "⚠️ **CSP采集 $level**\n$msg\n时间: $(date '+%Y-%m-%d %H:%M:%S')" 2>/dev/null || true
}

echo "=== $(date) ==="
echo "Pre-flight checks..."

# 1. Check SSH tunnel (ZClaw port)
if ! nc -z -w 3 localhost 9481 2>/dev/null; then
    notify "隧道异常" "ZClaw 隧道 (localhost:9481) 不通，N100 可能离线或 SSH 断开。"
    exit 1
fi
echo "  ✅ SSH tunnel OK"

# 2. Check ZClaw Bridge is alive
ZCLAW_RESP=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST http://localhost:9481/zclaw/tools/invoke \
    -H "Content-Type: application/json" \
    -H "X-ZClaw-Api-Key: ${ZCLAW_API_KEY}" \
    -d '{"tool":"list_stores","args":{}}' \
    --max-time 10 2>/dev/null || echo "000")

if [ "$ZCLAW_RESP" != "200" ]; then
    notify "ZClaw异常" "ZClaw Bridge 无响应 (HTTP $ZCLAW_RESP)，可能需要重启紫鸟。"
    exit 1
fi
echo "  ✅ ZClaw Bridge alive"

# 3. Run collection
echo "Running CSP collection..."
COLLECT_EXIT=0
/usr/bin/python3 "$HOME/csp-automation/scripts/csp_daily_collect.py" "$@" || COLLECT_EXIT=$?

if [ $COLLECT_EXIT -ne 0 ]; then
    # Extract last few lines of log for context
    TAIL=$(tail -5 "$LOG_FILE" | sed 's/"/\\"/g')
    notify "采集失败" "退出码: $COLLECT_EXIT\n日志:\n\`\`\`\n$TAIL\n\`\`\`"
    exit $COLLECT_EXIT
fi

echo "Done: $(date)"
