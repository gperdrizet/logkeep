# LogKeep - Docker Management Makefile
# Simplifies docker-compose commands for different environments

.PHONY: help dev staging prod logs clean rebuild setup test

# Docker directory
DOCKER_DIR := docker

# Default target - show help
help:
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  LogKeep - Docker Environment Management"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@echo "Development (Local):"
	@echo "  make dev          - Start local development environment"
	@echo "  make dev-logs     - View development logs (follow)"
	@echo "  make dev-down     - Stop development environment"
	@echo "  make dev-rebuild  - Rebuild and restart dev environment"
	@echo ""
	@echo "Staging (VPS):"
	@echo "  make staging      - Start staging environment"
	@echo "  make staging-logs - View staging logs (follow)"
	@echo "  make staging-down - Stop staging environment"
	@echo ""
	@echo "Production (VPS):"
	@echo "  make prod         - Start production environment"
	@echo "  make prod-logs    - View production logs (follow)"
	@echo "  make prod-down    - Stop production environment"
	@echo ""
	@echo "Database:"
	@echo "  make db-backup    - Backup production database"
	@echo "  make db-restore   - Restore database from backup"
	@echo "  make db-shell     - PostgreSQL shell access"
	@echo ""
	@echo "Utility:"
	@echo "  make setup        - Create .env files from templates"
	@echo "  make clean        - Stop all environments and remove volumes"
	@echo "  make ps           - Show running containers"
	@echo "  make logs         - View all container logs"
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"

# ============================================================================
# Development Environment (Local Machine)
# ============================================================================

dev:
	@echo "🚀 Starting development environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. up -d
	@echo "✅ Development environment running"
	@echo "   App:      http://localhost:8000"
	@echo "   Postgres: localhost:5432"
	@echo "   Ollama:   http://localhost:11434"

dev-logs:
	cd $(DOCKER_DIR) && docker-compose --project-directory .. logs -f

dev-down:
	@echo "🛑 Stopping development environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. down
	@echo "✅ Development environment stopped"

dev-rebuild:
	@echo "🔨 Rebuilding development environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. build --no-cache
	cd $(DOCKER_DIR) && docker-compose --project-directory .. up -d
	@echo "✅ Development environment rebuilt and running"

dev-shell:
	@echo "🐚 Opening shell in app container..."
	docker exec -it logkeep /bin/bash

# ============================================================================
# Staging Environment (VPS)
# ============================================================================

staging:
	@echo "🚀 Starting staging environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.staging.yml up -d
	@sleep 5
	@echo "✅ Staging environment running"
	@echo "   App:      http://localhost:8003"
	@echo "   Access:   https://staging.perdrizet.org (basic auth required)"

staging-logs:
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.staging.yml logs -f

staging-down:
	@echo "🛑 Stopping staging environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.staging.yml down
	@echo "✅ Staging environment stopped"

staging-shell:
	@echo "🐚 Opening shell in staging container..."
	docker exec -it logkeep-staging /bin/bash

# ============================================================================
# Production Environment (VPS)
# ============================================================================

prod:
	@echo "🚀 Starting production environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.prod.yml up -d
	@echo "✅ Production environment running"
	@echo "   Blue:     http://localhost:8001"
	@echo "   Green:    http://localhost:8002"
	@echo "   Access:   https://logkeep.perdrizet.org"
	@echo "   Grafana:  https://grafana.perdrizet.org"

prod-logs:
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.prod.yml logs -f app-blue app-green

prod-down:
	@echo "🛑 Stopping production environment..."
	cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.prod.yml down
	@echo "✅ Production environment stopped"

prod-blue-logs:
	docker logs -f logkeep-blue

prod-green-logs:
	docker logs -f logkeep-green

# ============================================================================
# Database Management
# ============================================================================

db-backup:
	@echo "💾 Backing up database..."
	./scripts/backup-db.sh
	@echo "✅ Database backup complete"

db-restore:
	@echo "⚠️  This will restore the database from backup"
	@read -p "Enter backup file path: " BACKUP_FILE; \
	./scripts/restore-db.sh "$$BACKUP_FILE"

db-shell:
	@echo "🐚 Opening PostgreSQL shell..."
	docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep

db-staging-shell:
	@echo "🐚 Opening PostgreSQL shell (staging database)..."
	docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep_staging

# ============================================================================
# Utility Commands
# ============================================================================

setup:
	@echo "📝 Creating .env files from templates..."
	@if [ ! -f docker/.env ]; then \
		cp docker/.env.example docker/.env; \
		echo "✅ Created docker/.env from template"; \
		echo "⚠️  Please edit docker/.env with your secrets"; \
	else \
		echo "⚠️  docker/.env already exists, skipping..."; \
	fi

clean:
	@echo "🧹 Cleaning all environments..."
	@read -p "This will remove all containers and volumes. Continue? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. down -v; \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.staging.yml down -v; \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.prod.yml down -v; \
		echo "✅ All environments cleaned"; \
	else \
		echo "❌ Cancelled"; \
	fi

ps:
	@echo "📋 Running containers:"
	@docker ps --filter "name=logkeep" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

logs:
	@echo "📜 Showing logs from all LogKeep containers..."
	docker logs --tail 50 -f $$(docker ps -q --filter "name=logkeep")

# ============================================================================
# Deployment (VPS Only)
# ============================================================================

deploy:
	@echo "🚀 Deploying to production with blue/green strategy..."
	@if [ -f ./scripts/deploy.sh ]; then \
		./scripts/deploy.sh latest; \
	else \
		echo "❌ deploy.sh script not found"; \
		exit 1; \
	fi

rollback:
	@echo "🔄 Rolling back production deployment..."
	@if [ -f ./scripts/rollback.sh ]; then \
		./scripts/rollback.sh; \
	else \
		echo "❌ rollback.sh script not found"; \
		exit 1; \
	fi

# ============================================================================
# Health Checks
# ============================================================================

health:
	@echo "🏥 Checking application health..."
	@echo ""
	@echo "Development:"
	@curl -s http://localhost:8000/health 2>/dev/null && echo "" || echo "  ❌ Not running"
	@echo ""
	@echo "Staging:"
	@curl -s http://localhost:8003/health 2>/dev/null && echo "" || echo "  ❌ Not running"
	@echo ""
	@echo "Production (Blue):"
	@curl -s http://localhost:8001/health 2>/dev/null && echo "" || echo "  ❌ Not running"
	@echo ""
	@echo "Production (Green):"
	@curl -s http://localhost:8002/health 2>/dev/null && echo "" || echo "  ❌ Not running"

# ============================================================================
# Testing
# ============================================================================

test:
	@echo "🧪 Running tests..."
	@if [ -f requirements-dev.txt ]; then \
		pip install -r requirements-dev.txt; \
	fi
	pytest tests/ -v

lint:
	@echo "🔍 Running linters..."
	@black --check src/
	@flake8 src/
	@mypy src/
