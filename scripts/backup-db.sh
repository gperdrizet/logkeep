#!/bin/bash
###############################################################################
# LogKeep Database Backup Script
# Backs up PostgreSQL database with compression and retention management
###############################################################################

set -e

# Configuration
APP_DIR="${APP_DIR:-/opt/logkeep}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-logkeep-postgres}"
POSTGRES_USER="${POSTGRES_USER:-logkeep_admin}"
POSTGRES_DB="${POSTGRES_DB:-logkeep}"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate backup filename with timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/logkeep_${TIMESTAMP}.sql.gz"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting database backup..."

# Check if container is running
if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
    log "ERROR: PostgreSQL container '$POSTGRES_CONTAINER' is not running"
    exit 1
fi

# Perform backup using pg_dump with compression
if docker exec "$POSTGRES_CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_FILE"; then
    BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    log "Backup completed successfully: $BACKUP_FILE ($BACKUP_SIZE)"
else
    log "ERROR: Backup failed"
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Verify backup file exists and is not empty
if [ ! -s "$BACKUP_FILE" ]; then
    log "ERROR: Backup file is empty or missing"
    exit 1
fi

# Remove old backups beyond retention period
log "Cleaning up old backups (retention: $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "logkeep_*.sql.gz" -type f -mtime +$RETENTION_DAYS -delete

REMAINING_BACKUPS=$(find "$BACKUP_DIR" -name "logkeep_*.sql.gz" -type f | wc -l)
log "Cleanup complete. Current backup count: $REMAINING_BACKUPS"

# Optional: sync to remote location (uncomment and configure as needed)
# REMOTE_BACKUP_DIR="/mnt/arkk/logkeep/backups"
# if [ -d "$REMOTE_BACKUP_DIR" ]; then
#     log "Syncing backup to remote location..."
#     rsync -az "$BACKUP_FILE" "$REMOTE_BACKUP_DIR/" && \
#         log "Remote sync completed" || \
#         log "WARNING: Remote sync failed"
# fi

log "Backup process completed"

exit 0
