#!/usr/bin/env bash
# Health monitor for Legislation Explorer — zero LLM tokens.
# Runs every 5 minutes via systemd timer.
# - Git auto-deploy: fetch + fast-forward pull, rebuild frontend, restart
# - Health check: DB, Postgres, memory
# - Auto-rebuild search index on consecutive search_db failures

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="/home/harrison/legislation-explorer"
SERVICE="legislation-explorer.service"
BOT_TOKEN="8069497916:AAFp84IPt8KUWffsUkwiA3mLxNAdbfvSCV0"
CHAT_ID="1890434867"
LOG_FILE="${SCRIPT_DIR}/healthcheck.log"
FAIL_COUNTER="${SCRIPT_DIR}/.search_db_fails"
SEARCH_DB="${PROJECT_DIR}/search_index.db"
MAX_LOG_LINES=500

# ---- Helpers ----

send_alert() {
    local message="$1"
    curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
        -d "chat_id=${CHAT_ID}" \
        -d "text=${message}" \
        -d "parse_mode=Markdown" > /dev/null 2>&1
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
    local lines
    lines=$(wc -l < "$LOG_FILE")
    if [ "$lines" -gt "$MAX_LOG_LINES" ]; then
        tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
}

restart_with_alert() {
    local reason="$1"
    send_alert "⚠️ *Legislation Explorer* — ${reason} → restarting..."
    systemctl --user restart "$SERVICE" 2>/dev/null || true
    sleep 4
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost:8765/health 2>/dev/null || echo "000")
    log "After restart: health HTTP ${status}"
    send_alert "✅ *Legislation Explorer* — restart complete, health HTTP ${status}"
}

# ---- Step 1: Git auto-deploy ----

cd "$PROJECT_DIR"
git fetch origin 2>/dev/null || log "git fetch failed"

CURRENT=$(git rev-parse HEAD 2>/dev/null || echo "")
REMOTE=$(git rev-parse origin/master 2>/dev/null || echo "")
if [ -n "$REMOTE" ] && [ "$CURRENT" != "$REMOTE" ]; then
    log "New commits: ${CURRENT:0:8} → ${REMOTE:0:8}"
    send_alert "🔄 *Legislation Explorer* — deploying update (${REMOTE:0:8})..."
    git pull --ff-only origin master 2>/dev/null && log "git pull ok" || log "git pull FAILED"
    # Rebuild frontend
    if [ -f frontend/package.json ]; then
        cd frontend && npm run build 2>&1 | tail -3 >> "$LOG_FILE"
        cd "$PROJECT_DIR"
    fi
    restart_with_alert "new code deployed (${REMOTE:0:8})"
    exit 0
fi

# ---- Step 2: Health check ----

HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://localhost:8765/health/check 2>/dev/null || echo "000")
if [ "$HEALTH" != "200" ]; then
    log "FAIL: health/check returned HTTP ${HEALTH}"
    restart_with_alert "health check HTTP ${HEALTH}"
    exit 1
fi

RESPONSE=$(curl -s --max-time 10 http://localhost:8765/health/check 2>/dev/null)
STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse-fail")

if [ "$STATUS" = "ok" ]; then
    # Reset fail counter on success
    rm -f "$FAIL_COUNTER"
    log "PASS: all checks ok"
    exit 0
fi

# ---- Step 3: Handle degraded state ----

FAILURES=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
fails = [k for k,v in data.get('checks',{}).items() if v.get('status') != 'pass']
if fails:
    print(', '.join(fails))
" 2>/dev/null || echo "unknown")

log "DEGRADED: ${FAILURES:-unknown}"

# Search DB failure — track consecutive fails and nuke+recover
if echo "$FAILURES" | grep -q "search_db"; then
    COUNT=0
    if [ -f "$FAIL_COUNTER" ]; then
        COUNT=$(cat "$FAIL_COUNTER" 2>/dev/null || echo 0)
    fi
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "$FAIL_COUNTER"
    log "search_db fail #${COUNT}"

    if [ "$COUNT" -ge 3 ]; then
        log "REBUILDING search index (fail #${COUNT})"
        send_alert "🔧 *Legislation Explorer* — search index corrupted, rebuilding..."
        rm -f "$SEARCH_DB"
        rm -f "$FAIL_COUNTER"
        restart_with_alert "search index rebuilt"
    else
        restart_with_alert "search_db failure #${COUNT}"
    fi
    exit 1
fi

# Postgres failure — restart immediately
if echo "$FAILURES" | grep -q "postgres"; then
    restart_with_alert "Postgres connection failure"
    exit 1
fi

# Soft failures (memory warnings etc.) — log only, no restart
log "Soft failure (${FAILURES}) — no restart"
