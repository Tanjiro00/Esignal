#!/usr/bin/env bash
set -euo pipefail

environment_file="${1:-.env.production}"
compose=(
  docker compose
  --env-file "${environment_file}"
  -f docker-compose.production.yml
)

"${compose[@]}" config --quiet
"${compose[@]}" build api worker

# Import the application and worker from the exact image that will be started.
# This catches incomplete source bundles and missing cross-package exports before
# the currently healthy containers are replaced.
"${compose[@]}" run --rm --no-deps api \
  uv run --no-sync python -c \
  "import apps.api.main; import apps.worker.topic_intelligence"

# Operational scripts must be invoked as modules from the monorepo root. Check
# the exact production entrypoint so a release cannot leave the shadow audit
# present in the image but unusable because Python resolves only /app/scripts.
"${compose[@]}" run --rm --no-deps worker \
  uv run --no-sync python -m scripts.audit_semantic_release_queue --help \
  >/dev/null
