# LogKeep production deployment plan

**Date:** December 14, 2025  
**Status:** Ready for Implementation  
**Repository:** gperdrizet/logkeep  
**Branch Strategy:** dev → main (production)

---

## Executive summary

This document outlines the complete production deployment architecture for LogKeep, a self-hosted link curation system with AI summarization. The deployment uses a split architecture with the web application and database hosted on a VPS, while GPU-accelerated AI processing remains on local hardware.

---

## Architecture overview

### Infrastructure components

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION ARCHITECTURE                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Internet → Nginx (SSL) → Blue/Green App Containers         │
│                            ↓                                │
│                      PostgreSQL                             │
│                      Prometheus                             │
│                      Grafana                                │
│                      Loki                                   │
│                            ↓                                │
│                   SSH Tunnel (reverse)                      │
│                            ↓                                │
│   Local Machine → Ollama (Docker) → Tesla P100 GPU          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Domain structure

| Domain | Purpose | Backend |
|--------|---------|---------|
| `logkeep.perdrizet.org` | Main application | App container (port 8001/8002) |
| `grafana.perdrizet.org` | Monitoring dashboards | Grafana (port 3000) |
| `staging.perdrizet.org` | Staging environment | Staging container (port 8003) |
| `perdrizet.org` | Root redirect | → logkeep.perdrizet.org |

### VPS Specifications (Ionos)

- **CPU:** 4 cores
- **RAM:** 8 GB
- **Storage:** 120 GB NVMe SSD
- **OS:** Ubuntu 22.04 LTS
- **Network:** Static IP with wildcard SSL certificate

### Local machine specifications

- **OS:** Ubuntu 24.04 LTS
- **GPU:** NVIDIA Tesla P100 (16GB VRAM)
- **Backup GPU:** NVIDIA GTX 1070 (emergency scaling)
- **Network:** Dynamic IP via ISP
- **SSH:** Port 4444, passwordless access to VPS as `gatekeeper`

---

## Technology stack

### Core application

| Component | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12 | Application runtime |
| **FastAPI** | 0.115.5 | Web framework |
| **Gunicorn** | 21.2.0 | WSGI server (9 workers) |
| **Uvicorn** | 0.32.1 | ASGI worker class |
| **PostgreSQL** | 16-alpine | Production database |
| **SQLAlchemy** | 2.0.36 | ORM |
| **Nginx** | Latest | Reverse proxy & SSL termination |

### AI/ML Components

| Component | Version | Purpose |
|-----------|---------|---------|
| **Ollama** | Latest | LLM inference server |
| **Llama 3.2 1B** | GGUF | Summarization model (807MB) |
| **Trafilatura** | 2.0.0 | Content extraction |

### Monitoring stack

| Component | Version | Purpose |
|-----------|---------|---------|
| **Prometheus** | Latest | Metrics collection |
| **Grafana** | Latest | Visualization & dashboards |
| **Loki** | Latest | Log aggregation |
| **Promtail** | Latest | Log shipping |
| **Node Exporter** | Latest | System metrics |
| **Postgres Exporter** | Latest | Database metrics |

### CI/CD & Deployment

| Component | Purpose |
|-----------|---------|
| **GitHub Actions** | Automated CI/CD pipeline |
| **Docker Hub** | Primary container registry (`gperdrizet/logkeep`) |
| **GitHub Container Registry** | Backup registry (`ghcr.io`) |
| **Docker Compose** | Service orchestration |

---

## Deployment configuration

### Application servers

**Gunicorn Configuration:**
- Workers: 9 `(2 × CPU_cores) + 1`
- Worker class: `uvicorn.workers.UvicornWorker`
- Timeout: 120 seconds
- Graceful timeout: 30 seconds
- Max requests: 1000 (worker recycling)
- Keepalive: 5 seconds

**Resource Allocation (per environment):**

| Environment | Workers | RAM Usage | CPU Usage |
|-------------|---------|-----------|-----------|
| Production (Blue) | 9 | ~1.5 GB | 4 cores |
| Production (Green) | 9 | ~1.5 GB | 4 cores (during deploy) |
| Staging | 4 | ~600 MB | 2 cores |
| PostgreSQL | - | ~512 MB | - |
| Monitoring Stack | - | ~1 GB | - |
| **Total Peak** | - | **~5.6 GB** | **4 cores** |

