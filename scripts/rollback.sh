#!/bin/bash
# =============================================================================
# LogKeep Production Rollback Script
# =============================================================================
# Rolls production back to a previous git ref and redeploys compose services.
#
# Usage: ./scripts/rollback.sh <git_ref>
# Example: ./scripts/rollback.sh v1.2.3
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

if [ $# -lt 1 ]; then
    log_error "Usage: $0 <git_ref>"
    exit 1
fi

ROLLBACK_REF="$1"

if [ ! -d .git ]; then
    log_error "Run this script from repository root"
    exit 1
fi

if [ ! -f "docker/docker-compose.prod.yml" ]; then
    log_error "Missing docker/docker-compose.prod.yml"
    exit 1
fi

if [ ! -f "docker/.env.production" ]; then
    log_error "Missing docker/.env.production"
    exit 1
fi

log_info "Fetching latest refs"
git fetch --prune origin

log_info "Checking out ${ROLLBACK_REF}"
git checkout -f "$ROLLBACK_REF"

log_info "Validating compose file"
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml config >/dev/null

log_info "Re-deploying production stack"
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml up --build -d --remove-orphans

log_info "Ensuring database schema exists"
init_ok=0
for _ in $(seq 1 20); do
    if docker exec logkeep python -m src.cli.admin init-db >/dev/null 2>&1; then
        init_ok=1
        break
    fi
    sleep 2
done

if [ "$init_ok" -ne 1 ]; then
    log_error "Database initialization failed after retries"
    docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml logs --tail=200 app
    exit 1
fi

log_info "Verifying health endpoint"
for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/health | grep -q '"status"'; then
        log_info "Rollback completed successfully"
        exit 0
    fi
    sleep 2
done

log_error "Rollback health check failed"
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml ps
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml logs --tail=200 app
exit 1
