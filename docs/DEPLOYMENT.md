# LogKeep Deployment Guide

Complete guide for deploying LogKeep to production on your Ionos VPS.

## Table of contents

1. [Prerequisites](#prerequisites)
2. [VPS Initial Setup](#vps-initial-setup)
3. [DNS Configuration](#dns-configuration)
4. [Local Machine Setup](#local-machine-setup)
5. [Application Deployment](#application-deployment)
6. [Monitoring Setup](#monitoring-setup)
7. [CI/CD Configuration](#cicd-configuration)
8. [Data Migration](#data-migration)
9. [Verification](#verification)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

**VPS Requirements:**
- Ubuntu 22.04 LTS
- 4 CPU cores, 8GB RAM, 120GB storage
- Static IP address
- Root or sudo access

**Local Machine Requirements:**
- Ubuntu 24.04 LTS
- Docker and Docker Compose installed
- Ollama running in Docker
- SSH access to VPS (passwordless key-based)

**Credentials Needed:**
- GitHub personal access token
- Ionos SMTP password
- SSL certificates (already on VPS)

---

## VPS initial setup

### Step 1: Connect to VPS

```bash
ssh your-vps-user@your-vps-ip
```

### Step 2: run setup script

```bash
# Download and run the setup script
sudo bash setup-vps.sh
```

**Note:** If you encounter GRUB bootloader errors during setup, see the [GRUB error troubleshooting section](#vps-setup-script-fails-with-grub-error) and use `setup-vps-skip-upgrade.sh` instead.

This script will:
- Update system packages
- Install Docker, Docker Compose, Nginx
- Configure firewall (UFW)
- Create application directories
- Generate secure passwords and secrets
- Set up initial configurations

### Step 3: save generated secrets

```bash
# View generated secrets
sudo cat /opt/logkeep/secrets/generated_secrets.txt
```

**IMPORTANT:** Copy these secrets to a secure password manager. You'll need them for the `.env.production` file.

### Step 4: clone repository

```bash
cd /opt/logkeep
git clone https://github.com/gperdrizet/logkeep.git .
git checkout main
```

### Step 5: create production environment file

```bash
# Copy template
cp .env.production.example .env.production

# Edit with generated secrets
nano .env.production
```

Fill in:
- `POSTGRES_PASSWORD` - from generated_secrets.txt
- `SECRET_KEY` - from generated_secrets.txt
- `ENCRYPTION_KEY` - from generated_secrets.txt
- `GRAFANA_ADMIN_PASSWORD` - from generated_secrets.txt
- `GITHUB_TOKEN` - your GitHub PAT
- `SMTP_PASSWORD` - your Ionos email password

### Step 6: copy nginx configurations

```bash
# Copy configs
sudo cp nginx/*.conf /etc/nginx/conf.d/

# Update nginx config to use localhost ports instead of Docker container names
sudo sed -i 's/logkeep-blue:8000/127.0.0.1:8001/' /etc/nginx/conf.d/logkeep.conf

# Enable sites
sudo ln -s /etc/nginx/conf.d/logkeep.conf /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/conf.d/grafana.conf /etc/nginx/sites-enabled/
sudo ln -s /etc/nginx/conf.d/perdrizet.conf /etc/nginx/sites-enabled/

# Test configuration (will fail until containers are running - this is expected)
sudo nginx -t

# Don't reload nginx yet - wait until containers are started
```

**Note:** System Nginx cannot resolve Docker container names. The config uses `127.0.0.1:8001` which maps to the blue container's exposed port. Nginx configuration test will fail at this stage because containers aren't running yet - this is expected.

---

## DNS Configuration

### Step 1: log into ionos DNS management

Go to your domain management panel at Ionos.

### Step 2: create a records

Add these DNS records (replace `YOUR_VPS_IP` with actual IP):

| Type | Hostname | Value | TTL |
|------|----------|-------|-----|
| A | logkeep | YOUR_VPS_IP | 3600 |
| A | grafana | YOUR_VPS_IP | 3600 |

### Step 3: Wait for DNS Propagation

```bash
# Check DNS propagation (run from local machine)
dig logkeep.perdrizet.org
dig grafana.perdrizet.org
```

This can take 5-60 minutes.

---

## Local machine setup

### Step 1: verify ollama is running

```bash
# Check ollama status
docker ps | grep ollama

# Test ollama
curl http://localhost:11434/api/tags

# If not running, start it
cd /mnt/arkk/logkeep
docker-compose up -d ollama
```

### Step 2: setup SSH tunnel

**Note:** This setup uses `autossh` for a reverse SSH tunnel rather than WireGuard, as it's simpler to configure and works well for this single-purpose tunnel.

```bash
# Run tunnel setup script
cd /mnt/arkk/logkeep
sudo bash scripts/setup-ssh-tunnel.sh
```

This creates a persistent reverse SSH tunnel that:
- Forwards local Ollama port 11434 to VPS port 11434
- Uses `autossh` for automatic reconnection
- Auto-starts on boot via systemd service
- Auto-reconnects if connection drops
- Monitors connection health with keepalive packets

### Step 3: verify tunnel

```bash
# Check tunnel status
sudo systemctl status logkeep-tunnel

# View tunnel logs
sudo journalctl -u logkeep-tunnel -f

# Test from VPS
ssh gatekeeper "curl -s http://localhost:11434/api/tags"
```

### Step 4: configure docker container to access tunnel

**Important:** Docker containers cannot reach `localhost:11434` because from inside a container, `localhost` refers to the container itself, not the VPS host. The SSH tunnel endpoint on the VPS host must be accessed via Docker's network gateway IP.

First, find your Docker network gateway IP:

```bash
# On VPS
sudo docker network inspect logkeep_logkeep-network | grep Gateway
# Should show: "Gateway": "172.18.0.1" (or similar)
```

Update `.env.production` on the VPS to use this gateway IP:

```bash
# On VPS
cd /opt/logkeep
sudo nano .env.production

# Change LLM_BASE_URL from:
LLM_BASE_URL=http://localhost:11434

# To (use your actual gateway IP):
LLM_BASE_URL=http://172.18.0.1:11434
```

### Step 5: configure firewall to allow docker access

**Critical:** UFW firewall blocks Docker containers from reaching the host by default. You must explicitly allow the Docker network to access port 11434:

```bash
# On VPS - allow Docker network to reach Ollama tunnel
sudo ufw allow from 172.18.0.0/16 to any port 11434 proto tcp comment "Docker to Ollama tunnel"

# Verify the rule was added
sudo ufw status verbose
```

Without this rule, containers will timeout when trying to reach the tunnel.

### Step 6: enable SSH gateway ports

For the SSH tunnel to be accessible from Docker containers, the VPS SSH server must allow gateway ports:

```bash
# On VPS
echo "GatewayPorts yes" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd

# Restart tunnel to bind to all interfaces
# On LOCAL machine:
sudo systemctl restart logkeep-tunnel

# Verify tunnel is listening on 0.0.0.0 (not just 127.0.0.1)
# On VPS:
sudo ss -tlnp | grep 11434
# Should show: LISTEN 0.0.0.0:11434
```

---

## Application deployment

### Step 1: pull docker image

On VPS:

```bash
cd /opt/logkeep
docker pull gperdrizet/logkeep:latest
```

### Step 2: start services

```bash
# Start production services (exclude containerized nginx if using system nginx)
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d postgres app-blue prometheus grafana loki postgres-exporter

# Check status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

**Note:** The `--env-file .env.production` flag is required because Docker Compose only auto-loads `.env` by default, not `.env.production`. We exclude the containerized `nginx` service since we're using the system Nginx that's already configured.

**TODO:** We're starting only `app-blue` for initial deployment. The `app-green` container is experiencing health check failures and needs investigation. For now, blue-green deployments are disabled. This should be revisited once the application is stable. See [Issue: Green container health check failures](#green-container-health-check-failures).

**TODO:** The `loki` container may experience restart loops during initial deployment. This is a known issue that needs investigation. Loki is used for log aggregation and is not critical for application functionality. See [Issue: Loki container restart loops](#loki-container-restart-loops).

### Step 3: Wait for services to be ready

```bash
# Wait for PostgreSQL
docker exec logkeep-postgres pg_isready -U logkeep_admin

# Wait for application
docker exec logkeep-blue curl -f http://localhost:8000/health
```

### Step 4: run database migrations

```bash
# If you have Alembic migrations
docker exec logkeep-blue alembic upgrade head

# Or run init script
docker exec logkeep-blue python -m src.utils.database
```

### Step 5: create admin user

```bash
# Create first admin user
docker exec -it logkeep-blue python -m src.cli.admin create-user \
    --username admin \
    --email admin@example.com \
    --admin
```

---

## Monitoring setup

### Step 1: access grafana

Open browser: `https://grafana.perdrizet.org`

Login:
- Username: `admin`
- Password: (from `.env.production` - `GRAFANA_ADMIN_PASSWORD`)

### Step 2: verify datasources

1. Go to Configuration → Data Sources
2. Verify Prometheus is connected (green checkmark)
3. Verify Loki is connected

### Step 3: import dashboards

1. Go to Dashboards → Import
2. Upload dashboard JSON files from `monitoring/grafana-dashboards/`
3. Or create new dashboards:
   - System Overview
   - Application Metrics
   - Database Performance

### Step 4: configure alerts

1. Go to Alerting → Contact Points
2. Add email contact point:
   - Name: Email Alerts
   - Type: Email
   - Addresses: george@perdrizet.org
3. Test notification

### Step 5: enable alert rules

1. Go to Alerting → Alert Rules
2. Verify alert rules are active
3. Test by triggering a test alert

---

## CI/CD Configuration

### Step 1: add github secrets

Go to GitHub repository → Settings → Secrets and Variables → Actions

Add these secrets:

| Secret Name | Value | Notes |
|-------------|-------|-------|
| `DOCKER_HUB_USERNAME` | gperdrizet | Docker Hub username |
| `DOCKER_HUB_TOKEN` | (generate at hub.docker.com) | Docker Hub access token |
| `VPS_SSH_PRIVATE_KEY` | (your SSH private key) | **Must be OpenSSH format** (starts with `-----BEGIN OPENSSH PRIVATE KEY-----`) |
| `VPS_HOST` | 74.208.107.78 | **Use IP address, not SSH alias** |
| `VPS_USER` | siderealyear | VPS username with deploy permissions |

**Important Notes:**
- SSH private key must be in OpenSSH format. Generate with: `ssh-keygen -t rsa -b 4096`
- VPS_HOST must be the IP address - SSH aliases from `~/.ssh/config` won't work in GitHub Actions
- VPS user must have passwordless SSH key authentication configured
- VPS SSH runs on port 44441 (configured in workflow, not in secrets)

### Step 2: create github environments

1. Go to Settings → Environments
2. Create `production` environment
3. Create `staging` environment
4. Add protection rules if desired

### Step 3: test CI/CD

```bash
# Make a small change and push to dev
git checkout dev
echo "# Test" >> README.md
git add README.md
git commit -m "Test CI/CD"
git push

# Check github actions tab for workflow run
```

### Step 4: test production deployment

```bash
# Merge to main to trigger production deploy
git checkout main
git merge dev
git push

# Watch deployment in github actions
```

---

## Data migration

If you have existing SQLite data to migrate:

### Step 1: export sqlite data

On local machine:

```bash
cd /mnt/arkk/logkeep

# Export to SQL dump
sqlite3 data/logkeep.db .dump > data/export.sql
```

### Step 2: Transfer to VPS

```bash
# Copy to VPS
scp data/export.sql gatekeeper:/opt/logkeep/data/
```

### Step 3: Import to PostgreSQL

On VPS:

```bash
cd /opt/logkeep

# Convert sqlite dump to postgresql format (if needed)
# You may need to edit the SQL file to fix syntax differences

# Import into PostgreSQL
docker exec -i logkeep-postgres psql -U logkeep_admin -d logkeep < data/export.sql

# Verify data
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "SELECT COUNT(*) FROM users;"
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "SELECT COUNT(*) FROM links;"
```

---

## Verification

### Checklist

- [ ] VPS services running: `docker-compose -f docker-compose.prod.yml ps`
- [ ] Application health check: `curl https://logkeep.perdrizet.org/health`
- [ ] SSL certificate valid (no browser warnings)
- [ ] Can log in to application
- [ ] Can create new link
- [ ] AI summarization works (check Ollama tunnel)
- [ ] Grafana accessible: `https://grafana.perdrizet.org`
- [ ] Prometheus scraping metrics
- [ ] Logs appearing in Loki
- [ ] Email alerts configured and tested
- [ ] Backups running: check `/opt/logkeep/backups/`
- [ ] CI/CD pipeline working (push to dev and main)

### Test deployment

```bash
# On vps, test a deployment
cd /opt/logkeep
./scripts/deploy.sh latest

# Should see:
# - Pull new image
# - Start green container
# - Health checks pass
# - Traffic switches
# - Blue container stops

# Test rollback
./scripts/rollback.sh

# Should switch back to previous container
```

---

## Troubleshooting

### Docker Compose not loading .env.production

**Problem:** Docker Compose shows warnings like:
```
WARNING: The POSTGRES_PASSWORD variable is not set. Defaulting to a blank string.
```

And PostgreSQL fails with:
```
Error: Database is uninitialized and superuser password is not specified.
```

**Cause:** Docker Compose only auto-loads a file named `.env` by default, not `.env.production`. The `${VARIABLE}` substitutions in `docker-compose.prod.yml` happen before container startup and need the variables to be available in the shell environment or in `.env`.

**Solution:** Use the `--env-file` flag to explicitly specify the environment file:

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d
docker-compose -f docker-compose.prod.yml --env-file .env.production down
docker-compose -f docker-compose.prod.yml --env-file .env.production ps
```

**Alternative solution:** Create a symlink so Docker Compose finds it automatically:

```bash
ln -sf .env.production .env
```

### Port 80 already in use (nginx conflict)

**Problem:** Docker Compose fails with:
```
failed to bind host port 0.0.0.0:80/tcp: address already in use
```

**Cause:** System Nginx is already running on port 80. The docker-compose file includes a containerized Nginx, but you're using the system Nginx instead.

**Solution:** Start services without the containerized nginx:

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d postgres app-blue prometheus grafana loki postgres-exporter
```

This uses your existing system Nginx configuration which proxies to the `logkeep-blue` container.

### VPS setup script fails with GRUB error

**Problem:** During `setup-vps.sh` execution, the script fails with:
```
Unknown device "/dev/disk/by-id/*": No such file or directory
dpkg: error processing package grub-efi-amd64-signed (--configure)
E: Sub-process /usr/bin/dpkg returned an error code (1)
```

**Cause:** This is a known issue on some VPS environments where the EFI boot configuration doesn't match the actual hardware setup. The GRUB bootloader package attempts to configure devices in `/dev/disk/by-id/` which don't exist in virtualized environments. VPS providers manage the bootloader externally, so GRUB configuration is unnecessary.

**Solution:** Remove the failing GRUB installation scripts and use the skip-upgrade setup script:

```bash
# On local machine, copy the fix script to VPS
scp scripts/fix-grub.sh gatekeeper:/tmp/

# On VPS, run the fix script
bash /tmp/fix-grub.sh

# Then run the skip-upgrade setup script
sudo bash setup-vps-skip-upgrade.sh
```

**Manual fix** (if you prefer to run commands individually):

```bash
# Remove GRUB postinst scripts that cause failures
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.postinst
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.preinst
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.prerm
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.postrm

# Create placeholder files so dpkg thinks package is configured
sudo touch /var/lib/dpkg/info/grub-efi-amd64-signed.list
sudo touch /var/lib/dpkg/info/grub-efi-amd64-signed.md5sums

# Complete package configuration
sudo dpkg --configure -a

# Run the skip-upgrade setup script
sudo bash setup-vps-skip-upgrade.sh
```

**Note:** The `setup-vps-skip-upgrade.sh` script skips the full system upgrade (`apt upgrade`) and only installs the packages LogKeep needs. This avoids the GRUB issue entirely. The bootloader configuration is not needed for LogKeep operation since all services run in Docker containers and the VPS provider manages system booting.

### Application won't start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs app-blue

# Check environment variables
docker exec logkeep-blue env

# Check database connection
docker exec logkeep-blue python -c "from src.utils.database import engine; engine.connect()"
```

### Nginx cannot resolve Docker container names

**Problem:** Nginx test fails with:
```
nginx: [emerg] host not found in upstream "logkeep-blue:8000"
```

**Cause:** System Nginx runs outside Docker and cannot resolve Docker container names. It can only connect to services on localhost.

**Solution:** Use localhost ports that are mapped from the containers. Update the nginx config:

```bash
# Change from container name to localhost port
sudo sed -i 's/server logkeep-blue:8000/server 127.0.0.1:8001/' /etc/nginx/conf.d/logkeep.conf

# For blue-green deployments, green uses port 8002:
# sudo sed -i 's/server 127.0.0.1:8001/server 127.0.0.1:8002/' /etc/nginx/conf.d/logkeep.conf
```

The docker-compose file maps:
- Blue container: `127.0.0.1:8001` → `logkeep-blue:8000`
- Green container: `127.0.0.1:8002` → `logkeep-green:8000`

### SSL certificate issues

```bash
# Verify cert files exist
ls -la /etc/nginx/certs/

# Check nginx config
sudo nginx -t

# View nginx error logs
sudo tail -f /var/log/nginx/error.log
```

### Ollama not accessible from Docker container

**Problem:** AI summarization fails with "Connection refused" or timeout errors when trying to reach Ollama.

**Symptoms:**
- Logs show: `ERROR - Unexpected error during summarization: [Errno 111] Connection refused`
- Or: `URLError: <urlopen error timed out>`
- Testing from VPS host works: `curl http://localhost:11434/api/tags` succeeds
- Testing from container fails: `docker exec logkeep-blue python -c "import urllib.request; urllib.request.urlopen('http://172.18.0.1:11434/api/tags')"`

**Cause:** Docker containers are isolated and cannot reach `localhost` on the host. They must use the Docker network gateway IP. Additionally, UFW firewall blocks Docker network traffic to the host by default.

**Solution:**

1. **Find your Docker network gateway IP:**
```bash
sudo docker network inspect logkeep_logkeep-network | grep Gateway
# Example output: "Gateway": "172.18.0.1"
```

2. **Update `.env.production` with correct gateway IP:**
```bash
cd /opt/logkeep
sudo nano .env.production
# Set: LLM_BASE_URL=http://172.18.0.1:11434 (use your actual gateway IP)
```

3. **Add UFW firewall rule to allow Docker network:**
```bash
sudo ufw allow from 172.18.0.0/16 to any port 11434 proto tcp comment "Docker to Ollama tunnel"
```

4. **Enable SSH GatewayPorts on VPS:**
```bash
echo "GatewayPorts yes" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
```

5. **Restart tunnel on local machine:**
```bash
sudo systemctl restart logkeep-tunnel
```

6. **Verify tunnel is listening on all interfaces:**
```bash
sudo ss -tlnp | grep 11434
# Should show: LISTEN 0.0.0.0:11434 (not 127.0.0.1:11434)
```

7. **Recreate container to load new environment:**
```bash
cd /opt/logkeep
sudo docker-compose -f docker-compose.prod.yml --env-file .env.production stop app-blue
sudo docker-compose -f docker-compose.prod.yml --env-file .env.production rm -f app-blue
sudo docker-compose -f docker-compose.prod.yml --env-file .env.production up -d app-blue
```

8. **Test connection from container:**
```bash
sudo docker exec logkeep-blue python -c "import urllib.request; print(urllib.request.urlopen('http://172.18.0.1:11434/api/tags', timeout=5).read().decode())"
# Should return JSON with model info
```

### Ollama tunnel check

```bash
# On local machine, check tunnel
sudo systemctl status logkeep-tunnel

# Restart tunnel
sudo systemctl restart logkeep-tunnel

# On vps, test ollama
curl http://localhost:11434/api/tags

# Check firewall isn't blocking
sudo ufw status
```

### Database connection issues

```bash
# Check postgresql is running
docker exec logkeep-postgres pg_isready -U logkeep_admin

# Check credentials in .env.production
cat .env.production | grep POSTGRES

# View postgresql logs
docker logs logkeep-postgres
```

### Monitoring not working

```bash
# Check prometheus targets
curl http://localhost:9090/api/v1/targets

# Check if services are exposing metrics
docker exec logkeep-blue curl http://localhost:8000/metrics

# Restart monitoring stack
docker-compose -f docker-compose.prod.yml restart prometheus grafana loki
```

### Deployment failures

```bash
# View deployment script output
./scripts/deploy.sh latest 2>&1 | tee deployment.log

# Check container health
docker exec logkeep-green curl http://localhost:8000/health

# Manual rollback
./scripts/rollback.sh
```

### Green container health check failures

**Problem:** The `app-green` container fails health checks during startup with "Container is unhealthy" error.

**Status:** Known issue - currently under investigation. Initial deployment uses only `app-blue` container.

**Temporary workaround:** Start only essential services without green container:

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d postgres app-blue prometheus grafana loki postgres-exporter
```

**Impact:** Blue-green deployment capability is temporarily disabled. Updates must be deployed by restarting `app-blue` container instead of switching traffic between blue and green.

**Investigation needed:**
1. Check if green container health check endpoint is accessible
2. Verify green container logs: `docker logs logkeep-green`
3. Compare blue and green container configurations in `docker-compose.prod.yml`
4. Test if both containers can run simultaneously without port conflicts
5. Verify health check timeout and retry settings are appropriate

**TODO:** Re-enable green container once health check issue is resolved. Update deployment scripts to use blue-green switching mechanism.

### Loki container restart loops

**Problem:** The `logkeep-loki` container enters a restart loop during or after deployment.

**Status:** Known issue - currently under investigation. Loki is not critical for core application functionality.

**Impact:** Log aggregation and centralized logging are unavailable. Application logs can still be viewed with `docker logs logkeep-blue`. Grafana dashboards that depend on Loki data sources will not function.

**Temporary workaround:** The application can run without Loki. To exclude it from startup:

```bash
docker-compose -f docker-compose.prod.yml --env-file .env.production up -d postgres app-blue prometheus grafana postgres-exporter
```

**Investigation needed:**
1. Check Loki logs for specific error: `docker logs logkeep-loki`
2. Verify volume permissions for Loki data directory
3. Check Loki configuration file in `monitoring/loki-config.yml`
4. Test if Loki can start in standalone mode
5. Verify Loki version compatibility with Grafana version
6. Check for port conflicts or resource constraints

**TODO:** Resolve Loki restart issue to enable full logging and monitoring capabilities.

### Static files (CSS) not loading

**Problem:** The application loaded and functioned correctly, but CSS styling was missing. Pages appeared unstyled.

**Status:** ✅ RESOLVED

**Root Cause:** The nginx configuration file `/etc/nginx/conf.d/logkeep.conf` had a static files location block that attempted to serve files from `/var/www/logkeep/static/`, which doesn't exist. This block took precedence over proxying requests to the FastAPI application.

```nginx
# This was causing the issue:
location /static/ {
    alias /var/www/logkeep/static/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

**Solution:** Comment out the nginx static files location block to allow all `/static/` requests to be proxied to the FastAPI application:

```bash
# Comment out the static files block
sudo sed -i '/# Static files/,/^    }/s/^/#/' /etc/nginx/conf.d/logkeep.conf

# Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx

# Verify CSS is now accessible
curl -I https://logkeep.perdrizet.org/static/css/style.css
```

**Verification:**
- Direct container access worked: `curl http://127.0.0.1:8001/static/css/style.css` returned 200 OK
- After nginx config fix: `curl https://logkeep.perdrizet.org/static/css/style.css` returns 200 OK
- CSS files properly served by FastAPI's StaticFiles mount

**Lessons Learned:**
- Always verify nginx location block priorities when debugging 404s
- FastAPI can handle static file serving efficiently in production
- Test direct container access to isolate whether issue is app or proxy layer

### Grafana dashboard metrics incomplete

**Problem:** Grafana dashboard shows errors for "Application Status" and "Prometheus Status" panels, and container metrics (CPU/memory) show no data.

**Status:** Known issue - dashboard needs updates after application metrics endpoint is implemented.

**Impact:** Dashboard shows database metrics and application data (links, users) correctly, but missing:
- Application health status from Prometheus
- Container CPU and memory metrics (requires cAdvisor or node-exporter)
- Application-specific metrics from `/metrics` endpoint

**Cause:** 
1. LogKeep application doesn't expose a `/metrics` endpoint yet (returns 404)
2. cAdvisor and node-exporter containers not included in deployment
3. Dashboard queries reference non-existent job names and metrics

**TODO:** 
1. Add Prometheus metrics endpoint to LogKeep application
2. Consider adding node-exporter for system metrics
3. Update dashboard queries to match actual available metrics
4. Test and validate all panels display data correctly

### CI/CD pipeline configuration

**Problem:** GitHub Actions workflows failed with multiple configuration issues during initial setup.

**Status:** ✅ RESOLVED

**Issues Encountered and Resolved:**

1. **Invalid Docker Tag Format**
   - **Error:** `invalid tag "***/logkeep:-c646840": invalid reference format`
   - **Cause:** Metadata action used `type=sha,prefix={{branch}}-` which evaluated to empty prefix for pull requests
   - **Fix:** Changed to `type=sha` without branch prefix in `.github/workflows/build-and-push.yml`

2. **SSH Private Key Format Error**
   - **Error:** `Error loading key "(stdin)": error in libcrypto`
   - **Cause:** SSH private key secret had incorrect format or encoding
   - **Fix:** Updated `VPS_SSH_PRIVATE_KEY` secret with proper OpenSSH format key using `gh secret set`

3. **SSH Connection Refused**
   - **Error:** `ssh: connect to host *** port 22: Connection refused`
   - **Cause:** VPS SSH runs on custom port 44441, not default port 22
   - **Fix:** Added SSH config in workflow to specify port 44441:
     ```yaml
     echo "Host ${{ secrets.VPS_HOST }}" >> ~/.ssh/config
     echo "  Port 44441" >> ~/.ssh/config
     ```

4. **VPS Host Resolution**
   - **Error:** `ssh-keyscan` failed to reach VPS
   - **Cause:** `VPS_HOST` secret contained SSH alias `gatekeeper` instead of IP
   - **Fix:** Updated `VPS_HOST` secret to actual IP address `74.208.107.78`

5. **Nginx Check Failure**
   - **Error:** `Nginx is not installed` during preflight checks
   - **Cause:** Deploy script used `sudo nginx -v` which requires interactive sudo password
   - **Fix:** Changed to `command -v nginx` with warning instead of error in `scripts/deploy.sh`

6. **Nginx Configuration Mismatch**
   - **Error:** Deploy script tried to update Docker container names, but nginx uses localhost ports
   - **Cause:** Script expected `server logkeep-blue:8000` but actual config uses `server 127.0.0.1:8001`
   - **Fix:** Updated `switch_nginx_upstream()` function to use port numbers (8001/8002) instead of container names

7. **Passwordless Sudo Required**
   - **Issue:** Deploy script needs to reload nginx without password prompt
   - **Fix:** Added sudoers file on VPS:
     ```bash
     # /etc/sudoers.d/logkeep-deploy
     siderealyear ALL=(ALL) NOPASSWD: /usr/bin/nginx, /usr/sbin/nginx, /bin/systemctl reload nginx, /usr/bin/systemctl reload nginx, /bin/sed
     ```

**Current State:**
- Build workflow successfully builds and pushes Docker images on dev and main branches
- Build workflow runs on pull requests for validation
- Production deployment workflow configured for main branch merges
- Staging workflow disabled (manual-only) until staging environment configured
- SSH authentication working with correct port and credentials
- Deploy script compatible with VPS nginx configuration

**Files Modified:**
- `.github/workflows/build-and-push.yml` - Fixed tag generation
- `.github/workflows/deploy-production.yml` - Added SSH port config
- `.github/workflows/deploy-staging.yml` - Changed to manual-only
- `scripts/deploy.sh` - Fixed nginx checks and port-based switching
- VPS: `/etc/sudoers.d/logkeep-deploy` - Passwordless sudo for deployment

### Staging environment not configured

**Problem:** The CI/CD pipeline includes a "Deploy to Staging" workflow that fails because no staging environment exists.

**Status:** Known limitation - staging deployment disabled for automatic runs.

**Current State:**
- Staging deployment workflow exists in `.github/workflows/deploy-staging.yml`
- Workflow changed to manual-only (`workflow_dispatch`) to prevent automatic failures
- No staging infrastructure deployed on VPS or elsewhere

**Impact:** 
- Cannot test deployments in staging before production
- CI/CD pipeline only builds images; production deploys manually or on merge to `main`
- Higher risk when deploying changes to production

**TODO:** Set up proper staging environment:
1. **Option A - VPS Staging Container:**
   - Add staging container to `docker-compose.prod.yml` (e.g., `app-staging` on port 8003)
   - Configure nginx reverse proxy for staging subdomain
   - Set up separate staging database or schema
   - Update GitHub secrets for staging deployment
   - Re-enable automatic staging deployments on dev branch pushes

2. **Option B - Separate Staging Server:**
   - Provision separate VPS or cloud instance for staging
   - Mirror production infrastructure at smaller scale
   - Configure DNS for staging subdomain
   - Set up SSH access and deployment credentials
   - Implement staging-specific configuration

3. **Option C - Local Staging:**
   - Keep staging environment on development machine
   - Use docker-compose for local staging tests
   - Manual verification before pushing to production
   - Simpler but less representative of production

**Recommendation:** Option A (VPS staging container) provides good balance of cost and testing fidelity. Can share database server with different schema or use separate staging database.

### Docker Compose log streaming error

**Problem:** When following container logs with `-f` flag, you may see:

```
Exception in thread Thread-2 (watch_events):
Traceback (most recent call last):
  File "/usr/lib/python3.10/threading.py", line 1016, in _bootstrap_inner
    self.run()
  File "/usr/lib/python3.10/threading.py", line 953, in run
    self._target(*self._args, **self._kwargs)
  File "/usr/lib/python3/dist-packages/compose/cli/log_printer.py", line 202, in watch_events
    for event in event_stream:
  File "/usr/lib/python3/dist-packages/compose/project.py", line 626, in yield_loop
    yield build_container_event(event)
  File "/usr/lib/python3/dist-packages/compose/project.py", line 594, in build_container_event
    container = Container.from_id(self.client, event['id'])
KeyError: 'id'
```

**Cause:** This is a known bug in docker-compose's log streaming thread. It occurs when the event stream encounters a malformed event.

**Impact:** None - this is purely a cosmetic issue in the log watching thread. It does not affect container operation, log collection, or application functionality.

**Solution:** This error can be safely ignored. If it bothers you, use `--tail` without `-f` for non-streaming logs, or use `docker logs` directly instead of `docker-compose logs`.

---

## Next steps

After successful deployment:

1. **Set up regular backups:** Verify cron job is running (`crontab -l`)
2. **Monitor for 48 hours:** Watch Grafana dashboards for issues
3. **Test all features:** Create users, submit links, test AI summaries
4. **Document any issues:** Update runbook with solutions
5. **Invite test users:** Generate invite codes
6. **Plan scaling:** Monitor resource usage and plan upgrades
7. **Clean up Ionos firewall:** Remove any temporary firewall rules from Ionos admin interface now that UFW is configured on the VPS

---

## Support resources

- **Documentation:** `/mnt/arkk/logkeep/docs/`
- **Operations Guide:** `docs/OPERATIONS.md`
- **Deployment Plan:** `docs/DEPLOYMENT_PLAN.md`
- **GitHub Issues:** https://github.com/gperdrizet/logkeep/issues

---

**Deployment Date:** _____________________  
**Deployed By:** _____________________  
**Version:** _____________________

