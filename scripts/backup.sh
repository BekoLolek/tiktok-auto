#!/bin/bash
# PostgreSQL Backup Script for TikTok Auto
# Run via cron or docker exec

set -e

# Configuration
BACKUP_PATH="${BACKUP_PATH:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_PATH}/tiktok_auto_${TIMESTAMP}.sql.gz"

# Database configuration
DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_USER="${POSTGRES_USER:-tiktok_auto}"
DB_NAME="${POSTGRES_DB:-tiktok_auto}"

echo "[$(date)] Starting backup..."

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_PATH}"

# Create compressed backup
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --format=plain \
    --no-owner \
    --no-acl \
    | gzip > "${BACKUP_FILE}"

# Get backup size
BACKUP_SIZE=$(ls -lh "${BACKUP_FILE}" | awk '{print $5}')
echo "[$(date)] Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Cleanup old backups
echo "[$(date)] Cleaning up backups older than ${RETENTION_DAYS} days..."
find "${BACKUP_PATH}" -name "tiktok_auto_*.sql.gz" -mtime +${RETENTION_DAYS} -delete

# Count remaining backups
BACKUP_COUNT=$(ls -1 "${BACKUP_PATH}"/tiktok_auto_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Backup complete. Total backups: ${BACKUP_COUNT}"

# Verify backup
if gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    echo "[$(date)] Backup verification: OK"
else
    echo "[$(date)] ERROR: Backup verification failed!"
    exit 1
fi
