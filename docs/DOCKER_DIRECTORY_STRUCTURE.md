# Docker Directory Structure - Reference

## Overview

All Docker Compose and environment files are now located in the `docker/` subdirectory for better organization.

## Directory Layout

```
logkeep/
├── docker/                          # All Docker configuration files
│   ├── docker-compose.yml           # Development environment
│   ├── docker-compose.override.yml  # Dev overrides (live reload)
│   ├── docker-compose.staging.yml   # Staging environment
│   ├── docker-compose.prod.yml      # Production environment
│   ├── .env                         # Dev environment variables
│   ├── .env.staging                 # Staging environment variables
│   └── .env.production              # Production environment variables
├── monitoring/                      # Monitoring config files (Prometheus, Grafana, etc.)
├── secrets/                         # Database secrets
├── src/                            # Application source code
├── data/                           # Application data (mounted volume)
├── logs/                           # Application logs (mounted volume)
├── scripts/                        # Deployment and management scripts
├── Makefile                        # Simplified commands
└── Dockerfile                      # Application container definition
```

## How It Works

### Command Pattern

All docker-compose commands follow this pattern:

```bash
cd docker && docker-compose --project-directory .. -f <compose-file> <command>
```

**Why this pattern?**
- `cd docker` - Change into docker directory where compose files live
- `--project-directory ..` - Set project root to parent directory for volume resolution
- `-f <compose-file>` - Specify which compose file to use

### Path Resolution Rules

**1. Volume Mounts in Compose Files**
Use `../` to reference project root directories:

```yaml
volumes:
  - ../src:/app/src              # Maps logkeep/src to /app/src
  - ../data:/app/data            # Maps logkeep/data to /app/data
  - ../monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
```

**2. Environment Files**
Use `docker/.env.*` format:

```yaml
env_file:
  - docker/.env.production       # Resolves from project root (set by --project-directory ..)
```

**3. Secrets**
Use `../secrets/` format:

```yaml
secrets:
  postgres_password:
    file: ../secrets/postgres_password.txt
```

## Usage

### Makefile (Recommended)

```bash
make dev          # Start development environment
make staging      # Start staging environment
make prod         # Start production environment
make logs         # View logs
make clean        # Stop and clean up
make help         # Show all commands
```

### Manual Docker Compose

```bash
# Development
cd docker && docker-compose --project-directory .. up -d

# Staging
cd docker && docker-compose --project-directory .. -f docker-compose.staging.yml up -d

# Production
cd docker && docker-compose --project-directory .. -f docker-compose.prod.yml up -d

# View logs
cd docker && docker-compose --project-directory .. logs -f

# Stop environment
cd docker && docker-compose --project-directory .. down
```

### Deployment Scripts

The `scripts/deploy.sh` script uses the same pattern:

```bash
cd docker && docker-compose --project-directory .. -f docker-compose.prod.yml up -d app-blue
```

### GitHub Actions

Workflows also use the consistent pattern:

```bash
cd docker && \
docker-compose --project-directory .. -f docker-compose.staging.yml down && \
docker-compose --project-directory .. -f docker-compose.staging.yml up -d
```

## Common Mistakes to Avoid

### ❌ Wrong: Using project-directory without cd

```bash
# Don't do this - paths won't resolve correctly
docker-compose --project-directory . -f docker/docker-compose.yml up
```

### ❌ Wrong: Inconsistent path prefixes

```yaml
# Don't mix ./ and ../ incorrectly
volumes:
  - ./monitoring/config.yml:/etc/config.yml    # Wrong - looks in docker/monitoring/
  - ../monitoring/config.yml:/etc/config.yml   # Correct - looks in logkeep/monitoring/
```

### ❌ Wrong: Omitting docker/ prefix in env_file

```yaml
# Don't do this
env_file:
  - .env.production              # Won't find the file

# Do this
env_file:
  - docker/.env.production       # Correct
```

## Verification Checklist

When making changes, ensure:

- [ ] All volume paths in compose files use `../` to reference project root
- [ ] All env_file paths use `docker/.env.*` format
- [ ] All secrets use `../secrets/` format  
- [ ] Makefile uses `cd $(DOCKER_DIR) && docker-compose --project-directory ..`
- [ ] Scripts use `cd docker && docker-compose --project-directory ..`
- [ ] GitHub Actions use the same pattern
- [ ] Local testing with `make dev` works
- [ ] VPS deployments work with the same commands

## Benefits of This Structure

1. **Organized** - All Docker config in one place
2. **Consistent** - Same command pattern everywhere
3. **Portable** - Works locally and on VPS identically
4. **Clear** - Obvious where to find configuration
5. **Maintainable** - Single source of truth for paths
