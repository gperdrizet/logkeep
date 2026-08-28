#!/bin/bash
# =============================================================================
# LogKeep Production Deploy Script
# =============================================================================
# Deploys the current checkout to production using docker-compose.prod.yml.
#
# Usage: ./scripts/deploy.sh
# =============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

if [ ! -f "docker/docker-compose.prod.yml" ]; then
    log_error "Run this script from repository root"
    exit 1
fi

if [ ! -f "docker/.env.production" ]; then
    log_error "Missing docker/.env.production"
    exit 1
fi

log_info "Validating compose file"
if ! docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml config >/dev/null; then
    log_error "docker/docker-compose.prod.yml failed validation"
    exit 1
fi

log_info "Removing stale fixed-name containers if present"
for name in logkeep-postgres logkeep-postgres-exporter logkeep; do
    if docker ps -a --format '{{.Names}}' | grep -Fxq "$name"; then
        docker rm -f "$name" >/dev/null 2>&1 || true
    fi
done

log_info "Starting production stack"
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

log_info "Waiting for health endpoint"
for _ in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8000/health | grep -q '"status"'; then
        log_info "Production deploy OK"
        exit 0
    fi
    sleep 2
done

log_error "Health check failed"
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml ps
docker compose --env-file docker/.env.production -f docker/docker-compose.prod.yml logs --tail=200 app
exit 1