### Database configuration

**PostgreSQL:**
- Database: `logkeep` (production), `logkeep_staging` (staging)
- User: `logkeep_admin`
- Password: Auto-generated 32-byte secure string
- Connection pool: 5 connections per worker (max 10 overflow)
- Shared instances for cost efficiency

**Backup Strategy:**
- **Daily backups:** Retained for 7 days
- **Weekly backups:** Retained for 4 weeks (every Monday)
- **Monthly backups:** Retained for 6 months (1st of month)
- **Location:** Local machine (`/mnt/arkk/logkeep/backups/`)
- **Verification:** Weekly automated restore test
- **Sync:** Automated via rsync at 3 AM daily

### SSL/TLS Configuration

**Certificate Details:**
- Type: Wildcard certificate (`*.perdrizet.org`)
- Provider: Ionos
- Auto-renewal: Enabled
- Files:
  - Certificate: `/etc/nginx/certs/perdrizet.org_fullchain.pem`
  - Private key: `/etc/nginx/certs/perdrizet.org_starter_wildcard.key`
- Protocol: TLS 1.2, TLS 1.3
- Ciphers: Mozilla Intermediate profile

### SSH tunnel (Ollama connection)

**Tunnel Configuration:**
- Direction: Local machine → VPS (reverse tunnel)
- Local port: 11434 (Ollama)
- VPS endpoint: localhost:11434
- Authentication: Passwordless SSH key (`ssh gatekeeper`)
- Persistence: `autossh` with keepalive
- Monitoring: Health checks every 60 seconds

**Security:**
- SSH port: 4444 (non-standard)
- Key-based authentication only
- Tunnel-only access (no shell)
- Automatic reconnection on failure

---

## Blue/green deployment strategy

### Deployment flow

```
1. GitHub: Push to main branch
2. GitHub Actions: Build Docker image
3. Push to Docker Hub: gperdrizet/logkeep:latest
4. VPS: Pull new image
5. VPS: Start Green container (port 8002)
6. Health Check: Wait for Green to be healthy
7. Nginx: Switch traffic from Blue → Green
8. Monitor: Keep Blue running for 5 minutes
9. Cleanup: Stop Blue container
10. Tag: Mark Green as new Blue for next deployment
```

### Container naming convention

| Slot | Container Name | Port | Purpose |
|------|----------------|------|---------|
| Blue | `logkeep-blue` | 8001 | Currently active |
| Green | `logkeep-green` | 8002 | Newly deployed |
| Staging | `logkeep-staging` | 8003 | Testing environment |

### Zero-downtime process

1. **Pre-deployment:** Blue serves all traffic
2. **Green startup:** New version starts on port 8002
3. **Health checks:** Automated validation (30 seconds)
4. **Traffic switch:** Nginx updates upstream to port 8002
5. **Observation period:** Blue kept alive for 5 minutes
6. **Rollback capability:** Quick switch back to Blue if issues
7. **Cleanup:** Blue stopped after validation period

### Rollback procedure

**Immediate Rollback (< 5 minutes):**
```bash
# Nginx already knows Blue port, just switch back
sudo sed -i 's/8002/8001/' /etc/nginx/sites-enabled/logkeep.conf
sudo nginx -s reload
```

**Full Rollback (> 5 minutes):**
```bash
# Restart blue container if stopped
docker start logkeep-blue
# Wait for health check
# Switch nginx back to blue
```

---

## Monitoring and observability

### Metrics collection

**Prometheus Targets:**
- FastAPI application metrics (custom exporters)
- PostgreSQL metrics (postgres_exporter)
- System metrics (node_exporter)
- Docker metrics (cadvisor)
- Nginx metrics (nginx-prometheus-exporter)

**Grafana Dashboards:**
1. **Application Overview**
   - Request rate, response times, error rates
   - Active users, link submissions
   - Background task queues
2. **System Resources**
   - CPU, RAM, disk usage per service
   - Network I/O
   - Container health status
3. **Database Performance**
   - Query performance, connection pool usage
   - Table sizes, index efficiency
   - Transaction rates
4. **LLM Processing**
   - Ollama response times
   - GPU utilization (from local machine)
   - Summarization success/failure rates

### Alerting rules

