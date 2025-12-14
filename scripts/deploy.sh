#!/bin/bash
# =============================================================================
# LogKeep Blue/Green Deployment Script
# =============================================================================
# This script performs a zero-downtime deployment using blue/green strategy.
#
# Usage: ./deploy.sh [image_tag]
#   image_tag: Docker image tag to deploy (default: latest)
#
# Example: ./deploy.sh v1.2.3
# =============================================================================

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
IMAGE_TAG="${1:-latest}"
IMAGE_NAME="gperdrizet/logkeep:${IMAGE_TAG}"
NGINX_CONF="/etc/nginx/conf.d/logkeep.conf"
HEALTH_CHECK_RETRIES=10
HEALTH_CHECK_INTERVAL=5
OBSERVATION_PERIOD=300  # 5 minutes in seconds

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

check_container_running() {
    local container=$1
    docker ps --filter "name=$container" --filter "status=running" --format "{{.Names}}" | grep -q "$container"
}

get_active_slot() {
    if check_container_running "logkeep-blue"; then
        echo "blue"
    elif check_container_running "logkeep-green"; then
        echo "green"
    else
        echo "none"
    fi
}

get_inactive_slot() {
    local active=$(get_active_slot)
    if [ "$active" = "blue" ]; then
        echo "green"
    else
        echo "blue"
    fi
}

get_container_port() {
    local slot=$1
    if [ "$slot" = "blue" ]; then
        echo "8001"
    else
        echo "8002"
    fi
}

wait_for_health() {
    local container=$1
    local retries=$HEALTH_CHECK_RETRIES
    
    log_info "Waiting for $container to become healthy..."
    
    for i in $(seq 1 $retries); do
        if docker exec "$container" curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_info "$container is healthy!"
            return 0
        fi
        log_info "Health check attempt $i/$retries..."
        sleep $HEALTH_CHECK_INTERVAL
    done
    
    log_error "$container failed health checks"
    return 1
}

switch_nginx_upstream() {
    local new_slot=$1
    local new_container="logkeep-${new_slot}"
    
    log_step "Switching Nginx upstream to $new_slot..."
    
    # Update Nginx config to point to new container
    sudo sed -i "s/server logkeep-[a-z]*:8000;/server ${new_container}:8000;/" "$NGINX_CONF"
    
    # Test configuration
    if ! sudo nginx -t; then
        log_error "Nginx configuration test failed!"
        return 1
    fi
    
    # Reload Nginx
    sudo nginx -s reload
    log_info "Nginx reloaded successfully"
}

send_notification() {
    local message=$1
    local status=$2  # success or failure
    
    # You can add email notification here
    log_info "Notification: $message"
    
    # Example email command (uncomment if configured):
    # echo "$message" | mail -s "LogKeep Deployment $status" george@perdrizet.org
}

# =============================================================================
# Deployment Steps
# =============================================================================

preflight_checks() {
    log_step "Running preflight checks..."
    
    # Check if running in correct directory
    if [ ! -f "docker-compose.prod.yml" ]; then
        log_error "Must be run from repository root directory"
        exit 1
    fi
    
    # Check if .env.production exists
    if [ ! -f ".env.production" ]; then
        log_error ".env.production not found"
        exit 1
    fi
    
    # Check Docker
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi
    
    # Check Nginx
    if ! sudo nginx -v > /dev/null 2>&1; then
        log_error "Nginx is not installed"
        exit 1
    fi
    
    log_info "Preflight checks passed"
}

pull_new_image() {
    log_step "Pulling new Docker image: $IMAGE_NAME..."
    
    if ! docker pull "$IMAGE_NAME"; then
        log_error "Failed to pull Docker image"
        exit 1
    fi
    
    log_info "Image pulled successfully"
}

