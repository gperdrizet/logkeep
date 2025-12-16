# Deployment Guide: Monitoring & Backup Updates

This guide walks through deploying the new monitoring metrics, backup scripts, and alerting infrastructure.

## Pre-Deployment Checklist

- [ ] All changes committed to git
- [ ] Docker installed and running
- [ ] Access to VPS (SSH configured)
- [ ] `.env.production` file exists on VPS with SMTP credentials

## Step 1: Local Testing (Development)

### 1.1 Test Prometheus Metrics Endpoint

```bash
# Install new dependency
pip install prometheus-client==0.21.0

# Start development server
docker-compose up -d

# Wait for startup
sleep 10

# Test metrics endpoint
curl http://localhost:8000/metrics

# Should see output like:
# logkeep_requests_total{...} 0.0
# logkeep_request_duration_seconds_bucket{...} 0.0
# logkeep_active_users 0.0
```

### 1.2 Test Application Health

```bash
# Test health endpoint
curl http://localhost:8000/health

# Submit a test link (requires login first)
# Check metrics again - request count should increase
curl http://localhost:8000/metrics | grep logkeep_requests_total
```

### 1.3 Verify Backup Scripts

```bash
# Check scripts are executable
ls -la scripts/backup-db.sh scripts/restore-db.sh

# Should show: -rwxr-xr-x (executable)
```

### 1.4 Stop Local Environment

```bash
docker-compose down
```

## Step 2: Build and Push Docker Image

### 2.1 Commit Changes

```bash
# Check what's changed
git status

# Add all changes
git add .

# Commit with descriptive message
git commit -m "Add Prometheus metrics, backup scripts, and monitoring infrastructure

- Implement /metrics endpoint with application-level metrics
- Add version-controlled backup/restore scripts
- Enable Alertmanager for email notifications
- Add cAdvisor for container metrics
- Add nginx-prometheus-exporter
- Create staging environment template"

# Push to repository
git push origin main
```

### 2.2 Build New Docker Image

```bash
# Build image with new tag
docker build -t gperdrizet/logkeep:v1.1.0 .
docker build -t gperdrizet/logkeep:latest .

# Test the image locally
docker run -d --name test-logkeep \
  -e SESSION_SECRET=test-secret-key-min-32-chars-long \
  -e ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
  -e DATABASE_URL=sqlite:///data/logkeep.db \
  -p 8000:8000 \
  gperdrizet/logkeep:v1.1.0

# Wait for startup
sleep 10

# Test metrics endpoint
curl http://localhost:8000/metrics

# Cleanup
docker stop test-logkeep
docker rm test-logkeep
```

### 2.3 Push to Registry

```bash
# Login to Docker Hub
docker login

# Push both tags
docker push gperdrizet/logkeep:v1.1.0
docker push gperdrizet/logkeep:latest
```

## Step 3: Update VPS Configuration Files

### 3.1 SSH to VPS

```bash
ssh -p 44441 your-user@your-vps-host
cd /opt/logkeep
```

### 3.2 Pull Latest Repository

```bash
# Backup current state
git stash

# Pull updates
git pull origin main

# If you had local changes, review them
git stash list
```

### 3.3 Update .env.production

Add these new variables to `.env.production`:

```bash
nano .env.production
```

Add/verify:
```bash
# Alert Email
ALERT_EMAIL=george@perdrizet.org

# SMTP Configuration (for Alertmanager)
SMTP_HOST=smtp.ionos.com
SMTP_PORT=587
SMTP_USER=your-email@perdrizet.org
SMTP_PASSWORD=your-ionos-smtp-password

# Grafana (if not already set)
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=your-secure-password
```

### 3.4 Update Nginx Configuration

```bash
# Copy nginx configs to system location
sudo cp nginx/blue.conf /etc/nginx/conf.d/
sudo cp nginx/green.conf /etc/nginx/conf.d/
sudo cp nginx/grafana.conf /etc/nginx/conf.d/

# Test nginx configuration
sudo nginx -t

# Reload nginx (don't restart yet - we'll do this after deployment)
# We'll reload after confirming which config is active
```

## Step 4: Deploy Monitoring Stack

### 4.1 Update Monitoring Containers

