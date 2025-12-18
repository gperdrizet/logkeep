#!/bin/bash
# Setup script for staging nginx configuration with basic auth

set -e

echo "============================================"
echo "LogKeep Staging Nginx Setup"
echo "============================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root or with sudo"
    exit 1
fi

# Install apache2-utils if not present (for htpasswd)
if ! command -v htpasswd &> /dev/null; then
    echo "Installing apache2-utils for htpasswd..."
    apt-get update
    apt-get install -y apache2-utils
fi

# Create htpasswd file
echo "Creating basic auth credentials..."
echo "Enter username for staging access:"
read -r USERNAME

# Create htpasswd file
htpasswd -c /etc/nginx/.htpasswd "$USERNAME"

echo ""
echo "✅ Basic auth credentials created"
echo ""

# Copy nginx config
echo "Installing staging nginx config..."
cp /opt/logkeep/nginx/staging.conf /etc/nginx/sites-available/staging.conf

# Enable the site
ln -sf /etc/nginx/sites-available/staging.conf /etc/nginx/sites-enabled/staging.conf

echo "✅ Nginx config installed"
echo ""

# Test nginx config
echo "Testing nginx configuration..."
nginx -t

if [ $? -eq 0 ]; then
    echo "✅ Nginx configuration is valid"
    echo ""
    echo "Reloading nginx..."
    systemctl reload nginx
    echo "✅ Nginx reloaded"
    echo ""
    echo "============================================"
    echo "Staging environment is now accessible at:"
    echo "  https://staging.perdrizet.org"
    echo ""
    echo "Basic auth credentials required:"
    echo "  Username: $USERNAME"
    echo "  Password: (the one you just entered)"
    echo "============================================"
else
    echo "❌ Nginx configuration test failed"
    echo "Please check the error messages above"
    exit 1
fi
