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

| Secret Name | Value |
|-------------|-------|
| `DOCKER_HUB_USERNAME` | gperdrizet |
| `DOCKER_HUB_TOKEN` | (generate at hub.docker.com) |
| `VPS_SSH_PRIVATE_KEY` | (your SSH private key) |
| `VPS_HOST` | (your VPS IP) |
| `VPS_USER` | siderealyear |

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

### Ollama not accessible

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

**Problem:** The application loads and functions correctly, but CSS styling is missing. Pages appear unstyled.

**Status:** Known issue - application is functional but visual appearance is affected.

**Impact:** User interface lacks styling and formatting. Application functionality (login, link submission, etc.) still works.

**Investigation needed:**
1. Verify CSS files exist in container: `docker exec logkeep-blue ls -la /app/src/static/css/`
2. Check browser console (F12) for 404 errors on CSS file requests
3. Verify static file route configuration in main application file
4. Check if Nginx is properly proxying static file requests
5. Test direct access to static files: `curl http://127.0.0.1:8001/static/css/style.css`
6. Verify static file mounting in docker-compose volumes
7. Check FastAPI/Starlette static file configuration

**TODO:** Debug and fix static file serving to restore application styling.

---

## Next steps

After successful deployment:

1. **Set up regular backups:** Verify cron job is running (`crontab -l`)
2. **Monitor for 48 hours:** Watch Grafana dashboards for issues
3. **Test all features:** Create users, submit links, test AI summaries
4. **Document any issues:** Update runbook with solutions
5. **Invite test users:** Generate invite codes
6. **Plan scaling:** Monitor resource usage and plan upgrades

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

