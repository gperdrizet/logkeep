# LogKeep - Docker Management Makefile
# Simplifies docker-compose commands for different environments

.PHONY: help dev staging prod logs clean setup health

# Docker directory
DOCKER_DIR := docker

# Default target - show help
help:
	@echo "================================================================"
	@echo "  LogKeep - Docker Environment Management"
	@echo "================================================================"
	@echo ""
	@echo "Development (Local):"
	@echo "  make dev          - Start local development environment"
	@echo "  make dev-logs     - View development logs (follow)"
	@echo "  make dev-down     - Stop development environment"
	@echo "  make dev-rebuild  - Rebuild and restart dev environment"
	@echo "  make dev-shell    - Shell access to app container"
	@echo ""
	@echo "Staging (VPS):"
	@echo "  make staging      - Start staging environment"
	@echo "  make staging-logs - View staging logs (follow)"
	@echo "  make staging-down - Stop staging environment"
	@echo "  make staging-shell - Shell access to staging container"
	@echo ""
	@echo "Production (VPS):"
	@echo "  make prod         - Start production environment"
	@echo "  make prod-logs    - View production logs (follow)"
	@echo "  make prod-down    - Stop production environment"
	@echo "  make prod-blue-logs  - View blue container logs"
	@echo "  make prod-green-logs - View green container logs"
	@echo ""
	@echo "Database:"
	@echo "  make db-backup    - Backup production database"
	@echo "  make db-restore   - Restore database from backup"
	@echo "  make db-shell     - PostgreSQL shell (production)"
	@echo "  make db-staging-shell - PostgreSQL shell (staging)"
	@echo ""
	@echo "Deployment (VPS):"
	@echo "  make deploy       - Deploy to production (blue/green)"
	@echo "  make rollback     - Rollback production deployment"
	@echo ""
	@echo "Utility:"
	@echo "  make setup        - Create .env files from templates"
	@echo "  make clean        - Stop all environments and remove volumes"
	@echo "  make ps           - Show running containers"
	@echo "  make logs         - View all container logs"
	@echo "  make health       - Check application health endpoints"
	@echo ""
	@echo "================================================================"

# ============================================================================
# Development Environment (Local Machine)
# ============================================================================

dev:
	@echo "[INFO] Starting development environment..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml up -d
	@echo "[OK] Development environment running"
	@echo "     App:      http://localhost:8000"
	@echo "     Postgres: localhost:5432"
	@echo "     Ollama:   http://localhost:11434"

dev-logs:
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml logs -f

dev-down:
	@echo "[INFO] Stopping development environment..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml down
	@echo "[OK] Development environment stopped"

dev-rebuild:
	@echo "[INFO] Rebuilding development environment..."
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml build --no-cache
	docker-compose -f $(DOCKER_DIR)/docker-compose.yml up -d
	@echo "[OK] Development environment rebuilt and running"

dev-shell:
	@echo "[INFO] Opening shell in app container..."
	docker exec -it logkeep /bin/bash

# ============================================================================
# Staging Environment (VPS)
# ============================================================================

staging:
	@echo "[INFO] Starting staging environment..."
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.staging -f $(DOCKER_DIR)/docker-compose.staging.yml up -d
	@sleep 5
	@echo "[OK] Staging environment running"
	@echo "     App:    http://localhost:8003"
	@echo "     Access: https://staging.perdrizet.org (basic auth required)"

staging-logs:
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.staging -f $(DOCKER_DIR)/docker-compose.staging.yml logs -f

staging-down:
	@echo "[INFO] Stopping staging environment..."
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.staging -f $(DOCKER_DIR)/docker-compose.staging.yml down
	@echo "[OK] Staging environment stopped"

staging-shell:
	@echo "[INFO] Opening shell in staging container..."
	docker exec -it logkeep-staging /bin/bash

# ============================================================================
# Production Environment (VPS)
# ============================================================================

prod:
	@echo "[INFO] Starting production environment..."
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.production -f $(DOCKER_DIR)/docker-compose.prod.yml up -d
	@echo "[OK] Production environment running"
	@echo "     Blue:    http://localhost:8001"
	@echo "     Green:   http://localhost:8002"
	@echo "     Access:  https://logkeep.perdrizet.org"
	@echo "     Grafana: https://grafana.perdrizet.org"