```bash
cd /opt/logkeep

# Pull latest monitoring images
docker-compose -f docker-compose.prod.yml pull \
  prometheus grafana loki promtail node-exporter \
  postgres-exporter alertmanager cadvisor

# Restart monitoring stack (no downtime for app)
docker-compose -f docker-compose.prod.yml up -d \
  prometheus grafana loki promtail node-exporter \
  postgres-exporter alertmanager cadvisor

# Check logs
docker-compose -f docker-compose.prod.yml logs -f alertmanager
# Press Ctrl+C after verifying it started
```

### 4.2 Verify Monitoring Services

```bash
# Check all containers are running
docker-compose -f docker-compose.prod.yml ps

# Test Prometheus
curl http://localhost:9090/-/healthy

# Test Alertmanager
curl http://localhost:9093/-/healthy

# Check Prometheus can reach Alertmanager
curl http://localhost:9090/api/v1/alertmanagers
```

## Step 5: Deploy Application (Blue/Green)

### 5.1 Run Deployment Script

```bash
cd /opt/logkeep

# Deploy latest version
./scripts/deploy.sh latest

# The script will:
# 1. Pull new Docker image
# 2. Start new container (green slot)
# 3. Wait for health checks
# 4. Switch Nginx to new container
# 5. Observe for configured period (60 seconds in CI/CD, 5 min manual)
# 6. Stop old container
```

### 5.2 Monitor Deployment

Watch the deployment output. It will show:
```
=== LogKeep Blue/Green Deployment ===
Current active slot: blue
Target slot: green

[1/6] Pulling latest image...
[2/6] Starting green container...
[3/6] Health check: Waiting for green to be ready...
[4/6] Switching Nginx to green...
[5/6] Observation period (60s)...
[6/6] Stopping old container (blue)...

Deployment completed successfully!
```

## Step 6: Verify Deployment

### 6.1 Test Application

```bash
# Test health endpoint through Nginx
curl https://logkeep.perdrizet.org/health

# Test metrics endpoint through Nginx
curl https://logkeep.perdrizet.org/metrics

# Should see Prometheus metrics output
```

### 6.2 Check Prometheus Scraping

```bash
# Check if Prometheus is scraping the app
curl "http://localhost:9090/api/v1/targets" | jq '.data.activeTargets[] | select(.labels.job=="logkeep-green")'

# Should show state: "up"
```

### 6.3 Test Application UI

Open in browser:
```
https://logkeep.perdrizet.org
```

- Login
- Submit a test link
- Check metrics again:
```bash
curl https://logkeep.perdrizet.org/metrics | grep logkeep_link_submissions_total
```

### 6.4 Check Grafana

```bash
# Open Grafana
https://grafana.perdrizet.org

# Login with credentials from .env.production
# Check the LogKeep dashboard
# Verify new metrics are showing:
# - Application metrics (requests, duration)
# - Container metrics (from cAdvisor)
```

## Step 7: Configure Alertmanager Email

### 7.1 Test Alert Email

```bash
# Trigger a test alert by stopping a container briefly
docker stop logkeep-green

# Wait 2 minutes for Prometheus to detect and alert

# Check Alertmanager
curl http://localhost:9093/api/v1/alerts | jq

# You should receive an email alert

# Restart container
docker start logkeep-green
```

### 7.2 Verify Alert Resolution Email

After container starts and health checks pass, you should receive a "resolved" email.

## Step 8: Test Backup Scripts

### 8.1 Manual Backup Test

```bash
cd /opt/logkeep

# Run backup script
./scripts/backup-db.sh

# Check backup was created
ls -lh backups/
# Should see: logkeep_YYYYMMDD_HHMMSS.sql.gz

# Check backup log
cat logs/backup.log
```

### 8.2 Schedule Automated Backups

```bash
# Edit crontab
crontab -e

# Add backup job (runs daily at 2 AM)
0 2 * * * /opt/logkeep/scripts/backup-db.sh >> /opt/logkeep/logs/backup.log 2>&1

# Verify cron job was added
crontab -l | grep backup
```

### 8.3 Test Restore (Optional - Use Staging DB)

```bash
# List available backups
ls -lh backups/

# Test restore to staging database
./scripts/restore-db.sh backups/logkeep_YYYYMMDD_HHMMSS.sql.gz logkeep_staging

# Verify staging database
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep_staging -c "SELECT COUNT(*) FROM users;"
```

