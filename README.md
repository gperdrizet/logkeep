# LogKeep

[![Deploy to Staging](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml)
[![Deploy to Production](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml)

Link curation with AI summarization and LogSeq integration via GitHub.

## What it does

Submit a URL, pick tags, and LogKeep handles the rest: it fetches the page, extracts the title and content, generates an AI summary (optional), and commits a formatted entry to a GitHub-hosted LogSeq graph. Designed for quick capture from mobile.

- **Invite-only registration** — multi-user, each user has their own GitHub repo and tag collection
- **Background processing** — extraction and GitHub commits happen asynchronously after submission
- **AI summarization** — optional, via a local Ollama instance; GPU-accelerated if available
- **Tag management** — personal tag collections with autocomplete
- **Analytics** — score and tag usage histograms on the data page
- **Prometheus metrics** — exposed at `/metrics`

## Development

### Prerequisites

- Docker and Docker Compose
- A GitHub PAT with `repo` scope (for GitHub integration)

### Running locally

```bash
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep
cp docker/.env.example docker/.env.development
# Edit docker/.env.development — set SESSION_SECRET, ENCRYPTION_KEY, database credentials
make dev
```

Generate the required secret values:

```bash
# ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# SESSION_SECRET
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Initialize and create the first user:

```bash
docker exec -it logkeep python -m src.cli.admin init-db
docker exec -it logkeep python -m src.cli.admin create-invite
docker exec -it logkeep python -m src.cli.admin create-user
```

App is available at `http://localhost:8000`.

### LLM summarization (optional)

Set in `.env.development`:

```bash
LLM_ENABLED=true
LLM_BASE_URL=http://ollama:11434
LLM_MODEL_NAME=hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF
SUMMARIZE_ON_SUBMIT=true
```

The `make dev` compose file includes an Ollama container. An NVIDIA GPU with `nvidia-container-toolkit` is required for GPU acceleration; CPU inference works without it.

## Deployment

### CI/CD overview

Three GitHub Actions workflows manage the pipeline:

| Workflow | Trigger | What it does |
|---|---|---|
| `test.yml` | PR to `main` | Runs pytest — blocks merge on failure |
| `deploy-staging.yml` | Push to `main` | Deploys to staging server via SSH |
| `deploy-production.yml` | Manual (`workflow_dispatch`) | Deploys to production, creates GitHub release |

Required GitHub secrets: `VPS_SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`.

### Staging

Staging deploys automatically on every push to `main`. The environment is accessible on the tailnet at `http://100.64.0.1:8003`.

### Production

Trigger manually from the **Actions** tab → **Deploy to Production**. Inputs:

- `version` — release version (e.g. `1.2.0`)
- `confirm` — must type `deploy` to proceed

The workflow deploys, runs a health check, tags the commit, and creates a GitHub release.

### Initializing a new deployment

After the first deploy, the database schema needs to be created and at least one invite code generated before anyone can register:

```bash
# Replace logkeep-staging with logkeep for production
docker exec logkeep-staging python -m src.cli.admin init-db
docker exec logkeep-staging python -m src.cli.admin create-invite
```

Subsequent deploys run `init-db` automatically (it is idempotent).

## CLI reference

All commands: `docker exec <container> python -m src.cli.admin <command>`

```bash
# Database
init-db                              # Create tables (safe to re-run)

# Users
create-user                          # Interactive: username, password, GitHub PAT, repo
list-users                           # Show all users and status
activate-user <username>             # Re-enable a deactivated account
deactivate-user <username>           # Disable login for a user
test-github <username>               # Verify GitHub token and repo access

# Invites
create-invite [--count N]            # Generate N invite codes (default: 1)
list-invites [--unused]              # List all or only unused codes

# Summaries
backfill-summaries <username>        # Generate summaries for links that don't have one
```
