# Backup and recovery

Private-beta targets are an RPO of 24 hours and an RTO of 4 hours. Back up
PostgreSQL/SQLite daily, before every schema release, and before a risky
provider or scoring migration. Keep at least 30 daily copies and one monthly
copy off-host. Raw provider payloads are a separate persistent volume and
should be copied to versioned object storage on the same retention schedule.

## Create and verify

```bash
BACKUP_DIRECTORY=/srv/earlysignal/backups make backup
BACKUP_DIRECTORY=/srv/earlysignal/backups make verify-backup
```

SQLite uses the online `.backup` command. PostgreSQL uses a custom-format
`pg_dump`. Both receive a sibling `.sha256` file. Verification checks the
checksum and then runs SQLite integrity/schema/count checks or
`pg_restore --list`.

The Operations page considers a backup healthy for 26 hours and shows only its
basename, age, and checksum state.

## Restore

1. Announce maintenance and stop API and worker writers.
2. Preserve current logs, Operations JSON, current database, and raw-payload
   volume.
3. Choose the newest verified backup from before the incident.
4. Restore it:

```bash
make restore-backup BACKUP_FILE=/absolute/path/to/earlysignal-backup
```

5. The script verifies the file first and migrates the restored database to
   head. For SQLite it also creates a timestamped copy of the current database.
   PostgreSQL uses `pg_restore --clean --if-exists --no-owner`; therefore the
   service must remain stopped.
6. Run `make verify-backup` against the source backup, start only the API, and
   verify workspace, signal, digest, brief, outcome, and product-event counts.
7. Open Pulse, Digest, a signal, and Admin → Operations. Start the worker only
   after the restored product reads correctly.

## Quarterly restore drill

Restore the newest backup into an isolated database, never the active target.
Run Alembic to head, integration tests, and read-only count/freshness queries.
Record source timestamp, checksum, restore duration, resulting revision,
counts, and any missing raw payload. A backup is not considered recoverable
until this drill succeeds.

Example isolated SQLite drill:

```bash
drill_dir="$(mktemp -d)"
DATABASE_URL="sqlite:///$drill_dir/recovery.db" \
  ./scripts/restore_backup.sh /absolute/path/to/backup.sqlite3
DATABASE_URL="sqlite:///$drill_dir/recovery.db" \
  uv run python -c "from apps.api.database import engine; print(engine.url)"
```
