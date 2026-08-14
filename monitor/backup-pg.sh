#!/usr/bin/env bash
# Daily PostgreSQL backup for Legislation Explorer (11.5GB DB).
set -euo pipefail

BACKUP_DIR="/home/harrison/backups/legislation-explorer"
CONTAINER="cadena-postgres"
DB_NAME="cadena_knowledge"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

BACKUP_FILE="${BACKUP_DIR}/pg_$(date +%F_%H%M%S).dump"

# Custom format (-Fc) with built-in compression — faster than
# SQL pipe through gzip and seekable for selective restore.
docker exec "$CONTAINER" pg_dump -U postgres -Fc --compress=9 "$DB_NAME" > "$BACKUP_FILE"

# Trim backups older than retention
find "$BACKUP_DIR" -name "pg_*.dump" -mtime +"$RETENTION_DAYS" -delete 2>/dev/null

echo "Backup: $(du -h "$BACKUP_FILE" | cut -f1) — $(ls "$BACKUP_DIR"/*.dump 2>/dev/null | wc -l) backups retained"