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
HEALTH_CHECK_RETRIES=15
HEALTH_CHECK_INTERVAL=10
OBSERVATION_PERIOD="${OBSERVATION_PERIOD:-300}"  # Default: 5 minutes, can be overridden with env var

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1" >&2
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
    
    # Get the port from container name (blue=8001, green=8002)
    local port
    if [[ "$container" == *"blue"* ]]; then
        port="8001"
    else
        port="8002"
    fi
    
    log_info "Waiting for $container to become healthy (timeout: ${retries}x${HEALTH_CHECK_INTERVAL}s = $((retries * HEALTH_CHECK_INTERVAL))s)..."
    
    for i in $(seq 1 $retries); do
        if curl -f http://127.0.0.1:${port}/health > /dev/null 2>&1; then
            log_info "$container is healthy! (took $((i * HEALTH_CHECK_INTERVAL))s)"
            return 0
        fi
        echo -n "." >&2  # Progress indicator
        sleep $HEALTH_CHECK_INTERVAL
    done
    
    echo "" >&2  # New line after dots
    log_error "$container failed health checks after $((retries * HEALTH_CHECK_INTERVAL))s"
    return 1
}

switch_nginx_via_symlink() {
    local new_slot="$1"
    local old_slot="$2"
    local nginx_configs_dir="/etc/nginx/logkeep-configs"
    local nginx_conf_dir="/etc/nginx/conf.d"
    local symlink_path="${nginx_conf_dir}/logkeep.conf"
    local new_config="${nginx_configs_dir}/${new_slot}.conf"
    
    log_step "Switching nginx to ${new_slot} via symlink..."
    log_info "Target: ${new_config}"
    
    # Update symlink on system to point to new config
    sudo ln -sf "$new_config" "$symlink_path"
    
    # Force filesystem sync
    sync
    sleep 0.5
    
    # Verify symlink was created correctly
    local current_link=$(sudo readlink "$symlink_path")
    if [ "$current_link" != "$new_config" ]; then
        log_error "Failed to create symlink (points to: $current_link, expected: $new_config)"
        return 1
    fi
    log_info "Symlink verified: $(sudo ls -l $symlink_path)"
    
    # Test nginx configuration
    if ! sudo nginx -t 2>&1 | tee /tmp/nginx-test.log | grep -q "test is successful"; then
        log_error "Nginx configuration test failed!"
        cat /tmp/nginx-test.log
        # Attempt to rollback
        sudo ln -sf "${nginx_configs_dir}/${old_slot}.conf" "$symlink_path"
        return 1
    fi
    
    # Reload nginx to pick up new config
    sudo systemctl reload nginx
    
    log_info "Traffic successfully switched to $new_slot"
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
    if [ ! -f "docker/docker-compose.prod.yml" ]; then
        log_error "Must be run from repository root directory"
        exit 1
    fi
    
    # Check if .env.production exists
    if [ ! -f "docker/.env.production" ]; then
        log_error "docker/.env.production not found"
        exit 1
    fi
    
    # Check Docker
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running"
        exit 1
    fi
    
    # Check system nginx
    if ! sudo systemctl is-active --quiet nginx; then
        log_error "System nginx is not running"
        exit 1
    fi
    
    # Verify nginx config files exist in logkeep-configs directory
    if [ ! -f "/etc/nginx/logkeep-configs/blue.conf" ] || [ ! -f "/etc/nginx/logkeep-configs/green.conf" ]; then
        log_error "Nginx blue/green config files not found in /etc/nginx/logkeep-configs/"
        exit 1
    fi
    
    log_info "Preflight checks passed"
}

pull_new_image() {
    log_step "Pulling new Docker image: $IMAGE_NAME..."
    
    if ! docker pull "$IMAGE_NAME" >&2; then
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
    
    # Check if green container exists - if not, do in-place update of blue
    if [ "$new_slot" = "green" ] && ! docker ps -a --filter "name=logkeep-green" --format "{{.Names}}" | grep -q "logkeep-green"; then
        log_warn "Green container doesn't exist yet. Performing in-place update of blue container."
        new_slot="blue"
        new_container="logkeep-blue"
    fi
    
    log_step "Deploying to slot: $new_slot"
    
    # For in-place update, just restart with new image
    if [ "$new_slot" = "$active_slot" ]; then
        log_info "Performing in-place update of $new_container..."
        docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d --no-deps app-blue >&2
    else
        # Stop the inactive container if it's running
        if docker ps -a --filter "name=$new_container" --format "{{.Names}}" | grep -q "$new_container"; then
            log_info "Stopping existing $new_container container..."
            docker stop "$new_container" >&2 || true
            docker rm "$new_container" >&2 || true
        fi
        
        # Start new container
        log_info "Starting $new_container with new image..."
        
        if [ "$new_slot" = "green" ]; then
            docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d app-green >&2
        else
            docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d app-blue >&2
        fi
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
    local old_slot=$2
    
    log_step "Switching traffic from $old_slot to $new_slot..."
    
    if ! switch_nginx_via_symlink "$new_slot" "$old_slot"; then
        log_error "Failed to switch traffic"
        return 1
    fi
    
    log_info "Traffic successfully switched to $new_slot"
}

observe_new_deployment() {
    local new_slot=$1
    local new_container="logkeep-${new_slot}"
    
    # Get the port from slot name (blue=8001, green=8002)
    local port
    if [[ "$new_slot" == "blue" ]]; then
        port="8001"
    else
        port="8002"
    fi
    
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
        if ! curl -f http://127.0.0.1:${port}/health > /dev/null 2>&1; then
            log_error "$new_container health check failed!"
            return 1
        fi
        
        # Show countdown
        local remaining=$((end_time - $(date +%s)))
        echo -ne "\rTime remaining: ${remaining}s " >&2
        sleep 10
    done
    
    echo "" >&2  # New line after countdown
    log_info "Observation period completed successfully"
}

cleanup_old_deployment() {
    local old_slot=$1
    local old_container="logkeep-${old_slot}"
    
    log_step "Cleaning up old deployment ($old_slot)..."
    
    if check_container_running "$old_container"; then
        docker stop "$old_container" >&2
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
        log_warn "No active deployment found. Bootstrapping initial deployment..."
        pull_new_image
        
        # Clean up any stopped containers first
        log_step "Cleaning up any existing stopped containers..."
        docker-compose --project-directory . -f docker/docker-compose.prod.yml down --remove-orphans
        
        # Start blue container as initial deployment
        log_step "Starting initial blue container..."
        docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d app-blue postgres prometheus grafana loki alertmanager promtail
        
        if ! wait_for_health "logkeep-blue"; then
            log_error "Initial deployment failed health checks"
            exit 1
        fi
        
        log_info "Initial blue deployment successful!"
        
        # Setup nginx symlink to blue
        local nginx_configs_dir="/etc/nginx/logkeep-configs"
        local nginx_conf_dir="/etc/nginx/conf.d"
        local symlink_path="${nginx_conf_dir}/logkeep.conf"
        local blue_config="${nginx_configs_dir}/blue.conf"
        
        log_step "Setting up nginx to point to blue..."
        sudo ln -sf "$blue_config" "$symlink_path"
        sudo nginx -t && sudo systemctl reload nginx
        
        log_info "=========================================="
        log_info "Initial deployment completed successfully!"
        log_info "Active slot: blue"
        log_info "=========================================="
        exit 0
    fi
    
    pull_new_image
    
    local new_slot=$(deploy_to_inactive_slot)
    
    switch_traffic "$new_slot" "$old_slot"
    
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