**Email Alerts to:** george@perdrizet.org  
**SMTP:** Ionos (smtp.ionos.com:465)

| Alert | Threshold | Severity |
|-------|-----------|----------|
| High CPU usage | > 85% for 5 min | Warning |
| High memory usage | > 90% for 5 min | Critical |
| Container down | Any container stopped | Critical |
| Database connections | > 80% pool size | Warning |
| LLM timeout | > 90s response time | Warning |
| Disk space | < 10% free | Critical |
| SSL expiration | < 30 days | Warning |
| Backup failure | Any backup job failure | Critical |

### Log aggregation

**Loki Configuration:**
- Retention: 30 days
- Sources:
  - Docker container logs
  - Nginx access/error logs
  - PostgreSQL logs
  - System logs (journald)
- Query interface: Grafana Explore

---

## CI/CD Pipeline

### GitHub actions workflows

**1. Build and test (on push to dev):**
```yaml
- Checkout code
- Set up Python 3.12
- Install dependencies
- Run unit tests
- Run integration tests
- Build Docker image (dev tag)
- Push to Docker Hub (dev)
```

**2. Deploy to Staging (on push to main):**
```yaml
- Build Docker image (staging tag)
- Push to Docker Hub & GHCR
- SSH to VPS
- Pull staging image
- Restart staging container
- Run smoke tests
- Notify via email
```

**3. Deploy to Production (on push to main, after staging):**
```yaml
- Build Docker image (latest + git SHA tag)
- Push to Docker Hub & GHCR
- SSH to VPS
- Execute blue/green deployment script
- Health check new container
- Switch Nginx upstream
- Monitor for 5 minutes
- Clean up old container
- Notify via email
```

### Secrets required (GitHub)

| Secret Name | Purpose |
|-------------|---------|
| `DOCKER_HUB_USERNAME` | Docker Hub authentication |
| `DOCKER_HUB_TOKEN` | Docker Hub push access |
| `GHCR_TOKEN` | GitHub Container Registry access |
| `VPS_SSH_PRIVATE_KEY` | SSH deployment access |
| `VPS_HOST` | VPS IP/hostname |
| `VPS_USER` | SSH user (siderealyear) |

### Docker image tags

| Tag | Purpose | Lifecycle |
|-----|---------|-----------|
| `latest` | Current production | Overwritten on each deploy |
| `staging` | Staging environment | Overwritten on each staging deploy |
| `dev` | Development builds | Overwritten on each dev push |
| `{git-sha}` | Specific commit | Permanent, for rollbacks |
| `v{version}` | Release versions | Permanent, semantic versioning |

---

## Security considerations

### Network security

- **Firewall (VPS):**
  - Allow: 22 (SSH), 80 (HTTP), 443 (HTTPS)
  - Deny: All other inbound traffic
  - Docker networks isolated

- **SSH Hardening:**
  - Non-standard port: 4444
  - Key-based auth only
  - Root login disabled
  - Fail2ban configured

### Application security

- **Secrets Management:**
  - Environment variables via `.env`
  - Docker secrets for database credentials
  - No secrets in repository
  - GitHub Actions secrets for CI/CD

- **Database Security:**
  - Strong auto-generated passwords
  - Connection from localhost only
  - Regular security updates

- **Session Management:**
  - HTTP-only cookies
  - 7-day expiration
  - Bcrypt password hashing
  - Fernet encryption for GitHub tokens

### SSL/TLS Security

- TLS 1.2+ only
- Strong cipher suites (Mozilla Intermediate)
- HSTS enabled
- Certificate auto-renewal monitoring

---

## Operational procedures

### Daily operations

**Automated Tasks:**
- 2:00 AM - PostgreSQL backup (VPS)
- 3:00 AM - Backup sync to local machine
- Every hour - Prometheus metrics scraping
- Every 5 minutes - Health checks

**Manual Tasks:**
- Monitor Grafana dashboards
- Review alert emails
- Check application logs for errors

### Weekly operations

- Review backup success/failure
- Check disk space trends
- Review application performance metrics
- Update dependencies if security patches available

### Monthly operations

- Review monthly backup archive
- Analyze traffic patterns and scaling needs
- Security audit (check for CVEs)
- Review and optimize database queries

### Incident response

**Priority Levels:**

