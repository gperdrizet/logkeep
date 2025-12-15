# LogKeep operations runbook

Day-to-day operations guide for managing LogKeep in production.

## Quick reference

### Common commands

```bash
# Check all service status
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Restart a service
docker-compose -f docker-compose.prod.yml restart app-blue

# Deploy new version
./scripts/deploy.sh latest

# Rollback deployment
./scripts/rollback.sh

# Database backup
./scripts/backup-db.sh

# View SSH tunnel status
sudo systemctl status logkeep-tunnel
```

### Key urls

- **Application:** https://logkeep.perdrizet.org
- **Monitoring:** https://grafana.perdrizet.org
- **Prometheus:** http://VPS_IP:9090 (internal)

---

## Daily operations

### Morning checklist

1. **Check Application Health**
```bash
curl -f https://logkeep.perdrizet.org/health
```

2. **Review Grafana Dashboards**
- Open Grafana
- Check CPU, memory, disk usage
- Review error rates
- Check response times

3. **Check for Alerts**
- Review email inbox for alert notifications
- Check Grafana alert history

4. **Verify Backups**
```bash
# Check latest backup
ls -lh /opt/logkeep/backups/ | tail -5

# On local machine, verify sync
ls -lh /mnt/arkk/logkeep/backups/ | tail -5
```

5. **Review Logs**
```bash
# Check for errors in last 24 hours
docker-compose -f docker-compose.prod.yml logs --since 24h | grep -i error

# Check nginx logs
sudo tail -100 /var/log/nginx/logkeep-error.log
```

---

## User management

### Create new user

```bash
# Interactive mode
docker exec -it logkeep-blue python -m src.cli.admin create-user

# Command line
docker exec logkeep-blue python -m src.cli.admin create-user \
    --username newuser \
    --email newuser@example.com
```

### Create admin user

```bash
docker exec logkeep-blue python -m src.cli.admin create-user \
    --username admin2 \
    --email admin2@example.com \
    --admin
```

### Generate invite code

```bash
docker exec logkeep-blue python -m src.cli.admin create-invite \
    --email invitee@example.com \
    --expires-days 7
```

### List users

```bash
docker exec logkeep-blue python -m src.cli.admin list-users
```

### Deactivate user

```bash
docker exec logkeep-blue python -m src.cli.admin deactivate-user \
    --username baduser
```

### Reset user password

```bash
docker exec logkeep-blue python -m src.cli.admin reset-password \
    --username username
```

---

## Deployments

### Standard deployment

```bash
cd /opt/logkeep

# Deploy latest
./scripts/deploy.sh latest

# Or deploy specific version
./scripts/deploy.sh v1.2.3
```

The deployment script will:
1. Pull new Docker image
2. Start new container (green slot)
3. Wait for health checks (30 seconds)
4. Switch Nginx traffic to new container
5. Observe for 5 minutes
6. Stop old container

### Rollback

If issues are detected:

```bash
# Quick rollback (within 5 minutes)
./scripts/rollback.sh

# Manual rollback (after cleanup)
# 1. Start old container
docker start logkeep-blue

# 2. Wait for health
docker exec logkeep-blue curl http://localhost:8000/health

# 3. switch nginx
sudo nano /etc/nginx/conf.d/logkeep.conf
# Change server line to point to old container
sudo nginx -s reload
```

### Staging deployment

```bash
# Deploy to staging
docker-compose -f docker-compose.staging.yml pull
docker-compose -f docker-compose.staging.yml up -d

# Test staging
curl http://localhost:8003/health

# View staging logs
docker logs -f logkeep-staging
```

---

## Monitoring & Alerting

### Check system resources

```bash
# CPU usage
top

# Memory
free -h

# Disk space
df -h

# Docker stats
docker stats

# Per-container stats
docker stats logkeep-blue logkeep-postgres
```

### Query prometheus

```bash
# CPU usage
curl 'http://localhost:9090/api/v1/query?query=node_cpu_seconds_total'

# Memory usage
curl 'http://localhost:9090/api/v1/query?query=node_memory_MemAvailable_bytes'

# Database connections
curl 'http://localhost:9090/api/v1/query?query=pg_stat_activity_count'
```

### Search logs in loki

In Grafana → Explore → Loki:

