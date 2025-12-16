#!/bin/bash
###############################################################################
# LogKeep Database Restore Script
# Restores PostgreSQL database from compressed backup file
###############################################################################

set -e

# Configuration
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-logkeep-postgres}"
POSTGRES_USER="${POSTGRES_USER:-logkeep_admin}"
POSTGRES_DB="${POSTGRES_DB:-logkeep}"

# Check if backup file is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <backup_file.sql.gz> [target_database]"
    echo ""
    echo "Examples:"
    echo "  $0 /opt/logkeep/backups/logkeep_20251216_020000.sql.gz"
    echo "  $0 /opt/logkeep/backups/logkeep_20251216_020000.sql.gz logkeep_staging"
    echo ""
    echo "Available backups:"
    ls -lh /opt/logkeep/backups/logkeep_*.sql.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"
TARGET_DB="${2:-$POSTGRES_DB}"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "Starting database restore..."
log "Backup file: $BACKUP_FILE"
log "Target database: $TARGET_DB"

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    log "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Check if container is running
if ! docker ps | grep -q "$POSTGRES_CONTAINER"; then
    log "ERROR: PostgreSQL container '$POSTGRES_CONTAINER' is not running"
    exit 1
fi

# Warning for production database
if [ "$TARGET_DB" == "logkeep" ]; then
    echo ""
    echo "WARNING: You are about to restore to the PRODUCTION database!"
    echo "This will OVERWRITE all current data in '$TARGET_DB'"
    echo ""
    read -p "Are you sure you want to continue? (type 'yes' to proceed): " confirm
    if [ "$confirm" != "yes" ]; then
        log "Restore cancelled by user"
        exit 0
    fi
fi

# Create target database if it doesn't exist (for staging/testing)
if [ "$TARGET_DB" != "logkeep" ]; then
    log "Checking if target database exists..."
    DB_EXISTS=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -tAc "SELECT 1 FROM pg_database WHERE datname='$TARGET_DB'" 2>/dev/null || echo "")
    
    if [ -z "$DB_EXISTS" ]; then
        log "Creating database: $TARGET_DB"
        docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "CREATE DATABASE $TARGET_DB;" || {
            log "ERROR: Failed to create database"
            exit 1
        }
    fi
fi

# Terminate active connections to the target database
log "Terminating active connections to $TARGET_DB..."
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "
SELECT pg_terminate_backend(pg_stat_activity.pid)
FROM pg_stat_activity
WHERE pg_stat_activity.datname = '$TARGET_DB'
  AND pid <> pg_backend_pid();" 2>/dev/null || true

# Drop and recreate database to ensure clean restore
if [ "$TARGET_DB" != "logkeep" ]; then
    log "Dropping and recreating database for clean restore..."
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS $TARGET_DB;" && \
    docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -c "CREATE DATABASE $TARGET_DB;" || {
        log "ERROR: Failed to recreate database"
        exit 1
    }
fi

# Restore from backup
log "Restoring database from backup (this may take a few minutes)..."
if gunzip -c "$BACKUP_FILE" | docker exec -i "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$TARGET_DB" > /dev/null 2>&1; then
    log "Database restored successfully"
else
    log "ERROR: Database restore failed"
    exit 1
fi

# Verify restore by checking table counts
log "Verifying restore..."
USER_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT COUNT(*) FROM users;" 2>/dev/null || echo "0")
LINK_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT COUNT(*) FROM links;" 2>/dev/null || echo "0")
TAG_COUNT=$(docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT COUNT(*) FROM tags;" 2>/dev/null || echo "0")

log "Restore verification:"
log "  - Users: $USER_COUNT"
log "  - Links: $LINK_COUNT"
log "  - Tags: $TAG_COUNT"

if [ "$USER_COUNT" -eq 0 ] && [ "$LINK_COUNT" -eq 0 ]; then
    log "WARNING: Restored database appears to be empty"
fi

# Run VACUUM ANALYZE to optimize after restore
log "Running VACUUM ANALYZE..."
docker exec "$POSTGRES_CONTAINER" psql -U "$POSTGRES_USER" -d "$TARGET_DB" -c "VACUUM ANALYZE;" 2>/dev/null || true

log "Restore process completed successfully"

# Additional recommendations
if [ "$TARGET_DB" == "logkeep" ]; then
    echo ""
    echo "IMPORTANT: After restoring production database, you should:"
    echo "  1. Restart application containers:"
    echo "     docker-compose -f docker-compose.prod.yml restart app-blue app-green"
    echo "  2. Verify application health:"
    echo "     curl https://logkeep.perdrizet.org/health"
    echo "  3. Check application logs:"
    echo "     docker-compose -f docker-compose.prod.yml logs -f app-blue"
fi

exit 0
