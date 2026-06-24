# Documentation Index

This directory documents the current LogKeep runtime and deployment model.

## Minimum Set

- `DEPLOYMENT.md`: staging and production deployment runbook
- `CI_CD_IMPLEMENTATION.md`: workflow behavior and release flow

## Current Implementation (At a Glance)

- Runtime: FastAPI app (`logkeep`) + PostgreSQL (`logkeep-postgres`) in Docker
- Environments:
	- Staging at `/opt/logkeep-staging` using `docker/docker-compose.staging.yml`
	- Production at `/opt/logkeep` using `docker/docker-compose.prod.yml`
- Security keys:
	- `SESSION_SECRET` for session/JWT signing
	- `ENCRYPTION_KEY` for Fernet encryption of stored sensitive credentials
- Optional summarization uses OpenAI-compatible API when these are set:
	- `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL_NAME`

## Environment Templates

- `docker/.env.example`: local development
- `docker/.env.staging.example`: staging deployment
- `docker/.env.production.example`: production deployment

For deployment and CI/CD details, use only the two core docs above.
