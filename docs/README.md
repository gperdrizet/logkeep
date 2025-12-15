# LogKeep Documentation Index

Welcome to the LogKeep production deployment documentation.

## Documentation overview

This directory contains complete documentation for deploying and operating LogKeep in production.

## Quick start

**First time deploying?** Start here:

1. Read **[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** - Understand the architecture
2. Follow **[DEPLOYMENT.md](DEPLOYMENT.md)** - Step-by-step deployment guide
3. Use **[OPERATIONS.md](OPERATIONS.md)** - Daily operations reference

## Documentation files

### Planning and architecture

**[DEPLOYMENT_PLAN.md](DEPLOYMENT_PLAN.md)** (60+ pages)
- Complete deployment architecture
- Technology stack details
- Blue/green deployment strategy
- Monitoring and observability setup
- Disaster recovery procedures
- Cost analysis
- Implementation timeline
- Success criteria

*Read this first to understand the big picture.*

### Deployment guide

**[DEPLOYMENT.md](DEPLOYMENT.md)** (25+ pages)
- Prerequisites checklist
- VPS initial setup
- DNS configuration
- Local machine setup (SSH tunnel)
- Application deployment steps
- Monitoring configuration
- CI/CD setup
- Data migration procedures
- Verification checklist
- Troubleshooting guide

*Follow this step-by-step during deployment.*

### Operations runbook

**[OPERATIONS.md](OPERATIONS.md)** (35+ pages)
- Quick reference commands
- Daily operations checklist
- User management
- Deployment procedures
- Monitoring and alerting
- Database operations
- Troubleshooting procedures
- Scaling guidelines
- Security practices
- Maintenance schedules

*Use this for day-to-day operations.*

### Implementation summary

**[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** (15+ pages)
- Complete list of files created
- Architecture summary
- Deployment flow overview
- Resource allocation
- Secrets checklist
- Verification procedures
- Success criteria

*Reference this to see what was built.*

## Configuration files

All configuration files are in the repository root and subdirectories:

### Application configuration
- `gunicorn.conf.py` - Production server config
- `Dockerfile` - Container build instructions
- `.env.production.example` - Environment variables template

### Docker compose
- `docker-compose.prod.yml` - Production stack
- `docker-compose.staging.yml` - Staging environment

### Nginx
- `nginx/logkeep.conf` - Main application proxy
- `nginx/grafana.conf` - Monitoring dashboard proxy
- `nginx/perdrizet.conf` - Root domain redirect

### Monitoring
- `monitoring/prometheus.yml` - Metrics collection
- `monitoring/alert-rules.yml` - Alert definitions
- `monitoring/grafana-datasources.yml` - Datasource config
- `monitoring/loki-config.yml` - Log aggregation
- `monitoring/promtail-config.yml` - Log shipping

### CI/CD
- `.github/workflows/build-and-push.yml` - Image building
- `.github/workflows/deploy-production.yml` - Production deployment
- `.github/workflows/deploy-staging.yml` - Staging deployment

### Scripts
- `scripts/setup-vps.sh` - VPS initial setup
- `scripts/deploy.sh` - Blue/green deployment
- `scripts/rollback.sh` - Quick rollback
- `scripts/setup-ssh-tunnel.sh` - Ollama tunnel setup
- `scripts/backup-db.sh` - Database backup
- `scripts/restore-db.sh` - Database restore
- `scripts/pull-backups.sh` - Sync backups to local

## Common tasks

### Initial deployment
```bash
# 1. On VPS
sudo bash scripts/setup-vps.sh
cd /opt/logkeep
git clone https://github.com/gperdrizet/logkeep.git .
cp .env.production.example .env.production
# Edit .env.production with secrets
docker-compose -f docker-compose.prod.yml up -d

# 2. On local machine
sudo bash scripts/setup-ssh-tunnel.sh
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for full instructions.

### Daily operations
```bash
# Check health
curl https://logkeep.perdrizet.org/health

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Create user
docker exec -it logkeep-blue python -m src.cli.admin create-user
```

See [OPERATIONS.md](OPERATIONS.md) for complete runbook.

### Deploy new version
```bash
# Automated (push to main)
git push origin main

# Manual
./scripts/deploy.sh latest
```

### Rollback
```bash
./scripts/rollback.sh
```

## Troubleshooting

### Quick diagnostics

```bash
# Check all services
docker-compose -f docker-compose.prod.yml ps

# Check resource usage
docker stats

# Check logs for errors
docker-compose -f docker-compose.prod.yml logs --tail 100 | grep -i error

# Test database
docker exec logkeep-postgres pg_isready -U logkeep_admin

# Test Ollama tunnel
ssh gatekeeper "curl -s http://localhost:11434/api/tags"
```

For comprehensive troubleshooting, see:
- [DEPLOYMENT.md - Troubleshooting](DEPLOYMENT.md#troubleshooting)
- [OPERATIONS.md - Troubleshooting](OPERATIONS.md#troubleshooting)

## Monitoring

### Access dashboards
- **Grafana:** https://grafana.perdrizet.org
- **Prometheus:** http://VPS_IP:9090 (internal only)

### Key metrics to watch
- CPU usage (target: < 70%)
- Memory usage (target: < 80%)
- Disk space (target: > 20% free)
- Response times (target: < 500ms)
- Error rates (target: < 1%)

See [OPERATIONS.md - Monitoring](OPERATIONS.md#monitoring--alerting) for details.

## Security

### Secrets management
- Generate with `scripts/setup-vps.sh`
- Store in `.env.production` (NOT committed)
- Also store in GitHub Actions secrets

### Regular security tasks
- [ ] Update OS monthly: `sudo apt update && sudo apt upgrade`
- [ ] Review access logs weekly
- [ ] Rotate secrets every 6-12 months
- [ ] Check for CVEs in dependencies

See [OPERATIONS.md - Security](OPERATIONS.md#security) for best practices.

## Scaling

### When to scale
- CPU consistently > 70%
- Memory consistently > 80%
- Response times > 1 second
- Error rates > 2%

### How to scale
1. **Vertical (more resources)**
   - Upgrade VPS plan in Ionos
   - Increase `GUNICORN_WORKERS` in `.env.production`
   - Restart application

2. **Horizontal (more services)**
   - Add Redis for caching
   - Add more Ollama instances on local machines

See [OPERATIONS.md - Scaling](OPERATIONS.md#scaling) for procedures.

## Getting help

### Documentation
- Read the relevant guide above
- Check troubleshooting sections
- Review implementation summary

### Community
- **GitHub Issues:** https://github.com/gperdrizet/logkeep/issues
- **Discussions:** https://github.com/gperdrizet/logkeep/discussions

### Support
- **Email:** george@perdrizet.org
- **GitHub:** @gperdrizet

## Contributing

Found an issue or improvement?

1. Create GitHub issue
2. Submit pull request
3. Update relevant documentation

## Success stories

After deploying, consider sharing:
- Performance metrics
- Lessons learned
- Customizations you made
- Issues you encountered and solved

This helps improve the documentation for others!

## Maintenance schedule

### Daily
- Check health endpoint
- Review Grafana dashboards
- Check for alerts

### Weekly
- Review logs for errors
- Verify backups successful
- Check resource usage trends

### Monthly
- OS security updates
- Database maintenance (VACUUM)
- Review and optimize queries
- Test disaster recovery

See [OPERATIONS.md - Maintenance](OPERATIONS.md#maintenance-windows) for details.

## Production readiness

Before going live, verify:
- [ ] All secrets configured
- [ ] DNS records created
- [ ] SSL certificates valid
- [ ] Monitoring dashboards working
- [ ] Alerts configured and tested
- [ ] Backups running automatically
- [ ] CI/CD pipeline working
- [ ] Disaster recovery tested
- [ ] Documentation reviewed

Use the checklist in [DEPLOYMENT.md - Verification](DEPLOYMENT.md#verification).

---

## Document versions

| Document | Version | Last Updated | Pages |
|----------|---------|--------------|-------|
| DEPLOYMENT_PLAN.md | 1.0 | 2025-12-14 | 60+ |
| DEPLOYMENT.md | 1.0 | 2025-12-14 | 25+ |
| OPERATIONS.md | 1.0 | 2025-12-14 | 35+ |
| IMPLEMENTATION_SUMMARY.md | 1.0 | 2025-12-14 | 15+ |

---

**Total Documentation:** 135+ pages | 6,370+ lines of code | 25 files created

**Status:** Production Ready
