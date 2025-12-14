#!/bin/bash
# =============================================================================
# LogKeep VPS Setup Script
# =============================================================================
# This script sets up a fresh VPS for LogKeep production deployment.
# Run this once on initial setup.
#
# Usage: sudo bash setup-vps.sh
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
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
}

generate_secret_key() {
    openssl rand -hex 32
}

generate_fernet_key() {
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
}

# =============================================================================
# System Updates
# =============================================================================

update_system() {
    log_info "Updating system packages..."
    apt-get update
    apt-get upgrade -y
    log_info "System updated successfully"
}

# =============================================================================
# Install Dependencies
# =============================================================================

install_dependencies() {
    log_info "Installing required packages..."
    
    # Check if Docker is already installed
    if command -v docker &> /dev/null; then
        log_info "Docker is already installed"
    else
        log_info "Installing Docker..."
        apt-get install -y \
            apt-transport-https \
            ca-certificates \
            curl \
            gnupg \
            lsb-release
        
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        
        echo \
          "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
          $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        apt-get update
        apt-get install -y docker-ce docker-ce-cli containerd.io
    fi
    
    # Check if Docker Compose is already installed
    if command -v docker-compose &> /dev/null; then
        log_info "Docker Compose is already installed"
    else
        log_info "Installing Docker Compose..."
        curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
    fi
    
    # Install other utilities
    apt-get install -y \
        nginx \
        python3-pip \
        git \
        htop \
        net-tools \
        ufw \
        fail2ban
    
    # Install Python packages needed for script
    pip3 install cryptography
    
    log_info "All dependencies installed successfully"
}

# =============================================================================
# Configure Firewall
# =============================================================================

configure_firewall() {
    log_info "Configuring firewall..."
    
    # Allow SSH
    ufw allow 22/tcp
    
    # Allow HTTP and HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    
    # Enable firewall
    ufw --force enable
    
    log_info "Firewall configured successfully"
}

# =============================================================================
# Setup Application Directories
# =============================================================================

setup_directories() {
    log_info "Creating application directories..."
    
    mkdir -p "$APP_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$APP_DIR/data"
    mkdir -p "$APP_DIR/logs"
    mkdir -p "$APP_DIR/nginx"
    mkdir -p "$APP_DIR/monitoring"
    mkdir -p "$APP_DIR/scripts"
    mkdir -p "$APP_DIR/secrets"
    
    # Set permissions
    chmod 700 "$APP_DIR/secrets"
    chmod 755 "$APP_DIR"
    
    log_info "Directories created successfully"
}

# =============================================================================
# Generate Secrets
# =============================================================================

generate_secrets() {
    log_info "Generating secrets..."
    
    POSTGRES_PASSWORD=$(generate_password)
    SECRET_KEY=$(generate_secret_key)
    ENCRYPTION_KEY=$(generate_fernet_key)
    GRAFANA_PASSWORD=$(generate_password)
    
    # Save to secrets file
    cat > "$APP_DIR/secrets/generated_secrets.txt" << EOF
# Generated on $(date)
# DO NOT COMMIT THIS FILE TO VERSION CONTROL

POSTGRES_PASSWORD=$POSTGRES_PASSWORD
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD
EOF
    
    chmod 600 "$APP_DIR/secrets/generated_secrets.txt"
    
    log_info "Secrets generated and saved to $APP_DIR/secrets/generated_secrets.txt"
    log_warn "IMPORTANT: Save these secrets securely! They are needed for .env.production"
}

# =============================================================================
# Create Environment File Template
# =============================================================================

create_env_template() {
    log_info "Creating environment file template..."
    
    cat > "$APP_DIR/.env.production.template" << 'EOF'
# Copy this to .env.production and fill in the values
# Then run: docker-compose -f docker-compose.prod.yml up -d

POSTGRES_USER=logkeep_admin
POSTGRES_PASSWORD=REPLACE_WITH_GENERATED_PASSWORD
SECRET_KEY=REPLACE_WITH_GENERATED_SECRET
ENCRYPTION_KEY=REPLACE_WITH_GENERATED_FERNET_KEY
GITHUB_TOKEN=REPLACE_WITH_YOUR_GITHUB_TOKEN
GRAFANA_ADMIN_PASSWORD=REPLACE_WITH_GENERATED_PASSWORD
SMTP_PASSWORD=REPLACE_WITH_YOUR_IONOS_SMTP_PASSWORD
EOF
    
    log_info "Environment template created at $APP_DIR/.env.production.template"
}

# =============================================================================
# Create Database Init Script
# =============================================================================

