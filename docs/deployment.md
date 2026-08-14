# Production deployment

The private-beta topology is one web process, one API process, one worker,
PostgreSQL 17 with pgvector, Redis with AOF, and a persistent raw-payload
volume. Only loopback ports `3000` and `8000` are published; terminate TLS and
route the public web/API hostnames through a reverse proxy.

## Prepare

1. Provision a Linux host with Docker Compose v2, persistent storage, HTTPS,
   monitoring, and an off-host backup destination.
2. Copy `.env.production.example` to a deployment-managed environment file.
   Set a random PostgreSQL password, the server-only YouTube key, the exact web
   origin, the public API URL ending in `/api/v1`, and the backup directory.
3. Keep the environment file outside source control and readable only by the
   deployment account. Rotate any credential that has been pasted into chat,
   an issue, or a log.
4. Point the reverse proxy at `127.0.0.1:3000` for the web hostname and
   `127.0.0.1:8000` for the API hostname.

Validate interpolation before changing services:

```bash
docker compose --env-file /secure/earlysignal.env \
  -f docker-compose.production.yml config --quiet
```

For a source-based release, build and import-check the exact API/worker image
before replacing the healthy containers:

```bash
./scripts/production_preflight.sh /secure/earlysignal.env
```

The import check is intentionally executed inside the built image. It catches
partial release bundles where an application module has been updated without
the package exports it imports.

## Release

```bash
./scripts/production_preflight.sh /secure/earlysignal.env
docker compose --env-file /secure/earlysignal.env \
  -f docker-compose.production.yml up -d postgres redis
docker compose --env-file /secure/earlysignal.env \
  -f docker-compose.production.yml run --rm api uv run alembic upgrade head
docker compose --env-file /secure/earlysignal.env \
  -f docker-compose.production.yml up -d api worker web
```

The API container also runs `alembic upgrade head` on startup, so the explicit
migration command is a visible preflight rather than a separate requirement.
Do not run two migrations concurrently.

Verify:

```bash
curl --fail https://api.earlysignal.example.com/health
curl --fail https://api.earlysignal.example.com/api/v1/admin/operations/readiness
docker compose --env-file /secure/earlysignal.env \
  -f docker-compose.production.yml ps
```

Open Pulse, Digest, one signal detail, and Admin → Operations. Confirm that
provider evidence is live, CORS accepts only the intended web origin, and the
worker advances scheduled runs.

## Rollback

Application rollback is image-based: redeploy the last known-good source/image
while keeping PostgreSQL and raw-payload volumes. Database migrations are
forward-only during the private beta. If a migration has damaged data, stop API
and worker and restore the pre-release verified backup; do not run an automatic
Alembic downgrade against production data.

Take and verify a backup before every schema release:

```bash
BACKUP_DIRECTORY=/srv/earlysignal/backups make backup
BACKUP_DIRECTORY=/srv/earlysignal/backups make verify-backup
```

## Scheduling

Run `make backup` daily through the host scheduler and copy the backup plus its
checksum off-host. The worker owns ingestion and digest schedules; do not run a
second worker unless job-claiming is upgraded from this single-worker MVP.
