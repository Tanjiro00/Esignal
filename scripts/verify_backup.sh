#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_directory="${BACKUP_DIRECTORY:-$repository_root/var/backups}"
backup_path="${1:-}"

if [[ -z "$backup_path" ]]; then
  backup_path="$(find "$backup_directory" -maxdepth 1 -type f \( -name '*.sqlite3' -o -name '*.dump' \) -print | sort | tail -n 1)"
fi
if [[ -z "$backup_path" || ! -f "$backup_path" ]]; then
  echo "No backup file found" >&2
  exit 2
fi
if [[ ! -f "$backup_path.sha256" ]]; then
  echo "Missing checksum file: $backup_path.sha256" >&2
  exit 2
fi

(cd "$(dirname "$backup_path")" && sha256sum -c "$(basename "$backup_path").sha256")

case "$backup_path" in
  *.sqlite3)
    integrity="$(sqlite3 "$backup_path" "PRAGMA integrity_check;")"
    if [[ "$integrity" != "ok" ]]; then
      echo "SQLite integrity check failed: $integrity" >&2
      exit 1
    fi
    revision="$(sqlite3 "$backup_path" "SELECT version_num FROM alembic_version LIMIT 1;")"
    workspaces="$(sqlite3 "$backup_path" "SELECT COUNT(*) FROM workspaces;")"
    signals="$(sqlite3 "$backup_path" "SELECT COUNT(*) FROM signals;")"
    echo "Verified SQLite backup at revision $revision ($workspaces workspaces, $signals signals)"
    ;;
  *.dump)
    if command -v pg_restore >/dev/null 2>&1; then
      pg_restore --list "$backup_path" >/dev/null
    else
      docker compose exec -T postgres pg_restore --list <"$backup_path" >/dev/null
    fi
    echo "Verified PostgreSQL custom-format backup"
    ;;
  *)
    echo "Unsupported backup extension" >&2
    exit 2
    ;;
esac
