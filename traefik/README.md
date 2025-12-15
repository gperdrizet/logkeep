# Traefik Configuration for LogKeep

This directory contains Traefik reverse proxy configuration for the LogKeep application.

## Overview

Traefik replaces nginx as the reverse proxy and provides:
- **Dynamic configuration** via Docker labels (no file editing required)
- **Automatic service discovery** from Docker containers
- **Zero-downtime deployments** by changing container labels
- **Built-in SSL/TLS** handling with certificate management
- **Blue/green traffic switching** without config file modifications

## Structure

```
traefik/
├── dynamic/
│   ├── tls.yml      # SSL certificate configuration
│   └── routes.yml   # Static routes (Grafana, redirects)
└── README.md        # This file
```

## How Traffic Switching Works

### Blue Container (Active)
```yaml
labels:
  - "traefik.enable=true"  # ← Receives traffic
  - "traefik.http.routers.logkeep-blue.rule=Host(`logkeep.perdrizet.org`)"
```

### Green Container (Inactive)
```yaml
labels:
  - "traefik.enable=false"  # ← No traffic
  - "traefik.http.routers.logkeep-green.rule=Host(`logkeep.perdrizet.org`)"
```

### Deployment Process
1. Deploy new version to inactive container (green)
2. Wait for health checks to pass
3. Switch traffic: `docker update --label-add traefik.enable=true logkeep-green`
4. Disable old: `docker update --label-add traefik.enable=false logkeep-blue`
5. Traefik automatically routes to new container (typically <2s)

## Configuration Files

### tls.yml
Defines SSL certificates for *.perdrizet.org wildcard domain.
- Uses existing Ionos certificates from `/etc/nginx/certs`
- TLS 1.2+ with secure cipher suites
- Default certificate store configuration

### routes.yml
Static routes that don't use Docker labels:
- **Grafana**: `grafana.perdrizet.org` → `logkeep-grafana:3000`
- **Root redirect**: `perdrizet.org` → `logkeep.perdrizet.org`

## Benefits Over Nginx

**Previous (Nginx):**
- Edit config file with sed
- Test configuration
- Reload nginx
- Risk of syntax errors
- Requires passwordless sudo

**Current (Traefik):**
- Change Docker label
- Traefik automatically reconfigures
- No file editing
- No sudo required
- Atomic operation

## Traefik Dashboard

Access Traefik dashboard (read-only) at:
- URL: `http://VPS_IP:8080/dashboard/` 
- Shows real-time routing configuration
- Displays active services and backends

## Troubleshooting

### Check Traefik logs
```bash
docker logs logkeep-traefik
```

### Verify container labels
```bash
docker inspect logkeep-blue | grep traefik.enable
docker inspect logkeep-green | grep traefik.enable
```

### Check active routes
```bash
curl http://localhost:8080/api/http/routers
```

### Manual traffic switch
```bash
# Enable green
docker update --label-add traefik.enable=true logkeep-green

# Disable blue
docker update --label-add traefik.enable=false logkeep-blue
```

## Certificate Management

Certificates are mounted from `/etc/nginx/certs` on the host:
- `perdrizet.org_fullchain.pem` - Certificate chain
- `perdrizet.org_starter_wildcard.key` - Private key

To update certificates:
1. Replace files in `/etc/nginx/certs`
2. Restart Traefik: `docker restart logkeep-traefik`

## Migration from Nginx

The nginx container is kept for Grafana and other services but LogKeep application traffic now flows through Traefik. Both can coexist safely on different ports or you can eventually migrate all services to Traefik.