```logql
# All logs from app
{container_name="logkeep-blue"}

# Errors only
{container_name="logkeep-blue"} |= "ERROR"

# Nginx errors
{job="nginx", log_type="error"}

# Database query logs
{container_name="logkeep-postgres"} |= "SELECT"
```

### Configure new alert

1. In Grafana, go to Alerting → Alert Rules
2. Click "New alert rule"
3. Set query (e.g., high error rate)
4. Set evaluation interval
5. Add notification channel
6. Save and test

---

## Database operations

### Database backup

```bash
# Manual backup
/opt/logkeep/scripts/backup-db.sh

# Verify backup
ls -lh /opt/logkeep/backups/
```

### Restore database

```bash
# From latest backup
/opt/logkeep/scripts/restore-db.sh /opt/logkeep/backups/logkeep_YYYYMMDD_HHMMSS.sql.gz

# Test restore in staging
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep_staging < backup.sql
```

### Database console access

```bash
# PostgreSQL shell
docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep

# Common queries
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM links;
SELECT COUNT(*) FROM tags;
SELECT * FROM users ORDER BY created_at DESC LIMIT 10;
```

### Database maintenance

```bash
# Vacuum and analyze
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "VACUUM ANALYZE;"

# Check database size
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
SELECT pg_size_pretty(pg_database_size('logkeep')) AS size;"

# Check table sizes
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::text)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(tablename::text) DESC;"
```

---

## Troubleshooting

### Application not responding

**Symptoms:** Can't access application, 502/504 errors

**Steps:**
1. Check container status
```bash
docker ps | grep logkeep
```

2. Check container logs
```bash
docker logs --tail 100 logkeep-blue
```

3. Check health endpoint
```bash
docker exec logkeep-blue curl http://localhost:8000/health
```

4. Restart container if needed
```bash
docker restart logkeep-blue
```

5. If still not working, check database
```bash
docker exec logkeep-postgres pg_isready
```

### High CPU usage

**Symptoms:** CPU > 85%, slow response times

**Steps:**
1. Check which process is using CPU
```bash
docker stats
top
```

2. Check for long-running queries
```bash
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 seconds'
ORDER BY duration DESC;"
```

3. If application is the culprit, check logs for errors
```bash
docker logs logkeep-blue | tail -500
```

4. Consider scaling workers (see Scaling section)

### High memory usage

**Symptoms:** Memory > 90%, OOM errors

**Steps:**
1. Identify memory hogs
```bash
docker stats --no-stream --format "table {{.Name}}\t{{.MemUsage}}"
```

2. Check for memory leaks in application
```bash
docker exec logkeep-blue ps aux
```

3. Restart high-memory containers
```bash
docker restart logkeep-blue
```

4. If persistent, consider reducing worker count or upgrading VPS

### Disk space full

**Symptoms:** < 10% disk space, alerts firing

**Steps:**
1. Check disk usage
```bash
df -h
du -sh /opt/logkeep/*
du -sh /var/lib/docker/volumes/*
```

2. Clean Docker images and volumes
```bash
docker system prune -a --volumes
```

3. Rotate old logs
```bash
sudo logrotate -f /etc/logrotate.conf
```

4. Archive old backups
```bash
# Move to local machine
rsync -avz /opt/logkeep/backups/ siderealyear@local:/mnt/arkk/logkeep/backups/
# Delete old backups on VPS
find /opt/logkeep/backups/ -type f -mtime +30 -delete
```

### Ollama not working

**Symptoms:** Summarization fails, "connection refused"

**Steps:**
1. Check SSH tunnel (on local machine)
```bash
sudo systemctl status logkeep-tunnel
```

2. Restart tunnel
```bash
sudo systemctl restart logkeep-tunnel
```

3. Test Ollama locally
```bash
curl http://localhost:11434/api/tags
```

4. Test from VPS
```bash
ssh gatekeeper "curl http://localhost:11434/api/tags"
```

5. Check Ollama container on local machine
```bash
docker ps | grep ollama
docker logs ollama
```

### SSL certificate errors

**Symptoms:** Browser shows "Not Secure", certificate warnings

**Steps:**
1. Check certificate expiration
```bash
openssl x509 -in /etc/nginx/certs/perdrizet.org_fullchain.pem -noout -dates
```

2. Check Nginx config
```bash
sudo nginx -t
```

3. Check Nginx error logs
```bash
sudo tail -f /var/log/nginx/error.log
```

4. If certificate expired, renew via Ionos and copy new files to VPS