deploy_to_inactive_slot() {
    local active_slot=$(get_active_slot)
    local new_slot=$(get_inactive_slot)
    local new_container="logkeep-${new_slot}"
    
    log_step "Current active slot: $active_slot"
    log_step "Deploying to slot: $new_slot"
    
    # Stop the inactive container if it's running
    if docker ps -a --filter "name=$new_container" --format "{{.Names}}" | grep -q "$new_container"; then
        log_info "Stopping existing $new_container container..."
        docker stop "$new_container" || true
        docker rm "$new_container" || true
    fi
    
    # Start new container
    log_info "Starting $new_container with new image..."
    
    if [ "$new_slot" = "green" ]; then
        docker-compose -f docker-compose.prod.yml up -d app-green
    else
        docker-compose -f docker-compose.prod.yml up -d app-blue
    fi
    
    # Wait for container to be healthy
    if ! wait_for_health "$new_container"; then
        log_error "New deployment failed health checks"
        log_info "Cleaning up failed deployment..."
        docker stop "$new_container" || true
        exit 1
    fi
    
    echo "$new_slot"
}

switch_traffic() {
    local new_slot=$1
    local old_slot=$(get_active_slot)
    
    log_step "Switching traffic from $old_slot to $new_slot..."
    
    if ! switch_nginx_upstream "$new_slot"; then
        log_error "Failed to switch Nginx upstream"
        return 1
    fi
    
    log_info "Traffic successfully switched to $new_slot"
}

observe_new_deployment() {
    local new_slot=$1
    local new_container="logkeep-${new_slot}"
    
    log_step "Observing new deployment for $OBSERVATION_PERIOD seconds..."
    log_info "Monitoring $new_container for errors..."
    
    # Monitor for errors during observation period
    local start_time=$(date +%s)
    local end_time=$((start_time + OBSERVATION_PERIOD))
    
    while [ $(date +%s) -lt $end_time ]; do
        # Check if container is still running
        if ! check_container_running "$new_container"; then
            log_error "$new_container stopped unexpectedly!"
            return 1
        fi
        
        # Check health endpoint
        if ! docker exec "$new_container" curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_error "$new_container health check failed!"
            return 1
        fi
        
        # Show countdown
        local remaining=$((end_time - $(date +%s)))
        echo -ne "\rTime remaining: ${remaining}s "
        sleep 10
    done
    
    echo ""  # New line after countdown
    log_info "Observation period completed successfully"
}

cleanup_old_deployment() {
    local old_slot=$1
    local old_container="logkeep-${old_slot}"
    
    log_step "Cleaning up old deployment ($old_slot)..."
    
    if check_container_running "$old_container"; then
        docker stop "$old_container"
        log_info "Stopped $old_container"
    fi
    
    # Don't remove the container, just stop it for potential rollback
    log_info "Old container stopped but preserved for rollback"
}

# =============================================================================
# Main Deployment Flow
# =============================================================================

main() {
    log_info "=========================================="
    log_info "LogKeep Blue/Green Deployment"
    log_info "=========================================="
    log_info "Image: $IMAGE_NAME"
    log_info "Starting at: $(date)"
    echo ""
    
    # Record start time
    local start_time=$(date +%s)
    
    # Run deployment steps
    preflight_checks
    
    local old_slot=$(get_active_slot)
    if [ "$old_slot" = "none" ]; then
        log_error "No active deployment found. Use docker-compose up instead."
        exit 1
    fi
    
    pull_new_image
    
    local new_slot=$(deploy_to_inactive_slot)
    
    switch_traffic "$new_slot"
    
    observe_new_deployment "$new_slot"
    
    cleanup_old_deployment "$old_slot"
    
    # Calculate deployment time
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    log_info "=========================================="
    log_info "Deployment completed successfully!"
    log_info "=========================================="
    log_info "Old slot: $old_slot"
    log_info "New slot: $new_slot"
    log_info "Duration: ${duration}s"
    log_info "Completed at: $(date)"
    
    send_notification "Deployment completed successfully (${duration}s)" "success"
}

# Error handler
trap 'log_error "Deployment failed at line $LINENO"; send_notification "Deployment failed" "failure"; exit 1' ERR

# Run main
main
