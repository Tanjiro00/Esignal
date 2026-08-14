#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

backup_path="${1:-}"
if [[ -z "$backup_path" || ! -f "$backup_path" ]]; then
  echo "Usage: $0 /absolute/path/to/backup.sqlite3-or-dump" >&2
  exit 2
fi
"$repository_root/scripts/verify_backup.sh" "$backup_path"

database_url="${DATABASE_URL:-$(uv run python -c 'from apps.api.config import get_settings; print(get_settings().database_url)')}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"

case "$backup_path" in
  *.sqlite3)
    if [[ "$database_url" != sqlite:///* ]]; then
      echo "SQLite backup cannot be restored into the configured database" >&2
      exit 2
    fi
    database_path="${database_url#sqlite:///}"
    if [[ "$database_path" != /* ]]; then
      database_path="$repository_root/${database_path#./}"
    fi
    if [[ -f "$database_path" ]]; then
      safety_copy="$database_path.before-restore-$timestamp"
      cp "$database_path" "$safety_copy"
      echo "Current database copied to: $safety_copy"
    fi
    sqlite3 "$database_path" ".restore '$backup_path'"
    ;;
  *.dump)
    if [[ "$database_url" != postgresql* ]]; then
      echo "PostgreSQL backup cannot be restored into the configured database" >&2
      exit 2
    fi
    if command -v pg_restore >/dev/null 2>&1; then
      pg_restore --clean --if-exists --no-owner --dbname="$database_url" "$backup_path"
    else
      docker compose exec -T postgres \
        pg_restore --clean --if-exists --no-owner \
        --username=earlysignal --dbname=earlysignal <"$backup_path"
    fi
    ;;
  *)
    echo "Unsupported backup extension" >&2
    exit 2
    ;;
esac

uv run alembic upgrade head
echo "Restore completed and migrations are at head"
