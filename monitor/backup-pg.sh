#!/usr/bin/env bash
# Monthly PostgreSQL backup for Legislation Explorer — the corpus only
# changes on the monthly update (1st), so a daily dump is N copies of the
# same data. Runs after monthly_update.sh; 4 dumps kept as rolling history.
set -euo pipefail

BACKUP_DIR="/home/harrison/backups/legislation-explorer"
CONTAINER="cadena-postgres"
DB_NAME="cadena_knowledge"

mkdir -p "$BACKUP_DIR"

BACKUP_FILE="${BACKUP_DIR}/pg_$(date +%F_%H%M%S).dump"

# Custom format (-Fc) with built-in compression — faster than
# SQL pipe through gzip and seekable for selective restore.
docker exec "$CONTAINER" pg_dump -U postgres -Fc --compress=9 "$DB_NAME" > "$BACKUP_FILE"

# Trim to the 4 most recent (one per version-bump since the dump is monthly)
ls -1t "$BACKUP_DIR"/pg_*.dump 2>/dev/null | tail -n +5 | xargs -r rm -- 2>/dev/null

echo "Backup: $(du -h "$BACKUP_FILE" | cut -f1) — $(ls "$BACKUP_DIR"/*.dump 2>/dev/null | wc -l) backups retained"