| Level | Response Time | Examples |
|-------|--------------|----------|
| P0 - Critical | Immediate | Application down, data loss |
| P1 - High | < 1 hour | Slow performance, partial outage |
| P2 - Medium | < 4 hours | Non-critical feature broken |
| P3 - Low | < 24 hours | Minor bugs, cosmetic issues |

**Response Procedures:**

1. **Incident Detection:**
   - Email alert received
   - User report
   - Monitoring dashboard shows issue

2. **Initial Assessment:**
   - Check Grafana dashboards
   - Review recent deployments
   - Check error logs in Loki

3. **Mitigation:**
   - If deployment-related: Rollback
   - If resource-related: Scale or restart services
   - If data-related: Restore from backup

4. **Root Cause Analysis:**
   - Document timeline
   - Identify root cause
   - Implement fix
   - Update runbooks

### Scaling procedures

**Vertical Scaling (Increase VPS Resources):**
1. Upgrade VPS plan in Ionos
2. Update `GUNICORN_WORKERS` in `.env`
3. Restart application containers
4. Monitor performance

**Horizontal Scaling (Add Services):**
- Not currently planned
- Could add: Redis for caching, additional Ollama instances

---

## Disaster recovery

### Backup strategy

**What is Backed Up:**
- PostgreSQL databases (production + staging)
- Application configuration files
- Nginx configuration
- SSL certificates (for reference)
- Docker Compose files

**Backup Locations:**
- Primary: VPS (`/opt/logkeep/backups/`)
- Secondary: Local machine (`/mnt/arkk/logkeep/backups/`)
- Future: Cloud storage (S3/Backblaze B2) for monthly archives

### Recovery scenarios

**Scenario 1: Application Container Failure**
- **RTO:** < 5 minutes
- **Procedure:** Restart container or rollback to previous version

**Scenario 2: Database Corruption**
- **RTO:** < 30 minutes
- **RPO:** Last daily backup (max 24 hours data loss)
- **Procedure:** Restore from most recent backup using `restore-db.sh`

**Scenario 3: VPS Complete Failure**
- **RTO:** < 4 hours
- **RPO:** Last daily backup
- **Procedure:**
  1. Provision new VPS
  2. Run `setup-vps.sh`
  3. Restore database from local backup
  4. Deploy application via CI/CD
  5. Update DNS if IP changed

**Scenario 4: Local Machine Failure (GPU/Ollama)**
- **RTO:** < 1 hour (emergency scaling to GTX 1070)
- **Procedure:**
  1. Update docker-compose to use GTX 1070
  2. Restart Ollama container
  3. Verify SSH tunnel
  4. Monitor performance (1070 slower than P100)

### Testing schedule

- **Backup Restoration:** Weekly automated test
- **Disaster Recovery Drill:** Quarterly manual test
- **Security Audit:** Annually

---

## Cost analysis

### Monthly operating costs (estimated)

| Item | Cost (USD) |
|------|------------|
| VPS (Ionos, 4 core/8GB) | $20-40 |
| Domain registration (perdrizet.org) | $1.50 |
| SSL certificate | $0 (included with Ionos) |
| Docker Hub (free tier) | $0 |
| GitHub (free tier) | $0 |
| Local electricity (GPU) | ~$15 |
| **Total** | **~$36.50-56.50/mo** |

### Cost optimization opportunities

- Monitor actual resource usage (may downsize VPS after initial period)
- Consider dedicated GPU hosting if local bandwidth becomes issue
- Evaluate free tier limits on monitoring tools

---

## Implementation timeline

### Phase 1: Infrastructure setup (Day 1-2)

- [ ] Clean VPS (remove old configs)
- [ ] Run `setup-vps.sh`
- [ ] Configure Docker & Docker Compose
- [ ] Set up secrets and environment variables
- [ ] Configure Nginx with SSL
- [ ] Test basic connectivity

### Phase 2: Application deployment (Day 2-3)

- [ ] Build and push Docker image
- [ ] Deploy PostgreSQL
- [ ] Run database migration from SQLite
- [ ] Deploy application container
- [ ] Test application functionality
- [ ] Set up staging environment

### Phase 3: SSH Tunnel & Ollama (Day 3)

- [ ] Configure reverse SSH tunnel
- [ ] Test Ollama connectivity from VPS
- [ ] Verify GPU acceleration
- [ ] Test summarization workflow

