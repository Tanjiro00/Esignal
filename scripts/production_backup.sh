#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
environment_file="$repository_root/.env.production"
compose_file="$repository_root/docker-compose.production.yml"

if [[ ! -f "$environment_file" ]]; then
  echo "Missing production environment file: $environment_file" >&2
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$environment_file"
set +a

backup_directory="${BACKUP_DIRECTORY:-$repository_root/backups}"
mkdir -p "$backup_directory"
chmod 700 "$backup_directory"

exec 9>"$backup_directory/.backup.lock"
if ! flock -n 9; then
  echo "Another backup is already running" >&2
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$backup_directory/earlysignal-$timestamp.dump"
temporary_path="$(mktemp "$backup_directory/.earlysignal-$timestamp.XXXXXX.dump")"

cleanup() {
  rm -f "$temporary_path"
}
trap cleanup EXIT

compose=(
  docker compose
  --env-file "$environment_file"
  -f "$compose_file"
)

"${compose[@]}" exec -T postgres \
  pg_dump --username=earlysignal --format=custom earlysignal >"$temporary_path"
"${compose[@]}" exec -T postgres \
  pg_restore --list <"$temporary_path" >/dev/null

chmod 600 "$temporary_path"
mv "$temporary_path" "$backup_path"
sha256sum "$backup_path" >"$backup_path.sha256"
chmod 600 "$backup_path.sha256"
trap - EXIT

echo "Verified PostgreSQL backup created: $backup_path"