### Database connection pool exhausted

**Symptoms:** "Too many connections", slow queries

**Steps:**
1. Check active connections
```bash
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'logkeep';"
```

2. Kill idle connections
```bash
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'logkeep' AND state = 'idle' AND now() - state_change > interval '5 minutes';"
```

3. Increase connection pool in .env.production
```bash
# Edit db_pool_size and db_max_overflow
nano /opt/logkeep/.env.production
# Restart application
docker restart logkeep-blue
```

---

## Scaling

### Scale worker processes

Edit `.env.production`:
```bash
# Increase workers (e.g., for 8 cores)
GUNICORN_WORKERS=17  # (2 × 8) + 1
```

Restart application:
```bash
docker restart logkeep-blue
```

Monitor resource usage in Grafana.

### Upgrade VPS resources

1. Log into Ionos control panel
2. Upgrade VPS plan (more CPU/RAM)
3. Wait for upgrade to complete
4. Update worker count as above
5. Test deployment

### Add redis caching (Future)

If response times are slow:

1. Add Redis to `docker-compose.prod.yml`
2. Update application to use Redis for caching
3. Configure cache TTLs in `.env.production`

---

## Security

### Update dependencies

```bash
# On local machine
cd /mnt/arkk/logkeep
git pull
pip list --outdated

# Update requirements.txt
pip install --upgrade package-name
pip freeze > requirements.txt

# Commit and push
git add requirements.txt
git commit -m "Update dependencies"
git push
```

### OS security updates

```bash
# On VPS
sudo apt update
sudo apt upgrade -y

# Reboot if kernel updated
sudo reboot
```

### Review access logs

```bash
# Check for suspicious activity
sudo tail -1000 /var/log/nginx/logkeep-access.log | grep -E '(401|403|404|500)'

# Check failed login attempts (if implemented in app)
docker exec logkeep-blue python -m src.cli.admin audit-logs --failed-logins
```

### Rotate secrets

Every 6-12 months:

1. Generate new secrets
2. Update `.env.production`
3. Restart application
4. Update GitHub Actions secrets
5. Test deployments

---

## Maintenance windows

### Planned maintenance

Schedule: 2nd Sunday of each month, 2-4 AM UTC

**Pre-maintenance:**
1. Notify users (if applicable)
2. Create full backup
3. Document current state

**During maintenance:**
1. OS updates
2. Docker updates
3. Database VACUUM
4. Log rotation
5. Certificate checks

**Post-maintenance:**
1. Verify all services running
2. Run health checks
3. Monitor for 1 hour

### Emergency maintenance

For critical security patches:

1. Test patch in staging
2. Create backup
3. Apply patch to production
4. Monitor closely
5. Document in runbook

---

## Performance optimization

### Database query optimization

```bash
# Enable query logging
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
ALTER DATABASE logkeep SET log_min_duration_statement = 1000;"

# Find slow queries
docker logs logkeep-postgres | grep "duration:"

# Add indexes if needed
docker exec logkeep-postgres psql -U logkeep_admin -d logkeep -c "
CREATE INDEX IF NOT EXISTS idx_links_user_id ON links(user_id);
CREATE INDEX IF NOT EXISTS idx_links_created_at ON links(created_at);"
```

### Application performance

```bash
# Check response times in Prometheus
curl 'http://localhost:9090/api/v1/query?query=http_request_duration_seconds'

# Profile application (add py-spy if needed)
docker exec logkeep-blue py-spy top --pid 1
```

---

## Contact & Escalation

**Primary Administrator:** George Perdrizet  
**Email:** george@perdrizet.org  
**GitHub:** @gperdrizet

**Service Providers:**
- **VPS:** Ionos support
- **Domain:** Ionos support
- **ISP:** Local ISP support

**Escalation Path:**
1. Check this runbook
2. Search GitHub issues
3. Check application logs and monitoring
4. Contact service provider if infrastructure issue
5. Create GitHub issue for application bugs

---

## Useful links

- **GitHub Repository:** https://github.com/gperdrizet/logkeep
- **Docker Hub:** https://hub.docker.com/r/gperdrizet/logkeep
- **Deployment Plan:** `docs/DEPLOYMENT_PLAN.md`
- **Deployment Guide:** `docs/DEPLOYMENT.md`

---

**Last Updated:** December 14, 2025  
**Version:** 1.0