## Step 9: Setup Staging Environment (Optional)

### 9.1 Create Staging Environment File

```bash
cd /opt/logkeep

# Copy template
cp .env.staging.example .env.staging

# Edit with appropriate values
nano .env.staging
```

### 9.2 Deploy Staging

```bash
# Pull staging image (assumes you tagged one as 'dev')
docker-compose -f docker-compose.staging.yml pull

# Start staging
docker-compose -f docker-compose.staging.yml up -d

# Test staging
curl http://localhost:8003/health
curl http://localhost:8003/metrics
```

## Step 10: Post-Deployment Verification

### 10.1 Check All Services

```bash
# List all containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Should see all running:
# - logkeep-green (or blue)
# - logkeep-postgres
# - logkeep-prometheus
# - logkeep-grafana
# - logkeep-loki
# - logkeep-promtail
# - logkeep-node-exporter
# - logkeep-postgres-exporter
# - logkeep-alertmanager
# - logkeep-cadvisor
```

### 10.2 Check Logs for Errors

```bash
# Check app logs
docker logs --tail 50 logkeep-green

# Check Prometheus logs
docker logs --tail 50 logkeep-prometheus

# Check Alertmanager logs
docker logs --tail 50 logkeep-alertmanager

# Check for any errors
docker-compose -f docker-compose.prod.yml logs --tail 100 | grep -i error
```

### 10.3 Test End-to-End Flow

1. **Submit Link** → Check link appears in dashboard
2. **View Metrics** → `curl https://logkeep.perdrizet.org/metrics`
3. **Check Grafana** → Verify dashboards show data
4. **Test Backup** → Run `./scripts/backup-db.sh`
5. **Monitor Alerts** → Stop a container, verify email received

## Rollback Procedure (If Needed)

If issues occur:

```bash
# Quick rollback to previous version
./scripts/rollback.sh

# Or manual rollback:
# 1. Check which slot is active
readlink /etc/nginx/conf.d/logkeep.conf

# 2. If green is active, switch back to blue
docker start logkeep-blue
docker exec logkeep-blue curl http://localhost:8000/health
sudo ln -sf /etc/nginx/conf.d/blue.conf /etc/nginx/conf.d/logkeep.conf
sudo systemctl reload nginx

# 3. Stop green
docker stop logkeep-green
```

## Troubleshooting

### Metrics Endpoint Not Working

```bash
# Check app is running
docker ps | grep logkeep-green

# Check logs
docker logs logkeep-green | grep -i metrics

# Test directly on container
docker exec logkeep-green curl http://localhost:8000/metrics
```

### Alertmanager Not Sending Emails

```bash
# Check Alertmanager config
docker exec logkeep-alertmanager cat /etc/alertmanager/alertmanager.yml

# Check SMTP credentials in .env.production
grep SMTP .env.production

# Check Alertmanager logs
docker logs logkeep-alertmanager | grep -i smtp
```

### Backup Script Fails

```bash
# Check PostgreSQL container is running
docker ps | grep postgres

# Check script permissions
ls -la scripts/backup-db.sh

# Run with debug
bash -x scripts/backup-db.sh
```

### Prometheus Can't Scrape App

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="logkeep-green")'

# Check network connectivity
docker exec logkeep-prometheus wget -O- http://logkeep-green:8000/metrics
```

## Success Criteria

✅ All containers running and healthy  
✅ Application accessible at https://logkeep.perdrizet.org  
✅ Metrics endpoint returns Prometheus data  
✅ Grafana shows application and container metrics  
✅ Alertmanager sends test email successfully  
✅ Backup script creates compressed database dump  
✅ Nginx serving both blue and green configs  
✅ No errors in any container logs  

## Next Steps

1. **Monitor for 24 hours** - Watch Grafana dashboards for anomalies
2. **Test alerts** - Verify critical alerts are received
3. **Backup verification** - Set up weekly restore tests
4. **Documentation** - Update runbook with any findings
5. **Staging usage** - Test future changes in staging first

## Support

If issues persist:
- Check [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- Review [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Check logs: `docker-compose -f docker-compose.prod.yml logs -f`