### Phase 4: Monitoring setup (Day 3-4)

- [ ] Deploy Prometheus, Grafana, Loki
- [ ] Configure dashboards
- [ ] Set up alert rules
- [ ] Test email notifications
- [ ] Create DNS record for grafana.perdrizet.org

### Phase 5: CI/CD Pipeline (Day 4-5)

- [ ] Create GitHub Actions workflows
- [ ] Configure secrets in GitHub
- [ ] Test build pipeline
- [ ] Test staging deployment
- [ ] Test production deployment
- [ ] Verify rollback procedure

### Phase 6: Backup and DR (Day 5)

- [ ] Set up backup scripts on VPS
- [ ] Set up backup sync on local machine
- [ ] Test backup restoration
- [ ] Document recovery procedures

### Phase 7: Testing and validation (Day 6-7)

- [ ] End-to-end functionality testing
- [ ] Load testing with multiple users
- [ ] Verify blue/green deployments
- [ ] Test disaster recovery scenarios
- [ ] Performance tuning

### Phase 8: Documentation and launch (Day 7)

- [ ] Complete operational runbooks
- [ ] Create user onboarding materials
- [ ] Generate invite codes for test users
- [ ] Soft launch with limited invites
- [ ] Monitor closely for first week

---

## Success criteria

### Technical metrics

- [ ] Application uptime: > 99.5%
- [ ] Average response time: < 500ms
- [ ] Summarization success rate: > 95%
- [ ] Zero-downtime deployments working
- [ ] Backups successful 100% of time
- [ ] Alert system functioning correctly

### User experience metrics

- [ ] Link submission < 2 seconds
- [ ] Summary generation < 30 seconds
- [ ] Mobile-responsive UI working
- [ ] Dark mode functioning
- [ ] No user-reported critical bugs

### Operational metrics

- [ ] Monitoring dashboards accessible
- [ ] Logs searchable in Grafana
- [ ] Deployment time < 5 minutes
- [ ] Rollback time < 2 minutes
- [ ] Documentation complete and accurate

---

## Maintenance windows

**Planned Maintenance:**
- **When:** 2nd Sunday of each month, 2-4 AM UTC
- **Duration:** Up to 2 hours
- **Activities:**
  - OS security updates
  - Database maintenance (VACUUM, ANALYZE)
  - Log rotation
  - SSL certificate renewal (if needed)
  - Performance optimization

**Emergency Maintenance:**
- Critical security patches: Apply immediately
- Notify users via GitHub issues or Discord

---

## Contact and escalation

**Primary Administrator:**
- Name: George Perdrizet
- Email: george@perdrizet.org
- GitHub: @gperdrizet

**Service Providers:**
- **VPS:** Ionos support
- **Domain/SSL:** Ionos support
- **ISP:** Local ISP support desk

---

## Appendix

### Useful commands

**VPS Management:**
```bash
# Check all services
docker-compose ps

# View logs
docker-compose logs -f app-blue

# Restart application
docker-compose restart app-blue

# Check resource usage
docker stats

# Manual deployment
./scripts/deploy.sh
```

**Database Management:**
```bash
# Backup database
./scripts/backup-db.sh

# Restore database
./scripts/restore-db.sh /path/to/backup.sql.gz

# Access database
docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep
```

**SSH Tunnel Management:**
```bash
# Check tunnel status (local machine)
systemctl status logkeep-tunnel

# Restart tunnel
systemctl restart logkeep-tunnel

# Test ollama connectivity
curl http://localhost:11434/api/tags
```

### File locations

**VPS:**
- Application: `/opt/logkeep/`
- Backups: `/opt/logkeep/backups/`
- Logs: `/opt/logkeep/logs/`
- Nginx config: `/etc/nginx/sites-available/`
- SSL certs: `/etc/nginx/certs/`
- Secrets: `/opt/logkeep/secrets/`

**Local Machine:**
- Repository: `/mnt/arkk/logkeep/`
- Backups: `/mnt/arkk/logkeep/backups/`
- Ollama data: `/mnt/arkk/logkeep/ollama_models/`

---

## Document control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-14 | George Perdrizet | Initial deployment plan |

**Review Schedule:** Quarterly or after major changes

**Approval:** Ready for implementation

---

*End of Deployment Plan*

