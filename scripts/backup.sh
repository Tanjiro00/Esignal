#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

backup_directory="${BACKUP_DIRECTORY:-$repository_root/var/backups}"
mkdir -p "$backup_directory"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
database_url="${DATABASE_URL:-$(uv run python -c 'from apps.api.config import get_settings; print(get_settings().database_url)')}"

if [[ "$database_url" == sqlite:///* ]]; then
  database_path="${database_url#sqlite:///}"
  if [[ "$database_path" != /* ]]; then
    database_path="$repository_root/${database_path#./}"
  fi
  backup_path="$backup_directory/earlysignal-$timestamp.sqlite3"
  sqlite3 "$database_path" ".backup '$backup_path'"
elif [[ "$database_url" == postgresql* ]]; then
  backup_path="$backup_directory/earlysignal-$timestamp.dump"
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump --format=custom --file="$backup_path" "$database_url"
  else
    docker compose exec -T postgres \
      pg_dump --username=earlysignal --format=custom earlysignal >"$backup_path"
  fi
else
  echo "Unsupported DATABASE_URL scheme" >&2
  exit 2
fi

sha256sum "$backup_path" >"$backup_path.sha256"
echo "Backup created: $backup_path"
echo "Checksum: $backup_path.sha256"
