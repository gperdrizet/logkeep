#!/bin/bash
# =============================================================================
# LogKeep Rollback Script
# =============================================================================
# Quickly rollback to the previous deployment by switching traffic back
#
# Usage: ./rollback.sh
# =============================================================================

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
NGINX_CONF="/etc/nginx/conf.d/logkeep.conf"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

get_active_slot() {
    # Check which container Nginx is pointing to
    if grep -q "server logkeep-blue:8000" "$NGINX_CONF"; then
        echo "blue"
    elif grep -q "server logkeep-green:8000" "$NGINX_CONF"; then
        echo "green"
    else
        echo "unknown"
    fi
}

get_inactive_slot() {
    local active=$(get_active_slot)
    if [ "$active" = "blue" ]; then
        echo "green"
    elif [ "$active" = "green" ]; then
        echo "blue"
    else
        echo "unknown"
    fi
}

check_container_exists() {
    local container=$1
    docker ps -a --filter "name=$container" --format "{{.Names}}" | grep -q "$container"
}

start_container_if_stopped() {
    local container=$1
    
    if ! docker ps --filter "name=$container" --filter "status=running" --format "{{.Names}}" | grep -q "$container"; then
        log_info "Starting $container..."
        docker start "$container"
        sleep 5
    fi
}

switch_nginx_upstream() {
    local new_slot=$1
    local new_container="logkeep-${new_slot}"
    
    log_info "Switching Nginx upstream to $new_slot..."
    
    sudo sed -i "s/server logkeep-[a-z]*:8000;/server ${new_container}:8000;/" "$NGINX_CONF"
    
    if ! sudo nginx -t; then
        log_error "Nginx configuration test failed!"
        return 1
    fi
    
    sudo nginx -s reload
    log_info "Nginx reloaded successfully"
}

main() {
    log_warn "=========================================="
    log_warn "LogKeep Rollback"
    log_warn "=========================================="
    
    local current_slot=$(get_active_slot)
    local previous_slot=$(get_inactive_slot)
    
    log_info "Current active slot: $current_slot"
    log_info "Rolling back to: $previous_slot"
    
    if [ "$previous_slot" = "unknown" ]; then
        log_error "Cannot determine previous slot"
        exit 1
    fi
    
    local previous_container="logkeep-${previous_slot}"
    
    # Check if previous container exists
    if ! check_container_exists "$previous_container"; then
        log_error "Previous container $previous_container not found"
        log_error "Cannot rollback - container may have been removed"
        exit 1
    fi
    
    # Start previous container if stopped
    start_container_if_stopped "$previous_container"
    
    # Wait for health check
    log_info "Waiting for $previous_container to be ready..."
    for i in {1..10}; do
        if docker exec "$previous_container" curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_info "$previous_container is healthy!"
            break
        fi
        if [ $i -eq 10 ]; then
            log_error "$previous_container health check failed"
            exit 1
        fi
        sleep 3
    done
    
    # Switch traffic
    switch_nginx_upstream "$previous_slot"
    
    log_warn "=========================================="
    log_warn "Rollback completed!"
    log_warn "=========================================="
    log_info "Traffic switched from $current_slot to $previous_slot"
    log_info "Monitor the application and stop the problematic container if needed"
}

main
