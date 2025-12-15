#!/bin/bash
# =============================================================================
# SSH Tunnel Setup for Ollama (Local Machine)
# =============================================================================
# This script sets up a persistent reverse SSH tunnel from local machine to VPS
# for Ollama access. Run this on your LOCAL MACHINE.
#
# Usage: sudo bash setup-ssh-tunnel.sh
# =============================================================================

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# Configuration
LOCAL_PORT=11434  # Ollama default port
REMOTE_PORT=11434
REMOTE_HOST="gatekeeper"  # Your SSH alias for VPS
LOCAL_USER="$SUDO_USER"  # User who ran sudo
SERVICE_NAME="logkeep-tunnel"

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_ssh_access() {
    log_info "Checking SSH access to VPS..."
    
    if ! sudo -u "$LOCAL_USER" ssh -o ConnectTimeout=5 "$REMOTE_HOST" "echo 'SSH connection successful'" > /dev/null 2>&1; then
        log_error "Cannot connect to $REMOTE_HOST"
        log_error "Make sure you can run: ssh $REMOTE_HOST"
        exit 1
    fi
    
    log_info "SSH access confirmed"
}

check_ollama() {
    log_info "Checking if Ollama is running..."
    
    if ! curl -s http://localhost:$LOCAL_PORT/api/tags > /dev/null 2>&1; then
        log_error "Ollama is not running on localhost:$LOCAL_PORT"
        log_error "Start Ollama first: docker-compose up -d ollama"
        exit 1
    fi
    
    log_info "Ollama is running"
}

install_autossh() {
    log_info "Checking for autossh..."
    
    if ! command -v autossh &> /dev/null; then
        log_info "Installing autossh..."
        apt-get update
        apt-get install -y autossh
    else
        log_info "autossh is already installed"
    fi
}

create_systemd_service() {
    log_info "Creating systemd service..."
    
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=SSH Tunnel for Ollama (LogKeep)
After=network.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${LOCAL_USER}
Restart=always
RestartSec=10
StartLimitInterval=200
StartLimitBurst=10

# SSH tunnel command
# -M 0 = disable autossh monitoring port (use ServerAliveInterval instead)
# -N = no remote command
# -T = disable pseudo-tty allocation
# -R = reverse tunnel
# -o ServerAliveInterval=30 = send keepalive every 30 seconds
# -o ServerAliveCountMax=3 = disconnect after 3 failed keepalives
# -o ExitOnForwardFailure=yes = exit if tunnel fails to establish
ExecStart=/usr/bin/autossh -M 0 -N -T \\
    -o "ServerAliveInterval=30" \\
    -o "ServerAliveCountMax=3" \\
    -o "ExitOnForwardFailure=yes" \\
    -o "StrictHostKeyChecking=no" \\
    -R ${REMOTE_PORT}:localhost:${LOCAL_PORT} \\
    ${REMOTE_HOST}

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
WantedBy=multi-user.target
EOF

    log_info "Systemd service created"
}

enable_and_start_service() {
    log_info "Enabling and starting service..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable service to start on boot
    systemctl enable ${SERVICE_NAME}.service
    
    # Start service
    systemctl start ${SERVICE_NAME}.service
    
    # Wait a moment for tunnel to establish
    sleep 3
    
    # Check status
    if systemctl is-active --quiet ${SERVICE_NAME}.service; then
        log_info "Service started successfully"
    else
        log_error "Service failed to start"
        systemctl status ${SERVICE_NAME}.service
        exit 1
    fi
}

test_tunnel() {
    log_info "Testing tunnel..."
    
    # Give tunnel time to establish
    sleep 5
    
    # Test from VPS side
    log_info "Testing Ollama access from VPS..."
    if sudo -u "$LOCAL_USER" ssh "$REMOTE_HOST" "curl -s http://localhost:$REMOTE_PORT/api/tags" > /dev/null 2>&1; then
        log_info "Tunnel is working! Ollama is accessible from VPS"
    else
        log_warn "Could not verify tunnel from VPS"
        log_warn "This might be normal if the VPS firewall is strict"
        log_info "Check manually by running on VPS: curl http://localhost:$REMOTE_PORT/api/tags"
    fi
}

display_instructions() {
    log_info "=========================================="
    log_info "SSH Tunnel Setup Complete!"
    log_info "=========================================="
    echo ""
    echo "Service name: ${SERVICE_NAME}"
    echo ""
    echo "Useful commands:"
    echo "  Status:  sudo systemctl status ${SERVICE_NAME}"
    echo "  Logs:    sudo journalctl -u ${SERVICE_NAME} -f"
    echo "  Restart: sudo systemctl restart ${SERVICE_NAME}"
    echo "  Stop:    sudo systemctl stop ${SERVICE_NAME}"
    echo ""
    echo "The tunnel will automatically:"
    echo "  - Start on system boot"
    echo "  - Reconnect if connection drops"
    echo "  - Monitor connection health"
    echo ""
    echo "On VPS, Ollama is now available at: http://localhost:${REMOTE_PORT}"
}

main() {
    log_info "Setting up SSH tunnel for Ollama..."
    
    check_root
    check_ssh_access
    check_ollama
    install_autossh
    create_systemd_service
    enable_and_start_service
    test_tunnel
    display_instructions
    
    log_info "Setup complete!"
}

main
