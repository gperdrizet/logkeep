#!/bin/bash
# Verify staging environment setup on VPS

set -e

echo "=========================================="
echo "LogKeep Staging Environment Verification"
echo "=========================================="
echo ""

# Check if in correct directory
if [ ! -f "docker-compose.staging.yml" ]; then
    echo "❌ Error: Not in /opt/logkeep directory"
    exit 1
fi

# Check .env.staging exists
echo "1. Checking .env.staging file..."
if [ -f ".env.staging" ]; then
    echo "   ✅ .env.staging exists"
else
    echo "   ❌ .env.staging not found"
    echo "   Run: cp .env.staging.example .env.staging"
    exit 1
fi

# Check PostgreSQL container is running
echo ""
echo "2. Checking PostgreSQL container..."
if docker ps | grep -q logkeep-postgres; then
    echo "   ✅ PostgreSQL container is running"
else
    echo "   ❌ PostgreSQL container not running"
    exit 1
fi

# Check staging database exists
echo ""
echo "3. Checking staging database..."
if docker exec logkeep-postgres psql -U logkeep_admin -d postgres -lqt | cut -d \| -f 1 | grep -qw logkeep_staging; then
    echo "   ✅ logkeep_staging database exists"
else
    echo "   ⚠️  logkeep_staging database not found"
    echo "   Creating database..."
    docker exec logkeep-postgres psql -U logkeep_admin -d postgres -c "CREATE DATABASE logkeep_staging;"
    docker exec logkeep-postgres psql -U logkeep_admin -d postgres -c "GRANT ALL PRIVILEGES ON DATABASE logkeep_staging TO logkeep_admin;"
    echo "   ✅ Database created"
fi

# Check logkeep-network exists
echo ""
echo "4. Checking Docker network..."
if docker network ls | grep -q logkeep-network; then
    echo "   ✅ logkeep-network exists"
else
    echo "   ❌ logkeep-network not found"
    echo "   Run: docker network create logkeep-network"
    exit 1
fi

# Check if dev image exists locally
echo ""
echo "5. Checking Docker image..."
if docker images | grep -q "gperdrizet/logkeep.*dev"; then
    echo "   ✅ gperdrizet/logkeep:dev image found"
else
    echo "   ⚠️  gperdrizet/logkeep:dev image not found locally"
    echo "   Will pull from Docker Hub on first deployment"
fi

echo ""
echo "=========================================="
echo "✅ Staging environment ready!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Test deployment: docker-compose -f docker-compose.staging.yml up -d"
echo "  2. Check logs: docker logs logkeep-staging"
echo "  3. Test health: curl http://localhost:8003/health"
echo "  4. Push to dev branch to trigger CI/CD"
echo ""
