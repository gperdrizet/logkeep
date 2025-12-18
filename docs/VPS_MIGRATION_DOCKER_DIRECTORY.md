# VPS Migration Guide: Docker Directory Restructure

**Date:** December 18, 2025  
**Purpose:** Migrate VPS from flat structure to organized `docker/` directory structure

## What Changed

### Before:
```
/opt/logkeep/
├── docker-compose.yml
├── docker-compose.staging.yml
├── docker-compose.prod.yml
├── docker-compose.override.yml
├── .env
├── .env.staging
├── .env.production
└── ...
```

### After:
```
/opt/logkeep/
├── Makefile
├── docker/
│   ├── docker-compose.yml
│   ├── docker-compose.staging.yml
│   ├── docker-compose.prod.yml
│   ├── docker-compose.override.yml
│   ├── .env.example
│   ├── .env.staging
│   ├── .env.staging.example
│   ├── .env.production
│   └── .env.production.example
└── ...
```

## Prerequisites

Before starting migration, ensure `make` is installed:

```bash
# Check if make is installed
which make

# If not installed, install it
sudo apt update
sudo apt install make -y
```

## Migration Steps

### Step 1: Stop All Services

```bash
cd /opt/logkeep

# Stop staging
docker-compose -f docker-compose.staging.yml down

# Stop production (optional - can do rolling update instead)
docker-compose -f docker-compose.prod.yml stop app-green
```

**Note:** Keep blue running for zero-downtime migration.

### Step 2: Pull Latest Changes

```bash
git fetch origin
git checkout main
git pull origin main
```

This will bring in:
- New `docker/` directory with updated compose files
- New `Makefile`
- Updated scripts and GitHub Actions

### Step 3: Migrate Environment Files

```bash
# Create docker directory if not exists (should be in git)
mkdir -p docker

# Move your actual .env files (with secrets) to docker/ directory
mv .env.staging docker/.env.staging
mv .env.production docker/.env.production

# Verify files moved
ls -la docker/.env*
```

### Step 4: Restart Services with New Structure

**For Staging:**
```bash
# Using Makefile (recommended)
make staging

# Or using docker-compose directly
docker-compose --project-directory . -f docker/docker-compose.staging.yml up -d
```

**For Production (Rolling Update):**
```bash
# Option 1: Use deployment script (recommended)
./scripts/deploy.sh latest

# Option 2: Manual restart using Makefile
make prod

# Option 3: Direct docker-compose command
docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d
```

### Step 5: Verify Everything Works

```bash
# Check all containers
make ps

# Health checks
make health

# View logs
make staging-logs  # Ctrl+C to exit
make prod-logs     # Ctrl+C to exit
```

### Step 6: Clean Up Old Files (Optional)

```bash
# These should now be in docker/ directory
# Only delete if you've verified everything works!

# Don't run this unless you're sure!
# rm -f docker-compose.yml docker-compose.staging.yml docker-compose.prod.yml docker-compose.override.yml
```

## Rollback Plan

If something goes wrong:

```bash
cd /opt/logkeep

# Revert git changes
git checkout HEAD~1

# Restore old structure
# Your .env files are safe in docker/ directory, just move them back
mv docker/.env.staging .env.staging
mv docker/.env.production .env.production

# Restart with old structure
docker-compose -f docker-compose.staging.yml up -d
docker-compose -f docker-compose.prod.yml up -d app-blue
```

## Updated Commands Reference

### Old Commands → New Commands

| Old | New (Makefile) | New (Direct) |
|-----|----------------|--------------|
| `docker-compose up -d` | `make dev` | `docker-compose --project-directory . -f docker/docker-compose.yml up -d` |
| `docker-compose -f docker-compose.staging.yml up -d` | `make staging` | `docker-compose --project-directory . -f docker/docker-compose.staging.yml up -d` |
| `docker-compose -f docker-compose.prod.yml up -d` | `make prod` | `docker-compose --project-directory . -f docker/docker-compose.prod.yml up -d` |
| `docker-compose logs -f` | `make dev-logs` | `docker-compose --project-directory . -f docker/docker-compose.yml logs -f` |
| `./scripts/deploy.sh` | `make deploy` | `./scripts/deploy.sh latest` |

## Common Issues

### Issue: "docker-compose.yml not found"

**Solution:** You're in the wrong directory or forgot `--project-directory .`

```bash
cd /opt/logkeep  # Make sure you're in repo root
make staging     # Use Makefile (handles paths automatically)
```

### Issue: "Environment variables not loaded"

**Solution:** env_file paths are now relative to docker/ directory

Check that `.env.staging` and `.env.production` exist in `docker/` directory:
```bash
ls -la docker/.env*
```

### Issue: "Volume mount failed"

**Solution:** All volume paths now use `../` to reference parent directory

This is already fixed in the compose files. If you modified them, check that paths like:
- `./data` → `../data`
- `./logs` → `../logs`
- `./monitoring` → `../monitoring`

### Issue: "Containers can't find each other"

**Solution:** Network configuration unchanged, should work as before

If issues persist:
```bash
docker network ls
docker network inspect logkeep_logkeep-network
```

## Testing Checklist

After migration, verify:

- [ ] Staging accessible at https://staging.perdrizet.org
- [ ] Production accessible at https://logkeep.perdrizet.org
- [ ] Grafana accessible at https://grafana.perdrizet.org
- [ ] Database connections working
- [ ] LLM summarization working (check a link submission)
- [ ] Logs being collected by Loki
- [ ] Prometheus metrics being collected
- [ ] Health checks passing
- [ ] GitHub Actions can deploy successfully

```bash
# Quick verification script
curl -s https://staging.perdrizet.org/health
curl -s https://logkeep.perdrizet.org/health
curl -s https://grafana.perdrizet.org/api/health
```

## Benefits of New Structure

1. **Cleaner root directory** - All Docker config in one place
2. **Easier to understand** - Clear separation of concerns
3. **Simpler commands** - Use `make` instead of long docker-compose commands
4. **Better for new developers** - Self-documenting `make help`
5. **Consistent with standards** - Common pattern in mature projects

## Need Help?

If you encounter issues during migration:

1. Check container logs: `docker logs logkeep-staging` or `docker logs logkeep-blue`
2. Check compose file paths: `cat docker/docker-compose.staging.yml | grep "\.\."`
3. Verify env files: `ls -la docker/.env*`
4. Test health endpoints: `curl http://localhost:8003/health`

Contact: george@perdrizet.org

---

*Migration Script Version: 1.0*  
*Compatible with LogKeep commit: [current commit hash]*
