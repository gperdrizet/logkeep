#!/bin/bash
# =============================================================================
# LogKeep VPS Setup Script (Skip Full Upgrade)
# =============================================================================
# This is a modified version that skips apt upgrade to avoid GRUB issues
# Use this if setup-vps.sh fails due to grub-efi-amd64-signed errors
#
# Usage: sudo bash setup-vps-skip-upgrade.sh
# =============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/logkeep"
BACKUP_DIR="/opt/logkeep/backups"
NGINX_CONF_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
DOCKER_GROUP="docker"

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

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

generate_secret_key() {
    openssl rand -hex 32
}

# =============================================================================
# Main Setup Functions
# =============================================================================

update_system() {
    log_info "Updating package lists..."
    apt-get update
    
    log_warn "Skipping full system upgrade to avoid GRUB issues"
    log_info "Installing only required packages..."
}

install_dependencies() {
    log_info "Installing Docker and dependencies..."
    
    # Install prerequisites
    apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
        git \
        ufw \
        fail2ban \
        certbot \
        python3-certbot-nginx
    
    # Add Docker's official GPG key
    if [ ! -f /etc/apt/keyrings/docker.gpg ]; then
        install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
            gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
    fi
    
    # Add Docker repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Enable and start Docker
    systemctl enable docker
    systemctl start docker
    
    log_info "Docker installed successfully"
}

setup_firewall() {
    log_info "Configuring firewall..."
    
    # Reset firewall to default
    ufw --force reset
    
    # Default policies
    ufw default deny incoming
    ufw default allow outgoing
    
    # Allow SSH (with rate limiting)
    ufw limit 22/tcp comment 'SSH with rate limiting'
    
    # Allow HTTP/HTTPS
    ufw allow 80/tcp comment 'HTTP'
    ufw allow 443/tcp comment 'HTTPS'
    
    # Enable firewall
    ufw --force enable
    
    log_info "Firewall configured successfully"
}

configure_fail2ban() {
    log_info "Configuring fail2ban..."
    
    # Create local configuration
    cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
destemail = root@localhost
sendername = Fail2Ban
action = %(action_mwl)s

[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
EOF
    
    # Restart fail2ban
    systemctl restart fail2ban
    systemctl enable fail2ban
    
    log_info "fail2ban configured successfully"
}

setup_directories() {
    log_info "Setting up application directories..."
    
    # Create application directory
    mkdir -p "$APP_DIR"
    mkdir -p "$APP_DIR/data"
    mkdir -p "$APP_DIR/logs"
    mkdir -p "$APP_DIR/secrets"
    mkdir -p "$BACKUP_DIR"
    
    # Set permissions
    chmod 755 "$APP_DIR"
    chmod 700 "$APP_DIR/secrets"
    
    log_info "Directories created successfully"
}

generate_secrets() {
    log_info "Generating application secrets..."
    
    SECRET_KEY=$(generate_secret_key)
    DB_PASSWORD=$(generate_password)
    ADMIN_PASSWORD=$(generate_password)
    
    # Save secrets to file
    cat > "$APP_DIR/secrets/generated_secrets.txt" <<EOF
# LogKeep Generated Secrets
# Generated on: $(date)
# IMPORTANT: Save these securely and delete this file after copying!

SECRET_KEY=$SECRET_KEY
DB_PASSWORD=$DB_PASSWORD
ADMIN_PASSWORD=$ADMIN_PASSWORD

# Next Steps:
# 1. Copy these values to your .env.production file
# 2. Save them in a secure password manager
# 3. Delete this file: rm $APP_DIR/secrets/generated_secrets.txt
EOF
    
    chmod 600 "$APP_DIR/secrets/generated_secrets.txt"
    
    log_info "Secrets generated and saved to: $APP_DIR/secrets/generated_secrets.txt"
    log_warn "IMPORTANT: Save these secrets securely and delete the file!"
}

setup_docker_compose() {
    log_info "Setting up Docker Compose..."
    
    # Add user to docker group if specified
    if [ ! -z "${SUDO_USER:-}" ]; then
        usermod -aG docker "$SUDO_USER"
        log_info "Added $SUDO_USER to docker group"
    fi
    
    log_info "Docker Compose setup complete"
}

install_nginx() {
    log_info "Installing and configuring Nginx..."
    
    # Install Nginx if not already installed
    if ! command -v nginx &> /dev/null; then
        apt-get install -y nginx
    fi
    
    # Create configuration directories if they don't exist
    mkdir -p "$NGINX_CONF_DIR"
    mkdir -p "$NGINX_ENABLED_DIR"
    
    # Disable default site
    rm -f "$NGINX_ENABLED_DIR/default"
    
    # Enable and start Nginx
    systemctl enable nginx
    systemctl start nginx
    
    log_info "Nginx installed successfully"
}

print_summary() {
    echo ""
    echo "========================================================================="
    log_info "VPS Setup Complete!"
    echo "========================================================================="
    echo ""
    echo "Generated secrets have been saved to:"
    echo "  $APP_DIR/secrets/generated_secrets.txt"
    echo ""
    echo "Next steps:"
    echo "  1. Copy the generated secrets to a secure location"
    echo "  2. Clone your repository to $APP_DIR"
    echo "  3. Create and configure .env.production"
    echo "  4. Copy Nginx configurations"
    echo "  5. Request SSL certificates"
    echo "  6. Start the application"
    echo ""
    echo "For detailed instructions, see: docs/DEPLOYMENT.md"
    echo ""
    echo "========================================================================="
}

# =============================================================================
# Main Script
# =============================================================================

main() {
    log_info "Starting LogKeep VPS setup (skipping full upgrade)..."
    echo ""
    
    check_root
    update_system
    install_dependencies
    setup_firewall
    configure_fail2ban
    setup_directories
    generate_secrets
    setup_docker_compose
    install_nginx
    
    print_summary
}

# Run main function
main

log_info "Setup script completed successfully!"
