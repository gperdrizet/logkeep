# LogKeep
[![Build and Push Docker Image](https://github.com/gperdrizet/logkeep/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/build-and-push.yml)
[![Deploy to Staging](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml)
[![Deploy to Production](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml)

Link curation with AI summarization and LogSeq integration via GitHub.

## Overview

LogKeep helps you capture and curate web content from your phone. Submit a link, select tags, and the system extracts the title, generates an AI summary, and commits a formatted entry to your GitHub-hosted journal. No manual typing of titles or copy-pasting required. LogKeep can also add extracted content to your LogSeq graph via a GitHub repository.

## Features

- **Mobile-first UI** - Quick submission, minimal typing
- **AI summarization** - Optional GPU-accelerated article summaries via Ollama
- **Async processing** - Background extraction and GitHub commits
- **Tag management** - Personal collections with autocomplete
- **Multi-user** - Invite-only with encrypted GitHub token storage
- **Analytics** - Score and tag usage histograms
- **Admin CLI** - User, invite, and tag management
- **Blue/Green Deployment** - Zero-downtime deployments with automated health checks
- **CI/CD Pipeline** - Automated staging and production deployments via GitHub Actions

## Quick Start

### Prerequisites

- Docker & Docker Compose
- GitHub PAT with `repo` scope
- Logseq graph in GitHub repo
- (Optional) NVIDIA GPU + nvidia-container-toolkit for summarization

### Docker Deployment

```bash
# Clone and configure
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep
cp docker/.env.example docker/.env

# Generate secrets
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"  # SESSION_SECRET

# Edit docker/.env with secrets and LLM settings (LLM_ENABLED=true for summarization)
nano docker/.env

# Start services
make dev

# Initialize
docker exec -it logkeep python -m src.cli.admin init-db
docker exec -it logkeep python -m src.cli.admin create-user
docker exec -it logkeep python -m src.cli.admin create-invite --count 5
```

Access at `http://localhost:8000`

### GPU Summarization

Requires NVIDIA GPU with drivers and nvidia-container-toolkit:

```bash
# Install nvidia-container-toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Enable in docker/.env
LLM_ENABLED=true
LLM_BASE_URL=http://ollama:11434
```

The Ollama container will download the model (~807MB) on first start.

## Configuration

Key environment variables (`docker/.env`):

```bash
# Required
SESSION_SECRET=<32+ chars>
ENCRYPTION_KEY=<Fernet key>

# LLM (optional)
LLM_ENABLED=true
LLM_BASE_URL=http://ollama:11434
LLM_MODEL_NAME=hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF
LLM_TIMEOUT=90
SUMMARIZE_ON_SUBMIT=true

# Limits
MAX_TAGS_PER_USER=1000
MAX_RETRIES=3
```

See `docker/.env.example` for full configuration options.

## CLI Commands

All commands run via `docker exec -it logkeep python -m src.cli.admin <command>`:

```bash
# Setup
init-db                              # Create database schema
create-user                          # Create user (prompts for GitHub PAT, repo)
create-invite --count 5              # Generate invite codes

# User management
list-users                           # Show all users
activate-user <username>             # Enable user
deactivate-user <username>           # Disable user
test-github <username>               # Test GitHub connection

# Summaries
backfill-summaries <username>        # Generate summaries for existing links

# Debugging
view-failed-links --username <user>  # Show failed links
retry-failed <username>              # Retry failed links
list-invites --unused                # Show available invites
```

## Architecture

```
┌──────────┐
│  Mobile  │ → FastAPI (async) → PostgreSQL (link, tags, score)
│ Browser  │    ↓         ↓
└──────────┘    │         └→ BackgroundTasks
                │              ↓
                │         Title extraction (trafilatura)
                │              ↓
                │         Summarization (Ollama/GPU)
                │              ↓
                │         PostgreSQL
                │              ↓
                └────────→ GitHub API commit (optional)
                           |
                           └→ LogSeq journal (link, title, tags, score)
```

- **Stack**: FastAPI, SQLAlchemy, PostgreSQL, Jinja2, Ollama, Docker
- **Models**: User, Link, Tag, Invite (normalized many-to-many)
- **Processing**: Async background tasks with retry logic, status tracking
- **Security**: Bcrypt passwords, Fernet-encrypted GitHub tokens, JWT sessions

## Logseq Entry Format

```markdown
- [[Article Title]] [link](https://example.com/article) #links #tag1 #tag2 0.8
```

Entries append to `journals/YYYY_MM_DD.md` with optional score (0.0-1.0).

## CI/CD Workflow

LogKeep uses a two-environment deployment strategy with automated pipelines:

### Branch Strategy

- **`dev`** → Staging environment (`staging.perdrizet.org`)
- **`main`** → Production environment (`logkeep.perdrizet.org`)

### Automated Deployments

**Staging Deployment** (on push to `dev`):
1. Build Docker image with `dev` tag
2. Push to Docker Hub and GitHub Container Registry
3. SSH to VPS and deploy to staging container (port 8003)
4. Run smoke tests (health check + database connectivity)
5. Accessible at `https://staging.perdrizet.org` (basic auth protected)

**Production Deployment** (on push to `main`):
1. Build Docker image with `latest` and SHA tags
2. Push to registries
3. Blue/green deployment:
   - Deploy to inactive slot (blue or green)
   - Health check validation
   - Nginx traffic switch
   - Keep old version running for 5 minutes (rollback capability)
   - Clean up old container
4. Accessible at `https://logkeep.perdrizet.org`

### Manual Deployments

Workflows can be manually triggered with custom image tags:

```bash
# Via GitHub Actions UI:
# Actions → Deploy to Staging/Production → Run workflow → Select tag
```

### Required GitHub Secrets

Configure in **Settings → Secrets and variables → Actions**:

- `DOCKER_USERNAME` - Docker Hub username
- `DOCKER_PASSWORD` - Docker Hub access token
- `VPS_HOST` - VPS hostname or IP
- `VPS_USER` - SSH username
- `VPS_SSH_PRIVATE_KEY` - SSH private key for deployment access

See [docs/GITHUB_SECRETS.md](docs/GITHUB_SECRETS.md) for detailed setup.

### Development Workflow

1. **Create feature branch from dev:**
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/my-feature
   ```

2. **Develop and test locally:**
   ```bash
   docker-compose up -d
   # Make changes, test locally
   ```

3. **Push to dev for staging deployment:**
   ```bash
   git checkout dev
   git merge feature/my-feature
   git push origin dev
   # GitHub Actions automatically deploys to staging
   ```

4. **Test on staging:**
   - Visit `https://staging.perdrizet.org`
   - Verify changes work as expected

5. **Deploy to production:**
   ```bash
   git checkout main
   git merge dev
   git push origin main
   # GitHub Actions automatically deploys to production
   ```

### Rollback

If a deployment fails or causes issues:

**Staging**: Fix and push to `dev` (overwrites previous)

**Production**: 
- Automatic rollback on health check failure
- Manual rollback: `ssh vps "cd /opt/logkeep && ./scripts/rollback.sh"`

## Development

Live-reload enabled via `docker-compose.override.yml`:

```bash
# Start development environment
make dev

# View logs
make logs

# Check running containers
make ps

# Stop development environment
make clean

# Edit src/ files → uvicorn auto-reloads
# Edit templates/static → changes immediate
```

### Available Make Commands

```bash
make dev          # Start local development environment
make staging      # Start staging environment
make prod         # Start production environment
make logs         # View logs for dev environment
make staging-logs # View logs for staging
make prod-logs    # View logs for production
make ps           # List running containers
make health       # Check health endpoints
make clean        # Stop and remove dev containers
make help         # Show all available commands
```

Project structure:
```
src/
├── api/          # FastAPI routes
├── cli/          # Admin commands
├── models/       # SQLAlchemy models
├── services/     # Business logic (GitHub, LLM, processing)
├── templates/    # Jinja2 HTML
├── static/       # CSS
└── utils/        # Auth, encryption, database
```

## Troubleshooting

```bash
# Test GitHub connection
docker exec -it logkeep python -m src.cli.admin test-github <username>

# View failed links
docker exec -it logkeep python -m src.cli.admin view-failed-links --username <user>

# Check health status
make health

# View logs
make logs              # Development
make staging-logs      # Staging
make prod-logs         # Production

# Check Ollama status (if enabled)
docker logs -f logkeep-ollama
```

## License

MIT - See LICENSE file