create_db_init_script() {
    log_info "Creating database initialization script..."
    
    cat > "$APP_DIR/scripts/init-staging-db.sql" << 'EOF'
-- Create staging database
CREATE DATABASE logkeep_staging;

-- Grant privileges to logkeep_admin
GRANT ALL PRIVILEGES ON DATABASE logkeep_staging TO logkeep_admin;
EOF
    
    log_info "Database init script created"
}

# =============================================================================
# Setup Nginx Configuration
# =============================================================================

setup_nginx() {
    log_info "Setting up Nginx configuration..."
    
    # Remove default site if exists
    if [ -f "$NGINX_ENABLED_DIR/default" ]; then
        rm -f "$NGINX_ENABLED_DIR/default"
        log_info "Removed default Nginx site"
    fi
    
    # Note: Actual nginx configs will be copied from repository
    # This just prepares the directory structure
    
    # Test nginx configuration
    nginx -t
    
    log_info "Nginx setup complete"
}

# =============================================================================
# Setup Docker Network
# =============================================================================

setup_docker_network() {
    log_info "Setting up Docker network..."
    
    # Create network if it doesn't exist
    if ! docker network inspect logkeep-network &> /dev/null; then
        docker network create logkeep-network
        log_info "Docker network 'logkeep-network' created"
    else
        log_info "Docker network 'logkeep-network' already exists"
    fi
}

# =============================================================================
# Setup Automated Backups
# =============================================================================

setup_backup_cron() {
    log_info "Setting up automated backup cron job..."
    
    # Create backup script placeholder
    cat > "$APP_DIR/scripts/backup-db.sh" << 'EOF'
#!/bin/bash
# This will be replaced with actual backup script from repository
echo "Run git pull to get the actual backup script"
EOF
    
    chmod +x "$APP_DIR/scripts/backup-db.sh"
    
    # Add cron job for backups (2 AM daily)
    CRON_JOB="0 2 * * * $APP_DIR/scripts/backup-db.sh >> $APP_DIR/logs/backup.log 2>&1"
    
    # Check if cron job already exists
    if ! crontab -l 2>/dev/null | grep -q "$APP_DIR/scripts/backup-db.sh"; then
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        log_info "Backup cron job added (runs daily at 2 AM)"
    else
        log_info "Backup cron job already exists"
    fi
}

# =============================================================================
# Setup SSH Tunnel Service (for Ollama)
# =============================================================================

setup_ssh_tunnel_info() {
    log_info "SSH tunnel must be set up on local machine..."
    log_info "Run scripts/setup-ssh-tunnel.sh on your local machine after VPS setup is complete"
}

# =============================================================================
# Final Instructions
# =============================================================================

display_final_instructions() {
    log_info "=========================================="
    log_info "VPS Setup Complete!"
    log_info "=========================================="
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Clone the LogKeep repository to $APP_DIR:"
    echo "   cd $APP_DIR"
    echo "   git clone https://github.com/gperdrizet/logkeep.git ."
    echo ""
    echo "2. Copy environment template:"
    echo "   cp .env.production.example .env.production"
    echo ""
    echo "3. Edit .env.production with generated secrets from:"
    echo "   cat $APP_DIR/secrets/generated_secrets.txt"
    echo ""
    echo "4. Copy Nginx configs:"
    echo "   sudo cp nginx/*.conf $NGINX_CONF_DIR/"
    echo "   sudo ln -s $NGINX_CONF_DIR/logkeep.conf $NGINX_ENABLED_DIR/"
    echo "   sudo ln -s $NGINX_CONF_DIR/grafana.conf $NGINX_ENABLED_DIR/"
    echo "   sudo ln -s $NGINX_CONF_DIR/perdrizet.conf $NGINX_ENABLED_DIR/"
    echo "   sudo nginx -s reload"
    echo ""
    echo "5. Start services:"
    echo "   docker-compose -f docker-compose.prod.yml up -d"
    echo ""
    echo "6. Set up SSH tunnel on local machine:"
    echo "   Run scripts/setup-ssh-tunnel.sh on your local machine"
    echo ""
    echo "7. Create first admin user:"
    echo "   docker exec -it logkeep-blue python -m src.cli.admin create-user --admin"
    echo ""
    log_warn "IMPORTANT: Secure the secrets file at $APP_DIR/secrets/generated_secrets.txt"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    log_info "Starting LogKeep VPS setup..."
    
    check_root
    update_system
    install_dependencies
    configure_firewall
    setup_directories
    generate_secrets
    create_env_template
    create_db_init_script
    setup_nginx
    setup_docker_network
    setup_backup_cron
    setup_ssh_tunnel_info
    display_final_instructions
    
    log_info "Setup script completed successfully!"
}

# Run main function
main
