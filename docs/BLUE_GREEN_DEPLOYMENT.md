# Blue/Green Deployment System

## Overview

LogKeep uses a blue/green deployment strategy with system nginx and symlink-based configuration switching for zero-downtime deployments.

## Architecture Decision

After evaluating multiple approaches, we implemented **system nginx with symlink switching**:

### Approaches Evaluated

1. **sed-based config editing** ❌
   - Fragile string replacement
   - Prone to errors
   - Difficult to maintain

2. **Traefik with Docker labels** ❌
   - Problem: Docker doesn't support runtime label changes
   - Requires container recreation even with `docker update --label-add`
   - Added complexity without benefits

3. **Containerized nginx with symlinks** ❌
   - Problem: Docker bind mounts resolve symlinks at **container creation time**
   - Changing symlink requires container recreation (~3-5s)
   - Defeats the purpose of fast switching

4. **System nginx with symlinks** ✅ **FINAL SOLUTION**
   - Nginx runs directly on host system
   - Symlinks resolved at runtime by nginx process
   - `systemctl reload nginx` picks up changes instantly (~100ms)
   - Clean, simple, battle-tested approach

## How It Works

### Directory Structure

```
/etc/nginx/
├── conf.d/
│   ├── logkeep.conf -> ../logkeep-configs/blue.conf  # Symlink (active config)
│   ├── grafana.conf                                    # Static configs
│   └── perdrizet.conf
└── logkeep-configs/
    ├── blue.conf    # Upstream: 127.0.0.1:8001
    └── green.conf   # Upstream: 127.0.0.1:8002
```

### Container Setup

- **Blue container**: `logkeep-blue` on port `127.0.0.1:8001`
- **Green container**: `logkeep-green` on port `127.0.0.1:8002`
- Both containers always run, only one receives traffic

### Switching Process

1. **Current state**: `logkeep.conf -> blue.conf` (traffic to port 8001)
2. **Deploy new version to green container** (port 8002)
3. **Health check**: Verify green is healthy
4. **Switch symlink**: 
   ```bash
   sudo ln -sf /etc/nginx/logkeep-configs/green.conf /etc/nginx/conf.d/logkeep.conf
   ```
5. **Test config**: `sudo nginx -t`
6. **Reload nginx**: `sudo systemctl reload nginx` (~100ms)
7. **Traffic now flows to green** (port 8002)
8. **Observe**: Monitor for errors (60s in CI/CD, 300s manual)
9. **Cleanup**: Stop blue container (kept for rollback)

### Rollback

If deployment fails:
```bash
# Switch back to blue
sudo ln -sf /etc/nginx/logkeep-configs/blue.conf /etc/nginx/conf.d/logkeep.conf
sudo systemctl reload nginx

# Restart blue if stopped
docker-compose -f docker-compose.prod.yml up -d app-blue
```

## Deployment Script

Location: `scripts/deploy.sh`

### Usage

```bash
# Manual deployment with full observation (5 minutes)
./scripts/deploy.sh latest

# CI/CD deployment with shorter observation (1 minute)
OBSERVATION_PERIOD=60 ./scripts/deploy.sh latest

# Quick test deployment (30 seconds)
OBSERVATION_PERIOD=30 ./scripts/deploy.sh v1.2.3
```

### Key Features

- **Stdout/stderr separation**: All logs go to stderr, only return values to stdout
- **Progress indicators**: Dots during health checks, countdown during observation
- **Health checks**: Curl to `127.0.0.1:{port}/health` from host
- **Automatic rollback**: Reverts symlink if nginx config test fails
- **Container preservation**: Old container stopped but not removed for quick rollback

## CI/CD Integration

### GitHub Actions Workflow

File: `.github/workflows/deploy-production.yml`

```yaml
- name: Deploy to VPS
  run: |
    ssh $VPS_USER@$VPS_HOST << 'EOF'
      cd /opt/logkeep
      OBSERVATION_PERIOD=60 ./scripts/deploy.sh latest
    EOF
```

### Passwordless Sudo

Required for automation. Sudoers config in `config/sudoers.d/logkeep-deploy`:

```bash
# Install on VPS
sudo cp /opt/logkeep/config/sudoers.d/logkeep-deploy /etc/sudoers.d/
sudo chmod 0440 /etc/sudoers.d/logkeep-deploy
sudo visudo -c
```

Allows passwordless execution of:
- `nginx -t` (test configuration)
- `systemctl reload/restart/start/stop/status/is-active nginx`
- `ln -sf` (symlink creation)
- `readlink` (symlink verification)
- Config file copying

## Performance

- **Symlink switch**: < 1ms
- **Nginx config test**: ~50ms
- **Nginx reload**: ~100ms
- **Total switching time**: ~150ms
- **Container recreation time** (previous approach): 3-5 seconds

**Result**: 20-30x faster than container-based approaches

## Security Considerations

1. **Minimal sudo access**: Only specific commands with exact paths
2. **No shell access**: Sudoers rules don't allow arbitrary commands
3. **Config validation**: `nginx -t` always runs before reload
4. **Automatic rollback**: Failed configs revert immediately
5. **Container isolation**: App containers have no sudo access

## Troubleshooting

### Deployment hangs at health check
- Check container is running: `docker ps | grep logkeep`
- Check container logs: `docker logs logkeep-{blue|green}`
- Verify port binding: `netstat -tlnp | grep 800[12]`
- Test health endpoint: `curl http://127.0.0.1:8001/health`

### Nginx config test fails
- Check symlink: `readlink /etc/nginx/conf.d/logkeep.conf`
- Verify target exists: `ls -l /etc/nginx/logkeep-configs/`
- Test manually: `sudo nginx -t`
- Check nginx error log: `sudo tail -50 /var/log/nginx/error.log`

### Sudo password prompts in CI/CD
- Verify sudoers file: `sudo cat /etc/sudoers.d/logkeep-deploy`
- Check permissions: `ls -l /etc/sudoers.d/logkeep-deploy` (should be 0440)
- Validate syntax: `sudo visudo -c`
- Test command: `sudo systemctl is-active nginx` (should not prompt)

### Wrong container serving traffic
- Check symlink: `readlink /etc/nginx/conf.d/logkeep.conf`
- Check nginx config: `sudo nginx -T | grep 'proxy_pass.*127.0.0.1'`
- Verify containers: `docker ps --filter 'name=logkeep-'`
- Force reload: `sudo systemctl reload nginx`

## Future Enhancements

- [ ] Automated smoke tests during observation period
- [ ] Slack/email notifications on deployment events
- [ ] Deployment metrics and timing tracking
- [ ] Database migration handling
- [ ] Canary deployments (gradual traffic shift)
- [ ] Integration with monitoring/alerting

## References

- Deployment script: `scripts/deploy.sh`
- Sudoers config: `config/sudoers.d/logkeep-deploy`
- CI/CD workflow: `.github/workflows/deploy-production.yml`
- Nginx configs: `nginx/{blue,green}.conf`