prod-logs:
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.production -f $(DOCKER_DIR)/docker-compose.prod.yml logs -f app-blue app-green

prod-down:
	@echo "[INFO] Stopping production environment..."
	docker-compose -p logkeep --env-file $(DOCKER_DIR)/.env.production -f $(DOCKER_DIR)/docker-compose.prod.yml down
	@echo "[OK] Production environment stopped"

prod-blue-logs:
	docker logs -f logkeep-blue

prod-green-logs:
	docker logs -f logkeep-green

# ============================================================================
# Database Management
# ============================================================================

db-backup:
	@echo "[INFO] Backing up database..."
	./scripts/backup-db.sh
	@echo "[OK] Database backup complete"

db-restore:
	@echo "[WARN] This will restore the database from backup"
	@read -p "Enter backup file path: " BACKUP_FILE; \
	./scripts/restore-db.sh "$$BACKUP_FILE"

db-shell:
	@echo "[INFO] Opening PostgreSQL shell (production database)..."
	docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep

db-staging-shell:
	@echo "[INFO] Opening PostgreSQL shell (staging database)..."
	docker exec -it logkeep-postgres psql -U logkeep_admin -d logkeep_staging

# ============================================================================
# Utility Commands
# ============================================================================

setup:
	@echo "[INFO] Creating .env files from templates..."
	@if [ ! -f docker/.env ]; then \
		cp docker/.env.example docker/.env; \
		echo "[OK] Created docker/.env from template"; \
		echo "[WARN] Please edit docker/.env with your secrets"; \
	else \
		echo "[WARN] docker/.env already exists, skipping..."; \
	fi

clean:
	@echo "[INFO] Cleaning all environments..."
	@read -p "This will remove all containers and volumes. Continue? [y/N] " -n 1 -r; \
	echo ""; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. down -v; \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.staging.yml down -v; \
		cd $(DOCKER_DIR) && docker-compose --project-directory .. -f docker-compose.prod.yml down -v; \
		echo "[OK] All environments cleaned"; \
	else \
		echo "[INFO] Cancelled"; \
	fi

ps:
	@echo "[INFO] Running containers:"
	@docker ps --filter "name=logkeep" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

logs:
	@echo "[INFO] Showing logs from all LogKeep containers..."
	docker logs --tail 50 -f $$(docker ps -q --filter "name=logkeep")

# ============================================================================
# Deployment (VPS Only)
# ============================================================================

deploy:
	@echo "[INFO] Deploying to production with blue/green strategy..."
	@if [ -f ./scripts/deploy.sh ]; then \
		./scripts/deploy.sh latest; \
	else \
		echo "[ERROR] deploy.sh script not found"; \
		exit 1; \
	fi

rollback:
	@echo "[INFO] Rolling back production deployment..."
	@if [ -f ./scripts/rollback.sh ]; then \
		./scripts/rollback.sh; \
	else \
		echo "[ERROR] rollback.sh script not found"; \
		exit 1; \
	fi

# ============================================================================
# Health Checks
# ============================================================================

health:
	@echo "[INFO] Checking application health..."
	@echo ""
	@echo "Development:"
	@curl -s http://localhost:8000/health 2>/dev/null && echo "" || echo "  [ERROR] Not running"
	@echo ""
	@echo "Staging:"
	@curl -s http://localhost:8003/health 2>/dev/null && echo "" || echo "  [ERROR] Not running"
	@echo ""
	@echo "Production (Blue):"
	@curl -s http://localhost:8001/health 2>/dev/null && echo "" || echo "  [ERROR] Not running"
	@echo ""
	@echo "Production (Green):"
	@curl -s http://localhost:8002/health 2>/dev/null && echo "" || echo "  [ERROR] Not running"

# ============================================================================
# Testing (not yet implemented)
# ============================================================================

# test:
# 	@echo "[INFO] Running tests..."
# 	@if [ -f requirements-dev.txt ]; then \
# 		pip install -r requirements-dev.txt; \
# 	fi
# 	pytest tests/ -v

# lint:
# 	@echo "[INFO] Running linters..."
# 	@black --check src/
# 	@flake8 src/
# 	@mypy src/
