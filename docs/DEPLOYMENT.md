# Deployment Runbook

## Runtime Targets

- Staging checkout: `/opt/logkeep-staging`
- Production checkout: `/opt/logkeep`

## Environment Files

- Staging: `docker/.env.staging`
- Production: `docker/.env.production`

Create from templates:

```bash
cp docker/.env.staging.example docker/.env.staging
cp docker/.env.production.example docker/.env.production
```

Generate security values:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Staging Deployment

Automatic on push to `main` and also available via manual dispatch.

Workflow:

- `.github/workflows/deploy-staging.yml`

Post-deploy verification:

```bash
curl -fsS http://100.64.0.1:8003/health
```

## Production Deployment

Manual only.

Workflow:

- `.github/workflows/deploy-production.yml`

Required inputs:

- `version`
- `confirm=deploy`

Post-deploy verification:

```bash
curl -fsS http://127.0.0.1:8000/health
```

## Nginx Configuration

`nginx/*.conf` are source-of-truth files in this repo but are **not** deployed
by CI/CD — the VPS runs system nginx, not a containerized one. After changing
a file under `nginx/`, apply it manually on the VPS:

```bash
sudo cp nginx/logkeep.conf /etc/nginx/conf.d/logkeep.conf
sudo nginx -t && sudo systemctl reload nginx
```

## First-Time Database Bootstrap

Run once per new environment database:

```bash
docker exec logkeep python -m src.cli.admin init-db
docker exec logkeep python -m src.cli.admin create-invite
```

For staging container name:

```bash
docker exec logkeep-staging python -m src.cli.admin init-db
docker exec logkeep-staging python -m src.cli.admin create-invite
```

## Data Migration (Postgres to Postgres)

When importing an existing production dataset:

1. dump source database
2. backup current target database
3. restore source dump into target
4. restart app and verify health

Always take a pre-restore backup before replacing target data.
