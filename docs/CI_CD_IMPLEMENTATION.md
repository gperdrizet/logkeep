# CI/CD Implementation

## Workflows

### `.github/workflows/test.yml`

- Trigger: pull requests to `main`
- Behavior:
  - Sets up Python 3.12
  - Installs `requirements.txt`
  - Runs pytest only if a `tests/` suite exists

### `.github/workflows/deploy-staging.yml`

- Trigger:
  - push to `main`
  - manual dispatch
- Behavior:
  - SSH to VPS (`port 44441`)
  - Syncs `/opt/logkeep-staging`
  - Builds and starts `docker/docker-compose.staging.yml`
  - Runs `python -m src.cli.admin init-db`
  - Verifies `http://100.64.0.1:8003/health`

### `.github/workflows/deploy-production.yml`

- Trigger: manual dispatch only
- Inputs:
  - `version`
  - `confirm` must equal `deploy`
- Behavior:
  - Deploys exact commit SHA (`github.sha`) to `/opt/logkeep`
  - Validates `docker/docker-compose.prod.yml`
  - Cleans stale production-named containers if present
  - Builds and starts production compose stack
  - Polls `/health` with retries and prints logs on failure
  - Tags the deployed commit and creates a GitHub release

## GitHub Environment/Secrets

Required repository secrets:

- `VPS_SSH_PRIVATE_KEY`
- `VPS_HOST`
- `VPS_USER`

Required environment approvals:

- `staging` environment for staging workflow
- `production` environment for production workflow
