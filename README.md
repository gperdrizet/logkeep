# LogKeep

[![Deploy to Staging](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-staging.yml)
[![Deploy to Production](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml/badge.svg)](https://github.com/gperdrizet/logkeep/actions/workflows/deploy-production.yml)

LogKeep is an invite-only link curation app that extracts page content, applies optional LLM summarization, and writes structured entries to each user's configured GitHub repository.

## Features

- Invite-only multi-user access
- Asynchronous extraction and processing pipeline
- Optional summarization via OpenAI-compatible API
- Per-user GitHub repository integration
- Tagging, analytics, and Prometheus metrics (`/metrics`)

## Local Development

### Prerequisites

- Docker with Compose support
- Python 3.12 (for local CLI usage outside containers)

### Start the stack

```bash
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep
make setup
```

Edit `docker/.env` after `make setup` creates it from `docker/.env.example`.

Generate required secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run locally:

```bash
make dev
```

App URL: `http://localhost:8000`

### Local bootstrap

```bash
docker exec -it logkeep python -m src.cli.admin init-db
docker exec -it logkeep python -m src.cli.admin create-invite
```

## Environment Configuration

Environment templates:

- `docker/.env.example` (local)
- `docker/.env.staging.example`
- `docker/.env.production.example`

Core required security values in each environment:

- `SESSION_SECRET`
- `ENCRYPTION_KEY`

LLM summarization is enabled when all three values are configured:

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL_NAME`

## Deployment

Current CI/CD workflows:

| Workflow | Trigger | Purpose |
|---|---|---|
| `.github/workflows/test.yml` | Pull request to `main` | Installs dependencies and runs tests if present |
| `.github/workflows/deploy-staging.yml` | Push to `main` (or manual) | Deploys to staging and runs health check |
| `.github/workflows/deploy-production.yml` | Manual (`workflow_dispatch`) | Deploys pinned commit SHA to production, verifies health, tags and releases |

Required GitHub secrets:

- `VPS_SSH_PRIVATE_KEY`
- `VPS_HOST`
- `VPS_USER`

Production deploy requires workflow inputs:

- `version` (release tag value)
- `confirm=deploy`

## CLI

Run commands inside app container:

```bash
docker exec <container> python -m src.cli.admin <command>
```

Common commands:

- `init-db`
- `create-invite [--count N]`
- `create-user`
- `list-users`
- `activate-user <username>`
- `deactivate-user <username>`
- `test-github <username>`
- `backfill-summaries <username>`

## Project Docs

See [docs/README.md](docs/README.md) for deployment, operations, and environment references.
