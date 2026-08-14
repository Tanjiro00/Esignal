#!/usr/bin/env bash
set -euo pipefail

archive_path="${1:?archive path is required}"
evaluation_root="${2:?evaluation root is required}"
download_pid="${3:-}"
expected_bytes=28374466107
data_root="/opt/earlysignal/evaluation_data"
filtered_path="${data_root}/global_ai_tech_evidence.csv.gz"
train_filtered_path="${data_root}/global_ai_tech_train_evidence.csv.gz"
stats_path="${data_root}/global_ai_tech_filter_stats.json"
source_hash_path="${data_root}/youtube_trends.tar.bz2.sha256"

if [[ -n "${download_pid}" ]]; then
  while kill -0 "${download_pid}" 2>/dev/null; do
    sleep 30
  done
fi

actual_bytes="$(stat -c %s "${archive_path}")"
if [[ "${actual_bytes}" != "${expected_bytes}" ]]; then
  echo "archive size mismatch: expected ${expected_bytes}, got ${actual_bytes}" >&2
  exit 2
fi

if [[ ! -s "${source_hash_path}" ]]; then
  sha256sum "${archive_path}" >"${source_hash_path}"
fi
cd "${evaluation_root}"
# Python's streaming bz2/tar reader performs the CRC check without requiring a
# host-level `bzip2` executable. With `pipefail`, corruption aborts the filter.
PYTHONPATH="${evaluation_root}" python3 -m scripts.stream_tar_member \
  --archive "${archive_path}" \
  --member most_popular.csv |
  docker run --rm -i \
    --volume "${evaluation_root}:/evaluation:ro" \
    --volume "${data_root}:/data" \
    --workdir /evaluation \
    --env PYTHONPATH=/evaluation \
    earlysignal-api:latest \
    /app/.venv/bin/python -m scripts.filter_global_trending_archive \
    --output /data/global_ai_tech_evidence.csv.gz \
    --train-output /data/global_ai_tech_train_evidence.csv.gz \
    --train-max-collection-at "2024-06-30T23:59:59Z" \
    --stats-output /data/global_ai_tech_filter_stats.json
sha256sum "${filtered_path}" >"${filtered_path}.sha256"
sha256sum "${train_filtered_path}" >"${train_filtered_path}.sha256"
